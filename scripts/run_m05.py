"""M05 Capex & future spend: one owner script, one subcommand per build part (M05 Part 1).

    uv run python scripts/run_m05.py demand --no-sec     # Part 1 live check (0 requests)
    uv run python scripts/run_m05.py export              # fixture export from stored facts (0)
    uv run python scripts/run_m05.py --list              # the subcommand table

`demand` (Part 1): computes from stored facts and M04 rows (0 requests; `--no-sec` is
accepted for the D-M04-69 pattern and changes nothing, since the subcommand never calls
SEC) the three M05 rows — `capex_demand` (with the rule-4 capex vote), `growth_capex_roic`,
`bookings_cover` — for every covered name (watchlist, promoted and tracked), writes them,
and prints one line per name, the deposits line, the 8-FY capex ÷ depreciation strip of the
brief's companies, and the brief's worked-example figures to compare.

`export` (0 requests): writes the stored `fact` rows of the tags the Part 1 fixtures lack
(capex, depreciation, D&A, revenue, contract liabilities, RPO, OCF) for MU, INTC and MSFT
(`--tickers` to change) as trimmed companyfacts JSON in logs/, for the owner to send back
(Claude cannot read data\\; the files become fixtures in a later part).

Takes data/refresh.lock (one data-writing run at a time). Writes
logs/m05_<subcommand>_<YYYYMMDD-HHMMSS>.txt as it goes; the console shows the summary only.
Its own tracebacks go to the log too, so the log is all the owner sends back.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SUBCOMMANDS = (
    ("demand", "1", "capex_demand (+ vote), growth_capex_roic, bookings_cover; deposits line"),
    ("export", "1", "stored facts of MU, INTC, MSFT capex/depreciation/deposit tags (fixtures)"),
    ("commitments", "2", "commitment_cover, lease and post-period lines"),
)
BUILT = {"demand", "export"}
SUMMARY_MARK = "=== Summary"
CONSOLE_ALWAYS = ("Log written to:", "FAILED", "Export written to:")
COUNTED_TABLES = ("signal",)
STRIP_TICKERS = ("MU", "INTC", "MSFT")
# The brief's worked example (docs/mvp/M05_MVP_BRIEF.md; docs/M05_FUTURE_SPEND.md "Live
# checks"), to compare with the lines above them.
CHECKPOINTS = (
    ("MU", "FY2022 1.72 BUILD_INTO_DEMAND (median 1.61); FY2023 1.00 CUTTING (capex ÷ revenue "
     "49.4% = 1.30× its 3-yr average, no M04 pointer); FY2024 1.09 MAINTENANCE (1.68); FY2025 "
     "1.92 BUILD (1.56); FY2026 3.26 BUILD_INTO_DEMAND (1.68); deposits $13.0B vs $169M"),
    ("INTC", "2023 capex ÷ revenue 1.75× its 3-yr average while revenue fell → AHEAD_OF_DEMAND, "
     "if its 2020–23 capex and revenue are stored; 2022 growth share 55%"),
    ("MSFT", "bookings_cover 1.33 → 2.06 (+55%) RISING; capex ÷ depreciation FY2026 3.38 "
     "(FY2025 2.93), capex_demand possibly INSUFFICIENT_HISTORY (no long depreciation series)"),
)  # fmt: skip
EXPORT_TAGS = (
    "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
    "Depreciation", "DepreciationDepletionAndAmortization",
    "DepreciationAmortizationAndAccretionNet", "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
    "ContractWithCustomerLiability", "ContractWithCustomerLiabilityCurrent",
    "ContractWithCustomerLiabilityNoncurrent", "DeferredRevenue", "DeferredRevenueCurrent",
    "DeferredRevenueNoncurrent", "RevenueRemainingPerformanceObligation",
    "NetCashProvidedByUsedInOperatingActivities",
)  # fmt: skip


class Log:
    """Every line goes to the log file; the console shows the "=== Summary" block onward,
    failures and the log path."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(exist_ok=True)
        self._fh = path.open("w", encoding="utf-8")
        self._echo = False

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


