"""Run the rungs over stored and fetched documents (D-M02-7, D-M02-35).

- L1: the company's own stored 10-K/10-Q text (local, no requests).
- L3: 8-K Item 1.01 filings of the last three years; their EX-10 exhibits are fetched
  (index + exhibit, a few requests per filing) up to a per-run cap, then read.
- L2: targeted phrases per customer alias (`<alias> accounted for`, `sales to <alias>`,
  `revenue from <alias>`, `<alias> represented`) through EDGAR full-text search over
  10-K, 10-Q and 20-F of the last 18 months; hit documents are queued and fetched up to a
  per-run cap, then read for the sentence. Searches per customer repeat after 30 days.
- Probe (c), counts only: the bare alias, hits limited to hardware/semiconductor SIC
  codes, so the owner can decide on option (c) from numbers (D-M02-35).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from engine.sec.client import SecClient, iso
from engine.sec.documents import IndexDoc, _stored, fetch_filing_index, store_document
from engine.sec.fulltext import search, search_page
from engine.sec.results import Failed, NotFound, Ok
from engine.supply import links
from engine.supply.aliases import Company, Matcher
from engine.supply.find import find_l1, find_l2, find_l3, self_keys

L2_TEMPLATES = ("{a} accounted for", "sales to {a}", "revenue from {a}", "{a} represented")
L2_FORMS = ("10-K", "10-Q", "20-F")
L2_MONTHS = 18
L2_REPEAT = timedelta(days=30)
L2_MAX_HITS = 100  # per phrase
L3_YEARS = 3
DOC_TTL_S = 0  # text is stored in the corpus; raw bytes are not cached again
# Probe (c): computers, electronic components, semiconductors, instruments
HARDWARE_SICS = tuple(
    str(s) for s in [*range(3570, 3580), *range(3670, 3680), *range(3810, 3830), 3661, 3663, 3669]
)


@dataclass
class ScanReport:
    l1_docs: int = 0
    l1_new: int = 0
    l3_filings: int = 0
    l3_new: int = 0
    l2_searches: int = 0
    l2_queued: int = 0
    l2_fetched: int = 0
    l2_new: int = 0
    probe: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    phrase_hits: dict[str, int] = field(default_factory=dict)

    def lines(self) -> list[str]:
        out = [
            f"L1: {self.l1_docs} own 10-K/10-Q document(s) read, {self.l1_new} new passage(s)",
            f"L3: {self.l3_filings} Item 1.01 filing(s) read, {self.l3_new} new passage(s)",
            f"L2: {self.l2_searches} search(es), {self.l2_queued} hit document(s) queued, "
            f"{self.l2_fetched} fetched, {self.l2_new} new passage(s)",
        ]
        out += [f"  {p}: {n} hit(s)" for p, n in sorted(self.phrase_hits.items())]
        if self.probe:
            out.append("Probe (c), counts only — bare name, hardware/semiconductor SIC filers:")
            out += [f"  {p}" for p in self.probe]
        out += [f"  problem: {p}" for p in self.problems]
        return out


def filer_name(
    engine: sqlite3.Connection, matcher: Matcher, cik: str
) -> tuple[str, Company | None]:
    c = matcher.by_cik(cik)
    if c is not None:
        return c.name, c
    row = engine.execute("SELECT name FROM entity WHERE cik = ?", (cik,)).fetchone()
    return (row[0] if row else cik), None


def _doc(corpus: sqlite3.Connection, doc_id: int, engine: sqlite3.Connection) -> links.Doc:
    d = corpus.execute(
        "SELECT accession, filename, doc_type, text FROM document WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    f = engine.execute(
        "SELECT form, filed FROM filing WHERE accession = ?", (d["accession"],)
    ).fetchone()
    return links.Doc(
        d["accession"],
        d["filename"],
        f["form"] if f else d["doc_type"],
        f["filed"] if f else None,
        d["text"],
    )


# --- L1 ---------------------------------------------------------------------------------


def scan_l1(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    matcher: Matcher,
    cik: str,
    now: datetime,
    rep: ScanReport,
) -> None:
    since = (now - timedelta(days=400)).date().isoformat()
    accs = {
        r[0]
        for r in engine.execute(
            "SELECT accession FROM filing WHERE cik = ? AND form IN ('10-K', '10-Q', '20-F') "
            "AND filed >= ?",
            (cik, since),
        )
    }
    name, company = filer_name(engine, matcher, cik)
    mine = self_keys(matcher, cik)
    for d in corpus.execute(
        "SELECT doc_id, accession, doc_type FROM document WHERE cik = ? "
        "AND doc_type IN ('10-K', '10-Q', '20-F')",
        (cik,),
    ).fetchall():
        if d["accession"] not in accs:
            continue
        doc = _doc(corpus, d["doc_id"], engine)
        rep.l1_docs += 1
        rep.l1_new += links.store(
            engine, cik, name, company, doc, find_l1(doc.text, matcher, mine), now
        )


# --- L3 ---------------------------------------------------------------------------------


def _fetch_doc(
    client: SecClient,
    corpus: sqlite3.Connection,
    cik: str,
    accession: str,
    doc: IndexDoc,
    now: datetime,
) -> int | None:
    existing = _stored(corpus, doc.url)
    if existing is not None:
        return existing.doc_id
    res = client.get_bytes(doc.url, ttl_s=DOC_TTL_S)
    if not isinstance(res, Ok):
        return None
    return store_document(corpus, cik, accession, doc, res.data, now).doc_id


def scan_l3(
    client: SecClient | None,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    matcher: Matcher,
    cik: str,
    now: datetime,
    rep: ScanReport,
    cap: int,
) -> int:
    """Read Item 1.01 exhibits; fetch at most `cap` filings this run → filings fetched."""
    since = (now - timedelta(days=365 * L3_YEARS)).date().isoformat()
    name, company = filer_name(engine, matcher, cik)
    mine = self_keys(matcher, cik)
    fetched = 0
    for f in engine.execute(
        "SELECT accession, form, filed, items FROM filing WHERE cik = ? AND form IN "
        "('8-K', '8-K/A') AND filed >= ? ORDER BY filed DESC",
        (cik, since),
    ).fetchall():
        if not (f["items"] and "1.01" in f["items"].split(",")):
            continue
        state = f"supply_l3:{f['accession']}"
        done = engine.execute("SELECT 1 FROM refresh_state WHERE name = ?", (state,)).fetchone()
        if not done:
            if client is None or fetched >= cap:
                continue
            idx = fetch_filing_index(client, cik, f["accession"])
            fetched += 1
            if isinstance(idx, Failed) and idx.throttled:
                rep.problems.append(f"{f['accession']}: throttled")
                break
            exhibits = (
                [d for d in idx.data if (d.doc_type or "").startswith("EX-10")]
                if isinstance(idx, Ok)
                else []
            )
            for d in exhibits:
                _fetch_doc(client, corpus, cik, f["accession"], d, now)
            engine.execute(
                "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES "
                "(?, ?, ?, ?) ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
                "detail = excluded.detail",
                (state, f["accession"], iso(now), json.dumps({"exhibits": len(exhibits)})),
            )
        for d in corpus.execute(
            "SELECT doc_id FROM document WHERE accession = ? AND doc_type LIKE 'EX-10%'",
            (f["accession"],),
        ).fetchall():
            doc = _doc(corpus, d["doc_id"], engine)
            rep.l3_new += links.store(
                engine, cik, name, company, doc, find_l3(doc.text, matcher, mine), now
            )
        rep.l3_filings += 1
    return fetched


# --- L2 ---------------------------------------------------------------------------------


def l2_phrases(c: Company) -> list[str]:
    return [t.format(a=n) for n in c.names for t in L2_TEMPLATES if len(n) >= 3]


def search_l2(
    client: SecClient,
    engine: sqlite3.Connection,
    c: Company,
    now: datetime,
    rep: ScanReport,
    *,
    force: bool = False,
) -> None:
    """Targeted-phrase searches for one customer → hit documents queued."""
    state = f"supply_l2:{c.key}"
    row = engine.execute("SELECT fetched_at FROM refresh_state WHERE name = ?", (state,)).fetchone()
    if row and not force and now - datetime.fromisoformat(row[0]) < L2_REPEAT:
        return
    start = (now - timedelta(days=30 * L2_MONTHS)).date().isoformat()
    end = now.date().isoformat()
    for phrase in l2_phrases(c):
        res = search(
            client,
            engine,
            phrase,
            forms=L2_FORMS,
            start=start,
            end=end,
            now=now,
            max_hits=L2_MAX_HITS,
            allow_fallback=False,
        )
        rep.l2_searches += 1
        if not isinstance(res, Ok):
            rep.problems.append(f"{phrase}: {getattr(res, 'reason', res)}")
            if isinstance(res, Failed) and res.throttled:
                return
            continue
        rep.phrase_hits[phrase] = res.data.total
        for h in res.data.hits:
            if h.url is None or (c.cik and h.cik == c.cik):
                continue  # the customer's own filings are L1, not L2
            cur = engine.execute(
                "INSERT OR IGNORE INTO supply_fetch (url, cik, entity_name, accession, filename, "
                "form, file_date, customer_key, phrase, status, queued_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)",
                (
                    h.url,
                    h.cik,
                    h.entity_name,
                    h.accession,
                    h.filename,
                    h.form,
                    h.file_date,
                    c.key,
                    phrase,
                    iso(now),
                ),
            )
            rep.l2_queued += cur.rowcount
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at",
        (state, c.key, iso(now), "{}"),
    )


def fetch_l2(
    client: SecClient | None,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    matcher: Matcher,
    now: datetime,
    rep: ScanReport,
    cap: int,
) -> None:
    """Fetch queued hit documents (newest first) and read the customer's sentence."""
    by_key = {c.key: c for c in matcher.companies}
    for q in engine.execute(
        "SELECT * FROM supply_fetch WHERE status = 'queued' ORDER BY file_date DESC LIMIT ?",
        (cap if client is not None else 0,),
    ).fetchall():
        cik = q["cik"]
        doc = IndexDoc(None, None, q["filename"], q["url"], q["form"], None, False)
        res = (
            client.get_bytes(q["url"], ttl_s=DOC_TTL_S)
            if _stored(corpus, q["url"]) is None
            else None
        )
        if isinstance(res, Failed) and res.throttled:
            rep.problems.append(f"{q['url']}: throttled")
            break
        if res is not None and not isinstance(res, Ok):
            status = "failed"
            detail = "HTTP 404" if isinstance(res, NotFound) else getattr(res, "reason", "")
            engine.execute(
                "UPDATE supply_fetch SET status = ?, detail = ?, done_at = ? WHERE url = ?",
                (status, detail, iso(now), q["url"]),
            )
            continue
        if res is not None:
            store_document(corpus, cik, q["accession"], doc, res.data, now)
        rep.l2_fetched += 1
        engine.execute(
            "UPDATE supply_fetch SET status = 'stored', done_at = ? WHERE url = ?",
            (iso(now), q["url"]),
        )
        read_l2(engine, corpus, matcher, q, by_key.get(q["customer_key"]), now, rep)


