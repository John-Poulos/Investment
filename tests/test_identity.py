from __future__ import annotations

import json
from datetime import timedelta

import pytest

from engine.sec import identity
from engine.sec.identity import (
    EXCHANGE_URL,
    SUBMISSIONS_URL,
    TICKERS_URL,
    load_entity,
    normalize_cik,
    normalize_ticker,
    parse_ticker_files,
    refresh_ticker_map,
    resolve,
)
from engine.sec.results import Empty, Failed, Ok
from tests.conftest import FakeTransport, fixture_bytes, ok

APPLE = "0000320193"
APPLE_URL = SUBMISSIONS_URL.format(cik=APPLE)


def ticker_routes(exchange: bytes | None = None, tickers: bytes | None = None):
    return {
        EXCHANGE_URL: [ok(exchange or fixture_bytes("sec/company_tickers_exchange.json"))],
        TICKERS_URL: [ok(tickers or fixture_bytes("sec/company_tickers.json"))],
    }


def exchange_file(rows: list[list]) -> bytes:
    return json.dumps({"fields": ["cik", "name", "ticker", "exchange"], "data": rows}).encode()


def current(conn, ticker):
    return conn.execute(
        "SELECT cik FROM ticker WHERE ticker = ? AND valid_to IS NULL", (ticker,)
    ).fetchone()


@pytest.mark.parametrize(("raw", "norm"), [("brk.b", "BRK-B"), (" BRK/B ", "BRK-B"), ("mu", "MU")])
def test_normalize_ticker(raw, norm):
    assert normalize_ticker(raw) == norm


def test_normalize_cik():
    assert normalize_cik("320193") == APPLE
    assert normalize_cik(320193) == APPLE
    assert normalize_cik("AAPL") is None
    assert normalize_cik("12345678901") is None


def test_parse_merges_files_and_reports_conflicts():
    rows, conflicts = parse_ticker_files(
        json.loads(fixture_bytes("sec/company_tickers_exchange.json")),
        json.loads(fixture_bytes("sec/company_tickers.json")),
    )
    assert rows["AAPL"].cik == APPLE and rows["AAPL"].exchange == "Nasdaq"
    assert rows["AVGO"].source == "company_tickers.json"  # only in the second file
    assert rows["MU"].cik == "0000723125"  # first seen wins
    assert len(conflicts) == 1 and conflicts[0].startswith("MU:")


def test_parse_rejects_changed_layout():
    with pytest.raises(ValueError, match="fields changed"):
        parse_ticker_files({"fields": ["cik", "ticker"], "data": []}, {})


def test_refresh_tracks_history(make_client, dbs, clock):
    engine, _ = dbs
    first = refresh_ticker_map(
        make_client(FakeTransport(ticker_routes())), engine, clock.now().date(), clock.now()
    )
    assert isinstance(first, Ok) and first.data.added == 6 and len(first.data.conflicts) == 1

    clock.advance(86400)
    moved = exchange_file(
        [
            [320193, "Apple Inc.", "AAPL", "Nasdaq"],
            [1045810, "NVIDIA CORP", "NVDA", "Nasdaq"],
            [723125, "MICRON TECHNOLOGY INC", "MU", "Nasdaq"],
            [1067983, "BERKSHIRE HATHAWAY INC", "BRK-B", "NYSE"],
            [99, "NEW HOLDER OF TICKER", "INTC", "Nasdaq"],  # ticker reassigned
        ]
    )
    second = refresh_ticker_map(
        make_client(FakeTransport(ticker_routes(exchange=moved))),
        engine,
        clock.now().date(),
        clock.now(),
    )
    assert isinstance(second, Ok)
    assert second.data.changed == 1 and second.data.closed == 0
    assert current(engine, "INTC")["cik"] == "0000000099"
    history = engine.execute(
        "SELECT cik, valid_from, valid_to FROM ticker WHERE ticker = 'INTC' ORDER BY valid_from"
    ).fetchall()
    assert [tuple(r) for r in history] == [
        ("0000050863", "2026-10-07", "2026-10-08"),
        ("0000000099", "2026-10-08", None),
    ]


