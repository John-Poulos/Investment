# ruff: noqa: E501  (fixture rows)
"""M04 Part 4a: survival gate (numbers), distress score, debt / FCF / negative-equity rows,
credit lines, review items, the refresh pass, the `gate` script and the gate panel
(docs/M04_BUILD_LOG.md Part 4a).

Fixtures: tests/fixtures/m04/nvta_us-gaap_*_20261013.json (Invitae FY2021) and
rivn_us-gaap_*_20261013.json (Rivian Q2 2026), hand-built from the M04 design pack's
worked examples (README "Part 4a"); the other cases are entered here."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine.financials import debt, distress, gate, gate_step, gate_view, models, queue
from engine.sec.xbrl_facts import store_concept
from tests.conftest import FIXTURES, FakeTransport, ok

M04 = FIXTURES / "m04"
M = 1_000_000
NVTA, RIVN, BA, INTC, AMZN = "0001501134", "0001874178", "0000012927", "0000050863", "0001018724"
MSTR, INFQ, GFS, ETV = "0001050446", "0002007825", "0001709048", "0001270523"
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
TODAY = "2026-10-13"
MF = models.parse({"company": [
    {"ticker": "MSTR", "cik": MSTR, "tag": "asset_treasury", "reason": "bitcoin treasury", "source": "D-M04-8"},
    {"ticker": "ETV", "tag": "fund", "reason": "closed-end fund", "source": "D-M04-8"},
    {"ticker": "INFQ", "cik": INFQ, "tag": "spac_shell", "before": "2026-02-13", "reason": "shell years", "source": "D-M04-8"},
]})  # fmt: skip


def entity(engine, cik, name, sic, fye="1231", ticker=None):
    engine.execute(
        "INSERT OR REPLACE INTO entity (cik, name, sic, fiscal_year_end, source_ref, fetched_at) "
        "VALUES (?, ?, ?, ?, 't', 'n')",
        (cik, name, sic, fye),
    )
    if ticker:
        engine.execute(
            "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES (?, ?, '2000-01-01', 't')",
            (ticker, cik),
        )


def concepts(engine, prefix, cik):
    engine.execute("BEGIN")
    for f in sorted(M04.glob(f"{prefix}_us-gaap_*_20261013.json")):
        store_concept(engine, cik, json.loads(f.read_text(encoding="utf-8")))
    engine.execute("COMMIT")


def fact(
    engine, cik, tag, start, end, value_m, filed, form="10-Q", tax="us-gaap", acc=None, unit="USD"
):
    engine.execute(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession, "
        "form, filed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
        (cik, tax, tag, unit, start, end, value_m * M if unit == "USD" else value_m,
         acc or f"{cik}-{filed[2:4]}-9{filed[5:7]}{filed[8:10]}0", form, filed),
    )  # fmt: skip


def quarter(engine, cik, start, end, filed, ocf, capex=None, form="10-Q", tax="us-gaap",
            ocf_tag="NetCashProvidedByUsedInOperatingActivities",
            capex_tag="PaymentsToAcquirePropertyPlantAndEquipment"):  # fmt: skip
    fact(engine, cik, ocf_tag, start, end, ocf, filed, form, tax)
    if capex is not None:
        fact(engine, cik, capex_tag, start, end, capex, filed, form, tax)


def inst(engine, cik, end, filed, form="10-Q", tax="us-gaap", **tags):
    for tag, v in tags.items():
        fact(engine, cik, tag, None, end, v, filed, form, tax)


def price(engine, cik, symbol, day, close):
    engine.execute(
        "INSERT OR REPLACE INTO price_fetch (symbol, cik, bars) VALUES (?, ?, 1)", (symbol, cik)
    )
    engine.execute(
        "INSERT INTO price_bar (symbol, date, close, source, fetched_at) VALUES (?, ?, ?, 'tiingo', 'n')",
        (symbol, day, close),
    )


def cover(engine, cik, end, filed, shares):
    fact(engine, cik, "EntityCommonStockSharesOutstanding", None, end, shares, filed, "10-Q",
         "dei", unit="shares")  # fmt: skip


def rivian(engine):
    entity(engine, RIVN, "Rivian Automotive, Inc. / DE", "3711", ticker="RIVN")
    concepts(engine, "rivn", RIVN)


def invitae(engine):
    entity(engine, NVTA, "INVITAE CORP", "8071")
    concepts(engine, "nvta", NVTA)


def boeing(engine):
    entity(engine, BA, "BOEING CO", "3721", ticker="BA")
    # FY2019 (10-K 2020-01-31): last two quarters FCF −2,700 and −2,856 → 2,778 a quarter
    # 10-Q cash flows are year-to-date (Q4 = fiscal year − nine months)
    for e, f, ocf, cx in (
        ("2019-03-31", "2019-04-24", 2788, 400),
        ("2019-06-30", "2019-07-24", 2198, 1128),
        ("2019-09-30", "2019-10-23", -202, 1428),
    ):
        quarter(engine, BA, "2019-01-01", e, f, ocf, cx)
    quarter(engine, BA, "2019-01-01", "2019-12-31", "2020-01-31", -2652, 1834, form="10-K")
    inst(
        engine,
        BA,
        "2019-12-31",
        "2020-01-31",
        "10-K",
        CashAndCashEquivalentsAtCarryingValue=9485,
        ShortTermInvestments=545,
        DebtCurrent=7340,
        CommercialPaper=6109,
    )
    # Q2 2022 (10-Q 2022-07-27): Q1 FCF −3,416, Q2 −332 → 1,874
    quarter(engine, BA, "2022-01-01", "2022-03-31", "2022-04-27", -3216, 200)
    quarter(engine, BA, "2022-04-01", "2022-06-30", "2022-07-27", 81, 413)
    inst(
        engine,
        BA,
        "2022-06-30",
        "2022-07-27",
        CashAndCashEquivalentsAtCarryingValue=11448,
        DebtCurrent=5406,
    )
    # Q2 2024 (10-Q 2024-07-31): FCF −3,900 and −4,356 → 4,128
    quarter(engine, BA, "2024-01-01", "2024-03-31", "2024-04-24", -3360, 540)
    quarter(engine, BA, "2024-04-01", "2024-06-30", "2024-07-31", -3920, 436)
    inst(
        engine,
        BA,
        "2024-06-30",
        "2024-07-31",
        CashAndCashEquivalentsAtCarryingValue=12621,
        DebtCurrent=4765,
    )


def lines(bs, *spec):
    return tuple(gate.Credit(None, f, a * M, m, bs, "A", "PROBE_RESULTS S11", False, "")
                 for f, a, m in spec)  # fmt: skip


# --- The runway and the wall (D-M04-32, -33) -------------------------------------------------


def test_boeing_fy2019_fail_with_credit_and_cp_not_double_counted(dbs):
    engine, _ = dbs
    boeing(engine)
    cash = gate.evaluate(engine, BA, "BA", "2020-01-31", models=MF, calendar=False)
    assert cash.balance_date == "2019-12-31" and cash.liquidity == 10_030 * M
    assert cash.tier == "cash_burner" and cash.burn == pytest.approx(2_778 * M)
    assert round(cash.runway, 1) == 3.6 and cash.state == "fail"
    extra = lines(
        "2019-12-31",
        ("364-day", 3200, "2020-10-30"),
        ("three-year", 3200, "2022-10-30"),
        ("five-year", 3200, "2024-10-30"),
    )
    g = gate.evaluate(engine, BA, "BA", "2020-01-31", models=MF, calendar=False, extra_credit=extra)
    assert [c.counted for c in g.credits] == [False, True, True]  # 364-day ends inside 12 months
    assert g.liquidity == 16_430 * M and round(g.runway, 1) == 5.9 and g.state == "fail"
    assert g.debt12 == 7_340 * M  # DebtCurrent holds the commercial paper: never 13,449
    assert "commercial paper 6,109M inside, not added twice" in g.debt12_text
    # 12-month debt 7,340 < liquidity: no wall fail; + 4 × burn (18,452) > 16,430 only warns
    assert g.wall_test[0] == "warn"
    assert any("runway 5.9 q < 6" in t for t in g.triggers)


def test_boeing_q2_2024_fail_and_q2_2022_pass_with_credit(dbs):
    engine, _ = dbs
    boeing(engine)
    extra = lines(
        "2024-06-30",
        ("five-year", 4000, "2029-05-15"),
        ("364-day", 3000, "2025-08-25"),
        ("three-year", 3000, "2028-08-25"),
    )
    g = gate.evaluate(engine, BA, "BA", "2024-07-31", models=MF, calendar=False, extra_credit=extra)
    assert round(g.runway, 1) == 5.5 and g.state == "fail" and g.wall_test[0] == "pass"
    assert sum(c.amount for c in g.credits if c.beyond_24m) == 7_000 * M
    assert g.basis_note.startswith("short history")
    cash = gate.evaluate(engine, BA, "BA", "2022-07-27", models=MF, calendar=False)
    assert round(cash.runway, 1) == 6.1 and cash.state == "warn"
    assert cash.wall_test[0] == "warn"  # 5,406 + 4 × 1,874 > 11,448
    extra = lines(
        "2022-06-30", ("three-year", 3200, "2023-10-30"), ("five-year", 3200, "2025-10-30")
    )
    g = gate.evaluate(engine, BA, "BA", "2022-07-27", models=MF, calendar=False, extra_credit=extra)
    assert round(g.runway, 1) == 9.5 and g.state == "pass" and g.wall_test[0] == "pass"


def test_rivian_cash_only_fail_then_warn_with_the_confirmed_abl(dbs):
    engine, _ = dbs
    rivian(engine)
    g = gate.evaluate(engine, RIVN, "RIVN", TODAY, models=MF, calendar=False)
    assert g.liquidity == 5_310 * M and g.tier == "cash_burner"
    assert round(g.runway_by_basis["last two quarters"], 1) == 5.5
    assert round(g.runway_by_basis["TTM ÷ 4"], 1) == 6.1
    assert round(g.runway, 1) == 5.5 and g.state == "fail" and g.burn_basis == "last two quarters"
    assert "credit: none confirmed (cash-only)" in g.method()
    lid = gate_view.add_credit_line(
        engine,
        RIVN,
        "ABL",
        "536",
        "2029-06-30",
        "2026-06-30",
        "Q2 2026 10-Q liquidity note",
        "owner",
        NOW,
    )
    g = gate.evaluate(engine, RIVN, "RIVN", TODAY, models=MF, calendar=False)
    assert round(g.runway, 1) == 6.1 and g.state == "warn" and round(g.runway_cash, 1) == 5.5
    row = engine.execute("SELECT * FROM credit_line WHERE line_id = ?", (lid,)).fetchone()
    assert (row["status"], row["origin"], row["confirmed_by"], row["grade"]) == (
        "confirmed",
        "owner",
        "owner",
        "B",
    )
    assert any(s.grade == "B" for s in g.sources)  # an owner entry without a filing source
    # a line stated for an older balance sheet must be confirmed again (pack S4.2)
    assert gate_view.withdraw_credit_line(engine, RIVN, lid, "owner", NOW)
    gate_view.add_credit_line(
        engine,
        RIVN,
        "ABL",
        "536",
        "2029-06-30",
        "2026-03-31",
        "https://www.sec.gov/Archives/edgar/data/1874178/x.htm",
        "owner",
        NOW,
    )
    g = gate.evaluate(engine, RIVN, "RIVN", TODAY, models=MF, calendar=False)
    assert round(g.runway, 1) == 5.5 and "confirm again" in g.credits[0].why


def test_credit_line_entry_rules(dbs):
    engine, _ = dbs
    for args, msg in ((("", "5", "2030-01-01", "2026-06-30", "x"), "facility"),
                      (("ABL", "-1", "2030-01-01", "2026-06-30", "x"), "above 0"),
                      (("ABL", "5", "2026-01-01", "2026-06-30", "x"), "after the as-of"),
                      (("ABL", "5", "2030-01-01", "2026-06-30", ""), "source")):  # fmt: skip
        with pytest.raises(gate_view.CreditLineError, match=msg):
            gate_view.add_credit_line(engine, RIVN, *args, "owner", NOW)
    lid = gate_view.add_credit_line(
        engine,
        RIVN,
        "revolver",
        "1,000",
        "2031-01-01",
        "2026-06-30",
        "0001874178-26-900031 note 9",
        "owner",
        NOW,
    )
    assert engine.execute("SELECT grade, accession, amount FROM credit_line WHERE line_id = ?",
                          (lid,)).fetchone()[:] == ("A", "0001874178-26-900031", 1e9)  # fmt: skip


def test_invitae_fy2021_fails_715_days_before_its_103(dbs):
    engine, _ = dbs
    invitae(engine)
    g = gate.evaluate(engine, NVTA, "Invitae", "2022-03-01", models=MF, calendar=False)
    assert g.liquidity == pytest.approx(1_045.4 * M) and g.restricted == pytest.approx(10.2 * M)
    assert round(g.runway_by_basis["last two quarters"], 1) == 5.6
    assert round(g.runway_by_basis["TTM ÷ 4"], 1) == 6.8
    assert g.state == "fail" and g.tier == "cash_burner"
    s = distress.score(engine, NVTA, "Invitae", "2022-03-01", models=MF)
    assert s.variant == "Z''" and round(s.value, 2) == 1.31 and s.zone == "grey" and not s.warning
    assert s.o_p is not None and s.o_p < distress.O_CUTOFF  # index 2020 = 577


def test_intel_fy2024_capex_funded_warn_and_runway_review(dbs):
    engine, _ = dbs
    entity(engine, INTC, "INTEL CORP", "3674", ticker="INTC")
    for e, f, ocf, cx in (
        ("2024-03-30", "2024-04-26", -1227, 5970),
        ("2024-06-29", "2024-08-02", 1054, 11670),
        ("2024-09-28", "2024-11-01", 5130, 17770),
    ):
        quarter(engine, INTC, "2024-01-01", e, f, ocf, cx)  # year-to-date, as filed
    quarter(engine, INTC, "2024-01-01", "2024-12-28", "2025-01-31", 8288, 23944, form="10-K")
    inst(
        engine,
        INTC,
        "2024-12-28",
        "2025-01-31",
        "10-K",
        CashAndCashEquivalentsAtCarryingValue=8249,
        ShortTermInvestments=13813,
        DebtCurrent=3729,
    )
    g = gate.evaluate(engine, INTC, "INTC", "2025-01-31", models=MF, calendar=False)
    assert g.tier == "capex_funded" and round(g.runway, 1) == 5.6 and g.burn_basis == "TTM ÷ 4"
    assert g.state == "warn" and g.runway_review and not g.triggers
    cg = gate_step.CompanyGate("INTC", INTC, g)
    engine.execute("BEGIN")
    gate_step.propose_items(engine, cg, NOW)
    engine.execute("COMMIT")
    assert cg.queued == {"m04_runway": "queued"}
    item = engine.execute("SELECT * FROM review_queue WHERE kind = 'm04_runway'").fetchone()
    assert "5.6 q" in item["reason"] and json.loads(item["payload"])["tier"] == "capex-funded"


def test_amzn_capex_funded_pass_on_the_broader_tag_and_fcf_burn(dbs):
    engine, _ = dbs
    entity(engine, AMZN, "AMAZON COM INC", "5961", ticker="AMZN")
    quarter(
        engine,
        AMZN,
        "2026-01-01",
        "2026-03-31",
        "2026-05-01",
        17000,
        40000,
        capex_tag="PaymentsToAcquireProductiveAssets",
    )
    quarter(
        engine,
        AMZN,
        "2026-04-01",
        "2026-06-30",
        "2026-08-01",
        32000,
        35992,
        capex_tag="PaymentsToAcquireProductiveAssets",
    )
    fact(
        engine,
        AMZN,
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "2026-01-01",
        "2026-03-31",
        160000,
        "2026-05-01",
    )
    fact(
        engine,
        AMZN,
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "2026-04-01",
        "2026-06-30",
        170000,
        "2026-08-01",
    )
    inst(
        engine,
        AMZN,
        "2026-06-30",
        "2026-08-01",
        CashAndCashEquivalentsAtCarryingValue=92988,
        MarketableSecuritiesCurrent=30000,
    )
    g = gate.evaluate(engine, AMZN, "AMZN", TODAY, models=MF, calendar=False)
    assert round(g.runway, 1) == 9.1 and g.state == "pass" and g.tier == "capex_funded"
    assert "broader tag" in g.capex_mark and "broader tag" in g.method()
    f = debt.fcf_burn(engine, g, TODAY)
    assert f.basis == "last two quarters × 2" and round(f.value, 4) == round(-53984 / 660000, 4)
    assert f.tier == "capex-funded"


def test_mstr_liquidity_only_with_the_24_month_wall(dbs):
    engine, _ = dbs
    entity(engine, MSTR, "Strategy Inc", "6199", ticker="MSTR")
    quarter(engine, MSTR, "2026-01-01", "2026-03-31", "2026-05-01", -20, 1)
    quarter(engine, MSTR, "2026-04-01", "2026-06-30", "2026-08-01", -30, 1)
    inst(engine, MSTR, "2026-06-30", "2026-08-01", CashAndCashEquivalentsAtCarryingValue=2448)
    inst(
        engine,
        MSTR,
        "2025-12-31",
        "2026-02-05",
        "10-K",
        LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths=40,
        LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo=4510,
    )
    g = gate.evaluate(engine, MSTR, "MSTR", TODAY, models=MF, calendar=False)
    assert g.scope == "liquidity_only" and g.state == "pass"
    assert g.runway_test[0] == "shown" and g.debt12 == 40 * M
    assert g.debt24 == 4_550 * M and "vs liquidity 2,448M" in g.debt24_text
    s = distress.score(engine, MSTR, "MSTR", TODAY, models=MF)
    assert s.not_meaningful == "not_meaningful"


def test_etv_not_applicable_reads_not_pass(dbs):
    engine, _ = dbs
    entity(engine, ETV, "Eaton Vance Tax-Managed Buy-Write Opportunities Fund", None, ticker="ETV")
    g = gate.evaluate(engine, ETV, "ETV", TODAY, models=MF)
    assert g.state == "not_applicable" and "not-pass" in g.method()
    cg = gate_step.company_gate(engine, "ETV", ETV, NOW, mf=MF)
    sig = engine.execute(
        "SELECT * FROM signal WHERE signal = 'survival_gate' AND timeframe = 'MY'"
    ).fetchone()
    assert sig["value_text"] == "not_applicable" and sig["evidence_grade"] == "B"
    assert cg.queued == {}
    rw = engine.execute(
        "SELECT method FROM signal WHERE signal = 'runway_q' AND timeframe = 'MY'"
    ).fetchone()
    assert rw["method"].startswith("missing: not applicable (fund)")


def test_infq_trust_only_before_the_closing_then_ocf_only_runway(dbs):
    engine, _ = dbs
    entity(engine, INFQ, "Infleqtion, Inc.", "3829", ticker="INFQ")
    inst(
        engine,
        INFQ,
        "2025-09-30",
        "2025-11-10",
        AssetsHeldInTrustNoncurrent=418,
        CashAndCashEquivalentsAtCarryingValue=1,
    )
    before = gate.evaluate(engine, INFQ, "INFQ", "2026-01-15", models=MF, calendar=False)
    assert before.scope == "trust_only" and before.state == "pass" and before.trust == 418 * M
    quarter(engine, INFQ, "2026-01-01", "2026-03-31", "2026-05-12", -4.0)
    quarter(engine, INFQ, "2026-04-01", "2026-06-30", "2026-08-10", -6.19)
    inst(engine, INFQ, "2026-06-30", "2026-08-10", CashAndCashEquivalentsAtCarryingValue=477)
    g = gate.evaluate(engine, INFQ, "INFQ", TODAY, models=MF, calendar=False)
    assert g.scope == "full" and g.ocf_only and round(g.runway, 1) == 93.6 and g.state == "pass"
    assert g.gate_inputs == [("capex", "capex untagged")]
    cg = gate_step.company_gate(engine, "INFQ", INFQ, NOW, mf=MF)
    assert cg.queued == {"m04_gate_input:capex": "queued"}
    # the owner says capex is not reported: the label stays, no new item
    item = engine.execute(
        "SELECT item_id FROM review_queue WHERE kind = 'm04_gate_input'"
    ).fetchone()[0]
    from engine import review

    done = review.m04_action(engine, item, "not_reported", "", "owner", NOW)
    assert done.startswith("not_reported")
    g = gate.evaluate(engine, INFQ, "INFQ", TODAY, models=MF, calendar=False)
    assert g.gate_inputs == [] and "capex not reported (owner)" in g.method()


def test_map_tag_action_needs_a_stored_tag(dbs):
    engine, _ = dbs
    entity(engine, INFQ, "Infleqtion, Inc.", "3829", ticker="INFQ")
    quarter(engine, INFQ, "2026-01-01", "2026-03-31", "2026-05-12", -4.0)
    quarter(engine, INFQ, "2026-04-01", "2026-06-30", "2026-08-10", -6.19)
    inst(engine, INFQ, "2026-06-30", "2026-08-10", CashAndCashEquivalentsAtCarryingValue=477)
    gate_step.company_gate(engine, "INFQ", INFQ, NOW, mf=MF)
    item = engine.execute(
        "SELECT item_id FROM review_queue WHERE kind = 'm04_gate_input'"
    ).fetchone()[0]
    from engine import review

    with pytest.raises(review.ReviewError, match="No stored fact"):
        review.m04_action(
            engine,
            item,
            "map_tag",
            "",
            "owner",
            NOW,
            target="us-gaap:PaymentsForCapitalImprovements",
        )
    fact(
        engine,
        INFQ,
        "PaymentsForCapitalImprovements",
        "2026-01-01",
        "2026-03-31",
        0.5,
        "2026-05-12",
    )
    fact(
        engine,
        INFQ,
        "PaymentsForCapitalImprovements",
        "2026-04-01",
        "2026-06-30",
        0.7,
        "2026-08-10",
    )
    review.m04_action(
        engine, item, "map_tag", "", "owner", NOW, target="us-gaap:PaymentsForCapitalImprovements"
    )
    g = gate.evaluate(engine, INFQ, "INFQ", TODAY, models=MF, calendar=False)
    assert not g.ocf_only and g.bases[0].capex == pytest.approx(1.2 * M)
    assert "owner-mapped tag" in " ".join(p for p in [g.method()]) or g.gate_inputs == []


def test_one_quarter_is_incomplete_and_overdue_adds_an_exit_warning(dbs):
    engine, _ = dbs
    entity(engine, "0000000001", "One Quarter Co", "3711", ticker="ONEQ")
    quarter(engine, "0000000001", "2026-04-01", "2026-06-30", "2026-08-10", -100, 10)
    inst(
        engine, "0000000001", "2026-06-30", "2026-08-10", CashAndCashEquivalentsAtCarryingValue=500
    )
    g = gate.evaluate(engine, "0000000001", "ONEQ", TODAY, models=MF)
    assert g.state == "incomplete" and any("one quarter" in m for m in g.missing)
    engine.execute(
        "INSERT INTO filing_status (cik, period_end, form, category_source, due_date, status, evaluated_at) "
        "VALUES ('0000000001', '2026-06-30', '10-Q', 'submissions', '2026-08-14', 'overdue', 'n')"
    )
    g = gate.evaluate(engine, "0000000001", "ONEQ", TODAY, models=MF)
    assert (
        g.overdue
        and "overdue filing (D-M04-61)" in g.exit_warning
        and g.signal_as_of >= "2026-08-14"
    )


def test_8k_103_fails_the_gate_and_open_402_warns(dbs):
    engine, _ = dbs
    rivian(engine)
    for item, cls, state in (("1.03", "bankruptcy", "fail"), ("4.02", "non_reliance", "warn")):
        engine.execute(
            "INSERT INTO m04_event (accession, item, cik, form, filed, class, base_state, state, review, "
            "clears_when, note, first_seen_at, computed_at) VALUES (?, ?, ?, '8-K', '2026-09-01', ?, ?, ?, 1, "
            "'never', 'n', 'n', 'n')",
            (f"0001874178-26-0001{item[0]}", item, RIVN, cls, state, state),
        )
    g = gate.evaluate(engine, RIVN, "RIVN", TODAY, models=MF, calendar=False)
    assert g.state == "fail" and any("8-K 1.03 bankruptcy" in t for t in g.triggers)
    assert g.non_reliance.startswith("inputs under non-reliance")


# --- Distress scores (D-M04-31, S4.4, S4.8) ----------------------------------------------------


def z_company(engine, cik, ticker, close, *, ifrs=False, form="10-K", self_funding=True):
    """TA 100,000; X1 0.1, X2 0.5, X3 0.02, X5 0.5; X4 = market value ÷ 50,000."""
    entity(engine, cik, ticker, "3674", ticker=ticker)
    filed = "2026-02-10"
    inst(
        engine,
        cik,
        "2025-12-31",
        filed,
        form,
        Assets=100000,
        AssetsCurrent=30000,
        LiabilitiesCurrent=20000,
        Liabilities=50000,
        RetainedEarningsAccumulatedDeficit=50000,
        StockholdersEquity=50000,
        CashAndCashEquivalentsAtCarryingValue=10000,
    )
    fact(engine, cik, "OperatingIncomeLoss", "2025-01-01", "2025-12-31", 2000, filed, form)
    fact(
        engine,
        cik,
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "2025-01-01",
        "2025-12-31",
        50000,
        filed,
        form,
    )
    cover(engine, cik, "2026-02-01", filed, 1_000_000_000)
    price(engine, cik, ticker, "2026-10-09", close)


def test_manufacturer_z_grey_raises_no_score_gap(dbs):
    engine, _ = dbs
    z_company(engine, INTC, "INTC", 51.16667)
    z_company(engine, GFS, "GFS", 57.0)
    for cik, t, want in ((INTC, "INTC", 2.00), (GFS, "GFS", 2.07)):
        s = distress.score(engine, cik, t, TODAY, models=MF, close_day=TODAY)
        assert s.variant == "Z" and round(s.value, 2) == want and s.zone == "grey" and not s.warning
        assert "close $" in s.close_note and "2026-10-09" in s.close_note
        assert s.without_x4 == pytest.approx(s.value - 0.6 * s.x["X4"])


def test_boeing_z_153_warns_and_opens_score_gap_with_a_passing_gate(dbs):
    engine, _ = dbs
    entity(engine, BA, "BOEING CO", "3721", ticker="BA")
    filed = "2026-01-30"
    inst(
        engine,
        BA,
        "2025-12-31",
        filed,
        "10-K",
        Assets=150000,
        AssetsCurrent=120000,
        LiabilitiesCurrent=95000,
        Liabilities=144546,
        RetainedEarningsAccumulatedDeficit=17252,
        StockholdersEquity=5454,
        CashAndCashEquivalentsAtCarryingValue=23000,
    )
    fact(engine, BA, "OperatingIncomeLoss", "2025-01-01", "2025-12-31", -1000, filed, "10-K")
    fact(
        engine,
        BA,
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "2025-01-01",
        "2025-12-31",
        80000,
        filed,
        "10-K",
    )
    quarter(engine, BA, "2025-07-01", "2025-09-30", "2025-10-29", 2400, 700)
    quarter(engine, BA, "2025-10-01", "2025-12-31", filed, 1600, 900, form="10-K")
    cover(engine, BA, "2026-01-20", filed, 760_000_000)
    price(engine, BA, "BA", "2026-10-09", 208.4870)
    cg = gate_step.company_gate(engine, "BA", BA, NOW, mf=MF)
    assert cg.gate.state == "pass" and cg.gate.tier == "self_funding"
    assert round(cg.score.value, 2) == 1.53 and cg.score.warning
    assert "stage unconfirmed" in cg.score.method()
    assert cg.queued == {"m04_score_gap": "queued"}
    sig = engine.execute(
        "SELECT * FROM signal WHERE signal = 'distress_score' AND timeframe = 'MY'"
    ).fetchone()
    assert sig["value_text"] == "distress" and "close $208.49 of 2026-10-09" in sig["method"]
    st = engine.execute(
        "SELECT * FROM signal WHERE signal = 'survival_gate' AND timeframe = 'MY'"
    ).fetchone()
    assert st["value_text"] == "pass" and st["as_of"] == filed  # the gate ignores the score


def test_rivian_scores_z_by_sic_with_zpp_beside_and_ohlson(dbs):
    engine, _ = dbs
    rivian(engine)
    cover(engine, RIVN, "2026-07-28", "2026-08-05", 1_200_000_000)
    price(engine, RIVN, "RIVN", "2026-10-09", 12.0)
    s = distress.score(engine, RIVN, "RIVN", TODAY, models=MF, close_day=TODAY)
    assert s.variant == "Z" and s.warning and round(s.zpp, 2) == -5.37 and s.zpp_zone == "distress"
    assert round(s.o_p, 3) == 0.031  # Ohlson Model 1, assets in dollars, index 706 (2025)


# --- Debt rows and negative equity (D-M04-29, S4.8) ---------------------------------------------


def test_debt_rows_and_negative_equity(dbs):
    engine, _ = dbs
    c = "0000000002"
    entity(engine, c, "Debt Co", "2000", ticker="DEBT")
    for y, filed in ((2023, "2024-02-10"), (2024, "2025-02-10"), (2025, "2026-02-10")):
        e = f"{y}-12-31"
        inst(
            engine,
            c,
            e,
            filed,
            "10-K",
            LongTermDebtNoncurrent=900 + 100 * (y - 2023),
            DebtCurrent=100,
            CashAndCashEquivalentsAtCarryingValue=200,
            StockholdersEquity=-50,
            RetainedEarningsAccumulatedDeficit=300,
        )
        fact(
            engine,
            c,
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            f"{y}-01-01",
            e,
            1000,
            filed,
            "10-K",
        )
        fact(engine, c, "OperatingIncomeLoss", f"{y}-01-01", e, 150, filed, "10-K")
        fact(engine, c, "DepreciationDepletionAndAmortization", f"{y}-01-01", e, 50, filed, "10-K")
        fact(
            engine,
            c,
            "NetCashProvidedByUsedInOperatingActivities",
            f"{y}-01-01",
            e,
            120,
            filed,
            "10-K",
        )
    d = debt.debt_rows(engine, c, TODAY, "2025-12-31")
    assert d.latest.ratio == pytest.approx(1.2) and d.latest.nd_ebitda == pytest.approx(5.0)
    assert "own 3-year range 1.00–1.20 (3 fiscal years)" in d.range_text("ratio")
    assert d.peer_note.startswith("peer z: missing: no confirmed SEC peers")
    n = debt.negative_equity(engine, c, TODAY)
    assert n.state == "note" and "buyback-funded" in n.reasons[0]
    fact(engine, c, "OperatingIncomeLoss", "2025-01-01", "2025-12-31", -10, "2026-03-01", "10-K/A")
    assert debt.negative_equity(engine, c, TODAY).state == "warn"


# --- Turns, items, the pass, the script, the tab -------------------------------------------------


def test_gate_fail_opens_once_and_is_withdrawn_when_it_passes(dbs):
    engine, _ = dbs
    rivian(engine)
    gp = gate_step.gate_pass(engine, {"RIVN": RIVN}, NOW, mf=MF)
    assert gp.companies["RIVN"].queued == {"m04_gate_fail": "queued"}
    assert gp.alerts and "survival gate turned fail" in gp.alerts[0]
    later = NOW.replace(hour=13)
    again = gate_step.gate_pass(engine, {"RIVN": RIVN}, later, mf=MF)
    assert again.companies["RIVN"].queued == {"m04_gate_fail": "suppressed"} and not again.alerts
    gate_view.add_credit_line(
        engine, RIVN, "ABL", "536", "2029-06-30", "2026-06-30", "note", "owner", NOW
    )
    third = gate_step.gate_pass(engine, {"RIVN": RIVN}, later, mf=MF)
    assert third.companies["RIVN"].gate.state == "warn" and third.companies["RIVN"].withdrawn == 1
    row = engine.execute(
        "SELECT resolution, resolved_by FROM review_queue WHERE kind = 'm04_gate_fail'"
    ).fetchone()
    assert tuple(row) == ("withdrawn", "engine")
    names = {r[0] for r in engine.execute("SELECT DISTINCT signal FROM signal")}
    assert set(gate_step.SIGNALS) <= names
    assert queue.GROUP["m04_gate_fail"] == 1 and "m04_gate_fail" in queue.UNCAPPED


def test_gate_signals_never_fill_zero(dbs):
    engine, _ = dbs
    entity(engine, "0000000003", "Empty Co", "3711", ticker="EMPT")
    gate_step.company_gate(engine, "EMPT", "0000000003", NOW, mf=MF)
    rows = engine.execute(
        "SELECT signal, value, value_text, method FROM signal WHERE timeframe = 'MY'"
    ).fetchall()
    gate_row = next(r for r in rows if r["signal"] == "survival_gate")
    assert gate_row["value_text"] == "incomplete" or gate_row["method"].startswith("missing:")
    for r in rows:
        if r["signal"] != "survival_gate":
            assert r["value"] is None and r["method"].startswith("missing:"), r["signal"]


def run_financials_module():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_financials

    return run_financials


def test_gate_run_with_a_fake_client(dbs, make_client):
    rf = run_financials_module()
    engine, _ = dbs
    from engine.sec.xbrl_facts import CONCEPT_URL

    routes = {}
    for tag in rf.GATE_TAGS:
        f = M04 / f"nvta_us-gaap_{tag}_20261013.json"
        routes[CONCEPT_URL.format(cik=NVTA, taxonomy="us-gaap", tag=tag)] = [
            ok(f.read_bytes()) if f.exists() else ok(b"", 404)
        ]
    rivian(engine)  # covered: its stored facts are read, no request
    t = FakeTransport(routes)
    out: list[str] = []
    rf.gate_run(engine, {"RIVN": RIVN}, NOW, lambda *a: out.extend(a), make_client(t), mf=MF)
    text = "\n".join(out)
    assert len(t.calls) == len(rf.GATE_TAGS) and all(NVTA[3:] in u for u, _, _ in t.calls)
    for want in ("RIVN: covered (refresh facts stored), 0 requests", "=== Summary gate (Part 4a)",
                 "Invitae FY2021 (as of 2022-03-01, 715 days before its 8-K 1.03): fail",
                 "Rivian with the ABL as if confirmed: warn", "Fails without a trigger: 0",
                 "m04_gate_fail queued 1", "RIVN: fail [full gate]"):  # fmt: skip
        assert want in text, want


def test_financials_tab_shows_the_gate_panel(tmp_path):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui.app import create_app
    from engine.ui.settings import UiSettings

    data = tmp_path / "data"
    engine = open_db("engine", data)
    rivian(engine)
    gate_step.gate_pass(engine, {"RIVN": RIVN}, NOW, mf=MF)
    item = engine.execute(
        "SELECT item_id FROM review_queue WHERE kind = 'm04_gate_fail'"
    ).fetchone()[0]
    engine.close()
    open_db("corpus", data).close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text('[watchlist]\ntickers = ["RIVN"]\n', encoding="utf-8")
    with TestClient(create_app(UiSettings(data_dir=data, watchlist=watch))) as c:
        html = c.get("/c/RIVN?tab=financials").text
        one = c.get(f"/review/{item}").text
        guide = c.get("/review").text
    for want in ("Survival gate — RIVN", "Add confirmed credit line", "Distress, debt and FCF burn",
                 "Gate — all covered companies", "credit: none confirmed (cash-only)",
                 "gate: fail"):  # fmt: skip
        assert want in html, want
    assert "Survival gate: runway, maturity wall" not in html  # left "still to come"
    assert "object at 0x" not in html
    assert "Inputs wrong (note)" in one and "survival gate panel" in one
    assert "Capex-funded runway below 6 quarters" in guide


# --- Live check 1 (logs/financials_gate_20261013-100053.txt) ------------------------------------


def intel_fy2024_like(
    engine, cash_tag="CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
):
    """Intel as of 2025-01-31 in the live log read the 2021-09-25 balance sheet: its cash tag
    was absent for the later periods as known then. Here the main tag stops at Q3 2021, the
    FY2024 cash sits under another tag, and the FY2025 10-K re-tags the 2024 comparative
    under the main tag (filed a year later, so invisible on 2025-01-31)."""
    entity(engine, INTC, "INTEL CORP", "3674", ticker="INTC")
    inst(engine, INTC, "2021-09-25", "2021-10-22", CashAndCashEquivalentsAtCarryingValue=4807,
         ShortTermInvestments=7067, DebtCurrent=4694)  # fmt: skip
    for e, f, ocf, cx in (
        ("2024-03-30", "2024-04-26", -1227, 5970),
        ("2024-06-29", "2024-08-02", 1054, 11670),
        ("2024-09-28", "2024-11-01", 5130, 17770),
    ):
        quarter(engine, INTC, "2024-01-01", e, f, ocf, cx)
    quarter(engine, INTC, "2024-01-01", "2024-12-28", "2025-01-31", 8288, 23944, form="10-K")
    tags = {"Assets": 196485, "ShortTermInvestments": 13813, "DebtCurrent": 3729}
    if cash_tag:
        tags[cash_tag] = 8249 + 120
        tags["RestrictedCashCurrent"] = 120
    inst(engine, INTC, "2024-12-28", "2025-01-31", "10-K", **tags)
    fact(engine, INTC, "CashAndCashEquivalentsAtCarryingValue", None, "2024-12-28", 8249,
         "2026-01-30", "10-K", acc="0000050863-26-000001")  # fmt: skip


def test_intel_historical_as_of_reads_the_latest_balance_sheet_not_a_stale_one(dbs):
    engine, _ = dbs
    intel_fy2024_like(engine)
    g = gate.evaluate(engine, INTC, "INTC", "2025-01-31", models=MF, calendar=False)
    assert g.balance_date == "2024-12-28" and g.cash == 8249 * M and g.liquidity == 22062 * M
    assert "CashCashEquivalentsRestrictedCash" in g.method() and "− restricted 120M" in g.method()
    assert g.tier == "capex_funded" and round(g.runway, 1) == 5.6 and g.state == "warn"
    assert g.runway_review
    # today the main tag is back (FY2025 10-K): no fallback label
    now = gate.evaluate(engine, INTC, "INTC", TODAY, models=MF, calendar=False)
    assert now.balance_date == "2024-12-28" and "fallback" not in now.method()


def test_no_cash_tag_at_the_latest_balance_sheet_is_incomplete_with_the_tags_named(dbs):
    engine, _ = dbs
    intel_fy2024_like(engine, cash_tag=None)
    fact(
        engine, INTC, "CashAndShortTermInvestments", None, "2024-12-28", 22062, "2025-01-31", "10-K"
    )
    g = gate.evaluate(engine, INTC, "INTC", "2025-01-31", models=MF, calendar=False)
    assert g.state == "incomplete" and g.balance_date == "2024-12-28"
    assert "cash at the latest balance sheet (2024-12-28)" in g.missing[0]
    assert "us-gaap:CashAndShortTermInvestments 22,062M" in g.method()
    assert ("cash", "no cash tag at the balance sheet of 2024-12-28") in g.gate_inputs


def test_infq_before_the_closing_reads_trust_only_and_the_line_names_the_scope(dbs):
    rf = run_financials_module()
    engine, _ = dbs
    entity(engine, INFQ, "Infleqtion, Inc.", "3829", ticker="INFQ")
    inst(engine, INFQ, "2025-09-30", "2025-11-10", AssetsHeldInTrustNoncurrent=420,
         CashAndCashEquivalentsAtCarryingValue=1)  # fmt: skip
    quarter(engine, INFQ, "2026-04-01", "2026-06-30", "2026-08-10", -6.19)
    inst(engine, INFQ, "2026-06-30", "2026-08-10", CashAndCashEquivalentsAtCarryingValue=477)
    g = gate.evaluate(engine, INFQ, "INFQ", "2026-02-12", models=MF, calendar=False)
    assert g.scope == "trust_only" and g.state == "pass" and g.trust == 420 * M
    out: list[str] = []
    rf._gate_line(lambda *a: out.extend(a), "INFQ before the closing", g, "trust only")
    assert "pass [trust only] — runway —" in out[0]


def orcl_like(engine, cik, ticker):
    """Capex-funded, runway 5.0 q on the last two quarters, Z'' in distress (live check 1:
    ORCL warn with Z'' 0.97)."""
    entity(engine, cik, f"{ticker} CORP", "7372", fye="0630", ticker=ticker)
    quarter(engine, cik, "2026-01-01", "2026-03-31", "2026-04-30", 5000, 9000)
    quarter(engine, cik, "2026-04-01", "2026-06-30", "2026-08-01", 5000, 9000, form="10-K")
    inst(engine, cik, "2026-06-30", "2026-08-01", "10-K", Assets=100000, AssetsCurrent=25000,
         LiabilitiesCurrent=30000, Liabilities=95000, RetainedEarningsAccumulatedDeficit=-5000,
         StockholdersEquity=5000, CashAndCashEquivalentsAtCarryingValue=20000)  # fmt: skip
    fact(engine, cik, "OperatingIncomeLoss", "2025-07-01", "2026-06-30", 1000, "2026-08-01", "10-K")


def test_capex_funded_review_and_score_gap_open_at_first_sight_but_not_for_tracked(dbs):
    from engine.themes import tiers

    engine, _ = dbs
    orcl_like(engine, "0000000011", "CORE")
    cg = gate_step.company_gate(engine, "CORE", "0000000011", NOW, mf=MF)
    assert cg.gate.state == "warn" and cg.gate.runway_review and round(cg.gate.runway, 1) == 5.0
    assert cg.score.variant == "Z''" and cg.score.warning  # warn counts as pass (D-M04-31)
    assert cg.queued == {"m04_runway": "queued", "m04_score_gap": "queued"}
    assert "prior year" in cg.score.o_note and "net income ends stored: TTM none" in cg.score.o_note
    orcl_like(engine, "0001341439", "ORCL")
    tiers.add_tracked(engine, "0001341439", "ORCL", reason="t", theme_key=None, by="owner", now=NOW)
    gp = gate_step.gate_pass(engine, {"ORCL": "0001341439"}, NOW, mf=MF)
    oc = gp.companies["ORCL"]
    assert oc.queued == {} and oc.held == ["m04_runway", "m04_score_gap"]
    assert len(gate_step.open_items(engine)) == 2  # CORE's two; none for the tracked name
    assert "no stage computed: tracked tier" in oc.score.method()


def test_rivian_without_a_cover_count_uses_the_labelled_share_fallback(dbs):
    engine, _ = dbs
    rivian(engine)
    price(engine, RIVN, "RIVN", "2026-10-09", 12.0)
    fact(engine, RIVN, "WeightedAverageNumberOfSharesOutstandingBasic", "2026-04-01",
         "2026-06-30", 1_200_000_000, "2026-08-05", unit="shares")  # fmt: skip
    s = distress.score(engine, RIVN, "RIVN", TODAY, models=MF, close_day=TODAY)
    assert s.variant == "Z" and round(s.value, 2) == -1.84 and s.warning
    assert "basic weighted-average shares (fallback:" in s.close_note
    assert round(s.zpp, 2) == -5.37


def test_short_term_investments_alias_fallback_and_the_tags_named(dbs):
    engine, _ = dbs
    nv = "0001045810"
    entity(engine, nv, "NVIDIA CORP", "3674", fye="0125", ticker="NVDA")
    quarter(engine, nv, "2026-01-26", "2026-04-26", "2026-05-28", 20000, 1000)
    quarter(engine, nv, "2026-04-27", "2026-07-26", "2026-08-27", 20000, 1000)
    inst(engine, nv, "2026-07-26", "2026-08-27", CashAndCashEquivalentsAtCarryingValue=22443)
    fact(engine, nv, "MarketableSecuritiesCurrent", None, "2019-01-27", 5000, "2019-02-21", "10-K")
    g = gate.evaluate(engine, nv, "NVDA", TODAY, models=MF, calendar=False)
    assert g.sti is None and "ST investments none at 2026-07-26: tags with facts " \
        "us-gaap:MarketableSecuritiesCurrent (latest 2019-01-27)" in g.method()  # fmt: skip
    assert "no facts for us-gaap:ShortTermInvestments" in g.method()
    fact(engine, nv, "CashCashEquivalentsAndShortTermInvestments", None, "2026-07-26", 60000,
         "2026-08-27")  # fmt: skip
    g = gate.evaluate(engine, nv, "NVDA", TODAY, models=MF, calendar=False)
    assert g.sti == (60000 - 22443) * M and "(fallback, labelled)" in g.method()
    fact(engine, nv, "MarketableSecuritiesAndEquitySecuritiesFVNI", None, "2026-07-26", 40000,
         "2026-08-27", tax="nvda")  # fmt: skip
    g = gate.evaluate(engine, nv, "NVDA", TODAY, models=MF, calendar=False)
    assert g.sti == 40000 * M and "alias, NVDA only" in g.method()
    assert debt.debt_rows(engine, nv, TODAY, "2026-07-26").latest.cash == (22443 + 40000) * M


def test_stage_label_reads_the_owner_stage_like_the_setup_page(dbs):
    from engine.financials import stage

    engine, _ = dbs
    c = "0000000012"
    assert "no stage computed" in distress.stage_label(engine, c)[0]
    stage.confirm(engine, c, None, "growth", "owner", NOW)
    assert distress.stage_label(engine, c) == ("stage growth (confirmed)", True)


def test_gate_summary_says_already_proposed_and_lists_open_items(dbs, make_client):
    rf = run_financials_module()
    engine, _ = dbs
    rivian(engine)
    rf.gate_run(engine, {"RIVN": RIVN}, NOW, lambda *a: None, None, mf=MF)
    out: list[str] = []
    rf.gate_run(engine, {"RIVN": RIVN}, NOW.replace(hour=13), lambda *a: out.extend(a), None,
                mf=MF)  # fmt: skip
    text = "\n".join(out)
    assert "m04_gate_fail already proposed by an earlier run 1" in text and "suppressed" not in text
    assert "Open Part 4a items: 1" in text and "m04_gate_fail RIVN (item 1" in text
    assert "12-month test passes; + 4 × burn warns" in text
