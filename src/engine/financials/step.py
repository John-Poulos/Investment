"""The M04 step of a refresh run (M04_BUILD_LOG "Logon-refresh constraints"; D-M04-70).

Two hooks in `scripts/run_refresh.py`, both inside the refresh lock and timed:

- **SEC part, after the official feeds:** per-new-filing work only. Part 1a: the R1 cover
  page of each new annual report (10-K, 10-KT, 20-F, 40-F; cover count and the error-
  correction flag) and of each new 10-Q of a multi-class filer (~30 requests a year).
  "New" = filed in the last 30 days and not read yet; history is backfilled only by the
  owner (`scripts/run_financials.py data`).
- **Local pass, after prices (0 SEC requests; also when prices are skipped):**
  `filing_status` for every covered company from the calendar, and the `filing_status`,
  `shares_cover` and `implied_float_shares` signals.

Never fails the run: errors are reported in its lines; writes are short transactions.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timedelta

from engine.financials import shares, status
from engine.sec.client import SecClient
from engine.sec.cover import fetch_cover, r1_done
from engine.sec.results import Failed, NotFound, Ok
from engine.signals import Source, write_signal

ANNUAL_COVER_FORMS = ("10-K", "10-KT", "20-F", "40-F")
QUARTERLY_COVER_FORMS = ("10-Q", "10-QT")
NEW_DAYS = 30
SEC_BUDGET_S = 120.0
MODULE = "M04"


def r1_wanted(
    engine: sqlite3.Connection, cik: str, since: str, *, annual: bool = True
) -> list[sqlite3.Row]:
    """Filings since `since` whose R1 page is wanted and not read: annual covers (if
    `annual`), and quarterly covers of a multi-class filer (D-M04-2)."""
    forms = list(ANNUAL_COVER_FORMS if annual else ())
    if shares.needs_r1(engine, cik):
        forms += list(ANNUAL_COVER_FORMS) + list(QUARTERLY_COVER_FORMS)
    forms = sorted(set(forms))
    if not forms:
        return []
    marks = ",".join("?" * len(forms))
    rows = engine.execute(
        f"SELECT f.accession, f.form, f.filed, f.report_date FROM filing f JOIN filing_cik c "
        f"ON c.accession = f.accession WHERE c.cik = ? AND f.form IN ({marks}) AND f.filed >= ? "
        "ORDER BY f.filed",
        (cik, *forms, since),
    ).fetchall()
    return [r for r in rows if not r1_done(engine, r["accession"])]


def read_covers(
    client: SecClient,
    engine: sqlite3.Connection,
    todo: list[tuple[str, str, sqlite3.Row]],
    now: datetime,
    *,
    budget_s: float = SEC_BUDGET_S,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[list[str], dict[str, int]]:
    """Read R1 pages for (ticker, cik, filing) items. Returns (lines, counts)."""
    lines, counts = [], {"cover": 0, "not_cover": 0, "not_found": 0, "failed": 0, "pending": 0}
    start = clock()
    for i, (ticker, cik, f) in enumerate(todo):
        if clock() - start > budget_s:
            counts["pending"] += len(todo) - i
            lines.append(f"  time budget reached; {len(todo) - i} R1 page(s) left for the next run")
            break
        res = fetch_cover(client, engine, cik, f, now)
        if isinstance(res, Ok):
            read = res.data
            if read.is_cover and read.classes:
                counts["cover"] += 1
                parts = " + ".join(f"{c or '(no class)'} {n:,.0f}" for c, n in read.classes)
                flag = {True: "true", False: "false", None: "not on cover"}[
                    read.error_correction_flag
                ]
                lines.append(f"  {ticker} {f['form']} {f['accession']}: {parts} = "
                             f"{read.total:,.0f} at {read.cover_date}; error-correction flag {flag}"
                             + (f"; {'; '.join(read.notes)}" if read.notes else ""))  # fmt: skip
            else:
                counts["not_cover"] += 1
                lines.append(f"  {ticker} {f['form']} {f['accession']}: R1 read as not a cover "
                             f"({read.title or 'no title'}); {'; '.join(read.notes)}")  # fmt: skip
        elif isinstance(res, NotFound):
            counts["not_found"] += 1
            lines.append(f"  {ticker} {f['form']} {f['accession']}: no R1 page (HTTP 404)")
        else:
            counts["failed"] += 1
            reason = res.reason if isinstance(res, Failed) else str(res)
            lines.append(f"  {ticker} {f['form']} {f['accession']}: failed: {reason}")
            if isinstance(res, Failed) and res.throttled:
                counts["pending"] += len(todo) - i - 1
                lines.append("  SEC throttle: the rest waits for the next run")
                break
    return lines, counts


def run_sec_part(
    client: SecClient,
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    """New R1 cover pages (per-new-filing work only)."""
    t0 = clock()
    lines: list[str] = []
    try:
        since = (now - timedelta(days=NEW_DAYS)).date().isoformat()
        todo = [
            (t, c, f) for t, c in sorted(companies.items()) for f in r1_wanted(engine, c, since)
        ]
        got, counts = read_covers(client, engine, todo, now, clock=clock)
        lines += got
        lines.insert(0, f"R1 cover pages: {len(todo)} new filing(s); read {counts['cover']}, "
                        f"not a cover {counts['not_cover']}, not found {counts['not_found']}, "
                        f"failed {counts['failed']}, pending {counts['pending']}")  # fmt: skip
    except Exception as e:  # the step must not break the run report
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        lines.append(f"error — {type(e).__name__}: {e}")
    head = f"M04 financials — SEC part (Part 1a) ({clock() - t0:.1f} s):"
    return [head, *lines]


def share_signals(engine: sqlite3.Connection, cik: str, ticker: str | None, today: str) -> int:
    """`shares_cover` and `implied_float_shares` (information rows, weight 0)."""
    n = 0
    covers = shares.cover_counts(engine, cik)
    latest = shares.latest_periodic(engine, cik)
    if covers and covers[0].value is not None:
        v = covers[0]
        n += write_signal(
            engine, cik=cik, ticker=ticker, module_id=MODULE, signal="shares_cover",
            as_of=v.date, value=v.value, info=("MY", "PT", "ST"),
            method=f"{v.tag}" + (f"; classes: {', '.join(f'{c} {s:,.0f}' for c, s in v.classes)}"
                                 if v.classes else "") + (f"; {v.note}" if v.note else ""),
            sources=[Source(v.accession, v.first_filed or v.date, "A", "cover")],
        )  # fmt: skip
    else:
        n += write_signal(
            engine, cik=cik, ticker=ticker, module_id=MODULE, signal="shares_cover",
            as_of=(latest["report_date"] if latest and latest["report_date"] else today),
            method="cover count", missing=shares.cover_missing_reason(engine, cik),
            info=("MY", "PT", "ST"),
        )  # fmt: skip
    floats = [f for f in shares.implied_float(engine, cik) if f.value is not None]
    if floats:
        f = floats[0]
        n += write_signal(
            engine, cik=cik, ticker=ticker, module_id=MODULE, signal="implied_float_shares",
            as_of=f.date, value=round(f.value), info=("MY", "PT", "ST"), method=f.note,
            sources=[Source(f.accession, f.latest_filed or f.date, "A", "dei:EntityPublicFloat")],
        )  # fmt: skip
    return n


def run_local_part(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    companies: dict[str, str],
    now: datetime,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    """`filing_status` and share signals for every covered company (0 SEC requests)."""
    t0 = clock()
    lines: list[str] = []
    counts = {"current": 0, "stale": 0, "overdue": 0, "none": 0}
    alerts = []
    for ticker, cik in sorted(companies.items()):
        try:
            rec = status.refresh_status(engine, corpus, cik, ticker, now)
            if rec is None:
                counts["none"] += 1
            else:
                counts[rec.status] += 1
                if rec.status != "current":
                    alerts.append(f"  {ticker}: {rec.status} — {rec.form} period {rec.period_end}, "
                                  f"due {rec.due_date}; {rec.note}")  # fmt: skip
            engine.execute("BEGIN")
            try:
                share_signals(engine, cik, ticker, now.date().isoformat())
                engine.execute("COMMIT")
            except Exception:
                engine.execute("ROLLBACK")
                raise
        except Exception as e:  # one company's error must not stop the others
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            lines.append(f"  {ticker}: error — {type(e).__name__}: {e}")
    summary = (
        f"filing status: current {counts['current']}, stale {counts['stale']}, "
        f"overdue {counts['overdue']}, no periodic reports {counts['none']}"
    )
    lines.insert(0, summary)
    lines[1:1] = alerts
    head = f"M04 financials — local pass (Part 1a, 0 SEC requests) ({clock() - t0:.1f} s):"
    return [head, *lines]
