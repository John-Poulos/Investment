"""The weekly news review item, `m02_news` (D-M02-58 (2), (3)).

One item per completed week (Monday–Sunday, UTC), built at the first run after the week
ends; it counts as 1 of the 10 M02 items a week. An item belongs to the week in which it
was first seen (the PC is off overnight, so a Friday release may arrive on Monday), if
its own date is no more than 7 days before that week (the first run's backlog stays out).

Events (D-M02-58 (3)): items containing an active theme phrase that are either
- grade A from the company itself (IR RSS, 8-K release) of a watchlist/tracked company, or
- grade A/B and naming a watchlist/tracked company (vendor ticker or alias).
Theme items about other companies are counted only. First mentions come from
`first_mentions.scan` (found that week). News is never a signal on its own.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from engine.sec.client import iso
from engine.themes import proposals

LIST_PER_THEME = 15  # the rest are counted, and listed on the theme page


def tier_ciks(engine: sqlite3.Connection, core: dict[str, str]) -> dict[str, str]:
    """cik → ticker of core (watchlist), promoted and tracked companies."""
    out = dict(core)
    for r in engine.execute("SELECT cik, ticker FROM tier_member WHERE status = 'active'"):
        out.setdefault(r["cik"], r["ticker"])
    return out


def build(
    engine: sqlite3.Connection, week_start: datetime, tiers: dict[str, str]
) -> dict[str, Any] | None:
    """The digest payload for the week starting `week_start`, or None when empty."""
    lo, hi = iso(week_start), iso(week_start + timedelta(days=7))
    oldest = iso(week_start - timedelta(days=7))
    rows = engine.execute(
        "SELECT i.item_id, i.title, i.url, i.grade, i.snippet, "
        "coalesce(i.published_at, i.first_seen_at) AS dated, t.theme_id, t.phrase, "
        "th.key AS theme_key, th.name AS theme_name FROM news_item i "
        "JOIN news_theme t USING (item_id) JOIN theme th ON th.theme_id = t.theme_id "
        "WHERE th.status = 'active' AND i.first_seen_at >= ? AND i.first_seen_at < ? "
        "AND coalesce(i.published_at, i.first_seen_at) >= ? ORDER BY dated",
        (lo, hi, oldest),
    ).fetchall()
    ids = sorted({r["item_id"] for r in rows})
    companies: dict[int, list[tuple[str, str]]] = defaultdict(list)
    sources: dict[int, list[dict[str, str]]] = defaultdict(list)
    if ids:
        marks = ",".join("?" * len(ids))
        for c in engine.execute(f"SELECT item_id, cik, how FROM news_company "
                                f"WHERE item_id IN ({marks})", ids):  # fmt: skip
            companies[c["item_id"]].append((c["cik"], c["how"]))
        sql = (f"SELECT item_id, channel, feed, origin, grade FROM news_source "
               f"WHERE item_id IN ({marks}) ORDER BY grade, channel")  # fmt: skip
        for s in engine.execute(sql, ids):
            src = {"channel": s["channel"], "feed": s["feed"], "origin": s["origin"] or ""}
            sources[s["item_id"]].append(src | {"grade": s["grade"]})
    by_theme: dict[int, dict[str, Any]] = {}
    other: dict[int, int] = defaultdict(int)
    for r in rows:
        cos = companies.get(r["item_id"], [])
        own = any(how == "feed" and cik in tiers for cik, how in cos)
        named = [tiers[cik] for cik, _ in cos if cik in tiers]
        event = (own and r["grade"] == "A") or (r["grade"] in ("A", "B") and named)
        if not event:
            other[r["theme_id"]] += 1
            continue
        t = by_theme.setdefault(r["theme_id"], {"theme_id": r["theme_id"], "key": r["theme_key"],
                                                "name": r["theme_name"], "events": []})  # fmt: skip
        t["events"].append({
            "item_id": r["item_id"], "title": r["title"], "url": r["url"],
            "date": r["dated"][:10], "grade": r["grade"], "phrase": r["phrase"],
            "companies": sorted(set(named)), "sources": sources.get(r["item_id"], []),
        })  # fmt: skip
    firsts = [
        dict(r) | {"ticker": tiers.get(r["cik"], r["cik"])}
        for r in engine.execute(
            "SELECT f.cik, f.theme_id, th.key AS theme_key, th.name AS theme_name, f.phrase, "
            "f.source, f.accession, f.filename, f.section, f.item_id, f.dated, f.quote "
            "FROM theme_first_mention f JOIN theme th USING (theme_id) "
            "WHERE f.baseline = 0 AND f.found_at >= ? AND f.found_at < ? ORDER BY f.dated",
            (lo, hi),
        )
    ]
    if not by_theme and not firsts:
        return None
    themes = []
    for t in sorted(by_theme.values(), key=lambda t: (-len(t["events"]), t["name"])):
        t["events"].sort(key=lambda e: (e["grade"], e["date"]))
        t["more"] = max(0, len(t["events"]) - LIST_PER_THEME)
        t["events"] = t["events"][:LIST_PER_THEME]
        t["other"] = other.pop(t["theme_id"], 0)
        themes.append(t)
    n_events = sum(len(t["events"]) + t["more"] for t in themes)
    return {
        "week": week_start.date().isoformat(),
        "week_end": (week_start + timedelta(days=6)).date().isoformat(),
        "themes": themes,
        "first_mentions": firsts,
        "events": n_events,
        "other_items": sum(t["other"] for t in themes) + sum(other.values()),
        "companies": len(
            {c for t in themes for e in t["events"] for c in e["companies"]}
            | {f["ticker"] for f in firsts}
        ),
        "money_flow": False,
        "grade": "A"
        if any(e["grade"] == "A" for t in themes for e in t["events"]) or firsts
        else "B",
        "why": "News on accepted themes this week, one item per distinct event (the same "
        "release from IR RSS, Finnhub and an 8-K is one event). Evidence, never a signal "
        "on its own.",
    }


def propose_week(
    engine: sqlite3.Connection,
    week_start: datetime,
    tiers: dict[str, str],
    now: datetime,
    *,
    preview: bool = False,
) -> str:
    """Queue the week's item: 'queued', 'overflow', 'suppressed' or 'empty'.
    A preview (the current, unfinished week; owner's live check) has its own key."""
    payload = build(engine, week_start, tiers)
    if payload is None:
        return "empty"
    key = payload["week"] + (":preview" if preview else "")
    payload["preview"] = preview
    reason = (f"News {payload['week']} to {payload['week_end']}"
              + (" (so far)" if preview else "")
              + f": {payload['events']} event(s) on {len(payload['themes'])} theme(s), "
              f"{len(payload['first_mentions'])} first mention(s)")  # fmt: skip
    return proposals.propose(engine, "m02_news", key, reason, payload, now)


def last_week_start(now: datetime) -> datetime:
    return proposals.week_start(now) - timedelta(days=7)
