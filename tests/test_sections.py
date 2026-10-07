from __future__ import annotations

import json

from engine.sec.sections import (
    resplit,
    section_text,
    split_document,
    split_items,
    strip_header,
)
from engine.store.db import connect, migrate

BODY = "Body sentence that fills a section with enough text to look real. " * 20

TEN_K = "\n".join(
    [
        "UNITED STATES",
        "FORM 10-K",
        "TABLE OF CONTENTS",
        "Part I",
        "Item 1.\tBusiness\t1",
        "Item 1A.\tRisk Factors\t5",
        "Item 1B.\tUnresolved Staff Comments\t15",
        "Item 2.\tProperties\t16",
        "Part II",
        "Item 5.\tMarket for Registrant's Common Equity\t17",
        "Item 7.\tManagement's Discussion and Analysis\t18",
        "Item 7A.\tQuantitative and Qualitative Disclosures About Market Risk\t30",
        "Item 8.\tFinancial Statements and Supplementary Data\t31",
        "Part III",
        "Item 10.\tDirectors, Executive Officers and Corporate Governance\t60",
        "Part IV",
        "Item 15.\tExhibit and Financial Statement Schedules\t61",
        "Item 16.\tForm 10-K Summary\t64",
        "Forward-looking statements. " + BODY,
        "PART I",
        "Item 1. Business",
        "The Company designs products. " + BODY,
        "Item 1A. Risk Factors",
        "Risks. " + BODY,
        "Item 7 of this report discusses results.",  # cross-reference at a line start
        "More risk text. " + BODY,
        "Item 1B. Unresolved Staff Comments",
        "None.",
        "Item 2. Properties",
        "Headquarters. " + BODY,
        "PART II",
        "Item 5. Market for Registrant's Common Equity",
        "Listed on Nasdaq. " + BODY,
        "Item 7. Management's Discussion and Analysis of Financial Condition",
        "MD&A starts here. " + BODY * 3,
        "Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
        "Interest rate risk. " + BODY,
        "Item 8. Financial Statements and Supplementary Data",
        "Balance sheet. " + BODY * 2,
        "PART III",
        "Item 10. Directors, Executive Officers and Corporate Governance",
        "Incorporated by reference.",
        "PART IV",
        "Item 15. Exhibit and Financial Statement Schedules",
        "Exhibit list. " + BODY,
        "Item 16. Form 10-K Summary",
        "None.",
        "SIGNATURES",
        "/s/ Chief Executive Officer",
    ]
)

TEN_Q = "\n".join(
    [
        "FORM 10-Q",
        "Part I\tFinancial Information",
        "Item 1.\tFinancial Statements\t1",
        "Item 2.\tManagement's Discussion and Analysis\t10",
        "Part II\tOther Information",
        "Item 1A.\tRisk Factors\t20",
        "PART I — FINANCIAL INFORMATION",
        "Item 1. Financial Statements",
        "Statements. " + BODY * 2,
        "Item 2. Management's Discussion and Analysis",
        "Quarter MD&A. " + BODY * 2,
        "Item 4. Controls and Procedures",
        "Effective. " + BODY,
        "PART II — OTHER INFORMATION",
        "Item 1. Legal Proceedings",
        "Litigation. " + BODY,
        "Item 1A. Risk Factors",
        "No material changes. " + BODY,
        "Item 6. Exhibits",
        "Exhibit list.",
        "SIGNATURE",
        "/s/ CFO",
    ]
)

EIGHT_K = "\n".join(
    [
        "FORM 8-K",
        "Item 2.02 Results of Operations and Financial Condition.",
        "The company issued a press release. " + BODY,
        "Item 9.01 Financial Statements and Exhibits.",
        "(d) Exhibit 99.1 press release.",
        "SIGNATURE",
        "/s/ CFO",
    ]
)


def labels(split):
    return [s.label for s in split.sections]


def body(text, label, split):
    s = next(s for s in split.sections if s.label == label)
    return text[s.start : s.end]


