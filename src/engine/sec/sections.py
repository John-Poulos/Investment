"""Split stored document text into sections (M00_SEARCH Tier 2, D-SRCH-4).

Sections are character offsets into `document.text`; the text itself is never
changed. Each section's slice is indexed in FTS5 under its label and split
into passages (engine.search.passages, D-SRCH-7).

- 10-K / 10-Q / 8-K (and /A): split at "Item N" headings (line start). 10-Q
  item numbers repeat in Parts I and II, so 10-Q labels carry the part.
  Headings appear twice in 10-Ks (table of contents, then body): items are
  taken in order, and for each the occurrence after the previous item with the
  longest body wins, so short TOC entries and cross-references lose.
- A required item missing (10-K: 1, 7, 8; 10-Q: Part I Items 1, 2; 8-K: any
  item) → fallback: one "whole" section, logged in split_log with what is
  missing. Other forms split when two or more items are found.
- Exhibits and other documents: one section named for the document type,
  starting after SEC's header lines (e.g. "EX-99.1 / 2 / file.htm / EX-99.1").
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from engine.search.passages import delete_passages, fts_label, write_passages
from engine.sec.client import iso

SPLITTER_VERSION = "items-1"

_ITEM = re.compile(
    r"^[ \t]*item[ \t\xa0]+(\d{1,2}\.\d{2}|\d{1,2}[a-d]?)"  # item code: 7, 7A, 2.02
    r"(?=[\s.:\-–—)]|$)[ \t.:\-–—)]*([^\n]{0,200})$",  # short heading line, title
    re.IGNORECASE | re.MULTILINE,
)
_PART = re.compile(r"^[ \t]*part[ \t\xa0]+(iv|i{1,3})\b[^\n]{0,200}$", re.IGNORECASE | re.MULTILINE)
_SIGNATURES = re.compile(r"^[ \t]*signatures?[ \t]*$", re.IGNORECASE | re.MULTILINE)
_PART_RANK = {"I": 1, "II": 2, "III": 3, "IV": 4}

REQUIRED: dict[str, tuple[str, ...]] = {
    "10-K": ("Item 1", "Item 7", "Item 8"),
    "10-Q": ("Part I Item 1", "Part I Item 2"),
    "8-K": (),
}
SPLIT_FORMS = {"10-K": "10-K", "10-K/A": "10-K", "10-Q": "10-Q", "10-Q/A": "10-Q",
               "8-K": "8-K", "8-K/A": "8-K"}  # fmt: skip


@dataclass(frozen=True)
class Section:
    label: str
    title: str | None
    start: int
    end: int


@dataclass(frozen=True)
class Split:
    outcome: str  # split | fallback | single
    sections: tuple[Section, ...]
    missing: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _Heading:
    key: tuple[int, int, str]  # (part rank, item number, suffix) for ordering
    label: str
    title: str | None
    pos: int


def _item_key(code: str) -> tuple[int, str]:
    if "." in code:  # 8-K style 2.02
        major, minor = code.split(".")
        return int(major) * 100 + int(minor), ""
    m = re.match(r"(\d+)([a-dA-D]?)", code)
    assert m
    return int(m.group(1)) * 100, m.group(2).upper()


def _headings(text: str, form: str) -> tuple[list[_Heading], list[int]]:
    """Item headings (with labels) and every boundary position (items, parts, signatures)."""
    parts = [(m.start(), m.group(1).upper()) for m in _PART.finditer(text)]
    boundaries = [p for p, _ in parts] + [m.start() for m in _SIGNATURES.finditer(text)]
    heads = []
    for m in _ITEM.finditer(text):
        code = m.group(1).upper()
        number, suffix = _item_key(code)
        part = next((name for p, name in reversed(parts) if p < m.start()), None)
        if form == "10-Q":
            if part is None:
                continue
            label = f"Part {part} Item {code}"
            key = (_PART_RANK[part], number, suffix)
        else:
            label = f"Item {code}"
            key = (0, number, suffix)
        title = " ".join(m.group(2).replace("\t", " ").split()) or None
        heads.append(_Heading(key, label, title, m.start()))
        boundaries.append(m.start())
    return heads, sorted(set(boundaries))


def _next_boundary(boundaries: list[int], pos: int, end: int) -> int:
    return next((b for b in boundaries if b > pos), end)


def split_items(text: str, form: str) -> Split:
    """Split a 10-K/10-Q/8-K text at its item headings."""
    family = SPLIT_FORMS.get(form, form)
    heads, boundaries = _headings(text, family)
    end = len(text)

    by_label: dict[str, list[_Heading]] = {}
    for h in heads:
        by_label.setdefault(h.label, []).append(h)
    ordered = sorted(by_label.values(), key=lambda hs: hs[0].key)

    chosen: list[_Heading] = []
    last = -1
    for occurrences in ordered:
        candidates = [h for h in occurrences if h.pos > last]
        if not candidates:
            continue
        best = max(candidates, key=lambda h: _next_boundary(boundaries, h.pos, end) - h.pos)
        chosen.append(best)
        last = best.pos

    found = {h.label for h in chosen}
    required = REQUIRED.get(family)
    if required is None:
        enough = len(chosen) >= 2
        missing: tuple[str, ...] = ()
    else:
        missing = tuple(r for r in required if r not in found)
        enough = bool(chosen) and not missing
    if not enough:
        return Split("fallback", (Section("whole", None, 0, end),), missing)

    sections = []
    if chosen[0].pos > 0:
        sections.append(Section("cover", None, 0, chosen[0].pos))
    signatures = [m.start() for m in _SIGNATURES.finditer(text) if m.start() > chosen[-1].pos]
    stops = [h.pos for h in chosen[1:]] + [signatures[0] if signatures else end]
    for h, stop in zip(chosen, stops, strict=True):
        sections.append(Section(f"{family} {h.label}", h.title, h.pos, stop))
    if signatures:
        sections.append(Section("signatures", None, signatures[0], end))
    return Split("split", tuple(sections))


def strip_header(text: str, doc_type: str | None, filename: str) -> int:
    """Offset just past SEC's leading header lines (type, sequence, file name)."""
    tokens = {t.lower() for t in (doc_type, filename) if t}
    pos = 0
    for _ in range(6):
        nl = text.find("\n", pos)
        line = text[pos : nl if nl != -1 else len(text)].strip()
        if line and (line.lower() in tokens or line.isdigit()):
            pos = nl + 1 if nl != -1 else len(text)
            continue
        if not line and pos > 0:  # blank line inside the header block
            pos = nl + 1 if nl != -1 else len(text)
            continue
        break
    return pos


