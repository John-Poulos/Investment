"""Company extension facts from a filing's XBRL instance (D-M02-29, D-M02-31, D-M02-32).

SEC's companyfacts API carries the standard taxonomies only (us-gaap, dei, srt, ifrs),
so a company's own tags — Amazon's `amzn:ProceedsFromPropertyPlantAndEquipmentSales
AndIncentives`, its financing-obligation repayments — are missing. For the few companies
that need them (an override recipe in `config/capex_definitions.toml`, or financing
coverage below 80%), each 10-K/10-Q's extracted instance is read once: SEC publishes it
beside an inline-XBRL primary document as `<primary stem>_htm.xml`. Only facts in a
company namespace, on contexts without dimensions, are stored — in the same `fact`
table, taxonomy = the namespace prefix (e.g. `amzn`), so every series and recipe reads
them like any other tag. One request per filing; filings are immutable, so a stored
instance is never fetched again. Since M04 Part 7a the same read also stores the kept
dimensional facts in `fact_dim` (`engine.sec.instance_dim`, D-M04-42).
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta

from engine.sec.client import SecClient, iso
from engine.sec.documents import INDEX_TTL_S, filing_folder
from engine.sec.results import Empty, Failed, NotFound, Ok, Probe, Result

STANDARD_NS = (
    "http://fasb.org/",
    "http://xbrl.sec.gov/",
    "http://xbrl.ifrs.org/",
    "http://www.xbrl.org/",
    "http://www.w3.org/",
)
XBRLI = "{http://www.xbrl.org/2003/instance}"
FORMS = ("10-K", "10-Q", "10-K/A", "10-Q/A")
YEARS_BACK = 3


@dataclass(frozen=True)
class ExtFact:
    prefix: str
    tag: str
    unit: str
    start: str | None
    end: str
    value: float


def instance_url(cik: str, accession: str, primary_doc: str) -> str | None:
    """`amzn-20260630.htm` → `.../amzn-20260630_htm.xml`; None for a non-HTML primary."""
    stem, dot, ext = primary_doc.rpartition(".")
    if not dot or ext.lower() not in ("htm", "html"):
        return None
    return f"{filing_folder(cik, accession)}/{stem}_{ext.lower()}.xml"


def _unit_name(el: ET.Element) -> str | None:
    def names(parent: ET.Element | None) -> list[str]:
        if parent is None:
            return []
        return [m.text.strip().split(":")[-1] for m in parent.iter(f"{XBRLI}measure") if m.text]

    divide = el.find(f"{XBRLI}divide")
    if divide is not None:
        num = names(divide.find(f"{XBRLI}unitNumerator"))
        den = names(divide.find(f"{XBRLI}unitDenominator"))
        return f"{num[0]}/{den[0]}" if len(num) == 1 and len(den) == 1 else None
    measures = names(el)
    return measures[0] if len(measures) == 1 else None


_XML_HREF = re.compile(r'href="([^"]+\.xml)"', re.IGNORECASE)
_NOT_INSTANCE = ("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml", "filingsummary.xml")


def instance_href(html: str) -> str | None:
    """The XBRL instance in a filing index page: a pre-inline `x-20130127.xml` or an
    inline filing's extracted `_htm.xml` (moved from scripts/probe_m04.py, M04 Part 1b)."""
    for href in _XML_HREF.findall(html):
        low = href.lower()
        if low.endswith(_NOT_INSTANCE) or "xsl" in low:
            continue
        return href if href.startswith("http") else "https://www.sec.gov" + href
    return None


def find_instance(client: SecClient, cik: str, accession: str) -> Result[str]:
    """The instance URL from the filing's index page (`-index.htm`, else `-index.html`;
    cached like every index page). The instance sits in the index's data-files table,
    which `documents.parse_filing_index` does not read, so the raw page is searched."""
    probes = []
    for name in (f"{accession}-index.htm", f"{accession}-index.html"):
        url = f"{filing_folder(cik, accession)}/{name}"
        res = client.get_text(url, ttl_s=INDEX_TTL_S)
        if isinstance(res, NotFound):
            probes.append(Probe("filing index", url, "HTTP 404: no file at this URL"))
            continue
        if not isinstance(res, Ok):
            return res
        href = instance_href(res.data)
        if href is None:
            return Empty((Probe("XBRL instance", url, "no instance listed in the index"),))
        return Ok(href, source_ref=url, fetched_at=res.fetched_at, from_cache=res.from_cache)
    return Empty(tuple(probes))


def instance_facts(data: bytes) -> list[tuple[str, str, str | None, str, float]]:
    """(prefix, tag, start, end, value) for every numeric fact (standard taxonomies too)
    on contexts without dimensions (the probe's listing form)."""
    return [(f.prefix, f.tag, f.start, f.end, f.value) for f in parse_instance(data, standard=True)]


