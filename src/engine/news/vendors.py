"""Company news from Finnhub (primary) and Massive (backup) (D-M02-13).

- Finnhub `GET /api/v1/company-news?symbol=&from=&to=`, key in the `X-Finnhub-Token`
  header; free tier 60 requests/min, one year of history, North American companies.
  Reply: a JSON list of {category, datetime (Unix s), headline, id, image, related,
  source, summary, url}. Finnhub's `url` is often its own redirect, so dedupe falls back
  to title + date (items.url_key).
- Massive (ex-Polygon) `GET /v2/reference/news?ticker=&published_utc.gte=`, key as a
  Bearer header; free tier 5/min. Reply: {results: [{title, article_url, published_utc,
  description, publisher: {name, homepage_url}, tickers}], next_url, status}.
- Licences: personal use only; Finnhub forbids sharing data or results without approval
  (U7, DATA_SOURCES DS4). Keys never appear in logged URLs.
- An empty list is "no news in the window", a failure is never empty.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime

from engine.news.config import domain
from engine.news.fetch import Fetcher
from engine.news.items import RawItem, clean, snippet
from engine.sec.client import iso
from engine.sec.results import Failed

FINNHUB_URL = "https://finnhub.io/api/v1/company-news"
MASSIVE_URL = "https://api.massive.com/v2/reference/news"


def key_from_env(name: str) -> str | None:
    from dotenv import load_dotenv

    load_dotenv()
    return os.getenv(name, "").strip() or None


def parse_finnhub(symbol: str, body: bytes, cik: str | None = None) -> list[RawItem] | str:
    try:
        data = json.loads(body)
    except ValueError as e:
        return f"unreadable JSON: {e}"
    if isinstance(data, dict) and data.get("error"):
        return f"error: {str(data['error'])[:200]}"
    if not isinstance(data, list):
        return "unexpected reply shape"
    out = []
    for d in data:
        if not isinstance(d, dict):
            continue
        title = clean(d.get("headline"))
        if not title:
            continue
        ts = d.get("datetime")
        published = (
            iso(datetime.fromtimestamp(ts, UTC)) if isinstance(ts, int | float) and ts > 0 else None
        )
        url = d.get("url") or None
        source = clean(d.get("source")) or None
        host = domain(url)
        out.append(
            RawItem(
                channel="finnhub",
                feed=symbol,
                title=title,
                url=url,
                published_at=published,
                snippet=snippet(d.get("summary")),
                # the article's own domain when the link is direct, else Finnhub's source name
                origin=host if host and not host.endswith("finnhub.io") else source,
                tickers=(symbol,),
                cik=cik,
            )
        )
    return out


def parse_massive(symbol: str, body: bytes, cik: str | None = None) -> list[RawItem] | str:
    try:
        data = json.loads(body)
    except ValueError as e:
        return f"unreadable JSON: {e}"
    if not isinstance(data, dict):
        return "unexpected reply shape"
    if str(data.get("status", "OK")).upper() not in ("OK", "DELAYED"):
        return f"status {data.get('status')}: {str(data.get('error') or data.get('message'))[:200]}"
    results = data.get("results") or []
    if not isinstance(results, list):
        return "unexpected reply shape"
    out = []
    for d in results:
        if not isinstance(d, dict):
            continue
        title = clean(d.get("title"))
        if not title:
            continue
        url = d.get("article_url") or None
        published = d.get("published_utc") or None
        if published:
            try:
                published = iso(datetime.fromisoformat(published.replace("Z", "+00:00")))
            except ValueError:
                published = None
        out.append(
            RawItem(
                channel="massive",
                feed=symbol,
                title=title,
                url=url,
                published_at=published,
                snippet=snippet(d.get("description")),
                origin=domain(url) or None,
                tickers=(symbol,),
                cik=cik,
            )
        )
    return out


def finnhub_news(
    fetcher: Fetcher, key: str, symbol: str, start: date, end: date, cik: str | None = None
) -> list[RawItem] | Failed:
    params = {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()}
    shown = f"{FINNHUB_URL}?symbol={symbol}&from={start}&to={end}"
    reply = fetcher.get(FINNHUB_URL, lane="finnhub", params=params,
                        headers={"X-Finnhub-Token": key}, logged_url=shown)  # fmt: skip
    if isinstance(reply, Failed):
        return reply
    items = parse_finnhub(symbol, reply.body, cik)
    return Failed(items, url=shown) if isinstance(items, str) else items


def massive_news(
    fetcher: Fetcher, key: str, symbol: str, start: date, cik: str | None = None
) -> list[RawItem] | Failed:
    params = {"ticker": symbol, "published_utc.gte": start.isoformat(), "order": "desc",
              "sort": "published_utc", "limit": "100"}  # fmt: skip
    shown = f"{MASSIVE_URL}?ticker={symbol}&published_utc.gte={start}"
    reply = fetcher.get(MASSIVE_URL, lane="massive", params=params,
                        headers={"Authorization": f"Bearer {key}"}, logged_url=shown)  # fmt: skip
    if isinstance(reply, Failed):
        return reply
    items = parse_massive(symbol, reply.body, cik)
    return Failed(items, url=shown) if isinstance(items, str) else items
