"""Guidance accuracy loop (M02 part 4b, D-M02-24).

The parser's own review items only catch what it already doubts. These checks look for
errors it is confident about, and every answer becomes a label (engine.guidance_label):

- **Wrong button** (owner): any ledger row can be marked wrong with a reason.
- **Weekly random audit**: each week AUDIT_CALL_ROWS call/IR rows, AUDIT_RELEASE_ROWS
  release row and AUDIT_SKIPPED skipped call sentences are queued (`guidance_audit`) for
  "correct / wrong" or "no guidance / missed". Random samples are the only unbiased
  estimate of the error rate, and they find error types no rule anticipated.
- **Plausibility** (code): capex and revenue guidance compared with the company's last
  reported fiscal-year figure (XBRL); outside the bounds → `guidance_implausible`.
- **Gemini cross-check** (owner-triggered per season, llm/call_check.py): statements the
  code did not store become `guidance_audit` items found by 'gemini'.

A row labelled wrong is deleted and never re-inserted by later scans (labels are keyed by
document + quote offset + metric + period). `accuracy()` reports precision per parser
version from audit samples; `check_labels()` re-runs the current parser over every label,
so a new version shows which past errors it fixes and which correct rows it breaks.
"""

from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from engine.guidance.parse import PARSER_VERSION, ParseResult
from engine.guidance.sources import origin_of, stated_prefix
from engine.sec.client import iso

MODULE = "M11"
REASONS = {
    "wrong_company": "another company's figure (customer, industry, peer)",
    "segment": "a segment or product line, not the company total",
    "past_actual": "a reported actual, not guidance",
    "wrong_period": "right figure, wrong period",
    "wrong_value": "wrong number, unit or bound",
    "not_guidance": "not guidance (example, hypothetical, analyst's number)",
    "missed_guidance": "guidance the parser did not store",
    "other": "other (see note)",
}
AUDIT_CALL_ROWS = 4
AUDIT_RELEASE_ROWS = 1
AUDIT_SKIPPED = 3
# guided value ÷ last reported fiscal-year value (quarters: ÷ a quarter of it)
PLAUSIBLE = {"capex": (Decimal("0.3"), Decimal("3")), "revenue": (Decimal("0.5"), Decimal("2"))}


class LabelError(ValueError):
    pass


def _value_text(r: sqlite3.Row) -> str:
    from engine.llm.guidance_reasons import fmt_range

    if r["kind"] == "direction":
        return f"direction {r['direction']}"
    v = fmt_range(Decimal(str(r["low"])), Decimal(str(r["high"])), r["unit"])
    return stated_prefix(r["kind"], r["bound"]) + v


def describe_row(r: sqlite3.Row) -> str:
    basis = "" if r["basis"] == "unspecified" else f" ({r['basis']})"
    return f"{r['metric']}{basis} {r['period']}: {_value_text(r)}"


def _insert_label(engine: sqlite3.Connection, **f: Any) -> int:
    cols = ", ".join(f)
    return engine.execute(
        f"INSERT INTO guidance_label ({cols}) VALUES ({', '.join('?' * len(f))})",
        tuple(f.values()),
    ).lastrowid


def label_row(
    engine: sqlite3.Connection,
    guidance_id: int,
    verdict: str,
    reason: str | None,
    note: str,
    found_by: str,
    by: str,
    now: datetime,
) -> int:
    """Label a stored ledger row; 'wrong' also removes it (it stays out of later scans).
    Caller owns the transaction."""
    if verdict not in ("right", "wrong"):
        raise LabelError(f"unknown verdict {verdict!r}")
    if verdict == "wrong" and reason not in REASONS:
        raise LabelError("Choose why the row is wrong.")
    r = engine.execute("SELECT * FROM guidance WHERE guidance_id = ?", (guidance_id,)).fetchone()
    if r is None:
        raise LabelError("That guidance row is no longer stored (re-scanned or removed).")
    label_id = _insert_label(
        engine, cik=r["cik"], accession=r["accession"], filename=r["filename"],
        quote_start=r["quote_start"], quote_end=r["quote_end"], quote=r["quote"],
        metric=r["metric"], period=r["period"], value_text=_value_text(r), verdict=verdict,
        reason=reason if verdict == "wrong" else None, note=note or None, found_by=found_by,
        origin=r["origin"], parser_version=r["parser_version"], labelled_by=by,
        labelled_at=iso(now),
    )  # fmt: skip
    if verdict == "wrong":
        engine.execute("DELETE FROM guidance WHERE guidance_id = ?", (guidance_id,))
    return label_id


