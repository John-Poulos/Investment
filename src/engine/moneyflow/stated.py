"""Stated capex actuals: "CapEx was $44.9 billion in the second quarter" (D-M02-29 (2)).

Past-tense capex sentences in earnings releases (grade A) and management turns of call
documents (B; A when a release states the same figure for the same period). They are
never guidance: they reconcile each XBRL recipe and, when the recipe is approximate,
partial or off by more than 1%, they are the actual shown (D-M02-32).

A sentence counts when it names capex (not another party's), has a past-tense verb
after the capex words (was / were / totaled / amounted to / came in at / reached),
carries no forward cue, and states one money figure (point or approximate; ranges and
bounds are not actuals). Its period: a stated quarter or fiscal year (spoken ones
resolved backwards against the document's own quarter — "the second quarter" on a
Q3 call is this year's Q2); a release sentence with no period word takes the release's
reported quarter, labelled as such. Year-to-date and half-year figures are skipped.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from engine.calls.transcripts import fiscal_quarter
from engine.guidance.calls import anchor_of, call_documents, management_turns
from engine.guidance.ledger import earnings_releases
from engine.guidance.parse import (
    _BOILERPLATE,
    _CLAUSE,
    _CUE,
    CALL_CUE,
    CAPEX_WORDS,
    MAX_SENTENCE,
    _lines,
    _sentences,
    find_periods,
    find_values,
    third_party,
)
from engine.guidance.sources import origin_of

PARSER_VERSION = "stated-1"
_PAST = re.compile(
    r"\b(?:was|were|totaled|totalled|amounted to|came in at|reached|of)\b", re.IGNORECASE
)
_FORWARD = re.compile(
    r"\b(?:will|would|plan\w*|intend\w*|outlook|guidance|going to|continue to|next)\b",
    re.IGNORECASE,
)
_PARTIAL = re.compile(
    r"\b(?:year[- ]to[- ]date|first half|second half|first (?:six|nine) months|"
    r"(?:six|nine|twelve) months|trailing|cumulative|since)\b",
    re.IGNORECASE,
)
_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_PAST_Q = re.compile(
    r"\b(?:(?:the|this)\s+(?P<this>quarter)\b|(?:the\s+)?(?P<q>first|second|third|fourth)"
    r"[- ]quarter\b|\bQ(?P<qn>[1-4])\b(?!\s*(?:FY|fiscal)?\s*'?\d))",
    re.IGNORECASE,
)
_PAST_Y = re.compile(
    r"\b(?:the|this)\s+(?:full\s+|fiscal\s+)?year\b|\bfull[- ]year\b|\bfor the year\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Stated:
    period: str
    period_how: str  # stated | release quarter
    kind: str  # point | approx
    value: Decimal
    clause: str | None
    quote_start: int
    quote_end: int


def _past_period(sent: str, anchor: tuple[int, int] | None) -> str | None:
    """A period already over at the document's quarter, or None."""
    explicit = [
        p for p in find_periods(sent, bare_years=False) if not p.label.endswith("remaining")
    ]
    if explicit:
        label = explicit[0].label
        m = re.fullmatch(r"FY(\d{4})(?: Q([1-4]))?", label)
        if anchor and m:
            fy, q = int(m.group(1)), m.group(2)
            if (fy, int(q)) > anchor if q else fy > anchor[0]:
                return None  # a future period: not an actual
        return label
    if anchor is None:
        return None
    fy, aq = anchor
    m = _PAST_Q.search(sent)
    if m:
        if m["this"]:
            return f"FY{fy} Q{aq}"
        t = _ORD[m["q"].lower()] if m["q"] else int(m["qn"])
        return f"FY{fy if t <= aq else fy - 1} Q{t}"
    if _PAST_Y.search(sent) and aq == 4:
        return f"FY{fy}"
    return None


def parse_stated(
    text: str,
    spans: list[tuple[int, int]],
    anchor: tuple[int, int] | None,
    *,
    release: bool,
) -> list[Stated]:
    """Stated capex actuals in the given spans (whole release, or management turns)."""
    out: list[Stated] = []
    for a, b in spans:
        for la, lb in _lines(text):
            if lb <= a or la >= b:
                continue
            for s, e in _sentences(text, max(la, a), min(lb, b)):
                sent = text[s:e]
                if len(sent) > MAX_SENTENCE or _BOILERPLATE.search(sent) or "\t" in sent:
                    continue
                cap = CAPEX_WORDS.search(sent)
                if not cap or third_party(sent, cap):
                    continue
                if _CUE.search(sent) or CALL_CUE.search(sent) or _FORWARD.search(sent):
                    continue
                if _PARTIAL.search(sent):
                    continue
                verb = _PAST.search(sent, cap.end())
                values = [v for v in find_values(sent) if v.start > cap.end() and v.unit == "USD"]
                if verb is None or not values or values[0].start < verb.start():
                    continue
                v = values[0]
                if v.kind not in ("point", "approx") or v.bound or not v.scaled or v.low <= 0:
                    continue
                period = _past_period(sent, anchor)
                how = "stated"
                if period is None and release and anchor is not None:
                    period, how = f"FY{anchor[0]} Q{anchor[1]}", "release quarter"
                if period is None:
                    continue
                m = _CLAUSE.search(sent, cap.start(), min(len(sent), v.end + 120))
                clause = " ".join(m.group(0).split()) if m else None
                out.append(Stated(period, how, v.kind, v.low, clause, s, e))
    return out


