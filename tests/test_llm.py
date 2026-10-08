# ruff: noqa: E501  (fixtures are verbatim release lines)
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from engine.guidance.changes import changes_for, classify
from engine.guidance.ledger import scan_all
from engine.llm import guidance_reasons
from engine.llm.provider import FakeProvider, load_settings
from engine.llm.runs import run
from engine.llm.verify import numbers, quote_found, unsupported_numbers
from engine.sec.sections import resplit

CIK = "0000000042"
D = Decimal

JAN = """Meta Reports Fourth Quarter and Full Year 2025 Results
CFO Outlook Commentary
We anticipate 2026 capital expenditures, including principal payments on finance leases, to be in the range of $115-135 billion.
We expect full year 2026 total expenses to be in the range of $162-169 billion.
"""
APR = """Meta Reports First Quarter 2026 Results
CFO Outlook Commentary
We anticipate 2026 capital expenditures, including principal payments on finance leases, to be in the range of $125-145 billion, increased from our prior outlook of $115-135 billion. The increase reflects higher expected component pricing and additional data center capacity.
We expect full year 2026 total expenses to be in the range of $162-169 billion.
"""


# --- verify --------------------------------------------------------------------


def test_quote_found_normalizes_spacing_quotes_and_dashes():
    passage = "The increase reflects  higher expected\ncomponent pricing — and “capacity”."
    assert quote_found(
        'The increase reflects higher expected component pricing - and "capacity"', passage
    )
    assert not quote_found("The increase reflects lower costs", passage)
    assert not quote_found("pricing", passage)  # too short to prove anything


def test_numbers_must_come_from_quotes_or_facts():
    assert numbers("$2.4 billion and 15-17%") == {D("2.4"), D("15"), D("17")}
    facts = [D("125000000000"), D("145000000000"), D("2026")]
    assert unsupported_numbers("raised to $125-145 billion in 2026", [], facts) == set()
    assert unsupported_numbers("about $3 billion more", ["no figures here"], facts) == {D("3")}


# --- changes (code) ------------------------------------------------------------


def test_classify():
    assert classify((D(1), D(2)), (D(1), D(2))) == "reaffirmed"
    assert classify((D(1), D(2)), (D(2), D(3))) == "raised"
    assert classify((D(2), D(4)), (D(1), D(3))) == "lowered"
    assert classify((D(1), D(4)), (D(2), D(3))) == "narrowed"
    assert classify((D(125), D(145)), (D(130), D(145))) == "raised low end"
    assert classify((D(125), D(145)), (D(125), D(140))) == "lowered high end"
    assert classify((D(7), D(7)), (D(8), D(8))) == "raised"  # point guidance
    assert classify((D(2), D(3)), (D(1), D(4))) == "widened"


@pytest.fixture
def meta(dbs, clock):
    engine, corpus = dbs
    engine.execute(
        "INSERT INTO entity (cik, name, source_ref, fetched_at) VALUES (?, 'Meta Platforms, Inc.', 't', 'n')",
        (CIK,),
    )
    for acc, filed, text in (("m-jan", "2026-01-28", JAN), ("m-apr", "2026-04-29", APR)):
        engine.execute(
            "INSERT INTO filing (accession, cik, form, filed, items, ingested_at) VALUES (?, ?, '8-K', ?, '2.02,9.01', 'n')",
            (acc, CIK, filed),
        )
        doc_id = corpus.execute(
            "INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, fetched_at) "
            "VALUES (?, ?, 'ex991.htm', 'EX-99.1', ?, ?, ?, 'n')",
            (acc, CIK, f"u/{acc}", text, f"sha-{acc}"),
        ).lastrowid
        resplit(corpus, doc_id, clock.now())
    scan_all(engine, corpus, clock.now())
    return engine, corpus


def test_changes_between_releases_and_reaffirmations(meta):
    engine, _ = meta
    got = {(c.metric, c.kind, c.source) for c in changes_for(engine, CIK)}
    assert got == {("capex", "raised", "releases"), ("total_expenses", "reaffirmed", "releases")}


def test_flagged_rows_are_not_compared(meta):
    engine, _ = meta
    engine.execute("UPDATE guidance SET flag = 'not_meaningful' WHERE metric = 'capex'")
    assert {c.metric for c in changes_for(engine, CIK)} == {"total_expenses"}


# --- guidance reasons (LLM, recorded replies) -----------------------------------

REASON_QUOTE = (
    "The increase reflects higher expected component pricing and additional data center capacity."
)


def reply(**overrides) -> str:
    r = {
        "change_id": "C1",
        "reason_stated": True,
        "summary": "Higher expected component pricing and more data center capacity.",
        "quotes": [{"passage_id": "P2", "quote": REASON_QUOTE}],
    } | overrides
    return json.dumps({"reasons": [r]})


