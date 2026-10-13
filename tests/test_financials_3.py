# ruff: noqa: E501  (fixture rows)
"""M04 Part 3: restatement walk, filing events, ratings, non-reliance, prior filings and the
`flags` run (docs/M04_BUILD_LOG.md Part 3; D-M04-15, -16, -17, -21, -37, -71, -73).

Fixtures: tests/fixtures/m04/ge_us-gaap_*_20261012.json and ge_10k_fy201{8,9}_excerpt.txt
(hand-built from Round 2's worked example; README). Infleqtion, Rite Aid, Invitae, the
co-filings, AVGO's dei flag and Intel's rating sentence are entered in the tests (figures
from M04_BUILD_LOG Part 3, PROBE_RESULTS; texts illustrative). Never calls SEC."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from engine.financials import events, filings, flags_step, labels, queue, ratings, restate
from engine.sec import cover
from engine.sec.documents import IndexDoc, store_document
from engine.sec.xbrl_facts import store_concept
from tests.conftest import FIXTURES, FakeTransport, ok

M04 = FIXTURES / "m04"
GE, INFQ, RAD, NVTA, AMZN, MU, TSLA, INTC, AVGO = (
    "0000040545", "0002007825", "0000084129", "0001501134", "0001018724", "0000723125",
    "0001318605", "0000050863", "0001730168")  # fmt: skip
A17, A18, A19 = "0000040545-18-000014", "0000040545-19-900010", "0000040545-20-900010"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
M = 1_000_000
GE_TAGS = ("Revenues", "NetIncomeLoss", "NetIncomeLossAttributableToNoncontrollingInterest",
           "NetCashProvidedByUsedInOperatingActivities",
           "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
           "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest")  # fmt: skip


def concept(engine, cik, tag, rows, name="X"):
    """Store a companyconcept-shaped dict: rows = (start, end, value, accession, form, filed)."""
    data = {"cik": int(cik), "taxonomy": "us-gaap", "tag": tag, "entityName": name,
            "units": {"USD": [{"start": s, "end": e, "val": v, "accn": a, "form": f, "filed": d}
                              for s, e, v, a, f, d in rows]}}  # fmt: skip
    engine.execute("BEGIN")
    store_concept(engine, cik, data)
    engine.execute("COMMIT")


def doc(corpus, cik, acc, text, doc_type="10-K", name="doc.htm"):
    d = IndexDoc(1, None, name.replace(".htm", ".txt"), f"https://x/{acc}/{name}", doc_type, None,
                 False)  # fmt: skip
    store_document(corpus, cik, acc, d, text.encode("utf-8"), NOW)


def filing(engine, cik, acc, form, filed, items=None, report=None):
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, report_date, items, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'x')",
        (acc, cik, form, filed, report, items),
    )
    engine.execute("INSERT INTO filing_cik (accession, cik) VALUES (?, ?)", (acc, cik))


def event(engine, cik, acc, item, filed, form="8-K"):
    engine.execute(
        "INSERT INTO event (accession, item, cik, form, filed, category, severity, title, "
        "modules, amended, catalog) VALUES (?, ?, ?, ?, ?, 'x', 'high', 't', '[]', 0, 'c')",
        (acc, item, cik, form, filed),
    )


def ge(dbs):
    engine, corpus = dbs
    for tag in GE_TAGS:
        engine.execute("BEGIN")
        store_concept(
            engine,
            GE,
            json.loads((M04 / f"ge_us-gaap_{tag}_20261012.json").read_text(encoding="utf-8")),
        )
        engine.execute("COMMIT")
    doc(corpus, GE, A18, (M04 / "ge_10k_fy2018_excerpt.txt").read_text(encoding="utf-8"))
    doc(corpus, GE, A19, (M04 / "ge_10k_fy2019_excerpt.txt").read_text(encoding="utf-8"))
    return restate.walk(engine, corpus, GE)


def step_of(steps, concept_, end, to_acc):
    return next(
        s for s in steps if s.concept == concept_ and s.end == end and s.new.accession == to_acc
    )


def fams(s):
    return {lb.family for lb in s.labels}


# --- Walk (D-M04-16) ---------------------------------------------------------------------------


def test_ge_revenue_fy2017_recast_to_discontinued_operations_with_ni_unchanged(dbs):
    steps = ge(dbs)
    s = step_of(steps, "revenue", "2017-12-31", A19)
    assert s.delta == -18_964 * M
    assert "discontinued" in fams(s) and s.residual == 0 and s.outcome == "explained"
    lab = next(lb for lb in s.labels if lb.family == "discontinued")
    assert lab.amount == -18_964 * M and "discontinued operations" in lab.quote


def test_ge_ni_fy2017_residual_94_is_the_nci_share(dbs):
    s = step_of(ge(dbs), "net_income", "2017-12-31", A18)
    assert s.delta == -2_698 * M
    amounts = sorted(lb.amount for lb in s.labels if lb.family == "standards")
    assert amounts == [-2_668 * M, -124 * M]
    nci = next(lb for lb in s.labels if lb.family == "nci_share")
    assert nci.amount == pytest.approx(94 * M)
    assert s.residual == pytest.approx(0) and s.outcome == "explained"


def test_ge_ni_fy2016_asc606_and_lifo_leave_minus_2(dbs):
    s = step_of(ge(dbs), "net_income", "2016-12-31", A18)
    assert s.residual == pytest.approx(-2 * M) and s.outcome == "explained"


def test_ge_cfo_fy2017_asu_2016_15_and_restricted_cash(dbs):
    s = step_of(ge(dbs), "operating_cash_flow", "2017-12-31", A18)
    assert s.delta == -4_394 * M
    assert {"standards", "restricted_cash"} <= fams(s)
    assert [lb.amount for lb in s.labels if lb.family == "standards"] == [-4_411 * M]
    assert s.residual == pytest.approx(17 * M)
    assert abs(s.residual) < 0.005 * abs(s.old.value) and s.outcome == "explained"


def test_ge_cfo_fy2016_shift_up_leaves_4_on_minus_244_and_reviews(dbs):
    s = step_of(ge(dbs), "operating_cash_flow_cont", "2016-12-31", A18)
    assert s.delta == 1_404 * M and "cf_shift_up" in fams(s)
    assert s.residual == pytest.approx(4 * M)
    assert s.residual_pct == pytest.approx(4 / 244)
    assert s.outcome == "review"


def test_ge_walk_counts_and_baseline_store(dbs):
    engine, _ = dbs
    steps = ge(dbs)
    assert len(steps) == 7  # pretax unchanged → no step
    engine.execute("BEGIN")
    got = restate.store(engine, GE, "GE", steps, NOW)
    engine.execute("COMMIT")
    assert got["review"] == 1 and got["baseline"] == 1  # filed 2019: baseline (D-M04-71)
    assert engine.execute("SELECT count(*) FROM review_queue").fetchone()[0] == 0
    rows = restate.stored_steps(engine, GE)
    assert len(rows) == 7 and all(r["baseline"] == 1 for r in rows)
    # a second walk is not a baseline any more
    assert not restate.first_walk(engine, GE)


def infq_little_r(dbs):
    engine, corpus = dbs
    a1, a2 = "0002007825-26-900101", "0002007825-26-900202"
    q1 = ("2026-01-01", "2026-03-31")
    concept(
        engine,
        INFQ,
        "Revenues",
        [
            (*q1, 9_100_000, a1, "10-Q", "2026-05-14"),
            (*q1, 9_546_000, a2, "10-Q", "2026-08-13"),
            ("2026-04-01", "2026-06-30", 11_000_000, a2, "10-Q", "2026-08-13"),
        ],
    )
    concept(
        engine,
        INFQ,
        "NetIncomeLoss",
        [
            (*q1, -30_200_000, a1, "10-Q", "2026-05-14"),
            (*q1, -30_744_000, a2, "10-Q", "2026-08-13"),
        ],
    )
    doc(
        corpus,
        INFQ,
        a2,
        "INFLEQTION, INC. FORM 10-Q\n\nREVISION OF PREVIOUSLY ISSUED FINANCIAL STATEMENTS. We identified an "
        "immaterial error in our previously issued financial statements for the quarter ended March 31, 2026, and revised "
        "revenue and net loss for that quarter.\n",
        "10-Q",
    )
    return a2


def test_infleqtion_q1_2026_little_r_creates_both_steps(dbs):
    engine, corpus = dbs
    a2 = infq_little_r(dbs)
    steps = restate.walk(engine, corpus, INFQ)
    rev = step_of(steps, "revenue", "2026-03-31", a2)
    ni = step_of(steps, "net_income", "2026-03-31", a2)
    assert rev.delta == 446_000 and ni.delta == -544_000
    for s in (rev, ni):
        assert "error" in fams(s) and s.outcome == "review" and s.residual == s.delta
    engine.execute("BEGIN")
    got = restate.store(engine, INFQ, "INFQ", steps, NOW)
    engine.execute("COMMIT")
    assert got["queued"] == 2  # baseline, but filed in the last 12 months → queued
    item = engine.execute("SELECT * FROM review_queue WHERE kind = 'm04_restate'").fetchone()
    assert "unexplained" in item["reason"]


def test_rite_aid_fy2017_recast_is_discontinued_operations(dbs):
    engine, corpus = dbs
    r17, r19 = "0000084129-17-900017", "0000084129-19-900019"
    fy = ("2016-02-28", "2017-03-04")
    concept(engine, RAD, "SalesRevenueNet", [(*fy, 32_845 * M, r17, "10-K", "2017-05-03")])
    concept(
        engine,
        RAD,
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        [(*fy, 22_928 * M, r19, "10-K", "2019-04-25")],
    )
    concept(
        engine,
        RAD,
        "NetIncomeLoss",
        [(*fy, 4 * M, r17, "10-K", "2017-05-03"), (*fy, 4 * M, r19, "10-K", "2019-04-25")],
    )
    doc(
        corpus,
        RAD,
        r19,
        "RITE AID CORPORATION 10-K\n\n(In thousands)\n\nThe stores sold to Walgreens Boots Alliance are "
        "reported as discontinued operations, and prior periods have been recast.\n",
    )
    s = step_of(restate.walk(engine, corpus, RAD), "revenue", "2017-03-04", r19)
    assert s.old.value == 32_845 * M and s.new.value == 22_928 * M
    assert {"discontinued", "tag_switch"} <= fams(s) and s.outcome == "explained"


def test_rounding_and_tolerance_rules():
    assert restate._rounding(5 * M, 6 * M) and not restate._rounding(5 * M, 8 * M)
    assert not restate.over_tolerance(90_000, 1_000)  # below $0.1M
    assert not restate.over_tolerance(4 * M, 10_000 * M)  # below 0.5%
    assert restate.over_tolerance(4 * M, -244 * M)
    assert restate.over_tolerance(200_000, 0)


def test_hypothetical_error_wording_is_not_little_r():
    assert restate.is_error_sentence("We revised the prior period for an immaterial error.")
    assert not restate.is_error_sentence(
        "If we identify errors in our previously issued financial statements, we may need to restate."
    )


# --- dei flag (D-M04-15) ------------------------------------------------------------------------


def test_dei_flag_required_from_2023_12_01_only(dbs, make_client):
    engine, _ = dbs
    for i in range(13):
        cik = f"{1_000_001 + i:010d}"
        filing(engine, cik, f"{cik}-23-0000{i:02d}", "10-K", f"2023-{(i % 10) + 1:02d}-15")
        assert [f.state for f in restate.dei_flags(engine, cik)] == ["not required"]
    acc = "0001730168-23-000096"
    filing(engine, AVGO, acc, "10-K", "2023-12-14", report="2023-10-29")
    assert restate.dei_flags(engine, AVGO)[0].state == "not read"
    url, _ = cover.r1_urls(AVGO, acc)
    client = make_client(FakeTransport({url: [ok((M04 / "meta_10k_fy2025_R1.htm").read_bytes())]}))
    cover.fetch_cover(
        client, engine, AVGO, {"accession": acc, "form": "10-K", "filed": "2023-12-14"}, NOW
    )
    assert restate.dei_flags(engine, AVGO)[0].state == "false"


# --- Events (D-M04-37, -15; S1.11; L8) ---------------------------------------------------------------


def test_infq_301_transfer_and_401_after_de_spac_are_information(dbs):
    engine, corpus = dbs
    event(engine, INFQ, "0002007825-26-000301", "3.01", "2026-02-03")
    doc(
        corpus,
        INFQ,
        "0002007825-26-000301",
        "Item 3.01. On February 2, 2026, the Company notified Nasdaq of its "
        "decision to transfer the listing of its common stock to the New York Stock Exchange.\n",
        "8-K",
    )
    event(engine, INFQ, "0002007825-26-000401", "4.01", "2026-03-26")
    doc(
        corpus,
        INFQ,
        "0002007825-26-000401",
        "Item 4.01. The Audit Committee dismissed the auditor of Churchill "
        "Capital Corp X. There were no disagreements with the former auditor on any matter of accounting principles.\n",
        "8-K",
    )
    evs = {e.item: e for e in events.classify(engine, corpus, INFQ, NOW.date(),
                                              [("2026-08-13", "little r")])}  # fmt: skip
    assert (
        evs["3.01"].klass == "transfer" and evs["3.01"].state == "info" and not evs["3.01"].review
    )
    assert evs["4.01"].klass == "despac_auditor" and evs["4.01"].state == "info"
    assert "not escalated" in evs["4.01"].note  # restatement nearby, routine post-de-SPAC change


def test_invitae_delisting_bankruptcy_and_acceleration_fail(dbs):
    engine, corpus = dbs
    event(engine, NVTA, "0001501134-24-000010", "3.01", "2024-02-06")
    doc(
        corpus,
        NVTA,
        "0001501134-24-000010",
        "Item 3.01. On February 5, 2024, the NYSE notified the Company that it "
        "had determined to commence proceedings to delist the Company's common stock, and trading was suspended.\n",
        "8-K",
    )
    for item in ("1.03", "2.04"):
        event(engine, NVTA, "0001501134-24-000014", item, "2024-02-14")
    evs = {e.item: e for e in events.classify(engine, corpus, NVTA, datetime(2024, 3, 1).date())}
    assert evs["3.01"].klass == "delisting" and evs["3.01"].state == "fail"
    assert evs["1.03"].state == "fail" and evs["2.04"].state == "fail"
    engine.execute("BEGIN")
    got = events.store(engine, NVTA, "NVTAQ", list(evs.values()), datetime(2024, 3, 1, tzinfo=UTC))
    engine.execute("COMMIT")
    assert got["queued"] == 3
    assert {r["priority"] for r in engine.execute("SELECT priority FROM m04_proposal")} == {
        1
    }  # current fails
    assert len(events.gate_inputs(engine, NVTA)) == 3
    assert len(events.alert_lines(engine, "2024-03-01")) == 3


@pytest.mark.parametrize("cik,acc,filed", [(AMZN, "0001018724-23-000101", "2023-11-01"),
                                          (MU, "0000723125-25-000121", "2025-01-21"),
                                          (MU, "0000723125-25-000312", "2025-03-12"),
                                          (TSLA, "0001318605-26-000929", "2026-09-29")])  # fmt: skip
def test_102_co_filed_with_203_is_financing(dbs, cik, acc, filed):
    engine, corpus = dbs
    for item in ("1.01", "1.02", "2.03", "9.01"):
        event(engine, cik, acc, item, filed)
    evs = events.classify(engine, corpus, cik, NOW.date())
    assert [(e.item, e.klass, e.review) for e in evs] == [("1.02", "financing", False)]


def test_402_warns_until_the_restated_filing_and_marks_non_reliance(dbs):
    engine, corpus = dbs
    event(engine, INTC, "0000050863-25-000402", "4.02", "2025-01-10")
    event(engine, INTC, "0000050863-25-000401", "4.01", "2025-06-01")
    engine.execute("BEGIN")
    evs = events.classify(
        engine, corpus, INTC, NOW.date(), restate.evidence_dates(engine, corpus, INTC)
    )
    events.store(engine, INTC, "INTC", evs, NOW)
    engine.execute("COMMIT")
    by = {e.item: e for e in evs}
    assert by["4.02"].state == "warn" and by["4.01"].klass == "escalated" and by["4.01"].review
    nr = restate.non_reliance(engine, INTC, "2024-12-28")
    assert nr is not None and "inputs under non-reliance" in nr.mark
    assert restate.non_reliance(engine, INTC, "2025-03-29") is None  # period after the 4.02
    filing(engine, INTC, "0000050863-25-900001", "10-K/A", "2025-03-01")
    evs = events.classify(engine, corpus, INTC, NOW.date())
    assert next(e for e in evs if e.item == "4.02").state == "cleared"


def test_nt_10q_clears_with_the_late_report_and_owner_resolves_deficiency(dbs):
    engine, corpus = dbs
    filing(engine, INFQ, "0002007825-26-000700", "NT 10-Q", "2026-08-14")
    filing(engine, INFQ, "0002007825-26-000701", "10-Q", "2026-08-20")
    nt = events.classify(engine, corpus, INFQ, NOW.date())[0]
    assert nt.item == "NT 10-Q" and nt.state == "cleared"
    event(engine, INFQ, "0002007825-26-000800", "3.01", "2026-09-01")
    doc(
        corpus,
        INFQ,
        "0002007825-26-000800",
        "Item 3.01. The Company received a notice that it is not in compliance "
        "with the minimum bid price rule and has 180 calendar days to regain compliance.\n",
        "8-K",
    )
    evs = events.classify(engine, corpus, INFQ, NOW.date())
    d = next(e for e in evs if e.item == "3.01")
    assert d.klass == "deficiency" and d.state == "warn"
    engine.execute("BEGIN")
    events.store(engine, INFQ, "INFQ", evs, NOW)
    engine.execute("COMMIT")
    item = engine.execute("SELECT item_id FROM m04_event WHERE item = '3.01'").fetchone()[0]
    from engine import review

    assert (
        review.m04_action(engine, item, "resolve", "regained per release", "owner", NOW)
        == "resolve"
    )
    row = engine.execute(
        "SELECT state, owner_resolution FROM m04_event WHERE item = '3.01'"
    ).fetchone()
    assert row["state"] == "resolved" and row["owner_resolution"] == "regained per release"
    engine.execute("BEGIN")  # a recomputation keeps the owner's resolution
    events.store(engine, INFQ, "INFQ", events.classify(engine, corpus, INFQ, NOW.date()), NOW)
    engine.execute("COMMIT")
    assert (
        engine.execute("SELECT state FROM m04_event WHERE item = '3.01'").fetchone()[0]
        == "resolved"
    )


def test_hypothetical_delisting_wording_is_a_deficiency():
    k, s, _ = events.classify_301("We received a deficiency notice. If the Company does not regain compliance, its "
                                  "shares will be delisted.")  # fmt: skip
    assert (k, s) == ("deficiency", "warn")
    assert events.classify_301("")[0] == "unread"


# --- Ratings (S3.7) ------------------------------------------------------------------------------


def test_intel_bbb_plus_to_bbb_and_hypothetical_skipped(dbs):
    engine, corpus = dbs
    acc = "0000050863-25-000088"
    filing(engine, INTC, acc, "8-K", "2025-08-20", items="7.01,9.01")
    doc(
        corpus,
        INTC,
        acc,
        "Intel update.\n\nIn August 2025, S&P Global Ratings lowered Intel's long-term credit rating "
        "from BBB+ to BBB. A downgrade of our credit ratings could increase our cost of borrowing.\n",
        "EX-99.1",
        "ex991.htm",
    )
    found = ratings.scan(engine, corpus, INTC)
    assert len(found) == 1
    r = found[0]
    assert (r.action, r.from_rating, r.to_rating, r.agency) == (
        "downgrade",
        "BBB+",
        "BBB",
        "S&P Global",
    )
    engine.execute("BEGIN")
    got = ratings.store(engine, INTC, "INTC", found, NOW)
    engine.execute("COMMIT")
    assert got["baseline"] == 1  # first scan, filed more than 12 months ago (D-M04-71)


# --- Prior filings (D-M04-17) -------------------------------------------------------------------


def test_prior_10ks_skip_fund_and_shell_years_and_fetch_one_request_each(dbs, make_client):
    engine, corpus = dbs
    from engine.financials import models

    mu = [("0000723125-24-000020", "2024-10-03"), ("0000723125-25-000021", "2025-10-03"),
          ("0000723125-23-000019", "2023-10-06"), ("0000723125-22-000018", "2022-10-07")]  # fmt: skip
    for acc, filed in mu:
        filing(engine, MU, acc, "10-K", filed)
    engine.execute("UPDATE filing SET primary_doc = 'mu-10k.htm' WHERE cik = ?", (MU,))
    filing(engine, INFQ, "0002007825-26-134544", "10-K", "2026-03-31", report="2025-12-31")
    mf = models.parse({"company": [{"ticker": "ETV", "tag": "fund", "reason": "r", "source": "s"}]})
    pt = {
        p.ticker: p
        for p in filings.prior_targets(
            engine, corpus, {"MU": MU, "INFQ": INFQ, "ETV": "0001270523"}, mf
        )
    }
    assert pt["MU"].accessions == ("0000723125-24-000020", "0000723125-23-000019")
    assert pt["INFQ"].accessions == () and "shell-year" in pt["INFQ"].note
    assert pt["ETV"].note.startswith("skipped: fund")
    urls = {f"https://www.sec.gov/Archives/edgar/data/723125/{a.replace('-', '')}/mu-10k.htm": [ok(b"<html><p>Item 7. Text.</p></html>")]
            for a in pt["MU"].accessions}  # fmt: skip
    t = FakeTransport(urls)
    got = filings.fetch_all(make_client(t), engine, corpus, list(pt["MU"].accessions), NOW)
    assert [f.outcome for f in got] == ["stored", "stored"] and len(t.calls) == 2
    assert (
        filings.fetch_primary(make_client(t), engine, corpus, pt["MU"].accessions[0], NOW).outcome
        == "already stored"
    )


# --- Signals, pass, script, UI, labels ---------------------------------------------------------------


def test_flags_pass_writes_signals_and_queues(dbs):
    engine, corpus = dbs
    engine.execute(
        "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES ('INFQ', ?, '2020-01-01', 't')",
        (INFQ,),
    )
    infq_little_r(dbs)
    filing(engine, INFQ, "0002007825-26-900202", "10-Q", "2026-08-13")
    fp = flags_step.flags_pass(engine, corpus, {"INFQ": INFQ}, NOW)
    c = fp.companies["INFQ"]
    assert c.error == "" and c.restatement == "little_r" and c.non_reliance == "none"
    assert c.restate_delta == "review"
    rows = {r["signal"]: r for r in engine.execute("SELECT * FROM signal WHERE timeframe = 'MY'")}
    assert rows["restatement"]["value_text"] == "little_r" and rows["restatement"]["value"] is None
    assert rows["restate_delta"]["value"] == pytest.approx(4.901, abs=0.01)
    st = engine.execute(
        "SELECT method FROM signal WHERE signal = 'restate_delta' AND timeframe = 'ST'"
    ).fetchone()
    assert "info (weight 0)" in st[0]
    lines = flags_step.local_lines(fp)
    assert lines[0].startswith("Part 3: walk 2 steps (2 over tolerance)")
    # owner answers the item: error keeps it counted, explained releases it
    item = engine.execute(
        "SELECT item_id FROM review_queue WHERE kind = 'm04_restate' ORDER BY item_id"
    ).fetchone()[0]
    from engine import review

    assert review.m04_action(engine, item, "explained", "", "owner", NOW) == "explained"
    assert queue.KIND_LABELS["m04_rating"] and "noted" in queue.ACTIONS["m04_event"]


def test_flags_run_with_a_fake_client(dbs, make_client):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_financials

    engine, corpus = dbs
    infq_little_r(dbs)
    from engine.sec.xbrl_facts import CONCEPT_URL

    routes = {
        CONCEPT_URL.format(cik=GE, taxonomy="us-gaap", tag=t): [ok(b"", 404)]
        for t in run_financials.GE_TAGS
    }
    t = FakeTransport(routes)
    out: list[str] = []
    run_financials.flags_run(
        engine, corpus, {"INFQ": INFQ}, NOW, lambda *a: out.extend(a), make_client(t)
    )
    text = "\n".join(out)
    for want in ("=== Summary (what the owner looks for) ===", "INFQ: 2 steps from 1 filings", "m04_restate proposals: queued 2",
                 "dei error-correction flag", "Filing events, 3 years: 0", "GE walk", "Old filings for walk labels: 0 stored of 0 wanted",
                 "Label file"):  # fmt: skip
        assert want in text, want
    assert all("companyconcept" in u for u, _, _ in t.calls)


def test_financials_tab_shows_part3_sections(tmp_path):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui.app import create_app
    from engine.ui.settings import UiSettings

    data = tmp_path / "data"
    engine = open_db("engine", data)
    corpus = open_db("corpus", data)
    engine.execute(
        "INSERT INTO entity (cik, name, source_ref, fetched_at) VALUES (?, 'Infleqtion, Inc.', 't', 'n')",
        (INFQ,),
    )
    engine.execute(
        "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES ('INFQ', ?, '2020-01-01', 't')",
        (INFQ,),
    )
    infq_little_r((engine, corpus))
    event(engine, INFQ, "0002007825-26-000301", "3.01", "2026-02-03")
    flags_step.flags_pass(engine, corpus, {"INFQ": INFQ}, datetime.now(UTC))
    engine.close()
    corpus.close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text('[watchlist]\ntickers = ["INFQ"]\n', encoding="utf-8")
    with TestClient(create_app(UiSettings(data_dir=data, watchlist=watch))) as c:
        html = c.get("/c/INFQ?tab=financials").text
        items = c.get("/review").text
    for want in ("Filing events (3 years)", "Restatement walk", "Credit ratings", "m04_labels.toml",
                 "error (little r)", "unread", "restate_delta", "review"):  # fmt: skip
        assert want in html, want
    assert "object at 0x" not in html
    assert "restatement step not explained" in items


def test_label_template_has_28_episodes_and_red_flags_blank():
    lf = labels.read(labels.Path(__file__).resolve().parent.parent / "config" / "m04_labels.toml")
    assert lf.error == "" and lf.episodes == 28 and lf.controls == 4
    assert lf.episodes_labelled == 0 and lf.red_flags >= 12 and lf.red_flags_labelled == 0
    assert lf.problems == ()
