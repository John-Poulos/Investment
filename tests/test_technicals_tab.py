"""M09 Part 2: the single M01 reader (open item 5), 6-K earnings releases as news (open item
2), the Technicals tab and the chart overlays (docs/M09_TECHNICALS.md Part 2; D-UI-35)."""

from __future__ import annotations

from dataclasses import replace

from engine import m01_rules
from engine.financials import cvd
from tests import test_financials_8a as t8a

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
