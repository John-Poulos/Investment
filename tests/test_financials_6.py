# ruff: noqa: E501  (fixture rows)
"""M04 Part 6: earnings quality — CFO/NI, accruals, M-score, misstatement score, contract
gaps, estimate changes, recurring "one-time" charges, signals, review items and the
`quality` run (docs/M04_BUILD_LOG.md Part 6; D-M04-14, -17…21, -60, -90…93).

Fixtures: tests/fixtures/m04/quality_cases_20261013.json (per-company 10-K values; NVIDIA
FY2023–25, Apple and Microsoft as reported to the best of the build's knowledge, the rest
illustrative — README "Part 6"), the GE contract-asset and Lockheed catch-up companyconcept
files, and two GE 10-K text excerpts. Alphabet, Amazon and the synthetic cases are entered
in the tests. Never calls SEC."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from engine.financials import estimates, quality, quality_step, queue, special, stage
from engine.sec.documents import IndexDoc, store_document
from engine.sec.xbrl_facts import store_concept, store_facts
from tests.conftest import FIXTURES, FakeTransport, ok

M04 = FIXTURES / "m04"
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
M = 1_000_000
GE, LMT, GOOG, AMZN, ZZZ = "0000040545", "0000936468", "0001652044", "0001018724", "0000099999"
CASES = json.loads((M04 / "quality_cases_20261013.json").read_text(encoding="utf-8"))["companies"]
INSTANT = {"AccountsReceivableNetCurrent", "AssetsCurrent", "PropertyPlantAndEquipmentNet", "Assets",
           "LiabilitiesCurrent", "LongTermDebtNoncurrent", "Liabilities", "CashAndCashEquivalentsAtCarryingValue",
           "MarketableSecuritiesCurrent", "ShortTermInvestments", "LongTermDebtCurrent", "DebtCurrent", "InventoryNet",
           "ContractWithCustomerAssetNetCurrent", "ContractWithCustomerLiabilityCurrent"}  # fmt: skip


def load(engine, ticker):
    """Store one company of the fixture as us-gaap facts; returns its CIK."""
    c = CASES[ticker]
    facts: dict[str, list] = {}
    years = c["years"]
    for i, y in enumerate(years):
        for tag, v in y["values"].items():
            row = {
                "end": y["end"],
                "val": v * M,
                "accn": y["accn"],
                "form": "10-K",
                "filed": y["filed"],
            }
            if tag not in INSTANT:
                row["start"] = y["start"]
            facts.setdefault(tag, []).append(row)
        for tag, v in (y.get("prior") or {}).items():
            facts.setdefault(tag, []).append({"end": years[i - 1]["end"], "val": v * M, "accn": y["accn"],
                                              "form": "10-K", "filed": y["filed"]})  # fmt: skip
    engine.execute("BEGIN")
    store_facts(
        engine,
        c["cik"],
        {"facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in facts.items()}}},
    )
    engine.execute("COMMIT")
    return c["cik"]


def synth(engine, cik, years, accn_prefix="0000099999"):
    """Synthetic fiscal years: years = [(end, {tag: $M}), …] (calendar years, own 10-K each)."""
    facts: dict[str, list] = {}
    for i, (end, vals) in enumerate(years):
        acc = f"{accn_prefix}-{end[2:4]}-9{i:05d}"
        filed = f"{int(end[:4]) + 1}-02-15"
        for tag, v in vals.items():
            row = {"end": end, "val": v * M, "accn": acc, "form": "10-K", "filed": filed}
            if tag not in INSTANT:
                row["start"] = f"{end[:4]}-01-01"
            facts.setdefault(tag, []).append(row)
    engine.execute("BEGIN")
    store_facts(
        engine, cik, {"facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in facts.items()}}}
    )
    engine.execute("COMMIT")


def concept_file(engine, cik, name):
    engine.execute("BEGIN")
    store_concept(engine, cik, json.loads((M04 / name).read_text(encoding="utf-8")))
    engine.execute("COMMIT")


def concept(engine, cik, tag, rows, taxonomy="us-gaap"):
    data = {"cik": int(cik), "taxonomy": taxonomy, "tag": tag,
            "units": {"USD": [{"start": s, "end": e, "val": v, "accn": a, "form": f, "filed": d}
                              for s, e, v, a, f, d in rows]}}  # fmt: skip
    engine.execute("BEGIN")
    store_concept(engine, cik, data)
    engine.execute("COMMIT")


def doc(corpus, cik, acc, text, doc_type="10-K", name="doc.htm"):
    d = IndexDoc(1, None, name.replace(".htm", ".txt"), f"https://x/{acc}/{name}", doc_type, None,
                 False)  # fmt: skip
    store_document(corpus, cik, acc, d, text.encode("utf-8"), NOW)


def filing(engine, cik, acc, form, filed, report=None):
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, report_date, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, 'x')",
        (acc, cik, form, filed, report),
    )
    engine.execute("INSERT INTO filing_cik (accession, cik) VALUES (?, ?)", (acc, cik))


def q_of(engine, ticker, **kw):
    return quality.compute(engine, load(engine, ticker), ticker, **kw)


def score(q, label):
    return (
        next(m for m in q.mscores if m.label == label),
        next(f for f in q.fscores if f.label == label),
    )


# --- M-score and misstatement score (D-M04-14) -------------------------------------------------


def test_nvda_fy2025_growth_driven_note_and_f_3_11(dbs):
    engine, _ = dbs
    ms, fs = score(q_of(engine, "NVDA"), "FY2025")
    assert ms.m == pytest.approx(-0.956, abs=0.005) and ms.m_sgi1 == pytest.approx(
        -1.975, abs=0.005
    )
    assert ms.components["SGI"] == pytest.approx(2.142, abs=0.001)
    assert ms.reading == "growth_driven"
    assert fs.score == pytest.approx(3.11, abs=0.01) and fs.band == "above_2.45"
    assert fs.components["rsst_acc"] == pytest.approx(0.395, abs=0.002)
    assert (
        fs.components["ch_cs"] == pytest.approx(1.145, abs=0.002) and fs.components["issue"] == 1.0
    )
    # current debt went to none: the FY2025 report tags only FY2024's 1,250 (D-M04-90)
    assert "debt in current liabilities: none in FY2025" in fs.inputs.method()


def test_nvda_fy2026_review_and_f_incomplete_on_tag_switch(dbs):
    engine, _ = dbs
    ms, fs = score(q_of(engine, "NVDA"), "FY2026")
    assert ms.m == pytest.approx(-1.17, abs=0.005) and ms.m_sgi1 == pytest.approx(-1.75, abs=0.005)
    assert ms.components["AQI"] == pytest.approx(1.52, abs=0.01)
    assert ms.reading == "review"
    assert fs.state == "incomplete" and fs.score is None
    assert "short-term investments FY2026" in fs.why and "tag switch" in fs.why


def test_mrvl_fy2026_note_and_issue_unknown(dbs):
    engine, _ = dbs
    ms, fs = score(q_of(engine, "MRVL"), "FY2026")
    assert ms.m == pytest.approx(-1.60, abs=0.005) and ms.m_sgi1 == pytest.approx(-1.98, abs=0.005)
    assert ms.reading == "growth_driven"
    assert fs.score is None and "issue FY2026" in fs.why and "unknown" in fs.why


def test_aapl_and_msft_fy2025(dbs):
    engine, _ = dbs
    ms, fs = score(q_of(engine, "AAPL"), "FY2025")
    assert (round(ms.m, 2), round(ms.m_sgi1, 2), round(fs.score, 2)) == (-2.29, -2.35, 1.30)
    assert ms.reading == "below" and fs.band == "above_1.00"
    assert "D&A for depreciation" in ms.inputs.method()
    ms, fs = score(q_of(engine, "MSFT"), "FY2025")
    # Round 2 scratch: −2.54 / −2.67, F 1.15; this fixture gives −2.544 / −2.678 (build notes)
    assert ms.m == pytest.approx(-2.54, abs=0.01) and ms.m_sgi1 == pytest.approx(-2.68, abs=0.01)
    assert fs.score == pytest.approx(1.15, abs=0.01)
    assert "SG&A = S&M + G&A" in ms.inputs.method()


def test_ba_fy2024_incomplete_without_sga_and_mu_fy2023_not_meaningful(dbs):
    engine, _ = dbs
    ms, fs = score(q_of(engine, "BA"), "FY2024")
    assert ms.state == "incomplete" and ms.m is None
    assert "SG&A FY2024" in ms.why and "depreciation" not in ms.why
    assert fs.state == "ok" and fs.score == pytest.approx(
        1.75, abs=0.01
    )  # spec 1.63 (illustrative inputs)
    ms, _ = score(q_of(engine, "MU"), "FY2023")
    assert ms.state == "not_meaningful" and ms.reading == "not_meaningful"
    assert ms.components["GMI"] == pytest.approx(-4.96, abs=0.01)
    assert "gross margin ≤ 0" in ms.why and "raw M" in ms.why


def test_mstr_not_meaningful_by_tag_with_swings_shown(dbs):
    engine, _ = dbs
    q = q_of(engine, "MSTR")
    assert q.tag == "asset_treasury"
    assert all(m.state == "not_meaningful" for m in q.mscores)
    assert all(f.state == "not_meaningful" for f in q.fscores)
    assert q.cash.state == "not_meaningful"
    ((label, what, v, effect, share),) = q.swings
    assert label == "FY2025" and v.value == -5_403 * M and "digital-asset" in what
    assert effect == pytest.approx(-5_403 * M * 0.79) and share == pytest.approx(
        -5_403 * 0.79 / 3_848
    )


def test_missing_never_zero_and_optional_lines_named(dbs):
    engine, _ = dbs
    ms, _ = score(q_of(engine, "NVDA"), "FY2024")
    assert ms.state == "incomplete" and ms.m is None
    assert "cost of revenue FY2023" in ms.why
    _, fs = score(q_of(engine, "AAPL"), "FY2025")
    assert "long-term investments: no tag either year" in fs.inputs.method()


# --- Cash conversion and accruals (D-M04-20, S2.1) --------------------------------------------


def test_tsla_valuation_allowance_release_switches_to_operating_basis(dbs):
    engine, _ = dbs
    cc = q_of(engine, "TSLA").cash
    y23 = next(y for y in cc.years if y.label == "FY2023")
    assert y23.operating and y23.basis_ni == pytest.approx(9_035 * M)
    assert cc.ratio3 == pytest.approx(
        (14_724 + 13_256 + 14_923) / (12_556 + 9_035 + 7_091), abs=1e-6
    )
    assert cc.state == "ok"


def three_years(cfo_ni=0.72):
    rows = []
    for y, ni in (("2023", 1000), ("2024", 1100), ("2025", 1200)):
        rows.append((f"{y}-12-31", {"Revenues": 10_000, "NetIncomeLoss": ni,
                                     "NetCashProvidedByUsedInOperatingActivities": round(ni * cfo_ni),
                                     "Assets": 20_000}))  # fmt: skip
    return rows


@pytest.mark.parametrize("st, want", [("mature", "warn"), ("decline", "warn"), ("growth", "note"),
                                      ("introduction", "note"), ("shake_out", "note"), (None, "warn_or_note")])  # fmt: skip
def test_cfo_ni_below_0_8_routes_by_confirmed_stage(dbs, st, want):
    engine, _ = dbs
    synth(engine, ZZZ, three_years())
    cc = quality.compute(engine, ZZZ, "ZZZ", stage=st).cash
    assert cc.ratio3 == pytest.approx(0.72, abs=0.001) and cc.state == want


def test_cfo_ni_not_meaningful_on_losses_or_tiny_income(dbs):
    engine, _ = dbs
    synth(engine, ZZZ, [(f"{y}-12-31", {"Revenues": 10_000, "NetIncomeLoss": -100,
                                         "NetCashProvidedByUsedInOperatingActivities": -50})
                        for y in ("2023", "2024", "2025")])  # fmt: skip
    cc = quality.compute(engine, ZZZ).cash
    assert cc.state == "not_meaningful" and cc.ratio3 is None  # NI −100, CFO −50 never reads 0.5
    synth(engine, "0000099998", [(f"{y}-12-31", {"Revenues": 10_000, "NetIncomeLoss": 20,
                                                  "NetCashProvidedByUsedInOperatingActivities": 500})
                                 for y in ("2023", "2024", "2025")], "0000099998")  # fmt: skip
    cc = quality.compute(engine, "0000099998").cash
    assert cc.state == "not_meaningful" and "below 1% of revenue" in cc.why


def test_accruals_against_own_history_never_warn(dbs):
    engine, _ = dbs
    rows = [(f"{y}-12-31", {"Revenues": 10_000, "NetIncomeLoss": 1000,
                            "NetCashProvidedByUsedInOperatingActivities": 1000 - d, "Assets": 20_000})
            for y, d in (("2019", 100), ("2020", 120), ("2021", 80), ("2022", 110), ("2023", 90), ("2024", 400))]  # fmt: skip
    synth(engine, ZZZ, rows)
    cc = quality.compute(engine, ZZZ, stage="mature").cash
    assert cc.accruals == pytest.approx(0.02) and cc.accruals_text == "above_own_range"
    assert cc.state == "ok"  # 3-year CFO/NI ≥ 0.8; accruals never set a warning


# --- Contract assets and deferred revenue (S2.2) ---------------------------------------------


def ge_facts(engine):
    concept(engine, GE, "Revenues", [
        ("2015-01-01", "2015-12-31", 117_386 * M, "0000040545-16-900001", "10-K", "2016-02-26"),
        ("2016-01-01", "2016-12-31", 123_693 * M, "0000040545-17-000010", "10-K", "2017-02-24"),
        ("2017-01-01", "2017-12-31", 122_092 * M, "0000040545-18-000014", "10-K", "2018-02-23")])  # fmt: skip
    concept(engine, GE, "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", [
        ("2016-01-01", "2016-12-31", 9_030 * M, "0000040545-17-000010", "10-K", "2017-02-24"),
        ("2016-01-01", "2016-12-31", 7_036 * M, "0000040545-18-000014", "10-K", "2018-02-23"),
        ("2017-01-01", "2017-12-31", -8_791 * M, "0000040545-18-000014", "10-K", "2018-02-23")])  # fmt: skip
    concept_file(engine, GE, "ge_ge_ContractAsset_20261013.json")
    concept_file(engine, GE, "ge_us-gaap_UnbilledContractsReceivable_20261013.json")


def test_ge_contract_assets_alias_to_standard_switch_is_definition_changed(dbs):
    engine, _ = dbs
    ge_facts(engine)
    g = quality.contract_asset_gap(quality.Facts(engine, GE))
    r16, r17 = g.readings
    assert (r16.label, r16.line.tag, r16.state) == ("FY2016", "ge:ContractAsset", "scored")
    assert r16.line.value == 25_162 * M and r16.prior.value == 21_156 * M
    assert r16.line_growth == pytest.approx(0.189, abs=0.001)  # spec "+18.8%": see build notes
    assert r16.gap_pp == pytest.approx(13.6, abs=0.1)
    assert (r17.prior.tag, r17.line.tag) == (
        "ge:ContractAsset",
        "us-gaap:UnbilledContractsReceivable",
    )
    assert r17.line_growth == pytest.approx(0.147, abs=0.001) and r17.state == "definition_changed"
    assert g.state == "none" and "definition changed" in g.why


def test_commodity_contract_asset_tag_never_mapped_for_others(dbs):
    engine, _ = dbs
    synth(engine, ZZZ, [("2024-12-31", {"Revenues": 100}), ("2025-12-31", {"Revenues": 110})])
    concept(engine, ZZZ, "CommodityContractAssetNoncurrent", [
        (None, "2024-12-31", 10 * M, "0000099999-25-900001", "10-K", "2025-02-15"),
        (None, "2025-12-31", 30 * M, "0000099999-26-900001", "10-K", "2026-02-15")])  # fmt: skip
    g = quality.contract_asset_gap(quality.Facts(engine, ZZZ))
    assert g.state == "missing" and not g.readings


def test_contract_asset_and_deferred_revenue_watch_after_two_readings(dbs):
    engine, _ = dbs
    synth(engine, ZZZ, [
        ("2023-12-31", {"Revenues": 1000, "ContractWithCustomerAssetNetCurrent": 100, "ContractWithCustomerLiabilityCurrent": 300}),
        ("2024-12-31", {"Revenues": 1100, "ContractWithCustomerAssetNetCurrent": 125, "ContractWithCustomerLiabilityCurrent": 280}),
        ("2025-12-31", {"Revenues": 1200, "ContractWithCustomerAssetNetCurrent": 160, "ContractWithCustomerLiabilityCurrent": 250})])  # fmt: skip
    fx = quality.Facts(engine, ZZZ)
    g = quality.contract_asset_gap(fx)
    assert g.state == "watch" and [round(r.gap_pp, 1) for r in g.readings] == [15.0, 18.9]
    d = quality.deferred_rev_gap(fx)
    assert d.state == "watch"


# --- Estimate changes (D-M04-17, -18) ----------------------------------------------------------


def ge_text(dbs):
    engine, corpus = dbs
    ge_facts(engine)
    doc(
        corpus,
        GE,
        "0000040545-17-000010",
        (M04 / "ge_10k_fy2016_estimate_excerpt.txt").read_text(encoding="utf-8"),
    )
    doc(
        corpus,
        GE,
        "0000040545-18-000014",
        (M04 / "ge_10k_fy2017_estimate_excerpt.txt").read_text(encoding="utf-8"),
    )
    return estimates.scan(engine, corpus, GE)


def test_ge_2016_estimate_share_24_4_watch_and_restated_amount_kept_by_version(dbs):
    found = ge_text(dbs)
    f16 = next(f for f in found if f.accession == "0000040545-17-000010")
    assert (f16.amount, f16.basis, f16.fiscal_label) == (2_200 * M, "pre_tax", "FY2016")
    assert f16.denominator == 9_030 * M and f16.share == pytest.approx(0.2436, abs=0.0005)
    assert f16.band == "watch" and "pretax income" in f16.denominator_what
    # the real FY2017 10-K (re-run 1): "such adjustments increased earnings by $2.1 billion,
    # $2.2 billion and $1.4 billion … 2017, 2016 and 2015, respectively" → one row per year;
    # "$2,131 million" for 2017 is the same amount as "$2.1 billion" (one row); the cash-flow
    # variance sentence stays out
    f17 = sorted(
        (f.fiscal_label, round(f.amount / M), f.band) for f in found
         if f.accession == "0000040545-18-000014"
    )  # fmt: skip
    assert f17 == [("FY2015", 1400, "missing"), ("FY2016", 2200, "elevated"),
                   ("FY2017", 2100, "not_meaningful")]  # fmt: skip
    r16 = next(
        f for f in found if f.accession == "0000040545-18-000014" and f.fiscal_label == "FY2016"
    )
    # D-M04-18: FY2016 pretax as known on 2018-02-23 (fixture 7,036; the brief's 9,030 is the
    # FY2016 10-K's own figure): 2,200 ÷ 7,036 = 31.3%
    assert r16.denominator == 7_036 * M and r16.share == pytest.approx(2_200 / 7_036)
    assert all("$3,699" not in f.quote and "Cash used" not in f.quote for f in found)
    engine, _ = dbs
    engine.execute("BEGIN")
    estimates.store(engine, found, GE, "2026-10-13T12:00:00+00:00", False)
    engine.execute("COMMIT")
    assert len(estimates.stored(engine, GE)) == 4  # both filing versions kept, keys unique


def test_ge_change_in_estimated_profitability_amount_is_the_change():
    sent = (
        "Contract assets increased $3,699 million in 2017, which was primarily driven by a "
        "change in estimated profitability of $2,131 million within our long-term product "
        "service agreements within Power ($1,300 million)."
    )
    assert estimates.qualifies(sent, "")[0]
    best = estimates.pick(estimates.candidates(sent, M))
    assert (best.amount, best.basis, best.year) == (2_131 * M, "pre_tax", "2017")
    cash = (
        "Cash used for contract assets of $3.9 billion in 2016 compared with $1.9 billion in "
        "2015, primarily due to cumulative catch up adjustments driven by lower forecasted cost "
        "to complete the contracts."
    )
    assert not estimates.qualifies(cash, "")[0]  # a cash-flow variance


def test_hypothetical_general_clause_before_such_adjustments_counts_only_with_estimate():
    ok = (
        "Revisions may affect a product services agreement’s total estimated profitability "
        "resulting in an adjustment of earnings; such adjustments decreased earnings by $0.5 "
        "billion in 2017."
    )
    assert estimates.qualifies(ok, "")[0]
    (c,) = estimates.candidates(ok, M)
    assert c.amount == -500 * M and c.basis == "pre_tax"
    assert not estimates.qualifies(
        "Prices may change; such adjustments increased earnings by $0.5 billion.", ""
    )[0]  # no estimate named before the ";"
    assert not estimates.qualifies(
        "We changed our estimated useful lives; this change could reduce net income by $1 billion.",
        "",
    )[0]  # the hypothetical is in the amount's own clause


def test_schedule_rows_are_not_estimate_changes():
    # Intel re-run 1: future-amortization rows after a useful-life sentence
    for row in ("Future amortization expenses\t$ 998\t$ 858\t$ 655\t$ 431\t$ 252\t$ 493\t$ 3,687",
                "Future amortization expenses $ 1,360 $ 948 $ 742 $ 552 $ 339 $ 643 $ 4,584",
                "Amortization expense\t$ 1,360\t$ 948\t$ 742",
                "Debt maturities\t$ 500\t$ 700"):  # fmt: skip
        assert estimates.is_schedule_row(row, estimates.is_table_row(row)), row
    ba = "Decrease/increase to Earnings/(loss) from operations\t($1,377)\t($6,562)\t($2,943)"
    assert not estimates.is_schedule_row(ba, True)
    ge = ("Revisions to total estimated profitability increased earnings by $2.1 billion, "
          "$2.2 billion and $1.4 billion in 2017, 2016 and 2015, respectively.")  # fmt: skip
    assert not estimates.is_schedule_row(ge, estimates.is_table_row(ge))


def test_intel_like_report_drops_future_amortization_rows(dbs):
    engine, corpus = dbs
    acc = "0000099999-25-900003"
    filing(engine, ZZZ, acc, "10-K", "2025-01-31", "2024-12-31")
    concept(engine, ZZZ, "OperatingIncomeLoss", [("2024-01-01", "2024-12-31", 5_000 * M, acc, "10-K", "2025-01-31")])  # fmt: skip
    doc(corpus, ZZZ, acc,
        "FORM 10-K (In millions)\n\nIdentified intangible assets are amortized over their "
        "estimated useful lives. As of December 31, 2024, we expected future amortization "
        "expense as follows:\n\nFuture amortization expenses\t$ 998\t$ 858\t$ 655\t$ 431\t$ 252"
        "\t$ 493\t$ 3,687\n\nThe effect of this change in estimate was an increase in operating "
        "income of $300 million.\n")  # fmt: skip
    found = estimates.scan(engine, corpus, ZZZ)
    assert [(f.fiscal_label, round(f.amount / M)) for f in found] == [("FY2024", 300)]


def goog_amzn(dbs):
    engine, corpus = dbs
    g10k, a10k = "0001652044-24-000022", "0001018724-26-900004"
    filing(engine, GOOG, g10k, "10-K", "2024-01-31", "2023-12-31")
    concept(
        engine,
        GOOG,
        "NetIncomeLoss",
        [("2023-01-01", "2023-12-31", 73_795 * M, g10k, "10-K", "2024-01-31")],
    )
    concept(
        engine,
        GOOG,
        "Revenues",
        [("2023-01-01", "2023-12-31", 307_394 * M, g10k, "10-K", "2024-01-31")],
    )
    doc(
        corpus,
        GOOG,
        g10k,
        "ALPHABET INC. FORM 10-K (in millions)\n\nIn January 2023, we completed an assessment of the useful lives of our servers and network equipment and adjusted the estimated useful life of our servers from four years to six years. The effect of this change in estimate for the fiscal year ended December 31, 2023 was a reduction in depreciation expense of $3.9 billion and an increase in net income of $3.0 billion, or $0.24 per basic and $0.24 per diluted share.\n",
    )
    filing(engine, AMZN, a10k, "10-K", "2026-02-06", "2025-12-31")
    concept(
        engine,
        AMZN,
        "NetIncomeLoss",
        [("2025-01-01", "2025-12-31", 77_670 * M, a10k, "10-K", "2026-02-06")],
    )
    concept(
        engine,
        AMZN,
        "Revenues",
        [("2025-01-01", "2025-12-31", 716_900 * M, a10k, "10-K", "2026-02-06")],
    )
    doc(
        corpus,
        AMZN,
        a10k,
        "AMAZON.COM, INC. FORM 10-K (in millions)\n\nEffective January 1, 2025, we changed our estimate of the useful lives of a subset of our servers and networking equipment from six years to five years. The effect of this change for the year ended December 31, 2025 was an increase in depreciation and amortization expense of $1.4 billion and a reduction in net income of $1.0 billion.\n\nIf our estimates of useful lives change in the future, depreciation could increase by $2.0 billion.\n",
    )


def test_alphabet_useful_lives_note_and_amazon_income_decreasing_kept(dbs):
    engine, corpus = dbs
    goog_amzn(dbs)
    (g,) = estimates.scan(engine, corpus, GOOG)
    assert (g.amount, g.basis, g.kind, g.fiscal_label) == (
        3_000 * M,
        "after_tax",
        "useful_life",
        "FY2023",
    )
    assert g.share == pytest.approx(3_000 / 73_795) and g.band == "note"  # ≈ 4.1%
    assert "$3.9 billion (expense)" in g.others[0]
    (a,) = estimates.scan(engine, corpus, AMZN)  # the hypothetical "could" sentence is skipped
    assert a.amount == -1_000 * M and a.band == "note" and a.share == pytest.approx(-1_000 / 77_670)


def test_recurrence_needs_three_disclosures_in_one_direction(dbs):
    engine, corpus = dbs
    for i, y in enumerate((2023, 2024, 2025)):
        acc = f"0000099999-{str(y + 1)[2:]}-90000{i}"
        filing(engine, ZZZ, acc, "10-K", f"{y + 1}-02-15", f"{y}-12-31")
        concept(
            engine,
            ZZZ,
            "NetIncomeLoss",
            [(f"{y}-01-01", f"{y}-12-31", 1000 * M, acc, "10-K", f"{y + 1}-02-15")],
        )
        doc(
            corpus,
            ZZZ,
            acc,
            f"FORM 10-K (in millions)\n\nChanges in estimates on long-term contracts increased operating income by $150 million in {y}.\n",
        )
    concept(engine, ZZZ, "OperatingIncomeLoss", [(f"{y}-01-01", f"{y}-12-31", 1200 * M, f"0000099999-{str(y + 1)[2:]}-90000{i}", "10-K", f"{y + 1}-02-15")
                                                 for i, y in enumerate((2023, 2024, 2025))])  # fmt: skip
    found = estimates.scan(engine, corpus, ZZZ)
    assert len(found) == 3 and all(f.band == "watch" and f.basis == "pre_tax" for f in found)
    assert {round(f.share, 3) for f in found} == {0.125}
    assert estimates.recurrence(found) == "income-increasing"
    assert estimates.recurrence(found[:2]) == ""


def test_lockheed_catch_up_shown_against_own_history(dbs):
    engine, _ = dbs
    concept_file(
        engine,
        LMT,
        "lmt_us-gaap_ContractWithCustomerPerformanceObligationSatisfiedInPreviousPeriod_20261013.json",
    )
    cu = estimates.catch_up(engine, LMT)
    assert [v / 1e9 for _, v, _ in cu.years] == [2.2, 2.0, 2.2, 2.0, 1.6, 1.2]
    assert cu.flag == "same sign 3 years"


# --- Recurring "one-time" charges (D-M04-19) -----------------------------------------------


def test_special_items_three_of_four_years_warn_with_wording_and_quoted_non_gaap(dbs):
    engine, corpus = dbs
    vals = [("2022-12-31", {"RestructuringCharges": 300}), ("2023-12-31", {"AssetImpairmentCharges": 200}),
            ("2024-12-31", {}), ("2025-12-31", {"RestructuringCharges": 100})]  # fmt: skip
    synth(
        engine, ZZZ, [(e, {"Revenues": 10_000, "OperatingIncomeLoss": 1000, **v}) for e, v in vals]
    )
    acc = "0000099999-25-900002"  # the FY2024 10-K (no tag that year, wording only)
    filing(engine, ZZZ, acc, "10-K", "2025-02-15", "2024-12-31")
    doc(
        corpus,
        ZZZ,
        acc,
        "FORM 10-K (in millions)\n\nResults include a one-time charge for the settlement of a customer dispute. We expect no further charges.\n",
    )
    rel = "0000099999-26-900010"
    doc(
        corpus,
        ZZZ,
        rel,
        "Q4 RELEASE\n\nGAAP net income was $900 million and non-GAAP net income was $1,150 million, excluding restructuring and impairment charges.\n",
        doc_type="EX-99.1",
        name="ex991.htm",
    )
    sp = special.compute(engine, corpus, ZZZ)
    # D-M04-94: FY2024's wording states no amount → context, not counted
    assert [y.has for y in sp.years] == [True, True, False, True] and sp.count == 3
    assert sp.state == "warn" and sp.ratio == pytest.approx(600 / 4000)
    fy24 = next(y for y in sp.years if y.label == "FY2024")
    assert fy24.text_state == "read" and fy24.text[0][0] == "one-time" and fy24.text[0][3] is None
    assert fy24.source == "wording only (context, not counted)"
    assert "non-GAAP net income was $1,150 million" in sp.non_gaap
    engine.execute("BEGIN")
    assert special.store(engine, ZZZ, sp, "t") == 4
    engine.execute("COMMIT")


def special_case(dbs, op, tags, text=None):
    """Four fiscal years 2022–2025 with operating income `op` ($M each) and tags per year;
    `text` = the FY2024 10-K sentence."""
    engine, corpus = dbs
    vals = [(f"{y}-12-31", {"Revenues": 10_000, "OperatingIncomeLoss": op, **t})
            for y, t in zip((2022, 2023, 2024, 2025), tags, strict=True)]  # fmt: skip
    synth(engine, ZZZ, vals)
    if text:
        acc = "0000099999-25-900002"
        filing(engine, ZZZ, acc, "10-K", "2025-02-15", "2024-12-31")
        doc(corpus, ZZZ, acc, f"FORM 10-K (in millions)\n\n{text}\n")
    return special.compute(engine, corpus, ZZZ)


def test_special_items_stated_amount_counts_and_another_year_does_not(dbs):
    r = {"RestructuringCharges": 300}
    sp = special_case(dbs, 1000, [r, r, {}, {}],
                      "Results include a one-time charge of $150 million for a customer settlement.")  # fmt: skip
    fy24 = sp.years[2]
    assert fy24.has and fy24.text[0][3] == 150 * M and "150M" in fy24.source
    assert sp.count == 3 and sp.ratio == pytest.approx(750 / 4000) and sp.state == "warn"
    assert special.stated_amount("A one-time charge of $40 million in 2022.", "2024", M) is None
    assert special.stated_amount("A one-time charge of $40 million in 2024.", "2024", M) == 40 * M
    assert special.stated_amount("A one-time benefit of $0.12 per share.", "2024", M) is None


def test_special_items_wording_only_years_never_warn(dbs):
    # AAPL / META / GFS at 0.0% on the live check: wording in 3 years, no tags, no amounts
    engine, corpus = dbs
    synth(engine, ZZZ, [(f"{y}-12-31", {"Revenues": 10_000, "OperatingIncomeLoss": 1000})
                        for y in (2022, 2023, 2024, 2025)])  # fmt: skip
    for i, y in enumerate((2022, 2023, 2024)):
        acc = f"0000099999-{y + 1 - 2000}-90000{i}"
        filing(engine, ZZZ, acc, "10-K", f"{y + 1}-02-15", f"{y}-12-31")
        doc(corpus, ZZZ, acc, "FORM 10-K (in millions)\n\nWe exclude non-recurring items.\n")
    sp = special.compute(engine, corpus, ZZZ)
    assert sp.count == 0 and sp.state == "none" and sp.ratio == 0.0
    assert sum(1 for y in sp.years if y.text) == 3


def test_special_items_small_charges_every_year_stay_none(dbs):
    sp = special_case(dbs, 10_000, [{"RestructuringCharges": 100}] * 4)  # 1% of op income
    assert sp.count == 4 and sp.ratio == pytest.approx(0.01) and sp.state == "none"


def test_special_items_operating_loss_needs_three_tagged_years(dbs):
    t = {"AssetImpairmentCharges": 50}
    sp = special_case(dbs, -100, [t, t, t, {}])
    assert sp.state == "warn" and sp.ratio is None
    assert sp.ratio_why == "operating income ≤ 0: size not measured" and sp.tagged_years == 3


def test_special_items_operating_loss_with_a_stated_year_is_not_meaningful(dbs):
    t = {"AssetImpairmentCharges": 50}
    sp = special_case(dbs, -100, [t, t, {}, {}], "A non-recurring charge of $20 million.")
    assert sp.count == 3 and sp.tagged_years == 2 and sp.state == "not_meaningful"


def test_special_items_short_history_and_operating_loss_not_meaningful(dbs):
    engine, corpus = dbs
    synth(engine, ZZZ, [(f"{y}-12-31", {"Revenues": 1000, "OperatingIncomeLoss": -50, "RestructuringCharges": 10})
                        for y in (2024, 2025)])  # fmt: skip
    sp = special.compute(engine, corpus, ZZZ)
    assert sp.state == "short_history" and sp.ratio is None and "≤ 0" in sp.ratio_why


# --- Pass, signals and review items ------------------------------------------------------------


def watch(engine):
    for t in ("NVDA", "MRVL", "MSTR"):
        load(engine, t)
    return {
        "NVDA": CASES["NVDA"]["cik"],
        "MRVL": CASES["MRVL"]["cik"],
        "MSTR": CASES["MSTR"]["cik"],
    }


def sig(engine, cik, name, tf="MY"):
    return engine.execute("SELECT * FROM signal WHERE cik = ? AND signal = ? AND timeframe = ? "
                          "ORDER BY as_of DESC LIMIT 1", (cik, name, tf)).fetchone()  # fmt: skip


def test_quality_pass_writes_signals_and_queues_nvda_fy2026_only(dbs):
    engine, corpus = dbs
    comps = watch(engine)
    qp = quality_step.quality_pass(engine, corpus, comps, NOW)
    nv = comps["NVDA"]
    m = sig(engine, nv, "mscore")
    assert float(m["value"]) == pytest.approx(-1.17, abs=0.005) and m["value_text"] == "review"
    assert "info (weight 0)" in m["method"] and m["as_of"] == "2026-02-25"
    assert sig(engine, nv, "mscore_sgi1")["value_text"] == "above_cut"
    f = sig(engine, nv, "misstate_f")
    assert (
        f["value"] is None
        and f["value_text"] is None
        and f["method"].startswith("missing: incomplete")
    )
    e = sig(engine, nv, "eq_cash")
    assert float(e["value"]) == pytest.approx(0.855, abs=0.001) and e["value_text"] == "ok"
    assert "info" not in sig(engine, nv, "eq_cash", "MY")["method"].split("; inputs")[0]
    assert "info (weight 0)" in sig(engine, nv, "eq_cash", "ST")["method"]
    assert sig(engine, nv, "estimate_share")["method"].startswith(
        "missing: latest annual report text not stored"
    )
    assert sig(engine, comps["MSTR"], "mscore")["value_text"] == "not_meaningful"
    assert sig(engine, comps["MSTR"], "eq_cash")["value_text"] == "not_meaningful"
    items = engine.execute(
        "SELECT kind, reason, payload FROM review_queue WHERE module_id = 'M04'"
    ).fetchall()
    assert [r["kind"] for r in items] == ["m04_mscore"]
    p = json.loads(items[0]["payload"])
    assert p["fiscal_label"] == "FY2026" and p["m_sgi1"] == pytest.approx(-1.754, abs=0.001)
    assert "−1.75" in items[0]["reason"]
    assert "m04_mscore queued" in quality_step.local_lines(qp)[0]
    # no signal stores a zero for a missing input
    assert (
        engine.execute(
            "SELECT count(*) FROM signal WHERE module_id = 'M04' AND value = 0"
        ).fetchone()[0]
        == 0
    )


def test_first_scan_baseline_and_withdrawal_when_finding_goes(dbs):
    engine, corpus = dbs
    comps = watch(engine)
    later = datetime(2027, 6, 1, tzinfo=UTC)  # NVDA's FY2026 10-K is older than 12 months
    quality_step.quality_pass(engine, corpus, comps, later)
    row = engine.execute(
        "SELECT status, baseline FROM m04_proposal WHERE kind = 'm04_mscore'"
    ).fetchone()
    assert tuple(row) == ("baseline", 1)
    assert engine.execute("SELECT count(*) FROM review_queue").fetchone()[0] == 0


def test_mscore_item_withdrawn_when_no_longer_above_cut(dbs):
    engine, corpus = dbs
    comps = watch(engine)
    quality_step.quality_pass(engine, corpus, comps, NOW)
    # a restated FY2026 operating cash flow filed earlier would change the first-reported
    # value; here the first-reported row itself is corrected in the fixture DB
    engine.execute("UPDATE fact SET value = ? WHERE cik = ? AND tag = "
                   "'NetCashProvidedByUsedInOperatingActivities' AND period_end = '2026-01-25'",
                   (118_000 * M, comps["NVDA"]))  # fmt: skip
    quality_step.quality_pass(engine, corpus, comps, NOW)
    it = engine.execute(
        "SELECT resolution, resolved_by FROM review_queue WHERE kind = 'm04_mscore'"
    ).fetchone()
    assert tuple(it) == ("withdrawn", "engine")


def test_estimate_item_queued_answered_and_kept(dbs):
    from engine import review

    engine, corpus = dbs
    for i, y in enumerate((2023, 2024, 2025)):
        acc = f"0000099999-{str(y + 1)[2:]}-90000{i}"
        filing(engine, ZZZ, acc, "10-K", f"{y + 1}-02-15", f"{y}-12-31")
        concept(
            engine,
            ZZZ,
            "NetIncomeLoss",
            [(f"{y}-01-01", f"{y}-12-31", 1000 * M, acc, "10-K", f"{y + 1}-02-15")],
        )
        concept(
            engine,
            ZZZ,
            "Revenues",
            [(f"{y}-01-01", f"{y}-12-31", 9000 * M, acc, "10-K", f"{y + 1}-02-15")],
        )
    doc(
        corpus,
        ZZZ,
        "0000099999-26-900002",
        "FORM 10-K (in millions)\n\nThe change in the estimated useful lives of our equipment increased net income by $200 million in 2025.\n",
    )
    comps = {"ZZZ": ZZZ}
    quality_step.quality_pass(engine, corpus, comps, NOW)
    it = engine.execute(
        "SELECT item_id, payload FROM review_queue WHERE kind = 'm04_estimate'"
    ).fetchone()
    p = json.loads(it["payload"])
    assert p["band"] == "watch" and p["share"] == pytest.approx(0.20)
    s = sig(engine, ZZZ, "estimate_share")
    assert float(s["value"]) == pytest.approx(20.0) and s["value_text"] == "watch"
    review.m04_action(engine, it["item_id"], "concern", "leans on lives", "owner", NOW)
    row = engine.execute(
        "SELECT owner_outcome, item_id FROM estimate_change WHERE cik = ?", (ZZZ,)
    ).fetchone()
    assert row["owner_outcome"] == "concern"
    quality_step.quality_pass(engine, corpus, comps, NOW)  # answered: not re-queued, kept
    assert (
        engine.execute("SELECT count(*) FROM review_queue WHERE kind = 'm04_estimate'").fetchone()[
            0
        ]
        == 1
    )
    assert (
        engine.execute(
            "SELECT owner_outcome FROM estimate_change WHERE cik = ?", (ZZZ,)
        ).fetchone()[0]
        == "concern"
    )


def test_mscore_action_and_unknown_action(dbs):
    from engine import review

    engine, corpus = dbs
    quality_step.quality_pass(engine, corpus, watch(engine), NOW)
    item = engine.execute("SELECT item_id FROM review_queue WHERE kind = 'm04_mscore'").fetchone()[
        0
    ]
    with pytest.raises(review.ReviewError):
        review.m04_action(engine, item, "concern", "", "owner", NOW)
    review.m04_action(engine, item, "explained", "AQI: equity stakes", "owner", NOW)
    r = engine.execute("SELECT resolution FROM review_queue WHERE item_id = ?", (item,)).fetchone()[
        0
    ]
    assert r.startswith("explained")


def test_excluded_tag_writes_missing_rows_and_stage_confirmation_routes(dbs):
    engine, corpus = dbs
    infq = "0002007825"
    synth(engine, infq, [("2025-12-31", {"Revenues": 30, "NetIncomeLoss": -50})], "0002007825")
    quality_step.quality_pass(engine, corpus, {"INFQ": infq}, NOW)
    r = sig(engine, infq, "eq_cash")
    assert r["method"].startswith("missing: not applicable (spac_shell)")
    synth(engine, ZZZ, three_years())
    stage.confirm(engine, ZZZ, "2025-12-31", "mature", "owner", NOW)
    quality_step.quality_pass(engine, corpus, {"ZZZ": ZZZ}, NOW)
    s = sig(engine, ZZZ, "eq_cash")
    assert s["value_text"] == "warn" and "stage mature (confirmed)" in s["method"]


def test_non_reliance_mark_on_rows(dbs):
    engine, corpus = dbs
    comps = watch(engine)
    engine.execute(
        "INSERT INTO m04_event (cik, accession, item, form, filed, class, state, base_state, review, "
        "clears_when, note, first_seen_at, computed_at) VALUES (?, '0001045810-26-900099', '4.02', "
        "'8-K', '2026-05-01', 'non_reliance', 'warn', 'warn', 1, 'restated filing', 'x', 't', 't')",
        (comps["NVDA"],))  # fmt: skip
    quality_step.quality_pass(engine, corpus, comps, NOW)
    assert "inputs under non-reliance" in sig(engine, comps["NVDA"], "mscore")["method"]


# --- Run script, refresh hook, tab, review page, migrations ------------------------------------


def run_financials_module():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_financials

    return run_financials


def test_quality_run_no_sec_summary(dbs):
    rf = run_financials_module()
    engine, corpus = dbs
    comps = watch(engine)
    ge_text(dbs)
    concept_file(
        engine,
        LMT,
        "lmt_us-gaap_ContractWithCustomerPerformanceObligationSatisfiedInPreviousPeriod_20261013.json",
    )
    out: list[str] = []
    rf.quality_run(engine, corpus, comps, NOW, lambda *a: out.extend(a))
    text = "\n".join(out)
    for want in ("SEC skipped (--no-sec)", "=== Summary (what the owner looks for) ===",
                 "NVDA FY2026: expected M −1.17 / SGI = 1 −1.75 → m04_mscore; got M -1.17 / -1.75 (review)",
                 "Queued items (1 expected: NVDA FY2026 m04_mscore): m04_mscore queued 1",
                 "FY2016 watch +24.4%", "definition_changed", "Lockheed catch-up revenue (expected 2.2B 2019 … 1.2B 2024): FY2019 2.2B",
                 "MSTR FY2025: digital-asset fair-value change", "M not meaningful: model tag asset_treasury",
                 "special_items", "FY2025: M -0.96 / SGI = 1 -1.9", "growth_driven; F 3.11 (above_2.45)"):  # fmt: skip
        assert want in text, want


def test_quality_run_with_a_fake_client_requests_only_reference_files(dbs, make_client):
    rf = run_financials_module()
    from engine.sec.xbrl_facts import CONCEPT_URL

    engine, corpus = dbs
    routes = {CONCEPT_URL.format(cik=c, taxonomy="us-gaap", tag=t): [ok(b"", 404)]
              for c, t in ((GE, "Revenues"), (GE, rf.GE_TAGS[6]), (GE, rf.GE_CONTRACT_TAG), (LMT, rf.LMT_TAG))}  # fmt: skip
    t = FakeTransport(routes)
    out: list[str] = []
    rf.quality_run(engine, corpus, {}, NOW, lambda *a: out.extend(a), make_client(t))
    text = "\n".join(out)
    assert "GE FY2016 10-K: no stored fact names it" in text and "Lockheed us-gaap" in text
    assert len(t.calls) == 4 and all("companyconcept" in u for u, _, _ in t.calls)


def test_quality_subcommand_is_built_and_listed():
    rf = run_financials_module()
    assert "quality" in rf.BUILT


def test_refresh_local_step_line(dbs):
    engine, corpus = dbs
    lines = quality_step.run_local_part(engine, corpus, watch(engine), NOW)
    assert lines[0].startswith("M04 earnings quality — local pass (Part 6, 0 SEC requests)")


def test_migrations_chain_has_gate_and_quality_tables(dbs):
    from engine.store.db import migrations

    engine, _ = dbs
    names = [n for _, n, _ in migrations("engine")]
    assert names[35:37] == ["m04_gate", "m04_quality"]
    for t in ("estimate_change", "special_item"):
        assert engine.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (t,)).fetchone()


def test_financials_tab_and_review_page_show_part6(tmp_path):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui.app import create_app
    from engine.ui.settings import UiSettings

    data = tmp_path / "data"
    engine = open_db("engine", data)
    corpus = open_db("corpus", data)
    cik = load(engine, "NVDA")
    engine.execute(
        "INSERT INTO entity (cik, name, source_ref, fetched_at) VALUES (?, 'NVIDIA CORP', 't', 'n')",
        (cik,),
    )
    engine.execute(
        "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES ('NVDA', ?, '2020-01-01', 't')",
        (cik,),
    )
    ge_text((engine, corpus))
    quality_step.quality_pass(engine, corpus, {"NVDA": cik}, datetime.now(UTC))
    item = engine.execute("SELECT item_id FROM review_queue WHERE kind = 'm04_mscore'").fetchone()
    engine.close()
    corpus.close()
    watchfile = tmp_path / "watchlist.toml"
    watchfile.write_text('[watchlist]\ntickers = ["NVDA"]\n', encoding="utf-8")
    with TestClient(create_app(UiSettings(data_dir=data, watchlist=watchfile))) as c:
        html = c.get("/c/NVDA?tab=financials").text
        page = c.get(f"/review/{item[0]}").text if item else ""
        guide = c.get("/review").text
    for want in ("Earnings-quality scores", "Contract assets and deferred revenue", "Estimate changes",
                 "Recurring “one-time” charges", "Non-operating swings", "m04_mscore (SGI = 1 above −1.78)",
                 "“growth-driven” note", "GE (reference)", "definition changed", "mscore_sgi1", "DSO"):  # fmt: skip
        assert want in html, want
    assert "object at 0x" not in html
    assert "Earnings quality: cash conversion" not in html  # no longer "still to come"
    assert item and "Look closer" in page and "AQI" in page
    assert "M04 earnings quality: M-score and estimate changes" in guide


def test_queue_kinds_registered():
    assert queue.GROUP["m04_mscore"] == queue.GROUP["m04_estimate"] == 7
    assert queue.ACTIONS["m04_estimate"] == ("explained", "concern")
    assert "m04_mscore" in queue.KIND_LABELS


# --- Live check 1 (2026-10-13, logs/financials_quality_20261013-104553.txt) -------------------

INSTANT |= {"RestrictedCashCurrent", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "Goodwill", "MarketableSecuritiesNoncurrent", "DeferredRevenueCurrent"}  # fmt: skip
YYY = "0000088888"
BA_TEXT = (
    "THE BOEING COMPANY FORM 10-K (Dollars in millions)\n\n"
    "Changes in estimates on long-term contracts are discussed below. BGS earnings from operations "
    "in 2025 increased by $9,856 million compared with 2024, primarily due to a 2025 gain on the "
    "Digital Aviation Solutions Divestiture of $9,566 million.\n\n"
    "Net cumulative catch-up adjustments for changes in estimated revenues and costs at completion "
    "across all long-term contracts decreased Earnings from operations by $1,377 million, $6,562 "
    "million and $2,943 million in 2025, 2024 and 2023, respectively.\n\n"
    "Years ended December 31\t2025\t2024\t2023\n\n"
    "Decrease/increase to Earnings/(loss) from operations\t($1,377)\t($6,562)\t($2,943)\n\n"
    "Decrease/increase to Diluted earnings/(loss) per share\t($1.53)\t($9.83)\t($5.43)\n\n"
    "The year over year improvement in earnings is primarily due to lower net unfavorable "
    "cumulative contract catch-up adjustments of $5,196 million compared to 2024.\n\n"
    "We changed the estimated useful lives of our servers. Research and development expenses in "
    "2025 increased $13.50 billion, or 31%, compared to 2024. Operating expenses increased $4.0 "
    "billion or 7% driven by Gaming. Accumulated amortization of leasehold improvements and "
    "finance leases was $519 million and $410 million as of December 31, 2025 and 2024, "
    "respectively.\n\n"
    "The impact of the change in estimated useful lives of certain buildings resulted in an "
    "increase to income before income taxes of $76 million for the year ended December 31, 2025.\n\n"
    "As noted, the impact of the change in estimated useful lives of certain buildings resulted in "
    "an increase to income before income taxes of $76 million for the year ended December 31, 2025.\n"
)


def ba_like(dbs, cik=ZZZ, acc="0000099999-26-004357"):
    engine, corpus = dbs
    filing(engine, cik, acc, "10-K", "2026-01-30", "2025-12-31")
    concept(engine, cik, "Revenues", [("2025-01-01", "2025-12-31", 89_000 * M, acc, "10-K", "2026-01-30")])  # fmt: skip
    concept(engine, cik, "OperatingIncomeLoss", [("2025-01-01", "2025-12-31", 4_281 * M, acc, "10-K", "2026-01-30")])  # fmt: skip
    doc(corpus, cik, acc, BA_TEXT)
    return acc


def test_estimate_finder_drops_variance_sentences_and_dedupes_table_rows(dbs):
    engine, corpus = dbs
    ba_like(dbs)
    found = estimates.scan(engine, corpus, ZZZ)
    got = sorted((f.fiscal_label, round(f.amount / M), f.basis) for f in found)
    # −1,377 once (prose and table row, FY2025, negative); the 76M sentence once; no BGS
    # +9,856, no catch-up variance 5,196, no R&D 13.5B, no opex 4.0B, no amortization 519,
    # no per-share row; the "…, respectively" list gives one row per year (re-run 1)
    assert got == [("FY2023", -2943, "pre_tax"), ("FY2024", -6562, "pre_tax"),
                   ("FY2025", -1377, "pre_tax"), ("FY2025", 76, "pre_tax")]  # fmt: skip
    f = next(f for f in found if f.amount < 0 and f.fiscal_label == "FY2025")
    assert f.share == pytest.approx(-1377 / 4281) and f.band == "elevated"
    assert f.kind == "catch_up" and "Net cumulative catch-up" in f.quote


def test_table_row_counts_with_sign_and_per_share_rows_are_skipped():
    row = "Decrease/increase to Earnings/(loss) from operations\t($1,377)\t($6,562)\t($2,943)"
    assert estimates.is_table_row(row)
    c = estimates.table_candidate(row, 1e6, "FY2025")
    assert (c.amount, c.basis, c.year) == (-1_377 * M, "pre_tax", "2025")
    eps = "Decrease/increase to Diluted earnings/(loss) per share\t($1.53)\t($9.83)\t($5.43)"
    assert estimates.table_candidate(eps, 1e6, "FY2025") is None


def test_estimate_wording_in_the_sentence_before_needs_this_change():
    ok, _ = estimates.qualifies(
        "The effect was a reduction in depreciation expense of $3.9 billion.",
        "We changed the estimated useful lives of our servers.",
    )
    assert not ok  # no reference to the change
    ok, ctx = estimates.qualifies(
        "These changes increased operating income by $135 million.",
        "We changed the estimated useful lives of our servers.",
    )
    assert ok and "useful lives" in ctx
    assert not estimates.qualifies("Operating expenses increased $4.0 billion or 7%.", "")[0]


def test_withdrawn_waiting_proposals_and_linked_rows_stay_as_history(dbs):
    # re-run 1: "m04_proposal -3, estimate_change -19" — a waiting (overflow) proposal left
    # no trace when withdrawn; a row linked to a review item was deleted with it
    engine, corpus = dbs
    acc = ba_like(dbs)
    gone = BA_TEXT.index("BGS earnings")
    engine.execute("BEGIN")
    for i in range(queue.WEEKLY_CAP):  # fill this week's cap so the next one waits
        queue.propose(engine, "m04_estimate", f"x{i}", "filler", {}, NOW, cik=YYY)
    assert queue.propose(engine, "m04_estimate", f"{ZZZ}:{acc}:{gone}", "old BGS", {"q": 1},
                         NOW, cik=ZZZ, filed="2026-01-30") == "overflow"  # fmt: skip
    engine.execute(
        "INSERT INTO estimate_change (cik, accession, start_offset, doc_ref, kind, amount, basis, "
        "band, quote, item_id, first_seen_at, computed_at) VALUES (?, ?, ?, 'd', 'other', 1, "
        "'pre_tax', 'elevated', 'old BGS', 999, '2026-10-01', '2026-10-01')",
        (ZZZ, acc, gone),
    )
    engine.execute("COMMIT")
    cq = quality_step.company_quality(engine, corpus, "ZZZ", ZZZ, NOW)
    assert cq.proposals.get("m04_estimate withdrawn") == 1
    row = engine.execute(
        "SELECT reason, resolution, resolved_by, note, resolved_at FROM review_queue "
        "WHERE cik = ? AND reason = 'old BGS'",
        (ZZZ,),
    ).fetchone()
    assert (row["resolution"], row["resolved_by"]) == ("withdrawn", "engine")
    assert "was overflow" in row["note"] and row["resolved_at"]
    assert not engine.execute(
        "SELECT 1 FROM m04_proposal WHERE prop_key LIKE ?", (f"%:{gone}",)
    ).fetchone()
    rows = estimates.stored(engine, ZZZ)
    assert (acc, gone) in {(r["accession"], r["start_offset"]) for r in rows}  # linked: kept
    assert estimates.superseded(engine, ZZZ, rows) == {(acc, gone)}
    assert (acc, gone) not in {
        (r["accession"], r["start_offset"]) for r in estimates.current(engine, ZZZ, rows)
    }


def test_withdrawn_items_when_the_finding_no_longer_holds(dbs):
    engine, corpus = dbs
    acc = ba_like(dbs)
    text = BA_TEXT
    old = {"bgs": text.index("BGS earnings"), "table": text.index("Decrease/increase to Earnings")}
    engine.execute("BEGIN")
    for k, off in old.items():  # what the first live run queued (key cik:accession:offset)
        queue.propose(engine, "m04_estimate", f"{ZZZ}:{acc}:{off}", f"old {k}", {}, NOW, cik=ZZZ,
                      filed="2026-01-30")  # fmt: skip
    engine.execute("COMMIT")
    n = engine.execute("SELECT count(*) FROM review_queue WHERE kind = 'm04_estimate'").fetchone()[
        0
    ]
    assert n == 2
    cq = quality_step.company_quality(engine, corpus, "ZZZ", ZZZ, NOW)
    assert cq.proposals.get("m04_estimate withdrawn") == 2
    rows = engine.execute("SELECT resolution, resolved_by FROM review_queue WHERE kind = 'm04_estimate' "
                          "AND note LIKE 'recomputed%'").fetchall()  # fmt: skip
    assert [tuple(r) for r in rows] == [("withdrawn", "engine")] * 2
    keys = {r[0] for r in engine.execute("SELECT prop_key FROM m04_proposal WHERE kind = 'm04_estimate'")}  # fmt: skip
    assert keys == {f"m04_estimate:{ZZZ}:{acc}:{text.index('Net cumulative')}"}


GE_RESPECTIVELY = (
    "GENERAL ELECTRIC COMPANY FORM 10-K (In millions)\n\n"
    "LONG-TERM SERVICE AGREEMENTS. Revisions that affect a product services agreement’s total "
    "estimated profitability result in an adjustment of earnings; such adjustments increased "
    "earnings by $2.2 billion, $1.4 billion and $1.6 billion in 2016, 2015 and 2014, "
    "respectively.\n"
)


def test_ge_named_reports_and_respectively_years(dbs):
    engine, corpus = dbs
    ge_facts(engine)
    for y, acc in ((2018, "0000040545-19-000010"), (2019, "0000040545-20-000015"),
                   (2020, "0000040545-21-000011")):  # newer GE 10-Ks stored by Part 3  # fmt: skip
        concept(engine, GE, "NetIncomeLoss", [(f"{y}-01-01", f"{y}-12-31", 1_000 * M, acc, "10-K", f"{y + 1}-02-20")])  # fmt: skip
        doc(corpus, GE, acc, f"GE FORM 10-K {y} (In millions)\n\nNothing about estimates here.\n")
    doc(corpus, GE, "0000040545-17-000010", GE_RESPECTIVELY)
    assert estimates.scan(engine, corpus, GE) == []  # the newest three hold no estimate text
    found = estimates.scan(engine, corpus, GE, accessions=["0000040545-17-000010"])
    assert [(f.fiscal_label, round(f.amount / M)) for f in found] == [
        ("FY2016", 2200), ("FY2015", 1400), ("FY2014", 1600)]  # fmt: skip
    assert len({f.start for f in found}) == 3  # one row per listed year, unique keys
    f = found[0]
    assert f.share == pytest.approx(0.2436, abs=0.0005) and f.band == "watch"


def test_near_misses_list_the_best_candidate_sentences(dbs):
    engine, corpus = dbs
    ge_facts(engine)
    doc(corpus, GE, "0000040545-17-000010",
        "GE FORM 10-K (In millions)\n\nWe estimate that service agreements are profitable. "
        "Earnings rose by $1.0 billion on higher volume as estimated. Profitability on long-term "
        "service agreements improved.\n")  # fmt: skip
    assert estimates.scan(engine, corpus, GE, accessions=["0000040545-17-000010"]) == []
    near = estimates.near_misses(engine, corpus, GE, ["0000040545-17-000010"])
    assert len(near) == 3 and all(len(t) <= 200 for _, _, t in near)
    assert near[0][0] >= near[-1][0]


def test_issue_reads_stock_plans_named_and_zero_only_when_tagged_elsewhere(dbs):
    engine, _ = dbs
    synth(engine, ZZZ, [("2024-12-31", {"Revenues": 100, "ProceedsFromStockPlans": 5}),
                        ("2025-12-31", {"Revenues": 110})])  # fmt: skip
    fx = quality.Facts(engine, ZZZ)
    inp = quality.Inputs()
    assert quality.issue_flag(fx, "2024-12-31", inp) == 1.0
    assert "ProceedsFromStockPlans" in inp.subs[0]
    inp = quality.Inputs()
    assert quality.issue_flag(fx, "2025-12-31", inp) == 0.0 and "other years" in inp.subs[0]
    synth(engine, YYY, [("2025-12-31", {"Revenues": 110})], accn_prefix="0000088888")
    inp = quality.Inputs()
    assert quality.issue_flag(quality.Facts(engine, YYY), "2025-12-31", inp) is None
    assert "unknown" in inp.missing[0]
    # an owner mapping in M02's fin_tag_map (an extension tag as equity issued) counts
    engine.execute("INSERT INTO fin_tag_map (cik, taxonomy, tag, role, mapped_by, mapped_at) VALUES "
                   "(?, 'yyy', 'ProceedsFromEmployeePlans', 'equity_issued', 'owner', 'x')", (YYY,))  # fmt: skip
    concept(engine, YYY, "ProceedsFromEmployeePlans",
            [("2025-01-01", "2025-12-31", 7 * M, "0000088888-26-900000", "10-K", "2026-02-15")],
            taxonomy="yyy")  # fmt: skip
    inp = quality.Inputs()
    assert quality.issue_flag(quality.Facts(engine, YYY), "2025-12-31", inp) == 1.0
    assert "yyy:ProceedsFromEmployeePlans" in inp.subs[0]


def test_sga_marketing_plus_ga_and_ga_only(dbs):
    engine, _ = dbs
    synth(engine, ZZZ, [("2025-12-31", {"Revenues": 100, "MarketingExpense": 20, "GeneralAndAdministrativeExpense": 10})])  # fmt: skip
    v, how = quality.sga(quality.Facts(engine, ZZZ), "2025-12-31")
    assert v.value == 30 * M and how == "SG&A = marketing + G&A"
    synth(engine, YYY, [("2025-12-31", {"Revenues": 100, "GeneralAndAdministrativeExpense": 12})],
          accn_prefix="0000088888")  # fmt: skip
    v, how = quality.sga(quality.Facts(engine, YYY), "2025-12-31")
    assert v.value == 12 * M and "G&A only" in how


def test_ifrs_trade_receivables_cash_fallback_and_noncurrent_securities(dbs):
    engine, _ = dbs
    synth(engine, ZZZ, [("2025-12-31", {"Revenues": 100, "RestrictedCashCurrent": 4,
          "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": 54,
          "MarketableSecuritiesNoncurrent": 70})])  # fmt: skip
    concept(engine, ZZZ, "CurrentTradeReceivables", [(None, "2025-12-31", 9 * M, "0000099999-25-900000", "20-F", "2026-02-15")],
            taxonomy="ifrs-full")  # fmt: skip
    fx = quality.Facts(engine, ZZZ)
    assert fx.at("receivables", "2025-12-31", True).tag == "ifrs-full:CurrentTradeReceivables"
    v, how = quality.cash_at(fx, "2025-12-31")
    assert v.value == 50 * M and "restricted" in how
    assert (
        fx.at("lt_investments", "2025-12-31", True).tag == "us-gaap:MarketableSecuritiesNoncurrent"
    )


def test_cost_of_revenue_from_components_only_when_unambiguous(dbs):
    engine, _ = dbs
    synth(engine, ZZZ, [("2025-12-31", {"Revenues": 1000, "CostOfServices": 300, "CostOfGoodsAndServicesSoldDepreciation": 20,
          "SellingAndMarketingExpense": 100, "GeneralAndAdministrativeExpense": 50,
          "ResearchAndDevelopmentExpense": 80, "OperatingExpenses": 550})])  # fmt: skip
    v, how = quality.cogs(quality.Facts(engine, ZZZ), "2025-12-31")
    assert v.value == 320 * M and "checked against OperatingExpenses" in how
    synth(engine, YYY, [("2025-12-31", {"Revenues": 1000, "CostOfServices": 300, "OperatingExpenses": 900})],
          accn_prefix="0000088888")  # fmt: skip
    v, how = quality.cogs(quality.Facts(engine, YYY), "2025-12-31")
    assert v is None and "ambiguous" in how


def test_readings_must_be_consecutive_to_the_latest_year(dbs):
    engine, _ = dbs
    yrs = []
    for y in range(2016, 2027):
        vals = {"Revenues": 100 + 10 * (y - 2016)}
        dr = {2016: 50, 2017: 100, 2018: 70, 2024: 60, 2025: 2}.get(y)
        if dr:
            vals["DeferredRevenueCurrent"] = dr
        yrs.append((f"{y}-12-31", vals))
    synth(engine, ZZZ, yrs)
    d = quality.deferred_rev_gap(quality.Facts(engine, ZZZ))
    assert [r.label for r in d.readings] == ["FY2017", "FY2018", "FY2025"]
    assert d.state == "short_history" and "FY2026" in d.why


def test_acquisition_year_reading_shown_not_counted(dbs):
    engine, _ = dbs
    synth(engine, ZZZ, [
        ("2023-12-31", {"Revenues": 1000, "ContractWithCustomerAssetNetCurrent": 100, "Goodwill": 500}),
        ("2024-12-31", {"Revenues": 1440, "ContractWithCustomerAssetNetCurrent": 384, "Goodwill": 900,
                        "PaymentsToAcquireBusinessesNetOfCashAcquired": 300}),
        ("2025-12-31", {"Revenues": 1780, "ContractWithCustomerAssetNetCurrent": 1003, "Goodwill": 905})])  # fmt: skip
    g = quality.contract_asset_gap(quality.Facts(engine, ZZZ))
    r24, r25 = g.readings
    assert r24.state == "acquisition_year" and "acquisition year" in r24.note
    assert r25.state == "scored" and g.state == "none" and "acquisition year" in g.why


def test_special_items_rule_is_one_function():
    y = special.YearItems("2025-12-31", "FY2025", text=[("one-time", "q", "a", 5 * M)])
    assert special.qualifies(y) and y.has and y.charge == 5 * M
    ctx = special.YearItems("2025-12-31", "FY2025", text=[("one-time", "q", "a", None)])
    assert not special.qualifies(ctx)  # wording without an amount (D-M04-94)
    assert not special.qualifies(special.YearItems("2025-12-31", "FY2025"))


def test_a_sentence_cut_by_a_line_break_keeps_the_wording_before():
    prev = "The effect of this change in estimate, based on servers included in “Property and equipment,"
    sent = "net” as of December 31, 2023, was a benefit to net income of $2.5 billion."
    assert estimates.qualifies(sent, prev)[0]
    assert not estimates.qualifies(sent, "We changed the estimated useful lives.")[0]
