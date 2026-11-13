"""Evaluate retrieved evidence and preserve per-query traces.

Hit definition (GUIDE.md §4.1): a retrieved chunk is a *hit* when it belongs to a
gold (source_id, page) pair AND contains the **whole** evidence quote of that
pair after whitespace collapsing. Any documented alternative gold pair counts.
Coherence / grounding are NOT inferred here: they are labelled by hand
(see results/audit/).
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def norm_match(text: str) -> str:
    """Whitespace-collapsed form used only for evidence containment checks."""
    return re.sub(r"\s+", " ", text).strip()


def gold_pairs(question: dict[str, Any]) -> list[dict[str, Any]]:
    pairs = [{"source_id": question["gold_source_id"], "page": int(question["gold_page"]),
              "evidence_quote": question["evidence_quote"]}]
    for alt in question.get("alternatives") or []:
        pairs.append({"source_id": alt["source_id"], "page": int(alt["page"]),
                      "evidence_quote": alt["evidence_quote"]})
    return pairs


def _coverage(evidence: str, text: str) -> float:
    """Fraction of evidence word tokens present in the chunk (diagnostic only)."""
    ev = re.findall(r"\w+", evidence.lower())
    tx = set(re.findall(r"\w+", text.lower()))
    return sum(1 for w in ev if w in tx) / len(ev) if ev else 0.0


def judge_hit(question: dict[str, Any], hit: dict[str, Any]) -> dict[str, Any]:
    best = {"is_hit": False, "same_page": False, "evidence_coverage": 0.0}
    text = norm_match(hit["text"])
    for g in gold_pairs(question):
        same_page = hit["document_id"] == g["source_id"] and int(hit["page"]) == g["page"]
        full = same_page and norm_match(g["evidence_quote"]) in text
        cov = _coverage(g["evidence_quote"], hit["text"]) if same_page else 0.0
        if full:
            return {"is_hit": True, "same_page": True, "evidence_coverage": 1.0}
        if same_page and cov >= best["evidence_coverage"]:
            best = {"is_hit": False, "same_page": True, "evidence_coverage": round(cov, 3)}
    return best


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    judged = []
    for rank, h in enumerate(hits, start=1):
        j = judge_hit(question, h)
        judged.append({"rank": rank, **h, **j})
    flags = [j["is_hit"] for j in judged]
    # Diagnostic only: a gold-page chunk in top-3 holds part (>=50% of words) but not all of the evidence.
    partial = (not any(flags)) and any(j["same_page"] and j["evidence_coverage"] >= 0.5 for j in judged)
    flt = question.get("filter") or None
    filter_ok = None
    if flt:
        filter_ok = all(all(str(j.get(k)) == str(v) for k, v in flt.items()) for j in judged)
    return {
        "question_id": question["id"],
        "split": question["split"],
        "type": question.get("type"),
        "question": question["question"],
        "filter": flt,
        "gold": gold_pairs(question),
        "hit_at_1": bool(flags[:1] and flags[0]),
        "hit_at_3": any(flags[:3]),
        "first_hit_rank": next((j["rank"] for j in judged if j["is_hit"]), None),
        "gold_page_in_top3": any(j["same_page"] for j in judged),
        "partial_evidence_in_top3": partial,
        "top3_filter_compliant": filter_ok,
        "hits": judged,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 / Evidence Hit@3 (n/N) by strategy and split."""
    agg: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for t in traces:
        for key in ((t["strategy"], t["split"]), (t["strategy"], "all")):
            a = agg[key]
            a["N"] += 1
            a["hit1"] += int(t["hit_at_1"])
            a["hit3"] += int(t["hit_at_3"])
            a["gold_page_top3"] += int(t["gold_page_in_top3"])
            a["partial"] += int(t["partial_evidence_in_top3"])
            a["unsplit"] += int(t.get("evidence_in_single_chunk_of_index", True))
            if t["top3_filter_compliant"] is not None:
                a["filter_N"] += 1
                a["filter_ok"] += int(t["top3_filter_compliant"])
    out = {}
    for (s, sp), a in sorted(agg.items()):
        out.setdefault(s, {})[sp] = {
            "hit_at_1": f"{a['hit1']}/{a['N']}",
            "evidence_hit_at_3": f"{a['hit3']}/{a['N']}",
            "hit_at_1_pct": round(100 * a["hit1"] / a["N"], 1),
            "evidence_hit_at_3_pct": round(100 * a["hit3"] / a["N"], 1),
            "gold_page_in_top3": f"{a['gold_page_top3']}/{a['N']}",
            "partial_evidence_in_top3": a["partial"],
            "questions_whose_evidence_fits_one_chunk": f"{a['unsplit']}/{a['N']}",
            "filter_compliance": f"{a['filter_ok']}/{a['filter_N']}" if a["filter_N"] else "N/A",
        }
    return out
