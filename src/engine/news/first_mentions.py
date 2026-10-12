"""First mention of an accepted theme by a watchlist/tracked company (D-M02-10, D-M02-58).

Local only. A company's own stored documents (filings, releases, transcripts) and its IR
headlines are searched for the theme's active phrases. The first scan of a (company,
theme) pair records what is already there as the baseline, so a newly tracked company or
a newly accepted theme does not flood the digest; a pair that had no mention and now has
one is a first-mention event, unless the document is older than 60 days before the
pair was first scanned (an older filing stored late, e.g. a backfill).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from engine.news.match import phrase_pattern
from engine.sec.client import iso

LATE_DOCUMENT = timedelta(days=60)


@dataclass(frozen=True)
class Mention:
    cik: str
    theme_id: int
    phrase: str
    source: str  # document or ir_rss
    dated: str
    accession: str | None = None
    filename: str | None = None
    section: str | None = None
    item_id: int | None = None
    quote: str | None = None


def _fts(phrase: str) -> str:
    return '"' + " ".join(re.findall(r"[a-z0-9]+", phrase.lower())) + '"'


def _quote(body: str, m: re.Match[str], width: int = 160) -> str:
    a, b = max(0, m.start() - width), min(len(body), m.end() + width)
    return ("…" if a else "") + " ".join(body[a:b].split()) + ("…" if b < len(body) else "")


def _doc_dates(engine: sqlite3.Connection) -> dict[str, str]:
    dates = {r[0]: r[1] for r in engine.execute("SELECT accession, filed FROM filing")}
    for r in engine.execute("SELECT accession, stated_on FROM call_document "
                            "WHERE stated_on IS NOT NULL"):  # fmt: skip
        dates.setdefault(r[0], r[1])
    return dates


def earliest(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, ciks: set[str]
) -> dict[tuple[str, int], Mention]:
    """(cik, theme_id) → the earliest dated mention in stored documents or IR headlines."""
    if not ciks:
        return {}
    dates = _doc_dates(engine)
    marks = ",".join("?" * len(ciks))
    best: dict[tuple[str, int], Mention] = {}

    def keep(m: Mention) -> None:
        k = (m.cik, m.theme_id)
        if k not in best or m.dated < best[k].dated:
            best[k] = m

    for p in engine.execute(
        "SELECT p.theme_id, p.phrase FROM theme_phrase p JOIN theme t USING (theme_id) "
        "WHERE t.status = 'active' AND p.status = 'active'"
    ).fetchall():
        phrase = p["phrase"].strip('"')
        rx = phrase_pattern(phrase)
        try:
            rows = corpus.execute(
                "SELECT d.cik, d.accession, d.filename, s.label, "
                "substr(d.text, p.start_offset + 1, p.end_offset - p.start_offset) AS body "
                "FROM passage_fts f JOIN passage p ON p.passage_id = f.rowid "
                "JOIN section s ON s.section_id = p.section_id "
                f"JOIN document d ON d.doc_id = p.doc_id WHERE passage_fts MATCH ? "
                f"AND d.cik IN ({marks})",
                (_fts(phrase), *sorted(ciks)),
            ).fetchall()
        except sqlite3.OperationalError:
            continue
        for r in rows:
            dated = dates.get(r["accession"])
            m = rx.search(r["body"] or "")
            if not dated or not m:
                continue
            q = _quote(r["body"], m)
            keep(Mention(r["cik"], p["theme_id"], phrase, "document", dated[:10],
                         r["accession"], r["filename"], r["label"], quote=q))  # fmt: skip
    for r in engine.execute(
        "SELECT c.cik, t.theme_id, t.phrase, i.item_id, i.title, "
        "coalesce(i.published_at, i.first_seen_at) AS dated FROM news_theme t "
        "JOIN news_item i USING (item_id) JOIN news_company c USING (item_id) "
        "JOIN news_source s USING (item_id) WHERE s.channel = 'ir_rss' AND c.how = 'feed' "
        f"AND c.cik IN ({marks})",
        sorted(ciks),
    ):
        keep(Mention(r["cik"], r["theme_id"], r["phrase"], "ir_rss", r["dated"][:10],
                     item_id=r["item_id"], quote=r["title"]))  # fmt: skip
    return best


def scan(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, ciks: set[str], now: datetime
) -> list[Mention]:
    """Record pairs seen for the first time (baseline) and return new first mentions."""
    found = earliest(engine, corpus, ciks)
    themes = [r[0] for r in engine.execute("SELECT theme_id FROM theme WHERE status = 'active'")]
    known = {
        (r["cik"], r["theme_id"]): r
        for r in engine.execute("SELECT cik, theme_id, phrase, scanned_at FROM theme_first_mention")
    }
    ts = iso(now)
    events: list[Mention] = []
    engine.execute("BEGIN")
    try:
        for cik in sorted(ciks):
            for theme_id in themes:
                k = (cik, theme_id)
                m = found.get(k)
                row = known.get(k)
                if row is not None and (row["phrase"] is not None or m is None):
                    continue
                baseline = 1
                if row is not None:  # had no mention; now has one
                    first_scan = date.fromisoformat(row["scanned_at"][:10])
                    late = date.fromisoformat(m.dated) < first_scan - LATE_DOCUMENT
                    baseline = 1 if late else 0
                vals = (
                    (m.phrase, m.source, m.accession, m.filename, m.section, m.item_id,
                     m.dated, m.quote, ts) if m else (None,) * 8 + (None,)
                )  # fmt: skip
                if row is None:
                    engine.execute(
                        "INSERT INTO theme_first_mention (cik, theme_id, baseline, phrase, "
                        "source, accession, filename, section, item_id, dated, quote, "
                        "found_at, scanned_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (cik, theme_id, baseline, *vals, ts),
                    )
                else:
                    engine.execute(
                        "UPDATE theme_first_mention SET baseline = ?, phrase = ?, source = ?, "
                        "accession = ?, filename = ?, section = ?, item_id = ?, dated = ?, "
                        "quote = ?, found_at = ? WHERE cik = ? AND theme_id = ?",
                        (baseline, *vals, cik, theme_id),
                    )
                    if not baseline and m is not None:
                        events.append(m)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return events
