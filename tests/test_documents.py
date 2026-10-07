from __future__ import annotations

from dataclasses import replace

import pytest

from engine.sec.documents import (
    document_text,
    fetch_filing_index,
    html_to_text,
    ingest_filing,
    parse_filing_index,
    strip_viewer,
)
from engine.sec.results import Empty, Failed, Ok
from engine.sec.submissions import Filing
from tests.conftest import FakeTransport, fixture_bytes, ok

CIK = "0000000042"
ACC = "0000000042-26-000004"
FOLDER = "https://www.sec.gov/Archives/edgar/data/42/000000004226000004"
INDEX_URL = f"{FOLDER}/{ACC}-index.htm"
INDEX_HTML_URL = f"{FOLDER}/{ACC}-index.html"
DOC_8K = f"{FOLDER}/xsem-8k_20260730.htm"
DOC_EX99 = f"{FOLDER}/ex99-1.htm"

FILING = Filing(
    accession=ACC,
    cik=CIK,
    form="8-K",
    filed="2026-07-30",
    accepted_at=None,
    report_date="2026-07-30",
    items=("2.02", "9.01"),
    primary_doc="xsem-8k_20260730.htm",
    primary_doc_desc="8-K",
    is_xbrl=True,
    is_inline_xbrl=True,
    size=45000,
)


def routes(**overrides):
    base = {
        INDEX_URL: [ok(fixture_bytes(f"sec/filing/{ACC}-index.htm"))],
        DOC_8K: [ok(fixture_bytes("sec/filing/xsem-8k_20260730.htm"))],
        DOC_EX99: [ok(fixture_bytes("sec/filing/ex99-1.htm"))],
    }
    base.update(overrides)
    return base


def test_strip_viewer():
    assert (
        strip_viewer("/ix?doc=/Archives/edgar/data/1/2/a.htm") == "/Archives/edgar/data/1/2/a.htm"
    )
    assert strip_viewer("/Archives/edgar/data/1/2/a.htm") == "/Archives/edgar/data/1/2/a.htm"


def test_parse_filing_index():
    docs = parse_filing_index(fixture_bytes(f"sec/filing/{ACC}-index.htm").decode())
    assert [d.doc_type for d in docs] == ["8-K", "EX-99.1", "GRAPHIC", None]  # Data Files excluded
    primary = docs[0]
    assert primary.url == DOC_8K and primary.inline_xbrl and primary.seq == 1
    assert primary.size == 45000
    assert docs[1].description == "PRESS RELEASE" and not docs[1].inline_xbrl
    full_text = docs[3]
    assert full_text.seq is None and full_text.description == "Complete submission text file"


def test_parse_filing_index_without_table_fails():
    with pytest.raises(ValueError, match="no 'Document Format Files' table"):
        parse_filing_index("<html><body>nothing</body></html>")


def test_html_to_text():
    text = html_to_text(fixture_bytes("sec/filing/xsem-8k_20260730.htm").decode())
    assert "Item 2.02 Results of Operations" in text  # &#160; decoded to a space
    assert "July 30, 2026" in text  # &nbsp;
    assert "Company’s release" in text  # &#8217;
    assert "UNITED STATES\nSECURITIES" in text  # <br> is a line break
    for junk in ("hiddenjunk", "dei:DocumentType", "do not keep", "margin:0", "xsem-8k"):
        assert junk not in text


def test_html_tables_keep_cells_apart():
    text = html_to_text(fixture_bytes("sec/filing/ex99-1.htm").decode())
    assert "Net sales\t$\t1,200\t$\t950" in text


def test_index_falls_back_to_html_then_reports_paths(make_client):
    html_index = fixture_bytes(f"sec/filing/{ACC}-index.htm")
    transport = FakeTransport({INDEX_URL: [ok(b"", 404)], INDEX_HTML_URL: [ok(html_index)]})
    found = fetch_filing_index(make_client(transport), CIK, ACC)
    assert isinstance(found, Ok) and found.source_ref == INDEX_HTML_URL

    missing = FakeTransport({INDEX_URL: [ok(b"", 404)], INDEX_HTML_URL: [ok(b"", 404)]})
    neither = fetch_filing_index(make_client(missing, cached=False), CIK, ACC)
    assert isinstance(neither, Empty)
    assert [p.query for p in neither.paths_checked] == [INDEX_URL, INDEX_HTML_URL]


def test_ingest_stores_primary_and_ex99_whole(make_client, dbs, clock):
    _, corpus = dbs
    result = ingest_filing(make_client(FakeTransport(routes())), corpus, FILING, clock.now())
    assert isinstance(result, Ok) and result.data.complete
    assert [d.doc_type for d in result.data.stored] == ["8-K", "EX-99.1"]
    assert result.data.not_listed == ()

    ex99 = result.data.stored[1]
    text = document_text(corpus, ex99.doc_id)
    assert text is not None and len(text) == ex99.chars
    row = corpus.execute("SELECT * FROM document WHERE doc_id = ?", (ex99.doc_id,)).fetchone()
    assert row["parser_version"] == "html-text-1" and row["raw_size"] > 0
    assert row["description"] == "PRESS RELEASE"
    section = corpus.execute("SELECT * FROM section WHERE doc_id = ?", (ex99.doc_id,)).fetchone()
    assert (section["label"], section["start_offset"], section["end_offset"]) == (
        "whole",
        0,
        len(text),
    )
    hits = corpus.execute(
        "SELECT rowid FROM section_fts WHERE section_fts MATCH 'HBM3E'"
    ).fetchall()
    assert [h[0] for h in hits] == [section["section_id"]]


def test_ingest_skips_stored_documents(make_client, dbs, clock):
    _, corpus = dbs
    transport = FakeTransport(routes())
    ingest_filing(make_client(transport), corpus, FILING, clock.now())
    again = ingest_filing(make_client(transport), corpus, FILING, clock.now())
    assert isinstance(again, Ok) and not any(d.new for d in again.data.stored)
    assert [c[0] for c in transport.calls].count(DOC_8K) == 1


def test_ingest_reports_missing_and_failed_documents(make_client, dbs, clock):
    _, corpus = dbs
    transport = FakeTransport(routes(**{DOC_EX99: [ok(b"", 404)]}))
    result = ingest_filing(
        make_client(transport), corpus, FILING, clock.now(), types=["8-K", "EX-99.1", "EX-99.2"]
    )
    assert isinstance(result, Ok) and not result.data.complete
    assert "ex99-1.htm: no file at" in result.data.failed[0]
    assert result.data.not_listed == ("EX-99.2",)
    assert [d.doc_type for d in result.data.stored] == ["8-K"]


def test_ingest_propagates_index_failure(make_client, dbs, clock):
    _, corpus = dbs
    transport = FakeTransport({INDEX_URL: [ok(b"", 503)]})
    assert isinstance(ingest_filing(make_client(transport), corpus, FILING, clock.now()), Failed)


def test_ex99_is_a_default_only_for_8k(make_client, dbs, clock):
    _, corpus = dbs
    transport = FakeTransport(routes())
    ten_k = replace(FILING, form="10-K")
    result = ingest_filing(make_client(transport), corpus, ten_k, clock.now())
    assert isinstance(result, Ok)
    assert result.data.not_listed == ("10-K",)  # only the form itself was wanted
    assert DOC_EX99 not in [c[0] for c in transport.calls]
