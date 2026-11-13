# Benchmark — Python PEP corpus

File: [`questions.jsonl`](questions.jsonl) — **25 questions: 19 dev / 6 test**, frozen before any retrieval run.

- SHA-256 at freeze time: `b1d2df1d07034fde7d0df63788b8888bd376bf66e641191ef52c04dc14c8dad9`
- Frozen at: 2026-11-13T02:25:50Z (UTC). The first retrieval run happened after this time (see timestamps in `starter/results/`).
- Evidence verification (first passing run at ~02:25 UTC, before the freeze and before any retrieval; the `checked_at` field in the file shows the most recent re-check, since the script can be re-run at any time): `starter/results/benchmark_verification.json`, produced by `python scripts/verify_benchmark.py` — every `evidence_quote` (and every alternative) is checked to be a substring of the gold unit after whitespace collapsing, and every filter value is checked to exist in the corpus metadata and to contain the gold unit.

## Fields

`id, split, type, question, expected_answer, gold_source_id, gold_page, evidence_quote, filter` plus optional `alternatives` (other valid source/page/evidence; any one counts as a hit) and `filter_context` (why the filter is a legitimate pre-retrieval input).

`gold_page` = unit number inside the document (see `starter/data/manifest.json`; unit ID = `<source_id>:uNN`).

## Composition

| Type | dev | test |
|---|---:|---:|
| direct | 7 | 0 |
| paraphrase | 5 | 1 |
| condition / exception | 4 | 3 |
| metadata_filter | 3 | 2 |
| **total** | **19** | **6** |

Questions are written in English (corpus language; the embedding model is English-only).

## Split and leakage

- Split by **section**, not by document: every test question targets a section that no dev question uses. All 6 documents can appear in both splits, so there is a leakage risk at the document/style level (same authors, same vocabulary). PEP 257 has no test question.
- Filter questions use `pep_type` ∈ {`Process`, `Informational`, `Standards Track`}. Each value covers exactly **two** documents, so the filter never reveals the gold document by itself. The filter is modelled as a **user-supplied browsing context given before retrieval** (`filter_context`), never derived from the gold.
- Filter questions are deliberately ambiguous without the filter (e.g. "closing quotes of a multi-line docstring" is answered in PEP 8 *and* PEP 257; "wildcard" appears in PEP 8 imports and PEP 636 patterns). The gold is the passage inside the filter scope.

## Strategy-selection rule (pre-registered before running)

Chosen **on dev only**, in this order:
1. highest dev Evidence Hit@3;
2. tie → highest dev Hit@1;
3. tie → fewer chunks (lower storage / embedding cost).

The test split is run once, after the choice is written to `starter/results/selection.json`.
