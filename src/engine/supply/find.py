"""Passages tying two companies, by rung (D-M02-7). Code finds; Gemini labels; owner confirms.

- L1 — a customer's own 10-K/10-Q names a supplier: a sentence with supplier wording
  ("supplier", "rely on", "manufactured by", "foundry", "sole source", "purchase from")
  and a known company other than the filer → B supplies A.
- L2 — a supplier names its customer: a sentence with the customer's name and revenue
  wording ("accounted for", "represented", "sales to", "revenue from", "% of revenue")
  → A supplies B; the revenue share is kept when stated.
- L3 — a contract (8-K Item 1.01 exhibit) naming the filer's counterparty with contract
  wording (supply, purchase, capacity, wafer, prepayment) in its opening part → direction
  not stated until Gemini or the owner reads it.
Sentences that also say "compete" are skipped (competitor lists name the same companies).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from engine.guidance.parse import MAX_SENTENCE, _lines, _sentences
from engine.supply.aliases import Company, Matcher

L3_HEAD = 30_000  # parties and recitals sit at the start of a contract
_SUPPLIER = re.compile(
    r"\b(?:suppliers?|supplied by|sole[- ]sourced?|single[- ]sourced?|rel(?:y|ies|ied) on|"
    r"depend(?:s|ed)? on|manufactured by|manufacturing partners?|foundr(?:y|ies)|"
    r"contract manufacturers?|purchases? (?:\w+ )?from|procure\w* from|sourced? from|"
    r"assembly and test|vendors?)\b",
    re.IGNORECASE,
)
_REVENUE = re.compile(
    r"\b(?:accounted for|represented|sales to|revenues? from|net sales to|"
    r"of (?:our )?(?:total |consolidated )?(?:net )?(?:revenues?|sales)|largest customers?|"
    r"significant customers?|major customers?)\b",
    re.IGNORECASE,
)
_CONTRACT = re.compile(
    r"\b(?:supply|purchase|capacity|wafers?|manufactur\w*|prepay\w*|take-or-pay|"
    r"long-term agreement|master services)\b",
    re.IGNORECASE,
)
_COMPETE = re.compile(r"\bcompet\w*\b", re.IGNORECASE)
# live check 2 (D-M02-39): share sales to a company are investments, not supply
_SECURITIES = re.compile(
    r"\b(?:shares|common stock|preferred stock|warrants?|convertible|private placement|"
    r"securities purchase|equity investment|American Depositary)\b",
    re.IGNORECASE,
)
# "NVIDIA NVLink", "NVIDIA GPUs": a product named after the company, not the company
_PRODUCT_AFTER = re.compile(
    r"\s+(?!(?:Corporation|Corp|Inc|Co|Ltd|Limited|Technology|Technologies|Holdings|"
    r"Electronics|Industry)\b)[A-Z][A-Za-z0-9-]+"
)
CONTEXT_CHARS = 1500  # how far back a competition heading or sentence is looked for
_PCT = re.compile(r"(?<![\d.])(\d{1,2}(?:\.\d+)?)\s?%(?!\s+or\s+(?:more|greater|less))")
# "suppliers of Arm-based CPUs ... such as Amazon": a market list (NVIDIA's competition
# section), not the filer's own supply chain (live check 1)
_GENERIC = re.compile(r"(?:suppliers?|vendors?|providers?)(?:\s+and\s+\w+)?\s+of\b", re.IGNORECASE)
# a filer's figure about what it buys: "purchases from ... Microsoft accounted for 13%"
_BUYS = re.compile(r"\b(?:purchases?|purchased|suppliers?|vendors?)\b", re.IGNORECASE)
_RESPECTIVELY = re.compile(r"\brespectively\b", re.IGNORECASE)
_LISTED_BEFORE = re.compile(r"(?:,|\band|&)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Found:
    rung: str
    b: Company
    b_name: str
    direction: str | None  # a_to_b | b_to_a | None
    share_pct: Decimal | None
    start: int
    end: int
    how: str


def _sentences_in(text: str, a: int = 0, b: int | None = None):
    end = len(text) if b is None else b
    for la, lb in _lines(text):
        if lb <= a or la >= end:
            continue
        for s, e in _sentences(text, max(la, a), min(lb, end)):
            if e - s <= MAX_SENTENCE:
                yield s, e


def _others(matcher: Matcher, text: str, s: int, e: int, self_keys: set[str]):
    seen = set()
    for m in matcher.find(text, s, e):
        if m.company.key in self_keys or m.company.key in seen:
            continue
        seen.add(m.company.key)
        yield m


def _noise(text: str, s: int, e: int, matcher: Matcher) -> bool:
    """Share sales, and lists of three or more companies inside a competition passage."""
    sent = text[s:e]
    if _COMPETE.search(sent) or _SECURITIES.search(sent):
        return True
    if _BUYING_VERB.search(sent):
        return False
    names = len(matcher.find(text, s, e))
    # a market list under a competition heading (NVIDIA's own 10-K): nearby wording, or the
    # line that introduces the bullet list the sentence belongs to (live check 3)
    if names >= 3 and _COMPETE.search(text[max(0, s - CONTEXT_CHARS) : s]):
        return True
    intro = _list_intro(text, s)
    return bool(names >= 2 and intro is not None and _COMPETE.search(intro))


_BULLET_LINE = re.compile(r"^\s*[•▪◦●\-–]\s*")


def _list_intro(text: str, s: int, max_lines: int = 80) -> str | None:
    """The non-bullet line above the bullet list holding offset `s`, or None."""
    start = text.rfind("\n", 0, s) + 1
    if not _BULLET_LINE.match(text, start):
        return None
    for _ in range(max_lines):
        if start == 0:
            return None
        prev = text.rfind("\n", 0, start - 1) + 1
        line = text[prev : start - 1]
        if line.strip() and not _BULLET_LINE.match(line):
            return line
        start = prev
    return None


_BUYING_VERB = re.compile(
    r"\b(?:purchas\w*|rel(?:y|ies|ied) on|utiliz\w*|engag\w*|manufactured by|supplied by|"
    r"sourc\w*|procur\w*|buy\w*|bought)\b",
    re.IGNORECASE,
)


def _product(text: str, m) -> bool:
    return bool(_PRODUCT_AFTER.match(text, m.end))


def find_l1(text: str, matcher: Matcher, self_keys: set[str]) -> list[Found]:
    out = []
    for s, e in _sentences_in(text):
        sent = text[s:e]
        w = next((x for x in _SUPPLIER.finditer(sent) if not _GENERIC.match(sent, x.start())), None)
        if not w or _noise(text, s, e, matcher):
            continue
        for m in _others(matcher, text, s, e, self_keys):
            out.append(
                Found(
                    "L1",
                    m.company,
                    m.name,
                    "b_to_a",
                    None,
                    s,
                    e,
                    f"supplier wording: {w.group(0).lower()}",
                )
            )
    return out


def find_l2(text: str, matcher: Matcher, customer: Company, self_keys: set[str]) -> list[Found]:
    """Sentences in a supplier's filing that name `customer` with revenue wording."""
    out = []
    for s, e in _sentences_in(text):
        sent = text[s:e]
        if _noise(text, s, e, matcher):
            continue
        w = _REVENUE.search(sent)
        if not w:
            continue
        for m in _others(matcher, text, s, e, self_keys):
            if m.company.key != customer.key or _product(text, m):
                continue
            pct = _PCT.search(text, m.end, e)
            share = Decimal(pct.group(1)) if pct else None
            before = text[max(s, m.start - 8) : m.start]
            if _RESPECTIVELY.search(sent) and _LISTED_BEFORE.search(before):
                share = None  # "A, B, and Microsoft accounted for 25%, 21% and 13%, respectively"
            buys = _BUYS.search(sent)
            out.append(
                Found(
                    "L2",
                    m.company,
                    m.name,
                    "b_to_a" if buys else "a_to_b",
                    share,
                    s,
                    e,
                    f"purchase wording: {buys.group(0).lower()}"
                    if buys
                    else f"revenue wording: {w.group(0).lower()}",
                )
            )
            break
    return out


