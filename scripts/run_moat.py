"""M06 Moat: one owner script, one subcommand per build part (M06 Parts 1–2).

    uv run python scripts/run_moat.py quant          # Part 1 live check (0 requests)
    uv run python scripts/run_moat.py --list         # the subcommand table

`quant` (Part 1): computes from stored facts (0 requests; `--no-sec` is accepted for the
D-M04-69 pattern and changes nothing, since the subcommand never calls SEC) the quant leg,
the engine's proposal, the owner's verdict in force and the gate for every covered name
(watchlist, promoted and tracked), writes `moat_quant`, `moat_verdict` and `moat_gate`,
queues the `m06_verdict` setup items (outside M04's cap), and prints one line per name, the
ROIC / GM / OM strip of the brief's companies, the missing rows and the brief's worked
example to compare.

Takes data/refresh.lock (one data-writing run at a time). Writes
logs/moat_<subcommand>_<YYYYMMDD-HHMMSS>.txt as it goes; the console shows the summary only.
Its own tracebacks go to the log too, so the log is all the owner sends back.
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
    ("quant", "1", "moat_quant, moat_verdict, moat_gate; m06_verdict setup items"),
    ("challengers", "2", "challenger events, rungs, CvD feed"),
)
BUILT = {"quant"}
SUMMARY_MARK = "=== Summary"
CONSOLE_ALWAYS = ("Log written to:", "FAILED")
COUNTED_TABLES = ("signal", "review_queue")
STRIP_TICKERS = ("MSFT", "INTC", "MU", "BA")
# The brief's worked example (docs/mvp/M06_MVP_BRIEF.md; docs/M06_MOAT.md), to compare.
CHECKPOINTS = (
    ("MSFT", "FY2026 ROIC 35.9% (engine, with current debt); GM 64.0–69.8% FY16–26; persistent "
     "expected; peer GM z missing (peers not confirmed)"),
    ("INTC", "OI 2021 19.456, 2022 2.334, 2023 0.093, 2024 −11.678, 2025 −2.214 ($B); FY2025 "
     "ROIC −1.1%; weak through the last-3-years guard"),
    ("MU", "GM FY2023 −9.1%, FY2026 80.7%; FY2026 ROIC 106.7% (a cycle peak); through_cycle "
     "expected (≈ 6/10 above, illus.)"),
    ("NVDA", "FY2026 ROIC 149.8%; persistent expected; R&D-heavy label"),
    ("BA", "FY2025 ROIC 13.5% after 2019–24 losses → weak or through_cycle (the D32 case)"),
    ("TSLA, GFS", "FY2025 ROIC 8.1% / 8.3%: inside ±2 pp, the class can flip on the hurdle"),
    ("SPCX, INFQ, RIVN", "short_history → UNRATED"),
    ("MSTR, ETV", "asset_treasury / fund → not_applicable, N_A, no setup item"),
    ("Setup batch", "15 m06_verdict items (17 covered minus ETV and MSTR)"),
)  # fmt: skip


class Log:
    """Every line goes to the log file; the console shows the "=== Summary" block onward,
    failures and the log path."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
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


def run_quant(args, log: Log, folder: Path, engine=None, now: datetime | None = None) -> int:
    """The Part 1 check. `engine` and `now` are injected by tests (never the real DB)."""
    from engine.moat import params as params_mod
    from engine.moat import step
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
    p, perr = params_mod.load_safe(ROOT / "config" / "moat.toml")
    log(f"run_moat quant · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} names · 0 requests · "
        f"hurdle {p.hurdle:.0%}†, window {p.window_years} FY, MY horizon {p.my_horizon_years} "
        f"years · {p.version}" + (" · --no-sec" if args.no_sec else ""), "")  # fmt: skip
    if perr:
        log(f"moat.toml rejected: {perr}")
    mp = step.moat_pass(engine, comps, now, p=p, params_error=perr)
    log("Per name (quant class and share, ±2 pp classes, GM median, proposal, verdict, gate):")
    for t in sorted(mp.results):
        log("  " + step.line(mp.results[t]))
    for t, e in sorted(mp.errors.items()):
        log(f"  {t}: error — {e}")
    log("", "Missing rows (reason per signal):")
    miss = [f"  {r.ticker} {o.signal}: missing: {o.missing}" for r in mp.results.values()
            for o in r.rows if o.missing]  # fmt: skip
    log(*(miss or ["  none"]))
    log("", "Labels and method notes (first name of each class):")
    seen: set[str] = set()
    for t in sorted(mp.results):
        r = mp.results[t]
        k = r.quant.state or "missing"
        if k in seen:
            continue
        seen.add(k)
        log(f"  {t} [{k}]: {r.quant.method()[:900]}")
    log("", "ROIC / GM / OM per fiscal year (standard rows, every company; brief's companies):")
    for t in STRIP_TICKERS:
        if t in mp.results:
            log(*step.strip_lines(mp.results[t]))
    log("", "Brief's worked example (compare with the lines above):")
    for who, what in CHECKPOINTS:
        log(f"  {who}: {what}")
    after = counts(engine)
    open_items = engine.execute(
        "SELECT count(*) FROM review_queue WHERE kind = 'm06_verdict' AND resolved_at IS NULL"
    ).fetchone()[0]
    log("", SUMMARY_MARK)
    log(*step.summary_lines(mp))
    log(f"  m06_verdict items open: {open_items}")
    log(f"SEC requests: 0 · other requests: 0 · {time.monotonic() - t0:.1f} s")
    log("Rows added per table: " + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in after))
    if own:
        engine.close()
    return 0


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("subcommand", nargs="?", choices=[s for s, _, _ in SUBCOMMANDS])
    ap.add_argument(
        "--no-sec",
        action="store_true",
        help="accepted for the D-M04-69 pattern; no M06 subcommand calls SEC",
    )
    ap.add_argument("--tickers", help="comma-separated subset")
    ap.add_argument("--list", action="store_true", help="print the subcommand table")
    args = ap.parse_args(argv)
    args.companies = None
    if args.list or not args.subcommand:
        for name, part, what in SUBCOMMANDS:
            print(f"{name:12} Part {part:2} {what}" + ("" if name in BUILT else "  (not built)"))
        return 0 if args.list else 2
    if args.subcommand not in BUILT:
        print(f"{args.subcommand}: not built")
        return 2
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.chdir(ROOT)  # data/, config/ and logs/ are relative to the repo
    from engine.store.db import data_dir

    log = Log(ROOT / "logs" / f"moat_{args.subcommand}_{datetime.now():%Y%m%d-%H%M%S}.txt")
    print(f"run_moat {args.subcommand}: working; full detail goes to {log.path}")
    try:
        return {"quant": run_quant}[args.subcommand](args, log, data_dir())
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

    return run_script(ROOT, "run_moat", _main)


if __name__ == "__main__":
    sys.exit(main())
