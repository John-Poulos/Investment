"""Owner-entered market share for the CvD Q2 share row (D-M04-68, -105; DS16; M04 Part 8a).

No filing states a company's market share, so the owner enters it from a third-party
source (grade B) or computes it from an industry total a filing states (grade A, the
filing named in the source; D-M04-9). The M04 tab's "Add market share" form writes
`market_share`; wrong rows are withdrawn, never deleted.

Q2 reading (D-M04-68): the latest active entry against an entry of the same market about
4 quarters earlier (300–430 days; the one nearest 365 days) → change in pp. "Weakening" =
down ≥ 1 pp† in a flat or growing market. Market size is optional: with both sizes
entered, a market down more than 2%† is "shrinking" and a share loss there reads neutral;
without them the market is read as flat (the stricter reading, D-M04-105). No pair →
"missing: no share data" (or the one-entry reason), never intact.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime

from engine.sec.client import iso
from engine.sec.identity import normalize_cik
from engine.signals import Source

FALL_PP = 1.0  # D-M04-68 starting value
SHRINK = 0.02  # market down more than 2%† = shrinking (D-M04-105)
PAIR_DAYS = (300, 430)
NO_DATA = "no share data"


class ShareError(ValueError):
    """The entry breaks a rule (share range, dates, source)."""


@dataclass
class ShareReading:
    reading: str  # intact | weakening | neutral | missing
    change_pp: float | None
    text: str
    grade: str | None = None
    sources: list[Source] = field(default_factory=list)
    as_of: str = ""


def _d(s: str, what: str) -> str:
    try:
        return date.fromisoformat(s.strip()).isoformat()
    except ValueError as e:
        raise ShareError(f"{what}: use YYYY-MM-DD") from e


def add(
    engine: sqlite3.Connection,
    cik: str,
    period_end: str,
    share_pct: str | float,
    market: str,
    source: str,
    *,
    by: str,
    now: datetime,
    market_size: str | float | None = None,
    url: str = "",
    filing_total: bool = False,
    note: str = "",
) -> int:
    """Store one entry (caller owns the transaction). Grade A only for a share computed from
    an industry total stated in a filing (the filing named in `source`)."""
    norm = normalize_cik(cik)
    if norm is None:
        raise ShareError("unknown company")
    try:
        pct = float(str(share_pct).strip().rstrip("%"))
    except ValueError as e:
        raise ShareError("share: a number in percent, e.g. 23.5") from e
    if not 0 <= pct <= 100:
        raise ShareError("share must lie between 0 and 100 percent")
    size = None
    if market_size not in (None, ""):
        try:
            size = float(str(market_size).replace(",", ""))
        except ValueError as e:
            raise ShareError("market size: a number in USD (optional)") from e
        if size <= 0:
            raise ShareError("market size must be above 0")
    if not market.strip():
        raise ShareError("name the market (e.g. 'DRAM revenue')")
    if not source.strip():
        raise ShareError("name the source (publisher and report, or the filing)")
    day = _d(period_end, "period")
    if day > now.date().isoformat():
        raise ShareError("the period lies in the future")
    return engine.execute(
        "INSERT INTO market_share (cik, period_end, share_pct, market, market_size, source, "
        "source_url, grade, status, note, entered_by, entered_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
        (
            norm,
            day,
            pct,
            market.strip(),
            size,
            source.strip(),
            url.strip() or None,
            "A" if filing_total else "B",
            note.strip() or None,
            by,
            iso(now),
        ),
    ).lastrowid


def withdraw(engine: sqlite3.Connection, share_id: int, cik: str, by: str, now: datetime) -> bool:
    cur = engine.execute(
        "UPDATE market_share SET status = 'withdrawn', withdrawn_by = ?, withdrawn_at = ? "
        "WHERE share_id = ? AND cik = ? AND status = 'active'",
        (by, iso(now), share_id, normalize_cik(cik) or cik),
    )
    return cur.rowcount == 1


def entries(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT * FROM market_share WHERE cik = ? ORDER BY market, period_end DESC, share_id DESC",
        (normalize_cik(cik) or cik,),
    ).fetchall()


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def reading(engine: sqlite3.Connection, cik: str, as_of: str) -> ShareReading:
    rows = [r for r in entries(engine, cik) if r["status"] == "active" and r["period_end"] <= as_of]
    if not rows:
        return ShareReading("missing", None, NO_DATA)
    latest = max(rows, key=lambda r: (r["period_end"], r["share_id"]))
    same = [
        r
        for r in rows
        if r["market"] == latest["market"]
        and PAIR_DAYS[0] <= _days(latest["period_end"], r["period_end"]) <= PAIR_DAYS[1]
    ]
    if not same:
        return ShareReading(
            "missing",
            None,
            f"{NO_DATA} about 4 quarters before the "
            f"{latest['period_end']} entry ({latest['market']}: "
            f"{latest['share_pct']:.1f}%); needs a pair 300–430 days apart",
        )
    early = min(same, key=lambda r: abs(_days(latest["period_end"], r["period_end"]) - 365))
    chg = float(latest["share_pct"]) - float(early["share_pct"])
    grade = "B" if "B" in (latest["grade"], early["grade"]) else "A"
    srcs = [
        Source(
            f"market_share:{r['share_id']}",
            r["period_end"],
            r["grade"],
            f"{r['market']} {r['share_pct']:.1f}% ({r['source']})",
        )
        for r in (latest, early)
    ]
    base = (
        f"{latest['market']}: {early['share_pct']:.1f}% ({early['period_end']}) → "
        f"{latest['share_pct']:.1f}% ({latest['period_end']}) = {chg:+.1f} pp; grade {grade}"
    )
    if latest["market_size"] and early["market_size"]:
        mkt = float(latest["market_size"]) / float(early["market_size"]) - 1
        market = f"market {mkt:+.1%}"
        shrinking = mkt < -SHRINK
    else:
        market, shrinking = "market size not entered: read as flat (D-M04-105)", False
    if chg <= -FALL_PP and shrinking:
        return ShareReading(
            "neutral",
            chg,
            f"{base}; {market}: share down in a shrinking "
            "market (D-M04-68 needs a flat or growing one)",
            grade,
            srcs,
            latest["period_end"],
        )
    if chg <= -FALL_PP:
        return ShareReading(
            "weakening",
            chg,
            f"{base}; {market}: down ≥ {FALL_PP:.0f} pp† over 4 quarters (D-M04-68)",
            grade,
            srcs,
            latest["period_end"],
        )
    return ShareReading(
        "intact",
        chg,
        f"{base}; {market}: not down ≥ {FALL_PP:.0f} pp",
        grade,
        srcs,
        latest["period_end"],
    )
