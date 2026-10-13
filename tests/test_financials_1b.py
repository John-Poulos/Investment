# ruff: noqa: E501  (fixture rows)
"""M04 Part 1b: capex definitions and split, core trends and ROIC, guidance record, NVIDIA
instance reads, local-pass signals and the Financials tab (docs/M04_BUILD_LOG.md Part 1b).

Fixtures: tests/fixtures/m04/*_companyfacts_trimmed_20261012.json (hand-built from the R1
brief and the probe log; sources in tests/fixtures/m04/README.md)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from engine.financials import capex, step, trends, views
from engine.guidance import record
from engine.moneyflow import guided, instance
from engine.sec.results import Ok
from engine.sec.xbrl_facts import rebuild_series, store_facts
from tests.conftest import FIXTURES, FakeTransport, ok

M04 = FIXTURES / "m04"
MU, INTC, MSFT, AMZN, NVDA = "0000723125", "0000050863", "0000789019", "0001018724", "0001045810"
AS_OF = "2026-10-12"
M = 1_000_000


def entity(engine, cik, name, fye, ticker=None):
    engine.execute(
        "INSERT OR REPLACE INTO entity (cik, name, fiscal_year_end, source_ref, fetched_at) "
        "VALUES (?, ?, ?, 't', 'n')",
        (cik, name, fye),
    )
    if ticker:
        engine.execute(
            "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES (?, ?, '2000-01-01', 't')",
            (ticker, cik),
        )


def load(engine, cik, name, fye, ticker=None, company="fixture"):
    entity(engine, cik, company, fye, ticker)
    engine.execute("BEGIN")
    store_facts(engine, cik, json.loads((M04 / name).read_text(encoding="utf-8")))
    engine.execute("COMMIT")


def mu(engine):
    load(engine, MU, "mu_companyfacts_trimmed_20261012.json", "0831", "MU", "Micron Technology")


def intc(engine):
    load(engine, INTC, "intc_companyfacts_trimmed_20261012.json", "1231", "INTC", "Intel Corp")


def fact(engine, cik, tag, start, end, value, filed="2026-01-01", form="10-K", unit="USD"):
    engine.execute(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession, "
        "form, filed) VALUES (?, 'us-gaap', ?, ?, ?, ?, ?, ?, ?, ?)",
        (cik, tag, unit, start, end, value, f"{cik}-{end[:4]}-{tag[:8]}", form, filed),
    )


def year(cv: capex.CapexView, label: str) -> capex.CapexYear:
    return next(y for y in cv.years if y.label == label)


# --- Capex definitions and the split (D-M04-3, -6, -78) ----------------------------------------


def test_mu_capex_rows_fy2022_to_fy2026(dbs):
    engine, _ = dbs
    mu(engine)
    engine.execute(
        "INSERT INTO capex_stated (cik, accession, filename, origin, grade, period, period_how, "
        "kind, value, stated_on, quote, quote_start, quote_end, parser_version) VALUES "
        "(?, '0000723125-23-000031', 'ex991.htm', 'release', 'A', 'FY2023', 'stated', 'point', "
        "7010000000, '2023-09-27', 'Net capital expenditures for fiscal 2023 were $7.01 billion.', 0, 60, 'stated-1')",
        (MU,),
    )
    cv = capex.capex_view(engine, MU, AS_OF)
    assert [y.label for y in cv.years] == [f"FY{y}" for y in range(2019, 2027)]
    y22, y23 = year(cv, "FY2022"), year(cv, "FY2023")
    assert (y22.total.value, y23.total.value) == (12_067 * M, 7_676 * M)
    assert (y22.depreciation, y23.depreciation) == (7_030 * M, 7_670 * M)
    assert (y22.ocf, y23.ocf) == (15_181 * M, 1_559 * M)
    # Company definition = M02's shown actual: the stated net capex, recipe gap beside it.
    assert y23.display.shown == 7_010 * M
    assert y23.display_label.startswith("stated net capex (release · A)")
    assert "recipe off by +9.5%" in y23.display_label
    assert cv.definition == "PP&E payments" and not cv.changed_years
    # FCF on total capex and on maintenance (depreciation) capex (R1 brief).
    fcf = {
        lbl: (year(cv, lbl).fcf_total, year(cv, lbl).fcf_maintenance)
        for lbl in ("FY2023", "FY2025", "FY2026")
    }
    assert fcf == {"FY2023": (-6_117 * M, -6_111 * M), "FY2025": (1_668 * M, 9_245 * M),
                   "FY2026": (58_963 * M, 80_255 * M)}  # fmt: skip
    tv = trends.trends_view(engine, MU, AS_OF, cv)
    rows = {r.key: r for r in tv.rows}
    assert round(rows["rev_yoy"].cells["FY2023"].value, 3) == -0.495  # 30,758 → 15,540
    assert round(rows["gm"].cells["FY2022"].value, 1) == 45.2
    assert round(rows["gm"].cells["FY2023"].value, 1) == -9.1
    assert round(rows["gm_trend_pp"].cells["FY2023"].value, 1) == -54.3
    assert rows["gm"].cells["FY2022"].text == "reported gross profit"


def test_split_cases_and_greenwald(dbs):
    engine, _ = dbs
    mu(engine)
    intc(engine)
    load(engine, MSFT, "msft_companyfacts_trimmed_20261012.json", "0630")
    m = capex.capex_view(engine, MU, AS_OF)
    y23, y26 = year(m, "FY2023"), year(m, "FY2026")
    assert (y23.maintenance, y23.growth, y23.rung) == (7_670 * M, 6 * M, "depreciation")
    assert not y23.gw_net_in and "out of range" in y23.greenwald_net_note  # revenue fell
    assert (y26.total.value, y26.maintenance, y26.growth) == (30_712 * M, 9_420 * M, 21_292 * M)
    assert m.gw_net_out == (6, 8) and m.gw_gross_out == (7, 8)
    assert m.gw_line("net") == "Greenwald (net PP&E): out of range in 6 of 8 years"
    i = capex.capex_view(engine, INTC, AS_OF)
    y22 = year(i, "FY2022")
    assert (y22.total.value, y22.maintenance) == (24_844 * M, 11_128 * M)
    assert i.gw_net_out == (4, 4) and i.gw_gross_out == (4, 4)
    s = capex.capex_view(engine, MSFT, AS_OF)
    f26 = year(s, "FY2026")
    assert (f26.total.value, f26.maintenance) == (115_948 * M, 34_300 * M)
    assert f26.gw_net_in and f26.gw_gross_in  # a build-out: Greenwald in range, beside only
    assert round(f26.greenwald_net / f26.total.value, 3) == 0.787
    assert round(f26.greenwald_gross / f26.total.value, 3) == 0.651
    assert f26.method == "depreciation, capped at total capex"


def test_intel_2023_useful_life_mark_on_the_depreciation_rung(dbs):
    engine, _ = dbs
    intc(engine)
    cv = capex.capex_view(engine, INTC, AS_OF)
    marks = year(cv, "FY2023").marks
    assert marks == [
        "useful-life change? depreciation −29.5% while gross PP&E +11.7% (S2.7)".replace("−", "-")
    ]
    assert year(cv, "FY2024").marks == []
    table = views.capex_table(cv)
    assert any("FY2023 maintenance (†): useful-life change?" in line for line in table.lines)


def test_amzn_broader_tag_marker_and_no_definition_change(dbs):
    engine, _ = dbs
    load(engine, AMZN, "amzn_companyfacts_trimmed_20261012.json", "1231")
    tot = {t.label: t for t in capex.total_capex(engine, AMZN, AS_OF)}
    assert set(tot) == {"FY2015", "FY2016", "FY2017"}
    t16 = tot["FY2016"]
    assert t16.definition == "productive" and not t16.definition_changed
    assert t16.mark == "broader tag: includes software and intangibles"
    assert t16.note.startswith("+15.8% vs the PP&E tag")
    cv = capex.capex_view(engine, AMZN, AS_OF)
    assert cv.definition == "productive assets (broader)"
    assert cv.definition_mark == "broader tag: includes software and intangibles"


def test_fiscal_year_points_only_at_the_year_end(dbs):
    """Amazon's 10-Qs carry trailing-twelve-month cash flows; they are not fiscal years."""
    engine, _ = dbs
    load(engine, AMZN, "amzn_companyfacts_trimmed_20261012.json", "1231")
    fact(engine, AMZN, "PaymentsToAcquireProductiveAssets", "2017-07-01", "2018-06-30", 13_000 * M,
         "2018-07-27", "10-Q")  # fmt: skip
    labels = [t.label for t in capex.total_capex(engine, AMZN, AS_OF)]
    assert labels == ["FY2015", "FY2016", "FY2017"]
    assert capex.is_fy_end("2015-09-03", "0831") and not capex.is_fy_end("2018-06-30", "1231")


