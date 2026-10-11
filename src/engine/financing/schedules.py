"""Schedule 13D/13G stakes, XML schedules only (D-M02-45 (2)).

The submissions list of a company holds schedules it filed and schedules others filed
about it (mostly funds); only the filing index header says which (`… (Filed by)` /
`… (Subject)`, each with its CIK). The header of every XML schedule (forms
`SCHEDULE 13D/G[/A]`, filed from Dec 2024) listed under our companies is read once; the
XML is read when one of our companies is the filer, or when both sides are known
companies (watchlist, tracked, `config/aliases.toml`). Probe 2026-10-10: the 13G XML
states `issuerCik`, `issuerCusipNumber`, `issuerName`, per reporting person the shares
(`reportingPersonBeneficiallyOwnedAggregateNumberOfShares`) and `classPercent`.
The issuer's CIK and CUSIP also teach the 13F issuer map.
"""

from __future__ import annotations

import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime

from engine.financing import issuers
from engine.financing.thirteenf import DOC_TTL_S, suppressed
from engine.sec.client import SecClient, iso
from engine.sec.documents import filing_folder, parse_filing_index
from engine.sec.results import Failed, NotFound, Ok

FORMS = ("SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A")
XML_FROM = "2024-12-18"  # EDGAR schedules 13D/G in XML from this date
_ROLE = re.compile(
    r'companyName">\s*([^<(]+?)\s*\((Subject|Filed by|Reporting|Filer)\).{0,400}?'
    r"(\d{10})",
    re.IGNORECASE | re.DOTALL,
)
_FIELDS = {
    "issuer_cik": ("issuercik",),
    "cusip": ("issuercusipnumber", "issuercusip", "cusipnumber"),
    "issuer_name": ("issuername",),
    "event": ("eventdaterequiresfilingthisstatement", "dateofevent"),
    "shares": ("reportingpersonbeneficiallyownedaggregatenumberofshares", "aggregateamountowned"),
    "pct": ("classpercent", "percentofclass"),
}


@dataclass
class ReportSchedules:
    headers: int = 0
    relevant: int = 0
    stakes: int = 0
    problems: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [
            f"13D/13G: {self.headers} schedule header(s) read, {self.relevant} filed by or "
            f"between our companies, {self.stakes} stake(s) stored"
        ]
        return out + [f"  problem: {p}" for p in self.problems]


def parse_header(html: str) -> dict[str, tuple[str, str]]:
    """{'filer': (cik, name), 'subject': (cik, name)} from the filing index page."""
    out: dict[str, tuple[str, str]] = {}
    for name, role, cik in _ROLE.findall(html):
        key = "subject" if role.lower() == "subject" else "filer"
        out.setdefault(key, (cik, " ".join(name.split())))
    return out


def _leaves(root: ET.Element) -> list[tuple[str, str]]:
    return [
        (el.tag.rsplit("}", 1)[-1].lower(), (el.text or "").strip())
        for el in root.iter()
        if len(el) == 0 and (el.text or "").strip()
    ]


