# ruff: noqa: E501  (fixture rows)
"""M04 Part 8a (MVP): CvD assembly, health vote, M01 reading, `m04_cvd`, market share and the
M04 tab (docs/M04_BUILD_LOG.md Part 8a; D-M04-1, -52…68, -100…105).

Fixture: tests/fixtures/m04/cvd_cases_20261013.json (Micron FY2008–Q1 FY2024 with Western
Digital as its peer; Intel 2008–2024 with AMD, NVIDIA, TI, Qualcomm and Micron; figures from
the Round 6 brief, the pack's worked examples A–C and probe L9, the rest illustrative —
README "Part 8a"). Invitae reuses the Part 4a companyconcept files. Never calls SEC."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from engine.financials import cvd, cvd_step, health, market_share, models
from engine.sec.xbrl_facts import store_facts
from tests.conftest import FIXTURES

M04 = FIXTURES / "m04"
DOC = json.loads((M04 / "cvd_cases_20261013.json").read_text(encoding="utf-8"))
CASES, TAGS = DOC["companies"], DOC["tags"]
M = 1_000_000
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
MF = models.parse({"company": []})
MU, WDC, INTC = CASES["MU"]["cik"], CASES["WDC"]["cik"], CASES["INTC"]["cik"]
NVDA = CASES["NVDA"]["cik"]


def acc(cik: str, filed: str) -> str:
    return f"{cik}-{filed[2:4]}-{filed[5:7]}{filed[8:10]}00"


def load(engine, ticker: str, *, ticker_row: bool = True) -> str:
    c = CASES[ticker]
    cik = c["cik"]
    engine.execute(
        "INSERT OR REPLACE INTO entity (cik, name, sic, fiscal_year_end, source_ref, fetched_at) "
        "VALUES (?, ?, ?, ?, 't', 'n')",
        (cik, c["name"], c["sic"], c["fye"]),
    )
    if ticker_row:
        engine.execute(
            "INSERT OR IGNORE INTO ticker (ticker, cik, valid_from, source) VALUES (?, ?, "
            "'2000-01-01', 't')",
            (ticker, cik),
        )
    facts: dict[str, dict[str, list]] = {}

    def put(key, start, end, filed, form, v):
        tag = TAGS[key]
        unit = "shares" if key == "shares" else "USD"
        row = {"end": end, "val": v * M, "accn": acc(cik, filed), "form": form, "filed": filed}
        if start:
            row["start"] = start
        facts.setdefault(tag, {}).setdefault(unit, []).append(row)

    fys = c["fy"]
    for i, row in enumerate(fys):
        start, end, filed, vals = row[:4]
        for k, v in vals.items():
            put(k, start, end, filed, "10-K", v)
        if len(row) > 4 and i > 0:
            for k, v in row[4].items():
                put(k, fys[i - 1][0], fys[i - 1][1], filed, "10-K", v)
    for start, end, filed, form, vals in c["q"]:
        for k, v in vals.items():
            put(k, start, end, filed, form, v)
    for end, filed, form, vals in c["inst"]:
        for k, v in vals.items():
            put(k, None, end, filed, form, v)
    engine.execute("BEGIN")
    store_facts(engine, cik, {"facts": {"us-gaap": {t: {"units": u} for t, u in facts.items()}}})
    engine.execute("COMMIT")
    return cik


def confirm_peers(engine, target: str, members: list[str]) -> None:
    engine.execute(
        "INSERT INTO peer_group (name, source, sic, created_at) VALUES (?, 'sic', '3674', 't')",
        (f"M04 peers {target}",),
    )
    gid = engine.execute("SELECT max(group_id) FROM peer_group").fetchone()[0]
    for t in members:
        engine.execute(
            "INSERT INTO peer_member (group_id, cik, name, source) VALUES (?, ?, ?, 'owner')",
            (gid, CASES[t]["cik"], CASES[t]["name"]),
        )


def confirm_stage(engine, cik: str, stage: str = "mature", end: str = "2023-08-31") -> None:
    engine.execute(
        "INSERT INTO company_stage (cik, period_end, fiscal_label, computed, years, reasons, "
        "method, confirmed, confirmed_by, confirmed_at, computed_at) VALUES (?, ?, 'FY', ?, '[]', "
        "'[]', 't', ?, 'owner', '2026-10-12T00:00:00+00:00', '2026-10-12T00:00:00+00:00')",
        (cik, end, stage, stage),
    )


def micron(engine, stage: str | None = "mature") -> None:
    load(engine, "MU")
    load(engine, "WDC")
    confirm_peers(engine, MU, ["WDC"])
    if stage:
        confirm_stage(engine, MU, stage)


def intel(engine) -> None:
    for t in ("INTC", "AMD", "TXN", "QCOM", "NVDA", "MU"):
        load(engine, t)
    confirm_peers(engine, INTC, ["AMD", "NVDA", "TXN", "QCOM", "MU"])
    confirm_stage(engine, INTC, "mature", "2023-12-30")


def ev(engine, cik, ticker, as_of, **kw):
    return cvd.evaluate(engine, cik, ticker, as_of, models=MF, calendar=False, **kw)


def filing(engine, cik, accession, form, filed, report):
    engine.execute(
        "INSERT OR IGNORE INTO filing (accession, cik, form, filed, report_date, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, 'x')",
        (accession, cik, form, filed, report),
    )
    engine.execute(
        "INSERT OR IGNORE INTO filing_cik (accession, cik) VALUES (?, ?)", (accession, cik)
    )


def mu_filings(engine) -> None:
    """Micron's 10-K / 10-Q rows (filing status, D-M04-61) from the fixture's filed dates."""
    seen = set()
    for _start, end, filed, form, _ in CASES["MU"]["q"]:
        if (filed, form) not in seen:
            seen.add((filed, form))
            filing(engine, MU, acc(MU, filed), form, filed, end)


def propose(engine, c, cik, ticker):
    cc = cvd_step.CompanyCvd(ticker, cik, c)
    engine.execute("BEGIN")
    cvd_step.propose_items(engine, cc, NOW)
    engine.execute("COMMIT")
    return cc


# --- Micron 2022–23 (R6 worked example; probe L9) -------------------------------------------


def test_mu_q4_fy22_activates_on_the_latest_quarter_only(dbs):
    engine, _ = dbs
    micron(engine)
    a = cvd.activation(engine, MU, "2022-10-07")
    assert a.ref == "2022-09-01" and a.kind == "fiscal year"
    assert a.rev_growth == pytest.approx(0.110, abs=0.001)  # TTM +11.0% (no TTM trigger)
    assert len(a.triggers) == 1 and "latest quarter (2022-09-01) revenue -19.7%" in a.triggers[0]
    assert "D-M04-67" in a.triggers[0]
    assert any("+11.0%" in t for t in a.tests)
    c = ev(engine, MU, "MU", "2022-10-07")
    assert c.active and c.raw_state == "AMBIGUOUS"  # WDC's matching quarter not filed yet
    assert c.row("revenue_vs_peers").awaiting


def test_mu_low_on_2022_09_26_reads_no_slowdown_in_a_stale_window(dbs):
    engine, _ = dbs
    micron(engine)
    mu_filings(engine)
    c = cvd.evaluate(engine, MU, "MU", "2022-09-26", models=MF, calendar=True)
    assert c.state == "NO_SLOWDOWN" and not c.active and c.ref_end == "2022-06-02"
    assert c.stale and "period 2022-09-01" in c.status_text  # Q4 FY22 ended, not filed
    assert "stale: the first tranche may use the carried state" in c.m01.rule3
    assert c.confidence is None


def test_mu_q4_fy23_cyclical_trough_1_00_with_q2_on_3_of_7(dbs):
    engine, _ = dbs
    micron(engine)
    c = ev(engine, MU, "MU", "2023-11-10")  # after WDC's September-quarter 10-Q (2023-11-07)
    assert c.state == c.raw_state == "CYCLICAL_TROUGH" and c.confidence == 1.0
    assert (c.q1.present, c.q1.applicable) == (4, 5) and (c.q2.present, c.q2.applicable) == (3, 7)
    assert {r.key: r.reading for r in c.rows if r.present} == {
        "revenue_vs_peers": "shared",
        "inventory_days": "shared",
        "supply_response": "shared",
        "cycle_history": "shared",
        "trough": "intact",
        "capex_rd": "intact",
        "health": "intact",
    }
    rev = c.row("revenue_vs_peers")
    assert "gap -14.3 pp vs median -35.2%" in rev.value and c.deeper is True  # fixed gap ≤ −10 pp
    assert "fewer than 5" in rev.why
    gm = c.row("gm_gap")
    assert gm.reading == "missing" and "fewer than 3 comparable peers (1)" in gm.why
    assert c.row("pricing").why.startswith("(DS13)")
    assert c.row("moat").reading == "not_applicable" and not c.row("moat").counted
    assert c.row("customer").why.startswith("deferred (MVP")
    sr = c.row("supply_response")
    assert "-36.4%" in sr.value and "-48.0%" in sr.value
    assert "FY2018→FY2020 -29.5%" in c.row("cycle_history").why
    assert c.gate.state == "pass" and c.m01.rule3 == "allowed"
    assert c.m01.rule7.startswith("yes (CYCLICAL_TROUGH with a gate pass")


def test_mu_before_wdc_files_is_ambiguous_but_awaits_peers_without_an_item(dbs):
    engine, _ = dbs
    micron(engine)
    c = ev(engine, MU, "MU", "2023-10-06")  # the 10-K's filing day
    assert c.raw_state == "AMBIGUOUS" and c.q1.present == 1 and c.confidence == 0.0
    assert "awaiting peer filing" in c.row("revenue_vs_peers").why
    assert not propose(engine, c, MU, "MU").queued  # S6.1: re-runs when the peer files


def test_cycle_episode_on_a_ttm_after_the_fiscal_year_measures_from_the_peak(dbs):
    engine, _ = dbs
    micron(engine)
    r = ev(engine, MU, "MU", "2024-01-10").row("cycle_history")  # TTM to 2023-11-30
    assert r.reading == "shared" and "this episode -47.4% from FY2022" in r.value


def test_mu_inventory_days_q2_fy23_153_1_and_235_0(dbs):
    engine, _ = dbs
    micron(engine)
    d = cvd.inventory_days(engine, MU, "2023-11-10", "Q", "2023-03-02")
    assert round(d.reported, 1) == 153.1 and round(d.adjusted, 1) == 235.0
    assert "write-down 1,430M added back" in d.text and "8,359/8,129M" in d.text


def test_mu_fy2023_capex_1_30x_is_intact(dbs):
    engine, _ = dbs
    micron(engine)
    r = ev(engine, MU, "MU", "2023-11-10").row("capex_rd")
    assert r.reading == "intact" and round(r.number, 2) == 1.30
    assert "49.4% vs 3-yr avg 37.9%" in r.value and "(+11%)" in r.value


def test_mu_fy2023_health_f_quality_4_and_piotroski_4(dbs):
    engine, _ = dbs
    micron(engine)
    bk = health.Book(engine, MU, "2023-11-10")
    fq = health.f_quality(engine, MU, "2023-11-10", stage="mature", book=bk)
    assert fq.known == 4 and fq.band == "intact" and fq.label == "FY2023"
    assert [p.value for p in fq.points] == [
        1,
        0,
        1,
        1,
        1,
    ]  # accruals, leverage, liquidity, equity, CFO
    f = health.piotroski(engine, MU, "2023-11-10", book=bk)
    assert f.value == 4 and not f.missing  # pack worked example C: four cycle-driven fails


def test_mu_fy2016_f_quality_is_neutral_not_weakening(dbs):
    engine, _ = dbs
    micron(engine)
    fq = health.f_quality(engine, MU, "2016-12-31", stage="mature")
    assert fq.label == "FY2016" and fq.known == 3 and fq.band == "neutral"
    assert health.piotroski(engine, MU, "2016-12-31").value == 3  # F ≤ 3 would say weakening


def test_unconfirmed_stage_leaves_the_equity_point_missing_and_the_band_open(dbs):
    engine, _ = dbs
    micron(engine, stage=None)
    fq = health.f_quality(engine, MU, "2023-11-10", stage=None)
    eq = next(p for p in fq.points if p.name == "equity")
    assert eq.value is None and "stage unconfirmed (D-M04-65)" in eq.text
    assert fq.known == 3 and fq.band is None and "decide the band" in fq.missing  # 3 or 4
    assert health.band(4, 1) == "intact" and health.band(1, 1) == "weakening"
    assert health.band(2, 1) is None


# --- Intel 2023–24 ---------------------------------------------------------------------------


def test_intc_2023_ambiguous_0_25_opens_m04_cvd(dbs):
    engine, _ = dbs
    intel(engine)
    c = ev(engine, INTC, "INTC", "2024-03-01")
    assert c.state == "AMBIGUOUS" and c.confidence == 0.25
    assert c.q1.counts == {"shared": 1, "company_specific": 1, "neutral": 2}
    assert c.q2.counts == {"intact": 1, "weakening": 0, "neutral": 2}
    rev = c.row("revenue_vs_peers")
    assert rev.reading == "shared" and "NVIDIA CORP z +8.97" in rev.why  # dropped → n = 4
    ch = c.row("cycle_history")
    assert ch.reading == "company_specific" and "first deep decline" in ch.why
    sr = c.row("supply_response")
    assert sr.reading == "neutral" and "mixed (2 cutting, 2 expanding of 4)" in sr.why
    assert c.row("inventory_days").reading == "neutral"  # 141.2 → 123.4 days
    gm = c.row("gm_gap")
    assert gm.reading == "intact" and "gap -14.3 → -15.5 pp = -1.2 pp" in gm.value
    assert "insufficient history" in c.row("trough").why
    assert c.m01.rule3.startswith("blocked until you answer the m04_cvd item")
    cc = propose(engine, c, INTC, "INTC")
    assert cc.queued == {"m04_cvd:AMBIGUOUS": "queued"}
    it = engine.execute("SELECT * FROM review_queue WHERE kind = 'm04_cvd'").fetchone()
    p = json.loads(it["payload"])
    assert p["computed"] == "AMBIGUOUS" and p["confidence"] == 0.25 and len(p["rows"]) == 14
    pr = engine.execute(
        "SELECT priority, capped FROM m04_proposal WHERE kind = 'm04_cvd'"
    ).fetchone()
    assert (pr["priority"], pr["capped"]) == (2, 1)


def test_intc_2023_capex_1_75x_into_falling_revenue_is_neutral_with_m05_pointer(dbs):
    engine, _ = dbs
    intel(engine)
    r = ev(engine, INTC, "INTC", "2024-03-01").row("capex_rd")
    assert r.reading == "neutral" and r.number == pytest.approx(1.75, abs=0.012)
    assert "see M05" in r.why and "47.5% vs 3-yr avg 27.2%" in r.value


def test_intc_2024_equity_point_kept_at_plus_2_1_percent(dbs):
    engine, _ = dbs
    intel(engine)
    fq = health.f_quality(engine, INTC, "2025-03-01", stage="mature")
    eq = next(p for p in fq.points if p.name == "equity")
    assert eq.value == 1 and "+2.1%" in eq.text and "kept unless shares rose > 10%" in eq.text
    assert fq.known == 4 and fq.band == "intact"
    f23 = health.f_quality(engine, INTC, "2024-03-01", stage="mature")
    assert f23.known == 3 and f23.band == "neutral"  # INTC 2023 (+2.00%, kept)


def test_owner_answer_becomes_the_state_and_lapses_when_the_state_leaves_review(dbs):
    from engine import review

    engine, _ = dbs
    intel(engine)
    cc = cvd_step.company_cvd(engine, "INTC", INTC, datetime(2024, 3, 1, 12, tzinfo=UTC), mf=MF)
    assert cc.queued == {"m04_cvd:AMBIGUOUS": "queued"}
    item = engine.execute("SELECT item_id FROM review_queue WHERE kind = 'm04_cvd'").fetchone()[0]
    with pytest.raises(review.ReviewError, match="note is required"):
        review.m04_action(engine, item, "set_state", "", "owner", NOW, target="structural_decline")
    done = review.m04_action(
        engine,
        item,
        "set_state",
        "share loss to AMD and Arm (S-new-69)",
        "owner",
        NOW,
        target="structural_decline",
    )
    assert done == "set_state STRUCTURAL_DECLINE (computed AMBIGUOUS)"
    row = engine.execute(
        "SELECT value_text, method FROM signal WHERE cik = ? AND signal = "
        "'cvd_state' AND timeframe = 'MY'",
        (INTC,),
    ).fetchone()
    assert row["value_text"] == "STRUCTURAL_DECLINE" and "owner answer" in row["method"]
    c = ev(engine, INTC, "INTC", "2024-03-01")
    assert c.raw_state == "AMBIGUOUS" and c.state == "STRUCTURAL_DECLINE"
    assert "CvD STRUCTURAL_DECLINE (M01 rule 4, S6.14)" in c.m01.rule4
    assert not propose(engine, c, INTC, "INTC").queued  # answered: no new item
    c.raw_state = "CYCLICAL_TROUGH"  # the computed state leaves review → answer cleared
    propose(engine, c, INTC, "INTC")
    assert cvd.stored_answer(engine, INTC) is None
    n = engine.execute("SELECT count(*) FROM m04_proposal WHERE kind = 'm04_cvd'").fetchone()[0]
    assert n == 0


# --- NVIDIA, Invitae, G ----------------------------------------------------------------------


def test_nvda_fy2023_activates_on_margin_not_revenue(dbs):
    engine, _ = dbs
    load(engine, "NVDA")
    a = cvd.activation(engine, NVDA, "2023-03-01")
    assert a.ref == "2023-01-29" and a.rev_growth == pytest.approx(0.002, abs=0.0005)
    assert any("gross margin -8.0 pp" in t for t in a.triggers)
    assert not any("revenue" in t for t in a.triggers)  # +0.2%: revenue alone never fires
    assert any("annual filer" in t for t in a.tests)  # fiscal years only in the fixture


def test_nvda_g_3_of_7_in_its_best_year_is_shown_not_voted():
    nv = {
        "roa": 0.453,
        "cfo_assets": 0.427,
        "accruals_assets": 0.025,
        "varroa": 0.066,
        "varsgr": 0.311,
        "rd_assets": 0.132,
        "capex_assets": 0.016,
        "adv_assets": None,
    }
    med = {
        "roa": 0.013,
        "cfo_assets": 0.060,
        "accruals_assets": -0.051,
        "varroa": 0.017,
        "varsgr": 0.104,
        "rd_assets": 0.084,
        "capex_assets": 0.094,
        "adv_assets": None,
    }
    pts = health.g_points(nv, [med])  # the pack's FY2024 medians (n = 5) as one stand-in row
    assert [p.value for p in pts] == [1, 1, 0, 0, 0, 1, 0, None]
    sc = health.Score("g_score", "2024-01-28", "FY2024", pts)
    assert (sc.known, sc.n) == (3, 7)


def test_invitae_gate_fail_overrides_the_grid(dbs):
    from tests import test_financials_4a as t4a

    engine, _ = dbs
    t4a.invitae(engine)
    c = cvd.evaluate(engine, t4a.NVTA, "Invitae", "2022-03-01", models=t4a.MF, calendar=False)
    assert c.gate.state == "fail"
    assert c.m01.rule3.startswith("blocked: survival gate fail overrides the grid")
    assert c.m01.rule7 == "no" and "survival gate fail (S6.14)" in c.m01.rule4
    c.raw_state = "AMBIGUOUS"  # even a review state opens no m04_cvd while the gate fails
    assert not propose(engine, c, t4a.NVTA, "NVTA").queued


# --- Rules -----------------------------------------------------------------------------------


def _rows(q, *readings):
    return [cvd.Row(q, f"r{i}", "", r) for i, r in enumerate(readings)]


def test_resolution_missing_rows_leave_the_denominator_and_2_of_3_wins():
    q = cvd.resolve("Q2", _rows("Q2", "intact", "intact", "neutral", "missing", "missing"))
    assert q.resolved and q.lead == "intact" and q.share == pytest.approx(2 / 3)
    assert (q.present, q.applicable) == (3, 5)
    one = cvd.resolve("Q1", _rows("Q1", "shared", "missing"))
    assert not one.resolved and one.share == 0.0  # fewer than 2 present rows
    split = cvd.resolve("Q1", _rows("Q1", "shared", "company_specific", "neutral", "neutral"))
    assert not split.resolved and split.share == 0.25
    assert cvd.classify(True, split, q) == ("AMBIGUOUS", 0.25)
    shared = cvd.resolve("Q1", _rows("Q1", "shared", "shared", "company_specific"))
    weak = cvd.resolve("Q2", _rows("Q2", "weakening", "weakening"))
    assert cvd.classify(True, shared, weak) == ("CYCLE_PLUS_DAMAGE", 0.67)
    assert cvd.classify(False, shared, weak) == ("NO_SLOWDOWN", None)


def test_turning_points_need_a_5pp_reversal():
    tr, pk, cur = cvd.turning_points([55.7, 65.3, 62.5, 62.1, 59.8, 63.7, 60.9, 58.6, 42.6, 40.0])
    assert tr == [0] and pk == [1] and cur == 9  # Intel: 1–4 pp wiggles are not cycles
    lows = [0, 2, 4]
    assert cvd._weakening([30, 50, 20, 40, 10], lows, [1, 3]) is True
    assert cvd._weakening([30, 50, 20, 60, 10], lows, [1, 3]) is False


def test_market_share_entries_feed_the_q2_row_and_the_signal(dbs):
    engine, _ = dbs
    micron(engine)
    engine.execute("BEGIN")
    market_share.add(
        engine, MU, "2022-09-30", "24.0", "DRAM revenue", "TrendForce Q3 2022", by="owner", now=NOW
    )
    market_share.add(
        engine,
        MU,
        "2023-09-30",
        "22.5",
        "DRAM revenue",
        "TrendForce Q3 2023",
        by="owner",
        now=NOW,
        market_size="20e9",
    )
    engine.execute("COMMIT")
    sh = market_share.reading(engine, MU, "2023-11-10")
    assert sh.reading == "weakening" and sh.change_pp == pytest.approx(-1.5) and sh.grade == "B"
    assert "market size not entered: read as flat" in sh.text
    with pytest.raises(market_share.ShareError):
        market_share.add(engine, MU, "2023-09-30", "120", "DRAM", "x", by="owner", now=NOW)
    cc = cvd_step.company_cvd(engine, "MU", MU, datetime(2023, 11, 10, 12, tzinfo=UTC), mf=MF)
    c = cc.c
    assert c.row("market_share").reading == "weakening" and c.q2.present == 4
    assert c.state == "CYCLICAL_TROUGH" and c.confidence == 0.75  # intact 3 of 4 present
    sig = engine.execute(
        "SELECT value, evidence_grade FROM signal WHERE cik = ? AND signal = "
        "'market_share_chg_pp' AND timeframe = 'MY'",
        (MU,),
    ).fetchone()
    assert sig["value"] == pytest.approx(-1.5) and sig["evidence_grade"] == "B"
    state = engine.execute(
        "SELECT evidence_grade FROM signal WHERE cik = ? AND signal = "
        "'cvd_state' AND timeframe = 'MY'",
        (MU,),
    ).fetchone()
    assert state["evidence_grade"] == "B"  # weakest deciding input: the owner's share entry


def test_signals_are_written_for_every_timeframe_and_never_fill_zero(dbs):
    engine, _ = dbs
    micron(engine)
    cvd_step.company_cvd(engine, "MU", MU, datetime(2023, 11, 10, 12, tzinfo=UTC), mf=MF)
    rows = engine.execute(
        "SELECT signal, timeframe, value, value_text, method FROM signal "
        "WHERE cik = ? AND module_id = 'M04'",
        (MU,),
    ).fetchall()
    names = {r["signal"] for r in rows}
    assert set(cvd_step.SIGNALS) <= names
    assert {n for n, _ in cvd_step.DEFERRED_SIGNALS} <= names
    for r in rows:
        if r["value"] is None and r["value_text"] is None:
            assert r["method"].startswith("missing: "), r["signal"]
    by = {(r["signal"], r["timeframe"]): r for r in rows}
    assert by[("cvd_state", "MY")]["value_text"] == "CYCLICAL_TROUGH"
    assert "info (weight 0)" in by[("cvd_state", "ST")]["method"]
    assert by[("cvd_confidence", "MY")]["value"] == 1.0
    assert by[("cvd_coverage_q2", "PT")]["value"] == pytest.approx(3 / 7, abs=1e-4)
    assert by[("deeper_than_peers", "MY")]["value_text"] == "flagged"
    assert (
        by[("f_quality", "MY")]["value"] == 4 and by[("f_quality", "MY")]["value_text"] == "intact"
    )
    assert by[("f_score", "MY")]["value"] == 4
    assert by[("g_score", "MY")]["method"].startswith("missing: fewer than 5 peers")
    assert by[("overreaction_gap", "MY")]["method"].startswith("missing: deferred (MVP, D31)")
    assert by[("market_share_chg_pp", "MY")]["method"].startswith("missing: no share data")
    assert "M01: rule 3 tranches: allowed" in by[("cvd_state", "MY")]["method"]


def test_excluded_tag_writes_not_applicable_rows(dbs):
    engine, _ = dbs
    load(engine, "TXN")
    mf = models.parse(
        {
            "company": [
                {
                    "ticker": "TXN",
                    "cik": CASES["TXN"]["cik"],
                    "tag": "fund",
                    "reason": "test",
                    "source": "test",
                }
            ]
        }
    )
    cc = cvd_step.company_cvd(engine, "TXN", CASES["TXN"]["cik"], NOW, mf=mf)
    assert cc.c.excluded.startswith("not applicable (fund)")
    r = engine.execute(
        "SELECT method FROM signal WHERE cik = ? AND signal = 'cvd_state' AND timeframe = 'MY'",
        (CASES["TXN"]["cik"],),
    ).fetchone()
    assert r["method"].startswith("missing: not applicable (fund)")


# --- Script, refresh hook, tab ---------------------------------------------------------------


def run_financials_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_financials", FIXTURES.parent.parent / "scripts" / "run_financials.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cvd_run_logs_a_grid_per_company_and_the_regression_lines(dbs):
    engine, _ = dbs
    micron(engine)
    rf = run_financials_module()
    lines: list[str] = []
    cp = rf.cvd_run(
        engine,
        {"MU": MU},
        datetime(2023, 11, 10, 12, tzinfo=UTC),
        lambda *ls: lines.extend(ls),
        mf=MF,
    )
    text = "\n".join(lines)
    assert "cvd" in rf.BUILT and cp.companies["MU"].c.state == "CYCLICAL_TROUGH"
    for want in (
        "MU: CYCLICAL_TROUGH · confidence 1.00 · coverage Q1 4 of 5, Q2 3 of 7",
        "Q2 Customer base (stickiness class): missing",
        "Regression cases",
        "MU Q4 FY23",
        "expected: CYCLICAL_TROUGH 1.00",
        "=== Summary cvd (Part 8a)",
        "Open m04_cvd items: 0",
    ):
        assert want in text, want


def test_refresh_hook_runs_the_cvd_pass(dbs):
    import importlib.util

    engine, _ = dbs
    spec = importlib.util.spec_from_file_location(
        "run_refresh", FIXTURES.parent.parent / "scripts" / "run_refresh.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "M04 CvD — local pass (Part 8a" in mod.financials_cvd_local_step(engine, None)


def test_m04_tab_and_summary_page(tmp_path):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui.app import create_app
    from engine.ui.settings import UiSettings

    data = tmp_path / "data"
    engine = open_db("engine", data)
    intel(engine)
    cvd_step.company_cvd(engine, "INTC", INTC, datetime(2024, 3, 1, 12, tzinfo=UTC), mf=MF)
    item = engine.execute("SELECT item_id FROM review_queue WHERE kind = 'm04_cvd'").fetchone()
    assert item is not None
    engine.close()
    open_db("corpus", data).close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text('[watchlist]\ntickers = ["INTC"]\n', encoding="utf-8")
    with TestClient(create_app(UiSettings(data_dir=data, watchlist=watch))) as c:
        html = c.get("/c/INTC?tab=m04").text
        summary = c.get("/m04").text
        guide = c.get("/review").text
        one = c.get(f"/review/{item[0]}").text
        r = c.post(
            "/m04/share/INTC",
            data={
                "period_end": "2025-12-31",
                "share_pct": "71.0",
                "market": "x86 server CPUs (units)",
                "source": "Mercury Research Q4 2025",
            },
            follow_redirects=False,
        )
    for want in (
        "Cycle vs Decline — INTC",
        "CvD state",
        "M01 reading",
        "Piotroski F",
        "Mohanram G",
        "shown, not voted",
        "Add market share",
        "Watchlist — CvD",
        "Industry pricing / volume",
        "missing: (DS13)",
        "?tab=financials#gate",
    ):
        assert want in html, want
    assert "object at 0x" not in html
    assert "Watchlist — CvD" in summary and "AMBIGUOUS" in summary
    assert "CvD state to choose" in guide and "INTC 2023" in guide
    assert "Choose the state" in one and "structural decline" in one and "Q1 slump shared?" in one
    assert r.status_code == 303 and "tab=m04" in r.headers["location"]
    assert "market%20share%201%20added" in r.headers["location"]
