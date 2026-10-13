"""Short interest: no source in the MVP (D-M07-8, DATA_SOURCES DS18).

The Insiders tab shows a "missing" line (no D13 row). M07 Part 1's live check sends one
Massive short-interest request to learn whether the owner's Basic key may read it (Massive's
docs list it for all Stocks plans; its pricing page does not, S-new-M08-29). Massive's free
tier allows 5 calls a minute; the key travels as a Bearer header and is never logged.
"""

from __future__ import annotations

import json

from engine.news.fetch import Fetcher
from engine.sec.results import Failed

MASSIVE_SI_URL = "https://api.massive.com/stocks/v1/short-interest"
PROBE_TICKER = "AAPL"


def probe(fetcher: Fetcher, key: str, ticker: str = PROBE_TICKER) -> list[str]:
    """One request; lines for the log (status, fields, latest settlement row)."""
    params = {"ticker": ticker, "limit": "1", "sort": "settlement_date.desc"}
    shown = f"{MASSIVE_SI_URL}?ticker={ticker}&limit=1&sort=settlement_date.desc"
    reply = fetcher.get(MASSIVE_SI_URL, lane="massive", params=params,
                        headers={"Authorization": f"Bearer {key}"}, logged_url=shown)  # fmt: skip
    head = f"Massive short-interest probe (1 request, {ticker}): {shown}"
    if isinstance(reply, Failed):
        verdict = ("not available on this key's plan (keep DS18 open; FINRA needs an owner "
                   "account)" if reply.status in (401, 403) else "failed")  # fmt: skip
        return [head, f"  → {reply.reason} — {verdict}"]
    try:
        body = json.loads(reply.body)
    except ValueError:
        return [head, f"  → HTTP 200 but not JSON: {reply.body[:200]!r}"]
    results = body.get("results") if isinstance(body, dict) else None
    if not results:
        status = body.get("status") if isinstance(body, dict) else "?"
        return [head, f"  → HTTP 200, no rows (status {status}): readable but empty for {ticker}"]
    row = results[0]
    fields = ", ".join(sorted(row))
    return [
        head,
        f"  → HTTP 200, {len(results)} row(s); fields: {fields}",
        "  latest: settlement_date {} · short_interest {} · avg_daily_volume {} · days_to_cover {}"
        .format(*(row.get(k, "n/a") for k in ("settlement_date", "short_interest",
                                             "avg_daily_volume", "days_to_cover"))),
        "  → readable on this key: short interest can be built at tuning (DS18, D-M07-8)",
    ]  # fmt: skip
