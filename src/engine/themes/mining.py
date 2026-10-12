"""Corpus phrase mining (D-M02-8): 2–3-word phrases per company and period over the
stored corpus, so rising phrases can be proposed for the EFTS tests (D-M02-49).

Unit = distinct companies using a phrase in a period (a phrase one company repeats is
one use). Text = stored passages, minus analyst/operator turns of call transcripts and
forward-looking-statement boilerplate (D-SRCH-20). Phrases break at punctuation, line
and tab boundaries and numbers; a phrase may not start or end with a stop word. Counting
runs one company at a time; when the table grows past `MAX_KEYS`, phrases seen by a
single company are dropped (lossy counting) and the result says so.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

MINER_VERSION = "mine-1"
MAX_KEYS = 3_000_000
SKIP_SECTIONS = ("call analyst", "call operator", "call other")
BOILERPLATE = re.compile(
    r"forward-looking statements?|safe harbor|private securities litigation reform act", re.I
)
_BREAK = re.compile(r"[.;:!?,()\[\]{}\"“”‘’'|/\n\t•·—–]+|\s-\s")
_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

_STOP_WORDS = """
a about above after again against all also an and any are as at be because been before
being below between both but by can could did do does doing down during each either
few for from further had has have having he her here hers him his how i if in into is
it its itself may might more most must my no nor not of off on once only or other our
ours out over own per same shall she should so some such than that the their them then
there these they this those through to too under until up upon us very via was we were
what when where whether which while who whom why will with within without would you your
year years quarter quarters month months fiscal company companies inc corp corporation
llc ltd first second third fourth new including included include includes certain
million billion thousand percent approximately based related respectively continue
continued result results primarily significant total
"""
STOP = frozenset(_STOP_WORDS.split())


def phrases_in(text: str, sizes: tuple[int, ...] = (2, 3)) -> set[str]:
    """Distinct 2–3-word phrases of one text, lowercased."""
    out: set[str] = set()
    for chunk in _BREAK.split(text.lower()):
        run: list[str] = []
        for tok in _TOKEN.findall(chunk) + ["0"]:  # "0" flushes the last run
            if tok[0].isdigit() or len(tok) < 2:
                _emit(run, sizes, out)
                run = []
            else:
                run.append(tok)
    return out


def _emit(run: list[str], sizes: tuple[int, ...], out: set[str]) -> None:
    for n in sizes:
        for i in range(len(run) - n + 1):
            gram = run[i : i + n]
            if gram[0] in STOP or gram[-1] in STOP:
                continue
            out.add(" ".join(gram))


@dataclass(frozen=True)
class Doc:
    doc_id: int
    cik: str
    accession: str
    doc_type: str | None
    dated: str  # filing date (SEC) or the release date of a call (AV-/IR-)


def corpus_docs(engine: sqlite3.Connection, corpus: sqlite3.Connection) -> list[Doc]:
    """Every stored document with a date: SEC filings by filing date; call transcripts and
    IR documents by their release date (else when they were added)."""
    filed = dict(engine.execute("SELECT accession, filed FROM filing"))
    calls = {(r[0], r[1]): r[2] for r in engine.execute(
        "SELECT accession, filename, coalesce(stated_on, substr(added_at, 1, 10)) "
        "FROM call_document")}  # fmt: skip
    out = []
    for r in corpus.execute("SELECT doc_id, cik, accession, filename, doc_type FROM document"):
        dated = filed.get(r["accession"]) or calls.get((r["accession"], r["filename"]))
        if dated:
            out.append(Doc(r["doc_id"], r["cik"], r["accession"], r["doc_type"], dated[:10]))
    return out


def passages(corpus: sqlite3.Connection, doc_id: int) -> Iterator[tuple[str, str]]:
    """(section label, passage text) of one document, skipping non-management call turns
    and boilerplate passages."""
    text = corpus.execute("SELECT text FROM document WHERE doc_id = ?", (doc_id,)).fetchone()
    if text is None:
        return
    body = text[0]
    for r in corpus.execute(
        "SELECT s.label, p.start_offset, p.end_offset FROM passage p "
        "JOIN section s ON s.section_id = p.section_id WHERE p.doc_id = ? ORDER BY p.start_offset",
        (doc_id,),
    ):
        if r[0] in SKIP_SECTIONS:
            continue
        piece = body[r[1] : r[2]]
        if BOILERPLATE.search(piece):
            continue
        yield r[0], piece


@dataclass
class PeriodCounts:
    start: str
    end: str
    companies: Counter[str] = field(default_factory=Counter)  # phrase → distinct companies
    n_companies: int = 0
    n_docs: int = 0
    pruned: int = 0  # times single-company phrases were dropped
    by_company: dict[str, set[str]] | None = None  # kept only when asked (small corpora)


def count_period(
    corpus: sqlite3.Connection,
    docs: Iterable[Doc],
    start: str,
    end: str,
    *,
    keep_sets_for: set[str] | None = None,
) -> PeriodCounts:
    """Distinct companies per phrase over documents dated start..end (inclusive)."""
    pc = PeriodCounts(start, end, by_company={} if keep_sets_for is not None else None)
    by_cik: dict[str, list[int]] = {}
    for d in docs:
        if start <= d.dated <= end:
            by_cik.setdefault(d.cik, []).append(d.doc_id)
            pc.n_docs += 1
    for cik, ids in sorted(by_cik.items()):
        grams: set[str] = set()
        for doc_id in ids:
            for _, piece in passages(corpus, doc_id):
                grams |= phrases_in(piece)
        pc.companies.update(grams)
        if pc.by_company is not None and keep_sets_for is not None and cik in keep_sets_for:
            pc.by_company[cik] = grams
        pc.n_companies += 1
        if len(pc.companies) > MAX_KEYS:
            for k in [k for k, v in pc.companies.items() if v <= 1]:
                del pc.companies[k]
            pc.pruned += 1
    return pc