def counts(engine) -> dict[str, int]:
    return {t: engine.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in COUNTED_TABLES}


def companies(engine) -> dict[str, str]:
    """Covered names: watchlist (core) + active tier members (promoted, tracked)."""
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


def strip_lines(r) -> list[str]:
    from engine.future_spend import demand

    s = r.series
    if s is None or not s.years:
        return [f"  {r.ticker}: no total capex stored"]
    out = [
        f"  {r.ticker} (rung: {demand.RUNG_NAME.get(s.rung, 'not split')}; "
        f"{len(s.years)} fiscal years with capex, {s.years[0].label}–{s.years[-1].label}):"
    ]
    for d in demand.strip(s):
        ratio = f"{d.ratio:.2f}" if d.ratio is not None else "—"
        med = f"{d.median:.2f}" if d.median is not None else "—"
        inten = (f"{d.intensity:.1%} ({d.intensity / d.intensity_avg:.2f}× its 3-FY avg)"
                 if d.intensity is not None and d.intensity_avg else
                 f"{d.intensity:.1%}" if d.intensity is not None else "—")  # fmt: skip
        out.append(f"    {d.label}: capex ÷ rung {ratio}, median {med}, capex "
                   f"{demand._pct(d.capex_yoy)}, revenue {demand._pct(d.rev_yoy)}, capex ÷ revenue "
                   f"{inten} → {d.state or 'missing: ' + str(d.missing)}")  # fmt: skip
    return out


def run_demand(args, log: Log, folder: Path, engine=None, now: datetime | None = None) -> int:
    """The Part 1 check. `engine` and `now` are injected by tests (never the real DB)."""
    from engine.future_spend import channels as channels_mod
    from engine.future_spend import step
    from engine.store.db import open_db

    own = engine is None
    engine = engine if engine is not None else open_db("engine", folder)
    now = now or datetime.now(UTC)
    t0 = time.monotonic()
    before = counts(engine)
    comps = companies(engine) if args.companies is None else args.companies
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    chf = channels_mod.load_safe(ROOT / "config" / "m05_channels.toml")
    log(f"run_m05 demand · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} names · 0 requests"
        + (" · --no-sec" if args.no_sec else ""), "")  # fmt: skip
    if chf.error:
        log(f"channel file rejected, every company read as unset: {chf.error}")
    fp = step.future_spend_pass(engine, comps, now, chf=chf)
    log("Per name:")
    for t in sorted(fp.results):
        log("  " + step.line(fp.results[t]))
    for t, e in sorted(fp.errors.items()):
        log(f"  {t}: error — {e}")
    log("", "Missing rows (reason per signal):")
    miss = [f"  {r.ticker} {o.signal}: missing: {o.missing}" for r in fp.results.values()
            for o in r.rows if o.missing]  # fmt: skip
    log(*(miss or ["  none"]))
    log("", "Deposits (contract liabilities; repayable, not revenue):")
    for t in sorted(fp.results):
        r = fp.results[t]
        if r.deposits is not None and r.deposits.now is not None:
            log(f"  {t}: {r.deposits.text()}")
    log("", "Capex ÷ depreciation strip (brief's companies):")
    for t in STRIP_TICKERS:
        if t in fp.results:
            log(*strip_lines(fp.results[t]))
    log("", "Brief's worked example (compare with the lines above):")
    for who, what in CHECKPOINTS:
        log(f"  {who}: {what}")
    after = counts(engine)
    log("", SUMMARY_MARK)
    log(*step.summary_lines(fp))
    log(f"SEC requests: 0 · other requests: 0 · {time.monotonic() - t0:.1f} s")
    log("Rows added per table: " + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in after))
    if own:
        engine.close()
    return 0


