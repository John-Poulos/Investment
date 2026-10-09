"""Scan call documents into the guidance ledger (M02 part 4; D-M02-6, D-M02-20).

Call documents are listed in engine.call_document: Alpha Vantage transcripts and
company IR files the owner downloaded. Only management speech is parsed
(transcript sections labelled 'call management'; for an IR file, the text before
its question-and-answer heading). Rows carry origin 'call' (grade B) or 'ir' (A).

Release vs call (D-M02-20 (3)): the release wins. For each call item, release rows
of the same metric and period (basis equal, or unspecified on either side) are
compared: the same quarter's release states an equal value → the call row is stored
as grade A with `matched_accession`; a different value → `guidance_conflict` (the
call row is not stored; the release value stands); no release value → the call
fills the gap as grade B, upgraded to A when any other company release states the
same figure. Direction-only rows are stored when no numeric row has that key.
Each scan replaces that document's rows and open review items, like releases.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from engine.guidance.labels import store_skips, wrong_keys
from engine.guidance.ledger import (
    Release,
    _clear,
    _consistent,
    _insert,
    _insert_direction,
    _past_full_year,
    _review,
)
from engine.guidance.parse import (
    PARSER_VERSION,
    Item,
    ParseResult,
    Value,
    ended,
    parse_call,
    parse_release,
)
from engine.guidance.sources import origin_of
from engine.sec.client import iso

MANAGEMENT = "call management"
IR_SECTION = "IR document"
_QA = re.compile(
    r"^\s*(?:question[- ]and[- ]answer(?: session)?|questions? (?:and|&) answers?|q&a(?: session)?)"
    r"\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class CallDoc:
    accession: str
    filename: str
    cik: str
    symbol: str
    quarter: str  # FY2026 Q4
    source: str
    doc_kind: str
    release_accession: str | None
    stated_on: str | None


@dataclass(frozen=True)
class CallScan:
    doc: CallDoc
    outcome: str  # parsed | none | review | no_date | missing
    candidates: int = 0
    items: int = 0
    directions: int = 0
    unparsed: int = 0
    skipped: int = 0
    conflicts: int = 0
    matched: int = 0


def call_documents(engine: sqlite3.Connection, cik: str | None = None) -> list[CallDoc]:
    sql = "SELECT * FROM call_document" + (" WHERE cik = ?" if cik else "")
    rows = engine.execute(sql + " ORDER BY stated_on, accession", (cik,) if cik else ())
    return [
        CallDoc(
            r["accession"],
            r["filename"],
            r["cik"],
            r["symbol"],
            r["quarter"],
            r["source"],
            r["doc_kind"],
            r["release_accession"],
            r["stated_on"],
        )  # fmt: skip
        for r in rows
    ]


def parse_document(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, accession: str, filename: str
) -> ParseResult | None:
    """The current parser's reading of a stored release or call document (labels re-check)."""
    doc = corpus.execute(
        "SELECT doc_id, text FROM document WHERE accession = ? AND filename = ?",
        (accession, filename),
    ).fetchone()
    if doc is None:
        return None
    if origin_of(accession) == "release":
        return parse_release(doc["text"])
    cd = engine.execute(
        "SELECT quarter FROM call_document WHERE accession = ? AND filename = ?",
        (accession, filename),
    ).fetchone()
    turns = management_turns(corpus, doc["doc_id"], doc["text"])
    return parse_call(doc["text"], turns, anchor_of(cd["quarter"]) if cd else None)


def rescan_document(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    accession: str,
    filename: str,
    now: datetime,
) -> None:
    """Re-scan one release or call document (after a label is undone)."""
    if origin_of(accession) == "release":
        from engine.guidance.ledger import earnings_releases, scan_release

        for r in earnings_releases(engine, corpus):
            if (r.accession, r.filename) == (accession, filename):
                scan_release(engine, corpus, r, now)
        return
    for cd in call_documents(engine):
        if (cd.accession, cd.filename) == (accession, filename):
            scan_call(engine, corpus, cd, now)


def anchor_of(quarter: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"FY(\d{4}) Q([1-4])", quarter)
    return (int(m.group(1)), int(m.group(2))) if m else None


def prepared_end(text: str) -> int:
    """End of the prepared remarks in an IR file: the Q&A heading, else the whole text."""
    m = _QA.search(text)
    return m.start() if m else len(text)


