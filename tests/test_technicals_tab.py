"""M09 Part 2: the single M01 reader (open item 5), 6-K earnings releases as news (open item
2), the Technicals tab and the chart overlays (docs/M09_TECHNICALS.md Part 2; D-UI-35)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest

from engine import m01_rules
from engine.financials import cvd
from engine.technicals import bands, earnings, step, views
from tests import test_financials_8a as t8a
from tests import test_technicals as tt

# --- single M01 reader: m01_rules agrees with Part 8a's reading -------------------------------


def legacy_m01_reading(engine, c):
    """Part 8a's own M01 reading before the switch (frozen copy of `cvd.m01_reading` at
    e4e8a6c): the agreement tests ran against it before `cvd.m01_reading` started calling
    `m01_rules`, and keep checking that the switch kept the wording."""
    from datetime import date, timedelta

    st, g = c.state, c.gate
    gs = g.state if g else "missing"
    rule4: list[str] = []
    notes = []
    for name, bad in cvd.RED_FLAGS:
        r = cvd._latest_text(engine, c.cik, name, c.as_of)
        if r is not None and r["value_text"] in bad:
            notes.append(f"{name} {r['value_text']}")
    rem = engine.execute(
        "SELECT as_of FROM signal WHERE cik = ? AND module_id = 'M04' AND signal = "
        "'guidance_removed' AND timeframe = 'MY' AND value_text = 'removed' AND as_of <= ? "
        "AND as_of >= ? ORDER BY as_of DESC LIMIT 1",
        (c.cik, c.as_of, (date.fromisoformat(c.as_of) - timedelta(days=365)).isoformat()),
    ).fetchone()
    if rem:
        rule4.append(f"guidance_removed {rem['as_of']} (quietly removed targets, S1.7)")
    if gs == "fail":
        rule4.append("survival gate fail (S6.14)")
        return cvd.M01("blocked: survival gate fail overrides the grid (D-M04-31)", "no", rule4,
                       notes)  # fmt: skip
    if gs in ("incomplete", "not_applicable", "missing"):
        why = ", ".join(g.missing) if g and g.missing else gs
        if c.overdue:
            rule4.append("filing overdue (D-M04-61)")
        return cvd.M01(f"blocked: gate {gs} ({why}; D-M04-35)", "no", rule4, notes)
    if c.overdue:
        rule4.append("filing overdue (D-M04-61)")
        return cvd.M01("blocked: filing overdue (D-M04-58, -61)", "no", rule4, notes)
    if st == cvd.INSUFFICIENT:
        qs = ", ".join(f"{q.q} {q.present} of {q.applicable}" for q in (c.q1, c.q2)
                       if q is not None and q.present < cvd.MIN_PRESENT)  # fmt: skip
        return cvd.M01(f"blocked: CvD insufficient data ({cvd.INSUFFICIENT_WHY}: {qs}; no review "
                       "item; D-M04-56, -58, -102)", "no", rule4, notes)  # fmt: skip
    if st in ("CYCLE_PLUS_DAMAGE", "STRUCTURAL_DECLINE"):
        rule4.append(f"CvD {st} (M01 rule 4, S6.14)")
        r3 = "blocked (D-M04-58)"
        if st == "CYCLE_PLUS_DAMAGE" and not c.answer:
            r3 = "blocked; the m04_cvd item asks you to confirm (D-M04-56, -58)"
        return cvd.M01(r3, "no", rule4, notes)
    if st == "AMBIGUOUS" or (st == "STUMBLE" and not c.answer):
        return cvd.M01("blocked until you answer the m04_cvd item; your answer becomes the state "
                       "(D-M04-56, -58)", "no", rule4, notes)  # fmt: skip
    if st == "STUMBLE":
        r3, r7 = "allowed: you resolved the m04_cvd item as STUMBLE (D-M01-5)", "no (STUMBLE)"
    elif st == "NO_SLOWDOWN":
        r3, r7 = "allowed", "no (NO_SLOWDOWN)"
    elif st == "CYCLICAL_TROUGH":
        r3 = "allowed"
        r7 = "yes (CYCLICAL_TROUGH with a gate pass, D27; gauge not required, D-M04-62)"
        if g and g.runway_review:
            r7 = "no: capex-funded runway review open (D-M04-38)"
    else:
        return cvd.M01("blocked: no CvD state", "no", rule4, notes)
    if gs == "warn":
        r3 += " (gate warn counts as pass, D-M04-31)"
    if c.stale:
        r3 += ("; stale: the first tranche may use the carried state, later tranches wait for "
               "the filing (D-M04-61)")  # fmt: skip
    return cvd.M01(r3, r7, rule4, notes)


def _readings(engine, c):
    rows = cvd.m04_rows(engine, c)
    return m01_rules.rule3(rows), m01_rules.rule7(rows), m01_rules.rule4(rows)


def _assert_agree(engine, c, legacy):
    old = legacy(engine, c)
    r3, r7, r4 = _readings(engine, c)
    assert old.rule3.startswith("allowed") == (r3.state in ("allowed", "first_tranche")), (
        old.rule3,
        r3.text,
    )
    assert ("stale:" in old.rule3) == (r3.state == "first_tranche"), (old.rule3, r3.text)
    assert old.rule7.startswith("yes") == (r7.state == "stronger"), (old.rule7, r7.text)
    # rule 4: every reason 8a listed; m01_rules lists every one that applies (8a stopped at a
    # gate fail), so 8a's list is a prefix-preserving subset
    assert [x for x in r4 if x in old.rule4] == old.rule4, (old.rule4, r4)
    # after the switch: the tab's reading is m01_rules' decision in 8a's words
    new = cvd.m01_reading(engine, c)
    assert (new.rule3, new.rule7, new.notes) == (old.rule3, old.rule7, old.notes)
    assert new.rule4 == r4
    return old, (r3, r7, r4)


def _variants(c):
    """The 8a case and the M01 table's other branches on the same grid."""
    g = c.gate
    yield c
    for state, answer in (
        ("STUMBLE", None),
        ("STUMBLE", {"answer": "STUMBLE"}),
        ("CYCLE_PLUS_DAMAGE", None),
        ("STRUCTURAL_DECLINE", {"answer": "STRUCTURAL_DECLINE"}),
        ("AMBIGUOUS", None),
        ("NO_SLOWDOWN", None),
        ("CYCLICAL_TROUGH", None),
        (cvd.INSUFFICIENT, None),
    ):
        yield replace(c, state=state, answer=answer)
    for status in ("stale", "overdue", ""):
        yield replace(c, status=status)
    if g is not None:
        for gs in ("warn", "fail", "incomplete", "not_applicable"):
            yield replace(c, gate=replace(g, state=gs))
        yield replace(c, state="CYCLICAL_TROUGH", gate=replace(g, runway_review=True))
    yield replace(c, gate=None)


