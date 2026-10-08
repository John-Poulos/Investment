"""Nightly refresh (M00_STORAGE refresh jobs; D-SEC-15).

One run:
1. Resolve the watchlist tickers (config/watchlist.toml). Unresolved tickers are
   reported every run and kept.
2. Read SEC's daily index (master.YYYYMMDD.idx) for every business day since the
   last day fully processed, plus the previous day again (late Form 4s). Running
   late or missing nights loses nothing: the next run catches up.
3. For each watchlist company that filed (and each company seen for the first
   time, which is backfilled): filing index, events, Form 4s, XBRL facts and the
   documents of new 10-K / 10-Q / 8-K filings.
4. Write a run report (also stored in refresh_run) listing new filings, notable
   events, insider transactions, failures and unresolved tickers.

A daily index that is not found is a market holiday once it is older than a few
days; until then the day stays pending and is retried. A throttle from SEC stops
the run; days not finished stay pending, and every step is safe to repeat.
"""

from __future__ import annotations

import json
import sqlite3
import tomllib
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from engine.sec.client import SecClient, iso
from engine.sec.documents import ingest_filing
from engine.sec.events import build_events, events
from engine.sec.identity import load_entity, normalize_cik, resolve
from engine.sec.insiders import sync_insiders
from engine.sec.results import Failed, NotFound, Ok, Result
from engine.sec.submissions import (
    earnings_releases,
    filing_by_accession,
    stored_filings,
    sync_filings,
)
from engine.sec.xbrl_facts import sync_facts

DAILY_INDEX_URL = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{q}/master.{ymd}.idx"
INDEX_TTL_S = 86400
# SEC's daily index is per US Eastern business day; dates must be Eastern, not UTC
# (live 2026-10-07: a 21:32 ET run is already the next day in UTC).
MARKET_TZ = ZoneInfo("America/New_York")
FACT_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F"}


# --- Config --------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    tickers: tuple[str, ...]
    form4_years: int = 3
    earnings_8k: int = 4
    latest_annual: bool = True
    latest_quarterly: bool = True
    document_forms: tuple[str, ...] = ("10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A")
    recheck_days: int = 1
    holiday_after_days: int = 3


def load_config(path: Path) -> Config:
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    tickers = tuple(dict.fromkeys(t.strip().upper() for t in raw["watchlist"]["tickers"]))
    backfill, nightly = raw.get("backfill", {}), raw.get("nightly", {})
    return Config(
        tickers=tickers,
        form4_years=int(backfill.get("form4_years", 3)),
        earnings_8k=int(backfill.get("earnings_8k", 4)),
        latest_annual=bool(backfill.get("latest_annual", True)),
        latest_quarterly=bool(backfill.get("latest_quarterly", True)),
        document_forms=tuple(nightly.get("document_forms", Config.document_forms)),
        recheck_days=int(nightly.get("recheck_days", 1)),
        holiday_after_days=int(nightly.get("holiday_after_days", 3)),
    )


# --- Daily index ---------------------------------------------------------------


@dataclass(frozen=True)
class IndexEntry:
    cik: str
    company: str
    form: str
    filed: str
    accession: str


def index_url(day: date) -> str:
    q = (day.month - 1) // 3 + 1
    return DAILY_INDEX_URL.format(year=day.year, q=q, ymd=day.strftime("%Y%m%d"))


