"""Point-in-time inputs for M08 (rule 1; D-M08-2, -10).

At a date d: the raw close on or before d (5-day tolerance; never `adj_close`), the cover
share count last filed on or before d scaled by the splits between its cover date and the
close (Tiingo split factors), and fundamentals filed on or before d.

`Known` reads each concept once per company (`facts_as_of` on today) and serves two views:

- `view(d)` — points first filed on or before d, at their **latest** value (the row of a
  recent week: a restatement filed since is applied; a filing made after d is not seen);
- `view(d, first=True)` — the same points at their **first-filed** value, accession and date
  (the own-history quarter-ends, D-M08-2: what the market saw then).

One read per concept and company keeps a 60-quarter history cheap (D-M08-10).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import date, timedelta

from engine.financials import distress, shares
from engine.financials.debt import Points
from engine.sec.asof import AsOfPoint, facts_as_of
from engine.sec.identity import normalize_cik
from engine.sec.xbrl_facts import Concept
from engine.signals import Source

TOLERANCE = 5
MIN_YEAR_BARS = 200  # sessions in the 365 days before a close (D-M08-12; about 250 trade)


class Known:
    """One company's facts, read once as of `as_of` (today)."""

    def __init__(self, engine: sqlite3.Connection, cik: str, as_of: str) -> None:
        self.engine = engine
        self.cik = normalize_cik(cik) or cik
        self.as_of = as_of
        self._pts: dict[tuple[str, str], tuple[AsOfPoint, ...]] = {}
        self._splits: list[tuple[str, float]] | None = None
        self._covers: list[shares.ShareValue] | None = None
        self._excl: dict[str, dict[str, int]] = {}

    def _all(self, concept: str | Concept, ptype: str) -> tuple[AsOfPoint, ...]:
        key = (concept if isinstance(concept, str) else concept.name, ptype)
        if key not in self._pts:
            res = facts_as_of(self.engine, self.cik, concept, self.as_of, ptype=ptype)
            self._pts[key] = res.points
            self._excl[key[0]] = res.excluded
        return self._pts[key]

    def excluded(self, concept: str) -> dict[str, int]:
        """Fact rows `facts_as_of` left out for a concept (shell documents, other forms)."""
        return {k: n for k, n in self._excl.get(concept, {}).items()
                if k != "filed after as-of date"}  # fmt: skip

    def view(self, day: str, *, first: bool = False) -> Points:
        def points(concept: str | Concept, ptype: str) -> dict[str, AsOfPoint]:
            out = {}
            for p in self._all(concept, ptype):
                if p.first_filed > day:
                    continue
                if first:
                    p = replace(
                        p, value=p.first_value, accession=p.first_accession, filed=p.first_filed
                    )
                out[p.end] = p
            return out

        return points

    # --- splits and shares ----------------------------------------------------------------

    def splits(self) -> list[tuple[str, float]]:
        if self._splits is None:
            syms = shares.price_symbols(self.engine, self.cik)
            seen: dict[str, float] = {}
            if syms:
                marks = ",".join("?" * len(syms))
                for r in self.engine.execute(
                    f"SELECT date, split_factor FROM price_bar WHERE symbol IN ({marks}) AND "
                    "split_factor IS NOT NULL AND split_factor != 1 ORDER BY date",
                    syms,
                ):
                    seen.setdefault(r["date"], float(r["split_factor"]))
            self._splits = sorted(seen.items())
        return self._splits

    def factor(self, after: str, upto: str | None = None) -> tuple[float, list[str]]:
        """Product of split factors on dates in (after, upto]; upto None = every later one."""
        f, seen = 1.0, []
        for d, x in self.splits():
            if d > after and (upto is None or d <= upto):
                f *= x
                seen.append(f"{d} ×{x:g}")
        return f, seen

    def covers(self) -> list[shares.ShareValue]:
        if self._covers is None:
            self._covers = [
                v for v in shares.cover_counts(self.engine, self.cik) if v.value is not None
            ]
        return self._covers


@dataclass
class Close:
    value: float
    day: str
    symbol: str


def close_at(engine: sqlite3.Connection, cik: str, day: str, tol: int = TOLERANCE) -> Close | None:
    """Raw close on `day` or the last bar up to `tol` days before (as `shares.close_on`), with
    the symbol it came from (dividends are read from the same symbol)."""
    syms = shares.price_symbols(engine, cik)
    if not syms:
        return None
    marks = ",".join("?" * len(syms))
    lo = (date.fromisoformat(day) - timedelta(days=tol)).isoformat()
    r = engine.execute(
        f"SELECT close, date, symbol FROM price_bar WHERE symbol IN ({marks}) AND date <= ? AND "
        "date >= ? AND close IS NOT NULL ORDER BY date DESC, symbol LIMIT 1",
        (*syms, day, lo),
    ).fetchone()
    return Close(float(r["close"]), r["date"], r["symbol"]) if r else None


