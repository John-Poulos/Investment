"""Fiscal labels → reported XBRL points, per tag (D-M02-28 (3), D-M02-29).

Guidance and stated actuals carry the company's own labels (FY2026, FY2026 Q2, CY2026);
XBRL points carry dates. A label is matched to the point of the same type whose end lies
within ten days of the label's end (52/53-week years end a few days off the month end).
Calendar-year labels for a company whose fiscal year is not the calendar year (today only
Microsoft) are the sum of the four quarters ending in that calendar year — "not comparable
yet" until all four exist (D-M02-28 (3)).
"""

from __future__ import annotations

import calendar
import re
import sqlite3
from dataclasses import dataclass
from datetime import date

from engine.calls.transcripts import _fye
from engine.sec.xbrl_facts import Concept, ConceptResult, Point, build_concept

TOLERANCE_DAYS = 10
_LABEL = re.compile(r"(?P<cy>CY|FY)(?P<y>\d{4})(?: Q(?P<q>[1-4]))?")


@dataclass(frozen=True)
class Span:
    label: str
    ptype: str  # Q | FY | TTM | CY (CY = calendar year summed from quarters)
    end: date


def fiscal_year_end(engine: sqlite3.Connection, cik: str) -> str | None:
    row = engine.execute("SELECT fiscal_year_end FROM entity WHERE cik = ?", (cik,)).fetchone()
    return row[0] if row else None


def calendar_fiscal(fye: str | None) -> bool:
    f = _fye(fye)
    return f is not None and f[0] == 12


def _month_end(year: int, month: int, day: int) -> date:
    """`day` of the month; 31 means the month's last day (June 30 → Dec 31, not Dec 30)."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def span_of(label: str, fye: str | None) -> Span | None:
    """The period a label names; CY on a calendar-year company is its fiscal year."""
    m = _LABEL.fullmatch(label)
    if not m:
        return None  # "FY2026 remaining" and other spans are not matched to actuals
    year, q = int(m["y"]), m["q"]
    if m["cy"] == "CY":
        if q:
            return Span(
                label, "Q", date(year, int(q) * 3, calendar.monthrange(year, int(q) * 3)[1])
            )
        return Span(label, "FY" if calendar_fiscal(fye) else "CY", date(year, 12, 31))
    f = _fye(fye)
    if f is None:
        return None
    month, day = f
    if day >= calendar.monthrange(2001, month)[1]:  # a month-end year end (0630, 1231)
        day = 31
    if q is None:
        return Span(label, "FY", _month_end(year, month, day))
    back = 3 * (4 - int(q))
    total = year * 12 + (month - 1) - back
    y, mo = divmod(total, 12)
    return Span(label, "Q", _month_end(y, mo + 1, day))


def tag_points(
    engine: sqlite3.Connection, cik: str, taxonomy: str, tag: str
) -> ConceptResult | None:
    """Series points (Q, FY, TTM; derived Q4) for one tag, like any concept."""
    concept = Concept(f"{taxonomy}:{tag}", ((taxonomy, tag),), "currency", "flow")
    return build_concept(engine, cik, concept)


def _near(a: str, b: date) -> bool:
    return abs((date.fromisoformat(a) - b).days) <= TOLERANCE_DAYS


def point_at(points: tuple[Point, ...] | list[Point], ptype: str, end: date) -> Point | None:
    for p in points:
        if p.ptype == ptype and _near(p.end, end):
            return p
    return None


@dataclass(frozen=True)
class Found:
    value: float
    end: str
    accession: str
    how: str  # "reported", "derived …", "sum of calendar quarters …"


def value_for(points: tuple[Point, ...] | list[Point], span: Span) -> Found | None:
    """The latest reported value for a span; CY = four quarters ending in that year."""
    if span.ptype in ("Q", "FY", "TTM"):
        p = point_at(points, span.ptype, span.end)
        return Found(p.latest.value, p.end, p.latest.accession, p.method) if p else None
    quarters = _calendar_quarters(points, span.end.year)
    if len(quarters) != 4:
        return None
    return Found(
        sum(q.latest.value for q in quarters),
        quarters[-1].end,
        quarters[-1].latest.accession,
        "sum of calendar quarters ending " + ", ".join(q.end for q in quarters),
    )


def _calendar_quarters(points: tuple[Point, ...] | list[Point], year: int) -> list[Point]:
    """Quarters ending near Mar 31 / Jun 30 / Sep 30 / Dec 31 of the year, oldest first.
    A company whose quarters end elsewhere (NVIDIA: Apr/Jul/Oct/Jan) has none."""
    ends = [date(year, m, calendar.monthrange(year, m)[1]) for m in (3, 6, 9, 12)]
    out = {}
    for p in points:
        if p.ptype != "Q":
            continue
        for e in ends:
            if _near(p.end, e):
                out[e] = p
    return [out[e] for e in sorted(out)]


def calendar_quarters_present(points: tuple[Point, ...] | list[Point], year: int) -> int:
    return len(_calendar_quarters(points, year))