def parse_master_index(text: str) -> list[IndexEntry]:
    """Rows of a master.idx file: CIK|Company Name|Form Type|Date Filed|Filename."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith("-----")) + 1
    except StopIteration as exc:
        raise ValueError("daily index has no header separator") from exc
    out = []
    for line in lines[start:]:
        parts = line.split("|")
        if len(parts) != 5:
            continue
        cik = normalize_cik(parts[0])
        filename = parts[4].strip()
        if cik is None or not filename.endswith(".txt"):
            continue
        filed = parts[3].strip()
        filed = f"{filed[:4]}-{filed[4:6]}-{filed[6:8]}" if len(filed) == 8 else filed
        accession = filename.rsplit("/", 1)[-1].removesuffix(".txt")
        out.append(IndexEntry(cik, parts[1].strip(), parts[2].strip(), filed, accession))
    return out


def market_date(now: datetime) -> date:
    """Today's date in US Eastern time (SEC's business day)."""
    return now.astimezone(MARKET_TZ).date()


def business_days(start: date, end: date) -> list[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def days_to_read(engine: sqlite3.Connection, today: date, recheck_days: int) -> list[date]:
    """Pending days, every business day after the last finished one up to yesterday,
    and the last `recheck_days` finished business days again."""
    yesterday = today - timedelta(days=1)
    done = engine.execute(
        "SELECT max(day) FROM refresh_day WHERE status IN ('processed', 'no_index')"
    ).fetchone()[0]
    pending = [
        date.fromisoformat(r[0])
        for r in engine.execute("SELECT day FROM refresh_day WHERE status = 'pending'")
    ]
    if done is None:
        recent = business_days(yesterday - timedelta(days=6), yesterday)[-1:]
        return sorted(set(recent) | set(pending))
    last = date.fromisoformat(done)
    new = business_days(last + timedelta(days=1), yesterday)
    finished = business_days(last - timedelta(days=10), last)
    recheck = finished[-recheck_days:] if recheck_days else []
    return sorted(set(new) | set(pending) | set(recheck))


# --- Run -----------------------------------------------------------------------


class Throttled(Exception):
    """SEC throttled us; stop the run (the client's breaker is open)."""


def _check(res: Result[Any], step: str, failures: list[str]) -> Any | None:
    if isinstance(res, Ok):
        return res.data
    if isinstance(res, Failed) and res.throttled:
        raise Throttled(f"{step}: {res.reason}")
    reason = res.reason if isinstance(res, Failed) else str(res)
    failures.append(f"{step}: {reason}")
    return None


@dataclass
class CompanyReport:
    ticker: str
    cik: str
    name: str | None = None
    backfilled: bool = False
    new_filings: list[str] = field(default_factory=list)  # "form accession"
    notable_events: list[str] = field(default_factory=list)  # medium and above, new filings
    insider_rows: int = 0
    insider_trades: list[str] = field(default_factory=list)  # open-market P/S in new Form 4s
    facts: str = "not refreshed"
    documents: int = 0
    failures: list[str] = field(default_factory=list)


@dataclass
class RunReport:
    run_id: int
    trigger: str
    started_at: str
    finished_at: str | None = None
    status: str = "running"
    days: dict[str, str] = field(default_factory=dict)  # day → processed/no_index/pending
    unresolved: dict[str, str] = field(default_factory=dict)  # ticker → what was checked
    watchlist: dict[str, str] = field(default_factory=dict)  # ticker → "name (CIK)"
    companies: list[CompanyReport] = field(default_factory=list)
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {**self.__dict__, "companies": [c.__dict__ for c in self.companies]}, default=str
        )


def _start(engine: sqlite3.Connection, trigger: str, now: datetime) -> int:
    run_id = engine.execute(
        "INSERT INTO refresh_run (trigger, started_at, status) VALUES (?, ?, 'running')",
        (trigger, iso(now)),
    ).lastrowid
    assert run_id is not None
    return run_id


def _mark_day(
    engine: sqlite3.Connection, day: date, status: str, entries: int | None, matched: int | None,
    run_id: int, now: datetime,
) -> None:  # fmt: skip
    engine.execute(
        "INSERT INTO refresh_day (day, status, entries, matched, run_id, processed_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (day) DO UPDATE SET status = excluded.status, "
        "entries = excluded.entries, matched = excluded.matched, run_id = excluded.run_id, "
        "processed_at = excluded.processed_at",
        (day.isoformat(), status, entries, matched, run_id, iso(now)),
    )


def _backfilled(engine: sqlite3.Connection, cik: str) -> bool:
    return (
        engine.execute(
            "SELECT 1 FROM refresh_state WHERE name = ?", (f"backfill:{cik}",)
        ).fetchone()
        is not None
    )


def _mark_backfilled(engine: sqlite3.Connection, cik: str, now: datetime) -> None:
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, 'refresh', "
        "?, NULL) ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at",
        (f"backfill:{cik}", iso(now)),
    )


