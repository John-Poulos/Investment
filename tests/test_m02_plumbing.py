"""M02 part 2: proposals (suppression, weekly cap, overflow), tiers, refresh and prices."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from engine import review
from engine.prices.store import TRACKED_SOFT_CAP, tracked_rotation
from engine.refresh import Config, format_report, run_refresh
from engine.themes import proposals, tiers
from tests.conftest import FakeTransport
from tests.test_refresh import CIK, routes

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)  # a Wednesday


def _resolve(engine, item_id, action, note=""):
    review.m02_action(engine, item_id, action, note, "owner", NOW)


def _item(engine, kind):
    return engine.execute("SELECT * FROM review_queue WHERE kind = ? ORDER BY item_id DESC",
                          (kind,)).fetchone()  # fmt: skip


def test_repeat_suppressed_and_rejection_returns_only_on_material_change(dbs):
    engine, _ = dbs
    p = {"companies": 10, "money_flow": False}
    assert proposals.propose(engine, "m02_phrase", "q:qubit", "rising", p, NOW) == "queued"
    assert proposals.propose(engine, "m02_phrase", "q:qubit", "rising", p, NOW) == "suppressed"
    _resolve(engine, _item(engine, "m02_phrase")["item_id"], "reject", "too narrow")
    same = {"companies": 15, "money_flow": False}
    assert proposals.propose(engine, "m02_phrase", "q:qubit", "x", same, NOW) == "suppressed"
    doubled = {"companies": 20, "money_flow": False}
    assert proposals.propose(engine, "m02_phrase", "q:qubit", "x", doubled, NOW) == "requeued"
    it = review.get(engine, _item(engine, "m02_phrase")["item_id"])
    assert it.payload["earlier"]["note"] == "too narrow" and it.resolved_at is None


def test_accepted_proposal_stays_closed(dbs):
    engine, _ = dbs
    proposals.propose(engine, "m02_input", "NVDA:hbm", "input", {"companies": 1}, NOW)
    _resolve(engine, _item(engine, "m02_input")["item_id"], "confirm")
    big = {"companies": 99, "money_flow": True}
    assert proposals.propose(engine, "m02_input", "NVDA:hbm", "input", big, NOW) == "suppressed"


def test_weekly_cap_overflow_and_flush(dbs):
    engine, _ = dbs
    for i in range(12):
        proposals.propose(engine, "m02_theme", f"t{i}", f"theme {i}", {}, NOW)
    assert proposals.queued_this_week(engine, NOW) == proposals.WEEKLY_CAP
    assert [o["prop_key"] for o in proposals.overflow(engine)] == ["m02_theme:t10", "m02_theme:t11"]
    # Download reminders are not capped.
    assert proposals.propose(engine, "m02_ir_download", "acc1", "download", {}, NOW) == "queued"
    assert proposals.flush_overflow(engine, NOW) == 0  # still this week
    next_week = NOW + timedelta(days=7)
    assert proposals.flush_overflow(engine, next_week) == 2 and proposals.overflow(engine) == []
    item = review.get(engine, _item(engine, "m02_theme")["item_id"])
    assert item.week == "2026-10-12"


def test_flush_takes_waiting_items_in_priority_order(dbs):
    """D-M02-51: grade → money flow → breadth growth, oldest first within a tie."""
    engine, _ = dbs
    for i in range(10):
        proposals.propose(engine, "m02_theme", f"fill{i}", "fill", {}, NOW)
    waiting = [
        ("m02_input", "c-grade", {"money_flow": True}),  # Gemini L0: grade C
        ("m02_phrase", "slow", {"growth_pts": 0.4}),
        ("m02_link", "money", {"money_flow": True}),
        ("m02_phrase", "fast", {"growth_pts": 2.1}),
        ("m02_phrase", "same-later", {"growth_pts": 0.4}),
        ("m02_candidate", "b-grade", {"grade": "B", "money_flow": True}),
    ]
    for i, (kind, key, p) in enumerate(waiting):
        proposals.propose(engine, kind, key, key, p, NOW + timedelta(minutes=i))
    assert len(proposals.overflow(engine)) == 6
    assert proposals.flush_overflow(engine, NOW + timedelta(days=7)) == 6
    order = [r[0] for r in engine.execute(
        "SELECT reason FROM review_queue WHERE created_at >= ? ORDER BY item_id",
        ((NOW + timedelta(days=7)).isoformat(timespec="seconds"),))]  # fmt: skip
    assert order == ["money", "fast", "slow", "same-later", "b-grade", "c-grade"]


def test_candidate_accept_tracks_and_core_is_refused(dbs):
    engine, _ = dbs
    payload = {"ticker": "XSEM", "theme_key": "hbm_packaging", "why": "HBM supplier"}
    proposals.propose(engine, "m02_candidate", CIK, "XSEM proposed", payload, NOW, cik=CIK)
    item_id = _item(engine, "m02_candidate")["item_id"]
    with pytest.raises(review.ReviewError, match="core watchlist"):
        review.m02_action(engine, item_id, "accept", "", "owner", NOW, core={CIK})
    assert review.get(engine, item_id).resolved_at is None  # rolled back, still open
    _resolve(engine, item_id, "accept")
    [m] = tiers.members(engine)
    assert (m.ticker, m.tier, m.theme_key) == ("XSEM", "tracked", "hbm_packaging")


def test_promotion_suggestion_and_still_track_cycle(dbs):
    engine, _ = dbs
    tiers.add_tracked(engine, CIK, "XSEM", reason="r", theme_key=None, by="owner", now=NOW)
    assert proposals.queue_still_track(engine, NOW + timedelta(days=100)) == 0
    later = NOW + timedelta(days=400)
    assert proposals.queue_still_track(engine, later) == 1
    assert proposals.queue_still_track(engine, later) == 0  # open item suppresses
    review.m02_action(engine, _item(engine, "m02_still_track")["item_id"], "keep", "", "owner",
                      later)  # fmt: skip
    assert tiers.member(engine, CIK).last_evidence_at.startswith("2027-11")
    assert proposals.suggest_promotion(engine, CIK, "confirmed supplier of NVDA", "link",
                                       later) == "queued"  # fmt: skip
    review.m02_action(engine, _item(engine, "m02_promote")["item_id"], "promote", "", "owner",
                      later)  # fmt: skip
    assert tiers.member(engine, CIK).tier == "promoted"
    tiers.remove(engine, CIK, "owner", later)
    assert tiers.members(engine) == []


def test_tracked_rotation_picks_stalest_third_and_caps():
    import sqlite3

    engine = sqlite3.connect(":memory:")
    engine.row_factory = sqlite3.Row
    engine.execute("CREATE TABLE price_fetch (symbol TEXT, last_fetched_at TEXT)")
    engine.executemany("INSERT INTO price_fetch VALUES (?, ?)",
                       [("A", "2026-10-06"), ("B", "2026-10-01"), ("C", "2026-10-05")])  # fmt: skip
    today, over = tracked_rotation(engine, {s: None for s in "ABCDEF"})
    assert sorted(today) == ["D", "E"]  # never fetched first; ceil(6 / 3) = 2
    many = {f"S{i:03d}": None for i in range(TRACKED_SOFT_CAP + 5)}
    today, over = tracked_rotation(engine, many)
    assert len(today) == TRACKED_SOFT_CAP // 3 and len(over) == 5


def test_refresh_gives_tracked_names_a_light_sync(make_client, dbs, clock):
    engine, corpus = dbs
    tiers.add_tracked(engine, CIK, "XSEM", reason="r", theme_key=None, by="owner", now=NOW)
    cfg = Config(tickers=(), earnings_8k=0, latest_annual=False, latest_quarterly=False)
    t = FakeTransport(routes())
    report = run_refresh(make_client(t), engine, corpus, cfg, clock.now())
    [c] = report.companies
    assert (c.ticker, c.tier, c.failures) == ("XSEM", "tracked", [])
    assert c.insider_rows == 0 and c.documents == 2  # no Form 4s; earnings 8-K + EX-99.1
    assert not any("form4" in url for url, _, _ in t.calls)
    assert report.tracked == {"XSEM": CIK}
    assert "tracked (filings, XBRL, earnings releases): XSEM" in format_report(report)
    # Second run: already synced and nothing new → not processed again.
    clock.advance(3600)
    again = run_refresh(make_client(FakeTransport(routes())), engine, corpus, cfg, clock.now())
    assert [c.ticker for c in again.companies] == ["XSEM"]  # day re-checked: still matched
    tiers.promote(engine, CIK, "owner", NOW)
    full = run_refresh(make_client(FakeTransport(routes())), engine, corpus, cfg, clock.now())
    [c] = full.companies
    assert c.tier == "promoted" and c.backfilled  # first full run backfills
    assert "XSEM" in full.watchlist
