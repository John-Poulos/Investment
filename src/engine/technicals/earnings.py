"""Earnings 8-Ks inside a price window (M09 rule 7; shared with M10 and M12, MVP_PLAN item 3).

An earnings 8-K (`event.category = 'earnings'`: Item 2.02, so Tesla's deliveries report counts
too, D-M02-23) moves the price from the first session it can reach:

- accepted before 16:00 US Eastern (or no acceptance time stored) → its filing date;
- accepted at or after 16:00 (after the close) → the next session.

A window runs from one weekly close to a later one: (start, end]. An event counts when that
first session falls inside: filed in (start, end] during the day, or filed in [start, end)
after the close (an after-close filing on the window's last day moves next week's price).

EDGAR's `acceptanceDateTime` (submissions JSON) carries the Eastern clock time with a "Z"
suffix (e.g. 16:05:12 for a release after the 16:00 close); the clock time is read as US
Eastern (D-M09-9).

Foreign filers' 6-Ks carry no item code (`foreign_report`); they are listed separately so a
caller can say "6-K in the window (not classified)".
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import time

from engine.sec.identity import normalize_cik

CLOSE = time(16, 0)


@dataclass(frozen=True)
class Catalyst:
    accession: str
    item: str
    form: str
    filed: str
    accepted_at: str | None
    title: str

    @property
    def after_close(self) -> bool:
        t = accepted_clock(self.accepted_at)
        return t is not None and t >= CLOSE and self.accepted_at[:10] == self.filed

    def in_window(self, start: str, end: str) -> bool:
        if self.after_close:
            return start <= self.filed < end
        return start < self.filed <= end

    def text(self) -> str:
        when = f" {self.accepted_at[11:16]} ET" if accepted_clock(self.accepted_at) else ""
        after = " (after the close: counts from the next session)" if self.after_close else ""
        return f"{self.form} item {self.item} {self.accession} filed {self.filed}{when}{after}"


def accepted_clock(accepted_at: str | None) -> time | None:
    """The clock time of an EDGAR acceptance stamp ("2026-08-05T16:05:12.000Z"), read as US
    Eastern; None when absent or unreadable."""
    if not accepted_at or len(accepted_at) < 16 or accepted_at[10] not in "T ":
        return None
    try:
        return time(int(accepted_at[11:13]), int(accepted_at[14:16]))
    except ValueError:
        return None


def _rows(engine: sqlite3.Connection, cik: str, start: str, end: str, category: str):
    # one day either side: the after-close shift and the window edges are applied in Python
    return engine.execute(
        "SELECT accession, item, form, filed, accepted_at, title FROM event WHERE cik = ? "
        "AND category = ? AND filed >= ? AND filed <= ? ORDER BY filed, accepted_at, accession",
        (normalize_cik(cik) or cik, category, start, end),
    ).fetchall()


def earnings_in_window(
    engine: sqlite3.Connection, cik: str, start: str, end: str
) -> list[Catalyst]:
    """Earnings 8-Ks whose first reachable session lies in (start, end] (one per filing)."""
    seen: set[str] = set()
    out: list[Catalyst] = []
    for r in _rows(engine, cik, start, end, "earnings"):
        c = Catalyst(r[0], r[1], r[2], r[3], r[4], r[5])
        if c.accession in seen or not c.in_window(start, end):
            continue
        seen.add(c.accession)
        out.append(c)
    return out


def foreign_reports_in_window(
    engine: sqlite3.Connection, cik: str, start: str, end: str
) -> list[Catalyst]:
    """6-K current reports in the window (unclassified: may or may not be results)."""
    return [
        c
        for r in _rows(engine, cik, start, end, "foreign_report")
        if (c := Catalyst(r[0], r[1], r[2], r[3], r[4], r[5])).in_window(start, end)
    ]
