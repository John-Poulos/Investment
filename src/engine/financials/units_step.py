"""The M04 Part 7a hooks of a refresh run (M04_BUILD_LOG "Logon-refresh constraints";
D-M04-42, D-M04-70). Called from `scripts/run_refresh.py` right after the other M04 hooks
(`financials_units_sec_step` after `financials_sec_step`, `financials_units_local_step`
after `financials_local_step`), inside the refresh lock and timed.

- **SEC part (per new filing only):** for core and promoted companies (D-M04-80: tracked
  names get no instance reads), the XBRL instance of each new 10-K/10-Q/20-F/40-F (and an
  XBRL 6-K) filed in the last 30 days and not read yet — one request each, ~70 a year,
  extension facts and dimensional facts on the one read, file not cached (SB.16); and the
  EX-99.2 of each new earnings 8-K (index usually cached; ≤ 60 a year). History is the
  owner's backfill (`scripts/run_financials.py units`).
- **Local pass (0 requests):** unit KPIs and release tables from documents stored since
  the last pass, and `m04_unit_kpi` items for category breaks (group 6, capped).

Never fails the run; a throttle or the time budget leaves the rest for the next run.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta

from engine.financials import exhibits, units
from engine.sec import instance_dim
from engine.sec.client import SecClient

NEW_DAYS = 30
SEC_BUDGET_S = 90.0


def full_scope(engine, companies: dict[str, str]) -> dict[str, str]:
    """Core and promoted names only (tracked: facts only, D-M04-80)."""
    tracked = {
        r[0]
        for r in engine.execute(
            "SELECT cik FROM tier_member WHERE status = 'active' AND tier = 'tracked'"
        )
    }
    return {t: c for t, c in companies.items() if c not in tracked}


def run_sec_part(
    client: SecClient,
    engine,
    corpus,
    companies: dict[str, str],
    now: datetime,
    *,
    clock: Callable[[], float] = time.monotonic,
    budget_s: float = SEC_BUDGET_S,
) -> list[str]:
    t0 = clock()
    lines: list[str] = []
    read = mb = dims = 0.0
    found = checked = 0
    stop = ""
    try:
        since = (now - timedelta(days=NEW_DAYS)).date().isoformat()
        scope = full_scope(engine, companies)
        for ticker, cik in sorted(scope.items()):
            if stop:
                break
            for f in instance_dim.due_filings(engine, cik, since):
                if clock() - t0 > budget_s:
                    stop = "time budget reached; the rest waits for the next run"
                    break
                r = instance_dim.read_instance(client, engine, cik, f, now)
                if r.outcome == "ok":
                    read += 1
                    mb += r.mb
                    dims += r.dim_new
                else:
                    lines.append(
                        f"  {ticker} {f['form']} {f['accession']}: {r.outcome} {r.detail}".rstrip()
                    )
                if r.throttled:
                    stop = "SEC throttle: the rest waits for the next run"
                    break
            if stop:
                break
            new_8k = [f for f in exhibits.ex992_due(engine, cik) if f.filed >= since]
            if new_8k:
                ex = exhibits.fetch_ex992(client, engine, corpus, cik, now, filings=new_8k)
                checked += ex.checked
                found += ex.found
                lines += [f"  {ticker} EX-99.2 {x}" for x in ex.failed or []]
                if ex.throttled:
                    stop = "SEC throttle: the rest waits for the next run"
    except Exception as e:  # the step must not break the run report
        for c in (engine, corpus):
            if c.in_transaction:
                c.execute("ROLLBACK")
        lines.append(f"  error — {type(e).__name__}: {e}")
    head = (
        f"M04 units — SEC part (Part 7a) ({clock() - t0:.1f} s): instances read {read:.0f} "
        f"({mb:.1f} MB, {dims:.0f} dimensional rows); earnings 8-Ks checked for EX-99.2 "
        f"{checked}, found {found}"
    )
    return [head, *lines, *([f"  {stop}"] if stop else [])]


def run_local_part(
    engine,
    corpus,
    companies: dict[str, str],
    now: datetime,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    t0 = clock()
    lines: list[str] = []
    docs = rows = tables = 0
    queued: dict[str, int] = {}
    for ticker, cik in sorted(full_scope(engine, companies).items()):
        try:
            s = units.scan_company(engine, corpus, cik, now)
            docs, rows = docs + s.docs, rows + s.rows
            tables += exhibits.scan_releases(engine, corpus, cik, now) if s.docs else 0
            for k, v in units.propose_breaks(engine, cik, ticker, now).items():
                queued[k] = queued.get(k, 0) + v
        except Exception as e:  # one company's error must not stop the others
            for c in (engine, corpus):
                if c.in_transaction:
                    c.execute("ROLLBACK")
            lines.append(f"  {ticker}: error — {type(e).__name__}: {e}")
    q = ", ".join(f"{k} {v}" for k, v in sorted(queued.items())) or "none"
    head = (
        f"M04 units — local pass (Part 7a, 0 SEC requests) ({clock() - t0:.1f} s): "
        f"{docs} new document(s) scanned, {rows} unit rows, {tables} release-table rows; "
        f"m04_unit_kpi items: {q}"
    )
    return [head, *lines]
