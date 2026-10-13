"""M04 Financials: one owner script, one subcommand per build part (D-M04-69).

    uv run python scripts/run_financials.py data             # Part 1a live check
    uv run python scripts/run_financials.py data --no-sec    # local re-run, 0 SEC requests
    uv run python scripts/run_financials.py capex            # Part 1b live check
    uv run python scripts/run_financials.py capex --no-sec   # local re-run, 0 SEC requests
    uv run python scripts/run_financials.py profile          # Part 1c live check
    uv run python scripts/run_financials.py profile --no-sec # local re-run, 0 SEC requests
    uv run python scripts/run_financials.py peers            # Part 2 live check
    uv run python scripts/run_financials.py peers --no-sec   # local re-run, 0 SEC requests
    uv run python scripts/run_financials.py flags            # Part 3 live check
    uv run python scripts/run_financials.py flags --no-sec   # local re-run, 0 SEC requests
    uv run python scripts/run_financials.py gate             # Part 4a live check
    uv run python scripts/run_financials.py gate --no-sec    # local re-run, 0 SEC requests
    uv run python scripts/run_financials.py gate-text        # Part 4b-lite (0 SEC requests)
    uv run python scripts/run_financials.py quality          # Part 6 live check
    uv run python scripts/run_financials.py quality --no-sec # local re-run, 0 SEC requests
    uv run python scripts/run_financials.py units            # Part 7a live check
    uv run python scripts/run_financials.py units --no-sec   # local re-run, 0 SEC requests
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

`peers` (Part 2): reads the confirmed peer sets (M04 setup page; a company without one reads
"peers not confirmed on the M04 setup page" and nothing is fetched for it); downloads each
distinct SEC peer's companyfacts once (not cached; trimmed to M04's tags and stored as
facts; peers that are covered companies use their own facts; a stored peer is downloaded
again only when the refresh marked it due, or with `--refetch`); recomputes the trend rows
with peer robust z and their signals for every covered company (0 requests); prints rows
and MB per peer, n per peer group and the groups below 5, peers with no comparable period,
peer flags and the peer z on MU's and INTC's revenue rows. `--no-sec` uses stored facts.

`flags` (Part 3): reads the R1 cover pages (dei error-correction flag) of annual reports
filed from 2023-12-01 not read yet (~26); the 8-K texts of filing events of the last 3
years whose class needs them (3.01, 4.01, 4.02, 2.04, 1.03); GE's ~8 companyconcept files
(Round 2's walk); then walks every covered company and GE, fetches at most 35 old filings
whose text labels steps over tolerance, and the two prior 10-Ks per company (≤ 28; one
request each, large files dropped from the cache); recomputes walk, events, ratings and the
`restatement`, `non_reliance`, `restate_delta` signals (0 requests) and prints what the
owner looks for. `--no-sec` uses stored pages, texts and facts.
`quality` (Part 6): GE's `UnbilledContractsReceivable` companyconcept file, GE's FY2016 10-K
instance (its `ge:ContractAsset` extension facts; index page + instance), GE's FY2016 and
FY2017 10-K documents when not stored (the estimate-change sentences; via the filing index)
and Lockheed's catch-up revenue companyconcept file: about 6–10 requests; then, from stored
facts and text (0 requests), every covered company's CFO/NI, accruals, M-score (and with
SGI = 1), misstatement score, contract-asset and deferred-revenue readings, estimate-change
sentences of the last three annual reports, recurring "one-time" charges and non-operating
swings; the nine Part 6 signals; `m04_mscore` and `m04_estimate` items (group 7, capped;
first scan a baseline). `--no-sec` uses stored facts and text.
`units` (Part 7a): for every core and promoted company, the XBRL instance of each 10-K,
10-Q, 20-F, 40-F and XBRL 6-K of the last 3 years not read yet (one request each, 2–14 MB,
not cached; extension and dimensional facts on the one read), the EX-99.2 of the last 4
earnings 8-Ks (index pages usually cached); RIVN's M04 backfill once it is promoted on the
UI ("RIVN not covered yet: promote it on the UI first" until then; D-M04-81); Invitae's
2020–22 earnings releases (EX-99.1 only) and Target's FY2021–22 Q1–Q2 cost line
(companyconcept, then 10-Q instances); then unit KPIs from stored text (0 requests) and
`m04_unit_kpi` items for category breaks; prints what the owner looks for. `--no-sec`
re-scans stored text only.

`gate` (Part 4a): Invitae's (and Rivian's, unless the refresh covers it) gate inputs as
companyconcept files (17 tags each, cached 30 days; ~17–34 requests); then the survival
gate, distress score, debt, FCF-burn and negative-equity rows for every covered company
from stored facts (0 requests), the Part 4a review items, one line per company and the
regression cases. `--no-sec` recomputes from stored data only.

`gate-text` (Part 4b-lite): going-concern and covenant sentences of every covered company's
stored periodic text (10-K, 10-Q, 20-F, 40-F, 6-K and their EX-10 / EX-99), classed per
D-M04-34 with verified quotes; `gc_language` / `covenant_status`; text alerts and reviews;
then the survival gate again with the text classes. 0 SEC requests (`--no-sec` is accepted
and changes nothing).

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
BUILT = {"data", "capex", "profile", "peers", "flags", "gate", "gate-text", "units", "quality"}
NVDA_CIK = "0001045810"
NVDA_YEARS = range(2013, 2022)  # FY2013–FY2021: capex only under the extension tag
WDC_CIK = "0000106040"
WDC_TAGS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")
COUNTED_TABLES = ("fact", "series", "cover_shares", "filing_status", "signal", "entity_link",
                  "entity", "refresh_state", "fetch_log", "capex_split",
                  "guidance_outcome", "company_stage", "m04_proposal", "peer_candidate",
                  "sic_listing", "frame_value", "review_queue", "peer_fetch", "peer_group",
                  "peer_member")  # fmt: skip


SUMMARY_MARK = "=== Summary"
CONSOLE_ALWAYS = ("Log written to:", "FAILED", "SEC throttle")


class Log:
    """Every line goes to the log file as it is produced; the console shows only the
    "=== Summary" block onward, failures and the log path (owner, Part 7a re-run 1: the
    full detail was too long for the terminal). The file content is unchanged."""

    def __init__(self, path: Path, *, echo_all: bool = False) -> None:
        self.path = path
        path.parent.mkdir(exist_ok=True)
        self._fh = path.open("w", encoding="utf-8")
        self._echo = echo_all

    def console(self, line: str) -> bool:
        if line.startswith((SUMMARY_MARK, "FAILED")):
            self._echo = True
        return self._echo or line.startswith(CONSOLE_ALWAYS)

    def __call__(self, *lines: str) -> None:
        for line in lines:
            if self.console(line):
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


# --- peers (Part 2) ------------------------------------------------------------------------


Z_ROWS = ("rev_yoy", "rev_cagr3", "fcf_growth", "fcf_growth_oe", "gm", "gm_trend_pp",
          "opex_vs_sales", "roic")  # fmt: skip
Z_DETAIL = ("MU", "INTC")


def peers_summary(engine, sets, results, fetched, covered) -> list[str]:
    """What the owner looks for (M04_BUILD_LOG Part 2 live check)."""
    lines = ["=== Summary (what the owner looks for) ==="]
    ciks = sorted({m["cik"] for s in sets.values() if s.confirmed for m in s.sec})
    lines.append(f"Peer facts per SEC peer ({len(ciks)} distinct; rows kept · new · MB · tags "
                 "kept · fiscal year end · latest period):")  # fmt: skip
    tot_mb = tot_rows = 0.0
    for cik in ciks:
        name = next(m["name"] for s in sets.values() if s.confirmed for m in s.sec
                    if m["cik"] == cik)  # fmt: skip
        if cik in covered:
            lines.append(f"  {name} ({cik}): own facts (covered company, kept by the refresh)")
            continue
        r = engine.execute("SELECT * FROM peer_fetch WHERE cik = ?", (cik,)).fetchone()
        if r is None:
            lines.append(f"  {name} ({cik}): not fetched")
            continue
        when = "this run" if cik in fetched else f"stored, fetched {(r['ok_at'] or '')[:10]}"
        if r["outcome"] != "ok" and not r["ok_at"]:
            lines.append(f"  {name} ({cik}): {r['outcome']}: {r['detail']}")
            continue
        tot_mb += float(r["mb"] or 0)
        tot_rows += r["rows_kept"] or 0
        line = (f"  {name} ({cik}): {r['rows_kept'] or 0:,} rows · {r['rows_new'] or 0:,} new · "
                f"{float(r['mb'] or 0):.2f} MB · {r['tags_kept']} of {r['tags_total']} tags · "
                f"FYE {r['fiscal_year_end'] or 'unknown'} · latest {r['latest_end'] or '—'} "
                f"({when})")  # fmt: skip
        if r["outcome"] != "ok":
            line += f"; last attempt {r['outcome']}: {r['detail']}"
        if r["due_filed"]:
            line += f"; due: {r['due_form']} filed {r['due_filed']}"
        lines.append(line)
    lines.append(
        f"  total: {tot_rows:,.0f} rows kept, {tot_mb:.1f} MB downloaded (as last fetched)"
    )
    lines.append("n per peer group (comparable peers scored per row; < 5 = fixed-gap fallback):")
    below = []
    for ticker, comp in sorted(results.items()):
        if comp is None:
            continue
        if comp.status:
            lines.append(f"  {ticker}: {comp.status}")
            continue
        parts = []
        for key in Z_ROWS:
            row = comp.rows.get(key)
            if row is None or row.missing:
                parts.append(f"{key} —")
                continue
            r = row.result
            parts.append(f"{key} {r.n}" + (f"/{r.n_in}" if r.n_in != r.n else ""))
            if r.n < 5:
                below.append(f"{ticker} {key}")
        lines.append(f"  {ticker} ({len(comp.lines)} peers): " + " · ".join(parts))
    lines.append(f"Groups below 5 (fallback, low confidence): {len(below)}"
                 + (f" — {', '.join(below)}" if below else ""))  # fmt: skip
    lines.append("Peers with no comparable period (latest 12 months, ±45 d) or no facts:")
    nothing = True
    for ticker, comp in sorted(results.items()):
        if comp is None or comp.status:
            continue
        for p in comp.lines:
            if not p.in_comparison.startswith("yes"):
                nothing = False
                off = f", offset {p.offset:+d} d" if p.offset is not None else ""
                lines.append(f"  {ticker}: {p.name} — {p.in_comparison} (latest "
                             f"{p.latest_end or '—'}{off}); {p.note}")  # fmt: skip
    if nothing:
        lines.append("  none")
    lines.append("Peer flags (53-week year, acquisition year):")
    flagged = [(t, p) for t, c in sorted(results.items()) if c and not c.status
               for p in c.lines if p.in_comparison.startswith("yes") and p.note]  # fmt: skip
    lines += [f"  {t}: {p.name} ({p.latest_end}): {p.note}" for t, p in flagged] or ["  none"]
    for ticker in Z_DETAIL:
        comp = results.get(ticker)
        if comp is None:
            lines.append(f"Peer z on {ticker} revenue rows: {ticker} not in this run")
            continue
        lines.append(f"Peer z on {ticker} revenue rows:")
        for key in ("rev_yoy", "rev_cagr3"):
            if comp.status:
                lines.append(f"  {key}: missing: {comp.status}")
                continue
            row = comp.rows[key]
            lines.append(f"  {key}: {row.text()}")
            if row.company.value is not None:
                lines.append(f"    company {row.company.value:+.1%}")
            for m in row.members:
                if m.included:
                    lines.append(f"    {m.name}: {m.value:+.1%} ({m.end}, {m.offset:+d} d)"
                                 + (f" [{'; '.join(m.flags)}]" if m.flags else ""))  # fmt: skip
                else:
                    lines.append(f"    {m.name}: not in comparison — {m.why}")
    return lines


def peers_run(engine, comps: dict[str, str], now, log, client=None, clog=None,
              refetch: bool = False, corpus=None) -> dict:  # fmt: skip
    """The `peers` work on open connections (tests inject a scratch DB and a fake client;
    `client=None` = no SEC requests). Returns ticker → peer comparison."""
    from engine.financials import models, peer_facts, profile
    from engine.financials.step import part1b

    mf = models.load_safe()
    targets = profile.peer_targets(engine, comps, mf)
    skipped = sorted(set(comps) - set(targets))
    sets = peer_facts.peer_sets(engine, {t: c for t, (c, _, _) in targets.items()})
    covered = set(comps.values())
    log(f"Peer sets ({len(sets)} companies; tracked names and fund/financial tags have none: "
        f"{', '.join(skipped) or 'none'}):")  # fmt: skip
    for t, s in sets.items():
        if not s.confirmed:
            log(f"  {t}: {peer_facts.NOT_CONFIRMED} — nothing fetched for {t}")
        else:
            non = [m["name"] for m in s.members if not m["cik"]]
            log(f"  {t}: {len(s.members)} confirmed — {len(s.sec)} SEC filers"
                + (f", not SEC filers: {', '.join(non)}" if non else "")
                + (": " + ", ".join(m["name"] for m in s.sec) if s.sec else ""))  # fmt: skip
    want: dict[str, str] = {}
    for s in sets.values():
        if s.confirmed:
            for m in s.sec:
                want.setdefault(m["cik"], m["name"])
    own = sorted(c for c in want if c in covered)
    log(f"Distinct SEC peers: {len(want)}; covered companies using their own facts: {len(own)}", "")
    fetched: set[str] = set()
    if client is not None:
        todo = []
        for cik, name in sorted(want.items(), key=lambda kv: kv[1]):
            if cik in covered:
                continue
            r = peer_facts.stored(engine, cik)
            if r is not None and r["ok_at"] and not r["due_filed"] and not refetch:
                continue
            todo.append((cik, name))
        stored_n = len(want) - len(own) - len(todo)
        log(f"Companyfacts downloads: {len(todo)} to fetch (not cached; trimmed to "
            f"{len(peer_facts.KEEP)} M04 tags); {stored_n} already stored"
            + (" (use --refetch to download again)" if stored_n else "") + ":")  # fmt: skip
        t0 = time.monotonic()
        for cik, name in todo:
            f = peer_facts.fetch_peer(client, engine, cik, name, now)
            log("  " + f.line())
            if f.outcome == "ok":
                fetched.add(cik)
            if f.throttled:
                log("  SEC throttle: the rest waits for the next run")
                break
        if clog is not None:
            clog.seconds["companyfacts"] += time.monotonic() - t0
        log("")
    else:
        log("SEC skipped (--no-sec): stored peer facts used", "")

    t1 = time.monotonic()
    cache: dict = {}
    results: dict = {}
    for ticker, cik in sorted(comps.items()):
        try:
            got = part1b(engine, corpus, cik, ticker, now, peer_cache=cache, covered=covered)
            results[ticker] = got.peers if ticker in targets else None
        except Exception as e:  # one company's error must not stop the others
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            log(f"  {ticker}: error — {type(e).__name__}: {e}")
    log(f"Trend rows, peer z and signals recomputed for {len(results)} companies "
        f"(0 requests, {time.monotonic() - t1:.1f} s)", "")  # fmt: skip
    log(*peers_summary(engine, sets, results, fetched, covered))
    return results


def run_peers(args, log: Log, folder: Path) -> int:
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
    head = f"run_financials peers · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} companies"
    log(head + (" · no SEC" if args.no_sec else ""), f"engine.db before: {mb_before:,.1f} MB", "")
    client = clog = None
    if not args.no_sec:
        from engine.sec.client import SecClient, user_agent_from_env

        clog = CountingLog(SqliteFetchLog(engine))
        client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=clog)
    peers_run(engine, comps, now, log, client, clog, refetch=args.refetch, corpus=corpus)
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


# --- flags (Part 3) ------------------------------------------------------------------------


GE_CIK = "0000040545"  # Round 2's worked walk (D-M04-16): companyconcept files, walk only
GE_TAGS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "NetIncomeLoss",
           "NetIncomeLossAttributableToNoncontrollingInterest",
           "NetCashProvidedByUsedInOperatingActivities",
           "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
           "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
           "ExtraordinaryItemsNoncontrollingInterest",
           "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
           "MinorityInterestAndIncomeLossFromEquityMethodInvestments")  # fmt: skip
FLAGS_TABLES = ("restate_step", "m04_event", "rating_action")
WALK_BASELINE = 101  # M04_BUILD_LOG Part 3 (Round 2 counted 102)


def flags_counts(engine) -> dict[str, int]:
    return counts(engine) | {
        t: engine.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in FLAGS_TABLES
    }


def annual_r1_todo(engine, comps: dict[str, str]) -> list:
    """Annual reports filed from 2023-12-01 whose R1 page (dei error flag) is not read."""
    from engine.financials.restate import DEI_FROM
    from engine.financials.step import ANNUAL_COVER_FORMS
    from engine.sec.cover import r1_done

    todo = []
    marks = ",".join("?" * len(ANNUAL_COVER_FORMS))
    for ticker, cik in sorted(comps.items()):
        for f in engine.execute(
            f"SELECT f.accession, f.form, f.filed, f.report_date FROM filing f JOIN filing_cik c "
            f"ON c.accession = f.accession WHERE c.cik = ? AND f.form IN ({marks}) AND "
            "f.filed >= ? ORDER BY f.filed",
            (cik, *ANNUAL_COVER_FORMS, DEI_FROM),
        ):
            if not r1_done(engine, f["accession"]):
                todo.append((ticker, cik, f))
    return todo


def ge_concepts(client, engine, log, clog) -> None:
    """GE's walk inputs: one companyconcept file per tag (stored as facts under GE's CIK)."""
    from engine.sec.results import NotFound, Ok
    from engine.sec.xbrl_facts import CONCEPT_URL, store_concept

    t0 = time.monotonic()
    for tag in GE_TAGS:
        url = CONCEPT_URL.format(cik=GE_CIK, taxonomy="us-gaap", tag=tag)
        res = client.get_json(url, ttl_s=30 * 86400)
        if isinstance(res, NotFound):
            log(f"  GE us-gaap:{tag}: not found")
            continue
        if not isinstance(res, Ok):
            log(f"  GE us-gaap:{tag}: {res}")
            continue
        engine.execute("BEGIN")
        seen, new = store_concept(engine, GE_CIK, res.data)
        engine.execute("COMMIT")
        log(f"  GE us-gaap:{tag}: {seen} facts, {new} new")
    if clog is not None:
        clog.seconds["companyconcept"] += time.monotonic() - t0


def walk_lines(ticker: str, steps, *, detail: int = 6) -> list[str]:
    from collections import Counter

    from engine.financials.restate import DEFECTS, LABEL_NAMES, ROUND2_CONCEPTS, money

    if not steps:
        return [f"  {ticker}: 0 steps"]
    r2 = [s for s in steps if s.concept in ROUND2_CONCEPTS]
    labs = Counter(lb.family for s in steps for lb in s.labels if lb.family not in DEFECTS)
    out = Counter(s.outcome for s in steps)
    bad = [s for s in steps if s.defect]
    pat = Counter(s.defect for s in bad)
    clean_r2 = [s for s in r2 if not s.defect]
    pats = ", ".join(f"{LABEL_NAMES[k].split(': ')[1]} {v}" for k, v in pat.most_common())
    line = (f"  {ticker}: {len(steps)} steps from {len({s.new.accession for s in steps})} filings "
            f"(revenue/NI/CFO {len(r2)} from {len({s.new.accession for s in r2})}); "
            f"data defects {len(bad)}" + (f" ({pats})" if bad else "")
            + f", excluding them {len(steps) - len(bad)} (revenue/NI/CFO {len(clean_r2)}); "
            f"explained {out['explained'] - len(bad)}, watch {out['watch']}, "
            f"review {out['review']}; labels: "
            + (", ".join(f"{LABEL_NAMES.get(k, k)} {v}" for k, v in labs.most_common())
               or "none"))  # fmt: skip
    lines = [line]
    for s in bad[: min(detail, 4)]:
        lb = s.labels[0]
        lines.append(f"    data defect ({LABEL_NAMES[lb.family].split(': ')[1]}): {s.concept} "
                     f"{s.period} {money(s.old.value)} → {money(s.new.value)} ({s.new.form} "
                     f"{s.new.filed} {s.new.accession}); {lb.quote}")  # fmt: skip
    for s in [s for s in steps if s.outcome == "review"][:detail]:
        lab = "; ".join(lb.family + (f" {money(lb.amount)}" if lb.amount is not None else "")
                        for lb in s.labels) or "no label"  # fmt: skip
        pct = f" ({s.residual_pct * 100:.2f}%)" if s.residual_pct is not None else ""
        lines.append(f"    review: {s.concept} {s.period} {money(s.old.value)} → "
                     f"{money(s.new.value)} ({s.new.form} {s.new.filed} {s.new.accession}); "
                     f"left {money(s.residual)}{pct}; {lab}; {s.text_state}")  # fmt: skip
    return lines


def flags_summary(engine, comps, fp, ge_steps, olds, priors, lf) -> list[str]:
    """What the owner looks for (M04_BUILD_LOG Part 3 live check)."""
    import json
    from collections import Counter

    from engine.financials import restate

    lines = ["=== Summary (what the owner looks for) ==="]
    total = sum(len(c.steps) for c in fp.companies.values())
    r2 = [s for c in fp.companies.values() for s in c.steps if s.concept in restate.ROUND2_CONCEPTS]
    r2c = [s for s in r2 if not s.defect]
    n_bad = sum(1 for c in fp.companies.values() for s in c.steps if s.defect)
    lines.append(f"Walk, watchlist: {total} steps from "
                 f"{len({s.new.accession for c in fp.companies.values() for s in c.steps})} "
                 f"filings, {n_bad} of them data defects (explained, never review); "
                 f"revenue/NI/CFO only (Round 2's concepts): {len(r2)} steps from "
                 f"{len({s.new.accession for s in r2})} filings, excluding data defects "
                 f"{len(r2c)} from {len({s.new.accession for s in r2c})} (expected about "
                 f"{WALK_BASELINE}; Round 2 counted 102)")  # fmt: skip
    for t, c in sorted(fp.companies.items()):
        if c.error:
            lines.append(f"  {t}: error — {c.error}")
        else:
            lines += walk_lines(t, c.steps)
    queued = engine.execute("SELECT p.reason, p.status, p.payload FROM m04_proposal p WHERE "
                            "p.kind = 'm04_restate' ORDER BY p.status, p.first_seen_at"
                            ).fetchall()  # fmt: skip
    by = Counter(r["status"] for r in queued)
    lines.append(f"m04_restate proposals: queued {by['queued']}, overflow {by['overflow']}, "
                 f"baseline {by['baseline']} (≤ 4 queued expected)")  # fmt: skip
    for r in queued:
        if r["status"] != "baseline":
            p = json.loads(r["payload"] or "{}")
            lead = restate.lead_label(p.get("labels", []))
            q = p.get("quote") or (lead["quote"] if lead else "")
            lines.append(f"  {r['status']}: {r['reason']}" + (f" — “{q[:200]}”" if q else ""))
    wd = Counter(r["kind"] for r in engine.execute(
        "SELECT kind FROM review_queue WHERE resolution = 'withdrawn' AND module_id = 'M04'"
    ))  # fmt: skip
    lines.append("M04 items withdrawn on recomputation (finding no longer holds): "
                 + (", ".join(f"{k} {v}" for k, v in sorted(wd.items())) or "none"))  # fmt: skip
    lines.append("dei error-correction flag (annual reports filed from 2023-12-01; false "
                 "expected):")  # fmt: skip
    for t, cik in sorted(comps.items()):
        fl = [f for f in restate.dei_flags(engine, cik) if f.state != "not required"]
        nr = sum(1 for f in restate.dei_flags(engine, cik) if f.state == "not required")
        lines.append(f"  {t}: " + (" · ".join(f"{f.form} {f.filed} {f.state}" for f in fl)
                                   or "no annual report filed from 2023-12-01")
                     + (f"; {nr} earlier: not required" if nr else ""))  # fmt: skip
    ev = [(t, e) for t, c in sorted(fp.companies.items()) for e in c.events]
    lines.append(f"Filing events, 3 years: {len(ev)} — by class: "
                 + (", ".join(f"{k} {v}" for k, v in Counter(e.klass for _, e in ev).most_common())
                    or "none"))  # fmt: skip
    for t, e in ev:
        lines.append(f"  {t} {e.filed} {e.label} {e.klass} ({e.state}); {e.note}"
                     + (f" — “{e.quote[:160]}”" if e.quote else ""))  # fmt: skip
    evq = Counter(r["status"] for r in engine.execute(
        "SELECT status FROM m04_proposal WHERE kind = 'm04_event'"))  # fmt: skip
    lines.append(f"m04_event proposals: queued {evq['queued']}, overflow {evq['overflow']}, "
                 f"baseline {evq['baseline']}")  # fmt: skip
    rs = [(t, r) for t, c in sorted(fp.companies.items()) for r in c.ratings]
    lines.append(f"Rating sentences: {len(rs)}")
    for t, r in rs[:20]:
        lines.append(f"  {t} {r.filed} {r.action}" + (f" {r.from_rating or '?'} → {r.to_rating}"
                                                       if r.to_rating else "")
                     + f": “{r.quote[:200]}”")  # fmt: skip
    rq = Counter(r["status"] for r in engine.execute(
        "SELECT status FROM m04_proposal WHERE kind = 'm04_rating'"))  # fmt: skip
    lines.append(f"m04_rating proposals: queued {rq['queued']}, overflow {rq['overflow']}, "
                 f"baseline {rq['baseline']}")  # fmt: skip
    lines.append("Signals (restatement · non_reliance · restate_delta):")
    for t, c in sorted(fp.companies.items()):
        lines.append(f"  {t}: {c.restatement or '—'} · {c.non_reliance or '—'} · "
                     f"{c.restate_delta or '—'}")  # fmt: skip
    lines.append("GE walk (Round 2 worked example; expected 142 steps from 45 filings, compare "
                 "the count excluding data defects):")  # fmt: skip
    lines += walk_lines("GE", ge_steps, detail=10)
    lines.append(f"Old filings for walk labels: {olds} (cap {35})")
    lines.append(f"Prior 10-Ks: {priors} (cap 28)")
    lines.append(lf.line())
    lines.append(f"Overflow flushed this run: {fp.flushed}")
    return lines


def flags_run(engine, corpus, comps: dict[str, str], now, log, client=None, clog=None) -> dict:
    """The `flags` work on open connections (tests inject a scratch DB and a fake client;
    `client=None` = no SEC requests)."""
    from engine.financials import events, filings, flags_step, labels, models, restate
    from engine.financials.profile import full_scope
    from engine.financials.step import read_covers

    mf = models.load_safe()
    scope = full_scope(engine, comps)
    since3 = restate.window_start(now.date())
    olds = priors = "not run (--no-sec)"
    if client is not None:
        todo = annual_r1_todo(engine, comps)
        log(f"R1 cover pages (dei error-correction flag) of annual reports filed from "
            f"{restate.DEI_FROM} not read yet: {len(todo)}")  # fmt: skip
        t0 = time.monotonic()
        lines, n = read_covers(client, engine, todo, now, budget_s=900)
        if clog is not None:
            clog.seconds["R page"] += time.monotonic() - t0
        log(*lines)
        log(f"  read {n['cover']}, not a cover {n['not_cover']}, not found {n['not_found']}, "
            f"failed {n['failed']}, pending {n['pending']}", "")  # fmt: skip
        wanted = [a for _, c in sorted(comps.items())
                  for a in events.text_wanted(engine, corpus, c, since3)]  # fmt: skip
        log(f"8-K texts for filing events (items {', '.join(events.TEXT_ITEMS)}, 3 years) not "
            f"stored: {len(wanted)}")  # fmt: skip
        t1 = time.monotonic()
        filings.fetch_all(client, engine, corpus, wanted, now, log)
        if clog is not None:
            clog.seconds["other"] += time.monotonic() - t1
        log("", "GE companyconcept files (Round 2 walk):")
        ge_concepts(client, engine, log, clog)
        log("")
        # first walk: which changing filings need their text (D-M04-15, ≤ 35)
        targets, names = [], {}
        for _, cik in sorted(comps.items()):
            targets += [a for a in restate.old_filing_targets(restate.walk(engine, corpus, cik))
                        if a not in targets]  # fmt: skip
        ge_first = restate.walk(engine, corpus, GE_CIK)
        for s in ge_first:
            names[s.new.accession] = (GE_CIK, s.new.form)
        targets += [a for a in restate.old_filing_targets(ge_first) if a not in targets]
        pick = targets[: filings.OLD_FILING_CAP]
        log(f"Old filings to label walk steps (changing filings without stored text, steps "
            f"over tolerance): {len(targets)}; fetching {len(pick)} (cap "
            f"{filings.OLD_FILING_CAP})")  # fmt: skip
        t2 = time.monotonic()
        got = filings.fetch_all(client, engine, corpus, pick, now, log, names)
        olds = (f"{sum(1 for f in got if f.outcome == 'stored')} stored of {len(targets)} wanted "
                f"({len(pick)} tried)")  # fmt: skip
        pt = filings.prior_targets(engine, corpus, scope, mf)
        need = [a for p in pt for a in p.accessions if a not in p.stored]
        need = need[: filings.PRIOR_CAP]
        n_want = sum(len(p.accessions) for p in pt)
        log("", f"Prior 10-Ks (two before the latest, D-M04-17): {n_want} wanted, "
            f"{sum(len(p.stored) for p in pt)} already stored, fetching {len(need)}")  # fmt: skip
        for p in pt:
            if p.note:
                log(f"  {p.ticker}: {p.note}")
        got2 = filings.fetch_all(client, engine, corpus, need, now, log)
        priors = (f"{sum(1 for f in got2 if f.outcome == 'stored')} fetched, "
                  f"{sum(len(p.stored) for p in pt)} already stored, "
                  f"{sum(len(p.accessions) for p in pt)} wanted")  # fmt: skip
        if clog is not None:
            clog.seconds["other"] += time.monotonic() - t2
        log("")
    else:
        log("SEC skipped (--no-sec): stored R1 reads, texts and facts used", "")
    t3 = time.monotonic()
    fp = flags_step.flags_pass(engine, corpus, comps, now)
    ge_steps = restate.walk(engine, corpus, GE_CIK)
    if ge_steps:
        engine.execute("BEGIN")
        restate.store(engine, GE_CIK, "GE", ge_steps, now, queue_items=False)
        engine.execute("COMMIT")
    log(f"Walk, events, ratings and signals recomputed for {len(fp.companies)} companies + GE "
        f"(0 requests, {time.monotonic() - t3:.1f} s)", "")  # fmt: skip
    log(*flags_summary(engine, comps, fp, ge_steps, olds, priors, labels.read()))
    return fp.companies


def run_flags(args, log: Log, folder: Path) -> int:
    from engine.store.db import open_db
    from engine.store.http import SqliteCache, SqliteFetchLog

    engine = open_db("engine", folder)
    corpus = open_db("corpus", folder, check_same_thread=False)
    now = datetime.now(UTC)
    mb_before, before = db_mb(folder), flags_counts(engine)
    comps = companies(engine)
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    head = f"run_financials flags · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} companies"
    log(head + (" · no SEC" if args.no_sec else ""), f"engine.db before: {mb_before:,.1f} MB", "")
    client = clog = None
    if not args.no_sec:
        from engine.sec.client import SecClient, user_agent_from_env

        clog = CountingLog(SqliteFetchLog(engine))
        client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=clog)
    flags_run(engine, corpus, comps, now, log, client, clog)
    if clog is not None:
        log(*clog.lines())
    else:
        log("SEC requests: 0 (--no-sec)")
    after = flags_counts(engine)
    log("Rows added per table: " + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in after))
    log(f"engine.db: {mb_before:,.1f} MB → {db_mb(folder):,.1f} MB")
    corpus.close()
    engine.close()
    return 0


# --- units (Part 7a) -----------------------------------------------------------------------

UNITS_TABLES = (
    "fact_dim",
    "unit_metric",
    "fact",
    "filing",
    "refresh_state",
    "m04_proposal",
    "review_queue",
)
RIVN = ("RIVN", "0001874178")
INVITAE = ("Invitae", "0001501134", "2020-01-01", "2023-03-31")  # FY2019 … FY2022 releases
TARGET = ("Target", "0000027419")
TARGET_TAGS = ("Revenues", "CostOfGoodsAndServicesSold")
TARGET_ENDS = ("2021-05-01", "2021-07-31", "2022-04-30", "2022-07-30")
TESLA_CIK = "0001318605"


def units_counts(engine) -> dict[str, int]:
    return {t: engine.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in UNITS_TABLES}


def rivn_backfill(client, engine, corpus, now, log) -> None:
    """RIVN after promotion (D-M04-81): the M04-needed backfill only — filing index,
    companyfacts, latest 10-K and 10-Q, last 4 earnings releases (~25 requests). Form 4s
    and the rest arrive with the refresh's own promoted-name backfill."""
    from engine.sec.documents import ingest_filing
    from engine.sec.results import Ok
    from engine.sec.submissions import earnings_releases, stored_filings, sync_filings
    from engine.sec.xbrl_facts import sync_facts

    cik = RIVN[1]
    s = sync_filings(client, engine, cik, now)
    log(f"  filing index: {s if not isinstance(s, Ok) else f'{s.data.new} new filing(s)'}")
    fx = sync_facts(client, engine, cik, now, force=True)
    log(f"  XBRL facts: {fx if not isinstance(fx, Ok) else 'refreshed'}")
    wanted = [f for f in stored_filings(engine, cik, forms=("10-K",))][:1]
    wanted += [f for f in stored_filings(engine, cik, forms=("10-Q",))][:1]
    wanted += earnings_releases(engine, cik)[:4]
    new = 0
    for f in wanted:
        got = ingest_filing(client, corpus, f, now)
        if isinstance(got, Ok):
            new += sum(1 for d in got.data.stored if d.new)
        else:
            log(f"  documents {f.form} {f.accession}: {got}")
    log(
        f"  documents: {len(wanted)} filing(s), {new} new document(s) (latest 10-K, 10-Q, "
        "last 4 earnings releases)"
    )


