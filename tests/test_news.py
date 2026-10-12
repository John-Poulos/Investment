# ruff: noqa: E501  (fixture text)
"""M02 part 7a: news — feeds, Finnhub/Massive, 8-K releases, dedupe, matching, first
mentions, weekly news item (D-M02-13, -15, -58).

Feeds and vendor replies here are synthetic, in each source's shape (vendor data and
publishers' text stay off GitHub).
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from engine.news import digest, discover, first_mentions, match, rss, sec8k, store, vendors
from engine.news.config import Feed, NewsConfig, load
from engine.news.fetch import Fetcher
from engine.news.items import RawItem, snippet, url_key
from engine.news.step import run_news_step
from engine.sec.documents import ARCHIVES, IndexDoc, store_document
from engine.themes.proposals import KIND_LABELS
from engine.themes.seeds import sync_seeds

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)  # a Wednesday
NVDA, MU, OTHER = "0001045810", "0000723125", "0000000099"
COMPANIES = {"NVDA": NVDA, "MU": MU}
SEEDS = """
[[theme]]
key = "hbm_packaging"
name = "HBM & advanced packaging"
phrases = ["high bandwidth memory", "HBM", "chiplet"]

[[theme]]
key = "ai_infrastructure"
name = "AI infrastructure"
phrases = ["AI infrastructure", "AI accelerator"]
"""
CFG = NewsConfig(
    ir={"NVDA": ("https://investor.nvidia.com/rss/pressrelease.aspx",)},
    company_domains={"nvidia.com": "NVDA", "micron.com": "MU"},
    trade=(Feed("trade", "eetimes", "EE Times", "https://www.eetimes.com/feed/"),),
    outlets=frozenset({"reuters.com", "eetimes.com"}),
    sources=frozenset({"reuters"}),
)

Q4_RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>NVIDIA Press Releases</title>
<item><title>NVIDIA Unveils Next-Generation AI Accelerator Platform</title>
<link>https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Unveils/default.aspx</link>
<pubDate>Mon, 12 Oct 2026 20:05:00 GMT</pubDate></item>
<item><title>NVIDIA Announces Date for Third Quarter Results</title>
<link>https://investor.nvidia.com/news/press-release-details/2026/date/default.aspx</link>
<pubDate>Tue, 06 Oct 2026 20:05:00 GMT</pubDate></item>
</channel></rss>"""

TRADE_RSS = (
    b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>EE Times</title>
<item><title>Micron ramps HBM4 for next-gen accelerators</title>
<link>https://www.eetimes.com/micron-ramps-hbm4/?utm_source=rss&amp;utm_medium=rss</link>
<pubDate>Tue, 13 Oct 2026 14:00:00 +0000</pubDate>
<description><![CDATA[<p>Micron Technology said volume shipments of its newest high bandwidth memory began this quarter.</p>]]></description>
<content:encoded><![CDATA[<p>"""
    + b"Long article text. " * 200
    + b"""</p>]]></content:encoded></item>
<item><title>Startup tapes out chiplet interposer</title>
<link>https://www.eetimes.com/startup-chiplet/</link>
<pubDate>Tue, 13 Oct 2026 15:00:00 +0000</pubDate>
<description>A small company shows its chiplet design.</description></item>
</channel></rss>"""
)

FINNHUB = [
    {
        "category": "company",
        "datetime": int(datetime(2026, 10, 13, 15, tzinfo=UTC).timestamp()),
        "headline": "Micron ramps HBM4 for next-gen accelerators",
        "id": 1,
        "image": "",
        "related": "MU",
        "source": "Reuters",
        "summary": "Micron began volume shipments.",
        "url": "https://finnhub.io/api/news?id=abc",
    },
    {
        "category": "company",
        "datetime": int(datetime(2026, 10, 13, 16, tzinfo=UTC).timestamp()),
        "headline": "3 memory stocks to watch as HBM demand grows",
        "id": 2,
        "image": "",
        "related": "MU",
        "source": "Yahoo",
        "summary": "Opinion piece.",
        "url": "https://finnhub.io/api/news?id=def",
    },
]
MASSIVE = {
    "status": "OK",
    "count": 1,
    "request_id": "x",
    "results": [
        {
            "id": "m1",
            "title": "NVIDIA expands AI infrastructure partnership",
            "article_url": "https://www.reuters.com/tech/nvidia-expands/",
            "published_utc": "2026-10-13T12:00:00Z",
            "description": "NVIDIA Corporation said…",
            "publisher": {"name": "Reuters", "homepage_url": "https://www.reuters.com"},
            "tickers": ["NVDA"],
        }
    ],
}


class Transport:
    """Routes by URL; records (url, params, headers)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, params, headers):
        self.calls.append((url, dict(params), dict(headers)))
        r = self.routes.get((url, params.get("symbol") or params.get("ticker"))) or self.routes.get(
            url
        )
        if r is None:
            raise AssertionError(f"unexpected request {url} {params}")
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        if isinstance(r, Exception):
            raise r
        return r


