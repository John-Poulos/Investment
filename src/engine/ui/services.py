"""Read functions behind the UI pages (M00_UI rule U4).

Plain functions over the two SQLite connections, returning plain data. Pages
and templates never run SQL; the same functions can serve scripts or an API.
Missing data stays missing (None), never zero.
"""

from __future__ import annotations

import re
import sqlite3
import tomllib
from dataclasses import dataclass, field
from decimal import Decimal
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
    tier: str = "core"  # core | promoted | tracked (D-M02-11)
    theme: str | None = None


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


def tiered(
    engine: sqlite3.Connection, core: list[ListedCompany]
) -> tuple[list[ListedCompany], list[ListedCompany]]:
    """Side panel lists: watchlist = core (toml) + promoted; tracked separately (D-M02-11)."""
    from engine.themes.tiers import members

    core_ciks = {c.cik for c in core if c.cik}
    promoted, tracked = [], []
    for m in members(engine):
        if m.cik in core_ciks:
            continue
        row = engine.execute("SELECT name FROM entity WHERE cik = ?", (m.cik,)).fetchone()
        reviews = engine.execute(
            "SELECT count(*) FROM review_queue WHERE resolved_at IS NULL AND cik = ?", (m.cik,)
        ).fetchone()[0]
        item = ListedCompany(m.ticker, m.cik, row["name"] if row else None, reviews, m.tier,
                             m.theme_key)  # fmt: skip
        (promoted if m.tier == "promoted" else tracked).append(item)
    return core + promoted, tracked


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
    blocks: list[Any] = field(default_factory=list)  # layout() of the section


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
    hl = (start, end) if start is not None and end is not None else None
    blocks = (
        layout(before + highlight + after, chosen["start_offset"], hl) if chosen is not None else []
    )
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
        blocks,
    )


# --- Text layout for the reader ---------------------------------------------------

_NUMERIC_CELL = re.compile(r"^[\s$€£(−-]*[\d.,]+\s*[%)]*\s*$|^[—–-]$")


@dataclass
class Block:
    kind: str  # p | table
    parts: list[tuple[str, bool]] = field(default_factory=list)  # p: (text, highlighted)
    rows: list[tuple[list[tuple[str, bool]], bool]] = field(default_factory=list)
    # table: ([(cell, numeric)], row highlighted)
    highlighted: bool = False


def layout(text: str, base: int = 0, hl: tuple[int, int] | None = None) -> list[Block]:
    """Split stored text into paragraphs and tables. Stored text has one block per
    line and tab-separated table cells (html_to_text); consecutive tab lines (blank
    lines between rows allowed) form one table. Offsets are absolute (base + index)
    so a citation's highlight lands on the right paragraph or table row."""
    blocks: list[Block] = []
    pos = 0
    table: Block | None = None
    for line in text.split("\n"):
        a, b = base + pos, base + pos + len(line)
        pos += len(line) + 1
        if not line.strip():
            continue
        hit = hl is not None and a < hl[1] and hl[0] < b
        if "\t" in line:
            cells = [c.strip() for c in line.split("\t")]
            row = ([(c, bool(_NUMERIC_CELL.match(c))) for c in cells], hit)
            if table is None:
                table = Block("table")
                blocks.append(table)
            table.rows.append(row)
            table.highlighted |= hit
            continue
        table = None
        blk = Block("p", highlighted=hit)
        if hit and hl is not None:
            s, e = max(hl[0], a) - a, min(hl[1], b) - a
            blk.parts = [(line[:s], False), (line[s:e], True), (line[e:], False)]
        else:
            blk.parts = [(line, False)]
        blocks.append(blk)
    for blk in blocks:
        if blk.kind == "table":
            width = max(len(r[0]) for r in blk.rows)
            blk.rows = [(cells + [("", False)] * (width - len(cells)), h) for cells, h in blk.rows]
    return blocks


# --- Guidance (R19) ------------------------------------------------------------------

