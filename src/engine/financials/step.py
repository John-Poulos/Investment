"""The M04 step of a refresh run (M04_BUILD_LOG "Logon-refresh constraints"; D-M04-70).

Two hooks in `scripts/run_refresh.py`, both inside the refresh lock and timed:

- **SEC part, after the official feeds:** per-new-filing work only. Part 1a: the R1 cover
  page of each new annual report (10-K, 10-KT, 20-F, 40-F; cover count and the error-
  correction flag) and of each new 10-Q of a multi-class filer (~30 requests a year).
  "New" = filed in the last 30 days and not read yet; history is backfilled only by the
  owner (`scripts/run_financials.py data`). Part 2: a confirmed peer's companyfacts is
  re-fetched (trimmed to M04's tags, not cached) when the refresh's daily-index read marked
  it due for a new 10-K/10-Q/20-F/40-F (`peer_facts.refetch_due`, ~160–200 a year); peers
  never fetched are listed, not fetched (first downloads are owner-run, D-M04-70).
- **Local pass, after prices (0 SEC requests; also when prices are skipped):**
  `filing_status` for every covered company from the calendar, and the `filing_status`,
  `shares_cover` and `implied_float_shares` signals (Part 1a); Part 1b recomputes the
  capex split (`capex_split`), the core trend rows and the guidance record
  (`guidance_outcome`) and writes their signals (`capex_maint`, `capex_growth`,
  `owner_earnings`, `rev_yoy`, `rev_cagr3`, `fcf_growth`, `fcf_growth_oe`, `gm_trend_pp`,
  `opex_vs_sales`, `guidance_hit_rate`, `guidance_removed`). NVIDIA's FY2013–21 capex
  instances are a one-off owner backfill (`scripts/run_financials.py capex`), never fetched
  here (D-M04-70). Part 1c recomputes the life-cycle stage of every core and promoted
  company (D-M04-80), opens the setup `m04_stage` items on the first run and an item per new
  fiscal year whose computed stage differs from the owner's or is ambiguous (D-M04-12),
  flushes M04 overflow (cap 5, D-M04-71) and writes `lifecycle_stage`. Browse-by-SIC and the
  revenue frames are owner-run only (`scripts/run_financials.py profile`). Part 2 adds the
  peer robust z to the trend signals' method (peer facts read once per pass).

Never fails the run: errors are reported in its lines; writes are short transactions.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from engine.financials import capex, models, peer_facts, peer_z, profile, shares, status, trends
from engine.guidance import record
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
    try:  # Part 2: a peer's companyfacts when the daily index showed its periodic filing
        if client.paused_for() > 0:
            lines.append("M04 peer facts: SEC throttle open; due peers wait for the next run")
        else:
            lines += peer_facts.refetch_due(client, engine, now, clock=clock)
        new = peer_facts.unfetched_peers(engine, companies.values())
        if new:
            lines.append(f"M04 peer facts: {len(new)} confirmed peer(s) never fetched (owner-run: "
                         "scripts/run_financials.py peers)")  # fmt: skip
    except Exception as e:
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        lines.append(f"M04 peer facts: error — {type(e).__name__}: {e}")
    head = f"M04 financials — SEC part (Parts 1a, 2) ({clock() - t0:.1f} s):"
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


TREND_SIGNALS = ("rev_yoy", "rev_cagr3", "fcf_growth", "fcf_growth_oe", "gm_trend_pp",
                 "opex_vs_sales")  # fmt: skip


def capex_signals(
    engine: sqlite3.Connection, cik: str, ticker: str | None, view: capex.CapexView, today: str
) -> int:
    """`capex_maint`, `capex_growth`, `owner_earnings` for the latest fiscal year (info)."""
    n = 0
    y = view.years[-1] if view.years else None
    for name, attr in (("capex_maint", "maintenance"), ("capex_growth", "growth"),
                       ("owner_earnings", "owner_earnings")):  # fmt: skip
        if y is None:
            n += write_signal(engine, cik=cik, ticker=ticker, module_id=MODULE, signal=name,
                              as_of=today, method="capex split (D-M04-6)",
                              missing="no total capex stored", info=("MY", "PT", "ST"))  # fmt: skip
            continue
        t = y.total
        srcs = [Source(t.accession, t.filed, "A", f"total capex {t.tag}")] if t else []
        method = (f"{y.label}: {y.method}; total capex {t.value / 1e6:,.0f}M on {t.tag}"
                  + (f" [{t.mark}]" if t.mark else "") if t else y.label)  # fmt: skip
        if attr == "owner_earnings":
            method += "; owner earnings = OCF − maintenance capex − SBC (information, D-M04-6)"
        v = getattr(y, attr)
        if v is None:
            n += write_signal(engine, cik=cik, ticker=ticker, module_id=MODULE, signal=name,
                              as_of=y.filed or y.end, method=method, missing=y.missing(attr),
                              sources=srcs, info=("MY", "PT", "ST"))  # fmt: skip
        else:
            n += write_signal(engine, cik=cik, ticker=ticker, module_id=MODULE, signal=name,
                              as_of=y.filed or y.end, value=round(v), method=method,
                              sources=srcs, info=("MY", "PT", "ST"))  # fmt: skip
    return n


def trend_signals(
    engine: sqlite3.Connection, cik: str, ticker: str | None, view: trends.TrendsView
) -> int:
    """The core trend rows as information signals (D-M04-11: no vote until Part 8)."""
    n = 0
    for s in view.signals:
        srcs = [Source(a, f, "A") for a, f in s.sources if a]
        common = dict(engine=engine, cik=cik, ticker=ticker, module_id=MODULE, signal=s.name,
                      as_of=s.as_of, info=("MY", "PT", "ST"))  # fmt: skip
        if s.missing is not None or not srcs:
            n += write_signal(**common, method=s.method, missing=s.missing or "no inputs",
                              sources=srcs)  # fmt: skip
        else:
            n += write_signal(**common, method=s.method, value=s.value, value_text=s.text,
                              sources=srcs)  # fmt: skip
    return n


@dataclass
class Part1b:
    capex: capex.CapexView
    trends: trends.TrendsView
    record: record.Record
    peers: peer_z.Comparison | None = None


def part1b(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    cik: str,
    ticker: str | None,
    now: datetime,
    *,
    peer_cache: dict | None = None,
    covered: set[str] | None = None,
) -> Part1b:
    """Recompute capex split, trend rows and the guidance record; store and signal them.
    The trend signals carry the peer robust z in their method (Part 2, D-M04-11)."""
    today = now.date()
    cv = capex.capex_view(engine, cik, today.isoformat())
    tv = trends.trends_view(engine, cik, today.isoformat(), cv)
    comp = peer_z.compare(engine, ticker or cik, cik, today.isoformat(), cache=peer_cache,
                          covered=covered)  # fmt: skip
    peer_z.annotate(tv, comp)
    rec = record.record_for(engine, corpus, cik, today)
    engine.execute("BEGIN")
    try:
        at = now.isoformat(timespec="seconds")
        capex.store_split(engine, cv, at)
        record.store(engine, rec, at)
        capex_signals(engine, cik, ticker, cv, today.isoformat())
        trend_signals(engine, cik, ticker, tv)
        record.write_signals(engine, rec, ticker, today)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return Part1b(cv, tv, rec, comp)


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
    p1b = {"companies": 0, "split": 0, "scored": 0, "removed": 0, "peer_sets": 0}
    alerts = []
    cache: dict = {}  # peers recur across peer sets: read their facts once per pass
    covered = set(companies.values())
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
            got = part1b(engine, corpus, cik, ticker, now, peer_cache=cache, covered=covered)
            p1b["companies"] += 1
            p1b["peer_sets"] += bool(got.peers and got.peers.confirmed)
            p1b["split"] += sum(1 for y in got.capex.years if y.maintenance is not None)
            p1b["scored"] += got.record.scored
            p1b["removed"] += sum(
                1 for o in got.record.outcomes if o.kind == "removal" and o.outcome == "removed"
            )
        except Exception as e:  # one company's error must not stop the others
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            lines.append(f"  {ticker}: error — {type(e).__name__}: {e}")
    summary = (
        f"filing status: current {counts['current']}, stale {counts['stale']}, "
        f"overdue {counts['overdue']}, no periodic reports {counts['none']}"
    )
    summary += (
        f"; capex/trends/guidance recomputed for {p1b['companies']} companies "
        f"({p1b['split']} split years, {p1b['scored']} scored guides, "
        f"{p1b['removed']} removed guides; peer z for {p1b['peer_sets']} confirmed peer sets)"
    )
    try:
        mf = models.load_safe()
        if mf.error:
            lines.append(f"  model tag file rejected, no tags applied: {mf.error}")
        sp = profile.stage_pass(engine, companies, mf, now)
        opened = sum(1 for v in sp.opened.values() if v == "queued")
        summary += (f"; stages computed for {len(sp.results)} companies, {opened} stage item(s) "
                    f"opened")  # fmt: skip
        lines += sp.errors
    except Exception as e:  # the stage pass must not stop the step
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        lines.append(f"  stage pass: error — {type(e).__name__}: {e}")
    lines.insert(0, summary)
    lines[1:1] = alerts
    head = f"M04 financials — local pass (Parts 1a–2, 0 SEC requests) ({clock() - t0:.1f} s):"
    return [head, *lines]
