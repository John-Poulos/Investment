from __future__ import annotations

import json

import pytest

from engine.sec.frames import (
    FRAMES_URL,
    calendar_quarter,
    concept_frame,
    fetch_frame,
    frame_name,
    peer_stats,
    previous_quarters,
    robust_z,
    series_values,
    series_yoy,
    ttm_frame,
    values_of,
    yoy_growth,
)
from engine.sec.results import Failed, NotFound, Ok
from engine.sec.xbrl_facts import CONCEPT_BY_NAME
from tests.conftest import FakeTransport, ok

A, B, C = "0000000001", "0000000002", "0000000003"
REVENUE_TAGS = CONCEPT_BY_NAME["revenue"].tags
TOP, SECOND = REVENUE_TAGS[0], REVENUE_TAGS[1]


def url(tag, period, unit="USD"):
    taxonomy, name = tag
    return FRAMES_URL.format(taxonomy=taxonomy, tag=name, unit=unit, period=period)


def frame(entries):
    data = [
        {"accn": f"acc-{cik}", "cik": int(cik), "entityName": f"Co {cik}", "loc": "US-CA",
         "start": "2025-03-30", "end": "2025-06-28", "val": val}
        for cik, val in entries.items()
    ]  # fmt: skip
    return ok(json.dumps({"taxonomy": "us-gaap", "uom": "USD", "pts": len(data), "data": data})
              .encode())  # fmt: skip


def revenue_routes(period, top, second=None, failing=()):
    """Routes for every revenue tag in one period; unlisted tags return 404."""
    routes = {}
    for tag in REVENUE_TAGS:
        if tag in failing:
            routes[url(tag, period)] = [ok(b"", 503)]
        elif tag == TOP:
            routes[url(tag, period)] = [frame(top)]
        elif tag == SECOND and second is not None:
            routes[url(tag, period)] = [frame(second)]
        else:
            routes[url(tag, period)] = [ok(b"", 404)]
    return routes


def test_frame_names():
    assert frame_name(2025, 2) == "CY2025Q2"
    assert frame_name(2025) == "CY2025"
    assert frame_name(2025, 4, instant=True) == "CY2025Q4I"
    with pytest.raises(ValueError):
        frame_name(2025, instant=True)


def test_calendar_quarter_maps_fiscal_periods():
    assert calendar_quarter("2025-03-30", "2025-06-28") == (2025, 2)  # Apple fiscal Q3
    assert calendar_quarter("2024-09-29", "2024-12-28") == (2024, 4)  # Apple fiscal Q1
    assert calendar_quarter(None, "2025-06-28") == (2025, 2)


def test_previous_quarters_cross_year():
    assert previous_quarters(2025, 2, 4) == [(2024, 3), (2024, 4), (2025, 1), (2025, 2)]


def test_concept_frame_uses_tag_priority(make_client, dbs, clock):
    engine, _ = dbs
    routes = revenue_routes("CY2025Q2", top={A: 100, B: 200}, second={B: 999, C: 300})
    result = concept_frame(make_client(FakeTransport(routes)), engine, "revenue", "CY2025Q2",
                           clock.now())  # fmt: skip
    assert isinstance(result, Ok) and result.data.complete
    v = result.data.values
    assert (v[A].value, v[B].value, v[C].value) == (100, 200, 300)  # B keeps the top tag's value
    assert v[C].tag == f"{SECOND[0]}:{SECOND[1]}"  # fallback tag stays visible
    assert v[A].accession == f"acc-{A}" and v[A].end == "2025-06-28"
    assert len(result.data.tags_missing) == len(REVENUE_TAGS) - 2


def test_frames_reused_within_30_days_including_404s(make_client, dbs, clock):
    engine, _ = dbs
    transport = FakeTransport(revenue_routes("CY2025Q2", top={A: 100}))
    client = make_client(transport)
    concept_frame(client, engine, "revenue", "CY2025Q2", clock.now())
    calls = len(transport.calls)
    clock.advance(10 * 86400)
    again = concept_frame(client, engine, "revenue", "CY2025Q2", clock.now())
    assert isinstance(again, Ok) and again.data.values[A].value == 100
    assert len(transport.calls) == calls
    clock.advance(25 * 86400)
    concept_frame(client, engine, "revenue", "CY2025Q2", clock.now())
    assert len(transport.calls) == 2 * calls


def test_refetch_replaces_frame_rows(make_client, dbs, clock):
    engine, _ = dbs
    tag_url = url(TOP, "CY2025Q2")
    transport = FakeTransport({tag_url: [frame({A: 100, B: 5}), frame({A: 110})]})
    client = make_client(transport)
    fetch_frame(client, engine, TOP[0], TOP[1], "USD", "CY2025Q2", clock.now())
    clock.advance(86400)
    second = fetch_frame(client, engine, TOP[0], TOP[1], "USD", "CY2025Q2", clock.now(),
                         force=True)  # fmt: skip
    assert isinstance(second, Ok) and second.data == 1
    rows = engine.execute("SELECT cik, value FROM frame_value").fetchall()
    assert [tuple(r) for r in rows] == [(A, 110)]


def test_failed_tag_marks_frame_incomplete(make_client, dbs, clock):
    engine, _ = dbs
    routes = revenue_routes("CY2025Q2", top={A: 100}, failing=(SECOND,))
    result = concept_frame(make_client(FakeTransport(routes)), engine, "revenue", "CY2025Q2",
                           clock.now())  # fmt: skip
    assert isinstance(result, Ok) and not result.data.complete
    assert "HTTP 503" in result.data.tags_failed[0]


