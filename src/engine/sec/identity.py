"""Ticker ↔ CIK, name, SIC, fiscal year end (M00_SEC_DATA identity.py).

Ticker files are primary: company_tickers_exchange.json (adds exchange), then
company_tickers.json for tickers the first omits. Both refresh daily into the
`ticker` table, which keeps history (valid_from/valid_to). Entity details come
from the submissions JSON. Lookups read storage first (M00_STORAGE read path);
a failed refresh serves the stored copy flagged stale, never a blank.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from engine.sec.client import SecClient, iso
from engine.sec.results import Empty, Failed, Ok, Probe, Result

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

TICKER_BACKSTOP = timedelta(days=1)
SUBMISSIONS_BACKSTOP = timedelta(days=1)
CACHE_TTL_S = 20 * 3600  # under a day, so the daily refresh refetches
MIN_KEEP_RATIO = 0.5  # refuse a refresh that would drop over half the current tickers

TICKER_MAP_PATH = "ticker map (company_tickers_exchange.json, company_tickers.json)"


@dataclass(frozen=True)
class TickerRow:
    cik: str
    name: str | None
    exchange: str | None
    source: str


@dataclass(frozen=True)
class TickerRefresh:
    current: int
    added: int
    changed: int
    closed: int
    conflicts: tuple[str, ...]


@dataclass(frozen=True)
class Entity:
    cik: str
    name: str
    sic: str | None
    sic_description: str | None
    fiscal_year_end: str | None
    exchanges: tuple[str, ...]
    tickers: tuple[str, ...]
    entity_type: str | None
    state_of_inc: str | None


def normalize_ticker(value: str) -> str:
    """SEC writes share classes with '-' (BRK-B); accept BRK.B and BRK/B."""
    return re.sub(r"[./]", "-", value.strip().upper())


def normalize_cik(value: str | int) -> str | None:
    text = str(value).strip()
    if not text.isdigit() or len(text.lstrip("0")) > 10:
        return None
    return text.zfill(10)


# --- Parsing -----------------------------------------------------------------


def parse_ticker_files(
    exchange_json: dict[str, Any], tickers_json: dict[str, Any]
) -> tuple[dict[str, TickerRow], list[str]]:
    """Merge both SEC ticker files. Returns (ticker → row, conflicts).

    A ticker listed under two CIKs keeps the first seen (exchange file first) and
    is reported as a conflict rather than silently overwritten.
    """
    rows: dict[str, TickerRow] = {}
    conflicts: list[str] = []

    def add(ticker: Any, cik: Any, name: Any, exchange: Any, source: str) -> None:
        if not ticker:
            return
        t = normalize_ticker(str(ticker))
        c = normalize_cik(cik)
        if c is None:
            conflicts.append(f"{t}: unreadable CIK {cik!r} in {source}")
            return
        existing = rows.get(t)
        if existing is None:
            rows[t] = TickerRow(c, name or None, exchange or None, source)
        elif existing.cik != c:
            conflicts.append(f"{t}: CIK {existing.cik} ({existing.source}) vs {c} ({source})")

    fields = exchange_json.get("fields") or []
    try:
        ci, ni, ti, ei = (fields.index(f) for f in ("cik", "name", "ticker", "exchange"))
    except ValueError as exc:
        raise ValueError(f"company_tickers_exchange.json fields changed: {fields}") from exc
    for rec in exchange_json.get("data") or []:
        add(rec[ti], rec[ci], rec[ni], rec[ei], "company_tickers_exchange.json")

    for rec in tickers_json.values():
        add(rec.get("ticker"), rec.get("cik_str"), rec.get("title"), None, "company_tickers.json")

    return rows, conflicts


def parse_submissions(cik: str, data: dict[str, Any]) -> Entity:
    def text(key: str) -> str | None:
        value = data.get(key)
        return str(value) if value not in (None, "") else None

    return Entity(
        cik=cik,
        name=str(data.get("name") or "").strip(),
        sic=text("sic"),
        sic_description=text("sicDescription"),
        fiscal_year_end=text("fiscalYearEnd"),
        exchanges=tuple(str(x) for x in data.get("exchanges") or [] if x),
        tickers=tuple(str(x) for x in data.get("tickers") or [] if x),
        entity_type=text("entityType"),
        state_of_inc=text("stateOfIncorporation"),
    )


# --- Ticker map --------------------------------------------------------------


def refresh_ticker_map(
    client: SecClient, conn: sqlite3.Connection, today: date, now: datetime
) -> Result[TickerRefresh]:
    """Fetch both ticker files and apply them to the ticker history in one transaction."""
    exch = client.get_json(EXCHANGE_URL, ttl_s=CACHE_TTL_S)
    tick = client.get_json(TICKERS_URL, ttl_s=CACHE_TTL_S)
    for res, url in ((exch, EXCHANGE_URL), (tick, TICKERS_URL)):
        if isinstance(res, Empty):
            return Failed("ticker file not found (HTTP 404)", url=url, status=404)
        if isinstance(res, Failed):
            return res
    assert isinstance(exch, Ok) and isinstance(tick, Ok)

    try:
        rows, conflicts = parse_ticker_files(exch.data, tick.data)
    except (ValueError, AttributeError, IndexError, TypeError) as exc:
        return Failed(f"ticker files unreadable: {exc}", url=EXCHANGE_URL)

    current = {
        r["ticker"]: r
        for r in conn.execute("SELECT * FROM ticker WHERE valid_to IS NULL").fetchall()
    }
    if current and len(rows) < MIN_KEEP_RATIO * len(current):
        return Failed(
            f"ticker files list {len(rows)} tickers vs {len(current)} stored; refusing refresh",
            url=EXCHANGE_URL,
        )

    day = today.isoformat()
    added = changed = closed = 0
    conn.execute("BEGIN")
    try:
        for t, row in rows.items():
            old = current.get(t)
            if old is None:
                _insert_ticker(conn, t, row, day)
                added += 1
            elif old["cik"] != row.cik:
                conn.execute(
                    "UPDATE ticker SET valid_to = ? WHERE ticker = ? AND valid_to IS NULL",
                    (day, t),
                )
                _insert_ticker(conn, t, row, day)
                changed += 1
            else:
                conn.execute(
                    "UPDATE ticker SET name = ?, exchange = coalesce(?, exchange), source = ? "
                    "WHERE ticker = ? AND valid_to IS NULL",
                    (row.name, row.exchange, row.source, t),
                )
        for t in current.keys() - rows.keys():
            conn.execute(
                "UPDATE ticker SET valid_to = ? WHERE ticker = ? AND valid_to IS NULL", (day, t)
            )
            closed += 1
        summary = TickerRefresh(len(rows), added, changed, closed, tuple(conflicts))
        _set_refresh_state(conn, "ticker_map", EXCHANGE_URL, now, summary)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return Ok(summary, source_ref=EXCHANGE_URL, fetched_at=iso(now))


def _insert_ticker(conn: sqlite3.Connection, ticker: str, row: TickerRow, day: str) -> None:
    # A span opened and closed on the same day is reopened in place (same key).
    conn.execute(
        "INSERT INTO ticker (ticker, cik, exchange, name, valid_from, source) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (ticker, valid_from) DO UPDATE SET cik = excluded.cik, "
        "exchange = excluded.exchange, name = excluded.name, source = excluded.source, "
        "valid_to = NULL",
        (ticker, row.cik, row.exchange, row.name, day, row.source),
    )


def _set_refresh_state(
    conn: sqlite3.Connection, name: str, source_ref: str, now: datetime, detail: Any
) -> None:
    conn.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET source_ref = excluded.source_ref, "
        "fetched_at = excluded.fetched_at, detail = excluded.detail",
        (name, source_ref, iso(now), json.dumps(detail.__dict__, default=list)),
    )


def _ticker_map_age(conn: sqlite3.Connection, now: datetime) -> timedelta | None:
    row = conn.execute("SELECT fetched_at FROM refresh_state WHERE name = 'ticker_map'").fetchone()
    if row is None:
        return None
    return now - datetime.fromisoformat(row["fetched_at"])


def resolve(
    client: SecClient, conn: sqlite3.Connection, identifier: str, now: datetime
) -> Result[str]:
    """Identifier (ticker or numeric CIK) → 10-digit CIK."""
    ident = (identifier or "").strip()
    if not ident:
        return Empty((Probe("identifier", "", "empty identifier"),))

    cik = normalize_cik(ident)
    if cik is not None:
        return Ok(cik, source_ref="numeric CIK")

    stale = False
    age = _ticker_map_age(conn, now)
    if age is None or age >= TICKER_BACKSTOP:
        refreshed = refresh_ticker_map(client, conn, now.date(), now)
        if isinstance(refreshed, Failed):
            if age is None:
                return refreshed
            stale = True

    ticker = normalize_ticker(ident)
    row = conn.execute(
        "SELECT cik FROM ticker WHERE ticker = ? AND valid_to IS NULL", (ticker,)
    ).fetchone()
    if row is not None:
        return Ok(row["cik"], source_ref=TICKER_MAP_PATH, stale=stale)

    probes = [Probe(TICKER_MAP_PATH, ticker, "no current match" + (" (stale)" if stale else ""))]
    for old in conn.execute(
        "SELECT cik, valid_from, valid_to FROM ticker WHERE ticker = ? ORDER BY valid_from",
        (ticker,),
    ):
        probes.append(
            Probe(
                "ticker history",
                ticker,
                f"CIK {old['cik']} from {old['valid_from']} to {old['valid_to']}",
            )
        )
    return Empty(tuple(probes))


# --- Entity ------------------------------------------------------------------


def load_entity(
    client: SecClient, conn: sqlite3.Connection, cik: str, now: datetime
) -> Result[Entity]:
    """Name, SIC, fiscal year end, exchanges and tickers from the submissions JSON."""
    norm = normalize_cik(cik)
    if norm is None:
        return Empty((Probe("CIK", str(cik), "not a CIK"),))

    stored = conn.execute("SELECT * FROM entity WHERE cik = ?", (norm,)).fetchone()
    if stored is not None:
        age = now - datetime.fromisoformat(stored["fetched_at"])
        if age < SUBMISSIONS_BACKSTOP:
            return Ok(_entity_from_row(stored), stored["source_ref"], stored["fetched_at"], True)

    url = SUBMISSIONS_URL.format(cik=norm)
    res = client.get_json(url, ttl_s=CACHE_TTL_S)
    if isinstance(res, Failed):
        if stored is not None:
            return Ok(
                _entity_from_row(stored),
                stored["source_ref"],
                stored["fetched_at"],
                True,
                stale=True,
            )
        return res
    if isinstance(res, Empty):
        return res

    try:
        entity = parse_submissions(norm, res.data)
    except (AttributeError, TypeError) as exc:
        return Failed(f"submissions unreadable: {exc}", url=url)
    if not entity.name:
        return Failed("submissions has no entity name", url=url)

    conn.execute(
        "INSERT INTO entity (cik, name, sic, sic_description, fiscal_year_end, exchanges, "
        "tickers, entity_type, state_of_inc, source_ref, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (cik) DO UPDATE SET name = excluded.name, sic = excluded.sic, "
        "sic_description = excluded.sic_description, "
        "fiscal_year_end = excluded.fiscal_year_end, exchanges = excluded.exchanges, "
        "tickers = excluded.tickers, entity_type = excluded.entity_type, "
        "state_of_inc = excluded.state_of_inc, source_ref = excluded.source_ref, "
        "fetched_at = excluded.fetched_at",
        (
            entity.cik,
            entity.name,
            entity.sic,
            entity.sic_description,
            entity.fiscal_year_end,
            json.dumps(entity.exchanges),
            json.dumps(entity.tickers),
            entity.entity_type,
            entity.state_of_inc,
            url,
            iso(now),
        ),
    )
    return Ok(entity, source_ref=url, fetched_at=iso(now), from_cache=res.from_cache)


def _entity_from_row(row: sqlite3.Row) -> Entity:
    return Entity(
        cik=row["cik"],
        name=row["name"],
        sic=row["sic"],
        sic_description=row["sic_description"],
        fiscal_year_end=row["fiscal_year_end"],
        exchanges=tuple(json.loads(row["exchanges"] or "[]")),
        tickers=tuple(json.loads(row["tickers"] or "[]")),
        entity_type=row["entity_type"],
        state_of_inc=row["state_of_inc"],
    )
