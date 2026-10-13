"""Dimensional facts from a filing's XBRL instance (M04 Part 7a; D-M04-42, S5.5–S5.7, SB.16).

SEC's companyfacts keeps only facts on contexts without dimensions, so a company's ≥ 10%
customers (`srt:MajorCustomersAxis`), its business segments, its revenue by product or
service and its share counts by class of stock never arrive there. This module reads
them on the one instance read that M02's extension-fact reader (`moneyflow/instance.py`)
already makes: one parse keeps both the company-extension facts without dimensions (into
`fact`, as before) and the dimensional facts on the kept axes (into `fact_dim`). The
instance file (2–14 MB) is not cached: rows stay, the file goes (SB.16).

Kept contexts: at least one explicit member on a kept axis (customers, segments, products
or services, classes of stock), and every other dimension on a kept or a qualifying axis
(concentration-risk benchmark and type, consolidation items). Contexts with typed members
or other axes (equity components, geography, …) are skipped, so the table holds what M04
reads and nothing that would read as a company total.

Recasts are not merged: a later filing that reports a different value for the same
concept, dimensions and period is listed by `recasts()` beside the first one (the Rivian
"recast" mistake, M04_FINANCIALS failure modes).
"""

from __future__ import annotations

import io
import json
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta

from engine.sec.client import SecClient, iso
from engine.sec.documents import filing_folder
from engine.sec.results import Empty, Failed, NotFound, Ok, Result

XBRLI = "{http://www.xbrl.org/2003/instance}"
XBRLDI = "{http://xbrl.org/2006/xbrldi}"
STANDARD_NS = (
    "http://fasb.org/",
    "http://xbrl.sec.gov/",
    "http://xbrl.ifrs.org/",
    "http://www.xbrl.org/",
    "http://www.w3.org/",
)

# Kept axes by local name → role; the first present in this order classifies the fact.
KEPT_AXES = {
    "MajorCustomersAxis": "customer",
    "StatementBusinessSegmentsAxis": "segment",
    "ProductOrServiceAxis": "product",
    "StatementClassOfStockAxis": "class",
}
# Axes allowed beside a kept one (they qualify the fact, they do not split the company).
QUALIFYING_AXES = frozenset(
    {
        "ConcentrationRiskByBenchmarkAxis",
        "ConcentrationRiskByTypeAxis",
        "ConsolidationItemsAxis",
    }
)

# Periodic forms whose instance carries the company's own statements (D-M04-42); XBRL 6-Ks
# count only when SEC flags them as XBRL (SB.11).
FORMS = ("10-K", "10-Q", "10-KT", "10-QT", "20-F", "40-F")
YEARS_BACK = 3
STATE = "fact_dim:"  # refresh_state name prefix: one row per instance read for dimensions
EXT_STATE = "xbrl_instance:"  # M02's marker: extension facts stored (moneyflow/instance.py)


@dataclass(frozen=True)
class DimFact:
    concept: str  # prefix:tag
    unit: str
    start: str | None
    end: str
    value: float
    dims: tuple[tuple[str, str], ...]  # sorted (axis, member), prefix:local names

    @property
    def axis_member(self) -> tuple[str, str]:
        for local in KEPT_AXES:
            for a, m in self.dims:
                if a.split(":")[-1] == local:
                    return a, m
        return self.dims[0]

    @property
    def dims_key(self) -> str:
        return ";".join(f"{a}={m}" for a, m in self.dims)


@dataclass(frozen=True)
class PlainFact:
    prefix: str
    tag: str
    unit: str
    start: str | None
    end: str
    value: float
    standard: bool


@dataclass(frozen=True)
class Parsed:
    plain: list[PlainFact]  # contexts without dimensions (all taxonomies)
    dims: list[DimFact]  # kept dimensional contexts
    contexts: int
    skipped_contexts: int  # dimensional contexts outside the kept axes

    @property
    def extension(self) -> list[PlainFact]:
        return [f for f in self.plain if not f.standard]


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


def _kept(dims: tuple[tuple[str, str], ...]) -> bool:
    locals_ = [a.split(":")[-1] for a, _ in dims]
    if not any(x in KEPT_AXES for x in locals_):
        return False
    return all(x in KEPT_AXES or x in QUALIFYING_AXES for x in locals_)


