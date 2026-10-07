from __future__ import annotations

import json

import pytest

from engine.sec.identity import SUBMISSIONS_URL
from engine.sec.results import Failed, NotFound, Ok
from engine.sec.submissions import (
    PAGE_URL,
    earnings_releases,
    parse_filing_arrays,
    parse_items,
    stored_filings,
    sync_filings,
)
from tests.conftest import FakeTransport, fixture_bytes, ok

CIK = "0000000042"
MAIN_URL = SUBMISSIONS_URL.format(cik=CIK)
PAGE_NAME = "CIK0000000042-submissions-001.json"
PAGE = PAGE_URL.format(name=PAGE_NAME)


def routes(page=None):
    return {
        MAIN_URL: [ok(fixture_bytes("sec/submissions_CIK0000000042.json"))],
        PAGE: [page or ok(fixture_bytes(f"sec/{PAGE_NAME}"))],
    }


def test_parse_items():
    assert parse_items("2.02,9.01") == ("2.02", "9.01")
    assert parse_items("") == ()
    assert parse_items(None) == ()


def test_parse_keeps_missing_as_none():
    recent = json.loads(fixture_bytes("sec/submissions_CIK0000000042.json"))["filings"]["recent"]
    form4 = parse_filing_arrays(CIK, recent)[-1]
    assert form4.form == "4"
    assert form4.report_date is None and form4.items == () and form4.is_xbrl is False


def test_parse_rejects_mismatched_arrays():
    with pytest.raises(ValueError, match="expected 2"):
        parse_filing_arrays(
            CIK, {"accessionNumber": ["a", "b"], "filingDate": ["d"], "form": ["f", "g"]}
        )
    with pytest.raises(ValueError, match="missing"):
        parse_filing_arrays(CIK, {"accessionNumber": []})


def test_sync_reads_recent_and_older_pages(make_client, dbs, clock):
    engine, _ = dbs
    result = sync_filings(make_client(FakeTransport(routes())), engine, "42", clock.now())
    assert isinstance(result, Ok) and result.data.complete
    assert (result.data.filings_seen, result.data.new) == (7, 7)
    assert result.data.pages_loaded == (PAGE_NAME,)

    forms = [f.form for f in stored_filings(engine, CIK)]
    assert forms == ["10-Q", "8-K", "8-K", "10-K", "4", "10-Q", "10-K/A"]  # newest first
    assert [f.form for f in stored_filings(engine, CIK, forms=["10-K", "10-K/A"])] == [
        "10-K",
        "10-K/A",
    ]
    assert len(stored_filings(engine, CIK, since="2026-01-01")) == 5


def test_earnings_releases_filter_item_202(make_client, dbs, clock):
    engine, _ = dbs
    sync_filings(make_client(FakeTransport(routes())), engine, CIK, clock.now())
    [release] = earnings_releases(engine, CIK)
    assert release.accession == "0000000042-26-000004" and release.items == ("2.02", "9.01")


def test_ingested_page_is_not_fetched_again(make_client, dbs, clock):
    engine, _ = dbs
    transport = FakeTransport(routes())
    sync_filings(make_client(transport), engine, CIK, clock.now())
    clock.advance(2 * 86400)
    again = sync_filings(make_client(transport), engine, CIK, clock.now())
    assert isinstance(again, Ok)
    assert again.data.pages_skipped == (PAGE_NAME,) and again.data.new == 0
    assert [c[0] for c in transport.calls].count(PAGE) == 1


@pytest.mark.parametrize(
    ("page", "reason"), [(ok(b"", 404), "no file at"), (ok(b"", 503), "HTTP 503")]
)
def test_failed_page_marks_sync_incomplete_and_retries(make_client, dbs, clock, page, reason):
    engine, _ = dbs
    first = sync_filings(make_client(FakeTransport(routes(page))), engine, CIK, clock.now())
    assert isinstance(first, Ok) and not first.data.complete
    assert reason in first.data.pages_failed[0]
    assert len(stored_filings(engine, CIK)) == 5  # recent rows kept

    clock.advance(2 * 86400)
    second = sync_filings(make_client(FakeTransport(routes())), engine, CIK, clock.now())
    assert isinstance(second, Ok) and second.data.complete
    assert second.data.pages_loaded == (PAGE_NAME,)
    assert len(stored_filings(engine, CIK)) == 7


def test_malformed_page_is_failure_not_fewer_filings(make_client, dbs, clock):
    engine, _ = dbs
    bad = ok(b'{"accessionNumber": ["x", "y"], "filingDate": ["d"], "form": ["f", "g"]}')
    result = sync_filings(make_client(FakeTransport(routes(bad))), engine, CIK, clock.now())
    assert isinstance(result, Ok) and "unreadable" in result.data.pages_failed[0]


def test_missing_submissions_file_is_not_found(make_client, dbs, clock):
    engine, _ = dbs
    transport = FakeTransport({MAIN_URL: [ok(b"", 404)]})
    assert isinstance(sync_filings(make_client(transport), engine, CIK, clock.now()), NotFound)


def test_unreadable_submissions_is_failure(make_client, dbs, clock):
    engine, _ = dbs
    transport = FakeTransport({MAIN_URL: [ok(b'{"name": "x"}')]})
    assert isinstance(sync_filings(make_client(transport), engine, CIK, clock.now()), Failed)


def test_accession_listed_under_two_ciks(make_client, dbs, clock):
    engine, _ = dbs
    sync_filings(make_client(FakeTransport(routes())), engine, CIK, clock.now())

    insider = "0001234567"
    data = json.loads(fixture_bytes("sec/submissions_CIK0000000042.json"))
    recent = {k: v[-1:] for k, v in data["filings"]["recent"].items()}  # the Form 4 only
    other = {"name": "An Insider", "filings": {"recent": recent, "files": []}}
    url = SUBMISSIONS_URL.format(cik=insider)
    sync_filings(
        make_client(FakeTransport({url: [ok(json.dumps(other).encode())]})),
        engine,
        insider,
        clock.now(),
    )
    [form4] = stored_filings(engine, insider)
    assert form4.accession == "0001234567-26-000001" and form4.cik == insider
    assert len(stored_filings(engine, CIK)) == 7  # still listed under the issuer
    links = engine.execute(
        "SELECT cik FROM filing_cik WHERE accession = ? ORDER BY cik", (form4.accession,)
    ).fetchall()
    assert [r[0] for r in links] == [CIK, insider]
