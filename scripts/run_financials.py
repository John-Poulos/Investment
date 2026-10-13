"""M04 Financials: one owner script, one subcommand per build part (D-M04-69).

    uv run python scripts/run_financials.py data             # Part 1a live check
    uv run python scripts/run_financials.py data --no-sec    # local re-run, 0 SEC requests
    uv run python scripts/run_financials.py capex            # Part 1b live check
    uv run python scripts/run_financials.py capex --no-sec   # local re-run, 0 SEC requests
    uv run python scripts/run_financials.py profile          # Part 1c live check
    uv run python scripts/run_financials.py profile --no-sec # local re-run, 0 SEC requests
    uv run python scripts/run_financials.py --list           # the subcommand table

Subcommands: data (1a) · capex (1b) · profile (1c) · peers (2) · flags (3) · gate (4a) ·
gate-text (4b) · issuance (5) · quality (6) · units (7a) · margins (7b) · cvd (8a) ·
backtest (8b). Parts not built yet print "not built, Part n".

`data` (Part 1a): rebuilds every covered company's series from stored facts (parser
facts-2, 0 requests); reads the R1 cover pages of the multi-class filers' 10-K/10-Q filings
of the last 3 years (GOOG, META, MSTR, SPCX: ~37 requests); fetches Western Digital's two
revenue companyconcept files for the as-of check (2 requests); evaluates filing status for
every covered company; prints the extra-tag report, the GFS 6-K sync rule and a summary.

`capex` (Part 1b): reads NVIDIA's FY2013–FY2021 10-K XBRL instances (filing index page +
instance per filing, ~18 requests; each instance is parsed, its extension facts stored and
the file dropped from http_cache, SB.16), rebuilds NVIDIA's series (0 requests), then
recomputes for every covered company the capex split, core trend rows, ROIC and the
guidance record (0 requests) and prints what the owner looks for.

`profile` (Part 1c): loads config/company_models.toml (unknown tags rejected); reads EDGAR's
browse-by-SIC lists for every SIC of the core and promoted companies (one browse per SIC,
at most 10 pages per SIC, at most 90 pages; pages re-used for 7 days; SIC 3674's full list
goes to the log: the S1 re-probe), 3 revenue frames for the ranking year and 2 for the
year before (suspect guard); ranks each company's peer shortlist by revenue closeness among
active filers (stored form indexes, 0 requests), suspect revenue last; opens the
setup batch (one `m04_stage` and one `m04_peer` item per company, outside the weekly cap);
writes `lifecycle_stage`; prints what the owner looks for. `--no-sec` re-ranks from stored
lists and frames.

Takes data/refresh.lock (one SEC process at a time). Writes
logs/financials_<subcommand>_<YYYYMMDD-HHMMSS>.txt as it goes, with requests, MB and
seconds per fetch type, rows added per table and engine.db size before and after; its own
tracebacks go to the log too, so the log is all the owner sends back.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SUBCOMMANDS = (
    ("data", "1a", "as-of facts, share series, R1 covers, filing status"),
    ("capex", "1b", "capex definitions, capex split, ROIC, trends, guidance record"),
    ("profile", "1c", "model tags, stage, M04 queue, peer shortlist"),
    ("peers", "2", "peer facts and statistics"),
    ("flags", "3", "restatements, filing events, prior filings"),
    ("gate", "4a", "survival gate: numbers"),
    ("gate-text", "4b", "survival gate: text"),
    ("issuance", "5", "dilution and financing pressure"),
    ("quality", "6", "earnings quality"),
    ("units", "7a", "unit and dimensional data"),
    ("margins", "7b", "R12, unit economics, customers"),
    ("cvd", "8a", "CvD assembly, health vote, M04 tab"),
    ("backtest", "8b", "calibration"),
)
BUILT = {"data", "capex", "profile"}
NVDA_CIK = "0001045810"
NVDA_YEARS = range(2013, 2022)  # FY2013–FY2021: capex only under the extension tag
WDC_CIK = "0000106040"
WDC_TAGS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")
COUNTED_TABLES = ("fact", "series", "cover_shares", "filing_status", "signal", "entity_link",
                  "entity", "refresh_state", "fetch_log", "capex_split",
                  "guidance_outcome", "company_stage", "m04_proposal", "peer_candidate",
                  "sic_listing", "frame_value", "review_queue")  # fmt: skip


class Log:
    """Lines go to the console and to the log file as they are produced."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(exist_ok=True)
        self._fh = path.open("w", encoding="utf-8")

    def __call__(self, *lines: str) -> None:
        for line in lines:
            print(line)
            self._fh.write(line + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def fetch_type(url: str) -> str:
    if "/cgi-bin/browse-edgar" in url:
        return "browse-by-SIC"
    if "/api/xbrl/frames/" in url:
        return "frames"
    if "/companyconcept/" in url:
        return "companyconcept"
    if "/companyfacts/" in url:
        return "companyfacts"
    if url.rsplit("/", 1)[-1].startswith("R") and url.endswith((".htm", ".xml")):
        return "R page"
    if url.endswith(("-index.htm", "-index.html")):
        return "filing index"
    if url.endswith(".xml"):
        return "XBRL instance"
    if "/submissions/" in url:
        return "submissions"
    return "other"


class CountingLog:
    """Wraps the fetch log: requests sent, cache hits and bytes per fetch type."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.sent: dict[str, int] = defaultdict(int)
        self.cached: dict[str, int] = defaultdict(int)
        self.bytes: dict[str, int] = defaultdict(int)
        self.seconds: dict[str, float] = defaultdict(float)

    def write(self, url, outcome, detail, status, from_cache, at) -> None:
        self.inner.write(url, outcome, detail, status, from_cache, at)
        kind = fetch_type(url)
        if from_cache:
            self.cached[kind] += 1
            return
        self.sent[kind] += 1
        if outcome == "ok" and detail.endswith(" bytes"):
            self.bytes[kind] += int(detail.split()[0])

    def lines(self) -> list[str]:
        kinds = sorted(set(self.sent) | set(self.cached) | set(self.seconds))
        out = ["SEC requests by fetch type (sent · cache hits · MB · seconds):"]
        for k in kinds:
            out.append(f"  {k}: {self.sent[k]} · {self.cached[k]} · {self.bytes[k] / 1e6:.2f} MB · "
                       f"{self.seconds[k]:.1f} s")  # fmt: skip
        out.append(f"  total sent: {sum(self.sent.values())}")
        return out


def db_mb(folder: Path) -> float:
    return sum((folder / n).stat().st_size for n in ("engine.db", "engine.db-wal")
               if (folder / n).exists()) / 1e6  # fmt: skip


def counts(engine) -> dict[str, int]:
    return {t: engine.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in COUNTED_TABLES}


def companies(engine) -> dict[str, str]:
    from engine.calls.transcripts import symbol_cik
    from engine.refresh import load_config
    from engine.themes import tiers

    out: dict[str, str] = {}
    for t in load_config(ROOT / "config" / "watchlist.toml").tickers:
        if cik := symbol_cik(engine, t):
            out[t] = cik
    for m in tiers.members(engine):
        out.setdefault(m.ticker, m.cik)
    return out


# --- data (Part 1a) ------------------------------------------------------------------------


def extra_tag_report(engine, comps: dict[str, str]) -> list[str]:
    """Per company: M04 concepts (share series and the S1.3 extra list) with no stored fact."""
    from engine.sec.xbrl_facts import CONCEPT_BY_NAME, EXTRA_CONCEPTS, concept_for

    wanted = [CONCEPT_BY_NAME[n] for n in ("shares_period_end", "shares_cover",
              "shares_basic_wavg", "shares_diluted_wavg", "sbc", "public_float", "da",
              "ppe_net")] + list(EXTRA_CONCEPTS)  # fmt: skip
    lines = [
        f"Extra-tag report: M04 concepts with no fact for the company ({len(wanted)} checked):"
    ]
    for ticker, cik in sorted(comps.items()):
        if engine.execute("SELECT 1 FROM fact WHERE cik = ? LIMIT 1", (cik,)).fetchone() is None:
            lines.append(f"  {ticker}: no XBRL facts stored")
            continue
        missing = []
        for c in wanted:
            con = concept_for(cik, c)
            clauses = " OR ".join("(taxonomy = ? AND tag = ?)" for _ in con.tags)
            args = [cik] + [x for pair in con.tags for x in pair]
            if engine.execute(f"SELECT 1 FROM fact WHERE cik = ? AND ({clauses}) LIMIT 1",
                              args).fetchone() is None:  # fmt: skip
                missing.append(c.name)
        lines.append(f"  {ticker}: missing {len(missing)} of {len(wanted)}"
                     + (f": {', '.join(missing)}" if missing else ""))  # fmt: skip
    return lines


def gfs_6k_lines(engine, comps: dict[str, str], today: str) -> list[str]:
    from engine.sec.asof import is_foreign_filer
    from engine.sec.xbrl_facts import forces_facts

    since = (datetime.fromisoformat(today) - timedelta(days=400)).date().isoformat()
    lines = ["6-K facts-sync rule (SB.11): a 6-K forces a companyfacts sync only with XBRL:"]
    found = False
    for ticker, cik in sorted(comps.items()):
        if not is_foreign_filer(engine, cik):
            continue
        found = True
        rows = engine.execute(
            "SELECT f.accession, f.filed, f.is_xbrl FROM filing f JOIN filing_cik c ON "
            "c.accession = f.accession WHERE c.cik = ? AND f.form IN ('6-K', '6-K/A') AND "
            "f.filed >= ? ORDER BY f.filed DESC",
            (cik, since),
        ).fetchall()
        sync = [r for r in rows if forces_facts("6-K", r["is_xbrl"])]
        lines.append(f"  {ticker}: {len(rows)} 6-K(s) since {since}; {len(sync)} with XBRL force a "
                     f"sync, {len(rows) - len(sync)} wait for the 7-day backstop")  # fmt: skip
        for r in rows[:6]:
            flag = {1: "XBRL → sync", 0: "no XBRL → no sync", None: "XBRL flag unknown → no sync"}
            lines.append(f"    {r['filed']} {r['accession']}: {flag[r['is_xbrl']]}")
    if not found:
        lines.append("  no 20-F/40-F filer among the covered companies")
    return lines


def cover_summary(engine, comps: dict[str, str]) -> list[str]:
    from engine.financials import shares

    lines = ["Cover counts (latest per company; per class where read from R1):"]
    split_hits = []
    for ticker, cik in sorted(comps.items()):
        covers = shares.cover_counts(engine, cik)
        for v in covers:
            if v.note.startswith("split-adjusted"):
                split_hits.append(f"  {ticker} {v.date} {v.accession}: {v.note}")
        if not covers:
            lines.append(f"  {ticker}: missing: {shares.cover_missing_reason(engine, cik)}")
            continue
        v = covers[0]
        parts = (" + ".join(f"{c} {n:,.0f}" for c, n in v.classes) + " = ") if v.classes else ""
        lines.append(f"  {ticker}: {parts}{v.value:,.0f} at {v.date} ({v.tag}; {v.accession})"
                     + (f"; {v.note}" if v.note else ""))  # fmt: skip
    per_co: dict[str, int] = {}
    for h in split_hits:
        per_co[h.split()[0]] = per_co.get(h.split()[0], 0) + 1
    lines.append(
        f"Split-guard hits: {len(split_hits)} (older counts scaled to today; raw stored as filed)"
    )
    lines.append("  " + " · ".join(f"{k} {n}" for k, n in sorted(per_co.items())))
    lines += [h for h in split_hits if not h.split()[0].startswith("AAPL")][:15]
    not_cover = engine.execute(
        "SELECT name, detail FROM refresh_state WHERE name LIKE 'r1:%' AND detail LIKE "
        '\'%"outcome": "not_cover"%\''
    ).fetchall()
    lines.append(f"R1 pages read as not a cover: {len(not_cover)}")
    lines += [f"  {r['name'][3:]}" for r in not_cover[:20]]
    return lines


def wdc_check(client, engine, log: Log, clog: CountingLog, today: str) -> None:
    from engine.sec.asof import facts_as_of
    from engine.sec.results import Ok
    from engine.sec.xbrl_facts import CONCEPT_URL, store_concept

    t0 = time.monotonic()
    for tag in WDC_TAGS:
        url = CONCEPT_URL.format(cik=WDC_CIK, taxonomy="us-gaap", tag=tag)
        res = client.get_json(url, ttl_s=30 * 86400)
        if not isinstance(res, Ok):
            log(f"  WDC {tag}: {res}")
            continue
        engine.execute("BEGIN")
        seen, new = store_concept(engine, WDC_CIK, res.data)
        engine.execute("COMMIT")
        log(f"  WDC us-gaap:{tag}: {seen} facts, {new} new")
    clog.seconds["companyconcept"] += time.monotonic() - t0
    for as_of in ("2024-12-31", today):
        p = facts_as_of(engine, WDC_CIK, "revenue", as_of).get("2023-06-30", "FY")
        if p is None:
            log(f"  WDC FY2023 revenue as of {as_of}: missing")
        else:
            log(f"  WDC FY2023 revenue as of {as_of}: {p.value / 1e6:,.0f}M ({p.accession}, "
                f"filed {p.filed}); first {p.first_value / 1e6:,.0f}M filed {p.first_filed}; "
                f"{p.method}")  # fmt: skip


def run_data(args, log: Log, folder: Path) -> int:
    from engine.financials import shares
    from engine.financials.step import read_covers, run_local_part
    from engine.sec.cover import r1_done
    from engine.sec.identity import stored_category
    from engine.sec.xbrl_facts import PARSER_VERSION, rebuild_series
    from engine.store.db import open_db
    from engine.store.http import SqliteCache, SqliteFetchLog

    engine = open_db("engine", folder)
    corpus = open_db("corpus", folder, check_same_thread=False)
    now = datetime.now(UTC)
    today = now.date().isoformat()
    mb_before, before = db_mb(folder), counts(engine)
    comps = companies(engine)
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    head = f"run_financials data · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} companies"
    log(head + (" · no SEC" if args.no_sec else ""), f"engine.db before: {mb_before:,.1f} MB", "")

    t0 = time.monotonic()
    built = rows = 0
    for _, cik in sorted(comps.items()):
        b, r = rebuild_series(engine, cik)
        built, rows = built + b, rows + r
    log(f"Series rebuilt from stored facts ({PARSER_VERSION}, 0 requests): {len(comps)} companies, "
        f"{built} concept series, {rows:,} rows ({time.monotonic() - t0:.1f} s)")  # fmt: skip

    filled = 0
    for _, cik in sorted(comps.items()):
        row = engine.execute("SELECT category FROM entity WHERE cik = ?", (cik,)).fetchone()
        if row is not None and not row["category"]:
            cat, _ = stored_category(corpus, cik)
            if cat:
                engine.execute("UPDATE entity SET category = ? WHERE cik = ?", (cat, cik))
                filled += 1
    log(f"Filer categories filled from cached submissions files (0 requests): {filled}", "")

    clog = None
    if not args.no_sec:
        from engine.sec.client import SecClient, user_agent_from_env

        clog = CountingLog(SqliteFetchLog(engine))
        client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=clog)
        since = (now - timedelta(days=365 * args.years)).date().isoformat()
        todo = []
        for ticker, cik in sorted(comps.items()):
            if not shares.needs_r1(engine, cik):
                continue
            marks = ",".join("?" * 4)
            for f in engine.execute(
                f"SELECT f.accession, f.form, f.filed, f.report_date FROM filing f JOIN "
                f"filing_cik c ON c.accession = f.accession WHERE c.cik = ? AND f.form IN "
                f"({marks}) AND f.filed >= ? ORDER BY f.filed",
                (cik, "10-K", "10-Q", "10-KT", "10-QT", since),
            ):
                if not r1_done(engine, f["accession"]):
                    todo.append((ticker, cik, f))
        multi = sorted({t for t, _, _ in todo})
        log(f"R1 cover pages: multi-class filers {', '.join(multi) or 'none'}; {len(todo)} "
            f"filing(s) of the last {args.years} years not read yet")  # fmt: skip
        t1 = time.monotonic()
        lines, n = read_covers(client, engine, todo, now, budget_s=900)
        clog.seconds["R page"] += time.monotonic() - t1
        log(*lines)
        log(f"  read {n['cover']}, not a cover {n['not_cover']}, not found {n['not_found']}, "
            f"failed {n['failed']}, pending {n['pending']}", "")  # fmt: skip
        log("Western Digital as-of check (2 companyconcept files):")
        wdc_check(client, engine, log, clog, today)
        log("")
    else:
        log("SEC skipped (--no-sec): no R1 pages, no WDC companyconcept files", "")

    log(*run_local_part(engine, corpus, comps, now))
    log("")
    log(*extra_tag_report(engine, comps))
    log("")
    log(*gfs_6k_lines(engine, comps, today))
    log("")
    log("=== Summary (what the owner looks for) ===")
    log(*cover_summary(engine, comps))
    log("Filing status, all covered companies:")
    for ticker, cik in sorted(comps.items()):
        r = engine.execute(
            "SELECT * FROM filing_status WHERE cik = ? ORDER BY filed IS NOT NULL, period_end DESC "
            "LIMIT 1",
            (cik,),
        ).fetchone()
        if r is None:
            log(f"  {ticker}: not evaluated (no 10-K, 10-Q or 20-F stored)")
        else:
            log(f"  {ticker}: {r['status']} — {r['form']} {r['period_end']}, due {r['due_date']}, "
                f"filed {r['filed'] or '—'}; {r['category'] or 'category unknown'} "
                f"({r['category_source']}); {r['note']}")  # fmt: skip
    if clog is not None:
        log(*clog.lines())
    after = counts(engine)
    log(
        "Rows added per table: "
        + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in COUNTED_TABLES)
    )
    log(f"engine.db: {mb_before:,.1f} MB → {db_mb(folder):,.1f} MB")
    corpus.close()
    engine.close()
    return 0


# --- capex (Part 1b) -----------------------------------------------------------------------


def nvda_filings(engine) -> list:
    """NVIDIA's original 10-Ks for fiscal years 2013–2021, from the stored filing index."""
    from engine.financials.capex import fiscal_label

    rows = engine.execute(
        "SELECT f.accession, f.form, f.filed, f.report_date, f.primary_doc FROM filing f "
        "JOIN filing_cik c ON c.accession = f.accession WHERE c.cik = ? AND f.form = '10-K' "
        "AND f.report_date IS NOT NULL ORDER BY f.report_date",
        (NVDA_CIK,),
    ).fetchall()
    want = {f"FY{y}" for y in NVDA_YEARS}
    return [r for r in rows if fiscal_label(r["report_date"]) in want]


def nvda_instances(client, engine, corpus, log: Log, clog: CountingLog, now) -> None:
    """Read NVIDIA's FY2013–21 10-K instances: index page → instance → extension facts."""
    from engine.moneyflow.instance import find_instance, store_instance
    from engine.sec.client import cache_key
    from engine.sec.results import Failed, Ok
    from engine.sec.submissions import sync_filings
    from engine.sec.xbrl_facts import rebuild_series

    t0 = time.monotonic()
    filings = nvda_filings(engine)
    if len(filings) < len(NVDA_YEARS):
        log(f"  stored index has {len(filings)} of {len(NVDA_YEARS)} NVIDIA 10-Ks; syncing the "
            "submissions pages")  # fmt: skip
        res = sync_filings(client, engine, NVDA_CIK, now)
        log(f"  submissions sync: {res}")
        filings = nvda_filings(engine)
    done = {
        r[0][len("xbrl_instance:") :]
        for r in engine.execute("SELECT name FROM refresh_state WHERE name LIKE 'xbrl_instance:%'")
    }
    already = sum(f["accession"] in done for f in filings)
    log(f"  {len(filings)} 10-K filing(s) FY2013–FY2021; {already} instance(s) already read")
    for f in filings:
        if f["accession"] in done:
            continue
        where = f"{f['report_date']} {f['accession']}"
        found = find_instance(client, NVDA_CIK, f["accession"])
        if not isinstance(found, Ok):
            log(f"  {where}: {found}")
            if isinstance(found, Failed) and found.throttled:
                log("  SEC throttle: the rest waits for the next run")
                break
            continue
        url = found.data
        before = clog.bytes["XBRL instance"]
        res = store_instance(client, engine, NVDA_CIK, dict(f), now, url=url)
        corpus.execute("DELETE FROM http_cache WHERE cache_key = ?", (cache_key(url, None),))
        mb = (clog.bytes["XBRL instance"] - before) / 1e6
        name = url.rsplit("/", 1)[-1]
        if isinstance(res, Ok):
            log(f"  {where}: {name} ({mb:.1f} MB, dropped from cache): {res.data} new facts")
        else:
            log(f"  {where}: {name}: {res}")
            if isinstance(res, Failed) and res.throttled:
                log("  SEC throttle: the rest waits for the next run")
                break
    clog.seconds["XBRL instance"] += time.monotonic() - t0
    b, r = rebuild_series(engine, NVDA_CIK)
    log(f"  NVIDIA series rebuilt from stored facts (0 requests): {b} concept series, {r} rows")


def capex_summary(ticker: str, got) -> list[str]:
    """What the owner looks for, one company."""
    from engine.financials.views import m

    cv, tv, rec = got.capex, got.trends, got.record
    out = []
    if not cv.years:
        out.append(f"  {ticker}: capex missing: no capex tag stored")
    else:
        y = cv.years[-1]
        t = y.total
        line = f"  {ticker}: total capex = {cv.definition}"
        if cv.definition_mark:
            line += f" [{cv.definition_mark}]"
        line += f"; company definition: {cv.recipe_label}"
        if cv.changed_years:
            line += f"; definition changed: {', '.join(cv.changed_years)}"
        out.append(line)
        disp = f"{m(y.display.shown)}M ({y.display_label})" if y.display else "missing"
        out.append(f"    {y.label}: total {m(t.value) if t else '—'}M · company definition {disp}")
        out.append(
            f"    split: {y.method}; maintenance {m(y.maintenance)}M, growth {m(y.growth)}M; "
            f"{cv.gw_line('net')}; {cv.gw_line('gross')}"
        )
        oe = f"{m(y.owner_earnings)}M"
        if y.owner_earnings is None:
            oe += f" ({y.missing('owner_earnings')})"
        out.append(
            f"    FCF on total capex {m(y.fcf_total)}M · on maintenance {m(y.fcf_maintenance)}M"
            f" · owner earnings {oe}"
        )
        for yy in cv.years:
            for mk in yy.marks:
                out.append(f"    {yy.label}: {mk}")
    parts = []
    for s in tv.signals:
        if s.missing is not None:
            parts.append(f"{s.name} missing: {s.missing}")
        elif s.text:
            parts.append(f"{s.name} n/m")
        elif s.name in ("gm_trend_pp", "opex_vs_sales"):
            parts.append(f"{s.name} {s.value:+.1f} pp")
        else:
            parts.append(f"{s.name} {s.value:+.1%}")
    roic = next((r for r in tv.rows if r.key == "roic"), None)
    if roic and tv.labels:
        c = roic.cells.get(tv.labels[-1])
        shown = f"{c.value:.1%}" if c and c.value is not None else (c.text if c else "missing")
        parts.append(f"ROIC {tv.labels[-1]} {shown}")
    out.append("    trends: " + " · ".join(parts))
    if rec.scored:
        g = f"hit rate {100 * rec.hits / rec.scored:.0f}% ({rec.hits}/{rec.scored})"
        g += "; repeated" if rec.repeated else ""
    else:
        g = f"hit rate missing: {rec.missing}"
    counts: dict[str, int] = {}
    for o in rec.outcomes:
        if o.kind == "score":
            counts[o.outcome] = counts.get(o.outcome, 0) + 1
    g += " · outcomes " + (", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "none")
    out.append(f"    guidance: {g}")
    removed = [o for o in rec.outcomes if o.kind == "removal"]
    for o in sorted(removed, key=lambda o: o.release_filed)[-6:]:
        why = f" “{o.reason[2][:140]}”" if o.reason else ""
        out.append(
            f"      {o.outcome}: {o.metric} {o.period} (release {o.release_filed}; {o.state}){why}"
        )
    approx = [o for o in rec.outcomes if o.kind == "score" and o.outcome == "unscored"
              and o.state.startswith("capex recipe approximate")]  # fmt: skip
    for o in approx[-2:]:
        out.append(f"      unscored: capex {o.period} guide {o.guide_text}: {o.state}")
    misses = [o for o in rec.outcomes if o.kind == "score" and o.outcome == "miss"]
    for o in misses[-4:]:
        out.append(
            f"      miss: {o.metric} {o.basis} {o.period} guide {o.guide_text}, "
            f"actual {o.actual:,.2f}"
        )
    return out


def run_capex(args, log: Log, folder: Path) -> int:
    from engine.financials.capex import total_capex
    from engine.financials.step import part1b
    from engine.store.db import open_db
    from engine.store.http import SqliteCache, SqliteFetchLog

    engine = open_db("engine", folder)
    corpus = open_db("corpus", folder, check_same_thread=False)
    now = datetime.now(UTC)
    mb_before, before = db_mb(folder), counts(engine)
    comps = companies(engine)
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    head = f"run_financials capex · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} companies"
    log(head + (" · no SEC" if args.no_sec else ""), f"engine.db before: {mb_before:,.1f} MB", "")

    clog = None
    if not args.no_sec:
        from engine.sec.client import SecClient, user_agent_from_env

        clog = CountingLog(SqliteFetchLog(engine))
        client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=clog)
        log(
            "NVIDIA FY2013–FY2021 capex from 10-K XBRL instances "
            "(nvda:PurchasesOfPropertyAndEquipmentAndIntangibleAssets):"
        )
        nvda_instances(client, engine, corpus, log, clog, now)
        log("")
    else:
        log("SEC skipped (--no-sec): NVIDIA instances not read; stored facts used")
        if NVDA_CIK in comps.values():
            from engine.sec.xbrl_facts import rebuild_series

            b, r = rebuild_series(engine, NVDA_CIK)
            log(f"  NVIDIA series rebuilt from stored facts (0 requests): {b} concept series, "
                f"{r} rows")  # fmt: skip
        log("")

    t0 = time.monotonic()
    results = {}
    for ticker, cik in sorted(comps.items()):
        try:
            results[ticker] = part1b(engine, corpus, cik, ticker, now)
        except Exception as e:  # one company's error must not stop the others
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            log(f"  {ticker}: error — {type(e).__name__}: {e}")
    log(
        f"Capex split, trends, ROIC and guidance record recomputed for {len(results)} companies "
        f"(0 requests, {time.monotonic() - t0:.1f} s)",
        "",
    )

    log("=== Summary (what the owner looks for) ===")
    log(
        "Per company: total-capex definition and marker, definition-changed years, split rung, "
        "Greenwald in range, FCF, trend rows, guidance outcomes:"
    )
    for ticker, got in sorted(results.items()):
        log(*capex_summary(ticker, got))
    if NVDA_CIK in comps.values():
        rows = [t for t in total_capex(engine, NVDA_CIK, now.date().isoformat())
                if t.label <= "FY2022"]  # fmt: skip
        log("NVIDIA pre-FY2022 capex (own history; expected FY2013 183.3M, FY2021 1,128.0M):")
        shown = " · ".join(f"{t.label} {t.value / 1e6:,.1f}M ({t.tag.split(':')[0]})" for t in rows)
        log("  " + (shown or "none stored"))
    if clog is not None:
        log(*clog.lines())
    else:
        log("SEC requests: 0 (--no-sec)")
    after = counts(engine)
    log(
        "Rows added per table: "
        + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in COUNTED_TABLES)
    )
    log(f"engine.db: {mb_before:,.1f} MB → {db_mb(folder):,.1f} MB")
    corpus.close()
    engine.close()
    return 0


