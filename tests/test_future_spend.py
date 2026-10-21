# ruff: noqa: E501  (fixture rows)
"""M05 Part 1: capex against demand, growth capex × ROIC, bookings cover, deposits, the
channel file, the rule-4 vote and AHEAD_OF_DEMAND in M01 rule 4, the refresh hook, the owner
script and the "Future spend (M05)" section (docs/M05_FUTURE_SPEND.md Part 1; D-M05-9…).

Fixtures: MU's trimmed companyfacts (tests/fixtures/m04, Part 1b) for the brief's worked
example; synthetic companies in tests/fixtures/m05 (README there) for the D32 cases and an
Intel-shaped decliner; RPO, deposits and ROIC inputs entered in the tests."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from engine import m01_rules
from engine.financials import models as models_mod
from engine.financials import trends
from engine.future_spend import channels, demand, step, views
from engine.moneyflow import views as mf_views
from engine.sec.xbrl_facts import ALL_CONCEPTS, rebuild_series, store_facts
from engine.signals import Source, write_signal
from tests.conftest import FIXTURES
from tests.test_financials_1b import AS_OF, MSFT, MU, M, entity, fact, load, mu
from tests.test_technicals import load_script

ROOT = Path(__file__).resolve().parent.parent
M05 = FIXTURES / "m05"
UTIL, LIGHT, DECL, ROIC_CO = "0009000001", "0009000002", "0009000003", "0009000004"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
TODAY = NOW.date()
NO_MODELS = models_mod.ModelFile("none", ())
B = 1_000_000_000


def chf(*entries: tuple[str, str | None, str]) -> channels.ChannelFile:
    return channels.ChannelFile("test", tuple(channels.Channel(c, t, k) for t, k, c in entries))


NONE = chf()


def load_synth(engine, name: str, cik: str, label: str, ticker: str) -> None:
    entity(engine, cik, label, "1231", ticker)
    engine.execute("BEGIN")
    store_facts(engine, cik, json.loads((M05 / name).read_text(encoding="utf-8")))
    engine.execute("COMMIT")


def utility(engine):
    load_synth(
        engine, "utility_synthetic_companyfacts_20261020.json", UTIL, "Synthetic Utility", "UTL"
    )


def light(engine):
    load_synth(
        engine,
        "assetlight_synthetic_companyfacts_20261020.json",
        LIGHT,
        "Synthetic Software",
        "SFT",
    )


def decliner(engine):
    load_synth(
        engine, "decliner_synthetic_companyfacts_20261020.json", DECL, "Synthetic Decliner", "DCL"
    )


def by_label(strip):
    return {d.label: d for d in strip}


def rows(engine, cik, signal, tf="MY"):
    return engine.execute(
        "SELECT * FROM signal WHERE cik = ? AND module_id = 'M05' AND signal = ? AND timeframe = ? "
        "ORDER BY as_of", (cik, signal, tf)).fetchall()  # fmt: skip


# --- concepts (D-SEC-30) -------------------------------------------------------------------------


def test_contract_liability_concepts_total_and_noncurrent_apart_from_current():
    cur = ALL_CONCEPTS["contract_liabilities"]
    assert [t for _, t in cur.tags] == [
        "ContractWithCustomerLiabilityCurrent",
        "DeferredRevenueCurrent",
    ]
    tot = ALL_CONCEPTS["contract_liabilities_total"]
    non = ALL_CONCEPTS["contract_liabilities_noncurrent"]
    assert [t for _, t in tot.tags] == ["ContractWithCustomerLiability", "DeferredRevenue"]
    assert [t for _, t in non.tags] == [
        "ContractWithCustomerLiabilityNoncurrent",
        "DeferredRevenueNoncurrent",
    ]
    assert tot.kind == non.kind == "instant" and tot.mark("us-gaap", "DeferredRevenue").startswith(
        "≈ pre-2018"
    )


# --- capex_demand on the brief's worked example (MU) ----------------------------------------------


def test_mu_strip_matches_the_brief(dbs):
    engine, _ = dbs
    mu(engine)
    s = demand.build_series(engine, MU, AS_OF)
    assert (
        s.rung == "depreciation" and s.years[0].label == "FY2012" and s.years[-1].label == "FY2026"
    )
    got = {k: (round(d.ratio, 2), round(d.median, 2) if d.median else None, d.state)
           for k, d in by_label(demand.strip(s)).items()}  # fmt: skip
    assert got["FY2022"] == (1.72, 1.61, "BUILD_INTO_DEMAND")
    assert got["FY2023"] == (1.0, 1.68, "CUTTING")
    assert got["FY2024"] == (1.09, 1.68, "MAINTENANCE")
    assert got["FY2025"] == (1.92, 1.56, "BUILD_INTO_DEMAND")
    assert got["FY2026"] == (3.26, 1.68, "BUILD_INTO_DEMAND")
    d23 = by_label(demand.strip(s))["FY2023"]
    # capex ÷ revenue 49.4% = 1.30× its 3-yr average: under D-M04-64's 1.5×, no pointer
    assert round(d23.intensity, 3) == 0.494 and round(d23.intensity / d23.intensity_avg, 2) == 1.30
    assert round(d23.capex_yoy, 3) == -0.364 and round(d23.rev_yoy, 3) == -0.495
    assert len(demand.strip(s)) == 8


def test_states_need_eight_prior_years_but_the_m04_64_test_needs_three(dbs):
    engine, _ = dbs
    mu(engine)
    s = demand.build_series(engine, MU, AS_OF)
    first = by_label([demand.classify(s, i) for i in range(len(s.years))])
    assert first["FY2019"].state == "INSUFFICIENT_HISTORY" and "7 of 8" in first["FY2019"].why
    assert first["FY2020"].median is not None  # FY2012–19 = 8 prior years


def test_decliner_reads_ahead_of_demand_at_175x(dbs):
    engine, _ = dbs
    decliner(engine)
    s = demand.build_series(engine, DECL, AS_OF)
    d = demand.classify(s, len(s.years) - 1)
    assert d.label == "FY2023" and d.state == "AHEAD_OF_DEMAND"
    assert round(d.intensity / d.intensity_avg, 2) == 1.75 and "D-M04-64" in d.why
    assert by_label(demand.strip(s))["FY2022"].state == "AHEAD_OF_DEMAND"


def test_utility_capex_above_depreciation_for_a_decade_is_steady_not_a_warning(dbs):
    engine, _ = dbs
    utility(engine)
    s = demand.build_series(engine, UTIL, AS_OF)
    strip = demand.strip(s)
    assert all(d.ratio > 1.7 for d in strip)  # rate-base growth: always above depreciation
    assert "AHEAD_OF_DEMAND" not in {d.state for d in strip}
    last = strip[-1]
    assert (last.label, last.state, round(last.median, 3)) == ("FY2025", "STEADY", 1.835)


def test_asset_light_without_depreciation_is_missing_never_zero(dbs):
    engine, _ = dbs
    light(engine)
    r = step.name_result(engine, "SFT", LIGHT, TODAY, chf=NONE, mf=NO_MODELS)
    o = r.row("capex_demand")
    assert o.missing == "no depreciation or D&A (not split)" and o.value is None and o.text is None
    assert r.row("bookings_cover").missing == "RPO not tagged"
    assert "channel unset" in o.method


def test_short_history_reads_insufficient_history(dbs):
    engine, _ = dbs
    entity(engine, LIGHT, "Short", "1231", "SHT")
    for y, cap, dep, rev in (
        (2022, 80, 50, 900),
        (2023, 90, 55, 1000),
        (2024, 120, 60, 1100),
        (2025, 150, 65, 1300),
    ):
        fact(
            engine,
            LIGHT,
            "PaymentsToAcquirePropertyPlantAndEquipment",
            f"{y}-01-01",
            f"{y}-12-31",
            cap * M,
            filed=f"{y + 1}-02-15",
        )
        fact(
            engine,
            LIGHT,
            "Depreciation",
            f"{y}-01-01",
            f"{y}-12-31",
            dep * M,
            filed=f"{y + 1}-02-15",
        )
        fact(engine, LIGHT, "Revenues", f"{y}-01-01", f"{y}-12-31", rev * M, filed=f"{y + 1}-02-15")
    s = demand.build_series(engine, LIGHT, AS_OF)
    d = demand.classify(s, len(s.years) - 1)
    assert d.state == "INSUFFICIENT_HISTORY" and "3 of 8" in d.why and d.ratio is not None


def test_definition_changed_year_is_not_scored(dbs):
    engine, _ = dbs
    entity(engine, LIGHT, "Switcher", "1231", "SWT")
    for y in range(2012, 2021):
        fact(
            engine,
            LIGHT,
            "PaymentsToAcquireProductiveAssets",
            f"{y}-01-01",
            f"{y}-12-31",
            100 * M,
            filed=f"{y + 1}-02-15",
        )
    fact(
        engine,
        LIGHT,
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "2021-01-01",
        "2021-12-31",
        140 * M,
        filed="2022-02-15",
    )
    for y in range(2012, 2022):
        fact(
            engine,
            LIGHT,
            "Depreciation",
            f"{y}-01-01",
            f"{y}-12-31",
            90 * M,
            filed=f"{y + 1}-02-15",
        )
    s = demand.build_series(engine, LIGHT, AS_OF)
    d = demand.classify(s, len(s.years) - 1)
    assert d.state is None and "definition changed" in d.missing and "D-M04-3" in d.missing


def test_build_needs_revenue_or_a_bookings_line_and_falling_revenue_without_bookings_is_ahead(dbs):
    engine, _ = dbs
    entity(engine, LIGHT, "Expander", "1231", "EXP")
    for i, y in enumerate(range(2015, 2026)):
        cap = 100 if y < 2025 else 140  # 1.4× depreciation, intensity under 1.5× its average
        rev = 1000 + 10 * i if y < 2025 else 990 + 10 * (i - 1)  # 2025: −1%
        fact(
            engine,
            LIGHT,
            "PaymentsToAcquirePropertyPlantAndEquipment",
            f"{y}-01-01",
            f"{y}-12-31",
            cap * M,
            filed=f"{y + 1}-02-15",
        )
        fact(
            engine,
            LIGHT,
            "Depreciation",
            f"{y}-01-01",
            f"{y}-12-31",
            100 * M,
            filed=f"{y + 1}-02-15",
        )
        fact(engine, LIGHT, "Revenues", f"{y}-01-01", f"{y}-12-31", rev * M, filed=f"{y + 1}-02-15")
    s = demand.build_series(engine, LIGHT, AS_OF)
    d = demand.classify(s, len(s.years) - 1)
    assert d.rev_yoy < 0 and d.expanding
    assert d.state == "AHEAD_OF_DEMAND" and "no bookings line rises" in d.why
    # a rising deposit balance is bookings evidence (D-M05-6): build into demand
    fact(
        engine,
        LIGHT,
        "ContractWithCustomerLiability",
        None,
        "2024-12-31",
        50 * M,
        filed="2025-02-15",
    )
    fact(
        engine,
        LIGHT,
        "ContractWithCustomerLiability",
        None,
        "2025-12-31",
        80 * M,
        filed="2026-02-15",
    )
    s = demand.build_series(engine, LIGHT, AS_OF)
    d = demand.classify(s, len(s.years) - 1)
    assert d.state == "BUILD_INTO_DEMAND" and "deposits +60.0%" in d.why


# --- deposits (D-M05-6) ---------------------------------------------------------------------------


def test_deposits_total_else_current_plus_noncurrent_and_a_jump_is_a_mark(dbs):
    engine, _ = dbs
    mu(engine)
    fact(
        engine,
        MU,
        "ContractWithCustomerLiabilityCurrent",
        None,
        "2025-08-28",
        169 * M,
        filed="2025-10-03",
    )
    fact(
        engine,
        MU,
        "ContractWithCustomerLiabilityCurrent",
        None,
        "2026-08-27",
        250 * M,
        filed="2026-10-03",
    )
    fact(
        engine,
        MU,
        "ContractWithCustomerLiabilityNoncurrent",
        None,
        "2026-08-27",
        12_750 * M,
        filed="2026-10-03",
    )
    s = demand.build_series(engine, MU, AS_OF)
    line = demand.deposits_line(s)
    assert line.now.how == "current + noncurrent" and line.now.value == 13_000 * M
    assert line.prior.how == "current only (no noncurrent tag)" and line.yoy is None  # other basis
    assert "repayable, not revenue" in line.text() and "not compared" in line.text()
    fact(
        engine, MU, "ContractWithCustomerLiability", None, "2025-08-28", 169 * M, filed="2025-10-03"
    )
    fact(
        engine,
        MU,
        "ContractWithCustomerLiability",
        None,
        "2026-08-27",
        13_000 * M,
        filed="2026-10-03",
    )
    line = demand.deposits_line(demand.build_series(engine, MU, AS_OF))
    assert line.now.how == "total" and round(line.yoy, 1) == 75.9 and line.jump
    assert "more than doubled" in line.text() and "Part 2" in line.text()


def test_deposits_last_tagged_years_ago_are_stale_not_current(dbs):
    # live check 1: INTC's newest deposit tag was 2021-12-25, shown as the current balance
    engine, _ = dbs
    mu(engine)
    fact(engine, MU, "ContractWithCustomerLiability", None, "2021-09-02", 500 * M,
         filed="2021-10-15")  # fmt: skip
    line = demand.deposits_line(demand.build_series(engine, MU, AS_OF))
    assert line.now is None and line.stale.startswith("missing: last tagged 2021-09-02")
    assert "newest fiscal year" in line.text()


# --- bookings_cover (views.rpo with the cover) -----------------------------------------------------


def msft_rpo(engine, rpo_2025=375 * B, rpo_2026=684 * B):
    entity(engine, MSFT, "Microsoft", "0630", "MSFT")
    fact(engine, MSFT, "Revenues", "2024-07-01", "2025-06-30", 281.72 * B, filed="2025-07-30")
    fact(engine, MSFT, "Revenues", "2025-07-01", "2026-06-30", 331.84 * B, filed="2026-07-29")
    fact(
        engine,
        MSFT,
        "RevenueRemainingPerformanceObligation",
        None,
        "2025-06-30",
        rpo_2025,
        filed="2025-07-30",
    )
    fact(
        engine,
        MSFT,
        "RevenueRemainingPerformanceObligation",
        None,
        "2026-06-30",
        rpo_2026,
        filed="2026-07-29",
    )
    rebuild_series(engine, MSFT)


def test_msft_bookings_cover_rises_133_to_206(dbs):
    engine, _ = dbs
    msft_rpo(engine)
    rp = mf_views.rpo(engine, MSFT)
    assert [round(r.cover, 2) for r in rp.rows] == [1.33, 2.06]
    assert round(rp.cover_change, 2) == 0.55 and rp.cover_state == "RISING"
    r = step.name_result(engine, "MSFT", MSFT, TODAY, chf=NONE, mf=NO_MODELS)
    o = r.row("bookings_cover")
    assert (o.text, o.value, o.as_of) == ("RISING", 2.0612, "2026-07-29")
    assert (
        "own history only" in o.method and "deposits (contract liabilities): not tagged" in o.method
    )
    assert o.info == ("ST",)


def test_bookings_cover_flat_falling_and_short_history(dbs):
    engine, _ = dbs
    msft_rpo(engine, rpo_2026=400 * B)  # 1.33 → 1.21: −9% → FLAT
    assert mf_views.rpo(engine, MSFT).cover_state == "FLAT"
    engine.execute(
        "DELETE FROM fact WHERE tag = 'RevenueRemainingPerformanceObligation' AND period_end = '2026-06-30'"
    )
    fact(
        engine,
        MSFT,
        "RevenueRemainingPerformanceObligation",
        None,
        "2026-06-30",
        300 * B,
        filed="2026-07-29",
    )
    rebuild_series(engine, MSFT)
    assert mf_views.rpo(engine, MSFT).cover_state == "FALLING"
    engine.execute(
        "DELETE FROM fact WHERE tag = 'RevenueRemainingPerformanceObligation' AND period_end = '2025-06-30'"
    )
    rebuild_series(engine, MSFT)
    rp = mf_views.rpo(engine, MSFT)
    assert rp.cover_state == "short_history" and rp.cover_change is None


# --- growth_capex_roic (rule 3) and the ROIC series (D-M04-107) -----------------------------------


def roic_company(engine, oi_2025: float, *, growth: float = 50, equity_2025: float = 1100):
    """IC = equity − cash = 1,000 every year (2025: equity_2025 − 100); tax 0 → ROIC = OI ÷ IC."""
    entity(engine, ROIC_CO, "Roic Co", "1231", "ROI")
    for y in range(2021, 2026):
        end, start, filed = f"{y}-12-31", f"{y}-01-01", f"{y + 1}-02-15"
        oi = {2022: 100, 2025: oi_2025}.get(y, 90)
        fact(engine, ROIC_CO, "OperatingIncomeLoss", start, end, oi * M, filed=filed)
        fact(
            engine,
            ROIC_CO,
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            start,
            end,
            oi * M,
            filed=filed,
        )
        fact(engine, ROIC_CO, "IncomeTaxExpenseBenefit", start, end, 0, filed=filed)
        fact(
            engine,
            ROIC_CO,
            "StockholdersEquity",
            None,
            end,
            (equity_2025 if y == 2025 else 1100) * M,
            filed=filed,
        )
        fact(
            engine,
            ROIC_CO,
            "CashAndCashEquivalentsAtCarryingValue",
            None,
            end,
            100 * M,
            filed=filed,
        )
        fact(engine, ROIC_CO, "Revenues", start, end, 2000 * M, filed=filed)
    engine.execute(
        "INSERT INTO capex_split (cik, period_end, fiscal_label, total, total_tag, total_accession, "
        "total_filed, definition_changed, maintenance, growth, method, rung, rung_value, marks, "
        "computed_at) VALUES (?, '2025-12-31', 'FY2025', ?, 'us-gaap:PaymentsToAcquirePropertyPlantAndEquipment', "
        "'0009000004-26-000001', '2026-02-15', 0, ?, ?, 'depreciation, capped at total capex', "
        "'depreciation', ?, NULL, 'now')",
        (ROIC_CO, 100 * M, (100 - growth) * M, growth * M, (100 - growth) * M),
    )


def test_roic_series_helper_reads_n_years_with_the_year_before_as_opening(dbs):
    engine, _ = dbs
    roic_company(engine, 150)
    s = trends.roic_series(engine, ROIC_CO, AS_OF, years=4)
    assert [y.label for y in s] == ["FY2022", "FY2023", "FY2024", "FY2025"]
    assert [round(y.cell.value, 3) for y in s] == [0.1, 0.09, 0.09, 0.15]
    full = trends.roic_series(engine, ROIC_CO, AS_OF, years=10)
    assert full[0].label == "FY2021" and full[0].cell.text == "missing: no opening invested capital"


@pytest.mark.parametrize(("oi", "growth", "equity", "state", "mark"), [
    (150, 50, 1100, "ACCRETIVE", ""),
    (60, 50, 1100, "DILUTING", ""),
    (80, 50, 1100, "ACCRETIVE", "mark: flat"),
    (150, 10, 1100, "MAINTENANCE_ONLY", ""),
    (150, 50, -2000, "not_meaningful", "average invested capital ≤ 0"),
    # owner, live check 1 (amends D-M05-5): a negative ROIC is never ACCRETIVE (RIVN)
    (-150, 50, 1100, "NEGATIVE_ROIC", "worsening, not yet earning a return"),
])  # fmt: skip
def test_growth_capex_roic_states(dbs, oi, growth, equity, state, mark):
    engine, _ = dbs
    roic_company(engine, oi, growth=growth, equity_2025=equity)
    g = demand.growth_roic(engine, ROIC_CO, AS_OF)
    assert g.state == state and mark in g.why and "growth share" in g.why


def test_growth_capex_roic_missing_without_a_split_row(dbs):
    engine, _ = dbs
    mu(engine)
    g = demand.growth_roic(engine, MU, AS_OF)
    assert g.state is None and g.missing == "no capex_split row (M04 local pass not run)"


# --- the vote (rule 4, D-M05-7) --------------------------------------------------------------------


def test_vote_positive_only_when_all_three_hold():
    assert demand.vote("BUILD_INTO_DEMAND", 1.4, "x", "NO_SLOWDOWN", None).positive
    assert "CvD unresolved" in demand.vote("BUILD_INTO_DEMAND", 1.4, "x", None, "no row").text
    assert (
        "STRUCTURAL_DECLINE"
        in demand.vote("BUILD_INTO_DEMAND", 1.4, "x", "STRUCTURAL_DECLINE", None).text
    )
    assert "0.80 < 1" in demand.vote("BUILD_INTO_DEMAND", 0.8, "x", "NO_SLOWDOWN", None).text
    assert "not BUILD_INTO_DEMAND" in demand.vote("STEADY", 1.4, "x", "NO_SLOWDOWN", None).text
    assert "missing" in demand.vote("BUILD_INTO_DEMAND", None, "no OCF", "NO_SLOWDOWN", None).text


def test_mu_vote_reads_cvd_and_ocf(dbs):
    engine, _ = dbs
    mu(engine)
    r = step.name_result(engine, "MU", MU, TODAY, chf=NONE, mf=NO_MODELS)
    assert not r.vote.positive and "CvD unresolved" in r.vote.text
    src = [Source("0000000000-26-000001", "2026-10-03")]
    write_signal(engine, cik=MU, module_id="M04", signal="cvd_state", as_of="2026-10-03",
                 value_text="CYCLICAL_TROUGH", method="cvd", sources=src)  # fmt: skip
    r = step.name_result(engine, "MU", MU, TODAY, chf=NONE, mf=NO_MODELS)
    assert r.vote.positive and "OCF ÷ capex 2.92" in r.vote.text
    assert "vote: positive" in r.row("capex_demand").method
    # live check 1 (NVDA, AAPL voted): capex is information for fabless / outsourced (R9)
    r = step.name_result(engine, "MU", MU, TODAY, chf=chf(("MU", None, "fabless")), mf=NO_MODELS)
    assert not r.vote.positive and "capex is information for fabless" in r.vote.text
    assert "would read: positive" in r.vote.text


# --- channels (D-M05-1) ----------------------------------------------------------------------------


def test_channel_file_rules_and_the_repo_file(tmp_path):
    f = channels.load(ROOT / "config" / "m05_channels.toml")
    assert f.for_company("0001045810", "NVDA").channel == "fabless"
    assert f.for_company(None, "MRVL").commitments_lead
    assert f.for_company("0001050446", "MSTR").not_applicable
    assert f.for_company(None, "ORCL").channel == channels.UNSET
    bad = tmp_path / "c.toml"
    bad.write_text('[[company]]\nticker = "X"\nchannel = "foundry"\n', encoding="utf-8")
    with pytest.raises(channels.ChannelFileError, match="unknown channel"):
        channels.load(bad)
    assert "unknown channel" in channels.load_safe(bad).error
    assert channels.load_safe(bad).for_company(None, "X").channel == channels.UNSET
    keyed = chf(("NEW", "0000000001", "fabless"), ("NEW", None, "hyperscaler"))
    assert keyed.for_company("0000000001", "NEW").channel == "fabless"  # the CIK wins


def test_fabless_reads_capex_rows_as_info_and_na_is_missing(dbs):
    engine, _ = dbs
    mu(engine)
    r = step.name_result(engine, "MU", MU, TODAY, chf=chf(("MU", None, "fabless")), mf=NO_MODELS)
    assert r.row("capex_demand").info == step.ALL and r.row("growth_capex_roic").info == step.ALL
    assert r.row("bookings_cover").info == ("ST",)
    r = step.name_result(engine, "MU", MU, TODAY, chf=chf(("MU", None, "n/a")), mf=NO_MODELS)
    assert r.not_applicable == "not applicable (channel n/a)"
    assert {o.missing for o in r.rows} == {"not applicable (channel n/a)"}


def test_m04_tag_makes_m05_not_applicable(dbs):
    engine, _ = dbs
    mu(engine)
    mf = models_mod.parse(
        {"company": [{"ticker": "MU", "tag": "fund", "reason": "r", "source": "s"}]}
    )
    r = step.name_result(engine, "MU", MU, TODAY, chf=NONE, mf=mf)
    assert r.not_applicable == "not applicable (fund)"


# --- the pass, rule 4 and the refresh hook -----------------------------------------------------------


def test_pass_writes_three_rows_per_timeframe_and_reruns_in_place(dbs):
    engine, _ = dbs
    mu(engine)
    decliner(engine)
    comps = {"MU": MU, "DCL": DECL}
    fp = step.future_spend_pass(
        engine, comps, NOW, chf=chf(("MU", None, "fab_owner")), mf=NO_MODELS
    )
    assert not fp.errors and fp.written == 18
    my = rows(engine, MU, "capex_demand")
    assert [(r["value_text"], r["value"], r["as_of"]) for r in my] == [
        ("BUILD_INTO_DEMAND", 3.2603, "2026-10-11")
    ]
    assert "info (weight 0)" not in my[0]["method"]
    assert "info (weight 0)" in rows(engine, MU, "capex_demand", "ST")[0]["method"]
    n = engine.execute("SELECT count(*) FROM signal WHERE module_id = 'M05'").fetchone()[0]
    step.future_spend_pass(engine, comps, NOW, chf=NONE, mf=NO_MODELS)
    assert engine.execute("SELECT count(*) FROM signal WHERE module_id = 'M05'").fetchone()[0] == n
    lines = step.summary_lines(fp)
    assert "AHEAD_OF_DEMAND (M01 rule-4 exit warning, D-M01-7): DCL" in lines[2]


def test_ahead_of_demand_is_a_rule4_reason_that_never_blocks(dbs):
    engine, _ = dbs
    decliner(engine)
    step.future_spend_pass(engine, {"DCL": DECL}, NOW, chf=NONE, mf=NO_MODELS)
    src = [Source("0000000000-26-000001", "2026-08-01")]
    for sig, txt in (
        ("survival_gate", "pass"),
        ("filing_status", "current"),
        ("cvd_state", "NO_SLOWDOWN"),
    ):
        write_signal(engine, cik=DECL, module_id="M04", signal=sig, as_of="2026-08-01",
                     value_text=txt, method="m", sources=src)  # fmt: skip
    m = m01_rules.read_m04(engine, DECL)
    assert m.capex_demand.text == "AHEAD_OF_DEMAND"
    reasons = m01_rules.rule4(m)
    assert reasons == [
        "capex AHEAD_OF_DEMAND 2024-02-15 (M05; warning only, never blocking; D-M01-7)"
    ]
    assert m01_rules.rule3(m).state == "allowed" and m01_rules.rule1(m).state == "qualified"


def test_run_local_part_never_fails(dbs, monkeypatch):
    engine, _ = dbs

    def boom(*a, **k):
        raise RuntimeError("bad")

    monkeypatch.setattr(step, "future_spend_pass", boom)
    out = step.run_local_part(engine, {}, NOW, clock=lambda: 0.0)
    assert out == [
        "M05 future spend — local pass (Part 1, 0 requests) (0.0 s):",
        "  M05: error — RuntimeError: bad",
    ]


def test_refresh_runs_m05_after_the_m04_local_steps_and_before_m07():
    src = (ROOT / "scripts" / "run_refresh.py").read_text(encoding="utf-8")
    i = src.index("prices += future_spend_local_step(engine, report)")
    assert src.index("prices += financials_cvd_local_step(engine, report)") < i
    assert i < src.index("prices += ownership_local_step(engine, report)")


# --- owner script --------------------------------------------------------------------------------


class Args:
    def __init__(self, **kw):
        self.no_sec, self.tickers, self.companies, self.out_dir = True, None, None, None
        self.__dict__.update(kw)


def test_script_list_and_unbuilt_subcommand(capsys):
    rm = load_script("run_m05")
    assert rm._main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "demand" in out and "commitments" in out and "(not built)" in out
    assert rm._main(["commitments"]) == 2  # Part 2: not built, nothing touched


def test_script_demand_on_an_injected_db(dbs, tmp_path, capsys):
    engine, _ = dbs
    mu(engine)
    rm = load_script("run_m05")
    log = rm.Log(tmp_path / "logs" / "m.txt")
    assert rm.run_demand(Args(companies={"MU": MU}), log, tmp_path, engine=engine, now=NOW) == 0
    log.close()
    text = (tmp_path / "logs" / "m.txt").read_text(encoding="utf-8")
    assert "MU [fab_owner]: capex_demand BUILD_INTO_DEMAND 3.26 (median 1.68, FY2026)" in text
    assert "FY2023: capex ÷ rung 1.00, median 1.68" in text and "→ CUTTING" in text
    assert "=== Summary" in text and "SEC requests: 0" in text and "signal +9" in text


def test_script_export_writes_companyfacts_layout(dbs, tmp_path):
    engine, _ = dbs
    mu(engine)
    rm = load_script("run_m05")
    log = rm.Log(tmp_path / "logs" / "e.txt")
    assert (
        rm.run_export(Args(tickers="MU", out_dir=tmp_path), log, tmp_path, engine=engine, now=NOW)
        == 0
    )
    log.close()
    data = json.loads((tmp_path / "m05_export_mu_20261012.json").read_text(encoding="utf-8"))
    dep = data["facts"]["us-gaap"]["Depreciation"]["units"]["USD"]
    assert data["cik"] == 723125 and any(
        r["end"] == "2026-08-27" and r["val"] == 9_420 * M for r in dep
    )
    assert "GrossProfit" not in data["facts"]["us-gaap"]


# --- the Future spend section (D-UI-37) --------------------------------------------------------------


def test_view_and_money_tab_render_the_section(tmp_path, monkeypatch):
    from tests.test_technicals_tab import _app

    def fill(engine, corpus):
        load(engine, MU, "mu_companyfacts_trimmed_20261012.json", "0831", None, "Micron Technology")
        fact(
            engine,
            MU,
            "ContractWithCustomerLiability",
            None,
            "2025-08-28",
            169 * M,
            filed="2025-10-03",
        )
        fact(
            engine,
            MU,
            "ContractWithCustomerLiability",
            None,
            "2026-08-27",
            13_000 * M,
            filed="2026-10-03",
        )

    monkeypatch.setattr(views.channels_mod, "load_safe", lambda *a: chf(("MU", None, "fab_owner")))
    client = _app(tmp_path, monkeypatch, fill, {"MU": MU})
    html = client.get("/c/MU?tab=money").text
    assert "Future spend (M05)" in html and "channel fab_owner" in html
    assert "BUILD_INTO_DEMAND" in html and "3.26×" in html and "CUTTING" in html
    assert "repayable, not revenue" in html and "$13.00B" in html
    assert "vote: neutral — CvD unresolved" in html
    assert "object at 0x" not in html and "<built-in method" not in html


def test_view_not_applicable(dbs):
    engine, _ = dbs
    mu(engine)
    v = views.company_view(
        engine, MU, "MU", date(2026, 10, 12), chf=chf(("MU", None, "n/a")), mf=NO_MODELS
    )
    assert v.not_applicable == "not applicable (channel n/a)" and v.rows[0].state == "missing"