def parse(data: bytes) -> Parsed:
    """One pass over an instance: facts without dimensions and kept dimensional facts."""
    prefixes: dict[str, str] = {}
    # context id → (period, dims) ; dims None = no dimensions; "skip" = not kept
    contexts: dict[str, tuple[tuple[str | None, str] | None, object]] = {}
    units: dict[str, str | None] = {}
    raw: list[tuple[str, str, str, str, str]] = []
    skipped = 0
    for event, item in ET.iterparse(io.BytesIO(data), events=("start-ns", "end")):
        if event == "start-ns":
            prefix, uri = item
            prefixes.setdefault(uri, prefix)
            continue
        el = item
        if el.tag == f"{XBRLI}context":
            p = el.find(f"{XBRLI}period")
            inst = p.findtext(f"{XBRLI}instant") if p is not None else None
            s = p.findtext(f"{XBRLI}startDate") if p is not None else None
            e = p.findtext(f"{XBRLI}endDate") if p is not None else None
            period = (None, inst.strip()) if inst else ((s.strip(), e.strip()) if s and e else None)
            holders = [
                x
                for x in (el.find(f".//{XBRLI}segment"), el.find(f".//{XBRLI}scenario"))
                if x is not None
            ]
            if not holders:
                dims: object = None
            elif any(h.find(f"{XBRLDI}typedMember") is not None for h in holders):
                dims = "skip"
            else:
                pairs = tuple(
                    sorted(
                        ((m.get("dimension") or "").strip(), (m.text or "").strip())
                        for h in holders
                        for m in h.findall(f"{XBRLDI}explicitMember")
                    )
                )
                dims = pairs if pairs and _kept(pairs) else "skip"
            if dims == "skip":
                skipped += 1
            contexts[el.get("id", "")] = (period, dims)
            el.clear()
        elif el.tag == f"{XBRLI}unit":
            units[el.get("id", "")] = _unit_name(el)
            el.clear()
        elif el.get("contextRef") and el.get("unitRef") and el.tag.startswith("{"):
            uri, tag = el.tag[1:].split("}", 1)
            if el.text and el.text.strip():
                raw.append(
                    (uri, tag, el.get("contextRef", ""), el.get("unitRef", ""), el.text.strip())
                )
            el.clear()

    plain: list[PlainFact] = []
    dimmed: list[DimFact] = []
    seen_p: set = set()
    seen_d: set = set()
    for uri, tag, ctx, unit_ref, text in raw:
        got = contexts.get(ctx)
        unit, prefix = units.get(unit_ref), prefixes.get(uri)
        if got is None or got[0] is None or unit is None or prefix is None:
            continue
        period, dims = got
        if dims == "skip":
            continue
        try:
            value = float(text.replace(",", ""))
        except ValueError:
            continue
        if dims is None:
            key = (prefix, tag, unit, period)
            if key in seen_p:
                continue  # the same fact repeated on another page of the filing
            seen_p.add(key)
            plain.append(
                PlainFact(
                    prefix, tag, unit, period[0], period[1], value, uri.startswith(STANDARD_NS)
                )
            )
        else:
            assert isinstance(dims, tuple)
            key = (prefix, tag, unit, period, dims)
            if key in seen_d:
                continue
            seen_d.add(key)
            dimmed.append(DimFact(f"{prefix}:{tag}", unit, period[0], period[1], value, dims))
    return Parsed(plain, dimmed, len(contexts), skipped)


# --- Storage -------------------------------------------------------------------------------


