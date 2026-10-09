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


def test_past_full_year_goes_to_review_not_ledger(dbs, clock):
    engine, corpus = dbs
    text = "Outlook\nWe expect full year 2025 revenue to be $44.7 billion.\n"
    _filing(engine, "p1", "2.02", filed="2026-04-22")
    _doc(corpus, "p1", text)
    (res,) = scan_all(engine, corpus, clock.now())
    assert (res.outcome, res.items, res.unparsed) == ("review", 0, 1)
    (reason,) = [r[0] for r in engine.execute("SELECT reason FROM review_queue")]
    assert "already over at the release" in reason


def test_point_equal_to_centre_is_not_a_conflict(dbs, clock):
    engine, corpus = dbs
    text = (
        "Outlook for the third quarter of fiscal 2027:\n"
        "•GAAP and non-GAAP gross margins are expected to be 74.0%, "
        "plus or minus 50 basis points.\n"
        "Q3 FY2027 Outlook\n"
        "GAAP gross margin\t74.0\t%\n"
        "Non-GAAP gross margin\t74.0\t%\n"
    )
    _filing(engine, "g1", "2.02")
    _doc(corpus, "g1", text)
    (res,) = scan_all(engine, corpus, clock.now())
    assert (res.items, res.conflicts) == (2, 0)
    rows = engine.execute("SELECT kind, low, high FROM guidance ORDER BY basis").fetchall()
    assert [tuple(r) for r in rows] == [("plusminus", 73.5, 74.5)] * 2


def test_repeated_unparsed_sentence_queued_once(dbs, clock):
    engine, corpus = dbs
    text = "We expect to remit the $27.4 million in Q3 2026.\n" * 2
    _filing(engine, "d1", "2.02")
    _doc(corpus, "d1", text)
    (res,) = scan_all(engine, corpus, clock.now())
    assert res.unparsed == 1
    assert engine.execute("SELECT count(*) FROM review_queue").fetchone()[0] == 1


def test_extreme_tax_rate_flagged_not_dropped(dbs, clock):
    engine, corpus = dbs
    text = (
        "Intel's guidance for the fourth quarter of 2025 includes both GAAP and "
        "non-GAAP estimates as follows:\n"
        "Q4 2025\tGAAP\tNon-GAAP\n"
        "Tax Rate\t476%\t12%\n"
    )
    _filing(engine, "t1", "2.02", filed="2025-10-23")
    _doc(corpus, "t1", text)
    scan_all(engine, corpus, clock.now())
    rows = {
        r["basis"]: (r["low"], r["flag"], r["flag_reason"])
        for r in engine.execute("SELECT basis, low, flag, flag_reason FROM guidance")
    }
    assert rows["GAAP"][:2] == (476, "not_meaningful") and "near zero" in rows["GAAP"][2]
    assert rows["non-GAAP"] == (12, None, None)
