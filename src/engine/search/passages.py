"""Split sections into paragraph-aligned passages (M00_SEARCH Tier 2, D-SRCH-7).

Passages are character offsets into `document.text`; together they tile each
section exactly, so nothing is dropped (D22). Stored text has one paragraph
per line (`html_to_text`), so lines are packed greedily up to MAX_CHARS. A
single line longer than MAX_CHARS (long paragraph, flattened table) is cut at
the last sentence end before the limit, else at the last whitespace, else hard.
Blank-only stretches are folded into the passage before them.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator

CHUNKER_VERSION = "para-1"
MAX_CHARS = 3000
MIN_CUT = 1500  # long-line cuts never land before this many chars

_SENTENCE_END = re.compile(r"[.!?;][\"')\]”’]*\s+")


def _lines(text: str, start: int, end: int) -> Iterator[tuple[int, int]]:
    """(start, end) of each line in text[start:end], newline included."""
    pos = start
    while pos < end:
        nl = text.find("\n", pos, end)
        stop = end if nl == -1 else nl + 1
        yield pos, stop
        pos = stop


def _cut(text: str, start: int, end: int) -> int:
    """Where to end a passage that starts at `start` inside one over-long line."""
    limit = start + MAX_CHARS
    window = text[start + MIN_CUT : limit]
    ends = [m.end() for m in _SENTENCE_END.finditer(window)]
    if ends:
        return start + MIN_CUT + ends[-1]
    space = window.rfind(" ")
    if space != -1:
        return start + MIN_CUT + space + 1
    return limit


def chunk(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Passages (start, end) tiling text[start:end]."""
    pieces: list[tuple[int, int]] = []  # lines, with over-long lines cut
    for a, b in _lines(text, start, end):
        while b - a > MAX_CHARS:
            c = _cut(text, a, b)
            pieces.append((a, c))
            a = c
        pieces.append((a, b))

    out: list[tuple[int, int]] = []
    cur_start = cur_end = None
    for a, b in pieces:
        blank = not text[a:b].strip()
        if cur_start is None:
            cur_start, cur_end = a, b
        elif blank or b - cur_start <= MAX_CHARS:
            cur_end = b
        else:
            out.append((cur_start, cur_end))
            cur_start, cur_end = a, b
    if cur_start is not None:
        assert cur_end is not None
        if out and not text[cur_start:cur_end].strip():
            out[-1] = (out[-1][0], cur_end)  # trailing blank lines join the last passage
        else:
            out.append((cur_start, cur_end))
    return out


def fts_label(label: str, title: str | None, doc_type: str | None, filename: str) -> str:
    """Searchable label column: section label + title (e.g. '10-K Item 1A Risk Factors')."""
    if label == "whole":
        return f"{doc_type or filename} whole"
    return f"{label} {title}" if title else label


# --- Storage -----------------------------------------------------------------


def delete_passages(corpus: sqlite3.Connection, doc_id: int) -> None:
    """Remove a document's passages and their FTS rows. Caller owns the transaction."""
    corpus.execute(
        "DELETE FROM passage_fts WHERE rowid IN (SELECT passage_id FROM passage WHERE doc_id = ?)",
        (doc_id,),
    )
    corpus.execute("DELETE FROM passage WHERE doc_id = ?", (doc_id,))


def write_passages(corpus: sqlite3.Connection, doc_id: int) -> int:
    """(Re)build passages for every section of a document. Caller owns the transaction.

    Returns the number of passages written.
    """
    delete_passages(corpus, doc_id)
    doc = corpus.execute(
        "SELECT text, doc_type, filename FROM document WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    if doc is None:
        raise KeyError(f"no document {doc_id}")
    text = doc["text"]
    count = 0
    sections = corpus.execute(
        "SELECT section_id, label, title, start_offset, end_offset FROM section "
        "WHERE doc_id = ? ORDER BY start_offset",
        (doc_id,),
    ).fetchall()
    for s in sections:
        label = fts_label(s["label"], s["title"], doc["doc_type"], doc["filename"])
        for seq, (a, b) in enumerate(chunk(text, s["start_offset"], s["end_offset"])):
            passage_id = corpus.execute(
                "INSERT INTO passage (section_id, doc_id, seq, start_offset, end_offset, "
                "chunker_version) VALUES (?, ?, ?, ?, ?, ?)",
                (s["section_id"], doc_id, seq, a, b, CHUNKER_VERSION),
            ).lastrowid
            corpus.execute(
                "INSERT INTO passage_fts (rowid, label, body) VALUES (?, ?, ?)",
                (passage_id, label, text[a:b]),
            )
            count += 1
    return count


def ensure_passages(corpus: sqlite3.Connection) -> dict[str, int]:
    """Build passages for documents that have none or an older chunker version.

    One transaction per document. Returns counts {documents, passages}.
    """
    stale = [
        r[0]
        for r in corpus.execute(
            "SELECT d.doc_id FROM document d WHERE EXISTS "
            "(SELECT 1 FROM section s WHERE s.doc_id = d.doc_id) AND NOT EXISTS "
            "(SELECT 1 FROM passage p WHERE p.doc_id = d.doc_id AND p.chunker_version = ?) "
            "ORDER BY d.doc_id",
            (CHUNKER_VERSION,),
        )
    ]
    passages = 0
    for doc_id in stale:
        corpus.execute("BEGIN")
        try:
            passages += write_passages(corpus, doc_id)
            corpus.execute("COMMIT")
        except Exception:
            corpus.execute("ROLLBACK")
            raise
    return {"documents": len(stale), "passages": passages}
