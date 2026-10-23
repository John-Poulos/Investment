"""M08 Part 2: Alpha Vantage EARNINGS_ESTIMATES (client, budget, storage, rotation), the
revision readings, forward P/E, PEG, the next-report cadence and walk-down window, the pass,
the refresh hook, the script and the Estimates block (docs/M08_VALUATION.md Part 2;
fixtures README in tests/fixtures/m08/)."""

from __future__ import annotations

import argparse
import json
from datetime import timedelta

import pytest

from engine.calls import calendar
from engine.calls.alpha_vantage import (
    DAILY_LIMIT,
    URL,
    AlphaVantageClient,
    logged_estimates_url,
    parse_estimates,
)
from engine.sec.results import Failed, Ok
from engine.valuation import estimates, peg, step
from engine.valuation.params import Params
from tests.conftest import Clock
from tests.test_valuation import (
    FIX,
    MF,
    MU,
    NO_MODELS,
    NOW,
    ROOT,
    TODAY,
    _app,
    annual_co,
    base,
    confirm_stage,
    filing,
    load_mu,
    load_script,
    quarterly_co,
    rows_of,
)

P = Params()
KEY = "SECRETKEY123"
IBM_RAW = (FIX / "ibm_estimates.json").read_bytes()
SIGN_RAW = (FIX / "estimates_sign_change.json").read_bytes()
EMPTY_RAW = (FIX / "estimates_no_coverage.json").read_bytes()
IBMX = "0000000501"
IBM_CLOSE = 20 * 12.3121  # forward P/E 20× (the brief's illustration)


class EstTransport:
    """Serves estimate replies per symbol; records params (the key must stay out of logs)."""

    def __init__(self, replies: dict[str, bytes], status: int = 200) -> None:
        self.replies = replies
        self.status = status
        self.calls: list[dict] = []

    def __call__(self, url, params, headers):
        assert url == URL
        self.calls.append(dict(params))
        return self.status, self.replies.get(params["symbol"], EMPTY_RAW)


def client(engine, transport, clock=None):
    clock = clock or Clock()
    clock.wall = NOW
    return AlphaVantageClient(KEY, engine, transport=transport, now=clock.now, clock=clock.mono,
                              sleep=clock.sleep)  # fmt: skip


def put(engine, cik, ticker, raw, day):
    reply = parse_estimates(raw)
    n = estimates.store(engine, cik, ticker, reply.rows, snapshot_date=day,
                        fetched_at=f"{day}T14:00:00Z",
                        source_ref=logged_estimates_url(ticker))  # fmt: skip
    estimates.record(engine, cik, ticker, "ok", f"{day}T14:00:00Z", f"{n} rows", "t")
    return n


def ibm_co(engine, close=IBM_CLOSE):
    """A calendar-year filer whose FY2025 is reported (as IBM on 2026-10-12)."""
    annual_co(engine, IBMX, "IBMX", [base(2023), base(2024), base(2025)], sic="7370",
              close=close)  # fmt: skip
    confirm_stage(engine, IBMX, "mature")


# --- the reply and the IBM worked example (brief: FY2026 −0.07% flat, 4.5%; g 6.8%) ---


def test_ibm_reply_figures_match_the_pack():
    reply = parse_estimates(IBM_RAW)
    assert len(reply.rows) == 4 and not reply.note
    snap = estimates.Snap(
        "IBM",
        "2026-10-12",
        "u",
        tuple(
            estimates.EstRow(
                r["horizon"],
                r["date"],
                {c: estimates.num(r.get(k)) for k, c in estimates.FIELDS.items()},
                r,
            )
            for r in reply.rows
        ),
    )
    fy1, fy2, note = estimates.fiscal_years(snap, "2025-12-31", "2026-10-12")
    assert (fy1.period_end, fy1.horizon) == ("2026-12-31", "current fiscal year")
    assert fy2.period_end == "2027-12-31" and "labelled" not in note
    h1, h2 = estimates.horizon("FY1", fy1, P), estimates.horizon("FY2", fy2, P)
    assert round(h1.rev30.value, 2) == -0.07 and estimates.band(h1.rev30, P) == "flat"
    assert round(h1.rev90.value, 2) == -1.27 and round(h1.dispersion.value, 1) == 4.5
    assert h1.breadth30.value == pytest.approx(-1 / 23)
    assert round(h2.rev30.value, 2) == -0.09 and round(h2.rev90.value, 2) == -2.39
    assert round(h2.dispersion.value, 1) == 11.8 and round(h2.breadth30.value, 2) == 0.04
    assert round((h2.avg / h1.avg - 1) * 100, 1) == 6.8
    # the quarter row ending on the fiscal year's date is never taken as the year
    assert all(r.is_year for r in (fy1, fy2))
    assert "eps_estimate_revision_down_trailing_7_days" in fy1.nulls()