# --- NVIDIA FY2013–21 from instances (D-M04-3) --------------------------------------------------

IDX13 = "https://www.sec.gov/Archives/edgar/data/1045810/000104581013000008/0001045810-13-000008-index.htm"
IDX21 = "https://www.sec.gov/Archives/edgar/data/1045810/000104581021000010/0001045810-21-000010-index.htm"
INS13 = "https://www.sec.gov/Archives/edgar/data/1045810/000104581013000008/nvda-20130127.xml"
INS21 = "https://www.sec.gov/Archives/edgar/data/1045810/000104581021000010/nvda-20210131_htm.xml"


def nvda_setup(engine):
    load(engine, NVDA, "nvda_companyfacts_trimmed_20261012.json", "0126", "NVDA", "NVIDIA CORP")
    for acc, filed, report, doc in (
        ("0001045810-13-000008", "2013-03-12", "2013-01-27", "q4fy13form10-k.htm"),
        ("0001045810-21-000010", "2021-02-26", "2021-01-31", "nvda-20210131.htm"),
    ):
        engine.execute(
            "INSERT INTO filing (accession, cik, form, filed, report_date, primary_doc, ingested_at) "
            "VALUES (?, ?, '10-K', ?, ?, ?, 'x')",
            (acc, NVDA, filed, report, doc),
        )
        engine.execute("INSERT INTO filing_cik (accession, cik) VALUES (?, ?)", (acc, NVDA))


def nvda_transport():
    return FakeTransport({
        IDX13: [ok((M04 / "nvda_10k_fy2013_index.htm").read_bytes())],
        IDX21: [ok((M04 / "nvda_10k_fy2021_index.htm").read_bytes())],
        INS13: [ok((M04 / "nvda_10k_fy2013_instance_trimmed.xml").read_bytes())],
        INS21: [ok((M04 / "nvda_10k_fy2021_instance_trimmed.xml").read_bytes())],
    })  # fmt: skip


def test_instance_helpers_find_pre_inline_and_extracted_instances(make_client, dbs):
    engine, _ = dbs
    html13 = (M04 / "nvda_10k_fy2013_index.htm").read_text(encoding="utf-8")
    assert instance.instance_href(html13) == INS13
    client = make_client(nvda_transport())
    found = instance.find_instance(client, NVDA, "0001045810-21-000010")
    assert isinstance(found, Ok) and found.data == INS21
    facts = instance.instance_facts((M04 / "nvda_10k_fy2013_instance_trimmed.xml").read_bytes())
    assert ("nvda", "PurchasesOfPropertyAndEquipmentAndIntangibleAssets", "2012-01-30",
            "2013-01-27", 183_300_000.0) in facts  # fmt: skip
    assert any(f[0] == "us-gaap" for f in facts)  # the listing form keeps standard facts too


