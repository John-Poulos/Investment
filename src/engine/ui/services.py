"""Read functions behind the UI pages (M00_UI rule U4).

Plain functions over the two SQLite connections, returning plain data. Pages
and templates never run SQL; the same functions can serve scripts or an API.
Missing data stays missing (None), never zero.
"""

from __future__ import annotations

import sqlite3
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.search.query import QueryError, phrase, search
from engine.sec.xbrl_facts import CONCEPTS

SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"


def filing_index_url(cik: str, accession: str) -> str:
    return f"{SEC_ARCHIVES}/{int(cik)}/{accession.replace('-', '')}/"


# --- Watchlist and status ----------------------------------------------------------


@dataclass(frozen=True)
class ListedCompany:
    ticker: str
    cik: str | None  # None: ticker not resolved against SEC's ticker files
    name: str | None
    open_reviews: int = 0


def watchlist_tickers(path: Path) -> list[str]:
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return list(dict.fromkeys(t.strip().upper() for t in raw["watchlist"]["tickers"]))


def resolve_ticker(engine: sqlite3.Connection, ticker: str) -> str | None:
    row = engine.execute(
        "SELECT cik FROM ticker WHERE upper(ticker) = upper(?) AND valid_to IS NULL "
        "ORDER BY valid_from DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    return row["cik"] if row else None


def watchlist(engine: sqlite3.Connection, tickers: list[str]) -> list[ListedCompany]:
    out = []
    for t in tickers:
        cik = resolve_ticker(engine, t)
        name = None
        reviews = 0
        if cik:
            row = engine.execute("SELECT name FROM entity WHERE cik = ?", (cik,)).fetchone()
            name = row["name"] if row else None
            reviews = engine.execute(
                "SELECT count(*) FROM review_queue WHERE resolved_at IS NULL AND cik = ?", (cik,)
            ).fetchone()[0]
        out.append(ListedCompany(t, cik, name, reviews))
    return out


@dataclass(frozen=True)
class Status:
    open_reviews: int
    last_run_status: str | None
    last_run_finished: str | None
    last_run_started: str | None


def status(engine: sqlite3.Connection) -> Status:
    reviews = engine.execute(
        "SELECT count(*) FROM review_queue WHERE resolved_at IS NULL"
    ).fetchone()[0]
    run = engine.execute(
        "SELECT status, started_at, finished_at FROM refresh_run ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    if run is None:
        return Status(reviews, None, None, None)
    return Status(reviews, run["status"], run["finished_at"], run["started_at"])


def price_state(engine: sqlite3.Connection, symbol: str) -> dict[str, Any] | None:
    row = engine.execute("SELECT * FROM price_fetch WHERE symbol = ?", (symbol.upper(),)).fetchone()
    return dict(row) if row else None


# --- Company -----------------------------------------------------------------------


def company(engine: sqlite3.Connection, cik: str) -> dict[str, Any] | None:
    row = engine.execute("SELECT * FROM entity WHERE cik = ?", (cik,)).fetchone()
    return dict(row) if row else None


def filings(engine: sqlite3.Connection, cik: str, limit: int = 40) -> list[dict[str, Any]]:
    rows = engine.execute(
        "SELECT accession, form, filed, report_date, items, primary_doc, primary_doc_desc "
        "FROM filing WHERE cik = ? ORDER BY filed DESC, accession DESC LIMIT ?",
        (cik, limit),
    ).fetchall()
    return [dict(r) | {"url": filing_index_url(cik, r["accession"])} for r in rows]


def events(engine: sqlite3.Connection, cik: str, limit: int = 60) -> list[dict[str, Any]]:
    rows = engine.execute(
        "SELECT accession, item, form, filed, category, severity, title, amended FROM event "
        "WHERE cik = ? ORDER BY filed DESC, accession DESC, item LIMIT ?",
        (cik, limit),
    ).fetchall()
    return [dict(r) | {"url": filing_index_url(cik, r["accession"])} for r in rows]


def earnings_dates(engine: sqlite3.Connection, cik: str) -> list[str]:
    """Filing dates of earnings releases (8-K Item 2.02), oldest first — chart markers."""
    rows = engine.execute(
        "SELECT DISTINCT filed FROM event WHERE cik = ? AND item = '2.02' ORDER BY filed", (cik,)
    ).fetchall()
    return [r["filed"] for r in rows]


def insider_txns(engine: sqlite3.Connection, cik: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = engine.execute(
        "SELECT accession, line, owner_name, role, table_kind, security_title, txn_date, code, "
        "acquired_disposed, shares, price, shares_after, direct_indirect, is_10b5_1 "
        "FROM insider_txn WHERE issuer_cik = ? ORDER BY txn_date DESC, accession DESC, line "
        "LIMIT ?",
        (cik, limit),
    ).fetchall()
    return [dict(r) | {"url": filing_index_url(cik, r["accession"])} for r in rows]


# --- Financials (XBRL series) -------------------------------------------------------


@dataclass
class FinancialTable:
    title: str
    periods: list[str]  # period_end, newest first
    rows: list[tuple[str, str, list[dict[str, Any] | None]]] = field(default_factory=list)
    # (concept, unit kind, one cell per period: {value, accession, filed, method} or None)


def financials(engine: sqlite3.Connection, cik: str, quarters: int = 8) -> list[FinancialTable]:
    tables = []
    for title, kind, ptype in (
        ("Quarterly results", "flow", "Q"),
        ("Balance sheet", "instant", "I"),
    ):
        concepts = [c for c in CONCEPTS if c.kind == kind]
        names = [c.name for c in concepts]
        marks = ", ".join("?" * len(names))
        rows = engine.execute(
            f"SELECT concept, period_end, latest_value, latest_accession, latest_filed, method "
            f"FROM series WHERE cik = ? AND concept IN ({marks}) AND period_type = ?",
            [cik, *names, ptype],
        ).fetchall()
        periods = sorted({r["period_end"] for r in rows}, reverse=True)[:quarters]
        cells = {(r["concept"], r["period_end"]): r for r in rows}
        table = FinancialTable(title, periods)
        for c in concepts:
            line = [
                (
                    {
                        "value": r["latest_value"],
                        "accession": r["latest_accession"],
                        "filed": r["latest_filed"],
                        "method": r["method"],
                        "url": filing_index_url(cik, r["latest_accession"]),
                    }
                    if (r := cells.get((c.name, p)))
                    else None
                )
                for p in periods
            ]
            if any(line):
                table.rows.append((c.name, c.unit, line))
        tables.append(table)
    return tables


# --- Search and sources -----------------------------------------------------------


@dataclass(frozen=True)
class SearchResult:
    query_used: str
    note: str | None
    hits: list[Any]


def company_search(corpus: sqlite3.Connection, cik: str, q: str, limit: int = 20) -> SearchResult:
    """Tier-2 search in one company. Plain words that are not valid FTS5 syntax
    (e.g. 10b5-1) are retried as one quoted phrase."""
    try:
        return SearchResult(q, None, search(corpus, q, ciks=[cik], limit=limit))
    except QueryError:
        quoted = phrase(q)
        return SearchResult(
            quoted, "Searched as an exact phrase.", search(corpus, quoted, ciks=[cik], limit=limit)
        )


@dataclass(frozen=True)
class SourceView:
    accession: str
    filename: str
    doc_type: str | None
    cik: str
    url: str
    before: str
    highlight: str
    after: str
    section: str | None
    changed: bool  # document hash differs from the one the citation recorded


CONTEXT_CHARS = 1500


def source(
    corpus: sqlite3.Connection,
    accession: str,
    filename: str,
    start: int,
    end: int,
    sha: str | None = None,
) -> SourceView | None:
    doc = corpus.execute(
        "SELECT doc_id, cik, doc_type, url, text, sha256 FROM document "
        "WHERE accession = ? AND filename = ?",
        (accession, filename),
    ).fetchone()
    if doc is None:
        return None
    text = doc["text"]
    start = max(0, min(start, len(text)))
    end = max(start, min(end, len(text)))
    a = text.rfind("\n", 0, max(0, start - CONTEXT_CHARS)) + 1
    b = text.find("\n", min(len(text), end + CONTEXT_CHARS))
    b = len(text) if b == -1 else b
    sec = corpus.execute(
        "SELECT label, title FROM section WHERE doc_id = ? AND start_offset <= ? "
        "AND end_offset > ? LIMIT 1",
        (doc["doc_id"], start, start),
    ).fetchone()
    section = None
    if sec:
        section = f"{sec['label']} {sec['title']}" if sec["title"] else sec["label"]
    return SourceView(
        accession,
        filename,
        doc["doc_type"],
        doc["cik"],
        doc["url"],
        text[a:start],
        text[start:end],
        text[end:b],
        section,
        sha is not None and sha != doc["sha256"],
    )


# --- Document reader -----------------------------------------------------------------


def stored_accessions(corpus: sqlite3.Connection, accessions: list[str]) -> set[str]:
    """Which of these filings have documents stored in corpus.db (readable in the app)."""
    if not accessions:
        return set()
    marks = ", ".join("?" * len(accessions))
    rows = corpus.execute(
        f"SELECT DISTINCT accession FROM document WHERE accession IN ({marks})", accessions
    ).fetchall()
    return {r[0] for r in rows}


@dataclass(frozen=True)
class ReaderView:
    accession: str
    cik: str
    docs: list[dict[str, Any]]  # filename, doc_type, description, chars
    filename: str
    doc_type: str | None
    url: str
    sections: list[dict[str, Any]]  # section_id, label, title, chars
    section: dict[str, Any] | None
    before: str
    highlight: str
    after: str


def reader(
    corpus: sqlite3.Connection,
    accession: str,
    filename: str | None = None,
    section_id: int | None = None,
    start: int | None = None,
    end: int | None = None,
) -> ReaderView | None:
    """A stored filing by section, whole text (no limits, D22), optional highlight."""
    docs = [
        dict(r)
        for r in corpus.execute(
            "SELECT doc_id, cik, filename, doc_type, description, url, length(text) AS chars "
            "FROM document WHERE accession = ? ORDER BY doc_id",
            (accession,),
        )
    ]
    if not docs:
        return None
    doc = next((d for d in docs if d["filename"] == filename), docs[0])
    sections = [
        dict(r) | {"chars": r["end_offset"] - r["start_offset"]}
        for r in corpus.execute(
            "SELECT section_id, label, title, start_offset, end_offset FROM section "
            "WHERE doc_id = ? ORDER BY start_offset",
            (doc["doc_id"],),
        )
    ]
    chosen = None
    if section_id is not None:
        chosen = next((s for s in sections if s["section_id"] == section_id), None)
    if chosen is None and start is not None:
        chosen = next((s for s in sections if s["start_offset"] <= start < s["end_offset"]), None)
    if chosen is None and sections:
        body = [s for s in sections if s["label"] not in ("cover", "signatures")]
        chosen = (body or sections)[0]
    before = highlight = after = ""
    if chosen is not None:
        text = corpus.execute(
            "SELECT substr(text, ? + 1, ? - ?) FROM document WHERE doc_id = ?",
            (chosen["start_offset"], chosen["end_offset"], chosen["start_offset"], doc["doc_id"]),
        ).fetchone()[0]
        a, b = chosen["start_offset"], chosen["end_offset"]
        if start is not None and end is not None and a <= start < b:
            s, e = start - a, min(end, b) - a
            before, highlight, after = text[:s], text[s:e], text[e:]
        else:
            before = text
    return ReaderView(
        accession,
        doc["cik"],
        [{k: d[k] for k in ("filename", "doc_type", "description", "chars")} for d in docs],
        doc["filename"],
        doc["doc_type"],
        doc["url"],
        sections,
        chosen,
        before,
        highlight,
        after,
    )