@pytest.mark.parametrize(
    ("raw", "note"),
    [
        (EMPTY_RAW, "no coverage: empty reply"),
        (b'{"symbol": "INFQ", "estimates": []}', "no coverage: no estimate rows"),
        (b'{"Error Message": "Invalid API call. Please retry."}', "Invalid API call"),
    ],
)
def test_no_coverage_replies_are_replies_without_rows(raw, note):
    reply = parse_estimates(raw)
    assert reply.rows == [] and note in reply.note


def test_rate_limit_reply_is_a_failure():
    assert parse_estimates(b'{"Information": "rate limit: 25 requests per day"}').startswith(
        "Information"
    )


def test_sign_change_small_base_count_below_3_and_null_counts():
    reply = parse_estimates(SIGN_RAW)
    rows = [
        estimates.EstRow(r["horizon"], r["date"],
                         {c: estimates.num(r.get(k)) for k, c in estimates.FIELDS.items()}, r)
        for r in reply.rows
    ]  # fmt: skip
    h1, h2 = estimates.horizon("FY1", rows[0], P), estimates.horizon("FY2", rows[1], P)
    assert h1.rev30.value is None and h1.rev30.text == "not_meaningful" and h1.nm30 == "sign change"
    assert estimates.band(h1.rev30, P) == "not_meaningful"
    assert h1.dispersion.text == "not computed (count 2 < 3)" and h1.breadth30.value == 1.0
    assert h2.rev30.text == "not_meaningful" and "below $0.10" in h2.nm30
    assert h2.breadth30.missing.startswith("vendor revision counts null")  # never 0
    assert "missing (vendor revision counts null" in h2.text()
    assert rows[1].v["revenue_count"] is None


def test_off_calendar_mapping_by_period_end_names_a_disagreeing_label():
    """MSFT-like June year: on 2026-10-12 FY2026 (June) is reported; a vendor still labelling
    2026-06-30 'current fiscal year' is skipped by date, and the label named."""
    mk = estimates.EstRow
    rows = (
        mk("current fiscal year", "2026-06-30", {}, {}),
        mk("next fiscal year", "2027-06-30", {}, {}),
        mk("current fiscal quarter", "2026-09-30", {}, {}),
    )
    snap = estimates.Snap("MSFX", "2026-10-12", "u", rows)
    fy1, fy2, note = estimates.fiscal_years(snap, "2026-06-30", "2026-10-12")
    assert fy1.period_end == "2027-06-30" and fy2 is None
    assert "FY1 2027-06-30 is labelled 'next fiscal year'" in note


# --- the client: budget and key ---