def current_row(engine: sqlite3.Connection, p: dict[str, Any]) -> int:
    """The stored row a check refers to (ids change on re-scan; offsets and key do not)."""
    r = engine.execute(
        "SELECT guidance_id FROM guidance WHERE accession = ? AND filename = ? AND "
        "quote_start = ? AND metric = ? AND period = ? ORDER BY guidance_id LIMIT 1",
        (p["accession"], p["filename"], p["offsets"][0], p["metric"], p["period"]),
    ).fetchone()
    if r is None:
        raise LabelError("That guidance row is no longer stored (a re-scan changed or removed it).")
    return r[0]


def label_span(
    engine: sqlite3.Connection,
    *,
    cik: str,
    accession: str,
    filename: str,
    start: int,
    end: int,
    quote: str,
    verdict: str,
    note: str,
    found_by: str,
    parser_version: str,
    by: str,
    now: datetime,
) -> int:
    """Label a sentence the parser did not store: 'missed' (it was guidance) or 'right'."""
    if verdict not in ("right", "missed"):
        raise LabelError(f"unknown verdict {verdict!r}")
    return _insert_label(
        engine, cik=cik, accession=accession, filename=filename, quote_start=start,
        quote_end=end, quote=quote, verdict=verdict,
        reason="missed_guidance" if verdict == "missed" else None, note=note or None,
        found_by=found_by, origin=origin_of(accession), parser_version=parser_version,
        labelled_by=by, labelled_at=iso(now),
    )  # fmt: skip


def wrong_keys(
    engine: sqlite3.Connection, accession: str, filename: str
) -> set[tuple[int, str, str]]:
    """(quote_start, metric, period) the owner labelled wrong in this document."""
    return {
        (r[0], r[1], r[2])
        for r in engine.execute(
            "SELECT quote_start, metric, period FROM guidance_label WHERE accession = ? "
            "AND filename = ? AND verdict = 'wrong'",
            (accession, filename),
        )
    }


def store_skips(
    engine: sqlite3.Connection, cik: str, accession: str, filename: str, parsed: ParseResult
) -> None:
    """Replace the document's skipped sentences. Caller owns the transaction."""
    engine.execute(
        "DELETE FROM guidance_skip WHERE accession = ? AND filename = ?", (accession, filename)
    )
    engine.executemany(
        "INSERT OR IGNORE INTO guidance_skip (accession, filename, cik, start_offset, end_offset, "
        "reason, parser_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(accession, filename, cik, u.start, u.end, u.reason, PARSER_VERSION)
         for u in parsed.skipped_spans],
    )  # fmt: skip


def enqueue(
    engine: sqlite3.Connection, kind: str, cik: str, reason: str, payload: dict, now: datetime
) -> int:
    return engine.execute(
        "INSERT INTO review_queue (module_id, kind, cik, reason, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (MODULE, kind, cik, reason, json.dumps(payload), iso(now)),
    ).lastrowid


def labelled_or_queued(
    engine: sqlite3.Connection,
    accession: str,
    start: int,
    kinds: tuple[str, ...] = ("guidance_audit", "guidance_implausible"),
) -> bool:
    """A label exists for this sentence, or an item of `kinds` was already queued for it."""
    marks = ", ".join("?" * len(kinds))
    return bool(
        engine.execute(
            "SELECT 1 FROM guidance_label WHERE accession = ? AND quote_start = ?",
            (accession, start),
        ).fetchone()
        or engine.execute(
            f"SELECT 1 FROM review_queue WHERE kind IN ({marks}) "
            "AND json_extract(payload, '$.accession') = ? "
            "AND json_extract(payload, '$.offsets[0]') = ?",
            (*kinds, accession, start),
        ).fetchone()
    )