def split_document(text: str, doc_type: str | None, filename: str) -> Split:
    if doc_type in SPLIT_FORMS:
        return split_items(text, doc_type)
    start = strip_header(text, doc_type, filename)
    return Split("single", (Section(doc_type or "document", None, start, len(text)),))


# --- Storage -----------------------------------------------------------------


def write_sections(
    corpus: sqlite3.Connection,
    doc_id: int,
    text: str,
    doc_type: str | None,
    filename: str,
    now: datetime,
) -> Split:
    """Replace the document's sections, passages and FTS rows. Caller owns the transaction."""
    delete_passages(corpus, doc_id)
    old = [
        r[0] for r in corpus.execute("SELECT section_id FROM section WHERE doc_id = ?", (doc_id,))
    ]
    for section_id in old:
        corpus.execute("DELETE FROM section_fts WHERE rowid = ?", (section_id,))
    corpus.execute("DELETE FROM section WHERE doc_id = ?", (doc_id,))

    split = split_document(text, doc_type, filename)
    for s in split.sections:
        section_id = corpus.execute(
            "INSERT INTO section (doc_id, label, start_offset, end_offset, title, "
            "splitter_version) VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, s.label, s.start, s.end, s.title, SPLITTER_VERSION),
        ).lastrowid
        corpus.execute(
            "INSERT INTO section_fts (rowid, label, body) VALUES (?, ?, ?)",
            (section_id, fts_label(s.label, s.title, doc_type, filename), text[s.start : s.end]),
        )
    write_passages(corpus, doc_id)
    corpus.execute(
        "INSERT INTO split_log (doc_id, form, splitter_version, outcome, found, missing, at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (doc_id) DO UPDATE SET form = excluded.form, "
        "splitter_version = excluded.splitter_version, outcome = excluded.outcome, "
        "found = excluded.found, missing = excluded.missing, at = excluded.at",
        (
            doc_id,
            doc_type,
            SPLITTER_VERSION,
            split.outcome,
            json.dumps([s.label for s in split.sections]),
            json.dumps(list(split.missing)),
            iso(now),
        ),
    )
    return split


def resplit(corpus: sqlite3.Connection, doc_id: int, now: datetime) -> Split:
    """Re-run the splitter on a stored document (e.g. after a splitter change)."""
    row = corpus.execute(
        "SELECT text, doc_type, filename FROM document WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"no document {doc_id}")
    corpus.execute("BEGIN")
    try:
        split = write_sections(corpus, doc_id, row["text"], row["doc_type"], row["filename"], now)
        corpus.execute("COMMIT")
    except Exception:
        corpus.execute("ROLLBACK")
        raise
    return split


def section_text(corpus: sqlite3.Connection, section_id: int) -> str | None:
    row = corpus.execute(
        "SELECT substr(d.text, s.start_offset + 1, s.end_offset - s.start_offset) AS body "
        "FROM section s JOIN document d ON d.doc_id = s.doc_id WHERE s.section_id = ?",
        (section_id,),
    ).fetchone()
    return row["body"] if row else None
