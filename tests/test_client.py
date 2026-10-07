from __future__ import annotations

import pytest
import requests

from engine.sec.client import (
    BREAKER_SECONDS,
    Breaker,
    RateLimiter,
    UserAgentError,
    cache_key,
    is_throttle,
    validate_user_agent,
)
from engine.sec.results import Empty, Failed, NotFound, Ok
from tests.conftest import AGENT, FakeTransport, fixture_bytes, ok

URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
DAY = 86400


@pytest.mark.parametrize(
    "agent",
    [None, "", "noemail", "a@b.com", "PharmaAgent contact@pharmaagent.com", "Jane x@example.com"],
)
def test_user_agent_rejected(agent):
    with pytest.raises(UserAgentError):
        validate_user_agent(agent)


def test_user_agent_accepted():
    assert validate_user_agent(f"  {AGENT} ") == AGENT


def test_cache_key_ignores_param_order():
    assert cache_key(URL, {"b": 2, "a": 1}) == cache_key(URL, {"a": 1, "b": 2})
    assert cache_key(URL, None) == URL


def test_ok_json_then_cache_hit(make_client, dbs):
    transport = FakeTransport({URL: [ok(b'{"x": 1}')]})
    client = make_client(transport)

    first = client.get_json(URL, ttl_s=DAY)
    second = client.get_json(URL, ttl_s=DAY)

    assert isinstance(first, Ok) and first.data == {"x": 1} and not first.from_cache
    assert isinstance(second, Ok) and second.data == {"x": 1} and second.from_cache
    assert len(transport.calls) == 1
    assert transport.calls[0][2]["User-Agent"] == AGENT
    engine, _ = dbs
    outcomes = [r["outcome"] for r in engine.execute("SELECT outcome FROM fetch_log")]
    assert outcomes == ["ok", "ok"]


def test_cache_expires(make_client, clock):
    transport = FakeTransport({URL: [ok(b"{}")]})
    client = make_client(transport)
    client.get_json(URL, ttl_s=60)
    clock.advance(61)
    client.get_json(URL, ttl_s=60)
    assert len(transport.calls) == 2


def test_404_is_not_found_and_cached_briefly(make_client, clock, dbs):
    transport = FakeTransport({URL: [ok(b"not found", status=404)]})
    client = make_client(transport)

    first = client.get_json(URL, ttl_s=30 * DAY)
    again = client.get_json(URL, ttl_s=30 * DAY)
    assert isinstance(first, NotFound) and first.url == URL and not first.from_cache
    assert isinstance(again, NotFound) and again.from_cache
    assert not isinstance(first, Empty)  # a missing file is never "no data"
    assert len(transport.calls) == 1
    engine, corpus = dbs
    assert {r[0] for r in engine.execute("SELECT outcome FROM fetch_log")} == {"not_found"}
    assert corpus.execute("SELECT outcome FROM http_cache").fetchone()[0] == "not_found"

    clock.advance(7 * 3600)  # past the short negative TTL, well inside the 30-day TTL
    client.get_json(URL, ttl_s=30 * DAY)
    assert len(transport.calls) == 2


def test_5xx_retries_then_succeeds(make_client, clock):
    transport = FakeTransport({URL: [ok(b"", 500), ok(b"", 503), ok(b'{"ok": true}')]})
    result = make_client(transport).get_json(URL, ttl_s=DAY)
    assert isinstance(result, Ok) and result.data == {"ok": True}
    assert len(transport.calls) == 3
    assert len(clock.sleeps) == 2


def test_5xx_exhausted_is_failure_and_not_cached(make_client):
    transport = FakeTransport({URL: [ok(b"", 500)]})
    client = make_client(transport)
    result = client.get_json(URL, ttl_s=DAY)
    assert isinstance(result, Failed) and result.status == 500
    calls = len(transport.calls)
    client.get_json(URL, ttl_s=DAY)
    assert len(transport.calls) == calls * 2  # failure was not cached


def test_network_error_retries_then_fails(make_client):
    transport = FakeTransport({URL: [requests.ConnectionError("down")]})
    result = make_client(transport).get_json(URL, ttl_s=DAY)
    assert isinstance(result, Failed) and "network error" in result.reason


def test_other_4xx_fails_without_retry(make_client):
    transport = FakeTransport({URL: [ok(b"", 400)]})
    result = make_client(transport).get_json(URL, ttl_s=DAY)
    assert isinstance(result, Failed) and result.status == 400 and not result.throttled
    assert len(transport.calls) == 1


def test_invalid_json_is_failure(make_client):
    transport = FakeTransport({URL: [ok(b"<html>")]})
    assert isinstance(make_client(transport).get_json(URL, ttl_s=DAY), Failed)


@pytest.mark.parametrize("status", [403, 429])
def test_throttle_status_trips_breaker(make_client, clock, status):
    other = "https://www.sec.gov/files/company_tickers.json"
    transport = FakeTransport({URL: [ok(b"", status)], other: [ok(b"{}")]})
    client = make_client(transport)

    first = client.get_json(URL, ttl_s=DAY)
    assert isinstance(first, Failed) and first.throttled
    blocked = client.get_json(other, ttl_s=DAY)  # every SEC call pauses, not just this URL
    assert isinstance(blocked, Failed) and blocked.throttled
    assert len(transport.calls) == 1

    clock.advance(BREAKER_SECONDS + 1)
    assert isinstance(client.get_json(other, ttl_s=DAY), Ok)


def test_throttle_page_under_200_trips_breaker(make_client):
    page = fixture_bytes("sec/throttle_page.html")
    transport = FakeTransport({URL: [ok(page)]})
    result = make_client(transport).get_bytes(URL, ttl_s=DAY)
    assert isinstance(result, Failed) and result.throttled


def test_retry_after_extends_breaker(make_client, clock):
    transport = FakeTransport({URL: [ok(b"", 429, **{"Retry-After": "1800"}), ok(b"{}")]})
    client = make_client(transport)
    client.get_bytes(URL, ttl_s=DAY)
    clock.advance(BREAKER_SECONDS + 1)
    still = client.get_bytes(URL, ttl_s=DAY)
    assert isinstance(still, Failed) and still.throttled and len(transport.calls) == 1
    clock.advance(1800)
    assert isinstance(client.get_bytes(URL, ttl_s=DAY), Ok)


def test_is_throttle():
    assert is_throttle(429, b"")
    assert is_throttle(200, b"...Request Rate Threshold Exceeded...")
    assert not is_throttle(200, b'{"name": "Apple"}')


def test_rate_limiter_spaces_calls(clock):
    limiter = RateLimiter(rate=8, clock=clock.mono, sleep=lambda s: clock.sleeps.append(s))
    for _ in range(3):
        limiter.acquire()
    assert clock.sleeps == pytest.approx([0.125, 0.25])


def test_breaker_remaining(clock):
    breaker = Breaker(clock=clock.mono)
    assert breaker.remaining() == 0
    breaker.trip(600)
    clock.advance(100)
    assert breaker.remaining() == pytest.approx(500)