def row_payload(r: sqlite3.Row, found_by: str, **extra: Any) -> dict[str, Any]:
    return {
        "sample": "row",
        "found_by": found_by,
        "guidance_id": r["guidance_id"],
        "accession": r["accession"],
        "filename": r["filename"],
        "offsets": [r["quote_start"], r["quote_end"]],
        "text": r["quote"],
        "stored": describe_row(r),
        "metric": r["metric"],
        "period": r["period"],
        "origin": r["origin"],
        "grade": r["grade"],
        "parser_version": r["parser_version"],
        **extra,
    }


# --- Weekly random audit -------------------------------------------------------------


def _week(now: datetime) -> str:
    return (now.date() - timedelta(days=now.weekday())).isoformat()


def queue_audit(engine: sqlite3.Connection, corpus: sqlite3.Connection, now: datetime) -> int:
    """Queue this week's random sample once per week (Monday–Sunday). Returns items queued."""
    week = _week(now)
    state = f"guidance-audit:{week}"
    if engine.execute("SELECT 1 FROM refresh_state WHERE name = ?", (state,)).fetchone():
        return 0
    rng = random.Random(week)  # reproducible for a given week
    queued = 0
    for origins, n in ((("call", "ir"), AUDIT_CALL_ROWS), (("release",), AUDIT_RELEASE_ROWS)):
        marks = ", ".join("?" * len(origins))
        rows = [
            r
            for r in engine.execute(
                f"SELECT * FROM guidance WHERE origin IN ({marks}) AND source != 'owner' "
                "ORDER BY guidance_id",
                origins,
            )
            if not labelled_or_queued(engine, r["accession"], r["quote_start"])
        ]
        for r in rng.sample(rows, min(n, len(rows))):
            enqueue(engine, "guidance_audit", r["cik"],
                     f"Weekly check: is this {r['origin']} row right? {describe_row(r)}",
                     row_payload(r, "audit"), now)  # fmt: skip
            queued += 1
    skips = [
        s
        for s in engine.execute("SELECT * FROM guidance_skip ORDER BY accession, start_offset")
        if not labelled_or_queued(engine, s["accession"], s["start_offset"])
    ]
    for s in rng.sample(skips, min(AUDIT_SKIPPED, len(skips))):
        text = _doc_text(corpus, s["accession"], s["filename"], s["start_offset"], s["end_offset"])
        payload = {"sample": "skipped", "found_by": "audit", "accession": s["accession"],
                   "filename": s["filename"], "offsets": [s["start_offset"], s["end_offset"]],
                   "text": text, "skipped_because": s["reason"],
                   "parser_version": s["parser_version"]}  # fmt: skip
        enqueue(engine, "guidance_audit", s["cik"],
                 f"Weekly check: the parser set this call sentence aside ({s['reason']}). "
                 "Was it guidance?", payload, now)  # fmt: skip
        queued += 1
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) "
        "VALUES (?, 'audit', ?, ?) ON CONFLICT (name) DO NOTHING",
        (state, iso(now), str(queued)),
    )
    return queued


def _doc_text(corpus: sqlite3.Connection, accession: str, filename: str, a: int, b: int) -> str:
    row = corpus.execute(
        "SELECT substr(text, ? + 1, ? - ?) FROM document WHERE accession = ? AND filename = ?",
        (a, b, a, accession, filename),
    ).fetchone()
    return row[0] if row else ""


# --- Plausibility ----------------------------------------------------------------------


