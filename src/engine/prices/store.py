"""Store and serve daily bars (M00_UI DS8, D-UI-2/3).

Update rule per symbol:
- first fetch: full history (one request);
- later: from 5 days before the last stored bar (re-checks recent corrections);
- if a newly fetched bar carries a dividend or split, the full history is fetched
  again, because the provider recomputes every earlier adjusted price.
A throttle or budget stop ends a batch; the remaining symbols wait for the next run.
Charts read adjusted prices; raw prices are kept for audit.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from engine.prices.tiingo import TiingoClient
from engine.sec.client import iso
from engine.sec.results import Failed, NotFound, Ok

FULL_START = date(1962, 1, 2)
OVERLAP_DAYS = 5
STALE_AFTER_DAYS = 5  # calendar days since the last bar (covers weekends and a holiday)
# Benchmark symbol (D-UI-33, D-M09-6): fetched every run with the core names (one
# full-history request, then one a day), stored with no CIK, never given D13 rows; M09's
# market context, M10's move_context, M11's hurdle proxy and M12 read it.
BENCHMARK = "SPY"


def with_benchmark(symbols: dict[str, str | None]) -> dict[str, str | None]:
    """The run's symbol map with the benchmark added (no CIK)."""
    out = dict(symbols)
    out.setdefault(BENCHMARK, None)
    return out


_COLS = (
    ("open", "open"), ("high", "high"), ("low", "low"), ("close", "close"), ("volume", "volume"),
    ("adjOpen", "adj_open"), ("adjHigh", "adj_high"), ("adjLow", "adj_low"),
    ("adjClose", "adj_close"), ("adjVolume", "adj_volume"),
    ("divCash", "div_cash"), ("splitFactor", "split_factor"),
)  # fmt: skip


def _n(v: Any) -> str | None:
    return None if v is None else format(Decimal(str(v)), "f")


def write_bars(
    engine: sqlite3.Connection, symbol: str, rows: list[dict[str, Any]], now: datetime
) -> int:
    cols = ", ".join(c for _, c in _COLS)
    marks = ", ".join("?" * (len(_COLS) + 4))
    updates = ", ".join(f"{c} = excluded.{c}" for _, c in _COLS)
    engine.executemany(
        f"INSERT INTO price_bar (symbol, date, {cols}, source, fetched_at) VALUES ({marks}) "
        f"ON CONFLICT (symbol, date) DO UPDATE SET {updates}, source = excluded.source, "
        "fetched_at = excluded.fetched_at",
        [
            (symbol, str(r["date"])[:10], *(_n(r.get(k)) for k, _ in _COLS), "tiingo", iso(now))
            for r in rows
        ],
    )
    return len(rows)


def _event(row: dict[str, Any]) -> bool:
    div = Decimal(str(row.get("divCash") or 0))
    split = Decimal(str(row.get("splitFactor") or 1))
    return div != 0 or split != 1


@dataclass(frozen=True)
class SymbolUpdate:
    symbol: str
    outcome: str  # ok | not_found | failed | throttled | budget
    bars: int = 0
    full: bool = False
    detail: str = ""


def _state(
    engine: sqlite3.Connection,
    symbol: str,
    cik: str | None,
    outcome: str,
    detail: str,
    now: datetime,
    *,
    full: bool = False,
) -> None:
    span = engine.execute(
        "SELECT min(date), max(date), count(*) FROM price_bar WHERE symbol = ?", (symbol,)
    ).fetchone()
    engine.execute(
        "INSERT INTO price_fetch (symbol, cik, first_date, last_date, bars, last_fetched_at, "
        "last_outcome, detail, full_fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (symbol) DO UPDATE SET cik = coalesce(excluded.cik, cik), "
        "first_date = excluded.first_date, last_date = excluded.last_date, bars = excluded.bars, "
        "last_fetched_at = excluded.last_fetched_at, last_outcome = excluded.last_outcome, "
        "detail = excluded.detail, full_fetched_at = coalesce(excluded.full_fetched_at, "
        "full_fetched_at)",
        (
            symbol,
            cik,
            span[0],
            span[1],
            span[2],
            iso(now),
            outcome,
            detail,
            iso(now) if full else None,
        ),  # fmt: skip
    )


def update_symbol(
    engine: sqlite3.Connection,
    client: TiingoClient,
    symbol: str,
    cik: str | None,
    now: datetime,
    *,
    full: bool = False,
) -> SymbolUpdate:
    symbol = symbol.upper()
    last = engine.execute("SELECT max(date) FROM price_bar WHERE symbol = ?", (symbol,)).fetchone()[
        0
    ]
    full = full or last is None
    start = FULL_START if full else date.fromisoformat(last) - timedelta(days=OVERLAP_DAYS)
    res = client.daily(symbol, start)
    if (
        isinstance(res, Ok)
        and not full
        and any(_event(r) for r in res.data if str(r["date"])[:10] > last)
    ):
        full = True  # dividend or split: every earlier adjusted price changed
        res = client.daily(symbol, FULL_START)
    if isinstance(res, Ok):
        engine.execute("BEGIN")
        try:
            if full:
                engine.execute("DELETE FROM price_bar WHERE symbol = ?", (symbol,))
            n = write_bars(engine, symbol, res.data, now)
            _state(engine, symbol, cik, "ok", f"{n} bars", now, full=full)
            engine.execute("COMMIT")
        except Exception:
            engine.execute("ROLLBACK")
            raise
        return SymbolUpdate(symbol, "ok", n, full)
    if isinstance(res, NotFound):
        _state(engine, symbol, cik, "not_found", "symbol not found at Tiingo", now)
        return SymbolUpdate(symbol, "not_found", detail="symbol not found at Tiingo")
    assert isinstance(res, Failed)
    outcome = "throttled" if res.throttled else "failed"
    if res.throttled and res.status is None:
        outcome = "budget"
    _state(engine, symbol, cik, outcome, res.reason, now)
    return SymbolUpdate(symbol, outcome, detail=res.reason)