def target_check(client, engine, now, log, clog=None) -> None:
    """Target FY2022 Q1–Q2 (episode, not covered): 2 companyconcept files, then the 10-Q
    instances of quarters whose cost line companyconcept lacks (D-M04-42)."""
    from engine.financials import units
    from engine.sec import instance_dim
    from engine.sec.results import Ok
    from engine.sec.submissions import sync_filings
    from engine.sec.xbrl_facts import CONCEPT_URL, store_concept

    cik = TARGET[1]
    for tag in TARGET_TAGS:
        res = client.get_json(
            CONCEPT_URL.format(cik=cik, taxonomy="us-gaap", tag=tag), ttl_s=30 * 86400
        )
        if not isinstance(res, Ok):
            log(f"  Target us-gaap:{tag}: {res}")
            continue
        engine.execute("BEGIN")
        seen, new = store_concept(engine, cik, res.data)
        engine.execute("COMMIT")
        log(f"  Target us-gaap:{tag}: {seen} facts, {new} new")
    missing = [e for e in TARGET_ENDS if units.quarter_gm(engine, cik, e).basis != "companyfacts"]
    if not missing:
        log("  Target: every quarter has revenue and cost in companyfacts; no instance needed")
        return
    rows = engine.execute(
        "SELECT accession, form, filed, report_date, primary_doc FROM filing "
        "WHERE cik = ? AND form = '10-Q'",
        (cik,),
    ).fetchall()
    if not rows:
        s = sync_filings(client, engine, cik, now)
        log(f"  Target filing index: {s if not isinstance(s, Ok) else f'{s.data.new} filings'}")
        rows = engine.execute(
            "SELECT accession, form, filed, report_date, primary_doc FROM filing "
            "WHERE cik = ? AND form = '10-Q'",
            (cik,),
        ).fetchall()
    for e in missing:
        f = next((r for r in rows if r["report_date"] == e), None)
        if f is None:
            log(f"  Target 10-Q for {e}: not in the filing index")
            continue
        if instance_dim.dims_done(engine, f["accession"]):
            continue
        r = instance_dim.read_instance(client, engine, cik, f, now)
        log(
            f"  Target 10-Q {e} {f['accession']}: {r.outcome} ({r.mb:.1f} MB, "
            f"{r.dim_new} dimensional rows, {r.ext_new} extension facts) {r.detail}".rstrip()
        )