def _baseline(
    engine: sqlite3.Connection, cik: str, metric: str, quarter: bool, stated_on: str
) -> tuple[Decimal, str] | None:
    """The latest figure reported before the guidance was given: the last quarter for
    quarterly guidance, the latest trailing four quarters (or fiscal year) for annual
    guidance. Later actuals are not the comparison (a fast grower's next quarters would
    make old guidance look implausible, live check 3)."""
    types = ("Q",) if quarter else ("TTM", "FY")
    marks = ", ".join("?" * len(types))
    row = engine.execute(
        f"SELECT latest_value, period_type, period_end FROM series WHERE cik = ? AND concept = ? "
        f"AND period_type IN ({marks}) AND period_end < ? "
        "ORDER BY period_end DESC, period_type = 'FY' LIMIT 1",
        (cik, metric, *types, stated_on),
    ).fetchone()
    if not row or not row[0]:
        return None
    what = {"Q": "the last reported quarter's", "TTM": "the last four reported quarters'",
            "FY": "the last fiscal year's"}[row[1]]  # fmt: skip
    return abs(Decimal(str(row[0]))), f"{what} {metric} (to {row[2]})"


def plausibility(engine: sqlite3.Connection, r: sqlite3.Row) -> str | None:
    """Why a capex/revenue row looks implausible against the latest reported figure, or None.
    Fast growers stay inside the bounds because the comparison is the latest period, not a
    year-old average (live check 2026-10-09)."""
    if r["metric"] not in PLAUSIBLE or r["kind"] == "direction" or r["unit"] != "USD":
        return None
    quarter = " Q" in r["period"]
    base = _baseline(engine, r["cik"], r["metric"], quarter, r["stated_on"])
    if base is None:
        return None  # nothing to compare with: unknown, not flagged
    actual, what = base
    mid = (Decimal(str(r["low"])) + Decimal(str(r["high"]))) / 2
    lo, hi = PLAUSIBLE[r["metric"]]
    ratio = mid / actual
    if lo <= ratio <= hi:
        return None
    return (f"{r['metric']} {r['period']} guidance is {ratio:.2f}× {what} "
            f"(expected {lo}–{hi}×)")  # fmt: skip


def close_stale(engine: sqlite3.Connection, now: datetime) -> int:
    """Close open checks that no longer apply after a re-scan: the row is gone (the new
    parser no longer produces it) or a plausibility flag no longer fires. Recorded as
    'dismiss' with a note, so the queue shows only live questions."""
    closed = 0
    for it in engine.execute(
        "SELECT item_id, kind, payload FROM review_queue WHERE resolved_at IS NULL "
        "AND kind IN ('guidance_audit', 'guidance_implausible')"
    ).fetchall():
        p = json.loads(it["payload"])
        if p.get("sample") != "row":
            continue
        row = engine.execute(
            "SELECT * FROM guidance WHERE accession = ? AND filename = ? AND quote_start = ? "
            "AND metric = ? AND period = ?",
            (p["accession"], p["filename"], p["offsets"][0], p["metric"], p["period"]),
        ).fetchone()
        if row is None:
            note = f"auto: the parser ({PARSER_VERSION}) no longer stores this row"
        elif it["kind"] == "guidance_implausible" and plausibility(engine, row) is None:
            note = "auto: no longer outside the plausible range"
        else:
            continue
        engine.execute(
            "UPDATE review_queue SET resolved_at = ?, resolution = 'dismiss', resolved_by = "
            "'engine', note = ? WHERE item_id = ?",
            (iso(now), note, it["item_id"]),
        )
        closed += 1
    return closed


def check_plausibility(engine: sqlite3.Connection, now: datetime) -> int:
    """Queue `guidance_implausible` for rows outside the bounds (once per sentence)."""
    queued = 0
    for r in engine.execute(
        "SELECT * FROM guidance WHERE metric IN ('capex', 'revenue') AND kind != 'direction' "
        "ORDER BY guidance_id"
    ).fetchall():
        why = plausibility(engine, r)
        if why and not labelled_or_queued(
            engine, r["accession"], r["quote_start"], ("guidance_implausible",)
        ):
            enqueue(engine, "guidance_implausible", r["cik"], why,
                     row_payload(r, "plausibility", why=why), now)  # fmt: skip
            queued += 1
    return queued