def _process_company(
    client: SecClient,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    config: Config,
    rep: CompanyReport,
    entries: list[IndexEntry],
    now: datetime,
) -> None:
    cik, fails = rep.cik, rep.failures
    entity = _check(load_entity(client, engine, cik, now), "entity", fails)
    rep.name = entity.name if entity else None

    _check(sync_filings(client, engine, cik, now, fresh=bool(entries)), "filings", fails)
    rep.new_filings = [f"{e.form} {e.accession}" for e in entries]
    _check(build_events(engine, cik), "events", fails)
    new_acc = {e.accession for e in entries}
    for ev in events(engine, cik, min_severity="medium"):
        if ev.accession in new_acc:
            rep.notable_events.append(f"{ev.filed} {ev.form} {ev.item} {ev.severity}: {ev.title}")

    since = (market_date(now) - timedelta(days=365 * config.form4_years)).isoformat()
    ins = _check(sync_insiders(client, engine, cik, now, since=since), "form 4", fails)
    if ins is not None:
        rep.insider_rows = ins.transactions
        fails.extend(f"form 4 {f}" for f in ins.failed)
    form4_acc = [e.accession for e in entries if e.form in ("4", "4/A")]
    if form4_acc:
        marks = ",".join("?" * len(form4_acc))
        for r in engine.execute(
            f"SELECT txn_date, owner_name, role, code, shares, price, is_10b5_1 FROM insider_txn "
            f"WHERE accession IN ({marks}) AND code IN ('P', 'S') ORDER BY txn_date",
            form4_acc,
        ):
            price = "n/a" if r["price"] is None else f"{r['price']:,.2f}"
            plan = {1: "10b5-1", 0: "not 10b5-1", None: "plan n/a"}[r["is_10b5_1"]]
            rep.insider_trades.append(
                f"{r['txn_date']} {r['owner_name']} ({r['role']}) {r['code']} "
                f"{r['shares'] or 0:,.0f} @ {price} [{plan}]"
            )

    force_facts = rep.backfilled or any(e.form in FACT_FORMS for e in entries)
    facts = sync_facts(client, engine, cik, now, force=force_facts)
    if isinstance(facts, NotFound):
        rep.facts = "no XBRL company facts (fund, foreign filer or no XBRL)"
    else:
        data = _check(facts, "facts", fails)
        if data is not None:
            rep.facts = (f"refreshed: {data.facts_new:,} new facts, {data.series_rows:,} series"
                         if data.refreshed else "up to date")  # fmt: skip

    wanted = [e.accession for e in entries if e.form in config.document_forms]
    if rep.backfilled:
        filings = stored_filings(engine, cik)
        if config.latest_annual:
            wanted += [f.accession for f in filings if f.form in ("10-K", "20-F")][:1]
        if config.latest_quarterly:
            wanted += [f.accession for f in filings if f.form == "10-Q"][:1]
        wanted += [f.accession for f in earnings_releases(engine, cik)][: config.earnings_8k]
    for accession in dict.fromkeys(wanted):
        filing = filing_by_accession(engine, accession)
        if filing is None:
            fails.append(f"documents {accession}: not in the filing index yet")
            continue
        docs = _check(ingest_filing(client, corpus, filing, now), f"documents {accession}", fails)
        if docs is not None:
            rep.documents += sum(1 for d in docs.stored if d.new)
            fails.extend(f"documents {accession} {f}" for f in docs.failed)

    if rep.backfilled and not fails:
        _mark_backfilled(engine, cik, now)