def units_summary(
    engine, scope: dict[str, str], instance_log: dict, ex_log: dict, corpus=None
) -> list[str]:
    """What the owner looks for (M04_BUILD_LOG Part 7a live check)."""
    from engine.financials import exhibits, units, units_view

    lines = ["=== Summary (what the owner looks for) ==="]
    tot_read = sum(v["read"] for v in instance_log.values())
    tot_mb = sum(v["mb"] for v in instance_log.values())
    fails = [x for v in instance_log.values() for x in v["problems"]]
    lines.append(
        f"Instances read this run: {tot_read} ({tot_mb:,.1f} MB downloaded, not cached); "
        f"parse failures or misses: {len(fails)}"
    )
    lines += [f"  {x}" for x in fails[:20]]
    lines.append("Dimensional rows per company and axis (stored; instances read in total):")
    for ticker, cik in sorted(scope.items()):
        per = engine.execute(
            "SELECT axis, count(*) FROM fact_dim WHERE cik = ? GROUP BY axis ORDER BY axis", (cik,)
        ).fetchall()
        n_acc = engine.execute(
            "SELECT count(DISTINCT accession) FROM fact_dim WHERE cik = ?", (cik,)
        ).fetchone()[0]
        lines.append(
            f"  {ticker}: {n_acc} instance(s); "
            + (" · ".join(f"{a.split(':')[-1]} {n:,}" for a, n in per) or "none")
        )
    nvda = scope.get("NVDA")
    lines.append("NVIDIA ≥ 10% customers (expected FY2025 3 at 34%, FY2026 2 at 36% ≈ $77.7B):")
    if nvda:
        for c in units_view.major_customers(engine, nvda)[-4:]:
            usd = f" ≈ ${c.at_stake_usd / 1e9:,.1f}B" if c.at_stake_usd else ""
            lines.append(
                f"  {c.label}: {c.count} customer(s), {c.at_stake:.0%} at stake{usd} — "
                + ", ".join(f"{n} {p:.0%}" for n, p in c.customers)
                + f" ({c.accession}; {c.basis})"
            )
    else:
        lines.append("  NVDA not in this run")
    other = [
        (t, units_view.major_customers(engine, c)) for t, c in sorted(scope.items()) if t != "NVDA"
    ]
    lines.append(
        "Other companies with ≥ 10% customers (latest year): "
        + (
            "; ".join(
                f"{t} {cs[-1].label} {cs[-1].count} at {cs[-1].at_stake:.0%}"
                for t, cs in other
                if cs
            )
            or "none"
        )
    )
    lines.append(
        "Per-customer breakdown, latest year (customer share of revenue; benchmark / type "
        "axes per customer; facts left out with the reason, D-M04-43):"
    )
    for t, cik in sorted(scope.items()):
        cs = units_view.major_customers(engine, cik, keep_empty=True)
        if not cs:
            continue
        with_result = [c for c in cs if c.count]
        shown_years = ([with_result[-1]] if with_result else []) + (
            [cs[-1]] if not with_result or cs[-1] is not with_result[-1] else []
        )
        for c in shown_years:
            usd = f" ≈ ${c.at_stake_usd / 1e9:,.1f}B" if c.at_stake_usd else ""
            lines.append(
                f"  {t} {c.label}: {c.count} at {c.at_stake:.0%}{usd}"
                + (" — " + ", ".join(f"{n} {p:.1%}" for n, p in c.customers) if c.customers else "")
                + f" ({c.accession}; {c.basis})"
            )
            for n, ax in c.axes:
                lines.append(f"    {n}: {ax}")
            for n, v, why in c.excluded[:12]:
                shown = f"{v:.1%}" if abs(v) <= 1 else (f"{v:,.0f}" if abs(v) > 100 else f"{v:g}")
                lines.append(f"    left out: {n} {shown} — {why}")
            if len(c.excluded) > 12:
                lines.append(f"    … {len(c.excluded) - 12} more left out")
    lines.append("Segments (latest annual instance; recasts and breaks):")
    for ticker, cik in sorted(scope.items()):
        sg = units_view.segment_table(engine, cik)
        if sg:
            lines.append(
                f"  {ticker}: {len(sg.rows)} row(s) in {sg.accession}"
                + (f"; {' '.join(sg.notes)}" if sg.notes else "")
            )
    tesla = scope.get("TSLA")
    lines.append("Tesla KPI table (DS2; latest period vs a year earlier):")
    if tesla:
        rows = units.kpi_rows(engine, tesla)
        for r in rows:
            e = f"{r.earlier[0]} {r.earlier[1]:,.0f}" if r.earlier else "—"
            ch = f"{r.change:+.1%}" if r.change is not None else "—"
            tag = " [credit, kept separate]" if r.kind == "credit" else ""
            lines.append(
                f"  {r.metric}{' · ' + r.line if r.line else ''}: {e} → {r.later[0]} "
                f"{r.later[1]:,.0f} {r.unit} ({ch}; {r.basis}){tag}"
            )
        for b in units.breaks(engine, tesla):
            lines.append(f"  break: {b.metric} in {b.filed} — {b.text()}")
        if corpus is not None:
            lines.append(
                "  stored documents (what they can give; DS2):"
                if rows
                else "  no Tesla KPI rows; stored documents (what they can and cannot give; DS2):"
            )
            lines += [f"    {x}" for x in units.coverage_lines(engine, corpus, tesla)]
        elif not rows:
            lines.append("  no Tesla KPI rows in the stored documents")
    else:
        lines.append("  TSLA not in this run")
    lines.append(
        "RIVN (D-M04-81): "
        + (
            f"covered; deliveries {', '.join(f'{r.later[0]} {r.later[1]:,.0f}' for r in units.kpi_rows(engine, RIVN[1]) if r.metric == 'deliveries') or 'none stated in stored text'}"  # noqa: E501
            if RIVN[1] in scope.values()
            else "not covered yet: promote it on the UI first"
        )
    )
    lines.append("EX-99.2 found per company (last 4 earnings 8-Ks; checked · found · new):")
    lines.append(
        "  "
        + (
            " · ".join(
                f"{t} {v['checked']}/{v['found']}/{v['stored']}" for t, v in sorted(ex_log.items())
            )
            or "none checked"
        )
    )
    lines.append("Cover-count agreement, instance vs Part 1a R1 (multi-class filers):")
    any_cls = False
    for ticker, cik in sorted(scope.items()):
        for c in units_view.class_checks(engine, cik, limit=3):
            any_cls = True
            lines.append(
                f"  {ticker} {c.form} {c.filed}: instance {c.instance_total:,.0f} ("
                + ", ".join(f"{n} {v:,.0f}" for n, v in c.instance)
                + f") vs R1 {'—' if c.r1_total is None else f'{c.r1_total:,.0f}'}: "
                f"{c.agree}"
            )
    if not any_cls:
        lines.append("  no per-class cover facts in the stored instances")
    lines.append(
        "Invitae non-GAAP gross margin YoY (expected 2020Q1 −7.0, Q2 −31.6, Q3 −6.7, "
        "Q4 −2.3 pp) and billable units (469k → 1,290k):"
    )
    for m in exhibits.non_gaap_margin_yoy(engine, INVITAE[1]):
        lines.append(
            f"  {m.label}: {m.margin:.1%} vs {m.prior:.1%} → {m.pp:+.1f} pp ({m.accession})"
        )
    for r in units.kpi_rows(engine, INVITAE[1]):
        if r.metric == "billable_units" and r.later[0].startswith("Q"):
            e = f"{r.earlier[0]} {r.earlier[1]:,.0f}" if r.earlier else "—"
            lines.append(f"  billable units: {e} → {r.later[0]} {r.later[1]:,.0f}")
    for y in ("FY2019", "FY2020", "FY2021", "FY2022"):
        v, src = units.period_value(engine, INVITAE[1], "billable_units", y)
        lines.append(f"  billable units {y}: " + (f"{v:,.0f} ({src})" if v is not None else src))
    lines.append("Target gross margin (expected 2022Q1 −4.4, Q2 −8.9 pp):")
    for label, end, prior in units_view.TARGET_QUARTERS:
        pp, cur, old = units.gm_yoy_pp(engine, TARGET[1], end, prior)
        lines.append(
            f"  {label}: "
            + (
                f"{cur.gm:.1%} vs {old.gm:.1%} → {pp:+.1f} pp ({cur.basis})"
                if pp is not None
                else f"{cur.basis}; prior {old.basis}"
            )
        )
    return lines


