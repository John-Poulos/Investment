from __future__ import annotations

import pytest

from engine.search.query import QueryError, get_passage, phrase, search
from engine.sec.sections import resplit
from engine.store.db import connect, migrate

FILLER = "General operating discussion without the search terms in it. " * 30
TEN_K = "\n".join(
    [
        "FORM 10-K",
        "Risk factors are described in Item 1A.",  # short cover mention
        "Item 1. Business",
        "We sell HBM3E memory to accelerator makers. " + FILLER,
        "Item 1A. Risk Factors",
        "Our customers may reduce orders. " + FILLER,
        "Supply of wafers could be disrupted. " + FILLER,
        "Item 7. Management's Discussion and Analysis",
        "Revenue increased. Officers adopted Rule 10b5-1 trading plans. " + FILLER,
        "Item 8. Financial Statements",
        "Balance sheet. " + FILLER,
        "SIGNATURES",
        "Signed.",
        "",
    ]
)
EX99 = "EX-99.1\n2\nex991.htm\nEX-99.1\n\nOutlook: revenue is expected to be $1.2 billion.\n"


@pytest.fixture
def corpus(clock):
    conn = connect(":memory:")
    migrate(conn, "corpus")
    for accession, cik, filename, doc_type, text in (
        ("acc-10k", "0000000042", "k.htm", "10-K", TEN_K),
        ("acc-8k", "0000000099", "ex991.htm", "EX-99.1", EX99),
    ):
        doc_id = conn.execute(
            "INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, "
            "fetched_at, parser_version) VALUES (?, ?, ?, ?, ?, ?, 'h', 'now', 'p1')",
            (accession, cik, filename, doc_type, f"https://x/{filename}", text),
        ).lastrowid
        resplit(conn, doc_id, clock.now())
    yield conn
    conn.close()


def test_label_weight_ranks_item_1a_above_cover_mention(corpus):
    hits = search(corpus, phrase("risk factors"))
    assert hits[0].section == "10-K Item 1A"
    assert {h.section for h in hits} >= {"10-K Item 1A", "cover"}


def test_domain_terms_match_as_phrases(corpus):
    (hit,) = search(corpus, phrase("10b5-1"))
    assert hit.section == "10-K Item 7" and "[10b5-1]" in hit.snippet
    (hit,) = search(corpus, phrase("HBM3E"))
    assert hit.section == "10-K Item 1"


def test_unquoted_punctuation_is_a_query_error(corpus):
    with pytest.raises(QueryError):
        search(corpus, "10b5-1")


def test_filters(corpus):
    assert [h.cik for h in search(corpus, "revenue", ciks=["0000000099"])] == ["0000000099"]
    assert search(corpus, "revenue", doc_types=["EX-99.1"])[0].accession == "acc-8k"
    assert {h.section for h in search(corpus, "revenue", sections=["10-K Item 7"])} == {
        "10-K Item 7"
    }
    assert search(corpus, "revenue", accessions=[]) == []


def test_get_passage_returns_citable_text(corpus):
    (hit,) = search(corpus, phrase("$1.2 billion"))
    p = get_passage(corpus, hit.passage_id)
    assert p is not None and p.section == "EX-99.1"
    assert "expected to be $1.2 billion" in p.text
    assert (p.accession, p.filename, p.doc_sha256, p.parser_version) == (
        "acc-8k",
        "ex991.htm",
        "h",
        "p1",
    )
    assert get_passage(corpus, 10_000) is None
