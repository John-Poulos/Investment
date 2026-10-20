"""M08 Valuation: one owner script, one subcommand per build part (M08 Part 1).

    uv run python scripts/run_valuation.py value --no-sec   # Part 1 live check (0 requests)
    uv run python scripts/run_valuation.py --list           # the subcommand table

`value` (Part 1): from stored facts and prices only (0 SEC or API requests; `--no-sec` is
accepted for the usual pattern and changes nothing in Part 1), for every covered name —
watchlist, promoted and tracked — every standard row (P/E TTM, EV/EBITDA, EV/EBIT, EV/Sales,
EV/GP, P/S, P/B, P/FCF, FCF yield, dividend yield, EV ÷ normalized EBIT, P ÷ normalized
EPS), the cyclical flag with both test values, the headline (`valuation_multiple`) and its
own-history percentile (`valuation_pctile`), written as one row set for the newest completed
week (D-M08-8). Then the pack checkpoints recomputed from stored data (MU at its 10-K dates,
NVDA ≈ 29×, INFQ P/S, MSTR mNAV, GFS's 12-month basis), the missing rows with reasons and a
summary.

Takes data/refresh.lock (one data-writing run at a time). Writes
logs/valuation_<subcommand>_<YYYYMMDD-HHMMSS>.txt as it goes, with seconds, rows added per
table and engine.db size before and after; the console shows the summary only. Its own
tracebacks go to the log too, so the log is all the owner sends back.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SUBCOMMANDS = (
    ("value", "1", "standard rows, cyclical flag, headline and percentile (0 requests)"),
    ("estimates", "2", "Alpha Vantage EARNINGS_ESTIMATES snapshots, PEG, est_revision"),
)
BUILT = {"value"}
SUMMARY_MARK = "=== Summary"
CONSOLE_ALWAYS = ("Log written to:", "FAILED")
COUNTED_TABLES = ("signal",)
# The pack's figures (docs/M08_DESIGN_PACK.md S1/S2 worked examples; Yahoo closes, so stored
# Tiingo closes may differ slightly): (ticker, date, row, pack figure)
CHECKPOINTS = (
    ("MU", "2022-10-07", "val_pe_ttm", "6.8×"),
    ("MU", "2023-10-06", "val_pe_ttm", "n/m"),
    ("MU", "2024-10-04", "val_pe_ttm", "146.1×"),
    ("MU", "2025-10-03", "val_pe_ttm", "24.7×"),
    ("NVDA", "2026-10-09", "val_pe_ttm", "≈ 29.0× (TTM EPS 7.91 at $229.28)"),
    ("INFQ", "2026-10-09", "val_ps", "60.6× (225,357,052 shares × $11.04 ÷ TTM revenue 41.081M)"),
    ("MSTR", "2026-10-09", "mnav", "market cap ÷ CryptoAssetFairValue (no pack figure)"),
)


class Log:
    """Every line goes to the log file; the console shows the "=== Summary" block onward,
    failures and the log path."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(exist_ok=True, parents=True)
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


def db_mb(folder: Path) -> float:
    return (
        sum(
            (folder / n).stat().st_size
            for n in ("engine.db", "engine.db-wal")
            if (folder / n).exists()
        )
        / 1e6
    )


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


def checkpoint_line(engine, comps, who, day, key, pack, today, p, mf) -> str:
    """The row recomputed at a past date from stored data (no rows written)."""
    from engine.moneyflow.periods import fiscal_year_end
    from engine.valuation.asof import Known
    from engine.valuation.measures import LABELS, snapshot

    cik = comps.get(who)
    if not cik:
        return f"  {who} {day}: pack {pack} · engine: not a covered name"
    tag = mf.for_company(cik, who, day)
    s = snapshot(Known(engine, cik, today), day, fye=fiscal_year_end(engine, cik),
                 asset_treasury=bool(tag and tag.tag == "asset_treasury"),
                 nep_swing=p.nep_swing_pp, nep_min_years=p.nep_min_years)  # fmt: skip
    m = s.m(key)
    got = f"missing: {m.missing}" if m.missing else m.shown
    close = f"close ${s.close.value:,.2f} {s.close.day}" if s.close else "no close"
    return (f"  {who} {day}: pack {pack} · engine {LABELS[key]} {got} ({close}; "
            f"{s.twelve or 'no 12-month period'})")  # fmt: skip