def units_run(engine, corpus, comps: dict[str, str], now, log, client=None, clog=None) -> None:
    """The `units` work on open connections (tests inject a scratch DB and a fake client;
    `client=None` = no SEC requests)."""
    from engine.financials import exhibits, units, units_step
    from engine.sec import instance_dim

    scope = units_step.full_scope(engine, comps)
    log(f"Scope: {len(scope)} core and promoted companies (tracked names: facts only, D-M04-80)")
    if RIVN[1] not in scope.values():
        log(
            "RIVN not covered yet: promote it on the UI first (open /c/RIVN, Themes tab, "
            "Track, then Promote; D-M04-81). Its backfill is skipped until then.",
            "",
        )
    elif (
        client is not None
        and not engine.execute(
            "SELECT 1 FROM refresh_state WHERE name = ?", (f"backfill:{RIVN[1]}",)
        ).fetchone()
        and not engine.execute(
            "SELECT 1 FROM refresh_state WHERE name = ?", (f"m04_units_backfill:{RIVN[1]}",)
        ).fetchone()
    ):
        log("RIVN promoted, not backfilled yet: M04 backfill (filings, facts, documents):")
        rivn_backfill(client, engine, corpus, now, log)
        engine.execute(
            "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES "
            "(?, 'm04', ?, NULL) ON CONFLICT (name) DO NOTHING",
            (f"m04_units_backfill:{RIVN[1]}", now.isoformat()),
        )
        log("")
    else:
        log("RIVN promoted and backfilled", "")

    instance_log: dict[str, dict] = {}
    ex_log: dict[str, dict] = {}
    if client is not None:
        since = instance_dim.backfill_since(now)
        log(
            f"XBRL instances (10-K, 10-Q, 20-F, 40-F, XBRL 6-K filed since {since}; one read keeps "
            "extension and dimensional facts; files not cached):"
        )
        t0 = time.monotonic()
        stop = False
        for ticker, cik in sorted(scope.items()):
            due = instance_dim.due_filings(engine, cik, since)
            st = {"read": 0, "mb": 0.0, "dims": 0, "problems": []}
            for f in due:
                r = instance_dim.read_instance(client, engine, cik, f, now)
                if r.outcome == "ok":
                    st["read"] += 1
                    st["mb"] += r.mb
                    st["dims"] += r.dim_new
                else:
                    st["problems"].append(
                        f"{ticker} {f['form']} {f['accession']}: {r.outcome} {r.detail}".rstrip()
                    )
                if r.throttled:
                    stop = True
                    break
            instance_log[ticker] = st
            log(
                f"  {ticker}: {len(due)} due; read {st['read']} ({st['mb']:.1f} MB), "
                f"{st['dims']:,} dimensional rows"
                + (f"; {len(st['problems'])} problem(s)" if st["problems"] else "")
            )
            if stop:
                log("  SEC throttle: the rest waits for the next run")
                break
        if clog is not None:
            clog.seconds["XBRL instance"] += time.monotonic() - t0
        log("")
        log("EX-99.2 (last 4 earnings 8-Ks per company; index pages usually cached):")
        t1 = time.monotonic()
        for ticker, cik in sorted(scope.items()):
            if stop:
                break
            ex = exhibits.fetch_ex992(client, engine, corpus, cik, now)
            ex_log[ticker] = {"checked": ex.checked, "found": ex.found, "stored": ex.stored}
            for x in ex.failed or []:
                log(f"  {ticker}: {x}")
            stop = ex.throttled
        if clog is not None:
            clog.seconds["other"] += time.monotonic() - t1
        log(
            "  "
            + (
                " · ".join(
                    f"{t} {v['found']} of {v['checked']}"
                    for t, v in sorted(ex_log.items())
                    if v["checked"]
                )
                or "nothing new to check"
            )
        )
        log("")
        if not stop:
            log(f"Invitae earnings releases {INVITAE[2]}..{INVITAE[3]} (EX-99.1 only):")
            n, new, probs = exhibits.fetch_episode_releases(
                client, engine, corpus, INVITAE[1], INVITAE[2], INVITAE[3], now
            )
            log(f"  {n} earnings 8-K(s), {new} new EX-99.1 document(s)")
            log(*[f"  {p}" for p in probs[:10]])
            log("Target companyconcept and 10-Q instances (FY2021–22 Q1–Q2):")
            target_check(client, engine, now, log, clog)
            log("")
    else:
        log("SEC skipped (--no-sec): stored instances, releases and facts used", "")

    t2 = time.monotonic()
    docs = rows = tables = 0
    queued: dict[str, int] = {}
    for ticker, cik in sorted(scope.items()) + [(INVITAE[0], INVITAE[1])]:
        try:
            s = units.scan_company(engine, corpus, cik, now)
            docs, rows = docs + s.docs, rows + s.rows
            tables += exhibits.scan_releases(engine, corpus, cik, now)
            if cik in scope.values():
                for k, v in units.propose_breaks(engine, cik, ticker, now).items():
                    queued[k] = queued.get(k, 0) + v
        except Exception as e:  # one company's error must not stop the others
            for c in (engine, corpus):
                if c.in_transaction:
                    c.execute("ROLLBACK")
            log(f"  {ticker}: error — {type(e).__name__}: {e}")
    log(
        f"Unit KPIs from stored text (0 requests, {time.monotonic() - t2:.1f} s): {docs} "
        f"document(s) scanned, {rows} unit row(s) added, {tables} release-table row(s); "
        f"m04_unit_kpi items: {', '.join(f'{k} {v}' for k, v in sorted(queued.items())) or 'none'}",
        "",
    )
    log(*units_summary(engine, scope, instance_log, ex_log, corpus))