def test_nvda_capex_from_instances_one_definition_across_the_switch(
    make_client, dbs, clock, monkeypatch
):
    engine, corpus = dbs
    nvda_setup(engine)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_financials as rf

    monkeypatch.setattr(rf, "NVDA_YEARS", (2013, 2021))
    from engine.store.http import SqliteFetchLog

    clog = rf.CountingLog(SqliteFetchLog(engine))
    client = make_client(nvda_transport())
    client._log = clog
    lines: list[str] = []
    rf.nvda_instances(client, engine, corpus, lambda *ls: lines.extend(ls), clog, clock.now())
    assert clog.sent == {"filing index": 2, "XBRL instance": 2}
    assert any("nvda-20130127.xml" in ln and "1 new facts" in ln for ln in lines), lines
    # Instances are parsed, then dropped from the cache (SB.16); index pages stay cached.
    cached = {r[0] for r in corpus.execute("SELECT url FROM http_cache")}
    assert INS13 not in cached and INS21 not in cached and IDX13 in cached
    # Only the extension fact is stored; the us-gaap one in the instance is companyfacts'.
    stored = engine.execute(
        "SELECT taxonomy, tag, value FROM fact WHERE cik = ? AND taxonomy = 'nvda'", (NVDA,)
    ).fetchall()
    assert sorted(float(r["value"]) for r in stored) == [183_300_000.0, 1_128_000_000.0]
    tot = {t.label: t for t in capex.total_capex(engine, NVDA, AS_OF)}
    assert tot["FY2013"].value == 183.3 * M and tot["FY2021"].value == 1_128 * M
    assert tot["FY2013"].tag == "nvda:PurchasesOfPropertyAndEquipmentAndIntangibleAssets"
    assert "includes intangibles" in tot["FY2021"].mark
    assert tot["FY2022"].tag == "us-gaap:PaymentsToAcquireProductiveAssets"
    assert not any(tot[k].definition_changed for k in ("FY2013", "FY2021", "FY2022"))
    assert tot["FY2012"].definition_changed  # the PP&E tag year (illustrative) is the switch
    # A second run reads nothing again (resumable, filings immutable).
    lines.clear()
    rf.nvda_instances(client, engine, corpus, lambda *ls: lines.extend(ls), clog, clock.now())
    assert clog.sent == {"filing index": 2, "XBRL instance": 2}
    assert "2 instance(s) already read" in " ".join(lines)
    rebuild_series(engine, NVDA)
    caps = engine.execute(
        "SELECT method FROM series WHERE cik = ? AND concept = 'capex' AND period_end = '2013-01-27' AND period_type = 'FY'",
        (NVDA,),
    ).fetchone()
    assert "includes intangibles" in caps["method"]


# --- Trends and ROIC (D-M04-11, S2.1, S6.5) ---------------------------------------------------


def test_fcf_growth_not_meaningful_on_negative_or_near_zero_base(dbs):
    engine, _ = dbs
    mu(engine)
    cv = capex.capex_view(engine, MU, AS_OF)
    rows = {r.key: r for r in trends.trends_view(engine, MU, AS_OF, cv).rows}
    g = rows["fcf_growth"].cells
    assert g["FY2024"].value is None and g["FY2024"].text == "not_meaningful: base ≤ 0"
    assert g["FY2025"].text == "not_meaningful: base below 1% of revenue"  # FCF 121 on 25,111
    assert round(g["FY2026"].value, 2) == round(58_963 / 1_668 - 1, 2)
    assert (
        rows["owner_earnings"].cells["FY2026"].text == "missing: no share-based compensation fact"
    )
    assert (
        views.trends_table(trends.trends_view(engine, MU, AS_OF, cv)).rows[3].cells[5].text == "n/m"
    )


def test_roic_s65_definition(dbs):
    engine, _ = dbs
    cik = "0000000042"
    entity(engine, cik, "Illustrative", "1231")
    for end, start in (("2024-12-31", "2024-01-01"), ("2025-12-31", "2025-01-01")):
        fact(engine, cik, "RevenueFromContractWithCustomerExcludingAssessedTax", start, end, 1000)
    fact(engine, cik, "OperatingIncomeLoss", "2025-01-01", "2025-12-31", 100)
    fact(
        engine,
        cik,
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "2025-01-01",
        "2025-12-31",
        90,
    )
    fact(engine, cik, "IncomeTaxExpenseBenefit", "2025-01-01", "2025-12-31", 18)
    for end, eq, cash in (("2024-12-31", 450, 40), ("2025-12-31", 500, 50)):
        fact(engine, cik, "StockholdersEquity", None, end, eq)
        fact(engine, cik, "LongTermDebtNoncurrent", None, end, 100)
        fact(engine, cik, "CashAndCashEquivalentsAtCarryingValue", None, end, cash)
    rows = {r.key: r for r in trends.trends_view(engine, cik, AS_OF).rows}
    c = rows["roic"].cells["FY2025"]
    assert round(c.value, 4) == round(80 / 530, 4)  # NOPAT 100 × (1 − 20%) ÷ avg(510, 550)
    assert "tax rate 20.0%" in c.text and "no fact: debt_current, short_term_investments" in c.text
    # Invested capital ≤ 0 (buybacks) → not meaningful; pretax ≤ 0 → NOPAT = operating income.
    engine.execute(
        "UPDATE fact SET value = -600 WHERE cik = ? AND tag = 'StockholdersEquity'", (cik,)
    )
    assert (
        trends.trends_view(engine, cik, AS_OF)
        .rows[-1]
        .cells["FY2025"]
        .text.startswith("not_meaningful")
    )
    engine.execute(
        "UPDATE fact SET value = 300 WHERE cik = ? AND tag = 'StockholdersEquity'", (cik,)
    )
    engine.execute(
        "UPDATE fact SET value = -5 WHERE cik = ? AND tag LIKE 'IncomeLossFromContinuing%'", (cik,)
    )
    c = trends.trends_view(engine, cik, AS_OF).rows[-1].cells["FY2025"]
    assert c.text.startswith("pretax ≤ 0: NOPAT = operating income") and round(c.value, 4) == round(
        100 / 355, 4
    )


def test_gross_profit_derived_and_labelled(dbs):
    engine, _ = dbs
    cik = "0000000043"
    entity(engine, cik, "Illustrative", "1231")
    for y in (2024, 2025):
        fact(engine, cik, "Revenues", f"{y}-01-01", f"{y}-12-31", 1000 + 100 * (y - 2024))
        fact(engine, cik, "CostOfRevenue", f"{y}-01-01", f"{y}-12-31", 600)
    tv = trends.trends_view(engine, cik, AS_OF)
    gm = next(r for r in tv.rows if r.key == "gm")
    assert tv.gp_derived and gm.cells["FY2025"].text == "derived: revenue − cost of revenue"
    assert round(gm.cells["FY2025"].value, 2) == round(500 / 1100 * 100, 2)


