# ruff: noqa: E501  (fixture rows)
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine import review
from engine.guidance.ledger import scan_all
from engine.store.db import open_db
from engine.ui.app import create_app
from engine.ui.settings import UiSettings
from tests.test_guidance_ledger import CIK, _doc, _filing

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
TEXT = (
    "Outlook\n"
    "We expect third quarter 2026 revenue to be $10-11 billion.\n"
    "We expect third quarter 2026 revenue to be $12-13 billion.\n"
    "We expect third quarter 2026 bookings of $5 billion.\n"
)


def seeded(engine, corpus):
    engine.execute(
        "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES ('ZZZ', ?, '2020-01-01', 't')",
        (CIK,),
    )
    _filing(engine, "c1", "2.02", filed="2026-07-29")
    _doc(corpus, "c1", TEXT)
    scan_all(engine, corpus, NOW)
    return {it.kind: it for it in review.items(engine)}


def test_enter_guidance_stores_owner_row_that_survives_rescan(dbs):
    engine, corpus = dbs
    items = seeded(engine, corpus)
    it = items["guidance_unparsed"]
    warn = review.enter_guidance(
        engine, corpus, it.item_id,
        review.ManualGuidance("operating_income", "unspecified", "FY2026 Q3", "USD", "5", "", "1000000000"),
        "bookings, logged as operating income for the test", "owner", NOW,
    )  # fmt: skip
    assert warn == []  # 5 billion appears in the sentence
    row = engine.execute("SELECT * FROM guidance WHERE source = 'owner'").fetchone()
    assert (row["low"], row["high"], row["kind"], row["parser_version"]) == (
        5e9,
        5e9,
        "point",
        "owner",
    )
    assert row["quote"] == "We expect third quarter 2026 bookings of $5 billion."
    closed = review.get(engine, it.item_id)
    assert (closed.resolution, closed.resolved_by, closed.note) == (
        "entered",
        "owner",
        "bookings, logged as operating income for the test",
    )
    # a forced re-scan keeps the owner row and does not re-open the resolved item
    scan_all(engine, corpus, NOW, force=True)
    assert engine.execute("SELECT count(*) FROM guidance WHERE source = 'owner'").fetchone()[0] == 1
    assert not [i for i in review.items(engine) if i.kind == "guidance_unparsed"]


def test_enter_guidance_validates_and_warns(dbs):
    engine, corpus = dbs
    it = seeded(engine, corpus)["guidance_unparsed"]
    with pytest.raises(review.ReviewError, match="Period must look like"):
        review.enter_guidance(
            engine,
            corpus,
            it.item_id,
            review.ManualGuidance("revenue", "unspecified", "Q3", "USD", "5"),
            "",
            "owner",
            NOW,
        )
    with pytest.raises(review.ReviewError, match="Low is above high"):
        review.enter_guidance(
            engine,
            corpus,
            it.item_id,
            review.ManualGuidance("capex", "unspecified", "FY2026", "USD", "9", "8"),
            "",
            "owner",
            NOW,
        )
    warn = review.enter_guidance(
        engine,
        corpus,
        it.item_id,
        review.ManualGuidance("capex", "unspecified", "FY2026", "USD", "7", "", "1000000000"),
        "",
        "owner",
        NOW,
    )
    assert warn and "does not appear in the sentence" in warn[0]


def test_conflict_keep_other_replaces_value(dbs):
    engine, corpus = dbs
    it = seeded(engine, corpus)["guidance_conflict"]
    assert it.payload["key"] == ["revenue", "unspecified", "FY2026 Q3"]
    review.keep_other(engine, corpus, it.item_id, "second sentence is the update", "owner", NOW)
    row = engine.execute("SELECT low, high FROM guidance WHERE metric = 'revenue'").fetchone()
    assert (row["low"], row["high"]) == (12e9, 13e9)
    assert review.get(engine, it.item_id).resolution == "keep_other"


def test_closing_actions_and_wrong_actions(dbs):
    engine, corpus = dbs
    items = seeded(engine, corpus)
    with pytest.raises(review.ReviewError, match="not a closing action"):
        review.resolve(engine, items["guidance_conflict"].item_id, "acknowledge", "", "owner", NOW)
    review.resolve(engine, items["guidance_conflict"].item_id, "keep_stored", "", "owner", NOW)
    with pytest.raises(review.ReviewError, match="already resolved"):
        review.resolve(engine, items["guidance_conflict"].item_id, "dismiss", "", "owner", NOW)
    assert review.counts(engine) == {"guidance_unparsed": 1}


# --- pages -----------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path):
    data = tmp_path / "data"
    engine = open_db("engine", data)
    corpus = open_db("corpus", data)
    engine.execute(
        "INSERT INTO entity (cik, name, source_ref, fetched_at) VALUES (?, 'Zed Co', 't', 'n')",
        (CIK,),
    )
    seeded(engine, corpus)
    engine.close()
    corpus.close()
    watch = tmp_path / "w.toml"
    watch.write_text('[watchlist]\ntickers = ["ZZZ"]\n', encoding="utf-8")
    with TestClient(create_app(UiSettings(data_dir=data, watchlist=watch))) as c:
        yield c


def test_review_list_item_page_and_actions(client):
    html = client.get("/review").text
    assert "Guidance sentence not parsed" in html and "Guidance stated twice" in html
    assert "bookings of $5 billion" in html
    item_id = int(html.split('href="/review/')[1].split('"')[0])
    page = client.get(f"/review/{item_id}").text
    assert "Resolve" in page and "<mark>" in page
    r = client.post(
        f"/review/{item_id}/dismiss", data={"note": "not guidance"}, follow_redirects=False
    )
    assert r.status_code == 303 and "/review?msg=" in r.headers["location"]
    resolved = client.get("/review?show=resolved").text
    assert "not guidance" in resolved and "owner" in resolved


def test_enter_form_errors_return_to_item(client):
    html = client.get("/review?kind=guidance_unparsed").text
    item_id = int(html.split('href="/review/')[1].split('"')[0])
    r = client.post(
        f"/review/{item_id}/enter",
        data={"metric": "revenue", "period": "next year", "low": "5"},
        follow_redirects=False,
    )
    assert r.headers["location"].startswith(f"/review/{item_id}?error=")
    assert "Period must look like" in client.get(r.headers["location"]).text


def test_review_actions_are_owner_only(client):
    from engine.ui.viewer import Viewer, current_viewer

    item_id = int(client.get("/review").text.split('href="/review/')[1].split('"')[0])
    client.app.dependency_overrides[current_viewer] = lambda: Viewer("guest", "viewer")
    try:
        assert client.post(f"/review/{item_id}/dismiss").status_code == 403
        assert "Only the owner can resolve" in client.get(f"/review/{item_id}").text
    finally:
        client.app.dependency_overrides.clear()


def test_top_bar_links_to_queue(client):
    html = client.get("/c/ZZZ").text
    assert 'href="/review"' in html and "Review 2" in html