METRIC_ORDER = (
    "revenue", "gross_margin", "operating_expenses", "total_expenses", "operating_income",
    "operating_margin", "other_income", "tax_rate", "net_income", "eps_diluted", "capex",
    "shares_basic", "shares_diluted",
)  # fmt: skip


@dataclass
class GuidanceRow:
    guidance_id: int
    stated_on: str
    accession: str
    filename: str
    value: str
    kind: str  # range | plusminus | approx | point
    source: str  # sentence | table
    quote: str
    quote_start: int
    quote_end: int
    doc_sha256: str
    change: str  # first stated | raised | ... (code, guidance/changes.py)
    prior: str | None
    flag: str | None
    flag_reason: str | None
    reason: dict[str, Any] | None = None  # verified Gemini observation, with citations


@dataclass
class GuidanceGroup:
    metric: str
    basis: str
    period: str
    rows: list[GuidanceRow]


@dataclass
class GuidanceView:
    groups: list[GuidanceGroup]
    no_guidance: list[str]  # filing dates of releases scanned with no numeric guidance
    open_reviews: int
    last_call: dict[str, Any] | None


def _period_key(period: str) -> tuple[int, int]:
    parts = period.split()
    year = int(parts[0][2:])
    q = int(parts[1][1:]) if len(parts) > 1 and parts[1].startswith("Q") else 5
    return (year, q)


def guidance_view(engine: sqlite3.Connection, cik: str) -> GuidanceView:
    from engine.guidance.changes import changes_for
    from engine.llm.guidance_reasons import USE_CASE, fmt_range
    from engine.llm.runs import load_observations

    kinds = {c.guidance_id: c.kind for c in changes_for(engine, cik)}
    reasons: dict[int, dict[str, Any]] = {}
    call = engine.execute(
        "SELECT call_id, model, created_at, cost_usd FROM llm_call WHERE cik = ? AND use_case = ? "
        "AND status = 'ok' ORDER BY call_id DESC LIMIT 1",
        (cik, USE_CASE),
    ).fetchone()
    last_call = None
    if call:
        obs = load_observations(engine, call["call_id"])
        for o in obs:
            gid = o.subject.get("guidance_id")
            if o.verified and gid is not None:
                reasons[gid] = {
                    "claim": o.claim,
                    "citations": [c.__dict__ for c in o.citations],
                }
        last_call = dict(call) | {
            "verified": sum(o.verified for o in obs),
            "rejected": sum(not o.verified for o in obs),
        }
    groups: dict[tuple[str, str, str], GuidanceGroup] = {}
    for r in engine.execute(
        "SELECT * FROM guidance WHERE cik = ? ORDER BY stated_on, guidance_id", (cik,)
    ):
        key = (r["metric"], r["basis"], r["period"])
        g = groups.setdefault(key, GuidanceGroup(*key, []))
        low, high = Decimal(str(r["low"])), Decimal(str(r["high"]))
        prior = None
        if r["prior_low"] is not None:
            prior = fmt_range(
                Decimal(str(r["prior_low"])), Decimal(str(r["prior_high"])), r["unit"]
            )
        g.rows.append(
            GuidanceRow(
                r["guidance_id"],
                r["stated_on"],
                r["accession"],
                r["filename"],
                fmt_range(low, high, r["unit"]),
                r["kind"],
                r["source"],
                r["quote"],
                r["quote_start"],
                r["quote_end"],
                r["doc_sha256"],
                kinds.get(r["guidance_id"], "first stated" if not g.rows else "—"),
                prior,
                r["flag"],
                r["flag_reason"],
                reasons.get(r["guidance_id"]),
            )  # fmt: skip
        )
    order = {m: i for i, m in enumerate(METRIC_ORDER)}
    ordered = sorted(
        groups.values(),
        key=lambda g: (
            [-x for x in _period_key(g.period)],
            order.get(g.metric, 99),
            g.basis,
        ),
    )
    none = [
        r[0]
        for r in engine.execute(
            "SELECT filed FROM guidance_scan WHERE cik = ? AND outcome = 'none' "
            "ORDER BY filed DESC",
            (cik,),
        )
    ]
    reviews = engine.execute(
        "SELECT count(*) FROM review_queue WHERE resolved_at IS NULL AND cik = ? "
        "AND kind IN ('guidance_unparsed', 'guidance_conflict', 'llm_rejected')",
        (cik,),
    ).fetchone()[0]
    return GuidanceView(ordered, none, reviews, last_call)