# --- profile (Part 1c) ---------------------------------------------------------------------


S1_SIC = "3674"  # the S1 re-probe: full list to the log (SB.17)


def profile_summary(engine, mf, sp, pp, now) -> list[str]:
    """What the owner looks for (M04_BUILD_LOG Part 1c live check)."""
    from engine.financials import peers, stage
    from engine.sec.browse import BROWSE_FORM

    lines = ["=== Summary (what the owner looks for) ==="]
    if mf.error:
        lines.append(f"Model tag file {mf.path}: REJECTED — {mf.error}")
    else:
        lines.append(
            f"Model tag file {mf.path}: loaded with {len(mf.entries)} entries: "
            + "; ".join(f"{e.ticker or e.cik} {e.tag} ({e.scope})" for e in mf.entries)
        )
    review = [t for t, r in sorted(sp.results.items()) if r.reasons]
    lines.append(f"Stages computed: {len(sp.results)}; all go to the setup batch (first "
                 f"confirmation); with an ambiguity as well: {len(review)} — "
                 f"{', '.join(review) or 'none'}")  # fmt: skip
    for ticker, r in sorted(sp.results.items()):
        held = stage.STAGE_NAMES[r.computed] if r.computed else "none holds"
        why = ", ".join(stage.REASONS[c] for c in r.reasons) or "plain (first confirmation only)"
        cagr = f"{r.cagr3:+.1%}" if r.cagr3 is not None else r.cagr_note
        lines.append(f"  {ticker}: {held} ({r.label}; CAGR 3y {cagr}); {why}")
    for ticker, how in sorted(sp.excluded.items()):
        lines.append(f"  {ticker}: no stage — {how}")
    lines.append(
        f"Setup stage items: {sum(v == 'queued' for v in sp.opened.values())} queued "
        f"now, {sum(v == 'suppressed' for v in sp.opened.values())} already open"
    )
    lines.append("Peer shortlists per SIC (listed · active = 10-K/20-F/40-F in 12 months):")
    by_sic: dict = {}
    for ticker, s in sorted(pp.shortlists.items()):
        by_sic.setdefault(s.sic, []).append((ticker, s))
    for sic, rows in sorted(by_sic.items(), key=lambda kv: (kv[0] is None, kv[0] or "")):
        if sic is None:
            continue
        ciks = [r[0] for r in engine.execute("SELECT DISTINCT cik FROM sic_listing WHERE sic = ?",
                                             (sic,))]  # fmt: skip
        act = peers.active_filers(engine, ciks, now.date())
        foreign = sum(1 for f, _ in act.values() if f.split("/")[0] in ("20-F", "40-F"))
        b = engine.execute("SELECT pages, capped FROM sic_browse WHERE sic = ? AND browsed = ?",
                           (sic, BROWSE_FORM)).fetchone()  # fmt: skip
        how = (f"browse {b['pages']} page(s)" + (" PARTIAL (cap)" if b["capped"] else "")
               if b else "not browsed")  # fmt: skip
        lines.append(
            f"  SIC {sic}: listed {len(ciks)} ({how}); active "
            f"{len(act)} ({len(act) - foreign} on 10-K, {foreign} on 20-F/40-F)"
        )
        for ticker, s in rows:
            names = "; ".join(
                f"{c.rank}. {c.name}"
                + (f" {c.revenue / 1e9:,.1f}B" if c.revenue else " (revenue missing)")
                + (f" (revenue suspect: {c.suspect})" if c.suspect else "")
                for c in s.candidates
            )
            tv = f"{s.target_revenue / 1e9:,.1f}B" if s.target_revenue else "missing"
            lines.append(f"    {ticker} (revenue {tv}): {len(s.candidates)} — {names or s.note}")
        suspects = sorted({(n, w) for _, s in rows for n, w in s.suspects})
        if suspects:
            lines.append("    revenue suspect (ranked after the valued names): "
                         + "; ".join(f"{n} ({w})" for n, w in suspects))  # fmt: skip
    nopeer = {t: (s.note or "no active candidate") for t, s in pp.shortlists.items()
              if not s.candidates}  # fmt: skip
    lines.append(f"Companies with no usable SIC peers: {len(nopeer)}")
    lines += [f"  {t}: {why}" for t, why in sorted(nopeer.items())]
    lines.append(f"Setup peer items: {sum(v == 'queued' for v in pp.opened.values())} queued now, "
                 f"{sum(v == 'suppressed' for v in pp.opened.values())} already open")  # fmt: skip
    if pp.gaps:
        lines.append("Form-index quarters missing in the last 12 months (active counts partial): "
                     + ", ".join(pp.gaps))  # fmt: skip
    else:
        lines.append("Form indexes cover the last 12 months (active counts complete)")
    return lines


