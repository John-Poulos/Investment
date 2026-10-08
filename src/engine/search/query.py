"""Tier 2 search over passages (M00_SEARCH, D-SRCH-7).

`search()` takes an FTS5 query (phrases, prefix*, AND/OR/NOT, NEAR, column
filters such as `label:"Item 1A"`) and returns ranked passages with their
document, section, offsets and a highlighted snippet. Ranking is BM25 with the
label column (section label + title) weighted above the body, so "risk factors"
prefers passages inside Item 1A. Passages have similar lengths, which removes
the short-section bias seen when whole sections were ranked.

Free text with punctuation (e.g. 10b5-1, HBM3E, "$1.2 billion") must be quoted:
use `phrase()`. The tokenizer splits "10b5-1" into 10b5 + 1; inside a phrase
those tokens must be adjacent, so the phrase still matches exactly.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

LABEL_WEIGHT = 10.0  # calibrated on the live corpus check (scripts/search_check.py)
BODY_WEIGHT = 1.0
SNIPPET_TOKENS = 32


@dataclass(frozen=True)
class Hit:
    passage_id: int
    doc_id: int
    accession: str
    cik: str
    filename: str
    doc_type: str | None
    url: str
    section: str
    section_title: str | None
    start: int
    end: int
    score: float  # bm25: lower is better
    snippet: str


@dataclass(frozen=True)
class Passage:
    """A passage with everything needed to cite and re-verify it after a rebuild."""

    passage_id: int
    doc_id: int
    accession: str
    cik: str
    filename: str
    doc_type: str | None
    url: str
    section: str
    section_title: str | None
    start: int
    end: int
    text: str
    doc_sha256: str
    parser_version: str | None


class QueryError(ValueError):
    """The FTS5 query could not be parsed."""


def phrase(text: str) -> str:
    """Quote free text as one FTS5 phrase."""
    return '"' + text.replace('"', '""') + '"'


def _in(column: str, values: Sequence[str]) -> tuple[str, list[str]]:
    return f"{column} IN ({', '.join('?' * len(values))})", list(values)


def search(
    corpus: sqlite3.Connection,
    query: str,
    *,
    ciks: Sequence[str] | None = None,
    doc_types: Sequence[str] | None = None,
    sections: Sequence[str] | None = None,
    accessions: Sequence[str] | None = None,
    limit: int = 20,
) -> list[Hit]:
    """Ranked passages matching `query`, optionally filtered.

    sections: exact section labels, e.g. "10-K Item 1A", "8-K Item 2.02", "EX-99.1".
    """
    where = ["passage_fts MATCH ?"]
    params: list[object] = [query]
    for column, values in (
        ("d.cik", ciks),
        ("d.doc_type", doc_types),
        ("s.label", sections),
        ("d.accession", accessions),
    ):
        if values is not None:
            if not values:
                return []
            clause, vals = _in(column, values)
            where.append(clause)
            params.extend(vals)
    sql = (
        "SELECT p.passage_id, p.doc_id, d.accession, d.cik, d.filename, d.doc_type, d.url, "
        "s.label AS section, s.title AS section_title, p.start_offset, p.end_offset, "
        f"bm25(passage_fts, {LABEL_WEIGHT}, {BODY_WEIGHT}) AS score, "
        f"snippet(passage_fts, 1, '[', ']', '…', {SNIPPET_TOKENS}) AS snippet "
        "FROM passage_fts JOIN passage p ON p.passage_id = passage_fts.rowid "
        "JOIN section s ON s.section_id = p.section_id "
        "JOIN document d ON d.doc_id = p.doc_id "
        f"WHERE {' AND '.join(where)} ORDER BY score LIMIT ?"
    )
    params.append(limit)
    try:
        rows = corpus.execute(sql, params).fetchall()
    except sqlite3.OperationalError as e:
        if "fts5" in str(e) or "syntax" in str(e) or "no such column" in str(e):
            raise QueryError(f"{query!r}: {e}") from e
        raise
    return [
        Hit(
            r["passage_id"],
            r["doc_id"],
            r["accession"],
            r["cik"],
            r["filename"],
            r["doc_type"],
            r["url"],
            r["section"],
            r["section_title"],
            r["start_offset"],
            r["end_offset"],
            r["score"],
            r["snippet"],
        )
        for r in rows
    ]


def get_passage(corpus: sqlite3.Connection, passage_id: int) -> Passage | None:
    r = corpus.execute(
        "SELECT p.passage_id, p.doc_id, d.accession, d.cik, d.filename, d.doc_type, d.url, "
        "s.label AS section, s.title AS section_title, p.start_offset, p.end_offset, "
        "substr(d.text, p.start_offset + 1, p.end_offset - p.start_offset) AS text, "
        "d.sha256, d.parser_version "
        "FROM passage p JOIN section s ON s.section_id = p.section_id "
        "JOIN document d ON d.doc_id = p.doc_id WHERE p.passage_id = ?",
        (passage_id,),
    ).fetchone()
    if r is None:
        return None
    return Passage(
        r["passage_id"],
        r["doc_id"],
        r["accession"],
        r["cik"],
        r["filename"],
        r["doc_type"],
        r["url"],
        r["section"],
        r["section_title"],
        r["start_offset"],
        r["end_offset"],
        r["text"],
        r["sha256"],
        r["parser_version"],
    )