def fetcher(engine, routes, secrets=()):
    t = Transport(routes)
    return Fetcher(engine, transport=t, now=lambda: NOW, clock=lambda: 0.0,
                   sleep=lambda s: None, intervals={}, secrets=secrets), t  # fmt: skip


@pytest.fixture
def db(dbs, tmp_path: Path):
    engine, corpus = dbs
    p = tmp_path / "themes.toml"
    p.write_text(SEEDS, encoding="utf-8")
    sync_seeds(engine, p, NOW - timedelta(days=30))
    for t, c in (("NVDA", NVDA), ("MU", MU)):
        engine.execute(
            "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES (?, ?, '2020-01-01', 't')",
            (t, c),
        )
    return engine, corpus


def matchers(engine):
    return match.ThemeMatcher(engine), match.CompanyMatcher(engine)


def put(engine, items, now=NOW, cfg=CFG):
    return store.store_all(engine, items, cfg, now, *matchers(engine))


def raw(
    channel="trade",
    feed="eetimes",
    title="Micron ramps HBM4",
    url="https://www.eetimes.com/a/",
    published="2026-10-13T14:00:00+00:00",
    snip=None,
    origin=None,
    cik=None,
    tickers=(),
):
    return RawItem(channel, feed, title, url, published, snip, origin, tickers, cik)


def filing(engine, cik, acc, form, filed, accepted=None):
    engine.execute("INSERT INTO filing (accession, cik, form, filed, accepted_at, ingested_at) "
                   "VALUES (?, ?, ?, ?, ?, ?)", (acc, cik, form, filed, accepted, filed))  # fmt: skip
    engine.execute("INSERT INTO filing_cik (accession, cik) VALUES (?, ?)", (acc, cik))


def doc(corpus, cik, acc, doc_type, text, name="d.htm"):
    url = f"{ARCHIVES}/{int(cik)}/{acc.replace('-', '')}/{name}"
    d = IndexDoc(None, None, name, url, doc_type, None, False)
    return store_document(corpus, cik, acc, d, text.encode(), NOW).doc_id


# --- text rules ----------------------------------------------------------------------------


def test_snippet_and_url_key():
    long = "<p>word " * 200 + "</p>"
    s = snippet(long)
    assert len(s) <= 300 and s.endswith("…") and "<" not in s
    assert snippet("") is None and snippet(None) is None
    assert url_key("https://www.eetimes.com/a/?utm_source=rss&id=3#top") == "eetimes.com/a?id=3"
    assert url_key("http://eetimes.com/a") == "eetimes.com/a"
    assert url_key("https://finnhub.io/api/news?id=abc") is None  # vendor redirect