def profile_run(engine, comps: dict[str, str], mf, now, log, client=None, clog=None) -> None:
    """The `profile` work on open connections (tests inject a scratch DB and a fake client;
    `client=None` = no SEC requests)."""
    from engine.financials import peers, profile
    from engine.sec import browse

    targets = profile.peer_targets(engine, comps, mf)
    sics = sorted({sic for _, sic, _ in targets.values() if sic})
    if client is not None:
        log(f"Browse-by-SIC for {len(sics)} SIC(s): {', '.join(sics)} (one browse per SIC, "
            f"at most {browse.PAGE_CAP} pages each):")  # fmt: skip
        t0 = time.monotonic()
        for sic in sics:
            b = browse.browse_sic(client, sic)
            engine.execute("BEGIN")
            browse.store(engine, b, now)
            engine.execute("COMMIT")
            log(f"  SIC {sic}: {len(b.companies)} companies in {b.pages} page(s)"
                + (" PARTIAL (cap)" if b.capped else "")
                + (f" FAILED: {b.error}" if b.error else ""))  # fmt: skip
            if b.throttled:
                log("  SEC throttle: the rest waits for the next run")
                break
        year = peers.frame_year(now.date())
        if clog is not None:
            clog.seconds["browse-by-SIC"] += time.monotonic() - t0
        log(f"Revenue frames CY{year} (ranking) and CY{year - 1} (suspect guard):")
        t1 = time.monotonic()
        log(*peers.fetch_revenue_frames(client, engine, year, now))
        if clog is not None:
            clog.seconds["frames"] += time.monotonic() - t1
        log("")
    else:
        log("SEC skipped (--no-sec): stored browse lists and frames used", "")

    if S1_SIC in sics:
        rows = engine.execute("SELECT cik, name, browsed FROM sic_listing WHERE sic = ? "
                              "ORDER BY name", (S1_SIC,)).fetchall()  # fmt: skip
        act = peers.active_filers(engine, [r["cik"] for r in rows], now.date())
        log(f"S1 re-probe — SIC {S1_SIC} full list ({len(rows)} listed, {len(act)} active; "
            "* = active, with its form and date):")  # fmt: skip
        log(
            "  "
            + "; ".join(
                f"{r['name']} ({r['cik'].lstrip('0')})"
                + (f" *{act[r['cik']][0]} {act[r['cik']][1]}" if r["cik"] in act else "")
                + ("" if r["browsed"] == "10-K" else f" [{r['browsed']} list]")
                for r in rows
            )
        )
        log("")

    pp = profile.peer_pass(engine, comps, mf, now)
    sp = profile.stage_pass(engine, comps, mf, now)
    log(*profile.stage_lines(sp, engine))
    log("")
    log(*profile_summary(engine, mf, sp, pp, now))


