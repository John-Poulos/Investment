# ruff: noqa: E501  (fixture rows)
"""Seasonal pass screens (M02 part 6): Themes page section and the new review layouts."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from engine.store.db import open_db
from engine.themes.proposals import propose
from tests.test_ui import client  # noqa: F401  (fixture)

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
T = NOW.isoformat(timespec="seconds")
X = "0000000077"


@pytest.fixture
def seasoned(client):  # noqa: F811
    e = open_db("engine", client.app.state.settings.data_dir)
    seed(e)
    e.close()
    return client


def seed(e) -> None:
    """One finished pass: a proposed phrase, a listed one, a screened-out one, a candidate
    with flags (also used to seed a scratch database for the visual check)."""
    e.execute("INSERT INTO theme VALUES (1, 'optics', 'Custom silicon & optics', 'seed', "
              "'active', ?, ?)", (T, T))  # fmt: skip
    e.execute("INSERT INTO seasonal_run (season, season_date, family, latest_start, latest_end, "
              "prior_start, prior_end, status, started_at, finished_at) VALUES ('2026-08', "
              "'2026-08-19', '10-Q', '2026-01-01', '2026-08-19', '2025-01-01', '2025-08-19', "
              "'done', ?, ?)", (T, T))  # fmt: skip
    spread = {"operating": 21, "blank_check": 1, "unknown": 0, "finance": 2,
              "groups": [["business equipment (chips, computers, software)", 15],
                         ["manufacturing", 3]], "top3": 1.0, "known": 18, "generic": None}  # fmt: skip
    sample = {"passage_id": 9, "cik": X, "name": "NVIDIA CORP", "group": "business equipment",
              "accession": "0001045810-26-000010", "filename": "n.htm",
              "text": "our switches use co-packaged optics to cut <power> per port"}  # fmt: skip
    rows = [
        ("co-packaged optics", "proposed", "m02_phrase: queued", 1, 21, 9, 0.18, 0.009),
        ("bandwidth memory", "listed", 'covered by "high bandwidth memory"', None, 10, 2, 0.1, 0.02),
    ]  # fmt: skip
    for ph, stage, why, tid, n1, n0, g, p in rows:
        e.execute("INSERT INTO seasonal_phrase (season, phrase, source, adopters, adopter_ciks, "
                  "rank, stage, reason, latest_companies, prior_companies, growth_pts, p_value, "
                  "p0, spread, crowding, theme_id, overlap, samples, discovered_at, updated_at) "
                  "VALUES ('2026-08', ?, 'mined', 1, ?, 1, ?, ?, ?, ?, ?, ?, 0.497, ?, ?, ?, 0.92, "
                  "?, ?, ?)",
                  (ph, json.dumps([X]), stage, why, n1, n0, g, p, json.dumps(spread),
                   json.dumps({"latest": 19, "prior": 4, "flag": True}), tid,
                   json.dumps([sample]), T, T))  # fmt: skip
    e.execute("INSERT INTO seasonal_phrase (season, phrase, source, rank, stage, reason, "
              "discovered_at, updated_at) VALUES ('2026-08', 'research and development', "
              "'mined', 2, 'screened_out', 'no rise beyond chance (4337 → 4130 documents, p 0.97)', "
              "?, ?)", (T, T))  # fmt: skip
    payload = {"phrase": "co-packaged optics", "season": "2026-08", "family": "10-Q",
               "windows": {"latest": ["2026-01-01", "2026-08-19"],
                           "prior": ["2025-01-01", "2025-08-19"]},
               "companies": 21, "prior_companies": 9, "lower_bound": False, "p": 0.009,
               "p0": 0.497, "growth_pts": 0.18, "spread": spread,
               "crowding": {"latest": 19, "prior": 4, "flag": True}, "samples": [sample],
               "adopters": ["NVDA"], "source": "mined", "theme_key": "optics",
               "theme_name": "Custom silicon & optics", "overlap": 0.92, "grade": "A",
               "money_flow": False, "first_detected": T, "phrase_id": 5, "new_theme": False}  # fmt: skip
    propose(e, "m02_phrase", "optics:co-packaged optics", '"co-packaged optics" — new phrase',
            payload, NOW)  # fmt: skip
    e.execute("INSERT INTO seasonal_company (season, cik, theme_id, name, ticker, phrases, "
              "first_mention, tier, section, quantified, quote, accession, filename, quote_start, "
              "quote_end, flags, float_usd, float_as_of, size_label, discovered_at, updated_at) "
              "VALUES ('2026-08', ?, 1, 'Bluegrass Quantum Holdings', 'BQH', ?, '2026-03-30', "
              "'candidate', '10-K Item 1', 0, 'q', 'a-1', 'b.htm', 0, 5, ?, 18400000, "
              "'2025-06-30', 'nano: float $18.4M', ?, ?)",
              (X, json.dumps(['"co-packaged optics"']),
               json.dumps(["renamed 2026-02-14 (was Bluegrass Mining Corp)",
                           "nano: float $18.4M"]), T, T))  # fmt: skip
    cand = {"ticker": "BQH", "name": "Bluegrass Quantum Holdings", "theme_key": "optics",
            "theme_name": "Custom silicon & optics", "phrases": ["co-packaged optics"],
            "section": "10-K Item 1", "quantified": False,
            "quote": "the Company intends to develop Co-Packaged Optics software",
            "accession": "a-1", "filename": "b.htm", "offsets": [0, 5],
            "flags": ["renamed 2026-02-14 (was Bluegrass Mining Corp)", "nano: float $18.4M"],
            "size": "nano: float $18.4M", "float_as_of": "2025-06-30", "float_ref": "f1",
            "first_mention": "2026-03-30", "first_note": "first mention this season",
            "industry": "other: business services", "grade": "A", "money_flow": False,
            "companies": 1, "season": "2026-08", "why": "x"}  # fmt: skip
    propose(e, "m02_candidate", X, "BQH: candidate for Custom silicon & optics", cand, NOW, cik=X)


def test_themes_page_shows_the_seasonal_pass(seasoned):
    html = seasoned.get("/themes").text
    assert "Seasonal pass 2026-08" in html and "10-Q filers" in html
    assert "co-packaged optics" in html and "9 → 21" in html and "+0.18 pts" in html
    assert "crowding" in html and "finance 2" in html and X in html  # adopter without a ticker
    assert "covered by &#34;high bandwidth memory&#34;" in html
    assert "no rise beyond chance" in html  # screened-out reasons
    assert "Bluegrass Quantum Holdings" in html and "renamed 2026-02-14" in html
    assert "first this season" in html and "candidate · in review" in html
    assert "{'" not in html and "[{" not in html  # no Python objects rendered


def test_phrase_and_candidate_review_layouts(seasoned):
    e = open_db("engine", seasoned.app.state.settings.data_dir)
    items = {r["kind"]: r["item_id"] for r in e.execute("SELECT kind, item_id FROM review_queue")}
    e.close()
    html = seasoned.get(f"/review/{items['m02_phrase']}").text
    assert "21 operating 10-Q filers" in html and "p 0.009" in html
    assert "<mark>co-packaged optics</mark>" in html and "&lt;power&gt;" in html  # escaped
    assert "92% of its passages" in html and "--gemini-name" in html
    assert "{'" not in html
    html = seasoned.get(f"/review/{items['m02_candidate']}").text
    assert "First-mention flags: renamed 2026-02-14" in html
    assert "<mark>Co-Packaged Optics</mark>" in html and "first mention this season" in html
    assert "as of 2025-06-30" in html and "{'" not in html