@pytest.mark.parametrize(
    ("phrase", "text", "hit"),
    [
        ("HBM", "Micron ramps HBM4 output", True),
        ("HBM", "SK hynix HBM3E supply", True),
        ("HBM", "HBMX is a ticker", False),
        ("chiplet", "two chiplets on one interposer", True),
        ("AI accelerator", "a new AI-accelerator card", True),
        ('"AI infrastructure"', "spend on ai infrastructure rose", True),
        ("qubit", "qubitless", False),
    ],
)
def test_phrase_pattern(phrase, text, hit):
    assert bool(match.phrase_pattern(phrase).search(text)) is hit


def test_config_file_loads():
    cfg = load()
    assert "NVDA" in cfg.ir and len(cfg.trade) == 11
    assert "semiengineering.com" in cfg.outlets  # trade domains are grade-B outlets
    assert cfg.company_domains["nvidia.com"] == "NVDA"


# --- RSS -----------------------------------------------------------------------------------


def test_rss_parse_q4_and_wordpress_shapes():
    f = Feed("ir_rss", "NVDA", "NVDA", "https://investor.nvidia.com/rss/pressrelease.aspx")
    items = rss.parse(f, Q4_RSS, NVDA)
    assert [i.title for i in items][0] == "NVIDIA Unveils Next-Generation AI Accelerator Platform"
    assert items[0].snippet is None and items[0].published_at == "2026-10-12T20:05:00+00:00"
    assert items[0].cik == NVDA and items[0].origin == "investor.nvidia.com"
    t = rss.parse(CFG.trade[0], TRADE_RSS)
    assert t[0].snippet.startswith("Micron Technology said") and len(t[0].snippet) <= 300
    assert isinstance(rss.parse(f, b"<html>not a feed"), str)


def test_rss_fetch_conditional_get_and_failure(db):
    engine, _ = db
    f = CFG.trade[0]
    fx, t = fetcher(
        engine, {f.url: [(200, TRADE_RSS, {"ETag": '"v1"'}), (304, b"", {}), (403, b"blocked", {})]}
    )
    r1 = rss.fetch(engine, fx, f, NOW)
    assert r1.status == "ok" and len(r1.items) == 2
    r2 = rss.fetch(engine, fx, f, NOW)
    assert r2.status == "not modified" and t.calls[1][2]["If-None-Match"] == '"v1"'
    r3 = rss.fetch(engine, fx, f, NOW)
    assert r3.status == "failed" and "403" in r3.detail
    st = engine.execute("SELECT * FROM news_feed_state").fetchone()
    assert st["etag"] == '"v1"' and st["last_status"] == 403 and st["items_last"] == 2


# --- vendors -------------------------------------------------------------------------------


def test_finnhub_parse_and_key_never_logged(db):
    engine, _ = db
    fx, t = fetcher(
        engine, {vendors.FINNHUB_URL: (200, json.dumps(FINNHUB).encode(), {})}, secrets=("FHKEY",)
    )
    got = vendors.finnhub_news(fx, "FHKEY", "MU", NOW.date() - timedelta(days=30), NOW.date(), MU)
    assert len(got) == 2 and got[0].origin == "Reuters" and got[0].tickers == ("MU",)
    assert t.calls[0][2]["X-Finnhub-Token"] == "FHKEY" and "token" not in t.calls[0][1]
    logged = engine.execute("SELECT url, detail FROM fetch_log").fetchall()
    assert all("FHKEY" not in (r["url"] + (r["detail"] or "")) for r in logged)
    assert isinstance(vendors.parse_finnhub("MU", b'{"error": "Invalid API key"}'), str)


def test_massive_parse_and_bearer(db):
    engine, _ = db
    fx, t = fetcher(engine, {vendors.MASSIVE_URL: (200, json.dumps(MASSIVE).encode(), {})})
    got = vendors.massive_news(fx, "MKEY", "NVDA", NOW.date(), NVDA)
    assert got[0].origin == "reuters.com" and got[0].published_at == "2026-10-13T12:00:00+00:00"
    assert t.calls[0][2]["Authorization"] == "Bearer MKEY" and "apiKey" not in t.calls[0][1]


