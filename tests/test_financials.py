# ruff: noqa: E501  (fixture rows)
"""M04 Part 1a: as-of facts, concept fixes, R1 cover reader, share series, filing status,
signal writer, refresh hooks and the Financials tab (docs/M04_BUILD_LOG.md Part 1a)."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine.financials import shares, status, step
from engine.refresh import IndexEntry, facts_due
from engine.sec import cover
from engine.sec.asof import facts_as_of, is_foreign_filer
from engine.sec.results import NotFound, Ok
from engine.sec.xbrl_facts import (
    ALL_CONCEPTS,
    CONCEPT_BY_NAME,
    CONCEPTS,
    concept_for,
    forces_facts,
    get_series,
    rebuild_series,
    store_concept,
    sync_facts,
)
from engine.signals import Source, write_signal
from tests.conftest import FIXTURES, FakeTransport, ok

M04 = FIXTURES / "m04"
MU, WDC, GOOGL, GOOG_INC = "0000723125", "0000106040", "0001652044", "0001288776"
INFQ, NVTA, META, MSTR, SPCX, GFS = ("0002007825", "0001501134", "0001326801", "0001050446",
                                     "0001181412", "0001709048")  # fmt: skip


def load(engine: sqlite3.Connection, cik: str, name: str) -> None:
    engine.execute("BEGIN")
    store_concept(engine, cik, json.loads((M04 / name).read_text(encoding="utf-8")))
    engine.execute("COMMIT")


def filing(engine, cik, acc, form, filed, report=None, is_xbrl=None):
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, report_date, is_xbrl, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'x')",
        (acc, cik, form, filed, report, is_xbrl),
    )
    engine.execute("INSERT INTO filing_cik (accession, cik) VALUES (?, ?)", (acc, cik))


def fact(engine, cik, tag, start, end, value, acc, filed, form, taxonomy="us-gaap", unit="USD"):
    engine.execute(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession, "
        "form, filed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cik, taxonomy, tag, unit, start, end, value, acc, form, filed),
    )


# --- As-of facts (S1.1) --------------------------------------------------------------------


def test_wdc_fy2023_revenue_as_of_2024_is_the_first_report(dbs):
    engine, _ = dbs
    load(engine, WDC, "wdc_us-gaap_Revenues_20261012.json")
    load(
        engine, WDC, "wdc_us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax_20261012.json"
    )
    then = facts_as_of(engine, WDC, "revenue", "2024-12-31").get("2023-06-30", "FY")
    assert then.value == 12_318_000_000 and then.accession == "0000106040-24-000022"
    assert then.first_filed == "2023-08-25"
    now = facts_as_of(engine, WDC, "revenue", "2026-01-01").get("2023-06-30", "FY")
    assert now.value == 6_255_000_000  # the SanDisk recast, known only from 2025-08-19
    assert now.first_value == 12_318_000_000 and now.restated
    assert "first filed 2023-08-25 under us-gaap:Revenues" in now.method


def test_mu_fy2018_revenue_known_from_2018_10_15_despite_the_tag_switch(dbs):
    engine, _ = dbs
    load(engine, MU, "mu_us-gaap_Revenues_20261012.json")
    load(engine, MU, "mu_us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax_20261012.json")
    rebuild_series(engine, MU)
    shown = [r for r in get_series(engine, MU, "revenue", "FY") if r.end == "2018-08-30"][0]
    assert shown.first.filed == "2019-10-17"  # series (display) keeps tag priority first
    early = facts_as_of(engine, MU, "revenue", "2018-11-01").get("2018-08-30", "FY")
    assert early.value == 30_391_000_000 and early.filed == "2018-10-15"
    assert "us-gaap:Revenues" in early.method
    later = facts_as_of(engine, MU, "revenue", "2020-01-01").get("2018-08-30", "FY")
    assert later.first_filed == "2018-10-15" and later.filed == "2019-10-17"


def test_alphabet_2023_net_income_never_from_a_proxy_statement(dbs):
    engine, _ = dbs
    load(engine, GOOGL, "googl_us-gaap_NetIncomeLoss_20261012.json")
    rebuild_series(engine, GOOGL)
    shown = [r for r in get_series(engine, GOOGL, "net_income", "FY") if r.end == "2023-12-31"][0]
    assert shown.latest.accession == "0001308179-26-000342"  # the defect `series` still shows
    res = facts_as_of(engine, GOOGL, "net_income", "2026-06-30")
    p = res.get("2023-12-31", "FY")
    assert p.accession == "0001652044-26-000018" and p.value == 73_795_000_000
    assert res.excluded == {"form DEF 14A (not a periodic report)": 1}


def test_predecessor_cik_read_up_to_its_boundary(dbs):
    engine, _ = dbs
    fact(engine, GOOG_INC, "NetIncomeLoss", "2014-01-01", "2014-12-31", 14_444_000_000,
         "0001288776-15-000008", "2015-02-06", "10-K")  # fmt: skip
    fact(
        engine,
        GOOG_INC,
        "NetIncomeLoss",
        "2014-01-01",
        "2014-12-31",
        1,
        "0001288776-16-000099",
        "2016-03-01",
        "10-K",
    )  # filed after the boundary: ignored
    p = facts_as_of(engine, GOOGL, "net_income", "2015-06-01").get("2014-12-31", "FY")
    assert p.value == 14_444_000_000 and "predecessor CIK: Google Inc." in p.method
    res = facts_as_of(engine, GOOGL, "net_income", "2026-06-01")
    assert res.get("2014-12-31", "FY").value == 14_444_000_000
    assert res.excluded["predecessor CIK filing after the boundary"] == 1


def test_de_spac_shell_periods_keyed_on_period_end(dbs):
    engine, _ = dbs
    filing(engine, INFQ, "A10K", "10-K", "2026-03-31", "2025-12-31")
    filing(engine, INFQ, "A10Q", "10-Q", "2026-08-18", "2026-06-30")
    fact(
        engine,
        INFQ,
        "NetIncomeLoss",
        "2025-01-01",
        "2025-12-31",
        -66_931_068,
        "A10K",
        "2026-03-31",
        "10-K",
    )
    fact(
        engine,
        INFQ,
        "NetIncomeLoss",
        "2025-01-01",
        "2025-12-31",
        -32_228_000,
        "A10Q",
        "2026-08-18",
        "10-Q",
    )
    after = facts_as_of(engine, INFQ, "net_income", "2026-09-01")
    assert after.get("2025-12-31", "FY").value == -32_228_000  # Infleqtion, not the SPAC
    assert after.excluded["shell (pre-closing document)"] == 1
    assert facts_as_of(engine, INFQ, "net_income", "2026-04-30").get("2025-12-31", "FY") is None
    shell = facts_as_of(engine, INFQ, "net_income", "2026-04-30", include_shell=True)
    assert shell.get("2025-12-31", "FY").value == -66_931_068


def test_6k_counts_only_for_a_20f_filer(dbs):
    engine, _ = dbs
    fact(
        engine,
        GFS,
        "Revenue",
        "2025-01-01",
        "2025-12-31",
        6_800_000_000,
        "G20F",
        "2026-03-20",
        "20-F",
        "ifrs-full",
    )
    fact(
        engine,
        GFS,
        "Revenue",
        "2026-04-01",
        "2026-06-30",
        1_700_000_000,
        "G6K",
        "2026-08-05",
        "6-K",
        "ifrs-full",
    )
    assert is_foreign_filer(engine, GFS)
    res = facts_as_of(engine, GFS, "revenue", "2026-09-01")
    assert res.get("2026-06-30", "Q").accession == "G6K"
    fact(engine, MU, "Revenues", "2026-04-01", "2026-06-30", 5, "M6K", "2026-08-05", "6-K")
    assert facts_as_of(engine, MU, "revenue", "2026-09-01").get("2026-06-30", "Q") is None


# --- Concepts (S1.3, SB.18) ------------------------------------------------------------------


def test_concept_fixes_and_per_company_aliases():
    da = CONCEPT_BY_NAME["da"]
    assert ("us-gaap", "DepreciationAndAmortization") not in da.tags  # nonproduction concept
    assert da.tags[-1] == ("us-gaap", "Depreciation") and "narrower" in da.mark(
        "us-gaap", "Depreciation"
    )
    ppe = CONCEPT_BY_NAME["ppe_net"]
    assert "broader tag" in ppe.label(*ppe.tags[-1])
    general = {t for c in ALL_CONCEPTS.values() for t in c.tags}
    assert ("us-gaap", "CommodityContractAssetNoncurrent") not in general  # never mapped generally
    ge = concept_for("0000040545", ALL_CONCEPTS["contract_assets"])
    assert ("us-gaap", "CommodityContractAssetNoncurrent") in ge.tags
    assert concept_for(MU, ALL_CONCEPTS["contract_assets"]) == ALL_CONCEPTS["contract_assets"]
    nvda = concept_for("0001045810", CONCEPT_BY_NAME["short_term_investments"])
    assert nvda.tags[-1] == ("nvda", "MarketableSecuritiesAndEquitySecuritiesFVNI")
    names = {c.name for c in CONCEPTS}
    assert {
        "shares_period_end",
        "shares_cover",
        "shares_basic_wavg",
        "shares_diluted_wavg",
        "sbc",
    } <= names


def test_marks_reach_the_series_method(dbs):
    engine, _ = dbs
    fact(engine, MU, "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
         None, "2026-09-03", 60_000_000_000, "K26", "2026-10-03", "10-K")  # fmt: skip
    rebuild_series(engine, MU)
    (row,) = get_series(engine, MU, "ppe_net", "I")
    assert "[≈ broader tag: includes finance-lease right-of-use assets]" in row.method


# --- R1 cover reader (D-M04-2) ---------------------------------------------------------------


def r1(name: str) -> cover.CoverRead:
    return cover.read_cover(cover.parse_r_html((M04 / name).read_text(encoding="utf-8")))


def test_meta_r1_classes_summed_on_the_cover_date():
    read = r1("meta_10k_fy2025_R1.htm")
    assert read.is_cover and read.document_type == "10-K"
    assert read.classes == [
        ("Class A Common Stock", 2_187_177_748),
        ("Class B Common Stock", 342_377_716),
    ]
    assert read.total == 2_529_555_464 and read.cover_date == "2026-01-23"
    assert read.error_correction_flag is False


def test_mstr_2011_r1_classes_in_columns():
    read = r1("mstr_10q_2011q2_R1.htm")
    assert read.classes == [("Class A", 8_217_394), ("Class B", 2_492_830)]
    assert read.cover_date == "2011-07-27" and read.error_correction_flag is None


def test_spcx_r1_member_rows():
    read = r1("spcx_10q_2026q2_R1.htm")
    assert [c for c, _ in read.classes] == ["Common Class A", "Common Class B"]
    assert read.cover_date == "2026-08-10" and read.document_type == "10-Q"


def test_google_2009_r1_is_not_a_cover():
    read = r1("goog_inc_10q_2009q2_R1.htm")
    assert not read.is_cover and read.classes == [] and "not a cover" in read.notes[0]


def test_xml_rendered_r_page():
    xml = (b"<InstanceReport><ReportName>Document and Entity Information</ReportName><Columns>"
           b"<Column><Id>1</Id><Labels><Label Id='1' Label='Jul. 27, 2011' /><Label Id='2' Label='Class A [Member]' /></Labels></Column>"
           b"<Column><Id>2</Id><Labels><Label Id='1' Label='Jul. 27, 2011' /><Label Id='2' Label='Class B [Member]' /></Labels></Column>"
           b"</Columns><Rows><Row><Label>Document Type</Label><Cells><Cell><Id>1</Id><IsNumeric>false</IsNumeric><NonNumbericText>10-Q</NonNumbericText></Cell></Cells></Row>"
           b"<Row><Label>Entity Common Stock, Shares Outstanding</Label><Cells>"
           b"<Cell><Id>1</Id><IsNumeric>true</IsNumeric><NumericAmount>8217394</NumericAmount></Cell>"
           b"<Cell><Id>2</Id><IsNumeric>true</IsNumeric><NumericAmount>2492830</NumericAmount></Cell>"
           b"</Cells></Row></Rows></InstanceReport>")  # fmt: skip
    read = cover.read_cover(cover.parse_r_xml(xml))
    assert read.classes == [("Class A", 8_217_394), ("Class B", 2_492_830)]


def test_fetch_cover_stores_once_and_split_guard_scales_mstr(make_client, dbs, clock):
    engine, _ = dbs
    acc = "0001193125-11-205391"
    filing(engine, MSTR, acc, "10-Q", "2011-07-29", "2011-06-30")
    htm, _xml = cover.r1_urls(MSTR, acc)
    transport = FakeTransport({htm: [ok((M04 / "mstr_10q_2011q2_R1.htm").read_bytes())]})
    f = engine.execute("SELECT * FROM filing WHERE accession = ?", (acc,)).fetchone()
    res = cover.fetch_cover(make_client(transport), engine, MSTR, f, clock.now())
    assert isinstance(res, Ok) and cover.r1_done(engine, acc)
    assert engine.execute("SELECT count(*) FROM cover_shares").fetchone()[0] == 2
    (v,) = shares.cover_counts(engine, MSTR)
    assert v.value == 10_710_224 and v.note == "split check: no price history stored"
    engine.execute("INSERT INTO price_fetch (symbol, cik) VALUES ('MSTR', ?)", (MSTR,))
    engine.execute("INSERT INTO price_bar (symbol, date, close, split_factor, source, fetched_at) "
                   "VALUES ('MSTR', '2024-08-08', 130.0, 10, 'tiingo', 'x')")  # fmt: skip
    (v,) = shares.cover_counts(engine, MSTR)
    assert v.value == 107_102_240 and v.classes[0] == ("Class A", 82_173_940)
    assert v.note == "split-adjusted ×10 (2024-08-08 ×10)"


def test_fetch_cover_records_a_missing_page(make_client, dbs, clock):
    engine, _ = dbs
    filing(engine, SPCX, "S1", "10-Q", "2026-08-12", "2026-06-30")
    htm, xml = cover.r1_urls(SPCX, "S1")
    transport = FakeTransport({htm: [ok(b"", 404)], xml: [ok(b"", 404)]})
    f = engine.execute("SELECT * FROM filing WHERE accession = 'S1'").fetchone()
    assert isinstance(
        cover.fetch_cover(make_client(transport), engine, SPCX, f, clock.now()), NotFound
    )
    assert cover.r1_outcome(engine, "S1")["outcome"] == "not_found"


def test_multi_class_detection_and_missing_reason(dbs):
    engine, _ = dbs
    filing(engine, META, "K25", "10-K", "2026-01-29", "2025-12-31")
    fact(engine, META, "WeightedAverageNumberOfSharesOutstandingBasic", "2025-01-01", "2025-12-31",
         2_530_000_000, "K25", "2026-01-29", "10-K", unit="shares")  # fmt: skip
    assert shares.needs_r1(engine, META)
    rows = {r.series: r for r in shares.share_rows(engine, META)}
    assert (
        rows["shares_cover"].missing == "missing: multi-class, no total tag (R1 page not read yet)"
    )
    filing(engine, MU, "MK", "10-K", "2026-10-03", "2026-09-03")
    fact(engine, MU, "EntityCommonStockSharesOutstanding", None, "2026-09-25", 1_120_000_000, "MK",
         "2026-10-03", "10-K", taxonomy="dei", unit="shares")  # fmt: skip
    assert not shares.needs_r1(engine, MU)


def test_not_a_cover_falls_back_to_basic_weighted_average(dbs, clock):
    engine, _ = dbs
    filing(engine, GOOG_INC, "G09", "10-Q", "2009-08-07", "2009-06-30")
    fact(engine, GOOG_INC, "WeightedAverageNumberOfSharesOutstandingBasic", "2009-04-01", "2009-06-30",
         316_000_000, "G09", "2009-08-07", "10-Q", unit="shares")  # fmt: skip
    rebuild_series(engine, GOOG_INC)
    read = r1("goog_inc_10q_2009q2_R1.htm")
    cover.store_cover(engine, GOOG_INC, {"accession": "G09", "form": "10-Q", "filed": "2009-08-07"},
                      read, "u", "not_cover", clock.now())  # fmt: skip
    row = shares.share_rows(engine, GOOG_INC)[0]
    assert row.values[0].value == 316_000_000
    assert row.values[0].note.startswith("basic weighted average (no cover count)")


def test_implied_float_is_float_over_close(dbs):
    engine, _ = dbs
    load(engine, NVTA, "nvta_dei_EntityPublicFloat_20261012.json")
    rebuild_series(engine, NVTA)
    engine.execute("INSERT INTO price_fetch (symbol, cik) VALUES ('NVTA', ?)", (NVTA,))
    engine.execute("INSERT INTO price_bar (symbol, date, close, split_factor, source, fetched_at) "
                   "VALUES ('NVTA', '2022-06-30', 2.44, 1, 'tiingo', 'x')")  # fmt: skip
    latest, older = shares.implied_float(engine, NVTA)
    assert latest.value == pytest.approx(569_800_000 / 2.44)
    assert latest.note.startswith("implied: float $569.8M ÷ close $2.44 on 2022-06-30")
    assert older.value is None and older.note.startswith("missing: no close on 2021-06-30")


# --- Filing status (S1.6, D-M04-36, D-M04-61) ------------------------------------------------


def invitae(engine):
    load(engine, NVTA, "nvta_dei_EntityPublicFloat_20261012.json")
    load(engine, NVTA, "nvta_dei_EntityCommonStockSharesOutstanding_20261012.json")
    for acc, form, filed, report in (
        ("K21", "10-K", "2022-02-24", "2021-12-31"), ("Q122", "10-Q", "2022-05-05", "2022-03-31"),
        ("Q222", "10-Q", "2022-08-04", "2022-06-30"), ("Q322", "10-Q", "2022-11-08", "2022-09-30"),
        ("K22", "10-K", "2023-02-28", "2022-12-31"), ("Q123", "10-Q", "2023-05-09", "2023-03-31"),
        ("Q223", "10-Q", "2023-08-08", "2023-06-30"), ("Q323", "10-Q", "2023-11-08", "2023-09-30"),
    ):  # fmt: skip
        filing(engine, NVTA, acc, form, filed, report)
    engine.execute("INSERT INTO price_fetch (symbol, cik) VALUES ('NVTA', ?)", (NVTA,))
    engine.execute("INSERT INTO price_bar (symbol, date, close, split_factor, source, fetched_at) "
                   "VALUES ('NVTA', '2023-06-30', 1.13, 1, 'tiingo', 'x')")  # fmt: skip


def test_rule_12b2_exit_lines_apply_only_to_an_issuer_in_the_category():
    assert status.next_category(status.LARGE, 569.8e6, None) == status.LARGE
    assert status.next_category(None, 569.8e6, None) == status.ACCEL  # entry-line reading
    assert status.next_category(status.LARGE, 301.7e6, None) == status.ACCEL
    assert status.next_category(status.ACCEL, 65e6, None) == status.ACCEL
    assert status.next_category(None, 65e6, None) == status.NON
    assert status.next_category(None, 900e6, 50e6) == status.LARGE
    assert status.next_category(None, 300e6, 50e6) == status.NON  # SRC revenue test


def test_invitae_fy2022_current_and_fy2023_overdue(dbs):
    engine, _ = dbs
    invitae(engine)
    rows = {r.period_end: r for r in status.evaluate(engine, NVTA, "2024-04-01")}
    fy22 = rows["2022-12-31"]
    assert (fy22.category, fy22.due_date, fy22.filed, fy22.status) == (
        status.LARGE,
        "2023-03-01",
        "2023-02-28",
        "current",
    )
    assert fy22.note.startswith("filed 1 days before due")
    fy23 = rows["2023-12-31"]
    assert (fy23.form, fy23.category, fy23.due_date, fy23.status) == (
        "10-K",
        status.ACCEL,
        "2024-03-15",
        "overdue",
    )
    assert "float estimated $301.7M" in fy23.category_source
    assert rows["2023-03-31"].deadline_days == 40  # 10-Qs of FY2023 follow FY2022's category
    before = {r.period_end: r for r in status.evaluate(engine, NVTA, "2024-03-01")}
    assert before["2023-12-31"].status == "stale"


def test_deadlines_nt_extension_weekend_and_foreign():
    due, days = status.due_date("2025-12-31", "annual", "10-K", status.LARGE, nt=False)
    assert (due.isoformat(), days) == ("2026-03-02", 60)  # Sunday 2026-03-01 → Monday
    due, _ = status.due_date("2025-12-31", "annual", "10-K", status.ACCEL, nt=True)
    assert due.isoformat() == "2026-03-31"  # 75 + 15
    due, _ = status.due_date("2026-06-30", "quarterly", "10-Q", None, nt=False)
    assert due.isoformat() == "2026-08-14"  # unknown category → longest (45)
    due, days = status.due_date("2025-12-31", "annual", "20-F", None, nt=False)
    assert (due.isoformat(), days) == ("2026-04-30", None)


def test_next_expected_period_without_a_year_of_history(dbs):
    engine, _ = dbs
    filing(engine, META, "K25", "10-K", "2026-01-29", "2025-12-31")
    filing(engine, META, "Q126", "10-Q", "2026-04-30", "2026-03-31")
    filing(engine, META, "Q226", "10-Q", "2026-07-30", "2026-06-30")
    rows = status.evaluate(engine, META, "2026-10-12", live_category="Large accelerated filer")
    last = rows[-1]
    assert (last.period_end, last.form, last.due_date, last.status) == (
        "2026-09-30",
        "10-Q",
        "2026-11-09",
        "stale",
    )  # month-end quarters, not +91 days
    filing(engine, MU, "MK", "10-K", "2026-10-03", "2026-09-03")
    rows = status.evaluate(engine, MU, "2026-12-20", live_category="Large accelerated filer")
    assert rows[-1].period_end == "2026-12-03"  # 13-week quarter


def test_local_pass_writes_status_rows_and_signals(dbs):
    engine, _ = dbs
    invitae(engine)
    lines = step.run_local_part(engine, None, {"NVTA": NVTA}, datetime(2024, 4, 1, tzinfo=UTC))
    assert "overdue 1" in lines[1] and "NVTA: overdue" in lines[2]
    sig = engine.execute("SELECT * FROM signal WHERE signal = 'filing_status'").fetchall()
    assert {r["timeframe"] for r in sig} == {"MY", "PT", "ST"}
    assert {(r["value"], r["value_text"], r["as_of"], r["source_ref"]) for r in sig} == {
        (None, "overdue", "2024-03-15", "Q323")
    }
    cov = engine.execute("SELECT * FROM signal WHERE signal = 'shares_cover'").fetchall()
    assert cov[0]["value"] == 267_014_064 and "info (weight 0)" in cov[0]["method"]
    assert engine.execute("SELECT count(*) FROM filing_status").fetchone()[0] == 9


# --- Facts sync trigger (SB.11) ----------------------------------------------------------------


def test_6k_with_xbrl_forces_a_facts_sync_and_without_does_not(dbs):
    engine, _ = dbs
    assert forces_facts("6-K", 1) and not forces_facts("6-K", 0) and not forces_facts("6-K", None)
    assert forces_facts("10-KT", None) and forces_facts("20-F", None)
    filing(engine, GFS, "X6K", "6-K", "2026-08-05", is_xbrl=1)
    filing(engine, GFS, "N6K", "6-K", "2026-05-06", is_xbrl=0)
    assert facts_due(engine, [IndexEntry(GFS, "GF", "6-K", "2026-08-05", "X6K")])
    assert not facts_due(engine, [IndexEntry(GFS, "GF", "6-K", "2026-05-06", "N6K")])


def test_xbrl_6k_makes_companyfacts_due(make_client, dbs, clock):
    from engine.sec.xbrl_facts import FACTS_URL

    engine, _ = dbs
    body = json.dumps({"facts": {}}).encode()
    transport = FakeTransport({FACTS_URL.format(cik=GFS): [ok(body)]})
    sync_facts(make_client(transport), engine, GFS, clock.now())
    filing(engine, GFS, "N6K", "6-K", clock.now().date().isoformat(), is_xbrl=0)
    clock.advance(7 * 3600)
    assert not sync_facts(make_client(transport), engine, GFS, clock.now()).data.refreshed
    filing(engine, GFS, "X6K", "6-K", clock.now().date().isoformat(), is_xbrl=1)
    assert sync_facts(make_client(transport), engine, GFS, clock.now()).data.refreshed


# --- Signal writer (D-M04-9, D-M04-74) -----------------------------------------------------------


def test_signal_text_never_in_value(dbs):
    engine, _ = dbs
    with pytest.raises(TypeError):
        write_signal(engine, cik=MU, module_id="M04", signal="cvd_state", as_of="2026-10-12",
                     value="CYCLICAL_TROUGH", method="grid", sources=[Source("a", "2026-10-01")])  # fmt: skip
    with pytest.raises(ValueError, match="never 0"):
        write_signal(
            engine, cik=MU, module_id="M04", signal="runway_q", as_of="2026-10-12", method="x"
        )
    n = write_signal(engine, cik=MU, module_id="M04", signal="cvd_state", as_of="2026-10-12",
                     value_text="CYCLICAL_TROUGH", method="grid", info=("ST",),
                     sources=[Source("acc1", "2026-10-03", "A", "10-K"),
                              Source("tr1", "2026-09-30", "B", "call"),
                              Source("acc0", "2026-06-25", "A")])  # fmt: skip
    assert n == 3
    rows = {r["timeframe"]: r for r in engine.execute("SELECT * FROM signal")}
    assert rows["MY"]["value"] is None and rows["MY"]["value_text"] == "CYCLICAL_TROUGH"
    assert rows["MY"]["evidence_grade"] == "B" and rows["MY"]["source_ref"] == "acc1 +2"
    assert "inputs: acc1 (10-K) 2026-10-03 grade A; tr1 (call)" in rows["MY"]["method"]
    assert rows["ST"]["method"].endswith("info (weight 0)") and "info" not in rows["PT"]["method"]


def test_missing_signal_row(dbs):
    engine, _ = dbs
    write_signal(engine, cik=SPCX, ticker="SPCX", module_id="M04", signal="runway_q",
                 as_of="2026-10-12", method="burn needs 4 quarters", missing="no TTM until the first 10-K",
                 timeframes=("MY",))  # fmt: skip
    r = engine.execute("SELECT * FROM signal").fetchone()
    assert (r["value"], r["value_text"], r["evidence_grade"], r["source_ref"]) == (
        None,
        None,
        None,
        None,
    )
    assert r["method"] == "missing: no TTM until the first 10-K; burn needs 4 quarters"


def test_two_ciks_that_shared_bbby_keep_separate_rows(dbs):
    engine, _ = dbs
    for cik in ("0000886158", "0001130713"):  # Bed Bath & Beyond Inc.; Beyond, Inc. (ex-Overstock)
        write_signal(engine, cik=cik, ticker="BBBY", module_id="M04", signal="filing_status",
                     as_of="2026-10-12", value_text="current", method="m",
                     sources=[Source("a" + cik, "2026-10-01")])  # fmt: skip
    rows = engine.execute(
        "SELECT cik FROM signal WHERE ticker = 'BBBY' AND timeframe = 'MY'"
    ).fetchall()
    assert sorted(r["cik"] for r in rows) == ["0000886158", "0001130713"]


# --- Refresh SEC part ------------------------------------------------------------------------------


def test_sec_part_reads_r1_of_new_filings_only(make_client, dbs, clock):
    engine, _ = dbs
    now = clock.now()  # 2026-10-07
    filing(engine, META, "0001326801-26-000099", "10-Q", "2026-09-30", "2026-06-30")
    filing(
        engine, META, "0001326801-25-000001", "10-Q", "2025-07-31", "2025-06-30"
    )  # old: backfill only
    filing(engine, MU, "0000723125-26-000050", "10-K", "2026-10-03", "2026-09-03")
    fact(
        engine,
        META,
        "Revenues",
        "2026-04-01",
        "2026-06-30",
        1,
        "0001326801-26-000099",
        "2026-09-30",
        "10-Q",
    )
    fact(engine, MU, "EntityCommonStockSharesOutstanding", None, "2026-09-25", 1_120_000_000,
         "0000723125-26-000050", "2026-10-03", "10-K", taxonomy="dei", unit="shares")  # fmt: skip
    meta_htm, _ = cover.r1_urls(META, "0001326801-26-000099")
    mu_htm, _ = cover.r1_urls(MU, "0000723125-26-000050")
    transport = FakeTransport({meta_htm: [ok((M04 / "meta_10k_fy2025_R1.htm").read_bytes())],
                               mu_htm: [ok((M04 / "spcx_10q_2026q2_R1.htm").read_bytes())]})  # fmt: skip
    lines = step.run_sec_part(make_client(transport), engine, {"META": META, "MU": MU}, now)
    assert lines[0].startswith("M04 financials — SEC part (Part 1a)")
    assert "2 new filing(s); read 2" in lines[1]
    assert len(transport.calls) == 2
    step.run_sec_part(make_client(transport), engine, {"META": META, "MU": MU}, now)
    assert len(transport.calls) == 2  # read once


# --- UI and script ----------------------------------------------------------------------------------


def test_financials_tab_shows_the_m04_sections(tmp_path, clock):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui.app import create_app
    from engine.ui.settings import UiSettings

    data = tmp_path / "data"
    engine = open_db("engine", data)
    open_db("corpus", data).close()
    engine.execute(
        "INSERT INTO entity (cik, name, source_ref, fetched_at, category) VALUES (?, 'Meta Platforms, Inc.', 't', 'n', 'Large accelerated filer')",
        (META,),
    )
    engine.execute(
        "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES ('META', ?, '2020-01-01', 't')",
        (META,),
    )
    acc = "0001326801-26-000012"
    filing(engine, META, acc, "10-K", "2026-01-29", "2025-12-31")
    read = r1("meta_10k_fy2025_R1.htm")
    cover.store_cover(
        engine,
        META,
        {"accession": acc, "form": "10-K", "filed": "2026-01-29"},
        read,
        "u",
        "cover",
        clock.now(),
    )
    status.refresh_status(engine, None, META, "META", datetime(2026, 2, 10, tzinfo=UTC))
    engine.close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text('[watchlist]\ntickers = ["META"]\n', encoding="utf-8")
    with TestClient(create_app(UiSettings(data_dir=data, watchlist=watch))) as c:
        html = c.get("/c/META?tab=financials").text
    for text in ("Filing status", "Share counts", "Marker legend", "M04 rows still to come",
                 "2,529,555,464", "2,187,177,748", "Class B Common Stock", "R1 cover page",
                 "missing: not built, Part 1c", "missing: not built, Part 8a", "Capex", "Core trends", "Guidance record", "≈ broader tag",
                 "current", "2026-03-02"):  # fmt: skip
        assert text in html, text
    assert "object at 0x" not in html


def test_run_financials_table_and_unbuilt_parts(capsys, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_financials

    monkeypatch.setattr(sys, "argv", ["run_financials.py", "--list"])
    assert run_financials.main() == 0
    out = capsys.readouterr().out
    assert "data       Part 1a" in out and "backtest   Part 8b" in out and "(not built)" in out
    # An unbuilt subcommand only: a built one would open the real data folder (never in tests).
    assert "profile" not in run_financials.BUILT
    monkeypatch.setattr(sys, "argv", ["run_financials.py", "profile"])
    assert run_financials.main() == 2
    assert "profile: not built, Part 1c" in capsys.readouterr().out
    assert (
        run_financials.fetch_type("https://www.sec.gov/Archives/edgar/data/1/2/R1.htm") == "R page"
    )
    assert (
        run_financials.fetch_type(
            "https://data.sec.gov/api/xbrl/companyconcept/CIK1/us-gaap/Revenues.json"
        )
        == "companyconcept"
    )


def test_class_label_cut_to_class_when_member_names_no_stock():
    from engine.sec.cover import _clean_class

    assert _clean_class("Class C share repurchases [Member]") == "Class C"
    assert _clean_class("Class C Capital Stock [Member]") == "Class C Capital Stock"
    assert _clean_class("Common Class A [Member]") == "Common Class A"


def test_src_revenue_test_named_in_category_reason():
    from engine.financials import status

    assert status.next_category(None, 426.4e6, 20e6) == status.NON
    assert status.next_category(None, 426.4e6, None) == status.ACCEL
