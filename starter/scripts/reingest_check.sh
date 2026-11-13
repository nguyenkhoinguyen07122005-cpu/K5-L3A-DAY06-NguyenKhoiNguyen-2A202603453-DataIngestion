#!/usr/bin/env bash
# Re-ingestion check (run from starter/ after `python -m src.run ingest`).
# 1) same version again  -> expect 0 new embeddings, 0 deletes, same row counts
# 2) simulate a changed document (drop the "Handling Docstring Indentation" section of PEP 257)
#    -> expect only PEP 257 chunks updated/deleted
# 3) restore the original -> expect counts back to step 1
set -euo pipefail
PY=${PY:-python}
F=data/raw/pep-0257.rst
cp "$F" /tmp/pep-0257.orig.rst
trap 'cp /tmp/pep-0257.orig.rst "$F"' EXIT
$PY -m src.run ingest --report ingest_rerun_same.json
$PY - "$F" <<'PY'
import sys, re
p = sys.argv[1]; s = open(p, encoding="utf-8").read()
start = s.index("Handling Docstring Indentation\n")
end = s.index("References and Footnotes\n")
open(p, "w", encoding="utf-8").write(s[:start] + s[end:])
PY
$PY -m src.run ingest --report ingest_rerun_changed.json
cp /tmp/pep-0257.orig.rst "$F"
$PY -m src.run ingest --report ingest_rerun_restored.json
$PY - <<'PY'
import json
rows = []
for name in ["ingest_stats", "ingest_rerun_same", "ingest_rerun_changed", "ingest_rerun_restored"]:
    r = json.load(open(f"../results/{name}.json"))["strategies"]
    rows.append({"run": name, **{s: {"chunks": r[s]["chunk_count"], "new_embeds": r[s]["newly_embedded_texts"],
                                     **r[s]["upsert"], "rows": r[s]["rows_in_store_after"]} for s in r}})
json.dump(rows, open("../results/reingest_check.json", "w"), indent=2)
for x in rows: print(json.dumps(x))
PY
