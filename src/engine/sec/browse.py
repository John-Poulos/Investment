"""EDGAR browse-by-SIC company lists (S162; D-M04-4; M04 Part 1c).

`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&SIC=<sic>&type=<form>&owner=include&count=100&start=<n>`
lists the companies EDGAR files under a 4-digit SIC, 100 per page (SIC 3674 with type
10-K: 6 pages, 505 companies, probe S1 2026-10-12). One browse per form type: 10-K, then
20-F and 40-F, so foreign filers such as GlobalFoundries are listed too (S1 re-probe,
SB.17). Pages are capped per SIC (default 10: 10-K up to 8, then 20-F and 40-F with what
is left); a list cut by the cap is marked partial, never silently short.

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
FORMS = ("10-K", "20-F", "40-F")
TTL_S = 7 * 86400
_ROW = re.compile(r"CIK=(\d{10})[^>]*>\s*\d{10}\s*</a>\s*</td>\s*<td[^>]*>([^<]+)", re.IGNORECASE)


def parse_browse(page: str) -> list[tuple[str, str]]:
    """(cik, name) rows of one browse page, in page order."""
    return [(cik, " ".join(html.unescape(name).split())) for cik, name in _ROW.findall(page)]


@dataclass
class FormBrowse:
    form: str
    pages: int = 0
    listed: int = 0
    capped: bool = False
    error: str = ""


@dataclass
class SicBrowse:
    sic: str
    forms: list[FormBrowse] = field(default_factory=list)
    companies: dict[str, tuple[str, str]] = field(default_factory=dict)  # cik → (name, form)

    @property
    def pages(self) -> int:
        return sum(f.pages for f in self.forms)

    @property
    def partial(self) -> bool:
        return any(f.capped or f.error for f in self.forms)

    @property
    def throttled(self) -> bool:
        return any("throttle" in f.error for f in self.forms)


def browse_sic(
    client: SecClient, sic: str, *, page_cap: int = PAGE_CAP, forms: tuple[str, ...] = FORMS
) -> SicBrowse:
    """Every company EDGAR lists under `sic` for each form type, within the page cap."""
    out = SicBrowse(sic)
    budget = page_cap
    for i, form in enumerate(forms):
        reserve = len(forms) - i - 1
        allowed = max(budget - reserve, 1 if budget > 0 else 0)
        fb = FormBrowse(form)
        out.forms.append(fb)
        start = 0
        while True:
            if fb.pages >= allowed:
                fb.capped = True
                break
            params = {"action": "getcompany", "SIC": sic, "type": form, "owner": "include",
                      "count": str(PER_PAGE), "start": str(start)}  # fmt: skip
            res = client.get_text(BROWSE_URL, params, ttl_s=TTL_S)
            fb.pages += 1
            if not isinstance(res, Ok):
                fb.error = (f"SEC throttle: {res.reason}" if isinstance(res, Failed)
                            and res.throttled else str(res))  # fmt: skip
                break
            rows = parse_browse(res.data)
            for cik, name in rows:
                out.companies.setdefault(cik, (name, form))
            fb.listed += len(rows)
            if len(rows) < PER_PAGE:
                break
            start += PER_PAGE
        budget -= fb.pages
        if fb.error and "throttle" in fb.error:
            break
    return out


def store(engine: sqlite3.Connection, b: SicBrowse, now: datetime) -> None:
    """Replace the SIC's stored listing (caller owns the transaction)."""
    ts = iso(now)
    engine.execute("DELETE FROM sic_listing WHERE sic = ?", (b.sic,))
    engine.execute("DELETE FROM sic_browse WHERE sic = ?", (b.sic,))
    engine.executemany(
        "INSERT OR IGNORE INTO sic_listing (sic, cik, name, browsed, fetched_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [(b.sic, cik, name, form, ts) for cik, (name, form) in b.companies.items()],
    )
    engine.executemany(
        "INSERT INTO sic_browse (sic, browsed, pages, listed, capped, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(b.sic, f.form, f.pages, f.listed, int(f.capped or bool(f.error)), ts) for f in b.forms],
    )