# --- Reports ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Accuracy:
    parser_version: str
    rows_checked: int  # random audit only (unbiased)
    rows_wrong: int
    skipped_checked: int
    skipped_missed: int
    labels_other: int  # owner button, plausibility, Gemini (not a random sample)

    @property
    def precision(self) -> float | None:
        if not self.rows_checked:
            return None
        return 1 - self.rows_wrong / self.rows_checked


def accuracy_line(a: Accuracy) -> str:
    p = "n/a" if a.precision is None else f"{a.precision:.0%}"
    return (f"{a.parser_version}: sampled rows {a.rows_checked}, wrong {a.rows_wrong} "
            f"(precision {p}); sampled skipped sentences {a.skipped_checked}, missed "
            f"{a.skipped_missed}; other labels {a.labels_other}")  # fmt: skip


def accuracy(engine: sqlite3.Connection) -> list[Accuracy]:
    def count(v: str, where: str) -> int:
        return engine.execute(
            f"SELECT count(*) FROM guidance_label WHERE parser_version = ? AND {where}", (v,)
        ).fetchone()[0]

    out = []
    for (v,) in engine.execute(
        "SELECT DISTINCT parser_version FROM guidance_label ORDER BY parser_version DESC"
    ).fetchall():

        def n(where: str, v: str = v) -> int:
            return count(v, where)

        out.append(Accuracy(
            v,
            n("found_by = 'audit' AND metric IS NOT NULL"),
            n("found_by = 'audit' AND metric IS NOT NULL AND verdict = 'wrong'"),
            n("found_by = 'audit' AND metric IS NULL"),
            n("found_by = 'audit' AND metric IS NULL AND verdict = 'missed'"),
            n("found_by != 'audit'"),
        ))  # fmt: skip
    return out


def check_labels(engine: sqlite3.Connection, corpus: sqlite3.Connection) -> list[str]:
    """Re-run the current parser over every labelled sentence: what it now fixes or breaks."""
    from engine.guidance.calls import parse_document

    fixed = still = kept = broken = found = still_missed = 0
    problems: list[str] = []
    cache: dict[tuple[str, str], ParseResult | None] = {}
    for lb in engine.execute("SELECT * FROM guidance_label ORDER BY label_id").fetchall():
        key = (lb["accession"], lb["filename"])
        if key not in cache:
            cache[key] = parse_document(engine, corpus, *key)
        parsed = cache[key]
        if parsed is None:
            problems.append(f"label {lb['label_id']}: document no longer stored")
            continue
        produced = {(i.quote_start, i.metric, i.period) for i in parsed.items} | {
            (d.quote_start, d.metric, d.period) for d in parsed.directions
        }
        in_span = any(lb["quote_start"] <= s < lb["quote_end"] for s, _, _ in produced)
        mine = (lb["quote_start"], lb["metric"], lb["period"]) in produced
        tag = f"label {lb['label_id']} ({lb['verdict']}, {lb['reason'] or '-'})"
        if lb["verdict"] == "wrong":
            if mine:
                still += 1
                problems.append(f"{tag}: still produced: {lb['metric']} {lb['period']}")
            else:
                fixed += 1
        elif lb["verdict"] == "right" and lb["metric"]:
            if mine:
                kept += 1
            else:
                broken += 1
                problems.append(f"{tag}: no longer produced: {lb['metric']} {lb['period']}")
        elif lb["verdict"] == "missed":
            if in_span:
                found += 1
            else:
                still_missed += 1
    head = (f"labels re-checked with {PARSER_VERSION}: wrong rows fixed {fixed}, still wrong "
            f"{still}; right rows kept {kept}, broken {broken}; missed now found {found}, "
            f"still missed {still_missed}")  # fmt: skip
    return [head] + [f"  {p}" for p in problems]