def run_refresh(
    client: SecClient,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    config: Config,
    now: datetime,
    *,
    trigger: str = "manual",
) -> RunReport:
    run_id = _start(engine, trigger, now)
    report = RunReport(run_id, trigger, iso(now))
    try:
        watch: dict[str, str] = {}  # cik → ticker
        for ticker in config.tickers:
            res = resolve(client, engine, ticker, now)
            if isinstance(res, Ok):
                watch.setdefault(res.data, ticker)
                row = engine.execute(
                    "SELECT name FROM entity WHERE cik = ?", (res.data,)
                ).fetchone()
                name = row[0] if row else "name not loaded yet"
                report.watchlist[ticker] = f"{name} ({res.data})"
            elif isinstance(res, Failed) and res.throttled:
                raise Throttled(f"resolve {ticker}: {res.reason}")
            else:
                checked = getattr(res, "paths_checked", ()) or ()
                report.unresolved[ticker] = "; ".join(
                    f"{p.path}: {p.result}" for p in checked
                ) or str(res)

        today = market_date(now)
        days = days_to_read(engine, today, config.recheck_days)
        recent = {d for d in days if (today - d).days <= config.recheck_days + 1}
        matched: dict[str, list[IndexEntry]] = {}
        day_status: dict[date, tuple[str, int | None, int | None]] = {}
        for day in days:
            res = client.get_text(index_url(day), ttl_s=INDEX_TTL_S, fresh=day in recent)
            missing = isinstance(res, NotFound) or (
                isinstance(res, Failed) and res.status == 403 and not res.throttled
            )  # Archives answer 403 for an index not published yet
            if missing:
                old = (today - day).days > config.holiday_after_days
                day_status[day] = ("no_index" if old else "pending", None, None)
                continue
            text = _check(res, f"daily index {day}", [])
            if text is None:
                day_status[day] = ("pending", None, None)
                continue
            entries = parse_master_index(text)
            hits = [e for e in entries if e.cik in watch]
            for e in hits:
                matched.setdefault(e.cik, []).append(e)
            day_status[day] = ("processed", len(entries), len(hits))

        todo = sorted(set(matched) | {c for c in watch if not _backfilled(engine, c)})
        for cik in todo:
            rep = CompanyReport(watch[cik], cik, backfilled=not _backfilled(engine, cik))
            report.companies.append(rep)
            entries = list({e.accession: e for e in matched.get(cik, [])}.values())
            try:
                _process_company(client, engine, corpus, config, rep, entries, now)
            except Throttled:
                raise
            except Exception as exc:  # one company's error must not stop the others
                if engine.in_transaction:
                    engine.execute("ROLLBACK")
                if corpus.in_transaction:
                    corpus.execute("ROLLBACK")
                where = traceback.extract_tb(exc.__traceback__)[-1]
                rep.failures.append(
                    f"internal error: {type(exc).__name__}: {exc} "
                    f"({Path(where.filename).name}:{where.lineno})"
                )

        for day, (status, n, m) in day_status.items():
            _mark_day(engine, day, status, n, m, run_id, now)
            report.days[day.isoformat()] = status
        failed = any(c.failures for c in report.companies) or any(
            s == "pending" for s, _, _ in day_status.values()
        )
        report.status = "partial" if failed else "ok"
    except Throttled as exc:
        report.status, report.error = "partial", f"stopped by SEC throttle: {exc}"
    except Exception as exc:  # recorded, then re-raised for the log
        report.status, report.error = "failed", f"{type(exc).__name__}: {exc}"
        _finish(engine, report, now)
        raise
    _finish(engine, report, now)
    return report


def _finish(engine: sqlite3.Connection, report: RunReport, now: datetime) -> None:
    report.finished_at = iso(now)
    engine.execute(
        "UPDATE refresh_run SET finished_at = ?, status = ?, days = ?, companies = ?, "
        "report = ?, error = ? WHERE run_id = ?",
        (report.finished_at, report.status, json.dumps(report.days), len(report.companies),
         report.to_json(), report.error, report.run_id),
    )  # fmt: skip


def last_success(engine: sqlite3.Connection) -> str | None:
    """Start of the last run that completed (ok, or partial with only per-item
    failures). Runs stopped by a throttle or an error do not count."""
    row = engine.execute(
        "SELECT max(started_at) FROM refresh_run "
        "WHERE status = 'ok' OR (status = 'partial' AND error IS NULL)"
    ).fetchone()
    return row[0] if row else None


def format_report(report: RunReport) -> str:
    lines = [
        f"Nightly SEC refresh — run {report.run_id} ({report.trigger})",
        f"started {report.started_at}  finished {report.finished_at}  status {report.status}",
    ]
    if report.error:
        lines.append(f"ERROR: {report.error}")
    lines.append("index days: " + (", ".join(f"{d} {s}" for d, s in report.days.items()) or "none"))
    if report.watchlist:
        lines.append("watchlist: " + "; ".join(f"{t} = {n}" for t, n in report.watchlist.items()))
    if report.unresolved:
        lines.append("unresolved tickers (kept on the watchlist):")
        lines += [f"  {t}: {why}" for t, why in report.unresolved.items()]
    if not report.companies:
        lines.append("no watchlist company filed; nothing to update")
    for c in report.companies:
        head = f"{c.ticker} {c.name or ''} (CIK {c.cik})" + (" — first run: backfilled" if
                                                            c.backfilled else "")  # fmt: skip
        lines.append("")
        lines.append(head)
        if c.new_filings:
            lines.append(f"  new filings: {', '.join(c.new_filings)}")
        lines += [f"  event: {e}" for e in c.notable_events]
        lines += [f"  insider: {t}" for t in c.insider_trades]
        lines.append(f"  form 4 rows parsed: {c.insider_rows}; facts: {c.facts}; "
                     f"documents stored: {c.documents}")  # fmt: skip
        lines += [f"  FAILED {f}" for f in c.failures]
    return "\n".join(lines) + "\n"
