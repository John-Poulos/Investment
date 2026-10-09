"""Spender → theme link sentences (D-M02-5, D-M02-30 (3)).

A spender counts toward a theme only through a quoted sentence tying its spending to
the theme's phrases: code finds sentences with an active theme phrase and spending words
(capex, capital expenditures, invest, spend) in the company's own documents of the last
~400 days — 10-K/10-Q text, earnings releases (grade A) and management turns of call
transcripts (grade B) — and the owner confirms one `m02_spender` review item per
company and theme (up to three sample sentences shown; confirm/reject applies to all
of that pair's sentences). Confirmed links put the company in the theme's money-flow
list.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from engine.guidance.calls import management_turns
from engine.guidance.parse import CAPEX_WORDS, MAX_SENTENCE, _lines, _sentences
from engine.guidance.sources import origin_of
from engine.sec.client import iso

LOOKBACK_DAYS = 400
SAMPLES = 3
_SPENDING = re.compile(r"\b(?:invest\w*|spend\w*|spent|build[- ]?out)\b", re.IGNORECASE)
_FILING_TYPES = ("10-K", "10-Q", "10-K/A", "10-Q/A")
_RELEASE_TYPES = ("EX-99.1", "EX-99.01", "EX-99")


@dataclass(frozen=True)
class Found:
    theme_id: int
    theme_key: str
    phrase: str
    accession: str
    filename: str
    origin: str
    grade: str
    quote: str
    start: int
    end: int
    filed: str | None


def _phrases(engine: sqlite3.Connection) -> list[tuple[int, str, str, re.Pattern[str]]]:
    rows = engine.execute(
        "SELECT t.theme_id, t.key, p.phrase FROM theme_phrase p JOIN theme t "
        "ON t.theme_id = p.theme_id WHERE p.status = 'active' AND t.status = 'active'"
    )
    out = []
    for r in rows:
        words = r["phrase"].strip('"').split()
        rx = re.compile(r"\b" + r"[\s-]+".join(map(re.escape, words)) + r"\b", re.IGNORECASE)
        out.append((r["theme_id"], r["key"], r["phrase"].strip('"'), rx))
    return out


def find_sentences(
    text: str,
    spans: list[tuple[int, int]],
    phrases: list[tuple[int, str, str, re.Pattern[str]]],
) -> list[tuple[int, str, str, int, int]]:
    """(theme_id, key, phrase, start, end) of sentences with a phrase and spending words."""
    out = []
    for a, b in spans:
        for la, lb in _lines(text):
            if lb <= a or la >= b:
                continue
            for s, e in _sentences(text, max(la, a), min(lb, b)):
                sent = text[s:e]
                if len(sent) > MAX_SENTENCE or "\t" in sent:
                    continue
                if not (CAPEX_WORDS.search(sent) or _SPENDING.search(sent)):
                    continue
                for theme_id, key, phrase, rx in phrases:
                    if rx.search(sent):
                        out.append((theme_id, key, phrase, s, e))
    return out


def scan_company(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, cik: str, now: datetime
) -> list[Found]:
    phrases = _phrases(engine)
    if not phrases:
        return []
    since = (now - timedelta(days=LOOKBACK_DAYS)).date().isoformat()
    filed = {
        r["accession"]: r["filed"]
        for r in engine.execute(
            "SELECT accession, filed FROM filing WHERE cik = ? AND filed >= ?", (cik, since)
        )
    }
    calls = {
        (r["accession"], r["filename"]): r["stated_on"]
        for r in engine.execute(
            "SELECT accession, filename, stated_on FROM call_document WHERE cik = ? "
            "AND stated_on >= ?",
            (cik, since),
        )
    }
    out: list[Found] = []
    for d in corpus.execute(
        "SELECT doc_id, accession, filename, doc_type, text FROM document WHERE cik = ?", (cik,)
    ):
        key = (d["accession"], d["filename"])
        origin = origin_of(d["accession"])
        if origin == "release":
            if d["accession"] not in filed:
                continue
            if d["doc_type"] in _FILING_TYPES:
                origin = "filing"
            elif d["doc_type"] not in _RELEASE_TYPES:
                continue
            spans = [(0, len(d["text"]))]
            when = filed[d["accession"]]
        else:
            if key not in calls:
                continue
            spans = management_turns(corpus, d["doc_id"], d["text"])
            when = calls[key]
        grade = "B" if origin == "call" else "A"
        for theme_id, tkey, phrase, s, e in find_sentences(d["text"], spans, phrases):
            out.append(
                Found(
                    theme_id,
                    tkey,
                    phrase,
                    d["accession"],
                    d["filename"],
                    origin,
                    grade,
                    d["text"][s:e].strip(),
                    s,
                    e,
                    when,
                )
            )
    return out


def store_and_propose(
    engine: sqlite3.Connection, cik: str, ticker: str, found: list[Found], now: datetime
) -> dict[str, int]:
    """Store link candidates; one m02_spender proposal per (company, theme)."""
    from engine.themes.proposals import propose

    by_theme: dict[int, list[Found]] = defaultdict(list)
    for f in found:
        engine.execute(
            "INSERT OR IGNORE INTO spender_link (cik, theme_id, accession, filename, origin, "
            "grade, phrase, quote, quote_start, quote_end, filed, found_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cik,
                f.theme_id,
                f.accession,
                f.filename,
                f.origin,
                f.grade,
                f.phrase,
                f.quote,
                f.start,
                f.end,
                f.filed,
                iso(now),
            ),
        )
        by_theme[f.theme_id].append(f)
    counts: dict[str, int] = {}
    for theme_id, items in by_theme.items():
        status = engine.execute(
            "SELECT status FROM spender_link WHERE cik = ? AND theme_id = ? "
            "AND status != 'open' LIMIT 1",
            (cik, theme_id),
        ).fetchone()
        if status is not None:
            # a decided pair: new sentences follow the decision (confirmed stays confirmed)
            engine.execute(
                "UPDATE spender_link SET status = ? WHERE cik = ? AND theme_id = ? "
                "AND status = 'open'",
                (status[0], cik, theme_id),
            )
            continue
        best = sorted(items, key=lambda f: (f.grade != "A", f.origin == "filing", -_ord(f.filed)))[
            :SAMPLES
        ]
        payload = {
            "ticker": ticker,
            "theme_id": theme_id,
            "theme_key": items[0].theme_key,
            "samples": [f"{f.quote} [{f.origin} · {f.grade} · {f.filed}]" for f in best],
            "sentences": len(items),
            "money_flow": True,
            "why": f'{len(items)} sentence(s) tie {ticker}\'s spending to "{items[0].phrase}"',
        }
        reason = f"{ticker}: does its spending count toward {items[0].theme_key}?"
        res = propose(
            engine, "m02_spender", f"{cik}:{items[0].theme_key}", reason, payload, now, cik=cik
        )
        counts[res] = counts.get(res, 0) + 1
    return counts


def _ord(d: str | None) -> int:
    return int((d or "0000-00-00")[:10].replace("-", "") or 0)


def decide(
    engine: sqlite3.Connection, cik: str, theme_id: int, action: str, item_id: int, now: datetime
) -> None:
    status = {"confirm": "confirmed", "reject": "rejected"}[action]
    engine.execute(
        "UPDATE spender_link SET status = ?, item_id = ?, decided_at = ? "
        "WHERE cik = ? AND theme_id = ?",
        (status, item_id, iso(now), cik, theme_id),
    )


def confirmed(engine: sqlite3.Connection, theme_id: int) -> dict[str, sqlite3.Row]:
    """cik → the best confirmed sentence (release/filing first, newest)."""
    out: dict[str, sqlite3.Row] = {}
    for r in engine.execute(
        "SELECT * FROM spender_link WHERE theme_id = ? AND status = 'confirmed' "
        "ORDER BY grade, filed DESC",
        (theme_id,),
    ):
        out.setdefault(r["cik"], r)
    return out


def company_links(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT l.theme_id, t.key, t.name, l.status, l.quote, l.origin, l.grade, l.filed, "
        "l.accession, l.filename, l.quote_start FROM spender_link l "
        "JOIN theme t ON t.theme_id = l.theme_id WHERE l.cik = ? "
        "ORDER BY l.status = 'confirmed' DESC, t.name, l.grade, l.filed DESC",
        (cik,),
    ).fetchall()
