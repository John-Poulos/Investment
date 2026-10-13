"""M07 Ownership: one owner script, one subcommand per build part (D-M07-9).

    uv run python scripts/run_ownership.py insiders --no-sec            # 0 SEC requests
    uv run python scripts/run_ownership.py insiders --history --dry-run # count only, 0 requests
    uv run python scripts/run_ownership.py insiders --history           # the 4th year (D-M07-1)
    uv run python scripts/run_ownership.py insiders                     # cache misses + probe
    uv run python scripts/run_ownership.py --list                       # the subcommand table

Subcommands: insiders (Part 1) · managers (Part 2, not built yet).

`insiders` (Part 1), for the core and promoted companies (the tracked tier stores no Form 4s):
1. Re-parses every stored Form 4 at parser form4-2 (holding lines, D-SEC-27) from the HTTP
   cache: 0 requests; cache misses are counted, and fetched unless `--no-sec`.
2. With `--history`: fetches every Form 4 listed in the `form4_years` window (config, 4 since
   D-M07-1) that is not stored — the 4th year, back to about 2022-10 — and records the
   covered start. `--dry-run` only prints the exact count per company (0 requests, nothing
   written). The owner runs this before the first logon refresh on the new setting (else the
   refresh fetches the gap itself).
3. The M07 local pass for every company (0 requests): 4/A links, CMP classes, `insider_buy`,
   `insider_sale`, `insider_net_flow`, alerts (a company's first pass is a baseline).
4. The short-interest line (missing, D-M07-8) and, unless `--no-sec` or `--no-probe`, one
   Massive short-interest probe request (DS18).
5. Reference cards: Huang (NVDA 0001045810-25-000143), Musk (TSLA 0001104659-25-089693), Tan
   (INTC 0001127602-25-010360) and the AAPL counts (D-SEC-10).

Takes data/refresh.lock (one SEC process at a time). Writes
logs/ownership_<subcommand>_<YYYYMMDD-HHMMSS>.txt as it goes, with requests, MB and seconds per
fetch type, rows added per table and engine.db size before and after; its own tracebacks go
to the log too, so the log is all the owner sends back. The console shows the summary only.
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
    ("insiders", "1", "Form 4 re-parse and history, CMP classes, buy / sale / net-flow signals"),
    ("managers", "2", "followed managers' 13F (not built)"),
)
BUILT = {"insiders"}
COUNTED = ("form4_doc", "insider_txn", "form4_holding", "insider_class", "signal",
           "refresh_state", "fetch_log")  # fmt: skip
REFERENCE = (
    ("Huang", "NVDA", "0001045810", "0001045810-25-000143",
     "sale: 7 S rows 100,000 sh $14,403,585, plan (F3); F 40,163 sh $5,788,292 not in total; "
     "0.012% of stake before (9 lines; 0.13% on the direct line alone); ≈ 0.0004% of cover"),
    ("Musk", "TSLA", "0001318605", "0001104659-25-089693",
     "buy: 25 P rows 2,568,732 sh ≈ $999.96M; 0.50% of stake after (509,362,808); 0.080% of "
     "cover 3,225,448,889 (2025-07-17); class from P/S in 2022–2024, else unclassified + alert"),
    ("Tan", "INTC", "0000050863", "0001127602-25-010360",
     "purchase_from_issuer: code A 1,043,406 sh at $23.96 ≈ $25.0M, offer-letter footnote; "
     "not scored, not in net flow"),
)  # fmt: skip
AAPL = "0000320193"

SUMMARY_MARK = "=== Summary"
CONSOLE_ALWAYS = ("Log written to:", "FAILED", "SEC throttle")


class Log:
    """Every line goes to the log file; the console shows the summary block onward."""

    def __init__(self, path: Path, *, echo_all: bool = False) -> None:
        self.path = path
        path.parent.mkdir(exist_ok=True)
        self._fh = path.open("w", encoding="utf-8")
        self._echo = echo_all

    def __call__(self, *lines: str) -> None:
        for line in lines:
            if line.startswith((SUMMARY_MARK, "FAILED")):
                self._echo = True
            if self._echo or line.startswith(CONSOLE_ALWAYS):
                print(line)
            self._fh.write(line + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def fetch_type(url: str) -> str:
    if url.endswith(("-index.htm", "-index.html")):
        return "filing index"
    if url.endswith(".xml"):
        return "Form 4 XML"
    if "massive.com" in url:
        return "Massive"
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
    return {t: engine.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in COUNTED}


def companies(engine) -> dict[str, str]:
    """Core and promoted companies (ticker → cik): the ones whose Form 4s are stored."""
    from engine.calls.transcripts import symbol_cik
    from engine.refresh import load_config
    from engine.themes import tiers

    out: dict[str, str] = {}
    for t in load_config(ROOT / "config" / "watchlist.toml").tickers:
        if cik := symbol_cik(engine, t):
            out[t] = cik
    for m in tiers.members(engine, "promoted"):
        if m.cik not in out.values():
            out.setdefault(m.ticker, m.cik)
    return out


# --- insiders (Part 1) ---------------------------------------------------------------------


def _card_lines(card, market) -> list[str]:
    from engine.ownership.step import money, pct, shares_txt

    out = [f"    {card.accession} filed {card.filed} ({card.doc_type}) {card.owner_name} "
           f"[{card.role}]"]  # fmt: skip
    if card.buys:
        sh = card.buy_shares
        out.append(f"    buy: {len(card.buys)} P rows {shares_txt(sh)} sh {money(card.buy_usd)}; "
                   f"{pct(card.pct_stake_after_buy())} of stake after "
                   f"{shares_txt(card.stake_after)} ({card.stake_note}); "
                   f"cover {pct(card.cover.pct(card.scaled(sh, market)), 4)} of "
                   f"{card.cover.text}")  # fmt: skip
    if card.issuer_buys:
        sh = sum(r.shares or 0 for r in card.issuer_buys)
        out.append(
            f"    purchase_from_issuer: {shares_txt(sh)} sh {money(card.issuer_usd)} "
            f"(codes {', '.join(sorted({r.code or '?' for r in card.issuer_buys}))})"
        )
    if card.sales:
        sh = card.sale_shares
        statuses = ", ".join(sorted({card.sale_status(r) for r in card.sales}))
        direct = [r.shares_after for r in card.rows if r.table_kind == "non_derivative"
                  and r.direct_indirect == "D" and r.shares_after is not None]  # fmt: skip
        direct_pct = (sh / (direct[-1] + sh) * 100) if direct and sh else None
        out.append(f"    sale: {len(card.sales)} S rows {shares_txt(sh)} sh {money(card.sale_usd)} "
                   f"[{statuses}]; {pct(card.pct_stake_before_sale())} of stake before "
                   f"{shares_txt(card.stake_before_sale)} ({card.stake_note}); direct line alone "
                   f"{pct(direct_pct)}")  # fmt: skip
        out.append(f"    cover {pct(card.cover.pct(card.scaled(sh, market)), 4)} of "
                   f"{card.cover.text}; float "
                   + (f"{pct(card.float_.pct(card.scaled(sh, market)), 4)} of {card.float_.text}"
                      if card.float_.value else card.float_.text)
                   + "; ADV " + (f"{pct(card.adv.pct(sh), 2)} of {card.adv.text}"
                                 if card.adv.value else card.adv.text))  # fmt: skip
        w = card.warning()
        out.append(f"    warning: {w}" if w else "    no warning (info)")
    for r in card.others:
        out.append(f"    not in total: {r.code} {shares_txt(r.shares)} sh × {r.price} = "
                   f"{money(r.usd)}")  # fmt: skip
    return out


def insiders_run(
    engine,
    corpus,
    comps: dict[str, str],
    now: datetime,
    log,
    *,
    client=None,
    history: bool = False,
    dry_run: bool = False,
    years: int = 4,
    probe=None,
) -> dict:
    """The `insiders` work on open connections (tests inject scratch DBs and a fake client).
    `client=None` = no SEC requests. Returns a small result dict for tests."""
    from engine.ownership import step
    from engine.ownership.cards import Market
    from engine.ownership.views import SHORT_INTEREST_LINE
    from engine.refresh import market_date
    from engine.sec.insiders import (
        PARSER_VERSION,
        history_plan,
        record_coverage,
        reparse_cached,
        sync_insiders,
    )
    from engine.sec.results import Ok
    from engine.store.http import SqliteCache

    cache = SqliteCache(corpus)
    result: dict = {"misses": 0, "reparsed": 0, "fetched": 0, "planned": 0, "history": {}}
    since = (market_date(now) - timedelta(days=365 * years)).isoformat()

    if dry_run:
        log(f"Dry run: Form 4s listed since {since} (form4_years = {years}) not stored at "
            f"{PARSER_VERSION}; nothing is fetched or written", "")  # fmt: skip
        total = 0
        for t, cik in sorted(comps.items()):
            p = history_plan(engine, cache, cik, since, now)
            total += p.requests
            result["history"][t] = p
            log(
                f"  {t}: {p.listed} listed, {p.pending} not at {PARSER_VERSION} — {p.cached} in "
                f"the cache (0 requests), {p.to_fetch} to fetch = {p.requests} requests"
            )
        result["planned"] = total
        log("", SUMMARY_MARK + " ===",
            f"History fetch would send {total} SEC requests (~{total / 5 / 60:.1f} min at 5/s) "
            f"for {len(comps)} companies.",
            "Run it: uv run python scripts/run_ownership.py insiders --history")  # fmt: skip
        return result

    # 1. re-parse from the cache
    t0 = time.monotonic()
    log(
        f"1. Re-parse stored Form 4s at {PARSER_VERSION} from the HTTP cache"
        + (" (cache misses fetched)" if client else " (--no-sec: misses counted only)")
    )
    for t, cik in sorted(comps.items()):
        rp = reparse_cached(engine, cache, cik, now, client=client)
        result["misses"] += len(rp.misses)
        result["reparsed"] += rp.reparsed
        result["fetched"] += rp.fetched
        log(f"  {t}: {rp.stale} older parse(s) → {rp.reparsed} re-parsed from the cache, "
            f"{rp.fetched} fetched, {len(rp.misses)} cache misses"
            + (f" ({', '.join(rp.misses[:5])}{' …' if len(rp.misses) > 5 else ''})"
               if rp.misses else "")
            + f"; holding lines stored {rp.holdings}")  # fmt: skip
        for f in rp.failed:
            log(f"  FAILED {t} {f}")
    log(f"  ({time.monotonic() - t0:.1f} s)", "")

    # 2. history (the 4th year)
    if history:
        if client is None:
            log("2. History: skipped (--no-sec)", "")
        else:
            log(f"2. History: every Form 4 listed since {since} (form4_years = {years})")
            planned = 0
            for t, cik in sorted(comps.items()):
                p = history_plan(engine, cache, cik, since, now)
                planned += p.requests
                log(f"  {t}: {p.pending} pending, {p.to_fetch} to fetch ({p.requests} requests)")
            result["planned"] = planned
            log(f"  planned: {planned} requests (~{planned / 5 / 60:.1f} min at 5/s)")
            t1 = time.monotonic()
            for t, cik in sorted(comps.items()):
                res = sync_insiders(client, engine, cik, now, since=since)
                if not isinstance(res, Ok):
                    log(f"  FAILED {t}: {res}")
                    continue
                s = res.data
                result["history"][t] = s
                if s.complete and not s.deferred:
                    record_coverage(engine, cik, since, now)
                log(
                    f"  {t}: {s.filings} listed, {s.ingested} parsed now ({s.transactions} rows), "
                    f"{s.already} already stored"
                    + (
                        f"; FAILED {len(s.failed)}: " + "; ".join(s.failed[:3])
                        if s.failed
                        else "; history covered from " + since
                    )
                )
                if any("throttle" in f for f in s.failed):
                    log("  SEC throttle: stopped; re-run later (every step is safe to repeat)")
                    break
            log(f"  ({time.monotonic() - t1:.1f} s)", "")

    # 3. local pass
    t2 = time.monotonic()
    op = step.local_pass(engine, comps, now, force=True)
    log(f"3. M07 local pass (0 requests, {time.monotonic() - t2:.1f} s)")
    for t, c in sorted(op.companies.items()):
        if c.error:
            log(f"  FAILED {t}: {c.error}")
            continue
        cl = " / ".join(f"{k} {c.classes.get(k, 0)}" for k in ("routine", "opportunistic",
                                                                  "unclassified"))  # fmt: skip
        warn = sum(1 for d in c.sales if "warning:" in d.method)
        net = " · ".join(
            f"{tf} {nf.text or 'missing'}" + (f" {step.money(nf.value)}" if nf.value is not None
                                              else "") + (f" ({nf.missing})" if nf.missing else "")
            + (" [written]" if nf.written else " [unchanged]")
            for tf, nf in c.net.items())  # fmt: skip
        no_buy = " · ".join(f"{tf} {s}" for tf, s in c.no_buy.items() if s) or "none"
        log(f"  {t}: history from {c.history_start or 'none'}; {c.forms} forms, {c.rows} rows, "
            f"4/A links {c.links} ({c.links_by_code} on code); classes this year: {cl}; buy days "
            f"{len(c.buys)}, sale days {len(c.sales)} ({warn} with a warning); net flow {net}; "
            f"no-qualifying-buy rows {no_buy}")  # fmt: skip
        for x in c.link_log:
            log(f"    4/A kept apart: {x}")
        for d in c.buys:
            log(f"    buy {d.day}: {d.text} {step.money(d.value)}")
        for d in c.sales[-5:]:
            log(
                f"    sale {d.day}: {d.text} {step.money(d.value)}"
                + (" WARNING" if "warning:" in d.method else "")
            )
        for a in c.alerts:
            log(f"    alert: {a}")
        for a in c.baseline:
            log(f"    baseline (first pass, not alerted): {a}")
    log("")
    result["pass"] = op

    # 4. short interest
    log(f"4. Short interest — Insiders tab line: {SHORT_INTEREST_LINE}")
    probe_lines = (
        probe()
        if probe is not None
        else ["Massive probe: not sent (--no-sec, --no-probe or no MASSIVE_API_KEY)"]
    )
    log(*(f"  {x}" for x in probe_lines))
    log("")

    # 5. reference cards
    log("5. Reference cards (pack and D-SEC-10 figures)")
    ref_lines = []
    for who, ticker, cik, acc, expect in REFERENCE:
        cp = next((c for c in op.companies.values() if c.cik == cik), None)
        card = next((c for c in (cp.cards if cp else []) if c.accession == acc), None)
        log(f"  {who} ({ticker} {acc}) — expected: {expect}")
        if card is None:
            line = f"  {who}: not stored (company not covered or the form not parsed)"
            log(line)
            ref_lines.append(line)
            continue
        lines = _card_lines(card, Market(engine, cik))
        log(*lines)
        ref_lines.append(f"  {who}: " + lines[1].strip() if len(lines) > 1 else lines[0])
    aapl = next((c for c in op.companies.values() if c.cik == AAPL), None)
    if aapl is not None:
        sales = [r for card in aapl.cards for r in card.sales]
        by = defaultdict(int)
        for r in sales:
            by[r.plan] += 1
        line = (
            f"  AAPL: {aapl.forms} forms, {aapl.rows} rows stored; sales {len(sales)}: "
            f"plan {by['plan']}, plan_na {by['plan_na']}, non-plan {by['non_plan']} "
            "(D-SEC-10 live re-run: 60 forms / 170 rows, 43 of 48 sales plan, 5 non-plan)"
        )
        log(line)
        ref_lines.append(line)
    log("")

    # summary
    cs = list(op.companies.values())
    log(SUMMARY_MARK + " ===",
        f"Companies: {len(cs)}; Form 4s re-parsed from the cache {result['reparsed']}, fetched "
        f"{result['fetched']}, cache misses left {result['misses']}"
        + (f"; history planned {result['planned']} requests" if history else ""),
        "Classes this year: " + ", ".join(
            f"{c.ticker} {c.classes.get('routine', 0)}/{c.classes.get('opportunistic', 0)}/"
            f"{c.classes.get('unclassified', 0)}" for c in cs if c.classes) + " (r/o/u)",
        f"Buy days {sum(len(c.buys) for c in cs)}, sale days {sum(len(c.sales) for c in cs)}, "
        f"sale warnings {sum(1 for c in cs for d in c.sales if 'warning:' in d.method)}, new "
        f"alerts {len(op.alerts)}, baseline buys {sum(len(c.baseline) for c in cs)}",
        "Net flow MY: " + ", ".join(
            f"{c.ticker} {(c.net.get('MY').text if c.net.get('MY') else None) or 'missing'}"
            for c in cs),
        *ref_lines,
        *(f"  {x}" for x in probe_lines[:2]),
        *(f"FAILED {c.ticker}: {c.error}" for c in cs if c.error))  # fmt: skip
    return result


def run_insiders(args, log: Log, folder: Path) -> int:
    from engine.store.db import open_db
    from engine.store.http import SqliteFetchLog

    engine = open_db("engine", folder)
    corpus = open_db("corpus", folder, check_same_thread=False)
    now = datetime.now(UTC)
    mb_before, before = db_mb(folder), counts(engine)
    comps = companies(engine)
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    from engine.refresh import load_config

    years = load_config(ROOT / "config" / "watchlist.toml").form4_years
    mode = ("dry run" if args.dry_run else "no SEC" if args.no_sec else "SEC for cache misses"
            + (" and history" if args.history else ""))  # fmt: skip
    log(f"run_ownership insiders · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} companies "
        f"({', '.join(sorted(comps))}) · {mode} · form4_years = {years}",
        f"engine.db before: {mb_before:,.1f} MB", "")  # fmt: skip
    client = clog = probe = None
    if not (args.no_sec or args.dry_run):
        from engine.sec.client import SecClient, user_agent_from_env
        from engine.store.http import SqliteCache

        clog = CountingLog(SqliteFetchLog(engine))
        client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=clog)
        if not args.no_probe:
            from engine.news.fetch import Fetcher
            from engine.news.vendors import key_from_env
            from engine.ownership import short_interest

            key = key_from_env("MASSIVE_API_KEY")
            if key:
                fetcher = Fetcher(engine, secrets=(key,))
                probe = lambda: short_interest.probe(fetcher, key)  # noqa: E731
    t0 = time.monotonic()
    insiders_run(engine, corpus, comps, now, log, client=client, history=args.history,
                 dry_run=args.dry_run, years=years, probe=probe)  # fmt: skip
    if clog is not None:
        clog.seconds["Form 4 XML"] = time.monotonic() - t0
        log(*clog.lines())
    else:
        log("SEC requests: 0 (" + ("--dry-run" if args.dry_run else "--no-sec") + ")")
    after = counts(engine)
    log("Rows added per table: " + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in COUNTED))
    log(f"engine.db: {mb_before:,.1f} MB → {db_mb(folder):,.1f} MB")
    corpus.close()
    engine.close()
    return 0


def _main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("subcommand", nargs="?", choices=[s for s, _, _ in SUBCOMMANDS])
    ap.add_argument("--no-sec", action="store_true", help="no SEC requests (local re-run)")
    ap.add_argument("--history", action="store_true",
                    help="fetch the Form 4s of the whole form4_years window (D-M07-1)")  # fmt: skip
    ap.add_argument("--dry-run", action="store_true",
                    help="with --history: print the exact request count only")  # fmt: skip
    ap.add_argument("--no-probe", action="store_true", help="skip the Massive probe request")
    ap.add_argument("--tickers", help="comma-separated subset (default: core + promoted)")
    ap.add_argument("--list", action="store_true", help="print the subcommand table")
    args = ap.parse_args()
    if args.list or not args.subcommand:
        for name, part, what in SUBCOMMANDS:
            print(f"{name:10} Part {part:3} {what}" + ("" if name in BUILT else "  (not built)"))
        return 0 if args.list else 2
    if args.subcommand not in BUILT:
        part = dict((s, p) for s, p, _ in SUBCOMMANDS)[args.subcommand]
        print(f"{args.subcommand}: not built, Part {part}")
        return 2
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.chdir(ROOT)  # data/, config/ and logs/ are relative to the repo
    from engine.store.db import data_dir

    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    log = Log(ROOT / "logs" / f"ownership_{args.subcommand}_{stamp}.txt")
    print(f"run_ownership {args.subcommand}: working; full detail goes to {log.path}")
    try:
        return run_insiders(args, log, data_dir())
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

    return run_script(ROOT, "run_ownership", _main)


if __name__ == "__main__":
    sys.exit(main())
