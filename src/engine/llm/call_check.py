"""Gemini cross-check of call guidance (M02 part 4b, D-M02-24; owner-triggered, D28).

Gemini reads the management turns of one stored call (no other text) and lists every
statement of the company's own future results or spending, each with an exact quote.
Quotes are verified against the turn (unverified → `llm_rejected`, never a fact). Each
verified statement is compared with what the code did with that sentence:

- matched: a ledger row (or a direction-only row) comes from the same sentence;
- in review: the code already queued the sentence;
- code missed: neither → a `guidance_audit` item (found by 'gemini') asks the owner
  "missed / no guidance"; the answer becomes a label (engine/guidance/labels.py).

Gemini's list is never stored as guidance: it only points the owner at sentences. LLM
extraction is precise but low-recall (S85), so a row Gemini did not list is not doubted.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.guidance.calls import IR_SECTION, MANAGEMENT, prepared_end
from engine.guidance.labels import enqueue, labelled_or_queued
from engine.guidance.parse import PARSER_VERSION
from engine.llm.runs import Citation, Observation, Request, RunResult
from engine.llm.verify import normalize, quote_found

USE_CASE = "call_guidance_check"
PROMPT_VERSION = "call_check-1"
SYSTEM = (Path(__file__).parent / "prompts" / "call_check_1.md").read_text(encoding="utf-8")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "statements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "turn_id": {"type": "string"},
                    "quote": {"type": "string"},
                    "metric": {"type": "string"},
                    "period": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["turn_id", "quote", "metric", "period", "value"],
            },
        }
    },
    "required": ["statements"],
}


@dataclass(frozen=True)
class Turn:
    label: str  # T1, T2, ...
    start: int
    end: int
    title: str
    text: str


@dataclass(frozen=True)
class Prepared:
    request: Request | None
    turns: list[Turn]
    cik: str
    accession: str
    filename: str
    sha256: str


def locate(quote: str, text: str, start: int, end: int) -> tuple[int, int] | None:
    """Offsets of a verified quote in the document (whitespace and punctuation tolerant)."""
    words = normalize(quote).strip(" .…\"'").split()
    if not words:
        return None
    pattern = r"\s+".join(re.escape(w) for w in words)
    pattern = pattern.replace('"', '["“”]').replace("'", "['‘’]").replace(r"\-", "[-–—−]")
    m = re.compile(pattern).search(text, start, end)
    return (m.start(), m.end()) if m else None


def _turns(corpus: sqlite3.Connection, doc_id: int, text: str) -> list[Turn]:
    rows = corpus.execute(
        "SELECT label, title, start_offset, end_offset FROM section WHERE doc_id = ? "
        "AND label IN (?, ?) ORDER BY start_offset",
        (doc_id, MANAGEMENT, IR_SECTION),
    ).fetchall()
    out = []
    for r in rows:
        a = r["start_offset"]
        b = (
            r["end_offset"]
            if r["label"] == MANAGEMENT
            else min(r["end_offset"], prepared_end(text))
        )
        out.append(Turn(f"T{len(out) + 1}", a, b, r["title"] or "", text[a:b]))
    return out


def prepare(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, accession: str, filename: str
) -> Prepared | None:
    doc = corpus.execute(
        "SELECT doc_id, cik, text, sha256 FROM document WHERE accession = ? AND filename = ?",
        (accession, filename),
    ).fetchone()
    cd = engine.execute(
        "SELECT symbol, quarter, doc_kind FROM call_document WHERE accession = ? AND filename = ?",
        (accession, filename),
    ).fetchone()
    if doc is None or cd is None:
        return None
    text = doc["text"]
    turns = _turns(corpus, doc["doc_id"], text)
    if not turns:
        return Prepared(None, [], doc["cik"], accession, filename, doc["sha256"])
    name = engine.execute("SELECT name FROM entity WHERE cik = ?", (doc["cik"],)).fetchone()
    lines = [
        f"Company: {name['name'] if name else cd['symbol']}",
        f"Call: fiscal {cd['quarter']} ({cd['doc_kind'].replace('_', ' ')})",
        "",
        "Management turns:",
    ]
    for t in turns:
        lines += [f"[{t.label}] {t.title}", t.text.strip(), ""]
    req = Request(USE_CASE, doc["cik"], PROMPT_VERSION, SYSTEM, "\n".join(lines), SCHEMA,
                  _check(engine, turns, accession, filename, doc["sha256"], text))  # fmt: skip
    return Prepared(req, turns, doc["cik"], accession, filename, doc["sha256"])


def _status(engine: sqlite3.Connection, accession: str, filename: str, a: int, b: int) -> str:
    """matched | in_review | code_missed for the sentence at [a, b)."""
    if engine.execute(
        "SELECT 1 FROM guidance WHERE accession = ? AND filename = ? AND quote_start < ? "
        "AND quote_end > ?",
        (accession, filename, b, a),
    ).fetchone():
        return "matched"
    if engine.execute(
        "SELECT 1 FROM review_queue WHERE resolved_at IS NULL AND "
        "json_extract(payload, '$.accession') = ? AND json_extract(payload, '$.filename') = ? "
        "AND json_extract(payload, '$.offsets[0]') < ? "
        "AND json_extract(payload, '$.offsets[1]') > ?",
        (accession, filename, b, a),
    ).fetchone():
        return "in_review"
    return "code_missed"


def _check(
    engine: sqlite3.Connection,
    turns: list[Turn],
    accession: str,
    filename: str,
    sha: str,
    text: str,
):
    by_label = {t.label: t for t in turns}

    def check(reply: Any) -> list[Observation]:
        out = []
        for s in reply["statements"]:
            claim = f"{s['metric']} {s['period']}: {s['value']}"
            t = by_label.get(str(s["turn_id"]))
            subject: dict[str, Any] = {"turn": s["turn_id"], "metric": s["metric"],
                                       "period": s["period"], "value": s["value"]}  # fmt: skip
            if t is None:
                out.append(Observation(subject, claim, False, f"unknown turn {s['turn_id']}"))
                continue
            quote = str(s["quote"])
            span = locate(quote, text, t.start, t.end) if quote_found(quote, t.text) else None
            if span is None:
                why = f"quote not found in {t.label}: {quote[:80]!r}"
                out.append(Observation(subject, claim, False, why))
                continue
            subject |= {"offsets": list(span),
                        "status": _status(engine, accession, filename, *span)}  # fmt: skip
            cite = Citation(accession, filename, None, span[0], span[1], quote, sha)
            out.append(Observation(subject, claim, True, None, (cite,)))
        return out

    return check


def queue_missed(
    engine: sqlite3.Connection,
    prep: Prepared,
    result: RunResult,
    text: str,
    now: datetime,
) -> int:
    """`guidance_audit` items for verified statements the code neither stored nor queued."""
    queued = 0
    for ob in result.observations:
        if not ob.verified or ob.subject.get("status") != "code_missed":
            continue
        a, b = ob.subject["offsets"]
        # re-check now: the code may have changed since the call was made (cached results)
        if _status(engine, prep.accession, prep.filename, a, b) != "code_missed":
            continue
        if labelled_or_queued(engine, prep.accession, a):
            continue
        payload = {"sample": "gemini", "found_by": "gemini", "accession": prep.accession,
                   "filename": prep.filename, "offsets": [a, b], "text": text[a:b],
                   "gemini_read": ob.claim, "parser_version": PARSER_VERSION,
                   "llm_call": result.call_id}  # fmt: skip
        enqueue(
            engine,
            "guidance_audit",
            prep.cik,
            f"Gemini read guidance the code did not store: {ob.claim}",
            payload,
            now,
        )
        queued += 1
    return queued
