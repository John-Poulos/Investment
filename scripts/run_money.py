"""Money flow (M02 part 3): spenders, capex guidance and actuals, capital allocation.

    uv run python scripts/run_money.py                    # full step: SEC instances + frames
    uv run python scripts/run_money.py --no-sec           # local only (no SEC requests)
    uv run python scripts/run_money.py --tickers META,AMZN

Per company: capex guidance lines with freshness, recipe vs stated actuals
(reconciliation), the capital-allocation block with financing coverage; then spender
candidates from annual capex frames. SEC requests: one per new 10-K/10-Q XBRL instance
for companies with an override recipe or coverage below 80%, plus the annual capex
frames (refreshed every 30 days). Writes logs/money_<YYYYMMDD-HHMMSS>.txt. Does not run
while the nightly refresh holds data/refresh.lock.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.calls.transcripts import symbol_cik  # noqa: E402
from engine.moneyflow.step import run_money_step  # noqa: E402
from engine.refresh import load_config  # noqa: E402
from engine.store.db import open_db  # noqa: E402
from engine.themes import tiers  # noqa: E402


def companies(engine) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in load_config(ROOT / "config" / "watchlist.toml").tickers:
        if cik := symbol_cik(engine, t):
            out[t] = cik
    for m in tiers.members(engine):
        out.setdefault(m.ticker, m.cik)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-sec", action="store_true", help="no SEC requests (local only)")
    ap.add_argument("--tickers", help="comma-separated subset (default: watchlist + tracked)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # "≈", "≥" on a cp1252 console
    if (ROOT / "data" / "refresh.lock").exists():
        print("data/refresh.lock exists: the refresh is running; try again later.")
        return 1
    import os

    os.chdir(ROOT)  # config/ and logs/ are relative to the repo
    engine = open_db("engine", ROOT / "data")
    corpus = open_db("corpus", ROOT / "data")
    client = None
    if not args.no_sec:
        from engine.sec.client import SecClient, user_agent_from_env
        from engine.store.http import SqliteCache, SqliteFetchLog

        client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus),
                           log=SqliteFetchLog(engine))  # fmt: skip
    comps = companies(engine)
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    now = datetime.now(UTC)
    lines = [f"run_money {now:%Y-%m-%d %H:%M} UTC · {len(comps)} companies"
             + (" · no SEC" if args.no_sec else "")]  # fmt: skip
    lines += run_money_step(client, engine, corpus, comps, now, detail=True)
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"money_{datetime.now():%Y%m%d-%H%M%S}.txt"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"Log written to: {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