def test_grades():
    assert store.grade(raw(channel="ir_rss"), CFG) == "A"
    assert store.grade(raw(channel="sec_8k"), CFG) == "A"
    assert store.grade(raw(channel="trade"), CFG) == "B"
    fh = dict(channel="finnhub", url="https://finnhub.io/api/news?id=1")
    assert store.grade(raw(**fh, origin="Reuters"), CFG) == "B"
    assert store.grade(raw(**fh, origin="Yahoo"), CFG) == "C"
    assert (
        store.grade(
            raw(channel="massive", url="https://www.reuters.com/x", origin="reuters.com"), CFG
        )
        == "B"
    )
    assert (
        store.grade(
            raw(
                channel="massive",
                url="https://nvidianews.nvidia.com/x",
                origin="nvidianews.nvidia.com",
            ),
            CFG,
        )
        == "A"
    )
    assert (
        store.grade(
            raw(channel="massive", url="https://blog.example/x", origin="blog.example"), CFG
        )
        == "C"
    )


# --- dedupe and matching -------------------------------------------------------------------


def test_dedupe_url_title_and_company_headline(db):
    engine, _ = db
    c = put(
        engine,
        [
            raw(
                url="https://www.eetimes.com/micron-ramps-hbm4/?utm_source=rss",
                title="Micron ramps HBM4 for next-gen accelerators",
            ),
            raw(
                channel="massive",
                feed="MU",
                url="https://eetimes.com/micron-ramps-hbm4/",
                title="Micron ramps HBM4 (EE Times)",
                origin="eetimes.com",
                cik=MU,
            ),
            raw(
                channel="finnhub",
                feed="MU",
                url="https://finnhub.io/api/news?id=abc",
                title="Micron ramps HBM4 for next-gen accelerators",
                published="2026-10-14T01:00:00+00:00",
                origin="Reuters",
                cik=MU,
            ),
            raw(
                channel="ir_rss",
                feed="NVDA",
                url="https://investor.nvidia.com/x",
                title="NVIDIA Unveils Next-Generation AI Accelerator Platform",
                published="2026-10-12T20:05:00+00:00",
                cik=NVDA,
            ),
            raw(
                channel="sec_8k",
                feed="0001045810-26-000100",
                url=f"{ARCHIVES}/1045810/x/ex991.htm",
                title="NVIDIA Unveils Next Generation AI Accelerator Platform for Data Centers",
                published="2026-10-13T20:10:00+00:00",
                cik=NVDA,
            ),
        ],
    )
    assert (c.new, c.merged) == (2, 3)
    items = engine.execute("SELECT item_id, grade FROM news_item ORDER BY item_id").fetchall()
    assert [r["grade"] for r in items] == ["B", "A"]
    assert (
        engine.execute(
            "SELECT count(*) FROM news_source WHERE item_id = ?", (items[0][0],)
        ).fetchone()[0]
        == 3
    )
    # a repeat from the same source adds nothing
    c2 = put(
        engine,
        [
            raw(
                url="https://www.eetimes.com/micron-ramps-hbm4/",
                title="Micron ramps HBM4 for next-gen accelerators",
            )
        ],
    )
    assert (c2.new, c2.merged, c2.repeats) == (0, 0, 1)


