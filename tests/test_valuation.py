"""M08 Part 1: standard rows, EV, NEP, cyclical flag, routing, percentiles, the pass, the
script and the tab (docs/M08_VALUATION.md; fixtures README in tests/fixtures/m08/)."""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from engine.financials import models
from engine.financials import nep as nep_mod
from engine.signals import Source, write_signal
from engine.valuation import params, pctile, route, step
from engine.valuation.asof import Known
from engine.valuation.measures import STANDARD_KEYS, snapshot
from engine.valuation.params import Params

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures" / "m08"
M = 1_000_000
TODAY = "2026-10-13"
NOW = datetime(2026, 10, 13, 16, 0, tzinfo=UTC)  # Tuesday, 12:00 US Eastern
P = Params()
MU, NVDA, INFQ, MSTR, ETV = "0000723125", "0001045810", "0002007825", "0001050446", "0001270523"
MF = models.parse(
    {
        "company": [
            {
                "ticker": "MSTR",
                "cik": MSTR,
                "tag": "asset_treasury",
                "reason": "bitcoin treasury",
                "source": "D-M04-8",
            },
            {
                "ticker": "ETV",
                "cik": ETV,
                "tag": "fund",
                "reason": "closed-end fund",
                "source": "D-M04-8",
            },
            {
                "ticker": "INFQ",
                "cik": INFQ,
                "tag": "spac_shell",
                "before": "2026-02-13",
                "reason": "shell years",
                "source": "D-M04-8",
            },
        ]
    }
)
NO_MODELS = models.ModelFile("none", ())


# --- helpers ---


def entity(engine, cik, name, ticker, sic="3674", fye="1231"):
    engine.execute(
        "INSERT OR REPLACE INTO entity (cik, name, sic, fiscal_year_end, source_ref, fetched_at) "
        "VALUES (?, ?, ?, ?, 't', 'n')",
        (cik, name, sic, fye),
    )
    engine.execute(
        "INSERT OR IGNORE INTO ticker (ticker, cik, valid_from, source) VALUES (?, ?, "
        "'2000-01-01', 't')",
        (ticker, cik),
    )


def fact(
    engine, cik, tag, start, end, value, filed, form="10-K", tax="us-gaap", unit="USD", acc=None
):
    acc = acc or f"{cik}-{filed[2:4]}-{filed[5:7]}{filed[8:10]}{len(form):02d}"
    engine.execute(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession, "
        "form, filed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cik, tax, tag, unit, start, end, value, acc, form, filed),
    )
    return acc


def filing(engine, cik, acc, form, filed, report_date=None):
    engine.execute(
        "INSERT OR IGNORE INTO filing (accession, cik, form, filed, report_date, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, 'n')",
        (acc, cik, form, filed, report_date),
    )


def bars(engine, cik, symbol, rows):
    """rows: (date, raw close[, div_cash[, split_factor]])."""
    engine.execute(
        "INSERT OR REPLACE INTO price_fetch (symbol, cik, bars) VALUES (?, ?, ?)",
        (symbol, cik, len(rows)),
    )
    engine.executemany(
        "INSERT OR REPLACE INTO price_bar (symbol, date, close, adj_close, div_cash, split_factor, "
        "source, fetched_at) VALUES (?, ?, ?, ?, ?, ?, 'tiingo', 'n')",
        [
            (symbol, r[0], r[1], r[1], r[2] if len(r) > 2 else 0.0, r[3] if len(r) > 3 else 1.0)
            for r in rows
        ],
    )


def weekdays(start: str, end: str):
    d, stop = date.fromisoformat(start), date.fromisoformat(end)
    while d <= stop:
        if d.weekday() < 5:
            yield d.isoformat()
        d += timedelta(days=1)


def cover(engine, cik, day, filed, n, form="10-Q"):
    fact(
        engine,
        cik,
        "EntityCommonStockSharesOutstanding",
        None,
        day,
        n,
        filed,
        form,
        "dei",
        "shares",
    )


def confirm_stage(engine, cik, stage):
    engine.execute(
        "INSERT INTO company_stage (cik, period_end, fiscal_label, computed, years, reasons, "
        "method, confirmed, confirmed_by, confirmed_at, computed_at) VALUES (?, '2025-12-31', "
        "'FY2025', ?, '[]', '[]', 't', ?, 'owner', '2026-10-01', '2026-10-01')",
        (cik, stage, stage),
    )


def m04_row(engine, cik, signal, text, as_of="2026-10-01"):
    write_signal(
        engine,
        cik=cik,
        module_id="M04",
        signal=signal,
        as_of=as_of,
        method="t",
        value_text=text,
        sources=[Source("a", as_of)],
    )


def load_mu(engine):
    fx = json.loads((FIX / "mu_fy2014_25.json").read_text(encoding="utf-8"))
    cik = fx["cik"]
    entity(engine, cik, fx["name"], fx["ticker"], fx["sic"], fx["fye"])
    for start, end, filed, rev, gp, oi, ni, eps, dil in fx["years"]:
        acc = fact(
            engine,
            cik,
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            start,
            end,
            rev * M,
            filed,
        )
        filing(engine, cik, acc, "10-K", filed, end)
        for tag, v in (("GrossProfit", gp), ("OperatingIncomeLoss", oi), ("NetIncomeLoss", ni)):
            fact(engine, cik, tag, start, end, v * M, filed, acc=acc)
        fact(
            engine,
            cik,
            "EarningsPerShareDiluted",
            start,
            end,
            eps,
            filed,
            unit="USD/shares",
            acc=acc,
        )
        fact(
            engine,
            cik,
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            start,
            end,
            dil * M,
            filed,
            unit="shares",
            acc=acc,
        )
    years = {y[1]: y for y in fx["years"]}
    for end, cash, sti, ltd, cur, eq, da, ocf, capex in fx["balance"]:
        start, filed = years[end][0], years[end][2]
        acc = f"{cik}-{filed[2:4]}-{filed[5:7]}{filed[8:10]}04"
        for tag, v in (
            ("CashAndCashEquivalentsAtCarryingValue", cash),
            ("ShortTermInvestments", sti),
            ("LongTermDebtNoncurrent", ltd),
            ("DebtCurrent", cur),
            ("StockholdersEquity", eq),
        ):
            fact(engine, cik, tag, None, end, v * M, filed, acc=acc)
        for tag, v in (
            ("DepreciationDepletionAndAmortization", da),
            ("NetCashProvidedByUsedInOperatingActivities", ocf),
            ("PaymentsToAcquirePropertyPlantAndEquipment", capex),
        ):
            fact(engine, cik, tag, start, end, v * M, filed, acc=acc)
    for day, filed, n in fx["covers"]:
        cover(engine, cik, day, filed, n, "10-K")
    bars(engine, cik, "MU", fx["closes"])
    return fx


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- parameters ---


