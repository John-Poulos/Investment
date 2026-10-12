"""Corpus phrase mining (D-M02-8, D-M02-52): 2–3-word phrases that watchlist companies
newly use, compared with their own documents of the same kind a year earlier.

Each company's documents are split into the 12 months to the season date ("current") and
the 12 months before ("year ago"), by kind: 10-K, 10-Q, 20-F, earnings release (EX-99.1
of an Item 2.02 8-K) and call (management turns of a transcript or IR document). Only
kinds present in both periods are compared, so filing boilerplate cancels out. A phrase
is an adopter's when it appears in the current documents and not the year-ago ones;
rank = adopters − droppers. Text = narrative passages (10-K Items 1, 1A, 7, 7A; 10-Q MD&A
and risk factors; releases and calls whole) minus analyst/operator turns and
forward-looking-statement boilerplate (D-SRCH-20); phrases with an accounting, tax or
legal-process word are dropped and counted (mine-3, live check 1); phrases break at
punctuation, line and tab boundaries and numbers, and may not start or end with a stop word.
Hit documents of other filers have no twins and are not mined. The probe's corpus-wide counter
(`count_period`, D-M02-52 (1)) stays for comparison.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta

MINER_VERSION = "mine-4"
MAX_KEYS = 3_000_000
SKIP_SECTIONS = ("call analyst", "call operator", "call other")
BOILERPLATE = re.compile(
    r"forward-looking statements?|safe harbor|private securities litigation reform act|"
    r"cautionary (?:statement|note|language)|beliefs and opinions|references to past events",
    re.I,
)  # the last three: cautionary-statement wording seen in live check 3
# a three-word phrase may carry one of these inside ("internet of things"); any other stop
# word there makes it a clause fragment ("events are provided", live check 3)
MIDDLE_OK = frozenset({"of", "and", "for", "in", "on", "to", "by", "with", "at", "as", "from"})
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
january february march april may june july august september october november december
"""
STOP = frozenset(_STOP_WORDS.split())

# Narrative sections of 10-K/10-Q (D-M02-14): the business, risk factors and MD&A.
# Financial-statement notes, the cover and exhibits carry new accounting standards that
# every filer adopts at once (live check 1: "cross-border tax", "targeted improvements").
# Other documents (releases, calls, 20-F, unsplit filings) are read whole.
NARRATIVE = frozenset({
    "10-K Item 1", "10-K Item 1A", "10-K Item 7", "10-K Item 7A",
    "10-Q Part I Item 2", "10-Q Part I Item 3", "10-Q Part II Item 1A",
})  # fmt: skip
# Accounting, tax and legal-process words: a phrase containing one is the wording of a
# rule every filer adopts (ASUs, tax law, tariff authorities), not an investment theme.
# Macro wording (tariffs, tax law) belongs to M10. Dropped phrases are counted.
_ADMIN_WORDS = """
tax taxes taxable taxation deductible nondeductible nontaxable accounting asu asus gaap fasb
ifrs act acts bill statute amendment amendments retrospective prospective transition adoption
adopted adopt improvements disclosure disclosures reporting interim pursuant regulation
regulations tariff tariffs emergency powers grant grants internal-use impairment valuation
unrecognized allowance allowances lease leases goodwill amortization depreciation vesting
dividend dividends auditor audit pro forma consideration remeasurement hedge hedging
derivative derivatives fair receivable receivables payable payables accrued accruals
regulatory department departments agency agencies
"""
ADMIN = frozenset(_ADMIN_WORDS.split())


def admin_phrase(phrase: str) -> bool:
    return any(w in ADMIN for w in phrase.split())


def narrative(label: str) -> bool:
    if label.startswith(("10-K ", "10-Q ")):
        return label in NARRATIVE
    return label not in ("cover", "signatures") and label not in SKIP_SECTIONS


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
            if any(w in STOP and w not in MIDDLE_OK for w in gram[1:-1]):
                continue
            out.add(" ".join(gram))


@dataclass(frozen=True)
class Doc:
    doc_id: int
    cik: str
    accession: str
    doc_type: str | None
    dated: str  # filing date (SEC) or the release date of a call (AV-/IR-)
    kind: str | None = None  # 10-K, 10-Q, 20-F, release, call; None = not mined


def doc_kind(doc_type: str | None, form: str | None, items: str | None, call: bool) -> str | None:
    """The comparison kind of a stored document (amendments and contracts are not mined)."""
    if call:
        return "call"
    if doc_type in ("10-K", "10-Q", "20-F") and form == doc_type:
        return doc_type
    if (doc_type or "").startswith("EX-99.1") and form == "8-K" and "2.02" in (items or ""):
        return "release"
    return None