def test_estimates_budget_is_its_own_share_and_the_key_limit_and_the_key_is_never_logged(dbs):
    engine, _ = dbs
    t = EstTransport({"IBM": IBM_RAW})
    c = client(engine, t)
    got = [c.estimates("IBM") for _ in range(4)]
    assert [isinstance(g, Ok) for g in got] == [True, True, True, False]
    assert got[3].throttled and "daily budget" in got[3].reason and len(t.calls) == 3
    assert all(call["apikey"] == KEY for call in t.calls)
    logged = engine.execute("SELECT url, detail FROM fetch_log").fetchall()
    assert all(KEY not in (r["url"] + (r["detail"] or "")) for r in logged)
    assert logged[0]["url"] == f"{URL}?function=EARNINGS_ESTIMATES&symbol=IBM"
    # transcripts keep their own 20: three estimate calls do not reduce them (D-M08-6)
    assert c.budget_left() == 20
    # a probe uses the spare: only the key's daily limit stops it
    assert c.budget_left("EARNINGS_ESTIMATES", DAILY_LIMIT) == DAILY_LIMIT - 3
    for _ in range(DAILY_LIMIT - 3):
        engine.execute(
            "INSERT INTO fetch_log (url, outcome, status, from_cache, detail, at) VALUES "
            "(?, 'ok', 200, 0, '', ?)",
            (f"{URL}?function=EARNINGS_CALL_TRANSCRIPT&symbol=X&quarter=2026Q1",
             "2026-10-13T15:00:00Z"),
        )  # fmt: skip
    assert c.budget_left() == 0 and isinstance(c.estimates("IBM", budget=DAILY_LIMIT), Failed)


# --- storage and rotation ---


def test_fetch_stores_every_field_records_no_coverage_and_stops_on_the_budget(dbs):
    engine, _ = dbs
    comps = {"IBMX": IBMX, "INFQ": "0002007825", "MU": MU, "NVDA": "0001045810",
             "ETV": "0001270523"}  # fmt: skip
    t = EstTransport({"IBMX": IBM_RAW, "MU": SIGN_RAW})
    dues, skipped = estimates.due(engine, comps, NOW, P, MF)
    assert [d.ticker for d in dues] == ["IBMX", "INFQ", "MU", "NVDA"]  # never asked, by name
    assert skipped == ["ETV: not asked (fund, D-M04-8)"]
    run = estimates.fetch(engine, client(engine, t), dues, NOW)
    assert run.asked == 3 and run.stored == ["IBMX (4 rows)", "MU (2 rows)"]
    assert run.no_coverage == ["INFQ"] and run.left == ["NVDA"]
    assert "daily budget" in run.stopped
    text = "\n".join(run.lines())
    assert "BUDGET STOP" in text and "left for the next run: NVDA" in text
    row = engine.execute(
        "SELECT * FROM estimate_snapshot WHERE cik = ? AND horizon = 'current fiscal year'",
        (IBMX,),
    ).fetchone()
    assert row["snapshot_date"] == "2026-10-13" and row["eps_avg"] == 12.3121
    assert row["rev_down_7d"] is None and json.loads(row["raw"])["date"] == "2026-12-31"
    assert KEY not in row["source_ref"]
    assert estimates.last_attempt(engine, "0002007825")["outcome"] == "no_coverage"
    # a week later IBMX and MU are due again; INFQ (no coverage) waits 4 weeks
    later = NOW + timedelta(days=7)
    assert [d.ticker for d in estimates.due(engine, comps, later, P, MF)[0]] == [
        "NVDA", "IBMX", "MU"
    ]  # fmt: skip
    assert "INFQ" in [d.ticker for d in estimates.due(engine, comps, NOW + timedelta(28), P, MF)[0]]
    # a rerun on the same day replaces that day's rows
    estimates.fetch(engine, client(engine, EstTransport({"IBMX": IBM_RAW})),
                    [estimates.Due("IBMX", IBMX)], NOW, budget=DAILY_LIMIT)  # fmt: skip
    n = engine.execute("SELECT count(*) FROM estimate_snapshot WHERE cik = ?", (IBMX,)).fetchone()
    assert n[0] == 4


def test_refresh_hook_reports_a_missing_key_and_nothing_due(dbs):
    engine, _ = dbs
    lines = estimates.run_fetch_part(
        engine, None, {"IBMX": IBMX}, NOW, mf=NO_MODELS,
        no_client_reason="ALPHA_VANTAGE_API_KEY is not set",
    )  # fmt: skip
    assert "skipped — ALPHA_VANTAGE_API_KEY is not set; due: IBMX" in lines[1]
    put(engine, IBMX, "IBMX", IBM_RAW, "2026-10-12")
    lines = estimates.run_fetch_part(engine, client(engine, EstTransport({})), {"IBMX": IBMX},
                                     NOW, mf=NO_MODELS)  # fmt: skip
    assert "nothing due" in lines[1]


