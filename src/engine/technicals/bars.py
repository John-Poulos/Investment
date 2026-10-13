"""Completed weekly bars on `price_bar` (M09 Part 1, rule 1; shared with M10 and M12).

`prices.store.bars()` (the chart) includes the partial current week; signals must not. Here:

- Dates are US Eastern market dates (D-SEC-16): "today" is the Eastern date of `now`.
- A week runs Monday–Friday. Its bar is keyed by the week's last trading day (the last
  session stored for the symbol in that week); OHLCV are adjusted (split- and
  dividend-adjusted, Tiingo `adj_*`); close = the adjusted close of that session.
- **Completed weeks only.** A week counts once its Friday has passed (Eastern) and the
  session calendar confirms its final session: a stored Friday session, or any later stored
  session (a holiday Friday such as Good Friday is confirmed by the next week's first
  session). The calendar is every session date stored in `price_bar` (SPY and every priced
  name: all Tiingo trading days), so its newest session is the newest anyone fetched.
- A symbol whose newest completed week lacks the calendar's final session of that week (a
  tracked name in the 3-day rotation not fetched yet, D-M02-12) drops that week and shows
  the older week; older weeks are never dropped (a halted day stays missing).
- Missing days are never filled. Stale = the last stored bar older than 5 calendar days
  (`prices.store.STALE_AFTER_DAYS`): reported, the caller writes "missing: stale bars".
- Shell cut-off: bars before a `spac_shell` tag's `before` date are excluded (INFQ before
  the 2026-02-13 merger close; `config/company_models.toml`, D-M04-8).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from engine.prices.store import STALE_AFTER_DAYS

MARKET_TZ = ZoneInfo("America/New_York")
CALENDAR_DAYS = 400  # sessions loaded for the completion test (only the newest weeks matter)


def eastern_today(now: datetime) -> date:
    """The US Eastern market date of `now` (an evening run in UTC is already "tomorrow")."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(MARKET_TZ).date()


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


class Calendar:
    """Stored session dates (≤ today) for the completion test."""

    def __init__(self, dates: Iterable[str], today: date) -> None:
        cut = today.isoformat()
        self.dates = sorted({d for d in dates if d <= cut})
        self.today = today

    @classmethod
    def load(cls, engine: sqlite3.Connection, today: date) -> Calendar:
        since = (today - timedelta(days=CALENDAR_DAYS)).isoformat()
        rows = engine.execute(
            "SELECT DISTINCT date FROM price_bar WHERE date >= ? AND adj_close IS NOT NULL",
            (since,),
        )
        return cls((r[0] for r in rows), today)

    def last_session(self, monday: date) -> str | None:
        lo, hi = monday.isoformat(), (monday + timedelta(days=4)).isoformat()
        inside = [d for d in self.dates if lo <= d <= hi]
        return inside[-1] if inside else None

    def week_complete(self, monday: date) -> bool:
        friday = monday + timedelta(days=4)
        if friday >= self.today:
            return False
        f = friday.isoformat()
        return bool(self.dates) and (f in self.dates or self.dates[-1] > f)

    def last_completed(self) -> tuple[date, str] | None:
        """(Monday, final session) of the newest completed week with a stored session."""
        mondays = sorted({monday_of(date.fromisoformat(d)) for d in self.dates}, reverse=True)
        for m in mondays:
            if self.week_complete(m):
                return m, self.last_session(m) or ""
        return None

    def expected_as_of(self) -> str:
        """The as_of a fully fetched name shows today: the newest completed week's final
        session; with no stored session, the Friday of the last week that has ended."""
        last = self.last_completed()
        if last:
            return last[1]
        friday = monday_of(self.today) + timedelta(days=4)
        if friday >= self.today:
            friday -= timedelta(days=7)
        return friday.isoformat()


@dataclass(frozen=True)
class WeekBar:
    date: str  # the week's last trading day for this symbol (the bar key)
    monday: str
    open: float
    high: float
    low: float
    close: float  # adjusted close of `date`
    volume: float
    sessions: int