def run_units(args, log: Log, folder: Path) -> int:
    from engine.store.db import open_db
    from engine.store.http import SqliteCache, SqliteFetchLog

    engine = open_db("engine", folder)
    corpus = open_db("corpus", folder, check_same_thread=False)
    now = datetime.now(UTC)
    mb_before, before = db_mb(folder), units_counts(engine)
    comps = companies(engine)
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    head = f"run_financials units · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} companies"
    log(head + (" · no SEC" if args.no_sec else ""), f"engine.db before: {mb_before:,.1f} MB", "")
    client = clog = None
    if not args.no_sec:
        from engine.sec.client import SecClient, user_agent_from_env

        clog = CountingLog(SqliteFetchLog(engine))
        client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=clog)
    units_run(engine, corpus, comps, now, log, client, clog)
    if clog is not None:
        log(*clog.lines())
    else:
        log("SEC requests: 0 (--no-sec)")
    after = units_counts(engine)
    log(
        "Rows added per table: " + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in UNITS_TABLES)
    )
    log(f"engine.db: {mb_before:,.1f} MB → {db_mb(folder):,.1f} MB")
    corpus.close()
    engine.close()
    return 0


# --- gate (Part 4a) ------------------------------------------------------------------------

GATE_TABLES = ("credit_line", "fact", "entity", "signal", "m04_proposal", "review_queue",
               "refresh_state")  # fmt: skip
# Episode companies for the gate's regression lines (D-M04-32, SB.18): one companyconcept
# file per gate input (D-SEC-25); a company the refresh already covers (RIVN once promoted,
# D-M04-81) reads its stored facts instead (0 requests).
GATE_EPISODES = (
    ("Invitae", "0001501134", "8071", "INVITAE CORP"),
    ("RIVN", "0001874178", "3711", "Rivian Automotive, Inc. / DE"),
)
GATE_TAGS = (
    "CashAndCashEquivalentsAtCarryingValue", "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    "MarketableSecuritiesCurrent", "ShortTermInvestments", "RestrictedCash",
    "NetCashProvidedByUsedInOperatingActivities",
    "PaymentsToAcquirePropertyPlantAndEquipment", "Assets", "AssetsCurrent", "LiabilitiesCurrent",
    "Liabilities", "RetainedEarningsAccumulatedDeficit", "StockholdersEquity",
    "OperatingIncomeLoss", "RevenueFromContractWithCustomerExcludingAssessedTax",
    "NetIncomeLoss", "LongTermDebtNoncurrent",
)  # fmt: skip
INVITAE_103 = "2024-02-14"  # 8-K items 1.03 and 2.04 (S-new-r4-6)
BA_CIK = "0000012927"
# Stated credit lines for the Boeing regression lines (PROBE_RESULTS S11); shown, never stored.
BA_LINES = {
    "FY2019": ("2020-01-31", "2019-12-31", (("364-day", 3.2e9, "2020-10-30"),
               ("three-year", 3.2e9, "2022-10-30"), ("five-year", 3.2e9, "2024-10-30"))),
    "Q2 2024": ("2024-07-31", "2024-06-30", (("five-year", 4.0e9, "2029-05-15"),
                ("364-day", 3.0e9, "2025-08-25"), ("three-year", 3.0e9, "2028-08-25"))),
    "Q2 2022": ("2022-07-27", "2022-06-30", ()),
}  # fmt: skip
BA_EXPECT = {
    "FY2019": (
        "fail 3.6; 12-month test passes; + 4 × burn warns (DebtCurrent 7,340 holds CP 6,109)",
        "fail 5.9 (6,400 beyond 12 months)",
    ),
    "Q2 2024": ("fail 3.1", "fail 5.5; 7,000 beyond 24 months"),
    "Q2 2022": ("warn 6.1 cash-only (wall warn: 5,406 + 4 × 1,874 > 11,448)", ""),
}


def gate_counts(engine) -> dict[str, int]:
    return {t: engine.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in GATE_TABLES}


def gate_episodes(client, engine, comps, now, log, clog=None) -> None:
    """Companyconcept files for the episode companies the refresh does not cover."""
    from engine.sec.results import NotFound, Ok
    from engine.sec.xbrl_facts import CONCEPT_URL, store_concept

    t0 = time.monotonic()
    for name, cik, sic, legal in GATE_EPISODES:
        engine.execute(
            "INSERT INTO entity (cik, name, sic, fiscal_year_end, source_ref, fetched_at) "
            "VALUES (?, ?, ?, '1231', 'M04 Part 4a episode', ?) ON CONFLICT (cik) DO UPDATE SET "
            "sic = coalesce(entity.sic, excluded.sic)",
            (cik, legal, sic, now.isoformat(timespec="seconds")),
        )
        if cik in comps.values():
            log(f"  {name}: covered (refresh facts stored), 0 requests")
            continue
        got = []
        for tag in GATE_TAGS:
            url = CONCEPT_URL.format(cik=cik, taxonomy="us-gaap", tag=tag)
            res = client.get_json(url, ttl_s=30 * 86400)
            if isinstance(res, Ok):
                engine.execute("BEGIN")
                seen, new = store_concept(engine, cik, res.data)
                engine.execute("COMMIT")
                got.append(f"{tag} {seen}/{new}")
            elif isinstance(res, NotFound):
                got.append(f"{tag} 404")
            else:
                got.append(f"{tag} failed: {res}")
        log(f"  {name}: " + "; ".join(got))
    if clog is not None:
        clog.seconds["companyconcept"] += time.monotonic() - t0


def _gate_line(log, label, g, expect) -> None:
    from engine.financials import gate

    rb = " · ".join(f"{k} {v:.1f}" if v is not None else f"{k} —"
                    for k, v in g.runway_by_basis.items()) or "—"  # fmt: skip
    trig = ("; trigger: " + "; ".join(g.triggers)) if g.triggers else ""
    miss = ("; missing: " + "; ".join(g.missing)) if g.missing else ""
    log(f"  {label}: {g.state} [{g.scope_name}] — runway {g.runway_text()} "
        f"({g.tier_text}; {rb}); liquidity "
        f"{gate.money(g.liquidity)} as of {g.balance_date}; wall {g.wall_test[0]} "
        f"({g.debt12_text or 'no debt tags'}){trig}{miss} | expected: {expect}")  # fmt: skip


def gate_regression(engine, now, log, mf=None) -> None:
    """The fixture cases against the stored data (M04_BUILD_LOG Part 4a; SB.18)."""
    from datetime import date

    from engine.financials import distress, gate

    log("Regression cases (stored data, as of the dates shown; credit lines stated in the "
        "probe are passed in, never stored):")  # fmt: skip
    nv = gate.evaluate(engine, "0001501134", "Invitae", "2022-03-01", calendar=False, models=mf)
    lead = (date.fromisoformat(INVITAE_103) - date(2022, 3, 1)).days
    _gate_line(log, f"Invitae FY2021 (as of 2022-03-01, {lead} days before its 8-K 1.03)", nv,
               "fail, 5.6 (last two quarters) / 6.8 (TTM)")  # fmt: skip
    sc = distress.score(engine, "0001501134", "Invitae", "2022-03-01", models=mf)
    log(f"    Invitae distress {sc.text()} (expected Z'' 1.31 grey); {sc.method()}")
    today = now.date().isoformat()
    rv = gate.evaluate(engine, "0001874178", "RIVN", today, models=mf)
    _gate_line(log, "Rivian latest, cash-only unless a line is confirmed", rv,
               "Q2 2026: fail 5.5 cash-only; 6.1 (warn) with the ABL past 12 months")  # fmt: skip
    if rv.balance_date:
        abl = gate.Credit(None, "ABL (pack: 536 derived; not confirmed)", 536e6,
                          f"{int(rv.balance_date[:4]) + 3}{rv.balance_date[4:]}", rv.balance_date,
                          "B", "M04_DESIGN_PACK Rivian worked example", False, "")  # fmt: skip
        _gate_line(log, "Rivian with the ABL as if confirmed",
                   gate.evaluate(engine, "0001874178", "RIVN", today, extra_credit=(abl,),
                                 models=mf), "warn 6.1")  # fmt: skip
        rs = distress.score(engine, "0001874178", "RIVN", today, close_day=today, models=mf)
        zpp = f" (Z'' {rs.zpp:.2f}; expected −5.37 at Q2 2026)" if rs.zpp is not None else ""
        log(f"    Rivian distress {rs.text()}{zpp}")
    for label, (as_of, bs, lines_) in BA_LINES.items():
        cash = gate.evaluate(engine, BA_CIK, "BA", as_of, calendar=False, models=mf)
        _gate_line(log, f"Boeing {label} cash-only", cash, BA_EXPECT[label][0])
        if lines_:
            extra = tuple(gate.Credit(None, f, a, m, bs, "A", "PROBE_RESULTS S11", False, "")
                          for f, a, m in lines_)  # fmt: skip
            g = gate.evaluate(
                engine, BA_CIK, "BA", as_of, calendar=False, extra_credit=extra, models=mf
            )
            _gate_line(log, f"Boeing {label} with the stated lines", g, BA_EXPECT[label][1])
            far = sum(c.amount for c in g.credits if c.beyond_24m)
            log(f"    credit beyond 24 months: {gate.money(far)}")
    ig = gate.evaluate(engine, "0000050863", "INTC", "2025-01-31", calendar=False, models=mf)
    _gate_line(log, "Intel FY2024 (as of 2025-01-31)", ig,
               "warn, capex-funded 5.6 → m04_runway (balance sheet 2024-12-28)")  # fmt: skip
    log(f"    method: {ig.method()}")
    fq = gate.evaluate(engine, "0002007825", "INFQ", "2026-02-12", calendar=False, models=mf)
    _gate_line(log, "INFQ before the closing (as of 2026-02-12)", fq,
               "trust only: pass on the trust account (spac_shell before 2026-02-13)")  # fmt: skip
    log(f"    method: {fq.method()}")