def test_config_file_equals_the_built_in_defaults():
    got = params.load(ROOT / "config" / "valuation.toml")
    assert dataclasses.replace(got, overrides=()) == Params()
    # the owner's override from live check 1 (option a)
    assert [(o.ticker, o.cyclical) for o in got.overrides] == [("AMZN", False)]


def test_params_reject_unknown_keys_and_bad_overrides(tmp_path):
    with pytest.raises(params.ParamsError, match="unknown key"):
        params.parse({"version": "v1", "history": {"points": 3}})
    with pytest.raises(params.ParamsError, match="headline must be one of"):
        params.parse(
            {"version": "v1", "company": [{"ticker": "X", "headline": "pe", "reason": "r"}]}
        )
    with pytest.raises(params.ParamsError, match="missing reason"):
        params.parse({"version": "v1", "company": [{"ticker": "X", "cyclical": False}]})
    p = params.parse(
        {
            "version": "v1",
            "company": [{"ticker": "acme", "cyclical": False, "reason": "one loss year"}],
        }
    )
    assert p.override("0000000001", "ACME").cyclical is False
    bad = tmp_path / "v.toml"
    bad.write_text("version = 1\n", encoding="utf-8")
    got, note = params.load_safe(bad)
    assert got == Params() and "defaults used" in note


# --- Micron across the cycle (pack S2 worked example) ---


@pytest.mark.parametrize(
    ("day", "pe"),
    [("2022-10-07", 6.8), ("2023-10-06", None), ("2024-10-04", 146.1), ("2025-10-03", 24.7)],
)
def test_mu_trailing_pe_at_the_10k_dates(dbs, day, pe):
    engine, _ = dbs
    load_mu(engine)
    s = snapshot(Known(engine, MU, TODAY), day, fye="0831")
    m = s.m("val_pe_ttm")
    assert s.close.day == day and "as of FY" in s.twelve
    if pe is None:
        assert m.value is None and m.text == "not_meaningful" and m.missing is None
    else:  # the engine divides TTM net income by diluted shares; the pack used reported EPS
        assert m.value == pytest.approx(pe, rel=0.012)


def test_mu_nep_window_trough_to_trough_on_the_cvd_series(dbs):
    engine, _ = dbs
    load_mu(engine)
    s = snapshot(Known(engine, MU, TODAY), "2024-10-04", fye="0831")
    w = s.nep.window
    assert w.kind == "trough_to_trough" and w.troughs == ["FY2016", "FY2020", "FY2023"]
    assert [y.label for y in w.years] == ["FY2020", "FY2021", "FY2022"]  # FY2023 excluded once
    assert s.nep.margin == pytest.approx(21378 / 79898)
    assert s.nep.nebit_cycle == pytest.approx(21378 * M / 3)
    assert s.nep.nebit_current == pytest.approx(21378 / 79898 * 25111 * M)
    assert s.nep.neps == pytest.approx((2687 + 5861 + 8687) / 3 / 1117)
    ev = 1109 * M * 102.25 + (13375 + 1423 - 7041 - 1065) * M
    assert s.ev == pytest.approx(ev)
    # owner, live check 1: the headline uses the current-revenue base (amends D-M08-3)
    assert s.m("val_ev_nebit").value == pytest.approx(ev / (21378 / 79898 * 25111 * M))
    assert "on cycle-average revenue" in s.m("val_ev_nebit").detail
    assert "later trough year excluded" in s.nep.text()
    assert "current-revenue base" in s.nep.text()


def test_mu_pack_window_fy2019_24_by_hand():
    """The pack's FY2019–24 window on the fixture's figures: revenue and average EPS match the
    pack; operating income sums to 24,313 here vs the pack's 21,923 (an open item)."""
    fx = json.loads((FIX / "mu_fy2014_25.json").read_text(encoding="utf-8"))
    ys = [
        nep_mod.Year(y[1], y[3] * M, y[5] * M, y[6] * M, y[4] * M, eps=y[7])
        for y in fx["years"]
        if "2018-09" <= y[1][:7] <= "2024-08"
    ]
    assert [y.label for y in ys] == [f"FY{n}" for n in range(2019, 2025)]
    w = nep_mod.Window(ys, "longest_history", "operating margin")
    n = nep_mod.normalize(w, ttm_revenue=25111 * M, shares=1117 * M)
    assert sum(y.revenue for y in ys) == fx["pack"]["nep_fy2019_24"]["revenue_sum"] * M
    assert sum(y.eps for y in ys) / 6 == pytest.approx(
        fx["pack"]["average_eps_fy2019_24"], abs=5e-4
    )
    assert n.margin == pytest.approx(24313 / 143955)  # 16.9% (pack: 15.2%)
    assert n.nebit_current == pytest.approx(24313 / 143955 * 25111 * M)
    # normalized EPS on average net income ÷ latest diluted shares (D-M04-106) vs the pack's
    # average reported EPS: 37.1× vs 38.0× at $102.25
    assert 102.25 / n.neps == pytest.approx(37.06, abs=0.05)
    assert 102.25 / fx["pack"]["average_eps_fy2019_24"] == pytest.approx(38.0, abs=0.05)


