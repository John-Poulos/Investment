"""News for the UI: company News tab and the theme page section (D-M02-58)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

CHANNEL_LABELS = {
    "ir_rss": "IR feed",
    "sec_8k": "8-K",
    "finnhub": "Finnhub",
    "massive": "Massive",
    "trade": "trade press",
}


def _items(
    engine: sqlite3.Connection, where: str, params: tuple, limit: int
) -> list[dict[str, Any]]:
    rows = engine.execute(
        "SELECT i.item_id, i.title, i.url, i.snippet, i.grade, "
        "coalesce(i.published_at, i.first_seen_at) AS dated, i.published_at IS NULL AS undated "
        f"FROM news_item i WHERE {where} ORDER BY dated DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    ids = [r["item_id"] for r in rows]
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    themes: dict[int, list[dict[str, str]]] = {}
    for t in engine.execute(
        f"SELECT n.item_id, n.phrase, th.key, th.name FROM news_theme n JOIN theme th "
        f"USING (theme_id) WHERE n.item_id IN ({marks}) AND th.status = 'active'",
        ids,
    ):
        themes.setdefault(t["item_id"], []).append({"key": t["key"], "name": t["name"],
                                                    "phrase": t["phrase"]})  # fmt: skip
    sources: dict[int, list[str]] = {}
    sql = (f"SELECT item_id, channel, origin FROM news_source "
           f"WHERE item_id IN ({marks}) ORDER BY grade, channel")  # fmt: skip
    for s in engine.execute(sql, ids):
        label = CHANNEL_LABELS.get(s["channel"], s["channel"])
        if s["channel"] in ("finnhub", "massive", "trade") and s["origin"]:
            label += f" ({s['origin']})"
        sources.setdefault(s["item_id"], []).append(label)
    tickers: dict[int, list[str]] = {}
    for c in engine.execute(
        f"SELECT n.item_id, coalesce((SELECT min(ticker) FROM ticker t WHERE t.cik = n.cik "
        f"AND t.valid_to IS NULL), n.cik) AS ticker FROM news_company n "
        f"WHERE n.item_id IN ({marks})",
        ids,
    ):
        tickers.setdefault(c["item_id"], []).append(c["ticker"])
    return [
        dict(r)
        | {
            "date": r["dated"][:10],
            "themes": themes.get(r["item_id"], []),
            "sources": sources.get(r["item_id"], []),
            "tickers": sorted(tickers.get(r["item_id"], [])),
        }
        for r in rows
    ]


@dataclass
class CompanyNews:
    items: list[dict[str, Any]] = field(default_factory=list)
    firsts: list[dict[str, Any]] = field(default_factory=list)
    themed_only: bool = False


def company_view(
    engine: sqlite3.Connection, cik: str, *, themed_only: bool = False, limit: int = 100
) -> CompanyNews:
    where = "i.item_id IN (SELECT item_id FROM news_company WHERE cik = ?)"
    if themed_only:
        where += " AND i.item_id IN (SELECT item_id FROM news_theme)"
    firsts = [
        dict(r)
        for r in engine.execute(
            "SELECT f.*, th.key, th.name FROM theme_first_mention f JOIN theme th "
            "USING (theme_id) WHERE f.cik = ? AND f.phrase IS NOT NULL AND th.status = 'active' "
            "ORDER BY f.dated",
            (cik,),
        )
    ]
    return CompanyNews(_items(engine, where, (cik,), limit), firsts, themed_only)


@dataclass
class ThemeNews:
    days: int
    items: list[dict[str, Any]]
    companies: list[tuple[str, int]]  # (ticker or name, items) in the window
    firsts: list[dict[str, Any]]


def theme_view(
    engine: sqlite3.Connection, theme_id: int, today: date, days: int = 90, limit: int = 40
) -> ThemeNews:
    since = (today - timedelta(days=days)).isoformat()
    where = ("i.item_id IN (SELECT item_id FROM news_theme WHERE theme_id = ?) "
             "AND coalesce(i.published_at, i.first_seen_at) >= ?")  # fmt: skip
    cos = [
        (r["label"], r["n"])
        for r in engine.execute(
            "SELECT coalesce((SELECT min(ticker) FROM ticker t WHERE t.cik = c.cik "
            "AND t.valid_to IS NULL), e.name, c.cik) AS label, count(DISTINCT c.item_id) n "
            "FROM news_company c JOIN news_theme n USING (item_id) "
            "JOIN news_item i USING (item_id) "
            "LEFT JOIN entity e ON e.cik = c.cik "
            "WHERE n.theme_id = ? AND coalesce(i.published_at, i.first_seen_at) >= ? "
            "GROUP BY c.cik ORDER BY n DESC, label",
            (theme_id, since),
        )
    ]
    firsts = [
        dict(r)
        for r in engine.execute(
            "SELECT f.*, coalesce((SELECT min(ticker) FROM ticker t WHERE t.cik = f.cik "
            "AND t.valid_to IS NULL), f.cik) AS ticker FROM theme_first_mention f "
            "WHERE f.theme_id = ? AND f.phrase IS NOT NULL ORDER BY f.dated DESC",
            (theme_id,),
        )
    ]
    return ThemeNews(days, _items(engine, where, (theme_id, since), limit), cos, firsts)
