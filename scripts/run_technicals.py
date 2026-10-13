"""M09 Technicals: one owner script, one subcommand per build part (M09 Part 1).

    uv run python scripts/run_technicals.py signals             # Part 1 live check
    uv run python scripts/run_technicals.py signals --no-fetch  # 0 requests (SPY not fetched)
    uv run python scripts/run_technicals.py --list              # the subcommand table

`signals` (Part 1): fetches SPY's daily prices from Tiingo (the benchmark, D-UI-33: one
full-history request the first time, then one request for the recent days; `--no-fetch`
skips it), then computes from stored prices (0 requests) for every covered name —
watchlist, promoted and tracked — the five M09 rows: `band_z`, `price_band`, `trend_state`,
`mom_12_1`, `rev_1m` (one row set for the newest completed week), with the M04
qualification label, and prints one line per name, SPY's trend and 12-1, and the known
pack checkpoints to compare.

Takes data/refresh.lock (one data-writing run at a time). Writes
logs/technicals_<subcommand>_<YYYYMMDD-HHMMSS>.txt as it goes, with Tiingo requests and
seconds, rows added per table and engine.db size before and after; the console shows the
summary only. Its own tracebacks go to the log too, so the log is all the owner sends back.
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
    ("signals", "1", "band_z, price_band, trend_state, mom_12_1, rev_1m; SPY benchmark"),
    ("tab", "2", "Technicals tab and chart overlays (app, no script)"),
)
BUILT = {"signals"}
SUMMARY_MARK = "=== Summary"
CONSOLE_ALWAYS = ("Log written to:", "FAILED", "Tiingo stop")
COUNTED_TABLES = ("signal", "price_bar", "price_fetch", "fetch_log")
# The pack's figures to compare (Yahoo weekly closes, read 2026-10-12; Tiingo may differ
# slightly): docs/M09_TECHNICALS.md "Live checks".
CHECKPOINTS = (
    ("MU", "2026-03-27", "band_z +0.32 inside, z price +0.24, pullback_sigma −2.01, "
     "20-week high 427.92 (close 357.02)"),
    ("MU", "2026-07-31", "band_z +0.43 inside, z price +0.30, pullback_sigma −2.43, "
     "20-week high 1133.82 (close 823.03)"),
    ("MSTR", "2025-11-21", "z price −2.24 (close 170.50)"),
    ("MSTR", "2026-06-26", "band_z −2.66 below_2, z price −2.22, pullback_sigma −6.83, "
     "40-week MA 175.85 (close 82.31)"),
    ("SPY", "2026-10-09", "trend up: 778.57 vs MA 721.29 (+7.9%), slope +1.3% (week of 10-05)"),
    ("SPY", "2026-03-27", "trend flat: 630.89 vs MA 656.64 (−3.9%), 2nd close below, slope "
     "+1.0% (week of 03-23)"),
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


def db_mb(folder: Path) -> float:
    return sum((folder / n).stat().st_size for n in ("engine.db", "engine.db-wal")
               if (folder / n).exists()) / 1e6  # fmt: skip


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


def tiingo_requests(engine, since: str) -> int:
    from engine.prices.tiingo import BASE

    return engine.execute(
        "SELECT count(*) FROM fetch_log WHERE url LIKE ? AND at >= ? AND from_cache = 0",
        (BASE + "/%", since),
    ).fetchone()[0]


def fetch_spy(engine, log: Log, now: datetime) -> None:
    """One Tiingo request for SPY (full history the first time). Never raises."""
    from engine.prices.store import BENCHMARK, update_symbol
    from engine.prices.tiingo import MissingKey, TiingoClient, token_from_env

    try:
        client = TiingoClient(token_from_env(), engine)
    except MissingKey as e:
        log(f"{BENCHMARK}: not fetched — {e}")
        return
    t0 = time.monotonic()
    u = update_symbol(engine, client, BENCHMARK, None, now)
    span = engine.execute(
        "SELECT first_date, last_date, bars FROM price_fetch WHERE symbol = ?", (BENCHMARK,)
    ).fetchone()
    stored = f"stored {span[2]} bars {span[0]}..{span[1]}" if span else "nothing stored"
    log(f"{BENCHMARK}: {u.outcome}, {u.bars} bars fetched" + (" (full history)" if u.full else "")
        + f"; {stored}; {time.monotonic() - t0:.1f} s {u.detail}".rstrip())  # fmt: skip
    if u.outcome in ("throttled", "budget"):
        log(f"Tiingo stop: {u.detail}; signals use the SPY bars already stored")


def checkpoint_line(engine, who: str, day: str, p, now: datetime) -> str:
    """The same numbers recomputed at a past week from stored bars (no rows written)."""
    from datetime import date

    from engine.technicals import bands, bars
    from engine.technicals import signals as sig

    today = bars.eastern_today(now)
    w = bars.weekly(engine, who, today)
    monday = bars.monday_of(date.fromisoformat(day)).isoformat()
    idx = next((i for i, b in enumerate(w.bars) if b.monday == monday), None)
    if idx is None:
        return f"engine: no completed week of {monday} stored for {who}"
    closes = w.closes()[: idx + 1]
    b = bands.band_at(closes, window=p.band_window, returns=p.pullback_returns)
    tr = sig.trend_at(closes, p)
    bits = [f"engine {w.bars[idx].date} close {closes[-1]:.2f}"]
    if b is not None and b.z is not None:
        pb = f", pullback_sigma {b.pullback_sigma:+.2f}" if b.pullback_sigma is not None else ""
        zp = f"{b.z_price:+.2f}" if b.z_price is not None else "n/a"
        bits.append(f"band_z {b.z:+.2f} {bands.zone(b.z, p.zone_1, p.zone_2)}, z price {zp}"
                    f"{pb}, 20-week high {b.high:.2f}")  # fmt: skip
    if tr is not None:
        bits.append(f"trend {tr.state} (MA {tr.ma:.2f}, {tr.ma_distance:+.1%}, slope "
                    f"{tr.slope:+.2%}{', pending flip' if tr.pending else ''})")  # fmt: skip
    return "; ".join(bits)


def run_signals(args, log: Log, folder: Path, engine=None, now: datetime | None = None) -> int:
    """The Part 1 check. `engine` and `now` are injected by tests (never the real DB)."""
    from engine.financials import models
    from engine.store.db import open_db
    from engine.technicals import params as params_mod
    from engine.technicals import signals as sig
    from engine.technicals.step import spy_line, summary_lines, technicals_pass

    own = engine is None
    engine = engine if engine is not None else open_db("engine", folder)
    now = now or datetime.now(UTC)
    t_start = time.monotonic()
    since = now.isoformat(timespec="seconds")
    mb_before = db_mb(folder)
    before = counts(engine)
    comps = companies(engine) if args.companies is None else args.companies
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    p, note = params_mod.load_safe(ROOT / "config" / "technicals.toml")
    log(f"run_technicals signals · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} names · parameters "
        f"{p.version}" + (" · --no-fetch (0 requests)" if args.no_fetch else " · SPY: 1 Tiingo "
        "request"), f"engine.db before: {mb_before:,.1f} MB", "")  # fmt: skip
    if note:
        log(f"parameters: {note}")
    if not args.no_fetch:
        fetch_spy(engine, log, now)
    tp = technicals_pass(engine, comps, now, params=p, mf=models.load_safe())
    tp.params_note = note
    log("", f"Per name (newest completed week {tp.expected_as_of}):")
    for t in sorted(tp.results):
        log("  " + sig.line(tp.results[t]))
    for t, e in sorted(tp.errors.items()):
        log(f"  {t}: error — {e}")
    log("", "Missing rows (reason per signal):")
    miss = [f"  {r.ticker} {o.signal}: missing: {o.missing}" for r in tp.results.values()
            for o in r.rows if o.missing]  # fmt: skip
    log(*(miss or ["  none"]))
    log("", "News moves (earnings 8-K in the rev_1m window):")
    news = [f"  {r.ticker}: " + "; ".join(c.text() for c in r.news)
            for r in tp.results.values() if r.news]  # fmt: skip
    log(*(news or ["  none"]))
    log("", "Pack checkpoints (Yahoo; recomputed here from stored Tiingo bars, no rows written):")
    for who, day, what in CHECKPOINTS:
        log(f"  {who} {day}: pack {what}", f"    {checkpoint_line(engine, who, day, p, now)}")
    req = tiingo_requests(engine, since)
    after = counts(engine)
    log("", SUMMARY_MARK)
    log(*summary_lines(tp, p))
    log(f"Tiingo requests: {req} · SEC requests: 0 · {time.monotonic() - t_start:.1f} s")
    log("Rows added per table: " + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in after))
    log(f"engine.db: {mb_before:,.1f} MB → {db_mb(folder):,.1f} MB")
    log(spy_line(tp, p))
    if own:
        engine.close()
    return 0


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("subcommand", nargs="?", choices=[s for s, _, _ in SUBCOMMANDS])
    ap.add_argument("--no-fetch", action="store_true", help="no Tiingo request (SPY not fetched)")
    ap.add_argument("--tickers", help="comma-separated subset (default: watchlist + tiers)")
    ap.add_argument("--list", action="store_true", help="print the subcommand table")
    args = ap.parse_args(argv)
    args.companies = None
    if args.list or not args.subcommand:
        for name, part, what in SUBCOMMANDS:
            print(f"{name:8} Part {part:2} {what}" + ("" if name in BUILT else "  (not built)"))
        return 0 if args.list else 2
    if args.subcommand not in BUILT:
        print(f"{args.subcommand}: not built (Part 2 is the app's Technicals tab)")
        return 2
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.chdir(ROOT)  # data/, config/ and logs/ are relative to the repo
    from engine.store.db import data_dir

    log = Log(ROOT / "logs" / f"technicals_{args.subcommand}_{datetime.now():%Y%m%d-%H%M%S}.txt")
    print(f"run_technicals {args.subcommand}: working; full detail goes to {log.path}")
    try:
        return run_signals(args, log, data_dir())
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

    return run_script(ROOT, "run_technicals", _main)


if __name__ == "__main__":
    sys.exit(main())