def corpus_docs(engine: sqlite3.Connection, corpus: sqlite3.Connection) -> list[Doc]:
    """Every stored document with a date: SEC filings by filing date; call transcripts and
    IR documents by their release date (else when they were added)."""
    filed = {r[0]: (r[1], r[2], r[3]) for r in engine.execute(
        "SELECT accession, filed, form, items FROM filing")}  # fmt: skip
    calls = {(r[0], r[1]): r[2] for r in engine.execute(
        "SELECT accession, filename, coalesce(stated_on, substr(added_at, 1, 10)) "
        "FROM call_document")}  # fmt: skip
    out = []
    for r in corpus.execute("SELECT doc_id, cik, accession, filename, doc_type FROM document"):
        call = calls.get((r["accession"], r["filename"]))
        f = filed.get(r["accession"])
        dated = (f[0] if f else None) or call
        if dated:
            kind = doc_kind(r["doc_type"], f[1] if f else None, f[2] if f else None,
                            call is not None)  # fmt: skip
            out.append(Doc(r["doc_id"], r["cik"], r["accession"], r["doc_type"], dated[:10],
                           kind))  # fmt: skip
    return out


def periods(season_date: date) -> tuple[tuple[str, str], tuple[str, str]]:
    """(current, year ago): the 12 months to the season date and the 12 months before."""
    cur = ((season_date - timedelta(days=364)).isoformat(), season_date.isoformat())
    ago_end = season_date - timedelta(days=365)
    return cur, ((ago_end - timedelta(days=364)).isoformat(), ago_end.isoformat())


@dataclass(frozen=True)
class Mined:
    phrase: str
    adopters: tuple[str, ...]  # CIKs newly using it
    droppers: int
    users: int  # compared companies using it in the current period

    @property
    def score(self) -> int:
        return len(self.adopters) - self.droppers


@dataclass
class MineResult:
    current: tuple[str, str]
    year_ago: tuple[str, str]
    compared: dict[str, tuple[str, ...]] = field(default_factory=dict)  # cik → shared kinds
    not_compared: dict[str, str] = field(default_factory=dict)  # cik → why
    candidates: list[Mined] = field(default_factory=list)
    above_floor: int = 0  # phrases with ≥ min adopters before the cap
    admin_dropped: int = 0  # accounting, tax or legal-process wording (ADMIN)


def _grams(corpus: sqlite3.Connection, docs: Iterable[Doc]) -> set[str]:
    out: set[str] = set()
    for d in docs:
        for _, piece in passages(corpus, d.doc_id):
            out |= phrases_in(piece)
    return out


def mine(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    ciks: Iterable[str],
    season_date: date,
    *,
    exclude: set[str] = frozenset(),
    min_adopters: int = 2,
    cap: int = 200,
) -> MineResult:
    """Phrases newly used by ≥ `min_adopters` of `ciks`, ranked; at most `cap`."""
    cur, ago = periods(season_date)
    res = MineResult(cur, ago)
    wanted = set(ciks)
    by_cik: dict[str, list[Doc]] = {}
    for d in corpus_docs(engine, corpus):
        if d.cik in wanted and d.kind:
            by_cik.setdefault(d.cik, []).append(d)
    adopters: dict[str, list[str]] = {}
    drops: Counter[str] = Counter()
    users: Counter[str] = Counter()
    for cik in sorted(wanted):
        docs = by_cik.get(cik, [])
        now_docs = [d for d in docs if cur[0] <= d.dated <= cur[1]]
        old_docs = [d for d in docs if ago[0] <= d.dated <= ago[1]]
        shared = sorted({d.kind for d in now_docs} & {d.kind for d in old_docs})  # type: ignore[misc]
        if not shared:
            res.not_compared[cik] = (
                "no stored documents" if not docs else
                f"no kind in both periods (current: {sorted({d.kind for d in now_docs})}, "
                f"year ago: {sorted({d.kind for d in old_docs})})"
            )  # fmt: skip
            continue
        res.compared[cik] = tuple(shared)  # type: ignore[arg-type]
        a = _grams(corpus, (d for d in now_docs if d.kind in shared))
        b = _grams(corpus, (d for d in old_docs if d.kind in shared))
        users.update(a)
        for g in a - b:
            adopters.setdefault(g, []).append(cik)
        drops.update(b - a)
    rows = [
        Mined(g, tuple(c), drops.get(g, 0), users[g])
        for g, c in adopters.items()
        if len(c) >= min_adopters and g not in exclude
    ]
    res.admin_dropped = sum(1 for m in rows if admin_phrase(m.phrase))
    rows = [m for m in rows if not admin_phrase(m.phrase)]
    res.above_floor = len(rows)
    # ties: two-word phrases first (a phrase inside a longer one is at least as common);
    # which of "bandwidth memory" / "high bandwidth memory" to keep is decided on EFTS
    # counts at proposal time (seasonal._covered), not on a handful of adopters here
    rows.sort(key=lambda m: (-m.score, -len(m.adopters), m.phrase.count(" "), m.phrase))
    res.candidates = rows[:cap]
    return res


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
        if not narrative(r[0]):
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
