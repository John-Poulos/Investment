"""Live SEC checks (opt-in): uv run pytest -m live -v -s

About 6 requests, well under the rate limit. Uses temporary databases; nothing
is written to data/. Prints what it found so the output can be reviewed.
"""

from __future__ import annotations

import json
import re

import pytest

from engine.sec.client import SecClient, user_agent_from_env, utc_now
from engine.sec.identity import SUBMISSIONS_URL, load_entity, resolve
from engine.sec.results import NotFound, Ok
from engine.store.db import open_db
from engine.store.http import SqliteCache, SqliteFetchLog

pytestmark = pytest.mark.live

APPLE = "0000320193"


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    folder = tmp_path_factory.mktemp("live")
    engine = open_db("engine", folder)
    corpus = open_db("corpus", folder)
    client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=SqliteFetchLog(engine))
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