def test_mu_is_flagged_cyclical_and_routes_to_normalized_ebit_unconfirmed_stage(dbs):
    engine, _ = dbs
    load_mu(engine)
    r = step.evaluate(engine, "MU", MU, "2024-10-04", TODAY, P, NO_MODELS, with_peers=False)
    assert r.flag.cyclical and r.flag.computed and r.flag.source == "computed"
    assert "sign change yes" in r.flag.eps_test and "→ yes" in r.flag.margin_test
    assert r.route.measure == "val_ev_nebit" and "overrides the stage" in r.route.why
    assert r.headline.value == pytest.approx(r.snap.m("val_ev_nebit").value)
    rows = {o.signal: o for o in r.rows}
    assert "inverts at cycle extremes" in rows["val_pe_ttm"].method
    assert rows["valuation_multiple"].info == ("ST",)
    assert "beside: P/normalized EPS" in rows["valuation_multiple"].method
    assert set(STANDARD_KEYS) <= set(rows)  # every standard row, whatever the routing (D32)
    # four annual points only: no own percentile (< 20 quarters)
    assert rows["valuation_pctile"].missing.startswith("0/20 quarters")
    # MU's dividend: four stored bars are not 12 months
    assert rows["val_div_yield"].missing.startswith("fewer than 12 months of stored bars")
    m04_row(engine, MU, "cvd_state", "CYCLICAL_TROUGH")
    r = step.evaluate(engine, "MU", MU, "2024-10-04", TODAY, P, NO_MODELS, with_peers=False)
    assert (
        "reads trough earnings, not expensive" in {o.signal: o for o in r.rows}["val_pe_ttm"].method
    )


def test_owner_override_wins_over_the_computed_flag(dbs):
    engine, _ = dbs
    load_mu(engine)
    confirm_stage(engine, MU, "mature")
    p = params.parse(
        {"version": "v1", "company": [{"cik": MU, "cyclical": False, "reason": "owner test"}]}
    )
    r = step.evaluate(engine, "MU", MU, "2025-10-03", TODAY, p, NO_MODELS, with_peers=False)
    assert r.flag.cyclical is False and r.flag.computed is True and r.flag.source == "owner"
    assert "owner override: owner test" in r.flag.text()
    assert r.route.measure == "val_pe_ttm" and r.headline.value == pytest.approx(24.75, rel=0.01)


# --- NVIDIA: the split and the TTM P/E ---


def load_nvda(engine):
    """Synthetic in NVIDIA's shape (README): FY2026 (2025-01-27..2026-01-25) as filed (Q1 3M,
    6M, 9M YTD, FY), FY2027 Q1 and 6M; quarterly diluted EPS 0.76, 1.08, 1.30, 1.76, 2.39,
    2.46 on 24,400M diluted shares (the pack's TTM 7.91 = 1.30 + 1.76 + 2.39 + 2.46)."""
    entity(engine, NVDA, "NVIDIA CORP", "NVDA", fye="0125")
    dil = 24_400 * M
    q = [0.76, 1.08, 1.30, 1.76, 2.39, 2.46]
    fy26, fy27 = "2025-01-27", "2026-01-26"
    ytd = [
        (fy26, "2025-04-27", sum(q[:1]), "2025-05-28", "10-Q"),
        (fy26, "2025-07-27", sum(q[:2]), "2025-08-27", "10-Q"),
        (fy26, "2025-10-26", sum(q[:3]), "2025-11-19", "10-Q"),
        (fy26, "2026-01-25", sum(q[:4]), "2026-02-25", "10-K"),
        (fy27, "2026-04-26", q[4], "2026-05-27", "10-Q"),
        (fy27, "2026-07-26", q[4] + q[5], "2026-08-26", "10-Q"),
    ]
    for start, end, eps, filed, form in ytd:
        acc = fact(engine, NVDA, "NetIncomeLoss", start, end, eps * dil, filed, form)
        filing(engine, NVDA, acc, form, filed, end)
        fact(
            engine,
            NVDA,
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            start,
            end,
            eps * dil * 1.8,
            filed,
            form,
            acc=acc,
        )
        if end in ("2026-01-25", "2026-07-26"):
            for tag, v in (
                ("CashAndCashEquivalentsAtCarryingValue", 11_000 * M),
                ("ShortTermInvestments", 45_000 * M),
                ("LongTermDebtNoncurrent", 8_500 * M),
                ("StockholdersEquity", 120_000 * M),
            ):
                fact(engine, NVDA, tag, None, end, v, filed, form, acc=acc)
    fact(
        engine,
        NVDA,
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "2026-04-27",
        "2026-07-26",
        dil,
        "2026-08-26",
        "10-Q",
        unit="shares",
    )
    # the 2024 split: a pre-split cover count and a post-split close
    cover(engine, NVDA, "2024-05-17", "2024-05-29", 2_460_000_000)
    cover(engine, NVDA, "2026-08-20", "2026-08-26", 24_300_000_000)
    bars(
        engine,
        NVDA,
        "NVDA",
        [
            ("2024-06-07", 1208.88),
            ("2024-06-10", 121.79, 0.0, 10.0),
            ("2024-06-28", 125.83),
            ("2026-10-09", 229.28),
        ],
    )


def test_nvda_split_scales_the_cover_count_and_ttm_pe_is_29(dbs):
    engine, _ = dbs
    load_nvda(engine)
    k = Known(engine, NVDA, TODAY)
    pre = snapshot(k, "2024-06-07", fye="0125")
    post = snapshot(k, "2024-06-28", fye="0125")
    assert pre.cap.value == pytest.approx(2_460_000_000 * 1208.88)
    assert post.cap.value == pytest.approx(24_600_000_000 * 125.83)  # ×10 between cover and close
    assert "× splits 10 (2024-06-10 ×10)" in post.cap.text
    now = snapshot(k, "2026-10-09", fye="0125")
    assert now.twelve == "TTM to 2026-07-26"
    assert now.m("val_pe_ttm").value == pytest.approx(229.28 / 7.91)
    assert round(now.m("val_pe_ttm").value, 1) == 29.0
    assert "debt none" not in now.ev_text and "short-term investments" in now.ev_text


