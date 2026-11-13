"""Read and normalize source data (Python PEPs in reStructuredText).

Corpus: 6 PEP files from github.com/python/peps (public domain / CC0).
RST has no physical pages, so per GUIDE.md each document is split, in order,
into *source units* of >= 1,500 normalized characters at paragraph boundaries.
A unit plays the role of a "page": ``DocumentPage.page`` is the 1-based unit
number inside the document and ``metadata['unit_id']`` is e.g. ``pep-0008:u05``.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import DocumentPage

MIN_UNIT_CHARS = 1500
# Sections whose body is only references / licence boilerplate: excluded from
# the content count (GUIDE.md: drop cover, ToC, blank and reference-only pages).
EXCLUDED_SECTIONS = {"copyright", "references", "footnotes"}
HEADER_FIELDS = ("PEP", "Title", "Author", "Status", "Type", "Created", "Python-Version", "Topic")
UNDERLINE_CHARS = set("=-~^'`\"*+#:.")


@dataclass
class ParsedDocument:
    document_id: str
    source: str
    header: dict[str, str]
    text: str                                 # full normalized body text
    blocks: list[tuple[int, int]]             # (start, end) offsets of paragraphs in text
    headings: list[tuple[int, int, str]]      # (offset, level, title)
    excluded_sections: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)


# --------------------------------------------------------------------- normalize
def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace without discarding paragraph structure."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace("​", "").replace("﻿", "")
    text = text.expandtabs(4)
    lines = [ln.rstrip() for ln in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_ROLE_RE = re.compile(r":(?:pep|rfc|ref|term|func|class|mod|meth|data|attr|exc|const|doc|file|samp|abbr|envvar|option|kbd|py:\w+):`([^`]*)`")


def _clean_inline(line: str) -> str:
    """Strip RST inline markup that would add noise but keep the words."""
    def role(m: re.Match) -> str:
        inner = m.group(1)
        inner = re.sub(r"\s*<[^>]*>$", "", inner)       # `text <target>` -> text
        if m.group(0).startswith(":pep:") and inner.strip().isdigit():
            return f"PEP {inner.strip()}"
        return inner.lstrip("~!")
    line = _ROLE_RE.sub(role, line)
    line = re.sub(r"`([^`<]+?)\s*<[^>]+>`__?", r"\1", line)   # `text <url>`_
    line = re.sub(r"`([^`]+)`_\b", r"\1", line)               # `text`_
    line = re.sub(r"\s?\[(\d+|#[\w-]*)\]_", "", line)              # footnote refs [1]_
    line = line.replace("``", "`")
    return line


def _clean_inline_multiline(text: str) -> str:
    """Roles split across lines, e.g. :pep:`style guidelines ...\n<7>`."""
    def role(m: re.Match) -> str:
        inner = re.sub(r"\s+", " ", m.group(2))
        tgt = m.group(3)
        if m.group(1) == "pep" and tgt and tgt.isdigit():
            return f"{inner} (PEP {tgt})"
        return inner
    return re.sub(r":(pep|ref|term):`([^`<]+?)\s*<([^>]*)>`", role, text, flags=re.S)


def _is_underline(line: str, title: str) -> bool:
    s = line.strip()
    return (len(s) >= 3 and len(set(s)) == 1 and s[0] in UNDERLINE_CHARS
            and line == s and len(s) >= len(title.strip()) - 1 and title.strip() != "")


def parse_pep(path: Path, document_id: str, source: str) -> ParsedDocument:
    raw = path.read_text(encoding="utf-8")
    raw = normalize_text(raw)
    lines = raw.split("\n")

    # 1. RFC-822 style header until first blank line.
    header: dict[str, str] = {}
    i, last_key = 0, None
    while i < len(lines) and lines[i].strip():
        m = re.match(r"^([A-Za-z-]+):\s*(.*)$", lines[i])
        if m:
            last_key = m.group(1)
            header[last_key] = m.group(2).strip()
        elif last_key:  # continuation line (e.g. multiple authors)
            header[last_key] += " " + lines[i].strip()
        i += 1
    body = lines[i:]

    # 2. Walk body lines, convert headings, drop pure markup, skip excluded sections.
    out: list[str] = []
    headings_raw: list[tuple[int, int, str]] = []   # (line index in out, level, title)
    level_chars: list[str] = []
    excluded: list[str] = []
    log: list[str] = []
    skipping = False
    skip_level = 0
    j = 0
    while j < len(body):
        line = body[j]
        nxt = body[j + 1] if j + 1 < len(body) else ""
        if line.strip() and not line.startswith(" ") and _is_underline(nxt, line):
            ch = nxt.strip()[0]
            if ch not in level_chars:
                level_chars.append(ch)
            level = level_chars.index(ch) + 1
            title = _clean_inline(line.strip())
            if skipping and level <= skip_level:
                skipping = False
            if title.lower() in EXCLUDED_SECTIONS:
                skipping, skip_level = True, level
                excluded.append(title)
            if not skipping:
                headings_raw.append((len(out), level, title))
                out.append("#" * level + " " + title)
            j += 2
            continue
        if skipping:
            j += 1
            continue
        s = line.strip()
        # explicit markup that carries no content
        if re.match(r"^\.\. _[^:]*:.*$", s) or s.startswith(".. contents::") or s.startswith(".. image::") \
                or re.match(r"^:(class|local|depth|alt|width|height|align|target|caption):", s):
            j += 1
            continue
        if re.match(r"^\.\.\s*$", s) and j + 1 < len(body) and "Local Variables" in "".join(body[j:j + 3]):
            log.append("dropped trailing editor comment block")
            break
        if s.startswith(".. code-block::") or s.startswith(".. code::"):
            j += 1
            continue
        if s.startswith(".. rubric::"):
            line = s.replace(".. rubric::", "").strip()
        if s.startswith(".. [") :  # footnote definition outside References
            line = re.sub(r"^\.\. \[[^\]]*\]\s*", "", s)
        if s.startswith(".. note::") or s.startswith(".. warning::") or s.startswith(".. seealso::"):
            line = s.split("::", 1)[0].replace("..", "").strip().capitalize() + ":" + s.split("::", 1)[1]
        if line.rstrip().endswith("::") and not line.strip() == "::":
            line = line.rstrip()[:-1]           # "Example::" -> "Example:"
        elif line.strip() == "::":
            j += 1
            continue
        out.append(_clean_inline(line))
        j += 1

    text = "\n".join(out)
    # multi-line hyperlinks `text\n<url>`_ -> text (second pass on joined text)
    text = re.sub(r"`([^`<]+?)\s*<[^>]+>`__?", lambda m: re.sub(r"\s+", " ", m.group(1)), text, flags=re.S)
    text = re.sub(r"\{(NNNN)\}", r"\1", text)
    text = _clean_inline_multiline(text)
    text = normalize_text(text)
    # 3. Paragraph blocks and heading offsets in the normalized text.
    blocks: list[tuple[int, int]] = []
    for m in re.finditer(r"[^\n](?:[^\n]|\n(?!\n))*", text):
        blocks.append((m.start(), m.end()))
    headings: list[tuple[int, int, str]] = []
    for m in re.finditer(r"^(#+) (.+)$", text, flags=re.M):
        headings.append((m.start(), len(m.group(1)), m.group(2)))
    if excluded:
        log.append(f"excluded sections: {excluded}")
    return ParsedDocument(document_id, source, header, text, blocks, headings, excluded, log)


def section_at(doc: ParsedDocument, offset: int) -> str:
    """Heading path (e.g. 'Code Lay-out > Indentation') in effect at offset."""
    stack: list[tuple[int, str]] = []
    for off, level, title in doc.headings:
        if off > offset:
            break
        stack = [s for s in stack if s[0] < level] + [(level, title)]
    return " > ".join(t for _, t in stack) if stack else "(preamble)"


def doc_metadata(doc: ParsedDocument) -> dict[str, Any]:
    h = doc.header
    created = h.get("Created", "")
    year = int(created[-4:]) if re.search(r"\d{4}$", created) else None
    return {
        "pep_number": int(h["PEP"]),
        "title": h.get("Title"),
        "pep_type": h.get("Type"),               # Process / Informational / Standards Track
        "status": h.get("Status"),               # Active / Final
        "python_version": h.get("Python-Version"),  # None when header absent (not guessed)
        "created_year": year,
    }


def split_units(doc: ParsedDocument, min_chars: int = MIN_UNIT_CHARS) -> list[DocumentPage]:
    """Sequentially group paragraph blocks into units of >= min_chars characters.

    A remainder shorter than min_chars is merged into the previous unit so every
    unit satisfies the GUIDE.md minimum. Offsets refer to ``doc.text``.
    """
    groups: list[list[tuple[int, int]]] = []
    cur: list[tuple[int, int]] = []
    for blk in doc.blocks:
        cur.append(blk)
        if cur[-1][1] - cur[0][0] >= min_chars:
            groups.append(cur)
            cur = []
    if cur:
        if groups:
            groups[-1].extend(cur)
        else:
            groups.append(cur)
    meta = doc_metadata(doc)
    pages: list[DocumentPage] = []
    for n, g in enumerate(groups, start=1):
        start, end = g[0][0], g[-1][1]
        text = doc.text[start:end]
        pages.append(DocumentPage(
            document_id=doc.document_id,
            source=doc.source,
            page=n,
            text=text,
            metadata={
                **meta,
                "unit_id": f"{doc.document_id}:u{n:02d}",
                "char_start": start,
                "char_end": end,
                "n_chars": len(text),
                "section": section_at(doc, start),
                "sha1": hashlib.sha1(text.encode()).hexdigest()[:12],
            },
        ))
    return pages


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Not used for this corpus (RST). Kept for the starter contract."""
    from pypdf import PdfReader
    pages = []
    for i, p in enumerate(PdfReader(str(path)).pages, start=1):
        txt = normalize_text(p.extract_text() or "")
        pages.append(DocumentPage(document_id, source, i, txt, {"empty": not txt}))
    return pages
