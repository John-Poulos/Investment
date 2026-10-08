"""Show what watchlist tickers resolved to in data/engine.db (read-only).

uv run python scripts/check_tickers.py SPCX ETV INFQ
uv run python scripts/check_tickers.py            # all tickers in config/watchlist.toml
"""

from __future__ import annotations

import sqlite3
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    tickers = [t.upper() for t in sys.argv[1:]]
    if not tickers:
        with (ROOT / "config" / "watchlist.toml").open("rb") as fh:
            tickers = [t.upper() for t in tomllib.load(fh)["watchlist"]["tickers"]]
    conn = sqlite3.connect(f"file:{ROOT / 'data' / 'engine.db'}?mode=ro", uri=True)
    for ticker in tickers:
        row = conn.execute(
            "SELECT t.cik, t.name, t.exchange, e.name, e.sic, e.sic_description, e.entity_type "
            "FROM ticker t LEFT JOIN entity e ON e.cik = t.cik "
            "WHERE t.ticker = ? AND t.valid_to IS NULL",
            (ticker,),
        ).fetchone()
        if row is None:
            print(f"{ticker:<6} not in SEC's ticker files")
            continue
        cik, file_name, exchange, entity, sic, sic_desc, kind = row
        forms = conn.execute(
            "SELECT f.form, count(*) FROM filing f JOIN filing_cik c ON c.accession = f.accession "
            "WHERE c.cik = ? GROUP BY f.form ORDER BY count(*) DESC LIMIT 6",
            (cik,),
        ).fetchall()
        print(f"{ticker:<6} CIK {cik}  {entity or file_name}  exchange={exchange}  "
              f"SIC {sic} {sic_desc or ''}  type={kind}")  # fmt: skip
        print(f"       top forms: {', '.join(f'{f} x{n}' for f, n in forms) or 'none stored'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
