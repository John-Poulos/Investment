from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from engine.sec.client import Breaker, RateLimiter, Response, SecClient
from engine.store.db import open_db
from engine.store.http import SqliteCache, SqliteFetchLog

FIXTURES = Path(__file__).parent / "fixtures"
AGENT = "Test Owner test.owner@mailbox.org"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def ok(body: bytes, status: int = 200, **headers: str) -> Response:
    return Response(status, body, headers)


class FakeTransport:
    """Serves queued responses per URL; the last response for a URL repeats."""

    def __init__(self, routes: Mapping[str, list[Response | Exception]] | None = None) -> None:
        self.routes: dict[str, list[Response | Exception]] = {
            k: list(v) for k, v in (routes or {}).items()
        }
        self.calls: list[tuple[str, dict[str, Any] | None, dict[str, str]]] = []

    def __call__(
        self, url: str, params: Mapping[str, Any] | None, headers: Mapping[str, str]
    ) -> Response:
        self.calls.append((url, dict(params) if params else None, dict(headers)))
        queue = self.routes.get(url)
        if not queue:
            raise AssertionError(f"unexpected request: {url}")
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.wall = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
        self.sleeps: list[float] = []

    def mono(self) -> float:
        return self.t

    def now(self) -> datetime:
        return self.wall + timedelta(seconds=self.t - 1000.0)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def dbs(tmp_path: Path):
    engine = open_db("engine", tmp_path)
    corpus = open_db("corpus", tmp_path)
    yield engine, corpus
    engine.close()
    corpus.close()


@pytest.fixture
def make_client(clock: Clock, dbs):
    engine, corpus = dbs

    def build(transport: FakeTransport, *, cached: bool = True) -> SecClient:
        return SecClient(
            AGENT,
            transport=transport,
            cache=SqliteCache(corpus) if cached else None,
            log=SqliteFetchLog(engine),
            limiter=RateLimiter(rate=1e9, clock=clock.mono, sleep=clock.sleep),
            breaker=Breaker(clock=clock.mono),
            now=clock.now,
            sleep=clock.sleep,
        )

    return build