def test_theme_and_company_matching_and_rematch(db):
    engine, _ = db
    put(
        engine,
        [
            raw(
                title="NVIDIA Corporation picks chiplet design",
                snip="Partners named Meta in passing.",
            )
        ],
    )
    i = engine.execute("SELECT item_id FROM news_item").fetchone()[0]
    assert (
        engine.execute("SELECT phrase FROM news_theme WHERE item_id = ?", (i,)).fetchone()[0]
        == "chiplet"
    )
    assert [r[0] for r in engine.execute("SELECT cik FROM news_company")] == [
        NVDA
    ]  # 'Meta' alone is no alias
    # a new active phrase: re-matching picks it up
    tid = engine.execute("SELECT theme_id FROM theme WHERE key = 'ai_infrastructure'").fetchone()[0]
    engine.execute("UPDATE theme_phrase SET status = 'archived' WHERE phrase LIKE '%chiplet%'")
    engine.execute(
        "INSERT INTO theme_phrase (theme_id, phrase, source, status, discovered_at, updated_at) "
        "VALUES (?, '\"design\"', 'owner', 'active', ?, ?)",
        (tid, NOW.isoformat(), NOW.isoformat()),
    )
    assert match.rematch_all(engine) == 1
    assert engine.execute("SELECT theme_id FROM news_theme").fetchall()[0][0] == tid


# --- 8-K releases --------------------------------------------------------------------------


def test_sec8k_headline_and_releases(db):
    engine, corpus = db
    text = (
        "Exhibit 99.1\nPRESS RELEASE\nOctober 13, 2026\n"
        "NVIDIA Unveils Next-Generation AI Accelerator Platform\n"
        "SANTA CLARA, Calif. — NVIDIA today announced a platform for AI infrastructure.\n"
    )
    assert sec8k.headline(text)[0] == "NVIDIA Unveils Next-Generation AI Accelerator Platform"
    filing(engine, NVDA, "0001045810-26-000100", "8-K", "2026-10-13", "2026-10-13T20:10:00.000Z")
    doc(corpus, NVDA, "0001045810-26-000100", "EX-99.1", text, "ex991.htm")
    filing(engine, NVDA, "0001045810-26-000090", "8-K", "2026-10-01")  # no stored exhibit
    items = sec8k.releases(engine, corpus, {NVDA}, NOW)
    assert len(items) == 1 and items[0].published_at == "2026-10-13T20:10:00+00:00"
    assert items[0].snippet.startswith("SANTA CLARA") and items[0].cik == NVDA


# --- first mentions ------------------------------------------------------------------------


def test_first_mentions_baseline_then_event(db):
    engine, corpus = db
    filing(engine, MU, "0000723125-26-000001", "10-Q", "2026-07-01")
    doc(
        corpus,
        MU,
        "0000723125-26-000001",
        "10-Q",
        "PART I\nItem 2. MD&A\nWe sell high bandwidth memory.\n",
    )
    assert first_mentions.scan(engine, corpus, {MU, NVDA}, NOW - timedelta(days=7)) == []
    rows = engine.execute(
        "SELECT cik, theme_id, baseline, phrase FROM theme_first_mention ORDER BY cik, theme_id"
    ).fetchall()
    assert len(rows) == 4 and all(r["baseline"] == 1 for r in rows)
    assert sum(r["phrase"] is not None for r in rows) == 1  # MU × HBM
    # NVIDIA's new 10-Q names a theme for the first time → event
    filing(engine, NVDA, "0001045810-26-000200", "10-Q", "2026-10-12")
    doc(
        corpus, NVDA, "0001045810-26-000200", "10-Q", "PART I\nItem 2. MD&A\nDemand for HBM grew.\n"
    )
    # a late-stored old filing naming the other theme is not an event
    filing(engine, NVDA, "0001045810-24-000001", "10-K", "2024-02-01")
    doc(
        corpus,
        NVDA,
        "0001045810-24-000001",
        "10-K",
        "PART I\nItem 1. Business\nOur AI infrastructure.\n",
    )
    ev = first_mentions.scan(engine, corpus, {MU, NVDA}, NOW)
    assert [(e.cik, e.phrase, e.dated) for e in ev] == [(NVDA, "HBM", "2026-10-12")]
    assert ev[0].section and "HBM" in ev[0].quote
    late = engine.execute(
        "SELECT baseline, dated FROM theme_first_mention WHERE cik = ? AND phrase = 'AI infrastructure'",
        (NVDA,),
    ).fetchone()
    assert (late["baseline"], late["dated"]) == (1, "2024-02-01")


