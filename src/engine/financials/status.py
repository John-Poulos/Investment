"""Filing status: current / stale / overdue (S1.6, D-M04-36, D-M04-61; M04 Part 1a).

- **Due date** = period end + the deadline for the filer category: 10-K 60 / 75 / 90 days
  (large accelerated / accelerated / other), 10-Q 40 / 40 / 45, 20-F and 40-F four months;
  a Form NT 12b-25 for the period adds 15 days (annual) or 5 (quarterly). A due date on a
  weekend moves to the Monday (Rule 0-3; holidays are not checked).
- **Category, live:** the submissions `category` ("Large accelerated filer", …) for the
  periods after the latest annual report. **Derived (backtests and older periods):**
  Rule 12b-2 from the stored public float at the end of the second fiscal quarter,
  carried year to year — entry lines $700M (large accelerated) and $75M (accelerated),
  exit lines $560M and $60M apply only to an issuer already in the category (Invitae
  FY2022: $569.8M keeps it large accelerated). A missing float is estimated from the cover
  count × the close on that date, labelled; with neither, the category is carried, and
  with no category at all the longest deadline is used, labelled.
- **Status:** `current` when every period that has ended is filed or not yet ended;
  `stale` when a period has ended unfiled but is not yet due (the carried CvD state is
  marked stale, D-M04-61); `overdue` once its due date passes unfiled (survival gate
  incomplete and an exit warning, D-M04-61). Recomputed from the calendar on every run.
- **Foreign annual filers** (20-F/40-F; 6-Ks are not required periodic reports): annual
  inputs are usable up to 16 months after the period end, then the gate is incomplete
  (D-M04-36); the limit is shown in the note.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from engine.sec.client import iso
from engine.sec.identity import normalize_cik, stored_category
from engine.sec.xbrl_facts import get_series
from engine.signals import Source, write_signal

ANNUAL = ("10-K", "10-KT", "20-F", "40-F")
QUARTERLY = ("10-Q", "10-QT")
FOREIGN = ("20-F", "40-F")
NT_FORMS = {"NT 10-K": "annual", "NT 10-Q": "quarterly", "NT 20-F": "annual",
            "NT 10-K/A": "annual", "NT 10-Q/A": "quarterly", "NT 20-F/A": "annual"}  # fmt: skip
LARGE, ACCEL, NON = "large accelerated", "accelerated", "non-accelerated"
DEADLINES = {
    "annual": {LARGE: 60, ACCEL: 75, NON: 90},
    "quarterly": {LARGE: 40, ACCEL: 40, NON: 45},
}
NT_EXTENSION = {"annual": 15, "quarterly": 5}
ENTRY_LARGE, ENTRY_ACCEL = 700e6, 75e6
EXIT_LARGE, EXIT_ACCEL = 560e6, 60e6
SRC_REVENUE = 100e6
FOREIGN_INPUT_MONTHS = 16
MODULE = "M04"


@dataclass
class StatusRow:
    cik: str
    period_end: str
    form: str
    category: str | None
    category_source: str
    deadline_days: int | None
    due_date: str
    nt_accession: str | None
    filed: str | None
    accession: str | None
    status: str  # current | stale | overdue
    note: str


def category_from_submissions(text: str | None) -> str | None:
    """'Large accelerated filer' → large accelerated; 'Emerging growth company' alone → None."""
    t = (text or "").lower()
    if "large accelerated" in t:
        return LARGE
    if "non-accelerated" in t:
        return NON
    if "accelerated" in t:
        return ACCEL
    return None


def next_category(prev: str | None, float_usd: float, revenue: float | None) -> str:
    """Rule 12b-2 with exit lines applied only to an issuer already in the category."""
    if revenue is not None and revenue < SRC_REVENUE and float_usd < ENTRY_LARGE:
        return NON  # SRC revenue test: not an accelerated filer
    if prev == LARGE:
        return LARGE if float_usd >= EXIT_LARGE else (ACCEL if float_usd >= EXIT_ACCEL else NON)
    if prev == ACCEL:
        if float_usd >= ENTRY_LARGE:
            return LARGE
        return ACCEL if float_usd >= EXIT_ACCEL else NON
    if float_usd >= ENTRY_LARGE:
        return LARGE
    return ACCEL if float_usd >= ENTRY_ACCEL else NON


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _business_day(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def due_date(period_end: str, kind: str, form: str, category: str | None,
             nt: bool) -> tuple[date, int | None]:  # fmt: skip
    """(due date, deadline days or None for a months rule)."""
    end = _d(period_end)
    if form in FOREIGN:
        due = _add_months(end, 4)
        days = None
    else:
        days = DEADLINES[kind][category or NON]
        due = end + timedelta(days=days)
    if nt:
        due += timedelta(days=NT_EXTENSION[kind])
    return _business_day(due), days


# --- Inputs ------------------------------------------------------------------------------


def _reports(engine: sqlite3.Connection, cik: str, as_of: str) -> list[sqlite3.Row]:
    forms = ANNUAL + QUARTERLY
    marks = ",".join("?" * len(forms))
    return engine.execute(
        f"SELECT f.accession, f.form, f.filed, f.report_date FROM filing f JOIN filing_cik c "
        f"ON c.accession = f.accession WHERE c.cik = ? AND f.form IN ({marks}) "
        "AND f.report_date IS NOT NULL AND f.filed <= ? ORDER BY f.report_date, f.filed",
        (cik, *forms, as_of),
    ).fetchall()


def _nt_filings(engine: sqlite3.Connection, cik: str, as_of: str) -> list[sqlite3.Row]:
    marks = ",".join("?" * len(NT_FORMS))
    return engine.execute(
        f"SELECT f.accession, f.form, f.filed, f.report_date FROM filing f JOIN filing_cik c "
        f"ON c.accession = f.accession WHERE c.cik = ? AND f.form IN ({marks}) AND f.filed <= ?",
        (cik, *NT_FORMS, as_of),
    ).fetchall()


def _kind(form: str) -> str:
    return "annual" if form in ANNUAL else "quarterly"


def _float_for_year(
    engine: sqlite3.Connection, cik: str, fy_end: str, as_of: str
) -> tuple[float | None, str]:
    """Public float for the fiscal year ending `fy_end`: the dei fact dated 4–8 months
    before it, else cover count × close at the second-quarter end (estimated)."""
    from engine.financials.shares import close_on

    end = _d(fy_end)
    lo, hi = (end - timedelta(days=245)).isoformat(), (end - timedelta(days=120)).isoformat()
    row = engine.execute(
        "SELECT value, period_end, accession FROM fact WHERE cik = ? AND taxonomy = 'dei' AND "
        "tag = 'EntityPublicFloat' AND period_end BETWEEN ? AND ? AND filed <= ? "
        "ORDER BY filed DESC LIMIT 1",
        (cik, lo, hi, as_of),
    ).fetchone()
    if row is not None:
        return float(
            row["value"]
        ), f"float ${float(row['value']) / 1e6:,.1f}M at {row['period_end']}"
    q2 = _add_months(end, -6)
    q2_report = engine.execute(
        "SELECT report_date FROM filing WHERE cik = ? AND form IN ('10-Q', '10-Q/A') AND "
        "report_date BETWEEN ? AND ? ORDER BY report_date LIMIT 1",
        (cik, (q2 - timedelta(days=15)).isoformat(), (q2 + timedelta(days=15)).isoformat()),
    ).fetchone()
    q2s = q2_report["report_date"] if q2_report else q2.isoformat()
    close = close_on(engine, cik, q2s)
    covers = engine.execute(
        "SELECT value, period_end FROM fact WHERE cik = ? AND taxonomy = 'dei' AND "
        "tag = 'EntityCommonStockSharesOutstanding' AND unit = 'shares' AND filed <= ? AND "
        "period_end BETWEEN ? AND ?",
        (cik, as_of, (_d(q2s) - timedelta(days=120)).isoformat(),
         (_d(q2s) + timedelta(days=120)).isoformat()),
    ).fetchall()  # fmt: skip
    if close is None or not covers:
        return None, f"float missing for FY ending {fy_end}"
    near = min(covers, key=lambda r: abs((_d(r["period_end"]) - _d(q2s)).days))
    est = float(near["value"]) * close[0]
    return est, (f"float estimated ${est / 1e6:,.1f}M = cover {float(near['value']):,.0f} "
                 f"({near['period_end']}) × close ${close[0]:,.2f} ({close[1]})")  # fmt: skip


def _fy_revenue(engine: sqlite3.Connection, cik: str, fy_end: str) -> float | None:
    rows = [r for r in get_series(engine, cik, "revenue", "FY") if r.end <= fy_end]
    return float(rows[-1].first.value) if rows else None


def derived_categories(
    engine: sqlite3.Connection, cik: str, fy_ends: list[str], as_of: str
) -> dict[str, tuple[str | None, str]]:
    """fiscal-year end → (category, how), carried in order (Rule 12b-2)."""
    out, prev = {}, None
    for e in sorted(fy_ends):
        f, how = _float_for_year(engine, cik, e, as_of)
        if f is None:
            out[e] = (prev, f"{how}; " + ("carried" if prev else "no category"))
            continue
        rev = _fy_revenue(engine, cik, e)
        cat = next_category(prev, f, rev)
        out[e] = (cat, f"{how} → {cat} (Rule 12b-2{', carried from ' + prev if prev else ''})")
        prev = cat
    return out


def _expected_next(reports: list[sqlite3.Row], foreign: bool) -> tuple[str, str] | None:
    """(period end, form) of the report expected after the last one filed."""
    if not reports:
        return None
    last = reports[-1]
    last_end = _d(last["report_date"])
    if foreign:
        return _add_months(last_end, 12).isoformat(), last["form"]
    ends = [_d(r["report_date"]) for r in reports]
    for i, e in enumerate(ends):
        if abs((last_end - e).days - 365) <= 10 and i + 1 < len(reports):
            nxt = reports[i + 1]
            shift = last_end - e
            return (_d(nxt["report_date"]) + shift).isoformat(), (
                "10-K" if nxt["form"] in ANNUAL else "10-Q"
            )
    annuals = [r for r in reports if r["form"] in ANNUAL]
    since = [r for r in reports if annuals and r["report_date"] > annuals[-1]["report_date"]]
    if annuals and len(since) >= 3:
        return _add_months(_d(annuals[-1]["report_date"]), 12).isoformat(), "10-K"
    if (last_end + timedelta(days=1)).day == 1:  # calendar quarters end on a month end
        nxt_end = _add_months(last_end + timedelta(days=1), 3) - timedelta(days=1)
        return nxt_end.isoformat(), "10-Q"
    return (last_end + timedelta(days=91)).isoformat(), "10-Q"  # 13-week quarters


# --- Evaluation ----------------------------------------------------------------------------


def evaluate(
    engine: sqlite3.Connection,
    cik: str,
    as_of: str,
    *,
    live_category: str | None = None,
    years: int = 3,
) -> list[StatusRow]:
    """Status rows known on `as_of`: filed reports of the last `years` years, then the
    first period that has ended unfiled (stale or overdue), if any."""
    norm = normalize_cik(cik) or cik
    reports = _reports(engine, norm, as_of)
    if not reports:
        return []
    foreign = any(r["form"] in FOREIGN for r in reports)
    nts = _nt_filings(engine, norm, as_of)
    annual_ends = [r["report_date"] for r in reports if r["form"] in ANNUAL]
    nxt = _expected_next(reports, foreign)
    if nxt and nxt[1] in ANNUAL:
        annual_ends.append(nxt[0])
    derived = derived_categories(engine, norm, annual_ends, as_of)
    live = category_from_submissions(live_category)
    last_annual = max((r["report_date"] for r in reports if r["form"] in ANNUAL), default=None)

    def category_for(period_end: str, form: str) -> tuple[str | None, str]:
        # the submissions category is the status set at the latest fiscal year end: it
        # governs that year's 10-K and the periods after it
        if live and (last_annual is None or period_end >= last_annual):
            return live, f"submissions: {live_category}"
        # a 10-K uses its own year's determination; a 10-Q the latest year before it
        ends = [e for e in derived if (e <= period_end if form in ANNUAL else e < period_end)]
        if ends:
            cat, how = derived[max(ends)]
            if cat:
                return cat, how
        return None, "missing: no float or category; longest deadline"

    def nt_for(period_end: str, kind: str) -> sqlite3.Row | None:
        for n in nts:
            if NT_FORMS[n["form"]] != kind:
                continue
            if n["report_date"] == period_end or (
                not n["report_date"]
                and 0 <= (_d(n["filed"]) - _d(period_end)).days <= (100 if kind == "annual" else 50)
            ):
                return n
        return None

    def row(period_end: str, form: str, filed: sqlite3.Row | None) -> StatusRow:
        kind = _kind(form)
        cat, how = category_for(period_end, form)
        nt = nt_for(period_end, kind)
        due, days = due_date(period_end, kind, form, cat, nt is not None)
        notes = []
        if nt is not None:
            notes.append(f"NT filed {nt['filed']} (+{NT_EXTENSION[kind]} days)")
        if form in FOREIGN:
            limit = _add_months(_d(period_end), FOREIGN_INPUT_MONTHS)
            notes.append(f"annual inputs usable to {limit} (16 months, D-M04-36)")
        if filed is not None:
            gap = (due - _d(filed["filed"])).days
            notes.insert(
                0, f"filed {gap} days before due" if gap >= 0 else f"filed {-gap} days late"
            )
            status = "current"
        else:
            left = (due - _d(as_of)).days
            status = "overdue" if left < 0 else "stale"
            notes.insert(0, f"not filed; {-left} days past due" if left < 0
                         else f"period ended, not filed; due in {left} days")  # fmt: skip
        return StatusRow(
            norm, period_end, form, cat, how, days, due.isoformat(),
            nt["accession"] if nt else None, filed["filed"] if filed else None,
            filed["accession"] if filed else None, status, "; ".join(notes),
        )  # fmt: skip

    since = (_d(as_of) - timedelta(days=365 * years)).isoformat()
    rows = [row(r["report_date"], r["form"], r) for r in reports if r["report_date"] >= since]
    if nxt and nxt[0] <= as_of:
        rows.append(row(nxt[0], nxt[1], None))
    return rows


def record_of(rows: list[StatusRow]) -> StatusRow | None:
    """The row that sets the company's status: an unfiled period, else the newest filed."""
    if not rows:
        return None
    open_rows = [r for r in rows if r.filed is None]
    return open_rows[0] if open_rows else max(rows, key=lambda r: r.period_end)