# --- INFQ: P/S, EV incomplete, shell period, recast ---


def load_infq(engine):
    """INFQ's TTM revenue 41.081M (pack): FY2025 31,108k − H1 2025 13,472k + H1 2026 23,445k;
    cover 225,357,052 (10-Q filed 2026-08-18); close $11.04. No cash or debt stored (the pack
    did not fetch them). FY2025 net income first filed −32.2M, recast to −66.9M."""
    entity(engine, INFQ, "Infleqtion, Inc.", "INFQ")
    k = 1000
    rev = "RevenueFromContractWithCustomerExcludingAssessedTax"
    for start, end, v, filed, form in (
        ("2025-01-01", "2025-03-31", 6_000, "2026-03-20", "10-K"),
        ("2025-01-01", "2025-06-30", 13_472, "2026-08-18", "10-Q"),
        ("2025-01-01", "2025-09-30", 21_000, "2026-03-20", "10-K"),
        ("2025-01-01", "2025-12-31", 31_108, "2026-03-20", "10-K"),
        ("2026-01-01", "2026-03-31", 11_000, "2026-05-15", "10-Q"),
        ("2026-01-01", "2026-06-30", 23_445, "2026-08-18", "10-Q"),
    ):
        acc = fact(engine, INFQ, rev, start, end, v * k, filed, form)
        filing(engine, INFQ, acc, form, filed)  # period = the newest end in its facts
    fact(engine, INFQ, "NetIncomeLoss", "2025-01-01", "2025-12-31", -32.2 * M, "2026-03-20")
    fact(
        engine, INFQ, "NetIncomeLoss", "2025-01-01", "2025-12-31", -66.9 * M, "2026-06-30", "10-K/A"
    )
    fact(
        engine,
        INFQ,
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "2025-01-01",
        "2025-12-31",
        200 * M,
        "2026-03-20",
        unit="shares",
    )
    fact(engine, INFQ, "StockholdersEquity", None, "2026-06-30", 900 * M, "2026-08-18", "10-Q")
    cover(engine, INFQ, "2026-08-14", "2026-08-18", 225_357_052)
    bars(engine, INFQ, "INFQ", [("2025-12-31", 10.0), ("2026-10-09", 11.04)])


def test_infq_ps_606_with_ev_incomplete_the_recast_and_the_shell_period(dbs):
    engine, _ = dbs
    load_infq(engine)
    confirm_stage(engine, INFQ, "growth")
    # as stored: the de-SPAC boundary (entity_link, D-M04-8) leaves the FY2025 10-K out (its
    # period ends before 2026-02-13), so no 12-month revenue exists yet (an open item)
    r = step.evaluate(engine, "INFQ", INFQ, "2026-10-09", TODAY, P, MF, with_peers=False)
    assert r.snap.m("val_ps").missing.startswith(
        "no 12-month revenue: 2 quarter(s) stored to 2026-06-30"
    )
    # the pack's arithmetic, with the FY2025 10-K read as the operating company's
    engine.execute("DELETE FROM entity_link WHERE successor_cik = ?", (INFQ,))
    r = step.evaluate(engine, "INFQ", INFQ, "2026-10-09", TODAY, P, MF, with_peers=False)
    s = r.snap
    assert s.cap.value == pytest.approx(225_357_052 * 11.04)
    assert s.m("val_ps").value == pytest.approx(225_357_052 * 11.04 / 41_081_000)
    assert round(s.m("val_ps").value, 1) == 60.6
    assert s.m("val_ev_sales").missing.startswith("EV incomplete (cash")
    assert r.route.measure == "val_ev_sales"
    assert r.headline.measure == "val_ps" and r.headline.value == pytest.approx(60.6, abs=0.05)
    rows = {o.signal: o for o in r.rows}
    assert "EV incomplete" in rows["valuation_multiple"].method
    # net income has FY2025 only, two quarters behind revenue's TTM: stale, not used (live
    # check 1, the AVGO case)
    assert rows["val_pe_ttm"].missing.startswith("12-month net income stale: the newest is "
                                                 "fiscal year to 2025-12-31")  # fmt: skip
    # the net-income recast note goes with the net income, which is stale here (not used)
    assert "series break: net income" not in rows["val_ps"].method
    shell = step.evaluate(engine, "INFQ", INFQ, "2025-12-31", TODAY, P, MF, with_peers=False)
    assert shell.snap.missing == "shell period (before 2026-02-13)"
    assert {o.signal: o for o in shell.rows}["val_ps"].missing == "shell period (before 2026-02-13)"


# --- MSTR, ETV ---


def test_mstr_mnav_headline_and_fair_value_pe(dbs):
    engine, _ = dbs
    entity(engine, MSTR, "Strategy Inc", "MSTR", sic="7372")
    acc = fact(
        engine, MSTR, "CryptoAssetFairValue", None, "2026-06-30", 60_000 * M, "2026-08-01", "10-Q"
    )
    fact(
        engine,
        MSTR,
        "NetIncomeLoss",
        "2025-07-01",
        "2026-06-30",
        5_000 * M,
        "2026-08-01",
        "10-K",
        acc=acc,
    )
    fact(
        engine,
        MSTR,
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "2025-07-01",
        "2026-06-30",
        280 * M,
        "2026-08-01",
        "10-K",
        unit="shares",
        acc=acc,
    )
    cover(engine, MSTR, "2026-07-30", "2026-08-01", 280 * M)
    bars(engine, MSTR, "MSTR", [("2026-10-09", 300.0)])
    r = step.evaluate(engine, "MSTR", MSTR, "2026-10-09", TODAY, P, MF, with_peers=False)
    assert r.route.measure == "mnav" and r.headline.value == pytest.approx(84_000 / 60_000)
    rows = {o.signal: o for o in r.rows}
    assert "crypto exposure" in rows["valuation_multiple"].method
    pe = rows["val_pe_ttm"]
    assert pe.text == "fair_value_earnings" and pe.value == pytest.approx(300 / (5000 / 280))