# --- Runs and costs ------------------------------------------------------------------


def runs_and_costs(engine: sqlite3.Connection, now_iso: str) -> dict[str, Any]:
    """Nightly runs, guidance scans, Gemini spend and Tiingo usage vs its limits (D-UI-13)."""
    from datetime import datetime, timedelta

    from engine.prices.tiingo import BASE, DAILY_BUDGET, HOURLY_BUDGET, MONTHLY_SYMBOLS, symbol_of

    now = datetime.fromisoformat(now_iso)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    def since(delta: timedelta) -> str:
        return (now - delta).isoformat(timespec="seconds")

    runs = [
        dict(r)
        for r in engine.execute(
            "SELECT run_id, trigger, started_at, finished_at, status, companies, error "
            "FROM refresh_run ORDER BY run_id DESC LIMIT 20"
        )
    ]
    scans = {
        r[0]: r[1]
        for r in engine.execute("SELECT outcome, count(*) FROM guidance_scan GROUP BY outcome")
    }
    last_scan = engine.execute("SELECT max(at) FROM guidance_scan").fetchone()[0]
    llm_month = engine.execute(
        "SELECT count(*), coalesce(sum(cost_usd), 0), coalesce(sum(input_tokens), 0), "
        "coalesce(sum(output_tokens), 0) FROM llm_call WHERE created_at >= ?",
        (month,),
    ).fetchone()
    llm_all = engine.execute("SELECT count(*), coalesce(sum(cost_usd), 0) FROM llm_call").fetchone()
    calls = [
        dict(r)
        for r in engine.execute(
            "SELECT c.call_id, c.use_case, c.cik, t.ticker, c.model, c.input_tokens, "
            "c.output_tokens, c.cost_usd, c.status, c.created_at FROM llm_call c "
            "LEFT JOIN ticker t ON t.cik = c.cik AND t.valid_to IS NULL "
            "ORDER BY c.call_id DESC LIMIT 20"
        )
    ]
    tiingo = BASE + "/%"
    hour = engine.execute(
        "SELECT count(*) FROM fetch_log WHERE url LIKE ? AND at >= ? AND from_cache = 0",
        (tiingo, since(timedelta(hours=1))),
    ).fetchone()[0]
    day = engine.execute(
        "SELECT count(*) FROM fetch_log WHERE url LIKE ? AND at >= ? AND from_cache = 0",
        (tiingo, since(timedelta(days=1))),
    ).fetchone()[0]
    symbols = {
        s
        for (u,) in engine.execute(
            "SELECT DISTINCT url FROM fetch_log WHERE url LIKE ? AND at >= ?", (tiingo, month)
        )
        if (s := symbol_of(u))
    }
    prices = [
        dict(r)
        for r in engine.execute(
            "SELECT symbol, first_date, last_date, bars, last_outcome, last_fetched_at "
            "FROM price_fetch ORDER BY symbol"
        )
    ]
    return {
        "runs": runs,
        "scans": scans,
        "last_scan": last_scan,
        "llm_month": {
            "calls": llm_month[0],
            "cost": llm_month[1],
            "input": llm_month[2],
            "output": llm_month[3],
        },  # fmt: skip
        "llm_all": {"calls": llm_all[0], "cost": llm_all[1]},
        "calls": calls,
        "tiingo": {
            "hour": hour,
            "hour_cap": HOURLY_BUDGET,
            "day": day,
            "day_cap": DAILY_BUDGET,
            "symbols": len(symbols),
            "symbols_cap": MONTHLY_SYMBOLS,
        },  # fmt: skip
        "prices": prices,
    }
