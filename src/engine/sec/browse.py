"""EDGAR browse-by-SIC company lists (S162; D-M04-4; M04 Part 1c).

`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&SIC=<sic>&type=10-K&owner=include&count=100&start=<n>`
lists the companies EDGAR files under a 4-digit SIC, 100 per page (SIC 3674: 6 pages, 505
companies, probe S1 2026-10-12). One browse per SIC: the `type` parameter does not filter
the company list (live check 1: SIC 3571 gave 114 companies on the 10-K, 20-F and 40-F
browses alike, SIC 3711 153), so foreign filers such as GlobalFoundries are on it; which
names are active comes from the stored form indexes (10-K/20-F/40-F families,
`financials/peers.py`). `type=10-K` stays in the request so cached pages are re-used.
Pages are capped at 10 per SIC; the list is marked partial only when the last page read
was full (a short page is the end of the list), never silently short.

The page is HTML: a results table whose rows hold the CIK link and the company name.
Names are unescaped (`&amp;` → `&`) and kept as EDGAR writes them (never re-cased).
"""

from __future__ import annotations

import html
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from engine.sec.client import SecClient, iso
from engine.sec.results import Failed, Ok

BROWSE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
PER_PAGE = 100
PAGE_CAP = 10  # per SIC (≤ 9 SICs → ≤ 90 pages)
BROWSE_FORM = "10-K"  # the request's type parameter; it does not filter the list
TTL_S = 7 * 86400
_ROW = re.compile(r"CIK=(\d{10})[^>]*>\s*\d{10}\s*</a>\s*</td>\s*<td[^>]*>([^<]+)", re.IGNORECASE)


def parse_browse(page: str) -> list[tuple[str, str]]:
    """(cik, name) rows of one browse page, in page order."""
    return [(cik, " ".join(html.unescape(name).split())) for cik, name in _ROW.findall(page)]


@dataclass
class SicBrowse:
    sic: str
    pages: int = 0
    listed: int = 0  # rows read (a CIK repeated across pages counts once in `companies`)
    capped: bool = False  # the cap was reached on a full page: more companies may exist
    error: str = ""
    companies: dict[str, str] = field(default_factory=dict)  # cik → name

    @property
    def partial(self) -> bool:
        return self.capped or bool(self.error)

    @property
    def throttled(self) -> bool:
        return "throttle" in self.error


def browse_sic(client: SecClient, sic: str, *, page_cap: int = PAGE_CAP) -> SicBrowse:
    """Every company EDGAR lists under `sic`, within the page cap."""
    out = SicBrowse(sic)
    start = 0
    while out.pages < page_cap:
        params = {"action": "getcompany", "SIC": sic, "type": BROWSE_FORM, "owner": "include",
                  "count": str(PER_PAGE), "start": str(start)}  # fmt: skip
        res = client.get_text(BROWSE_URL, params, ttl_s=TTL_S)
        out.pages += 1
        if not isinstance(res, Ok):
            out.error = (f"SEC throttle: {res.reason}" if isinstance(res, Failed)
                         and res.throttled else str(res))  # fmt: skip
            break
        rows = parse_browse(res.data)
        for cik, name in rows:
            out.companies.setdefault(cik, name)
        out.listed += len(rows)
        if len(rows) < PER_PAGE:
            break  # a short page ends the list
        if out.pages >= page_cap:
            out.capped = True  # the last page read was full
            break
        start += PER_PAGE
    return out


def store(engine: sqlite3.Connection, b: SicBrowse, now: datetime) -> None:
    """Replace the SIC's stored listing and its one browse row (rows from the earlier
    per-form browses are dropped with it). Caller owns the transaction."""
    ts = iso(now)
    engine.execute("DELETE FROM sic_listing WHERE sic = ?", (b.sic,))
    engine.execute("DELETE FROM sic_browse WHERE sic = ?", (b.sic,))
    engine.executemany(
        "INSERT OR IGNORE INTO sic_listing (sic, cik, name, browsed, fetched_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [(b.sic, cik, name, BROWSE_FORM, ts) for cik, name in b.companies.items()],
    )
    engine.execute(
        "INSERT INTO sic_browse (sic, browsed, pages, listed, capped, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (b.sic, BROWSE_FORM, b.pages, len(b.companies), int(b.partial), ts),
    )