def legacy_cases(engine):
    t8a.micron(engine)
    t8a.mu_filings(engine)
    yield cvd.evaluate(engine, t8a.MU, "MU", "2022-09-26", models=t8a.MF, calendar=True)
    yield t8a.ev(engine, t8a.MU, "MU", "2023-11-10")  # CYCLICAL_TROUGH 1.00
    yield t8a.ev(engine, t8a.MU, "MU", "2023-10-06")  # insufficient_data


def test_m01_rules_agrees_with_the_8a_reading_on_the_fixture_cases(dbs):
    engine, _ = dbs
    n = 0
    for case in legacy_cases(engine):
        for c in _variants(case):
            _assert_agree(engine, c, legacy_m01_reading)
            n += 1
    assert n > 30


def test_m01_rules_agrees_on_intel_and_invitae(dbs):
    from tests import test_financials_4a as t4a

    engine, _ = dbs
    t8a.intel(engine)
    for c in _variants(t8a.ev(engine, t8a.INTC, "INTC", "2024-03-01")):  # AMBIGUOUS
        _assert_agree(engine, c, legacy_m01_reading)
    t4a.invitae(engine)
    c = cvd.evaluate(engine, t4a.NVTA, "Invitae", "2022-03-01", models=t4a.MF, calendar=False)
    assert c.gate.state == "fail"
    _assert_agree(engine, c, legacy_m01_reading)


