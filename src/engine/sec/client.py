"""The one SEC HTTP client (M00_SEC_DATA rules 1-5).

- One rate limiter for every SEC call in the process, across threads (≤ 8 req/s).
- `SEC_USER_AGENT` (name + email) required; placeholders rejected.
- 5xx and network errors retry with exponential backoff; other 4xx fail.
- 404 is `NotFound` (no file at that URL), never a failure and never "no data".
- A throttle (403/429, or the rate-threshold page under any status) opens a
  breaker that fails every SEC call fast for ≥ 10 minutes.
- Raw responses are cached by URL + params with a caller-supplied TTL.
  Failures are never cached; 404s are cached briefly and labeled not_found.
"""

from __future__ import annotations

import json
import os
import random
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlencode

import requests

from engine.sec.results import Failed, NotFound, Ok, Result

TARGET_RATE_PER_S = 8.0  # SEC allows 10/s per user; we target ≤ 8
BREAKER_SECONDS = 600.0  # rule 4: pause all SEC calls ≥ 10 min after a throttle
NOT_FOUND_TTL_S = 6 * 3600  # 404s are cached briefly so a broken link is not re-hit
MAX_ATTEMPTS = 4
TIMEOUT_S = 30.0
THROTTLE_MARKER = b"Request Rate Threshold Exceeded"

_PLACEHOLDER_AGENTS = (
    "example.com",
    "your@email",
    "your name",
    "pharmaagent",
)
_AGENT_RE = re.compile(r"^\S.*\s\S+@\S+\.\S+$")


class UserAgentError(ValueError):
    pass


def validate_user_agent(agent: str | None) -> str:
    """Return the agent if it looks like 'Name email@domain'; raise otherwise."""
    agent = (agent or "").strip()
    if not agent:
        raise UserAgentError("SEC_USER_AGENT is not set (expected 'Your Name you@domain.com')")
    if not _AGENT_RE.match(agent):
        raise UserAgentError("SEC_USER_AGENT must be a name followed by an email address")
    lowered = agent.lower()
    if any(p in lowered for p in _PLACEHOLDER_AGENTS):
        raise UserAgentError("SEC_USER_AGENT is a placeholder; use your own name and email")
    return agent


def user_agent_from_env() -> str:
    """Load .env (if present) and validate SEC_USER_AGENT. Call once at startup."""
    from dotenv import load_dotenv

    load_dotenv()
    return validate_user_agent(os.getenv("SEC_USER_AGENT"))


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat(timespec="seconds")


def cache_key(url: str, params: Mapping[str, Any] | None) -> str:
    if not params:
        return url
    return f"{url}?{urlencode(sorted((str(k), str(v)) for k, v in params.items()))}"


def is_throttle(status: int, body: bytes) -> bool:
    return status in (403, 429) or THROTTLE_MARKER in body[:50_000]


# --- Collaborators (protocols so tests and storage plug in) ------------------


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    headers: Mapping[str, str]


class Transport(Protocol):
    def __call__(
        self, url: str, params: Mapping[str, Any] | None, headers: Mapping[str, str]
    ) -> Response: ...


@dataclass(frozen=True)
class CachedResponse:
    status: int
    body: bytes
    content_type: str
    outcome: str  # "ok" | "not_found"
    fetched_at: str


class Cache(Protocol):
    def get(self, key: str, now: datetime) -> CachedResponse | None: ...

    def put(
        self,
        key: str,
        url: str,
        status: int,
        body: bytes,
        content_type: str,
        outcome: str,
        fetched_at: datetime,
        expires_at: datetime,
    ) -> None: ...


class FetchLog(Protocol):
    def write(
        self,
        url: str,
        outcome: str,
        detail: str,
        status: int | None,
        from_cache: bool,
        at: datetime,
    ) -> None: ...


class RequestsTransport:
    """Default transport: one requests.Session per thread."""

    def __init__(self, timeout: float = TIMEOUT_S) -> None:
        self._local = threading.local()
        self._timeout = timeout

    def __call__(
        self, url: str, params: Mapping[str, Any] | None, headers: Mapping[str, str]
    ) -> Response:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            self._local.session = session
        resp = session.get(url, params=params, headers=dict(headers), timeout=self._timeout)
        return Response(resp.status_code, resp.content, dict(resp.headers))


# --- Rate limiter and breaker -------------------------------------------------