# --- Guidance record (D-M04-10, -79; S1.7) ------------------------------------------------------

_q = [0]


def guide(engine, cik, acc, stated_on, metric, period, kind, low, high, *, basis="GAAP", unit="USD",
          origin="release", grade="A", source="sentence", bound=None, filename="ex991.htm",
          clause=None, direction=None, flag=None):  # fmt: skip
    _q[0] += 10
    engine.execute(
        "INSERT INTO guidance (cik, accession, filename, metric, basis, period, unit, kind, low, "
        "high, stated_on, source, quote, quote_start, quote_end, period_quote, period_start, "
        "period_end, doc_sha256, parser_version, created_at, origin, grade, bound, clause, "
        "direction, flag) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'q', ?, ?, 'p', 0, 1, 's', "
        "'guidance-9', 'n', ?, ?, ?, ?, ?, ?)",
        (cik, acc, filename, metric, basis, period, unit, kind, low, high, stated_on, source,
         _q[0], _q[0] + 5, origin, grade, bound, clause, direction, flag),
    )  # fmt: skip
    return engine.execute("SELECT max(guidance_id) FROM guidance").fetchone()[0]


def release(engine, cik, acc, filed, scanned=True):
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, items, ingested_at) VALUES (?, ?, '8-K', ?, '2.02,9.01', 'x')",
        (acc, cik, filed),
    )
    engine.execute("INSERT INTO filing_cik (accession, cik) VALUES (?, ?)", (acc, cik))
    if scanned:
        engine.execute(
            "INSERT INTO guidance_scan (accession, filename, cik, filed, outcome, candidates, items, "
            "unparsed, conflicts, parser_version, at) VALUES (?, 'ex991.htm', ?, ?, 'parsed', 1, 1, 0, 0, 'guidance-9', 'n')",
            (acc, cik, filed),
        )


def call(engine, cik, acc, quarter, release_acc, stated_on):
    engine.execute(
        "INSERT INTO call_document (accession, filename, cik, symbol, quarter, source, doc_kind, "
        "release_accession, stated_on, added_at) VALUES (?, 'transcript.txt', ?, 'INTC', ?, "
        "'alpha_vantage', 'transcript', ?, ?, 'n')",
        (acc, cik, quarter, release_acc, stated_on),
    )


def test_mu_q3_fy2023_three_hits(dbs):
    engine, _ = dbs
    mu(engine)
    acc = "0000723125-23-000010"
    release(engine, MU, acc, "2023-03-28")
    guide(engine, MU, acc, "2023-03-28", "revenue", "FY2023 Q3", "plusminus", 3.5e9, 3.9e9)
    guide(
        engine,
        MU,
        acc,
        "2023-03-28",
        "gross_margin",
        "FY2023 Q3",
        "plusminus",
        -25.5,
        -20.5,
        unit="%",
    )
    guide(engine, MU, acc, "2023-03-28", "eps_diluted", "FY2023 Q3", "plusminus", -1.86, -1.72)
    rec = record.record_for(engine, None, MU, date(2026, 10, 12))
    got = {o.metric: o for o in rec.outcomes if o.kind == "score"}
    assert {m: o.outcome for m, o in got.items()} == {
        "revenue": "hit",
        "gross_margin": "hit",
        "eps_diluted": "hit",
    }
    assert got["revenue"].actual == 3_752 * M and got["revenue"].state == "within the range"
    assert (
        round(got["gross_margin"].actual, 1) == -17.8
        and got["gross_margin"].state == "above the range"
    )
    assert got["eps_diluted"].actual == -1.73
    assert (rec.hits, rec.misses, rec.hit_rate, rec.repeated) == (3, 0, 1.0, False)


def intel_2022_guides(engine):
    for acc, filed in (("0000050863-22-000020", "2022-04-28"), ("0000050863-22-000030", "2022-07-28"),
                       ("0000050863-22-000040", "2022-10-27")):  # fmt: skip
        release(engine, INTC, acc, filed)
    guide(
        engine,
        INTC,
        "0000050863-22-000020",
        "2022-04-28",
        "revenue",
        "FY2022",
        "approx",
        76e9,
        76e9,
    )
    guide(
        engine, INTC, "0000050863-22-000030", "2022-07-28", "revenue", "FY2022", "range", 65e9, 68e9
    )
    return guide(
        engine, INTC, "0000050863-22-000040", "2022-10-27", "revenue", "FY2022", "range", 63e9, 64e9
    )


def test_intel_fy2022_hit_with_two_downward_revisions(dbs):
    engine, _ = dbs
    intc(engine)
    last = intel_2022_guides(engine)
    rec = record.record_for(engine, None, INTC, date(2026, 10, 12))
    o = next(o for o in rec.outcomes if o.kind == "score" and o.period == "FY2022")
    assert (o.outcome, o.guidance_id, o.actual) == ("hit", last, 63_054 * M)
    assert (o.revisions_down, o.revisions_up) == (2, 0)
    assert o.guide_text == "$63.00B to $64.00B"


def intel_releases(engine, *, apr23_call=True):
    rels = {
        "jan22": ("0000050863-22-000010", "2022-01-26"), "apr22": ("0000050863-22-000020", "2022-04-28"),
        "jan23": ("0000050863-23-000010", "2023-01-26"), "apr23": ("0000050863-23-000020", "2023-04-27"),
    }  # fmt: skip
    for acc, filed in rels.values():
        release(engine, INTC, acc, filed)
    a = {k: v[0] for k, v in rels.items()}
    for m in ("revenue", "eps_diluted"):  # January: next quarter only, both years
        guide(engine, INTC, a["jan22"], "2022-01-26", m, "FY2022 Q1", "range", 1, 2)
        guide(engine, INTC, a["jan23"], "2023-01-26", m, "FY2023 Q1", "range", 1, 2)
        guide(engine, INTC, a["apr22"], "2022-04-28", m, "FY2022 Q2", "range", 1, 2)
        guide(engine, INTC, a["apr23"], "2023-04-27", m, "FY2023 Q2", "range", 1, 2)
    guide(engine, INTC, a["apr22"], "2022-04-28", "revenue", "FY2022", "approx", 76e9, 76e9)
    guide(engine, INTC, a["apr22"], "2022-04-28", "eps_diluted", "FY2022", "approx", 3.6, 3.6)
    guide(engine, INTC, a["apr22"], "2022-04-28", "capex", "FY2022", "approx", 27e9, 27e9)
    call(engine, INTC, "AV-INTC-2022Q4", "FY2022 Q4", a["jan23"], "2023-01-26")
    if apr23_call:
        call(engine, INTC, "AV-INTC-2023Q1", "FY2023 Q1", a["apr23"], "2023-04-27")
    return a


