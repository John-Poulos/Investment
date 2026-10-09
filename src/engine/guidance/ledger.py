"""Scan stored earnings releases into the R19 guidance ledger (M00_SEARCH D-SRCH-11).

Releases = EX-99.1 exhibits of 8-Ks that report Item 2.02. Each scan replaces
that release's ledger rows and open review items, so re-running is safe.
Same metric/basis/period stated twice with equal values (e.g. sentence and
table) is stored once; different values keep the first and open a
`guidance_conflict` review item. Sentences that look like guidance but do not
parse open a `guidance_unparsed` review item with the exact sentence; so does a
full-year period that ended before the release (a reported actual, not guidance).
Rows the owner entered by hand (source 'owner', review queue) survive re-scans and
take precedence; items the owner already resolved are not re-opened.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from engine.guidance.parse import PARSER_VERSION, Direction, Item, Value, clause_of, parse_release
from engine.guidance.sources import default_grade, origin_of
from engine.sec.client import iso

RELEASE_TYPES = ("EX-99.1", "EX-99.01", "EX-99")
REVIEW_KINDS = ("guidance_unparsed", "guidance_conflict")


@dataclass(frozen=True)
class Release:
    cik: str
    accession: str
    filename: str
    filed: str
    doc_id: int


@dataclass(frozen=True)
class ScanResult:
    release: Release
    outcome: str  # parsed | none | review
    candidates: int
    items: int
    unparsed: int
    conflicts: int


def earnings_releases(engine: sqlite3.Connection, corpus: sqlite3.Connection) -> list[Release]:
    """Stored earnings-release exhibits (8-K Item 2.02), oldest first."""
    filings = {
        r["accession"]: r["filed"]
        for r in engine.execute(
            "SELECT accession, filed, items FROM filing WHERE form IN ('8-K', '8-K/A')"
        )
        if r["items"] and "2.02" in r["items"].split(",")
    }
    marks = ", ".join("?" * len(RELEASE_TYPES))
    out = [
        Release(r["cik"], r["accession"], r["filename"], filings[r["accession"]], r["doc_id"])
        for r in corpus.execute(
            f"SELECT doc_id, cik, accession, filename FROM document WHERE doc_type IN ({marks})",
            RELEASE_TYPES,
        )
        if r["accession"] in filings
    ]
    return sorted(out, key=lambda r: (r.filed, r.accession, r.filename))


def _n(d: Decimal | None) -> str | None:
    """Exact decimal text for a NUMERIC column."""
    if d is None:
        return None
    return format(d.normalize(), "f")


def _past_full_year(period: str, filed: str) -> bool:
    """FY2025 (or 'FY2025 remaining') stated in a release filed in 2026 or later.

    Quarters are not checked: fiscal calendars differ, and a quarter label alone
    cannot be placed in time without the company's fiscal year end.
    """
    parts = period.split()
    if len(parts) > 1 and parts[1] != "remaining":
        return False
    return int(parts[0][2:]) < int(filed[:4])


TAX_RATE_SANE = (Decimal(0), Decimal(50))  # percent; outside → near-zero pretax base


def quality_flag(item: Item) -> tuple[str | None, str | None]:
    """('not_meaningful', reason) for ratio guidance on a near-zero base (D-SRCH-15).

    Flagged rows are stored as stated, shown with the reason, and excluded from
    guidance-vs-actual scoring and LLM trend input.
    """
    v = item.value
    lo, hi = TAX_RATE_SANE
    if item.metric == "tax_rate" and (v.low < lo or v.high > hi):
        return (
            "not_meaningful",
            f"tax rate outside {lo}-{hi}%: pretax income near zero makes the ratio swing "
            "(e.g. Intel guided 476% for Q4 2025; actual 198.5%)",
        )
    return None, None


def _consistent(a: Value, b: Value) -> bool:
    """Same value, or a bare point equal to the other's centre ('74.8%' vs '74.8% ± 50 bps').
    A bound ('more than $25 billion') equals only the same bound."""
    if a.bound != b.bound:
        return False
    if (a.low, a.high) == (b.low, b.high):
        return True
    for x, y in ((a, b), (b, a)):
        if x.kind in ("point", "approx") and y.point is not None and x.low == y.point:
            return True
    return False


def _clear(engine: sqlite3.Connection, release: Release) -> None:
    engine.execute(
        "DELETE FROM guidance WHERE accession = ? AND filename = ? AND source != 'owner'",
        (release.accession, release.filename),
    )
    marks = ", ".join("?" * len(REVIEW_KINDS))
    engine.execute(
        f"DELETE FROM review_queue WHERE resolved_at IS NULL AND kind IN ({marks}) "
        "AND json_extract(payload, '$.accession') = ? AND json_extract(payload, '$.filename') = ?",
        (*REVIEW_KINDS, release.accession, release.filename),
    )


def _review(
    engine: sqlite3.Connection, release: Release, kind: str, reason: str, payload: dict, now: str
) -> None:
    payload = {"accession": release.accession, "filename": release.filename, **payload}
    same = payload.get("text") or payload.get("other")
    for r in engine.execute(
        "SELECT payload FROM review_queue WHERE resolved_at IS NOT NULL AND kind = ? "
        "AND json_extract(payload, '$.accession') = ? AND json_extract(payload, '$.filename') = ?",
        (kind, release.accession, release.filename),
    ):
        old = json.loads(r[0])
        if (old.get("text") or old.get("other")) == same:
            return  # the owner already resolved this exact item; a re-scan does not re-open it
    engine.execute(
        "INSERT INTO review_queue (module_id, kind, cik, reason, payload, created_at) "
        "VALUES ('M11', ?, ?, ?, ?, ?)",
        (kind, release.cik, reason, json.dumps(payload), now),
    )


def _insert(
    engine: sqlite3.Connection,
    release: Release,
    text: str,
    sha: str,
    item: Item,
    now: str,
    *,
    grade: str | None = None,
    matched: str | None = None,
) -> None:
    v, p = item.value, item.prior
    origin = origin_of(release.accession)
    engine.execute(
        "INSERT INTO guidance (cik, accession, filename, metric, basis, period, unit, kind, low, "
        "high, point, spread, spread_kind, prior_low, prior_high, stated_on, source, quote, "
        "quote_start, quote_end, period_quote, period_start, period_end, doc_sha256, "
        "parser_version, created_at, flag, flag_reason, origin, grade, matched_accession, "
        f"clause, bound) VALUES ({', '.join('?' * 33)})",
        (
            release.cik,
            release.accession,
            release.filename,
            item.metric,
            item.basis,
            item.period,
            v.unit,
            v.kind,
            _n(v.low),
            _n(v.high),
            _n(v.point),
            _n(v.spread),
            v.spread_kind,
            _n(p.low) if p else None,
            _n(p.high) if p else None,
            release.filed,
            item.source,
            text[item.quote_start : item.quote_end],
            item.quote_start,
            item.quote_end,
            text[item.period_start : item.period_end],
            item.period_start,
            item.period_end,
            sha,
            PARSER_VERSION,
            now,
            *quality_flag(item),
            origin,
            grade or default_grade(origin),
            matched,
            clause_of(text, item),
            v.bound,
        ),
    )


def _insert_direction(
    engine: sqlite3.Connection, release: Release, text: str, sha: str, d: Direction, now: str
) -> None:
    """Direction-only row (D-M02-20): no figure, low/high NULL; scored later by direction."""
    origin = origin_of(release.accession)
    engine.execute(
        "INSERT INTO guidance (cik, accession, filename, metric, basis, period, unit, kind, "
        "stated_on, source, quote, quote_start, quote_end, period_quote, period_start, "
        "period_end, doc_sha256, parser_version, created_at, origin, grade, direction) "
        "VALUES (?, ?, ?, ?, 'unspecified', ?, 'USD', 'direction', ?, 'sentence', ?, ?, ?, ?, ?, "
        "?, ?, ?, ?, ?, ?, ?)",
        (
            release.cik,
            release.accession,
            release.filename,
            d.metric,
            d.period,
            release.filed,
            text[d.quote_start : d.quote_end],
            d.quote_start,
            d.quote_end,
            text[d.period_start : d.period_end],
            d.period_start,
            d.period_end,
            sha,
            PARSER_VERSION,
            now,
            origin,
            default_grade(origin),
            d.direction,
        ),
    )


def scan_release(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, release: Release, now: datetime
) -> ScanResult:
    doc = corpus.execute(
        "SELECT text, sha256 FROM document WHERE doc_id = ?", (release.doc_id,)
    ).fetchone()
    text, sha = doc["text"], doc["sha256"]
    parsed = parse_release(text)
    at = iso(now)

    engine.execute("BEGIN")
    try:
        _clear(engine, release)
        from engine.guidance.labels import wrong_keys

        wrong = wrong_keys(engine, release.accession, release.filename)
        kept: dict[tuple[str, str, str], Item] = {}
        conflicts = 0
        past = 0
        for item in parsed.items:
            if _past_full_year(item.period, release.filed):
                past += 1
                _review(
                    engine,
                    release,
                    "guidance_unparsed",
                    f"{item.metric} {item.period}: full-year period ended before the release "
                    "(likely a reported actual, not guidance)",
                    {
                        "text": text[item.quote_start : item.quote_end],
                        "offsets": [item.quote_start, item.quote_end],
                    },
                    at,
                )
                continue
            if (item.quote_start, item.metric, item.period) in wrong:
                continue  # the owner labelled this wrong (D-M02-24)
            key = (item.metric, item.basis, item.period)
            if engine.execute(
                "SELECT 1 FROM guidance WHERE accession = ? AND filename = ? AND metric = ? "
                "AND basis = ? AND period = ? AND source = 'owner'",
                (release.accession, release.filename, *key),
            ).fetchone():
                continue  # the owner entered this one by hand; it takes precedence
            first = kept.get(key)
            if first is None:
                kept[key] = item
                _insert(engine, release, text, sha, item, at)
            elif not _consistent(first.value, item.value):
                conflicts += 1
                _review(
                    engine,
                    release,
                    "guidance_conflict",
                    f"{item.metric} {item.basis} {item.period}: two different values stated",
                    {
                        "key": list(key),
                        "kept": text[first.quote_start : first.quote_end],
                        "kept_offsets": [first.quote_start, first.quote_end],
                        "other": text[item.quote_start : item.quote_end],
                        "other_offsets": [item.quote_start, item.quote_end],
                    },
                    at,
                )
        seen: set[str] = set()
        for u in parsed.unparsed:
            if text[u.start : u.end] in seen:
                continue  # same sentence repeated in the release
            seen.add(text[u.start : u.end])
            _review(
                engine,
                release,
                "guidance_unparsed",
                f"guidance-like sentence not parsed ({u.reason})",
                {"text": text[u.start : u.end], "offsets": [u.start, u.end]},
                at,
            )
        if kept:
            outcome = "parsed"
        elif seen or past:
            outcome = "review"
        else:
            outcome = "none"
        engine.execute(
            "INSERT INTO guidance_scan (accession, filename, cik, filed, outcome, candidates, "
            "items, unparsed, conflicts, parser_version, at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (accession, filename) DO UPDATE "
            "SET outcome = excluded.outcome, candidates = excluded.candidates, "
            "items = excluded.items, unparsed = excluded.unparsed, "
            "conflicts = excluded.conflicts, parser_version = excluded.parser_version, "
            "at = excluded.at",
            (
                release.accession,
                release.filename,
                release.cik,
                release.filed,
                outcome,
                parsed.candidates,
                len(kept),
                len(seen) + past,
                conflicts,
                PARSER_VERSION,
                at,
            ),
        )
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return ScanResult(release, outcome, parsed.candidates, len(kept), len(seen) + past, conflicts)


def scan_all(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    now: datetime,
    *,
    force: bool = False,
) -> list[ScanResult]:
    """Scan every stored release not yet scanned with this parser version (all if force)."""
    done = {
        (r["accession"], r["filename"])
        for r in engine.execute(
            "SELECT accession, filename FROM guidance_scan WHERE parser_version = ?",
            (PARSER_VERSION,),
        )
    }
    return [
        scan_release(engine, corpus, r, now)
        for r in earnings_releases(engine, corpus)
        if force or (r.accession, r.filename) not in done
    ]
