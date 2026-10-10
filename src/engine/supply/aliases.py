"""Company names as other filers write them (`config/aliases.toml`, D-M02-35).

Matching in text is case-sensitive with word boundaries, longest name first, so "Apple"
does not match "Applied" and "Samsung Electronics" wins over "Samsung". Full-text search
(EFTS) is case-insensitive by itself.
"""

from __future__ import annotations

import re
import sqlite3
import tomllib
from dataclasses import dataclass
from pathlib import Path

ALIASES = Path("config/aliases.toml")


@dataclass(frozen=True)
class Company:
    key: str
    ticker: str | None
    names: tuple[str, ...]
    customer: bool
    cik: str | None = None
    bare: bool = False  # option (c) trial: bare-name search in hardware/semiconductor filers

    @property
    def name(self) -> str:
        return self.names[0]


@dataclass(frozen=True)
class Mention:
    company: Company
    name: str
    start: int
    end: int


def load(engine: sqlite3.Connection | None = None, path: Path = ALIASES) -> list[Company]:
    if not path.exists():
        return []
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    out = []
    for key, v in data.items():
        if not isinstance(v, dict) or not v.get("names"):
            continue
        ticker = v.get("ticker")
        cik = None
        if engine is not None and ticker:
            row = engine.execute(
                "SELECT cik FROM ticker WHERE ticker = ? AND valid_to IS NULL", (ticker,)
            ).fetchone()
            cik = row[0] if row else None
        names = tuple(sorted(v["names"], key=len, reverse=True))
        out.append(
            Company(
                key, ticker, names, bool(v.get("customer", False)), cik, bool(v.get("bare", False))
            )
        )
    return out


class Matcher:
    """Finds alias mentions in text; overlapping matches keep the longest name."""

    def __init__(self, companies: list[Company]) -> None:
        self.companies = companies
        pairs = sorted(((n, c) for c in companies for n in c.names), key=lambda p: -len(p[0]))
        self._by_name = {n: c for n, c in pairs}
        alts = "|".join(re.escape(n) for n, _ in pairs)
        self._rx = re.compile(rf"(?<![\w.-])(?:{alts})(?![\w-])") if pairs else None

    def find(self, text: str, start: int = 0, end: int | None = None) -> list[Mention]:
        if self._rx is None:
            return []
        out: list[Mention] = []
        for m in self._rx.finditer(text, start, len(text) if end is None else end):
            out.append(Mention(self._by_name[m.group(0)], m.group(0), m.start(), m.end()))
        return out

    def by_cik(self, cik: str) -> Company | None:
        return next((c for c in self.companies if c.cik == cik), None)
