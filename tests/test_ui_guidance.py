# ruff: noqa: E501  (fixture rows)
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.guidance.ledger import scan_all
from engine.llm.provider import FakeProvider
from engine.sec.sections import resplit
from engine.store.db import open_db
from engine.ui.app import create_app
from engine.ui.settings import UiSettings
from tests.test_llm import APR, CIK, JAN, REASON_QUOTE

ACC_APR = "0001628280-26-028364"


@pytest.fixture
def setup(tmp_path: Path, clock):
    data = tmp_path / "data"
    engine = open_db("engine", data)
    corpus = open_db("corpus", data)
    engine.execute(
        "INSERT INTO entity (cik, name, source_ref, fetched_at) VALUES (?, 'Meta Platforms, Inc.', 't', 'n')",
        (CIK,),
    )
    engine.execute(
        "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES ('META', ?, '2020-01-01', 't')",
        (CIK,),
    )
    for acc, filed, text in (
        ("0001628280-26-003832", "2026-01-28", JAN),
        (ACC_APR, "2026-04-29", APR),
    ):
        engine.execute(
            "INSERT INTO filing (accession, cik, form, filed, items, ingested_at) VALUES (?, ?, '8-K', ?, '2.02,9.01', 'n')",
            (acc, CIK, filed),
        )
        doc_id = corpus.execute(
            "INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, fetched_at) VALUES (?, ?, 'ex991.htm', 'EX-99.1', ?, ?, 'sha', 'n')",
            (acc, CIK, f"https://x/{acc}", text),
        ).lastrowid
        resplit(corpus, doc_id, clock.now())
    scan_all(engine, corpus, clock.now())
    engine.close()
    corpus.close()
    watch = tmp_path / "watch.toml"
    watch.write_text('[watchlist]\ntickers = ["META"]\n', encoding="utf-8")
    fake = FakeProvider([])
    app = create_app(UiSettings(data_dir=data, watchlist=watch, llm_factory=lambda: fake))
    with TestClient(app) as c:
        yield c, fake


def reply(label: str) -> str:
    return json.dumps(
        {
            "reasons": [
                {
                    "change_id": "C1",
                    "reason_stated": True,
                    "summary": "Higher expected component pricing and more data center capacity.",
                    "quotes": [{"passage_id": label, "quote": REASON_QUOTE}],
                }
            ]
        }
    )


def test_guidance_tab_shows_ledger_changes_and_source_links(setup):
    client, _ = setup
    html = client.get("/c/META?tab=guidance").text
    assert "FY2026 · capex" in html and "$125 billion – $145 billion" in html
    assert "raised" in html and "first stated" in html
    assert f"/source/{ACC_APR}/ex991.htm?start=" in html and "sha=sha" in html
    assert "not analyzed" in html and "Analyze reasons" in html
    assert "(unspecified)" not in html


def test_analyze_page_shows_what_is_sent_and_cost_without_calling(setup):
    client, fake = setup
    html = client.get("/c/META/analyze/guidance-reasons").text
    assert "C1: capex for FY2026: raised" in html and "gemini-3.1-flash-lite" in html
    assert "Run with Gemini" in html
    assert fake.sent == []  # viewing the page never calls Gemini


def test_run_stores_verified_reason_shown_in_tab_then_cached(setup):
    client, fake = setup
    fake.replies.append(reply("P1"))
    r = client.post("/c/META/analyze/guidance-reasons?rerun=0", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("msg=analyzed")
    html = client.get("/c/META?tab=guidance&msg=analyzed").text
    assert "Higher expected component pricing" in html and REASON_QUOTE in html
    assert f"/doc/{ACC_APR}?file=ex991.htm&start=" in html  # quote opens the reader
    assert "1 verified" in html
    # identical request: stored result, no second call
    r = client.post("/c/META/analyze/guidance-reasons?rerun=0", follow_redirects=False)
    assert r.headers["location"].endswith("msg=stored-result") and len(fake.sent) == 1
    assert "already stored" in client.get("/c/META/analyze/guidance-reasons").text


def test_failed_call_is_reported_not_stored_as_fact(setup):
    client, fake = setup
    fake.replies.append("not json")
    r = client.post("/c/META/analyze/guidance-reasons?rerun=0", follow_redirects=False)
    assert "msg=llm-error" in r.headers["location"]
    html = client.get(r.headers["location"]).text
    assert "did not complete" in html and "Higher expected" not in html


def test_analyze_is_owner_only(setup):
    from engine.ui.viewer import Viewer, current_viewer

    client, fake = setup
    client.app.dependency_overrides[current_viewer] = lambda: Viewer("guest", "viewer")
    try:
        assert client.post("/c/META/analyze/guidance-reasons").status_code == 403
        assert (
            "Only the owner can start a Gemini run."
            in client.get("/c/META/analyze/guidance-reasons").text
        )
    finally:
        client.app.dependency_overrides.clear()
    assert fake.sent == []
