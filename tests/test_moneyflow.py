# ruff: noqa: E501  (fixture rows)
"""M02 part 3: money flow — instances, periods, recipes, stated actuals, guidance lines,
freshness, capital allocation, spenders, links and the views (D-M02-28…32)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from engine import review
from engine.moneyflow import allocation, instance, links, spenders, stated
from engine.moneyflow.actuals import Book, actual_for, recipe_for
from engine.moneyflow.guided import freshness, guided_lines, guided_vs_actual
from engine.moneyflow.periods import span_of
from engine.moneyflow.views import company_view, theme_view
from engine.sec.client import Response
from engine.store.db import open_db
from tests.conftest import FakeTransport
from tests.test_ui import client  # noqa: F401  (fixture)

CIK = "0001326801"
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
TODAY = NOW.date()
T = "2026-10-09T00:00:00+00:00"


# --- helpers ---------------------------------------------------------------------------


def _entity(engine, cik=CIK, fye="1231", ticker="META"):
    engine.execute(
        "INSERT INTO entity (cik, name, fiscal_year_end, source_ref, fetched_at) "
        "VALUES (?, ?, ?, 't', 'n')",
        (cik, f"{ticker} Inc.", fye),
    )
    engine.execute(
        "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES (?, ?, '2020-01-01', 't')",
        (ticker, cik),
    )


def _fact(
    engine, tag, start, end, value, *, taxonomy="us-gaap", cik=CIK, accn="a-10q", filed="2026-07-30"
):
    engine.execute(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession, "
        "form, filed) VALUES (?, ?, ?, 'USD', ?, ?, ?, ?, '10-Q', ?)",
        (cik, taxonomy, tag, start, end, value, accn, filed),
    )


def _quarters(engine, tag, values, *, year=2026, cik=CIK, taxonomy="us-gaap"):
    """Calendar quarters Q1..Qn of a year."""
    bounds = [("01-01", "03-31"), ("04-01", "06-30"), ("07-01", "09-30"), ("10-01", "12-31")]
    for (s, e), v in zip(bounds, values, strict=False):
        _fact(engine, tag, f"{year}-{s}", f"{year}-{e}", v, cik=cik, taxonomy=taxonomy)


def _release(engine, corpus, accession, filed, text, cik=CIK, scanned=True):
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, items, ingested_at) "
        "VALUES (?, ?, '8-K', ?, '2.02,9.01', 'n')",
        (accession, cik, filed),
    )
    corpus.execute(
        "INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, fetched_at) "
        "VALUES (?, ?, 'ex991.htm', 'EX-99.1', ?, ?, 'sha', 'n')",
        (accession, cik, f"https://x/{accession}", text),
    )
    if scanned:
        engine.execute(
            "INSERT INTO guidance_scan (accession, filename, cik, filed, outcome, candidates, "
            "items, unparsed, conflicts, parser_version, at) "
            "VALUES (?, 'ex991.htm', ?, ?, 'parsed', 1, 1, 0, 0, 't', 'n')",
            (accession, cik, filed),
        )


def _guid(engine, accession, period, low, high, *, kind="range", origin="release", grade="A",
          bound=None, clause=None, stated_on="2026-07-29", direction=None, cik=CIK):  # fmt: skip
    engine.execute(
        "INSERT INTO guidance (cik, accession, filename, metric, basis, period, unit, kind, low, "
        "high, point, stated_on, source, quote, quote_start, quote_end, period_quote, "
        "period_start, period_end, doc_sha256, parser_version, created_at, origin, grade, "
        "clause, direction, bound) VALUES (?, ?, 'ex991.htm', 'capex', 'unspecified', ?, "
        "'USD', ?, ?, ?, NULL, ?, 'sentence', 'q', 0, 1, 'p', 0, 1, 'sha', 't', 'n', ?, ?, ?, "
        "?, ?)",
        (cik, accession, period, kind, low, high, stated_on, origin, grade, clause, direction,
         bound),
    )  # fmt: skip


PRINCIPAL = "including principal payments on finance leases"


@pytest.fixture
def meta(dbs):
    """Meta-like: calendar year, capex = PP&E + finance-lease principal."""
    engine, corpus = dbs
    _entity(engine)
    _quarters(engine, "PaymentsToAcquirePropertyPlantAndEquipment", [13.0e9, 30.116e9])
    _quarters(engine, "FinanceLeasePrincipalPayments", [0.69e9, 0.962e9])
    _fact(
        engine,
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "2025-01-01",
        "2025-12-31",
        70.0e9,
        accn="a-10k",
        filed="2026-01-29",
    )
    _fact(
        engine,
        "FinanceLeasePrincipalPayments",
        "2025-01-01",
        "2025-12-31",
        2.2e9,
        accn="a-10k",
        filed="2026-01-29",
    )
    _release(engine, corpus, "a-rel", "2026-07-29",
             "Second Quarter 2026 Results\nCapital expenditures, including principal payments on "
             "finance leases, were $31.08 billion.\nWe expect 2026 capital expenditures to be in "
             "the range of $130-145 billion.\n")  # fmt: skip
    return engine, corpus


# --- XBRL instance ---------------------------------------------------------------------

INSTANCE = b"""<?xml version="1.0" encoding="utf-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2025"
  xmlns:amzn="http://www.amazon.com/20260630" xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
  xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
  <xbrli:context id="c1"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001018724</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:context id="c2"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001018724</xbrli:identifier>
    <xbrli:segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">amzn:AWSMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
    <xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
  <amzn:ProceedsFromPropertyPlantAndEquipmentSalesAndIncentives contextRef="c1" unitRef="usd" decimals="-6">1132000000</amzn:ProceedsFromPropertyPlantAndEquipmentSalesAndIncentives>
  <amzn:ProceedsFromPropertyPlantAndEquipmentSalesAndIncentives contextRef="c1" unitRef="usd" decimals="-6">1132000000</amzn:ProceedsFromPropertyPlantAndEquipmentSalesAndIncentives>
  <amzn:SegmentThing contextRef="c2" unitRef="usd" decimals="-6">5</amzn:SegmentThing>
  <us-gaap:PaymentsToAcquireProductiveAssets contextRef="c1" unitRef="usd" decimals="-6">54208000000</us-gaap:PaymentsToAcquireProductiveAssets>
