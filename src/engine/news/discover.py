"""IR feed discovery for watchlist/tracked companies without a configured feed (D-M02-59).

1. The company's web domain from Finnhub's company profile (`/stock/profile2`, 1 request).
2. Known vendor feed addresses on its investor./investors./ir. hosts, in order, stopping at
   the first that passes — feed URLs only, never pages (feeds are published for readers,
   D-M02-13). Patterns seen on 2026-10-08/12: Q4 Inc `/rss/pressrelease.aspx` (NVDA, MU,
   META, BA, AMZN, SPCX), Nasdaq IR `/news-events/press-releases/rss` (INTC, MRVL, INFQ),
   Notified `/rss/news-releases.xml` (GFS), Drupal `/rss.xml` (TSLA).
3. A candidate passes when it parses as a feed with ≥ 3 entries and most entry links stay
   on the company's domain (an empty feed, like Apple's investor feed, does not).
4. A feed found → review item `m02_ir_feed` (confirm / reject; operational, uncapped);
   confirmed feeds are polled from the database. Nothing found → 'none_found', re-checked
   after 90 days. A company listed in `config/news.toml` is never looked up.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from engine.news import rss
from engine.news.config import Feed, NewsConfig, domain, matches_domain
from engine.news.fetch import Fetcher
from engine.sec.client import iso
from engine.sec.results import Failed
from engine.themes import proposals

PROFILE_URL = "https://finnhub.io/api/v1/stock/profile2"
HOSTS = ("ir.{d}", "investor.{d}", "investors.{d}")
PATHS = (
    "/rss/pressrelease.aspx",
    "/news-events/press-releases/rss",
    "/rss/news-releases.xml",
    "/rss.xml",
)
MIN_ENTRIES = 3
RECHECK = timedelta(days=90)
PER_RUN = 5  # companies looked up per run (≤ 13 requests each at 1 s)


@dataclass(frozen=True)
class Found:
    url: str
    title: str
    samples: list[str]


def candidates(dom: str) -> list[str]:
    return [f"https://{h.format(d=dom)}{p}" for h in HOSTS for p in PATHS]


def web_domain(fetcher: Fetcher, key: str, symbol: str) -> str | None | Failed:
    """The company's web domain without 'www.', None when Finnhub has none."""
    reply = fetcher.get(PROFILE_URL, lane="finnhub", params={"symbol": symbol},
                        headers={"X-Finnhub-Token": key},
                        logged_url=f"{PROFILE_URL}?symbol={symbol}")  # fmt: skip
    if isinstance(reply, Failed):
        return reply
    try:
        data = json.loads(reply.body)
    except ValueError:
        return Failed("unreadable profile JSON", url=PROFILE_URL)
    if not isinstance(data, dict):
        return None
    return domain(data.get("weburl")) or None


def check(body: bytes, url: str, dom: str) -> Found | str:
    """The feed if it passes, else why not."""
    items = rss.parse(Feed("ir_rss", "?", "?", url), body)
    if isinstance(items, str):
        return items
    if len(items) < MIN_ENTRIES:
        return f"{len(items)} entries"
    own = sum(1 for i in items if matches_domain(domain(i.url), {dom}))
    if own * 2 < len(items):
        return f"{own} of {len(items)} entries link to {dom}"
    import feedparser

    title = (feedparser.parse(body).feed.get("title") or "").strip()
    return Found(url, title, [i.title for i in items[:3]])


def find(fetcher: Fetcher, dom: str) -> tuple[Found | None, int, list[str]]:
    """(feed found or None, addresses tried, notes on the misses)."""
    notes: list[str] = []
    tried = 0
    for url in candidates(dom):
        tried += 1
        reply = fetcher.get(url, lane="feed")
        if isinstance(reply, Failed):
            notes.append(f"{url}: {reply.reason}")
            continue
        got = check(reply.body, url, dom)
        if isinstance(got, Found):
            return got, tried, notes
        notes.append(f"{url}: {got}")
    return None, tried, notes


def due(engine: sqlite3.Connection, companies: dict[str, str], cfg: NewsConfig,
        now: datetime) -> list[tuple[str, str]]:  # fmt: skip
    """(ticker, cik) of companies to look up: no config feed, and no row or a
    'none_found' row older than 90 days."""
    rows = {r["cik"]: r for r in engine.execute("SELECT cik, status, checked_at FROM ir_feed")}
    out = []
    for ticker, cik in sorted(companies.items()):
        if ticker in cfg.ir:
            continue
        r = rows.get(cik)
        if r is None or (r["status"] == "none_found"
                         and r["checked_at"] < iso(now - RECHECK)):  # fmt: skip
            out.append((ticker, cik))
    return out


