"""Tiingo end-of-day client (M00_UI DS8, D-UI-2; S68, S69).

- The key is read from `TIINGO_API_KEY` (.env) and sent only in the
  `Authorization: Token …` header, so it never appears in URLs or logs.
- Free-tier limits (50 requests/hour, 1,000/day, 500 symbols/month) are kept
  with margins: requests are spaced a few seconds apart within a process, and before
  every request the shared `fetch_log` is checked so the nightly job and the UI
  together stay under 48/hour, 950/day and 480 symbols/month.
- Every request is logged in `fetch_log` (URL without the key).
- Results use the SEC layer's types: Ok (bars, possibly none in range),
  NotFound (unknown symbol), Failed (throttled = budget or HTTP 429).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from engine.sec.client import iso
from engine.sec.results import Failed, NotFound, Ok, Result

BASE = "https://api.tiingo.com/tiingo/daily"
HOURLY_BUDGET = 48  # Tiingo free: 50
DAILY_BUDGET = 950  # Tiingo free: 1,000
MONTHLY_SYMBOLS = 480  # Tiingo free: 500 unique symbols per month
# Tiingo's limits are counts (per hour, per day, symbols per month), enforced by
# budget_problem() from fetch_log; spacing only avoids bursts (D-M02-19; was 75 s).
MIN_INTERVAL_S = 3.0
# The scheduled run stays at 40/hour so the app keeps 8/hour for its own fetches
# (D-M02-12: runs happen at logon, during the owner's session).
BATCH_HOURLY_BUDGET = 40
BATCH_MIN_INTERVAL_S = 3.0

Transport = Callable[[str, Mapping[str, str], Mapping[str, str]], tuple[int, bytes]]


def requests_transport(
    url: str, params: Mapping[str, str], headers: Mapping[str, str]
) -> tuple[int, bytes]:
    import requests

    r = requests.get(url, params=dict(params), headers=dict(headers), timeout=60)
    return r.status_code, r.content


class MissingKey(RuntimeError):
    pass


def token_from_env() -> str:
    from dotenv import load_dotenv

    load_dotenv()
    token = os.getenv("TIINGO_API_KEY", "").strip()
    if not token:
        raise MissingKey("TIINGO_API_KEY is not set in .env")
    return token


def symbol_of(url: str) -> str | None:
    if not url.startswith(BASE + "/"):
        return None
    return url[len(BASE) + 1 :].split("/", 1)[0].upper()


class TiingoClient:
    def __init__(
        self,
        token: str,
        engine: sqlite3.Connection,
        *,
        transport: Transport = requests_transport,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        min_interval_s: float = MIN_INTERVAL_S,
        hourly_budget: int = HOURLY_BUDGET,
    ) -> None:
        self._hourly = hourly_budget
        self._token = token
        self._engine = engine
        self._transport = transport
        self._now = now
        self._clock = clock
        self._sleep = sleep
        self._min_interval = min_interval_s
        self._last: float | None = None

    # --- budget -------------------------------------------------------------

    def _count_since(self, since: datetime) -> int:
        return self._engine.execute(
            "SELECT count(*) FROM fetch_log WHERE url LIKE ? AND at >= ? AND from_cache = 0",
            (BASE + "/%", iso(since)),
        ).fetchone()[0]

    def symbols_this_month(self) -> set[str]:
        start = self._now().astimezone(UTC).replace(day=1, hour=0, minute=0, second=0)
        rows = self._engine.execute(
            "SELECT DISTINCT url FROM fetch_log WHERE url LIKE ? AND at >= ?",
            (BASE + "/%", iso(start)),
        ).fetchall()
        return {s for r in rows if (s := symbol_of(r[0]))}

    def budget_problem(self, symbol: str) -> str | None:
        now = self._now()
        if self._count_since(now - timedelta(hours=1)) >= self._hourly:
            return f"hourly budget reached ({self._hourly} requests in the last hour)"
        if self._count_since(now - timedelta(days=1)) >= DAILY_BUDGET:
            return f"daily budget reached ({DAILY_BUDGET} requests in 24 hours)"
        month = self.symbols_this_month()
        if symbol.upper() not in month and len(month) >= MONTHLY_SYMBOLS:
            return f"monthly symbol budget reached ({MONTHLY_SYMBOLS} symbols)"
        return None

    # --- requests -----------------------------------------------------------

    def _pace(self) -> None:
        if self._last is not None:
            wait = self._min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()

    def _log(self, url: str, outcome: str, status: int | None, detail: str) -> None:
        self._engine.execute(
            "INSERT INTO fetch_log (url, outcome, status, from_cache, detail, at) "
            "VALUES (?, ?, ?, 0, ?, ?)",
            (url, outcome, status, detail[:500], iso(self._now())),
        )

    def daily(
        self, symbol: str, start: date | None = None, end: date | None = None
    ) -> Result[list[dict[str, Any]]]:
        url = f"{BASE}/{symbol.upper()}/prices"
        problem = self.budget_problem(symbol)
        if problem:
            return Failed(problem, url=url, throttled=True)
        params = {"format": "json"}
        if start:
            params["startDate"] = start.isoformat()
        if end:
            params["endDate"] = end.isoformat()
        logged = url + ("?" + "&".join(f"{k}={v}" for k, v in params.items()))
        headers = {"Authorization": f"Token {self._token}", "Content-Type": "application/json"}
        self._pace()
        try:
            status, body = self._transport(url, params, headers)
        except Exception as e:  # network errors are failures, never empty data
            self._log(logged, "failed", None, f"{type(e).__name__}: {e}")
            return Failed(f"{type(e).__name__}: {e}", url=url)
        if status == 200:
            try:
                rows = json.loads(body)
            except ValueError as e:
                self._log(logged, "failed", status, f"unreadable JSON: {e}")
                return Failed(f"unreadable JSON: {e}", url=url, status=status)
            if not isinstance(rows, list):
                self._log(logged, "failed", status, "unexpected reply shape")
                return Failed("unexpected reply shape", url=url, status=status)
            self._log(logged, "ok", status, f"{len(rows)} bars")
            return Ok(rows, source_ref=f"tiingo:{symbol.upper()}", fetched_at=iso(self._now()))
        detail = body[:200].decode("utf-8", "replace")
        if status == 404:
            self._log(logged, "not_found", status, detail)
            return NotFound(url, status)
        if status == 429:
            self._log(logged, "throttled", status, detail)
            return Failed("HTTP 429 from Tiingo", url=url, status=status, throttled=True)
        self._log(logged, "failed", status, detail)
        return Failed(f"HTTP {status}: {detail}", url=url, status=status)