def test_fund_is_not_applicable_on_every_row(dbs):
    engine, _ = dbs
    entity(engine, ETV, "Eaton Vance Tax-Managed Buy-Write", "ETV", sic="6726")
    bars(engine, ETV, "ETV", [("2026-10-09", 14.0)])
    r = step.evaluate(engine, "ETV", ETV, "2026-10-09", TODAY, P, MF, with_peers=False)
    rows = {o.signal: o for o in r.rows}
    assert rows["valuation_multiple"].text == "not_applicable"
    assert rows["valuation_multiple"].info == ("MY", "PT", "ST")
    assert rows["val_pb"].missing == "not applicable (fund, D-M04-8)"


# --- edge cases on a synthetic annual filer ---


def annual_co(
    engine, cik, ticker, years, *, sic="3500", close=50.0, cover_n=100 * M, close_day="2026-10-09"
):
    """years: [{year, rev, oi, ni, eps?, dil?, gp?, da?, ocf?, capex?, cash?, debt?, eq?}] ($M);
    calendar fiscal years, each 10-K filed 15 February of the next year."""
    entity(engine, cik, f"{ticker} CO", ticker, sic=sic)
    for y in years:
        start, end, filed = f"{y['year']}-01-01", f"{y['year']}-12-31", f"{y['year'] + 1}-02-15"
        acc = fact(engine, cik, "Revenues", start, end, y["rev"] * M, filed)
        filing(engine, cik, acc, "10-K", filed, end)
        flows = (
            ("OperatingIncomeLoss", "oi"),
            ("NetIncomeLoss", "ni"),
            ("GrossProfit", "gp"),
            ("DepreciationDepletionAndAmortization", "da"),
            ("NetCashProvidedByUsedInOperatingActivities", "ocf"),
            ("PaymentsToAcquirePropertyPlantAndEquipment", "capex"),
        )
        for tag, key in flows:
            if y.get(key) is not None:
                fact(engine, cik, tag, start, end, y[key] * M, filed, acc=acc)
        if y.get("eps") is not None:
            fact(
                engine,
                cik,
                "EarningsPerShareDiluted",
                start,
                end,
                y["eps"],
                filed,
                unit="USD/shares",
                acc=acc,
            )
        fact(
            engine,
            cik,
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            start,
            end,
            y.get("dil", 100) * M,
            filed,
            unit="shares",
            acc=acc,
        )
        for tag, key in (
            ("CashAndCashEquivalentsAtCarryingValue", "cash"),
            ("LongTermDebtNoncurrent", "debt"),
            ("StockholdersEquity", "eq"),
        ):
            if y.get(key) is not None:
                fact(engine, cik, tag, None, end, y[key] * M, filed, acc=acc)
    last = years[-1]["year"] + 1
    cover(engine, cik, f"{last}-02-01", f"{last}-02-15", cover_n, "10-K")
    bars(engine, cik, ticker, [(close_day, close)])


def base(year, **kw):
    return {
        "year": year,
        "rev": 1000,
        "oi": 100,
        "ni": 80,
        "gp": 400,
        "da": 50,
        "ocf": 120,
        "capex": 40,
        "cash": 200,
        "debt": 300,
        "eq": 600,
    } | kw


def test_negative_equity_ev_at_or_below_zero_and_da_untagged(dbs):
    engine, _ = dbs
    a = "0000000101"
    annual_co(engine, a, "NEGQ", [base(2024), base(2025, eq=-50)])
    s = snapshot(Known(engine, a, TODAY), "2026-10-09")
    assert s.m("val_pb").text == "not_meaningful" and s.m("val_pb").value is None
    assert s.ev == pytest.approx(5000 * M + 300 * M - 200 * M)
    assert s.m("val_ev_ebitda").value == pytest.approx(5100 / 150)
    assert "debt none" not in s.ev_text and "preferred none tagged" in s.ev_text
    b = "0000000102"
    annual_co(engine, b, "CASHY", [base(2025, cash=9000, da=None)], close=50.0)
    s = snapshot(Known(engine, b, TODAY), "2026-10-09")
    assert s.ev < 0
    for key in ("val_ev_ebit", "val_ev_sales", "val_ev_gp"):
        assert s.m(key).text == "not_meaningful" and "EV ≤ 0" in s.m(key).detail
    assert s.m("val_ev_ebitda").missing.startswith("D&A untagged (checked: us-gaap:Depreciation")
    assert s.m("val_ps").value == pytest.approx(5.0)  # P/S does not need EV


def test_debt_tagged_earlier_but_not_now_is_ev_incomplete_never_tagged_is_missing(dbs):
    engine, _ = dbs
    a = "0000000103"
    annual_co(engine, a, "GAPD", [base(2024), base(2025, debt=None)])
    s = snapshot(Known(engine, a, TODAY), "2026-10-09")
    assert s.ev is None and s.ev_missing == "debt (tagged until 2024-12-31, not at 2025-12-31)"
    assert s.m("val_ev_sales").missing == f"EV incomplete ({s.ev_missing})"
    b = "0000000104"
    annual_co(engine, b, "NODEBT", [base(2024, debt=None), base(2025, debt=None)])
    s = snapshot(Known(engine, b, TODAY), "2026-10-09")
    # live check 1 (GFS has debt but no stored debt tag): untagged is missing, never zero
    assert s.ev is None and s.ev_missing == "debt untagged (no debt tag ever stored)"
    assert s.m("val_ps").value is not None  # P/S does not need EV


