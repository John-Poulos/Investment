# ruff: noqa: E501  (fixture rows)
"""M04 Part 7a: dimensional facts, unit KPIs, release exhibits (docs/M04_BUILD_LOG.md Part 7a;
D-M04-42, -81).

Fixtures: tests/fixtures/m04/ — trimmed instances (NVIDIA FY2025/FY2026, Meta, MSTR 2011,
SPCX, Alphabet, Target FY2022 Q1–Q2), Target companyconcept files, Tesla, Rivian and
Invitae release snippets (hand-built; figures and placeholders in the README). SEC is only
ever a fake transport."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine.financials import exhibits, queue, units, units_step, units_view
from engine.moneyflow import instance as mf_instance
from engine.sec import cover, instance_dim
from engine.sec.documents import IndexDoc, store_document
from engine.sec.xbrl_facts import store_concept
from engine.themes import tiers
from tests.conftest import FIXTURES, FakeTransport, ok

M04 = FIXTURES / "m04"
NVDA, META, MSTR, SPCX, GOOG = "0001045810", "0001326801", "0001050446", "0001181412", "0001652044"
TSLA, RIVN, NVTA, TGT = "0001318605", "0001874178", "0001501134", "0000027419"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
ARCH = "https://www.sec.gov/Archives/edgar/data"


def data(name: str) -> bytes:
    return (M04 / name).read_bytes()


def filing(
    engine, cik, acc, form, filed, report_date=None, primary_doc=None, items=None, is_xbrl=1
):
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, report_date, items, primary_doc, is_xbrl, "
        "ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'n')",
        (acc, cik, form, filed, report_date, items, primary_doc, is_xbrl),
    )
    engine.execute("INSERT INTO filing_cik (accession, cik) VALUES (?, ?)", (acc, cik))
    return {
        "accession": acc,
        "form": form,
        "filed": filed,
        "primary_doc": primary_doc,
        "report_date": report_date,
    }


def entity(engine, cik, name, fye="1231", ticker=None):
    engine.execute(
        "INSERT OR REPLACE INTO entity (cik, name, fiscal_year_end, source_ref, "
        "fetched_at) VALUES (?, ?, ?, 't', 'n')",
        (cik, name, fye),
    )
    if ticker:
        engine.execute(
            "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES (?, ?, '2000-01-01', 't')",
            (ticker, cik),
        )


def store_instance(engine, cik, f, name):
    return instance_dim.store_parsed(engine, cik, f, instance_dim.parse(data(name)), "u", NOW)


def revenue_fact(engine, cik, start, end, value, acc, filed):
    engine.execute(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession, "
        "form, filed) VALUES (?, 'us-gaap', 'Revenues', 'USD', ?, ?, ?, ?, '10-K', ?)",
        (cik, start, end, value, acc, filed),
    )


def doc(corpus, cik, acc, name, doc_type="EX-99.1"):
    d = IndexDoc(
        2, doc_type, name, f"{ARCH}/{int(cik)}/{acc.replace('-', '')}/{name}", doc_type, None, False
    )
    return store_document(corpus, cik, acc, d, data(name), NOW)


def nvda_filings(engine):
    entity(engine, NVDA, "NVIDIA CORP", "0125", "NVDA")
    k25 = filing(
        engine,
        NVDA,
        "0001045810-25-000023",
        "10-K",
        "2025-02-26",
        "2025-01-26",
        "nvda-20250126.htm",
    )
    k26 = filing(
        engine,
        NVDA,
        "0001045810-26-000021",
        "10-K",
        "2026-02-25",
        "2026-01-25",
        "nvda-20260125.htm",
    )
    return k25, k26


# --- Instance reader (sec/instance_dim.py) ------------------------------------------------------


def test_parse_keeps_kept_axes_and_skips_the_rest():
    p = instance_dim.parse(data("nvda_10k_fy2025_instance_trimmed.xml"))
    axes = sorted({d.axis_member[0] for d in p.dims})
    assert axes == ["srt:MajorCustomersAxis", "us-gaap:StatementBusinessSegmentsAxis"]
    assert len(p.dims) == 7  # 3 customers + 1 receivables share + 3 segment facts
    assert p.skipped_contexts == 2  # equity components; typed member
    assert [f.tag for f in p.extension] == ["IllustrativeExtensionFact"]
    assert any(f.tag == "Revenues" and f.standard for f in p.plain)
    cust = [d for d in p.dims if d.concept.endswith("ConcentrationRiskPercentage1")]
    assert {d.axis_member[1] for d in cust} == {
        "nvda:CustomerAMember",
        "nvda:CustomerBMember",
        "nvda:CustomerCMember",
    }
    assert (
        "us-gaap:ConcentrationRiskByBenchmarkAxis=us-gaap:RevenueFromContractWithCustomerMember"
        in cust[0].dims_key
    )


def test_read_instance_stores_both_kinds_once_and_never_caches(make_client, dbs):
    engine, corpus = dbs
    k25, _ = nvda_filings(engine)
    url = f"{ARCH}/1045810/000104581025000023/nvda-20250126_htm.xml"
    t = FakeTransport({url: [ok(data("nvda_10k_fy2025_instance_trimmed.xml"))]})
    client = make_client(t)
    assert [r["accession"] for r in instance_dim.due_filings(engine, NVDA, "2023-01-01")] == [
        "0001045810-26-000021",
        "0001045810-25-000023",
    ]
    r = instance_dim.read_instance(client, engine, NVDA, k25, NOW)
    assert r.outcome == "ok" and r.dim_new == 7 and r.ext_new == 1
    assert engine.execute("SELECT count(*) FROM fact_dim").fetchone()[0] == 7
    assert (
        engine.execute("SELECT tag FROM fact WHERE taxonomy = 'nvda'").fetchone()[0]
        == "IllustrativeExtensionFact"
    )
    names = {x[0] for x in engine.execute("SELECT name FROM refresh_state")}
    assert {"fact_dim:0001045810-25-000023", "xbrl_instance:0001045810-25-000023"} <= names
    assert corpus.execute("SELECT count(*) FROM http_cache").fetchone()[0] == 0  # SB.16
    assert [x["accession"] for x in instance_dim.due_filings(engine, NVDA, "2023-01-01")] == [
        "0001045810-26-000021"
    ]
    assert store_instance(engine, NVDA, k25, "nvda_10k_fy2025_instance_trimmed.xml") == (
        0,
        0,
    )  # idempotent
    assert len(t.calls) == 1


def test_missing_instance_is_recorded_not_retried(make_client, dbs):
    engine, _ = dbs
    k25, _ = nvda_filings(engine)
    folder = f"{ARCH}/1045810/000104581025000023"
    nf = ok(b"", status=404)
    t = FakeTransport({f"{folder}/nvda-20250126_htm.xml": [nf],
                       f"{folder}/0001045810-25-000023-index.htm": [nf],
                       f"{folder}/0001045810-25-000023-index.html": [nf]})  # fmt: skip
    r = instance_dim.read_instance(make_client(t), engine, NVDA, k25, NOW)
    assert r.outcome == "not_found"
    assert instance_dim.dims_done(engine, k25["accession"])


def test_moneyflow_reader_keeps_dimensions_on_the_same_read(make_client, dbs):
    engine, _ = dbs
    k25, _ = nvda_filings(engine)
    url = f"{ARCH}/1045810/000104581025000023/nvda-20250126_htm.xml"
    client = make_client(FakeTransport({url: [ok(data("nvda_10k_fy2025_instance_trimmed.xml"))]}))
    res = mf_instance.store_instance(client, engine, NVDA, k25, NOW)
    assert res.data == 1  # the extension fact, as before
    assert engine.execute("SELECT count(*) FROM fact_dim").fetchone()[0] == 7
    assert instance_dim.dims_done(engine, k25["accession"])  # M04 never fetches it again


# --- Customers, segments, classes (financials/units_view.py) ------------------------------------


def nvda_stored(engine):
    k25, k26 = nvda_filings(engine)
    store_instance(engine, NVDA, k25, "nvda_10k_fy2025_instance_trimmed.xml")
    store_instance(engine, NVDA, k26, "nvda_10k_fy2026_instance_trimmed.xml")
    revenue_fact(
        engine, NVDA, "2024-01-29", "2025-01-26", 130_497e6, k25["accession"], "2025-02-26"
    )
    revenue_fact(
        engine, NVDA, "2025-01-27", "2026-01-25", 215_938e6, k26["accession"], "2026-02-25"
    )
    return k25, k26


def test_nvidia_customers_3_to_2_with_revenue_at_stake(dbs):
    engine, _ = dbs
    nvda_stored(engine)
    ys = units_view.major_customers(engine, NVDA)
    assert [(y.label, y.count) for y in ys] == [("FY2025", 3), ("FY2026", 2)]
    assert ys[0].at_stake == pytest.approx(0.34)  # receivables share (17%) not counted
    assert ys[1].at_stake == pytest.approx(0.36)
    assert ys[1].at_stake_usd / 1e9 == pytest.approx(77.7, abs=0.05)
    assert (
        ys[0].accession == "0001045810-25-000023"
    )  # the year's first filing, not the FY2026 re-statement
    assert ys[1].customers[0] == ("CustomerA", pytest.approx(0.22))


def test_segments_flag_recasts_and_breaks_without_merging(dbs):
    engine, _ = dbs
    nvda_stored(engine)
    sg = units_view.segment_table(engine, NVDA)
    assert sg.accession == "0001045810-26-000021" and sg.labels == ["FY2025", "FY2026"]
    row = dict(sg.rows)["ComputeAndNetworking · revenue"]
    assert row[0][0] == "115,186 recast" and "first filed 116,193" in row[0][1]
    assert row[1][0] == "193,000"
    assert any("recast" in n for n in sg.notes)
    assert not any(n.startswith("Break") for n in sg.notes)
    # a later filing with a new segment set is a break, listed, not merged
    engine.execute(
        "INSERT INTO fact_dim (cik, accession, form, filed, concept, axis, member, dims, period_start, period_end, value, unit) VALUES (?, 'X-27', '10-K', '2027-02-24', 'us-gaap:Revenues', 'us-gaap:StatementBusinessSegmentsAxis', 'nvda:DataCenterMember', 'us-gaap:StatementBusinessSegmentsAxis=nvda:DataCenterMember', '2026-01-26', '2027-01-31', 1, 'USD')",
        (NVDA,),
    )
    sg2 = units_view.segment_table(engine, NVDA)
    assert any(
        n.startswith("Break") and "DataCenter" in n and "ComputeAndNetworking" in n
        for n in sg2.notes
    )


@pytest.mark.parametrize(
    "cik,r1_name,inst,acc,form,total",
    [
        (
            META,
            "meta_10k_fy2025_R1.htm",
            "meta_10k_fy2025_instance_trimmed.xml",
            "0001326801-26-000012",
            "10-K",
            2_529_555_464,
        ),
        (
            MSTR,
            "mstr_10q_2011q2_R1.htm",
            "mstr_10q_2011q2_instance_trimmed.xml",
            "0001050446-11-000020",
            "10-Q",
            10_710_224,
        ),
        (
            SPCX,
            "spcx_10q_2026q2_R1.htm",
            "spcx_10q_2026q2_instance_trimmed.xml",
            "0001181412-26-000031",
            "10-Q",
            6_000_000_000,
        ),
    ],
)
def test_class_counts_from_the_instance_agree_with_r1(dbs, cik, r1_name, inst, acc, form, total):
    engine, _ = dbs
    f = filing(engine, cik, acc, form, "2026-01-29")
    read = cover.read_cover(cover.parse_r_html(data(r1_name).decode("utf-8")))
    cover.store_cover(engine, cik, f, read, "u", "cover", NOW)
    store_instance(engine, cik, f, inst)
    (c,) = units_view.class_checks(engine, cik)
    assert c.instance_total == total and c.r1_total == total and c.agree == "agree"
    assert len(c.instance) == 2


def test_goog_three_classes_agree_and_a_mismatch_is_shown(dbs):
    engine, _ = dbs
    f = filing(engine, GOOG, "0001652044-26-000070", "10-Q", "2026-07-24")
    store_instance(engine, GOOG, f, "goog_10q_2026q2_instance_trimmed.xml")
    for cls, n in (
        ("Class A", 5_800_000_000),
        ("Class B", 850_000_000),
        ("Class C", 5_580_000_000),
    ):
        engine.execute(
            "INSERT INTO cover_shares (accession, cik, class_label, shares, cover_date, form, filed, source_url, read_at) VALUES (?, ?, ?, ?, '2026-07-15', '10-Q', '2026-07-24', 'u', 'n')",
            (f["accession"], GOOG, cls, n),
        )
    (c,) = units_view.class_checks(engine, GOOG)
    assert c.agree == "agree" and c.instance_total == 12_230_000_000
    assert [n for n, _ in c.instance] == ["CommonClassA", "CommonClassB", "CapitalStockClassC"]
    engine.execute("UPDATE cover_shares SET shares = shares + 1000 WHERE class_label = 'Class C'")
    assert units_view.class_checks(engine, GOOG)[0].agree == "differ by -1,000"


# --- Unit KPIs (financials/units.py) -------------------------------------------------------------


def tesla(engine, corpus):
    entity(engine, TSLA, "Tesla, Inc.", "1231", "TSLA")
    for acc, filed, name in (
        ("0001318605-22-000040", "2022-10-02", "tsla_pd_q3_2022_ex991_trimmed.htm"),
        ("0000950170-23-001409", "2023-01-25", "tsla_update_q4_2022_ex991_trimmed.htm"),
        ("0001628280-24-002390", "2024-01-24", "tsla_update_q4_2023_ex991_trimmed.htm"),
    ):
        filing(engine, TSLA, acc, "8-K", filed, items="2.02,9.01")
        doc(corpus, TSLA, acc, name)
    return units.scan_company(engine, corpus, TSLA, NOW)


def test_tesla_ds2_table_by_model_line_with_prior_quarters():
    text = store_text("tsla_update_q4_2023_ex991_trimmed.htm")
    ms = {(m.metric, m.line, m.period_label): m for m in units.quarter_table(text)}
    assert ms[("deliveries", "", "Q4-2023")].value == 484_507
    assert ms[("deliveries", "", "Q4-2022")].value == 405_278  # the year-ago column
    assert ms[("production", "Model 3/Y", "Q3-2023")].value == 416_800
    assert ms[("deliveries", "Other models", "Q4-2023")].value == 22_969
    assert ms[("storage_deployed", "", "Q4-2023")].unit == "MWh"
    cr = ms[("regulatory_credits", "", "Q4-2023")]
    assert cr.kind == "credit" and cr.value == 433e6 and cr.unit == "USD"  # kept separate
    assert ms[("deliveries", "", "Q4-2023")].end == "2023-12-31"


def store_text(name):
    from engine.sec.documents import extract_text

    return extract_text(data(name), name)[0]


def test_tesla_deliveries_2022_to_2023_up_38_percent(dbs):
    engine, corpus = dbs
    s = tesla(engine, corpus)
    assert s.docs == 3 and s.rows > 0
    ch = units.change_between(engine, TSLA, "deliveries", "FY2022", "FY2023")
    assert ch == pytest.approx(1_808_581 / 1_313_851 - 1) and round(ch * 100) == 38
    rows = {(r.metric, r.line): r for r in units.kpi_rows(engine, TSLA)}
    y = [
        r
        for r in units.kpi_rows(engine, TSLA)
        if r.metric == "deliveries" and not r.line and r.later[0] == "FY2023"
    ]
    assert y and y[0].basis == "sum of 4 quarters"  # exact quarters beat "over 1.8 million"
    assert rows[("regulatory_credits", "")].kind == "credit"
    # a second scan adds nothing (documents are scanned once per extractor version)
    assert units.scan_company(engine, corpus, TSLA, NOW).docs == 0


def test_tesla_category_break_opens_m04_unit_kpi(dbs):
    engine, corpus = dbs
    tesla(engine, corpus)
    bs = units.breaks(engine, TSLA)
    deliv = [b for b in bs if b.metric == "deliveries"]
    assert (
        len(deliv) == 1
        and deliv[0].dropped == ("Model S/X",)
        and deliv[0].added == ("Other models",)
    )
    # first scan: a break filed more than 12 months ago is a baseline, not queued
    assert units.propose_breaks(engine, TSLA, "TSLA", NOW) == {"baseline": 2}
    assert engine.execute("SELECT count(*) FROM review_queue").fetchone()[0] == 0


def test_recent_break_is_queued_in_group_6_and_resolved(dbs):
    from engine import review

    engine, corpus = dbs
    tesla(engine, corpus)
    soon = datetime(2023, 3, 1, tzinfo=UTC)
    assert units.propose_breaks(engine, TSLA, "TSLA", soon) == {"queued": 2}
    p = engine.execute(
        "SELECT * FROM m04_proposal WHERE kind = 'm04_unit_kpi' ORDER BY prop_key"
    ).fetchone()
    assert p["priority"] == 6 and p["capped"] == 1
    item = p["item_id"]
    assert queue.ACTIONS["m04_unit_kpi"] == ("break_confirmed", "same_scope")
    done = review.m04_action(engine, item, "break_confirmed", "new lines", "owner", soon)
    assert done.startswith("break_confirmed")
    assert list(units.owner_breaks(engine, TSLA).values())[0].startswith("break_confirmed")
    assert units.propose_breaks(engine, TSLA, "TSLA", soon) == {"suppressed": 2}


def test_rivian_deliveries_down_18_percent(dbs):
    engine, corpus = dbs
    entity(engine, RIVN, "Rivian Automotive, Inc. / DE", "1231", "RIVN")
    for acc, filed, name in (
        ("0001874178-25-000011", "2025-02-20", "rivn_q4_2024_ex991_trimmed.htm"),
        ("0001874178-26-000006", "2026-02-12", "rivn_q4_2025_ex991_trimmed.htm"),
    ):
        filing(engine, RIVN, acc, "8-K", filed, items="2.02,9.01")
        doc(corpus, RIVN, acc, name)
    units.scan_company(engine, corpus, RIVN, NOW)
    ch = units.change_between(engine, RIVN, "deliveries", "FY2024", "FY2025")
    assert round(ch * 100, 1) == -18.1  # 51,579 → 42,247
    q = [
        r
        for r in units.latest_rows(engine, RIVN)
        if r["period_label"] == "Q4-2025" and r["metric"] == "deliveries"
    ]
    assert q[0]["value"] == 9_745 and "quarter ended December 31, 2025" in q[0]["quote"]
    assert not [r for r in units.latest_rows(engine, RIVN) if r["metric"] == "regulatory_credits"]


def test_sentences_without_a_period_are_not_stored():
    assert units.sentence_metrics("We delivered 1,000 vehicles to customers.") == []
    got = units.sentence_metrics(
        "In the fourth quarter of 2025 we delivered approximately 9,700 vehicles."
    )
    assert got[0].basis == "stated (approximately)" and got[0].period_label == "Q4-2025"


def test_quarter_dates_follow_the_fiscal_year_end():
    assert units.quarter_dates(4, 2023) == ("2023-10-01", "2023-12-31")
    assert units.quarter_dates(1, 2026, "0125") == ("2025-02-01", "2025-04-30")  # NVIDIA-style
    assert units.year_dates(2022, "0930") == ("2021-10-01", "2022-09-30")


# --- Invitae and Target (reference episodes) ---------------------------------------------------


INVITAE_RELEASES = (
    ("0001501134-20-000007", "2020-02-19", "nvta_q4_2019_ex991_trimmed.htm"),
    ("0001501134-20-000023", "2020-05-05", "nvta_q1_2020_ex991_trimmed.htm"),
    ("0001501134-20-000037", "2020-08-04", "nvta_q2_2020_ex991_trimmed.htm"),
    ("0001501134-20-000078", "2020-11-05", "nvta_q3_2020_ex991_trimmed.htm"),
    ("0001501134-21-000004", "2021-02-17", "nvta_q4_2020_ex991_trimmed.htm"),
    ("0001501134-23-900001", "2023-02-28", "nvta_q4_2022_ex991_trimmed.htm"),
)


def invitae(engine, corpus):
    entity(engine, NVTA, "Invitae Corp", "1231")
    for acc, filed, name in INVITAE_RELEASES:
        filing(engine, NVTA, acc, "8-K", filed, items="2.02,9.01")
        doc(corpus, NVTA, acc, name)
    units.scan_company(engine, corpus, NVTA, NOW)
    return exhibits.scan_releases(engine, corpus, NVTA, NOW)


def test_invitae_non_gaap_margin_yoy_on_each_release(dbs):
    engine, corpus = dbs
    assert invitae(engine, corpus) > 0
    got = exhibits.non_gaap_margin_yoy(engine, NVTA)
    assert [(m.label, round(m.pp, 1)) for m in got] == [
        ("Q1-2020", -7.0),
        ("Q2-2020", -31.6),
        ("Q3-2020", -6.7),
        ("Q4-2020", -2.3),
    ]
    fy = engine.execute(
        "SELECT value FROM unit_metric WHERE cik = ? AND metric = 'non_gaap_gross_profit' AND period_label = 'FY2020'",
        (NVTA,),
    ).fetchone()
    assert fy[0] == 106_794e3  # the Q4 release's year column, in thousands → dollars
    assert (
        engine.execute(
            "SELECT DISTINCT kind FROM unit_metric WHERE metric = 'non_gaap_gross_profit'"
        ).fetchone()[0]
        == "non_gaap"
    )


def test_invitae_billable_units_469k_to_1290k(dbs):
    engine, corpus = dbs
    invitae(engine, corpus)
    ch = units.change_between(engine, NVTA, "billable_units", "FY2019", "FY2022")
    assert ch == pytest.approx(1_290_000 / 469_000 - 1)
    lines = units_view.reference_lines(engine)
    assert any(
        k.company == "Invitae"
        and k.metric.startswith("non-GAAP gross margin")
        and k.change == "−7.0 pp"
        for k in lines
    )


def target_facts(engine):
    for tag in ("Revenues", "CostOfGoodsAndServicesSold"):
        engine.execute("BEGIN")
        store_concept(engine, TGT, json.loads(data(f"tgt_us-gaap_{tag}_20261012.json")))
        engine.execute("COMMIT")


def test_target_gross_margin_needs_the_instance_for_fy2022(dbs):
    engine, _ = dbs
    target_facts(engine)
    pp, cur, old = units.gm_yoy_pp(engine, TGT, "2022-04-30", "2021-05-01")
    assert (
        pp is None and cur.basis.startswith("missing: dimensional") and old.basis == "companyfacts"
    )
    for acc, end, name in (
        ("0000027419-22-900011", "2022-04-30", "tgt_10q_fy2022q1_instance_trimmed.xml"),
        ("0000027419-22-900021", "2022-07-30", "tgt_10q_fy2022q2_instance_trimmed.xml"),
    ):
        store_instance(engine, TGT, filing(engine, TGT, acc, "10-Q", "2022-06-01", end), name)
    q1, cur, _ = units.gm_yoy_pp(engine, TGT, "2022-04-30", "2021-05-01")
    q2, _, _ = units.gm_yoy_pp(engine, TGT, "2022-07-30", "2021-07-31")
    assert round(q1, 1) == -4.4 and round(q2, 1) == -8.9
    assert cur.basis.startswith("instance dimension tgt:SalesMember")


def test_target_check_fetches_concepts_then_only_missing_instances(make_client, dbs):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_financials

    from engine.sec.xbrl_facts import CONCEPT_URL

    engine, _ = dbs
    for acc, end, doc_name in (
        ("0000027419-21-900011", "2021-05-01", "tgt-20210501.htm"),
        ("0000027419-21-900021", "2021-07-31", "tgt-20210731.htm"),
        ("0000027419-22-900011", "2022-04-30", "tgt-20220430.htm"),
        ("0000027419-22-900021", "2022-07-30", "tgt-20220730.htm"),
    ):
        filing(engine, TGT, acc, "10-Q", "2022-06-01", end, doc_name)
    routes = {
        CONCEPT_URL.format(cik=TGT, taxonomy="us-gaap", tag=t): [
            ok(data(f"tgt_us-gaap_{t}_20261012.json"))
        ]
        for t in ("Revenues", "CostOfGoodsAndServicesSold")
    }
    routes[f"{ARCH}/27419/000002741922900011/tgt-20220430_htm.xml"] = [
        ok(data("tgt_10q_fy2022q1_instance_trimmed.xml"))
    ]
    routes[f"{ARCH}/27419/000002741922900021/tgt-20220730_htm.xml"] = [
        ok(data("tgt_10q_fy2022q2_instance_trimmed.xml"))
    ]
    t = FakeTransport(routes)
    out: list[str] = []
    run_financials.target_check(make_client(t), engine, NOW, lambda *ls: out.extend(ls))
    assert len(t.calls) == 4  # 2 concept files + the 2 FY2022 instances; FY2021 needs none
    assert any("2022-04-30" in x and "ok" in x for x in out)


# --- Exhibits: EX-99.2 and episode releases ------------------------------------------------------


def index_page(acc: str, cik: str, docs: list[tuple[str, str]]) -> bytes:
    rows = "".join(
        f'<tr><td>{i}</td><td>{t}</td><td><a href="/Archives/edgar/data/{int(cik)}/{acc.replace("-", "")}/{n}">{n}</a></td><td>{t}</td><td>100</td></tr>'
        for i, (n, t) in enumerate(docs, 1)
    )
    return (
        f'<table class="tableFile" summary="Document Format Files"><tr><th>Seq</th><th>Description</th>'
        f"<th>Document</th><th>Type</th><th>Size</th></tr>{rows}</table>"
    ).encode()


def test_ex992_fetched_once_per_release(make_client, dbs):
    engine, corpus = dbs
    entity(engine, NVDA, "NVIDIA CORP", "0125", "NVDA")
    a1, a2 = "0001045810-26-000019", "0001045810-26-000044"
    filing(engine, NVDA, a1, "8-K", "2026-02-25", items="2.02,9.01")
    filing(engine, NVDA, a2, "8-K", "2026-05-28", items="2.02,9.01")
    f1, f2 = f"{ARCH}/1045810/000104581026000019", f"{ARCH}/1045810/000104581026000044"
    t = FakeTransport({
        f"{f1}/{a1}-index.htm": [ok(index_page(a1, NVDA, [("q4fy26pr.htm", "EX-99.1"), ("q4fy26cfo.htm", "EX-99.2")]))],
        f"{f1}/q4fy26cfo.htm": [ok(b"<p>CFO commentary. Revenue for the fourth quarter was $68.1 billion.</p>")],
        f"{f2}/{a2}-index.htm": [ok(index_page(a2, NVDA, [("q1fy27pr.htm", "EX-99.1")]))],
    })  # fmt: skip
    res = exhibits.fetch_ex992(make_client(t), engine, corpus, NVDA, NOW)
    assert (res.checked, res.found, res.stored) == (2, 1, 1)
    assert corpus.execute("SELECT doc_type FROM document").fetchone()[0] == "EX-99.2"
    again = exhibits.fetch_ex992(make_client(t), engine, corpus, NVDA, NOW)
    assert again.checked == 0 and len(t.calls) == 3


def test_episode_releases_fetch_ex991_only(make_client, dbs):
    engine, corpus = dbs
    acc = "0001501134-20-000023"
    filing(engine, NVTA, acc, "8-K", "2020-05-05", items="2.02,9.01")
    filing(engine, NVTA, "0001501134-20-000030", "8-K", "2020-06-01", items="5.07")  # not a release
    folder = f"{ARCH}/1501134/000150113420000023"
    t = FakeTransport({
        f"{folder}/{acc}-index.htm": [ok(index_page(acc, NVTA, [("nvta-8k.htm", "8-K"), ("ex991.htm", "EX-99.1")]))],
        f"{folder}/ex991.htm": [ok(data("nvta_q1_2020_ex991_trimmed.htm"))],
    })  # fmt: skip
    n, new, probs = exhibits.fetch_episode_releases(
        make_client(t), engine, corpus, NVTA, "2020-01-01", "2023-03-31", NOW
    )
    assert (n, new, probs) == (1, 1, []) and len(t.calls) == 2  # the 8-K body is not fetched


# --- Refresh step and script ----------------------------------------------------------------------


def test_sec_step_reads_new_filings_of_covered_names_only(make_client, dbs):
    engine, corpus = dbs
    k25, k26 = nvda_filings(engine)
    engine.execute(
        "UPDATE filing SET filed = '2026-10-01' WHERE accession = ?", (k26["accession"],)
    )
    entity(engine, RIVN, "Rivian", "1231", "RIVN")
    filing(
        engine,
        RIVN,
        "0001874178-26-000050",
        "10-Q",
        "2026-10-05",
        "2026-09-30",
        "rivn-20260930.htm",
    )
    tiers.add_tracked(engine, RIVN, "RIVN", reason="t", theme_key=None, by="o", now=NOW)
    url = f"{ARCH}/1045810/000104581026000021/nvda-20260125_htm.xml"
    t = FakeTransport({url: [ok(data("nvda_10k_fy2026_instance_trimmed.xml"))]})
    lines = units_step.run_sec_part(
        make_client(t), engine, corpus, {"NVDA": NVDA, "RIVN": RIVN}, NOW
    )
    assert lines[0].startswith("M04 units — SEC part (Part 7a)") and "instances read 1" in lines[0]
    assert len(t.calls) == 1  # FY2025 10-K is history (owner backfill); RIVN tracked → none
    assert units_step.full_scope(engine, {"NVDA": NVDA, "RIVN": RIVN}) == {"NVDA": NVDA}
    local = units_step.run_local_part(engine, corpus, {"NVDA": NVDA}, NOW)
    assert local[0].startswith("M04 units — local pass (Part 7a, 0 SEC requests)")


def test_units_run_without_sec_reports_rivn_and_the_summary(dbs):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_financials

    engine, corpus = dbs
    nvda_stored(engine)
    tesla(engine, corpus)
    out: list[str] = []
    run_financials.units_run(
        engine, corpus, {"NVDA": NVDA, "TSLA": TSLA}, NOW, lambda *ls: out.extend(ls)
    )
    text = "\n".join(out)
    assert "RIVN not covered yet: promote it on the UI first" in text
    assert "SEC skipped (--no-sec)" in text
    assert "FY2026: 2 customer(s), 36% at stake ≈ $77.7B" in text
    assert (
        "deliveries: FY2022 1,313,851 → FY2023 1,808,581 vehicles (+37.7%; sum of 4 quarters)"
        in text
    )
    assert "[credit, kept separate]" in text
    tiers.add_tracked(engine, RIVN, "RIVN", reason="t", theme_key=None, by="o", now=NOW)
    tiers.promote(engine, RIVN, "o", NOW)
    out.clear()
    run_financials.units_run(
        engine, corpus, {"NVDA": NVDA, "TSLA": TSLA, "RIVN": RIVN}, NOW, lambda *ls: out.extend(ls)
    )
    assert "RIVN not covered yet" not in "\n".join(out)
    assert "units" in run_financials.BUILT


def test_financials_tab_shows_the_7a_sections(tmp_path):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui.app import create_app
    from engine.ui.settings import UiSettings

    data_dir = tmp_path / "data"
    engine = open_db("engine", data_dir)
    corpus = open_db("corpus", data_dir)
    nvda_stored(engine)
    invitae(engine, corpus)
    engine.close()
    corpus.close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text('[watchlist]\ntickers = ["NVDA"]\n', encoding="utf-8")
    with TestClient(create_app(UiSettings(data_dir=data_dir, watchlist=watch))) as c:
        html = c.get("/c/NVDA?tab=financials").text
    for text in ("Major customers (≥ 10% of revenue)", "36%", "≈ $77.7B", "shorter list is not a loss",
                 "Segments", "115,186 recast", "Unit KPIs", "Reference episodes", "Invitae",
                 "−31.6 pp", "Share classes", "RIVN enters as a promoted company"):  # fmt: skip
        assert text in html, text
    assert "Unit and dimensional data" not in html  # no longer "still to come"
    assert "object at 0x" not in html
