"""Where financing passages come from (D-M02-42 (1)–(2), D-M02-45 (4)).

- Stored documents of watchlist/tracked companies (10-K, 10-Q, 8-K and their exhibits,
  three years): read once each (new documents only; `rescan` re-reads all and prunes).
- 8-K Item 3.02 (unregistered sales of equity) of our companies, three years: the
  filing's EX-10/EX-4/EX-99 exhibits are fetched, ≤ `cap` filings per run (Item 1.01
  exhibits are already fetched by the supplier step).
- Targeted full-text phrases per company name over 10-K/10-Q/8-K of all filers, 18
  months ("<name> agreed to purchase", "<name> agreed to invest", "warrant(s) to <name>",
  "investment from <name>"), repeated after 30 days; hit documents fetched ≤ `cap` per
  run, newest first — the counterparties of backstops and warrants (CoreWeave, Fabrinet)
  have no stored documents.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from engine.financing import find, links
from engine.sec.client import SecClient, iso
from engine.sec.documents import IndexDoc, _stored, fetch_filing_index, store_document
from engine.sec.fulltext import search
from engine.sec.results import Failed, NotFound, Ok
from engine.supply.aliases import Company, Matcher
from engine.supply.find import self_keys
from engine.supply.scan import _doc, filer_name

YEARS = 3
TEMPLATES = (
    "{a} agreed to purchase",
    "{a} agreed to invest",
    "warrant to {a}",
    "warrants to {a}",
    "investment from {a}",
)
# wording that names the counterparty elsewhere in the sentence ("NVIDIA has agreed to
# purchase any unsold capacity"): one search each, hits read like the others (D-M02-47)
GLOBAL = ("unsold capacity",)
FORMS = ("10-K", "10-Q", "8-K")
MONTHS = 18
REPEAT = timedelta(days=30)
MAX_HITS = 100
EXHIBITS = ("EX-10", "EX-4", "EX-99")
DOC_TTL_S = 0  # text is stored in the corpus


@dataclass
class ScanReport:
    docs: int = 0
    new: int = 0
    f302: int = 0
    searches: int = 0
    queued: int = 0
    fetched: int = 0
    problems: list[str] = field(default_factory=list)
    phrase_hits: dict[str, int] = field(default_factory=dict)

    def lines(self) -> list[str]:
        out = [
            f"text: {self.docs} document(s) read, {self.new} new passage(s); "
            f"8-K Item 3.02 filings fetched: {self.f302}; searches: {self.searches}, "
            f"{self.queued} hit document(s) queued, {self.fetched} fetched"
        ]
        out += [f"  {p}: {n} hit(s)" for p, n in sorted(self.phrase_hits.items()) if n]
        return out + [f"  problem: {p}" for p in self.problems]


def _state(engine: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return engine.execute("SELECT * FROM refresh_state WHERE name = ?", (name,)).fetchone()


def _mark(engine: sqlite3.Connection, name: str, ref: str, now: datetime, detail=None) -> None:
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET source_ref = excluded.source_ref, "
        "fetched_at = excluded.fetched_at, detail = excluded.detail",
        (name, ref, iso(now), json.dumps(detail or {})),
    )


def read_stored(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    matcher: Matcher,
    ciks: list[str],
    now: datetime,
    rep: ScanReport,
    *,
    rescan: bool = False,
) -> None:
    """Our companies' stored documents of the last three years; new ones only unless
    `rescan`."""
    last = _state(engine, "fin_text:last_doc")
    after = 0 if rescan or last is None else int(last["source_ref"])
    since = (now - timedelta(days=365 * YEARS)).date().isoformat()
    accs = {
        r[0]: r[1]
        for r in engine.execute(
            f"SELECT accession, filed FROM filing WHERE cik IN ({','.join('?' * len(ciks))}) "
            "AND filed >= ?",
            (*ciks, since),
        )
    }
    top = after
    for d in corpus.execute(
        f"SELECT doc_id, cik, accession FROM document WHERE doc_id > ? AND cik IN "
        f"({','.join('?' * len(ciks))}) ORDER BY doc_id",
        (after, *ciks),
    ).fetchall():
        top = max(top, d["doc_id"])
        if d["accession"] not in accs:
            continue
        doc = _doc(corpus, d["doc_id"], engine)
        name, company = filer_name(engine, matcher, d["cik"])
        rep.docs += 1
        rep.new += links.store(
            engine,
            d["cik"],
            name,
            company,
            doc,
            find.find(doc.text, matcher, self_keys(matcher, d["cik"])),
            now,
        )
    _mark(engine, "fin_text:last_doc", str(top), now)


def fetch_302(
    client: SecClient | None,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    ciks: list[str],
    now: datetime,
    rep: ScanReport,
    cap: int,
) -> None:
    if client is None:
        return
    since = (now - timedelta(days=365 * YEARS)).date().isoformat()
    for cik in ciks:
        for f in engine.execute(
            "SELECT f.accession, f.items FROM filing f JOIN filing_cik c ON c.accession = "
            "f.accession WHERE c.cik = ? AND f.form IN ('8-K', '8-K/A') AND f.filed >= ? "
            "ORDER BY f.filed DESC",
            (cik, since),
        ).fetchall():
            if "3.02" not in (f["items"] or "").split(","):
                continue
            state = f"fin_302:{f['accession']}"
            if _state(engine, state) is not None:
                continue
            if rep.f302 >= cap:
                return
            idx = fetch_filing_index(client, cik, f["accession"])
            rep.f302 += 1
            if isinstance(idx, Failed) and idx.throttled:
                rep.problems.append(f"{f['accession']}: throttled")
                return
            docs = (
                [d for d in idx.data if (d.doc_type or "").startswith(EXHIBITS)]
                if isinstance(idx, Ok)
                else []
            )
            for d in docs:
                if _stored(corpus, d.url) is None:
                    res = client.get_bytes(d.url, ttl_s=DOC_TTL_S)
                    if isinstance(res, Ok):
                        store_document(corpus, cik, f["accession"], d, res.data, now)
            _mark(engine, state, f["accession"], now, {"exhibits": len(docs)})


def search_names(c: Company) -> list[str]:
    """Names not covered by a shorter name followed by a space ("Amazon" covers "Amazon Web
    Services"; EDGAR search matches phrases by whole words)."""
    names = sorted({n for n in c.names if len(n) >= 3}, key=len)
    out: list[str] = []
    for n in names:
        if not any(n.startswith(o + " ") for o in out):
            out.append(n)
    return out


def phrases(c: Company) -> list[str]:
    return [t.format(a=n) for n in search_names(c) for t in TEMPLATES]


def search_company(
    client: SecClient,
    engine: sqlite3.Connection,
    c: Company | None,
    now: datetime,
    rep: ScanReport,
    *,
    force: bool = False,
) -> bool:
    """One company's phrases, or the phrases naming no company (`c` None) → False when
    throttled."""
    state = f"fin_search:{c.key if c else '_global'}"
    row = _state(engine, state)
    if row and not force and now - datetime.fromisoformat(row["fetched_at"]) < REPEAT:
        return True
    start = (now - timedelta(days=30 * MONTHS)).date().isoformat()
    for phrase in phrases(c) if c else GLOBAL:
        res = search(
            client,
            engine,
            phrase,
            forms=FORMS,
            start=start,
            end=now.date().isoformat(),
            now=now,
            max_hits=MAX_HITS,
            allow_fallback=False,
        )
        rep.searches += 1
        if not isinstance(res, Ok):
            rep.problems.append(f"{phrase}: {getattr(res, 'reason', res)}")
            if isinstance(res, Failed) and res.throttled:
                return False
            continue
        rep.phrase_hits[phrase] = res.data.total
        for h in res.data.hits:
            if h.url is None or (c and c.cik and h.cik == c.cik):
                continue
            cur = engine.execute(
                "INSERT OR IGNORE INTO fin_fetch (url, cik, entity_name, accession, filename, "
                "form, file_date, phrase, status, queued_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, "
                "'queued', ?)",
                (
                    h.url,
                    h.cik,
                    h.entity_name,
                    h.accession,
                    h.filename,
                    h.form,
                    h.file_date,
                    phrase,
                    iso(now),
                ),
            )
            rep.queued += cur.rowcount
    _mark(engine, state, c.key if c else "_global", now)
    return True


def fetch_hits(
    client: SecClient | None,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    matcher: Matcher,
    now: datetime,
    rep: ScanReport,
    cap: int,
) -> None:
    for q in engine.execute(
        "SELECT * FROM fin_fetch WHERE status = 'queued' ORDER BY file_date DESC LIMIT ?",
        (cap if client is not None else 0,),
    ).fetchall():
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
            detail = "HTTP 404" if isinstance(res, NotFound) else getattr(res, "reason", "")
            engine.execute(
                "UPDATE fin_fetch SET status = 'failed', detail = ?, done_at = ? WHERE url = ?",
                (detail, iso(now), q["url"]),
            )
            continue
        if res is not None:
            store_document(corpus, q["cik"] or "", q["accession"], doc, res.data, now)
        rep.fetched += 1
        engine.execute(
            "UPDATE fin_fetch SET status = 'stored', done_at = ? WHERE url = ?",
            (iso(now), q["url"]),
        )
        read_hit(engine, corpus, matcher, q, now, rep)


def read_hit(engine, corpus, matcher: Matcher, q, now: datetime, rep: ScanReport) -> None:
    row = corpus.execute("SELECT doc_id FROM document WHERE url = ?", (q["url"],)).fetchone()
    if row is None:
        return
    d = _doc(corpus, row[0], engine)
    doc = links.Doc(d.accession, d.filename, q["form"] or d.form, q["file_date"] or d.filed, d.text)
    company = matcher.by_cik(q["cik"]) if q["cik"] else None
    name = company.name if company else (q["entity_name"] or q["cik"] or "?")
    rep.docs += 1
    rep.new += links.store(
        engine,
        q["cik"],
        name,
        company,
        doc,
        find.find(doc.text, matcher, self_keys(matcher, q["cik"])),
        now,
    )


def reread_hits(engine, corpus, matcher: Matcher, now: datetime, rep: ScanReport) -> None:
    for q in engine.execute("SELECT * FROM fin_fetch WHERE status = 'stored'").fetchall():
        read_hit(engine, corpus, matcher, q, now, rep)
