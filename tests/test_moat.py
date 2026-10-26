# ruff: noqa: E501  (fixture rows)
"""M06 Part 1: the quant leg, the owner verdict, the gate, the setup batch, the refresh hook,
the owner script and the "Moat (M06)" section and setup page (docs/M06_MOAT.md Part 1;
D-M06-1…8, D-M06-9…).

Fixtures are entered in the tests (sources per case; "illus." = illustrative, as in the
brief): MSFT FY2025–26 ROIC inputs (the pack's arithmetic, S-new-M06-17), INTC 2021–25
operating income (real; earlier years illustrative), MU FY2023 / FY2026 gross margin (the
M04 Part 1b trimmed companyfacts plus the FY2026 10-K figure), a 6-year company, MSTR / ETV
(asset_treasury, fund), an invested-capital ≤ 0 year, and the D32 non-tech case (a
Boeing-like industrial with losses, then one good year)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine.financials import models as models_mod
from engine.moat import gate as gate_mod
from engine.moat import params as params_mod
from engine.moat import quant as quant_mod
from engine.moat import step
from engine.moat import verdict as verdict_mod
from tests.test_financials_1b import AS_OF, INTC, MSFT, MU, M, entity, fact, mu
from tests.test_technicals import load_script

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
P = params_mod.Params()
NO_MODELS = models_mod.ModelFile("none", ())
B = 1_000_000_000
PERS, CYC, SHORT, BUYB, BA_LIKE, NEAR, BANK = (
    "0009600001", "0009600002", "0009600003", "0009600004", "0009600005", "0009600006",
    "0009600007",
)  # fmt: skip
MSTR, ETV = "0001050446", "0001270523"


def synth(engine, cik, ticker, roics, *, start=2015, gm=None, sic=None, equity=None, rd=None):
    """len(roics) + 1 fiscal years (Dec year end); IC = equity (cash 0, no debt), tax 0, so
    ROIC = OI ÷ average equity; the first year is the opening balance. `roics` in percent."""
    entity(engine, cik, f"Synthetic {ticker}", "1231", ticker)
    if sic:
        engine.execute("UPDATE entity SET sic = ? WHERE cik = ?", (sic, cik))
    vals = [roics[0], *roics]
    for i, r in enumerate(vals):
        y = start + i
        end, begin, filed = f"{y}-12-31", f"{y}-01-01", f"{y + 1}-02-15"
        eq = (equity or {}).get(y, 1000)
        fact(engine, cik, "StockholdersEquity", None, end, eq * M, filed=filed)
        fact(engine, cik, "CashAndCashEquivalentsAtCarryingValue", None, end, 0, filed=filed)
        oi = r * 10 * M  # r% of an invested capital of 1,000
        fact(engine, cik, "OperatingIncomeLoss", begin, end, oi, filed=filed)
        fact(
            engine,
            cik,
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            begin,
            end,
            oi,
            filed=filed,
        )
        fact(engine, cik, "IncomeTaxExpenseBenefit", begin, end, 0, filed=filed)
        fact(engine, cik, "Revenues", begin, end, 2000 * M, filed=filed)
        if gm is not None:
            fact(engine, cik, "GrossProfit", begin, end, gm * 20 * M, filed=filed)
        if rd is not None:
            fact(engine, cik, "ResearchAndDevelopmentExpense", begin, end, rd * 20 * M, filed=filed)


def q_of(engine, cik, ticker, mf=NO_MODELS, p=P):
    return quant_mod.compute(engine, cik, ticker, AS_OF, p, mf, peers=False)


def rows(engine, cik, signal, tf="MY"):
    return engine.execute(
        "SELECT * FROM signal WHERE cik = ? AND module_id = 'M06' AND signal = ? AND timeframe = ? "
        "ORDER BY as_of", (cik, signal, tf)).fetchall()  # fmt: skip


def models(*entries):
    return models_mod.parse({"company": [
        {"ticker": t, "tag": tag, "reason": "r", "source": "s", **({"before": b} if b else {})}
        for t, tag, b in entries]})  # fmt: skip


# --- config --------------------------------------------------------------------------------------


def test_repo_config_equals_the_built_in_defaults(tmp_path):
    assert params_mod.load(ROOT / "config" / "moat.toml") == params_mod.Params()
    bad = tmp_path / "m.toml"
    bad.write_text('version = "v1"\n[quant]\nhurdle = 8\n', encoding="utf-8")
    p, err = params_mod.load_safe(bad)
    assert p == params_mod.Params() and "share between 0 and 1" in err
    bad.write_text('version = "v1"\n[quant]\nmin_years = 12\n', encoding="utf-8")
    assert "cannot exceed" in params_mod.load_safe(bad)[1]


# --- rule 1: the quant leg ------------------------------------------------------------------------


def test_classify_rules_and_the_last_three_years_guard():
    # MU-like: 7/10 above 8%, median 15%, a recent year above → through_cycle
    r = quant_mod.classify([0.30, 0.05, 0.12, 0.35, 0.18, -0.03, 0.09, 0.25, 0.04, 0.40], 0.08, P)
    assert (r.state, r.above, r.n, round(r.median, 3), r.recent_above) == (
        "through_cycle",
        7,
        10,
        0.15,
        2,
    )
    assert (
        quant_mod.classify([0.2] * 8 + [0.05, 0.05], 0.08, P).state == "persistent"
    )  # 80% exactly
    assert quant_mod.classify([0.2] * 6, 0.08, P).state == "short_history"
    # INTC-shaped: median above the hurdle, but none of the last 3 years → weak (the guard)
    intc_like = [0.11, 0.152, 0.198, 0.187, 0.201, 0.165, 0.0198, 0.0008, -0.117, -0.022]
    assert quant_mod.classify(intc_like, 0.08, P).state == "weak"
    unguarded = params_mod.Params(recent_years=10)
    assert quant_mod.classify(intc_like, 0.08, unguarded).state == "through_cycle"


def test_msft_fy2026_roic_with_current_debt(dbs):
    """Pack arithmetic (S-new-M06-17): OI 155.237, tax 32.185 ÷ pretax 165.934, IC 289.066 →
    396.611 ($B) without current debt = 36.5%; the engine adds `debt_current` → 35.9%. The
    split of IC (all in equity) and the FY2026 current debt (8.42) are illus.; FY2025 current
    debt 2.999 as reported."""
    engine, _ = dbs
    entity(engine, MSFT, "Microsoft", "0630", "MSFT")
    for end, eq, cd in (("2025-06-30", 289.066, 2.999), ("2026-06-30", 396.611, 8.42)):
        fact(engine, MSFT, "StockholdersEquity", None, end, eq * B, filed=f"{end[:4]}-07-30")
        fact(
            engine,
            MSFT,
            "CashAndCashEquivalentsAtCarryingValue",
            None,
            end,
            0,
            filed=f"{end[:4]}-07-30",
        )
        fact(engine, MSFT, "DebtCurrent", None, end, cd * B, filed=f"{end[:4]}-07-30")
    for start, end, oi, pre, tax in (
        ("2024-07-01", "2025-06-30", 128.528, 123.0, 21.8),
        ("2025-07-01", "2026-06-30", 155.237, 165.934, 32.185),
    ):
        fact(engine, MSFT, "OperatingIncomeLoss", start, end, oi * B, filed=f"{end[:4]}-07-30")
        fact(
            engine,
            MSFT,
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            start,
            end,
            pre * B,
            filed=f"{end[:4]}-07-30",
        )
        fact(engine, MSFT, "IncomeTaxExpenseBenefit", start, end, tax * B, filed=f"{end[:4]}-07-30")
    q = q_of(engine, MSFT, "MSFT")
    fy26 = q.years[-1]
    assert fy26.label == "FY2026" and round(fy26.roic, 3) == 0.359
    nopat = 155.237 * (1 - 32.185 / 165.934)
    assert round(nopat / ((289.066 + 396.611) / 2), 3) == 0.365  # without current debt
    assert (
        q.state == "short_history"
        and q.years[0].roic_text == "missing: no opening invested capital"
    )
    assert "excludes leases" in q.method() and "consolidated only" in q.method()


def intc_like(engine):
    """INTC 2021–25 operating income real ($B: 19.456, 2.334, 0.093, −11.678, −2.214);
    2015–20 operating income, IC 100 and the 15% tax illus.; GM 2018 61.7% and 2024 32.7%
    real (S-new-M06-17), other years illus."""
    entity(engine, INTC, "Intel Corp", "1231", "INTC")
    oi = {2015: 14.0, 2016: 12.9, 2017: 17.9, 2018: 23.3, 2019: 22.0, 2020: 23.7,
          2021: 19.456, 2022: 2.334, 2023: 0.093, 2024: -11.678, 2025: -2.214}  # fmt: skip
    gm = {2018: 61.7, 2024: 32.7}
    for y, o in oi.items():
        end, begin, filed = f"{y}-12-31", f"{y}-01-01", f"{y + 1}-01-30"
        fact(engine, INTC, "StockholdersEquity", None, end, 100 * B, filed=filed)
        fact(engine, INTC, "CashAndCashEquivalentsAtCarryingValue", None, end, 0, filed=filed)
        fact(engine, INTC, "OperatingIncomeLoss", begin, end, o * B, filed=filed)
        fact(
            engine,
            INTC,
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            begin,
            end,
            o * B,
            filed=filed,
        )
        fact(engine, INTC, "IncomeTaxExpenseBenefit", begin, end, max(o, 0) * 0.15 * B, filed=filed)
        fact(engine, INTC, "Revenues", begin, end, 60 * B, filed=filed)
        fact(engine, INTC, "GrossProfit", begin, end, gm.get(y, 50.0) * 0.6 * B, filed=filed)


def test_intc_reads_weak_only_through_the_guard(dbs):
    engine, _ = dbs
    intc_like(engine)
    q = q_of(engine, INTC, "INTC")
    assert [y.label for y in q.years] == [f"FY{y}" for y in range(2016, 2026)]
    assert q.state == "weak" and q.reading.above == 6 and q.reading.recent_above == 0
    assert q.reading.median > 0.08  # the median alone would say through_cycle
    gms = {y.label: round(y.gm, 1) for y in q.years}
    assert gms["FY2018"] == 61.7 and gms["FY2024"] == 32.7
    assert "pretax ≤ 0: NOPAT = operating income" in q.years[-2].roic_text  # losses kept negative
    assert verdict_mod.propose(q).verdict == "NONE"


def test_mu_gm_trough_and_peak_shown_never_the_latest_year_alone(dbs):
    """MU FY2023 GM −9.1% (GP −1.416 ÷ rev 15.540, M04 fixture); FY2026 80.7% (GP 107.504 ÷
    rev 133.188 $B, 10-K 0000723125-26-000023, S300). No operating income in the fixture →
    ROIC missing, the leg missing, GM still shown (D32)."""
    engine, _ = dbs
    mu(engine)
    fact(engine, MU, "GrossProfit", "2025-08-29", "2026-08-27", 107.504 * B, filed="2026-10-03")
    q = q_of(engine, MU, "MU")
    gms = {y.label: y.gm for y in q.years}
    assert round(gms["FY2023"], 1) == -9.1 and round(gms["FY2026"], 1) == 80.7
    assert q.state is None and q.missing == "no fiscal-year operating income stored"
    assert all(y.roic is None for y in q.years) and q.gm_median is not None


def test_persistent_through_cycle_and_hurdle_band(dbs):
    engine, _ = dbs
    synth(engine, PERS, "PRS", [30, 28, 31, 25, 33, 35, 36, 34, 35, 36], gm=68)
    q = q_of(engine, PERS, "PRS")
    assert q.state == "persistent" and q.value == 1.0 and len(q.sources) == 10
    assert q.as_of == "2026-02-15" and q.gm_median == pytest.approx(68.0)
    assert verdict_mod.propose(q).verdict == "NARROW candidate"
    synth(engine, CYC, "CYC", [30, 5, 12, 35, 18, -3, 9, 25, 4, 40])
    q = q_of(engine, CYC, "CYC")
    assert q.state == "through_cycle" and q.value == 0.7
    assert "D32: through_cycle was built on MU's memory cycle" in q.method()
    # TSLA / GFS-like names inside ±2 pp can flip on the hurdle (D-M06-1)
    synth(engine, NEAR, "NER", [8.1, 9.5, 7.0, 8.3, 6.5, 9.0, 7.9, 8.6, 10.5, 8.1])
    q = q_of(engine, NEAR, "NER")
    sens = {round(h, 2): s.state for h, s in q.sensitivity}
    assert q.state == "through_cycle" and sens == {0.06: "persistent", 0.10: "weak"}
    assert "within ±2 pp of the hurdle" in q.method() and "at 6%: persistent" in q.method()


def test_six_year_company_is_short_history_and_unrated(dbs):
    engine, _ = dbs
    synth(engine, SHORT, "YNG", [20, 22, 25, 30, 35, 40], start=2019)
    q = q_of(engine, SHORT, "YNG")
    assert q.state == "short_history" and q.reading.n == 6 and q.value == 1.0
    assert verdict_mod.propose(q).verdict == "UNRATED"


def test_invested_capital_at_or_below_zero_is_left_out_or_not_meaningful(dbs):
    engine, _ = dbs
    synth(engine, BUYB, "BUY", [20] * 10, equity={2020: -1500})  # IC ≤ 0 averages in 2020, 2021
    q = q_of(engine, BUYB, "BUY")
    assert q.nm_years == ["FY2020", "FY2021"] and q.reading.n == 8 and q.state == "persistent"
    assert "short window: 8 computable years" in q.method() and "n/m (IC ≤ 0)" in q.method()
    engine.execute(
        "UPDATE fact SET value = -5000000000 WHERE cik = ? AND tag = 'StockholdersEquity' AND period_end >= '2019-12-31'",
        (BUYB,),
    )
    q = q_of(engine, BUYB, "BUY")
    assert q.state == "not_meaningful" and q.value is None
    assert verdict_mod.propose(q).verdict == "UNRATED"


def test_ba_like_industrial_losses_then_one_good_year_is_weak_d32(dbs):
    """D32 non-tech case (SIC 3721, aircraft): above the hurdle 2016–18 (illus.), losses
    2019–24 (as Boeing's), 13.5% in 2025 (the engine's BA FY2025 figure). One recent good
    year passes the guard, the median does not: weak, not through_cycle."""
    engine, _ = dbs
    synth(engine, BA_LIKE, "BAL", [14, 16, 18, -2, -12, -4, -5, -8, -10, 13.5], sic="3721", gm=12)
    q = q_of(engine, BA_LIKE, "BAL")
    assert q.state == "weak" and q.reading.above == 4 and q.reading.recent_above == 1
    assert q.reading.median < 0.08 and "SIC 3721" in q.method()


def test_tags_make_the_leg_not_applicable_but_keep_the_standard_rows(dbs):
    engine, _ = dbs
    synth(engine, MSTR, "MSTR", [5, 6, 7, 8, 9, 10, 11, 12, 13, 14])
    synth(engine, ETV, "ETV", [5, 6, 7, 8, 9, 10, 11, 12, 13, 14])
    mf = models(("MSTR", "asset_treasury", None), ("ETV", "fund", None))
    q = q_of(engine, MSTR, "MSTR", mf)
    assert q.state == "not_applicable" and q.headline() == "asset vehicle: ROIC shown, not rated"
    assert len(q.years) == 10 and q.years[-1].roic is not None  # ROIC shown (D32)
    assert verdict_mod.propose(q).verdict == "N_A"
    assert q_of(engine, ETV, "ETV", mf).state == "not_applicable"
    # an untagged financial (SIC 6022, a bank) routes N_A through models.route
    synth(engine, BANK, "BNK", [12] * 10, sic="6022")
    q = q_of(engine, BANK, "BNK")
    assert q.state == "not_applicable" and q.headline().startswith(
        "financial: book ROIC meaningless"
    )


def test_spac_shell_years_left_out_and_rd_heavy_label(dbs):
    engine, _ = dbs
    synth(engine, SHORT, "YNG", [1, 1, 1, 1, 1, 20, 22, 25, 30, 35], rd=25)
    mf = models(("YNG", "spac_shell", "2021-01-01"))
    q = q_of(engine, SHORT, "YNG", mf)
    assert [y.excluded for y in q.years[:5]] == ["spac_shell period, not rated"] * 5
    assert q.state == "short_history" and q.reading.n == 5
    assert any(lbl.startswith("R&D-heavy (R&D 25% of FY2025 revenue") for lbl in q.labels)


# --- rules 2 and 4: verdict and gate --------------------------------------------------------------


def entry(**kw):
    base = dict(verdict="NARROW", sources=("switching_costs",), band="5to10", reason="r")
    return verdict_mod.Entry(**(base | kw))


def test_entry_validation():
    with pytest.raises(verdict_mod.VerdictError, match="reads NARROW, not WIDE"):
        verdict_mod.validate(entry(verdict="WIDE"))
    with pytest.raises(verdict_mod.VerdictError, match="A reason is required"):
        verdict_mod.validate(entry(reason=" "))
    with pytest.raises(verdict_mod.VerdictError, match="at least one moat source"):
        verdict_mod.validate(entry(sources=()))
    with pytest.raises(verdict_mod.VerdictError, match="UNRATED takes no catch-up band"):
        verdict_mod.validate(entry(verdict="UNRATED"))
    with pytest.raises(verdict_mod.VerdictError, match="needs its reason"):
        verdict_mod.validate(entry(override="met"))
    with pytest.raises(verdict_mod.VerdictError, match="N_A comes from the model tags"):
        verdict_mod.validate(entry(verdict="N_A"))
    with pytest.raises(verdict_mod.VerdictError, match="accession"):
        verdict_mod.validate(entry(quote="a long enough quote here"))
    e = verdict_mod.validate(entry(verdict="none", band="le3", sources=()))
    assert e.verdict == "NONE"
    assert verdict_mod.validate(
        entry(sources=("network", "switching_costs", "network"))
    ).sources == ("network", "switching_costs")


def gate_row(verdict, band=None, override=None, why="", as_of="2026-10-12"):
    return {"verdict": verdict, "band": band, "override": override, "override_reason": why,
            "as_of": as_of}  # fmt: skip


@pytest.mark.parametrize(("verdict", "band", "state"), [
    ("WIDE", "gt10", "met"),
    ("NARROW", "5to10", "met"),
    ("NARROW", "3to5", "not_met"),  # A3: band low 3 < the 5-year horizon
    ("NONE", "le3", "not_met"),
    ("UNRATED", None, "unrated"),
])  # fmt: skip
def test_gate_states(verdict, band, state):
    assert gate_mod.compute(gate_row(verdict, band), "persistent", 5).state == state


def test_gate_na_missing_override_and_stale():
    assert gate_mod.compute(None, "not_applicable", 5).state == "not_applicable"
    g = gate_mod.compute(None, "persistent", 5)
    assert g.state is None and g.why == "no owner verdict yet"
    g = gate_mod.compute(
        gate_row("UNRATED", override="met", why="young; S-1 shows lock-in"), "short_history", 5
    )
    assert (g.state, g.computed, g.override) == ("met", "unrated", True)
    assert "override met by the owner: young; S-1 shows lock-in" in g.why
    g = gate_mod.compute(
        gate_row("NARROW", "5to10", as_of="2026-01-10"), "persistent", 5, "2026-07-30"
    )
    assert g.stale == "stale since 2026-07-30" and g.state == "met"


def doc(corpus, cik, acc, text, filename="k.htm"):
    corpus.execute(
        "INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, fetched_at) "
        "VALUES (?, ?, ?, '10-K', ?, ?, 'h', 'now')", (acc, cik, filename, f"u/{acc}/{filename}", text))  # fmt: skip


def test_enter_verified_quote_lifts_to_a_and_unverified_is_stored_rejected(dbs):
    engine, corpus = dbs
    synth(engine, PERS, "PRS", [30] * 10)
    q = q_of(engine, PERS, "PRS")
    acc = "0009600001-26-000001"
    doc(corpus, PERS, acc, "Customers rely on our platform. Switching to another vendor requires "
        "retraining every engineer and rewriting years of code.")  # fmt: skip
    vid = verdict_mod.enter(
        engine,
        corpus,
        PERS,
        entry(
            accession=acc, quote="Switching to another vendor requires retraining every engineer"
        ),
        q,
        "owner",
        NOW,
    )
    v = verdict_mod.current(engine, PERS)
    assert v["verdict_id"] == vid and v["grade"] == "A" and v["quote_status"] == "verified"
    assert v["passage_ref"] == f"{acc}/k.htm" and v["quant_class"] == "persistent"
    with pytest.raises(verdict_mod.VerdictRejected, match="stored as rejected"):
        verdict_mod.enter(
            engine,
            corpus,
            PERS,
            entry(
                verdict="WIDE",
                band="gt10",
                accession=acc,
                quote="a sentence that is not in the filing",
            ),
            q,
            "owner",
            NOW,
        )
    assert (
        verdict_mod.current(engine, PERS)["verdict_id"] == vid
    )  # the rejected entry never applies
    hist = verdict_mod.history(engine, PERS)
    assert [h["status"] for h in hist] == ["rejected", "active"]
    # another company's filing does not verify (the document must be the company's own)
    with pytest.raises(verdict_mod.VerdictRejected):
        verdict_mod.enter(
            engine,
            corpus,
            CYC,
            entry(
                accession=acc,
                quote="Switching to another vendor requires retraining every engineer",
            ),
            q,
            "owner",
            NOW,
        )


def test_entry_refused_for_a_not_applicable_name(dbs):
    engine, corpus = dbs
    synth(engine, MSTR, "MSTR", [5] * 10)
    q = q_of(engine, MSTR, "MSTR", models(("MSTR", "asset_treasury", None)))
    with pytest.raises(verdict_mod.VerdictError, match="edit the model tag file"):
        verdict_mod.enter(engine, corpus, MSTR, entry(), q, "owner", NOW)


# --- the pass: rows, setup batch, re-open ---------------------------------------------------------


def test_pass_writes_three_rows_and_the_setup_batch(dbs):
    engine, corpus = dbs
    synth(engine, PERS, "PRS", [30] * 10)
    synth(engine, SHORT, "YNG", [20, 22, 25, 30, 35, 40], start=2019)
    synth(engine, MSTR, "MSTR", [5] * 10)
    comps = {"PRS": PERS, "YNG": SHORT, "MSTR": MSTR}
    mf = models(("MSTR", "asset_treasury", None))
    mp = step.moat_pass(engine, comps, NOW, p=P, mf=mf)
    assert not mp.errors and mp.written == 27 and mp.queued == 2  # MSTR (N_A) gets no item
    q = rows(engine, PERS, "moat_quant")
    assert [(r["value_text"], r["value"], r["evidence_grade"], r["as_of"]) for r in q] == [
        ("persistent", 1.0, "A", "2026-02-15")
    ]
    assert q[0]["source_ref"].endswith("+9")
    assert "info (weight 0)" in rows(engine, PERS, "moat_quant", "ST")[0]["method"]
    v = rows(engine, PERS, "moat_verdict")[0]
    assert v["value_text"] is None and v["method"].startswith(
        "missing: no owner verdict yet; engine proposal: NARROW candidate"
    )
    g = rows(engine, PERS, "moat_gate")[0]
    assert g["method"].startswith("missing: no owner verdict yet")
    assert "info (weight 0)" in rows(engine, PERS, "moat_gate", "PT")[0]["method"]
    na = rows(engine, MSTR, "moat_verdict")[0]
    assert (na["value_text"], na["evidence_grade"]) == ("N_A", "B")
    assert rows(engine, MSTR, "moat_gate")[0]["value_text"] == "not_applicable"
    assert not rows(engine, PERS, "challenger_max_rung")  # Part 2
    items = engine.execute("SELECT module_id, kind, cik FROM review_queue ORDER BY cik").fetchall()
    assert [tuple(i) for i in items] == [
        ("M06", "m06_verdict", PERS),
        ("M06", "m06_verdict", SHORT),
    ]
    # a rerun on unchanged facts updates in place and queues nothing new
    n = engine.execute("SELECT count(*) FROM signal WHERE module_id = 'M06'").fetchone()[0]
    mp = step.moat_pass(engine, comps, NOW, p=P, mf=mf)
    assert (
        mp.queued == 0
        and engine.execute("SELECT count(*) FROM signal WHERE module_id = 'M06'").fetchone()[0] == n
    )
    lines = step.summary_lines(mp)
    assert "names awaiting a verdict (setup batch): 2" in lines[2]

    # the owner's verdict closes the item and the rows follow
    vid = verdict_mod.enter(
        engine,
        corpus,
        PERS,
        entry(),
        step.name_result(engine, "PRS", PERS, NOW, p=P, mf=mf, peers=False).quant,
        "owner",
        NOW,
    )
    assert verdict_mod.open_item(engine, PERS) is None
    step.recompute_one(engine, "PRS", PERS, NOW)
    v = rows(engine, PERS, "moat_verdict")[-1]
    assert (v["value_text"], v["value"], v["evidence_grade"], v["as_of"]) == (
        "NARROW",
        None,
        "B",
        "2026-10-12",
    )
    assert f"M06 verdict {vid}" in v["source_ref"] and "catch-up band 5–10 years" in v["method"]
    g = rows(engine, PERS, "moat_gate")[-1]
    assert (
        g["value_text"] == "met"
        and g["evidence_grade"] == "B"
        and "low end 5 ≥ the 5-year MY horizon" in g["method"]
    )
    assert gate_mod.latest_gate(engine, PERS)["value_text"] == "met"


def test_reopen_only_when_a_new_10k_changes_the_class_and_stale_since(dbs):
    engine, corpus = dbs
    synth(engine, CYC, "CYC", [30, 5, 12, 35, 18, -3, 9, 40, 4, 5], start=2014)
    step.moat_pass(engine, {"CYC": CYC}, NOW, p=P, mf=NO_MODELS)
    q = step.name_result(engine, "CYC", CYC, NOW, p=P, mf=NO_MODELS, peers=False).quant
    assert q.state == "through_cycle" and q.newest_fy == "FY2024"
    verdict_mod.enter(
        engine,
        corpus,
        CYC,
        entry(verdict="NARROW", band="3to5", sources=("efficient_scale",)),
        q,
        "owner",
        NOW,
    )
    # FY2025 10-K: a deep loss year drops the median below the hurdle → weak → re-open item
    later = datetime(2026, 10, 20, tzinfo=UTC)
    for tag, v in (
        ("OperatingIncomeLoss", -300 * M),
        (
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            -300 * M,
        ),
        ("IncomeTaxExpenseBenefit", 0),
        ("Revenues", 2000 * M),
    ):
        fact(engine, CYC, tag, "2025-01-01", "2025-12-31", v, filed="2026-10-15")
    for tag in ("StockholdersEquity", "CashAndCashEquivalentsAtCarryingValue"):
        fact(
            engine,
            CYC,
            tag,
            None,
            "2025-12-31",
            1000 * M if tag == "StockholdersEquity" else 0,
            filed="2026-10-15",
        )
    mp = step.moat_pass(engine, {"CYC": CYC}, later, p=P, mf=NO_MODELS)
    r = mp.results["CYC"]
    assert r.quant.state == "weak" and mp.queued == 1
    it = verdict_mod.open_item(engine, CYC)
    assert "quant class changed through_cycle → weak at FY2025" in it["reason"]
    assert r.gate.stale == "stale since 2026-10-15" and r.gate.state == "not_met"  # 3–5 years < 5
    assert "stale since 2026-10-15" in rows(engine, CYC, "moat_gate")[-1]["method"]


def test_run_local_part_never_fails(dbs, monkeypatch):
    engine, _ = dbs

    def boom(*a, **k):
        raise RuntimeError("bad")

    monkeypatch.setattr(step, "moat_pass", boom)
    assert step.run_local_part(engine, {}, NOW, clock=lambda: 0.0) == [
        "M06 moat — local pass (Part 1, 0 requests) (0.0 s):",
        "  M06: error — RuntimeError: bad",
    ]


def test_refresh_runs_m06_after_m05_and_before_m07():
    src = (ROOT / "scripts" / "run_refresh.py").read_text(encoding="utf-8")
    i = src.index("prices += moat_local_step(engine, report)")
    assert src.index("prices += future_spend_commitments_local_step(engine, corpus, report)") < i
    assert i < src.index("prices += ownership_local_step(engine, report)")


# --- owner script ---------------------------------------------------------------------------------


class Args:
    def __init__(self, **kw):
        self.no_sec, self.tickers, self.companies = True, None, None
        self.__dict__.update(kw)


def test_script_list(capsys):
    rm = load_script("run_moat")
    assert rm._main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "quant" in out and "challengers" in out and "(not built)" in out


def test_script_quant_on_an_injected_db(dbs, tmp_path):
    engine, _ = dbs
    intc_like(engine)
    synth(engine, PERS, "PRS", [30] * 10)
    rm = load_script("run_moat")
    log = rm.Log(tmp_path / "logs" / "m.txt")
    assert (
        rm.run_quant(
            Args(companies={"INTC": INTC, "PRS": PERS}), log, tmp_path, engine=engine, now=NOW
        )
        == 0
    )
    log.close()
    text = (tmp_path / "logs" / "m.txt").read_text(encoding="utf-8")
    assert "INTC: quant weak 60% (6/10 > 8%" in text and "last 3 above 0" in text
    assert "FY2018: ROIC 19.8%, GM 61.7%" in text
    assert "=== Summary" in text and "SEC requests: 0" in text and "signal +18" in text
    assert "m06_verdict items open: 2" in text


# --- the Moat section and the M06 setup page (D-UI-40) ---------------------------------------------


def _client(tmp_path, monkeypatch, fill, tickers):
    from engine.moat import views as m06_views
    from tests.test_technicals_tab import _app

    monkeypatch.setattr(m06_views.models_mod, "load_safe", lambda *a: NO_MODELS)
    return _app(tmp_path, monkeypatch, fill, tickers)


def test_financials_tab_shows_the_moat_section_for_every_company(tmp_path, monkeypatch):
    def fill(engine, corpus):
        engine.execute("DELETE FROM ticker")  # the helpers insert their own
        intc_like(engine)
        synth(engine, PERS, "PRS", [30] * 10, gm=68)

    client = _client(tmp_path, monkeypatch, fill, {"INTC": INTC, "PRS": PERS})
    html = client.get("/c/INTC?tab=financials").text
    assert (
        'Moat <span class="muted">(M06)</span>' in html and "weak: 6 of 10 years above 8%†" in html
    )
    assert "61.7%" in html and "32.7%" in html  # GM row (D32 standard rows)
    assert "−11.7%" in html  # FY2024 ROIC, losses kept negative
    assert "no owner verdict yet" in html and "Engine proposal" in html and "NONE" in html
    assert "Evidence against" in html and "excludes leases" in html
    assert "RPO: not tagged (unknown, not none)" in html
    assert "object at 0x" not in html and "<built-in method" not in html


def test_setup_page_and_verdict_form_store_close_and_rewrite(tmp_path, monkeypatch):
    def fill(engine, corpus):
        engine.execute("DELETE FROM ticker")  # the helpers insert their own
        synth(engine, PERS, "PRS", [30] * 10, gm=68)
        synth(engine, MSTR, "MSTR", [5] * 10)
        step.moat_pass(engine, {"PRS": PERS}, NOW, p=P, mf=NO_MODELS)

    client = _client(tmp_path, monkeypatch, fill, {"PRS": PERS, "MSTR": MSTR})
    monkeypatch.setattr(
        step.models_mod, "load_safe", lambda *a: models(("MSTR", "asset_treasury", None))
    )
    from engine.moat import views as m06_views

    monkeypatch.setattr(
        m06_views.models_mod, "load_safe", lambda *a: models(("MSTR", "asset_treasury", None))
    )
    html = client.get("/m06/setup").text
    assert (
        'id="m06-PRS"' in html and "proposal NARROW candidate" in html and "1 item(s) open" in html
    )
    assert (
        "Not applicable (N_A, no verdict taken)" in html
        and "asset vehicle: ROIC shown, not rated" in html
    )
    assert "object at 0x" not in html and "<built-in method" not in html
    assert "Enter the verdict on the M06 setup page" in client.get("/review/1").text
    # refused: band and verdict disagree
    r = client.post(
        "/m06/verdict/PRS",
        data={"verdict": "WIDE", "band": "5to10", "sources": ["network"], "reason": "x"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and "error=" in r.headers["location"]
    r = client.post(
        "/m06/verdict/PRS",
        data={
            "verdict": "NARROW",
            "band": "5to10",
            "sources": ["switching_costs", "network"],
            "reason": "rewrite cost",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303 and "gate%20met" in r.headers["location"]
    html = client.get("/m06/setup").text
    assert "0 item(s) open" in html and "rewrite cost" in html
    html = client.get("/c/PRS?tab=financials").text
    assert "NARROW" in html and "5–10 years" in html and "switching costs, network" in html
    # the review action route sends m06 items to the setup page
    from engine.store.db import open_db

    eng = open_db("engine", tmp_path / "data")
    item = eng.execute(
        "SELECT item_id, resolution FROM review_queue WHERE kind = 'm06_verdict'"
    ).fetchone()
    gate = eng.execute(
        "SELECT value_text FROM signal WHERE cik = ? AND signal = 'moat_gate' AND timeframe = 'MY' ORDER BY as_of DESC",
        (PERS,),
    ).fetchone()
    eng.close()
    assert item["resolution"] == "verdict NARROW (5–10 years)" and gate[0] == "met"
    assert (
        "Resolved: verdict NARROW (5–10 years) by owner"
        in client.get(f"/review/{item['item_id']}").text
    )
    r = client.post(f"/review/{item['item_id']}/dismiss", follow_redirects=False)
    assert r.headers["location"].startswith("/m06/setup?error=")
