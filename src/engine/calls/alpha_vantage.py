"""Alpha Vantage client: EARNINGS_CALL_TRANSCRIPT (M02 D-M02-6, D-M02-20) and
EARNINGS_ESTIMATES (M08 Part 2, D-M08-6, D-M08-14).

- Free key `ALPHA_VANTAGE_API_KEY` (.env). Alpha Vantage requires it as a query
  parameter, so it is passed only to the transport and never logged: `fetch_log`
  stores the URL without the key.
- Free tier: 25 requests/day. Before every request the shared `fetch_log` is
  counted over the last 24 hours: each function keeps its own share (transcripts 20,
  estimates 3 a day in scheduled runs, D-M08-6) and every request also stops at the
  key's 25 in total, so about 2 stay free for interactive use and probes; requests are
  spaced 15 s apart (as in the probe).
- `quarter` is the company's fiscal label ("2026Q4" = Microsoft FY26 Q4, probe
  2026-10-09). An empty `transcript` list means "not available yet", never "no
  guidance" (LESSONS).
- Results: Ok(Reply) (transcript possibly empty), Failed (throttled = budget, a
  rate-limit/premium message or HTTP 429).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from engine.sec.client import iso
from engine.sec.results import Failed, Ok, Result

URL = "https://www.alphavantage.co/query"
DAILY_LIMIT = 25  # Alpha Vantage free tier
RUN_BUDGET = 20  # scheduled runs; ~5 a day stay free for interactive use (D-M02-20)
MIN_INTERVAL_S = 15.0
TRANSCRIPT = "EARNINGS_CALL_TRANSCRIPT"
ESTIMATES = "EARNINGS_ESTIMATES"
ESTIMATES_BUDGET = 3  # M08's share of the key a day in scheduled runs (D-M08-6)

Transport = Callable[[str, Mapping[str, str], Mapping[str, str]], tuple[int, bytes]]


def requests_transport(
    url: str, params: Mapping[str, str], headers: Mapping[str, str]
) -> tuple[int, bytes]:
    import requests

    r = requests.get(url, params=dict(params), headers=dict(headers), timeout=60)
    return r.status_code, r.content


class MissingKey(RuntimeError):
    pass


def key_from_env() -> str:
    from dotenv import load_dotenv

    load_dotenv()
    key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
    if not key:
        raise MissingKey("ALPHA_VANTAGE_API_KEY is not set in .env")
    return key


def logged_url(symbol: str, quarter: str) -> str:
    """The request as logged: no key."""
    return f"{URL}?function={TRANSCRIPT}&symbol={symbol}&quarter={quarter}"


def logged_estimates_url(symbol: str) -> str:
    """The estimates request as logged: no key."""
    return f"{URL}?function={ESTIMATES}&symbol={symbol}"


@dataclass(frozen=True)
class Reply:
    raw: bytes  # the reply as received, stored once (doc_raw)
    data: dict[str, Any]

    @property
    def turns(self) -> list[dict[str, Any]]:
        t = self.data.get("transcript")
        return [s for s in t if isinstance(s, dict)] if isinstance(t, list) else []


def parse_reply(raw: bytes) -> Reply | str:
    """A transcript reply, or the reason it is not one."""
    try:
        data = json.loads(raw)
    except ValueError as e:
        return f"unreadable JSON: {e}"
    if not isinstance(data, dict):
        return "unexpected reply shape"
    for k in ("Information", "Note", "Error Message"):
        if k in data:
            return f"{k}: {str(data[k])[:200]}"
    if not isinstance(data.get("transcript", []), list):
        return "unexpected reply shape"
    return Reply(raw, data)


@dataclass(frozen=True)
class EstimatesReply:
    """An EARNINGS_ESTIMATES reply: one dict per horizon row (fiscal years and quarters, past
    quarters included). No rows = no coverage (`note` says which reply form), never zero."""

    raw: bytes
    data: dict[str, Any]
    note: str = ""

    @property
    def rows(self) -> list[dict[str, Any]]:
        t = self.data.get("estimates")
        return [r for r in t if isinstance(r, dict)] if isinstance(t, list) else []


def parse_estimates(raw: bytes) -> EstimatesReply | str:
    """An estimates reply (possibly without coverage), or the reason it is not one.

    No coverage reads as an empty reply (`{}`), an empty `estimates` list, or the vendor's
    "Invalid API call" error, which it also gives for an unknown symbol; the probe confirms
    which form the free key returns (D-M08-14)."""
    try:
        data = json.loads(raw)
    except ValueError as e:
        return f"unreadable JSON: {e}"
    if not isinstance(data, dict):
        return "unexpected reply shape"
    for k in ("Information", "Note"):
        if k in data:
            return f"{k}: {str(data[k])[:200]}"
    if "Error Message" in data:
        msg = str(data["Error Message"])
        if "invalid api call" in msg.lower():
            return EstimatesReply(raw, {}, "no coverage: vendor 'Invalid API call' "
                                  "(unknown symbol or not covered)")  # fmt: skip
        return f"Error Message: {msg[:200]}"
    est = data.get("estimates", [])
    if not isinstance(est, list):
        return "unexpected reply shape"
    if not any(isinstance(r, dict) for r in est):
        return EstimatesReply(raw, data, "no coverage: empty reply" if not data
                              else "no coverage: no estimate rows")  # fmt: skip
    return EstimatesReply(raw, data)


class AlphaVantageClient:
    def __init__(
        self,
        key: str,
        engine: sqlite3.Connection,
        *,
        transport: Transport = requests_transport,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        daily_budget: int = RUN_BUDGET,
        min_interval_s: float = MIN_INTERVAL_S,
    ) -> None:
        self._key = key
        self._engine = engine
        self._transport = transport
        self._now = now
        self._clock = clock
        self._sleep = sleep
        self._budget = min(daily_budget, DAILY_LIMIT)
        self._min_interval = min_interval_s
        self._last: float | None = None

    def used_24h(self, function: str | None = None) -> int:
        """Requests in the last 24 hours: all of the key's, or one function's."""
        since = self._now() - timedelta(days=1)
        like = URL + "%" if function is None else f"{URL}?function={function}&%"
        return self._engine.execute(
            "SELECT count(*) FROM fetch_log WHERE url LIKE ? AND at >= ? AND from_cache = 0",
            (like, iso(since)),
        ).fetchone()[0]

    def budget_left(self, function: str = TRANSCRIPT, budget: int | None = None) -> int:
        """Requests left for `function`: its own share (transcripts: the run budget) and the
        key's daily limit in total, whichever is lower (D-M08-6)."""
        own = self._budget if budget is None else min(budget, DAILY_LIMIT)
        return max(0, min(own - self.used_24h(function), DAILY_LIMIT - self.used_24h()))

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
            (url, outcome, status, detail.replace(self._key, "***")[:500], iso(self._now())),
        )

    def transcript(self, symbol: str, quarter: str) -> Result[Reply]:
        url = logged_url(symbol, quarter)
        if self.budget_left() <= 0:
            return Failed(f"daily budget reached ({self._budget} requests in 24 hours)",
                          url=url, throttled=True)  # fmt: skip
        params = {"function": TRANSCRIPT, "symbol": symbol,
                  "quarter": quarter, "apikey": self._key}  # fmt: skip
        got = self._get(url, params)
        if not isinstance(got, tuple):
            return got
        status, body = got
        reply = parse_reply(body)
        if isinstance(reply, str):
            return self._refused(url, status, reply)
        n = len(reply.turns)
        self._log(url, "ok", status, f"{n} turns" if n else "empty transcript")
        return Ok(reply, source_ref=url, fetched_at=iso(self._now()))

    def estimates(self, symbol: str, *, budget: int = ESTIMATES_BUDGET) -> Result[EstimatesReply]:
        """EARNINGS_ESTIMATES for one symbol (M08, D-M08-6). `budget` = M08's share in 24 hours
        (3 in scheduled runs; a probe passes the key's limit and uses the spare)."""
        url = logged_estimates_url(symbol)
        if self.budget_left(ESTIMATES, budget) <= 0:
            return Failed(f"daily budget reached (estimates {min(budget, DAILY_LIMIT)}, key "
                          f"{DAILY_LIMIT} requests in 24 hours)", url=url,
                          throttled=True)  # fmt: skip
        params = {"function": ESTIMATES, "symbol": symbol, "apikey": self._key}
        got = self._get(url, params)
        if not isinstance(got, tuple):
            return got
        status, body = got
        reply = parse_estimates(body)
        if isinstance(reply, str):
            return self._refused(url, status, reply)
        n = len(reply.rows)
        self._log(url, "ok", status, f"{n} estimate rows" if n else reply.note)
        return Ok(reply, source_ref=url, fetched_at=iso(self._now()))

    def _refused(self, url: str, status: int, reason: str) -> Failed:
        limit = any(w in reason.lower() for w in ("rate limit", "requests per", "premium"))
        self._log(url, "throttled" if limit else "failed", status, reason)
        return Failed(reason.replace(self._key, "***"), url=url, status=status,
                      throttled=limit)  # fmt: skip

    def _get(self, url: str, params: dict[str, str]) -> tuple[int, bytes] | Failed:
        """(status 200, body), or the failure, logged. The key goes only to the transport."""
        self._pace()
        try:
            status, body = self._transport(URL, params, {})
        except Exception as e:  # network errors are failures, never empty data
            detail = f"{type(e).__name__}: {e}".replace(self._key, "***")
            self._log(url, "failed", None, detail)
            return Failed(detail, url=url)
        if status == 429:
            self._log(url, "throttled", status, "HTTP 429")
            return Failed("HTTP 429 from Alpha Vantage", url=url, status=status, throttled=True)
        if status != 200:
            detail = body[:200].decode("utf-8", "replace")
            self._log(url, "failed", status, detail)
            return Failed(f"HTTP {status}", url=url, status=status)
        return status, body