def read_l2(engine, corpus, matcher, q, customer: Company | None, now, rep) -> None:
    if customer is None:
        return
    row = corpus.execute("SELECT doc_id FROM document WHERE url = ?", (q["url"],)).fetchone()
    if row is None:
        return
    doc = _doc(corpus, row[0], engine)
    doc = links.Doc(
        doc.accession, doc.filename, q["form"] or doc.form, q["file_date"] or doc.filed, doc.text
    )
    name = q["entity_name"] or q["cik"] or "?"
    company = matcher.by_cik(q["cik"]) if q["cik"] else None
    if company is not None:
        name = company.name
    mine = self_keys(matcher, q["cik"])
    found = find_l2(doc.text, matcher, customer, mine)
    rep.l2_new += links.store(engine, q["cik"], name, company, doc, found, now)


def probe_c(client: SecClient, engine: sqlite3.Connection, c: Company, now: datetime) -> list[str]:
    """Counts only: bare names, all filers vs hardware/semiconductor SIC filers (≤ 10 pages),
    and how many of those filers the targeted phrases (a) did not already find."""
    known = {
        r[0]
        for r in engine.execute(
            "SELECT DISTINCT cik FROM supply_fetch WHERE customer_key = ? AND cik IS NOT NULL",
            (c.key,),
        )
    }
    start = (now - timedelta(days=30 * L2_MONTHS)).date().isoformat()
    end = now.date().isoformat()
    out = []
    for n in c.names:
        hits, total, offset, capped = [], None, 0, False
        while offset < 1000:
            res = search_page(
                client, n, forms=L2_FORMS, start=start, end=end, offset=offset, allow_fallback=False
            )
            if not isinstance(res, Ok):
                out.append(f"{n}: {getattr(res, 'reason', res)}")
                break
            total = res.data.total
            capped = res.data.capped
            hits.extend(res.data.hits)
            offset += len(res.data.hits)
            if not res.data.hits or offset >= total:
                break
        if total is None:
            continue
        hw = {h.accession for h in hits if set(h.sics) & set(HARDWARE_SICS)}
        filers = {h.cik for h in hits if set(h.sics) & set(HARDWARE_SICS)}
        seen = len(hits)
        note = "" if seen >= total else f" (first {seen} of {total} read; counts are lower bounds)"
        out.append(
            f'"{n}": {total}{"+" if capped else ""} hit document(s) in all filers; '
            f"{len(hw)} filing(s) from {len(filers)} hardware/semiconductor filer(s), "
            f"{len(filers - known)} not found by the targeted phrases{note}"
        )
    return out