@dataclass
class Weekly:
    symbol: str
    bars: list[WeekBar]  # completed weeks only, oldest first
    daily: list[tuple[str, float]]  # (date, adjusted close) after the cut-off, oldest first
    last_daily: str | None  # newest stored daily bar (any week)
    stale: bool
    stale_days: int | None
    cut_off: str | None = None  # shell cut-off applied (bars before it excluded)
    cut_bars: int = 0
    dropped: list[str] = field(default_factory=list)  # trailing weeks excluded, with why
    basis: str = ""  # adjusted-price basis: the last full fetch (rule 8)

    @property
    def as_of(self) -> str | None:
        return self.bars[-1].date if self.bars else None

    def closes(self) -> list[float]:
        return [b.close for b in self.bars]


def shell_cut_off(models, cik: str | None, ticker: str | None) -> str | None:
    """The `before` date of a company's `spac_shell` tag (bars before it are the shell's)."""
    if models is None:
        return None
    entry = models.any_for(cik, ticker)
    if entry is not None and entry.tag == "spac_shell" and entry.before:
        return entry.before
    return None


def _num(v) -> float | None:
    return None if v is None else float(v)


def weekly(
    engine: sqlite3.Connection,
    symbol: str,
    today: date,
    calendar: Calendar | None = None,
    *,
    cut_off: str | None = None,
) -> Weekly:
    """Completed weekly bars for one symbol as of the Eastern date `today`."""
    symbol = symbol.upper()
    cal = calendar if calendar is not None else Calendar.load(engine, today)
    rows = engine.execute(
        "SELECT date, adj_open, adj_high, adj_low, adj_close, adj_volume FROM price_bar "
        "WHERE symbol = ? AND adj_close IS NOT NULL AND date <= ? ORDER BY date",
        (symbol, today.isoformat()),
    ).fetchall()
    last_daily = rows[-1][0] if rows else None
    stale_days = (today - date.fromisoformat(last_daily)).days if last_daily else None
    stale = stale_days is None or stale_days > STALE_AFTER_DAYS
    cut_bars = 0
    if cut_off:
        kept = [r for r in rows if r[0] >= cut_off]
        cut_bars = len(rows) - len(kept)
        rows = kept
    weeks: dict[str, list] = {}
    order: list[str] = []
    for r in rows:
        key = monday_of(date.fromisoformat(r[0])).isoformat()
        if key not in weeks:
            weeks[key] = []
            order.append(key)
        weeks[key].append(r)
    bars: list[WeekBar] = []
    for key in order:
        days = weeks[key]
        close = float(days[-1][4])
        opens = [_num(d[1]) for d in days]
        highs = [x for d in days if (x := _num(d[2])) is not None]
        lows = [x for d in days if (x := _num(d[3])) is not None]
        bars.append(
            WeekBar(
                date=days[-1][0],
                monday=key,
                open=next((o for o in opens if o is not None), close),
                high=max(highs) if highs else close,
                low=min(lows) if lows else close,
                close=close,
                volume=sum(_num(d[5]) or 0.0 for d in days),
                sessions=len(days),
            )
        )
    dropped: list[str] = []
    while bars:  # trailing weeks only: the partial week, or a week not fetched to its end
        b = bars[-1]
        monday = date.fromisoformat(b.monday)
        if not cal.week_complete(monday):
            dropped.append(f"week of {b.monday}: not complete (last session {b.date})")
        elif (final := cal.last_session(monday)) and b.date < final:
            dropped.append(f"week of {b.monday}: last session {final} not fetched (have {b.date})")
        else:
            break
        bars.pop()
    full = engine.execute(
        "SELECT full_fetched_at FROM price_fetch WHERE symbol = ?", (symbol,)
    ).fetchone()
    basis = f"adjusted as of the full fetch {full[0][:10]}" if full and full[0] else ""
    daily = [(r[0], float(r[4])) for r in rows]
    return Weekly(symbol, bars, daily, last_daily, stale, stale_days, cut_off, cut_bars, dropped,
                  basis)  # fmt: skip
