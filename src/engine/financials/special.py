"""Recurring "one-time" charges — `special_items` (M04 Part 6; outline Red Flag 3; D-M04-19,
-60, -93, -94; S2.11).

- Per fiscal year of the last 4 (D-M04-94, owner 2026-10-13): a year **counts** only when it
  has an amount — a non-zero restructuring, asset-impairment, goodwill-impairment or
  inventory write-down tag, or a "non-recurring" / "one-time" sentence in that year's stored
  annual report that states a dollar amount for that year (no other year named; the quote is
  stored). Wording without an amount is shown as context and never counted. A year whose
  report text is not stored counts on its tags only, and says so.
- **Warning** when ≥ 3† of the 4 years count AND the cumulative counted charges are ≥ 5%† of
  the cumulative operating income over the same years (starting values). A year's counted
  charge is its tagged total, else its largest stated amount (a tag and a sentence about the
  same charge are not added twice). When cumulative operating income is ≤ 0 (or a year lacks
  it), the size is not measured: the warning then needs ≥ 3 of 4 years with tagged charges
  and reads "operating income ≤ 0: size not measured"; otherwise the state is
  `not_meaningful`.
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
from engine.financials.estimates import PER_SHARE, YEAR, annual_reports, report_fy
from engine.financials.text import clean, doc_scale, numbers, sentences
from engine.sec.identity import normalize_cik

YEARS = 4
WARN_YEARS = 3  # starting value (D-M04-19)
SIZE_MIN = 0.05  # cumulative counted charges ÷ cumulative operating income (D-M04-94, †)
CONTEXT_MAX = 5  # wording-only sentences kept per year (context)
AMOUNT_MAX = 10  # sentences with an amount kept per year
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

# (phrase, quote, accession, stated $ amount for the year, or None = context only)
Hit = tuple[str, str, str, float | None]


@dataclass
class YearItems:
    end: str
    label: str
    tags: list[tuple[str, float, str]] = field(default_factory=list)  # (what, $, accession)
    text: list[Hit] = field(default_factory=list)
    text_state: str = "not stored"  # read | not stored

    @property
    def has(self) -> bool:
        return qualifies(self)

    @property
    def stated(self) -> list[Hit]:
        return [t for t in self.text if t[3] is not None]

    @property
    def charge(self) -> float:
        """The year's counted charge: its tagged total, else its largest stated amount."""
        if self.tags:
            return sum(abs(v) for _, v, _ in self.tags)
        return max((abs(t[3] or 0.0) for t in self.stated), default=0.0)

    @property
    def source(self) -> str:
        """Where the year's count comes from (log and signal method)."""
        if self.tags:
            return "tag " + ", ".join(f"{w} {v / 1e6:,.0f}M" for w, v, _ in self.tags)
        if self.stated:
            return f"text “{self.stated[0][0]}” {self.charge / 1e6:,.0f}M (quote stored)"
        if self.text:
            return "wording only (context, not counted)"
        return "none" + ("" if self.text_state == "read" else " (text not stored)")


def qualifies(y: YearItems) -> bool:
    """Whether a fiscal year counts toward `special_items` (D-M04-94, refines D-M04-19, -93):
    a non-zero tagged charge, or a "non-recurring" / "one-time" sentence stating a dollar
    amount for that year. Wording without an amount never counts."""
    return bool(y.tags or y.stated)


def stated_amount(sentence: str, year: str | None, scale: float) -> float | None:
    """The dollar amount a wording sentence states for fiscal `year` ("2024"): the $ amount
    nearest the wording (per-share figures skipped); None when the sentence states no amount
    or names only other years (D-M04-94)."""
    years = set(YEAR.findall(sentence))
    if years and year not in years:
        return None
    m = WORDING.search(sentence)
    at = m.start() if m else 0
    best: tuple[int, float] | None = None
    for n in numbers(sentence, 0, len(sentence), scale):
        if "$" not in n.raw and not re.search(r"million|billion|thousand", n.raw, re.I):
            continue
        if PER_SHARE.match(sentence[n.end : n.end + 20]):
            continue
        d = abs(n.start - at)
        if best is None or d < best[0]:
            best = (d, n.value)
    return best[1] if best else None