def test_prepare_asks_only_moved_guidance_with_its_passages(meta):
    engine, corpus = meta
    prep = guidance_reasons.prepare(engine, corpus, CIK)
    assert list(prep.asked) == ["C1"] and prep.asked["C1"].metric == "capex"
    assert (
        "C1: capex for FY2026: raised from $115 billion – $135 billion (earlier release) to $125 billion – $145 billion"
        in prep.request.user
    )
    assert REASON_QUOTE in prep.request.user
    assert {p.accession for p in prep.passages} == {"m-apr"}
    assert "Do not use outside knowledge" in prep.request.system


def test_verified_reason_is_stored_with_citation(meta, clock):
    engine, corpus = meta
    req = guidance_reasons.prepare(engine, corpus, CIK).request
    labels = [line.split("]")[0][1:] for line in req.user.splitlines() if line.startswith("[P")]
    fake = FakeProvider([reply(quotes=[{"passage_id": labels[0], "quote": REASON_QUOTE}])])
    res = run(engine, fake, load_settings(), req, clock.now())
    (ob,) = res.observations
    assert ob.verified and ob.detail is None
    (c,) = ob.citations
    assert (c.accession, c.quote, c.doc_sha256) == ("m-apr", REASON_QUOTE, "sha-m-apr")
    row = engine.execute("SELECT status, model, prompt_version, cost_usd FROM llm_call").fetchone()
    assert (row["status"], row["model"], row["prompt_version"]) == (
        "ok",
        "gemini-3.1-flash-lite",
        "guidance_reasons-1",
    )
    assert (
        engine.execute("SELECT count(*) FROM review_queue WHERE kind = 'llm_rejected'").fetchone()[
            0
        ]
        == 0
    )


def test_identical_request_is_served_from_storage(meta, clock):
    engine, corpus = meta
    req = guidance_reasons.prepare(engine, corpus, CIK).request
    label = req.user.split("[")[1].split("]")[0]
    fake = FakeProvider([reply(quotes=[{"passage_id": label, "quote": REASON_QUOTE}])])
    first = run(engine, fake, load_settings(), req, clock.now())
    again = run(
        engine, fake, load_settings(), req, clock.now()
    )  # no reply left: would fail if called
    assert again.cached and again.call_id == first.call_id and again.observations[0].verified
    assert len(fake.sent) == 1


@pytest.mark.parametrize(
    ("overrides", "problem"),
    [
        (
            {
                "quotes": [
                    {"passage_id": "P1", "quote": "Component pricing fell sharply this quarter."}
                ]
            },
            "quote not found",
        ),
        ({"summary": "Component pricing adds about $7 billion."}, "numbers not in quotes"),
        ({"quotes": []}, "reason stated without a quote"),
        ({"change_id": "C9"}, "unknown change id"),
    ],
)
def test_rejections_are_stored_and_queued_not_trusted(meta, clock, overrides, problem):
    engine, corpus = meta
    req = guidance_reasons.prepare(engine, corpus, CIK).request
    base = {"quotes": [{"passage_id": "P1", "quote": REASON_QUOTE}]}
    res = run(
        engine, FakeProvider([reply(**(base | overrides))]), load_settings(), req, clock.now()
    )
    rejected = [o for o in res.observations if not o.verified]
    assert rejected and any(problem in (o.detail or "") for o in rejected)
    queued = engine.execute(
        "SELECT reason FROM review_queue WHERE kind = 'llm_rejected'"
    ).fetchall()
    assert queued


def test_unanswered_change_is_recorded(meta, clock):
    engine, corpus = meta
    req = guidance_reasons.prepare(engine, corpus, CIK).request
    res = run(
        engine, FakeProvider([json.dumps({"reasons": []})]), load_settings(), req, clock.now()
    )
    (ob,) = res.observations
    assert not ob.verified and ob.detail == "no answer for this change"


def test_unreadable_reply_is_logged_and_raised(meta, clock):
    engine, corpus = meta
    req = guidance_reasons.prepare(engine, corpus, CIK).request
    with pytest.raises(ValueError, match="could not be read"):
        run(engine, FakeProvider(["not json"]), load_settings(), req, clock.now())
    row = engine.execute("SELECT status, response FROM llm_call").fetchone()
    assert (row["status"], row["response"]) == ("error", "not json")


def test_prompt_file_is_versioned():
    assert (
        Path(guidance_reasons.__file__)
        .with_name("prompts")
        .joinpath("guidance_reasons_1.md")
        .exists()
    )
    assert guidance_reasons.PROMPT_VERSION == "guidance_reasons-1"


def test_basis_shown_only_when_stated_and_boilerplate_not_sent(meta):
    engine, corpus = meta
    prep = guidance_reasons.prepare(engine, corpus, CIK)
    assert "(unspecified)" not in prep.request.user
    c = prep.asked["C1"]
    from dataclasses import replace as dc_replace

    assert "capex (GAAP) for FY2026" in guidance_reasons.describe(dc_replace(c, basis="GAAP"))
    assert not guidance_reasons._BOILERPLATE.match("Rules and contacts. Revenue rose.")
    assert guidance_reasons._BOILERPLATE.match(
        "This press release contains forward-looking statements regarding our future plans"
    )
