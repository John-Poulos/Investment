"""M09 Part 2: the single M01 reader (open item 5), 6-K earnings releases as news (open item
2), the Technicals tab and the chart overlays (docs/M09_TECHNICALS.md Part 2; D-UI-35)."""

from __future__ import annotations

from dataclasses import replace

from engine import m01_rules
from engine.financials import cvd
from tests import test_financials_8a as t8a

# --- single M01 reader: m01_rules agrees with Part 8a's reading -------------------------------


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
            _assert_agree(engine, c, cvd.m01_reading)
            n += 1
    assert n > 30


def test_m01_rules_agrees_on_intel_and_invitae(dbs):
    from tests import test_financials_4a as t4a

    engine, _ = dbs
    t8a.intel(engine)
    for c in _variants(t8a.ev(engine, t8a.INTC, "INTC", "2024-03-01")):  # AMBIGUOUS
        _assert_agree(engine, c, cvd.m01_reading)
    t4a.invitae(engine)
    c = cvd.evaluate(engine, t4a.NVTA, "Invitae", "2022-03-01", models=t4a.MF, calendar=False)
    assert c.gate.state == "fail"
    _assert_agree(engine, c, cvd.m01_reading)


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