def test_intel_january_2023_not_removed_and_april_2023_removed(dbs):
    engine, corpus = dbs
    entity(engine, INTC, "Intel Corp", "1231")
    a = intel_releases(engine)
    rec = record.record_for(engine, corpus, INTC, date(2023, 5, 20))
    rem = [o for o in rec.outcomes if o.kind == "removal"]
    assert {o.release for o in rem} == {a["apr23"]}  # January 2023 vs January 2022: same position
    assert {(o.metric, o.period, o.outcome) for o in rem} == {
        ("revenue", "FY2023", "removed"), ("eps_diluted", "FY2023", "removed"),
        ("capex", "FY2023", "removed")}  # fmt: skip
    assert all(o.state.startswith("not restated") for o in rem)
    engine.execute("BEGIN")
    n = record.write_signals(engine, rec, "INTC", date(2023, 5, 20))
    engine.execute("COMMIT")
    sig = engine.execute(
        "SELECT * FROM signal WHERE signal = 'guidance_removed' AND timeframe = 'MY'"
    ).fetchall()
    assert n and len(sig) == 1 and sig[0]["value_text"] == "removed" and sig[0]["value"] is None
    assert sig[0]["as_of"] == "2023-04-27" and sig[0]["source_ref"] == f"{a['apr23']} +1"
    for text in ("capex FY2023 removed", "eps_diluted FY2023 removed", "revenue FY2023 removed",
                 "info (weight 0)"):  # fmt: skip
        assert text in sig[0]["method"], text


def test_intel_april_2023_reason_stated_in_the_january_call(dbs):
    engine, corpus = dbs
    entity(engine, INTC, "Intel Corp", "1231")
    intel_releases(engine)
    text = ("Operator: welcome. Given the uncertain macro environment, we are not providing "
            "full-year guidance at this time. We will guide one quarter at a time.")  # fmt: skip
    corpus.execute(
        "INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, fetched_at) "
        "VALUES ('AV-INTC-2022Q4', ?, 'transcript.txt', 'CALL-TRANSCRIPT', 'av://intc', ?, 's', 'n')",
        (INTC, text),
    )
    rec = record.record_for(engine, corpus, INTC, date(2023, 5, 20))
    rem = [o for o in rec.outcomes if o.kind == "removal"]
    assert {o.outcome for o in rem} == {"unscored"} and {o.state for o in rem} == {"reason stated"}
    assert rem[0].reason[0] == "AV-INTC-2022Q4"
    assert "we are not providing full-year guidance at this time." in rem[0].reason[2]


def test_removal_needs_the_call_or_reads_missing(dbs):
    engine, corpus = dbs
    entity(engine, INTC, "Intel Corp", "1231")
    intel_releases(engine, apr23_call=False)
    rec = record.record_for(engine, corpus, INTC, date(2023, 5, 20))
    rem = [o for o in rec.outcomes if o.kind == "removal"]
    assert {(o.outcome, o.state) for o in rem} == {("missing", "call not stored yet")}
    # Once the period has ended, the removal reads "expired".
    rec = record.record_for(engine, corpus, INTC, date(2024, 2, 1))
    assert {o.outcome for o in rec.outcomes if o.kind == "removal"} == {"expired"}


def test_scoring_rules_floor_ceiling_point_review_owner_and_grade(dbs):
    engine, _ = dbs
    cik = "0000000044"
    entity(engine, cik, "Illustrative", "1231")
    fact(engine, cik, "Revenues", "2025-01-01", "2025-12-31", 120e9, "2026-02-01")
    fact(engine, cik, "OperatingIncomeLoss", "2025-01-01", "2025-12-31", 30e9, "2026-02-01")
    fact(engine, cik, "NetIncomeLoss", "2025-01-01", "2025-12-31", 20e9, "2026-02-01")
    fact(
        engine,
        cik,
        "EarningsPerShareDiluted",
        "2025-01-01",
        "2025-12-31",
        2.0,
        "2026-02-01",
        unit="USD/shares",
    )
    acc = "0000000044-25-000001"
    release(engine, cik, acc, "2025-04-30")
    guide(engine, cik, acc, "2025-04-30", "revenue", "FY2025", "point", 100e9, 100e9, bound="floor",
          origin="call", grade="B", filename="transcript.txt")  # fmt: skip
    guide(
        engine,
        cik,
        acc,
        "2025-04-30",
        "operating_income",
        "FY2025",
        "point",
        25e9,
        25e9,
        bound="ceiling",
    )
    guide(engine, cik, acc, "2025-04-30", "net_income", "FY2025", "approx", 19e9, 19e9)
    gid = guide(engine, cik, acc, "2025-04-30", "eps_diluted", "FY2025", "range", 2.5, 3.0)
    rec = record.record_for(engine, None, cik, date(2026, 10, 12))
    got = {o.metric: o for o in rec.outcomes if o.kind == "score"}
    assert (got["revenue"].outcome, got["revenue"].state, got["revenue"].grade) == (
        "hit",
        "at or above the floor",
        "B",
    )
    assert got["operating_income"].outcome == "unscored" and got[
        "operating_income"
    ].state.startswith("ceiling")
    assert got["net_income"].state == "approx guide: no tolerance yet (D-M04-10)"
    assert got["eps_diluted"].outcome == "miss"
    # An open implausible item keeps the row unscored until resolved (D-M04-79).
    engine.execute(
        "INSERT INTO review_queue (module_id, kind, cik, reason, payload, created_at) VALUES "
        "('M11', 'guidance_implausible', ?, 'r', ?, 'n')",
        (cik, json.dumps({"accession": acc, "guidance_id": gid, "offsets": [0, 1]})),
    )
    rec = record.record_for(engine, None, cik, date(2026, 10, 12))
    eps = next(o for o in rec.outcomes if o.metric == "eps_diluted")
    assert (eps.outcome, eps.state) == ("unscored", "open guidance_implausible review")
    # An owner correction stated the same day wins over the parser's row.
    acc2 = "0000000044-25-000002"
    guide(engine, cik, acc2, "2025-07-30", "eps_diluted", "FY2025", "range", 1.5, 2.2)
    guide(
        engine,
        cik,
        acc2,
        "2025-07-30",
        "eps_diluted",
        "FY2025",
        "range",
        2.4,
        2.6,
        source="owner",
        filename="owner",
    )
    eps = next(
        o
        for o in record.record_for(engine, None, cik, date(2026, 10, 12)).outcomes
        if o.metric == "eps_diluted"
    )
    assert (eps.origin, eps.outcome) == ("owner", "miss")


