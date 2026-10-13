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

Foreign filers' 6-Ks carry no item code (`foreign_report`). A 6-K whose stored exhibit is an
earnings release counts as an earnings event (M09 Part 2, coordinator decision on open item
2, D-M09-16): an EX-99 / EX-99.1 / EX-99.01 document in corpus.db whose file name or
filing-index description says earnings or results, or whose heading (the first 400
characters of its text) reads as a results release ("… Reports Third Quarter 2025 Financial
Results"); a notice of a coming release ("to announce … results on …") or meeting results
do not count, even when the file name says results. Other 6-Ks — and every 6-K when no
corpus is passed or no exhibit is stored — are listed separately so a caller can say "6-K in
the window (not classified)".
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import time

from engine.sec.identity import normalize_cik

CLOSE = time(16, 0)
RELEASE_TYPES = ("EX-99", "EX-99.1", "EX-99.01")
HEAD_CHARS = 400
_NAMED = re.compile(r"earn|result", re.I)
_TITLED = (
    re.compile(
        r"\b(reports?|reported|announces?|announced|posts?|delivers?)\b[^\n]{0,120}?"
        r"\b(results|earnings)\b",
        re.I,
    ),  # fmt: skip
    re.compile(
        r"\b(quarter(ly)?|half[- ]year(ly)?|full[- ]year|annual|fiscal|interim|"
        r"first|second|third|fourth|q[1-4])\b[^\n]{0,60}?\b(financial |operating )?"
        r"(results|earnings)\b",
        re.I,
    ),  # fmt: skip
    re.compile(r"\b(earnings release|financial results)\b", re.I),
)
_NOTICE = re.compile(  # in the heading up to the match: a coming release
    r"\b(to|will)\s+(announce|report|release|host|publish|present)\b|\bconference call (date|"
    r"schedule)\b",
    re.I,
)
_MEETING = re.compile(  # right after the match: meeting or vote results
    r"\bresults of (the )?(annual|extraordinary|general|special)?\s*(general )?(meeting|vote|"
    r"voting|tender|offer|election)",
    re.I,
)


def results_exhibit(corpus: sqlite3.Connection | None, accession: str) -> str | None:
    """The stored EX-99 of a 6-K that is an earnings release, described for `method`
    ('EX-99.1 gfs-ex991.htm "GlobalFoundries Reports Third Quarter 2025 Financial Results"');
    None when no such exhibit is stored."""
    if corpus is None:
        return None
    marks = ",".join("?" * len(RELEASE_TYPES))
    rows = corpus.execute(
        f"SELECT doc_type, filename, description, substr(text, 1, {HEAD_CHARS * 2}) FROM "
        f"document WHERE accession = ? AND upper(doc_type) IN ({marks}) "
        "ORDER BY doc_type, filename",
        (accession, *RELEASE_TYPES),
    ).fetchall()
    for doc_type, filename, description, text in rows:
        head = " ".join((text or "").split())[:HEAD_CHARS]
        titled = next((m for rx in _TITLED if (m := rx.search(head))), None)
        if titled is not None and (
            _NOTICE.search(head[: titled.end()])
            or _MEETING.search(head[titled.start() : titled.end() + 60])
        ):
            continue  # a notice of a coming release, or meeting / vote results  # fmt: skip
        named = f"{filename or ''} {description or ''}"
        if titled is None and (not _NAMED.search(named) or _NOTICE.search(named)
                               or _MEETING.search(named)):  # fmt: skip
            continue
        if titled is not None:
            line = head[max(0, titled.start() - 80) : titled.end() + 20].strip()
            return f'{doc_type} {filename} "{line}"'
        return f"{doc_type} {filename} (named: {named.strip()})"
    return None


@dataclass(frozen=True)
class Catalyst:
    accession: str
    item: str
    form: str
    filed: str
    accepted_at: str | None
    title: str
    exhibit: str = ""  # a 6-K's earnings-release exhibit (D-M09-16)

    @property
    def after_close(self) -> bool:
        t = accepted_clock(self.accepted_at)
        return t is not None and t >= CLOSE and self.accepted_at[:10] == self.filed

    def in_window(self, start: str, end: str) -> bool:
        if self.after_close:
            return start <= self.filed < end
        return start < self.filed <= end

    @property
    def what(self) -> str:
        """Short label for a source line: "8-K item 2.02" or "6-K earnings release"."""
        return f"{self.form} earnings release" if self.exhibit else f"{self.form} item {self.item}"

    def text(self) -> str:
        when = f" {self.accepted_at[11:16]} ET" if accepted_clock(self.accepted_at) else ""
        after = " (after the close: counts from the next session)" if self.after_close else ""
        if self.exhibit:
            return (f"{self.form} {self.accession} filed {self.filed}{when}{after}, earnings-"
                    f"release exhibit {self.exhibit}")  # fmt: skip
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


def _foreign(engine: sqlite3.Connection, cik: str, start: str, end: str, corpus) -> list[Catalyst]:
    out = []
    for r in _rows(engine, cik, start, end, "foreign_report"):
        c = Catalyst(r[0], r[1], r[2], r[3], r[4], r[5], results_exhibit(corpus, r[0]) or "")
        if c.in_window(start, end):
            out.append(c)
    return out


def earnings_in_window(
    engine: sqlite3.Connection,
    cik: str,
    start: str,
    end: str,
    corpus: sqlite3.Connection | None = None,
) -> list[Catalyst]:
    """Earnings 8-Ks — and, with `corpus`, 6-Ks carrying an earnings-release exhibit — whose
    first reachable session lies in (start, end] (one per filing, filing order)."""
    seen: set[str] = set()
    out: list[Catalyst] = []
    for r in _rows(engine, cik, start, end, "earnings"):
        c = Catalyst(r[0], r[1], r[2], r[3], r[4], r[5])
        if c.accession in seen or not c.in_window(start, end):
            continue
        seen.add(c.accession)
        out.append(c)
    out += [c for c in _foreign(engine, cik, start, end, corpus) if c.exhibit]
    return sorted(out, key=lambda c: (c.filed, c.accepted_at or "", c.accession))


def foreign_reports_in_window(
    engine: sqlite3.Connection,
    cik: str,
    start: str,
    end: str,
    corpus: sqlite3.Connection | None = None,
) -> list[Catalyst]:
    """6-K current reports in the window that are not earnings releases (unclassified: may
    or may not be results; every 6-K when no corpus is passed)."""
    return [c for c in _foreign(engine, cik, start, end, corpus) if not c.exhibit]
