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
_PCT = re.compile(r"(?<![\d.])(\d{1,2}(?:\.\d+)?)\s?%")


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


def find_l1(text: str, matcher: Matcher, self_keys: set[str]) -> list[Found]:
    out = []
    for s, e in _sentences_in(text):
        sent = text[s:e]
        w = _SUPPLIER.search(sent)
        if not w or _COMPETE.search(sent):
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
        if _COMPETE.search(sent):
            continue
        w = _REVENUE.search(sent)
        if not w:
            continue
        for m in _others(matcher, text, s, e, self_keys):
            if m.company.key != customer.key:
                continue
            pct = _PCT.search(text, m.end, e) or _PCT.search(sent)
            share = Decimal(pct.group(1)) if pct else None
            out.append(
                Found(
                    "L2",
                    m.company,
                    m.name,
                    "a_to_b",
                    share,
                    s,
                    e,
                    f"revenue wording: {w.group(0).lower()}",
                )
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
