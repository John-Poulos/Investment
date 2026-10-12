"""First-mention flags and size for candidate companies (D-M02-15, D-M02-50, D-M02-52 (5)).

Size = public float from the 10-K cover (`dei:EntityPublicFloat`), read for all filers
through SEC's quarter-end instant frames (the last five), each company's latest value,
labelled "float" with its as-of date and accession. Missing → "size unknown" (20-F/40-F
filers, new registrants), never small; a reported $0 → "no public float". Nano (< $50M)
flags on its own; micro (< $250M) flags only beside another flag.

Other flags come from the company's submissions JSON (one request, cached a day), around
its first stored mention of the theme: a rename (SEC's former-names list, within 180
days), a share offering (S-1, S-3, F-1, F-3 or a 424B prospectus within 90 days) and
reverse-merger or shell signs (8-K Items 2.01 with 5.01, or 5.06, within 180 days). A
rename is read from former names rather than 8-K Item 5.03, which also covers every
charter or bylaw amendment.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from engine.sec.client import SecClient
from engine.sec.frames import fetch_frame
from engine.sec.identity import SUBMISSIONS_URL
from engine.sec.results import Failed, Ok
from engine.sec.submissions import parse_filing_arrays

NANO, MICRO = 50e6, 250e6
FLOAT_FRAMES = 5
OFFERING_FORMS = ("S-1", "S-1/A", "S-3", "S-3/A", "F-1", "F-1/A", "F-3", "F-3/A",
                  "424B1", "424B2", "424B3", "424B4", "424B5")  # fmt: skip
OFFERING_DAYS, RENAME_DAYS, MERGER_DAYS = 90, 180, 180


def float_frames(today: date, n: int = FLOAT_FRAMES) -> list[str]:
    """The last `n` quarter-end instant frames ending before today (CY2026Q2I …)."""
    y, q = today.year, (today.month - 1) // 3  # quarter before the current one
    out = []
    for _ in range(n):
        if q == 0:
            y, q = y - 1, 4
        out.append(f"CY{y}Q{q}I")
        q -= 1
    return out


def ensure_floats(client: SecClient, engine: sqlite3.Connection, today: date,
                  now: datetime) -> list[str]:  # fmt: skip
    """Store the float frames (cached 30 days by `fetch_frame`); returns problems."""
    problems = []
    for period in float_frames(today):
        res = fetch_frame(client, engine, "dei", "EntityPublicFloat", "USD", period, now)
        if isinstance(res, Failed):
            problems.append(f"{period}: {res.reason}")
    return problems


@dataclass(frozen=True)
class Size:
    value: float | None
    as_of: str | None
    accession: str | None
    label: str

    @property
    def nano(self) -> bool:
        return self.value is not None and 0 < self.value < NANO

    @property
    def micro(self) -> bool:
        return self.value is not None and 0 < self.value < MICRO


def size_of(engine: sqlite3.Connection, cik: str) -> Size:
    r = engine.execute(
        "SELECT value, period_end, accession FROM frame_value WHERE taxonomy = 'dei' AND "
        "tag = 'EntityPublicFloat' AND cik = ? ORDER BY period_end DESC LIMIT 1", (cik,)
    ).fetchone()  # fmt: skip
    if r is None:
        return Size(None, None, None, "size unknown")
    v = float(r[0])
    if v == 0:
        label = "no public float (reported $0)"
    elif v < NANO:
        label = f"nano: float ${v / 1e6:,.1f}M"
    elif v < MICRO:
        label = f"micro: float ${v / 1e6:,.0f}M"
    else:
        label = f"float ${v / 1e9:,.2f}B" if v >= 1e9 else f"float ${v / 1e6:,.0f}M"
    return Size(v, r[1], r[2], label)


def _near(d: str | None, anchor: date, days: int) -> bool:
    if not d:
        return False
    try:
        return abs((date.fromisoformat(d[:10]) - anchor).days) <= days
    except ValueError:
        return False


_SUFFIX = re.compile(
    r"\b(?:incorporated|inc|corporation|corp|company|co|limited|ltd|plc|llc|lp|sa|nv|ag|"
    r"holdings?|group|the|de|nv|md)\b"
)


def _norm(name: str) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", name.lower())
    return " ".join(_SUFFIX.sub(" ", words).split())


def submission_flags(data: dict[str, Any], cik: str, first_mention: date) -> list[str]:
    """Rename, offering and reverse-merger/shell signs around the first mention."""
    flags = []
    # oldest first by end date (SEC lists them newest first), so the name that replaced each
    # one is the next in time, else the current name; a change of case, punctuation or
    # legal suffix is not a rename (live checks 1–2: QuickLogic, SharonAI)
    former = sorted(data.get("formerNames") or [], key=lambda f: str(f.get("to") or ""))
    names = [str(f.get("name") or "") for f in former]
    for i, f in enumerate(former):
        after = names[i + 1] if i + 1 < len(names) else str(data.get("name") or "")
        if _near(f.get("to"), first_mention, RENAME_DAYS) and _norm(names[i]) != _norm(after):
            flags.append(f"renamed {str(f.get('to'))[:10]} (was {f.get('name')})")
    recent = ((data.get("filings") or {}).get("recent")) or {}
    try:
        filings = parse_filing_arrays(cik, recent) if recent else []
    except KeyError, ValueError, TypeError:
        filings = []
    offers = sorted(
        {
            f"{f.form} {f.filed}"
            for f in filings
            if f.form in OFFERING_FORMS and _near(f.filed, first_mention, OFFERING_DAYS)
        }
    )
    if offers:
        flags.append("share offering: " + ", ".join(offers[:3]) + (" …" if len(offers) > 3 else ""))
    for f in filings:
        if f.form != "8-K" or not _near(f.filed, first_mention, MERGER_DAYS):
            continue
        if f.has_item("5.06"):
            flags.append(f"shell status change: 8-K {f.filed} (Item 5.06)")
        elif f.has_item("2.01") and f.has_item("5.01"):
            flags.append(f"reverse-merger signs: 8-K {f.filed} (Items 2.01 + 5.01)")
    return flags


def company_flags(client: SecClient | None, engine: sqlite3.Connection, cik: str,
                  first_mention: date) -> tuple[list[str], Size, str | None]:  # fmt: skip
    """(flags, size, problem). Without a client only the size is read."""
    size = size_of(engine, cik)
    flags: list[str] = []
    problem = None
    if client is not None:
        res = client.get_json(SUBMISSIONS_URL.format(cik=cik), ttl_s=20 * 3600)
        if isinstance(res, Ok) and isinstance(res.data, dict):
            flags = submission_flags(res.data, cik, first_mention)
        else:
            problem = f"submissions: {getattr(res, 'reason', res)}"
    if size.nano or (size.micro and flags):
        flags.append(size.label)
    return flags, size, problem


def days_ago(d: date, n: int) -> date:
    return d - timedelta(days=n)