</xbrli:xbrl>"""


def test_instance_keeps_company_facts_without_dimensions_once():
    facts = instance.parse_instance(INSTANCE)
    assert [(f.prefix, f.tag, f.unit, f.start, f.end, f.value) for f in facts] == [
        ("amzn", "ProceedsFromPropertyPlantAndEquipmentSalesAndIncentives", "USD",
         "2026-04-01", "2026-06-30", 1.132e9)]  # fmt: skip


def test_instance_url_from_primary_document():
    assert instance.instance_url("0001018724", "0001018724-26-000012", "amzn-20260630.htm") == (
        "https://www.sec.gov/Archives/edgar/data/1018724/000101872426000012/amzn-20260630_htm.xml")  # fmt: skip
    assert instance.instance_url("0001018724", "x", "form.txt") is None


def test_sync_instances_stores_extension_facts_once(dbs, make_client):
    engine, _ = dbs
    amzn = "0001018724"
    _entity(engine, amzn, "1231", "AMZN")
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, primary_doc, ingested_at) VALUES "
        "('0001018724-26-000012', ?, '10-Q', '2026-07-31', 'amzn-20260630.htm', 'n')",
        (amzn,),
    )
    url = "https://www.sec.gov/Archives/edgar/data/1018724/000101872426000012/amzn-20260630_htm.xml"
    t = FakeTransport({url: [Response(200, INSTANCE, {})]})
    sec = make_client(t, cached=False)
    read, new, problems = instance.sync_instances(sec, engine, amzn, NOW)
    assert (read, new, problems) == (1, 1, [])
    assert instance.sync_instances(sec, engine, amzn, NOW) == (0, 0, [])  # never twice
    assert len(t.calls) == 1


# --- periods and recipes ---------------------------------------------------------------


def test_span_of_fiscal_labels():
    assert span_of("FY2026 Q2", "0630").end == date(2025, 12, 31)  # Microsoft
    assert span_of("FY2027 Q1", "0125").end == date(2026, 4, 25)  # NVIDIA
    assert span_of("CY2026", "1231").ptype == "FY"
    assert span_of("CY2026", "0630").ptype == "CY"
    assert span_of("FY2026 remaining", "1231") is None


def test_recipe_from_clause():
    assert recipe_for(PRINCIPAL).key == "ppe+lease_principal"
    r = recipe_for("including finance leases")
    assert r.key == "ppe+lease_assets" and r.approximate
    assert recipe_for(None).fallback.endswith("ProductiveAssets")
    assert recipe_for(PRINCIPAL, {"plus": ["us-gaap:X"], "minus": ["amzn:Y"]}).source == "override"


def test_stated_actual_reconciles_meta_recipe(meta):
    engine, corpus = meta
    assert stated.scan_all(engine, corpus) == 1
    [row] = engine.execute("SELECT * FROM capex_stated").fetchall()
    assert (row["period"], row["period_how"], row["grade"], float(row["value"])) == (
        "FY2026 Q2", "release quarter", "A", 31.08e9)  # fmt: skip
    assert row["clause"] == "including principal payments on finance leases"
    a = actual_for(Book(engine, CIK), "FY2026 Q2", PRINCIPAL)
    assert a.status == "reconciled" and a.shown == pytest.approx(31.078e9)
    assert a.label.startswith("reconciled")


def test_override_without_extension_fact_shows_stated_then_reconciles(dbs):
    engine, corpus = dbs
    amzn = "0001018724"
    _entity(engine, amzn, "1231", "AMZN")
    _quarters(engine, "PaymentsToAcquireProductiveAssets", [40e9, 54.208e9], cik=amzn)
    _release(engine, corpus, "z-rel", "2026-07-31",
             "Cash capital expenditures were $53.08 billion in the second quarter of 2026.\n", cik=amzn)  # fmt: skip
    stated.scan_all(engine, corpus)
    ov = {"plus": ["us-gaap:PaymentsToAcquireProductiveAssets"],
          "minus": ["amzn:ProceedsFromPropertyPlantAndEquipmentSalesAndIncentives"]}  # fmt: skip
    a = actual_for(Book(engine, amzn), "FY2026 Q2", None, ov)
    assert a.source == "stated" and a.shown == 53.08e9 and a.recipe.approximate
    assert "excludes amzn:ProceedsFrom" in a.recipe.note and a.gap == pytest.approx(
        0.0213, abs=1e-3
    )
    _fact(engine, "ProceedsFromPropertyPlantAndEquipmentSalesAndIncentives", "2026-04-01",
          "2026-06-30", 1.132e9, taxonomy="amzn", cik=amzn)  # fmt: skip
    a = actual_for(Book(engine, amzn), "FY2026 Q2", None, ov)
    assert a.status == "reconciled" and a.shown == pytest.approx(53.076e9)


def test_calendar_basis_sums_quarters_or_says_not_comparable(dbs):
    engine, _ = dbs
    msft = "0000789019"
    _entity(engine, msft, "0630", "MSFT")
    _quarters(
        engine, "PaymentsToAcquirePropertyPlantAndEquipment", [10e9, 11e9], year=2025, cik=msft
    )
    _guid(engine, "m-call", "CY2026", 175e9, 175e9, kind="approx", origin="call", grade="B",
          clause="including finance leases", cik=msft)  # fmt: skip
    [g] = guided_lines(engine, msft, TODAY)
    assert (
        g.growth_low is None
        and g.comparable == "not comparable yet (2/4 calendar quarters of 2025)"
    )
    _fact(
        engine,
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "2025-07-01",
        "2025-09-30",
        12e9,
        cik=msft,
    )
    _fact(
        engine,
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "2025-10-01",
        "2025-12-31",
        13e9,
        cik=msft,
    )
    [g] = guided_lines(engine, msft, TODAY)
    assert g.base.shown == 46e9 and g.base.recipe.approximate  # lease assets not reported: ≈


def test_stated_parser_cases():
    text = (
        "CapEx was $44.9 billion in the second quarter.\n"
        "We expect CapEx to be about $50 billion next quarter.\n"
        "CapEx by the top five hyperscalers was $800 billion.\n"
        "Year-to-date capital expenditures were $80 billion.\n"
        "Capital expenditures were roughly $12 billion this quarter.\n"
    )
    found = stated.parse_stated(text, [(0, len(text))], (2026, 3), release=False)
    assert [(f.period, float(f.value), f.kind) for f in found] == [
        ("FY2026 Q2", 44.9e9, "point"), ("FY2026 Q3", 12e9, "approx")]  # fmt: skip


# --- guidance lines and freshness -------------------------------------------------------


def test_guided_line_growth_forms(meta):
    engine, corpus = meta
    _guid(engine, "a-rel", "CY2026", 130e9, 145e9, clause=PRINCIPAL)
    [g] = guided_lines(engine, CIK, TODAY, corpus)
    assert g.base.shown == pytest.approx(72.2e9)
    assert g.growth_text == "+90% (+80%…+101%)" and g.ranked
    assert g.freshness.state == "restated"
    _guid(
        engine, "a-rel2", "CY2027", 25e9, 25e9, kind="point", bound="floor", stated_on="2026-07-30"
    )
    lines = {x.period: x for x in guided_lines(engine, CIK, TODAY, corpus)}
    assert lines["CY2027"].growth_text == "no base year"


def test_floor_ranks_at_minimum_and_ceiling_is_not_ranked(dbs):
    engine, _ = dbs
    _entity(engine, fye="1231")
    _fact(engine, "PaymentsToAcquirePropertyPlantAndEquipment", "2025-01-01", "2025-12-31", 20e9)
    _guid(
        engine,
        "t-call",
        "FY2026",
        25e9,
        25e9,
        kind="point",
        bound="floor",
        origin="call",
        grade="B",
    )
    [g] = guided_lines(engine, CIK, TODAY)
    assert g.growth_text == "≥ +25% (ranked at minimum)" and g.rank_value == pytest.approx(0.25)
    engine.execute("UPDATE guidance SET bound = 'ceiling'")
    [g] = guided_lines(engine, CIK, TODAY)
    assert not g.ranked and g.growth_text == "not ranked (ceiling)"


def test_freshness_states(dbs):
    engine, corpus = dbs
    _entity(engine)
    assert freshness(engine, CIK, "CY2026", TODAY).state == "no earnings release on file"
    _release(engine, corpus, "r1", "2026-07-29", "x", scanned=False)
    assert freshness(engine, CIK, "CY2026", TODAY).state == "latest results not read yet"
    engine.execute("INSERT INTO guidance_scan (accession, filename, cik, filed, outcome, "
                   "candidates, items, unparsed, conflicts, parser_version, at) VALUES "
                   "('r1', 'ex991.htm', ?, '2026-07-29', 'none', 0, 0, 0, 0, 't', 'n')", (CIK,))  # fmt: skip
    assert freshness(engine, CIK, "CY2026", date(2026, 8, 10)).state == "call not stored yet"
    assert freshness(engine, CIK, "CY2026", date(2026, 9, 15)).state == (
        "call unavailable — not checked")  # fmt: skip
    engine.execute("INSERT INTO call_document (accession, filename, cik, symbol, quarter, source, "
                   "doc_kind, release_accession, stated_on, added_at) VALUES ('AV-META-2026Q2', "
                   "'t.txt', ?, 'META', 'FY2026 Q2', 'alpha_vantage', 'transcript', 'r1', "
                   "'2026-07-29', 'n')", (CIK,))  # fmt: skip
    assert freshness(engine, CIK, "CY2026", TODAY).state == "not restated"
    _guid(engine, "AV-META-2026Q2", "CY2026", 1e9, 2e9, origin="call", grade="B")
    f = freshness(engine, CIK, "CY2026", TODAY, change="raised")
    assert f.state == "restated" and "raised in the call" in f.why


def test_explicit_refusal_reads_no_outlook(dbs):
    engine, corpus = dbs
    _entity(engine)
    text = "We are not providing a 2027 capex outlook at this time.\n"
    _release(engine, corpus, "r1", "2026-07-29", text)
    engine.execute("INSERT INTO guidance_skip VALUES ('r1', 'ex991.htm', ?, 0, ?, "
                   "'says no guidance is given', 't')", (CIK, len(text) - 1))  # fmt: skip
    assert freshness(engine, CIK, "CY2027", TODAY, corpus).state == "company gives no outlook yet"


def test_ended_period_compares_guided_with_actual(meta):
    engine, corpus = meta
    stated.scan_all(engine, corpus)
    _guid(engine, "a-old", "FY2026 Q2", 30e9, 32e9, clause=PRINCIPAL, stated_on="2026-04-29")
    [g] = guided_lines(engine, CIK, TODAY, corpus)
    assert g.ended and guided_vs_actual(g) == "within guidance"


# --- capital allocation -------------------------------------------------------------------


def _fy(engine, tag, value, taxonomy="us-gaap", cik=CIK):
    _fact(engine, tag, "2025-01-01", "2025-12-31", value, taxonomy=taxonomy, cik=cik, accn="a-10k")


def test_allocation_coverage_and_tag_discovery(dbs):
    engine, _ = dbs
    _entity(engine)
    _fy(engine, "NetCashProvidedByUsedInOperatingActivities", 100e9)
    _fy(engine, "PaymentsToAcquirePropertyPlantAndEquipment", 70e9)
    _fy(engine, "FinanceLeasePrincipalPayments", 2e9)
    _fy(engine, "ProceedsFromIssuanceOfLongTermDebt", 30e9)
    _fy(engine, "PaymentsForRepurchaseOfCommonStock", 20e9)
    _fy(engine, "PaymentsOfDividends", 5e9)
    _fy(engine, "RepaymentsOfFinancingObligations", 10e9, taxonomy="meta")
    _fy(engine, "NetCashProvidedByUsedInFinancingActivities", 30e9 - 20e9 - 5e9 - 2e9 - 10e9)
    [w] = allocation.allocation(engine, CIK, PRINCIPAL)
    assert w.capex == 72e9 and w.ocf_cover == pytest.approx(100 / 72)
    assert "lease_principal" not in w.lines  # inside capex (Meta), never twice
    assert w.coverage == pytest.approx(57 / 67) and w.coverage_text.startswith("coverage")
    _fy(engine, "RepaymentsOfOtherDebtThing", 0, taxonomy="meta")
    engine.execute("UPDATE fact SET value = 40e9 WHERE tag = 'RepaymentsOfFinancingObligations'")
    engine.execute("UPDATE fact SET value = ? WHERE tag = 'NetCashProvidedByUsedInFinancingActivities'",
                   (30e9 - 20e9 - 5e9 - 2e9 - 40e9,))  # fmt: skip
    [w] = allocation.allocation(engine, CIK, PRINCIPAL)
    assert w.coverage < 0.8 and w.coverage_text.startswith("partial")
    assert ("meta:RepaymentsOfFinancingObligations", 40e9) in w.unmapped
    assert allocation.raise_tag_items(engine, CIK, "META", [w], NOW) >= 1
    item = engine.execute("SELECT item_id FROM review_queue WHERE kind = 'm02_tag' AND payload LIKE "
                          "'%RepaymentsOfFinancingObligations%'").fetchone()  # fmt: skip
    review.m02_action(engine, item["item_id"], "debt_repaid", "", "owner", NOW)
    [w] = allocation.allocation(engine, CIK, PRINCIPAL)
    assert w.coverage == pytest.approx(1.0) and w.lines["debt_repaid"].value == 40e9
    assert w.net_debt == -10e9 and w.net_equity == -20e9
    m = engine.execute("SELECT * FROM fin_tag_map").fetchone()
    assert (m["cik"], m["role"], m["mapped_by"]) == (
        CIK,
        "debt_repaid",
        "owner",
    )  # extension: per company
    assert allocation.unmap(engine, m["map_id"], "owner", NOW)
    assert allocation.allocation(engine, CIK, PRINCIPAL)[0].coverage < 0.8
    assert review.get(engine, item["item_id"]).resolved_at is None  # the item reopens


# --- spenders and links -------------------------------------------------------------------


def _theme(engine):
    engine.execute(
        "INSERT INTO theme VALUES (1, 'ai', 'AI infrastructure', 'seed', 'active', ?, ?)", (T, T)
    )
    engine.execute("INSERT INTO theme_phrase (theme_id, phrase, source, status, discovered_at, "
                   "updated_at) VALUES (1, '\"AI infrastructure\"', 'seed', 'active', ?, ?)", (T, T))  # fmt: skip


def _frame(engine, year, cik, value, name):
    engine.execute("INSERT INTO frame_value (taxonomy, tag, unit, frame, cik, entity_name, value, "
                   "fetched_at) VALUES ('us-gaap', 'PaymentsToAcquirePropertyPlantAndEquipment', "
                   "'USD', ?, ?, ?, ?, 'n')", (f"CY{year}", cik, name, value))  # fmt: skip


def test_candidates_need_size_rank_and_theme_hits(dbs):
    engine, _ = dbs
    _theme(engine)
    big_hit, big_nohit, small = "0000000001", "0000000002", "0000000003"
    for cik, v24, v25 in ((big_hit, 5e9, 9e9), (big_nohit, 50e9, 60e9), (small, 0.1e9, 0.9e9)):
        _frame(engine, 2024, cik, v24, cik)
        _frame(engine, 2025, cik, v25, cik)
    q = engine.execute("INSERT INTO fulltext_query (phrase, variant, forms, start_date, end_date, "
                       "total, capped, hits_kept, fetched_at) VALUES ('\"AI infrastructure\"', "
                       "'phrase', '10-K', '2025-01-01', '2025-12-31', 2, 0, 2, ?)", (T,)).lastrowid  # fmt: skip
    for cik in (big_hit, small):
        engine.execute("INSERT INTO fulltext_hit (query_id, accession, filename, cik) "
                       "VALUES (?, ?, 'x.htm', ?)", (q, f"acc-{cik}", cik))  # fmt: skip
    found = spenders.candidates(engine, 2025, exclude=set())
    assert [(s.cik, themes) for s, themes, _ in found] == [(big_hit, ["ai"])]
    assert "+80%" in found[0][2]
    assert spenders.propose_candidates(engine, 2025, set(), NOW) == {"queued": 1}
    assert spenders.candidates(engine, 2025, exclude={big_hit}) == []


def test_spender_link_review_and_theme_view(meta):
    engine, corpus = meta
    _theme(engine)
    engine.execute("INSERT INTO filing (accession, cik, form, filed, ingested_at) VALUES "
                   "('k1', ?, '10-K', '2026-01-29', 'n')", (CIK,))  # fmt: skip
    corpus.execute("INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, "
                   "fetched_at) VALUES ('k1', ?, 'k.htm', '10-K', 'https://x/k1', ?, 'sha', 'n')",
                   (CIK, "We expect capital expenditures to grow as we invest in AI infrastructure.\n"
                         "Our offices are in Menlo Park.\n"))  # fmt: skip
    found = links.scan_company(engine, corpus, CIK, NOW)
    assert [(f.origin, f.grade, f.theme_key) for f in found] == [("filing", "A", "ai")]
    assert links.store_and_propose(engine, CIK, "META", found, NOW) == {"queued": 1}
    assert theme_view(engine, 1, "ai", TODAY).ranked == []  # not confirmed yet
    item = engine.execute("SELECT item_id FROM review_queue WHERE kind = 'm02_spender'").fetchone()
    review.m02_action(engine, item["item_id"], "confirm", "", "owner", NOW)
    _guid(engine, "a-rel", "CY2026", 130e9, 145e9, clause=PRINCIPAL)
    tv = theme_view(engine, 1, "ai", TODAY, corpus)
    [row] = tv.ranked
    assert row.ticker == "META" and row.contribution == pytest.approx(137.5e9 - 72.2e9)
    # a new sentence for a decided pair follows the decision, no new item
    assert links.store_and_propose(engine, CIK, "META", found, NOW) == {}


def test_company_view_and_money_tab_render(client):  # noqa: F811
    engine = open_db("engine", client.app.state.settings.data_dir)
    _quarters(engine, "PaymentsToAcquirePropertyPlantAndEquipment", [13.0e9, 30.116e9])
    _quarters(engine, "FinanceLeasePrincipalPayments", [0.69e9, 0.962e9])
    _fy(engine, "NetCashProvidedByUsedInOperatingActivities", 100e9)
    _fy(engine, "PaymentsToAcquirePropertyPlantAndEquipment", 70e9)
    _guid(engine, "a-rel", "CY2026", 130e9, 145e9, clause=PRINCIPAL)
    v = company_view(engine, CIK, TODAY)
    assert v.recipe_label.startswith("PP&E payments + finance-lease principal")
    assert [r.period for r in v.actuals][:2] == ["FY2026 Q2", "FY2026 Q1"]
    engine.close()
    html = client.get("/c/META?tab=money").text
    assert "Capex guidance" in html and "$130.0B–$145.0B" in html
    assert "Capital allocation" in html and "not reported" in html
    assert "RPO not reported" in html and "object at 0x" not in html


# --- live check 1 fixes (2026-10-09) ------------------------------------------------------


def test_payload_values_show_dollars_and_percentages():
    from engine.moneyflow.views import payload_value

    assert payload_value("value", 13000000000.0) == "$13,000,000,000"
    assert payload_value("capex", -2_500_000) == "−$2,500,000"
    assert payload_value("coverage", 0.6176470588235294) == "61.8%"
    assert payload_value("growth", 0.8) == "+80.0%"
    assert payload_value("money_flow", True) is True and payload_value("ticker", "AMZN") == "AMZN"
    assert payload_value("sentences", 3) == 3


def test_two_figures_for_two_periods_are_not_read_as_one():
    text = ("Capital expenditures were $22.1 billion and $72.2 billion for the fourth quarter "
            "and full year 2025.\n"
            "Capital expenditures were $44.9 billion, up from $22.4 billion a year ago.\n")  # fmt: skip
    found = stated.parse_stated(text, [(0, len(text))], (2025, 4), release=True)
    assert [(f.period, float(f.value)) for f in found] == [("FY2025 Q4", 44.9e9)]


def test_stated_far_from_exact_recipe_is_doubtful_and_recipe_stays(meta):
    engine, corpus = meta
    engine.execute(
        "INSERT INTO capex_stated (cik, accession, filename, origin, grade, period, period_how, "
        "kind, value, stated_on, quote, quote_start, quote_end, parser_version) VALUES "
        "(?, 'a-rel', 'ex991.htm', 'release', 'A', 'FY2026 Q1', 'stated', 'point', 45e9, "
        "'2026-04-29', 'q', 0, 1, 't')",
        (CIK,),
    )
    a = actual_for(Book(engine, CIK), "FY2026 Q1", PRINCIPAL)
    assert a.status == "doubtful statement" and a.shown == pytest.approx(13.69e9)
    assert "likely misread" in a.label


def test_fiscal_year_window_ignores_twelve_month_10q_figures(dbs):
    engine, _ = dbs
    _entity(engine)
    _fy(engine, "NetCashProvidedByUsedInOperatingActivities", 100e9)
    _fact(engine, "NetCashProvidedByUsedInOperatingActivities", "2025-07-01", "2026-06-30", 120e9)
    _fact(engine, "NetCashProvidedByUsedInOperatingActivities", "2025-07-01", "2025-09-30", -5e9)
    windows = {w.ptype: w for w in allocation.allocation(engine, CIK, None)}
    assert windows["FY"].end == "2025-12-31" and windows["FY"].ocf == 100e9
    engine.execute("UPDATE fact SET value = -1e9 WHERE period_end = '2025-12-31'")
    _fy(engine, "PaymentsToAcquirePropertyPlantAndEquipment", 2e9)
    w = {w.ptype: w for w in allocation.allocation(engine, CIK, None)}["FY"]
    assert w.ocf_cover_text == "n/m (negative OCF)"


def test_freshness_skips_an_operating_update_filed_days_after_quarter_end(dbs):
    engine, corpus = dbs
    _entity(engine)
    _release(engine, corpus, "results", "2026-07-22", "x")
    engine.execute("INSERT INTO filing (accession, cik, form, filed, items, ingested_at) "
                   "VALUES ('deliveries', ?, '8-K', '2026-10-02', '2.02,9.01', 'n')", (CIK,))  # fmt: skip
    f = freshness(engine, CIK, "CY2026", TODAY)
    assert f.state == "call unavailable — not checked" and "2026-07-22" in f.why