def _store(
    engine: sqlite3.Connection,
    cik: str,
    accession: str,
    filename: str,
    stated_on: str,
    text: str,
    found: list[Stated],
) -> int:
    origin = origin_of(accession)
    grade = "B" if origin == "call" else "A"
    engine.execute(
        "DELETE FROM capex_stated WHERE accession = ? AND filename = ?", (accession, filename)
    )
    for f in found:
        engine.execute(
            "INSERT OR IGNORE INTO capex_stated (cik, accession, filename, origin, grade, "
            "period, period_how, kind, value, clause, stated_on, quote, quote_start, quote_end, "
            "parser_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cik,
                accession,
                filename,
                origin,
                grade,
                f.period,
                f.period_how,
                f.kind,
                str(f.value),
                f.clause,
                stated_on,
                text[f.quote_start : f.quote_end],
                f.quote_start,
                f.quote_end,
                PARSER_VERSION,
            ),
        )
    return len(found)


def _upgrade(engine: sqlite3.Connection) -> None:
    """A call figure the same company's release also states (within 0.5%) is grade A."""
    engine.execute(
        "UPDATE capex_stated SET grade = 'A' WHERE origin = 'call' AND EXISTS ("
        "SELECT 1 FROM capex_stated r WHERE r.cik = capex_stated.cik AND r.origin = 'release' "
        "AND r.period = capex_stated.period "
        "AND abs(r.value - capex_stated.value) <= 0.005 * r.value)"
    )


def scan_all(engine: sqlite3.Connection, corpus: sqlite3.Connection, cik: str | None = None) -> int:
    """Re-read every stored release and call document → stated actuals stored."""
    n = 0
    fyes = {r[0]: r[1] for r in engine.execute("SELECT cik, fiscal_year_end FROM entity")}
    engine.execute("BEGIN")
    try:
        for rel in earnings_releases(engine, corpus):
            if cik and rel.cik != cik:
                continue
            doc = corpus.execute(
                "SELECT text FROM document WHERE doc_id = ?", (rel.doc_id,)
            ).fetchone()
            if doc is None:
                continue
            anchor = fiscal_quarter(date.fromisoformat(rel.filed[:10]), fyes.get(rel.cik))
            found = parse_stated(doc[0], [(0, len(doc[0]))], anchor, release=True)
            n += _store(engine, rel.cik, rel.accession, rel.filename, rel.filed, doc[0], found)
        for cd in call_documents(engine, cik):
            if cd.stated_on is None:
                continue
            doc = corpus.execute(
                "SELECT doc_id, text FROM document WHERE accession = ? AND filename = ?",
                (cd.accession, cd.filename),
            ).fetchone()
            if doc is None:
                continue
            turns = management_turns(corpus, doc["doc_id"], doc["text"])
            found = parse_stated(doc["text"], turns, anchor_of(cd.quarter), release=False)
            n += _store(engine, cd.cik, cd.accession, cd.filename, cd.stated_on, doc["text"], found)
        _upgrade(engine)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return n


@dataclass(frozen=True)
class StatedRow:
    period: str
    value: float
    kind: str
    grade: str
    origin: str
    accession: str
    filename: str
    quote: str
    quote_start: int
    clause: str | None
    stated_on: str
    period_how: str


def stated_for(engine: sqlite3.Connection, cik: str) -> dict[str, StatedRow]:
    """The best stated figure per period: release before call, then the latest."""
    best: dict[str, StatedRow] = {}
    rows = engine.execute(
        "SELECT * FROM capex_stated WHERE cik = ? ORDER BY origin != 'release', grade, "
        "period_how != 'stated', stated_on DESC",
        (cik,),
    )
    for r in rows:
        best.setdefault(
            r["period"],
            StatedRow(
                r["period"],
                float(r["value"]),
                r["kind"],
                r["grade"],
                r["origin"],
                r["accession"],
                r["filename"],
                r["quote"],
                r["quote_start"],
                r["clause"],
                r["stated_on"],
                r["period_how"],
            ),
        )
    return best
