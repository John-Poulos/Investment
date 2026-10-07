"""Live SEC checks (opt-in): uv run pytest -m live -v -s

About 15 requests, well under the rate limit. Uses temporary databases; nothing
is written to data/. Prints what it found so the output can be reviewed.
"""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from engine.sec.client import SecClient, user_agent_from_env, utc_now
from engine.sec.documents import document_text, ingest_filing
from engine.sec.identity import SUBMISSIONS_URL, load_entity, resolve
from engine.sec.results import NotFound, Ok
from engine.sec.submissions import earnings_releases, stored_filings, sync_filings
from engine.sec.xbrl_facts import get_series, sync_facts
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


REQUIRED_SECTIONS = {
    "10-K": ["10-K Item 1", "10-K Item 1A", "10-K Item 7", "10-K Item 7A", "10-K Item 8"],
    "10-Q": ["10-Q Part I Item 1", "10-Q Part I Item 2", "10-Q Part II Item 1A"],
    "8-K": ["8-K Item 2.02"],
}


@pytest.mark.parametrize("form", ["10-K", "10-Q", "8-K 2.02"])
def test_documents_and_sections(live, form):
    """Latest 10-K, 10-Q and earnings 8-K (+ EX-99.1): stored whole and split into sections."""
    client, engine = live
    corpus = _CORPUS[0]
    sync = sync_filings(client, engine, APPLE, utc_now())
    assert isinstance(sync, Ok)
    if form == "8-K 2.02":
        filing = earnings_releases(engine, APPLE)[0]
    else:
        filing = stored_filings(engine, APPLE, forms=[form])[0]

    result = ingest_filing(client, corpus, filing, utc_now())
    print(f"\n{form} {filing.accession} filed {filing.filed}: {result}")
    assert isinstance(result, Ok) and result.data.complete
    assert filing.form in [d.doc_type for d in result.data.stored]

    for doc in result.data.stored:
        text = document_text(corpus, doc.doc_id) or ""
        leftover = len(re.findall(r"&#?\w+;|<[a-zA-Z/][^>]{0,40}>", text))
        print(f"  {doc.doc_type} {doc.filename}: {doc.chars:,} chars, {leftover} markup leftovers")
        assert leftover < 20, "HTML entities or tags left in extracted text"
        assert "�" not in text, "replacement characters: text was decoded wrongly"

        log = corpus.execute(
            "SELECT outcome, missing FROM split_log WHERE doc_id = ?", (doc.doc_id,)
        ).fetchone()
        print(f"  split: {log['outcome']}, missing {log['missing']}")
        rows = corpus.execute(
            "SELECT label, title, start_offset, end_offset FROM section WHERE doc_id = ? "
            "ORDER BY start_offset",
            (doc.doc_id,),
        ).fetchall()
        for r in rows:
            start = text[r["start_offset"] : r["start_offset"] + 70].replace("\n", " | ")
            size = r["end_offset"] - r["start_offset"]
            print(f"    {r['label']:<24} {size:>8,}  {start}")
        assert rows[0]["start_offset"] == 0 or doc.doc_type not in REQUIRED_SECTIONS
        assert rows[-1]["end_offset"] == len(text)

        labels = [r["label"] for r in rows]
        wanted = REQUIRED_SECTIONS.get(doc.doc_type, [])
        if wanted:
            assert log["outcome"] == "split", f"{doc.doc_type} fell back: {log['missing']}"
            for label in wanted:
                assert label in labels, f"{label} not found"
            for r in rows:
                if r["label"] in wanted:
                    head = text[r["start_offset"] : r["start_offset"] + 20].lower()
                    assert head.startswith("item"), f"{r['label']} does not start at its heading"
        if doc.doc_type == "EX-99.1":
            first = text[rows[0]["start_offset"] : rows[0]["start_offset"] + 40]
            print(f"  EX-99.1 section starts: {first!r}")
            assert not first.startswith("EX-99.1"), "SEC header line not skipped"

    if form == "10-K":
        mdna = corpus.execute(
            "SELECT end_offset - start_offset FROM section WHERE label = '10-K Item 7'"
        ).fetchone()[0]
        assert mdna > 10_000, "MD&A section suspiciously short"
        hits = corpus.execute(
            "SELECT label FROM section_fts WHERE section_fts MATCH '\"risk factors\"' "
            "ORDER BY rank LIMIT 3"
        ).fetchall()
        print(f"  FTS 'risk factors' top sections: {[h[0] for h in hits]}")
        assert hits


def test_xbrl_facts_series(live):
    """AAPL companyfacts: concept map, derived quarters, TTM, point-in-time versions."""
    client, engine = live
    result = sync_facts(client, engine, APPLE, utc_now(), force=True)
    assert isinstance(result, Ok)
    s = result.data
    print(f"\nfacts: {s.facts_seen:,} seen, {s.facts_new:,} new, {s.series_rows:,} series rows")
    for concept, tags in s.concepts.items():
        print(f"  {concept:<24} {', '.join(tags)}")
    print(f"missing: {[p.path for p in s.missing]}")
    print(f"skipped units: {s.skipped_units}")
    for name in ("revenue", "net_income", "operating_cash_flow", "cash", "total_assets"):
        assert name in s.concepts, f"{name} not mapped"

    for concept in ("revenue", "capex", "net_income"):
        quarters = get_series(engine, APPLE, concept, "Q")
        print(f"\n{concept} last 6 quarters (first → latest, method):")
        for q in quarters[-6:]:
            print(f"  {q.start}..{q.end}  {q.first.value:>18,} → {q.latest.value:>18,}  {q.method}")
        restated = [q for q in quarters if q.restated]
        print(f"  quarters: {len(quarters)}, restated: {len(restated)}")

    revenue_q = get_series(engine, APPLE, "revenue", "Q")
    last8 = revenue_q[-8:]
    for a, b in zip(last8, last8[1:], strict=False):
        gap = (date.fromisoformat(b.start) - date.fromisoformat(a.end)).days
        assert gap == 1, f"revenue quarters not contiguous: {a.end} → {b.start}"

    # Cross-check with the Q3 FY2026 press release text: "quarterly revenue of $109.4 billion".
    q3 = next((q for q in revenue_q if q.end == "2026-06-27"), None)
    assert q3 is not None, "no revenue quarter ending 2026-06-27"
    print(f"\nQ3 FY2026 revenue (XBRL): {q3.latest.value:,}")
    assert abs(q3.latest.value - 109.4e9) < 0.06e9

    # TTM at a fiscal year end equals the reported FY (latest values), and derived Q4s exist.
    fy = {r.end: r for r in get_series(engine, APPLE, "revenue", "FY")}
    ttm = {r.end: r for r in get_series(engine, APPLE, "revenue", "TTM")}
    shared = sorted(set(fy) & set(ttm))[-3:]
    print(
        f"FY vs TTM at year ends: {[(e, fy[e].latest.value, ttm[e].latest.value) for e in shared]}"
    )
    assert shared
    for end in shared:
        assert abs(fy[end].latest.value - ttm[end].latest.value) <= 0.001 * fy[end].latest.value
    capex_q = get_series(engine, APPLE, "capex", "Q")
    assert any(q.method.startswith("derived") for q in capex_q), "capex quarters not derived"
    assert get_series(engine, APPLE, "eps_diluted", "TTM") == []