@dataclass
class Special:
    state: str  # warn | none | not_meaningful | short_history | missing
    years: list[YearItems]
    count: int
    ratio: float | None
    ratio_why: str
    non_gaap: str = ""  # quoted sentence
    non_gaap_ref: str = ""
    why: str = ""
    tagged_years: int = 0
    size_measured: bool = True


def _text_years(engine, corpus, cik: str) -> dict[str, tuple[str, list[Hit]]]:
    """fiscal label → (accession, wording hits) for stored annual reports: sentences that
    state an amount for the year first, then wording-only context sentences."""
    from engine.search.query import search

    out: dict[str, tuple[str, list[Hit]]] = {}
    if corpus is None:
        return out
    for a in annual_reports(engine, corpus, cik, n=YEARS):
        label, _ = report_fy(engine, cik, a)
        if label is None:
            continue
        stated: list[Hit] = []
        context: list[Hit] = []
        seen = set()
        for h in search(corpus, TEXT_QUERY, ciks=[cik], accessions=[a.accession], limit=50):
            text = corpus.execute(
                "SELECT text FROM document WHERE doc_id = ?", (h.doc_id,)
            ).fetchone()[0]
            scale = doc_scale(text)
            for s, e in sentences(text, h.start, h.end):
                m = WORDING.search(text, s, e)
                if m is None or (h.doc_id, s) in seen:
                    continue
                seen.add((h.doc_id, s))
                sent = clean(text[s:e])
                amt = stated_amount(sent, label[2:], scale)
                hit = (m.group(0).lower(), sent, a.accession, amt)
                if amt is not None and len(stated) < AMOUNT_MAX:
                    stated.append(hit)
                elif amt is None and len(context) < CONTEXT_MAX:
                    context.append(hit)
        out[label] = (a.accession, stated + context)
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


def state_of(n_years: int, count: int, tagged: int, ratio: float | None, measured: bool) -> str:
    """D-M04-94: warn = ≥ 3† of 4 years counting and cumulative counted charges ≥ 5%† of
    cumulative operating income; size not measured (operating income ≤ 0 or missing for a
    year) → warn on ≥ 3 tagged years, else not meaningful."""
    if n_years < YEARS:
        return "short_history"
    if not measured:
        return "warn" if tagged >= WARN_YEARS else "not_meaningful"
    return "warn" if count >= WARN_YEARS and ratio is not None and ratio >= SIZE_MIN else "none"


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
    tagged = sum(1 for y in years if y.tags)
    total = sum(y.charge for y in years if y.has)
    ops = [fx.at("operating_income", y.end) for y in years]
    measured = True
    if any(o is None for o in ops):
        gone = ", ".join(y.label for y, o in zip(years, ops, strict=True) if o is None)
        ratio, why, measured = None, f"operating income missing ({gone}): size not measured", False
    elif sum(o.value for o in ops) <= 0:
        ratio, why, measured = None, "operating income ≤ 0: size not measured", False
    else:
        ratio, why = total / sum(o.value for o in ops), ""
    state = state_of(len(years), count, tagged, ratio, measured)
    q, ref = non_gaap_quote(engine, corpus, norm)
    return Special(state, years, count, ratio, why, q, ref, tagged_years=tagged,
                   size_measured=measured)  # fmt: skip


def store(engine: sqlite3.Connection, cik: str, sp: Special, now_iso: str) -> int:
    """Replace the company's `special_item` rows (text rows carry the stated amount, NULL for
    context). Caller owns the transaction."""
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
        for phrase, quote, acc, amt in y.text:
            cur = engine.execute(
                "INSERT OR IGNORE INTO special_item (cik, period_end, fiscal_label, source, what, "
                "accession, amount, quote, computed_at) VALUES (?, ?, ?, 'text', ?, ?, ?, ?, ?)",
                (cik, y.end, y.label, phrase, acc, amt, quote, now_iso),
            )
            n += cur.rowcount
    return n
