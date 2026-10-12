"""M04 Financials: one owner script, one subcommand per build part (D-M04-69).

    uv run python scripts/run_financials.py data             # Part 1a live check
    uv run python scripts/run_financials.py data --no-sec    # local re-run, 0 SEC requests
    uv run python scripts/run_financials.py --list           # the subcommand table

Subcommands: data (1a) · capex (1b) · profile (1c) · peers (2) · flags (3) · gate (4a) ·
gate-text (4b) · issuance (5) · quality (6) · units (7a) · margins (7b) · cvd (8a) ·
backtest (8b). Parts not built yet print "not built, Part n".

`data` (Part 1a): rebuilds every covered company's series from stored facts (parser
facts-2, 0 requests); reads the R1 cover pages of the multi-class filers' 10-K/10-Q filings
of the last 3 years (GOOG, META, MSTR, SPCX: ~37 requests); fetches Western Digital's two
revenue companyconcept files for the as-of check (2 requests); evaluates filing status for
every covered company; prints the extra-tag report, the GFS 6-K sync rule and a summary.

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
BUILT = {"data"}
WDC_CIK = "0000106040"
WDC_TAGS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")
COUNTED_TABLES = ("fact", "series", "cover_shares", "filing_status", "signal", "entity_link",
                  "entity", "refresh_state", "fetch_log")  # fmt: skip


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
    if "/companyconcept/" in url:
        return "companyconcept"
    if "/companyfacts/" in url:
        return "companyfacts"
    if url.rsplit("/", 1)[-1].startswith("R") and url.endswith((".htm", ".xml")):
        return "R page"
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