def store_parsed(
    engine: sqlite3.Connection,
    cik: str,
    filing: sqlite3.Row | dict,
    parsed: Parsed | None,
    url: str,
    now: datetime,
    *,
    detail: dict | None = None,
) -> tuple[int, int]:
    """Write the extension facts (to `fact`) and the kept dimensional facts (to `fact_dim`)
    of one instance, and mark the filing read for both readers, in one transaction.
    Returns (new extension facts, new dimensional rows). `parsed=None` records a miss."""
    acc, form, filed = filing["accession"], filing["form"], filing["filed"]
    ext_rows = [
        (cik, f.prefix, f.tag, f.unit, f.start, f.end, f.value, acc, form, filed, None, None, None)
        for f in (parsed.extension if parsed else [])
    ]
    dim_rows = []
    for d in parsed.dims if parsed else []:
        axis, member = d.axis_member
        dim_rows.append(
            (
                cik,
                acc,
                form,
                filed,
                d.concept,
                axis,
                member,
                d.dims_key,
                d.start,
                d.end,
                d.value,
                d.unit,
            )
        )
    info = dict(detail or {})
    if parsed is not None:
        info |= {
            "facts": len(ext_rows),
            "dims": len(dim_rows),
            "contexts": parsed.contexts,
            "skipped_contexts": parsed.skipped_contexts,
        }
    engine.execute("BEGIN")
    try:
        before = engine.total_changes
        engine.executemany(
            "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, "
            "accession, form, filed, fy, fp, frame) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            ext_rows,
        )
        new_ext = engine.total_changes - before
        before = engine.total_changes
        engine.executemany(
            "INSERT INTO fact_dim (cik, accession, form, filed, concept, axis, member, dims, "
            "period_start, period_end, value, unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            dim_rows,
        )
        new_dim = engine.total_changes - before
        names = [STATE + acc]
        if parsed is not None:
            names.append(EXT_STATE + acc)  # M02 never fetches this instance again
        for name in names:
            engine.execute(
                "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES "
                "(?, ?, ?, ?) ON CONFLICT (name) DO UPDATE SET source_ref = excluded.source_ref, "
                "fetched_at = excluded.fetched_at, detail = excluded.detail",
                (
                    name,
                    url,
                    iso(now),
                    json.dumps(info if name.startswith(STATE) else {"facts": len(ext_rows)}),
                ),
            )
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return new_ext, new_dim


def dims_done(engine: sqlite3.Connection, accession: str) -> bool:
    return (
        engine.execute(
            "SELECT 1 FROM refresh_state WHERE name = ?", (STATE + accession,)
        ).fetchone()
        is not None
    )


def instance_url(cik: str, accession: str, primary_doc: str | None) -> str | None:
    """`nvda-20260125.htm` → `.../nvda-20260125_htm.xml` (inline XBRL's extracted instance)."""
    stem, dot, ext = (primary_doc or "").rpartition(".")
    if not dot or ext.lower() not in ("htm", "html"):
        return None
    return f"{filing_folder(cik, accession)}/{stem}_{ext.lower()}.xml"


@dataclass(frozen=True)
class ReadResult:
    accession: str
    url: str | None
    mb: float
    ext_new: int
    dim_new: int
    dims: int
    outcome: str  # ok | not_found | failed | unreadable
    detail: str = ""
    throttled: bool = False


def read_instance(
    client: SecClient,
    engine: sqlite3.Connection,
    cik: str,
    filing: sqlite3.Row | dict,
    now: datetime,
) -> ReadResult:
    """Fetch one filing's instance (derived `_htm.xml`, else the one the index lists), parse
    once, store extension and dimensional facts, mark it read. Never cached (SB.16)."""
    from engine.moneyflow.instance import find_instance

    acc = filing["accession"]
    url = instance_url(cik, acc, filing["primary_doc"])
    res: Result[bytes] | None = client.get_bytes(url, ttl_s=0) if url else None
    if res is None or isinstance(res, NotFound):
        found = find_instance(client, cik, acc)  # index page (cached for 10 years)
        if isinstance(found, Ok):
            url = found.data
            res = client.get_bytes(url, ttl_s=0)
        elif isinstance(found, Failed):
            return ReadResult(acc, url, 0.0, 0, 0, 0, "failed", found.reason, found.throttled)
        else:
            why = (
                "; ".join(p.result for p in found.paths_checked)
                if isinstance(found, Empty)
                else str(found)
            )
            store_parsed(
                engine,
                cik,
                filing,
                None,
                url or "",
                now,
                detail={"outcome": "not_found", "why": why},
            )
            return ReadResult(acc, url, 0.0, 0, 0, 0, "not_found", why)
    if isinstance(res, NotFound):
        store_parsed(
            engine,
            cik,
            filing,
            None,
            url or "",
            now,
            detail={"outcome": "not_found", "why": "HTTP 404"},
        )
        return ReadResult(acc, url, 0.0, 0, 0, 0, "not_found", "HTTP 404")
    if not isinstance(res, Ok):
        reason = res.reason if isinstance(res, Failed) else str(res)
        throttled = isinstance(res, Failed) and res.throttled
        return ReadResult(acc, url, 0.0, 0, 0, 0, "failed", reason, throttled)
    mb = len(res.data) / 1e6
    try:
        parsed = parse(res.data)
    except ET.ParseError as exc:
        return ReadResult(acc, url, mb, 0, 0, 0, "unreadable", f"XBRL instance unreadable: {exc}")
    ext_new, dim_new = store_parsed(
        engine, cik, filing, parsed, url or "", now, detail={"outcome": "ok", "mb": round(mb, 2)}
    )
    return ReadResult(acc, url, mb, ext_new, dim_new, len(parsed.dims), "ok")


