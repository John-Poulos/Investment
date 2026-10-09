"""Watch tiers below the core watchlist (M02 D-M02-4, D-M02-11).

- core: `config/watchlist.toml`, hand-edited by the owner; never stored here.
- promoted: full watchlist jobs (Form 4s, documents, alerts), stored in `tier_member`.
- tracked: filing index + XBRL facts only (a few SEC requests per filing).

Removing a member keeps its row (status 'removed') with who and when. A tracked name
with no new theme evidence for 12 months gets a "still track?" review item; nothing
is removed automatically.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from engine.sec.client import iso

STILL_TRACK_AFTER = timedelta(days=365)


class TierError(ValueError):
    """The tier change cannot be applied."""


@dataclass(frozen=True)
class Member:
    cik: str
    ticker: str
    tier: str
    theme_key: str | None
    reason: str | None
    added_at: str
    last_evidence_at: str


def members(engine: sqlite3.Connection, tier: str | None = None) -> list[Member]:
    sql = "SELECT * FROM tier_member WHERE status = 'active'"
    params: tuple = ()
    if tier:
        sql += " AND tier = ?"
        params = (tier,)
    return [
        Member(r["cik"], r["ticker"], r["tier"], r["theme_key"], r["reason"], r["added_at"],
               r["last_evidence_at"])
        for r in engine.execute(sql + " ORDER BY ticker", params)
    ]  # fmt: skip


def member(engine: sqlite3.Connection, cik: str) -> Member | None:
    return next((m for m in members(engine) if m.cik == cik), None)


def add_tracked(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str,
    *,
    reason: str,
    theme_key: str | None,
    by: str,
    now: datetime,
    core: set[str] = frozenset(),
) -> None:
    """Track a company (accepted candidate or owner action). Core names are refused."""
    if cik in core:
        raise TierError(f"{ticker} is on the core watchlist (config/watchlist.toml).")
    ts = iso(now)
    engine.execute(
        "INSERT INTO tier_member (cik, ticker, tier, status, theme_key, reason, added_at, "
        "added_by, changed_at, changed_by, last_evidence_at) VALUES "
        "(?, ?, 'tracked', 'active', ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (cik) DO UPDATE SET "
        "status = 'active', ticker = excluded.ticker, theme_key = coalesce(excluded.theme_key, "
        "tier_member.theme_key), reason = excluded.reason, changed_at = excluded.changed_at, "
        "changed_by = excluded.changed_by, last_evidence_at = excluded.last_evidence_at",
        (cik, ticker.upper(), theme_key, reason, ts, by, ts, by, ts),
    )


def _change(engine: sqlite3.Connection, cik: str, sets: str, by: str, now: datetime) -> None:
    cur = engine.execute(
        f"UPDATE tier_member SET {sets}, changed_at = ?, changed_by = ? "
        "WHERE cik = ? AND status = 'active'",
        (iso(now), by, cik),
    )
    if cur.rowcount == 0:
        raise TierError("That company is not tracked or promoted.")


def promote(engine: sqlite3.Connection, cik: str, by: str, now: datetime) -> None:
    _change(engine, cik, "tier = 'promoted'", by, now)


def demote(engine: sqlite3.Connection, cik: str, by: str, now: datetime) -> None:
    _change(engine, cik, "tier = 'tracked'", by, now)


def remove(engine: sqlite3.Connection, cik: str, by: str, now: datetime) -> None:
    _change(engine, cik, "status = 'removed'", by, now)


def touch_evidence(engine: sqlite3.Connection, cik: str, now: datetime) -> None:
    """New theme evidence (or the owner chose to keep tracking): restart the clock."""
    engine.execute("UPDATE tier_member SET last_evidence_at = ? WHERE cik = ?", (iso(now), cik))


def stale_tracked(engine: sqlite3.Connection, now: datetime) -> list[Member]:
    cutoff = iso(now - STILL_TRACK_AFTER)
    return [m for m in members(engine, "tracked") if m.last_evidence_at < cutoff]
