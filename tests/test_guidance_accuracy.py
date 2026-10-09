# ruff: noqa: E501  (fixture text)
"""M02 part 4b: guidance accuracy loop (D-M02-24) — labels, weekly audit, plausibility,
owner-triggered Gemini cross-check. Synthetic transcript from test_calls."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from engine import review
from engine.calls.step import run_calls_step
from engine.guidance import labels
from engine.guidance.calls import scan_calls
from engine.llm import call_check
from engine.llm.provider import FakeProvider, load_settings
from engine.llm.runs import run as llm_run
from engine.store.db import open_db
from engine.ui.app import create_app
from engine.ui.settings import UiSettings
from tests.test_calls import CFO, CIK, TRANSCRIPT, AvTransport, _client, _setup


def _items(engine, kind):
    return [
        dict(r) | {"payload": json.loads(r["payload"])}
        for r in engine.execute(
            "SELECT * FROM review_queue WHERE kind = ? AND resolved_at IS NULL ORDER BY item_id",
            (kind,),
        )
    ]


@pytest.fixture
def loaded(dbs, clock):
    engine, corpus = dbs
    _setup(engine, corpus, clock)
    lines = run_calls_step(engine, corpus, _client(engine, clock, AvTransport({"2026Q4": TRANSCRIPT})),
                           {"XCLD": CIK}, clock.now())  # fmt: skip
    return engine, corpus, lines


def _cy_row(engine):
    return engine.execute(
        "SELECT * FROM guidance WHERE period = 'CY2026' AND metric = 'capex'"
    ).fetchone()


def test_wrong_button_removes_row_and_keeps_it_out_of_rescans(loaded, clock):
    engine, corpus, _ = loaded
    row = _cy_row(engine)
    review.mark_wrong(engine, row["guidance_id"], "wrong_period", "fiscal, not calendar",
                      "owner", clock.now())  # fmt: skip
    assert _cy_row(engine) is None
    scan_calls(engine, corpus, clock.now(), force=True)
    assert _cy_row(engine) is None  # the label wins over the parser
    lb = engine.execute("SELECT * FROM guidance_label").fetchone()
    assert (lb["verdict"], lb["reason"], lb["found_by"], lb["origin"]) == (
        "wrong", "wrong_period", "owner", "call")  # fmt: skip
    head = labels.check_labels(engine, corpus)[0]
    assert "still wrong 1" in head  # the parser itself is not fixed yet
    with pytest.raises(review.ReviewError, match="Choose why"):
        review.mark_wrong(engine, engine.execute("SELECT guidance_id FROM guidance").fetchone()[0],
                          "", "", "owner", clock.now())  # fmt: skip


def test_skipped_sentences_are_stored_for_the_audit(loaded):
    engine, *_ = loaded
    reasons = [r[0] for r in engine.execute("SELECT reason FROM guidance_skip")]
    assert any(r.startswith("not capex") for r in reasons)  # the gross-margin sentence


def test_weekly_audit_once_per_week_and_answers_become_labels(loaded, clock):
    engine, corpus, lines = loaded
    assert any("weekly sample item(s) queued" in ln for ln in lines)
    items = _items(engine, "guidance_audit")
    rows = [i for i in items if i["payload"]["sample"] == "row"]
    skipped = [i for i in items if i["payload"]["sample"] == "skipped"]
    assert len(rows) == 4 and len(skipped) == 1  # 3 call rows + 1 release row; 1 skip exists
    assert labels.queue_audit(engine, corpus, clock.now()) == 0  # once per week
    assert skipped[0]["payload"]["text"] in CFO
    scan_calls(engine, corpus, clock.now(), force=True)  # ids change; checks still resolve
    first, second = rows[0], rows[1]
    review.label_action(engine, first["item_id"], "correct", "", "", "owner", clock.now())
    review.label_action(engine, second["item_id"], "wrong", "segment", "", "owner", clock.now())
    review.label_action(engine, skipped[0]["item_id"], "no_guidance", "", "", "owner", clock.now())
    with pytest.raises(review.ReviewError, match="does not apply"):
        review.label_action(engine, rows[2]["item_id"], "missed", "", "", "owner", clock.now())
    [acc] = labels.accuracy(engine)
    assert (acc.rows_checked, acc.rows_wrong, acc.skipped_checked, acc.precision) == (2, 1, 1, 0.5)
    next_week = clock.now() + timedelta(days=7)
    assert labels.queue_audit(engine, corpus, next_week) >= 1  # unlabelled rows remain


def test_plausibility_flags_capex_far_from_last_year(loaded, clock):
    engine, *_ = loaded
    assert _items(engine, "guidance_implausible") == []  # no XBRL actual: unknown, not flagged
    engine.execute(
        "INSERT INTO series (cik, concept, period_end, period_type, period_start, unit, "
        "first_value, first_accession, first_filed, latest_value, latest_accession, latest_filed, "
        "method, parser_version) VALUES (?, 'capex', '2026-06-30', 'FY', '2025-07-01', 'USD', "
        "80e9, 'a', '2026-07-30', 80e9, 'a', '2026-07-30', 'direct', 't')",
        (CIK,),
    )
    assert labels.check_plausibility(engine, clock.now()) == 0  # $40B/quarter vs $20B: 2.0x ok
    engine.execute("UPDATE series SET latest_value = 20e9")
    # release Q1 $40B, call Q1 $40B and call CY $175B, against $20B a year
    assert labels.check_plausibility(engine, clock.now()) == 3
    first = _items(engine, "guidance_implausible")[0]
    assert "8.00× a quarter of last fiscal year's" in first["reason"]
    assert labels.check_plausibility(engine, clock.now()) == 0  # once per sentence


GEMINI_REPLY = json.dumps({"statements": [
    {"turn_id": "T2", "quote": "We expect capital expenditures to be roughly $40 billion in the first quarter.",
     "metric": "capex", "period": "Q1", "value": "roughly $40 billion"},
    {"turn_id": "T2", "quote": "We expect gross margin to be impacted by $2 billion of depreciation.",
     "metric": "gross margin", "period": "next year", "value": "$2 billion impact"},
    {"turn_id": "T2", "quote": "We expect operating margin of 50% next quarter.",
     "metric": "operating margin", "period": "next quarter", "value": "50%"},
]})  # fmt: skip


def test_gemini_cross_check_queues_only_what_the_code_missed(loaded, clock):
    engine, corpus, _ = loaded
    engine.execute("DELETE FROM review_queue WHERE kind = 'guidance_audit'")  # before the audit
    prep = call_check.prepare(engine, corpus, "AV-XCLD-2026Q4", "transcript.txt")
    assert [t.title for t in prep.turns] == [
        "Jane Doe — Vice President, Investor Relations",
        "Amy Example — Executive Vice President and Chief Financial Officer",
    ]
    assert "Do you expect" not in prep.request.user  # analysts are never sent
    res = llm_run(engine, FakeProvider([GEMINI_REPLY]), load_settings(), prep.request, clock.now())
    status = [o.subject.get("status") for o in res.observations]
    assert status == ["matched", "code_missed", None]  # third quote is invented → rejected
    text = corpus.execute(
        "SELECT text FROM document WHERE accession = ?", (prep.accession,)
    ).fetchone()[0]
    assert call_check.queue_missed(engine, prep, res, text, clock.now()) == 1
    assert call_check.queue_missed(engine, prep, res, text, clock.now()) == 0  # idempotent
    [item] = [i for i in _items(engine, "guidance_audit") if i["payload"]["found_by"] == "gemini"]
    assert "gross margin" in item["reason"]
    assert _items(engine, "llm_rejected")
    review.label_action(engine, item["item_id"], "missed", "", "note", "owner", clock.now())
    lb = engine.execute("SELECT * FROM guidance_label WHERE found_by = 'gemini'").fetchone()
    assert (lb["verdict"], lb["reason"]) == ("missed", "missed_guidance")


@pytest.fixture
def app_client(tmp_path, clock):
    data = tmp_path / "data"
    engine = open_db("engine", data)
    corpus = open_db("corpus", data)
    _setup(engine, corpus, clock)
    run_calls_step(engine, corpus, _client(engine, clock, AvTransport({"2026Q4": TRANSCRIPT})),
                   {"XCLD": CIK}, clock.now())  # fmt: skip
    # keep the weekly sample's row items; drop its skipped-sentence item so Gemini can raise it
    engine.execute("DELETE FROM review_queue WHERE kind = 'guidance_audit' "
                   "AND json_extract(payload, '$.sample') = 'skipped'")  # fmt: skip
    engine.close()
    corpus.close()
    watch = tmp_path / "watch.toml"
    watch.write_text('[watchlist]\ntickers = ["XCLD"]\n', encoding="utf-8")
    fake = FakeProvider([GEMINI_REPLY])
    app = create_app(UiSettings(data_dir=data, watchlist=watch, llm_factory=lambda: fake))
    with TestClient(app) as c:
        yield c, data


def test_ui_wrong_button_check_page_and_accuracy(app_client):
    client, data = app_client
    html = client.get("/c/XCLD?tab=guidance").text
    assert "check / wrong?</a>" in html and "/calls/check?acc=AV-XCLD-2026Q4" in html
    engine = open_db("engine", data)
    gid = engine.execute("SELECT guidance_id FROM guidance WHERE period = 'CY2026'").fetchone()[0]
    engine.close()
    form = client.get(f"/c/XCLD/guidance/{gid}/wrong").text
    assert "Your verdict" in form and "including finance leases" in form
    r = client.post(f"/c/XCLD/guidance/{gid}/wrong", data={"reason": "wrong_period"},
                    follow_redirects=False)  # fmt: skip
    assert "msg=labelled-wrong" in r.headers["location"]
    page = client.get("/c/XCLD/calls/check?acc=AV-XCLD-2026Q4&file=transcript.txt").text
    assert "Run with Gemini" in page and "2 management turns" in page
    r = client.post("/c/XCLD/calls/check?acc=AV-XCLD-2026Q4&file=transcript.txt",
                    follow_redirects=False)  # fmt: skip
    assert "1%20sentence" in r.headers["location"]
    review_page = client.get("/review").text
    assert "Gemini read guidance the code did not store" in review_page
    runs = client.get("/runs").text
    assert "Guidance accuracy" in runs and "guidance-6" in runs
    audit = [i for i in client.get("/review").text.split('href="/review/') if "Weekly check" in i]
    item_id = audit[0].split('"')[0]
    item = client.get(f"/review/{item_id}").text
    assert "weekly random sample" in item and "— why wrong —" in item


# --- Corrections and undo (owner request 2026-10-09) ---------------------------------


def test_wrong_with_correction_then_undo_restores_the_parser_row(loaded, clock):
    engine, corpus, _ = loaded
    row = _cy_row(engine)
    fix = review.ManualGuidance("capex", "unspecified", "CY2026", "USD", "170", "", "1000000000")
    warnings = review.mark_wrong(engine, row["guidance_id"], "wrong_value", "", "owner",
                                 clock.now(), corpus=corpus, correction=fix)  # fmt: skip
    assert warnings == [
        "170000000000 does not appear in the sentence (in raw, millions or billions form)"
    ]
    owner = _cy_row(engine)
    assert (owner["source"], owner["low"], owner["quote"]) == ("owner", 170e9, row["quote"])
    scan_calls(engine, corpus, clock.now(), force=True)
    assert _cy_row(engine)["source"] == "owner"  # the correction wins over the parser
    lb = engine.execute("SELECT * FROM guidance_label").fetchone()
    assert lb["correction_id"] == owner["guidance_id"]
    done = review.undo_label(engine, corpus, lb["label_id"], "owner", clock.now())
    assert done == "label removed; correction removed; the parser's row restored"
    back = _cy_row(engine)
    assert (back["source"], back["low"]) == ("sentence", 175e9)
    assert engine.execute("SELECT count(*) FROM guidance_label").fetchone()[0] == 0


def test_answered_check_can_be_reopened_and_missed_takes_a_correction(loaded, clock):
    engine, corpus, _ = loaded
    [skipped] = [i for i in _items(engine, "guidance_audit") if i["payload"]["sample"] == "skipped"]
    fix = review.ManualGuidance("gross_margin", "unspecified", "FY2027", "%", "68", "", "1")
    review.label_action(engine, skipped["item_id"], "missed", "", "", "owner", clock.now(),
                        corpus=corpus, correction=fix)  # fmt: skip
    assert engine.execute("SELECT 1 FROM guidance WHERE metric = 'gross_margin' "
                          "AND source = 'owner'").fetchone()  # fmt: skip
    with pytest.raises(review.ReviewError, match="'wrong' or 'missed'"):
        [row] = [i for i in _items(engine, "guidance_audit") if i["payload"]["sample"] == "row"][:1]
        review.label_action(engine, row["item_id"], "correct", "", "", "owner", clock.now(),
                            corpus=corpus, correction=fix)  # fmt: skip
    done = review.reopen(engine, skipped["item_id"], "owner", clock.now(), corpus)
    assert "correction removed" in done and f"item {skipped['item_id']} reopened" in done
    assert any(i["item_id"] == skipped["item_id"] for i in _items(engine, "guidance_audit"))
    assert not engine.execute("SELECT 1 FROM guidance WHERE source = 'owner'").fetchone()


def test_ui_correction_and_undo(app_client):
    client, data = app_client
    engine = open_db("engine", data)
    gid = engine.execute("SELECT guidance_id FROM guidance WHERE period = 'CY2026'").fetchone()[0]
    engine.close()
    assert "fix_low" in client.get(f"/c/XCLD/guidance/{gid}/wrong").text
    r = client.post(f"/c/XCLD/guidance/{gid}/wrong", follow_redirects=False, data={
        "reason": "wrong_value", "fix_metric": "capex", "fix_period": "CY2026",
        "fix_unit": "USD", "fix_low": "175", "fix_scale": "1000000000"})  # fmt: skip
    assert "msg=labelled-wrong" in r.headers["location"]
    html = client.get("/c/XCLD?tab=guidance").text
    assert "Your corrections and checks" in html and "→ capex CY2026: $175 billion" in html
    label_id = html.split('action="/labels/')[1].split("/")[0]
    r = client.post(
        f"/labels/{label_id}/undo?back=/c/XCLD%3Ftab%3Dguidance", follow_redirects=False
    )
    assert r.headers["location"].startswith("/c/XCLD?tab=guidance&msg=undone")
    assert "Your corrections and checks" not in client.get("/c/XCLD?tab=guidance").text


def test_no_error_verdict_keeps_the_row_and_wording_is_shown(app_client):
    client, data = app_client
    html = client.get("/c/XCLD?tab=guidance").text
    assert "approximately $175 billion" in html  # spoken "approximately" is shown, not dropped
    engine = open_db("engine", data)
    gid = engine.execute("SELECT guidance_id FROM guidance WHERE period = 'CY2026'").fetchone()[0]
    engine.close()
    form = client.get(f"/c/XCLD/guidance/{gid}/wrong").text
    assert "No error — keep the row as is" in form and "Ask three questions" in form
    r = client.post(f"/c/XCLD/guidance/{gid}/wrong", follow_redirects=False,
                    data={"reason": "no_error", "fix_low": "999"})  # fmt: skip
    assert r.headers["location"].endswith("msg=labelled-right")
    engine = open_db("engine", data)
    assert engine.execute("SELECT 1 FROM guidance WHERE guidance_id = ?", (gid,)).fetchone()
    lb = engine.execute("SELECT verdict, correction_id FROM guidance_label").fetchone()
    assert tuple(lb) == ("right", None)  # the correction is ignored with "No error"
    assert not engine.execute("SELECT 1 FROM guidance WHERE source = 'owner'").fetchone()
    engine.close()