def run_profile(args, log: Log, folder: Path) -> int:
    from engine.financials import models
    from engine.store.db import open_db
    from engine.store.http import SqliteCache, SqliteFetchLog

    engine = open_db("engine", folder)
    corpus = open_db("corpus", folder, check_same_thread=False)
    now = datetime.now(UTC)
    mb_before, before = db_mb(folder), counts(engine)
    comps = companies(engine)
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    head = f"run_financials profile · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} companies"
    log(head + (" · no SEC" if args.no_sec else ""), f"engine.db before: {mb_before:,.1f} MB", "")
    try:
        mf = models.load()
    except models.ModelFileError as e:
        mf = models.ModelFile(str(models.MODELS), (), str(e))
    log(f"Model tags: {mf.error or f'{len(mf.entries)} entries loaded'}", "")
    client = clog = None
    if not args.no_sec:
        from engine.sec.client import SecClient, user_agent_from_env

        clog = CountingLog(SqliteFetchLog(engine))
        client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=clog)
    profile_run(engine, comps, mf, now, log, client, clog)
    if clog is not None:
        log(*clog.lines())
    else:
        log("SEC requests: 0 (--no-sec)")
    after = counts(engine)
    log(
        "Rows added per table: "
        + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in COUNTED_TABLES)
    )
    log(f"engine.db: {mb_before:,.1f} MB → {db_mb(folder):,.1f} MB")
    corpus.close()
    engine.close()
    return 0