def test_10k_takes_body_headings_not_toc_or_cross_refs():
    split = split_items(TEN_K, "10-K")
    assert split.outcome == "split"
    assert labels(split) == [
        "cover",
        "10-K Item 1",
        "10-K Item 1A",
        "10-K Item 1B",
        "10-K Item 2",
        "10-K Item 5",
        "10-K Item 7",
        "10-K Item 7A",
        "10-K Item 8",
        "10-K Item 10",
        "10-K Item 15",
        "10-K Item 16",
        "signatures",
    ]
    assert "TABLE OF CONTENTS" in body(TEN_K, "cover", split)
    assert "Forward-looking statements" in body(TEN_K, "cover", split)
    mdna = body(TEN_K, "10-K Item 7", split)
    assert mdna.startswith("Item 7. Management's") and "MD&A starts here" in mdna
    assert "Interest rate risk" not in mdna
    assert "Item 7 of this report" in body(TEN_K, "10-K Item 1A", split)  # stays in 1A
    assert body(TEN_K, "10-K Item 16", split).strip() == "Item 16. Form 10-K Summary\nNone."
    item7 = next(s for s in split.sections if s.label == "10-K Item 7")
    assert item7.title == "Management's Discussion and Analysis of Financial Condition"


def test_sections_tile_the_document():
    split = split_items(TEN_K, "10-K")
    assert split.sections[0].start == 0 and split.sections[-1].end == len(TEN_K)
    for a, b in zip(split.sections, split.sections[1:], strict=False):
        assert a.end == b.start


def test_10q_labels_carry_the_part():
    split = split_items(TEN_Q, "10-Q")
    assert split.outcome == "split"
    assert labels(split) == [
        "cover",
        "10-Q Part I Item 1",
        "10-Q Part I Item 2",
        "10-Q Part I Item 4",
        "10-Q Part II Item 1",
        "10-Q Part II Item 1A",
        "10-Q Part II Item 6",
        "signatures",
    ]
    assert "Quarter MD&A" in body(TEN_Q, "10-Q Part I Item 2", split)
    assert "Litigation" in body(TEN_Q, "10-Q Part II Item 1", split)


def test_8k_items():
    split = split_items(EIGHT_K, "8-K/A")
    assert labels(split) == ["cover", "8-K Item 2.02", "8-K Item 9.01", "signatures"]
    assert "press release" in body(EIGHT_K, "8-K Item 2.02", split)


def test_missing_required_item_falls_back_to_whole():
    no_item8 = TEN_K.replace("Item 8.", "Section 8.")
    split = split_items(no_item8, "10-K")
    assert split.outcome == "fallback" and split.missing == ("Item 8",)
    assert labels(split) == ["whole"] and split.sections[0].end == len(no_item8)


def test_10q_without_part_headings_falls_back():
    split = split_items(TEN_Q.replace("PART", "SECTION").replace("Part", "Sect"), "10-Q")
    assert split.outcome == "fallback"
    assert split.missing == ("Part I Item 1", "Part I Item 2")


def test_exhibit_header_is_skipped():
    text = "EX-99.1\n2\na8-kex991.htm\nEX-99.1\n\nExhibit 99.1\nApple reports results\n"
    start = strip_header(text, "EX-99.1", "a8-kex991.htm")
    assert text[start:].startswith("Exhibit 99.1")
    split = split_document(text, "EX-99.1", "a8-kex991.htm")
    assert split.outcome == "single" and labels(split) == ["EX-99.1"]
    assert text[split.sections[0].start :].startswith("Exhibit 99.1")


def test_no_header_starts_at_zero():
    assert strip_header("Exhibit 99.1\nText\n", "EX-99.1", "x.htm") == 0


def test_resplit_replaces_sections_and_logs(clock):
    corpus = connect(":memory:")
    migrate(corpus, "corpus")
    doc_id = corpus.execute(
        "INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, fetched_at) "
        "VALUES ('a', '0000000042', 'k.htm', '10-K', 'u', ?, 'h', 'now')",
        (TEN_K,),
    ).lastrowid
    for _ in range(2):  # running twice must not duplicate sections or FTS rows
        resplit(corpus, doc_id, clock.now())
    assert corpus.execute("SELECT count(*) FROM section").fetchone()[0] == 13
    assert corpus.execute("SELECT count(*) FROM section_fts").fetchone()[0] == 13

    row = corpus.execute(
        "SELECT s.section_id FROM section s JOIN section_fts f ON f.rowid = s.section_id "
        "WHERE section_fts MATCH 'label:\"Item 7A\"'"
    ).fetchone()
    assert section_text(corpus, row[0]).startswith("Item 7A. Quantitative")

    log = corpus.execute("SELECT * FROM split_log WHERE doc_id = ?", (doc_id,)).fetchone()
    assert log["outcome"] == "split" and json.loads(log["missing"]) == []
    assert "10-K Item 7" in json.loads(log["found"])
