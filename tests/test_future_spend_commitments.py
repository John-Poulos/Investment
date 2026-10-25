# ruff: noqa: E501  (fixture rows)
"""M05 Part 2: committed future spend — the per-tag purchase-obligation concepts (D-SEC-31),
the text finder (categories, cancellable and after-period flags, reasons set aside, verified
quotes), the `future_commitment` store, `commitment_cover` (numerator, denominator, history,
labelled breaks, the XBRL / text mark), the lease and after-period lines, the deposit
wording, the refresh hook, the owner script and the commitment lines of the Future spend
section (docs/M05_FUTURE_SPEND.md Part 2; D-M05-18…).

Fixtures: tests/fixtures/m05/commitments/*.txt — labelled SYNTHETIC passages built from the
published figures in the brief (NVIDIA, Meta, Micron; wording reconstructed until the
owner's `export-text` arrives) and two D32 non-tech companies (an airline, an outsourced
apparel retailer); facts entered in the tests. Never calls SEC; never opens the owner's data
folder; never runs a built subcommand's main()."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from engine.future_spend import channels, commit_step, step, views
from engine.future_spend import commitments as cm
from engine.search.passages import ensure_passages
from engine.sec.documents import IndexDoc, store_document
from engine.sec.xbrl_facts import ALL_CONCEPTS, rebuild_series
from tests.conftest import FIXTURES
from tests.test_financials_1b import MU, M, entity, mu
from tests.test_future_spend import NO_MODELS, Args, chf
from tests.test_technicals import load_script

ROOT = Path(__file__).resolve().parent.parent
CM = FIXTURES / "m05" / "commitments"
NVDA, META, AIR, RTL = "0001045810", "0001326801", "0009000011", "0009000012"
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
B = 1_000_000_000
FAB = chf(("NVDA", None, "fabless"))
K26, Q227, K25 = "0001045810-26-000010", "0001045810-26-000070", "0001045810-25-000020"


def read(name: str) -> str:
    return (CM / name).read_text(encoding="utf-8")


def filing(engine, cik, acc, form, filed, report):
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, report_date, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, 'x')",
        (acc, cik, form, filed, report),
    )
    engine.execute("INSERT INTO filing_cik (accession, cik) VALUES (?, ?)", (acc, cik))


def report(engine, corpus, cik, acc, form, filed, period, fixture):
    filing(engine, cik, acc, form, filed, period)
    d = IndexDoc(1, None, "main.htm", f"https://x/{acc}/main.htm", form, None, False)
    store_document(corpus, cik, acc, d, read(fixture).encode("utf-8"), NOW)


def fact(engine, cik, tag, start, end, value, acc, form, filed):
    engine.execute(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession, "
        "form, filed) VALUES (?, 'us-gaap', ?, 'USD', ?, ?, ?, ?, ?, ?)",
        (cik, tag, start, end, value, acc, form, filed),
    )


def nvda(
    engine, corpus, *, q2=True, tag_at_10k=None, q2_fixture="nvda_10q_q2_fy2027_synthetic.txt"
):
    """NVIDIA-shaped: cost of revenue FY2026 $62.48B, TTM at 2026-07-26 $76.73B (Q3 + Q4 of
    FY2026 + the first half of FY2027); PurchaseObligation tagged to 2025-07-27 ($45.77B)."""
    entity(engine, NVDA, "NVIDIA CORP", "0125", "NVDA")
    cor = "CostOfRevenue"
    for start, end, v, acc, form, filed in (
        ("2025-01-27", "2025-04-27", 8.0, "a1", "10-Q", "2025-05-28"),
        ("2025-01-27", "2025-07-27", 18.0, "a2", "10-Q", "2025-08-27"),
        ("2025-01-27", "2025-10-26", 44.0, "a3", "10-Q", "2025-11-19"),
        ("2025-01-27", "2026-01-25", 62.48, K26, "10-K", "2026-02-25"),
        ("2026-01-26", "2026-04-26", 15.0, "a5", "10-Q", "2026-05-27"),
        ("2026-01-26", "2026-07-26", 32.25, Q227, "10-Q", "2026-08-26"),
    ):
        if q2 or filed < "2026-08-01":
            fact(engine, NVDA, cor, start, end, v * B, acc, form, filed)
    fact(
        engine, NVDA, "PurchaseObligation", None, "2025-01-26", 30.8 * B, K25, "10-K", "2025-02-26"
    )
    fact(
        engine,
        NVDA,
        "PurchaseObligation",
        None,
        "2025-07-27",
        45.77 * B,
        "a2",
        "10-Q",
        "2025-08-27",
    )
    if tag_at_10k is not None:
        fact(
            engine,
            NVDA,
            "PurchaseObligation",
            None,
            "2026-01-25",
            tag_at_10k,
            K26,
            "10-K",
            "2026-02-25",
        )
    rebuild_series(engine, NVDA)
    report(engine, corpus, NVDA, K26, "10-K", "2026-02-25", "2026-01-25",
           "nvda_10k_fy2026_note12_synthetic.txt")  # fmt: skip
    if q2:
        report(engine, corpus, NVDA, Q227, "10-Q", "2026-08-26", "2026-07-26",
               q2_fixture)  # fmt: skip


def meta(engine, corpus, ticker="META", q3_total_only=False):
    entity(engine, META, "Meta Platforms, Inc.", "1231", ticker)
    capex = "PaymentsToAcquirePropertyPlantAndEquipment"
    for start, end, v, acc, form, filed in (
        ("2025-01-01", "2025-03-31", 13.0, "m1", "10-Q", "2025-04-30"),
        ("2025-01-01", "2025-06-30", 30.0, "m2", "10-Q", "2025-07-31"),
        ("2025-01-01", "2025-09-30", 50.0, "m3", "10-Q", "2025-10-30"),
        ("2025-01-01", "2025-12-31", 72.0, "mk", "10-K", "2026-01-29"),
        ("2026-01-01", "2026-03-31", 25.0, "m5", "10-Q", "2026-04-29"),
        ("2026-01-01", "2026-06-30", 54.0, "mq2", "10-Q", "2026-07-30"),
    ):
        fact(engine, META, capex, start, end, v * B, acc, form, filed)
    fact(engine, META, "UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount", None,
         "2026-06-30", 41.2 * B, "mq2", "10-Q", "2026-07-30")  # fmt: skip
    rebuild_series(engine, META)
    report(engine, corpus, META, "mq2", "10-Q", "2026-07-30", "2026-06-30",
           "meta_10q_q2_2026_synthetic.txt")  # fmt: skip
    if q3_total_only:  # live check 2: the newest report states a total, no PP&E figure
        fact(engine, META, capex, "2026-01-01", "2026-09-30", 84.0 * B, "mq3", "10-Q",
             "2026-10-22")  # fmt: skip
        rebuild_series(engine, META)
        report(engine, corpus, META, "mq3", "10-Q", "2026-10-22", "2026-09-30",
               "meta_10q_q3_2026_total_only_synthetic.txt")  # fmt: skip


def airline(engine, corpus):
    entity(engine, AIR, "Synthetic Airline", "1231", "AIRX")
    for start, end, v, acc, filed in (
        ("2024-01-01", "2024-12-31", 3.8, "air24", "2025-02-10"),
        ("2025-01-01", "2025-12-31", 4.0, "air25", "2026-02-10"),
    ):
        fact(engine, AIR, "PaymentsToAcquirePropertyPlantAndEquipment", start, end, v * B, acc,
             "10-K", filed)  # fmt: skip
    rebuild_series(engine, AIR)
    report(engine, corpus, AIR, "air24", "10-K", "2025-02-10", "2024-12-31",
           "airline_10k_fy2024_synthetic.txt")  # fmt: skip
    report(engine, corpus, AIR, "air25", "10-K", "2026-02-10", "2025-12-31",
           "airline_10k_fy2025_synthetic.txt")  # fmt: skip


def retailer(engine, corpus):
    entity(engine, RTL, "Synthetic Apparel", "0131", "RTLX")
    fact(engine, RTL, "CostOfRevenue", "2025-02-02", "2026-01-31", 7.0 * B, "rtl25", "10-K",
         "2026-03-20")  # fmt: skip
    fact(engine, RTL, "PaymentsToAcquirePropertyPlantAndEquipment", "2025-02-02", "2026-01-31",
         0.4 * B, "rtl25", "10-K", "2026-03-20")  # fmt: skip
    rebuild_series(engine, RTL)
    report(engine, corpus, RTL, "rtl25", "10-K", "2026-03-20", "2026-01-31",
           "retailer_10k_fy2025_synthetic.txt")  # fmt: skip


def run(engine, corpus, companies, channel_file, now=NOW):
    return commit_step.commitments_pass(engine, corpus, companies, now, chf=channel_file,
                                        mf=NO_MODELS)  # fmt: skip


def mrow(engine, cik, tf="MY"):
    return engine.execute(
        "SELECT * FROM signal WHERE cik = ? AND module_id = 'M05' AND signal = "
        "'commitment_cover' AND timeframe = ? ORDER BY as_of DESC",
        (cik, tf),
    ).fetchone()


def info(engine, cik, tf="MY") -> bool:
    return "info (weight 0)" in mrow(engine, cik, tf)["method"]


# --- concepts (D-SEC-31) -----------------------------------------------------------------------


def test_purchase_obligation_concepts_one_tag_each_never_merged():
    for name, tag in cm.XBRL_CONCEPTS:
        c = ALL_CONCEPTS[name]
        assert len(c.tags) == 1 and f"{c.tags[0][0]}:{c.tags[0][1]}" == tag and c.kind == "instant"


# --- the text finder (rule 7) ------------------------------------------------------------------


def test_nvda_10k_categories_cancellable_and_set_asides():
    ts = cm.scan_text(read("nvda_10k_fy2026_note12_synthetic.txt"), "2026-01-25")
    got = [(f.category, f.amount / B, f.cancellable) for f in ts.findings]
    assert got == [("supply_capacity", 95.2, True), ("cloud", 27.0, False),
                   ("investment", 11.4, False), ("other", 3.4, False)]  # fmt: skip
    reasons = {a.reason for a in ts.set_aside}
    assert "table row (parsed schedules deferred, S2.3)" in reasons
    assert "no dollar amount" in reasons
    assert all(f.as_of == "2026-01-25" and not f.after_period for f in ts.findings)


def test_nvda_10q_comparative_change_and_hypothetical_set_aside():
    ts = cm.scan_text(read("nvda_10q_q2_fy2027_synthetic.txt"), "2026-07-26")
    assert [(f.category, f.amount / B) for f in ts.findings] == [("supply_capacity", 279.0)]
    assert ts.findings[
        0
    ].cancellable  # "cancelable, rescheduled, or adjustable" in the next sentence
    reasons = [a.reason for a in ts.set_aside]
    assert any(r.startswith("comparative as of 2026-01-25") for r in reasons)
    assert "a change, not a balance" in reasons
    assert "hypothetical wording before the amount" in reasons


def test_schedule_lines_and_forward_wording_are_set_aside():
    text = ("As of July 26, 2026, our purchase obligations totaled $279 billion, of which $92 billion "
            "is due in the remainder of fiscal year 2027. We expect purchase commitments of $300 "
            "billion by year end.")  # fmt: skip
    ts = cm.scan_text(text, "2026-07-26")
    assert [f.amount / B for f in ts.findings] == [279.0]
    assert ts.findings[0].category == "purchase_total"  # scope not split
    reasons = [a.reason for a in ts.set_aside]
    assert "a schedule line (parsed schedules deferred, S2.3)" in reasons
    assert "forward-looking wording (guidance is M02's)" in reasons


def test_noncancelable_never_sets_the_flag():
    assert cm.cancellable("Our non-cancelable purchase obligations were $5 billion.", 0, 55) == ""
    assert cm.cancellable("These orders are not cancellable.", 0, 33) == ""
    t = "We had purchase obligations of $5 billion. They are cancelable before shipment."
    assert cm.cancellable(t, 0, 42) == "in the next sentence"


def test_meta_leases_and_after_period_line():
    ts = cm.scan_text(read("meta_10q_q2_2026_synthetic.txt"), "2026-06-30")
    got = [(f.category, f.amount / B, f.after_period, f.stated_date) for f in ts.findings]
    assert got == [("ppe", 349.31, False, None), ("lease_not_commenced", 41.2, False, None),
                   ("lease_not_commenced", 68.0, True, "2026-07-31")]  # fmt: skip
    assert ts.findings[0].scope_label == "PP&E (non-cancelable as stated)"
    assert not ts.findings[0].cancellable


def test_deposit_wording_is_its_own_category():
    ts = cm.scan_text(read("mu_10k_fy2026_deposits_synthetic.txt"), "2026-08-27")
    assert [(f.category, f.amount / B) for f in ts.findings] == [("ppe", 9.1),
                                                                 ("customer_deposit", 12.75)]  # fmt: skip
    assert not ts.findings[1].cancellable  # never a cancellable commitment


def test_d32_airline_aircraft_is_ppe_and_fuel_is_supply():
    ts = cm.scan_text(read("airline_10k_fy2025_synthetic.txt"), "2025-12-31")
    assert [(f.category, f.amount / B) for f in ts.findings] == [("ppe", 14.6),
                                                                 ("supply_capacity", 1.2)]  # fmt: skip


def test_verified_rejects_a_shifted_span():
    text = read("nvda_10k_fy2026_note12_synthetic.txt")
    f = cm.scan_text(text, "2026-01-25").findings[0]
    assert cm.verified(text, text, f)
    from dataclasses import replace

    assert not cm.verified(text, text, replace(f, start=f.start + 3))
    assert not cm.verified(text, "an unrelated passage", f)


# --- store and commitment_cover (rules 6-7, D-M05-3) -----------------------------------------------


def test_nvda_10k_cover_1_52_short_history_with_the_tag_across_a_labelled_break(dbs):
    engine, corpus = dbs
    nvda(engine, corpus, q2=False)
    cp = run(engine, corpus, {"NVDA": NVDA}, FAB)
    r = cp.results["NVDA"]
    c = r.cover
    assert round(c.value, 2) == 1.52 and c.state == "short_history"
    assert c.denom.what == "TTM cost of revenue" and c.denom.value == 62.48 * B
    assert c.point.cancellable and c.other_prior.series == "xbrl:us-gaap:PurchaseObligation"
    assert [b.split(" (")[0] for b in c.beside] == ["cloud services $27.00B", "investments $11.40B",
                                                    "other $3.40B"]  # fmt: skip
    row = mrow(engine, NVDA)
    assert row["value_text"] == "short_history" and round(row["value"], 2) == 1.52
    assert (
        "labelled break, not compared" in row["method"]
        and "cancelable / adjustable" in row["method"]
    )
    assert not info(engine, NVDA) and not info(engine, NVDA, "PT") and info(engine, NVDA, "ST")


def test_nvda_10q_cover_3_64_tag_stopped_and_text_used(dbs):
    engine, corpus = dbs
    nvda(engine, corpus)
    r = run(engine, corpus, {"NVDA": NVDA}, FAB).results["NVDA"]
    c = r.cover
    assert c.point.as_of == "2026-07-26" and c.point.amount == 279 * B
    assert round(c.denom.value / B, 2) == 76.73 and c.denom.basis == "TTM"
    assert round(c.value, 2) == 3.64 and c.state == "short_history"
    assert c.other_prior.amount == 45.77 * B and c.other_prior.as_of == "2025-07-27"
    assert any(
        "PurchaseObligation last tagged $45.77B at 2025-07-27 (stopped" in s for s in c.stale
    )
    # both reports stored, every text amount verified and kept with its offsets
    n = engine.execute("SELECT count(*) FROM future_commitment WHERE cik = ? AND source = 'text'",
                       (NVDA,)).fetchone()[0]  # fmt: skip
    assert n == 5
    assert "3.64 years" in commit_step.line(r) and "✓ MY/PT" in commit_step.line(r)


def test_two_companies_with_the_same_tag_and_date_never_collide(dbs):
    # live check 2: AMZN, INTC, META, RIVN failed on UNIQUE future_commitment.key because the
    # XBRL key had no company in it and an earlier company stored the same tag on the same date
    engine, corpus = dbs
    nvda(engine, corpus)
    twin = "0009000013"
    entity(engine, twin, "Twin Co", "0126", "TWIN")
    fact(engine, twin, "PurchaseObligation", None, "2025-07-27", 1.0 * B,
         "0009000013-25-000001", "10-Q", "2025-08-27")  # fmt: skip
    cp = run(engine, corpus, {"NVDA": NVDA, "TWIN": twin},
             chf(("NVDA", None, "fabless"), ("TWIN", None, "fabless")))  # fmt: skip
    assert cp.errors == {}
    for cik in (NVDA, twin):
        n = engine.execute("SELECT count(*) FROM future_commitment WHERE cik = ? AND source = "
                           "'xbrl' AND as_of = '2025-07-27'", (cik,)).fetchone()[0]  # fmt: skip
        assert n == 1, cik


def test_letters_of_credit_are_not_commitments():
    t = (
        "As of September 30, 2026, we had $1.53 billion of unused letters of credit outstanding, "
        "the majority of which was related to our long-term infrastructure purchase commitments."
    )
    ts = cm.scan_text(t, "2026-09-30")
    assert ts.findings == [] and "letter of credit" in ts.set_aside[0].reason


def test_hyperscaler_without_a_ppe_total_falls_back_to_the_stated_total(dbs):
    # owner, live check 2 (D-M05-26): META read stale from 2016 because only PP&E counted
    engine, corpus = dbs
    meta(engine, corpus, q3_total_only=True)
    hyper = chf(("META", None, "hyperscaler"))
    c = run(engine, corpus, {"META": META}, hyper).results["META"].cover
    assert c.point.as_of == "2026-09-30" and c.point.amount == 454.52 * B
    assert c.point.series == "text:purchase_total" and c.numerator_category == "purchase_total"
    assert any("scope not split" in m and "D-M05-26" in m for m in c.marks)


def test_xbrl_and_text_more_than_5pct_apart_are_both_shown_with_a_mark(dbs):
    engine, corpus = dbs
    nvda(engine, corpus, q2=False, tag_at_10k=90.0 * B)
    c = run(engine, corpus, {"NVDA": NVDA}, FAB).results["NVDA"].cover
    assert c.point.series == "text:supply_capacity"  # text wins a tie on the date
    assert c.marks and "XBRL us-gaap:PurchaseObligation $90.00B vs text $95.20B" in c.marks[0]


def test_meta_ppe_numerator_on_ttm_capex_leases_and_after_period_separate(dbs):
    engine, corpus = dbs
    meta(engine, corpus)
    r = run(engine, corpus, {"META": META}, chf(("META", None, "hyperscaler"))).results["META"]
    c = r.cover
    assert c.numerator_category == "ppe" and c.denom.what == "TTM capex"
    assert round(c.denom.value / B, 2) == 96.0 and round(c.value, 2) == 3.64
    assert c.leases and c.leases[0].startswith("leases not yet commenced $41.20B")
    assert c.after_period and "2026-07-31" in c.after_period[0] and "$68.00B" in c.after_period[0]
    tag = engine.execute("SELECT scope_label FROM future_commitment WHERE cik = ? AND source = 'xbrl'",
                         (META,)).fetchone()[0]  # fmt: skip
    assert tag == "labelled by the quote: leases not yet commenced"
    assert all(info(engine, META, tf) for tf in ("MY", "PT", "ST"))  # not fabless


def test_d32_airline_rising_against_its_own_history_info_only(dbs):
    engine, corpus = dbs
    airline(engine, corpus)
    c = run(engine, corpus, {"AIRX": AIR}, chf()).results["AIRX"].cover
    assert round(c.value, 2) == 3.65 and round(c.prior_value, 2) == 3.16
    assert c.state == "RISING" and c.denom.basis == "FY"
    assert c.beside and c.beside[0].startswith("supply and capacity $1.20B")
    assert info(engine, AIR)  # channel unset: info only


def test_d32_retailer_outsourced_leads_unset_reads_missing_with_beside(dbs):
    engine, corpus = dbs
    retailer(engine, corpus)
    c = run(engine, corpus, {"RTLX": RTL}, chf(("RTLX", None, "outsourced"))).results["RTLX"].cover
    assert round(c.value, 2) == 0.50 and c.state == "short_history" and c.point.cancellable
    assert not info(engine, RTL)
    r = run(engine, corpus, {"RTLX": RTL}, chf()).results["RTLX"]
    assert r.cover.missing == "no stated PP&E commitment total (other categories shown beside)"
    row = mrow(engine, RTL)
    assert row["value"] is None and row["value_text"] is None
    assert "beside: supply and capacity $3.50B" in row["method"]


def test_not_applicable_and_pass_not_run(dbs):
    engine, corpus = dbs
    nvda(engine, corpus, q2=False)
    r = run(engine, corpus, {"NVDA": NVDA}, chf(("NVDA", None, "n/a"))).results["NVDA"]
    assert r.not_applicable == "not applicable (channel n/a)" and r.scan is None
    assert engine.execute("SELECT count(*) FROM future_commitment").fetchone()[0] == 0
    # the app reads stored rows only: before any pass the reason says so
    v = commit_step.name_result(engine, "NVDA", NVDA, NOW, chf=FAB, mf=NO_MODELS)
    assert v.row().missing.startswith("commitments pass not run")


def test_rows_replaced_per_pass_first_seen_kept_and_passage_ids(dbs):
    engine, corpus = dbs
    nvda(engine, corpus, q2=False)
    ensure_passages(corpus)
    run(engine, corpus, {"NVDA": NVDA}, FAB)
    first = dict(engine.execute("SELECT key, first_seen_at FROM future_commitment").fetchall())
    later = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    run(engine, corpus, {"NVDA": NVDA}, FAB, now=later)
    again = dict(engine.execute("SELECT key, first_seen_at FROM future_commitment").fetchall())
    assert again == first  # replaced, first-seen carried
    pids = [r[0] for r in engine.execute(
        "SELECT passage_id FROM future_commitment WHERE source = 'text'")]  # fmt: skip
    assert pids and all(p is not None for p in pids)
    st = cm.scan_state(engine, NVDA)
    assert st["version"] == cm.FINDER_VERSION and st["newest_period"] == "2026-01-25"


def test_unverified_quotes_are_never_stored(dbs, monkeypatch):
    engine, corpus = dbs
    nvda(engine, corpus, q2=False)
    monkeypatch.setattr(cm, "quote_found", lambda q, p: False)
    r = run(engine, corpus, {"NVDA": NVDA}, FAB).results["NVDA"]
    assert r.scan.reports[0].unverified == 4
    assert (
        engine.execute("SELECT count(*) FROM future_commitment WHERE source = 'text'").fetchone()[0]
        == 0
    )
    # the only series left is the tag, which stopped 182 days before the newest report
    assert r.cover.missing.startswith("last stated 2025-07-27 (us-gaap:PurchaseObligation")
    assert mrow(engine, NVDA)["value"] is None


# --- the deposits mark (rule 6, D-M05-11) -------------------------------------------------------------


def test_deposit_wording_found_replaces_the_part1_mark(dbs):
    engine, corpus = dbs
    mu(engine)
    for end, v, filed in (("2025-08-28", 169, "2025-10-03"), ("2026-08-27", 13_000, "2026-10-03")):
        fact(
            engine,
            MU,
            "ContractWithCustomerLiability",
            None,
            end,
            v * M,
            f"mu-{end}",
            "10-K",
            filed,
        )
    channels_mu = chf(("MU", None, "fab_owner"))
    r = step.name_result(engine, "MU", MU, date(2026, 10, 21), chf=channels_mu, mf=NO_MODELS)
    assert "commitments pass not run" in r.deposits.text()
    report(engine, corpus, MU, "0000723125-26-000030", "10-K", "2026-10-03", "2026-08-27",
           "mu_10k_fy2026_deposits_synthetic.txt")  # fmt: skip
    cp = run(engine, corpus, {"MU": MU}, channels_mu)
    assert "customer deposit wording $12.75B" in cp.results["MU"].cover.deposits[0]
    r = step.name_result(engine, "MU", MU, date(2026, 10, 21), chf=channels_mu, mf=NO_MODELS)
    assert "deposit wording found: $12.75B at 2026-08-27" in r.deposits.text()


# --- refresh hook and owner script -------------------------------------------------------------------


def test_run_local_part_never_fails(dbs, monkeypatch):
    engine, corpus = dbs

    def boom(*a, **k):
        raise RuntimeError("bad")

    monkeypatch.setattr(commit_step, "commitments_pass", boom)
    out = commit_step.run_local_part(engine, corpus, {}, NOW, clock=lambda: 0.0)
    assert out == ["M05 commitments — local pass (Part 2, 0 requests) (0.0 s):",
                   "  M05 commitments: error — RuntimeError: bad"]  # fmt: skip


def test_refresh_runs_part2_right_after_part1_and_before_m07():
    src = (ROOT / "scripts" / "run_refresh.py").read_text(encoding="utf-8")
    i = src.index("prices += future_spend_commitments_local_step(engine, corpus, report)")
    assert src.index("prices += future_spend_local_step(engine, report)") < i
    assert i < src.index("prices += ownership_local_step(engine, report)")


def test_script_commitments_on_injected_dbs(dbs, tmp_path, monkeypatch):
    engine, corpus = dbs
    nvda(engine, corpus)
    rm = load_script("run_m05")
    monkeypatch.setattr(channels, "load_safe", lambda *a: FAB)
    log = rm.Log(tmp_path / "logs" / "c.txt")
    args = Args(companies={"NVDA": NVDA})
    assert rm.run_commitments(args, log, tmp_path, engine=engine, corpus=corpus, now=NOW) == 0
    log.close()
    text = (tmp_path / "logs" / "c.txt").read_text(encoding="utf-8")
    assert "NVDA [fabless]: commitment_cover short_history 3.64 years" in text
    assert "tag us-gaap:PurchaseObligation: 2 instants, last $45.77B at 2025-07-27" in text
    assert "taken supply and capacity $279.00B at 2026-07-26 [cancellable]" in text
    assert "set aside (a change, not a balance; $183.8 billion)" in text
    assert "=== Summary" in text and "SEC requests: 0" in text and "signal +3" in text


def test_script_export_text_writes_trimmed_excerpts(dbs, tmp_path):
    engine, corpus = dbs
    nvda(engine, corpus)
    rm = load_script("run_m05")
    log = rm.Log(tmp_path / "logs" / "x.txt")
    args = Args(tickers="NVDA", out_dir=tmp_path)
    assert rm.run_export_text(args, log, tmp_path, engine=engine, corpus=corpus, now=NOW) == 0
    log.close()
    data = json.loads((tmp_path / "m05_text_nvda_20261021.json").read_text(encoding="utf-8"))
    forms = [d["form"] for d in data["documents"]]
    assert forms == ["10-K", "10-Q"]
    ex = data["documents"][1]["excerpts"]
    assert any("$279 billion" in e["text"] for e in ex)
    full = read("nvda_10q_q2_fy2027_synthetic.txt")
    assert all(full[e["start"] : e["end"]] == e["text"] for e in ex)


# --- the commitment lines in the Future spend section (D-UI-39) ---------------------------------------


def test_view_shows_the_cover_lines_and_quotes(dbs):
    engine, corpus = dbs
    meta(engine, corpus)
    hyper = chf(("META", None, "hyperscaler"))
    run(engine, corpus, {"META": META}, hyper)
    v = views.company_view(engine, META, "META", date(2026, 10, 21), chf=hyper, mf=NO_MODELS)
    assert v.commitment.state == "short_history" and v.commitment.value == "3.64 years"
    assert any(x.startswith("signed after the period $68.00B") for x in v.commit_lines)
    assert v.commit_quotes and v.commit_quotes[0]["quote"]


def test_money_tab_renders_the_commitment_block(tmp_path, monkeypatch):
    from tests.test_technicals_tab import _app

    def fill(engine, corpus):
        meta(engine, corpus, ticker=None)  # _app registers the ticker
        run(engine, corpus, {"META": META}, chf(("META", None, "hyperscaler")))

    monkeypatch.setattr(views.channels_mod, "load_safe",
                        lambda *a: chf(("META", None, "hyperscaler")))  # fmt: skip
    client = _app(tmp_path, monkeypatch, fill, {"META": META})
    html = client.get("/c/META?tab=money").text
    assert "Committed future spend" in html and "3.64 years" in html
    assert "leases not yet commenced" in html and "signed after the period" in html
    assert "object at 0x" not in html and "<built-in method" not in html


# --- live check 1 (2026-10-23): fixes, each failing before -------------------------------------


def _runon() -> str:
    """No sentence boundary for > 1,200 characters: two trigger hits more than 600 apart
    give overlapping clipped spans that both hold the amount, with different categories."""
    return ("(In millions)\n\nInventory purchase obligations " + "word " * 90 + "came to $5 billion "
            + "word " * 40 + "purchase commitments " + "word " * 200)  # fmt: skip


def test_overlapping_spans_read_an_amount_once():
    ts = cm.scan_text(_runon(), "2026-06-30")
    starts = [f.amount_start for f in ts.findings]
    assert len(starts) == len(set(starts)) == 1


def test_store_skips_a_repeated_key_and_a_company_error_never_stops_the_others(dbs, monkeypatch):
    engine, corpus = dbs
    nvda(engine, corpus, q2=False)
    cs = cm.scan_company(engine, corpus, NVDA, "2026-10-21")
    f = cs.reports[0].findings[0]
    cs.reports[0].findings.append(f)  # the same amount twice (live check 1: AMZN, INTC, META, RIVN)
    tag, pts = next(iter(cs.xbrl.items()))
    cs.xbrl[tag] = pts + [pts[-1]]
    engine.execute("BEGIN")
    n = cm.store(engine, cs, NOW)
    engine.execute("COMMIT")
    assert cs.duplicates == 2 and n == engine.execute(
        "SELECT count(*) FROM future_commitment").fetchone()[0]  # fmt: skip
    real = cm.scan_company
    monkeypatch.setattr(cm, "scan_company", lambda e, c, cik, today: (
        (_ for _ in ()).throw(RuntimeError("boom")) if cik == META else real(e, c, cik, today)))  # fmt: skip
    meta(engine, corpus)
    both = chf(("NVDA", None, "fabless"), ("META", None, "hyperscaler"))
    cp = run(engine, corpus, {"NVDA": NVDA, "META": META}, both)
    assert "META" in cp.errors and "NVDA" in cp.results


def test_period_charges_and_provisions_are_not_commitments():
    ts = cm.scan_text(read("nvda_10q_q2_fy2027_live1_synthetic.txt"), "2026-07-26")
    got = [(f.category, f.amount / B, f.as_of) for f in ts.findings]
    assert got == [("supply_capacity", 279.0, "2026-07-26"),
                   ("customer_deposit", 2.8, "2026-07-26")]  # fmt: skip
    by = {}
    for a in ts.set_aside:
        if a.raw:
            by.setdefault(a.reason, []).append(a.raw)
    assert by[cm.REASON_FLOW] == ["$0.4 billion", "$985 million", "$2.1 billion", "$177 million",
                                  "$280 million", "$4.5 billion"]  # fmt: skip
    assert by[cm.REASON_PERIOD] == ["$15.6 billion", "$7.5 billion"]
    assert by[cm.REASON_FROM] == ["$119 billion"]
    assert any(r.startswith("comparative as of 2026-01-25") and "paired" in r for r in by)
    mrvl = ("During the six months ended August 1, 2026, the Company recognized a net "
            "restructuring expense of $5.7 million relating to contractual obligation offset by "
            "the changes in accrual estimates.")  # fmt: skip
    ts = cm.scan_text(mrvl, "2026-08-01")
    assert not ts.findings and [a.reason for a in ts.set_aside] == [cm.REASON_FLOW]
    # a balance with "totaled" and a payment window stays a balance
    ok = "As of June 27, 2026, purchase obligations totaled $57.0 billion for components."
    assert [f.amount / B for f in cm.scan_text(ok, "2026-06-27").findings] == [57.0]


def test_nvda_from_to_sentence_reads_279_over_76_73_short_history(dbs):
    engine, corpus = dbs
    nvda(engine, corpus, q2_fixture="nvda_10q_q2_fy2027_live1_synthetic.txt")
    r = run(engine, corpus, {"NVDA": NVDA}, FAB).results["NVDA"]
    c = r.cover
    assert c.numerator_category == "supply_capacity" and c.point.amount == 279 * B
    assert round(c.value, 2) == 3.64 and c.state == "short_history"
    assert any("customer deposit wording $2.80B" in x for x in c.deposits)


def test_one_point_per_date_takes_the_largest_amount_of_the_newest_filing():
    def row(amount, filed, cat="supply_capacity"):
        return {"after_period": 0, "source": "text", "category": cat, "tag": None,
                "as_of": "2026-07-26", "amount": amount, "accession": filed, "filed": filed,
                "cancellable": 0, "quote": "q", "form": "10-Q"}  # fmt: skip

    pts = cm.series_points([row(119 * B, "2026-08-26"), row(279 * B, "2026-08-26"),
                            row(300 * B, "2026-08-01")], "text:supply_capacity")  # fmt: skip
    assert pts["2026-07-26"].amount == 279 * B  # newest filing, then the largest


def test_several_dates_pair_with_amounts_in_order():
    text = "(In millions)\n\n"
    q = "At June 30, 2026, and December 31, 2025, total purchase obligations were $1,130 and $1,267."
    ts = cm.scan_text(text + q, "2026-06-30")
    assert [(f.amount, f.as_of) for f in ts.findings] == [(1130e6, "2026-06-30")]
    assert ts.set_aside[0].raw == "$1,267" and "paired" in ts.set_aside[0].reason
    q = "At December 31, 2025 and 2024, total purchase obligations were $1,267 and $1,393."
    ts = cm.scan_text(text + q, "2025-12-31")
    assert [(f.amount, f.as_of) for f in ts.findings] == [(1267e6, "2025-12-31")]
    assert ts.set_aside[0].reason.startswith("comparative as of 2024-12-31")
    assert cm.listed_dates("At December 31, 2025 and 2024, x") == [
        (3, date(2025, 12, 31)), (25, date(2024, 12, 31))]  # fmt: skip


def test_trade_in_and_repurchase_commitments_set_aside_leases_always_leases():
    text = "(In millions)\n\n"
    q = ("At June 30, 2026, and December 31, 2025, total contractual trade-in commitments were "
         "$1,130 and $1,267. As of June 30, 2026, contingent repurchase commitments were $163.")  # fmt: skip
    ts = cm.scan_text(text + q, "2026-06-30")
    assert not ts.findings
    assert {a.reason for a in ts.set_aside} == {cm.REASON_NOT_PURCHASE}
    q = ("As of December 31, 2023, we have entered into leases that have not yet commenced of "
         "$430, primarily for a maintenance, repair and overhaul hangar that will support "
         "military aircraft programs.")  # fmt: skip
    ts = cm.scan_text(text + q, "2023-12-31")
    assert [(f.category, f.amount) for f in ts.findings] == [("lease_not_commenced", 430e6)]
    q = (
        "As of March 31, 2025, we had additional operating and finance leases, primarily for "
        "datacenters, that had not yet commenced of $4.4 billion and $94.8 billion, respectively."
    )
    ts = cm.scan_text(q, "2025-03-31")
    assert [f.category for f in ts.findings] == ["lease_not_commenced"] * 2


def test_log_is_short_by_default_and_verbose_prints_everything(dbs):
    engine, corpus = dbs
    nvda(engine, corpus, q2_fixture="nvda_10q_q2_fy2027_live1_synthetic.txt")
    filing(engine, NVDA, "old1", "10-Q", "2025-05-28", "2025-04-27")
    filing(engine, NVDA, "old2", "10-Q", "2024-05-28", "2024-04-28")
    r = run(engine, corpus, {"NVDA": NVDA}, FAB).results["NVDA"]
    short = commit_step.detail_lines(r)
    full = commit_step.detail_lines(r, verbose=True)
    assert "    2 older filing(s) with no stored main document" in short
    assert not any("old1" in x for x in short) and any("old1" in x for x in full)
    head = next(x for x in short if "0001045810-26-000070" in x)
    assert "2 taken, " in head and f"{cm.REASON_FLOW} 6" in head
    assert not any(x.startswith("      set aside (no dollar amount") for x in short)
    assert any(x.startswith("      set aside (no dollar amount") for x in full)
    assert len(short) < len(full)


@pytest.mark.parametrize("fixture", sorted(p.name for p in CM.glob("*.txt")))
def test_fixtures_are_labelled_synthetic(fixture):
    assert read(fixture).startswith("SYNTHETIC FIXTURE (M05 Part 2")