def test_non_gaap_missing_and_release_silent_guider(dbs):
    engine, _ = dbs
    cik = "0000000045"
    entity(engine, cik, "Illustrative", "1231")
    release(engine, cik, "0000000045-25-000001", "2025-04-30")
    rec = record.record_for(engine, None, cik, date(2026, 10, 12))
    assert (
        rec.missing
        == "(DS1) release-silent guider: no guidance in 1 scanned earnings release(s) or stored calls"
    )
    guide(
        engine,
        cik,
        "0000000045-25-000001",
        "2025-04-30",
        "revenue",
        "FY2025",
        "range",
        1,
        2,
        basis="non-GAAP",
    )
    rec = record.record_for(engine, None, cik, date(2026, 10, 12))
    o = next(o for o in rec.outcomes if o.kind == "score")
    assert (o.outcome, o.state) == (
        "missing",
        "non-GAAP: the stated reconciliation is not stored yet",
    )
    assert rec.missing == "no scored guide yet (missing 1)"


def test_repeated_two_misses_in_last_four_guided_quarters():
    def o(period, end, outcome):
        return record.Outcome("score", "revenue", "GAAP", period, outcome, end=end)

    outs = [o("FY2025 Q1", "2025-03-31", "miss"), o("FY2025 Q2", "2025-06-30", "hit"),
            o("FY2025 Q3", "2025-09-30", "miss"), o("FY2025 Q4", "2025-12-31", "hit")]  # fmt: skip
    assert record._repeated(outs)
    assert not record._repeated(outs + [o("FY2026 Q1", "2026-03-31", "hit")])


def test_freshness_extended_to_other_metrics_and_capex_refusal_scoped(dbs):
    engine, corpus = dbs
    cik = "0000000046"
    entity(engine, cik, "Illustrative", "1231")
    acc = "0000000046-26-000001"
    release(engine, cik, acc, "2026-04-29")
    call(engine, cik, "AV-X-2026Q1", "FY2026 Q1", acc, "2026-04-29")
    guide(engine, cik, acc, "2026-04-29", "revenue", "FY2026 Q2", "range", 1, 2)
    text = "We are not providing a specific outlook for 2027 CapEx at this point."
    corpus.execute(
        "INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, fetched_at) "
        "VALUES ('AV-X-2026Q1', ?, 'transcript.txt', 'CALL-TRANSCRIPT', 'av://x', ?, 's', 'n')",
        (cik, text),
    )
    engine.execute(
        "INSERT INTO guidance_skip (accession, filename, cik, start_offset, end_offset, reason, "
        "parser_version) VALUES ('AV-X-2026Q1', 'transcript.txt', ?, 0, ?, ?, 'guidance-9')",
        (cik, len(text), guided.NO_OUTLOOK),
    )
    today = date(2026, 5, 10)
    assert (
        guided.freshness(engine, cik, "FY2026 Q2", today, corpus, metric="revenue").state
        == "restated"
    )
    assert (
        guided.freshness(engine, cik, "FY2027", today, corpus, metric="tax_rate").state
        == "not restated"
    )
    assert (
        guided.freshness(engine, cik, "FY2027", today, corpus).state
        == "company gives no outlook yet"
    )
    assert record.stated_reason(engine, corpus, ["AV-X-2026Q1"], "tax_rate") is None
    assert record.stated_reason(engine, corpus, ["AV-X-2026Q1"], "capex")[2] == text


# --- Local pass, signals and the tab ----------------------------------------------------------


def test_local_pass_stores_split_outcomes_and_info_signals(dbs):
    engine, corpus = dbs
    mu(engine)
    acc = "0000723125-23-000010"
    release(engine, MU, acc, "2023-03-28")
    guide(engine, MU, acc, "2023-03-28", "revenue", "FY2023 Q3", "plusminus", 3.5e9, 3.9e9)
    now = datetime(2026, 10, 12, 12, tzinfo=UTC)
    got = step.part1b(engine, corpus, MU, "MU", now)
    assert got.record.hits == 1
    split = engine.execute(
        "SELECT * FROM capex_split WHERE cik = ? ORDER BY period_end", (MU,)
    ).fetchall()
    assert (
        len(split) == 8
        and split[-1]["rung"] == "depreciation"
        and split[-1]["maintenance"] == 9_420 * M
    )
    assert split[-1]["greenwald_net"] is None and "out of range" in split[-1]["greenwald_note"]
    assert (
        engine.execute("SELECT outcome FROM guidance_outcome WHERE cik = ?", (MU,)).fetchone()[0]
        == "hit"
    )
    sig = {
        (r["signal"], r["timeframe"]): r
        for r in engine.execute("SELECT * FROM signal WHERE cik = ?", (MU,))
    }
    for name in ("rev_yoy", "rev_cagr3", "fcf_growth", "fcf_growth_oe", "gm_trend_pp", "opex_vs_sales",
                 "capex_maint", "capex_growth", "owner_earnings", "guidance_hit_rate"):  # fmt: skip
        assert (name, "MY") in sig, name
    assert sig[("capex_maint", "PT")]["value"] == 9_420 * M
    assert "info (weight 0)" in sig[("capex_maint", "MY")]["method"]
    assert "info (weight 0)" in sig[("rev_cagr3", "PT")]["method"]
    assert sig[("guidance_hit_rate", "MY")]["value"] == 100.0
    assert "info (weight 0)" not in sig[("guidance_hit_rate", "MY")]["method"]
    assert "info (weight 0)" in sig[("guidance_hit_rate", "ST")]["method"]
    assert sig[("owner_earnings", "MY")]["method"].startswith(
        "missing: no share-based compensation fact"
    )
    assert sig[("fcf_growth", "MY")]["value"] is not None and sig[("rev_cagr3", "MY")][
        "value"
    ] == pytest.approx(1.046, abs=1e-3)
    # Re-running replaces rows (idempotent).
    step.part1b(engine, corpus, MU, "MU", now)
    assert (
        engine.execute("SELECT count(*) FROM capex_split WHERE cik = ?", (MU,)).fetchone()[0] == 8
    )