def test_refresh_runs_estimates_after_the_transcripts():
    src = (ROOT / "scripts" / "run_refresh.py").read_text(encoding="utf-8")
    calls = src.index("calls = calls_step(engine, corpus, report)")
    est = src.index("calls += estimates_step(engine, report)")
    money = src.index("calls += money_step(client, engine, corpus, report)")
    assert calls < est < money


# --- next report and the walk-down window (grade C) ---


def test_cadence_from_periodic_reports_and_the_walk_down_window(dbs):
    engine, _ = dbs
    a = "0000000502"
    quarterly_co(engine, a, "CADX")  # 10-Qs 40 days after quarter end, last 2026-06-30
    nr = calendar.next_report(engine, a, "2026-10-09")
    assert (nr.quarter, nr.day, nr.grade) == ("FY2026 Q3", "2026-11-09", "C")
    assert "lag 40 days as FY2025 Q3" in nr.basis and "periodic reports" in nr.basis
    assert calendar.walk_down(nr, "2026-10-09", 30)[0] is False  # 31 days
    on, text = calendar.walk_down(calendar.next_report(engine, a, "2026-10-12"), "2026-10-12")
    assert on is True and "walk-down window (28 days ≤ 30†)" in text
    late = calendar.next_report(engine, a, "2026-11-20")
    assert late.overdue and calendar.walk_down(late, "2026-11-20")[0] is True
    stale = calendar.next_report(engine, a, "2027-01-15")
    assert stale.day is None and stale.missing.startswith("cadence stale")
    assert calendar.walk_down(stale, "2027-01-15")[0] is None


def test_cadence_prefers_earnings_8ks_and_needs_a_fiscal_year_end(dbs):
    engine, _ = dbs
    a = "0000000503"
    quarterly_co(engine, a, "RELX")
    for acc, filed in (("r-25q3", "2025-10-22"), ("r-25q4", "2026-01-28"), ("r-26q1", "2026-04-22"),
                       ("r-26q2", "2026-07-22")):  # fmt: skip
        engine.execute(
            "INSERT INTO filing (accession, cik, form, filed, items, ingested_at) VALUES "
            "(?, ?, '8-K', ?, '2.02,9.01', 'n')",
            (acc, a, filed),
        )
        engine.execute("INSERT INTO filing_cik (accession, cik) VALUES (?, ?)", (acc, a))
    nr = calendar.next_report(engine, a, "2026-10-01")
    assert nr.day == "2026-10-22" and "earnings 8-Ks" in nr.basis and nr.n == 4
    assert calendar.next_report(engine, "0000000999", "2026-10-01").missing == (
        "no fiscal year end stored"
    )


# --- forward P/E, PEG and est_revision in the pass ---


def test_ibm_forward_pe_peg_and_est_revision_rows(dbs):
    engine, _ = dbs
    ibm_co(engine)
    put(engine, IBMX, "IBMX", IBM_RAW, "2026-10-09")
    vp = step.valuation_pass(engine, {"IBMX": IBMX}, NOW, mf=NO_MODELS)
    assert not vp.errors
    fwd = rows_of(engine, IBMX, "val_pe_fwd")[0]
    assert fwd["value"] == pytest.approx(20.0) and fwd["evidence_grade"] == "B"
    assert "vendor basis, non-GAAP" in fwd["method"] and "no quarter-end history" in fwd["method"]
    pg = rows_of(engine, IBMX, "peg")[0]
    assert pg["value"] == pytest.approx(20 / ((13.1512 / 12.3121 - 1) * 100))
    assert round(pg["value"], 1) == 2.9 and pg["value_text"] == ">2"
    assert "g = FY2 2027-12-31 13.1512 ÷ FY1 2026-12-31 12.3121 − 1 = 6.8%" in pg["method"]
    assert "trailing 3-year GAAP EPS CAGR" in pg["method"] and pg["evidence_grade"] == "B"
    assert rows_of(engine, IBMX, "peg", "ST")[0]["method"].endswith("info (weight 0)")
    er = rows_of(engine, IBMX, "est_revision")[0]
    assert er["value"] == pytest.approx(-0.0698, abs=1e-3) and er["value_text"] == "flat"
    assert "dispersion 4.5%" in er["method"] and "count 23" in er["method"]
    assert "breadth 30 d +0.04" in er["method"] and "MY weight low (M01)" in er["method"]
    assert not rows_of(engine, IBMX, "est_revision", "MY")[0]["method"].endswith("(weight 0)")
    assert er["source_ref"] == "AV-EST-IBMX-2026-10-09"
    assert any("est_revision: flat 1" in x for x in step.summary_lines(vp))