def due_filings(
    engine: sqlite3.Connection, cik: str, since: str, *, limit: int | None = None
) -> list[sqlite3.Row]:
    """Periodic filings under `cik` filed since `since` whose dimensions are not read yet,
    newest first (XBRL 6-Ks only when flagged XBRL)."""
    marks = ",".join("?" * len(FORMS))
    rows = engine.execute(
        f"SELECT f.accession, f.form, f.filed, f.report_date, f.primary_doc, f.is_xbrl "
        f"FROM filing f JOIN filing_cik c ON c.accession = f.accession WHERE c.cik = ? "
        f"AND f.filed >= ? AND (f.form IN ({marks}) OR (f.form = '6-K' AND f.is_xbrl = 1)) "
        "AND NOT EXISTS (SELECT 1 FROM refresh_state WHERE name = 'fact_dim:' || f.accession) "
        "ORDER BY f.filed DESC",
        (cik, since, *FORMS),
    ).fetchall()
    return rows[:limit] if limit else rows


def backfill_since(now: datetime) -> str:
    return (now - timedelta(days=365 * YEARS_BACK)).date().isoformat()


# --- Reads ---------------------------------------------------------------------------------


def rows(
    engine: sqlite3.Connection,
    cik: str,
    *,
    role: str | None = None,
    concepts: tuple[str, ...] | None = None,
) -> list[sqlite3.Row]:
    """Stored dimensional rows of a company, optionally one role's axis and some concepts."""
    sql = "SELECT * FROM fact_dim WHERE cik = ?"
    args: list = [cik]
    if role:
        local = next(k for k, v in KEPT_AXES.items() if v == role)
        sql += " AND (axis = ? OR axis LIKE ?)"
        args += [local, f"%:{local}"]
    if concepts:
        sql += f" AND concept IN ({','.join('?' * len(concepts))})"
        args += list(concepts)
    return engine.execute(sql + " ORDER BY period_end, filed, accession", args).fetchall()


@dataclass(frozen=True)
class Recast:
    concept: str
    dims: str
    start: str | None
    end: str
    first: tuple[float, str, str]  # value, accession, filed
    latest: tuple[float, str, str]


def recasts(engine: sqlite3.Connection, cik: str, *, role: str | None = None) -> list[Recast]:
    """Same concept, dimensions and period reported with different values by different
    filings: listed, never merged (D-M04-42)."""
    groups: dict[tuple, list[sqlite3.Row]] = {}
    for r in rows(engine, cik, role=role):
        groups.setdefault(
            (r["concept"], r["dims"], r["period_start"], r["period_end"], r["unit"]), []
        ).append(r)
    out = []
    for (concept, dims, start, end, _), rs in groups.items():
        vals = {float(r["value"]) for r in rs}
        if len(vals) > 1:
            rs = sorted(rs, key=lambda r: (r["filed"], r["accession"]))
            f, la = rs[0], rs[-1]
            out.append(
                Recast(
                    concept,
                    dims,
                    start,
                    end,
                    (float(f["value"]), f["accession"], f["filed"]),
                    (float(la["value"]), la["accession"], la["filed"]),
                )
            )
    return sorted(out, key=lambda x: (x.end, x.concept, x.dims))


def local(name: str) -> str:
    """`nvda:CustomerAMember` → `CustomerA`; `us-gaap:CommonClassAMember` → `CommonClassA`."""
    x = name.split(":")[-1]
    return x[: -len("Member")] if x.endswith("Member") else x
