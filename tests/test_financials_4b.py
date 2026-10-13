# ruff: noqa: E501  (fixture rows)
"""M04 Part 4b-lite: going-concern and covenant text — sentence classes, the current-report
rule, the gate trigger, signals, review items and baselines, owner answers, the `gate-text`
run, the refresh hook and the Gate text block (docs/M04_BUILD_LOG.md Part 4b; D-M04-34,
-71, -95…99).

Fixtures: tests/fixtures/m04/gate_text/*.txt (S10's documents trimmed to the sentences;
wording reconstructed where the repo holds no real text — README "Part 4b"). Never calls
SEC; never opens the owner's data folder."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine.financials import gate, gate_step, gate_text, gate_text_step, gate_view, models, queue
from engine.sec.documents import IndexDoc, store_document
from tests.conftest import FIXTURES
from tests.test_financials_4a import RIVN, entity, rivian

GT = FIXTURES / "m04" / "gate_text"
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
TODAY = "2026-10-13"
NVTA, FSR, PTRA, MVST, RIOT = "0001501134", "0001720990", "0001820630", "0001760689", "0001167419"
UTI, ALB, BA, INFQ, SPAC = "0001261654", "0000915913", "0000012927", "0002007825", "0000077777"
MF = models.parse({"company": [
    {"ticker": "INFQ", "cik": INFQ, "tag": "spac_shell", "before": "2026-02-13", "reason": "shell years", "source": "D-M04-8"},
]})  # fmt: skip


def read(name: str) -> str:
    return (GT / name).read_text(encoding="utf-8")


def filing(engine, cik, acc, form, filed, report=None):
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, report_date, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, 'x')",
        (acc, cik, form, filed, report),
    )
    engine.execute("INSERT INTO filing_cik (accession, cik) VALUES (?, ?)", (acc, cik))


def doc(corpus, cik, acc, text, doc_type="10-K", name="doc.txt"):
    d = IndexDoc(1, None, name, f"https://x/{acc}/{name}", doc_type, None, False)
    store_document(corpus, cik, acc, d, text.encode("utf-8"), NOW)


def report(
    engine, corpus, cik, acc, form, filed, period, fixture, *, doc_type=None, name="main.txt"
):
    filing(engine, cik, acc, form, filed, period)
    doc(corpus, cik, acc, read(fixture), doc_type or form, name)


def classes(text: str, exhibit: bool = False) -> list[str]:
    return [h.klass for h in gate_text.scan_text(text, exhibit=exhibit).hits]


# --- Sentence classes (D-M04-34, D-M04-95) ------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "want", "exhibit"),
    [
        (
            "fisker_10k_fy2023_excerpt.txt",
            ["management_exists", "boilerplate", "auditor_gc", "forbearance"],
            False,
        ),
        ("invitae_10q_q3_2023_excerpt.txt", ["management_exists"], False),
        ("invitae_10q_q2_2023_excerpt.txt", ["boilerplate"], False),
        ("proterra_10k_fy2022_excerpt.txt", ["breach_unwaived", "reclass_covenant"], False),
        ("microvast_10k_fy2025_excerpt.txt", ["auditor_cam", "alleviated", "alleviated"], False),
        ("riot_10k_fy2025_excerpt.txt", ["hypothetical"], False),
        ("uti_10q_q3_fy2025_excerpt.txt", ["breach_waived", "breach_waived", "compliant"], False),
        ("albemarle_ex10_1_q3_2024_excerpt.txt", ["reset", "reset"], True),
        ("boeing_10k_fy2023_excerpt.txt", ["compliant", "boilerplate"], False),
        ("infq_10k_fy2025_excerpt.txt", ["alleviated"], False),
        (
            "synthetic_cases_excerpt.txt",
            [
                "ifrs_material_uncertainty",
                "negated",
                "listing_deficiency",
                "no_default",
                "acceleration",
            ],
            False,
        ),
    ],
)
def test_fixture_sentences_get_their_class(fixture, want, exhibit):
    assert classes(read(fixture), exhibit) == want


def test_effects_by_class_follow_d_m04_34():
    fail = {k for k, v in gate_text.CLASSES.items() if v[1] == "fail"}
    warn = {k for k, v in gate_text.CLASSES.items() if v[1] == "warn"}
    assert fail == {"auditor_gc", "management_exists", "breach_unwaived", "forbearance",
                    "reclass_covenant", "acceleration", "delisting"}  # fmt: skip
    assert warn == {"alleviated", "auditor_cam", "ifrs_material_uncertainty", "breach_waived",
                    "reset", "listing_deficiency"}  # fmt: skip
    assert gate_text.CLASSES["hypothetical"][1] == "hypothetical"
    assert {
        gate_text.CLASSES[k][1] for k in ("boilerplate", "negated", "compliant", "no_default")
    } == {"none"}


def test_negations_hypotheticals_headings_and_exhibit_terms():
    t = (
        "We do not believe there is substantial doubt about our ability to continue as a going concern. "
        "Substantial doubt about our ability to continue as a going concern does not exist. "
        "Management's plans do not alleviate the substantial doubt about the Company's ability to continue as a going concern. "
        "Any breach of these covenants could result in an event of default under the indenture."
    )
    assert classes(t) == ["negated", "negated", "management_exists"]
    assert gate_text.scan_text(t).hypothetical_cov == 1
    assert (
        classes(
            "Substantial Doubt About the Company's Ability to Continue as a Going Concern\n\nOther text."
        )
        == []
    )
    # a credit agreement defines "Event of Default" and forbearance: only the reset terms count
    ex = (
        "“Event of Default” has the meaning set forth in Section 8.01. The Lenders may agree to a forbearance. "
        "The parties amend the financial covenants in Section 7.11 as follows."
    )
    assert classes(ex, exhibit=True) == ["reset"]
    # "not in compliance" outside a debt context (NVIDIA's 68 EFTS hits) is no covenant class
    assert (
        classes("Products that are not in compliance with export regulations may be seized.") == []
    )


def test_waiver_in_the_next_sentence_counts_only_when_it_refers_back():
    t = (
        "As of December 31, 2022, we were not in compliance with the leverage covenant under the Credit Agreement. "
        "We obtained waivers from the holders of our Convertible Notes of their cross-default provisions."
    )
    assert classes(t)[0] == "breach_unwaived"
    t2 = t.replace("of their cross-default provisions", "for such breach")
    assert classes(t2)[0] == "breach_waived"


# --- Storing, the current report and the gate (D-M04-96) -----------------------------------------


def invitae_reports(engine, corpus):
    entity(engine, NVTA, "INVITAE CORP", "8071", ticker="NVTA")
    report(
        engine,
        corpus,
        NVTA,
        "0001501134-23-000060",
        "10-Q",
        "2023-08-08",
        "2023-06-30",
        "invitae_10q_q2_2023_excerpt.txt",
    )
    report(
        engine,
        corpus,
        NVTA,
        "0001501134-23-000079",
        "10-Q",
        "2023-11-08",
        "2023-09-30",
        "invitae_10q_q3_2023_excerpt.txt",
    )


def test_invitae_q2_boilerplate_no_trigger_then_q3_exists_fails_the_gate(dbs):
    engine, corpus = dbs
    invitae_reports(engine, corpus)
    cs = gate_text.scan_company(engine, corpus, NVTA, "NVTA", NOW, mf=MF)
    assert cs.first and cs.docs_read == 2 and cs.rows_new == 2
    g = gate.evaluate(engine, NVTA, "NVTA", "2023-09-01", models=MF, calendar=False)
    assert not any("going-concern text" in t for t in g.triggers)
    assert g.text_summary == "no trigger in the current report" and "000060" in g.text_report
    g = gate.evaluate(engine, NVTA, "NVTA", "2023-11-10", models=MF, calendar=False)
    assert g.state == "fail"
    trig = next(t for t in g.triggers if t.startswith("going-concern text"))
    assert (
        'management: "substantial doubt exists"' in trig
        and "concluded that substantial doubt exists" in trig
    )
    assert any(s.ref == "0001501134-23-000079" for s in g.sources)
    # scanned once per classifier version: a second scan reads nothing
    again = gate_text.scan_company(engine, corpus, NVTA, "NVTA", NOW, mf=MF)
    assert not again.first and again.docs_read == 0 and again.docs_skipped == 2


def test_quotes_are_verified_and_a_changed_document_is_scanned_again(dbs):
    engine, corpus = dbs
    invitae_reports(engine, corpus)
    gate_text.scan_company(engine, corpus, NVTA, "NVTA", NOW, mf=MF)
    rows = gate_text.rows_for(engine, NVTA)
    assert gate_text.verify_rows(corpus, rows) == (2, 2)
    assert all(r["passage_id"] for r in rows)
    text = read("invitae_10q_q3_2023_excerpt.txt").replace(
        "Going Concern\n\n", "Going Concern\n\nPreface.\n\n"
    )
    corpus.execute(
        "UPDATE document SET text = ?, sha256 = 'changed' WHERE accession = '0001501134-23-000079'",
        (text,),
    )
    assert gate_text.verify_rows(corpus, gate_text.rows_for(engine, NVTA))[0] == 1
    cs = gate_text.scan_company(engine, corpus, NVTA, "NVTA", NOW, mf=MF)
    assert cs.docs_read == 1 and gate_text.verify_rows(
        corpus, gate_text.rows_for(engine, NVTA)
    ) == (2, 2)


def test_a_newer_report_without_stored_text_is_named_and_the_stored_one_read(dbs):
    engine, corpus = dbs
    invitae_reports(engine, corpus)
    filing(engine, NVTA, "0001501134-24-000010", "10-K", "2024-02-28", "2023-12-31")
    gate_text.scan_company(engine, corpus, NVTA, "NVTA", NOW, mf=MF)
    cur = gate_text.current(engine, NVTA, TODAY)
    assert cur.accessions == {"0001501134-23-000079"}
    assert "newer 10-K 0001501134-24-000010" in cur.note and "no stored text" in cur.note


def test_six_ks_after_the_annual_report_are_current(dbs):
    engine, corpus = dbs
    entity(engine, "0001709048", "GLOBALFOUNDRIES", "3674", ticker="GFS")
    report(
        engine,
        corpus,
        "0001709048",
        "0001709048-26-000005",
        "20-F",
        "2026-03-20",
        "2025-12-31",
        "boeing_10k_fy2023_excerpt.txt",
    )
    filing(engine, "0001709048", "0001709048-26-000040", "6-K", "2026-08-05", "2026-06-30")
    doc(
        corpus,
        "0001709048",
        "0001709048-26-000040",
        read("synthetic_cases_excerpt.txt"),
        "EX-99.1",
        "ex991.txt",
    )
    gate_text.scan_company(engine, corpus, "0001709048", "GFS", NOW, mf=MF)
    tg = gate_text.gate_lines(engine, "0001709048", TODAY)
    assert tg.current.accessions == {"0001709048-26-000005", "0001709048-26-000040"}
    assert any("IFRS" in w for w, _ in tg.warns) and any("accelerated" in f for f, _ in tg.fails)


# --- The pass: signals, items, baselines (D-M04-71, D-M04-97) -----------------------------------


def test_first_scan_baseline_queues_only_a_current_fail_and_writes_both_signals(dbs):
    engine, corpus = dbs
    invitae_reports(engine, corpus)  # filed 2023: older than 12 months
    tp = gate_text_step.text_pass(engine, corpus, {"NVTA": NVTA}, NOW, mf=MF)
    ct = tp.companies["NVTA"]
    assert ct.queued == {f"m04_gate_fail:{NVTA}:text:0001501134-23-000079": "queued"}
    p = engine.execute("SELECT priority, baseline, capped FROM m04_proposal").fetchone()
    assert tuple(p) == (1, 1, 0)  # baseline exception: a current fail, priority 1, uncapped
    assert tp.alerts and "fail-class text" in tp.alerts[0]
    sig = {r["signal"]: r for r in engine.execute("SELECT * FROM signal WHERE timeframe = 'ST'")}
    assert (
        sig["gc_language"]["value_text"] == "management_exists"
        and sig["gc_language"]["value"] is None
    )
    assert (
        "“Based on its evaluation" in sig["gc_language"]["method"]
        and sig["gc_language"]["source_ref"] == "0001501134-23-000079"
    )
    assert sig["covenant_status"]["value_text"] == "silent"
    assert {r[0] for r in engine.execute("SELECT DISTINCT timeframe FROM signal")} == {
        "MY",
        "PT",
        "ST",
    }
    item = engine.execute(
        "SELECT item_id FROM review_queue WHERE kind = 'm04_gate_fail'"
    ).fetchone()[0]
    assert (
        engine.execute(
            "SELECT item_id FROM gate_text WHERE class = 'management_exists'"
        ).fetchone()[0]
        == item
    )


def test_part_4a_pass_keeps_the_text_alert_and_the_gate_fails_on_the_text(dbs):
    engine, corpus = dbs
    invitae_reports(engine, corpus)
    gate_text_step.text_pass(engine, corpus, {"NVTA": NVTA}, NOW, mf=MF)
    gp = gate_step.gate_pass(engine, {"NVTA": NVTA}, NOW, mf=MF)
    g = gp.companies["NVTA"].gate
    assert g.state == "fail" and any(t.startswith("going-concern text") for t in g.triggers)
    open_text = engine.execute(
        "SELECT count(*) FROM review_queue q JOIN m04_proposal p ON p.item_id = q.item_id WHERE "
        "p.prop_key LIKE 'm04_gate_fail:%:text:%' AND q.resolved_at IS NULL"
    ).fetchone()[0]
    assert open_text == 1 and gp.companies["NVTA"].withdrawn == 0


def test_fisker_fail_classes_open_one_alert_per_report(dbs):
    engine, corpus = dbs
    entity(engine, FSR, "Fisker Inc.", "3711", ticker="FSR")
    report(
        engine,
        corpus,
        FSR,
        "0001720990-24-000045",
        "10-K",
        "2024-04-23",
        "2023-12-31",
        "fisker_10k_fy2023_excerpt.txt",
    )
    tp = gate_text_step.text_pass(engine, corpus, {"FSR": FSR}, NOW, mf=MF)
    ct = tp.companies["FSR"]
    assert list(ct.queued) == [f"m04_gate_fail:{FSR}:text:0001720990-24-000045"]
    payload = engine.execute("SELECT payload FROM review_queue").fetchone()[0]
    assert (
        '"auditor_gc"' in payload
        and '"forbearance"' in payload
        and '"management_exists"' in payload
    )
    # the most severe class, the first in the report on a tie (the risk-factor summary)
    assert ct.signals == {"gc_language": "management_exists", "covenant_status": "forbearance"}


def test_proterra_unwaived_breach_and_reclassification_fail(dbs):
    engine, corpus = dbs
    entity(engine, PTRA, "Proterra Inc", "3711", ticker="PTRA")
    report(
        engine,
        corpus,
        PTRA,
        "0001628280-23-008519",
        "10-K",
        "2023-03-17",
        "2022-12-31",
        "proterra_10k_fy2022_excerpt.txt",
    )
    gate_text.scan_company(engine, corpus, PTRA, "PTRA", NOW, mf=MF)
    g = gate.evaluate(engine, PTRA, "PTRA", "2023-03-20", models=MF, calendar=False)
    joined = " | ".join(g.triggers)
    assert g.state == "fail" and "not waived" in joined and "classified as current" in joined


def test_microvast_alleviated_warns_and_opens_a_gc_text_review(dbs):
    engine, corpus = dbs
    entity(engine, MVST, "Microvast Holdings", "3690", ticker="MVST")
    report(
        engine,
        corpus,
        MVST,
        "0001628280-26-018264",
        "10-K",
        "2026-03-16",
        "2025-12-31",
        "microvast_10k_fy2025_excerpt.txt",
    )
    tp = gate_text_step.text_pass(engine, corpus, {"MVST": MVST}, NOW, mf=MF)
    ct = tp.companies["MVST"]
    assert (
        ct.queued
        == {
            f"m04_gc_text:{MVST}:0001628280-26-018264:alleviated": "queued",  # filed in the last 12 months
            f"m04_gc_text:{MVST}:0001628280-26-018264:auditor_cam": "queued",
        }
    )
    g = gate.evaluate(engine, MVST, "MVST", TODAY, models=MF)
    assert not any(t.startswith("going-concern") for t in g.triggers)
    assert any("substantial doubt alleviated" in w for w in g.warnings)
    assert queue.GROUP["m04_gc_text"] == 1 and "m04_gc_text" not in queue.UNCAPPED


def test_riot_hypothetical_is_reviewed_only_below_8_quarters():
    assert gate_text.runway_reviews(5.0, "cash_burner", "full") == (True, "runway 5.0 q")
    assert gate_text.runway_reviews(9.4, "cash_burner", "full")[0] is False
    assert gate_text.runway_reviews(None, "self_funding", "full") == (False, "self-funding")
    assert gate_text.runway_reviews(None, None, "full") == (True, "runway unknown")
    assert gate_text.runway_reviews(None, None, "trust_only")[0] is False


def test_hypothetical_with_a_short_runway_queues_and_is_withdrawn_when_it_recovers(dbs):
    engine, corpus = dbs
    rivian(engine)  # Rivian Q2 2026 runway 5.5 cash-only
    report(
        engine,
        corpus,
        RIVN,
        "0001874178-26-000050",
        "10-Q",
        "2026-08-05",
        "2026-06-30",
        "riot_10k_fy2025_excerpt.txt",
    )
    tp = gate_text_step.text_pass(engine, corpus, {"RIVN": RIVN}, NOW, mf=MF)
    ct = tp.companies["RIVN"]
    assert ct.review_hypo and ct.runway_why.startswith("runway 5.")
    assert ct.queued == {f"m04_gc_text:{RIVN}:0001874178-26-000050:hypothetical": "queued"}
    assert ct.signals["gc_language"] == "hypothetical"
    # a confirmed 20,000M line lifts the runway above 8 quarters: the review is withdrawn
    gate_view.add_credit_line(
        engine, RIVN, "ABL", "20000", "2030-06-30", "2026-06-30", "note", "owner", NOW
    )
    tp = gate_text_step.text_pass(engine, corpus, {"RIVN": RIVN}, NOW, mf=MF)
    assert not tp.companies["RIVN"].review_hypo and tp.companies["RIVN"].withdrawn == 1
    row = engine.execute(
        "SELECT resolution FROM review_queue WHERE kind = 'm04_gc_text'"
    ).fetchone()
    assert row[0] == "withdrawn"


def test_uti_waiver_and_albemarle_reset_open_covenant_reviews_boeing_compliant_nothing(dbs):
    engine, corpus = dbs
    entity(engine, UTI, "Universal Technical Institute", "8200", ticker="UTI")
    report(
        engine,
        corpus,
        UTI,
        "0001261654-25-000019",
        "10-Q",
        "2025-08-07",
        "2025-06-30",
        "uti_10q_q3_fy2025_excerpt.txt",
    )
    entity(engine, ALB, "ALBEMARLE CORP", "2821", ticker="ALB")
    report(
        engine,
        corpus,
        ALB,
        "0000915913-24-000158",
        "10-Q",
        "2024-11-06",
        "2024-09-30",
        "boeing_10k_fy2023_excerpt.txt",
    )
    doc(
        corpus,
        ALB,
        "0000915913-24-000158",
        read("albemarle_ex10_1_q3_2024_excerpt.txt"),
        "EX-10.1",
        "ex101.txt",
    )
    entity(engine, BA, "BOEING CO", "3721", ticker="BA")
    report(
        engine,
        corpus,
        BA,
        "0000012927-24-000010",
        "10-K",
        "2024-01-31",
        "2023-12-31",
        "boeing_10k_fy2023_excerpt.txt",
    )
    now = datetime(2025, 9, 1, tzinfo=UTC)  # UTI's 10-Q and Albemarle's 10-Q within 12 months
    tp = gate_text_step.text_pass(engine, corpus, {"UTI": UTI, "ALB": ALB, "BA": BA}, now, mf=MF)
    assert tp.companies["UTI"].queued == {
        f"m04_covenant:{UTI}:0001261654-25-000019:breach_waived": "queued"
    }
    assert tp.companies["ALB"].queued == {
        f"m04_covenant:{ALB}:0000915913-24-000158:reset": "queued"
    }
    assert (
        tp.companies["BA"].queued == {}
        and tp.companies["BA"].signals["covenant_status"] == "compliant"
    )
    assert tp.companies["UTI"].signals["covenant_status"] == "breach_waived"
    ex = engine.execute(
        "SELECT exhibit, doc_type, note FROM gate_text WHERE cik = ? AND class = 'reset' LIMIT 1",
        (ALB,),
    ).fetchone()
    assert tuple(ex) == (1, "EX-10.1", "exhibit")
    g = gate.evaluate(engine, BA, "BA", "2024-02-15", models=MF, calendar=False)
    assert not any("text" in t for t in g.triggers + g.warnings)


def test_infq_shell_year_alleviated_is_excluded_keyed_on_period_end(dbs):
    engine, corpus = dbs
    entity(engine, INFQ, "Infleqtion, Inc.", "3829", ticker="INFQ")
    report(
        engine,
        corpus,
        INFQ,
        "0001193125-26-134544",
        "10-K",
        "2026-03-31",
        "2025-12-31",
        "infq_10k_fy2025_excerpt.txt",
    )
    tp = gate_text_step.text_pass(engine, corpus, {"INFQ": INFQ}, NOW, mf=MF)
    r = engine.execute("SELECT class, effect, note FROM gate_text").fetchone()
    assert (r["class"], r["effect"]) == ("alleviated", "excluded") and "spac_shell period" in r[
        "note"
    ]
    assert (
        tp.companies["INFQ"].queued == {}
        and tp.companies["INFQ"].signals["gc_language"] == "excluded"
    )
    g = gate.evaluate(engine, INFQ, "INFQ", TODAY, models=MF)
    assert not any("text" in w for w in g.warnings + g.triggers)


def test_untagged_spac_falls_back_to_the_2_01_close(dbs):
    engine, corpus = dbs
    entity(engine, SPAC, "Some Holdings (formerly a SPAC)", "6770", ticker="SPCQ")
    engine.execute(
        "INSERT INTO event (accession, item, cik, form, filed, report_date, category, severity, title, modules, amended, catalog) "
        "VALUES ('0000077777-26-000002', '2.01', ?, '8-K', '2026-02-17', '2026-02-13', 'agreement', 'low', 't', '[]', 0, 'c')",
        (SPAC,),
    )
    report(
        engine,
        corpus,
        SPAC,
        "0000077777-26-000009",
        "10-K",
        "2026-03-31",
        "2025-12-31",
        "infq_10k_fy2025_excerpt.txt",
    )
    gate_text.scan_company(engine, corpus, SPAC, "SPCQ", NOW, mf=MF)
    r = engine.execute("SELECT effect, note FROM gate_text").fetchone()
    assert (
        r["effect"] == "excluded"
        and "before the close 2026-02-13" in r["note"]
        and "8-K 2.01" in r["note"]
    )


def test_history_rows_never_act_on_the_gate(dbs):
    engine, corpus = dbs
    invitae_reports(engine, corpus)
    report(
        engine,
        corpus,
        NVTA,
        "0001501134-24-000020",
        "10-Q",
        "2024-05-08",
        "2024-03-31",
        "boeing_10k_fy2023_excerpt.txt",
    )
    gate_text.scan_company(engine, corpus, NVTA, "NVTA", NOW, mf=MF)
    tg = gate_text.gate_lines(engine, NVTA, TODAY)
    assert not tg.fails and tg.current.accessions == {"0001501134-24-000020"}
    rows, more, _ = gate_text.view_rows(engine, NVTA, TODAY, False)
    assert rows[0].effect == "no trigger" and any(r.effect == "history (fail class)" for r in rows)


def test_tracked_names_get_rows_and_signals_but_no_items(dbs):
    engine, corpus = dbs
    invitae_reports(engine, corpus)
    engine.execute(
        "INSERT INTO tier_member (cik, ticker, tier, status, reason, added_at, added_by, changed_at, changed_by, last_evidence_at) "
        "VALUES (?, 'NVTA', 'tracked', 'active', 'r', 'n', 'owner', 'n', 'owner', 'n')",
        (NVTA,),
    )
    tp = gate_text_step.text_pass(engine, corpus, {"NVTA": NVTA}, NOW, mf=MF)
    assert tp.companies["NVTA"].queued == {} and tp.companies["NVTA"].held
    assert engine.execute("SELECT count(*) FROM review_queue").fetchone()[0] == 0


def test_no_stored_text_is_missing_never_none(dbs):
    engine, corpus = dbs
    entity(engine, "0000000005", "No Text Co", "3711", ticker="NOTX")
    filing(engine, "0000000005", "0000000005-26-000001", "10-Q", "2026-08-01", "2026-06-30")
    tp = gate_text_step.text_pass(engine, corpus, {"NOTX": "0000000005"}, NOW, mf=MF)
    for r in engine.execute(
        "SELECT value, value_text, method FROM signal WHERE cik = '0000000005'"
    ):
        assert (
            r["value"] is None
            and r["value_text"] is None
            and r["method"].startswith("missing: no stored periodic text")
        )
    assert tp.companies["NOTX"].scan.no_text == ["10-Q 0000000005-26-000001 filed 2026-08-01"]


# --- Owner answers (D-M04-98) ---------------------------------------------------------------


def test_owner_misread_removes_the_effect_and_treat_as_fail_makes_a_trigger(dbs):
    from engine import review

    engine, corpus = dbs
    entity(engine, MVST, "Microvast Holdings", "3690", ticker="MVST")
    report(
        engine,
        corpus,
        MVST,
        "0001628280-26-018264",
        "10-K",
        "2026-03-16",
        "2025-12-31",
        "microvast_10k_fy2025_excerpt.txt",
    )
    gate_text_step.text_pass(engine, corpus, {"MVST": MVST}, NOW, mf=MF)
    items = dict(engine.execute(
        "SELECT p.prop_key, p.item_id FROM m04_proposal p WHERE kind = 'm04_gc_text'").fetchall())  # fmt: skip
    cam = items[f"m04_gc_text:{MVST}:0001628280-26-018264:auditor_cam"]
    allev = items[f"m04_gc_text:{MVST}:0001628280-26-018264:alleviated"]
    with pytest.raises(review.ReviewError):
        review.m04_action(engine, cam, "misread", "", "owner", NOW)  # a note is required
    review.m04_action(engine, cam, "misread", "the CAM restates the note", "owner", NOW)
    review.m04_action(
        engine, allev, "treat_as_fail", "plan rests on an unclosed raise", "owner", NOW
    )
    g = gate.evaluate(engine, MVST, "MVST", TODAY, models=MF)
    assert g.state == "fail" and any("substantial doubt alleviated" in t for t in g.triggers)
    assert not any("critical audit matter" in w for w in g.warnings)
    again = gate_text_step.text_pass(engine, corpus, {"MVST": MVST}, NOW, mf=MF)
    assert again.companies["MVST"].withdrawn == 0  # answered items are kept, no new alert
    assert (
        engine.execute("SELECT count(*) FROM review_queue WHERE kind = 'm04_gate_fail'").fetchone()[
            0
        ]
        == 0
    )


def test_text_alert_inputs_wrong_marks_the_sentence_misread(dbs):
    from engine import review

    engine, corpus = dbs
    invitae_reports(engine, corpus)
    gate_text_step.text_pass(engine, corpus, {"NVTA": NVTA}, NOW, mf=MF)
    item = engine.execute(
        "SELECT item_id FROM review_queue WHERE kind = 'm04_gate_fail'"
    ).fetchone()[0]
    done = review.m04_action(engine, item, "inputs_wrong", "not this company's note", "owner", NOW)
    assert done.startswith("misread")
    g = gate.evaluate(engine, NVTA, "NVTA", TODAY, models=MF, calendar=False)
    assert not any(t.startswith("going-concern text") for t in g.triggers)


# --- The script, the refresh hook and the UI ------------------------------------------------------


def run_financials_module():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_financials

    return run_financials


def test_gate_text_run_logs_classes_quotes_and_gate_changes(dbs):
    rf = run_financials_module()
    engine, corpus = dbs
    invitae_reports(engine, corpus)
    out: list[str] = []
    rf.gate_text_run(engine, corpus, {"NVTA": NVTA}, NOW, lambda *a: out.extend(a), mf=MF)
    text = "\n".join(out)
    for want in ("=== Summary gate-text (Part 4b-lite)", "Quotes verified against the stored documents: 2 of 2",
                 "NVTA: documents scanned 2 new, 0 already scanned (first scan: baseline)",
                 "[current] management_exists", "m04_gate_fail queued 1",
                 "hits per class: boilerplate 1 (current 0), management_exists 1 (current 1)",
                 "Gate changes after the text pass: NVTA: not computed → fail", "Baseline rows (first scan): 2",
                 "gc_language / covenant_status: NVTA management_exists / silent"):  # fmt: skip
        assert want in text, want
    assert "gate-text" in rf.BUILT


def test_refresh_hook_runs_before_the_gate_and_never_fails(dbs):
    engine, corpus = dbs
    invitae_reports(engine, corpus)
    lines = gate_text_step.run_local_part(engine, corpus, {"NVTA": NVTA}, NOW)
    assert lines[0].startswith("M04 gate text — local pass (Part 4b-lite, 0 SEC requests)")
    assert "current-report fail 1 (NVTA)" in lines[1]
    assert "no corpus connection" in gate_text_step.run_local_part(engine, None, {}, NOW)[1]
    src = (Path(__file__).resolve().parent.parent / "scripts" / "run_refresh.py").read_text(
        encoding="utf-8"
    )
    assert src.index("financials_gate_text_local_step(engine, corpus, report)") < src.index(
        "prices += financials_gate_local_step(engine, report)")  # fmt: skip


def test_financials_tab_shows_the_gate_text_block_and_the_review_pages(tmp_path):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui.app import create_app
    from engine.ui.settings import UiSettings

    data = tmp_path / "data"
    engine = open_db("engine", data)
    corpus = open_db("corpus", data)
    rivian(engine)
    report(
        engine,
        corpus,
        RIVN,
        "0001874178-26-000050",
        "10-Q",
        "2026-08-05",
        "2026-06-30",
        "riot_10k_fy2025_excerpt.txt",
    )
    gate_text_step.text_pass(engine, corpus, {"RIVN": RIVN}, NOW, mf=MF)
    item = engine.execute("SELECT item_id FROM review_queue WHERE kind = 'm04_gc_text'").fetchone()[
        0
    ]
    engine.close()
    corpus.close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text('[watchlist]\ntickers = ["RIVN"]\n', encoding="utf-8")
    with TestClient(create_app(UiSettings(data_dir=data, watchlist=watch))) as c:
        html = c.get("/c/RIVN?tab=financials").text
        one = c.get(f"/review/{item}").text
        guide = c.get("/review").text
    for want in ("Gate text — RIVN", "<td>hypothetical (", "review (m04_gc_text)",
                 "Going-concern and covenant text (Part 4b)", "Albemarle relief period", "62–144 days",
                 "could raise substantial doubt about our ability"):  # fmt: skip
        assert want in html, want
    assert "object at 0x" not in html
    for want in (
        "Deciding sentence",
        "Treat as fail",
        "Misread (note)",
        "current report",
        "Gate text block",
    ):
        assert want in one, want
    assert "M04 survival gate text (Part 4b)" in guide and "Covenant waived or reset" in guide
