from __future__ import annotations

import pytest

from engine.sec.documents import filing_folder
from engine.sec.events import CATALOG, build_events, classify_filing, events, ingest_event_documents
from engine.sec.results import Ok
from engine.sec.submissions import Filing, store_filings
from tests.conftest import FakeTransport, fixture_bytes, ok

CIK = "0000000042"


def filing(acc, form="8-K", items=(), filed="2026-07-30", primary="x.htm"):
    return Filing(
        accession=acc, cik=CIK, form=form, filed=filed, accepted_at=f"{filed}T20:00:00.000Z",
        report_date=filed, items=items, primary_doc=primary, primary_doc_desc=form,
        is_xbrl=None, is_inline_xbrl=None, size=None,
    )  # fmt: skip


FILINGS = [
    filing("0000000042-26-000010", items=("2.02", "9.01"), filed="2026-07-30"),
    filing("0000000042-26-000011", items=("4.02",), filed="2026-08-15"),
    filing("0000000042-26-000012", form="8-K/A", items=("4.02", "9.01"), filed="2026-08-20"),
    filing("0000000042-26-000013", items=("5.02", "9.01"), filed="2026-06-01"),
    filing("0000000042-26-000014", items=("1.01", "2.03", "9.01"), filed="2026-05-10"),
    filing("0000000042-26-000015", items=("9.01",), filed="2026-05-01"),
    filing("0000000042-03-000001", items=("5", "7"), filed="2003-04-01"),  # pre-2004 numbering
    filing("0000000042-26-000016", items=(), filed="2026-04-01"),
    filing("0000000042-26-000017", form="6-K", filed="2026-03-01"),
    filing("0000000042-26-000018", form="10-Q", filed="2026-08-05"),
]


@pytest.fixture
def built(dbs, clock):
    engine, _ = dbs
    engine.execute("BEGIN")
    store_filings(engine, FILINGS, clock.now())
    engine.execute("COMMIT")
    result = build_events(engine, CIK)
    assert isinstance(result, Ok)
    return engine, result.data


def test_catalog_covers_every_current_8k_item():
    expected = {
        "1.01", "1.02", "1.03", "1.04", "1.05", "2.01", "2.02", "2.03", "2.04", "2.05", "2.06",
        "3.01", "3.02", "3.03", "4.01", "4.02", "5.01", "5.02", "5.03", "5.04", "5.05", "5.06",
        "5.07", "5.08", "6.01", "6.02", "6.03", "6.04", "6.05", "6.06", "6.10", "7.01", "8.01",
        "9.01",
    }  # fmt: skip
    assert set(CATALOG) == expected
    assert CATALOG["4.02"].severity == "high" and CATALOG["4.02"].category == "red_flag"
    assert CATALOG["2.02"].category == "earnings" and "M11" in CATALOG["2.02"].modules


def test_one_event_per_item(built):
    _, summary = built
    assert summary.filings == 9  # the 10-Q is not a current report
    assert summary.events == 15  # 2 + 1 + 2 + 2 + 3 + 1 + 2 (pre-2004) + 1 (unlisted) + 1 (6-K)
    assert summary.by_category["earnings"] == 1
    assert summary.by_category["red_flag"] == 2
    assert summary.unknown_items == {"5": 1, "7": 1, "unlisted": 1}  # kept, not dropped


def test_amendment_and_foreign_report(built):
    engine, _ = built
    amended = [e for e in events(engine, CIK, categories=["red_flag"]) if e.amended]
    assert [(e.form, e.item) for e in amended] == [("8-K/A", "4.02")]
    [foreign] = events(engine, CIK, categories=["foreign_report"])
    assert foreign.item == "6-K" and foreign.severity == "low"


def test_query_by_severity_and_date(built):
    engine, _ = built
    high = events(engine, CIK, min_severity="high")
    assert [(e.filed, e.item) for e in high] == [("2026-08-20", "4.02"), ("2026-08-15", "4.02")]
    recent = events(engine, CIK, since="2026-07-01", min_severity="medium")
    assert [e.item for e in recent] == ["4.02", "4.02", "2.02"]  # 9.01 is severity none
    with pytest.raises(ValueError):
        events(engine, CIK, min_severity="urgent")


def test_rebuild_is_idempotent(built):
    engine, first = built
    second = build_events(engine, CIK)
    assert second.data.events == first.events
    assert engine.execute("SELECT count(*) FROM event").fetchone()[0] == first.events


def test_classify_ignores_other_forms():
    assert classify_filing(filing("a", form="10-K")) == []


def test_ingest_event_documents_stores_item_sections(built, dbs, make_client, clock):
    engine, _ = built
    _, corpus = dbs
    acc = "0000000042-26-000004"
    f = filing(acc, items=("2.02", "9.01"), primary="xsem-8k_20260730.htm")
    engine.execute("BEGIN")
    store_filings(engine, [f], clock.now())
    engine.execute("COMMIT")
    build_events(engine, CIK)
    folder = filing_folder(CIK, acc)
    transport = FakeTransport({
        f"{folder}/{acc}-index.htm": [ok(fixture_bytes(f"sec/filing/{acc}-index.htm"))],
        f"{folder}/xsem-8k_20260730.htm": [ok(fixture_bytes("sec/filing/xsem-8k_20260730.htm"))],
        f"{folder}/ex99-1.htm": [ok(fixture_bytes("sec/filing/ex99-1.htm"))],
    })  # fmt: skip
    earnings = [e for e in events(engine, CIK, categories=["earnings"]) if e.accession == acc]
    result = ingest_event_documents(make_client(transport), engine, corpus, earnings, clock.now())
    assert isinstance(result, Ok) and result.data.complete
    assert [d.doc_type for d in result.data.stored[acc].stored] == ["8-K", "EX-99.1"]
    labels = [r[0] for r in corpus.execute("SELECT label FROM section ORDER BY section_id")]
    assert "8-K Item 2.02" in labels


def test_ingest_event_documents_lists_failures(built, dbs, make_client, clock):
    engine, _ = built
    _, corpus = dbs
    [ev] = [e for e in events(engine, CIK) if e.item == "5.02"]
    folder = filing_folder(CIK, ev.accession)
    transport = FakeTransport({f"{folder}/{ev.accession}-index.htm": [ok(b"", 503)]})
    result = ingest_event_documents(make_client(transport), engine, corpus, [ev], clock.now())
    assert isinstance(result, Ok) and not result.data.complete
    assert result.data.failed[0].startswith(ev.accession)