@dataclass
class PriceReport:
    updates: list[SymbolUpdate] = field(default_factory=list)
    stopped: str | None = None  # why the batch stopped early
    skipped: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = ["", "Prices (Tiingo)"]
        for u in self.updates:
            extra = " (full history)" if u.full else ""
            out.append(f"  {u.symbol}: {u.outcome} {u.bars} bars{extra} {u.detail}".rstrip())
        if self.stopped:
            out.append(
                f"  stopped early: {self.stopped}; left for next run: {', '.join(self.skipped)}"
            )
        return out


def refresh_prices(
    engine: sqlite3.Connection,
    client: TiingoClient,
    symbols: dict[str, str | None],
    now: datetime,
) -> PriceReport:
    """Update each symbol (symbol → cik). Stops at the first throttle or budget stop."""
    report = PriceReport()
    todo = list(symbols.items())
    for i, (symbol, cik) in enumerate(todo):
        u = update_symbol(engine, client, symbol, cik, now)
        report.updates.append(u)
        if u.outcome in ("throttled", "budget"):
            report.stopped = u.detail
            report.skipped = [s for s, _ in todo[i + 1 :]]
            break
    return report


TRACKED_ROTATION_DAYS = 3  # D-M02-12: each tracked name about every third run
TRACKED_SOFT_CAP = 150


def tracked_rotation(
    engine: sqlite3.Connection, tracked: dict[str, str | None]
) -> tuple[dict[str, str | None], list[str]]:
    """Today's share of the tracked tier: never-fetched first, then the oldest fetch.
    Returns (symbols to fetch today, symbols over the soft cap)."""
    names = sorted(tracked)
    over = names[TRACKED_SOFT_CAP:]
    names = names[:TRACKED_SOFT_CAP]
    last = {r["symbol"]: r["last_fetched_at"] or "" for r in engine.execute(
        "SELECT symbol, last_fetched_at FROM price_fetch")}  # fmt: skip
    order = sorted(names, key=lambda s: (last.get(s, ""), s))
    take = -(-len(names) // TRACKED_ROTATION_DAYS)  # ceiling
    today = order[:take]
    return {s: tracked[s] for s in today}, over


# --- Reading -----------------------------------------------------------------------


@dataclass(frozen=True)
class Bars:
    symbol: str
    bar: str  # D | W
    bars: list[dict[str, Any]]  # time, open, high, low, close, volume (adjusted)
    last_date: str | None
    stale: bool
    markers: list[dict[str, str]]


def _week_key(d: str) -> str:
    day = date.fromisoformat(d)
    return (day - timedelta(days=day.weekday())).isoformat()  # Monday of that week


def bars(
    engine: sqlite3.Connection,
    symbol: str,
    bar: str,
    today: date,
    events: list[str] | None = None,
) -> Bars:
    rows = engine.execute(
        "SELECT date, adj_open, adj_high, adj_low, adj_close, adj_volume FROM price_bar "
        "WHERE symbol = ? AND adj_close IS NOT NULL ORDER BY date",
        (symbol.upper(),),
    ).fetchall()
    daily = [
        {"time": r[0], "open": float(r[1]), "high": float(r[2]), "low": float(r[3]),
         "close": float(r[4]), "volume": float(r[5] or 0)}
        for r in rows
        if None not in (r[1], r[2], r[3], r[4])
    ]  # fmt: skip
    out = daily
    if bar == "W":
        weeks: dict[str, dict[str, Any]] = {}
        for b in daily:
            k = _week_key(b["time"])
            w = weeks.get(k)
            if w is None:
                weeks[k] = dict(b, time=k)
            else:
                w["high"] = max(w["high"], b["high"])
                w["low"] = min(w["low"], b["low"])
                w["close"] = b["close"]
                w["volume"] += b["volume"]
        out = list(weeks.values())
    last = rows[-1][0] if rows else None
    stale = last is None or (today - date.fromisoformat(last)).days > STALE_AFTER_DAYS
    times = [b["time"] for b in out]
    markers = []
    for d in events or []:
        key = _week_key(d) if bar == "W" else d
        t = next((x for x in times if x >= key), None)  # first bar on or after the event
        if t is not None:
            markers.append({"time": t, "text": "ER"})
    return Bars(symbol.upper(), bar, out, last, stale, markers)