# --- weekly news item ----------------------------------------------------------------------


def test_digest_rules_and_proposal(db):
    engine, _ = db
    week = digest.last_week_start(NOW)  # Mon 2026-10-05
    seen = week + timedelta(days=2)
    put(
        engine,
        [
            # A, the company's own feed, with a phrase → event
            raw(
                channel="ir_rss",
                feed="NVDA",
                url="https://investor.nvidia.com/a",
                title="NVIDIA ships AI accelerator",
                published="2026-10-07T12:00:00+00:00",
                cik=NVDA,
            ),
            # B naming a tracked company → event
            raw(
                url="https://www.eetimes.com/b/",
                title="Micron Technology expands HBM line",
                published="2026-10-07T13:00:00+00:00",
            ),
            # C (unknown outlet) naming a tracked company → counted only
            raw(
                channel="finnhub",
                feed="MU",
                url="https://finnhub.io/api/news?id=9",
                title="Is HBM a bubble?",
                origin="Yahoo",
                cik=MU,
                published="2026-10-07T14:00:00+00:00",
            ),
            # B about another company → counted only
            raw(
                url="https://www.eetimes.com/c/",
                title="Startup tapes out chiplet",
                published="2026-10-07T15:00:00+00:00",
            ),
            # B with a phrase but published long before the week → left out
            raw(
                url="https://www.eetimes.com/d/",
                title="Micron Technology HBM history",
                published="2026-08-01T00:00:00+00:00",
            ),
        ],
        now=seen,
    )
    engine.execute(
        "INSERT INTO entity (cik, name, source_ref, fetched_at) VALUES (?, 'Micron Technology, Inc.', 't', 't')",
        (MU,),
    )
    tiers = {NVDA: "NVDA", MU: "MU"}
    p = digest.build(engine, week, tiers)
    hbm = next(t for t in p["themes"] if t["key"] == "hbm_packaging")
    ai = next(t for t in p["themes"] if t["key"] == "ai_infrastructure")
    assert [e["title"] for e in ai["events"]] == ["NVIDIA ships AI accelerator"]
    assert [e["title"] for e in hbm["events"]] == ["Micron Technology expands HBM line"]
    assert hbm["events"][0]["companies"] == ["MU"] and hbm["other"] == 2
    assert p["events"] == 2 and p["grade"] == "A"
    assert digest.propose_week(engine, week, tiers, NOW) == "queued"
    assert digest.propose_week(engine, week, tiers, NOW) == "suppressed"
    item = engine.execute(
        "SELECT kind, reason, payload FROM review_queue WHERE kind = 'm02_news'"
    ).fetchone()
    assert (
        "2 event(s) on 2 theme(s)" in item["reason"]
        and json.loads(item["payload"])["week"] == "2026-10-05"
    )
    assert (
        digest.propose_week(engine, week + timedelta(days=7), tiers, NOW, preview=True) == "empty"
    )
    assert "m02_news" in KIND_LABELS


# --- the step ------------------------------------------------------------------------------


