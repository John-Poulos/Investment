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
from engine.sec.results import Empty, Failed, NotFound, Ok
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


def big_map(n: int = 300, drop=(), reassign=None, extra: int = 0) -> bytes:
    """Synthetic map of n tickers T000.. (CIK 1000+i); 1% of 300 = 3 tickers."""
    reassign = reassign or {}
    rows = [
        [reassign.get(i, 1000 + i), f"CO {i}", f"T{i:03d}", "NYSE"]
        for i in range(n)
        if i not in drop
    ]
    rows += [[5000 + j, f"NEW {j}", f"N{j:03d}", "NYSE"] for j in range(extra)]
    return exchange_file(rows)


def refresh(make_client, engine, clock, exchange: bytes, **kwargs):
    client = make_client(FakeTransport(ticker_routes(exchange=exchange, tickers=b"{}")))
    return refresh_ticker_map(client, engine, clock.now().date(), clock.now(), **kwargs)


def next_day(clock):
    clock.advance(86400)  # past the raw-cache TTL, so new files are fetched


def refresh_outcomes(engine):
    return [
        r[0] for r in engine.execute("SELECT outcome FROM ticker_refresh_log ORDER BY refresh_id")
    ]


def open_holds(engine):
    return engine.execute(
        "SELECT * FROM review_queue WHERE kind = ? AND resolved_at IS NULL", (identity.HOLD_KIND,)
    ).fetchall()


def test_first_refresh_merges_fixture_files(make_client, dbs, clock):
    engine, _ = dbs
    first = refresh_ticker_map(
        make_client(FakeTransport(ticker_routes())), engine, clock.now().date(), clock.now()
    )
    assert isinstance(first, Ok) and first.data.added == 6 and len(first.data.conflicts) == 1
    assert refresh_outcomes(engine) == ["applied"]


def test_refresh_tracks_reassigned_ticker(make_client, dbs, clock):
    engine, _ = dbs
    assert isinstance(refresh(make_client, engine, clock, big_map()), Ok)
    next_day(clock)
    second = refresh(make_client, engine, clock, big_map(reassign={5: 99}))
    assert isinstance(second, Ok)
    assert (second.data.changed, second.data.dropped) == (1, 0)
    history = engine.execute(
        "SELECT cik, valid_from, valid_to FROM ticker WHERE ticker = 'T005' ORDER BY valid_from"
    ).fetchall()
    assert [tuple(r) for r in history] == [
        ("0000001005", "2026-10-07", "2026-10-08"),
        ("0000000099", "2026-10-08", None),
    ]


def test_drops_within_one_percent_apply_and_keep_history(make_client, dbs, clock):
    engine, _ = dbs
    refresh(make_client, engine, clock, big_map())
    next_day(clock)
    result = refresh(make_client, engine, clock, big_map(drop={1, 2, 3}))  # exactly 1%
    assert isinstance(result, Ok) and result.data.dropped == 3
    assert refresh_outcomes(engine) == ["applied", "applied"]

    client = make_client(FakeTransport(ticker_routes(exchange=big_map(drop={1, 2, 3}))))
    looked_up = resolve(client, engine, "t001", clock.now())
    assert isinstance(looked_up, Empty)
    assert [p.path for p in looked_up.paths_checked] == [identity.TICKER_MAP_PATH, "ticker history"]
    assert "0000001001" in looked_up.paths_checked[1].result


def test_drops_over_one_percent_are_held_for_review(make_client, dbs, clock):
    engine, _ = dbs
    refresh(make_client, engine, clock, big_map())
    next_day(clock)
    bad = big_map(drop={1, 2, 3, 4})
    held = refresh(make_client, engine, clock, bad)
    assert isinstance(held, Failed) and "held for owner review" in held.reason
    assert current(engine, "T001") is not None  # nothing changed

    [item] = open_holds(engine)
    payload = json.loads(item["payload"])
    assert payload["dropped"] == ["T001", "T002", "T003", "T004"]
    assert payload["summary"]["stored"] == 300

    next_day(clock)
    refresh(make_client, engine, clock, bad)  # same diff again: no duplicate review item
    assert len(open_holds(engine)) == 1
    assert refresh_outcomes(engine) == ["applied", "held"]

    forced = refresh(make_client, engine, clock, bad, force=True)
    assert isinstance(forced, Ok) and forced.data.dropped == 4
    assert current(engine, "T001") is None
    assert open_holds(engine) == []
    assert refresh_outcomes(engine) == ["applied", "held", "forced"]


def test_count_change_over_ten_percent_is_held(make_client, dbs, clock):
    engine, _ = dbs
    refresh(make_client, engine, clock, big_map())
    next_day(clock)
    assert isinstance(refresh(make_client, engine, clock, big_map(extra=30)), Ok)  # exactly 10%
    next_day(clock)
    held = refresh(make_client, engine, clock, big_map(extra=30 + 34))  # 364 vs 330 stored
    assert isinstance(held, Failed) and "files list 364 tickers vs 330 stored" in held.reason


def test_resolve_during_hold_serves_stored_map_without_rediffing(make_client, dbs, clock):
    engine, _ = dbs
    refresh(make_client, engine, clock, big_map())
    next_day(clock)
    transport = FakeTransport(ticker_routes(exchange=big_map(drop=set(range(10))), tickers=b"{}"))
    client = make_client(transport)

    first = resolve(client, engine, "T050", clock.now())
    assert isinstance(first, Ok) and first.stale and first.fetched_at == "2026-10-07T12:00:00+00:00"
    calls = len(transport.calls)
    second = resolve(client, engine, "T001", clock.now())
    assert isinstance(second, Ok) and second.stale
    assert len(transport.calls) == calls and len(open_holds(engine)) == 1


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


def test_load_entity_missing_submissions_file_is_not_found(make_client, dbs, clock):
    engine, _ = dbs
    url = SUBMISSIONS_URL.format(cik="0000000001")
    result = load_entity(
        make_client(FakeTransport({url: [ok(b"", 404)]})), engine, "1", clock.now()
    )
    assert isinstance(result, NotFound) and result.url == url  # no file, not "no company"