def test_dividend_yield_zero_with_a_full_year_missing_with_short_bars_split_scaled(dbs):
    engine, _ = dbs
    a = "0000000105"
    annual_co(engine, a, "NODIV", [base(2025)])
    bars(engine, a, "NODIV", [(d, 50.0) for d in weekdays("2025-09-01", "2026-10-09")])
    s = snapshot(Known(engine, a, TODAY), "2026-10-09")
    assert s.m("val_div_yield").value == 0.0 and "no dividend" in s.m("val_div_yield").detail
    b = "0000000106"
    annual_co(engine, b, "DIVY", [base(2025)])
    pays = {"2025-11-14": 1.0, "2026-02-13": 1.0, "2026-05-15": 0.5, "2026-08-14": 0.5}
    rows = [
        (d, 50.0 if d < "2026-03-02" else 25.0, pays.get(d, 0.0), 2.0 if d == "2026-03-02" else 1.0)
        for d in weekdays("2025-09-01", "2026-10-09")
    ]
    bars(engine, b, "DIVY", rows)
    s = snapshot(Known(engine, b, TODAY), "2026-10-09")
    # two $1.00 dividends before the 2:1 split count $0.50 each, then two $0.50: $2.00 ÷ $25
    assert s.m("val_div_yield").value == pytest.approx(2.0 / 25.0 * 100)
    assert "÷ 2 (split)" in s.m("val_div_yield").detail
    c = "0000000107"
    annual_co(engine, c, "SHORTB", [base(2025)])
    bars(engine, c, "SHORTB", [(d, 50.0) for d in weekdays("2026-07-01", "2026-10-09")])
    s = snapshot(Known(engine, c, TODAY), "2026-10-09")
    assert s.m("val_div_yield").missing.startswith("fewer than 12 months of stored bars")


# --- D32: non-tech synthetic companies ---


def test_one_loss_year_industrial_flags_and_the_owner_override_clears_it(dbs):
    """A steady industrial with one loss year (a 2020 shutdown): the EPS test flags it; the
    margin range (-2% to 12%) does not. D32: the rule's evidence is one memory company."""
    engine, _ = dbs
    a = "0000000201"
    ys = [base(y, oi=100 + 2 * (y - 2016), ni=70, eps=0.7) for y in range(2016, 2026)]
    ys[4] = base(2020, oi=-20, ni=-30, eps=-0.3)
    annual_co(engine, a, "INDU", ys, sic="3560")
    confirm_stage(engine, a, "mature")
    r = step.evaluate(engine, "INDU", a, "2026-10-09", TODAY, P, NO_MODELS, with_peers=False)
    assert r.flag.computed is True and "FY2019 +0.70 → FY2020 -0.30" in r.flag.eps_test
    assert "→ no" in r.flag.margin_test and r.route.measure == "val_ev_nebit"
    p = params.parse(
        {
            "version": "v1",
            "company": [{"ticker": "INDU", "cyclical": False, "reason": "2020 shutdown only"}],
        }
    )
    r = step.evaluate(engine, "INDU", a, "2026-10-09", TODAY, p, NO_MODELS, with_peers=False)
    assert r.flag.cyclical is False and r.route.measure == "val_pe_ttm"
    assert r.headline.value == pytest.approx(50.0 / 0.7)


def test_low_margin_cyclical_retailer_is_not_flagged_but_shows_both_tests(dbs):
    engine, _ = dbs
    a = "0000000202"
    oi = [20, 45, 60, 30, 15, 50, 55, 25, 35, 40]  # 1.5%-6% margins, always profitable
    annual_co(
        engine, a, "RETL", [base(2016 + i, oi=v, ni=v * 0.7) for i, v in enumerate(oi)], sic="5331"
    )
    r = step.evaluate(engine, "RETL", a, "2026-10-09", TODAY, P, NO_MODELS, with_peers=False)
    assert r.flag.cyclical is False and r.flag.computed is False
    assert "range 4.5 pp" in r.flag.margin_test and "sign change no" in r.flag.eps_test
    assert r.route.code == "stage_unconfirmed"
    rows = {o.signal: o for o in r.rows}
    assert rows["valuation_multiple"].text == "stage_unconfirmed"
    assert rows["valuation_multiple"].info == ("MY", "PT", "ST")
    assert rows["val_pe_ttm"].value == pytest.approx(5000 / 28)  # every row still shown (D32)


# --- routing and percentiles (pure) ---


@pytest.mark.parametrize(
    ("kw", "measure", "code"),
    [
        ({"stage": "growth"}, "val_ev_sales", None),
        ({"stage": "introduction"}, "val_ev_sales", None),
        ({"stage": "mature"}, "val_pe_ttm", None),
        ({"stage": "shake_out"}, "val_ev_nebit", None),
        ({"stage": "decline"}, "val_ev_ebit", None),
        ({"stage": None}, None, "stage_unconfirmed"),
        ({"stage": None, "cyclical": True}, "val_ev_nebit", None),
        ({"stage": "mature", "tag": "asset_treasury"}, "mnav", None),
        ({"stage": "mature", "tag": "fund"}, None, "not_applicable"),
        ({"stage": "mature", "tag": "financial"}, None, "not_applicable"),
        ({"stage": "mature", "override_headline": "val_pb"}, "val_pb", None),
    ],
)
def test_route_table(kw, measure, code):
    args = {"stage": None, "stage_text": "s", "cyclical": None, "tag": None} | kw
    r = route.choose(**args)
    assert (r.measure, r.code) == (measure, code)


def test_quarter_ends_and_midrank():
    assert pctile.quarter_ends("2025-02-10", "2025-12-31") == [
        "2025-03-31",
        "2025-06-30",
        "2025-09-30",
    ]
    assert pctile.midrank(5.0, [1.0, 5.0, 9.0, 10.0]) == pytest.approx(37.5)
    pk = pctile.peer(3.0, [("a", 1.0), ("b", 2.0)], 5, 4)
    assert pk.value is None and "2 priced peers with a value (needs 5)" in pk.text()
    assert pctile.peer(3.0, [], 5, 0).missing == "no confirmed SEC peers"
    pk = pctile.peer(3.0, [(c, float(i)) for i, c in enumerate("abcdef")], 5, 6)
    assert pk.value == pytest.approx(100 * 3.5 / 6) and "shown, not scored" in pk.text()


