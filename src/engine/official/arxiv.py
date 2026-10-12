"""arXiv: new preprints per theme phrase per calendar month (D-M02-13, D-M02-60).

Research momentum, never money flow (D-M02-15). API: `GET export.arxiv.org/api/query` with
`search_query=all:"<phrase>" AND submittedDate:[YYYYMMDD0000 TO YYYYMMDD2359]` (GMT);
the count is the Atom feed's `opensearch:totalResults`. arXiv asks for 3 s between calls
and one connection (lane `arxiv`); results change once a day, so each completed month is
counted once per phrase (a month is counted ≥ 3 days after it ends). An error comes back
as a feed whose single entry has an `api/errors` id → Failed, never a count of 0.

Bounded: `max_requests` per run; months are filled newest first, back to `BACKFILL_MONTHS`
(the backfill completes over several runs). A 429 stops arXiv for the run.
"""

from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from engine.news.fetch import Fetcher
from engine.official.common import Budget, Phrase, distinct_phrases, write
from engine.sec.client import iso
from engine.sec.results import Failed

URL = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"
BACKFILL_MONTHS = 24
SETTLE_DAYS = 3


def months_due(today: date, back: int = BACKFILL_MONTHS) -> list[str]:
    """Completed months (newest first) that ended at least SETTLE_DAYS ago."""
    last = today - timedelta(days=SETTLE_DAYS)
    y, m = last.year, last.month - 1  # the month before the settled day's month
    if m == 0:
        y, m = y - 1, 12
    out = []
    for _ in range(back):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def query(phrase: str, month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    last = monthrange(y, m)[1]
    words = " ".join(phrase.replace('"', " ").split())
    return f'all:"{words}" AND submittedDate:[{y:04d}{m:02d}010000 TO {y:04d}{m:02d}{last:02d}2359]'


def parse_total(body: bytes) -> int | str:
    """totalResults, or an error text."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        return f"unreadable feed: {e}"
    for entry in root.iter(f"{ATOM}entry"):
        eid = entry.findtext(f"{ATOM}id") or ""
        if "api/errors" in eid:
            return "arXiv error: " + (entry.findtext(f"{ATOM}summary") or "").strip()[:200]
    total = root.findtext(f"{OPENSEARCH}totalResults")
    if total is None or not total.strip().isdigit():
        return "no opensearch:totalResults in the reply"
    return int(total.strip())


def count(fetcher: Fetcher, phrase: str, month: str) -> int | Failed:
    q = query(phrase, month)
    got = fetcher.get(URL, lane="arxiv",
                      params={"search_query": q, "start": "0", "max_results": "1"},
                      logged_url=f"{URL}?search_query={q}")  # fmt: skip
    if isinstance(got, Failed):
        return got
    n = parse_total(got.body)
    return Failed(n, url=URL) if isinstance(n, str) else n


@dataclass
class ArxivResult:
    counted: int = 0
    due: int = 0  # (phrase, month) pairs still missing after this run
    failures: list[str] = field(default_factory=list)
    stopped: str = ""


def run(
    engine: sqlite3.Connection,
    fetcher: Fetcher,
    phrases: list[Phrase],
    now: datetime,
    budget: Budget,
    *,
    max_requests: int = 20,
    back: int = BACKFILL_MONTHS,
) -> ArxivResult:
    res = ArxivResult()
    have = {(r[0], r[1]) for r in engine.execute("SELECT phrase, month FROM arxiv_count")}
    todo = [(m, p) for m in months_due(now.date(), back) for p in distinct_phrases(phrases)
            if (p.lower(), m) not in have]  # fmt: skip
    for i, (month, phrase) in enumerate(todo):
        if i >= max_requests:
            res.stopped = f"request cap {max_requests} reached"
            break
        if budget.spent("arxiv"):
            res.stopped = "time budget spent"
            break
        n = count(fetcher, phrase, month)
        if isinstance(n, Failed):
            res.failures.append(f"{phrase} {month}: {n.reason}")
            if n.throttled:
                res.stopped = "throttled (HTTP 429)"
                break
            continue
        with write(engine):
            engine.execute(
                "INSERT OR REPLACE INTO arxiv_count (phrase, month, n, query, fetched_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (phrase.lower(), month, n, query(phrase, month), iso(now)),
            )
        res.counted += 1
    res.due = len(todo) - res.counted
    return res