_CUSTOMER_LIST = re.compile(
    r"\b(?:customers?|end customers?|clients?|OEMs?)\b[^.;]{0,40}?"
    r"\b(?:include|including|such as|like)\b"
    r"|\b(?:sell|sells|sold|ship|ships|shipped|deliver\w*) (?:\w+ ){0,4}?to\b",
    re.IGNORECASE,
)


def find_bare(text: str, matcher: Matcher, customer: Company, self_keys: set[str]) -> list[Found]:
    """Option (c) trial (D-M02-38): any sentence naming `customer` with revenue, customer-list,
    selling or buying wording. Wider than L2's phrases, so its passages are marked "(c)"
    and measured in the precision set before the trial is extended."""
    out = []
    for s, e in _sentences_in(text):
        sent = text[s:e]
        if _noise(text, s, e, matcher):
            continue
        sells = _REVENUE.search(sent) or _CUSTOMER_LIST.search(sent)
        buys = _BUYS.search(sent) or next(
            (x for x in _SUPPLIER.finditer(sent) if not _GENERIC.match(sent, x.start())), None
        )
        if not (sells or buys):
            continue
        for m in _others(matcher, text, s, e, self_keys):
            if m.company.key != customer.key or _product(text, m):
                continue
            pct = _PCT.search(text, m.end, e) if sells else None
            direction = "a_to_b" if sells and not buys else "b_to_a" if buys and not sells else None
            w = (sells or buys).group(0).lower()
            share = Decimal(pct.group(1)) if pct else None
            out.append(
                Found("L2", m.company, m.name, direction, share, s, e, f"(c) bare name: {w}")
            )
            break
    return out


def find_l3(text: str, matcher: Matcher, self_keys: set[str]) -> list[Found]:
    out, seen = [], set()
    for s, e in _sentences_in(text, 0, min(len(text), L3_HEAD)):
        sent = text[s:e]
        w = _CONTRACT.search(sent)
        if not w:
            continue
        for m in _others(matcher, text, s, e, self_keys):
            if m.company.key in seen:
                continue  # one passage per counterparty per contract
            seen.add(m.company.key)
            out.append(
                Found(
                    "L3",
                    m.company,
                    m.name,
                    None,
                    None,
                    s,
                    e,
                    f"contract wording: {w.group(0).lower()}",
                )
            )
    return out


def self_keys(matcher: Matcher, cik: str | None) -> set[str]:
    return {c.key for c in matcher.companies if cik and c.cik == cik}