def _main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("subcommand", nargs="?", choices=[s for s, _, _ in SUBCOMMANDS])
    ap.add_argument("--no-sec", action="store_true", help="no SEC requests (local re-run)")
    ap.add_argument("--tickers", help="comma-separated subset (default: watchlist + tracked)")
    ap.add_argument("--years", type=int, default=3, help="R1 history for multi-class filers")
    ap.add_argument("--list", action="store_true", help="print the subcommand table")
    args = ap.parse_args()
    if args.list or not args.subcommand:
        for name, part, what in SUBCOMMANDS:
            print(f"{name:10} Part {part:3} {what}" + ("" if name in BUILT else "  (not built)"))
        return 0 if args.list else 2
    part = dict((s, p) for s, p, _ in SUBCOMMANDS)[args.subcommand]
    if args.subcommand not in BUILT:
        print(f"{args.subcommand}: not built, Part {part}")
        return 2
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.chdir(ROOT)  # data/, config/ and logs/ are relative to the repo
    from engine.store.db import data_dir

    log = Log(ROOT / "logs" / f"financials_{args.subcommand}_{datetime.now():%Y%m%d-%H%M%S}.txt")
    try:
        if args.subcommand == "capex":
            return run_capex(args, log, data_dir())
        if args.subcommand == "profile":
            return run_profile(args, log, data_dir())
        return run_data(args, log, data_dir())
    except Exception:
        log("FAILED with a traceback:", traceback.format_exc())
        return 1
    finally:
        log(f"Log written to: {log.path}")
        log.close()


def main() -> int:
    if any(a in sys.argv[1:] for a in ("--list", "-h", "--help")) or len(sys.argv) < 2:
        return _main()  # no data touched: no lock needed
    if sys.argv[1] not in BUILT:
        return _main()
    from engine.store.lock import run_script

    return run_script(ROOT, "run_financials", _main)


if __name__ == "__main__":
    sys.exit(main())