def management_turns(corpus: sqlite3.Connection, doc_id: int, text: str) -> list[tuple[int, int]]:
    rows = corpus.execute(
        "SELECT label, start_offset, end_offset FROM section WHERE doc_id = ? "
        "ORDER BY start_offset",
        (doc_id,),
    ).fetchall()
    turns = [(r["start_offset"], r["end_offset"]) for r in rows if r["label"] == MANAGEMENT]
    if turns:
        return turns
    ir = [(r["start_offset"], r["end_offset"]) for r in rows if r["label"] == IR_SECTION]
    return [(a, min(b, prepared_end(text))) for a, b in ir]


def _row_value(r: sqlite3.Row) -> Value:
    low, high = Decimal(str(r["low"])), Decimal(str(r["high"]))
    point = Decimal(str(r["point"])) if r["point"] is not None else None
    return Value(r["kind"], r["unit"], low, high, point, None, None, True, 0, 0, r["bound"])


def _release_rows(engine: sqlite3.Connection, cik: str, item: Item) -> list[sqlite3.Row]:
    return [
        r
        for r in engine.execute(
            "SELECT * FROM guidance WHERE cik = ? AND origin = 'release' AND metric = ? "
            "AND period = ? AND kind != 'direction' AND flag IS NULL ORDER BY stated_on",
            (cik, item.metric, item.period),
        )
        if item.basis == r["basis"] or "unspecified" in (item.basis, r["basis"])
    ]


def release_period(engine: sqlite3.Connection, cd: CallDoc, item: Item) -> Item:
    """A call figure whose period was carried from an earlier sentence takes the period of
    the same quarter's release when that release states the same figure for exactly one
    period (NVIDIA's quarterly opex had taken "the full year" from the sentence before).
    The period offsets then point at the figure's own sentence start (no period text)."""
    if item.quote_start <= item.period_start < item.quote_end or not cd.release_accession:
        return item
    periods = {
        r["period"]
        for r in engine.execute(
            "SELECT * FROM guidance WHERE accession = ? AND metric = ? AND origin = 'release' "
            "AND kind != 'direction'",
            (cd.release_accession, item.metric),
        )
        if (item.basis == r["basis"] or "unspecified" in (item.basis, r["basis"]))
        and _consistent(_row_value(r), item.value)
        and not ended(r["period"], anchor_of(cd.quarter))  # never the quarter just reported
    }
    if len(periods) != 1:
        return item
    return replace(item, period=periods.pop(), period_start=item.quote_start,
                   period_end=item.quote_start)  # fmt: skip


