"""Load the corpus config, build source units and the data manifest."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ingestion import ParsedDocument, parse_pep, split_units
from .models import DocumentPage

STARTER = Path(__file__).resolve().parents[1]
DATA = STARTER / "data"
RAW_URL = "https://raw.githubusercontent.com/python/peps/{commit}/peps/{name}"


def load_corpus(config_path: Path = DATA / "corpus.json") -> tuple[dict, list[ParsedDocument], list[DocumentPage]]:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    docs, pages = [], []
    for d in cfg["documents"]:
        path = DATA / d["file"]
        if not path.exists():
            raise FileNotFoundError(f"{path} missing - run `python scripts/fetch_corpus.py` first")
        doc = parse_pep(path, d["source_id"], f"python/peps@{cfg['snapshot']['commit'][:12]}:peps/{path.name}")
        docs.append(doc)
        pages.extend(split_units(doc))
    return cfg, docs, pages


def license_line(raw_text: str) -> str:
    lines = raw_text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip() == "Copyright" and i + 1 < len(lines) and set(lines[i + 1].strip()) == {"="}:
            body = []
            for nxt in lines[i + 2:]:
                if body and not nxt.strip():
                    break
                if nxt.strip():
                    body.append(nxt.strip())
            return " ".join(body)
    return "NOT FOUND"


def build_manifest(cfg: dict, docs: list[ParsedDocument], pages: list[DocumentPage]) -> dict[str, Any]:
    snap = cfg["snapshot"]
    sources = []
    for d, doc in zip(cfg["documents"], docs):
        raw_path = DATA / d["file"]
        raw = raw_path.read_text(encoding="utf-8")
        units = [p for p in pages if p.document_id == doc.document_id]
        sources.append({
            "source_id": doc.document_id,
            "title": doc.header.get("Title"),
            "pep_type": doc.header.get("Type"),
            "status": doc.header.get("Status"),
            "python_version": doc.header.get("Python-Version"),
            "created": doc.header.get("Created"),
            "source_path_or_url": RAW_URL.format(commit=snap["commit"], name=raw_path.name),
            "local_path": f"starter/data/{d['file']}",
            "license_or_permission": license_line(raw),
            "accessed_at": snap["accessed_at"],
            "snapshot": f"{snap['repository']} @ {snap['commit']} ({snap['commit_date']})",
            "raw_chars": len(raw),
            "normalized_chars": len(doc.text),
            "excluded_sections": doc.excluded_sections,
            "physical_pages": "N/A (reStructuredText, no pagination)",
            "units": [{"unit_id": u.metadata["unit_id"], "page": u.page,
                       "char_start": u.metadata["char_start"], "char_end": u.metadata["char_end"],
                       "n_chars": u.metadata["n_chars"], "section_at_start": u.metadata["section"]}
                      for u in units],
            "n_units": len(units),
            "processing_log": doc.log,
        })
    return {
        "counting_rule": ("RST has no pages. Each PEP body (header preamble removed; sections "
                          "'Copyright', 'References', 'Footnotes' removed as reference/licence-only) is "
                          "normalized, split into paragraphs, and paragraphs are grouped IN ORDER into units; "
                          "a unit is closed as soon as it reaches >= 1500 normalized characters; a short "
                          "remainder is merged into the previous unit. No duplication. Unit = 'page' "
                          "(DocumentPage.page = unit number within the document)."),
        "min_unit_chars": 1500,
        "total_units": len(pages),
        "total_normalized_chars": sum(len(p.text) for p in pages),
        "min_unit_len": min(len(p.text) for p in pages),
        "sources": sources,
    }
