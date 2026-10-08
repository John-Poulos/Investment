from __future__ import annotations

from engine.search.passages import MAX_CHARS, MIN_CUT, chunk, ensure_passages, write_passages
from engine.sec.sections import resplit
from engine.store.db import connect, migrate
from tests.test_sections import TEN_K


def tiles(text: str, start: int, end: int, parts: list[tuple[int, int]]) -> bool:
    return (
        parts[0][0] == start
        and parts[-1][1] == end
        and all(a[1] == b[0] for a, b in zip(parts, parts[1:], strict=False))
    )


def test_short_text_is_one_passage():
    text = "Line one.\nLine two.\n"
    assert chunk(text, 0, len(text)) == [(0, len(text))]


def test_lines_pack_up_to_max_and_break_at_line_starts():
    line = "x" * 999 + "\n"  # 1000 chars
    text = line * 7
    parts = chunk(text, 0, len(text))
    assert tiles(text, 0, len(text), parts)
    assert [b - a for a, b in parts] == [3000, 3000, 1000]
    assert all(text[a - 1] == "\n" for a, _ in parts[1:])


def test_long_line_cuts_at_sentence_end():
    sentence = "Revenue grew because demand rose in every region. "  # 50 chars
    text = sentence * 200 + "\n"  # one 10,001-char line
    parts = chunk(text, 0, len(text))
    assert tiles(text, 0, len(text), parts)
    for a, b in parts[:-1]:
        assert MIN_CUT <= b - a <= MAX_CHARS
        assert text[a:b].endswith("region. ")


def test_unbroken_line_is_hard_cut():
    text = "9" * 7000
    parts = chunk(text, 0, len(text))
    assert parts == [(0, 3000), (3000, 6000), (6000, 7000)]


def test_trailing_blank_lines_join_last_passage():
    text = "a" * 2999 + "\n" + "b\n" + "\n\n"
    parts = chunk(text, 0, len(text))
    assert tiles(text, 0, len(text), parts)
    assert len(parts) == 2 and text[parts[-1][0] :].startswith("b")


def test_chunk_respects_section_bounds():
    text = "head\n" + "body line\n" * 5 + "tail\n"
    start, end = 5, 5 + 50
    parts = chunk(text, start, end)
    assert tiles(text, start, end, parts)


def _corpus_with_10k():
    corpus = connect(":memory:")
    migrate(corpus, "corpus")
    doc_id = corpus.execute(
        "INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, fetched_at) "
        "VALUES ('a', '0000000042', 'k.htm', '10-K', 'u', ?, 'h', 'now')",
        (TEN_K,),
    ).lastrowid
    return corpus, doc_id


def test_resplit_writes_passages_that_tile_each_section(clock):
    corpus, doc_id = _corpus_with_10k()
    for _ in range(2):  # no duplicates on re-run
        resplit(corpus, doc_id, clock.now())
    n = corpus.execute("SELECT count(*) FROM passage").fetchone()[0]
    assert n >= 13
    assert corpus.execute("SELECT count(*) FROM passage_fts").fetchone()[0] == n
    for s in corpus.execute("SELECT section_id, start_offset, end_offset FROM section"):
        parts = [
            (r[0], r[1])
            for r in corpus.execute(
                "SELECT start_offset, end_offset FROM passage WHERE section_id = ? ORDER BY seq",
                (s["section_id"],),
            )
        ]
        assert tiles(TEN_K, s["start_offset"], s["end_offset"], parts)
    label = corpus.execute(
        "SELECT f.label FROM passage_fts f JOIN passage p ON p.passage_id = f.rowid "
        "JOIN section s ON s.section_id = p.section_id WHERE s.label = '10-K Item 1A'"
    ).fetchone()[0]
    assert label == "10-K Item 1A Risk Factors"


def test_ensure_passages_backfills_only_missing(clock):
    corpus, doc_id = _corpus_with_10k()
    resplit(corpus, doc_id, clock.now())
    corpus.execute("BEGIN")
    corpus.execute("DELETE FROM passage_fts")
    corpus.execute("DELETE FROM passage")
    corpus.execute("COMMIT")
    first = ensure_passages(corpus)
    assert first["documents"] == 1 and first["passages"] > 0
    assert ensure_passages(corpus) == {"documents": 0, "passages": 0}


def test_write_passages_skips_documents_without_sections():
    corpus, doc_id = _corpus_with_10k()
    assert write_passages(corpus, doc_id) == 0
    assert ensure_passages(corpus) == {"documents": 0, "passages": 0}