def refresh_status(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    cik: str,
    ticker: str | None,
    now: datetime,
) -> StatusRow | None:
    """Re-evaluate one company from the calendar (0 SEC requests), store its rows and its
    `filing_status` signal (MY, PT, ST)."""
    norm = normalize_cik(cik) or cik
    ent = engine.execute("SELECT category FROM entity WHERE cik = ?", (norm,)).fetchone()
    live = ent["category"] if ent and ent["category"] else None
    if live is None and corpus is not None:
        live, _ = stored_category(corpus, norm)
    today = now.date().isoformat()
    rows = evaluate(engine, norm, today, live_category=live)
    rec = record_of(rows)
    engine.execute("BEGIN")
    try:
        engine.execute("DELETE FROM filing_status WHERE cik = ?", (norm,))
        engine.executemany(
            "INSERT INTO filing_status (cik, period_end, form, category, category_source, "
            "deadline_days, due_date, nt_accession, filed, accession, status, note, evaluated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(r.cik, r.period_end, r.form, r.category, r.category_source, r.deadline_days,
              r.due_date, r.nt_accession, r.filed, r.accession, r.status, r.note, iso(now))
             for r in rows],
        )  # fmt: skip
        if rec is None:
            write_signal(engine, cik=norm, ticker=ticker, module_id=MODULE, signal="filing_status",
                         as_of=today, method="no 10-K, 10-Q, 20-F or 40-F stored",
                         missing="no periodic reports (fund or new filer)")  # fmt: skip
        else:
            last = max((r for r in rows if r.filed), key=lambda r: r.filed or "", default=None)
            sources = [Source(last.accession, last.filed, "A", f"{last.form} {last.period_end}")
                       ] if last and last.accession and last.filed else []  # fmt: skip
            as_of = {"current": rec.filed, "stale": rec.period_end, "overdue": rec.due_date}[
                rec.status
            ] or today
            method = (f"{rec.form} period {rec.period_end}, due {rec.due_date}; {rec.note}; "
                      f"category {rec.category or 'unknown'} ({rec.category_source})")  # fmt: skip
            if sources:
                write_signal(engine, cik=norm, ticker=ticker, module_id=MODULE,
                             signal="filing_status", as_of=as_of, value_text=rec.status,
                             method=method, sources=sources)  # fmt: skip
            else:
                write_signal(engine, cik=norm, ticker=ticker, module_id=MODULE,
                             signal="filing_status", as_of=as_of, method=method,
                             missing="no filed report to cite")  # fmt: skip
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return rec


def stored_status(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT * FROM filing_status WHERE cik = ? ORDER BY period_end DESC",
        (normalize_cik(cik) or cik,),
    ).fetchall()
