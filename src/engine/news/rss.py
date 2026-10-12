"""RSS/Atom feeds through feedparser (D-M02-58 (4)); ideas from the owner's old
`ir_feeds.py` (fetch, entry cleaning), not its code.

Fetch with our own HTTP (pacing, fetch log, conditional GET with ETag/Last-Modified),
then parse the bytes. A feed feedparser cannot read at all is a failure; a readable feed
with a few broken entries keeps the good ones.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

import feedparser

from engine.news.config import Feed, domain
from engine.news.fetch import Fetcher
from engine.news.items import RawItem, clean, snippet
from engine.sec.client import iso
from engine.sec.results import Failed


@dataclass(frozen=True)
class FeedResult:
    feed: Feed
    items: list[RawItem]
    status: str  # ok, not modified, failed
    detail: str = ""


def _date(entry: feedparser.FeedParserDict) -> str | None:
    for k in ("published_parsed", "updated_parsed"):
        st = entry.get(k)
        if st:
            return iso(datetime.fromtimestamp(calendar.timegm(st), UTC))
    return None


def _body(entry: feedparser.FeedParserDict) -> str | None:
    if entry.get("summary"):
        return entry["summary"]
    content = entry.get("content")
    if content:
        return content[0].get("value")
    return None


def parse(feed: Feed, body: bytes, cik: str | None = None) -> list[RawItem] | str:
    """Items of the feed, or the reason it could not be read."""
    parsed = feedparser.parse(body)
    if parsed.get("bozo") and not parsed.entries:
        exc = parsed.get("bozo_exception")
        return f"unreadable feed: {type(exc).__name__ if exc else 'unknown'}"
    out = []
    for e in parsed.entries:
        title = clean(e.get("title"))
        if not title:
            continue
        link = e.get("link") or None
        out.append(
            RawItem(
                channel=feed.channel,
                feed=feed.key,
                title=title,
                url=link,
                published_at=_date(e),
                snippet=snippet(_body(e)),
                origin=domain(link) or domain(feed.url),
                cik=cik,
            )
        )
    return out


def fetch(
    engine: sqlite3.Connection,
    fetcher: Fetcher,
    feed: Feed,
    now: datetime,
    cik: str | None = None,
) -> FeedResult:
    state = engine.execute(
        "SELECT etag, last_modified FROM news_feed_state WHERE feed = ?", (feed.state_key,)
    ).fetchone()
    headers = {}
    if state and state["etag"]:
        headers["If-None-Match"] = state["etag"]
    if state and state["last_modified"]:
        headers["If-Modified-Since"] = state["last_modified"]
    reply = fetcher.get(feed.url, lane="feed", headers=headers)
    if isinstance(reply, Failed):
        _state(engine, feed, now, status=reply.status, error=reply.reason)
        return FeedResult(feed, [], "failed", reply.reason)
    if reply.status == 304:
        _state(engine, feed, now, status=304, ok=True, keep_validators=True)
        return FeedResult(feed, [], "not modified")
    items = parse(feed, reply.body, cik)
    if isinstance(items, str):
        _state(engine, feed, now, status=reply.status, error=items)
        return FeedResult(feed, [], "failed", items)
    _state(engine, feed, now, status=reply.status, ok=True, n=len(items),
           etag=reply.header("ETag"), last_modified=reply.header("Last-Modified"))  # fmt: skip
    return FeedResult(feed, items, "ok")


def _state(
    engine: sqlite3.Connection,
    feed: Feed,
    now: datetime,
    *,
    status: int | None,
    ok: bool = False,
    error: str | None = None,
    n: int | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
    keep_validators: bool = False,
) -> None:
    ts = iso(now)
    if keep_validators:
        engine.execute(
            "UPDATE news_feed_state SET last_ok_at = ?, last_status = ?, last_error = NULL, "
            "checked_at = ? WHERE feed = ?",
            (ts, status, ts, feed.state_key),
        )
        return
    engine.execute(
        "INSERT INTO news_feed_state (feed, etag, last_modified, last_ok_at, last_status, "
        "last_error, items_last, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (feed) DO UPDATE SET "
        "etag = CASE WHEN excluded.last_error IS NULL THEN excluded.etag ELSE etag END, "
        "last_modified = CASE WHEN excluded.last_error IS NULL THEN excluded.last_modified "
        "ELSE last_modified END, "
        "last_ok_at = coalesce(excluded.last_ok_at, last_ok_at), "
        "last_status = excluded.last_status, last_error = excluded.last_error, "
        "items_last = coalesce(excluded.items_last, items_last), checked_at = excluded.checked_at",
        (feed.state_key, etag, last_modified, ts if ok else None, status, error, n, ts),
    )