def test_run_news_step_end_to_end(db):
    engine, corpus = db
    routes = {
        CFG.ir_feeds()[0].url: (200, Q4_RSS, {}),
        CFG.trade[0].url: (200, TRADE_RSS, {}),
        (vendors.FINNHUB_URL, "MU"): (200, json.dumps(FINNHUB).encode(), {}),
        (vendors.FINNHUB_URL, "NVDA"): (500, b"oops", {}),
        (vendors.MASSIVE_URL, "NVDA"): (200, json.dumps(MASSIVE).encode(), {}),
    }
    fx, t = fetcher(engine, routes, secrets=("FHKEY", "MKEY"))
    rep = run_news_step(engine, corpus, COMPANIES, NOW, fetcher=fx, finnhub_key="FHKEY",
                        massive_key="MKEY", cfg=CFG, preview=True)  # fmt: skip
    text = "\n".join(rep.lines)
    assert "error" not in text, text
    assert "feeds: IR 1 (ok 1" in text and "trade press 1 (ok 1" in text
    assert "Finnhub: 1 symbol(s) ok" in text and "Massive (backup): 1 of 1" in text
    assert "failed: finnhub NVDA: HTTP 500" in text
    # Micron HBM4 from EE Times and Finnhub/Reuters is one item
    mu = engine.execute(
        "SELECT i.item_id FROM news_item i WHERE title LIKE 'Micron ramps%'"
    ).fetchall()
    assert len(mu) == 1
    assert "preview of this week so far: queued" in text
    # a second run asks Finnhub from the last success minus the overlap
    rep2 = run_news_step(engine, corpus, {"MU": MU}, NOW + timedelta(days=1), fetcher=fx,
                         finnhub_key="FHKEY", cfg=CFG, feeds=False)  # fmt: skip
    assert "error" not in "\n".join(rep2.lines)
    last = [c for c in t.calls if c[0] == vendors.FINNHUB_URL][-1][1]
    assert last["from"] == "2026-10-12" and last["to"] == "2026-10-15"


def test_run_news_step_without_keys_never_fails(db):
    engine, corpus = db
    rep = run_news_step(engine, corpus, COMPANIES, NOW, fetcher=fetcher(engine, {})[0], cfg=CFG,
                        feeds=False)  # fmt: skip
    text = "\n".join(rep.lines)
    assert "Finnhub: skipped" in text and "Massive (backup): skipped" in text


def test_full_week_replaces_its_preview(db):
    engine, _ = db
    week = digest.last_week_start(NOW)
    seen = week + timedelta(days=2)
    put(engine, [raw(channel="ir_rss", feed="NVDA", url="https://investor.nvidia.com/a",
                     title="NVIDIA ships AI accelerator", published="2026-10-07T12:00:00+00:00",
                     cik=NVDA)], now=seen)  # fmt: skip
    tiers = {NVDA: "NVDA"}
    assert digest.propose_week(engine, week, tiers, seen, preview=True) == "queued"
    assert digest.propose_week(engine, week, tiers, NOW) == "queued"
    rows = engine.execute("SELECT reason, resolution, resolved_by FROM review_queue "
                          "WHERE kind = 'm02_news' ORDER BY item_id").fetchall()  # fmt: skip
    assert "(so far)" in rows[0]["reason"] and rows[0]["resolved_by"] == "engine"
    assert rows[1]["resolution"] is None
    keys = [r[0] for r in engine.execute("SELECT prop_key FROM m02_proposal")]
    assert keys == ["m02_news:2026-10-05"]
    # a preview still waiting (overflow) is simply dropped
    engine.execute("INSERT INTO m02_proposal (prop_key, kind, reason, payload, status, "
                   "first_seen_at, last_seen_at) VALUES ('m02_news:2026-10-12:preview', "
                   "'m02_news', 'r', '{}', 'overflow', 't', 't')")  # fmt: skip
    digest.propose_week(engine, week + timedelta(days=7), tiers, NOW + timedelta(days=7))
    assert engine.execute("SELECT count(*) FROM m02_proposal WHERE prop_key LIKE '%preview'"
                          ).fetchone()[0] == 0  # fmt: skip


# --- IR feed discovery (D-M02-59) ------------------------------------------------------------