def test_insufficient_data_reads_as_no_state_yet(dbs):
    engine, _ = dbs
    t8a.micron(engine)
    c = t8a.ev(engine, t8a.MU, "MU", "2023-10-06")
    rows = cvd.m04_rows(engine, c)
    assert rows.cvd_state is None and rows.cvd_missing.startswith("insufficient_data — fewer")
    rows.filing = m01_rules.Row("current", c.as_of, "status")
    q = m01_rules.rule1(rows)
    assert q.state == "incomplete" and "cvd_state missing: insufficient_data" in q.text
    assert m01_rules.rule3(rows).state == "blocked"
    assert m01_rules.rule7(rows).state == "warning"


# --- 6-K earnings releases count as news (open item 2, D-M09-16) ------------------------------

GFS = "0001709048"


def doc(corpus, accession, filename, text, doc_type="EX-99.1", description=None):
    corpus.execute(
        "INSERT INTO document (accession, cik, filename, doc_type, url, content_type, text, "
        "sha256, fetched_at, description) VALUES (?, ?, ?, ?, ?, 'text/html', ?, 'x', 't', ?)",
        (accession, GFS, filename, doc_type, f"https://example/{accession}/{filename}", text,
         description),
    )  # fmt: skip


def six_k(engine, acc, filed, accepted=None):
    tt.event(engine, GFS, filed, accepted, acc=acc, item="6-K", category="foreign_report",
             form="6-K")  # fmt: skip


RELEASE = (
    "Exhibit 99.1 GlobalFoundries Reports Third Quarter 2026 Financial Results Revenue of "
    "$1.69 billion ... The company will host a conference call later today."
)


def test_results_exhibit_reads_the_heading_name_and_description(dbs):
    _, corpus = dbs
    doc(corpus, "A-release", "gfs-ex991.htm", RELEASE)
    doc(corpus, "B-notice", "gfs-ex991.htm",
        "Exhibit 99.1 GlobalFoundries to Announce Third Quarter 2026 Financial Results on "
        "November 4")  # fmt: skip
    doc(corpus, "C-agm", "ex99.htm", "GlobalFoundries Announces Results of Annual General "
        "Meeting of Shareholders", doc_type="EX-99")  # fmt: skip
    doc(corpus, "D-named", "q3-2026-earnings.htm", "Tables follow.")
    doc(corpus, "E-described", "ex991.htm", "Tables.", description="Press release: Q3 results")
    doc(corpus, "F-other", "ex991.htm", "GlobalFoundries appoints a new Chief Financial Officer")
    doc(corpus, "G-ex992", "ex992.htm", RELEASE, doc_type="EX-99.2")
    got = earnings.results_exhibit(corpus, "A-release")
    assert got.startswith("EX-99.1 gfs-ex991.htm") and "Reports Third Quarter 2026 Financial " \
        "Results" in got  # fmt: skip
    assert earnings.results_exhibit(corpus, "B-notice") is None  # a date notice
    assert earnings.results_exhibit(corpus, "C-agm") is None  # meeting results
    assert "named: q3-2026-earnings.htm" in earnings.results_exhibit(corpus, "D-named")
    assert "Q3 results" in earnings.results_exhibit(corpus, "E-described")
    assert earnings.results_exhibit(corpus, "F-other") is None
    assert earnings.results_exhibit(corpus, "G-ex992") is None  # EX-99.1 / EX-99 only
    assert earnings.results_exhibit(None, "A-release") is None  # no corpus: listed only


