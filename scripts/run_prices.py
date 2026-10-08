"""Fetch daily prices from Tiingo (M00_UI DS8, D-UI-2).

    uv run python scripts/run_prices.py                   # watchlist (full history first time)
    uv run python scripts/run_prices.py --symbols NVDA,MU
    uv run python scripts/run_prices.py --full            # force full history

Requests are spaced 75 s apart and kept under 48/hour (free tier: 50), so the
16-symbol watchlist takes about 20 minutes. Key: TIINGO_API_KEY in .env (never
printed). Writes logs/prices_<YYYYMMDD-HHMMSS>.txt. The nightly refresh runs the
same update for the watchlist after the SEC step.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.prices.store import update_symbol  # noqa: E402
from engine.prices.tiingo import MissingKey, TiingoClient, token_from_env  # noqa: E402
from engine.store.db import open_db  # noqa: E402
from engine.ui.services import resolve_ticker, watchlist_tickers  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", help="comma-separated; default: the watchlist")
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    engine = open_db("engine", ROOT / "data")
    try:
        client = TiingoClient(token_from_env(), engine)
    except MissingKey as e:
        print(e)
        return 1
    symbols = (
        [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else watchlist_tickers(ROOT / "config" / "watchlist.toml")
    )
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"prices_{datetime.now():%Y%m%d-%H%M%S}.txt"
    lines = [
        f"Tiingo prices: {len(symbols)} symbols, ~{len(symbols) * 75 // 60} min at 75 s spacing"
    ]
    print(lines[0])
    for s in symbols:
        u = update_symbol(engine, client, s, resolve_ticker(engine, s), datetime.now(UTC),
                          full=args.full)  # fmt: skip
        span = engine.execute(
            "SELECT first_date, last_date, bars FROM price_fetch WHERE symbol = ?", (s,)
        ).fetchone()
        stored = f"{span[2]} bars {span[0]}..{span[1]}" if span else "0 bars"
        full = " (full history)" if u.full else ""
        line = f"  {s}: {u.outcome}, {u.bars} bars fetched{full}; stored {stored} {u.detail}"
        line = line.rstrip()
        lines.append(line)
        print(line, flush=True)
        if u.outcome in ("throttled", "budget"):
            lines.append(f"  stopped: {u.detail}; run again later for the rest")
            print(lines[-1])
            break
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Log written to: {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
