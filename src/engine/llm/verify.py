"""Mechanical checks on LLM output (M00_SEARCH D21, grounded pipeline step 5).

- A quote must appear in the passage it cites, after normalizing whitespace,
  curly quotes and dashes (case kept). Quotes shorter than MIN_QUOTE are rejected.
- Every number in a claim must appear in the cited quotes or in the code-supplied
  facts the claim is about (in raw, millions or billions form), so the model can
  neither invent nor rescale a figure.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

MIN_QUOTE = 12

_SPACE = re.compile(r"\s+")
_TRANS = str.maketrans(
    {"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", "−": "-", "\xa0": " "}
)
_NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?")


def normalize(text: str) -> str:
    return _SPACE.sub(" ", text.translate(_TRANS)).strip()


def quote_found(quote: str, passage: str) -> bool:
    q = normalize(quote).strip(" .…\"'")
    return len(q) >= MIN_QUOTE and q in normalize(passage)


def numbers(text: str) -> set[Decimal]:
    out = set()
    for m in _NUMBER.finditer(text):
        try:
            out.add(Decimal(m.group(0).replace(",", "")).normalize())
        except InvalidOperation:
            continue
    return out


def scaled_forms(values: Iterable[Decimal]) -> set[Decimal]:
    """A fact in the forms a sentence may state it: raw, in millions, in billions."""
    out = set()
    for v in values:
        for f in (Decimal(1), Decimal(10) ** 6, Decimal(10) ** 9):
            out.add((abs(v) / f).normalize())
    return out


def unsupported_numbers(
    claim: str, quotes: Iterable[str], facts: Iterable[Decimal]
) -> set[Decimal]:
    allowed = set().union(*(numbers(q) for q in quotes)) | scaled_forms(facts)
    return {n for n in numbers(claim) if n not in allowed}
