"""Pre-run check: every gold/alternative evidence quote must exist in its gold unit.

Run BEFORE any retrieval. Writes results/benchmark_verification.json.
Usage (from starter/):  python scripts/verify_benchmark.py
"""
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.corpus import load_corpus  # noqa: E402
from src.evaluation import gold_pairs, norm_match  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
qs = [json.loads(l) for l in (ROOT / "benchmark/questions.jsonl").read_text().splitlines() if l.strip()]
_, _, pages = load_corpus()
idx = {(p.document_id, p.page): p for p in pages}
rows, bad = [], 0
for q in qs:
    for g in gold_pairs(q):
        p = idx.get((g["source_id"], g["page"]))
        ok = bool(p) and norm_match(g["evidence_quote"]) in norm_match(p.text)
        bad += not ok
        rows.append({"id": q["id"], "source_id": g["source_id"], "page": g["page"],
                     "unit_id": p.metadata["unit_id"] if p else None, "found": ok,
                     "evidence_chars": len(g["evidence_quote"])})
    if q.get("filter"):
        for k, v in q["filter"].items():
            vals = {str(p.metadata.get(k)) for p in pages}
            assert str(v) in vals, f"{q['id']}: filter value {v!r} not in corpus metadata {vals}"
            gp = idx[(q["gold_source_id"], int(q["gold_page"]))]
            assert str(gp.metadata.get(k)) == str(v), f"{q['id']}: gold not inside filter scope"
split = Counter(q["split"] for q in qs)
filt = Counter(q["split"] for q in qs if q.get("filter"))
out = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
       "n_questions": len(qs), "split": dict(split), "filter_questions": dict(filt),
       "types": dict(Counter(q["type"] for q in qs)), "all_evidence_found": bad == 0, "rows": rows}
res = ROOT / "results"
res.mkdir(exist_ok=True)
(res / "benchmark_verification.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
for r in rows:
    if not r["found"]:
        print("NOT FOUND:", r)
print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2))
sys.exit(0 if bad == 0 else 1)