def parse_instance(data: bytes, *, standard: bool = False) -> list[ExtFact]:
    """Numeric company-extension facts on contexts without dimensions (`standard=True`:
    us-gaap, dei and the other standard taxonomies too)."""
    prefixes: dict[str, str] = {}
    contexts: dict[str, tuple[str | None, str] | None] = {}
    units: dict[str, str | None] = {}
    raw: list[tuple[str, str, str, str, str]] = []  # uri, tag, context, unit, text
    for event, item in ET.iterparse(io.BytesIO(data), events=("start-ns", "end")):
        if event == "start-ns":
            prefix, uri = item
            prefixes.setdefault(uri, prefix)
            continue
        el = item
        if el.tag == f"{XBRLI}context":
            if (
                el.find(f".//{XBRLI}segment") is not None
                or el.find(f".//{XBRLI}scenario") is not None
            ):
                contexts[el.get("id", "")] = None  # dimensional: a segment, not the company
            else:
                p = el.find(f"{XBRLI}period")
                inst = p.findtext(f"{XBRLI}instant") if p is not None else None
                s = p.findtext(f"{XBRLI}startDate") if p is not None else None
                e = p.findtext(f"{XBRLI}endDate") if p is not None else None
                contexts[el.get("id", "")] = (
                    (None, inst.strip()) if inst else ((s.strip(), e.strip()) if s and e else None)
                )
            el.clear()
        elif el.tag == f"{XBRLI}unit":
            units[el.get("id", "")] = _unit_name(el)
            el.clear()
        elif el.get("contextRef") and el.get("unitRef") and el.tag.startswith("{"):
            uri, tag = el.tag[1:].split("}", 1)
            if (standard or not uri.startswith(STANDARD_NS)) and el.text and el.text.strip():
                raw.append(
                    (uri, tag, el.get("contextRef", ""), el.get("unitRef", ""), el.text.strip())
                )
            el.clear()

    out, seen = [], set()
    for uri, tag, ctx, unit_ref, text in raw:
        period, unit, prefix = contexts.get(ctx), units.get(unit_ref), prefixes.get(uri)
        if period is None or unit is None or prefix is None:
            continue
        try:
            value = float(text.replace(",", ""))
        except ValueError:
            continue
        key = (prefix, tag, unit, period)
        if key in seen:
            continue  # the same fact repeated on another page of the filing
        seen.add(key)
        out.append(ExtFact(prefix, tag, unit, period[0], period[1], value))
    return out


def _state(accession: str) -> str:
    return f"xbrl_instance:{accession}"


def due_filings(engine: sqlite3.Connection, cik: str, today: datetime) -> list[sqlite3.Row]:
    """10-K/10-Q filings of the last three years whose instance is not stored yet."""
    since = (today - timedelta(days=365 * YEARS_BACK)).date().isoformat()
    marks = ",".join("?" * len(FORMS))
    return engine.execute(
        f"SELECT accession, form, filed, primary_doc FROM filing WHERE cik = ? "
        f"AND form IN ({marks}) AND filed >= ? AND primary_doc IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM refresh_state WHERE name = 'xbrl_instance:' || accession) "
        "ORDER BY filed DESC",
        (cik, *FORMS, since),
    ).fetchall()


def store_instance(
    client: SecClient,
    engine: sqlite3.Connection,
    cik: str,
    filing: sqlite3.Row | dict,
    now: datetime,
    *,
    url: str | None = None,
) -> Result[int]:
    """Fetch one filing's instance and store its extension facts. Ok(new facts).

    `url` names the instance directly (a pre-inline filing's `x-20130127.xml`, found in its
    index page); otherwise it is derived from the inline primary document."""
    url = url or instance_url(cik, filing["accession"], filing["primary_doc"] or "")
    if url is None:
        return Empty((Probe("XBRL instance", filing["primary_doc"], "primary document not HTML"),))
    res = client.get_bytes(url, ttl_s=0)  # stored as facts; the large file is not cached
    if isinstance(res, Ok):
        # M04 Part 7a: the same read also keeps the dimensional facts (fact_dim), so the
        # instance is never fetched twice (D-M04-42, SB.16).
        from engine.sec import instance_dim

        try:
            parsed = instance_dim.parse(res.data)
        except ET.ParseError as exc:
            return Failed(f"XBRL instance unreadable: {exc}", url=url)
        new, _ = instance_dim.store_parsed(engine, cik, filing, parsed, url, now,
                                           detail={"outcome": "ok"})  # fmt: skip
        return Ok(new, source_ref=url, fetched_at=iso(now))
    if not isinstance(res, NotFound):
        return res
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET source_ref = excluded.source_ref, "
        "fetched_at = excluded.fetched_at, detail = excluded.detail",
        (_state(filing["accession"]), url, iso(now), json.dumps({"not_found": True})),
    )
    return Empty((Probe("XBRL instance", url, "HTTP 404: no extracted instance"),))


def sync_instances(
    client: SecClient, engine: sqlite3.Connection, cik: str, now: datetime
) -> tuple[int, int, list[str]]:
    """Store every due instance for a company → (filings read, new facts, problems)."""
    read = new = 0
    problems = []
    for f in due_filings(engine, cik, now):
        res = store_instance(client, engine, cik, f, now)
        if isinstance(res, Ok):
            read += 1
            new += res.data
        elif isinstance(res, Empty):
            read += 1
            problems.append(f"{f['accession']}: " + "; ".join(p.result for p in res.paths_checked))
        else:
            problems.append(f"{f['accession']}: {getattr(res, 'reason', res)}")
            break  # a failure (throttle, network) ends this company's batch for the run
    return read, new, problems
