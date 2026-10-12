"""Theme phrases and companies in a headline + snippet (D-M02-13, D-M02-58).

- Theme phrases: case-insensitive, word boundaries, a space or hyphen between words; in
  short news text a plural ("chiplets", "qubits") and an acronym's generation suffix
  ("HBM4", "HBM3E") also count. Active themes and active phrases only.
- Companies: aliases from `config/aliases.toml` (legal names and known aliases, case-
  sensitive, longest first; never short collision names like "Meta"), for companies
  resolved to a CIK.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from engine.supply import aliases

_ACRONYM = re.compile(r"^[A-Z][A-Z0-9]{1,5}$")


def phrase_pattern(phrase: str) -> re.Pattern[str]:
    raw = phrase.strip().strip('"')
    words = re.findall(r"[A-Za-z0-9]+", raw)
    body = r"[\s\-]+".join(re.escape(w) for w in words)
    tail = r"(?:\d+[A-Za-z]?)?s?" if _ACRONYM.match(raw) else r"(?:s|es)?"
    return re.compile(r"(?<![\w-])" + body + tail + r"(?![\w-])", re.I)


@dataclass(frozen=True)
class ThemePhrase:
    theme_id: int
    phrase: str  # as shown (unquoted)
    pattern: re.Pattern[str]


class ThemeMatcher:
    def __init__(self, engine: sqlite3.Connection) -> None:
        self.phrases = [
            ThemePhrase(r["theme_id"], r["phrase"].strip('"'), phrase_pattern(r["phrase"]))
            for r in engine.execute(
                "SELECT p.theme_id, p.phrase FROM theme_phrase p JOIN theme t USING (theme_id) "
                "WHERE t.status = 'active' AND p.status = 'active' ORDER BY p.phrase_id"
            )
        ]

    def find(self, text: str) -> dict[int, str]:
        """theme_id → the first phrase found for it."""
        out: dict[int, str] = {}
        for p in self.phrases:
            if p.theme_id not in out and p.pattern.search(text):
                out[p.theme_id] = p.phrase
        return out


class CompanyMatcher:
    def __init__(self, engine: sqlite3.Connection) -> None:
        self._m = aliases.Matcher([c for c in aliases.load(engine) if c.cik])

    def find(self, text: str) -> set[str]:
        return {m.company.cik for m in self._m.find(text) if m.company.cik}


def text_of(title: str, snippet: str | None) -> str:
    return f"{title}\n{snippet or ''}"


def rematch(
    engine: sqlite3.Connection,
    item_id: int,
    themes: ThemeMatcher,
    companies: CompanyMatcher,
) -> tuple[dict[int, str], set[str]]:
    """Rebuild the item's theme links and alias company links (feed/ticker links stay)."""
    r = engine.execute("SELECT title, snippet FROM news_item WHERE item_id = ?",
                       (item_id,)).fetchone()  # fmt: skip
    text = text_of(r["title"], r["snippet"])
    found = themes.find(text)
    engine.execute("DELETE FROM news_theme WHERE item_id = ?", (item_id,))
    engine.executemany(
        "INSERT INTO news_theme (item_id, theme_id, phrase) VALUES (?, ?, ?)",
        [(item_id, t, p) for t, p in found.items()],
    )
    ciks = companies.find(text)
    engine.execute("DELETE FROM news_company WHERE item_id = ? AND how = 'alias'", (item_id,))
    engine.executemany(
        "INSERT OR IGNORE INTO news_company (item_id, cik, how) VALUES (?, ?, 'alias')",
        [(item_id, c) for c in sorted(ciks)],
    )
    return found, ciks


def rematch_all(engine: sqlite3.Connection) -> int:
    """Re-run matching on every stored item (after theme or alias changes)."""
    themes, companies = ThemeMatcher(engine), CompanyMatcher(engine)
    ids = [r[0] for r in engine.execute("SELECT item_id FROM news_item")]
    for start in range(0, len(ids), 200):  # short write transactions (D-M02-12)
        engine.execute("BEGIN")
        try:
            for i in ids[start : start + 200]:
                rematch(engine, i, themes, companies)
            engine.execute("COMMIT")
        except Exception:
            engine.execute("ROLLBACK")
            raise
    return len(ids)
