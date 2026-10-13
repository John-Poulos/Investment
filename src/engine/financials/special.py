"""Recurring "one-time" charges — `special_items` (M04 Part 6; outline Red Flag 3; D-M04-19,
-60, -93; S2.11).

- Per fiscal year of the last 4: a restructuring, asset-impairment, goodwill-impairment or
  inventory write-down tag with a non-zero value, or "non-recurring" / "one-time" wording
  in that year's stored annual report (FTS5; the sentence is kept as the quote). A year
  whose report text is not stored counts on its tags only, and says so.
- **Warning** when items occur in ≥ 3† of the 4 years (all stages). The cumulative tagged
  amount is shown against cumulative operating income over the same years (not meaningful
  when that sum is ≤ 0 or a year lacks operating income).
- The company-stated non-GAAP vs GAAP gap is **quoted** from its latest stored earnings
  release, never computed (D-M04-19, D-M02-29).
- No D13 weight until ≥ 20 owner labels (D-M04-60). Part 7b's cleared R12 causes (one-off,
  accounting, segment, credits) will add to the recurrence count (D-M04-44).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from engine.financials.capex import fiscal_label
from engine.financials.estimates import annual_reports, report_fy
from engine.financials.text import clean, sentences
from engine.sec.identity import normalize_cik

YEARS = 4
WARN_YEARS = 3  # starting value (D-M04-19)
TAGS = (
    ("restructuring", "restructuring charges"),
    ("impairment", "asset impairment"),
    ("goodwill_impairment", "goodwill impairment"),
    ("inventory_writedown", "inventory write-down"),
)
TEXT_QUERY = '"non-recurring" OR nonrecurring OR "one-time"'
WORDING = re.compile(r"non-?recurring|one-time", re.I)  # "at any one time" is not wording
NON_GAAP_QUERY = '"non-GAAP" OR "non GAAP"'
NON_GAAP = re.compile(r"non-?\s?GAAP", re.I)


@dataclass
class YearItems:
    end: str
    label: str
    tags: list[tuple[str, float, str]] = field(default_factory=list)  # (what, $, accession)
    text: list[tuple[str, str, str]] = field(default_factory=list)  # (phrase, quote, accession)
    text_state: str = "not stored"  # read | not stored

    @property
    def has(self) -> bool:
        return qualifies(self)


def qualifies(y: YearItems) -> bool:
    """Whether a fiscal year counts toward `special_items` (D-M04-19, -93): a tagged charge or
    the wording. The one place to change if wording-only years stop counting (open owner
    question, Part 6 live check 1)."""
    return bool(y.tags or y.text)


@dataclass
class Special:
    state: str  # warn | none | short_history | missing
    years: list[YearItems]
    count: int
    ratio: float | None
    ratio_why: str
    non_gaap: str = ""  # quoted sentence
    non_gaap_ref: str = ""
    why: str = ""


def _text_years(engine, corpus, cik: str) -> dict[str, tuple[str, list[tuple[str, str, str]]]]:
    """fiscal label → (accession, wording hits) for stored annual reports."""
    from engine.search.query import search

    out: dict[str, tuple[str, list[tuple[str, str, str]]]] = {}
    if corpus is None:
        return out
    for a in annual_reports(engine, corpus, cik, n=YEARS):
        label, _ = report_fy(engine, cik, a)
        if label is None:
            continue
        found: list[tuple[str, str, str]] = []
        seen = set()
        for h in search(corpus, TEXT_QUERY, ciks=[cik], accessions=[a.accession], limit=50):
            text = corpus.execute(
                "SELECT text FROM document WHERE doc_id = ?", (h.doc_id,)
            ).fetchone()[0]
            for s, e in sentences(text, h.start, h.end):
                m = WORDING.search(text, s, e)
                if m is None or s in seen:
                    continue
                seen.add(s)
                found.append((m.group(0).lower(), clean(text[s:e]), a.accession))
                break
            if len(found) >= 5:
                break
        out[label] = (a.accession, found)
    return out


def non_gaap_quote(engine, corpus, cik: str) -> tuple[str, str]:
    """The company's own non-GAAP reconciliation sentence from its newest stored earnings
    release (EX-99.1), quoted as stated (never computed)."""
    from engine.search.query import search

    if corpus is None:
        return "", ""
    hits = search(corpus, NON_GAAP_QUERY, ciks=[cik], doc_types=["EX-99.1"], limit=100)
    by_acc = sorted({h.accession for h in hits}, reverse=True)
    for acc in by_acc:
        for h in sorted((h for h in hits if h.accession == acc), key=lambda h: h.start):
            text = corpus.execute(
                "SELECT text FROM document WHERE doc_id = ?", (h.doc_id,)
            ).fetchone()[0]
            for s, e in sentences(text, h.start, h.end):
                sent = text[s:e]
                if (
                    NON_GAAP.search(sent)
                    and re.search(r"\bGAAP\b", NON_GAAP.sub("", sent))
                    and re.search(r"\$\s?\d", sent)
                ):
                    return clean(sent)[:600], f"{acc}/{h.filename}"
    return "", ""


def compute(engine: sqlite3.Connection, corpus: sqlite3.Connection | None, cik: str) -> Special:
    from engine.financials.quality import Facts

    norm = normalize_cik(cik) or cik
    fx = Facts(engine, norm)
    ends = fx.ends()[-YEARS:]
    if not ends:
        return Special("missing", [], 0, None, "", why="no fiscal year stored")
    texts = _text_years(engine, corpus, norm)
    years = []
    for e in ends:
        y = YearItems(e, fiscal_label(e))
        for name, what in TAGS:
            v = fx.at(name, e)
            if v is not None and v.value != 0:
                y.tags.append((what, v.value, v.accession))
        if y.label in texts:
            y.text_state = "read"
            y.text = texts[y.label][1]
        years.append(y)
    count = sum(1 for y in years if y.has)
    total = sum(v for y in years for _, v, _ in y.tags)
    ops = [fx.at("operating_income", y.end) for y in years]
    if any(o is None for o in ops):
        ratio, why = None, "operating income missing for a year"
    elif sum(o.value for o in ops) <= 0:
        ratio, why = None, "cumulative operating income ≤ 0 (not meaningful)"
    else:
        ratio, why = total / sum(o.value for o in ops), ""
    state = "short_history" if len(years) < YEARS else "warn" if count >= WARN_YEARS else "none"
    q, ref = non_gaap_quote(engine, corpus, norm)
    return Special(state, years, count, ratio, why, q, ref)


def store(engine: sqlite3.Connection, cik: str, sp: Special, now_iso: str) -> int:
    """Replace the company's `special_item` rows. Caller owns the transaction."""
    engine.execute("DELETE FROM special_item WHERE cik = ?", (cik,))
    n = 0
    for y in sp.years:
        for what, v, acc in y.tags:
            engine.execute(
                "INSERT OR IGNORE INTO special_item (cik, period_end, fiscal_label, source, what, "
                "accession, amount, quote, computed_at) VALUES (?, ?, ?, 'tag', ?, ?, ?, NULL, ?)",
                (cik, y.end, y.label, what, acc, v, now_iso),
            )
            n += 1
        for phrase, quote, acc in y.text:
            engine.execute(
                "INSERT OR IGNORE INTO special_item (cik, period_end, fiscal_label, source, what, "
                "accession, amount, quote, computed_at) VALUES (?, ?, ?, 'text', ?, ?, NULL, ?, ?)",
                (cik, y.end, y.label, phrase, acc, quote, now_iso),
            )
            n += 1
    return n
