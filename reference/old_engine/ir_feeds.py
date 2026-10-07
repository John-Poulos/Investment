import os
import time
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from typing import Optional
from dotenv import load_dotenv
from config.settings import LOOKBACK_DAYS
from utils.text import sanitize_source_text

load_dotenv()

# SEC requires a descriptive User-Agent — reuse the one from sec_edgar.py
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "PharmaAgent contact@pharmaagent.com")

REQUEST_DELAY = 0.2

# ---------------------------------------------------------------------------
# Confirmed working direct IR feeds (tested live)
# Foreign filers (NVO, AZN) use EDGAR RSS — see EDGAR helpers below
# ---------------------------------------------------------------------------

DIRECT_IR_FEEDS: dict[str, list[str]] = {
    "LLY":  ["https://investor.lilly.com/rss/news-releases.xml"],
    "PFE":  ["https://www.pfizer.com/news/press-releases/press-releases-rss-feed"],
    "AMGN": ["https://www.amgen.com/media/news-releases/rss"],
    "MRK":  ["https://www.merck.com/media/news/rss-feeds/press-releases.xml"],
    "BMY":  ["https://news.bms.com/rss/news-releases.xml"],
    "ABBV": ["https://news.abbvie.com/rss/news-releases.xml"],
    "JNJ":  ["https://www.jnj.com/latest-news/rss.xml"],
}

# Foreign filers — primary source is EDGAR 6-K RSS
FOREIGN_FILERS = {"NVO", "AZN", "RHHBY", "NONOF"}

# Known CIKs for major foreign filers — avoids a CIK lookup API call
# Add more as needed; format is zero-padded 10-digit CIK
KNOWN_CIKS: dict[str, str] = {
    "NVO":   "0000353278",
    "AZN":   "0000901832",
    "RHHBY": "0001037346",
    "NONOF": "0000353278",
}

EDGAR_6K_RSS = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcompany&CIK={cik}&type=6-K"
    "&dateb=&owner=include&count=10&search_text=&output=atom"
)
EDGAR_8K_RSS = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcompany&CIK={cik}&type=8-K"
    "&dateb=&owner=include&count=10&search_text=&output=atom"
)

INDUSTRY_FEEDS: list[str] = [
    "https://www.fiercepharma.com/rss/xml",
    "https://www.fiercebiotech.com/rss/xml",
    "https://www.biopharmadive.com/feeds/news/",
    "https://endpts.com/feed/",
    "https://www.statnews.com/feed/",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_rss(url: str, use_sec_headers: bool = False) -> feedparser.FeedParserDict:
    """
    Fetch an RSS/Atom feed.

    For standard feeds: uses feedparser directly (handles redirects, encoding).
    For SEC EDGAR feeds: fetches with requests (proper User-Agent) then
    passes raw content to feedparser — SEC blocks feedparser's default UA.
    """
    time.sleep(REQUEST_DELAY)

    if use_sec_headers:
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": SEC_USER_AGENT},
                timeout=15
            )
            resp.raise_for_status()
            return feedparser.parse(resp.content)
        except requests.RequestException as e:
            print(f"    EDGAR feed error ({url[:60]}): {e}")
            return feedparser.FeedParserDict()
    else:
        return feedparser.parse(url)


def _clean_entry(entry: dict, source_name: str, keywords: list[str],
                 require_keywords: bool = True) -> Optional[dict]:
    # R4b: this channel always decoded correctly (tags -> unescape -> collapse)
    # but as a private copy. One owner now: utils.text.sanitize_source_text,
    # same three steps, so the output is identical by construction.
    def clean(raw: str) -> str:
        return sanitize_source_text(raw) if raw else ""

    title = clean(entry.get("title", ""))
    body  = clean(
        entry.get("summary") or entry.get("description") or
        (entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "")
    )
    blob = (title + " " + body).lower()

    if require_keywords and keywords:
        if not any(kw.lower() in blob for kw in keywords):
            return None

    return {
        "source":  source_name,
        "title":   title or "N/A",
        "snippet": body[:300],
        "url":     entry.get("link", entry.get("id", "N/A")),
        "date":    entry.get("published", entry.get("updated", "N/A")),
    }


def _is_recent(date_str: str, days_back: int) -> bool:
    if not date_str or date_str == "N/A":
        return True
    fmts = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
    ]
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)
    for fmt in fmts:
        try:
            pub = datetime.strptime(date_str, fmt)
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            return pub >= cutoff
        except ValueError:
            continue
    return True


def _process_feed(
    url: str,
    source_name: str,
    keywords: list[str],
    days_back: int,
    max_results: int,
    require_keywords: bool = True,
    use_sec_headers: bool = False,
) -> list[dict]:
    """Fetch, filter, and clean one RSS/Atom feed."""
    results = []
    try:
        feed = _fetch_rss(url, use_sec_headers=use_sec_headers)
        if not feed.entries:
            return []
        for entry in feed.entries:
            date_str = entry.get("published", entry.get("updated", ""))
            if not _is_recent(date_str, days_back):
                continue
            parsed = _clean_entry(entry, source_name, keywords, require_keywords)
            if parsed:
                results.append(parsed)
            if len(results) >= max_results:
                break
    except Exception as e:
        print(f"    Feed error ({url[:60]}): {e}")
    return results


