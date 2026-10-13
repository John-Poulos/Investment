"""Capex guidance as money flow, per spender and guided period (D-M02-5, -28, -30).

Latest statement per period, any grade, with its source label (D-M02-28 (1)): the newest
row wins; on the same day a release beats a call, and an owner correction beats both.
Growth vs the last reported year (or the same quarter a year earlier) uses the actual on
the company's own definition, recipe chosen by the row's clause (D-M02-29):
- range → growth at the midpoint, low–high growth beside it;
- approximate / point / ± → as stated;
- floor ("more than $25B") → "≥ +X%", ranked at its minimum;
- ceiling ("up to") and direction-only rows → listed below the ranking, not ranked;
- calendar-basis guidance of a non-calendar company (Microsoft) → summed calendar
  quarters, "not comparable yet" until all four exist (D-M02-28 (3)).

Freshness (D-M02-30), from the company's latest earnings event (original 8-K Item 2.02):
restated · not restated · call not stored yet · call unavailable — not checked · latest
results not read yet · no capex guidance given; an explicit refusal ("we aren't
providing a 2027 capex outlook") reads "company gives no outlook yet". A guided period
that has ended moves to guided-vs-actual.
Labelled "hypothesis, not backtested"; guidance is a forecast, not a commitment.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date

from engine.guidance.changes import changes_for
from engine.guidance.parse import CAPEX_WORDS, find_periods
from engine.guidance.sources import stated_prefix
from engine.moneyflow.actuals import Actual, Book, actual_for
from engine.moneyflow.periods import calendar_quarters_present, span_of
from engine.moneyflow.stated import stated_for

CALL_WAIT_DAYS = 30
NO_OUTLOOK = "says no guidance is given"


@dataclass(frozen=True)
class Freshness:
    state: str
    why: str


@dataclass(frozen=True)
class GuidedLine:
    cik: str
    period: str
    kind: str  # range | approx | point | plusminus | direction
    bound: str | None
    low: float | None
    high: float | None
    direction: str | None
    clause: str | None
    origin: str
    grade: str
    source: str  # sentence | table | owner
    quote: str
    accession: str
    filename: str
    stated_on: str
    change: str | None  # raised / lowered / narrowed … vs the previous statement
    base: Actual | None  # last year's actual, own definition
    growth_low: float | None
    growth_high: float | None
    growth_mid: float | None
    comparable: str | None  # why growth is missing ("not comparable yet (2/4 …)")
    freshness: Freshness
    ended: bool
    actual: Actual | None  # after the period ends: guided vs actual

    @property
    def ranked(self) -> bool:
        return self.kind != "direction" and self.bound != "ceiling" and self.growth_low is not None

    @property
    def rank_value(self) -> float:
        """Floors rank at their minimum; others at the midpoint (never overstates)."""
        if self.bound == "floor":
            return self.growth_low or 0.0
        return self.growth_mid if self.growth_mid is not None else (self.growth_low or 0.0)

    @property
    def value_text(self) -> str:
        if self.kind == "direction":
            arrow = {"up": "↑", "down": "↓", "flat": "→"}.get(self.direction or "", "?")
            return f"{arrow} no figure"
        lo, hi = _b(self.low), _b(self.high)
        if self.low == self.high:
            return f"{stated_prefix(self.kind, self.bound)}{lo}"
        return f"{lo}–{hi}"

    @property
    def growth_text(self) -> str:
        if self.kind == "direction":
            return "not ranked (direction only)"
        if self.bound == "ceiling":
            return "not ranked (ceiling)"
        if self.growth_low is None:
            return self.comparable or "no base year"
        if self.bound == "floor":
            return f"≥ {self.growth_low:+.0%} (ranked at minimum)"
        if self.growth_low == self.growth_high:
            return f"{self.growth_low:+.0%}"
        return f"{self.growth_mid:+.0%} ({self.growth_low:+.0%}…{self.growth_high:+.0%})"

    @property
    def source_text(self) -> str:
        if self.origin == "call":
            return f"call · oral · {self.grade}"
        if self.origin == "ir":
            return "IR document · A"
        return f"release · {self.grade}"


def _b(x: float | None) -> str:
    if x is None:
        return "—"
    return f"${x / 1e9:,.1f}B" if abs(x) >= 1e9 else f"${x / 1e6:,.0f}M"


def _prev_label(label: str) -> str | None:
    m = re.fullmatch(r"(CY|FY)(\d{4})( Q[1-4])?", label)
    return f"{m[1]}{int(m[2]) - 1}{m[3] or ''}" if m else None


def latest_rows(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    """The latest capex statement per guided period."""
    rows = engine.execute(
        "SELECT * FROM guidance WHERE cik = ? AND metric = 'capex' AND flag IS NULL "
        "AND (unit = 'USD' OR kind = 'direction') "
        "ORDER BY period, stated_on DESC, source = 'owner' DESC, origin = 'release' DESC, "
        "kind = 'direction', guidance_id DESC",
        (cik,),
    ).fetchall()
    best: dict[str, sqlite3.Row] = {}
    for r in rows:
        best.setdefault(r["period"], r)
    return list(best.values())


# --- Freshness ---------------------------------------------------------------------


RESULTS_MIN_DAYS = 10  # results never come this soon after quarter end (D-M02-23)


def _latest_event(engine: sqlite3.Connection, cik: str) -> sqlite3.Row | None:
    """The latest earnings results 8-K (Item 2.02). One filed within 10 days of a quarter
    end is an operating update, not results (Tesla files deliveries under Item 2.02)."""
    from engine.calls.transcripts import last_quarter
    from engine.moneyflow.periods import fiscal_year_end

    fye = fiscal_year_end(engine, cik)
    for r in engine.execute(
        "SELECT accession, filed, items FROM filing WHERE cik = ? AND form = '8-K' "
        "ORDER BY filed DESC LIMIT 20",
        (cik,),
    ):
        if not (r["items"] and "2.02" in r["items"].split(",")):
            continue
        filed = date.fromisoformat(r["filed"][:10])
        last = last_quarter(filed, fye)
        if last is not None and (filed - last[2]).days < RESULTS_MIN_DAYS:
            continue
        return r
    return None


def _states_capex(
    engine: sqlite3.Connection, accession: str, period: str, metric: str = "capex"
) -> bool:
    """The document states guidance for this metric (capex by default) and period."""
    return (
        engine.execute(
            "SELECT 1 FROM guidance WHERE accession = ? AND metric = ? AND period = ? LIMIT 1",
            (accession, metric, period),
        ).fetchone()
        is not None
    )


def _refused(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    accessions: list[str],
    period: str,
    anchor: tuple[int, int] | None,
    metric: str = "capex",
) -> bool:
    """An explicit "no outlook" sentence for this period in these documents: for capex it
    must name capex; for another metric family it must not be a capex refusal (M04 Part 1b:
    "we are not providing full-year guidance" counts for revenue, "no 2027 capex outlook"
    does not)."""
    if corpus is None or not accessions:
        return False
    marks = ",".join("?" * len(accessions))
    for s in engine.execute(
        f"SELECT accession, filename, start_offset, end_offset FROM guidance_skip "
        f"WHERE accession IN ({marks}) AND reason = ?",
        (*accessions, NO_OUTLOOK),
    ):
        row = corpus.execute(
            "SELECT substr(text, ? + 1, ? - ?) FROM document WHERE accession = ? AND filename = ?",
            (s["start_offset"], s["end_offset"], s["start_offset"], s["accession"], s["filename"]),
        ).fetchone()
        sent = row[0] if row else ""
        if bool(CAPEX_WORDS.search(sent)) == (metric == "capex") and any(
            p.label == period or p.label.replace("CY", "FY") == period.replace("CY", "FY")
            for p in find_periods(sent, anchor=anchor)
        ):
            return True
    return False


def freshness(
    engine: sqlite3.Connection,
    cik: str,
    period: str,
    today: date,
    corpus: sqlite3.Connection | None = None,
    change: str | None = None,
    metric: str = "capex",
    event: sqlite3.Row | dict | None = None,
) -> Freshness:
    """D-M02-30's states for one guided period; `metric` extends them from capex to every
    metric family M04 scores, and `event` evaluates them at an earlier earnings release
    instead of the latest (M04 Part 1b, `guidance/record.py`)."""
    word = "capex" if metric == "capex" else metric.replace("_", " ")
    ev = event if event is not None else _latest_event(engine, cik)
    if ev is None:
        return Freshness("no earnings release on file", "no 8-K Item 2.02 stored")
    filed = ev["filed"][:10]
    scanned = engine.execute(
        "SELECT 1 FROM guidance_scan WHERE accession = ? LIMIT 1", (ev["accession"],)
    ).fetchone()
    if scanned is None:
        return Freshness(
            "latest results not read yet",
            f"earnings 8-K filed {filed}; its release is not stored or not scanned yet",
        )
    calls = engine.execute(
        "SELECT accession, quarter FROM call_document WHERE cik = ? AND release_accession = ?",
        (cik, ev["accession"]),
    ).fetchall()
    docs = [ev["accession"]] + [c["accession"] for c in calls]
    if any(_states_capex(engine, a, period, metric) for a in docs):
        how = change or "stated again"
        where = "release" if _states_capex(engine, ev["accession"], period, metric) else "call"
        return Freshness("restated", f"{how} in the {where} of {filed}")
    anchor = None
    if calls:
        m = re.fullmatch(r"FY(\d{4}) Q([1-4])", calls[0]["quarter"])
        anchor = (int(m[1]), int(m[2])) if m else None
    if _refused(engine, corpus, docs, period, anchor, metric):
        return Freshness(
            "company gives no outlook yet",
            f"the results of {filed} say no {word} outlook is given for {period}",
        )
    if calls:
        return Freshness("not restated", f"release and call of {filed} are silent on {period}")
    late = (today - date.fromisoformat(filed)).days
    if late <= CALL_WAIT_DAYS:
        return Freshness(
            "call not stored yet",
            f"release {filed} silent on {period}; transcript {late} days after the release",
        )
    return Freshness(
        "call unavailable — not checked",
        f"release {filed} silent on {period}; no transcript after {late} days (download reminder)",
    )


# --- Lines -------------------------------------------------------------------------


def _growth(base: float | None, low: float | None, high: float | None) -> tuple:
    if base is None or base <= 0 or low is None or high is None:
        return None, None, None
    gl, gh = low / base - 1, high / base - 1
    return gl, gh, (gl + gh) / 2


def _ended(label: str, fye: str | None, today: date) -> bool:
    span = span_of(label, fye)
    return span is not None and span.end < today


def guided_lines(
    engine: sqlite3.Connection,
    cik: str,
    today: date,
    corpus: sqlite3.Connection | None = None,
    override: dict | None = None,
) -> list[GuidedLine]:
    book = Book(engine, cik)
    stated = stated_for(engine, cik)
    changes = {}
    for c in changes_for(engine, cik):
        if c.metric == "capex":
            changes[(c.period, c.accession)] = c.kind
    out = []
    for r in latest_rows(engine, cik):
        period = r["period"]
        if span_of(period, book.fye) is None:
            continue  # "FY2026 remaining" and similar: not a money-flow period
        low = float(r["low"]) if r["low"] is not None else None
        high = float(r["high"]) if r["high"] is not None else None
        prev = _prev_label(period)
        base = actual_for(book, prev, r["clause"], override, stated) if prev else None
        comparable = None
        if base is None or base.shown is None:
            comparable = "no base year"
            span = span_of(prev, book.fye) if prev else None
            if span is not None and span.ptype == "CY":
                pts = book.points("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment")
                n = calendar_quarters_present(pts, span.end.year)
                comparable = f"not comparable yet ({n}/4 calendar quarters of {span.end.year})"
        gl, gh, gm = _growth(base.shown if base else None, low, high)
        change = changes.get((period, r["accession"]))
        is_ended = _ended(period, book.fye, today)
        out.append(
            GuidedLine(
                cik=cik,
                period=period,
                kind=r["kind"],
                bound=r["bound"],
                low=low,
                high=high,
                direction=r["direction"],
                clause=r["clause"],
                origin=r["origin"],
                grade=r["grade"],
                source=r["source"],
                quote=r["quote"],
                accession=r["accession"],
                filename=r["filename"],
                stated_on=r["stated_on"],
                change=change,
                base=base,
                growth_low=gl,
                growth_high=gh,
                growth_mid=gm,
                comparable=comparable,
                freshness=(
                    Freshness("period ended", "see guided vs actual")
                    if is_ended
                    else freshness(engine, cik, period, today, corpus, change)
                ),
                ended=is_ended,
                actual=actual_for(book, period, r["clause"], override, stated)
                if is_ended
                else None,
            )
        )
    return sorted(out, key=lambda g: (g.ended, g.period))


def no_guidance(engine: sqlite3.Connection, cik: str) -> bool:
    """The company has never stated capex guidance (D-M02-30 state 6)."""
    return (
        engine.execute(
            "SELECT 1 FROM guidance WHERE cik = ? AND metric = 'capex' LIMIT 1", (cik,)
        ).fetchone()
        is None
    )


def guided_vs_actual(line: GuidedLine) -> str | None:
    """'within guidance' / 'above' / 'below' for an ended period with an actual."""
    a = line.actual
    if not line.ended or a is None or a.shown is None or line.low is None:
        return None
    if line.bound == "floor":
        return "within guidance (≥ floor)" if a.shown >= line.low else "below the floor"
    if line.bound == "ceiling":
        return "within guidance (≤ ceiling)" if a.shown <= line.high else "above the ceiling"
    if line.kind == "approx" or line.low == line.high:
        diff = a.shown / line.low - 1
        return f"actual {diff:+.1%} vs guided"
    if line.low <= a.shown <= line.high:
        return "within guidance"
    return "above guidance" if a.shown > line.high else "below guidance"
