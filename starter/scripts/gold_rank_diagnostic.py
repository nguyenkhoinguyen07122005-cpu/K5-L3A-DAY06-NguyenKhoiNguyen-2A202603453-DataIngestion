"""Diagnostic (not a benchmark metric): rank of the first evidence-hit chunk in the top-50
for every question/strategy. Helps explain misses. Usage: python scripts/gold_rank_diagnostic.py"""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from src.embeddings import MyEmbedder
from src.store import PgVectorStore
from src.evaluation import judge_hit
from src.run import STRATEGIES, load_questions, ROOT
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
emb = MyEmbedder(os.getenv("EMBEDDING_MODEL") or None)
store = PgVectorStore(os.environ["DATABASE_URL"], emb.dimensions)
rows = []
for q in load_questions():
    v = emb.embed_query(q["question"])
    for s, cfg in STRATEGIES.items():
        hits = store.search(s, v, 50, q.get("filter") if cfg["use_filter"] else None)
        r = next((i + 1 for i, h in enumerate(hits) if judge_hit(q, h)["is_hit"]), None)
        rows.append({"question_id": q["id"], "split": q["split"], "strategy": s, "first_hit_rank_top50": r})
(ROOT / "results" / "diagnostic_gold_rank.json").write_text(json.dumps(rows, indent=1))
for q in sorted({r["question_id"] for r in rows}):
    print(q, {r["strategy"]: r["first_hit_rank_top50"] for r in rows if r["question_id"] == q})
