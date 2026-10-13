"""Stored filing text for M04's finders (Part 3: walk labels, 8-K classes, rating sentences).

Reads corpus documents and passages only (0 requests). Quotes are cut from the stored
text by offsets, so every finding can be re-verified against the document (D21).
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class Doc:
    doc_id: int
    accession: str
    filename: str
    doc_type: str | None
    text: str

    @property
    def ref(self) -> str:
        return f"{self.accession}/{self.filename}"


def docs_for(corpus: sqlite3.Connection, accession: str) -> list[Doc]:
    return [
        Doc(r["doc_id"], r["accession"], r["filename"], r["doc_type"], r["text"])
        for r in corpus.execute(
            "SELECT doc_id, accession, filename, doc_type, text FROM document WHERE accession = ? "
            "ORDER BY doc_id",
            (accession,),
        )
    ]


def passages_for(corpus: sqlite3.Connection, doc_id: int) -> list[tuple[int, int, int]]:
    """(passage_id, start, end) in document order; one whole-document span when the
    document has no passages."""
    rows = [
        (r[0], r[1], r[2])
        for r in corpus.execute(
            "SELECT passage_id, start_offset, end_offset FROM passage WHERE doc_id = ? "
            "ORDER BY start_offset",
            (doc_id,),
        )
    ]
    return rows


_SENT_END = re.compile(r"(?<=[.!?;])[\"')\]”’]*\s+(?=[A-Z(“\"$])|\n{2,}")


def sentences(text: str, start: int = 0, end: int | None = None) -> Iterator[tuple[int, int]]:
    """Sentence spans inside [start, end) (stops at . ! ? ; before a capital, or a blank line)."""
    end = len(text) if end is None else end
    pos = start
    for m in _SENT_END.finditer(text, start, end):
        if m.start() > pos:
            yield pos, m.start()
        pos = m.end()
    if end > pos:
        yield pos, end


def sentence_at(text: str, offset: int, limit: int = 600) -> tuple[int, int]:
    """The sentence around `offset` (bounded to `limit` characters each side)."""
    lo = max(0, offset - limit)
    hi = min(len(text), offset + limit)
    best = (lo, hi)
    for s, e in sentences(text, lo, hi):
        if s <= offset < e:
            return s, e
        best = (s, e) if s <= offset else best
    return best


def quote_at(text: str, offset: int, min_chars: int = 40) -> str:
    """The sentence around `offset`; a heading-length sentence ("DISCONTINUED OPERATIONS.")
    is extended by the sentence after it."""
    a, b = sentence_at(text, offset)
    if b - a < min_chars or text[a:b].isupper():
        nxt = next(iter(sentences(text, b, min(len(text), b + 800))), None)
        if nxt is not None:
            b = nxt[1]
    return clean(text[a:b])


def clean(text: str) -> str:
    return " ".join(text.split())


def doc_scale(text: str) -> float:
    """The document's stated table scale: millions, thousands, or units."""
    head = text[:200_000].lower()
    if "in millions" in head:
        return 1e6
    if "in thousands" in head:
        return 1e3
    return 1.0


_NUM = re.compile(
    r"(?<![\w.])\(?\$?\s?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\)?\s*(million|billion|thousand|[mbk]\b)?",
    re.IGNORECASE,
)
_CODE_BEFORE = re.compile(r"(?:\bASC|\bASU|\bTopic|\bNo\.|\bNote|\bItem|\bSection|\d-)\s*$", re.I)
_SCALE_WORD = {"million": 1e6, "m": 1e6, "billion": 1e9, "b": 1e9, "thousand": 1e3, "k": 1e3}


@dataclass(frozen=True)
class Number:
    value: float  # scaled to dollars
    start: int
    end: int
    raw: str


def numbers(text: str, start: int, end: int, default_scale: float) -> list[Number]:
    """Amounts in [start, end): a scale word wins; otherwise the document's scale. Years,
    percentages and note numbers are skipped."""
    out = []
    for m in _NUM.finditer(text, start, end):
        whole, frac, word = m.group(1), m.group(2) or "", m.group(3)
        if _CODE_BEFORE.search(text[max(0, m.start() - 12) : m.start()]):
            continue  # ASC 606, ASU 2016-15, Topic 842, Note 7, Item 4.02
        after = text[m.end() : m.end() + 2]
        if after.startswith("%") or text[m.end() : m.end() + 8].lower().startswith(" percent"):
            continue
        digits = whole.replace(",", "")
        v = float(digits + frac)
        if not word and not frac and "," not in whole and len(digits) == 4 and 1900 <= v <= 2100:
            continue  # a year
        if not word and v < 10 and not frac:
            continue  # note and item numbers
        scale = _SCALE_WORD.get(word.lower(), default_scale) if word else default_scale
        out.append(Number(v * scale, m.start(), m.end(), m.group(0).strip()))
    return out
