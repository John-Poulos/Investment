"""A news item as one source gives it, and the text rules shared by every adapter.

Stored: headline, link, date and a snippet of at most 300 characters (D-M02-2), even when
a feed carries full text. A missing date stays missing (never the fetch date).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SNIPPET_MAX = 300

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"[a-z0-9]+")
# tracking parameters dropped before URLs are compared
_TRACKING = re.compile(r"^(utm_|mc_|fbclid$|gclid$|ref$|cmpid$|src$|ncid$|guccounter$)")


@dataclass(frozen=True)
class RawItem:
    channel: str  # ir_rss, finnhub, massive, trade, sec_8k
    feed: str  # ticker, outlet key or accession
    title: str
    url: str | None
    published_at: str | None  # ISO UTC, or None when the source gives no date
    snippet: str | None
    origin: str | None = None  # domain or vendor source name the grade is based on
    tickers: tuple[str, ...] = ()  # the vendor's own ticker tag (Finnhub/Massive)
    cik: str | None = None  # the company whose feed or filing this is


def clean(text: str | None) -> str:
    """HTML tags removed, entities decoded, whitespace collapsed."""
    if not text:
        return ""
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", text))).strip()


def snippet(text: str | None, limit: int = SNIPPET_MAX) -> str | None:
    """At most `limit` characters, cut at a word boundary with an ellipsis."""
    t = clean(text)
    if not t:
        return None
    if len(t) <= limit:
        return t
    cut = t[: limit - 1]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit // 2 else cut).rstrip(" ,;:-") + "…"


def url_key(url: str | None) -> str | None:
    """Scheme, 'www.', fragment, tracking parameters and a trailing slash removed;
    None for vendor redirect links (they differ per vendor for the same article)."""
    if not url:
        return None
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if not host or host.endswith("finnhub.io"):
        return None
    host = host[4:] if host.startswith("www.") else host
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query)
                             if not _TRACKING.match(k.lower())))  # fmt: skip
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("", host, path, query, ""))[2:]


def title_key(title: str) -> str:
    return " ".join(_WORD.findall(title.lower()))


def title_words(title: str) -> set[str]:
    return set(_WORD.findall(title.lower()))


def similar(a: str, b: str, threshold: float = 0.7) -> bool:
    """Near-identical headlines: word-set overlap (Jaccard) ≥ threshold."""
    wa, wb = title_words(a), title_words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= threshold