def gate_summary(engine, gp, now) -> list[str]:
    from engine.financials import gate_step

    out = [f"{SUMMARY_MARK} gate (Part 4a) · {now:%Y-%m-%d %H:%M} UTC"]
    states: dict[str, int] = {}
    for c in gp.companies.values():
        if c.gate:
            states[c.gate.state] = states.get(c.gate.state, 0) + 1
    out.append("Gate states: " + ", ".join(f"{k} {v}" for k, v in sorted(states.items())))
    no_trigger = [c.ticker for c in gp.companies.values()
                  if c.gate and c.gate.state == "fail" and not c.gate.triggers]  # fmt: skip
    out.append(f"Fails without a trigger: {len(no_trigger)}"
               + (f" ({', '.join(no_trigger)})" if no_trigger else ""))  # fmt: skip
    queued: dict[str, int] = {}
    for c in gp.companies.values():
        for k, v in c.queued.items():
            v = "already proposed by an earlier run" if v == "suppressed" else v
            key = f"{k.split(':')[0]} {v}"
            queued[key] = queued.get(key, 0) + 1
    out.append("Part 4a items this run: "
               + (", ".join(f"{k} {v}" for k, v in sorted(queued.items())) or "none"))  # fmt: skip
    held = [f"{c.ticker} {k}" for _, c in sorted(gp.companies.items()) for k in c.held]
    if held:
        out.append("Tracked names, rows only, no review items (D-M04-80): " + ", ".join(held))
    items = gate_step.open_items(engine)
    out.append(f"Open Part 4a items: {len(items)}")
    out += [f"  {x}" for x in items]
    withdrawn = sum(c.withdrawn for c in gp.companies.values())
    if withdrawn:
        out.append(f"Items withdrawn (condition no longer holds): {withdrawn}")
    out += [f"  alert: {a}" for a in gp.alerts]
    n_lines = engine.execute(
        "SELECT count(*) FROM credit_line WHERE status = 'confirmed'"
    ).fetchone()[0]
    out.append(f"Credit lines confirmed: {n_lines}")
    out.append("One line per company:")
    out += [f"  {gate_step.company_line(c)}" for _, c in sorted(gp.companies.items())]
    return out


def gate_run(engine, comps: dict[str, str], now, log, client=None, clog=None, mf=None):
    """The `gate` work on open connections (tests inject a scratch DB and a fake client;
    `client=None` = no SEC requests)."""
    from engine.financials import gate, gate_step

    if client is not None:
        log("Episode companyconcept files (Invitae; Rivian unless covered):")
        gate_episodes(client, engine, comps, now, log, clog)
        log("")
    else:
        log("SEC skipped (--no-sec): stored facts only", "")
    t0 = time.monotonic()
    gp = gate_step.gate_pass(engine, comps, now, mf=mf)
    log(f"Gate, distress, debt and FCF rows recomputed for {len(gp.companies)} companies "
        f"(0 requests, {time.monotonic() - t0:.1f} s)", "")  # fmt: skip
    for _, c in sorted(gp.companies.items()):
        log(gate_step.company_line(c))
        if c.gate is not None:
            log(f"    method: {c.gate.method()}")
            if c.score is not None:
                log(f"    distress: {c.score.text()}; {c.score.method()}")
            for cr in c.gate.credits:
                log(f"    credit: {cr.facility} {gate.money(cr.amount)} to {cr.maturity} "
                    f"(stated for {cr.as_of}): {cr.why}")  # fmt: skip
    log("")
    gate_regression(engine, now, log, mf)
    log("")
    log(*gate_summary(engine, gp, now))
    return gp


def run_gate(args, log: Log, folder: Path) -> int:
    from engine.store.db import open_db
    from engine.store.http import SqliteCache, SqliteFetchLog

    engine = open_db("engine", folder)
    corpus = open_db("corpus", folder, check_same_thread=False)
    now = datetime.now(UTC)
    mb_before, before = db_mb(folder), gate_counts(engine)
    comps = companies(engine)
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    head = f"run_financials gate · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} companies"
    log(head + (" · no SEC" if args.no_sec else ""), f"engine.db before: {mb_before:,.1f} MB", "")
    client = clog = None
    if not args.no_sec:
        from engine.sec.client import SecClient, user_agent_from_env

        clog = CountingLog(SqliteFetchLog(engine))
        client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=clog)
    gate_run(engine, comps, now, log, client, clog)
    if clog is not None:
        log(*clog.lines())
    else:
        log("SEC requests: 0 (--no-sec)")
    after = gate_counts(engine)
    log("Rows added per table: " + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in after))
    log(f"engine.db: {mb_before:,.1f} MB → {db_mb(folder):,.1f} MB")
    corpus.close()
    engine.close()
    return 0


# --- gate-text (Part 4b-lite) ----------------------------------------------------------------

GATE_TEXT_TABLES = ("gate_text", "signal", "m04_proposal", "review_queue", "refresh_state")
GATE_TEXT_SHOWN = 12  # "no trigger" rows printed per company (the rest counted)


def gate_text_counts(engine) -> dict[str, int]:
    return {t: engine.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in GATE_TEXT_TABLES}


def _stored_gate_state(engine, cik: str) -> str:
    r = engine.execute(
        "SELECT value_text, method FROM signal WHERE cik = ? AND module_id = 'M04' AND "
        "signal = 'survival_gate' AND timeframe = 'MY' ORDER BY as_of DESC LIMIT 1",
        (cik,),
    ).fetchone()
    return (r["value_text"] or "missing") if r else "not computed"


def gate_text_company_lines(engine, ct) -> list[str]:
    """Per company: documents scanned, the current report, hits per class with quotes,
    baseline rows, signals and items (M04_BUILD_LOG Part 4b "The owner looks for")."""
    from engine.financials import gate_text

    if ct.error:
        return [f"{ct.ticker}: error — {ct.error}"]
    s, tg = ct.scan, ct.tg
    cur = tg.current
    out = [
        f"{ct.ticker}: documents scanned {s.docs_read} new, {s.docs_skipped} already scanned"
        f"{' (first scan: baseline)' if s.first else ''}; {s.sentences} trigger sentence(s); "
        f"covenant hypotheticals counted, not stored: {s.hypothetical_cov}; rows added "
        f"{s.rows_new}" + (f"; kept (answered or reviewed) {s.rows_kept}" if s.rows_kept else "")
    ]
    rep = cur.report if cur else None
    out.append(
        "    current report: "
        + (
            f"{rep['form']} {rep['accession']} filed {rep['filed']} (period "
            f"{rep['period_end'] or '—'})"
            if rep
            else ("6-Ks of the last 400 days" if cur and cur.accessions else "none stored")
        )
        + (f" + {len(cur.accessions) - 1} later 6-K(s)" if rep and len(cur.accessions) > 1 else "")
        + (f"; {cur.note}" if cur and cur.note else "")
    )
    if s.no_text:
        out.append(f"    periodic filings without stored text: {len(s.no_text)} (newest: "
                   f"{s.no_text[0]})")  # fmt: skip
    rows = gate_text.rows_for(engine, ct.cik)
    accs = cur.accessions if cur else set()
    counts: dict[str, list[int]] = {}
    for r in rows:
        c = counts.setdefault(r["class"], [0, 0])
        c[0] += 1
        c[1] += int(r["accession"] in accs)
    out.append(
        "    hits per class: "
        + (", ".join(f"{k} {v[0]} (current {v[1]})" for k, v in sorted(counts.items())) or "none")
        + f"; baseline rows {sum(r['baseline'] for r in rows)}"
    )
    quiet = 0
    for r in rows:
        eff = gate_text.effective(r)
        is_cur = r["accession"] in accs
        if eff == "none" and (not is_cur or quiet >= GATE_TEXT_SHOWN):
            continue
        quiet += int(eff == "none")
        q = r["quote"] if len(r["quote"]) <= 300 else r["quote"][:297] + "…"
        out.append(
            f"      [{'current' if is_cur else 'history'}] {r['class']} — {r['form']} "
            f"{r['accession']} ({r['doc_type'] or r['form']}) filed {r['filed']}, period "
            f"{r['period_end'] or '—'}: {gate_text.effect_text(r, is_cur, ct.review_hypo)}: “{q}”"
            + (f" [{r['note']}]" if r["note"] else "")
        )
    out.append(
        f"    signals: gc_language {ct.signals.get('gc_language', '—')}; covenant_status "
        f"{ct.signals.get('covenant_status', '—')}; hypothetical review: "
        f"{'yes' if ct.review_hypo else 'no'} ({ct.runway_why})"
    )
    if ct.queued:
        out.append("    items: " + ", ".join(f"{k} {v}" for k, v in sorted(ct.queued.items())))
    if ct.held:
        out.append("    tracked, rows only (D-M04-80): would open " + ", ".join(ct.held))
    return out