def test_a_snapshot_after_the_close_is_not_used_and_an_old_one_is_missing(dbs):
    engine, _ = dbs
    ibm_co(engine)
    put(engine, IBMX, "IBMX", IBM_RAW, "2026-10-12")  # fetched after the 2026-10-09 close
    r = step.evaluate(engine, "IBMX", IBMX, "2026-10-09", TODAY, P, NO_MODELS, with_peers=False)
    er = next(o for o in r.rows if o.signal == "est_revision")
    assert er.missing == "no estimate snapshot on or before 2026-10-09 (first 2026-10-12)"
    assert next(o for o in r.rows if o.signal == "peg").missing.startswith("no estimate snapshot")
    live = step.evaluate(
        engine, "IBMX", IBMX, "2026-10-09", TODAY, P, NO_MODELS, with_peers=False, est_upto=TODAY
    )  # fmt: skip (the tab's reading)
    assert next(o for o in live.rows if o.signal == "est_revision").text == "flat"
    put(engine, IBMX, "IBMX", IBM_RAW, "2026-09-01")
    r = step.evaluate(engine, "IBMX", IBMX, "2026-10-09", TODAY, P, NO_MODELS, with_peers=False)
    er = next(o for o in r.rows if o.signal == "est_revision")
    assert er.missing == "estimate snapshot 2026-09-01 is 38 days old (> 28)"


def _peg_for(engine, cik, ticker, raw, *, mf=NO_MODELS, day="2026-10-09"):
    put(engine, cik, ticker, raw, day)
    r = step.evaluate(engine, ticker, cik, day, TODAY, P, mf, with_peers=False)
    return r, next(o for o in r.rows if o.signal == "peg")


def test_peg_reason_codes_first_failing_check_wins(dbs):
    engine, _ = dbs
    # growth above the cap: uncapped PEG in method, not scored
    a = "0000000504"
    annual_co(engine, a, "RAMP", [base(2024), base(2025)], close=100.0)
    hi = json.loads(IBM_RAW)
    hi["estimates"][0]["eps_estimate_average"] = "20.0000"  # FY2 20 vs FY1 12.3121: g 62%
    r, o = _peg_for(engine, a, "RAMP", json.dumps(hi).encode())
    assert o.text == "growth_above_cap" and o.value is None and "(uncapped, not scored)" in o.method
    assert "R6 sales fallback: EV/Sales" in o.method and o.info == step.INFO_ALL
    # growth ≤ 0
    b = "0000000505"
    annual_co(engine, b, "FLAT", [base(2024), base(2025)], close=100.0)
    lo = json.loads(IBM_RAW)
    lo["estimates"][0]["eps_estimate_average"] = "12.0000"
    assert _peg_for(engine, b, "FLAT", json.dumps(lo).encode())[1].text == "growth_nonpositive"
    # TTM GAAP EPS ≤ 0 comes before growth; both named
    c = "0000000506"
    annual_co(engine, c, "LOSS", [base(2024), base(2025, ni=-10)], close=100.0)
    r, o = _peg_for(engine, c, "LOSS", json.dumps(lo).encode())
    assert (
        o.text == "eps_nonpositive"
        and "failing checks: eps_nonpositive, growth_nonpositive" in (o.method)
    )
    # FY1 consensus ≤ 0: no growth base; forward P/E not meaningful
    d = "0000000507"
    annual_co(engine, d, "BASE", [base(2024), base(2025)], close=100.0)
    neg = json.loads(IBM_RAW)
    neg["estimates"][1]["eps_estimate_average"] = "-1.0000"
    r, o = _peg_for(engine, d, "BASE", json.dumps(neg).encode())
    assert o.text == "base_nonpositive" and r.snap.m("val_pe_fwd").text == "not_meaningful"
    # no FY2 row in the snapshot → growth_missing (a coded row on the snapshot)
    e = "0000000508"
    annual_co(engine, e, "ONEY", [base(2024), base(2025)], close=100.0)
    one = json.loads(IBM_RAW)
    one["estimates"] = one["estimates"][1:]
    assert _peg_for(engine, e, "ONEY", json.dumps(one).encode())[1].text == "growth_missing"