def test_wrong_frame_kind_fails(make_client, dbs, clock):
    engine, _ = dbs
    client = make_client(FakeTransport({}))
    assert isinstance(concept_frame(client, engine, "revenue", "CY2025Q2I", clock.now()), Failed)
    assert isinstance(concept_frame(client, engine, "cash", "CY2025Q2", clock.now()), Failed)


def test_ttm_needs_all_four_quarters(make_client, dbs, clock):
    engine, _ = dbs
    routes = {}
    for i, (y, q) in enumerate(previous_quarters(2025, 2, 4)):
        entries = {A: 10 + i, B: 100}
        if i == 1:
            entries.pop(B)  # B misses one quarter → no TTM for B
        routes |= revenue_routes(frame_name(y, q), top=entries)
    result = ttm_frame(make_client(FakeTransport(routes)), engine, "revenue", 2025, 2, clock.now())
    assert isinstance(result, Ok)
    assert values_of(result.data) == {A: 10 + 11 + 12 + 13}
    assert result.data.period == "TTM CY2025Q2"


def test_ttm_refused_for_non_additive(make_client, dbs, clock):
    engine, _ = dbs
    client = make_client(FakeTransport({}))
    assert isinstance(ttm_frame(client, engine, "eps_diluted", 2025, 2, clock.now()), Failed)


def test_peer_stats_and_robust_z():
    values = {A: 10.0, B: 20.0, C: 30.0, "0000000004": 40.0, "0000000005": 50.0}
    peers = [*values, "0000000009"]  # last peer has no value
    stats = peer_stats(values, peers)
    assert (stats.n, stats.median, stats.q1, stats.q3) == (5, 30.0, 20.0, 40.0)
    assert stats.missing == ("0000000009",) and not stats.low_confidence
    assert robust_z(57.0, stats) == pytest.approx((57 - 30) / (20 / 1.35))
    assert robust_z(None, stats) is None


def test_peer_stats_low_confidence_and_zero_spread():
    stats = peer_stats({A: 5.0, B: 5.0}, [A, B, C])
    assert stats.low_confidence and stats.robust_sd is None and stats.missing == (C,)
    assert robust_z(6.0, stats) is None  # no spread: z undefined, not infinite
    assert peer_stats({}, [A]).median is None


def test_yoy_growth_skips_missing_and_non_positive(make_client, dbs, clock):
    engine, _ = dbs
    now = concept_frame(
        make_client(FakeTransport(revenue_routes("CY2025Q2", top={A: 120, B: 50, C: 10}))),
        engine, "revenue", "CY2025Q2", clock.now(),
    )  # fmt: skip
    before = concept_frame(
        make_client(FakeTransport(revenue_routes("CY2024Q2", top={A: 100, B: -5}))),
        engine, "revenue", "CY2024Q2", clock.now(),
    )  # fmt: skip
    assert isinstance(now, Ok) and isinstance(before, Ok)
    assert yoy_growth(now.data, before.data) == {A: pytest.approx(0.2)}


def test_frame_404_is_not_found(make_client, dbs, clock):
    engine, _ = dbs
    transport = FakeTransport({url(TOP, "CY2010Q1"): [ok(b"", 404)]})
    result = fetch_frame(make_client(transport), engine, TOP[0], TOP[1], "USD", "CY2010Q1",
                         clock.now())  # fmt: skip
    assert isinstance(result, NotFound)


def put_series(engine, cik, end, value, ptype="TTM", concept="revenue"):
    engine.execute(
        "INSERT INTO series (cik, concept, period_end, period_type, period_start, unit, "
        "first_value, first_accession, first_filed, latest_value, latest_accession, latest_filed, "
        "method, parser_version) VALUES (?, ?, ?, ?, NULL, 'USD', ?, 'a1', 'f1', ?, 'a2', 'f2', "
        "'TTM sum of quarters', 'facts-1')",
        (cik, concept, end, ptype, value - 1, value),
    )


def test_series_values_pick_closest_period_within_tolerance(dbs):
    engine, _ = dbs
    put_series(engine, A, "2025-06-28", 400)  # off-calendar fiscal quarter end
    put_series(engine, A, "2025-03-29", 380)
    put_series(engine, B, "2025-06-30", 900)
    put_series(engine, C, "2025-01-31", 50)  # too far from the target: missing, not zero
    got = series_values(engine, [A, B, C], "revenue", "TTM", "2025-06-30")
    assert {c: v.value for c, v in got.items()} == {A: 400, B: 900}
    assert got[A].end == "2025-06-28" and got[A].accession == "a2"
    first = series_values(engine, [A], "revenue", "TTM", "2025-06-30", version="first")
    assert first[A].value == 399


def test_series_yoy(dbs):
    engine, _ = dbs
    put_series(engine, A, "2025-06-28", 120)
    put_series(engine, A, "2024-06-29", 100)
    put_series(engine, B, "2025-06-30", 50)
    put_series(engine, B, "2024-06-30", -10)  # non-positive prior: no growth
    put_series(engine, C, "2025-06-30", 70)  # no prior year: no growth
    growth = series_yoy(engine, [A, B, C], "revenue", "2025-06-30")
    assert growth == {A: pytest.approx(0.2)}
