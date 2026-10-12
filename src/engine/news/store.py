"""Grade, dedupe and store news items (D-M02-13, D-M02-15).

Dedupe, in order: the normalised URL; else the same headline words with a date within
± 1 day; else a near-identical headline (word overlap ≥ 70%) of the same company within
± 2 days (an IR headline and the 8-K exhibit's first line rarely match word for word).
A duplicate adds a source to the existing item; the item keeps its best grade.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from engine.news import match
from engine.news.config import NewsConfig, domain, matches_domain
from engine.news.items import RawItem, clean, similar, snippet, title_key, url_key
from engine.sec.client import iso

COMPANY_CHANNELS = ("ir_rss", "sec_8k")  # the company's own words: grade A


def grade(raw: RawItem, cfg: NewsConfig) -> str:
    if raw.channel in COMPANY_CHANNELS:
        return "A"
    if raw.channel == "trade":
        return "B"
    origin = (raw.origin or "").lower()
    host = origin if "." in origin and " " not in origin else domain(raw.url)
    if host and matches_domain(host, cfg.company_domains):
        return "A"
    if host and matches_domain(host, cfg.outlets):
        return "B"
    if origin in cfg.sources:
        return "B"
    return "C"


@dataclass(frozen=True)
class Stored:
    item_id: int
    new: bool  # a new item (False = a source added to an existing one, or a repeat)
    new_source: bool


def _day(raw: RawItem, now: datetime) -> date:
    return date.fromisoformat((raw.published_at or iso(now))[:10])


def find_duplicate(engine: sqlite3.Connection, raw: RawItem, now: datetime) -> int | None:
    uk = url_key(raw.url)
    if uk:
        r = engine.execute("SELECT item_id FROM news_item WHERE url_key = ?", (uk,)).fetchone()
        if r:
            return r[0]
    d = _day(raw, now)
    lo, hi = (d - timedelta(days=1)).isoformat(), (d + timedelta(days=1)).isoformat() + "T99"
    r = engine.execute(
        "SELECT item_id FROM news_item WHERE title_key = ? "
        "AND coalesce(published_at, first_seen_at) BETWEEN ? AND ?",
        (title_key(raw.title), lo, hi),
    ).fetchone()
    if r:
        return r[0]
    if raw.cik:
        lo2, hi2 = (d - timedelta(days=2)).isoformat(), (d + timedelta(days=2)).isoformat() + "T99"
        for c in engine.execute(
            "SELECT i.item_id, i.title FROM news_item i JOIN news_company c USING (item_id) "
            "WHERE c.cik = ? AND coalesce(i.published_at, i.first_seen_at) BETWEEN ? AND ?",
            (raw.cik, lo2, hi2),
        ):
            if similar(c["title"], raw.title):
                return c["item_id"]
    return None


def store(
    engine: sqlite3.Connection,
    raw: RawItem,
    cfg: NewsConfig,
    now: datetime,
    themes: match.ThemeMatcher,
    companies: match.CompanyMatcher,
) -> Stored:
    """Store one item (caller holds the transaction)."""
    raw = replace(raw, title=clean(raw.title), snippet=snippet(raw.snippet))  # every path
    g = grade(raw, cfg)
    ts = iso(now)
    item_id = find_duplicate(engine, raw, now)
    new = item_id is None
    if new:
        cur = engine.execute(
            "INSERT INTO news_item (url_key, title, title_key, url, published_at, snippet, "
            "grade, first_seen_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (url_key(raw.url), raw.title, title_key(raw.title), raw.url, raw.published_at,
             raw.snippet, g, ts, ts),
        )  # fmt: skip
        item_id = int(cur.lastrowid)
    else:
        uk = url_key(raw.url)
        taken = uk and engine.execute("SELECT 1 FROM news_item WHERE url_key = ? AND item_id != ?",
                                      (uk, item_id)).fetchone()  # fmt: skip
        engine.execute(
            "UPDATE news_item SET "
            "grade = CASE WHEN ? < grade THEN ? ELSE grade END, "
            "url_key = coalesce(url_key, ?), url = coalesce(url, ?), "
            "published_at = coalesce(published_at, ?), "
            "snippet = CASE WHEN snippet IS NULL OR snippet = '' THEN ? ELSE snippet END, "
            "updated_at = ? WHERE item_id = ?",
            (g, g, None if taken else uk, raw.url, raw.published_at, raw.snippet, ts, item_id),
        )
    cur = engine.execute(
        "INSERT OR IGNORE INTO news_source (item_id, channel, feed, origin, grade, url, title, "
        "seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (item_id, raw.channel, raw.feed, raw.origin, g, raw.url, raw.title, ts),
    )
    new_source = cur.rowcount == 1
    if raw.cik:
        how = "feed" if raw.channel in COMPANY_CHANNELS else "ticker"
        engine.execute(
            "INSERT INTO news_company (item_id, cik, how) VALUES (?, ?, ?) "
            "ON CONFLICT (item_id, cik) DO UPDATE SET how = CASE WHEN excluded.how = 'feed' "
            "OR news_company.how = 'alias' THEN excluded.how ELSE news_company.how END",
            (item_id, raw.cik, how),
        )
    if new or new_source:
        match.rematch(engine, item_id, themes, companies)
    return Stored(item_id, new, new_source)


@dataclass
class StoreCounts:
    seen: int = 0
    new: int = 0
    merged: int = 0  # a new source on an existing item (dedupe)
    repeats: int = 0  # already stored from this source


def store_all(
    engine: sqlite3.Connection,
    items: list[RawItem],
    cfg: NewsConfig,
    now: datetime,
    themes: match.ThemeMatcher,
    companies: match.CompanyMatcher,
) -> StoreCounts:
    """Store a batch in one short transaction."""
    counts = StoreCounts()
    if not items:
        return counts
    engine.execute("BEGIN")
    try:
        for raw in items:
            s = store(engine, raw, cfg, now, themes, companies)
            counts.seen += 1
            if s.new:
                counts.new += 1
            elif s.new_source:
                counts.merged += 1
            else:
                counts.repeats += 1
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return counts