def test_peg_cyclical_for_mu_and_fair_value_for_mstr(dbs):
    engine, _ = dbs
    load_mu(engine)
    r, o = _peg_for(engine, MU, "MU", SIGN_RAW, day="2025-10-03")
    assert o.text == "cyclical" and "cyclical flag: cyclical" in o.method
    er = next(x for x in r.rows if x.signal == "est_revision")
    assert er.text == "not_meaningful" and "[sign change]" in er.method
    assert "coverage: 2 analyst(s) (low coverage)" in er.method
    ms = "0001050446"
    annual_co(engine, ms, "MSTR", [base(2024), base(2025)], close=300.0)
    r, o = _peg_for(engine, ms, "MSTR", IBM_RAW, mf=MF)
    assert o.text == "fair_value_earnings"
    assert r.snap.m("val_pe_fwd").text == "fair_value_earnings"


def test_fund_rows_are_not_applicable_and_no_snapshot_is_missing(dbs):
    engine, _ = dbs
    etv = "0001270523"
    annual_co(engine, etv, "ETV", [base(2024), base(2025)])
    r = step.evaluate(engine, "ETV", etv, "2026-10-09", TODAY, P, MF, with_peers=False)
    for sig in ("val_pe_fwd", "peg", "est_revision"):
        o = next(x for x in r.rows if x.signal == sig)
        assert o.missing == "not applicable (fund, D-M04-8)"
    ibm_co(engine)
    r = step.evaluate(engine, "IBMX", IBMX, "2026-10-09", TODAY, P, NO_MODELS, with_peers=False)
    o = next(x for x in r.rows if x.signal == "est_revision")
    assert o.missing == "no estimate snapshot (budget / no coverage)"
    assert r.snap.m("val_pe_fwd").missing == "no estimate snapshot (budget / no coverage)"


def test_trailing_cagr_is_shown_never_substituted(dbs):
    engine, _ = dbs
    ys = [base(2022, ni=50), base(2023, ni=60), base(2024, ni=70), base(2025, ni=80)]
    annual_co(engine, IBMX, "IBMX", ys, close=IBM_CLOSE)
    put(engine, IBMX, "IBMX", IBM_RAW, "2026-10-09")
    r = step.evaluate(engine, "IBMX", IBMX, "2026-10-09", TODAY, P, NO_MODELS, with_peers=False)
    assert "trailing 3-year GAAP EPS CAGR 17.0% (EPS 0.50 at 2022-12-31 → 0.80 at 2025-12-31)" in (
        r.cagr
    )
    assert r.peg.g == pytest.approx((13.1512 / 12.3121 - 1) * 100)  # vendor growth, not CAGR


