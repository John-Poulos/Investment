from __future__ import annotations

import json

from engine.guidance.ledger import earnings_releases, scan_all
from engine.guidance.parse import PARSER_VERSION
from tests.test_guidance_parse import META, MICRON

CIK = "0000000042"


def _filing(engine, accession, items, filed="2026-07-29"):
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, items, ingested_at) "
        "VALUES (?, ?, '8-K', ?, ?, 'now')",
        (accession, CIK, filed, items),
    )


def _doc(corpus, accession, text, doc_type="EX-99.1", filename="ex991.htm"):
    corpus.execute(
        "INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'sha', 'now')",
        (accession, CIK, filename, doc_type, f"https://x/{accession}/{filename}", text),
    )


def test_only_item_202_releases(dbs):
    engine, corpus = dbs
    _filing(engine, "a-earn", "2.02,9.01")
    _filing(engine, "a-other", "7.01,9.01")
    _doc(corpus, "a-earn", META)
    _doc(corpus, "a-other", META)
    _doc(corpus, "a-earn", "x", doc_type="EX-99.2", filename="ex992.htm")
    assert [r.accession for r in earnings_releases(engine, corpus)] == ["a-earn"]


def test_scan_stores_rows_with_exact_quotes(dbs, clock):
    engine, corpus = dbs
    _filing(engine, "a1", "2.02,9.01")
    _doc(corpus, "a1", META)
    (res,) = scan_all(engine, corpus, clock.now())
    assert (res.outcome, res.items, res.unparsed, res.conflicts) == ("parsed", 4, 0, 0)

    row = engine.execute("SELECT * FROM guidance WHERE metric = 'capex'").fetchone()
    assert (row["low"], row["high"], row["prior_low"], row["prior_high"]) == (
        130e9,
        145e9,
        125e9,
        145e9,
    )
    assert row["quote"] == META[row["quote_start"] : row["quote_end"]]
    assert row["quote"].startswith("We anticipate 2026 capital expenditures")
    assert row["period_quote"] == "2026" and row["stated_on"] == "2026-07-29"
    assert (row["doc_sha256"], row["parser_version"]) == ("sha", PARSER_VERSION)

    # already scanned with this parser version → skipped; force re-scans without duplicates
    assert scan_all(engine, corpus, clock.now()) == []
    scan_all(engine, corpus, clock.now(), force=True)
    assert engine.execute("SELECT count(*) FROM guidance").fetchone()[0] == 4


def test_duplicate_table_rows_stored_once(dbs, clock):
    engine, corpus = dbs
    _filing(engine, "mu", "2.02")
    _doc(corpus, "mu", MICRON)
    (res,) = scan_all(engine, corpus, clock.now())
    assert (res.items, res.conflicts) == (8, 0)


def test_conflict_and_unparsed_go_to_review(dbs, clock):
    engine, corpus = dbs
    text = (
        "Outlook\n"
        "We expect third quarter 2026 revenue to be $10-11 billion.\n"
        "We expect third quarter 2026 revenue to be $12-13 billion.\n"
        "We expect third quarter 2026 bookings of $5 billion.\n"
    )
    _filing(engine, "c1", "2.02")
    _doc(corpus, "c1", text)
    (res,) = scan_all(engine, corpus, clock.now())
    assert (res.outcome, res.items, res.unparsed, res.conflicts) == ("parsed", 1, 1, 1)
    kinds = {
        r["kind"]: json.loads(r["payload"])
        for r in engine.execute("SELECT kind, payload FROM review_queue")
    }
    assert (
        kinds["guidance_unparsed"]["text"] == "We expect third quarter 2026 bookings of $5 billion."
    )
    assert kinds["guidance_conflict"]["kept"].endswith("$10-11 billion.")

    # re-scan replaces open review items instead of piling them up
    scan_all(engine, corpus, clock.now(), force=True)
    assert engine.execute("SELECT count(*) FROM review_queue").fetchone()[0] == 2


def test_release_without_guidance_is_recorded(dbs, clock):
    engine, corpus = dbs
    _filing(engine, "n1", "2.02")
    _doc(corpus, "n1", "Results\nRevenue was $90.0 billion and increased 18%.\n")
    (res,) = scan_all(engine, corpus, clock.now())
    assert res.outcome == "none"
    row = engine.execute("SELECT outcome, items FROM guidance_scan").fetchone()
    assert (row["outcome"], row["items"]) == ("none", 0)