def test_refresh_closes_dropped_ticker_and_resolve_reports_history(make_client, dbs, clock):
    engine, _ = dbs
    refresh_ticker_map(
        make_client(FakeTransport(ticker_routes())), engine, clock.now().date(), clock.now()
    )
    clock.advance(86400)
    without_intc = exchange_file(
        [
            [320193, "Apple Inc.", "AAPL", "Nasdaq"],
            [1045810, "NVIDIA CORP", "NVDA", "Nasdaq"],
            [723125, "MICRON TECHNOLOGY INC", "MU", "Nasdaq"],
            [1067983, "BERKSHIRE HATHAWAY INC", "BRK-B", "NYSE"],
        ]
    )
    client = make_client(FakeTransport(ticker_routes(exchange=without_intc)))
    result = refresh_ticker_map(client, engine, clock.now().date(), clock.now())
    assert isinstance(result, Ok) and result.data.closed == 1

    looked_up = resolve(client, engine, "intc", clock.now())
    assert isinstance(looked_up, Empty)
    assert [p.path for p in looked_up.paths_checked] == [identity.TICKER_MAP_PATH, "ticker history"]
    assert "0000050863" in looked_up.paths_checked[1].result


def test_refresh_refuses_shrunken_file(make_client, dbs, clock):
    engine, _ = dbs
    refresh_ticker_map(
        make_client(FakeTransport(ticker_routes())), engine, clock.now().date(), clock.now()
    )
    clock.advance(86400)  # past the raw-cache TTL, so the new files are fetched
    tiny = exchange_file([[320193, "Apple Inc.", "AAPL", "Nasdaq"]])
    result = refresh_ticker_map(
        make_client(FakeTransport(ticker_routes(exchange=tiny, tickers=b"{}"))),
        engine,
        clock.now().date(),
        clock.now(),
    )
    assert isinstance(result, Failed) and "refusing" in result.reason
    assert current(engine, "NVDA") is not None


def test_resolve_numeric_and_ticker(make_client, dbs, clock):
    engine, _ = dbs
    transport = FakeTransport(ticker_routes())
    client = make_client(transport)

    assert resolve(client, engine, "320193", clock.now()).data == APPLE
    assert transport.calls == []  # numeric CIK needs no lookup

    brk = resolve(client, engine, "brk.b", clock.now())
    assert isinstance(brk, Ok) and brk.data == "0001067983" and not brk.stale
    resolve(client, engine, "NVDA", clock.now())
    assert len(transport.calls) == 2  # ticker map fetched once (two files)


def test_resolve_serves_stale_when_refresh_fails(make_client, dbs, clock):
    engine, _ = dbs
    refresh_ticker_map(
        make_client(FakeTransport(ticker_routes())), engine, clock.now().date(), clock.now()
    )
    clock.advance(2 * 86400)
    down = FakeTransport({EXCHANGE_URL: [ok(b"", 503)], TICKERS_URL: [ok(b"", 503)]})
    result = resolve(make_client(down), engine, "AAPL", clock.now())
    assert isinstance(result, Ok) and result.data == APPLE and result.stale


def test_resolve_fails_without_any_ticker_map(make_client, dbs, clock):
    engine, _ = dbs
    down = FakeTransport({EXCHANGE_URL: [ok(b"", 503)], TICKERS_URL: [ok(b"", 503)]})
    result = resolve(make_client(down), engine, "AAPL", clock.now())
    assert isinstance(result, Failed)  # a failure, never "no such ticker"


def test_load_entity_stores_and_reuses(make_client, dbs, clock):
    engine, _ = dbs
    transport = FakeTransport(
        {APPLE_URL: [ok(fixture_bytes("sec/submissions_CIK0000320193.json"))]}
    )
    client = make_client(transport, cached=False)

    first = load_entity(client, engine, "320193", clock.now())
    assert isinstance(first, Ok)
    assert first.data.name == "Apple Inc." and first.data.sic == "3571"
    assert first.data.fiscal_year_end == "0926" and first.data.tickers == ("AAPL",)

    clock.advance(3600)
    again = load_entity(client, engine, APPLE, clock.now())
    assert isinstance(again, Ok) and again.from_cache and len(transport.calls) == 1


def test_load_entity_stale_on_failure(make_client, dbs, clock):
    engine, _ = dbs
    transport = FakeTransport(
        {APPLE_URL: [ok(fixture_bytes("sec/submissions_CIK0000320193.json")), ok(b"", 503)]}
    )
    client = make_client(transport, cached=False)
    load_entity(client, engine, APPLE, clock.now())
    clock.advance(int(timedelta(days=2).total_seconds()))
    result = load_entity(client, engine, APPLE, clock.now())
    assert isinstance(result, Ok) and result.stale and result.data.name == "Apple Inc."


def test_load_entity_unknown_cik_is_empty(make_client, dbs, clock):
    engine, _ = dbs
    url = SUBMISSIONS_URL.format(cik="0000000001")
    result = load_entity(
        make_client(FakeTransport({url: [ok(b"", 404)]})), engine, "1", clock.now()
    )
    assert isinstance(result, Empty)