def _number(s: str) -> float | None:
    try:
        return float(s.replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def parse_schedule(xml: bytes) -> dict:
    """Issuer CIK, CUSIP, name, event date; the largest stake among reporting persons
    (group members repeat the same shares)."""
    leaves = _leaves(ET.fromstring(xml))
    out: dict = {}
    for key in ("issuer_cik", "cusip", "issuer_name", "event"):
        out[key] = next((v for k, v in leaves if k in _FIELDS[key]), None)
    shares = [n for k, v in leaves if k in _FIELDS["shares"] if (n := _number(v)) is not None]
    pcts = [n for k, v in leaves if k in _FIELDS["pct"] if (n := _number(v)) is not None]
    out["shares"] = max(shares) if shares else None
    out["pct"] = max(pcts) if pcts else None
    if out["event"] and re.fullmatch(r"\d{2}/\d{2}/\d{4}", out["event"]):
        m, d, y = out["event"].split("/")
        out["event"] = f"{y}-{m}-{d}"
    return out


def due(engine: sqlite3.Connection, ciks: list[str]) -> list[sqlite3.Row]:
    marks, fm = ",".join("?" * len(ciks)), ",".join("?" * len(FORMS))
    return engine.execute(
        f"SELECT DISTINCT f.accession, f.form, f.filed, c.cik AS listed_cik FROM filing f "
        f"JOIN filing_cik c ON c.accession = f.accession WHERE c.cik IN ({marks}) "
        f"AND f.form IN ({fm}) AND f.filed >= ? AND f.accession NOT IN "
        "(SELECT accession FROM fin_schedule) ORDER BY f.filed DESC",
        (*ciks, *FORMS, XML_FROM),
    ).fetchall()


def run(
    client: SecClient | None,
    engine: sqlite3.Connection,
    ours: set[str],
    known: set[str],
    now: datetime,
    rep: ReportSchedules,
) -> None:
    if client is None:
        return
    seen: set[str] = set()
    for f in due(engine, sorted(ours)):
        if f["accession"] in seen:
            continue
        seen.add(f["accession"])
        folder = filing_folder(f["listed_cik"], f["accession"])
        res = client.get_text(f"{folder}/{f['accession']}-index.htm", ttl_s=DOC_TTL_S)
        if isinstance(res, Failed) and res.throttled:
            rep.problems.append(f"{f['accession']}: throttled")
            return
        if not isinstance(res, Ok):
            if isinstance(res, NotFound):
                _header(engine, f, {}, False, "no index page", now)
            else:
                rep.problems.append(f"{f['accession']}: {getattr(res, 'reason', res)}")
            continue
        head = parse_header(res.data)
        rep.headers += 1
        filer = head.get("filer", (None, None))[0]
        subject = head.get("subject", (None, None))[0]
        relevant = bool(filer in ours or (subject in known and filer in known))
        _header(engine, f, head, relevant, None, now)
        if not relevant:
            continue
        rep.relevant += 1
        try:
            docs = parse_filing_index(res.data)
        except ValueError as e:
            rep.problems.append(f"{f['accession']}: {e}")
            continue
        doc = next(
            (d for d in docs if d.filename.lower().endswith(".xml") and "xsl" not in d.url.lower()),
            None,
        )
        if doc is None:
            continue
        x = client.get_bytes(doc.url, ttl_s=DOC_TTL_S)
        if isinstance(x, Failed) and x.throttled:
            rep.problems.append(f"{f['accession']}: throttled")
            return
        if not isinstance(x, Ok):
            rep.problems.append(f"{f['accession']}: {getattr(x, 'reason', x)}")
            continue
        try:
            s = parse_schedule(x.data)
        except ET.ParseError as e:
            rep.problems.append(f"{f['accession']}: XML unreadable ({e})")
            continue
        rep.stakes += store(engine, f, head, s, now)


def _header(engine, f, head: dict, relevant: bool, detail: str | None, now) -> None:
    filer = head.get("filer", (None, None))
    subject = head.get("subject", (None, None))
    engine.execute(
        "INSERT OR REPLACE INTO fin_schedule (accession, form, filed, filer_cik, filer_name, "
        "subject_cik, subject_name, relevant, detail, read_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f["accession"],
            f["form"],
            f["filed"],
            filer[0],
            filer[1],
            subject[0],
            subject[1],
            int(relevant),
            detail,
            iso(now),
        ),
    )


def store(engine: sqlite3.Connection, f, head: dict, s: dict, now: datetime) -> int:
    filer_cik, filer_name = head.get("filer", (None, None))
    issuer_cik = (s.get("issuer_cik") or head.get("subject", (None,))[0] or "").zfill(10)
    cusip = (s.get("cusip") or "").upper()
    if s.get("issuer_cik") and cusip:
        issuers.learn(engine, cusip, s["issuer_cik"], s.get("issuer_name") or "", now)
    source = "13D" if "13D" in f["form"] else "13G"
    notes = []
    if not s.get("issuer_cik") or not cusip:
        notes.append("issuer CIK or CUSIP not found in the schedule")
    if s.get("pct") is not None and not 0 <= s["pct"] <= 100:
        notes.append(f"percent of class {s['pct']} outside 0–100")
    if suppressed(engine, f"{source}:{filer_cik}:{cusip[:6]}"):
        status = "wrong"
    else:
        status = "held" if notes else "automatic"
    cur = engine.execute(
        "INSERT OR IGNORE INTO fin_holding (source, accession, filer_cik, filer_name, issuer_cik, "
        "issuer_name, cusip, shares, share_type, pct_class, period, filed, resolved_how, status, "
        "check_note, discovered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'SH', ?, ?, ?, '13D/G issuer', "
        "?, ?, ?)",
        (
            source,
            f["accession"],
            filer_cik,
            filer_name or filer_cik,
            issuer_cik if issuer_cik.strip("0") else None,
            s.get("issuer_name") or head.get("subject", (None, "?"))[1],
            cusip or "?",
            s.get("shares"),
            s.get("pct"),
            s.get("event") or f["filed"],
            f["filed"],
            status,
            "; ".join(notes) or None,
            iso(now),
        ),
    )
    engine.execute(
        "UPDATE fin_schedule SET xml_read = 1, detail = ? WHERE accession = ?",
        (json.dumps({k: s.get(k) for k in ("shares", "pct", "event")}), f["accession"]),
    )
    return cur.rowcount
