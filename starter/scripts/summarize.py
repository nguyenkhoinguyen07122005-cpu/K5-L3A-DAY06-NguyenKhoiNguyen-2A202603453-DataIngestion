"""Aggregate metrics + manual labels into results/summary.json and results/summary.md.

Usage (from starter/):  python scripts/summarize.py
Reads: results/metrics_{dev,test}.json, results/ingest_stats.json,
       results/audit/{coherence_labels.csv, grounding_labels.csv, metadata_check_test.csv}
"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "results"
ing = json.loads((R / "ingest_stats.json").read_text())
md = {sp: json.loads((R / f"metrics_{sp}.json").read_text()) for sp in ("dev", "test")}
coh = list(csv.DictReader((R / "audit/coherence_labels.csv").open(encoding="utf-8")))
gro = list(csv.DictReader((R / "audit/grounding_labels.csv").open(encoding="utf-8")))
meta = list(csv.DictReader((R / "audit/metadata_check_test.csv").open(encoding="utf-8")))

out = {}
for s in ("A", "B", "C"):
    st = ing["strategies"][s]
    c = [int(r["label_0_1_2"]) for r in coh if r["strategy"] == s]
    g = [int(r["grounding_0_1_2"]) for r in gro if r["strategy"] == s]
    m = [r for r in meta if r["strategy"] == s]
    out[s] = {
        "chunk_count": st["chunk_count"],
        "chunk_chars_median": st["chunk_chars"]["median"],
        "chunk_tokens_median": st["chunk_tokens"]["median"],
        "truncated_chunks": st["chunks_truncated_over_max_seq_length"],
        "embed_seconds": st["embed_seconds"], "store_seconds": st["store_seconds"],
        "newly_embedded_texts": st["newly_embedded_texts"], "cost_usd": 0,
        "search_ms_per_query": {sp: md[sp]["search_ms_per_query"][s] for sp in md},
        "dev": md["dev"]["metrics"][s]["dev"], "test": md["test"]["metrics"][s]["test"],
        "coherence": {"n": len(c), "mean_of_2": round(sum(c) / len(c), 2), "counts": dict(Counter(c))},
        "grounding_test": {"n": len(g), "mean_of_2": round(sum(g) / len(g), 2),
                           "counts": {k: Counter(g).get(k, 0) for k in (0, 1, 2)}},
        "metadata_test": {"correct": sum(r["all_correct"] == "True" for r in m), "checked": len(m)},
    }
(R / "summary.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))

L = ["| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Embed + store (s) | Search ms/query | Cost |",
     "|---|---|---|---|---|---|---|---|"]
for s, o in out.items():
    for sp in ("dev", "test"):
        emb = "0 (reuse B vectors) + %.2f" % o["store_seconds"] if s == "C" else "%.2f + %.2f" % (o["embed_seconds"], o["store_seconds"])
        L.append(f"| {s} | {sp} | {o[sp]['hit_at_1']} | {o[sp]['evidence_hit_at_3']} | {o['chunk_count']} | {emb} | "
                 f"{o['search_ms_per_query'][sp]} | $0 |")
L += ["", "| Strategy | Coherence mean /2 (n) | Metadata đủ & đúng (n/N, test top-3) | Filter tuân thủ dev | Filter tuân thủ test | Grounding 0/1/2 (test) | Grounding mean /2 |",
      "|---|---|---|---|---|---|---|"]
for s, o in out.items():
    g = o["grounding_test"]["counts"]
    L.append(f"| {s} | {o['coherence']['mean_of_2']} ({o['coherence']['n']}) | {o['metadata_test']['correct']}/{o['metadata_test']['checked']} | "
             f"{o['dev']['filter_compliance']} | {o['test']['filter_compliance']} | {g[0]}/{g[1]}/{g[2]} | {o['grounding_test']['mean_of_2']} |")
(R / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
