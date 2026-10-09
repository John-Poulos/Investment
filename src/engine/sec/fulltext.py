"""EDGAR full-text search (M00_SEARCH Tier 1; M00_SEC_DATA fulltext.py; M02 discovery).

The one EFTS client. Rules carried over from the owner's bd_tools (confirmed there in
production):
- One quoted phrase per query. Several phrases must all appear in one document,
  which kills recall; run one query per phrase and merge by accession instead.
- No field syntax or OR groups in `q` (EFTS treats them as literal phrase text).
- Forms and dates are parameters (`forms`, `dateRange=custom`, `startdt`, `enddt`);
  `forms` matches root forms, so amendments are included.
- SIC filtering happens after the fetch (no server-side SIC parameter).
- At most three EFTS queries in flight at once.

EFTS reports at most 10,000 hits; totals at that cap are flagged `capped`, so a
count is never mistaken for the true total. If a quoted phrase fails (EFTS has
returned HTTP 500 for some quoted terms), the unquoted terms are tried and the
result is labeled `terms (fallback)`: weaker evidence, never silently mixed.
EFTS returns no matched text; fetch the document (documents.py) to read it.

Each response also carries an `entity_filter` aggregation (filers by hit count). It
lists only the top buckets (~30, observed by others; confirm live), so it gives a
lower bound on distinct companies when not every hit was fetched (M02 D-M02-14).
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

from engine.sec.client import SecClient, iso
from engine.sec.documents import ARCHIVES
from engine.sec.identity import normalize_cik
from engine.sec.results import Failed, NotFound, Ok, Result

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
EFTS_CAP = 10_000
MAX_IN_FLIGHT = 3
RECENT_TTL_S = 6 * 3600  # windows touching the last week still change
CLOSED_TTL_S = 30 * 86400  # older windows change little (late filings, re-indexing)
VARIANT_PHRASE = "phrase"
VARIANT_TERMS = "terms (fallback)"

_SLOTS = threading.BoundedSemaphore(MAX_IN_FLIGHT)
_FIELD_SYNTAX = re.compile(r"\b[a-z_]+:\S|[()]|\b(AND|OR|NOT)\b")


class QueryError(ValueError):
    """The query breaks an EFTS rule (more than one phrase, field syntax, OR groups)."""


def normalize_phrase(text: str) -> str:
    """One phrase, quoted: 'high bandwidth memory' or '"HBM3E"' → '"high bandwidth memory"'."""
    raw = text.strip()
    quotes = raw.count('"')
    wrapped = quotes == 2 and raw.startswith('"') and raw.endswith('"')
    if quotes not in (0, 2) or (quotes == 2 and not wrapped):
        raise QueryError(f"one phrase per query, got {text!r}")
    inner = raw.strip('"').strip()
    if not inner:
        raise QueryError("empty query")
    if _FIELD_SYNTAX.search(inner):
        raise QueryError(f"no field syntax, operators or groups in the query: {text!r}")
    return f'"{" ".join(inner.split())}"'


@dataclass(frozen=True)
class Hit:
    accession: str
    filename: str
    cik: str | None  # first filer CIK listed
    ciks: tuple[str, ...]
    entity_name: str | None
    form: str | None
    file_date: str | None
    period_end: str | None
    sics: tuple[str, ...]
    description: str | None

    @property
    def url(self) -> str | None:
        if not self.cik:
            return None
        folder = f"{ARCHIVES}/{int(self.cik)}/{self.accession.replace('-', '')}/"
        return urljoin(folder, self.filename)


@dataclass(frozen=True)
class SearchPage:
    phrase: str
    variant: str
    total: int
    capped: bool
    hits: tuple[Hit, ...]
    entities: tuple[str, ...] = ()  # entity_filter bucket keys (top filers only)
    entities_other: int | None = None  # hits outside those buckets, when reported


_CIK_IN_KEY = re.compile(r"CIK\s*0*(\d+)")


def parse_entities(data: dict[str, Any]) -> tuple[tuple[str, ...], int | None]:
    """Filer keys from the `entity_filter` aggregation: the CIK when the key shows one,
    else the key itself. Missing aggregation → ((), None)."""
    agg = (data.get("aggregations") or {}).get("entity_filter")
    if not isinstance(agg, dict):
        return (), None
    keys = []
    for b in agg.get("buckets") or []:
        key = str(b.get("key", "")).strip()
        if not key:
            continue
        m = _CIK_IN_KEY.search(key)
        keys.append(normalize_cik(m.group(1)) or key if m else key)
    other = agg.get("sum_other_doc_count")
    return tuple(dict.fromkeys(keys)), int(other) if isinstance(other, int) else None


def parse_hits(data: dict[str, Any]) -> tuple[int, bool, list[Hit]]:
    hits_root = data.get("hits")
    if not isinstance(hits_root, dict):
        raise ValueError("EFTS response has no 'hits'")
    total_raw = hits_root.get("total", {})
    if isinstance(total_raw, dict):
        total = int(total_raw.get("value", 0))
        capped = total_raw.get("relation") == "gte" or total >= EFTS_CAP
    else:
        total = int(total_raw or 0)
        capped = total >= EFTS_CAP
    out = []
    for h in hits_root.get("hits") or []:
        src = h.get("_source") or {}
        accession, _, filename = str(h.get("_id", "")).partition(":")
        accession = accession or str(src.get("adsh", ""))
        if not accession:
            continue
        ciks = tuple(c for c in (normalize_cik(x) for x in src.get("ciks") or []) if c)
        names = src.get("display_names") or []
        name = names[0].split("(")[0].strip() if names else None
        out.append(
            Hit(
                accession=accession,
                filename=filename,
                cik=ciks[0] if ciks else None,
                ciks=ciks,
                entity_name=name or None,
                form=src.get("form") or src.get("file_type"),
                file_date=src.get("file_date"),
                period_end=src.get("period_ending"),
                sics=tuple(str(s) for s in src.get("sics") or []),
                description=src.get("file_description"),
            )
        )
    return total, capped, out


def _ttl(end: str) -> float:
    return (
        CLOSED_TTL_S if date.fromisoformat(end) < date.today() - timedelta(days=7) else RECENT_TTL_S
    )


def search_page(
    client: SecClient,
    phrase: str,
    *,
    forms: Sequence[str],
    start: str,
    end: str,
    offset: int = 0,
    allow_fallback: bool = True,
) -> Result[SearchPage]:
    """One page of hits (EFTS pages by `from`)."""
    quoted = normalize_phrase(phrase)
    if offset >= EFTS_CAP:
        return Failed(f"EFTS returns at most {EFTS_CAP} hits; offset {offset} is beyond it")
    params = {
        "q": quoted,
        "forms": ",".join(forms),
        "dateRange": "custom",
        "startdt": start,
        "enddt": end,
    }
    if offset:
        params["from"] = str(offset)

    variants = [(VARIANT_PHRASE, quoted)]
    if allow_fallback and " " in quoted:
        variants.append((VARIANT_TERMS, quoted.strip('"')))
    last: Failed | NotFound | None = None
    for variant, q in variants:
        with _SLOTS:
            res = client.get_json(EFTS_URL, {**params, "q": q}, ttl_s=_ttl(end))
        if isinstance(res, Ok):
            try:
                total, capped, hits = parse_hits(res.data)
                entities, other = parse_entities(res.data)
            except (ValueError, TypeError) as exc:
                return Failed(f"EFTS response unreadable: {exc}", url=EFTS_URL)
            return Ok(SearchPage(quoted, variant, total, capped, tuple(hits), entities, other),
                      source_ref=res.source_ref, fetched_at=res.fetched_at,
                      from_cache=res.from_cache)  # fmt: skip
        if isinstance(res, Failed) and (res.throttled or (res.status or 0) < 500):
            return res  # only server errors justify trying the unquoted terms
        last = res if isinstance(res, Failed | NotFound) else None
    assert last is not None
    return last


@dataclass(frozen=True)
class SearchResult:
    query_id: int
    phrase: str
    variant: str
    total: int
    capped: bool
    hits: tuple[Hit, ...]
    sic_dropped: int = 0
    incomplete: tuple[str, ...] = field(default_factory=tuple)  # pages that failed
    entities: tuple[str, ...] = ()  # entity_filter keys from the first page (top filers)
    entities_other: int | None = None

    @property
    def complete(self) -> bool:
        """Every hit was fetched, so distinct filings and companies are exact."""
        return not self.capped and not self.incomplete and len(self.hits) >= self.total


def search(
    client: SecClient,
    engine: sqlite3.Connection,
    phrase: str,
    *,
    forms: Sequence[str],
    start: str,
    end: str,
    now: datetime,
    max_hits: int = 100,
    sics: Iterable[str] | None = None,
    allow_fallback: bool = True,
) -> Result[SearchResult]:
    """Search one phrase, page up to `max_hits`, filter by SIC after the fetch, store it.

    Hits without SIC codes are kept when filtering (unknown, not excluded).
    """
    sic_set = {str(s) for s in sics} if sics else None
    first = search_page(client, phrase, forms=forms, start=start, end=end,
                        allow_fallback=allow_fallback)  # fmt: skip
    if not isinstance(first, Ok):
        return first
    page = first.data
    hits = list(page.hits)
    incomplete = []
    limit = min(max_hits, page.total, EFTS_CAP)
    while len(hits) < limit and page.hits:
        nxt = search_page(client, phrase, forms=forms, start=start, end=end, offset=len(hits),
                          allow_fallback=False)  # fmt: skip
        if not isinstance(nxt, Ok):
            incomplete.append(f"offset {len(hits)}: {getattr(nxt, 'reason', nxt)}")
            break
        if nxt.data.variant != page.variant or not nxt.data.hits:
            break
        hits.extend(nxt.data.hits)
    hits = hits[:max_hits]

    kept = [h for h in hits if sic_set is None or not h.sics or set(h.sics) & sic_set]
    query_id = _store(engine, page, forms, start, end, kept, sic_set, now)
    return Ok(
        SearchResult(query_id, page.phrase, page.variant, page.total, page.capped, tuple(kept),
                     len(hits) - len(kept), tuple(incomplete), page.entities,
                     page.entities_other),
        source_ref=first.source_ref, fetched_at=iso(now),
    )  # fmt: skip


def _store(
    engine: sqlite3.Connection,
    page: SearchPage,
    forms: Sequence[str],
    start: str,
    end: str,
    hits: list[Hit],
    sic_set: set[str] | None,
    now: datetime,
) -> int:
    engine.execute("BEGIN")
    try:
        query_id = engine.execute(
            "INSERT INTO fulltext_query (phrase, variant, forms, start_date, end_date, total, "
            "capped, hits_kept, sic_filter, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (page.phrase, page.variant, ",".join(forms), start, end, page.total,
             int(page.capped), len(hits), json.dumps(sorted(sic_set)) if sic_set else None,
             iso(now)),
        ).lastrowid  # fmt: skip
        engine.executemany(
            "INSERT INTO fulltext_hit (query_id, accession, filename, cik, entity_name, form, "
            "file_date, period_end, sics) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            [(query_id, h.accession, h.filename, h.cik, h.entity_name, h.form, h.file_date,
              h.period_end, json.dumps(list(h.sics))) for h in hits],
        )  # fmt: skip
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    assert query_id is not None
    return query_id


@dataclass(frozen=True)
class WindowCount:
    """Hits in one date window. EFTS counts documents (a filing whose exhibits also
    match counts more than once), so distinct filings and companies are given when
    every hit was fetched; otherwise they stay missing (None), never estimated."""

    start: str
    end: str
    total: int | None  # documents; None when the window failed (missing, not zero)
    capped: bool
    variant: str | None
    filings: int | None = None  # distinct accessions, when all hits were fetched
    companies: int | None = None  # distinct filer CIKs, when all hits were fetched
    error: str | None = None


def count_by_window(
    client: SecClient,
    engine: sqlite3.Connection,
    phrase: str,
    *,
    forms: Sequence[str],
    windows: Iterable[tuple[str, str]],
    now: datetime,
    max_hits: int = 300,
) -> list[WindowCount]:
    """Hit counts per date window (M02 trend signal); each window stored with its date.

    Uses the phrase only (no fallback), so every window counts the same thing.
    Fetches up to `max_hits` hits per window to count distinct filings and companies.
    """
    out = []
    for start, end in windows:
        res = search(client, engine, phrase, forms=forms, start=start, end=end, now=now,
                     max_hits=max_hits, allow_fallback=False)  # fmt: skip
        if not isinstance(res, Ok):
            reason = res.reason if isinstance(res, Failed) else str(res)
            out.append(WindowCount(start, end, None, False, None, error=reason))
            continue
        r = res.data
        complete = r.complete
        out.append(
            WindowCount(
                start,
                end,
                r.total,
                r.capped,
                r.variant,
                filings=len({h.accession for h in r.hits}) if complete else None,
                companies=len({h.cik for h in r.hits if h.cik}) if complete else None,
            )  # fmt: skip
        )
    return out


def yearly_windows(first_year: int, last_year: int) -> list[tuple[str, str]]:
    return [(f"{y}-01-01", f"{y}-12-31") for y in range(first_year, last_year + 1)]


def merge_by_accession(results: Iterable[SearchResult]) -> dict[str, list[str]]:
    """Accession → phrases that matched it (one query per phrase, merged; bd_tools rule)."""
    merged: dict[str, list[str]] = {}
    for r in results:
        for h in r.hits:
            merged.setdefault(h.accession, [])
            if r.phrase not in merged[h.accession]:
                merged[h.accession].append(r.phrase)
    return merged
