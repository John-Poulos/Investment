"""CUSIP issuer → SEC company for 13F rows (D-M02-42: stored only on exactly one match).

Order: the issuer map (first six CUSIP characters; learned from 13D/G XML, which states
`issuerCik` with `issuerCusipNumber`, or mapped by the owner) → the issuer name against
SEC's company names (ticker list and stored entities), normalized; 13F names are often
cut short ("SPACE EXPLORATION TECHN CORP"), so the last word may be a prefix. More than
one company, or none → the row waits for the owner (`m02_13f_issuer`: map or dismiss).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from engine.sec.client import iso

_SUFFIX = {
    "INC",
    "INCORPORATED",
    "CORP",
    "CORPORATION",
    "CO",
    "COMPANY",
    "LTD",
    "LIMITED",
    "PLC",
    "NV",
    "SA",
    "AG",
    "SE",
    "LLC",
    "LP",
    "THE",
    "NEW",
    "DE",
    "CL",
    "CLASS",
    "A",
    "B",
}


# 13F issuer names are abbreviated and cut at ~28 characters (live check 1, D-M02-47):
# "CROWDSTRIKE HLDGS INC", "AIR TRANSPORT SERVICES GRP I", "RECURSION PHARMACEUTICALS IN"
_ABBREV = {
    "HLDGS": "HOLDINGS", "HLDG": "HOLDING", "HLDNGS": "HOLDINGS", "GRP": "GROUP",
    "INTL": "INTERNATIONAL", "SVCS": "SERVICES", "MFG": "MANUFACTURING", "COS": "COMPANIES",
    "TECHS": "TECHNOLOGIES", "SYS": "SYSTEMS", "PHARMS": "PHARMACEUTICALS",
}  # fmt: skip


def norm(name: str) -> tuple[str, ...]:
    """'INTEL CORPORATION' → ('INTEL',); 'Nebius Group N.V.' → ('NEBIUS', 'GROUP')."""
    s = name.upper().replace("&", " AND ")
    # state or country suffix in SEC names: "APPLE INC /CA/", "ARM HOLDINGS PLC /UK"
    s = re.sub(r"/[A-Z]{2,3}/?", " ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s.replace(".", ""))
    words = [_ABBREV.get(w, w) for w in s.split()]
    # a suffix cut short at the field width ("… IN", "… PL", "… GRP I")
    if len(words) > 1 and words[-1] not in _SUFFIX and any(
        x.startswith(words[-1]) and x != words[-1] for x in ("INC", "INCORPORATED", "PLC", "CORP",
                                                              "CORPORATION", "LTD", "LIMITED")
    ):  # fmt: skip
        words.pop()
    while words and words[-1] in _SUFFIX:
        words.pop()
    while words and words[0] == "THE":
        words.pop(0)
    return tuple(words)


class Names:
    """Normalized SEC company names → CIKs (ticker list + stored entities)."""

    def __init__(self, engine: sqlite3.Connection) -> None:
        self.by_name: dict[tuple[str, ...], set[str]] = {}
        for r in engine.execute(
            "SELECT name, cik FROM ticker WHERE valid_to IS NULL AND name IS NOT NULL "
            "UNION SELECT name, cik FROM entity"
        ):
            key = norm(r[0])
            if key:
                self.by_name.setdefault(key, set()).add(r[1])

    def match(self, name: str) -> set[str]:
        key = norm(name)
        if not key:
            return set()
        if key in self.by_name:
            return set(self.by_name[key])
        # a cut-short last word: same words before it, the last one a prefix (≥ 4 letters)
        if len(key[-1]) < 4:
            return set()
        out: set[str] = set()
        for k, ciks in self.by_name.items():
            if len(k) == len(key) and k[:-1] == key[:-1] and k[-1].startswith(key[-1]):
                out |= ciks
        return out


def mapped(engine: sqlite3.Connection, cusip: str) -> sqlite3.Row | None:
    return engine.execute(
        "SELECT * FROM fin_issuer_map WHERE cusip6 = ?", (cusip[:6].upper(),)
    ).fetchone()


def resolve(
    engine: sqlite3.Connection, names: Names, cusip: str, name: str
) -> tuple[str | None, str]:
    """(cik, how); cik None with how 'dismissed' | 'ambiguous (n)' | 'no match'."""
    m = mapped(engine, cusip)
    if m is not None:
        return (m["cik"], m["source"]) if m["cik"] else (None, "dismissed")
    # the same issuer already resolved under another name ("Mobileye, Inc." / "Mobileye
    # Global Inc." share CUSIP 60741F)
    same = {
        r[0]
        for r in engine.execute(
            "SELECT DISTINCT issuer_cik FROM fin_holding WHERE substr(cusip, 1, 6) = ? AND "
            "issuer_cik IS NOT NULL AND status NOT IN ('wrong', 'dismissed')",
            (cusip[:6].upper(),),
        )
    }
    if len(same) == 1:
        return next(iter(same)), "same CUSIP"
    ciks = names.match(name)
    if len(ciks) == 1:
        return next(iter(ciks)), "name"
    return None, f"ambiguous ({len(ciks)})" if ciks else "no match"


def learn(engine: sqlite3.Connection, cusip: str, cik: str, name: str, now: datetime) -> None:
    """A 13D/G schedule states the issuer's CIK with its CUSIP; the owner's map wins."""
    if not cusip or len(cusip) < 6 or not cik:
        return
    engine.execute(
        "INSERT INTO fin_issuer_map (cusip6, cik, name, source, mapped_at) "
        "VALUES (?, ?, ?, '13D/G', ?) ON CONFLICT (cusip6) DO NOTHING",
        (cusip[:6].upper(), cik.zfill(10), name, iso(now)),
    )


def owner_map(
    engine: sqlite3.Connection, cusip: str, target: str | None, by: str, now: datetime
) -> str | None:
    """Map a CUSIP issuer to a ticker or CIK (None = dismiss) → the CIK. Raises ValueError."""
    cik = None
    if target:
        t = target.strip().upper()
        if t.isdigit():
            cik = t.zfill(10)
        else:
            row = engine.execute(
                "SELECT cik FROM ticker WHERE ticker = ? AND valid_to IS NULL", (t,)
            ).fetchone()
            if row is None:
                raise ValueError(f"No current ticker {t}. Enter a ticker or a CIK.")
            cik = row[0]
    name = None
    if cik:
        row = engine.execute(
            "SELECT name FROM entity WHERE cik = ? UNION ALL SELECT name FROM ticker "
            "WHERE cik = ? AND name IS NOT NULL LIMIT 1",
            (cik, cik),
        ).fetchone()
        name = row[0] if row else None
    engine.execute(
        "INSERT INTO fin_issuer_map (cusip6, cik, name, source, mapped_by, mapped_at) "
        "VALUES (?, ?, ?, 'owner', ?, ?) ON CONFLICT (cusip6) DO UPDATE SET cik = excluded.cik, "
        "name = excluded.name, source = 'owner', mapped_by = excluded.mapped_by, "
        "mapped_at = excluded.mapped_at",
        (cusip[:6].upper(), cik, name, by, iso(now)),
    )
    return cik