FEED_3 = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Example Corp Press Releases</title>
<item><title>Example Corp Reports Third Quarter Results</title><link>/news/q3</link><pubDate>Tue, 13 Oct 2026 20:05:00 GMT</pubDate></item>
<item><title>Example Corp Opens AI Infrastructure Plant</title><link>/news/plant</link><pubDate>Mon, 05 Oct 2026 12:00:00 GMT</pubDate></item>
<item><title>Example Corp Declares Dividend</title><link>https://ir.example.com/news/div</link><pubDate>Fri, 25 Sep 2026 12:00:00 GMT</pubDate></item>
</channel></rss>"""
EMPTY = b'<?xml version="1.0"?><rss version="2.0"><channel><title>Empty</title></channel></rss>'
EX = "0000000055"


def test_relative_links_resolved():
    f = Feed("ir_rss", "EX", "EX", "https://ir.example.com/rss/news-releases.xml")
    items = rss.parse(f, FEED_3)
    assert items[0].url == "https://ir.example.com/news/q3"


def test_discover_check_rules():
    assert isinstance(discover.check(EMPTY, "u", "example.com"), str)  # empty feed fails
    foreign = FEED_3.replace(b"/news/", b"https://other.org/")
    assert "link to example.com" in discover.check(
        foreign, "https://ir.example.com/x", "example.com"
    )
    got = discover.check(FEED_3, "https://ir.example.com/rss/news-releases.xml", "example.com")
    assert got.title == "Example Corp Press Releases" and len(got.samples) == 3


def test_discovery_proposes_then_confirmed_feed_is_polled(db):
    engine, corpus = db
    c = discover.candidates("example.com")
    routes = {
        discover.PROFILE_URL: (
            200,
            json.dumps({"weburl": "https://www.example.com/"}).encode(),
            {},
        ),
        c[0]: (404, b"", {}),
        c[1]: (200, EMPTY, {}),
        c[2]: (200, FEED_3, {}),
    }
    fx, t = fetcher(engine, routes, secrets=("FHKEY",))
    companies = {"NVDA": NVDA, "EX": EX}  # NVDA has a config feed: never looked up
    lines = discover.run(engine, fx, "FHKEY", companies, CFG, NOW)
    assert lines == [f"IR feed discovery EX: found {c[2]} → review"]
    assert [u for u, _, _ in t.calls].count(discover.PROFILE_URL) == 1
    item = engine.execute("SELECT item_id, kind, payload FROM review_queue").fetchone()
    p = json.loads(item["payload"])
    assert (
        item["kind"] == "m02_ir_feed"
        and p["feed"] == c[2]
        and p["samples"][0].startswith("Example Corp Reports")
    )
    assert discover.due(engine, companies, CFG, NOW) == []
    # the owner confirms → the next run polls it, and its items are grade A
    from engine.themes import proposals

    proposals.apply(engine, "m02_ir_feed", "confirm", p, EX, "owner", NOW)
    feeds, domains = discover.confirmed(engine, companies, CFG)
    assert [f.url for f in feeds] == [c[2]] and domains == {"example.com": "EX"}
    rep = run_news_step(engine, corpus, companies, NOW, fetcher=fx, cfg=replace(CFG, ir={}, trade=()),
                        vendor_news=False)  # fmt: skip
    assert "feeds: IR 1 (ok 1" in "\n".join(rep.lines)
    g = engine.execute("SELECT DISTINCT s.grade FROM news_source s WHERE s.feed = 'EX'").fetchall()
    assert [r[0] for r in g] == ["A"]


def test_discovery_none_found_rechecked_after_90_days(db):
    engine, _ = db
    routes = {
        discover.PROFILE_URL: (200, json.dumps({"weburl": "https://example.com"}).encode(), {})
    }
    routes |= {u: (404, b"", {}) for u in discover.candidates("example.com")}
    fx, _ = fetcher(engine, routes)
    companies = {"EX": EX}
    assert discover.run(engine, fx, "K", companies, CFG, NOW) == [
        "IR feed discovery EX: none found on example.com (12 tried)"]  # fmt: skip
    assert discover.due(engine, companies, CFG, NOW + timedelta(days=30)) == []
    assert discover.due(engine, companies, CFG, NOW + timedelta(days=91)) == [("EX", EX)]
    # without a Finnhub key nothing is fetched; the wait is reported
    assert "FINNHUB_API_KEY not set" in discover.run(engine, fx, None, companies, CFG,
                                                     NOW + timedelta(days=91))[0]  # fmt: skip