def latest_close_day(engine: sqlite3.Connection, cik: str, upto: str) -> str | None:
    syms = shares.price_symbols(engine, cik)
    if not syms:
        return None
    marks = ",".join("?" * len(syms))
    r = engine.execute(
        f"SELECT max(date) FROM price_bar WHERE symbol IN ({marks}) AND date <= ? AND close IS "
        "NOT NULL",
        (*syms, upto),
    ).fetchone()
    return r[0] if r and r[0] else None


@dataclass
class Cap:
    value: float | None
    text: str
    count: float | None = None  # shares at the close date's share basis
    sources: list[Source] | None = None
    missing: str = ""


def market_cap(k: Known, day: str, close: Close) -> Cap:
    """Cover count first filed on or before `day` × raw close, split-scaled from the cover date
    to the close (rule 1). No cover count: `distress.share_fallback` (labelled, D-M04-82)."""
    covers = [v for v in k.covers() if (v.first_filed or v.date) <= day and v.date <= day]
    if covers:
        v = max(covers, key=lambda x: (x.date, x.accession))
        to_today, _ = k.factor(v.date)
        raw = float(v.value) / to_today  # cover_counts scaled it to today
        f, seen = k.factor(v.date, close.day)
        count = raw * f
        what = f"cover shares {raw:,.0f} ({v.date}, {v.tag or 'cover'})"
        acc, filed = v.accession, v.first_filed or v.date
    else:
        fb = distress.share_fallback(k.engine, k.cik, day)
        if fb is None:
            return Cap(
                None, "", missing="no cover share count, period-end or weighted-average count"
            )
        n, label, end, acc, filed = fb
        to_today, _ = k.factor(end)
        f, seen = k.factor(end, close.day)
        count = n / to_today * f
        what = f"{label} {n / to_today:,.0f} ({end})"
    split = f" × splits {f:g} ({', '.join(seen)})" if seen else ""
    mv = count * close.value
    text = (
        f"market cap {mv / 1e6:,.0f}M = {what}{split} × close ${close.value:,.2f} "
        f"({close.symbol} {close.day})"
    )
    srcs = [
        Source(acc, filed, "A", "shares"),
        Source(f"close {close.day}", close.day, "A", f"Tiingo close {close.symbol}"),
    ]
    return Cap(mv, text, count, srcs)


@dataclass
class Dividends:
    per_share: float | None
    text: str
    missing: str = ""


def dividends(engine: sqlite3.Connection, k: Known, close: Close) -> Dividends:
    """TTM cash dividends per share (Tiingo `div_cash` on ex-dates in the 365 days to the
    close), each scaled to the close's share basis by the splits after its ex-date. Zero only
    when the symbol's stored bars cover the whole year; fewer bars → missing."""
    lo = (date.fromisoformat(close.day) - timedelta(days=365)).isoformat()
    first = engine.execute(
        "SELECT min(date) FROM price_bar WHERE symbol = ? AND close IS NOT NULL", (close.symbol,)
    ).fetchone()[0]
    if first is None or first > (date.fromisoformat(lo) + timedelta(days=TOLERANCE)).isoformat():
        return Dividends(
            None, "", f"fewer than 12 months of stored bars ({close.symbol} from {first or 'none'})"
        )
    rows = engine.execute(
        "SELECT date, div_cash FROM price_bar WHERE symbol = ? AND date > ? AND date <= ? "
        "ORDER BY date",
        (close.symbol, lo, close.day),
    ).fetchall()
    if len(rows) < MIN_YEAR_BARS:  # a year has about 250 sessions; gaps hide ex-dates
        return Dividends(None, "", f"fewer than 12 months of stored bars ({len(rows)} sessions "
                         f"in the 365 days to {close.day}, needs {MIN_YEAR_BARS})")  # fmt: skip
    if all(r["div_cash"] is None for r in rows):
        return Dividends(None, "", "dividends not stored for these bars (div_cash empty)")
    total, parts = 0.0, []
    for r in rows:
        d = float(r["div_cash"] or 0.0)
        if d:
            f, _ = k.factor(r["date"], close.day)
            total += d / f
            parts.append(f"{r['date']} ${d:g}" + (f" ÷ {f:g} (split)" if f != 1.0 else ""))
    if not parts:
        return Dividends(0.0, f"no dividend in the 12 months to {close.day} ({close.symbol})")
    return Dividends(total, f"TTM dividends ${total:,.4f}/share: " + ", ".join(parts))
