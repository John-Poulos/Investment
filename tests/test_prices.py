# ruff: noqa: E501  (fixture rows)
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from engine.prices.store import bars, refresh_prices, update_symbol
from engine.prices.tiingo import BASE, HOURLY_BUDGET, MIN_INTERVAL_S, TiingoClient, symbol_of
from engine.sec.client import iso
from engine.sec.results import Failed, NotFound, Ok

TOKEN = "secret-token-123"
NOW = datetime(2026, 10, 8, 22, 0, tzinfo=UTC)


def bar(d: str, close: float, div: float = 0.0, split: float = 1.0) -> dict:
    return {
        "date": f"{d}T00:00:00.000Z", "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": 1000, "adjOpen": close, "adjHigh": close + 1,
        "adjLow": close - 1, "adjClose": close, "adjVolume": 1000, "divCash": div,
        "splitFactor": split,
    }  # fmt: skip


class Transport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, url, params, headers):
        self.calls.append((url, dict(params), dict(headers)))
        status, body = self.replies.pop(0)
        return status, json.dumps(body).encode() if not isinstance(body, bytes) else body


def client(engine, replies, sleeps=None):
    t = Transport(replies)
    clock = [0.0]
    s = sleeps if sleeps is not None else []

    def sleep(x):
        s.append(x)
        clock[0] += x

    c = TiingoClient(
        TOKEN, engine, transport=t, now=lambda: NOW, clock=lambda: clock[0], sleep=sleep
    )
    return c, t


def test_key_only_in_header_never_in_logs(dbs):
    engine, _ = dbs
    c, t = client(engine, [(200, [bar("2026-10-07", 10)])])
    res = c.daily("meta", date(2026, 10, 1))
    assert isinstance(res, Ok) and len(res.data) == 1
    url, params, headers = t.calls[0]
    assert url == f"{BASE}/META/prices" and params["startDate"] == "2026-10-01"
    assert headers["Authorization"] == f"Token {TOKEN}"
    logged = engine.execute("SELECT url, outcome, detail FROM fetch_log").fetchall()
    assert all(TOKEN not in (r[0] + (r[2] or "")) for r in logged)
    assert logged[0][1] == "ok" and symbol_of(logged[0][0]) == "META"


def test_requests_are_spaced(dbs):
    engine, _ = dbs
    sleeps = []
    c, _ = client(engine, [(200, []), (200, [])], sleeps)
    c.daily("A")
    c.daily("B")
    assert sleeps == [MIN_INTERVAL_S]


def test_errors_are_typed_not_empty(dbs):
    engine, _ = dbs
    c, _ = client(
        engine, [(404, b'{"detail":"Ticker not found"}'), (429, b"slow down"), (500, b"x")]
    )
    assert isinstance(c.daily("NOPE"), NotFound)
    r = c.daily("META")
    assert isinstance(r, Failed) and r.throttled and r.status == 429
    r = c.daily("META")
    assert isinstance(r, Failed) and not r.throttled


def test_hourly_budget_counts_shared_fetch_log(dbs):
    engine, _ = dbs
    for i in range(HOURLY_BUDGET):
        engine.execute(
            "INSERT INTO fetch_log (url, outcome, status, from_cache, detail, at) VALUES (?, 'ok', 200, 0, '', ?)",
            (f"{BASE}/S{i}/prices", iso(NOW - timedelta(minutes=30))),
        )
    c, t = client(engine, [])
    r = c.daily("META")
    assert isinstance(r, Failed) and r.throttled and r.status is None and "hourly" in r.reason
    assert t.calls == []  # nothing was sent


def test_first_fetch_is_full_history_then_incremental(dbs):
    engine, _ = dbs
    c, t = client(
        engine,
        [
            (200, [bar("2026-10-06", 10), bar("2026-10-07", 11)]),
            (200, [bar("2026-10-07", 11), bar("2026-10-08", 12)]),
        ],
    )
    u = update_symbol(engine, c, "META", "0001326801", NOW)
    assert (u.outcome, u.bars, u.full) == ("ok", 2, True)
    assert t.calls[0][1]["startDate"] == "1962-01-02"
    u = update_symbol(engine, c, "META", "0001326801", NOW)
    assert (u.outcome, u.full) == ("ok", False)
    assert t.calls[1][1]["startDate"] == "2026-10-02"  # 5 days before the last stored bar
    st = engine.execute(
        "SELECT first_date, last_date, bars, last_outcome FROM price_fetch"
    ).fetchone()
    assert tuple(st) == ("2026-10-06", "2026-10-08", 3, "ok")


def test_new_dividend_triggers_full_refetch(dbs):
    engine, _ = dbs
    c, t = client(engine, [
        (200, [bar("2026-10-06", 10)]),
        (200, [bar("2026-10-07", 11, div=0.5)]),          # incremental shows a dividend
        (200, [bar("2026-10-06", 9.5), bar("2026-10-07", 11, div=0.5)]),  # re-adjusted history
    ])  # fmt: skip
    update_symbol(engine, c, "META", None, NOW)
    u = update_symbol(engine, c, "META", None, NOW)
    assert u.full and len(t.calls) == 3 and t.calls[2][1]["startDate"] == "1962-01-02"
    old = engine.execute("SELECT adj_close FROM price_bar WHERE date = '2026-10-06'").fetchone()[0]
    assert old == 9.5


def test_not_found_is_recorded_and_batch_stops_on_throttle(dbs):
    engine, _ = dbs
    c, _ = client(engine, [(404, b"{}"), (429, b"x")])
    rep = refresh_prices(engine, c, {"SPCX": None, "META": None, "NVDA": None}, NOW)
    assert [u.outcome for u in rep.updates] == ["not_found", "throttled"]
    assert rep.skipped == ["NVDA"]
    assert (
        engine.execute("SELECT last_outcome FROM price_fetch WHERE symbol = 'SPCX'").fetchone()[0]
        == "not_found"
    )


def test_bars_weekly_aggregation_markers_and_stale(dbs):
    engine, _ = dbs
    c, _ = client(
        engine,
        [
            (
                200,
                [
                    bar("2026-09-28", 10),
                    bar("2026-09-29", 12),
                    bar("2026-10-02", 11),
                    bar("2026-10-05", 13),
                ],
            )
        ],
    )
    update_symbol(engine, c, "META", None, NOW)
    d = bars(engine, "META", "D", date(2026, 10, 6), ["2026-10-01"])
    assert len(d.bars) == 4 and not d.stale
    assert d.markers == [{"time": "2026-10-02", "text": "ER"}]  # first bar on or after the release
    w = bars(engine, "META", "W", date(2026, 10, 6), ["2026-10-01"])
    assert [b["time"] for b in w.bars] == ["2026-09-28", "2026-10-05"]
    first = w.bars[0]
    assert (first["open"], first["high"], first["low"], first["close"], first["volume"]) == (
        10,
        13,
        9,
        11,
        3000,
    )
    assert w.markers == [{"time": "2026-09-28", "text": "ER"}]
    assert bars(engine, "META", "D", date(2026, 10, 20)).stale  # last bar 15 days old
    assert bars(engine, "NONE", "D", date(2026, 10, 6)).bars == []


def test_missing_days_are_not_filled(dbs):
    engine, _ = dbs
    c, _ = client(engine, [(200, [bar("2026-10-01", 10), bar("2026-10-05", 11)])])
    update_symbol(engine, c, "META", None, NOW)
    assert [b["time"] for b in bars(engine, "META", "D", date(2026, 10, 6)).bars] == [
        "2026-10-01",
        "2026-10-05",
    ]
