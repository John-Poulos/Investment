"""Gemini use cases 5 and 5b for supplier discovery (D-M02-9, D-SRCH-21; owner-triggered).

5 — label link passages: Gemini reads code-selected passages (each names company A, the
filer, and B) and says type (supply / partner / competitor / none / unclear) and, for
supply, who supplies whom, with an exact supporting quote. Unverified quotes → rejected
(never stored as a label). Labels help the owner's review; they never confirm a link.
The same request on the precision set measures Gemini against the owner's blind labels.

5b — input categories: Gemini reads one company's latest 10-K Item 1 and 1A and lists
the inputs the company depends on, each with an exact quote → `input_category` rows and
`m02_input` review items (rung L0, grade C until a named link exists).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.llm.runs import Citation, Observation, Request, RunResult
from engine.llm.verify import quote_found
from engine.sec.client import iso

PROMPTS = Path(__file__).parent / "prompts"
LABELS = "supply_link_labels"
LABELS_VERSION = "supply_labels-1"
LABELS_SYSTEM = (PROMPTS / "supply_labels_1.md").read_text(encoding="utf-8")
INPUTS = "input_categories"
INPUTS_VERSION = "input_categories-1"
INPUTS_SYSTEM = (PROMPTS / "input_categories_1.md").read_text(encoding="utf-8")
BATCH = 40
TYPES = ("supply", "partner", "competitor", "none", "unclear")
DIRECTIONS = ("a_to_b", "b_to_a", "unclear")

LABELS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string", "enum": list(TYPES)},
                    "direction": {"type": "string", "enum": list(DIRECTIONS)},
                    "quote": {"type": "string"},
                },
                "required": ["id", "type", "direction", "quote"],
            },
        }
    },
    "required": ["answers"],
}
INPUTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"category": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["category", "quote"],
            },
        }
    },
    "required": ["categories"],
}


# --- 5: link labels ------------------------------------------------------------------------


def _passages(engine: sqlite3.Connection, link_ids: list[int]) -> list[sqlite3.Row]:
    marks = ",".join("?" * len(link_ids))
    return engine.execute(
        f"SELECT * FROM supply_link WHERE link_id IN ({marks}) ORDER BY link_id", link_ids
    ).fetchall()


def label_requests(engine: sqlite3.Connection, link_ids: list[int]) -> list[Request]:
    """One request per batch of passages. The user text holds no hint of the code's reading
    (rung, direction) so that the precision set measures Gemini on the passage alone."""
    rows = _passages(engine, link_ids)
    out = []
    for i in range(0, len(rows), BATCH):
        batch = rows[i : i + BATCH]
        lines = []
        for r in batch:
            lines += [
                f"[P{r['link_id']}] A = {r['a_name']} (filed the document); B = {r['b_name']}",
                r["quote"],
                "",
            ]
        out.append(
            Request(
                LABELS,
                None,
                LABELS_VERSION,
                LABELS_SYSTEM,
                "\n".join(lines),
                LABELS_SCHEMA,
                _label_check(batch),
            )
        )
    return out


def _label_check(batch: list[sqlite3.Row]):
    by_id = {f"P{r['link_id']}": r for r in batch}

    def check(reply: Any) -> list[Observation]:
        out = []
        for a in reply["answers"]:
            r = by_id.get(str(a["id"]))
            subject = {
                "link_id": int(str(a["id"]).lstrip("P")) if r is not None else None,
                "type": a["type"],
                "direction": a["direction"],
            }
            claim = f"{a['id']}: {a['type']} {a['direction']}"
            if r is None:
                out.append(Observation(subject, claim, False, f"unknown passage {a['id']}"))
                continue
            if a["type"] not in TYPES or a["direction"] not in DIRECTIONS:
                out.append(Observation(subject, claim, False, "label outside the allowed set"))
                continue
            if not quote_found(str(a["quote"]), r["quote"]):
                out.append(
                    Observation(
                        subject, claim, False, f"quote not in the passage: {str(a['quote'])[:80]!r}"
                    )
                )
                continue
            q = str(a["quote"]).strip()
            at = r["quote"].find(q)  # exact offsets when the quote is verbatim, else the passage
            start, end = (
                (r["quote_start"] + at, r["quote_start"] + at + len(q))
                if at >= 0
                else (r["quote_start"], r["quote_end"])
            )
            cite = Citation(r["accession"], r["filename"], None, start, end, q, "")
            out.append(Observation(subject, claim, True, None, (cite,)))
        return out

    return check


def apply_labels(engine: sqlite3.Connection, result: RunResult) -> int:
    n = 0
    for ob in result.observations:
        if not ob.verified or ob.subject.get("link_id") is None:
            continue
        direction = ob.subject["direction"] if ob.subject["type"] == "supply" else "unclear"
        n += engine.execute(
            "UPDATE supply_link SET llm_type = ?, llm_direction = ?, llm_call_id = ? "
            "WHERE link_id = ?",
            (ob.subject["type"], direction, result.call_id, ob.subject["link_id"]),
        ).rowcount
    return n


# --- 5b: input categories ----------------------------------------------------------------


def input_request(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, cik: str
) -> tuple[Request, dict[str, Any]] | None:
    """Item 1 and 1A of the latest stored 10-K → request, and the document it read."""
    doc = corpus.execute(
        "SELECT doc_id, accession, filename, text, sha256 FROM document WHERE cik = ? "
        "AND doc_type = '10-K' ORDER BY fetched_at DESC LIMIT 1",
        (cik,),
    ).fetchone()
    if doc is None:
        return None
    secs = corpus.execute(
        "SELECT label, start_offset, end_offset FROM section WHERE doc_id = ? "
        "AND (label LIKE '%Item 1' OR label LIKE '%Item 1A') ORDER BY start_offset",
        (doc["doc_id"],),
    ).fetchall()
    spans = [(s["start_offset"], s["end_offset"]) for s in secs] or [(0, len(doc["text"]))]
    name = engine.execute("SELECT name FROM entity WHERE cik = ?", (cik,)).fetchone()
    parts = [doc["text"][a:b] for a, b in spans]
    user = f"Company: {name[0] if name else cik}\n\n" + "\n\n".join(parts)
    meta = {
        "accession": doc["accession"],
        "filename": doc["filename"],
        "sha": doc["sha256"],
        "text": doc["text"],
        "spans": spans,
    }
    req = Request(
        INPUTS, cik, INPUTS_VERSION, INPUTS_SYSTEM, user, INPUTS_SCHEMA, _input_check(meta)
    )
    return req, meta


def _input_check(meta: dict[str, Any]):
    def check(reply: Any) -> list[Observation]:
        out, seen = [], set()
        text = meta["text"]
        for c in reply["categories"]:
            cat = " ".join(str(c["category"]).split())[:80]
            subject = {"category": cat}
            if not cat or cat.lower() in seen:
                continue
            seen.add(cat.lower())
            quote = str(c["quote"])
            hit = None
            for a, b in meta["spans"]:
                if quote_found(quote, text[a:b]):
                    at = text.find(quote.strip(), a, b)
                    hit = (at, at + len(quote.strip())) if at >= 0 else (a, b)
                    break
            if hit is None:
                out.append(Observation(subject, cat, False, f"quote not found: {quote[:80]!r}"))
                continue
            cite = Citation(
                meta["accession"], meta["filename"], None, hit[0], hit[1], quote, meta["sha"]
            )
            out.append(Observation(subject, cat, True, None, (cite,)))
        return out

    return check


def apply_inputs(
    engine: sqlite3.Connection, cik: str, ticker: str, result: RunResult, now: datetime
) -> int:
    from engine.themes.proposals import propose

    n = 0
    for ob in result.observations:
        if not ob.verified:
            continue
        c = ob.citations[0]
        cur = engine.execute(
            "INSERT OR IGNORE INTO input_category (cik, category, quote, accession, filename, "
            "quote_start, quote_end, llm_call_id, discovered_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cik,
                ob.claim,
                c.quote,
                c.accession,
                c.filename,
                c.start,
                c.end,
                result.call_id,
                iso(now),
            ),
        )
        if not cur.rowcount:
            continue
        n += 1
        payload = {
            "ticker": ticker,
            "category": ob.claim,
            "samples": [c.quote],
            "accession": c.accession,
            "filename": c.filename,
            "offsets": [c.start, c.end],
            "why": f"{ticker} says it depends on {ob.claim} (Gemini, quote verified; "
            "rung L0, grade C)",
            "companies": 1,
        }
        propose(
            engine,
            "m02_input",
            f"{cik}:{ob.claim.lower()}",
            f"{ticker}: depends on {ob.claim}?",
            payload,
            now,
            cik=cik,
        )
    return n


def decide_input(engine: sqlite3.Connection, cik: str, payload: dict, action: str) -> None:
    status = {"confirm": "confirmed", "reject": "rejected"}[action]
    engine.execute(
        "UPDATE input_category SET status = ? WHERE cik = ? AND category = ?",
        (status, cik, payload.get("category")),
    )