def test_financials_tab_shows_capex_trends_and_guidance(tmp_path):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui.app import create_app
    from engine.ui.settings import UiSettings

    data = tmp_path / "data"
    engine = open_db("engine", data)
    open_db("corpus", data).close()
    mu(engine)
    acc = "0000723125-23-000010"
    release(engine, MU, acc, "2023-03-28")
    guide(engine, MU, acc, "2023-03-28", "revenue", "FY2023 Q3", "plusminus", 3.5e9, 3.9e9)
    engine.close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text('[watchlist]\ntickers = ["MU"]\n', encoding="utf-8")
    with TestClient(create_app(UiSettings(data_dir=data, watchlist=watch))) as c:
        html = c.get("/c/MU?tab=financials").text
    for text in ("Capex", "Core trends", "Guidance record", "7,676", "30,712", "9,420",
                 "Greenwald (net PP&amp;E): out of range in 6 of 8 years",
                 "Maintenance capex (depreciation, capped at total capex)", "Hit rate 100%",
                 "within the range", "$3.50B to $3.90B", "rev_cagr3", "ROIC (S6.5)",
                 "missing: not built, Part 1c"):  # fmt: skip
        assert text in html, text
    assert "object at 0x" not in html


def test_fixture_tests_cannot_open_the_owner_data_folder():
    import pytest

    from engine.store.db import data_dir, open_db

    with pytest.raises(AssertionError, match="owner's data folder"):
        open_db("engine", data_dir())


# --- Part 1b live check 1 fixes (D-M04-3, -84, -85) --------------------------------------------


def test_amzn_window_definition_beats_older_ppe_years(dbs):
    """The definition covering the displayed window wins, not the one with more years over
    the whole history (live check 1: Amazon's PP&E tag runs back further)."""
    engine, _ = dbs
    load(engine, AMZN, "amzn_companyfacts_trimmed_20261012.json", "1231")
    for y in range(2004, 2015):  # older PP&E-tag years: 12 PP&E years vs 11 productive
        fact(engine, AMZN, "PaymentsToAcquirePropertyPlantAndEquipment", f"{y}-01-01",
             f"{y}-12-31", (100 + y - 2004) * M, f"{y + 1}-02-01")  # fmt: skip
    for y in range(2018, 2026):
        fact(engine, AMZN, "PaymentsToAcquireProductiveAssets", f"{y}-01-01", f"{y}-12-31",
             (12_000 + 1_000 * (y - 2018)) * M, f"{y + 1}-02-01")  # fmt: skip
    for y in range(2015, 2026):
        fact(engine, AMZN, "Revenues", f"{y}-01-01", f"{y}-12-31", (100_000 + 10_000 * (y - 2015)) * M,
             f"{y + 1}-02-01")  # fmt: skip
        fact(engine, AMZN, "NetCashProvidedByUsedInOperatingActivities", f"{y}-01-01",
             f"{y}-12-31", (20_000 + 3_000 * (y - 2015)) * M, f"{y + 1}-02-01")  # fmt: skip
    tot = {t.label: t for t in capex.total_capex(engine, AMZN, AS_OF)}
    window = [f"FY{y}" for y in range(2018, 2026)]
    assert all(tot[k].definition == "productive" and not tot[k].definition_changed for k in window)
    assert tot["FY2016"].definition == "productive" and not tot["FY2016"].definition_changed
    # Years outside the window filled from the PP&E tag are still marked.
    assert tot["FY2014"].definition_changed and tot["FY2004"].definition_changed
    assert tot["FY2014"].note == "definition changed: PP&E payments this year (not scored)"
    cv = capex.capex_view(engine, AMZN, AS_OF)
    assert cv.definition == "productive assets (broader)" and cv.changed_years == []
    assert [y.label for y in cv.years] == window
    g = {r.key: r for r in trends.trends_view(engine, AMZN, AS_OF, cv).rows}["fcf_growth"].cells
    ocf25, ocf24 = 50_000 * M, 47_000 * M
    assert g["FY2025"].value == pytest.approx((ocf25 - 19_000 * M) / (ocf24 - 18_000 * M) - 1)
    # A tie in the window goes to the PP&E tag.
    for y in range(2018, 2026):
        fact(engine, AMZN, "PaymentsToAcquirePropertyPlantAndEquipment", f"{y}-01-01",
             f"{y}-12-31", (11_000 + 1_000 * (y - 2018)) * M, f"{y + 1}-02-01")  # fmt: skip
    tot = {t.label: t for t in capex.total_capex(engine, AMZN, AS_OF)}
    assert tot["FY2025"].definition == "ppe" and tot["FY2025"].value == 18_000 * M
    assert tot["FY2015"].definition_changed  # productive-only year, now outside the series