def test_a_6k_release_sets_news_move_and_others_stay_listed(dbs):
    engine, corpus = dbs
    closes = [100.0] * 30 + tt.rev_closes()
    tt.put_weeks(engine, "GFS", closes, cik=GFS)
    six_k(engine, "0001709048-26-000040", "2026-09-29", "2026-09-29T07:00:00.000Z")
    doc(corpus, "0001709048-26-000040", "gfs-ex991.htm", RELEASE)
    six_k(engine, "0001709048-26-000041", "2026-10-01", "2026-10-01T07:00:00.000Z")
    doc(corpus, "0001709048-26-000041", "ex991.htm", "GlobalFoundries appoints a director")
    six_k(engine, "0001709048-26-000042", "2026-10-02")  # no exhibit stored
    # without corpus.db (Part 1 behaviour): every 6-K listed, no news move
    tp = step.technicals_pass(engine, {"GFS": GFS}, tt.NOW, params=tt.P, mf=tt.NO_MODELS)
    r = tp.results["GFS"]
    assert not r.news and len(r.foreign) == 3
    assert next(o for o in r.rows if o.signal == "rev_1m").text == "extended_up"
    tp = step.technicals_pass(engine, {"GFS": GFS}, tt.NOW, params=tt.P, mf=tt.NO_MODELS,
                              corpus=corpus)  # fmt: skip
    r = tp.results["GFS"]
    assert [c.accession for c in r.news] == ["0001709048-26-000040"]
    assert [c.accession for c in r.foreign] == ["0001709048-26-000041", "0001709048-26-000042"]
    row = tt.rows(engine, GFS, "rev_1m")[0]
    assert row["value_text"] == "news_move" and row["source_ref"].endswith("+1")
    assert "6-K 0001709048-26-000040 filed 2026-09-29 07:00 ET, earnings-release exhibit " \
        "EX-99.1 gfs-ex991.htm" in row["method"]  # fmt: skip
    assert "6-K earnings release" in row["method"]  # the source line
    assert "6-K in the window (not classified; may be results): 6-K item 6-K " \
        "0001709048-26-000041" in row["method"]  # fmt: skip


def test_script_lists_6k_news_and_listed_6ks(dbs, tmp_path):
    import argparse

    engine, corpus = dbs
    rt = tt.load_script("run_technicals")
    tt.put_weeks(engine, "GFS", [100.0] * 30 + tt.rev_closes(), cik=GFS)
    six_k(engine, "0001709048-26-000040", "2026-09-29", "2026-09-29T07:00:00.000Z")
    doc(corpus, "0001709048-26-000040", "gfs-ex991.htm", RELEASE)
    six_k(engine, "0001709048-26-000041", "2026-10-01")
    log = rt.Log(tmp_path / "logs" / "t.txt")
    args = argparse.Namespace(no_fetch=True, tickers=None, companies={"GFS": GFS})
    assert rt.run_signals(args, log, tmp_path, engine=engine, now=tt.NOW, corpus=corpus) == 0
    log.close()
    text = (tmp_path / "logs" / "t.txt").read_text(encoding="utf-8")
    news = text.split("News moves", 1)[1].split("6-Ks in the rev_1m window", 1)
    assert "GFS: 6-K 0001709048-26-000040" in news[0]
    assert "GFS: 6-K item 6-K 0001709048-26-000041" in news[1].split("Pack checkpoints")[0]


# --- chart overlays (D-M09-2 amendment, D-M09-17) ---------------------------------------------


def test_weekly_overlay_latest_week_equals_the_stored_price_band_row(dbs):
    engine, _ = dbs
    closes = tt.uptrend(60)
    tt.put_weeks(engine, "NVDA", closes, cik=tt.NVDA)  # + a partial week far off the band
    tt.run_pass(engine, {"NVDA": tt.NVDA})
    ov = views.overlay(engine, "NVDA", tt.NVDA, "W", tt.NOW, tt.P, tt.NO_MODELS)
    assert ov["as_of"] == tt.LAST_FRIDAY and ov["bar"] == "W"
    s = ov["series"]
    assert len(s["mean"]) == 60 - 19 and len(s["ma"]) == 60 - 39
    assert s["mean"][-1]["time"] == "2026-10-05"  # the chart's Monday key; partial week: none
    stored = tt.rows(engine, tt.NVDA, "price_band")[0]
    assert s["mean"][-1]["value"] == pytest.approx(stored["value"], abs=1e-4)
    b = bands.band_at(closes)
    lv = b.levels()
    for k, key in (("m2", "-2"), ("m1", "-1"), ("p1", "+1"), ("p2", "+2")):
        assert s[k][-1]["value"] == pytest.approx(lv[key], abs=1e-4)
        assert f"{lv[key]:.2f}" in stored["method"]
    assert s["ma"][-1]["value"] == pytest.approx(sum(closes[-40:]) / 40, abs=1e-4)
    assert s["mean"][0]["time"] == "2025-12-29"  # week 20 of 60 (Monday key)