class RateLimiter:
    """Spaces calls evenly at `rate` per second across all threads."""

    def __init__(
        self,
        rate: float = TARGET_RATE_PER_S,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = 1.0 / rate
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            slot = max(now, self._next)
            self._next = slot + self._interval
        if slot > now:
            self._sleep(slot - now)


class Breaker:
    """Opens on a throttle; while open, every SEC call fails fast."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._open_until = 0.0

    def trip(self, seconds: float = BREAKER_SECONDS) -> None:
        with self._lock:
            self._open_until = max(self._open_until, self._clock() + seconds)

    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self._open_until - self._clock())


# --- Client -------------------------------------------------------------------


class NullLog:
    def write(self, *args: Any, **kwargs: Any) -> None:
        pass


class SecClient:
    def __init__(
        self,
        user_agent: str,
        *,
        transport: Transport | None = None,
        cache: Cache | None = None,
        log: FetchLog | None = None,
        limiter: RateLimiter | None = None,
        breaker: Breaker | None = None,
        now: Callable[[], datetime] = utc_now,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.user_agent = validate_user_agent(user_agent)
        self._transport = transport or RequestsTransport()
        self._cache = cache
        self._log = log or NullLog()
        self._limiter = limiter or _shared_limiter()
        self._breaker = breaker or _shared_breaker()
        self._now = now
        self._sleep = sleep

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}

    def get_bytes(
        self, url: str, params: Mapping[str, Any] | None = None, *, ttl_s: float
    ) -> Result[bytes]:
        key = cache_key(url, params)
        now = self._now()

        if self._cache is not None and ttl_s > 0:
            hit = self._cache.get(key, now)
            if hit is not None:
                self._log.write(key, hit.outcome, "cache hit", hit.status, True, now)
                if hit.outcome == "not_found":
                    return NotFound(key, hit.status, from_cache=True)
                return Ok(hit.body, source_ref=key, fetched_at=hit.fetched_at, from_cache=True)

        result, resp = self._fetch(url, params, key)
        if isinstance(result, Ok | NotFound) and resp is not None and self._cache is not None:
            outcome = "ok" if isinstance(result, Ok) else "not_found"
            life = ttl_s if outcome == "ok" else min(ttl_s, NOT_FOUND_TTL_S)
            if life > 0:
                fetched = self._now()
                self._cache.put(
                    key,
                    url,
                    resp.status,
                    resp.body,
                    resp.headers.get("Content-Type", ""),
                    outcome,
                    fetched,
                    fetched + timedelta(seconds=life),
                )
        return result

    def get_json(
        self, url: str, params: Mapping[str, Any] | None = None, *, ttl_s: float
    ) -> Result[Any]:
        result = self.get_bytes(url, params, ttl_s=ttl_s)
        if not isinstance(result, Ok):
            return result
        try:
            data = json.loads(result.data)
        except ValueError as exc:
            return Failed(f"invalid JSON: {exc}", url=url)
        return Ok(
            data,
            source_ref=result.source_ref,
            fetched_at=result.fetched_at,
            from_cache=result.from_cache,
        )

    def get_text(
        self, url: str, params: Mapping[str, Any] | None = None, *, ttl_s: float
    ) -> Result[str]:
        result = self.get_bytes(url, params, ttl_s=ttl_s)
        if not isinstance(result, Ok):
            return result
        return Ok(
            result.data.decode("utf-8", errors="replace"),
            source_ref=result.source_ref,
            fetched_at=result.fetched_at,
            from_cache=result.from_cache,
        )

    def _fetch(
        self, url: str, params: Mapping[str, Any] | None, key: str
    ) -> tuple[Result[bytes], Response | None]:
        last: Failed | None = None
        for attempt in range(MAX_ATTEMPTS):
            wait = self._breaker.remaining()
            if wait > 0:
                failed = Failed(
                    f"throttle breaker open; SEC calls paused for {wait:.0f}s more",
                    url=url,
                    throttled=True,
                )
                self._log.write(key, "throttled", failed.reason, None, False, self._now())
                return failed, None

            self._limiter.acquire()
            try:
                resp = self._transport(url, params, self._headers())
            except requests.RequestException as exc:
                last = Failed(f"network error: {exc}", url=url)
                self._log.write(key, "failed", last.reason, None, False, self._now())
                self._backoff(attempt)
                continue

            if is_throttle(resp.status, resp.body):
                retry_after = _retry_after_s(resp.headers)
                self._breaker.trip(max(BREAKER_SECONDS, retry_after))
                detail = f"throttled (HTTP {resp.status}); breaker open {BREAKER_SECONDS:.0f}s+"
                self._log.write(key, "throttled", detail, resp.status, False, self._now())
                return Failed(detail, url=url, status=resp.status, throttled=True), None

            if resp.status >= 500:
                last = Failed(f"HTTP {resp.status}", url=url, status=resp.status)
                self._log.write(key, "failed", last.reason, resp.status, False, self._now())
                self._backoff(attempt)
                continue

            if resp.status == 404:
                self._log.write(
                    key, "not_found", "HTTP 404: no file at this URL", 404, False, self._now()
                )
                return NotFound(key), resp

            if resp.status >= 400:
                failed = Failed(f"HTTP {resp.status}", url=url, status=resp.status)
                self._log.write(key, "failed", failed.reason, resp.status, False, self._now())
                return failed, None

            fetched_at = iso(self._now())
            self._log.write(key, "ok", f"{len(resp.body)} bytes", resp.status, False, self._now())
            return Ok(resp.body, source_ref=key, fetched_at=fetched_at), resp

        assert last is not None
        return Failed(
            f"gave up after {MAX_ATTEMPTS} attempts: {last.reason}", url=url, status=last.status
        ), None

    def _backoff(self, attempt: int) -> None:
        if attempt < MAX_ATTEMPTS - 1:
            self._sleep((2**attempt) + random.uniform(0, 0.5))


def _retry_after_s(headers: Mapping[str, str]) -> float:
    value = next((v for k, v in headers.items() if k.lower() == "retry-after"), "")
    try:
        return float(value)
    except ValueError:
        return 0.0


_LIMITER: RateLimiter | None = None
_BREAKER: Breaker | None = None
_SHARED_LOCK = threading.Lock()


def _shared_limiter() -> RateLimiter:
    global _LIMITER
    with _SHARED_LOCK:
        if _LIMITER is None:
            _LIMITER = RateLimiter()
        return _LIMITER


def _shared_breaker() -> Breaker:
    global _BREAKER
    with _SHARED_LOCK:
        if _BREAKER is None:
            _BREAKER = Breaker()
        return _BREAKER