def test_capex_guide_scored_only_on_an_exact_recipe(dbs):
    """MSFT FY2026: guide >= $40B with an unmapped clause, PP&E-only actual $35.8B: unscored."""
    engine, _ = dbs
    cik = "0000000047"
    entity(engine, cik, "Illustrative", "0630")
    fact(engine, cik, "PaymentsToAcquirePropertyPlantAndEquipment", "2025-07-01", "2026-06-30",
         35_802 * M, "2026-07-30")  # fmt: skip
    fact(engine, cik, "PaymentsToAcquirePropertyPlantAndEquipment", "2024-07-01", "2025-06-30",
         30_000 * M, "2025-07-30")  # fmt: skip
    acc = "0000000047-25-000001"
    release(engine, cik, acc, "2025-04-30")
    clause = "including the lease reclassification impact from the useful life update"
    guide(engine, cik, acc, "2025-10-29", "capex", "FY2026", "point", 40e9, 40e9, bound="floor",
          clause=clause)  # fmt: skip
    guide(engine, cik, acc, "2025-01-29", "capex", "FY2025", "point", 32e9, 32e9, bound="floor")
    rec = record.record_for(engine, None, cik, date(2026, 10, 12))
    got = {o.period: o for o in rec.outcomes if o.kind == "score"}
    assert (got["FY2026"].outcome, got["FY2026"].state) == (
        "unscored", f"capex recipe approximate ({clause})")  # fmt: skip
    assert got["FY2026"].actual == 35_802 * M  # still shown
    assert (got["FY2025"].outcome, got["FY2025"].state) == ("miss", "below the floor")  # exact
    assert (rec.hits, rec.misses) == (0, 1)


def _row(metric, kind, low, high, bound=None):
    return {"metric": metric, "kind": kind, "low": low, "high": high, "bound": bound,
            "flag": None, "flag_reason": None}  # fmt: skip


def test_direction_aware_scoring_cost_and_not_a_target():
    act = record.ActualValue
    s = record._score_one
    # Performance metrics miss below the low end.
    assert s(_row("revenue", "range", 10, 12), act(9.0)) == ("miss", "below the low end")
    assert s(_row("operating_income", "range", 10, 12), act(13.0)) == ("hit", "above the range")
    # Cost metrics miss above the high end.
    assert s(_row("operating_expenses", "range", 10, 12), act(13.0)) == (
        "miss", "above the high end")  # fmt: skip
    assert s(_row("operating_expenses", "range", 10, 12), act(9.0)) == ("hit", "below the range")
    assert s(_row("total_expenses", "range", 10, 12), act(11.0)) == ("hit", "within the range")
    assert s(_row("operating_expenses", "point", 12, 12, "ceiling"), act(12.5)) == (
        "miss", "above the ceiling")  # fmt: skip
    assert s(_row("operating_expenses", "point", 10, 10, "floor"), act(9.0))[0] == "unscored"
    assert s(_row("operating_expenses", "range", 10, 12), act(None, why="no actual"))[0] == (
        "missing")  # fmt: skip
    # Tax rate and other income are not performance targets (NVDA, META rows).
    for m in ("tax_rate", "other_income"):
        assert s(_row(m, "range", 15.5, 17.5), act(12.4)) == (
            "unscored", "not a performance target (D-M04-84)")  # fmt: skip


def test_tax_rate_rows_unscored_in_the_record(dbs):
    engine, _ = dbs
    cik = "0000000048"
    entity(engine, cik, "Illustrative", "1231")
    acc = "0000000048-25-000001"
    release(engine, cik, acc, "2025-04-30")
    guide(engine, cik, acc, "2025-04-30", "tax_rate", "FY2025", "range", 12.0, 15.0, unit="%",
          basis="unspecified")  # fmt: skip
    rec = record.record_for(engine, None, cik, date(2026, 10, 12))
    o = next(o for o in rec.outcomes if o.kind == "score")
    assert (o.outcome, o.state) == ("unscored", "not a performance target (D-M04-84)")
    assert rec.scored == 0 and rec.missing == "no scored guide yet (unscored 1)"


def test_only_core_families_count_as_removed(dbs):
    engine, corpus = dbs
    entity(engine, INTC, "Intel Corp", "1231")
    a = intel_releases(engine)
    guide(
        engine, INTC, a["apr22"], "2022-04-28", "operating_expenses", "FY2022", "approx", 2e10, 2e10
    )
    guide(
        engine, INTC, a["apr22"], "2022-04-28", "tax_rate", "FY2022", "approx", 13.0, 13.0, unit="%"
    )
    rec = record.record_for(engine, corpus, INTC, date(2023, 5, 20))
    rem = {o.metric: o for o in rec.outcomes if o.kind == "removal"}
    assert {m: o.outcome for m, o in rem.items()} == {
        "revenue": "removed", "eps_diluted": "removed", "capex": "removed",
        "operating_expenses": "dropped", "tax_rate": "dropped"}  # fmt: skip
    assert rem["tax_rate"].state.startswith("dropped (information): removed; not restated")
    engine.execute("BEGIN")
    record.write_signals(engine, rec, "INTC", date(2023, 5, 20))
    record.store(engine, rec, "n")
    engine.execute("COMMIT")
    sig = engine.execute(
        "SELECT method FROM signal WHERE signal = 'guidance_removed' AND timeframe = 'MY'"
    ).fetchall()
    assert len(sig) == 1 and "tax_rate" not in sig[0][0] and "operating_expenses" not in sig[0][0]
    stored = engine.execute(
        "SELECT outcome FROM guidance_outcome WHERE kind = 'removal' AND metric = 'tax_rate'"
    ).fetchone()
    assert stored[0] == "dropped"
    # Once the period has ended, a non-core removal is still "dropped", not "expired".
    rec = record.record_for(engine, corpus, INTC, date(2024, 2, 1))
    got = {o.metric: o.outcome for o in rec.outcomes if o.kind == "removal"}
    assert got["tax_rate"] == "dropped" and got["revenue"] == "expired"


def test_capex_no_sec_recomputes_locally_and_prints_the_summary(tmp_path):
    """`run_financials.py capex --no-sec`: 0 requests, NVIDIA series rebuilt, same summary."""
    import argparse

    from engine.store.db import open_db

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_financials as rf

    data = tmp_path / "data"
    engine = open_db("engine", data)
    open_db("corpus", data).close()
    nvda_setup(engine)
    engine.close()
    lines: list[str] = []
    args = argparse.Namespace(no_sec=True, tickers="NVDA")
    assert rf.run_capex(args, lambda *ls: lines.extend(ls), data) == 0
    text = "\n".join(lines)
    for want in ("SEC skipped (--no-sec)", "NVIDIA series rebuilt from stored facts (0 requests)",
                 "=== Summary (what the owner looks for) ===", "  NVDA: total capex = ",
                 "NVIDIA pre-FY2022 capex", "SEC requests: 0 (--no-sec)"):  # fmt: skip
        assert want in text, want