def run(engine: sqlite3.Connection, fetcher: Fetcher, key: str | None,
        companies: dict[str, str], cfg: NewsConfig, now: datetime,
        per_run: int = PER_RUN) -> list[str]:  # fmt: skip
    """Look up due companies; returns report lines."""
    todo = due(engine, companies, cfg, now)
    if not todo:
        return []
    if not key:
        return [f"IR feed discovery: {len(todo)} compan(ies) waiting — FINNHUB_API_KEY not set"]
    lines = []
    for ticker, cik in todo[:per_run]:
        dom = web_domain(fetcher, key, ticker)
        if isinstance(dom, Failed):
            lines.append(f"IR feed discovery {ticker}: profile failed ({dom.reason}); next run")
            if dom.throttled:
                break
            continue
        if not dom:
            _save(engine, cik, ticker, "none_found", None, None, 0, "no web domain", now)
            lines.append(f"IR feed discovery {ticker}: no web domain in the company profile")
            continue
        found, tried, notes = find(fetcher, dom)
        if found is None:
            _save(engine, cik, ticker, "none_found", None, dom, tried, "; ".join(notes)[:2000], now)
            lines.append(f"IR feed discovery {ticker}: none found on {dom} ({tried} tried)")
            continue
        _save(engine, cik, ticker, "proposed", found, dom, tried, None, now)
        payload = {
            "ticker": ticker, "feed": found.url, "feed_title": found.title,
            "domain": dom, "samples": found.samples,
            "why": f"A feed on {dom}'s investor site with {len(found.samples)}+ recent entries "
            "linking to the company's own domain. Confirm to poll it on every run (grade A, "
            "the company's own words); reject if it is not this company's press releases.",
        }  # fmt: skip
        proposals.propose(engine, "m02_ir_feed", f"{cik}:{found.url}",
                          f"{ticker}: IR feed found — {found.title or found.url}",
                          payload, now, cik=cik)  # fmt: skip
        lines.append(f"IR feed discovery {ticker}: found {found.url} → review")
    left = len(todo) - per_run
    if left > 0:
        lines.append(f"IR feed discovery: {left} compan(ies) left for the next run")
    return lines


def _save(engine, cik, ticker, status, found, dom, tried, detail, now) -> None:  # fmt: skip
    ts = iso(now)
    engine.execute(
        "INSERT INTO ir_feed (cik, ticker, status, url, title, domain, samples, tried, detail, "
        "found_at, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (cik) DO UPDATE SET ticker = excluded.ticker, status = excluded.status, "
        "url = excluded.url, title = excluded.title, domain = excluded.domain, "
        "samples = excluded.samples, tried = excluded.tried, detail = excluded.detail, "
        "found_at = excluded.found_at, checked_at = excluded.checked_at",
        (cik, ticker, status, found.url if found else None, found.title if found else None,
         dom, json.dumps(found.samples) if found else None, tried, detail,
         ts if found else None, ts),
    )  # fmt: skip


def decide(engine: sqlite3.Connection, cik: str, url: str, action: str, by: str,
           now: datetime) -> None:  # fmt: skip
    """Owner's answer on an `m02_ir_feed` item."""
    status = "confirmed" if action == "confirm" else "rejected"
    engine.execute("UPDATE ir_feed SET status = ?, decided_at = ?, decided_by = ? "
                   "WHERE cik = ? AND url = ?", (status, iso(now), by, cik, url))  # fmt: skip


def confirmed(engine: sqlite3.Connection, companies: dict[str, str],
              cfg: NewsConfig) -> tuple[list[Feed], dict[str, str]]:  # fmt: skip
    """Confirmed feeds to poll (config entries win) and their company domains."""
    feeds, domains = [], {}
    for r in engine.execute(
        "SELECT ticker, cik, url, domain FROM ir_feed WHERE status = 'confirmed'"
    ):
        if r["ticker"] in cfg.ir or companies.get(r["ticker"]) != r["cik"]:
            continue
        feeds.append(Feed("ir_rss", r["ticker"], r["ticker"], r["url"]))
        if r["domain"]:
            domains[r["domain"]] = r["ticker"]
    return feeds, domains
