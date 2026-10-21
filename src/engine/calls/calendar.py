"""Next report date: a cadence estimate from stored releases (grade C; MVP_PLAN item 4).

Shared helper: M08 Part 2 reads it for the walk-down window (≤ 30† days before a report,
S-new-M08-16); M12 later adds the IR headline (A) and vendor (B) dates to the same helper.

- Reports: the company's earnings 8-Ks (Item 2.02, `transcripts.company_releases`: one
  results release per fiscal quarter), else its periodic reports (10-Q, 10-K, 20-F, 40-F
  filed dates; results may come earlier), filed on or before the reading date.
- Next fiscal quarter = the one after the newest report's quarter (fiscal year end from
  SEC submissions; a fiscal year is named by the calendar year it ends in, as Alpha
  Vantage does). Its expected date = its quarter end + the lag of the same fiscal quarter a
  year earlier (Q4 reports usually come later), else the median lag of the last 8 reports.
- Past the expected date with nothing stored: "expected, not stored yet" (overdue) up to
  30 days, then missing ("cadence stale"): a late filer or a store behind its refresh.
- Never a fetch; a date in the past of the reading date is never "next".
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from engine.calls.transcripts import company_releases, last_quarter

GRADE = "C"  # an estimate from the company's own cadence (D14: below a stated date)
STALE_DAYS = 30  # overdue longer than this → missing
MEDIAN_OF = 8
PERIODIC = ("10-Q", "10-K", "20-F", "40-F")


@dataclass(frozen=True)
class Report:
    fy: int
    q: int
    end: date
    filed: date


@dataclass(frozen=True)
class NextReport:
    day: str | None  # expected date (ISO); None when missing
    quarter: str = ""  # "FY2027 Q1"
    quarter_end: str = ""
    basis: str = ""
    n: int = 0  # reports the estimate rests on
    overdue: bool = False
    missing: str = ""
    grade: str = GRADE

    def text(self) -> str:
        if self.day is None:
            return f"next report missing: {self.missing}"
        state = "expected, not stored yet" if self.overdue else "expected"
        return (
            f"next report {self.quarter} {state} ≈ {self.day} (quarter end ≈ {self.quarter_end}; "
            f"{self.basis}; grade {self.grade} cadence estimate)"
        )


def _fye(engine: sqlite3.Connection, cik: str) -> str | None:
    r = engine.execute("SELECT fiscal_year_end FROM entity WHERE cik = ?", (cik,)).fetchone()
    return r[0] if r else None


def reports(engine: sqlite3.Connection, cik: str, upto: str) -> tuple[list[Report], str]:
    """(reports filed on or before `upto`, oldest first; which kind)."""
    fye = _fye(engine, cik)
    if fye is None:
        return [], ""
    stop = date.fromisoformat(upto)

    def mapped(filed_dates: list[str]) -> list[Report]:
        out: dict[tuple[int, int], Report] = {}
        for f in sorted(filed_dates):
            d = date.fromisoformat(f[:10])
            if d > stop:
                continue
            last = last_quarter(d, fye)
            if last is None:
                continue
            fy, q, end = last
            out.setdefault((fy, q), Report(fy, q, end, d))  # the first report of a quarter
        return sorted(out.values(), key=lambda r: r.filed)

    rel = mapped([filed for _, filed in company_releases(engine, cik).values()])
    if rel:
        return rel, "earnings 8-Ks"
    marks = ",".join("?" * len(PERIODIC))
    rows = engine.execute(
        f"SELECT filed FROM filing WHERE cik = ? AND form IN ({marks})", (cik, *PERIODIC)
    ).fetchall()
    return mapped([r[0] for r in rows]), "periodic reports (filed dates; results may come earlier)"


def next_report(engine: sqlite3.Connection, cik: str, day: str) -> NextReport:
    """The next report expected after `day`, from the reports stored by `day`."""
    if _fye(engine, cik) is None:
        return NextReport(None, missing="no fiscal year end stored")
    reps, kind = reports(engine, cik, day)
    if not reps:
        return NextReport(None, missing="no stored earnings releases or periodic reports")
    fye = _fye(engine, cik)
    newest = reps[-1]
    nxt = last_quarter(newest.end + timedelta(days=100), fye)
    assert nxt is not None
    fy, q, end = nxt
    same = next((r for r in reps if (r.fy, r.q) == (fy - 1, q)), None)
    if same is not None:
        lag = (same.filed - same.end).days
        how = f"lag {lag} days as FY{fy - 1} Q{q}"
    else:
        lags = [(r.filed - r.end).days for r in reps[-MEDIAN_OF:]]
        lag = int(statistics.median(lags))
        how = f"median lag {lag} days of the last {len(lags)} reports"
    expected = end + timedelta(days=lag)
    today = date.fromisoformat(day)
    basis = f"{how}; {len(reps)} stored {kind}, newest filed {newest.filed}"
    if expected < today:
        late = (today - expected).days
        if late > STALE_DAYS:
            return NextReport(
                None,
                f"FY{fy} Q{q}",
                end.isoformat(),
                basis,
                len(reps),
                missing=f"cadence stale: FY{fy} Q{q} expected ≈ {expected}, nothing stored "
                f"{late} days later",
            )
        return NextReport(
            expected.isoformat(), f"FY{fy} Q{q}", end.isoformat(), basis, len(reps), True
        )
    return NextReport(expected.isoformat(), f"FY{fy} Q{q}", end.isoformat(), basis, len(reps))


def walk_down(nr: NextReport, day: str, window_days: int = 30) -> tuple[bool | None, str]:
    """(inside the walk-down window, note): ≤ `window_days` before the next report, or the
    report expected and not stored yet (S-new-M08-16). None = unknown (no estimate)."""
    if nr.day is None:
        return None, f"walk-down window unknown ({nr.text()})"
    days = (date.fromisoformat(nr.day) - date.fromisoformat(day)).days
    if nr.overdue or days < 0:
        return True, f"walk-down window: {nr.text()}"
    if days <= window_days:
        return True, f"walk-down window ({days} days ≤ {window_days}†): {nr.text()}"
    return False, f"outside the walk-down window ({days} days): {nr.text()}"