# --- own history, the pass, the script ---


def quarterly_co(
    engine,
    cik,
    ticker,
    *,
    first_year=2019,
    last_q=(2026, 2),
    rev_q=250.0,
    price=lambda d: 20.0 + (date.fromisoformat(d) - date(2019, 1, 1)).days / 50,
):
    """Synthetic calendar-year filer, entered as filed (LESSONS): 10-Qs carry year-to-date
    flows (3M, 6M, 9M), the 10-K the fiscal year; constant quarterly flows, balance sheet each
    quarter, weekday closes rising linearly from 2019 (README: generated in the tests)."""
    entity(engine, cik, f"{ticker} CO", ticker, sic="3550")
    flows = {
        "Revenues": rev_q,
        "OperatingIncomeLoss": rev_q * 0.12,
        "NetIncomeLoss": rev_q * 0.1,
        "GrossProfit": rev_q * 0.4,
        "DepreciationDepletionAndAmortization": rev_q * 0.05,
        "NetCashProvidedByUsedInOperatingActivities": rev_q * 0.15,
        "PaymentsToAcquirePropertyPlantAndEquipment": rev_q * 0.05,
    }
    ends = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
    y, q = first_year, 1
    while (y, q) <= last_q:
        end = f"{y}-{ends[q]}"
        form = "10-K" if q == 4 else "10-Q"
        filed = (date.fromisoformat(end) + timedelta(days=60 if q == 4 else 40)).isoformat()
        acc = f"{cik}-{filed[2:4]}-{filed[5:7]}{filed[8:10]}00"
        filing(engine, cik, acc, form, filed, end)
        for tag, v in flows.items():
            fact(engine, cik, tag, f"{y}-01-01", end, v * q * M, filed, form, acc=acc)
        fact(
            engine,
            cik,
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            f"{y}-01-01",
            end,
            100 * M,
            filed,
            form,
            unit="shares",
            acc=acc,
        )
        for tag, v in (
            ("CashAndCashEquivalentsAtCarryingValue", 300),
            ("LongTermDebtNoncurrent", 500),
            ("StockholdersEquity", 2000),
        ):
            fact(engine, cik, tag, None, end, v * M, filed, form, acc=acc)
        cover(
            engine,
            cik,
            (date.fromisoformat(filed) - timedelta(days=5)).isoformat(),
            filed,
            100 * M,
            form,
        )
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)
    bars(engine, cik, ticker, [(d, price(d)) for d in weekdays("2019-01-01", "2026-10-12")])


def test_own_history_percentile_on_first_filed_quarter_ends(dbs):
    engine, _ = dbs
    a = "0000000301"
    quarterly_co(engine, a, "HIST")
    confirm_stage(engine, a, "growth")
    r = step.evaluate(engine, "HIST", a, "2026-10-09", TODAY, P, NO_MODELS, with_peers=False)
    assert r.snap.twelve == "TTM to 2026-06-30"
    assert r.snap.m("val_ps").value == pytest.approx(100 * r.snap.close.value / 1000)
    h = r.pctiles["val_ev_sales"]
    # quarter-ends from 2019-12-31 (first TTM filed 2020-02-29 → 2020-03-31 the first point)
    assert h.value == 100.0 and h.n >= 20  # the price only rose: above every quarter-end
    assert r.headline.measure == "val_ev_sales"
    rows = {o.signal: o for o in r.rows}
    assert rows["valuation_pctile"].value == pytest.approx(round(h.value, 1))
    assert f"own pctile {h.value:.0f} of {h.n} quarters" in rows["val_ev_sales"].method
    assert rows["valuation_multiple"].info == ("ST",)
    # quarter-ends before 20 points exist: missing with the count
    early = step.evaluate(engine, "HIST", a, "2022-06-30", TODAY, P, NO_MODELS, with_peers=False)
    assert early.pctiles["val_ev_sales"].missing.endswith("/20 quarters")


def test_value_trap_risk_needs_a_low_percentile_and_a_gate_fail_or_damage(dbs):
    engine, _ = dbs
    a = "0000000302"
    quarterly_co(
        engine,
        a,
        "FALL",
        price=lambda d: 200.0 - (date.fromisoformat(d) - date(2019, 1, 1)).days / 20,
    )
    confirm_stage(engine, a, "growth")
    r = step.evaluate(engine, "FALL", a, "2026-10-09", TODAY, P, NO_MODELS, with_peers=False)
    assert r.headline_pctile.value < 20 and r.trap == ""
    m04_row(engine, a, "cvd_state", "STRUCTURAL_DECLINE")
    r = step.evaluate(engine, "FALL", a, "2026-10-09", TODAY, P, NO_MODELS, with_peers=False)
    assert r.trap.startswith("value-trap risk") and "CvD STRUCTURAL_DECLINE" in r.trap
    assert "value-trap risk" in {o.signal: o for o in r.rows}["valuation_pctile"].method


def rows_of(engine, cik, signal=None, tf="MY"):
    sql = "SELECT * FROM signal WHERE cik = ? AND module_id = 'M08' AND timeframe = ?"
    args = [cik, tf]
    if signal:
        sql += " AND signal = ?"
        args.append(signal)
    return engine.execute(sql + " ORDER BY signal, as_of", args).fetchall()