def gate_text_summary(engine, corpus, tp, before, after, now) -> list[str]:
    from engine.financials import gate_text, gate_text_step

    out = [f"{SUMMARY_MARK} gate-text (Part 4b-lite) · {now:%Y-%m-%d %H:%M} UTC"]
    comps = tp.companies.values()
    read = sum(c.scan.docs_read for c in comps if c.scan)
    skipped = sum(c.scan.docs_skipped for c in comps if c.scan)
    out.append(f"Documents scanned: {read} new, {skipped} already scanned (classifier "
               f"{gate_text.SCAN_VERSION}); SEC requests 0 (stored text only)")  # fmt: skip
    rows = engine.execute("SELECT * FROM gate_text").fetchall()
    ok, n = gate_text.verify_rows(corpus, rows)
    out.append(f"Quotes verified against the stored documents: {ok} of {n} (D21)")
    per: dict[str, int] = {}
    for r in rows:
        per[r["class"]] = per.get(r["class"], 0) + 1
    out.append("Rows per class (all reports): "
               + (", ".join(f"{k} {v}" for k, v in sorted(per.items())) or "none"))  # fmt: skip
    out.append(f"Baseline rows (first scan): {sum(r['baseline'] for r in rows)}")
    fails = [f"{c.ticker} ({'; '.join(sorted({x.split(' — ')[0] for x, _ in c.tg.fails}))})"
             for c in comps if c.tg and c.tg.fails]  # fmt: skip
    warns = [f"{c.ticker} ({'; '.join(sorted({x.split(' — ')[0] for x, _ in c.tg.warns}))})"
             for c in comps if c.tg and c.tg.warns]  # fmt: skip
    out.append("Current-report fail classes: " + (", ".join(fails) or "none"))
    out.append("Current-report warn classes: " + (", ".join(warns) or "none"))
    queued: dict[str, int] = {}
    for c in comps:
        for k, v in c.queued.items():
            v = "already proposed by an earlier run" if v == "suppressed" else v
            key = f"{k.split(':')[0]} {v}"
            queued[key] = queued.get(key, 0) + 1
    out.append("Part 4b items this run: "
               + (", ".join(f"{k} {v}" for k, v in sorted(queued.items())) or "none"))  # fmt: skip
    held = [f"{c.ticker} {k}" for c in comps for k in c.held]
    if held:
        out.append("Tracked names, rows only, no review items (D-M04-80): " + ", ".join(held))
    withdrawn = sum(c.withdrawn for c in comps)
    if withdrawn:
        out.append(f"Items withdrawn (finding no longer holds): {withdrawn}")
    items = gate_text_step.open_items(engine)
    out.append(f"Open Part 4b items: {len(items)}")
    out += [f"  {x}" for x in items]
    out += [f"  alert: {a}" for a in tp.alerts]
    changes = [f"{t}: {before.get(t, '—')} → {after[t]}" for t in sorted(after)
               if before.get(t) != after[t]]  # fmt: skip
    out.append("Gate changes after the text pass: " + (", ".join(changes) or "none"))
    sig = [
        f"{c.ticker} {c.signals.get('gc_language', '—')} / {c.signals.get('covenant_status', '—')}"
        for c in comps
    ]
    out.append("gc_language / covenant_status: " + ", ".join(sig))
    out.append("Deferred (MVP): EDGAR full-text history (S4.7), undrawn-credit finder, "
               "m04_current_jump (D-M04-99)")  # fmt: skip
    return out


def gate_text_run(engine, corpus, comps: dict[str, str], now, log, mf=None):
    """The `gate-text` work on open connections (0 SEC requests; tests inject scratch DBs)."""
    from engine.financials import gate_step, gate_text_step

    before = {t: _stored_gate_state(engine, c) for t, c in comps.items()}
    t0 = time.monotonic()
    tp = gate_text_step.text_pass(engine, corpus, comps, now, mf=mf)
    log(f"Gate text scanned and classified for {len(tp.companies)} companies "
        f"(0 requests, {time.monotonic() - t0:.1f} s)", "")  # fmt: skip
    for _, c in sorted(tp.companies.items()):
        log(*gate_text_company_lines(engine, c))
    log("")
    t1 = time.monotonic()
    gp = gate_step.gate_pass(engine, comps, now, mf=mf)
    after = {t: c.gate.state if c.gate else "error" for t, c in gp.companies.items()}
    log(f"Survival gate recomputed with the text classes ({time.monotonic() - t1:.1f} s):")
    for _, c in sorted(gp.companies.items()):
        if c.gate is not None and (c.gate.text_summary or "").startswith(("fail", "warn")):
            log(f"  {c.ticker}: {c.gate.state} — text {c.gate.text_summary}")
    log("")
    log(*gate_text_summary(engine, corpus, tp, before, after, now))
    return tp, gp


def run_gate_text(args, log: Log, folder: Path) -> int:
    from engine.store.db import open_db

    engine = open_db("engine", folder)
    corpus = open_db("corpus", folder, check_same_thread=False)
    now = datetime.now(UTC)
    mb_before, before = db_mb(folder), gate_text_counts(engine)
    comps = companies(engine)
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    log(f"run_financials gate-text · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} companies · "
        "stored text only (0 SEC requests" + ("; --no-sec has no effect" if args.no_sec else "")
        + ")", f"engine.db before: {mb_before:,.1f} MB", "")  # fmt: skip
    gate_text_run(engine, corpus, comps, now, log)
    log("SEC requests: 0 (stored text only)")
    after = gate_text_counts(engine)
    log("Rows added per table: " + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in after))
    log(f"engine.db: {mb_before:,.1f} MB → {db_mb(folder):,.1f} MB")
    corpus.close()
    engine.close()
    return 0


# --- quality (Part 6) ----------------------------------------------------------------------

QUALITY_TABLES = ("estimate_change", "special_item", "signal", "m04_proposal", "review_queue",
                  "fact", "refresh_state")  # fmt: skip
LMT = ("Lockheed Martin", "0000936468")
LMT_TAG = "ContractWithCustomerPerformanceObligationSatisfiedInPreviousPeriod"
GE_CONTRACT_TAG = "UnbilledContractsReceivable"
GE_YEARS = ("2016-12-31", "2017-12-31")  # FY2016 (instance + text) and FY2017 (text) 10-Ks
# Round 2's scratch values (M04_BUILD_LOG Part 6 fixtures; recomputed here from stored facts)
QUALITY_EXPECTED = {
    ("NVDA", "FY2025"): "M −0.96 / SGI = 1 −1.98, F 3.11 → growth-driven note",
    ("NVDA", "FY2026"): "M −1.17 / SGI = 1 −1.75 → m04_mscore",
    ("MRVL", "FY2026"): "M −1.60 / SGI = 1 −1.98 → note; F missing (issue unknown)",
    ("AAPL", "FY2025"): "M −2.29 / SGI = 1 −2.35, F 1.30",
    ("MSFT", "FY2025"): "M −2.54 / SGI = 1 −2.67, F 1.15",
    ("BA", "FY2024"): "M incomplete in Round 2 (no SG&A tag); since live check 1 on G&A only, "
                      "F 1.63",
    ("MU", "FY2023"): "M −7.01 → not meaningful (gross margin ≤ 0)",
    ("MSTR", "FY2025"): "not meaningful (asset_treasury)",
}  # fmt: skip


def quality_counts(engine) -> dict[str, int]:
    return {t: engine.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in QUALITY_TABLES}


def _concept_file(client, engine, cik: str, tag: str, who: str, log) -> None:
    from engine.sec.results import NotFound, Ok
    from engine.sec.xbrl_facts import CONCEPT_URL, store_concept

    res = client.get_json(
        CONCEPT_URL.format(cik=cik, taxonomy="us-gaap", tag=tag), ttl_s=30 * 86400
    )
    if isinstance(res, NotFound):
        log(f"  {who} us-gaap:{tag}: not found")
        return
    if not isinstance(res, Ok):
        log(f"  {who} us-gaap:{tag}: {res}")
        return
    engine.execute("BEGIN")
    seen, new = store_concept(engine, cik, res.data)
    engine.execute("COMMIT")
    log(f"  {who} us-gaap:{tag}: {seen} facts, {new} new")


def ge_annual(engine, period_end: str):
    """GE's 10-K that first reported the fiscal year (from its stored facts)."""
    return engine.execute(
        "SELECT accession, filed FROM fact WHERE cik = ? AND form = '10-K' AND period_end = ? "
        "AND period_start IS NOT NULL ORDER BY filed, accession LIMIT 1",
        (GE_CIK, period_end),
    ).fetchone()


def quality_reference_fetch(client, engine, corpus, now, log, clog=None) -> None:
    """GE (contract assets, estimate text) and Lockheed (catch-up revenue): ~6–10 requests."""
    from engine.financials import filings
    from engine.sec import instance_dim

    t0 = time.monotonic()
    log("GE and Lockheed reference files:")
    if engine.execute("SELECT 1 FROM fact WHERE cik = ? AND tag = 'Revenues' LIMIT 1",
                      (GE_CIK,)).fetchone() is None:  # fmt: skip
        log("  GE revenue not stored (Part 3's flags run stores it): fetching Revenues and pretax")
        for tag in ("Revenues", GE_TAGS[6]):
            _concept_file(client, engine, GE_CIK, tag, "GE", log)
    _concept_file(client, engine, GE_CIK, GE_CONTRACT_TAG, "GE", log)
    _concept_file(client, engine, LMT[1], LMT_TAG, "Lockheed", log)
    if clog is not None:
        clog.seconds["companyconcept"] += time.monotonic() - t0
    t1 = time.monotonic()
    fy16 = ge_annual(engine, GE_YEARS[0])
    if fy16 is None:
        log("  GE FY2016 10-K: no stored fact names it (run `flags` first); instance skipped")
    elif engine.execute("SELECT 1 FROM fact WHERE cik = ? AND accession = ? AND taxonomy = 'ge' "
                        "LIMIT 1", (GE_CIK, fy16["accession"])).fetchone():  # fmt: skip
        log(f"  GE FY2016 10-K instance {fy16['accession']}: extension facts already stored")
    else:
        f = {"accession": fy16["accession"], "primary_doc": None, "form": "10-K",
             "filed": fy16["filed"], "report_date": GE_YEARS[0]}  # fmt: skip
        r = instance_dim.read_instance(client, engine, GE_CIK, f, now)
        ga = engine.execute("SELECT period_end, value FROM fact WHERE cik = ? AND tag = "
                            "'ContractAsset' AND taxonomy = 'ge' ORDER BY period_end",
                            (GE_CIK,)).fetchall()  # fmt: skip
        log(f"  GE FY2016 10-K instance {fy16['accession']}: {r.outcome} ({r.mb:.1f} MB, "
            f"{r.ext_new} extension facts) {r.detail}".rstrip()
            + "; ge:ContractAsset " + (", ".join(f"{x[0]} {float(x[1]) / 1e6:,.0f}M" for x in ga)
                                       or "not found"))  # fmt: skip
    if clog is not None:
        clog.seconds["XBRL instance"] += time.monotonic() - t1
    t2 = time.monotonic()
    for end in GE_YEARS:
        row = ge_annual(engine, end)
        if row is None:
            log(f"  GE 10-K for {end}: not named by any stored fact")
            continue
        got = filings.fetch_primary(client, engine, corpus, row["accession"], now, cik=GE_CIK,
                                    form="10-K")  # fmt: skip
        log(
            f"  GE 10-K {row['accession']} ({end}): {got.outcome}"
            + (f" — {got.detail}" if got.detail else "")
            + (f" ({got.mb:.1f} MB)" if got.mb else "")
        )
    if clog is not None:
        clog.seconds["other"] += time.monotonic() - t2
    log("")


def _score_lines(ticker: str, cq) -> list[str]:
    from engine.financials import quality

    q = cq.q
    if cq.error:
        return [f"  {ticker}: error — {cq.error}"]
    if q is None:
        return [f"  {ticker}: not computed"]
    if q.excluded:
        return [f"  {ticker}: {q.excluded} — {q.tag_how}"]
    out = [f"  {ticker} ({q.stage_label}; {q.tag_how}):"]
    for ms, fs in zip(q.mscores, q.fscores, strict=True):
        if ms.state == "ok":
            m = f"M {ms.m:.2f} / SGI = 1 {ms.m_sgi1:.2f} → {ms.reading}"
        elif ms.state == "not_meaningful":
            m = f"M not meaningful: {ms.why}"
        else:
            m = f"M incomplete: {ms.why}"
        f = (f"F {fs.score:.2f} ({fs.band})" if fs.score is not None
             else f"F {fs.state}: {fs.why}")  # fmt: skip
        out.append(f"    {ms.label}: {m}; {f}")
        if ms.components:
            out.append(
                "      M components: " + ", ".join(f"{k} {v:.3f}" for k, v in ms.components.items())
            )
        if fs.components:
            out.append(
                "      F components: " + ", ".join(f"{k} {v:.3f}" for k, v in fs.components.items())
            )
        subs = "; ".join(x for x in (ms.inputs.method(), fs.inputs.method()) if x)
        if subs:
            out.append(f"      {subs}")
        out.append(f"      inputs: {quality.inputs_text(ms.inputs.used + fs.inputs.used)[:900]}")
    cc = q.cash
    if cc.ratio3 is not None:
        line = f"    CFO/NI 3y {cc.ratio3:.2f} ({cc.state}); latest " + (
            f"{cc.latest:.2f}" if cc.latest is not None else "—"
        )
        if cc.accruals is not None:
            line += f"; accruals {cc.accruals:+.3f} ({cc.accruals_text})"
        out.append(line)
    else:
        out.append(f"    CFO/NI {cc.state}: {cc.why}")
    for y in cc.years:
        if y.operating:
            out.append(
                f"      {y.label}: operating basis NI {quality.money(y.basis_ni)}M (reported "
                f"{quality.money(y.ni.value)}M; {', '.join(w for w, _ in y.items)})"
            )
    for name, g in (("contract assets", q.contract), ("deferred revenue", q.deferred)):
        rs = "; ".join(
            f"{r.label} {r.line_growth:+.1%} vs revenue "
            + (f"{r.revenue_growth:+.1%}" if r.revenue_growth is not None else "—")
            + (
                ""
                if r.state == "scored"
                else f" [{r.state}" + (f": {r.note}" if r.note else "") + "]"
            )  # fmt: skip
            for r in g.readings[-3:]
        )
        out.append(
            f"    {name}: {g.state}" + (f" — {rs}" if rs else "") + (f" ({g.why})" if g.why else "")
        )
    return out


