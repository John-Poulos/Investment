from __future__ import annotations

import json
from dataclasses import replace

import pytest

from engine.sec.documents import filing_folder
from engine.sec.insiders import (
    ingest_form4,
    parse_form4,
    raw_xml_name,
    sync_insiders,
    transactions,
)
from engine.sec.results import Empty, Failed, Ok
from engine.sec.submissions import Filing, store_filings
from tests.conftest import FakeTransport, fixture_bytes, ok

ISSUER = "0000000042"


def filing(acc, primary="xslF345X05/form4.xml", filed="2026-05-04", form="4"):
    return Filing(
        accession=acc, cik=ISSUER, form=form, filed=filed, accepted_at=None, report_date=None,
        items=(), primary_doc=primary, primary_doc_desc="FORM 4", is_xbrl=False,
        is_inline_xbrl=False, size=None,
    )  # fmt: skip


def xml_url(f, name="form4.xml"):
    return f"{filing_folder(ISSUER, f.accession)}/{name}"


NEW = fixture_bytes("sec/form4/new_10b51_checkbox.xml")
OLD = fixture_bytes("sec/form4/old_footnote_latin1.xml")
JOINT = fixture_bytes("sec/form4/joint_gift_exercise.xml")


def test_raw_xml_name():
    assert raw_xml_name("xslF345X05/wk-form4_1714.xml") == "wk-form4_1714.xml"
    assert raw_xml_name("form4.xml") == "form4.xml"
    assert raw_xml_name("primary_doc.htm") is None and raw_xml_name(None) is None


def test_parse_checkbox_form():
    form = parse_form4(NEW)
    assert (form.doc_type, form.issuer_cik, form.issuer_ticker) == ("4", ISSUER, "XSEM")
    assert form.aff_10b5_1 is True
    [owner] = form.owners
    assert owner.cik == "0001111111" and owner.role == "Officer (Chief Executive Officer)"
    [t] = form.transactions
    assert (t.code, t.shares, t.price, t.acquired_disposed, t.shares_after) == (
        "S",
        10000.0,
        201.55,
        "D",
        390000.0,
    )
    assert t.is_10b5_1 is True and t.equity_swap is False
    assert "Weighted average price" in t.footnotes["F1"]


def test_parse_old_form_uses_footnotes_and_declared_encoding():
    form = parse_form4(OLD)
    assert form.aff_10b5_1 is None
    assert form.owners[0].name == "Müller Hans"  # ISO-8859-1 decoded correctly
    assert form.owners[0].role == "Director"
    sale, buy = form.transactions
    assert sale.code == "S" and sale.is_10b5_1 is True  # footnote on the row mentions 10b5-1
    assert buy.code == "P" and buy.is_10b5_1 is None  # not disclosed, not guessed as False


def test_parse_joint_filing_gift_and_exercise():
    form = parse_form4(JOINT)
    assert form.doc_type == "4/A" and form.issuer_cik == ISSUER  # "42" normalized
    assert [o.role for o in form.owners] == ["10% Owner", "10% Owner; Other (General partner)"]
    gift, exercise = form.transactions  # the holding row is not a transaction
    assert gift.code == "G" and gift.price is None  # missing stays missing
    assert gift.is_10b5_1 is False  # checkbox explicitly unset, no 10b5-1 footnote
    assert (gift.direct_indirect, gift.nature_of_ownership) == ("I", "By fund")
    assert exercise.table_kind == "derivative" and exercise.code == "M"
    assert (exercise.conversion_price, exercise.underlying_shares) == (45.10, 3000.0)


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        (b"<ownershipDocument><documentType>3</documentType></ownershipDocument>", "not a Form 4"),
        (b"<html></html>", "not an ownershipDocument"),
        (b"<ownershipDocument><documentType>4</documentType></ownershipDocument>", "no issuer"),
        (b"<ownershipDocument", "unreadable"),
    ],
)
def test_parse_rejects_bad_documents(xml, message):
    with pytest.raises(ValueError, match=message):
        parse_form4(xml)


def test_ingest_stores_rows_and_document(make_client, dbs, clock):
    engine, _ = dbs
    f = filing("0000000042-26-000101")
    result = ingest_form4(make_client(FakeTransport({xml_url(f): [ok(NEW)]})), engine, f,
                          clock.now())  # fmt: skip
    assert isinstance(result, Ok) and result.data == 1
    [row] = transactions(engine, ISSUER)
    assert (row["owner_cik"], row["role"], row["code"], row["is_10b5_1"]) == (
        "0001111111",
        "Officer (Chief Executive Officer)",
        "S",
        1,
    )
    doc = engine.execute("SELECT * FROM form4_doc").fetchone()
    assert doc["filename"] == "form4.xml" and doc["aff_10b5_1"] == 1
    assert json.loads(doc["owners"])[0]["role"] == "Officer (Chief Executive Officer)"


