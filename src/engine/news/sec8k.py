"""8-K press releases as news items (grade A; D-M02-58 (3)).

Local only: stored 8-Ks of watchlist/tracked companies with a stored EX-99.1, filed in
the last `days` days. Headline = the exhibit's first line that reads like one (skipping
"Exhibit 99.1", "Press release", contacts and dates); snippet = the text after it. The
same release from IR RSS or Finnhub is merged by the near-identical-headline rule.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime, timedelta

from engine.news.items import RawItem, clean, snippet
from engine.sec.client import iso

DAYS = 90
_SKIP = re.compile(
    r"^(exhibit|ex-)\s*99|^(press|news|media)\s+release|^for\s+immediate\s+release|"
    r"^(media|investor|press)\s+(contact|relations)|^contacts?\b|^source:|^\(?nasdaq|^\(?nyse",
    re.I,
)
_DATELINE = re.compile(
    r"^(january|february|march|april|may|june|july|august|september|october|november|"
    r"december)\s+\d{1,2},?\s+\d{4}$",
    re.I,
)


def _accepted(value: str | None) -> str | None:
    """SEC acceptance time ('…Z') as ISO UTC; None when absent or unreadable."""
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return iso(ts if ts.tzinfo else ts.replace(tzinfo=UTC))


def headline(text: str) -> tuple[str, int] | None:
    """(headline, offset after it) from the start of a release, or None."""
    pos = 0
    for n, line in enumerate(text.splitlines(keepends=True)):
        if n > 40:
            break
        t = clean(line)
        pos += len(line)
        words = t.split()
        if len(words) < 4 or len(t) > 250 or _SKIP.search(t) or _DATELINE.match(t):
            continue
        return t, pos
    return None


def releases(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    ciks: set[str],
    now: datetime,
    days: int = DAYS,
) -> list[RawItem]:
    if not ciks:
        return []
    since = (now - timedelta(days=days)).date().isoformat()
    marks = ",".join("?" * len(ciks))
    filings = engine.execute(
        f"SELECT accession, cik, filed, accepted_at FROM filing WHERE cik IN ({marks}) "
        f"AND form IN ('8-K', '8-K/A') AND filed >= ? ORDER BY filed",
        (*sorted(ciks), since),
    ).fetchall()
    out = []
    for f in filings:
        doc = corpus.execute(
            "SELECT url, text FROM document WHERE accession = ? AND doc_type = 'EX-99.1' "
            "ORDER BY doc_id LIMIT 1",
            (f["accession"],),
        ).fetchone()
        if doc is None:
            continue
        h = headline(doc["text"])
        if h is None:
            continue
        title, offset = h
        published = _accepted(f["accepted_at"]) or f["filed"]
        out.append(
            RawItem(
                channel="sec_8k",
                feed=f["accession"],
                title=title,
                url=doc["url"],
                published_at=published,
                snippet=snippet(doc["text"][offset : offset + 2000]),
                origin="sec.gov",
                cik=f["cik"],
            )
        )
    return out
