"""Live SEC checks (opt-in): uv run pytest -m live -v -s

About 15 requests, well under the rate limit. Uses temporary databases; nothing
is written to data/. Prints what it found so the output can be reviewed.
"""

from __future__ import annotations

import json
import re

import pytest

from engine.sec.client import SecClient, user_agent_from_env, utc_now
from engine.sec.documents import document_text, ingest_filing
from engine.sec.identity import SUBMISSIONS_URL, load_entity, resolve
from engine.sec.results import NotFound, Ok
from engine.sec.submissions import earnings_releases, stored_filings, sync_filings
from engine.store.db import open_db
from engine.store.http import SqliteCache, SqliteFetchLog

pytestmark = pytest.mark.live

APPLE = "0000320193"
_CORPUS: list = []  # the module's corpus.db, for document tests


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    folder = tmp_path_factory.mktemp("live")
    engine = open_db("engine", folder)
    corpus = open_db("corpus", folder)
    client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=SqliteFetchLog(engine))
    _CORPUS.append(corpus)
    yield client, engine
    print("\nfetch_log:")
    for row in engine.execute("SELECT outcome, status, from_cache, url, detail FROM fetch_log"):
        print("  ", tuple(row))
    engine.close()
    corpus.close()


def test_ticker_map_and_resolve(live):
    client, engine = live
    result = resolve(client, engine, "AAPL", utc_now())
    print(f"\nresolve AAPL -> {result}")
    assert isinstance(result, Ok) and result.data == APPLE

    state = engine.execute("SELECT detail FROM refresh_state WHERE name='ticker_map'").fetchone()
    detail = json.loads(state["detail"])
    print(f"ticker map: {detail['listed']} tickers, {len(detail['conflicts'])} conflicts")
    for line in detail["conflicts"][:20]:
        print("   conflict:", line)
    assert detail["listed"] > 5000

    for ticker in ("BRK.B", "NVDA", "MU", "AVGO"):
        print(f"resolve {ticker} -> {resolve(client, engine, ticker, utc_now())}")


def test_entity_from_submissions(live):
    client, engine = live
    result = load_entity(client, engine, APPLE, utc_now())
    print(f"\nentity: {result}")
    assert isinstance(result, Ok)
    assert "apple" in result.data.name.lower()
    assert result.data.sic and result.data.fiscal_year_end


def test_filing_index_pages(live):
    """Which per-filing index carries document types (M00_SEC_DATA, first integration test).

    Finding 2026-10-07: {accession}-index.json does not exist (404); index.json is a
    folder listing (type = icon name); {accession}-index.htm lists document types.
    """
    client, _ = live
    subs = client.get_json(SUBMISSIONS_URL.format(cik=APPLE), ttl_s=3600)
    assert isinstance(subs, Ok)
    recent = subs.data["filings"]["recent"]
    i = recent["form"].index("10-K")
    acc = recent["accessionNumber"][i]
    base = f"https://www.sec.gov/Archives/edgar/data/320193/{acc.replace('-', '')}"

    missing = client.get_bytes(f"{base}/{acc}-index.json", ttl_s=3600)
    print(f"\n{acc}-index.json -> {missing}")
    assert isinstance(missing, NotFound), "accession-index.json now exists; revisit documents.py"

    listing = client.get_json(f"{base}/index.json", ttl_s=3600)
    assert isinstance(listing, Ok)
    names = [item["name"] for item in listing.data["directory"]["item"]]
    print(f"index.json lists {len(names)} files: {names}")

    page = client.get_text(f"{base}/{acc}-index.htm", ttl_s=3600)
    assert isinstance(page, Ok)
    html = page.data
    start = html.find("tableFile")
    print(f"-index.htm document table (first 3000 chars):\n{html[start : start + 3000]}")
    assert re.search(r">\s*Type\s*<", html), "no Type column in -index.htm"
    assert re.search(r">\s*10-K\s*<", html), "10-K document type not found in -index.htm"


def test_submissions_all_pages(live):
    """Full filing index for AAPL, including the older pages in filings.files."""
    client, engine = live
    result = sync_filings(client, engine, APPLE, utc_now())
    print(f"\nsync: {result}")
    assert isinstance(result, Ok) and result.data.complete

    rows = stored_filings(engine, APPLE)
    by_form: dict[str, int] = {}
    for f in rows:
        by_form[f.form] = by_form.get(f.form, 0) + 1
    top = sorted(by_form.items(), key=lambda kv: -kv[1])[:15]
    print(f"stored {len(rows)} filings, earliest {rows[-1].filed}, latest {rows[0].filed}")
    print(f"pages: {result.data.pages_total} total, loaded {result.data.pages_loaded}")
    print(f"top forms: {top}")
    releases = earnings_releases(engine, APPLE)
    print(f"8-K Item 2.02: {len(releases)}; latest {releases[0] if releases else None}")

    assert len(rows) == result.data.filings_seen  # no accession lost or duplicated
    if result.data.pages_total:
        assert rows[-1].filed < "2010-01-01", "older pages did not extend history"
    assert releases and all(f.has_item("2.02") for f in releases)


@pytest.mark.parametrize("form", ["10-K", "8-K 2.02"])
def test_documents_whole_text(live, form):
    """Latest 10-K and latest earnings 8-K (+ EX-99.1): fetched via -index.htm, stored whole."""
    client, engine = live
    corpus = _CORPUS[0]
    sync = sync_filings(client, engine, APPLE, utc_now())
    assert isinstance(sync, Ok)
    if form == "10-K":
        filing = stored_filings(engine, APPLE, forms=["10-K"])[0]
    else:
        filing = earnings_releases(engine, APPLE)[0]

    result = ingest_filing(client, corpus, filing, utc_now())
    print(f"\n{form} {filing.accession} filed {filing.filed}: {result}")
    assert isinstance(result, Ok) and result.data.complete
    types = [d.doc_type for d in result.data.stored]
    assert filing.form in types

    for doc in result.data.stored:
        text = document_text(corpus, doc.doc_id) or ""
        leftover = len(re.findall(r"&#?\w+;|<[a-zA-Z/][^>]{0,40}>", text))
        print(f"  {doc.doc_type} {doc.filename}: {doc.chars:,} chars, {leftover} markup leftovers")
        print("  first 400 chars:", text[:400].replace("\n", " | "))
        print("  last 300 chars:", text[-300:].replace("\n", " | "))
        assert leftover < 20, "HTML entities or tags left in extracted text"
        assert "�" not in text, "replacement characters: text was decoded wrongly"

    texts = {d.doc_type: document_text(corpus, d.doc_id) or "" for d in result.data.stored}
    if form == "10-K":
        main = texts["10-K"]
        assert len(main) > 150_000, "10-K text looks truncated"
        for phrase in ("Item 1A", "Risk Factors", "Item 7", "Discussion and Analysis"):
            assert phrase in main, f"{phrase!r} missing from 10-K text"
        hits = corpus.execute(
            "SELECT count(*) FROM section_fts WHERE section_fts MATCH '\"risk factors\"'"
        ).fetchone()[0]
        assert hits >= 1
    else:
        assert "EX-99.1" in texts, "earnings 8-K has no EX-99.1"
        assert "net sales" in texts["EX-99.1"].lower()