def quality_summary(engine, qp, ge_findings, ge_gap, lmt, ge_near=()) -> list[str]:
    """What the owner looks for (M04_BUILD_LOG Part 6 live check)."""
    from collections import Counter

    from engine.financials import quality

    lines = ["=== Summary (what the owner looks for) ==="]
    lines.append("Earnings-quality scores per company (latest 3 fiscal years; values as first "
                 "reported; inputs with tag and accession):")  # fmt: skip
    for t, cq in sorted(qp.companies.items()):
        lines += _score_lines(t, cq)
    lines.append("Round 2 scratch values vs this run:")
    for (t, label), want in QUALITY_EXPECTED.items():
        cq = qp.companies.get(t)
        got = "not in this run"
        if cq is not None and cq.q is not None:
            ms = next((m for m in cq.q.mscores if m.label == label), None)
            fs = next((f for f in cq.q.fscores if f.label == label), None)
            if cq.q.excluded:
                got = cq.q.excluded
            elif ms is None:
                got = f"{label} not among the last 3 fiscal years"
            else:
                got = (f"M {ms.m:.2f} / {ms.m_sgi1:.2f} ({ms.reading})" if ms.m is not None and
                       ms.state == "ok" else f"M {ms.state}" + (f" (raw {ms.m:.2f})" if ms.m is not
                       None else "")) + (f", F {fs.score:.2f}" if fs and fs.score is not None else
                       f", F {fs.state if fs else '—'}")  # fmt: skip
        lines.append(f"  {t} {label}: expected {want}; got {got}")
    props = engine.execute(
        "SELECT kind, status, reason, payload FROM m04_proposal WHERE kind IN ('m04_mscore', "
        "'m04_estimate') ORDER BY kind, status, first_seen_at"
    ).fetchall()
    by = Counter((r["kind"], r["status"]) for r in props)
    lines.append("Queued items (1 expected: NVDA FY2026 m04_mscore): " + (", ".join(
        f"{k} {s} {n}" for (k, s), n in sorted(by.items())) or "none"))  # fmt: skip
    lines += [f"  {r['status']}: {r['reason']}" for r in props if r["status"] != "baseline"]
    lines.append(f"Baseline (first scan, older than 12 months, shown not queued): "
                 f"{sum(1 for r in props if r['status'] == 'baseline')}")  # fmt: skip
    lines.append("Estimate sentences per company (band · share · amount ÷ denominator):")
    for t, cq in sorted(qp.companies.items()):
        if not cq.findings:
            continue
        lines.append(
            f"  {t}: {len(cq.findings)}"
            + (f"; recurrence {cq.recurrence}" if cq.recurrence else "")
        )
        for f in cq.findings[:8]:
            share = f"{f.share:+.1%}" if f.share is not None else "—"
            lines.append(f"    {f.form} {f.filed} {f.fiscal_label} {f.band} {share}: "
                         f"{quality.money(f.amount)}M {f.basis} ÷ {f.denominator_what or f.why} — "
                         f"“{f.quote[:220]}”")  # fmt: skip
    lines.append("GE reference (brief: 2016 2,200 ÷ 9,030 = 24.4% → watch; the FY2017 10-K "
                 "states 2017 / 2016 / 2015 = $2.1B / $2.2B / $1.4B, each ÷ that year's pretax "
                 "income as known on 2018-02-23, D-M04-18; a denominator other than 9,030 for "
                 "FY2016 is the figure as of that filing):")  # fmt: skip
    for f in ge_findings:
        share = f"{f.share:+.1%}" if f.share is not None else "—"
        lines.append(f"  {f.form} {f.accession} {f.filed} {f.fiscal_label} {f.band} {share}: "
                     f"{quality.money(f.amount)}M {f.basis} ÷ {f.denominator_what or f.why} — "
                     f"“{f.quote[:220]}”")  # fmt: skip
    if not ge_findings:
        lines.append("  no estimate sentence with an amount in GE's FY2016 / FY2017 10-K texts; "
                     "best candidates (score of 8 · accession · first 200 chars):")  # fmt: skip
        lines += [f"    {sc} · {acc} · “{t}”" for sc, acc, t in ge_near] or [
            "    none (no GE 10-K text stored for FY2016 / FY2017)"]  # fmt: skip
    lines.append(
        "GE contract assets (expected FY2016 +18.9% (spec +18.8%, owner accepted 2026-10-13), "
        "scored; FY2017 25,162 ge:ContractAsset → 28,861 UnbilledContractsReceivable, +14.7%: "
        "definition changed, not scored):"
    )
    for r in ge_gap.readings[-3:]:
        lines.append(f"  {r.label}: {r.prior.tag} {quality.money(r.prior.value)} → {r.line.tag} "
                     f"{quality.money(r.line.value)} ({r.line_growth:+.1%}); revenue "
                     + (f"{r.revenue_growth:+.1%}" if r.revenue_growth is not None else "—")
                     + f"; {r.state}")  # fmt: skip
    if not ge_gap.readings:
        lines.append(f"  {ge_gap.why or 'no readings'}")
    cu = "not stored"
    if lmt:
        cu = " · ".join(f"{lb} {v / 1e9:,.1f}B" for lb, v, _ in lmt.years)
        cu += f" — {lmt.flag}" if lmt.flag else ""
    lines.append(f"Lockheed catch-up revenue (expected 2.2B 2019 … 1.2B 2024): {cu}")
    lines.append("special_items (D-M04-94: a year counts only with an amount; warn = ≥ 3 of 4 "
                 "years and ≥ 5% of cumulative operating income; years counted of 4 · "
                 "cumulative ÷ operating income · state; then the source per year):")  # fmt: skip
    for t, cq in sorted(qp.companies.items()):
        sp = cq.special
        if sp is None:
            continue
        size = (f"{sp.ratio:.1%}" if sp.ratio is not None
                else f"{sp.ratio_why or sp.why} (tagged years {sp.tagged_years})")  # fmt: skip
        lines.append(f"  {t}: {sp.count} of {len(sp.years)} · {size} · {sp.state}"
                     + (" · non-GAAP sentence quoted" if sp.non_gaap else ""))  # fmt: skip
        for y in sp.years:
            lines.append(f"    {y.label}: {'counted' if y.has else 'not counted'} — {y.source}")
    lines.append("Non-operating swings (MSTR expected: digital-asset fair-value loss inside "
                 "operating income):")  # fmt: skip
    for t, cq in sorted(qp.companies.items()):
        if cq.q is None:
            continue
        for lb, what, v, effect, share in cq.q.swings:
            lines.append(
                f"  {t} {lb}: {what} {quality.money(v.value)}M ({v.tag}); after-tax "
                f"{quality.money(effect)}M"
                + (f", {share:.1%} of |NI|" if share is not None else "")
            )
    lines.append("Signals (eq_cash · mscore · misstate_f · estimate_share · special_items):")
    for t, cq in sorted(qp.companies.items()):
        s = cq.signals
        lines.append(f"  {t}: " + " · ".join(s.get(k, "—") for k in (
            "eq_cash", "mscore", "misstate_f", "estimate_share", "special_items")))  # fmt: skip
    lines.append(f"Overflow flushed this run: {qp.flushed}")
    return lines


def quality_run(engine, corpus, comps: dict[str, str], now, log, client=None, clog=None):
    """The `quality` work on open connections (tests inject a scratch DB and a fake client;
    `client=None` = no SEC requests)."""
    from engine.financials import estimates, quality, quality_step
    from engine.sec.client import iso

    if client is not None:
        quality_reference_fetch(client, engine, corpus, now, log, clog)
    else:
        log("SEC skipped (--no-sec): stored facts and text used", "")
    t0 = time.monotonic()
    qp = quality_step.quality_pass(engine, corpus, comps, now)
    ge_accs = [r["accession"] for r in (ge_annual(engine, e) for e in GE_YEARS) if r]
    ge_findings = estimates.scan(engine, corpus, GE_CIK, accessions=ge_accs or None)
    engine.execute("BEGIN")
    estimates.store(engine, ge_findings, GE_CIK, iso(now), False)
    engine.execute("COMMIT")
    ge_gap = quality.contract_asset_gap(quality.Facts(engine, GE_CIK))
    lmt = estimates.catch_up(engine, LMT[1])
    log(f"Scores, estimate sentences, special items and signals recomputed for "
        f"{len(qp.companies)} companies + GE and Lockheed references (0 requests, "
        f"{time.monotonic() - t0:.1f} s)", "")  # fmt: skip
    log(*quality_step.local_lines(qp))
    log("")
    ge_near = (estimates.near_misses(engine, corpus, GE_CIK, ge_accs or None)
               if not ge_findings else [])  # fmt: skip
    log(*quality_summary(engine, qp, ge_findings, ge_gap, lmt, ge_near))
    return qp


def run_quality(args, log: Log, folder: Path) -> int:
    from engine.store.db import open_db
    from engine.store.http import SqliteCache, SqliteFetchLog

    engine = open_db("engine", folder)
    corpus = open_db("corpus", folder, check_same_thread=False)
    now = datetime.now(UTC)
    mb_before, before = db_mb(folder), quality_counts(engine)
    comps = companies(engine)
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    head = f"run_financials quality · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} companies"
    log(head + (" · no SEC" if args.no_sec else ""), f"engine.db before: {mb_before:,.1f} MB", "")
    client = clog = None
    if not args.no_sec:
        from engine.sec.client import SecClient, user_agent_from_env

        clog = CountingLog(SqliteFetchLog(engine))
        client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=clog)
    quality_run(engine, corpus, comps, now, log, client, clog)
    if clog is not None:
        log(*clog.lines())
    else:
        log("SEC requests: 0 (--no-sec)")
    after = quality_counts(engine)
    log(
        "Rows added per table: "
        + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in QUALITY_TABLES)
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
    ap.add_argument("--refetch", action="store_true",
                    help="peers: download every peer's companyfacts again")  # fmt: skip
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
    print(f"run_financials {args.subcommand}: working; full detail goes to {log.path}")
    try:
        if args.subcommand == "capex":
            return run_capex(args, log, data_dir())
        if args.subcommand == "profile":
            return run_profile(args, log, data_dir())
        if args.subcommand == "peers":
            return run_peers(args, log, data_dir())
        if args.subcommand == "flags":
            return run_flags(args, log, data_dir())
        if args.subcommand == "units":
            return run_units(args, log, data_dir())
        if args.subcommand == "quality":
            return run_quality(args, log, data_dir())
        if args.subcommand == "gate":
            return run_gate(args, log, data_dir())
        if args.subcommand == "gate-text":
            return run_gate_text(args, log, data_dir())
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