def run_value(args, log: Log, folder: Path, engine=None, now: datetime | None = None) -> int:
    """The Part 1 check. `engine` and `now` are injected by tests (never the real DB)."""
    from engine.financials import models
    from engine.store.db import open_db
    from engine.valuation import params as params_mod
    from engine.valuation import step

    own = engine is None
    engine = engine if engine is not None else open_db("engine", folder)
    now = now or datetime.now(UTC)
    t_start = time.monotonic()
    mb_before = db_mb(folder)
    before = counts(engine)
    comps = companies(engine) if args.companies is None else args.companies
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    p, note = params_mod.load_safe(ROOT / "config" / "valuation.toml")
    mf = models.load_safe()
    log(f"run_valuation value · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} names · parameters "
        f"{p.version} · 0 requests (stored facts and prices only)",
        f"engine.db before: {mb_before:,.1f} MB", "")  # fmt: skip
    if note:
        log(f"parameters: {note}")
    if mf.error:
        log(f"company_models.toml: {mf.error}")
    vp = step.valuation_pass(engine, comps, now, params=p, mf=mf)
    vp.params_note = note
    log(f"Per name (newest completed week {vp.week}):")
    for t in sorted(vp.results):
        for r in vp.results[t]:
            log("  " + step.line(r))
    for t, e in sorted(vp.errors.items()):
        log(f"  {t}: error — {e}")
    log("", "Cyclical flag (rule 5; expected: MU flagged; any non-memory name flagged is checked "
        "for D32):")  # fmt: skip
    for t in sorted(vp.results):
        r = vp.results[t][0]
        if r.flag is not None:
            log(f"  {t}: {r.flag.text()}")
    log("", "Headline routing and EV:")
    for t in sorted(vp.results):
        r = vp.results[t][0]
        ev = r.snap.ev_text or (f"EV incomplete: {r.snap.ev_missing}" if r.snap.ev_missing else "")
        log(f"  {t}: {r.route.why}; 12-month basis: {r.snap.twelve or '—'}")
        if ev:
            log(f"    {ev}")
        if r.snap.nep is not None and r.route.measure in ("val_ev_nebit", "val_p_neps"):
            log(f"    {r.snap.nep.text()}")
        if r.trap:
            log(f"    {r.trap}")
    log("", "Missing rows (reason per signal):")
    miss = [f"  {r.ticker} {o.signal}: missing: {o.missing}" for rs in vp.results.values()
            for r in rs for o in r.rows if o.missing]  # fmt: skip
    log(*(miss or ["  none"]))
    log("", "Pack checkpoints (recomputed from stored data, no rows written):")
    today = step.bars.eastern_today(now).isoformat()
    for who, day, key, pack in CHECKPOINTS:
        log(checkpoint_line(engine, comps, who, day, key, pack, today, p, mf))
    after = counts(engine)
    log("", SUMMARY_MARK)
    log(*step.summary_lines(vp))
    log(f"SEC requests: 0 · API requests: 0 · {time.monotonic() - t_start:.1f} s")
    log("Rows added per table: " + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in after))
    log(f"engine.db: {mb_before:,.1f} MB → {db_mb(folder):,.1f} MB")
    if own:
        engine.close()
    return 0


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("subcommand", nargs="?", choices=[s for s, _, _ in SUBCOMMANDS])
    ap.add_argument("--no-sec", action="store_true", help="no SEC requests (Part 1 makes none)")
    ap.add_argument("--tickers", help="comma-separated subset (default: watchlist + tiers)")
    ap.add_argument("--list", action="store_true", help="print the subcommand table")
    args = ap.parse_args(argv)
    args.companies = None
    if args.list or not args.subcommand:
        for name, part, what in SUBCOMMANDS:
            print(f"{name:10} Part {part:2} {what}" + ("" if name in BUILT else "  (not built)"))
        return 0 if args.list else 2
    if args.subcommand not in BUILT:
        print(f"{args.subcommand}: not built (M08 Part 2)")
        return 2
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.chdir(ROOT)  # data/, config/ and logs/ are relative to the repo
    from engine.store.db import data_dir

    log = Log(ROOT / "logs" / f"valuation_{args.subcommand}_{datetime.now():%Y%m%d-%H%M%S}.txt")
    print(f"run_valuation {args.subcommand}: working; full detail goes to {log.path}")
    try:
        return run_value(args, log, data_dir())
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

    return run_script(ROOT, "run_valuation", _main)


if __name__ == "__main__":
    sys.exit(main())
