"""Day 06 pipeline entry point.

From ``starter/``:
    python -m src.run ingest                 # corpus -> units -> chunks A/B -> embeddings -> pgvector (A, B, C)
    python -m src.run benchmark --split dev  # top-3 traces + Hit@1/Hit@3 for A, B, C on dev
    python -m src.run select                 # apply the pre-registered rule on dev metrics
    python -m src.run benchmark --split test # run test once, after selection
    python -m src.run audit-prep             # samples/sheets for manual labelling
    python -m src.run all                    # everything above in order
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import statistics as st
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .corpus import build_manifest, load_corpus
from .evaluation import evaluate_query, summarize
from .ingestion import section_at

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
RESULTS = ROOT / "results"
BENCHMARK = ROOT / "benchmark" / "questions.jsonl"

STRATEGIES: dict[str, dict[str, Any]] = {
    "A": {"chunking": "fixed_size", "chunk_size": 500, "overlap": 50, "use_filter": False,
          "description": "Fixed 500-char windows, 50-char overlap, inside each unit; metadata stored, no filter."},
    "B": {"chunking": "by_paragraph", "chunk_size": 800, "overlap": 0, "use_filter": False,
          "description": "Paragraph/heading-aware groups up to 800 chars (heading starts a chunk); no filter."},
    "C": {"chunking": "by_paragraph", "chunk_size": 800, "overlap": 0, "use_filter": True,
          "description": "Same chunks and vectors as B; SQL WHERE pep_type=<value> applied only when the question carries a filter."},
}
TOP_K = 3


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def log_event(event: str, **kw: Any) -> None:
    RESULTS.mkdir(exist_ok=True)
    with (RESULTS / "run_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now(), "event": event, **kw}, ensure_ascii=False, default=str) + "\n")


def env() -> tuple[str, str | None]:
    load_dotenv(STARTER / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL missing: copy starter/.env.example to starter/.env")
    return url, os.getenv("EMBEDDING_MODEL") or None


def make_chunks(strategy: str, pages, docs) -> list:
    cfg = STRATEGIES[strategy]
    doc_by_id = {d.document_id: d for d in docs}
    out = []
    for p in pages:
        cs = (fixed_size(p, cfg["chunk_size"], cfg["overlap"]) if cfg["chunking"] == "fixed_size"
              else by_paragraph(p, cfg["chunk_size"]))
        for c in cs:
            c.metadata["section"] = section_at(doc_by_id[c.document_id], c.metadata["char_start"])
        out.extend(cs)
    return out


def length_stats(values: list[int]) -> dict[str, Any]:
    v = sorted(values)
    q = lambda f: v[min(len(v) - 1, int(f * len(v)))]  # noqa: E731
    return {"n": len(v), "min": v[0], "p10": q(0.1), "median": int(st.median(v)), "mean": round(st.mean(v), 1),
            "p90": q(0.9), "max": v[-1], "total": sum(v)}


# ----------------------------------------------------------------------------- ingest
def cmd_ingest(args) -> None:
    from .embeddings import MyEmbedder
    from .store import PgVectorStore

    url, model_name = env()
    t0 = time.perf_counter()
    cfg, docs, pages = load_corpus()
    t_load = time.perf_counter() - t0
    if len(pages) < 30:
        raise SystemExit(f"only {len(pages)} content units (<30)")
    manifest = build_manifest(cfg, docs, pages)
    write_json(ROOT / "data" / "manifest.json", manifest)
    log_event("corpus_loaded", units=len(pages), docs=len(docs), seconds=round(t_load, 3),
              processing_logs={d.document_id: d.log for d in docs})

    t0 = time.perf_counter()
    emb = MyEmbedder(model_name)
    t_model = time.perf_counter() - t0
    store = PgVectorStore(url, emb.dimensions)
    store.create_schema()

    chunk_sets = {"A": make_chunks("A", pages, docs), "B": make_chunks("B", pages, docs)}
    chunk_sets["C"] = chunk_sets["B"]                       # identical chunks, separate index rows
    vec_cache: dict[str, list[float]] = {}
    report: dict[str, Any] = {"run_at": now(), "embedding": emb.describe(),
                              "vector_store": {"backend": "PostgreSQL + pgvector", "server_version": store.server_version,
                                               "pgvector_version": store.pgvector_version, "table": "day6_chunks",
                                               "metric": "cosine distance (<=>), score = 1 - distance",
                                               "search": "exact (no ANN index; sequential scan + ORDER BY)"},
                              "corpus": {"documents": len(docs), "units": len(pages),
                                         "normalized_chars": manifest["total_normalized_chars"],
                                         "load_and_normalize_seconds": round(t_load, 3)},
                              "model_load_seconds": round(t_model, 2),
                              "python": platform.python_version(), "machine": platform.platform(),
                              "cpu_count": os.cpu_count(), "strategies": {}}
    for s in ("A", "B", "C"):
        chunks = chunk_sets[s]
        existing = store.existing_hashes(s)
        todo = [c for c in chunks if existing.get(c.chunk_id) != (c.metadata["content_hash"], emb.model_name)]
        need = [c for c in todo if c.metadata["content_hash"] not in vec_cache]
        t0 = time.perf_counter()
        if need:
            vecs = emb.embed_documents([c.text for c in need])
            for c, v in zip(need, vecs):
                vec_cache[c.metadata["content_hash"]] = v
        t_embed = time.perf_counter() - t0
        todo_ids = {c.chunk_id for c in todo}
        vectors = [vec_cache[c.metadata["content_hash"]] if c.chunk_id in todo_ids else None for c in chunks]
        t0 = time.perf_counter()
        st_up = store.upsert(s, chunks, vectors, model=emb.model_name)
        t_store = time.perf_counter() - t0
        toks = emb.token_lengths([c.text for c in chunks])
        lens = [len(c.text) for c in chunks]
        report["strategies"][s] = {
            **STRATEGIES[s],
            "chunk_count": len(chunks),
            "chunk_chars": length_stats(lens),
            "chunk_tokens": length_stats(toks),
            "chunks_truncated_over_max_seq_length": sum(t > emb.max_seq_length for t in toks),
            "newly_embedded_texts": len(need),
            "embed_seconds": round(t_embed, 2),
            "store_seconds": round(t_store, 2),
            "upsert": st_up,
            "rows_in_store_after": store.count(s),
            "cost_usd": 0,
        }
        if s in ("A", "B"):
            write_jsonl(RESULTS / f"chunks_{s}.jsonl",
                        [{"chunk_id": c.chunk_id, "document_id": c.document_id, "page": c.page,
                          "section": c.metadata["section"], "pep_type": c.metadata["pep_type"],
                          "char_start": c.metadata["char_start"], "char_end": c.metadata["char_end"],
                          "n_chars": c.metadata["n_chars"], "tokens": t, "text": c.text}
                         for c, t in zip(chunks, toks)])
        log_event("ingest_strategy", strategy=s, **{k: report["strategies"][s][k] for k in
                  ("chunk_count", "newly_embedded_texts", "embed_seconds", "upsert", "rows_in_store_after")})
    name = args.report or "ingest_stats.json"
    write_json(RESULTS / name, report)
    store.close()
    print(json.dumps({s: {k: v for k, v in r.items() if k in ("chunk_count", "newly_embedded_texts", "embed_seconds",
                                                              "upsert", "rows_in_store_after",
                                                              "chunks_truncated_over_max_seq_length")}
                      for s, r in report["strategies"].items()}, indent=2))


# -------------------------------------------------------------------------- benchmark
def load_questions() -> list[dict]:
    return [json.loads(l) for l in BENCHMARK.read_text(encoding="utf-8").splitlines() if l.strip()]


def cmd_benchmark(args) -> None:
    from .embeddings import MyEmbedder
    from .store import PgVectorStore

    split = args.split
    if split == "test" and not (RESULTS / "selection.json").exists() and not args.force:
        raise SystemExit("run `python -m src.run select` on dev first (pre-registered rule); --force to override")
    url, model_name = env()
    emb = MyEmbedder(model_name)
    store = PgVectorStore(url, emb.dimensions)
    qs = [q for q in load_questions() if split == "all" or q["split"] == split]
    traces, timing = [], {}
    qvec = {}
    t0 = time.perf_counter()
    for q in qs:
        qvec[q["id"]] = emb.embed_query(q["question"])
    t_q = time.perf_counter() - t0
    from .evaluation import gold_pairs, norm_match
    for s, cfg in STRATEGIES.items():
        # Is the evidence contained in at least one chunk of this index? (False = split by chunking)
        with store.conn.cursor() as cur:
            cur.execute("SELECT document_id, page, text FROM day6_chunks WHERE strategy=%s", (s,))
            by_page: dict = {}
            for d, pg, tx in cur.fetchall():
                by_page.setdefault((d, pg), []).append(norm_match(tx))
        t0 = time.perf_counter()
        for q in qs:
            flt = q.get("filter") if cfg["use_filter"] else None
            hits = store.search(s, qvec[q["id"]], TOP_K, flt)
            tr = evaluate_query(q, hits)
            tr["strategy"] = s
            tr["filter_applied"] = flt
            tr["evidence_in_single_chunk_of_index"] = any(
                norm_match(g["evidence_quote"]) in t for g in gold_pairs(q)
                for t in by_page.get((g["source_id"], g["page"]), []))
            tr["expected_answer"] = q["expected_answer"]
            traces.append(tr)
        timing[s] = round((time.perf_counter() - t0) / max(1, len(qs)) * 1000, 2)
    summary = summarize(traces)
    out = {"run_at": now(), "split": split, "n_questions": len(qs), "top_k": TOP_K,
           "embedding_model": emb.describe()["model"], "query_embed_seconds_total": round(t_q, 3),
           "search_ms_per_query": timing, "metrics": summary}
    write_jsonl(RESULTS / f"traces_{split}.jsonl", traces)
    write_json(RESULTS / f"metrics_{split}.json", out)
    log_event("benchmark", split=split, metrics=summary)
    store.close()
    print(json.dumps(out["metrics"], indent=2))


def cmd_select(args) -> None:
    m = json.loads((RESULTS / "metrics_dev.json").read_text())["metrics"]
    ing = json.loads((RESULTS / "ingest_stats.json").read_text())["strategies"]

    def key(s):
        d = m[s]["dev"]
        return (d["evidence_hit_at_3_pct"], d["hit_at_1_pct"], -ing[s]["chunk_count"])
    ranking = sorted(m, key=key, reverse=True)
    ties = [s for s in ranking if key(s) == key(ranking[0])]
    sel = {"decided_at": now(), "rule": "max dev Evidence Hit@3 -> max dev Hit@1 -> fewer chunks",
           "tied_on_all_criteria": ties,
           "tie_note": ("tie not broken by the pre-registered rule; first in A/B/C order is reported"
                        if len(ties) > 1 else None),
           "dev_metrics": {s: m[s]["dev"] for s in m}, "ranking": ranking, "selected": ranking[0],
           "note": "decided before the test split was run"}
    write_json(RESULTS / "selection.json", sel)
    log_event("selection", selected=ranking[0], ranking=ranking)
    print(json.dumps(sel, indent=2))


# ------------------------------------------------------------------------ audit prep
def cmd_audit_prep(args) -> None:
    """Build labelling sheets. Labels are filled by a human reviewer, never computed here."""
    _, docs, pages = load_corpus()
    audit = RESULTS / "audit"
    audit.mkdir(parents=True, exist_ok=True)
    # 1) Coherence: 10 positions fixed by rule BEFORE looking at any score:
    #    units sorted by unit_id, take indices round(i*N/10), i=0..9; position = unit midpoint.
    units = sorted(pages, key=lambda p: p.metadata["unit_id"])
    N = len(units)
    positions = []
    for i in range(10):
        u = units[round(i * N / 10)]
        mid = (u.metadata["char_start"] + u.metadata["char_end"]) // 2
        positions.append({"pos_id": f"P{i+1:02d}", "unit_id": u.metadata["unit_id"],
                          "document_id": u.document_id, "doc_offset": mid})
    chunks = {s: [json.loads(l) for l in (RESULTS / f"chunks_{s}.jsonl").read_text().splitlines()] for s in ("A", "B")}
    rows = []
    for p in positions:
        for s in ("A", "B", "C"):
            src = chunks["B" if s == "C" else s]
            cover = [c for c in src if c["document_id"] == p["document_id"]
                     and c["char_start"] <= p["doc_offset"] < c["char_end"]]
            # several chunks may cover the position (overlap): take the one whose centre is closest
            c = min(cover, key=lambda c: abs((c["char_start"] + c["char_end"]) / 2 - p["doc_offset"]))
            doc = next(d for d in docs if d.document_id == p["document_id"])
            rows.append({**p, "strategy": s, "chunk_id": c["chunk_id"], "n_covering_chunks": len(cover),
                         "context_word": doc.text[p["doc_offset"]:p["doc_offset"] + 40].replace("\n", " "),
                         "chunk_text": c["text"], "label_0_1_2": "", "reason": ""})
    write_json(audit / "coherence_sample.json", {"rule": "units sorted by unit_id; idx=round(i*N/10); offset=unit midpoint",
                                                  "N_units": N, "positions": positions, "rows": rows})
    # 2) Grounding + metadata sheet for the test split (all strategies x top-3).
    tpath = RESULTS / "traces_test.jsonl"
    if tpath.exists():
        traces = [json.loads(l) for l in tpath.read_text().splitlines()]
        page_idx = {(p.document_id, p.page): p for p in pages}
        meta_rows = []
        for t in traces:
            for h in t["hits"]:
                unit = page_idx.get((h["document_id"], h["page"]))
                doc = next(d for d in docs if d.document_id == h["document_id"])
                checks = {
                    "source_matches_doc": h["source"].endswith(f"peps/{h['document_id']}.rst"),
                    "text_inside_claimed_page": bool(unit) and h["text"] in unit.text,
                    "offsets_reproduce_text": doc.text[h["char_start"]:h["char_end"]] == h["text"],
                    "pep_type_matches_header": h["pep_type"] == doc.header.get("Type"),
                    "status_matches_header": h["status"] == doc.header.get("Status"),
                    "python_version_matches_header": (h["python_version"] or None) == doc.header.get("Python-Version"),
                    "section_matches_heading_path": h["section"] == section_at(doc, h["char_start"]),
                }
                meta_rows.append({"strategy": t["strategy"], "question_id": t["question_id"], "rank": h["rank"],
                                  "chunk_id": h["chunk_id"], "document_id": h["document_id"], "page": h["page"],
                                  "section": h["section"], "pep_type": h["pep_type"],
                                  **checks, "all_correct": all(checks.values()),
                                  "filter": t["filter"], "filter_applied": t["filter_applied"]})
        with (audit / "metadata_check_test.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(meta_rows[0].keys()))
            w.writeheader()
            w.writerows(meta_rows)
        g_rows = [{"strategy": t["strategy"], "question_id": t["question_id"], "question": t["question"],
                   "expected_answer": t["expected_answer"], "auto_hit_at_3": t["hit_at_3"],
                   "top3": [{"rank": h["rank"], "chunk_id": h["chunk_id"], "score": h["score"], "text": h["text"]}
                            for h in t["hits"]], "grounding_0_1_2": "", "reason": ""} for t in traces]
        write_json(audit / "grounding_sheet_test.json", g_rows)
    print(f"audit sheets written to {audit}")


def cmd_all(args) -> None:
    cmd_ingest(args)
    args.split = "dev"
    cmd_benchmark(args)
    cmd_select(args)
    args.split = "test"
    cmd_benchmark(args)
    cmd_audit_prep(args)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest")
    p.add_argument("--report", default=None, help="file name for the ingest report (default ingest_stats.json)")
    p = sub.add_parser("benchmark")
    p.add_argument("--split", choices=["dev", "test", "all"], required=True)
    p.add_argument("--force", action="store_true")
    sub.add_parser("select")
    sub.add_parser("audit-prep")
    p = sub.add_parser("all")
    p.add_argument("--report", default=None)
    p.add_argument("--force", action="store_true")
    a = ap.parse_args()
    {"ingest": cmd_ingest, "benchmark": cmd_benchmark, "select": cmd_select,
     "audit-prep": cmd_audit_prep, "all": cmd_all}[a.cmd](a)


if __name__ == "__main__":
    main()