def test_pass_writes_one_row_set_per_completed_week_and_a_rerun_updates_it(dbs):
    engine, _ = dbs
    a = "0000000303"
    quarterly_co(engine, a, "PASS")
    confirm_stage(engine, a, "mature")
    vp = step.valuation_pass(engine, {"PASS": a, "SPY": ""}, NOW, mf=NO_MODELS)
    assert vp.week == "2026-10-09" and not vp.errors
    got = rows_of(engine, a)
    assert {r["signal"] for r in got} == {
        *STANDARD_KEYS, "val_pe_fwd", "peg", "est_revision", "valuation_multiple",
        "valuation_pctile",
    }  # fmt: skip
    assert {r["as_of"] for r in got} == {"2026-10-09"} and all(r["cik"] == a for r in got)
    vm = rows_of(engine, a, "valuation_multiple")[0]
    assert vm["value"] == pytest.approx(r_pe := vm["value"]) and r_pe > 0
    assert vm["evidence_grade"] == "A" and "M08 v1" in vm["method"]
    st = rows_of(engine, a, "valuation_multiple", "ST")[0]
    assert st["method"].endswith("info (weight 0)")
    n = len(rows_of(engine, a))
    step.valuation_pass(engine, {"PASS": a}, NOW, mf=NO_MODELS)
    assert len(rows_of(engine, a)) == n  # same week: same rows
    # a filing after the week's close adds a row set at the newest close
    filing(engine, a, "0000000303-26-999999", "10-Q", "2026-10-12", "2026-09-30")
    vp = step.valuation_pass(engine, {"PASS": a}, NOW, mf=NO_MODELS)
    assert [r.as_of for r in vp.results["PASS"]] == ["2026-10-09", "2026-10-12"]
    assert any("headlines: val_pe_ttm" in x for x in step.summary_lines(vp))


def test_missing_from_facts_replaces_a_stored_value_a_stale_price_store_keeps_it(dbs):
    engine, _ = dbs
    a = "0000000304"
    quarterly_co(engine, a, "KEEP")
    step.valuation_pass(engine, {"KEEP": a}, NOW, mf=NO_MODELS)
    # live check 2: a rule (or the facts) now giving missing replaces the old value
    engine.execute("DELETE FROM fact WHERE cik = ? AND tag = 'Revenues'", (a,))
    vp = step.valuation_pass(engine, {"KEEP": a}, NOW, mf=NO_MODELS)
    assert vp.kept == 0
    assert rows_of(engine, a, "val_ps")[0]["value"] is None
    # a stale price store moves the week back: the stored week's values stay (D-M09-13)
    pb = {r["as_of"]: r["value"] for r in rows_of(engine, a, "val_pb")}
    assert pb.get("2026-10-09") is not None
    engine.execute("DELETE FROM price_bar WHERE symbol = 'KEEP' AND date >= '2026-10-01'")
    step.valuation_pass(engine, {"KEEP": a}, NOW, mf=NO_MODELS)
    after = {r["as_of"]: r["value"] for r in rows_of(engine, a, "val_pb")}
    assert after["2026-10-09"] == pb["2026-10-09"]


def test_refresh_runs_m08_after_m07_and_before_m09():
    src = (ROOT / "scripts" / "run_refresh.py").read_text(encoding="utf-8")
    m07 = src.index("prices += managers_local_step(engine, report)")
    m08 = src.index("prices += valuation_local_step(engine, report)")
    m09 = src.index("prices += technicals_local_step(engine, report, corpus)")
    assert m07 < m08 < m09


def test_script_value_on_an_injected_db(dbs, tmp_path, capsys):
    engine, _ = dbs
    rv = load_script("run_valuation")
    a = "0000000305"
    quarterly_co(engine, a, "SCRP")
    load_mu(engine)
    log = rv.Log(tmp_path / "logs" / "v.txt")
    args = argparse.Namespace(
        subcommand="value", no_sec=True, tickers=None, companies={"SCRP": a, "MU": MU}
    )
    assert rv.run_value(args, log, tmp_path, engine=engine, now=NOW) == 0
    log.close()
    text = (tmp_path / "logs" / "v.txt").read_text(encoding="utf-8")
    assert "=== Summary" in text and "SEC requests: 0 · API requests: 0" in text
    assert "MU 2024-10-04: pack 146.1×" in text and "engine P/E TTM (GAAP) 146.8×" in text
    assert "SCRP" in text and "Missing rows" in text
    out = capsys.readouterr().out
    assert "=== Summary" in out


def test_script_list_and_unbuilt_subcommand(capsys):
    rv = load_script("run_valuation")
    assert rv._main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "estimates" in out and "not built" not in out  # every subcommand built (Part 2)
    assert rv._main([]) == 2  # no subcommand: the table, exit 2 (never a real run, LESSONS)


# --- the Valuation tab and the Overview line (D-UI-36) ---


def _app(tmp_path, monkeypatch, fill, tickers):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui import app as app_mod
    from engine.ui.settings import UiSettings

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(app_mod, "datetime", Clock)
    data = tmp_path / "data"
    engine = open_db("engine", data)
    corpus = open_db("corpus", data)
    fill(engine)
    engine.commit()
    engine.close()
    corpus.close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text(
        f"[watchlist]\ntickers = {list(tickers)!r}\n".replace("'", '"'), encoding="utf-8"
    )
    return TestClient(app_mod.create_app(UiSettings(data_dir=data, watchlist=watch)))


def test_valuation_tab_and_overview_line(tmp_path, monkeypatch):
    a = "0000000401"

    def fill(engine):
        quarterly_co(engine, a, "TABX")
        confirm_stage(engine, a, "growth")
        load_mu(engine)
        step.valuation_pass(engine, {"TABX": a}, NOW, mf=NO_MODELS)

    client = _app(tmp_path, monkeypatch, fill, ["TABX", "MU"])
    html = client.get("/c/TABX?tab=valuation").text
    assert "built-in method" not in html and "object at 0x" not in html
    assert "Valuation (M08) — TABX" in html and "EV/Sales" in html
    assert "Standard measures (every company, D32)" in html
    assert "own pctile 100 of" in html and "(2026-10-09)" in html  # the stored week
    assert "Headline at the last 8 quarter-ends" in html
    ov = client.get("/c/TABX?tab=overview").text
    assert "Valuation (M08)" in ov and "week to 2026-10-09" in ov and "own pctile 100" in ov
    mu = client.get("/c/MU?tab=valuation").text
    assert "cyclical flag: cyclical" in mu and "NEP window FY2020–FY2022" in mu
    assert "missing: fewer than 12 months of stored bars" in mu and "not stored yet" in mu
    assert "Valuation (M08)" not in client.get("/c/MU?tab=overview").text  # nothing stored yet