def export_facts(engine, cik: str, name: str) -> dict:
    """Stored `fact` rows of EXPORT_TAGS in SEC companyfacts layout (0 requests)."""
    facts: dict[str, dict] = {}
    marks = ",".join("?" * len(EXPORT_TAGS))
    for r in engine.execute(
        f"SELECT taxonomy, tag, unit, period_start, period_end, value, accession, form, filed, "
        f"fy, fp, frame FROM fact WHERE cik = ? AND tag IN ({marks}) ORDER BY taxonomy, tag, "
        "unit, period_end, filed",
        (cik, *EXPORT_TAGS),
    ):
        unit = facts.setdefault(r[0], {}).setdefault(r[1], {"units": {}})["units"]
        row = {"end": r[4], "val": r[5], "accn": r[6], "form": r[7], "filed": r[8]}
        if r[3]:
            row = {"start": r[3]} | row
        for k, v in (("fy", r[9]), ("fp", r[10]), ("frame", r[11])):
            if v is not None:
                row[k] = v
        unit.setdefault(r[2], []).append(row)
    return {"cik": int(cik), "entityName": name, "facts": facts}


def run_export(args, log: Log, folder: Path, engine=None, now: datetime | None = None) -> int:
    from engine.calls.transcripts import symbol_cik
    from engine.store.db import open_db

    own = engine is None
    engine = engine if engine is not None else open_db("engine", folder)
    now = now or datetime.now(UTC)
    tickers = [t.strip().upper() for t in (args.tickers or ",".join(STRIP_TICKERS)).split(",")]
    log(f"run_m05 export · {now:%Y-%m-%d %H:%M} UTC · {', '.join(tickers)} · 0 requests", "")
    out_dir = args.out_dir or (ROOT / "logs")
    written = []
    for t in tickers:
        cik = symbol_cik(engine, t)
        if cik is None:
            log(f"  {t}: no CIK resolved, skipped")
            continue
        row = engine.execute("SELECT name FROM entity WHERE cik = ?", (cik,)).fetchone()
        data = export_facts(engine, cik, row[0] if row else t)
        n = sum(len(v) for tags in data["facts"].values() for u in tags.values()
                for v in u["units"].values())  # fmt: skip
        path = Path(out_dir) / f"m05_export_{t.lower()}_{now:%Y%m%d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
            fh.write("\n")
        tags = sorted(g for tags in data["facts"].values() for g in tags)
        log(f"  {t} ({cik}): {n} facts, tags {', '.join(tags) or 'none'}")
        written.append(path)
    log("", SUMMARY_MARK, f"{len(written)} export file(s); SEC requests: 0")
    for p in written:
        log(f"Export written to: {p}")
    if own:
        engine.close()
    return 0


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("subcommand", nargs="?", choices=[s for s, _, _ in SUBCOMMANDS])
    ap.add_argument(
        "--no-sec",
        action="store_true",
        help="accepted for the D-M04-69 pattern; demand never calls SEC",
    )
    ap.add_argument("--tickers", help="comma-separated subset")
    ap.add_argument("--list", action="store_true", help="print the subcommand table")
    args = ap.parse_args(argv)
    args.companies = None
    args.out_dir = None
    if args.list or not args.subcommand:
        for name, part, what in SUBCOMMANDS:
            print(f"{name:12} Part {part:2} {what}" + ("" if name in BUILT else "  (not built)"))
        return 0 if args.list else 2
    if args.subcommand not in BUILT:
        print(f"{args.subcommand}: not built (Part 2)")
        return 2
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.chdir(ROOT)  # data/, config/ and logs/ are relative to the repo
    from engine.store.db import data_dir

    log = Log(ROOT / "logs" / f"m05_{args.subcommand}_{datetime.now():%Y%m%d-%H%M%S}.txt")
    print(f"run_m05 {args.subcommand}: working; full detail goes to {log.path}")
    try:
        run = run_demand if args.subcommand == "demand" else run_export
        return run(args, log, data_dir())
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

    return run_script(ROOT, "run_m05", _main)


if __name__ == "__main__":
    sys.exit(main())
