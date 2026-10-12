"""Federal Register: rules, proposed rules and notices matching theme phrases (D-M02-13).

API (no key): `GET www.federalregister.gov/api/v1/documents.json` with
`conditions[term]="<phrase>"` (full-text search of the document), `conditions[type][]`
RULE / PRORULE / NOTICE, `conditions[publication_date][gte]`, `order=newest`,
`per_page=100`, `fields[]`. Reply: {count, total_pages, next_page_url, results: [{document_number,
type ("Rule", "Proposed Rule", "Notice"), title, abstract, html_url, publication_date,
agencies: [{name, raw_name, …}]}]}.

Stored: number, type, title, agencies, date, link, abstract ≤ 300 characters. A match is
full text: the phrase may sit in a passing sentence of an unrelated rule, so the page shows
the type, agency and abstract and the owner judges; never a signal on its own.
Per phrase: first run looks back `FIRST_DAYS`, later runs from the last success − 3 days;
≤ `MAX_PAGES` pages per phrase a run.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from engine.news.fetch import Fetcher
from engine.official.common import (
    Budget,
    Phrase,
    link_theme,
    snip,
    state_get,
    state_set,
    write,
)
from engine.sec.client import iso
from engine.sec.results import Failed

URL = "https://www.federalregister.gov/api/v1/documents.json"
TYPES = ["RULE", "PRORULE", "NOTICE"]
FIELDS = ["document_number", "type", "title", "abstract", "html_url", "publication_date",
          "agencies"]  # fmt: skip
FIRST_DAYS = 365
OVERLAP_DAYS = 3
MAX_PAGES = 2


@dataclass(frozen=True)
class Doc:
    number: str
    doc_type: str
    title: str
    agencies: str | None
    published: str
    url: str | None
    abstract: str | None


def parse(body: bytes) -> tuple[list[Doc], int] | str:
    """(documents, total pages) or an error text."""
    try:
        data = json.loads(body)
    except ValueError as e:
        return f"unreadable JSON: {e}"
    if not isinstance(data, dict):
        return "unexpected reply shape"
    if data.get("errors"):
        return f"error: {str(data['errors'])[:200]}"
    out = []
    for d in data.get("results") or []:
        if not isinstance(d, dict) or not d.get("document_number") or not d.get("title"):
            continue
        if not d.get("publication_date"):
            continue
        names = [a.get("name") or a.get("raw_name") for a in d.get("agencies") or []
                 if isinstance(a, dict)]  # fmt: skip
        out.append(
            Doc(
                str(d["document_number"]),
                str(d.get("type") or "unspecified"),
                " ".join(str(d["title"]).split()),
                "; ".join(n for n in names if n) or None,
                str(d["publication_date"])[:10],
                d.get("html_url") or None,
                snip(d.get("abstract")),
            )
        )
    return out, int(data.get("total_pages") or (1 if out else 0))


def params(phrase: str, since: date, page: int) -> dict:
    return {
        "conditions[term]": f'"{phrase}"',
        "conditions[type][]": TYPES,
        "conditions[publication_date][gte]": since.isoformat(),
        "order": "newest",
        "per_page": "100",
        "page": str(page),
        "fields[]": FIELDS,
    }


def store(engine: sqlite3.Connection, docs: list[Doc], phrase: Phrase, now: datetime) -> int:
    """Upsert documents and link them to the phrase's theme; returns new documents."""
    new = 0
    with write(engine):
        for d in docs:
            cur = engine.execute(
                "INSERT INTO fedreg_doc (document_number, doc_type, title, agencies, "
                "publication_date, url, abstract, first_seen_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (document_number) DO NOTHING",
                (d.number, d.doc_type, d.title, d.agencies, d.published, d.url, d.abstract,
                 iso(now), iso(now)),
            )  # fmt: skip
            new += cur.rowcount
            link_theme(engine, "fedreg", d.number, phrase.theme_id, phrase.phrase, now)
    return new


@dataclass
class FedRegResult:
    phrases: int = 0
    seen: int = 0
    new: int = 0
    failures: list[str] = field(default_factory=list)
    capped: list[str] = field(default_factory=list)  # phrases with more than MAX_PAGES pages
    stopped: str = ""


def run(
    engine: sqlite3.Connection,
    fetcher: Fetcher,
    phrases: list[Phrase],
    now: datetime,
    budget: Budget,
) -> FedRegResult:
    res = FedRegResult()
    today = now.date()
    for ph in phrases:
        if budget.spent("fedreg"):
            res.stopped = "time budget spent; the rest next run"
            break
        name = f"official:fedreg:{ph.theme_id}:{ph.key}"
        last = state_get(engine, name)
        since = (date.fromisoformat(last[:10]) - timedelta(days=OVERLAP_DAYS) if last
                 else today - timedelta(days=FIRST_DAYS))  # fmt: skip
        if last and last[:10] == today.isoformat():
            continue  # once a day per phrase
        ok, seen, capped = True, 0, False
        for page in range(1, MAX_PAGES + 1):
            got = fetcher.get(URL, lane="fedreg", params=params(ph.phrase, since, page),
                              logged_url=f"{URL}?term={ph.phrase}&page={page}")  # fmt: skip
            if isinstance(got, Failed):
                res.failures.append(f"{ph.phrase}: {got.reason}")
                ok = False
                break
            parsed = parse(got.body)
            if isinstance(parsed, str):
                res.failures.append(f"{ph.phrase}: {parsed}")
                ok = False
                break
            docs, pages = parsed
            seen += len(docs)
            res.new += store(engine, docs, ph, now)
            capped = pages > MAX_PAGES
            if page >= pages or budget.spent("fedreg"):
                break
        res.seen += seen
        if ok:
            res.phrases += 1
            if capped:
                res.capped.append(ph.phrase)
            note = f"{seen} document(s) since {since}" + (" (newest pages only)" if capped else "")
            with write(engine):
                state_set(engine, name, URL, now, note)
    return res
