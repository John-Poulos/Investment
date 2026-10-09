# ruff: noqa: E501  (fixture text)
"""M02 part 4: call transcripts, call guidance, IR downloads (D-M02-6, -20, -21).

Transcripts here are synthetic, in Alpha Vantage's reply shape (vendor transcripts
stay off GitHub).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from engine.calls import ir_inbox
from engine.calls.alpha_vantage import URL, AlphaVantageClient, parse_reply
from engine.calls.step import run_calls_step
from engine.calls.transcripts import (
    fetch_due,
    fiscal_quarter,
    import_files,
    plan,
    queue_reminders,
    role_of,
)
from engine.guidance.calls import scan_calls
from engine.guidance.changes import changes_for
from engine.guidance.ledger import scan_all
from engine.guidance.parse import find_periods, find_values, parse_call
from engine.llm import guidance_reasons
from engine.search.query import search
from engine.sec.sections import resplit
from engine.store.db import open_db
from engine.ui.app import create_app
from engine.ui.settings import UiSettings

CIK = "0000000077"
KEY = "SECRETKEY123"
RELEASE = "0000000077-26-000050"
RELEASE_TEXT = (
    "Example Cloud reports fourth quarter results\n"
    "Business Outlook\n"
    "For the first quarter of fiscal 2027, we expect revenue of $80.0 billion to $81.0 billion.\n"
    "We expect capital expenditures of $40 billion in the first quarter of fiscal 2027.\n"
)
CFO = (
    "Thank you. We expect capital expenditures to be roughly $40 billion in the first quarter. "
    "We expect FY27 capex to grow. "
    "In calendar year 2026, we expect total capital expenditures of approximately $175 billion, including finance leases, to support demand. "
    "We expect revenue of $85 billion in the first quarter. "
    "We expect the capex growth rate in FY27 to be lower than FY26. "
    "We expect gross margin to be impacted by $2 billion of depreciation."
)
TRANSCRIPT = {
    "symbol": "XCLD",
    "quarter": "2026Q4",
    "transcript": [
        {
            "speaker": "Operator",
            "title": "",
            "content": "Welcome. We expect the call to last one hour and cover $1 billion of topics.",
            "sentiment": "0.1",
        },
        {
            "speaker": "Jane Doe",
            "title": "Vice President, Investor Relations",
            "content": "Thank you. Our remarks contain forward-looking statements.",
            "sentiment": "0.2",
        },
        {
            "speaker": "Amy Example",
            "title": "Executive Vice President and Chief Financial Officer",
            "content": CFO,
            "sentiment": "0.6",
        },
        {
            "speaker": "Keith Analyst",
            "title": "Analyst, Morgan Stanley",
            "content": "Do you expect capital expenditures of $200 billion next year?",
            "sentiment": "0.3",
        },
    ],
}


def tiny_pdf(text: str) -> bytes:
    """A minimal one-page PDF with one line of Helvetica text (readable by pypdf)."""
    content = f"BT /F1 10 Tf 20 700 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 3000 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


class AvTransport:
    """Serves replies per quarter; records params (to check the key stays out of logs)."""

    def __init__(self, replies: dict[str, object], status: int = 200) -> None:
        self.replies = replies
        self.status = status
        self.calls: list[dict] = []

    def __call__(self, url, params, headers):
        assert url == URL
        self.calls.append(dict(params))
        body = self.replies.get(
            params["quarter"],
            {"symbol": params["symbol"], "quarter": params["quarter"], "transcript": []},
        )
        return self.status, json.dumps(body).encode()


def _setup(engine, corpus, clock, *, fye="0630"):
    engine.execute(
        "INSERT INTO entity (cik, name, fiscal_year_end, source_ref, fetched_at) "
        "VALUES (?, 'Example Cloud Corp', ?, 't', 'n')",
        (CIK, fye),
    )
    engine.execute(
        "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES ('XCLD', ?, '2020-01-01', 't')",
        (CIK,),
    )
    _release(engine, corpus, clock, RELEASE, "2026-07-29", RELEASE_TEXT)


def _release(engine, corpus, clock, accession, filed, text):
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, items, ingested_at) "
        "VALUES (?, ?, '8-K', ?, '2.02,9.01', 'n')",
        (accession, CIK, filed),
    )
    engine.execute("INSERT INTO filing_cik (accession, cik) VALUES (?, ?)", (accession, CIK))
    doc_id = corpus.execute(
        "INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, fetched_at) "
        "VALUES (?, ?, 'ex991.htm', 'EX-99.1', ?, ?, 'sha', 'n')",
        (accession, CIK, f"https://x/{accession}", text),
    ).lastrowid
    resplit(corpus, doc_id, clock.now())


def _client(engine, clock, transport, **kw):
    return AlphaVantageClient(KEY, engine, transport=transport, now=clock.now,
                              clock=clock.mono, sleep=clock.sleep, **kw)  # fmt: skip


@pytest.fixture
def loaded(dbs, clock):
    engine, corpus = dbs
    _setup(engine, corpus, clock)
    t = AvTransport({"2026Q4": TRANSCRIPT})
    lines = run_calls_step(engine, corpus, _client(engine, clock, t), {"XCLD": CIK}, clock.now())
    return engine, corpus, t, lines


# --- Fiscal quarters and roles -----------------------------------------------------


@pytest.mark.parametrize(
    ("filed", "fye", "expected"),
    [
        ("2026-07-29", "0630", (2026, 4)),  # Microsoft FY26 Q4 call
        ("2026-10-28", "0630", (2027, 1)),
        ("2026-09-09", "0531", (2027, 1)),  # Oracle FY27 Q1 (probe: ORCL 2027Q1)
        ("2026-08-27", "0125", (2027, 2)),  # NVIDIA: FY2027 ends January 2027
        ("2026-02-25", "0125", (2026, 4)),
        ("2026-07-30", "0927", (2026, 3)),  # Apple
        ("2026-04-28", "1231", (2026, 1)),
        ("2026-02-20", "0103", (2025, 4)),  # 52/53-week year ending Jan 3 = fiscal 2025
    ],
)
def test_fiscal_quarter_of_a_release(filed, fye, expected):
    assert fiscal_quarter(date.fromisoformat(filed), fye) == expected


def test_fiscal_quarter_needs_a_fiscal_year_end():
    assert fiscal_quarter(date(2026, 7, 29), None) is None


@pytest.mark.parametrize(
    ("speaker", "title", "role"),
    [
        ("Operator", "", "operator"),
        ("Amy Hood", "Executive Vice President and Chief Financial Officer", "management"),
        ("Jonathan Neilson", "Vice President, Investor Relations", "management"),
        ("Keith Weiss", "Analyst, Morgan Stanley", "analyst"),
        ("Mark Moerdler", "Managing Director", "analyst"),
        ("Brent Thill", "Jefferies", "analyst"),
        ("Unknown", "", "other"),
    ],
)
def test_speaker_roles(speaker, title, role):
    assert role_of(speaker, title) == role


# --- Parser: calls -----------------------------------------------------------------


def test_spoken_periods_resolve_against_the_call_quarter():
    def labels(text, anchor):
        return [p.label for p in find_periods(text, anchor=anchor)]

    assert labels("next quarter", (2026, 4)) == ["FY2027 Q1"]
    assert labels("in the third quarter", (2026, 2)) == ["FY2026 Q3"]
    assert labels("in Q1", (2026, 4)) == ["FY2027 Q1"]
    assert labels("next fiscal year", (2026, 4)) == ["FY2027"]
    assert labels("for the full year", (2026, 2)) == ["FY2026"]
    assert labels("for the full year", (2026, 4)) == []  # ambiguous after Q4
    assert labels("next quarter", None) == []  # releases: no anchor, no spoken periods
    assert labels("calendar year 2026 and CY27", None) == ["CY2026", "CY2027"]
    assert labels("the third quarter of fiscal 2027", (2026, 4)) == ["FY2027 Q3"]


def test_parse_call_reads_management_only_with_directions():
    text = "\n".join(t["content"] for t in TRANSCRIPT["transcript"])
    cfo_start = text.index(CFO)
    analyst = text.index("Do you expect")
    r = parse_call(text, [(cfo_start, cfo_start + len(CFO))], (2026, 4))
    got = {(i.metric, i.period, i.value.low) for i in r.items}
    assert ("capex", "FY2027 Q1", 40e9) in got
    assert ("capex", "CY2026", 175e9) in got
    assert ("revenue", "FY2027 Q1", 85e9) in got
    assert all(i.quote_start < analyst for i in r.items)  # the analyst's $200 billion is never read
    assert [(d.metric, d.period, d.direction) for d in r.directions] == [("capex", "FY2027", "up")]
    assert [u.reason for u in r.unparsed] == ["growth-rate wording (kept for review, D-UI-15)"]
    assert r.skipped == 1  # gross-margin sentence: not capex → counted, not queued


# --- Alpha Vantage client --------------------------------------------------------------


def test_client_logs_without_key_and_keeps_the_budget(dbs, clock):
    engine, _ = dbs
    t = AvTransport({"2026Q4": TRANSCRIPT})
    c = _client(engine, clock, t, daily_budget=2)
    assert len(c.transcript("XCLD", "2026Q4").data.turns) == 4
    assert c.transcript("XCLD", "2026Q3").data.turns == []  # empty = not available yet
    stopped = c.transcript("XCLD", "2026Q2")
    assert stopped.throttled and "daily budget" in stopped.reason and len(t.calls) == 2
    logged = engine.execute("SELECT url, detail FROM fetch_log").fetchall()
    assert all(KEY not in r["url"] + (r["detail"] or "") for r in logged)
    assert t.calls[0]["apikey"] == KEY and clock.sleeps == [15.0]


def test_rate_limit_message_is_a_throttle(dbs, clock):
    engine, _ = dbs
    t = AvTransport(
        {"2026Q4": {"Information": "Our standard API rate limit is 25 requests per day."}}
    )
    res = _client(engine, clock, t).transcript("XCLD", "2026Q4")
    assert res.throttled
    assert engine.execute("SELECT outcome FROM fetch_log").fetchone()[0] == "throttled"
    assert isinstance(parse_reply(b"not json"), str)


# --- Store, scan, match ----------------------------------------------------------------


def test_transcript_is_stored_with_speaker_sections_and_searchable(loaded):
    engine, corpus, t, lines = loaded
    assert any("stored XCLD 2026Q4 (4 turns)" in ln for ln in lines)
    cd = engine.execute("SELECT * FROM call_document").fetchone()
    assert (cd["accession"], cd["quarter"], cd["release_accession"], cd["stated_on"]) == (
        "AV-XCLD-2026Q4", "FY2026 Q4", RELEASE, "2026-07-29")  # fmt: skip
    labels = [r[0] for r in corpus.execute("SELECT label FROM section ORDER BY start_offset")
              if r[0].startswith("call")]  # fmt: skip
    assert labels == ["call operator", "call management", "call management", "call analyst"]
    hits = search(corpus, '"calendar year 2026"', ciks=[CIK])
    assert [h.accession for h in hits] == ["AV-XCLD-2026Q4"]
    raw = corpus.execute("SELECT source, symbol, quarter FROM doc_raw").fetchone()
    assert tuple(raw) == ("alpha_vantage", "XCLD", "2026Q4")


def test_release_wins_call_fills_gaps_and_matches_upgrade(loaded):
    engine, *_ = loaded
    rows = {
        (r["metric"], r["period"], r["origin"]): r
        for r in engine.execute("SELECT * FROM guidance WHERE cik = ?", (CIK,))
    }
    same = rows[("capex", "FY2027 Q1", "call")]
    assert (same["grade"], same["matched_accession"]) == ("A", RELEASE)  # equal → A
    cy = rows[("capex", "CY2026", "call")]
    assert (cy["grade"], cy["low"], cy["clause"]) == ("B", 175e9, "including finance leases")
    d = rows[("capex", "FY2027", "call")]
    assert (d["kind"], d["direction"], d["low"], d["grade"]) == ("direction", "up", None, "B")
    assert ("revenue", "FY2027 Q1", "call") not in rows  # differs from the release → review
    conflict = engine.execute(
        "SELECT payload FROM review_queue WHERE kind = 'guidance_conflict'").fetchone()  # fmt: skip
    p = json.loads(conflict[0])
    assert p["cross"] and "$85 billion" in p["other"] and "$80.0 billion" in p["kept"]
    reviews = [json.loads(r[0])["text"] for r in engine.execute(
        "SELECT payload FROM review_queue WHERE kind = 'guidance_unparsed'")]  # fmt: skip
    assert reviews == ["We expect the capex growth rate in FY27 to be lower than FY26."]
    assert not engine.execute("SELECT 1 FROM guidance WHERE low = 200e9").fetchone()


def test_same_day_call_repeat_is_not_a_change(loaded):
    engine, *_ = loaded
    assert [c for c in changes_for(engine, CIK) if c.metric == "capex"] == []


def test_rescans_replace_rows_and_release_rescan_triggers_call_rescan(loaded, clock):
    engine, corpus, *_ = loaded
    before = engine.execute("SELECT count(*) FROM guidance").fetchone()[0]
    assert scan_calls(engine, corpus, clock.now()) == []  # nothing new
    again = scan_calls(engine, corpus, clock.now(), ciks={CIK})
    assert len(again) == 1
    assert engine.execute("SELECT count(*) FROM guidance").fetchone()[0] == before
    assert scan_all(engine, corpus, clock.now()) == []


def test_definition_change_is_labelled_not_a_cut(loaded, clock):
    engine, corpus, *_ = loaded
    _release(engine, corpus, clock, "later-rel", "2026-10-28",
             "We expect calendar 2026 capital expenditures of approximately $165 billion, excluding finance leases.\n")  # fmt: skip
    scan_all(engine, corpus, clock.now())
    [c] = [c for c in changes_for(engine, CIK) if c.period == "CY2026"]
    assert (c.kind, c.prev_origin, c.origin) == ("definition changed", "call", "release")


def test_paired_call_passages_go_to_gemini(loaded, clock):
    engine, corpus, *_ = loaded
    _release(engine, corpus, clock, "later-rel", "2026-10-28",
             "We expect capital expenditures of $45 billion in the first quarter of fiscal 2027.\n")  # fmt: skip
    engine.execute("UPDATE call_document SET release_accession = 'later-rel'")  # pair for the test
    scan_all(engine, corpus, clock.now())
    prep = guidance_reasons.prepare(engine, corpus, CIK)
    assert any(c.kind == "raised" for c in prep.asked.values())
    origins = {p.origin for p in prep.passages}
    assert origins == {"release", "call"}
    assert (
        "call transcript (oral statement, third-party transcript) AV-XCLD-2026Q4"
        in prep.request.user
    )


# --- Plan, retries, reminders, import -------------------------------------------------


def test_empty_reply_retried_daily_then_reminder(dbs, clock):
    engine, corpus = dbs
    _setup(engine, corpus, clock)
    t = AvTransport({})
    now = clock.now()  # 2026-10-07: 70 days after the release, past the retry window
    early = now.replace(year=2026, month=8, day=5)
    fetch_due(engine, corpus, _client(engine, clock, t), {"XCLD": CIK}, early)
    assert plan(engine, {"XCLD": CIK}, early.date()) == []  # tried today
    assert len(plan(engine, {"XCLD": CIK}, early.date() + timedelta(days=1))) == 1
    assert plan(engine, {"XCLD": CIK}, now.date()) == []  # after 30 days: no more requests
    assert queue_reminders(engine, now) == ["XCLD FY2026 Q4"]
    item = engine.execute("SELECT kind, payload FROM review_queue").fetchone()
    p = json.loads(item["payload"])
    assert item["kind"] == "m02_ir_download"
    assert (p["av_quarter"], p["release_accession"], p["release_filed"]) == (
        "2026Q4",
        RELEASE,
        "2026-07-29",
    )
    assert queue_reminders(engine, now) == []  # once


def test_probe_replies_are_imported_not_fetched(dbs, clock, tmp_path):
    engine, corpus = dbs
    _setup(engine, corpus, clock)
    folder = tmp_path / "probe"
    folder.mkdir()
    (folder / "XCLD_2026Q4.json").write_text(json.dumps(TRANSCRIPT), encoding="utf-8")
    (folder / "XCLD_2027Q1.json").write_text(
        json.dumps({"symbol": "XCLD", "quarter": "2027Q1", "transcript": []}), encoding="utf-8"
    )
    (folder / "ZZZZ_2026Q1.json").write_text("{}", encoding="utf-8")
    lines = import_files(engine, corpus, folder.glob("*.json"), clock.now())
    assert lines[0].startswith("imported XCLD 2026Q4: 4 turns, release 2026-07-29")
    assert "empty" in lines[1] and "not in the ticker map" in lines[2]
    assert plan(engine, {"XCLD": CIK}, clock.now().date()) == []
    assert engine.execute("SELECT count(*) FROM fetch_log").fetchone()[0] == 0


# --- IR downloads ---------------------------------------------------------------------


PREPARED = (
    "Prepared remarks, fourth quarter fiscal 2026\n"
    "We expect operating income of $30 billion in the first quarter of fiscal 2027, reflecting continued demand across our cloud business and disciplined spending.\n"
    "Question-and-Answer Session\n"
    "Do you expect operating income of $500 billion in the first quarter of fiscal 2027?\n"
)


def test_ir_pdf_is_grade_a_and_qa_is_not_parsed(dbs, clock, tmp_path):
    engine, corpus = dbs
    _setup(engine, corpus, clock)
    scan_all(engine, corpus, clock.now())
    pdf = tmp_path / "XCLD-Q4-FY26-remarks.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    acc, scan = ir_inbox.ingest_pdf(
        engine, corpus, path=pdf, cik=CIK, symbol="XCLD", av_quarter="2026Q4",
        doc_kind="transcript", release_accession=RELEASE, release_filed="2026-07-29",
        now=clock.now(), extract=lambda raw: PREPARED,
    )  # fmt: skip
    assert acc == "IR-XCLD-2026Q4-transcript" and scan.items == 1
    row = engine.execute("SELECT * FROM guidance WHERE origin = 'ir'").fetchone()
    assert (row["metric"], row["low"], row["grade"]) == ("operating_income", 30e9, "A")
    with pytest.raises(ir_inbox.InboxError, match="already stored"):
        ir_inbox.ingest_pdf(engine, corpus, path=pdf, cik=CIK, symbol="XCLD",
                            av_quarter="2026Q4", doc_kind="transcript", release_accession=None,
                            release_filed=None, now=clock.now(), extract=lambda raw: PREPARED)  # fmt: skip
    bad = tmp_path / "notes.pdf"
    bad.write_bytes(b"hello")
    with pytest.raises(ir_inbox.InboxError, match="not a PDF"):
        ir_inbox.ingest_pdf(engine, corpus, path=bad, cik=CIK, symbol="XCLD", av_quarter="2026Q4",
                            doc_kind="transcript", release_accession=None, release_filed=None,
                            now=clock.now())  # fmt: skip


def test_pdf_text_reads_a_real_pdf():
    text = ir_inbox.pdf_text(tiny_pdf("We expect capex of $12 billion."))
    assert "We expect capex of $12 billion." in text


# --- UI ----------------------------------------------------------------------------------


@pytest.fixture
def app_client(tmp_path, clock):
    data = tmp_path / "data"
    engine = open_db("engine", data)
    corpus = open_db("corpus", data)
    _setup(engine, corpus, clock)
    t = AvTransport({"2026Q4": TRANSCRIPT})
    run_calls_step(engine, corpus, _client(engine, clock, t), {"XCLD": CIK}, clock.now())
    engine.close()
    corpus.close()
    watch = tmp_path / "watch.toml"
    watch.write_text('[watchlist]\ntickers = ["XCLD"]\n', encoding="utf-8")
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    app = create_app(UiSettings(data_dir=data, watchlist=watch, downloads_dir=downloads))
    with TestClient(app) as c:
        yield c, data, downloads


def test_guidance_tab_labels_call_rows(app_client):
    client, *_ = app_client
    html = client.get("/c/XCLD?tab=guidance").text
    assert "call · oral · grade B" in html and "call · oral · grade A" in html
    assert "direction only: up (no figure stated)" in html
    assert "including finance leases" in html
    assert "forecast, not a commitment" in html
    assert "FY2026 Q4</a> (transcript, Alpha Vantage: 3 rows)" in html
    assert "built-in method" not in html


def test_reader_and_search_label_transcripts(app_client):
    client, *_ = app_client
    html = client.get("/doc/AV-XCLD-2026Q4").text
    assert "oral statement, not in an SEC filing" in html
    assert "View this filing on SEC" not in html
    assert "Amy Example — Executive Vice President" in html  # speakers in the table of contents
    hits = client.get("/c/XCLD?tab=search&q=%22calendar+year+2026%22").text
    assert "call · oral, grade B" in hits


def test_i_downloaded_it_stores_the_newest_pdf(app_client):
    client, data, downloads = app_client
    engine = open_db("engine", data)
    engine.execute(
        "INSERT INTO call_fetch (symbol, quarter, cik, release_accession, release_filed, outcome, "
        "attempts, first_at, last_at) VALUES ('XCLD', '2026Q3', ?, ?, '2026-04-20', 'empty', 3, "
        "'2026-04-21', '2026-05-15')",
        (CIK, RELEASE),
    )
    from datetime import UTC, datetime

    assert queue_reminders(engine, datetime(2026, 10, 7, tzinfo=UTC)) == ["XCLD FY2026 Q3"]
    item_id = engine.execute(
        "SELECT item_id FROM review_queue WHERE kind = 'm02_ir_download'"
    ).fetchone()[0]
    engine.close()
    assert "No PDF found" in client.get(f"/review/{item_id}/pickup").text
    line = "We expect operating income of $31 billion in the fourth quarter of fiscal 2026. " * 4
    (downloads / "remarks.pdf").write_bytes(tiny_pdf(line))
    page = client.get(f"/review/{item_id}/pickup").text
    assert "remarks.pdf" in page and "Store this file for XCLD FY2026 Q3" in page
    r = client.post(f"/review/{item_id}/ingest",
                    data={"name": "remarks.pdf", "doc_kind": "prepared_remarks"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and "stored remarks.pdf" in r.headers["location"].replace(
        "%20", " "
    )
    engine = open_db("engine", data)
    item = engine.execute(
        "SELECT resolution FROM review_queue WHERE item_id = ?", (item_id,)
    ).fetchone()
    assert item[0] == "downloaded"
    row = engine.execute("SELECT origin, grade, low FROM guidance WHERE origin = 'ir'").fetchone()
    assert tuple(row) == ("ir", "A", 31e9)
    engine.close()
    assert (downloads / "remarks.pdf").exists()  # the file is not moved


# --- Live-check fixes (2026-10-09, D-M02-23); wording modelled on the real cases -------


def _parse_turn(turn: str, anchor=(2026, 4)):
    return parse_call(turn, [(0, len(turn))], anchor)


def test_recounted_guidance_is_skipped_and_the_new_figure_kept():
    r = _parse_turn(
        "Earlier this year, we said we plan to invest approximately $150 billion in capex in 2026. "
        "We now believe we will spend approximately $170 billion in capex in 2026."
    )
    assert [(i.metric, i.period, i.value.low) for i in r.items] == [("capex", "FY2026", 170e9)]
    assert r.skipped == 1


def test_other_parties_capex_is_not_the_companys():
    r = _parse_turn(
        "Capex by the top five cloud hyperscalers is expected to reach nearly $700 billion in 2026 "
        "and $1.2 trillion in 2027. We expect our own capex of $2 billion next year."
    )
    assert [(i.metric, i.period, i.value.low) for i in r.items] == [("capex", "FY2027", 2e9)]
    assert r.unparsed == []
    assert find_values("$1.2 trillion")[0].low == 1.2e12


def test_segment_revenue_is_not_total_revenue():
    r = _parse_turn(
        "We expect Q1 AI revenue to be $20 billion. For Q1, we forecast software revenue of "
        "approximately $8 billion. We expect consolidated revenue of $33 billion in Q1."
    )
    assert [(i.metric, i.period, i.value.low) for i in r.items] == [("revenue", "FY2027 Q1", 33e9)]


def test_bounds_and_year_ago_comparisons():
    r = _parse_turn(
        "We continue to expect capex for this year will be more than $20 billion. "
        "We expect Q1 gross margin to be approximately 71%, down from 76% a year ago.",
        anchor=(2026, 2),
    )
    capex, gm = sorted(r.items, key=lambda i: i.metric)
    assert (capex.period, capex.value.low, capex.value.bound) == ("FY2026", 20e9, "floor")
    assert gm.prior is None  # a year-ago actual, not prior guidance


def test_period_carried_from_the_sentence_before_and_noun_guide():
    r = _parse_turn(
        "For Q1, we expect revenue of $80 billion to $81 billion. "
        "We expect capex spend will be over $45 billion, including finance leases. "
        "Capital expenditures were $40 billion, as noted in our guide. "
        "Next, we expect capital expenditures to decrease on a sequential basis."
    )
    capex = [i for i in r.items if i.metric == "capex"]
    assert [(i.period, i.value.low, i.value.bound) for i in capex] == [("FY2027 Q1", 45e9, "floor")]
    assert [(d.period, d.direction) for d in r.directions] == [("FY2027 Q1", "down")]
    assert r.unparsed == []


def test_multi_year_and_signal_free_capex_sentences():
    r = _parse_turn(
        "Capex will grow for the next two to three years as we add capacity. "
        "This is a big capex year, and I am confident the investments will pay off."
    )
    assert r.directions == []
    assert [u.reason for u in r.unparsed] == ["multi-year wording, no single period"]
    assert r.skipped == 1


def test_results_release_preferred_over_deliveries_report(dbs, clock):
    engine, corpus = dbs
    _setup(engine, corpus, clock, fye="1231")
    # Q3 2026 (calendar): deliveries 8-K two days after quarter end, results three weeks later
    _release(engine, corpus, clock, "deliveries", "2026-10-02", "Deliveries were 400,000.\n")
    _release(engine, corpus, clock, "results", "2026-10-22", "Results.\n")
    _release(engine, corpus, clock, "investor-day", "2026-12-15", "Investor day.\n")
    from engine.calls.transcripts import company_releases

    assert company_releases(engine, CIK)["2026Q3"] == ("results", "2026-10-22")


def test_one_symbol_per_company_and_relink(dbs, clock):
    engine, corpus = dbs
    _setup(engine, corpus, clock)
    due = plan(engine, {"XCLD-WT": CIK, "XCLD": CIK}, clock.now().date())
    assert {d.symbol for d in due} == {"XCLD"}
    # a transcript stored before its release was known gets linked later
    folder_reply = parse_reply(json.dumps(TRANSCRIPT | {"quarter": "2026Q3"}).encode())
    from engine.calls.transcripts import store_transcript

    store_transcript(engine, corpus, cik=CIK, symbol="XCLD", quarter="2026Q3",
                     reply=folder_reply, release=None, now=clock.now())  # fmt: skip
    assert scan_calls(engine, corpus, clock.now())[0].outcome == "no_date"
    _release(engine, corpus, clock, "q3-results", "2026-04-28", RELEASE_TEXT)
    (s,) = scan_calls(engine, corpus, clock.now())
    assert s.doc.stated_on == "2026-04-28" and s.outcome != "no_date"


# --- Live check 2 fixes (2026-10-09, D-M02-25) --------------------------------------


def test_segment_scoped_sentences_and_analyst_forecasts_are_skipped():
    r = _parse_turn(
        "In Intelligent Devices, we expect revenue of $12 to $13 billion. "
        "In Q1, we expect revenue of $80 billion. "
        "With analysts now forecasting hyperscale capex to exceed $1 trillion by 2027, demand is strong."
    )
    assert [(i.metric, i.period, i.value.low) for i in r.items] == [("revenue", "FY2027 Q1", 80e9)]
    assert r.unparsed == []


def test_two_digit_fiscal_years_and_comparison_periods():
    r = _parse_turn(
        "We now expect fiscal 28 revenue to reach $16 billion. "
        "We expect quarterly capex in fiscal 2027 to be above fiscal Q4 levels. "
        "We are forecasting 2027 capital expenditures to be significantly above the 2026 levels.",
        anchor=(2026, 4),
    )
    assert [(i.metric, i.period, i.value.low) for i in r.items] == [("revenue", "FY2028", 16e9)]
    assert [(d.period, d.direction) for d in r.directions] == [("FY2027", "up"), ("FY2027", "up")]


def test_no_guidance_statement_and_past_context_not_carried():
    r = _parse_turn(
        "We are not providing a specific outlook for 2027 capex at this time. "
        "Revenue for fiscal 2025 was strong and we will keep investing. "
        "We expect revenue to be $12 billion.",
        anchor=(2026, 4),
    )
    reasons = [s.reason for s in r.skipped_spans]
    assert r.items == [] and "not capex (no period)" in reasons  # FY2025 over: no context
    assert "says no guidance is given" in reasons
