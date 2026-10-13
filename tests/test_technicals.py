"""M09 Part 1: completed weekly bars, bands, trend, momentum, reversal, news moves, the M01
rule readers, the pass and its script (docs/M09_TECHNICALS.md; fixtures README in
tests/fixtures/m09/)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from engine import m01_rules
from engine.financials import models
from engine.prices.store import BENCHMARK, with_benchmark
from engine.signals import Source, write_signal
from engine.technicals import bands, bars, earnings, params, signals, step
from engine.technicals.params import Params

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures" / "m09"
NOW = datetime(2026, 10, 13, 16, 0, tzinfo=UTC)  # Tuesday 12:00 US Eastern
TODAY = date(2026, 10, 13)
LAST_FRIDAY = "2026-10-09"
P = Params()
MU = "0000723125"
NVDA = "0001045810"
MSTR = "0001050446"
INFQ = "0002007825"
SPCX = "0001181412"
NO_MODELS = models.ModelFile("none", ())


# --- helpers -------------------------------------------------------------------------------


def put_daily(engine, symbol, rows, *, cik=None, raw=None, full_at="2026-01-02T00:00:00+00:00"):
    """rows: (date, adjusted close); raw closes default to the adjusted ones."""
    raw = raw or {}
    engine.executemany(
        "INSERT OR REPLACE INTO price_bar (symbol, date, close, adj_open, adj_high, adj_low, "
        "adj_close, adj_volume, source, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'tiingo', "
        "'2026-10-13T00:00:00+00:00')",
        [(symbol, d, raw.get(d, c), c, c * 1.01, c * 0.99, c, 1000) for d, c in rows],
    )
    span = engine.execute("SELECT min(date), max(date), count(*) FROM price_bar WHERE symbol = ?",
                          (symbol,)).fetchone()  # fmt: skip
    engine.execute(
        "INSERT OR REPLACE INTO price_fetch (symbol, cik, first_date, last_date, bars, "
        "last_outcome, full_fetched_at) VALUES (?, ?, ?, ?, ?, 'ok', ?)",
        (symbol, cik, span[0], span[1], span[2], full_at),
    )


def week_rows(closes, last_friday=LAST_FRIDAY, *, skip=()):
    """Daily rows: every session of week i at closes[i]; week i ends on its Friday."""
    fri = date.fromisoformat(last_friday)
    out = []
    for i, c in enumerate(closes):
        f = fri - timedelta(weeks=len(closes) - 1 - i)
        for k in range(5):
            d = (f - timedelta(days=4 - k)).isoformat()
            if d not in skip:
                out.append((d, c))
    return out


PARTIAL = [("2026-10-12", 1.0), ("2026-10-13", 1.0)]


def put_weeks(engine, symbol, closes, *, cik=None, partial=True, **kw):
    rows = week_rows(closes, **kw)
    if partial:
        rows += [(d, closes[-1] * 0.5) for d, _ in PARTIAL]  # a partial week far off the band
    put_daily(engine, symbol, rows, cik=cik)


def m04(engine, cik, gate="pass", *, filing="current", cvd=None, runway_method=None,
        cvd_method="cvd", as_of="2026-08-01"):  # fmt: skip
    src = [Source("0000000000-26-000001", as_of)]
    if gate is not None:
        write_signal(engine, cik=cik, module_id="M04", signal="survival_gate", as_of=as_of,
                     value_text=gate, method="gate", sources=src)  # fmt: skip
    if filing is not None:
        write_signal(engine, cik=cik, module_id="M04", signal="filing_status", as_of=as_of,
                     value_text=filing, method="status", sources=src)  # fmt: skip
    if cvd == "missing":
        write_signal(engine, cik=cik, module_id="M04", signal="cvd_state", as_of=as_of,
                     method="", missing="not applicable (fund)")  # fmt: skip
    elif cvd is not None:
        write_signal(engine, cik=cik, module_id="M04", signal="cvd_state", as_of=as_of,
                     value_text=cvd, method=cvd_method, sources=src)  # fmt: skip
    if runway_method is not None:
        write_signal(engine, cik=cik, module_id="M04", signal="runway_q", as_of=as_of,
                     value=5.0, method=runway_method, sources=src)  # fmt: skip


def event(engine, cik, filed, accepted, *, acc="0000000000-26-000100", item="2.02",
          category="earnings", form="8-K"):  # fmt: skip
    engine.execute(
        "INSERT INTO event (accession, item, cik, form, filed, accepted_at, report_date, "
        "category, severity, title, modules, amended, catalog) VALUES (?, ?, ?, ?, ?, ?, NULL, "
        "?, 'medium', 'Results', '[\"M04\"]', 0, 'test')",
        (acc, item, cik, form, filed, accepted, category),
    )


def rows(engine, cik, signal=None, tf="MY"):
    sql = "SELECT * FROM signal WHERE cik = ? AND module_id = 'M09' AND timeframe = ?"
    args = [cik, tf]
    if signal:
        sql += " AND signal = ?"
        args.append(signal)
    return engine.execute(sql + " ORDER BY signal, as_of", args).fetchall()


def infq_models():
    entry = {
        "ticker": "INFQ",
        "cik": INFQ,
        "tag": "spac_shell",
        "before": "2026-02-13",
        "reason": "r",
        "source": "s",
    }
    return models.parse({"company": [entry]})


def run_pass(engine, companies, *, mf=NO_MODELS, now=NOW):
    return step.technicals_pass(engine, companies, now, params=P, mf=mf)


def uptrend(n, start=100.0, g=1.01, wiggle=0.01):
    """A steady trend with a small deterministic wiggle (real returns are never constant)."""
    return [start * g**k * (1 + wiggle * math.sin(k)) for k in range(n)]


# --- parameters ----------------------------------------------------------------------------


def test_config_file_equals_the_built_in_v1_defaults():
    assert params.load(ROOT / "config" / "technicals.toml") == Params()
    assert P.mom_min_bars == 53 and P.rev_min_bars == 31 and P.trend_min_bars == 45


def test_params_reject_unknown_keys_and_fall_back(tmp_path):
    with pytest.raises(params.ParamsError, match="unknown key"):
        params.parse({"version": "v1", "band": {"window": 20}})
    with pytest.raises(params.ParamsError, match="positive whole"):
        params.parse({"version": "v1", "band": {"window_weeks": 2.5}})
    bad = tmp_path / "t.toml"
    bad.write_text('version = "v2"\n[trend]\nma_weeks = "forty"\n', encoding="utf-8")
    p, note = params.load_safe(bad)
    assert p == Params() and "must be a number" in note


# --- completed weekly bars (rule 1) ----------------------------------------------------------


def test_eastern_date_and_week_completion():
    assert bars.eastern_today(datetime(2026, 10, 10, 2, 0, tzinfo=UTC)) == date(2026, 10, 9)
    cal = bars.Calendar(["2026-10-05", "2026-10-09"], date(2026, 10, 9))  # Friday itself
    assert not cal.week_complete(date(2026, 10, 5))
    cal = bars.Calendar(["2026-10-05", "2026-10-09"], date(2026, 10, 10))  # Saturday
    assert cal.week_complete(date(2026, 10, 5))
    assert cal.expected_as_of() == "2026-10-09"


def test_partial_current_week_is_excluded_and_bar_keyed_by_last_session(dbs):
    engine, _ = dbs
    put_weeks(engine, "AAA", [10.0, 11.0, 12.0])
    w = bars.weekly(engine, "AAA", TODAY)
    assert [b.date for b in w.bars] == ["2026-09-25", "2026-10-02", "2026-10-09"]
    assert w.bars[-1].close == 12.0 and w.bars[-1].monday == "2026-10-05"
    assert w.dropped and "week of 2026-10-12: not complete" in w.dropped[0]
    assert not w.stale and w.last_daily == "2026-10-13"


def test_holiday_friday_keys_the_week_on_thursday_once_confirmed(dbs):
    engine, _ = dbs
    # Good Friday 2026-04-03: the week's last session is Thursday 04-02
    rows_ = week_rows([20.0, 21.0], "2026-04-03", skip={"2026-04-03"})
    put_daily(engine, "AAA", rows_)
    w = bars.weekly(engine, "AAA", date(2026, 4, 6))  # Monday, next week not stored yet
    assert [b.date for b in w.bars] == ["2026-03-27"]  # holiday week not confirmed yet
    put_daily(engine, "AAA", rows_ + [("2026-04-06", 22.0)])
    w = bars.weekly(engine, "AAA", date(2026, 4, 7))
    assert w.bars[-1].date == "2026-04-02" and w.bars[-1].close == 21.0
    assert w.bars[-1].sessions == 4


def test_missing_days_are_not_filled(dbs):
    engine, _ = dbs
    put_daily(engine, "AAA", week_rows([5.0, 6.0], skip={"2026-10-07", "2026-10-08"}))
    put_daily(engine, "BBB", week_rows([1.0, 1.0]))
    w = bars.weekly(engine, "AAA", TODAY)
    assert w.bars[-1].sessions == 3 and w.bars[-1].date == "2026-10-09"


def test_tracked_name_not_fetched_to_the_week_end_shows_the_older_week(dbs):
    engine, _ = dbs
    put_weeks(engine, "CORE", [1.0] * 3)  # the calendar has Friday 10-09
    put_daily(engine, "TRK", week_rows([3.0, 4.0, 5.0], skip={"2026-10-08", "2026-10-09"}))
    w = bars.weekly(engine, "TRK", TODAY)
    assert w.as_of == "2026-10-02"
    assert any("2026-10-09 not fetched" in d for d in w.dropped)


def test_stale_after_five_days(dbs):
    engine, _ = dbs
    put_daily(engine, "AAA", week_rows([5.0, 6.0], "2026-10-02"))
    assert bars.weekly(engine, "AAA", date(2026, 10, 7)).stale is False  # 5 days
    w = bars.weekly(engine, "AAA", date(2026, 10, 8))
    assert w.stale and w.stale_days == 6


def test_shell_cut_off_drops_infq_bars_before_the_close(dbs):
    engine, _ = dbs
    mf = infq_models()
    assert bars.shell_cut_off(mf, INFQ, "INFQ") == "2026-02-13"
    assert bars.shell_cut_off(mf, MSTR, "MSTR") is None
    put_weeks(engine, "INFQ", [10.0] * 60)
    w = bars.weekly(engine, "INFQ", TODAY, cut_off="2026-02-13")
    assert w.bars[0].date >= "2026-02-13" and w.cut_bars > 0
    assert w.bars[0].date == "2026-02-13"  # the Friday of the closing week


def test_split_adjusted_closes_are_used(dbs):
    engine, _ = dbs
    closes = uptrend(30)
    rows_ = week_rows(closes)
    raw = {d: c * (2 if d < "2026-08-01" else 1) for d, c in rows_}  # 2:1 split on raw only
    put_daily(engine, "AAA", rows_, raw=raw)
    w = bars.weekly(engine, "AAA", TODAY)
    assert w.closes() == closes
    b = bands.band_at(w.closes())
    assert b.z > 0  # a steady rise, no false crash from the raw split


# --- bands (D27, D-M09-2) -----------------------------------------------------------------


def test_band_z_known_answer_sqrt19():
    closes = [1.0] * 19 + [math.exp(0.5)]
    b = bands.band_at(closes)
    assert b.z == pytest.approx(math.sqrt(19))
    closes = [50.0] * 19 + [60.0]
    b = bands.band_at(closes)
    assert b.z_price == pytest.approx(math.sqrt(19))
    lv = b.levels()
    assert lv["mean"] == pytest.approx(50.5)
    assert lv["+1"] - lv["mean"] == pytest.approx(statistics.pstdev(closes))
    assert lv["-2"] == pytest.approx(50.5 - 2 * statistics.pstdev(closes))


def test_pullback_sigma_known_answer_minus_one():
    r = 0.05
    closes = [100.0 * (math.exp(r) if k % 2 else 1.0) for k in range(21)]
    b = bands.band_at(closes)
    assert b.sigma_w == pytest.approx(r)
    assert b.high == pytest.approx(100 * math.exp(r))
    assert b.pullback_sigma == pytest.approx(-1.0)
    assert bands.band_at(closes[1:]).pullback_sigma is None  # 20 closes: 19 returns only


def test_band_matches_an_independent_computation_and_history():
    closes = [100 + 10 * math.sin(k / 3) + k for k in range(40)]
    b = bands.band_at(closes)
    logs = [math.log(c) for c in closes[-20:]]
    assert b.z == pytest.approx((logs[-1] - statistics.fmean(logs)) / statistics.pstdev(logs))
    hist = bands.band_history(closes)
    assert hist[18] is None and hist[-1] == b


def test_constant_returns_give_no_return_z():
    closes = [100 * 1.01**k for k in range(40)]  # σ of returns is rounding noise only
    b = bands.band_at(closes)
    assert b.z is not None and b.pullback_sigma is None and b.sigma_w is None
    assert signals.rev_at(closes, P) is None


def test_zone_edges_and_flat_prices():
    assert [bands.zone(z) for z in (-2.66, -2.0, -1.5, -1.0, 0.0, 1.0, 1.99, 2.0)] == [
        "below_2",
        "below_2",
        "below_1",
        "below_1",
        "inside",
        "above_1",
        "above_1",
        "above_2",
    ]
    assert bands.band_at([5.0] * 20).z is None
    assert bands.band_at([5.0] * 19) is None


# --- trend, momentum, reversal ---------------------------------------------------------------


def test_trend_steady_up_and_crash_down():
    up = signals.trend_at(uptrend(60), P)
    assert (up.state, up.value, up.position, up.pending) == ("up", 1, "above", False)
    down = signals.trend_at(uptrend(60, g=0.98), P)
    assert (down.state, down.value, down.position) == ("down", -1, "below")
    assert signals.trend_at(uptrend(44), P) is None


def test_trend_flips_after_two_closes_and_reads_flat_while_the_ma_rises():
    closes = uptrend(50, g=1.005)
    one = signals.trend_at(closes + [110.0], P)
    assert one.ma > 110.0 and one.position == "above" and one.pending
    assert one.state == "up"  # one close below: pending flip only
    two = signals.trend_at(closes + [110.0, 110.0], P)
    assert two.position == "below" and not two.pending
    assert two.slope > P.slope_tolerance and two.state == "flat"  # SPY 2026-03-23 case


def test_mom_12_1_known_answer():
    closes = [float(k) for k in range(1, 61)]
    assert signals.mom_12_1(closes, P) == pytest.approx(56 / 8 - 1)
    assert signals.mom_12_1(closes[:52], P) is None


def rev_closes(R=0.25, r=0.05):
    sigma = [100.0 * (math.exp(r) if k % 2 else 1.0) for k in range(27)]  # 26 returns, σ = r
    return sigma + [100 * math.exp(R * j / 4) for j in (1, 2, 3, 4)]


def test_rev_1m_known_answer():
    rv = signals.rev_at(rev_closes(), P)
    assert rv.sigma_w == pytest.approx(0.05)
    assert rv.ret == pytest.approx(0.25)
    assert rv.z == pytest.approx(2.5)
    assert signals.rev_at(rev_closes()[1:], P) is None  # 30 closes


# --- earnings in the window (rule 7) --------------------------------------------------------


def test_earnings_window_with_after_close_shift(dbs):
    engine, _ = dbs
    event(engine, NVDA, "2026-09-11", "2026-09-11T16:20:00.000Z", acc="A-base-after")
    event(engine, NVDA, "2026-09-11", "2026-09-11T08:00:00.000Z", acc="B-base-day")
    event(engine, NVDA, "2026-10-09", "2026-10-09T16:05:00.000Z", acc="C-end-after")
    event(engine, NVDA, "2026-10-09", "2026-10-09T09:00:00.000Z", acc="D-end-day")
    event(engine, NVDA, "2026-09-20", None, acc="E-no-time")
    event(engine, NVDA, "2026-09-21", "2026-09-21T09:00:00.000Z", acc="F-6k", item="6-K",
          category="foreign_report", form="6-K")  # fmt: skip
    got = earnings.earnings_in_window(engine, NVDA, "2026-09-11", "2026-10-09")
    assert [c.accession for c in got] == ["A-base-after", "E-no-time", "D-end-day"]
    assert got[0].after_close and "after the close" in got[0].text()
    assert [c.accession for c in earnings.foreign_reports_in_window(
        engine, NVDA, "2026-09-11", "2026-10-09")] == ["F-6k"]  # fmt: skip
    assert earnings.accepted_clock("bad") is None


# --- M01 rule readers -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("gate", "filing", "cvd", "state"),
    [
        ("pass", "current", "CYCLICAL_TROUGH", "qualified"),
        ("warn", "current", "NO_SLOWDOWN", "qualified"),
        ("warn", "stale", "AMBIGUOUS", "qualified"),
        ("pass", "current", "STRUCTURAL_DECLINE", "not_qualified"),
        ("pass", "current", "CYCLE_PLUS_DAMAGE", "not_qualified"),
        ("fail", "current", "CYCLICAL_TROUGH", "not_qualified"),
        ("incomplete", "current", None, "not_qualified"),
        ("not_applicable", "current", "missing", "not_qualified"),
        ("pass", "overdue", "CYCLICAL_TROUGH", "not_qualified"),
        ("pass", "current", None, "incomplete"),
        ("pass", "current", "missing", "incomplete"),
        (None, "current", None, "incomplete"),
    ],
)
def test_rule1_qualification(dbs, gate, filing, cvd, state):
    engine, _ = dbs
    m04(engine, MU, gate, filing=filing, cvd=cvd)
    r = m01_rules.rule1(m01_rules.read_m04(engine, MU, as_of="2026-10-09"))
    assert r.state == state, r.text


def test_rule1_texts_and_tracked_names(dbs):
    engine, _ = dbs
    m04(engine, MU, "warn")
    rd = m01_rules.read_m04(engine, MU)
    assert "cvd_state missing: Part 8a not built" in m01_rules.rule1(rd).text
    assert m01_rules.m04_line(rd).startswith("gate warn (2026-08-01), filing current")
    trk = m01_rules.read_m04(engine, MU, covered=False)
    assert m01_rules.rule1(trk).text.startswith("qualification: not covered by M04 (D-M04-80)")


def test_rule7_strength_needs_trough_gate_and_no_runway_review(dbs):
    engine, _ = dbs
    m04(engine, MU, "warn", cvd="CYCLICAL_TROUGH")
    assert m01_rules.rule7(m01_rules.read_m04(engine, MU)).state == "stronger"
    m04(
        engine,
        NVDA,
        "pass",
        cvd="CYCLICAL_TROUGH",
        runway_method="tier capex; capex-funded review open (m04_runway): rule-7 strength blocked",
    )
    assert m01_rules.rule7(m01_rules.read_m04(engine, NVDA)).state == "warning"
    m04(engine, MSTR, "pass", cvd="NO_SLOWDOWN")
    r = m01_rules.rule7(m01_rules.read_m04(engine, MSTR))
    assert r.state == "warning" and "CvD NO_SLOWDOWN" in r.text
    m04(engine, INFQ, "pass")
    assert "cvd_state missing" in m01_rules.rule7(m01_rules.read_m04(engine, INFQ)).text


def test_rule3_and_rule4_readings(dbs):
    engine, _ = dbs
    m04(engine, MU, "pass", cvd="STUMBLE")
    assert m01_rules.rule3(m01_rules.read_m04(engine, MU)).state == "blocked"
    m04(engine, NVDA, "pass", cvd="STUMBLE", cvd_method="owner answer STUMBLE (computed X)")
    assert m01_rules.rule3(m01_rules.read_m04(engine, NVDA)).state == "allowed"
    m04(engine, MSTR, "fail", filing="overdue", cvd="STRUCTURAL_DECLINE")
    rd = m01_rules.read_m04(engine, MSTR)
    assert m01_rules.rule3(rd).state == "blocked"
    assert m01_rules.rule4(rd) == ["survival gate fail (S6.14)", "filing overdue (D-M04-61)",
                                   "CvD STRUCTURAL_DECLINE (M01 rule 4, S6.14)"]  # fmt: skip


# --- the pass (rows, missing rows, SPY) ------------------------------------------------------


def test_pass_writes_five_rows_per_timeframe_with_info_and_sources(dbs):
    engine, _ = dbs
    put_weeks(engine, "NVDA", uptrend(60), cik=NVDA)
    m04(engine, NVDA, "pass")
    tp = run_pass(engine, {"NVDA": NVDA})
    assert not tp.errors and tp.expected_as_of == LAST_FRIDAY
    got = {r["signal"]: r for r in rows(engine, NVDA)}
    assert set(got) == set(signals.SIGNALS)
    for r in got.values():
        assert r["as_of"] == LAST_FRIDAY and r["evidence_grade"] == "A"
        assert r["source_ref"] == f"Tiingo adj_close {LAST_FRIDAY}"
        assert " v1" in r["method"] and r["ticker"] == "NVDA"
    assert got["band_z"]["value_text"] == "above_1"  # steady rise: top of the log band
    assert "upper extreme — information" in got["band_z"]["method"]
    assert "qualification incomplete (cvd_state missing: Part 8a not built" in \
        got["band_z"]["method"]  # fmt: skip
    assert got["trend_state"]["value"] == 1 and got["trend_state"]["value_text"] == "up"
    assert got["mom_12_1"]["value_text"] == "positive"
    assert got["price_band"]["value_text"] is None and got["price_band"]["value"] > 0
    assert "display only" in got["price_band"]["method"] and "+2σ" in got["price_band"]["method"]
    assert "turnover not checked (deferred)" in got["rev_1m"]["method"]
    assert "SPY: missing: SPY not stored" in got["trend_state"]["method"]
    info = {(r["signal"], r["timeframe"]) for r in rows_all(engine, NVDA)
            if r["method"].endswith("info (weight 0)")}  # fmt: skip
    assert info == {("band_z", "PT"), ("band_z", "ST"), ("price_band", "MY"),
                    ("price_band", "PT"), ("price_band", "ST"), ("trend_state", "ST"),
                    ("mom_12_1", "MY"), ("mom_12_1", "ST"), ("rev_1m", "MY"),
                    ("rev_1m", "PT")}  # fmt: skip
    # the partial current week (closes at half the price) never reaches a row
    assert got["band_z"]["value"] > 0


def rows_all(engine, cik):
    return engine.execute("SELECT * FROM signal WHERE cik = ? AND module_id = 'M09'",
                          (cik,)).fetchall()  # fmt: skip


def test_rerun_in_the_same_week_updates_the_same_rows(dbs):
    engine, _ = dbs
    put_weeks(engine, "NVDA", uptrend(60), cik=NVDA)
    run_pass(engine, {"NVDA": NVDA})
    n = len(rows_all(engine, NVDA))
    run_pass(engine, {"NVDA": NVDA})
    assert len(rows_all(engine, NVDA)) == n == 15


def test_spy_has_no_rows_and_feeds_method(dbs):
    engine, _ = dbs
    put_weeks(engine, BENCHMARK, uptrend(60, start=500, g=1.003))
    put_weeks(engine, "NVDA", uptrend(60, g=0.99), cik=NVDA)
    tp = run_pass(engine, {"NVDA": NVDA, BENCHMARK: None})
    assert BENCHMARK not in tp.results
    assert engine.execute("SELECT count(*) FROM signal WHERE ticker = 'SPY'").fetchone()[0] == 0
    trend = rows(engine, NVDA, "trend_state")[0]
    assert "SPY trend up (2026-10-09" in trend["method"]
    assert "SPY 12-1 +" in rows(engine, NVDA, "mom_12_1")[0]["method"]
    assert step.spy_line(tp, P).startswith("SPY (benchmark, no rows) 2026-10-09")


def test_spcx_length_history_gets_insufficient_history_rows(dbs):
    engine, _ = dbs
    put_weeks(engine, "SPCX", uptrend(18), cik=SPCX)
    run_pass(engine, {"SPCX": SPCX})
    got = {r["signal"]: r["method"] for r in rows(engine, SPCX)}
    assert got["band_z"].startswith("missing: insufficient_history (18/20)")
    assert got["trend_state"].startswith("missing: insufficient_history (18/45)")
    assert got["mom_12_1"].startswith("missing: insufficient_history (18/53)")
    assert got["rev_1m"].startswith("missing: insufficient_history (18/31)")
    assert all(r["value"] is None and r["value_text"] is None for r in rows(engine, SPCX))


def test_infq_shell_period_rows(dbs):
    engine, _ = dbs
    mf = infq_models()
    put_weeks(engine, "INFQ", [10.0 + (k % 3) for k in range(80)], cik=INFQ)
    run_pass(engine, {"INFQ": INFQ}, mf=mf)
    got = {r["signal"]: r for r in rows(engine, INFQ)}
    assert got["band_z"]["value"] is not None  # 35 weeks after the close: enough for 20
    assert got["rev_1m"]["value"] is not None
    assert got["trend_state"]["method"].startswith("missing: shell period (before 2026-02-13)")
    assert "35/45 completed weeks after the shell cut-off" in got["trend_state"]["method"]
    assert got["mom_12_1"]["method"].startswith("missing: shell period (before 2026-02-13)")


def test_stale_bars_give_missing_rows_without_overwriting_values(dbs):
    engine, _ = dbs
    put_weeks(engine, "CORE", [1.0, 1.0])  # the calendar is current
    put_daily(engine, "MU", week_rows(uptrend(60), "2026-10-02"), cik=MU)  # last bar 10-02
    run_pass(engine, {"MU": MU}, now=datetime(2026, 10, 5, 16, 0, tzinfo=UTC))
    assert rows(engine, MU, "band_z")[0]["value"] is not None  # computed while fresh
    run_pass(engine, {"MU": MU})
    got = rows(engine, MU, "band_z")
    assert [r["as_of"] for r in got] == ["2026-10-02", LAST_FRIDAY]
    assert got[0]["value"] is not None  # the earlier week keeps its value
    assert got[1]["method"].startswith("missing: stale bars; band_z v1; last stored bar 2026-10-02")
    # the whole store stale: the expected week equals the stored week → the value is kept
    put_weeks(engine, "NVDA", uptrend(60), cik=NVDA, partial=False)
    run_pass(engine, {"NVDA": NVDA}, now=datetime(2026, 10, 10, 16, 0, tzinfo=UTC))
    tp = run_pass(engine, {"NVDA": NVDA}, now=datetime(2026, 10, 16, 16, 0, tzinfo=UTC))
    assert tp.results["NVDA"].missing == "stale bars" and tp.kept == 5
    assert rows(engine, NVDA, "band_z")[-1]["value"] is not None


def test_no_stored_prices_gives_missing_rows(dbs):
    engine, _ = dbs
    put_weeks(engine, "CORE", [1.0, 1.0])
    run_pass(engine, {"GFS": "0001709048"})
    got = rows(engine, "0001709048")
    assert len(got) == 5 and all(r["method"].startswith("missing: no stored prices") for r in got)
    assert {r["as_of"] for r in got} == {LAST_FRIDAY}


def test_news_move_overrides_the_reversal_reading(dbs):
    engine, _ = dbs
    closes = [100.0] * 30 + rev_closes()
    put_weeks(engine, "TSLA", closes, cik="0001318605")
    run_pass(engine, {"TSLA": "0001318605"})
    r = rows(engine, "0001318605", "rev_1m")[0]
    assert r["value"] == pytest.approx(2.5) and r["value_text"] == "extended_up"
    # Tesla's deliveries report carries Item 2.02 (D-M02-23): it counts as news
    event(engine, "0001318605", "2026-10-02", "2026-10-02T09:00:00.000Z")
    run_pass(engine, {"TSLA": "0001318605"})
    r = rows(engine, "0001318605", "rev_1m")[0]
    assert r["value_text"] == "news_move" and r["value"] == pytest.approx(2.5)
    assert "drift expected" in r["method"] and r["source_ref"].endswith("+1")


def test_qualification_and_r17_on_a_below_2_reading(dbs):
    engine, _ = dbs
    closes = uptrend(60, g=0.995) + [40.0]  # a sharp drop below the band
    put_weeks(engine, "MSTR", closes, cik=MSTR)
    m04(engine, MSTR, "pass", cvd="CYCLICAL_TROUGH")
    run_pass(engine, {"MSTR": MSTR})
    r = rows(engine, MSTR, "band_z")[0]
    assert r["value_text"] == "below_2" and r["value"] < -2
    assert "qualified (gate pass, filing current, CvD CYCLICAL_TROUGH)" in r["method"]
    assert "beyond 2σ: stronger" in r["method"]
    assert "about 40% of Russell 3000 stocks" in r["method"]
    assert "falling-knife context" in r["method"]  # 12-1 < 0 and trend down
    m04(engine, MSTR, "fail", as_of="2026-09-01")
    run_pass(engine, {"MSTR": MSTR})
    r = rows(engine, MSTR, "band_z")[0]
    assert "not qualified: gate fail" in r["method"]
    assert "beyond 2σ: warning, no added strength (D27, D-M01-5): gate fail" in r["method"]
    assert r["value"] < -2  # the value is still shown (R3 note)


def test_tracked_name_label_and_older_as_of(dbs):
    from engine.themes import tiers

    engine, _ = dbs
    tiers.add_tracked(engine, "0001341439", "ORCL", reason="t", theme_key=None, by="owner",
                      now=NOW)  # fmt: skip
    put_weeks(engine, "CORE", [1.0, 1.0])
    # fetched on Thursday by the rotation: 5 days old, not stale, but Friday is missing
    put_daily(engine, "ORCL", week_rows(uptrend(40), skip={"2026-10-09"}), cik="0001341439")
    tp = run_pass(engine, {"ORCL": "0001341439"})
    r = rows(engine, "0001341439", "band_z")[0]
    assert r["as_of"] == "2026-10-02"
    assert "qualification: not covered by M04 (D-M04-80)" in r["method"]
    assert "as_of older than 2026-10-09" in r["method"]
    assert "older than 2026-10-09" in signals.line(tp.results["ORCL"])


def test_dividend_refetch_keeps_the_older_rows_basis(dbs):
    engine, _ = dbs
    put_weeks(engine, "MU", uptrend(60), cik=MU)
    run_pass(engine, {"MU": MU}, now=datetime(2026, 10, 10, 16, 0, tzinfo=UTC))
    put_daily(engine, "MU", week_rows([c * 0.99 for c in uptrend(61)], "2026-10-16"), cik=MU,
              full_at="2026-10-14T01:00:00+00:00")  # fmt: skip
    run_pass(engine, {"MU": MU}, now=datetime(2026, 10, 17, 16, 0, tzinfo=UTC))
    old, new = rows(engine, MU, "band_z")
    assert "full fetch 2026-01-02" in old["method"] and old["as_of"] == LAST_FRIDAY
    assert "full fetch 2026-10-14" in new["method"] and new["as_of"] == "2026-10-16"


def test_mu_2022_23_trough_shape_from_stored_anchors(dbs):
    engine, _ = dbs
    fx = json.loads((FIX / "mu_2022_23_anchors.json").read_text(encoding="utf-8"))
    anchors = [(date.fromisoformat(a["date"]), a["close"]) for a in fx["anchors"]]
    daily = []
    for (d0, c0), (d1, c1) in zip(anchors, anchors[1:], strict=False):
        span = (d1 - d0).days
        d = d0
        while d < d1:
            if d.weekday() < 5:
                daily.append((d.isoformat(), c0 * (c1 / c0) ** ((d - d0).days / span)))
            d += timedelta(days=1)
    daily.append((anchors[-1][0].isoformat(), anchors[-1][1]))
    put_daily(engine, "MU", daily, cik=MU)
    low = run_pass(engine, {"MU": MU}, now=datetime(2022, 10, 1, 16, 0, tzinfo=UTC))
    r = low.results["MU"]
    assert r.as_of == "2022-09-30"
    assert r.band.z < -1 and r.trend.state == "down" and r.mom < 0
    by = {o.signal: o for o in r.rows}
    assert "falling-knife context" in by["band_z"].method and "R17" in by["band_z"].method
    rec = run_pass(engine, {"MU": MU}, now=datetime(2023, 10, 7, 16, 0, tzinfo=UTC))
    r = rec.results["MU"]
    assert r.as_of == "2023-10-06" and r.trend.state == "up" and r.mom > 0


def test_one_name_error_does_not_stop_the_others(dbs, monkeypatch):
    engine, _ = dbs
    put_weeks(engine, "NVDA", uptrend(60), cik=NVDA)
    put_weeks(engine, "MU", uptrend(60), cik=MU)
    real = step.name_result

    def boom(engine_, ticker, *a, **kw):
        if ticker == "MU":
            raise RuntimeError("bad")
        return real(engine_, ticker, *a, **kw)

    monkeypatch.setattr(step, "name_result", boom)
    tp = run_pass(engine, {"NVDA": NVDA, "MU": MU})
    assert tp.errors == {"MU": "RuntimeError: bad"} and "NVDA" in tp.results
    lines = step.summary_lines(tp, P)
    assert any("MU: error" in x for x in lines)


def test_run_local_part_never_fails(dbs, monkeypatch):
    engine, _ = dbs
    put_weeks(engine, "NVDA", uptrend(60), cik=NVDA)
    lines = step.run_local_part(engine, {"NVDA": NVDA}, NOW, clock=lambda: 0.0)
    assert lines[0] == "M09 technicals — local pass (Part 1, 0 requests) (0.0 s):"
    assert "1 names" in lines[1]

    def boom(*a, **kw):
        raise RuntimeError("calendar")

    monkeypatch.setattr(step, "technicals_pass", boom)
    broken = step.run_local_part(engine, {"NVDA": NVDA}, NOW, clock=lambda: 0.0)
    assert broken[-1] == "  M09: error — RuntimeError: calendar"


# --- refresh wiring and the owner script ------------------------------------------------------


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Report:
    def __init__(self):
        self.watchlist = {"NVDA": "NVIDIA CORP (0001045810)", "ETV": "fund (0001322436)"}
        self.tracked = {"ORCL": "0001341439"}


def test_refresh_fetches_spy_without_a_cik_before_tracked_names(dbs):
    engine, _ = dbs
    rr = load_script("run_refresh")
    symbols, tracked, over = rr.price_symbols(engine, Report())
    assert list(symbols) == ["NVDA", "ETV", "SPY", "ORCL"]
    assert symbols["SPY"] is None and tracked == {"ORCL": "0001341439"} and over == []
    assert with_benchmark({"SPY": None}) == {"SPY": None}
    src = (ROOT / "scripts" / "run_refresh.py").read_text(encoding="utf-8")
    assert src.index("prices += financials_quality_local_step(engine, corpus, report)") < \
        src.index("prices += technicals_local_step(engine, report, corpus)")  # fmt: skip


def test_script_signals_no_fetch_on_injected_db(dbs, tmp_path, capsys):
    engine, _ = dbs
    rt = load_script("run_technicals")
    put_weeks(engine, "NVDA", uptrend(60), cik=NVDA)
    put_weeks(engine, BENCHMARK, uptrend(60, start=500, g=1.002))
    log = rt.Log(tmp_path / "logs" / "t.txt")
    args = argparse.Namespace(no_fetch=True, tickers=None, companies={"NVDA": NVDA})
    assert rt.run_signals(args, log, tmp_path, engine=engine, now=NOW) == 0
    log.close()
    text = (tmp_path / "logs" / "t.txt").read_text(encoding="utf-8")
    assert "--no-fetch (0 requests)" in text and "Tiingo requests: 0 · SEC requests: 0" in text
    assert "NVDA 2026-10-09 close" in text and "band_z +" in text
    assert "MU 2026-03-27: pack band_z +0.32" in text
    assert "engine: no completed week of 2026-03-23 stored for MU" in text
    assert "SPY (benchmark, no rows) 2026-10-09" in text
    assert text.count("SPY (benchmark, no rows)") == 1  # printed once (Part 2 cosmetic fix)
    out = capsys.readouterr().out
    assert "=== Summary" in out and "Per name" not in out  # console: summary only


def test_script_list_and_unbuilt_subcommand(capsys):
    rt = load_script("run_technicals")
    assert rt._main(["--list"]) == 0
    assert "signals  Part 1" in capsys.readouterr().out
    assert rt._main(["tab"]) == 2
