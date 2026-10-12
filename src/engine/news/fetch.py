"""HTTP for news feeds and news APIs (D-M02-13): pacing per lane, the shared fetch log.

- Lanes: `feed` (RSS, 1 s apart), `finnhub` (free tier 60/min → 1.1 s apart), `massive`
  (free tier 5/min → 12.5 s apart); official feeds (part 7b, D-M02-13): `arxiv` (3 s, as
  arXiv asks), `usaspending`, `fedreg` and `congress` (1 s each, well inside 5,000/h).
- `post_json` for APIs that take a JSON body (USAspending), same pacing and logging.
- Keys travel in headers only, and any secret is masked in logged details; `fetch_log`
  stores the URL as given by the caller (never with a key).
- A network error or HTTP error is a `Failed`, never empty data; 429 is throttled.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from engine.sec.client import iso
from engine.sec.results import Failed

USER_AGENT = "InvestmentEngine/0.1 (personal research; RSS reader)"
INTERVALS = {
    "feed": 1.0,
    "finnhub": 1.1,
    "massive": 12.5,
    "arxiv": 3.0,
    "usaspending": 1.0,
    "fedreg": 1.0,
    "congress": 1.0,
}

Transport = Callable[
    [str, Mapping[str, str], Mapping[str, str]], tuple[int, bytes, Mapping[str, str]]
]


def requests_transport(
    url: str, params: Mapping[str, str], headers: Mapping[str, str]
) -> tuple[int, bytes, Mapping[str, str]]:
    import requests

    r = requests.get(url, params=dict(params) or None, headers=dict(headers), timeout=30)
    return r.status_code, r.content, dict(r.headers)


PostTransport = Callable[[str, object, Mapping[str, str]], tuple[int, bytes, Mapping[str, str]]]


def requests_post_transport(
    url: str, body: object, headers: Mapping[str, str]
) -> tuple[int, bytes, Mapping[str, str]]:
    import requests

    r = requests.post(url, json=body, headers=dict(headers), timeout=60)
    return r.status_code, r.content, dict(r.headers)


@dataclass(frozen=True)
class Reply:
    status: int  # 200, or 304 (not modified)
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    def header(self, name: str) -> str | None:
        low = name.lower()
        return next((v for k, v in self.headers.items() if k.lower() == low), None)


class Fetcher:
    def __init__(
        self,
        engine: sqlite3.Connection,
        *,
        transport: Transport = requests_transport,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        intervals: Mapping[str, float] | None = None,
        secrets: tuple[str, ...] = (),
        post_transport: PostTransport = requests_post_transport,
    ) -> None:
        self._engine = engine
        self._transport = transport
        self._post = post_transport
        self._now = now
        self._clock = clock
        self._sleep = sleep
        self._intervals = dict(INTERVALS if intervals is None else intervals)
        self._last: dict[str, float] = {}
        self._secrets = tuple(s for s in secrets if s)

    def _mask(self, text: str) -> str:
        for s in self._secrets:
            text = text.replace(s, "***")
        return text

    def _pace(self, lane: str) -> None:
        last = self._last.get(lane)
        if last is not None:
            wait = self._intervals.get(lane, 1.0) - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last[lane] = self._clock()

    def _log(self, url: str, outcome: str, status: int | None, detail: str) -> None:
        self._engine.execute(
            "INSERT INTO fetch_log (url, outcome, status, from_cache, detail, at) "
            "VALUES (?, ?, ?, 0, ?, ?)",
            (self._mask(url), outcome, status, self._mask(detail)[:500], iso(self._now())),
        )

    def get(
        self,
        url: str,
        *,
        lane: str = "feed",
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        logged_url: str | None = None,
    ) -> Reply | Failed:
        hdrs = {"User-Agent": USER_AGENT} | dict(headers or {})
        return self._call(lambda: self._transport(url, params or {}, hdrs), lane,
                          logged_url or url)  # fmt: skip

    def post_json(
        self,
        url: str,
        body: object,
        *,
        lane: str,
        headers: Mapping[str, str] | None = None,
        logged_url: str | None = None,
    ) -> Reply | Failed:
        hdrs = {"User-Agent": USER_AGENT, "Content-Type": "application/json"} | dict(headers or {})
        return self._call(lambda: self._post(url, body, hdrs), lane, logged_url or url)

    def _call(self, send, lane: str, shown: str) -> Reply | Failed:
        self._pace(lane)
        try:
            status, body, rh = send()
        except Exception as e:  # network errors are failures, never empty data
            detail = self._mask(f"{type(e).__name__}: {e}")
            self._log(shown, "failed", None, detail)
            return Failed(detail, url=self._mask(shown))
        if status == 429:
            self._log(shown, "throttled", status, "HTTP 429")
            return Failed("HTTP 429", url=self._mask(shown), status=status, throttled=True)
        if status == 304:
            self._log(shown, "ok", status, "not modified")
            return Reply(304, b"", rh)
        if status != 200:
            detail = body[:200].decode("utf-8", "replace")
            self._log(shown, "failed", status, detail)
            return Failed(f"HTTP {status}", url=self._mask(shown), status=status)
        self._log(shown, "ok", status, f"{len(body):,} bytes")
        return Reply(200, body, rh)