def _edgar_rss_url(ticker: str, form: str) -> str:
    """Build EDGAR RSS URL using known CIK or ticker as fallback."""
    cik = KNOWN_CIKS.get(ticker.upper(), ticker.upper())
    template = EDGAR_6K_RSS if form == "6-K" else EDGAR_8K_RSS
    return template.format(cik=cik)


# ---------------------------------------------------------------------------
# PUBLIC FUNCTION 1 — Company IR feeds
# ---------------------------------------------------------------------------

def monitor_company_feeds(
    tickers: list[str],
    keywords: list[str],
    days_back: Optional[int] = None,
    max_per_company: int = 5,
) -> list[dict]:
    """
    Monitor investor relations press releases for competitor companies.

    Strategy:
      - US companies: direct IR RSS feed (keyword filtered)
      - Foreign filers (NVO, AZN): EDGAR 6-K RSS (keyword filtered)
        Uses requests + User-Agent to bypass SEC's feedparser block
      - Universal fallback: EDGAR 8-K/6-K RSS (no keyword filter)
        Flags any corporate filing — material events matter regardless
        of whether they mention the specific drug by name

    Args:
        tickers:         Competitor tickers from parse_query
        keywords:        Drug/target terms for filtering
        days_back:       Lookback window. Default: LOOKBACK_DAYS
        max_per_company: Max results per company. Default: 5
    """
    days_back = days_back or LOOKBACK_DAYS
    results   = []

    for ticker in tickers:
        t    = ticker.upper()
        hits = []

        # Tier 1a: direct IR RSS for US domestic companies
        for url in DIRECT_IR_FEEDS.get(t, []):
            hits.extend(_process_feed(
                url, f"{t} IR", keywords,
                days_back, max_per_company,
                require_keywords=True,
                use_sec_headers=False,
            ))
            if len(hits) >= max_per_company:
                break

        # Tier 1b: EDGAR 6-K for foreign filers
        if not hits and t in FOREIGN_FILERS:
            url = _edgar_rss_url(t, "6-K")
            hits.extend(_process_feed(
                url, f"{t} (SEC 6-K)", keywords,
                days_back, max_per_company,
                require_keywords=True,
                use_sec_headers=True,   # requests + SEC User-Agent
            ))

        # Tier 2: EDGAR fallback — no keyword filter, flag all filings
        if not hits:
            form = "6-K" if t in FOREIGN_FILERS else "8-K"
            url  = _edgar_rss_url(t, form)
            raw  = _process_feed(
                url, f"{t} (SEC {form})", keywords,
                days_back, max_per_company,
                require_keywords=False,
                use_sec_headers=True,
            )
            for h in raw:
                h["note"] = f"SEC {form} — no keyword match, flagged for review"
            hits.extend(raw)

        print(f"    {t} IR: {len(hits[:max_per_company])} releases")
        results.extend(hits[:max_per_company])

    return results


# ---------------------------------------------------------------------------
# PUBLIC FUNCTION 2 — Industry news
# ---------------------------------------------------------------------------

def monitor_industry_news(
    keywords: list[str],
    days_back: Optional[int] = None,
    max_results: int = 10,
) -> list[dict]:
    """
    Monitor pharma/biotech trade publications for keyword mentions.
    Sources: FiercePharma, FierceBiotech, BioPharma Dive, Endpoints, STAT.
    """
    days_back = days_back or LOOKBACK_DAYS
    results   = []

    for url in INDUSTRY_FEEDS:
        if len(results) >= max_results:
            break
        hits = _process_feed(
            url, url.split("/")[2], keywords,
            days_back, max_results - len(results),
            require_keywords=True,
            use_sec_headers=False,
        )
        results.extend(hits)

    print(f"    Industry news: {len(results)} relevant items")
    return results


# ---------------------------------------------------------------------------
# ENTRY POINT for runner.py
# ---------------------------------------------------------------------------

def search_ir_and_news(
    tickers: list[str],
    keywords: list[str],
    days_back: Optional[int] = None,
) -> dict:
    """
    Combined entry point for runner.py.

    Args:
        tickers:   Competitor tickers from parse_query
        keywords:  Drug/target keywords from parse_query
        days_back: Lookback window

    Returns:
        {"company_releases": [...], "industry_news": [...]}
    """
    print(f"  Monitoring IR feeds for: {tickers}")
    print(f"  Keywords: {keywords[:4]}")

    return {
        "company_releases": monitor_company_feeds(tickers, keywords, days_back),
        "industry_news":    monitor_industry_news(keywords, days_back),
    }