def test_daily_overlay_steps_on_completed_weeks(dbs):
    engine, _ = dbs
    closes = tt.uptrend(60)
    tt.put_weeks(engine, "NVDA", closes, cik=tt.NVDA)
    ov = views.overlay(engine, "NVDA", tt.NVDA, "D", tt.NOW, tt.P, tt.NO_MODELS)
    ma = {p["time"]: p["value"] for p in ov["series"]["ma"]}
    last = sum(closes[-40:]) / 40
    prev = sum(closes[-41:-1]) / 40
    assert ma["2026-10-09"] == pytest.approx(last, abs=1e-4)  # Friday completes the week
    assert ma["2026-10-08"] == pytest.approx(prev, abs=1e-4)  # Thursday: last week's MA
    assert ma["2026-10-05"] == pytest.approx(prev, abs=1e-4)
    assert ma["2026-10-13"] == pytest.approx(last, abs=1e-4)  # partial week: the newest MA
    mean = {p["time"]: p["value"] for p in ov["series"]["mean"]}
    assert mean["2026-10-12"] == mean["2026-10-09"]
    assert "2026-01-02" in mean and "2026-01-01" not in mean  # first band on week 20's Friday


def test_overlay_without_bars_and_with_a_shell_cut_off(dbs):
    engine, _ = dbs
    ov = views.overlay(engine, "NONE", None, "W", tt.NOW, tt.P, tt.NO_MODELS)
    assert ov["as_of"] is None and all(not x for x in ov["series"].values())
    tt.put_weeks(engine, "INFQ", [10.0 + (k % 3) for k in range(80)], cik=tt.INFQ)
    ov = views.overlay(engine, "INFQ", tt.INFQ, "W", tt.NOW, tt.P, tt.infq_models())
    assert ov["cut_off"] == "2026-02-13"
    assert ov["series"]["mean"][0]["time"] >= "2026-02-09" and not ov["series"]["ma"]


# --- the Technicals tab (D-UI-35) ---------------------------------------------------------------


def _app(tmp_path, monkeypatch, fill, tickers):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui import app as app_mod
    from engine.ui.settings import UiSettings

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return tt.NOW if tz else tt.NOW.replace(tzinfo=None)

    monkeypatch.setattr(app_mod, "datetime", Clock)
    data = tmp_path / "data"
    engine = open_db("engine", data)
    corpus = open_db("corpus", data)
    for t, cik in tickers.items():
        engine.execute("INSERT OR IGNORE INTO ticker (ticker, cik, valid_from, source) VALUES "
                       "(?, ?, '2000-01-01', 't')", (t, cik))  # fmt: skip
    fill(engine, corpus)
    engine.commit()
    corpus.commit()
    engine.close()
    corpus.close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text(f"[watchlist]\ntickers = {list(tickers)!r}\n".replace("'", '"'),
                     encoding="utf-8")  # fmt: skip
    return TestClient(app_mod.create_app(UiSettings(data_dir=data, watchlist=watch)))