def test_trailing_cagr_scales_shares_from_the_stating_filing_not_the_period_end(dbs):
    # live check 1 (NVDA FY2023 EPS read 0.02): a later 10-K restates the older year's share
    # count after a split, so scaling it again from the period end applied the split twice
    from tests.test_valuation import bars, fact

    engine, _ = dbs
    a = "0000000401"
    ys = [base(2022, dil=100), base(2023, dil=100), base(2024, dil=1000), base(2025, dil=1000)]
    annual_co(engine, a, "SPLT", ys)
    bars(engine, a, "SPLT", [("2024-06-10", 50.0, None, 10.0)])
    # the FY2024 10-K (filed after the 2024-06-10 ×10 split) restates FY2022 at 1,000M
    fact(engine, a, "WeightedAverageNumberOfDilutedSharesOutstanding", "2022-01-01",
         "2022-12-31", 1000 * M_, "2025-02-15", unit="shares",
         acc="0000000401-25-000001")  # fmt: skip
    r = step.evaluate(engine, "SPLT", a, "2026-10-09", TODAY, P, NO_MODELS, with_peers=False)
    assert "trailing 3-year GAAP EPS CAGR 0.0% (EPS 0.08 at 2022-12-31 → 0.08 at 2025-12-31)" in (
        r.cagr
    )


M_ = 1_000_000


def test_forward_pe_helper_and_bands():
    m = peg.forward_pe(None, None, treasury=False, sources=[])
    assert m.missing == "no close"
    assert [peg.band(x) for x in (0.8, 1.0, 1.5, 2.0, 2.9)] == ["≤1", "≤1", "1–2", "1–2", ">2"]


# --- the script and the tab ---


def test_script_estimates_probe_and_no_sec_on_an_injected_db(dbs, tmp_path):
    engine, _ = dbs
    rv = load_script("run_valuation")
    ibm_co(engine)
    t = EstTransport({"IBMX": IBM_RAW})
    log = rv.Log(tmp_path / "logs" / "e.txt")
    comps = {"IBMX": IBMX, "INFQ": "0002007825"}
    args = argparse.Namespace(subcommand="estimates", no_sec=False, probe="IBMX,INFQ,NOPE",
                              tickers=None, companies=comps)  # fmt: skip
    assert rv.run_estimates(args, log, tmp_path, engine=engine, now=NOW,
                            client=client(engine, t)) == 0  # fmt: skip
    log.close()
    text = (tmp_path / "logs" / "e.txt").read_text(encoding="utf-8")
    assert "NOPE: no CIK stored" in text and len(t.calls) == 2
    assert "IBMX: 4 rows (2 fiscal-year, 2 quarter)" in text
    assert "2026-12-31 'current fiscal year': avg EPS 12.3121, count 23; null: " in text
    assert "eps_estimate_revision_down_trailing_7_days" in text
    assert "INFQ: no snapshot today — no_coverage: no coverage: empty reply" in text
    assert "IBMX 2026-10-09: forward P/E" in text and "=== Summary" in text
    assert "Alpha Vantage requests: 2 · key used in the last 24 h: 2/25" in text
    assert KEY not in text
    log = rv.Log(tmp_path / "logs" / "n.txt")
    args.no_sec, args.probe = True, None
    assert rv.run_estimates(args, log, tmp_path, engine=engine, now=NOW) == 0
    log.close()
    text = (tmp_path / "logs" / "n.txt").read_text(encoding="utf-8")
    assert "Alpha Vantage requests: 0" in text and "est_revision" in text


def test_valuation_tab_shows_the_estimates_block(tmp_path, monkeypatch):
    def fill(engine):
        ibm_co(engine)
        put(engine, IBMX, "IBMX", IBM_RAW, "2026-10-12")
        filing(engine, IBMX, "q-26", "10-Q", "2026-08-05", "2026-06-30")
        step.valuation_pass(engine, {"IBMX": IBMX}, NOW, mf=NO_MODELS)

    c = _app(tmp_path, monkeypatch, fill, ["IBMX"])
    html = c.get("/c/IBMX?tab=valuation").text
    assert "built-in method" not in html and "object at 0x" not in html
    assert "Estimates (Alpha Vantage consensus, vendor basis, grade B)" in html
    assert "2026-10-12 (AV-EST-IBMX-2026-10-12)" in html and "Forward P/E (vendor basis)" in html
    assert "current fiscal year" in html and "Rev. 30 d" in html
    assert "-0.07%" in html and "4.5%" in html and "&gt;2" in html
    assert "next report" in html