def test_joint_filing_keeps_every_owner(make_client, dbs, clock):
    engine, _ = dbs
    f = filing("0000000042-26-000103", form="4/A")
    ingest_form4(make_client(FakeTransport({xml_url(f): [ok(JOINT)]})), engine, f, clock.now())
    doc = engine.execute("SELECT owners FROM form4_doc").fetchone()
    assert [o["cik"] for o in json.loads(doc["owners"])] == ["0003333333", "0003333334"]
    gift = transactions(engine, ISSUER, codes=["G"])[0]
    assert gift["price"] is None and gift["owner_name"] == "Big Fund LP"
    assert len(transactions(engine, ISSUER, table_kind="derivative")) == 1


def test_missing_xml_falls_back_to_filing_index(make_client, dbs, clock):
    engine, _ = dbs
    f = filing("0000000042-26-000104", primary="xslF345X05/gone.xml")
    folder = filing_folder(ISSUER, f.accession)
    index = (
        '<table class="tableFile" summary="Document Format Files">'
        "<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>"
        f'<tr><td>1</td><td>FORM 4</td><td><a href="{folder.removeprefix("https://www.sec.gov")}'
        '/actual.xml">actual.xml</a></td><td>4</td><td>3000</td></tr></table>'
    )
    transport = FakeTransport({
        f"{folder}/gone.xml": [ok(b"", 404)],
        f"{folder}/{f.accession}-index.htm": [ok(index.encode())],
        f"{folder}/actual.xml": [ok(NEW)],
    })  # fmt: skip
    result = ingest_form4(make_client(transport), engine, f, clock.now())
    assert isinstance(result, Ok)
    assert engine.execute("SELECT filename FROM form4_doc").fetchone()[0] == "actual.xml"


def test_no_xml_anywhere_is_empty_with_paths(make_client, dbs, clock):
    engine, _ = dbs
    f = filing("0000000042-26-000105")
    folder = filing_folder(ISSUER, f.accession)
    transport = FakeTransport({
        f"{folder}/form4.xml": [ok(b"", 404)],
        f"{folder}/{f.accession}-index.htm": [ok(b"", 404)],
        f"{folder}/{f.accession}-index.html": [ok(b"", 404)],
    })  # fmt: skip
    result = ingest_form4(make_client(transport), engine, f, clock.now())
    assert isinstance(result, Empty) and len(result.paths_checked) == 3


def test_sync_parses_new_filings_once_and_reports_failures(make_client, dbs, clock):
    engine, _ = dbs
    good, old, bad = (
        filing("0000000042-26-000101", filed="2026-05-04"),
        filing("0000000042-21-000050", filed="2021-03-17"),
        filing("0000000042-26-000102", filed="2026-05-05"),
    )
    other = replace(good, accession="0000000042-26-000200", form="10-Q", primary_doc="q.htm")
    engine.execute("BEGIN")
    store_filings(engine, [good, old, bad, other], clock.now())
    engine.execute("COMMIT")
    transport = FakeTransport({
        xml_url(good): [ok(NEW)],
        xml_url(old): [ok(OLD)],
        xml_url(bad): [ok(b"<html>not xml")],
    })  # fmt: skip

    first = sync_insiders(make_client(transport), engine, ISSUER, clock.now())
    assert isinstance(first, Ok)
    s = first.data
    assert (s.filings, s.ingested, s.already, s.transactions) == (3, 2, 0, 3)
    assert not s.complete and s.failed[0].startswith("0000000042-26-000102")

    again = sync_insiders(make_client(transport), engine, ISSUER, clock.now())
    assert again.data.already == 2 and again.data.ingested == 0  # only the failed one retried
    assert len(transactions(engine, ISSUER, since="2026-01-01")) == 1
    assert [r["code"] for r in transactions(engine, ISSUER, codes=["P"])] == ["P"]


def test_sync_stops_when_throttled(make_client, dbs, clock):
    engine, _ = dbs
    a, b = filing("0000000042-26-000301", filed="2026-06-02"), filing("0000000042-26-000302")
    engine.execute("BEGIN")
    store_filings(engine, [a, b], clock.now())
    engine.execute("COMMIT")
    transport = FakeTransport({xml_url(a): [ok(b"", 429)], xml_url(b): [ok(NEW)]})
    result = sync_insiders(make_client(transport), engine, ISSUER, clock.now())
    assert isinstance(result, Ok) and len(result.data.failed) == 1
    assert "throttle" in result.data.failed[0] and len(transport.calls) == 1


def test_parse_failure_is_failed_not_empty(make_client, dbs, clock):
    engine, _ = dbs
    f = filing("0000000042-26-000106")
    res = ingest_form4(make_client(FakeTransport({xml_url(f): [ok(b"<html/>")]})), engine, f,
                       clock.now())  # fmt: skip
    assert isinstance(res, Failed) and "ownershipDocument" in res.reason