def scan_call(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, cd: CallDoc, now: datetime
) -> CallScan:
    doc = corpus.execute(
        "SELECT doc_id, text, sha256 FROM document WHERE accession = ? AND filename = ?",
        (cd.accession, cd.filename),
    ).fetchone()
    if doc is None:
        return CallScan(cd, "missing")
    if cd.stated_on is None:
        return CallScan(cd, "no_date")  # stored and searchable; no ledger rows without a date
    text, sha = doc["text"], doc["sha256"]
    anchor = anchor_of(cd.quarter)
    parsed = parse_call(text, management_turns(corpus, doc["doc_id"], text), anchor)
    rel = Release(cd.cik, cd.accession, cd.filename, cd.stated_on, doc["doc_id"])
    at = iso(now)

    engine.execute("BEGIN")
    try:
        _clear(engine, rel)
        store_skips(engine, cd.cik, cd.accession, cd.filename, parsed)
        wrong = wrong_keys(engine, cd.accession, cd.filename)
        kept: dict[tuple[str, str, str], Item] = {}
        conflicts = matched = past = 0
        for item in parsed.items:
            item = release_period(engine, cd, item)
            if (item.quote_start, item.metric, item.period) in wrong:
                continue  # the owner labelled this wrong (D-M02-24)
            if _past_full_year(item.period, cd.stated_on) or ended(item.period, anchor):
                past += 1
                _review(engine, rel, "guidance_unparsed",
                        f"{item.metric} {item.period}: period already over at the call "
                        "(likely a reported actual, not guidance)",
                        {"text": text[item.quote_start : item.quote_end],
                         "offsets": [item.quote_start, item.quote_end]}, at)  # fmt: skip
                continue
            key = (item.metric, item.basis, item.period)
            if engine.execute(
                "SELECT 1 FROM guidance WHERE accession = ? AND filename = ? AND metric = ? "
                "AND basis = ? AND period = ? AND source = 'owner'",
                (cd.accession, cd.filename, *key),
            ).fetchone():
                continue
            first = kept.get(key)
            if first is not None:
                if not _consistent(first.value, item.value):
                    conflicts += 1
                    _review(engine, rel, "guidance_conflict",
                            f"{item.metric} {item.basis} {item.period}: two different values "
                            "stated on the call",
                            {"key": list(key),
                             "kept": text[first.quote_start : first.quote_end],
                             "kept_offsets": [first.quote_start, first.quote_end],
                             "other": text[item.quote_start : item.quote_end],
                             "other_offsets": [item.quote_start, item.quote_end]}, at)  # fmt: skip
                continue
            releases = _release_rows(engine, cd.cik, item)
            same_day = [r for r in releases if r["accession"] == cd.release_accession]
            equal = [r for r in releases if _consistent(_row_value(r), item.value)]
            equal_ids = {r["guidance_id"] for r in equal}
            if same_day and not any(r["guidance_id"] in equal_ids for r in same_day):
                conflicts += 1
                r = same_day[0]
                _review(engine, rel, "guidance_conflict",
                        f"{item.metric} {item.basis} {item.period}: the call states a different "
                        "value than the same quarter's release (the release value stands)",
                        {"key": list(key), "cross": True, "kept": r["quote"],
                         "kept_accession": r["accession"], "kept_filename": r["filename"],
                         "other": text[item.quote_start : item.quote_end],
                         "other_offsets": [item.quote_start, item.quote_end]}, at)  # fmt: skip
                continue
            kept[key] = item
            same_ids = {r["guidance_id"] for r in same_day}
            match = next(
                (r for r in equal if r["guidance_id"] in same_ids), equal[0] if equal else None
            )
            if match is not None:
                matched += 1
            _insert(engine, rel, text, sha, item, at,
                    grade="A" if match is not None else None,
                    matched=match["accession"] if match is not None else None)  # fmt: skip
        directions = 0
        seen_dir: dict[tuple[str, str], str] = {}
        for d in parsed.directions:
            k = (d.metric, d.period)
            if (d.quote_start, d.metric, d.period) in wrong:
                continue
            if (d.metric, "unspecified", d.period) in kept or any(
                (m, per) == k for m, _, per in kept
            ):
                continue  # a figure for the same period says more
            if k in seen_dir:
                if seen_dir[k] != d.direction:
                    conflicts += 1
                    _review(engine, rel, "guidance_unparsed",
                            f"{d.metric} {d.period}: different directions stated on the call",
                            {"text": text[d.quote_start : d.quote_end],
                             "offsets": [d.quote_start, d.quote_end]}, at)  # fmt: skip
                continue
            seen_dir[k] = d.direction
            _insert_direction(engine, rel, text, sha, d, at)
            directions += 1
        seen: set[str] = set()
        for u in parsed.unparsed:
            if text[u.start : u.end] in seen:
                continue
            seen.add(text[u.start : u.end])
            _review(engine, rel, "guidance_unparsed",
                    f"capex sentence on the call not parsed ({u.reason})",
                    {"text": text[u.start : u.end], "offsets": [u.start, u.end]}, at)  # fmt: skip
        stored = len(kept) + directions
        outcome = "parsed" if stored else ("review" if seen or past or conflicts else "none")
        engine.execute(
            "INSERT INTO guidance_scan (accession, filename, cik, filed, outcome, candidates, "
            "items, unparsed, conflicts, parser_version, at, skipped) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (accession, filename) "
            "DO UPDATE SET filed = excluded.filed, outcome = excluded.outcome, "
            "candidates = excluded.candidates, items = excluded.items, "
            "unparsed = excluded.unparsed, conflicts = excluded.conflicts, "
            "parser_version = excluded.parser_version, at = excluded.at, "
            "skipped = excluded.skipped",
            (cd.accession, cd.filename, cd.cik, cd.stated_on, outcome, parsed.candidates, stored,
             len(seen) + past, conflicts, PARSER_VERSION, at, parsed.skipped),
        )  # fmt: skip
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return CallScan(cd, outcome, parsed.candidates, len(kept), directions, len(seen) + past,
                    parsed.skipped, conflicts, matched)  # fmt: skip


def scan_calls(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    now: datetime,
    *,
    force: bool = False,
    ciks: set[str] | None = None,
) -> list[CallScan]:
    """Scan call documents not yet scanned with this parser version, plus every call of
    `ciks` (companies whose releases were just re-scanned), or all if force."""
    from engine.calls.transcripts import relink

    relinked = relink(engine)
    done = {
        (r[0], r[1])
        for r in engine.execute(
            "SELECT accession, filename FROM guidance_scan WHERE parser_version = ?",
            (PARSER_VERSION,),
        )
    }
    return [
        scan_call(engine, corpus, cd, now)
        for cd in call_documents(engine)
        if force
        or (cd.accession, cd.filename) not in done
        or (cd.accession, cd.filename) in relinked
        or (ciks and cd.cik in ciks)
    ]