def test_technicals_tab_renders_signals_history_r17_and_6k_news(tmp_path, monkeypatch):
    MSTR, SPCX = tt.MSTR, tt.SPCX

    def fill(engine, corpus):
        closes = tt.uptrend(60, g=0.995) + [40.0]  # a sharp drop below the band
        tt.put_weeks(engine, "MSTR", closes, cik=MSTR)
        tt.m04(engine, MSTR, "pass", cvd="CYCLICAL_TROUGH")
        tt.put_weeks(engine, "SPCX", tt.uptrend(18), cik=SPCX)
        tt.put_weeks(engine, "GFS", [100.0] * 30 + tt.rev_closes(), cik=GFS)
        six_k(engine, "0001709048-26-000040", "2026-09-29", "2026-09-29T07:00:00.000Z")
        doc(corpus, "0001709048-26-000040", "gfs-ex991.htm", RELEASE)
        tt.put_weeks(engine, "SPY", tt.uptrend(60, start=500, g=1.003))
        step.technicals_pass(engine, {"MSTR": MSTR}, tt.NOW, params=tt.P, mf=tt.NO_MODELS)

    with _app(tmp_path, monkeypatch, fill, {"MSTR": MSTR, "SPCX": SPCX, "GFS": GFS}) as c:
        html = c.get("/c/MSTR?tab=technicals").text
        spcx = c.get("/c/SPCX?tab=technicals").text
        gfs = c.get("/c/GFS?tab=technicals").text
        over = c.get("/c/MSTR?tab=overview").text
        chart = c.get("/c/MSTR?tab=technicals&bar=W").text
        ov = c.get("/api/overlay/MSTR?bar=W").json()
    for want in (
        "Technicals (M09) — MSTR",
        "Newest completed week 2026-10-09",
        "qualified (gate pass, filing current, CvD CYCLICAL_TROUGH)",
        "M04 reading: gate pass (2026-08-01), filing current, cvd_state CYCLICAL_TROUGH",
        "beyond 2σ: stronger",
        "R17: decline risk: about 40% of Russell 3000 stocks",
        "below_2",
        "pullback_sigma",
        "falling-knife context",
        "−2σ",
        "40-week MA",
        "SPY trend up (2026-10-09",
        "SPY 12-1 +",
        "turnover not checked (deferred)",
        "stored row 2026-10-09 matches",
        "Last 12 completed weeks",
        "✓ lead (timing)",
    ):
        assert want in html, want
    assert "object at 0x" not in html and "None" not in html.split("Last 12")[1]
    assert html.count("<tr>") >= 12
    for want in ("missing: insufficient_history (18/20)", "missing: insufficient_history (18/45)",
                 "not stored yet", "qualification incomplete (survival_gate missing"):  # fmt: skip
        assert want in spcx, want
    assert "object at 0x" not in spcx
    assert "news_move" in gfs and "earnings-release exhibit EX-99.1 gfs-ex991.htm" in gfs
    assert "drift expected" in gfs and "object at 0x" not in gfs
    assert "Technicals (M09)" in over and "band" in over and "below_2" in over
    assert "?tab=technicals" in over
    assert 'id="ov-band"' in chart and 'id="ov-ma"' in chart
    assert ov["as_of"] == "2026-10-09" and ov["series"]["mean"]


def test_technicals_tab_missing_rows_without_prices_and_for_a_tracked_name(tmp_path, monkeypatch):
    from engine.themes import tiers

    ORCL = "0001341439"

    def fill(engine, corpus):
        tt.put_weeks(engine, "CORE", [1.0, 1.0])
        tiers.add_tracked(engine, ORCL, "ORCL", reason="t", theme_key=None, by="owner",
                          now=tt.NOW)  # fmt: skip
        tt.put_daily(engine, "ORCL", tt.week_rows(tt.uptrend(40), skip={"2026-10-09"}), cik=ORCL)

    with _app(tmp_path, monkeypatch, fill, {"GFS": GFS, "ORCL": ORCL}) as c:
        none = c.get("/c/GFS?tab=technicals").text
        orcl = c.get("/c/ORCL?tab=technicals").text
        over = c.get("/c/GFS?tab=overview").text
    assert "Every row is missing: no stored prices." in none
    assert none.count("missing: no stored prices") >= 5
    assert "No completed weekly bars stored for GFS." in none
    assert "qualification: not covered by M04 (D-M04-80)" in orcl
    assert "as_of older than 2026-10-09" in orcl and "Newest completed week 2026-10-02" in orcl
    assert "object at 0x" not in none + orcl
    assert "Technicals (M09)" not in over  # nothing stored for GFS yet


def test_overview_row_reads_the_newest_stored_rows(dbs):
    engine, _ = dbs
    assert views.overview_row(engine, tt.NVDA) is None
    tt.put_weeks(engine, "SPCX", tt.uptrend(18), cik=tt.SPCX)
    tt.run_pass(engine, {"SPCX": tt.SPCX})
    r = views.overview_row(engine, tt.SPCX)
    assert r["as_of"] == tt.LAST_FRIDAY
    assert r["band_z"]["missing"] == "insufficient_history (18/20)"
