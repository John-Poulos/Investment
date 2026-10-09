# ruff: noqa: E501  (fixture rows)
"""Themes screens (M02 part 1): list, detail, filers, company tab."""

from __future__ import annotations

import pytest

from engine.store.db import open_db
from tests.test_ui import CIK, client  # noqa: F401  (fixture)

T = "2026-10-09T00:00:00+00:00"


@pytest.fixture
def themed(client):  # noqa: F811
    engine = open_db("engine", client.app.state.settings.data_dir)
    engine.execute("INSERT INTO theme VALUES (1, 'ai', 'AI infrastructure', 'seed', 'active', ?, ?)",
                   (T, T))  # fmt: skip
    engine.execute("INSERT INTO theme_phrase (theme_id, phrase, source, status, discovered_at, "
                   "updated_at) VALUES (1, '\"generative AI\"', 'seed', 'active', ?, ?)", (T, T))  # fmt: skip
    engine.execute("INSERT INTO theme_company VALUES (1, 'META', 'seed', 'active', NULL, ?, ?)",
                   (T, T))  # fmt: skip
    rows = [  # phrase, start, end, companies, lower_bound, filers
        ('"generative AI"', "2024-01-01", "2024-12-31", 509, 0, 6785),
        ('"generative AI"', "2025-01-01", "2025-10-08", 821, 0, 6273),
        ('"generative AI"', "2026-01-01", "2026-10-08", 1005, 1, 6288),
        ("", "2024-01-01", "2024-12-31", 524, 0, 6785),
        ("", "2025-01-01", "2025-10-08", 855, 0, 6273),
        ("", "2026-01-01", "2026-10-08", 1102, 1, 6288),
    ]
    for p, s, e, c, lb, f in rows:
        engine.execute("INSERT INTO theme_breadth VALUES (1, ?, '10-K', ?, ?, ?, ?, ?, ?, 0, ?, "
                       "NULL, ?)", (p, s, e, c, c, c, lb, f, T))  # fmt: skip
    engine.execute("INSERT INTO form_index VALUES (2026, 4, 0, '2026-10-08', 0, 'x', ?)", (T,))
    q = engine.execute(
        "INSERT INTO fulltext_query (phrase, variant, forms, start_date, end_date, total, capped, "
        "hits_kept, fetched_at) VALUES ('\"generative AI\"', 'phrase', '10-K,10-K405,10-KT,10-KSB', "
        "'2026-01-01', '2026-10-08', 1500, 0, 1000, ?)", (T,)).lastrowid  # fmt: skip
    engine.execute("INSERT INTO fulltext_hit (query_id, accession, filename, cik, entity_name, "
                   "form, file_date) VALUES (?, '0001326801-26-000010', 'meta-10k.htm', ?, "
                   "'Meta Platforms, Inc.', '10-K', '2026-01-29')", (q, CIK))  # fmt: skip
    engine.close()
    return client


def test_theme_list_shows_share_change_and_lower_bound(themed):
    html = themed.get("/themes").text
    assert "AI infrastructure" in html and "≥1,102" in html
    assert "≥17.53%" in html  # 1102 / 6288
    assert "+3.90 pts" in html  # vs 855 / 6273 = 13.63%
    assert "data through 2026-10-08" in html


def test_theme_detail_and_filers(themed):
    html = themed.get("/themes/ai").text
    assert "generative AI" in html and "Companies per phrase and window" in html
    assert "2026 to 10-08" in html and "first seen 2026-10-09" in html
    filers = themed.get("/themes/ai/filers", params={
        "phrase": '"generative AI"', "start": "2026-01-01", "end": "2026-10-08"}).text  # fmt: skip
    assert "Meta Platforms, Inc." in filers and "partial list" in filers
    assert themed.get("/themes/nope").status_code == 404


def test_company_themes_tab(themed):
    html = themed.get("/c/META?tab=themes").text
    assert "AI infrastructure" in html and "2026-01-29" in html and "generative AI" in html
    assert "built-in method" not in html and "object at 0x" not in html


def test_empty_themes_page(client):  # noqa: F811
    assert "No theme breadth stored yet" in client.get("/themes").text
    assert "Not linked to a theme yet" in client.get("/c/META?tab=themes").text


def test_tier_actions_side_panel_and_review_digest(client):  # noqa: F811
    from datetime import UTC, datetime

    from engine.themes import proposals

    data = client.app.state.settings.data_dir
    engine = open_db("engine", data)
    engine.execute("INSERT INTO entity (cik, name, source_ref, fetched_at) VALUES "
                   "('0000000042', 'Example Semis Inc.', 't', 'n')")  # fmt: skip
    engine.execute("INSERT INTO ticker (ticker, cik, valid_from, source) VALUES "
                   "('XSEM', '0000000042', '2020-01-01', 't')")  # fmt: skip
    now = datetime.now(UTC)
    for i in range(11):
        proposals.propose(engine, "m02_theme", f"t{i}", f"theme proposal {i}",
                          {"companies": 5, "why": "rising"}, now)  # fmt: skip
    engine.close()

    # Core names cannot be tracked; others can, then promote / remove.
    r = client.post("/c/META/tier/track", follow_redirects=False)
    assert (
        "core%20watchlist" in r.headers["location"]
        or "Core" in client.get(r.headers["location"]).text
    )
    client.post("/c/XSEM/tier/track", data={"reason": "HBM supplier"})
    page = client.get("/c/META").text
    assert "XSEM" in page.split("<h3>Tracked</h3>")[1]
    tab = client.get("/c/XSEM?tab=themes").text
    assert "Tracked (filings + XBRL)" in tab and "Promote to watchlist" in tab
    client.post("/c/XSEM/tier/promote")
    page = client.get("/c/META").text
    assert 'title="Promoted' in page.split("<h3>Tracked</h3>")[0]

    queue = client.get("/review").text
    assert "M02 digest — week of" in queue and "theme proposal 9" in queue
    themes_page = client.get("/themes").text
    assert "Waiting for next week" in themes_page and "theme proposal 10" in themes_page
    item_id = queue.split('href="/review/')[1].split('"')[0]
    item = client.get(f"/review/{item_id}").text
    assert "M02 proposals (themes, candidates, links)" in item and "Accept" in item
    r = client.post(f"/review/{item_id}/reject", data={"note": "not now"}, follow_redirects=False)
    assert r.status_code == 303 and "reject" in r.headers["location"]
