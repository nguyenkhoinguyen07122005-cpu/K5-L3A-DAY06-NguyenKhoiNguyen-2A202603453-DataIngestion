"""Fixed-size (strategy A) and structure-aware (strategies B/C) chunking.

Both chunkers work inside one source unit ("page") so every chunk keeps a single
(document_id, page) for traceability. ``metadata['char_start']`` /
``metadata['char_end']`` are offsets in the *document* normalized text, so a
chunk can always be located exactly in the source.
"""
from __future__ import annotations

import hashlib
import re

from .models import Chunk, DocumentPage


def _make_chunk(page: DocumentPage, kind: str, n: int, start: int, end: int) -> Chunk:
    text = page.text[start:end]
    base = page.metadata["char_start"]
    meta = {k: v for k, v in page.metadata.items() if k not in {"char_start", "char_end", "n_chars", "sha1", "section"}}
    meta.update({
        "chunker": kind,
        "char_start": base + start,
        "char_end": base + end,
        "n_chars": len(text),
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
    })
    return Chunk(
        chunk_id=f"{page.metadata['unit_id']}:{kind}:c{n:02d}",
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text,
        metadata=meta,
    )


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Character windows of ``size`` with ``overlap``; no regard for structure."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("require size > 0 and 0 <= overlap < size")
    step = size - overlap
    chunks: list[Chunk] = []
    start, n = 0, 0
    L = len(page.text)
    while start < L:
        end = min(start + size, L)
        # skip a tail that is entirely inside the previous window's overlap
        if chunks and end - start <= overlap:
            break
        chunks.append(_make_chunk(page, f"fixed{size}o{overlap}", n, start, end))
        n += 1
        if end == L:
            break
        start += step
    return chunks


def _blocks(text: str) -> list[tuple[int, int]]:
    """Paragraph spans (separated by blank lines)."""
    return [(m.start(), m.end()) for m in re.finditer(r"[^\n](?:[^\n]|\n(?!\n))*", text)]


def _split_oversized(text: str, s: int, e: int, max_size: int) -> list[tuple[int, int]]:
    """Split one paragraph larger than max_size at line boundaries (hard cut if a line is huge)."""
    spans, cur_s = [], s
    line_starts = [s] + [s + m.end() for m in re.finditer(r"\n", text[s:e])]
    cur_e = s
    for ls in line_starts[1:] + [e]:
        if ls - cur_s > max_size and cur_e > cur_s:
            spans.append((cur_s, cur_e))
            cur_s = cur_e
        cur_e = ls
    spans.append((cur_s, e))
    out = []
    for a, b in spans:          # hard split very long single lines
        while b - a > max_size:
            out.append((a, a + max_size))
            a += max_size
        out.append((a, b))
    return [(a, b) for a, b in out if text[a:b].strip()]


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Group paragraphs up to ``max_size`` chars; a heading always opens a new chunk.

    - headings ("# ...") start a new chunk and stay attached to the text after them;
    - consecutive paragraphs are merged while the chunk stays <= max_size
      (soft limit: a heading line may push a chunk slightly over it);
    - a paragraph > max_size is split at line boundaries;
    - a chunk that is only a heading at the end of a unit is merged backwards.
    """
    text = page.text
    groups: list[list[tuple[int, int]]] = []
    cur: list[tuple[int, int]] = []
    for s, e in _blocks(text):
        is_heading = text[s] == "#" and re.match(r"#+ ", text[s:e]) is not None
        pieces = [(s, e)] if e - s <= max_size else _split_oversized(text, s, e, max_size)
        for i, (ps, pe) in enumerate(pieces):
            start_new = is_heading and i == 0
            cur_only_heading = bool(cur) and all(re.match(r"#+ ", text[a:b]) for a, b in cur)
            if cur and not cur_only_heading and (start_new or (pe - cur[0][0]) > max_size):
                groups.append(cur)
                cur = []
            cur.append((ps, pe))
    if cur:
        if groups and all(re.match(r"#+ ", text[a:b]) for a, b in cur):
            groups[-1].extend(cur)
        else:
            groups.append(cur)
    return [_make_chunk(page, f"para{max_size}", n, g[0][0], g[-1][1]) for n, g in enumerate(groups)]
