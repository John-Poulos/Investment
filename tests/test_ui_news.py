# ruff: noqa: E501  (fixture text)
"""News screens (M02 part 7a): company News tab, theme page section, weekly news item."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from engine.news import digest, match, store
from engine.news.config import NewsConfig
from engine.news.items import RawItem
from engine.store.db import open_db
from tests.test_ui import CIK, client  # noqa: F401  (fixture)

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
T = NOW.isoformat(timespec="seconds")
CFG = NewsConfig(
    company_domains={"meta.com": "META"},
    outlets=frozenset({"reuters.com"}),
    sources=frozenset({"reuters"}),
)


def seed(e, now: datetime = NOW) -> None:
    """A theme, four news items (one deduped across three sources), a first mention and
    the weekly item (also used to seed a scratch database for the visual check)."""
    e.execute("INSERT INTO theme (key, name, source, status, discovered_at, updated_at) VALUES "
              "('ai_infrastructure', 'AI infrastructure', 'seed', 'active', ?, ?)", (T, T))  # fmt: skip
    tid = e.execute("SELECT theme_id FROM theme WHERE key = 'ai_infrastructure'").fetchone()[0]
    e.execute("INSERT INTO theme_phrase (theme_id, phrase, source, status, discovered_at, updated_at) "
              "VALUES (?, '\"AI infrastructure\"', 'seed', 'active', ?, ?)", (tid, T, T))  # fmt: skip
    seen = digest.last_week_start(now) + timedelta(days=2)
    items = [
        RawItem(
            "ir_rss",
            "META",
            "Meta Platforms expands AI infrastructure in Ohio",
            "https://investor.atmeta.com/a",
            "2026-10-07T12:00:00+00:00",
            None,
            "investor.atmeta.com",
            (),
            CIK,
        ),
        RawItem(
            "sec_8k",
            "0001326801-26-000200",
            "Meta Platforms Expands AI Infrastructure in Ohio",
            "https://www.sec.gov/Archives/edgar/data/1326801/x/ex991.htm",
            "2026-10-07T20:00:00+00:00",
            "MENLO PARK — Meta today announced a new data center campus.",
            "sec.gov",
            (),
            CIK,
        ),
        RawItem(
            "finnhub",
            "META",
            "Meta Platforms expands AI infrastructure in Ohio",
            "https://finnhub.io/api/news?id=1",
            "2026-10-07T13:00:00+00:00",
            "Reuters report.",
            "Reuters",
            ("META",),
            CIK,
        ),
        RawItem(
            "finnhub",
            "META",
            "Is Meta's <b>AI infrastructure</b> spend too much?",
            "https://finnhub.io/api/news?id=2",
            "2026-10-08T13:00:00+00:00",
            "Opinion.",
            "Yahoo",
            ("META",),
            CIK,
        ),
        RawItem(
            "finnhub",
            "META",
            "Meta Platforms quarterly dividend",
            "https://finnhub.io/api/news?id=3",
            "2026-10-08T15:00:00+00:00",
            None,
            "Yahoo",
            ("META",),
            CIK,
        ),
    ]
    store.store_all(e, items, CFG, seen, match.ThemeMatcher(e), match.CompanyMatcher(e))
    e.execute("INSERT INTO theme_first_mention (cik, theme_id, baseline, phrase, source, accession, "
              "filename, section, dated, quote, scanned_at, found_at) VALUES (?, ?, 0, 'AI infrastructure', "
              "'document', '0001326801-26-000150', 'meta-10q.htm', '10-Q Part I Item 2', '2026-10-06', "
              "'…we continue to invest in AI infrastructure across…', ?, ?)",
              (CIK, tid, T, (seen + timedelta(hours=1)).isoformat(timespec="seconds")))  # fmt: skip
    digest.propose_week(e, digest.last_week_start(now), {CIK: "META"}, now)


@pytest.fixture
def newsy(client):  # noqa: F811
    e = open_db("engine", client.app.state.settings.data_dir)
    seed(e)
    e.close()
    return client


def test_company_news_tab(newsy):
    r = newsy.get("/c/META?tab=news")
    assert r.status_code == 200
    html = r.text
    assert "Meta Platforms expands AI infrastructure in Ohio" in html
    assert (
        html.count("Meta Platforms expands AI infrastructure in Ohio") == 1
    )  # one row for three sources
    assert "IR feed · 8-K · Finnhub (Reuters)" in html
    assert "First mention of each accepted theme" in html and "10-Q Part I Item 2" in html
    assert "quarterly dividend" in html
    themed = newsy.get("/c/META?tab=news&only=themed").text
    assert "quarterly dividend" not in themed and "Show all" in themed
    assert "<function" not in html and "object at 0x" not in html


def test_theme_page_news_section(newsy):
    html = newsy.get("/themes/ai_infrastructure").text
    assert "News, last 90 days" in html
    assert "Companies named in news with a theme phrase: 1 — META (2)" in html
    assert "spend too much?" in html and "&lt;b&gt;" not in html


def test_weekly_news_review_item(newsy):
    e = open_db("engine", newsy.app.state.settings.data_dir)
    item = e.execute(
        "SELECT item_id, reason, payload FROM review_queue WHERE kind = 'm02_news'"
    ).fetchone()
    e.close()
    assert "1 event(s) on 1 theme(s), 1 first mention(s)" in item["reason"]
    assert (
        json.loads(item["payload"])["companies"] == 1
    )  # META once, from events and first mentions
    html = newsy.get(f"/review/{item['item_id']}").text
    assert "Week 2026-10-05 to 2026-10-11" in html
    assert "IR feed A · 8-K A · Finnhub (Reuters) B" in html
    assert "1 other item(s) (grade C" in html
    assert "First mention of an accepted theme" in html and "<mark>AI infrastructure</mark>" in html
    assert "noted" in html.lower() and "object at 0x" not in html
