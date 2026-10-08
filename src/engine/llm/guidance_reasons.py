"""Use case 1: stated reasons for guidance changes (R19, M00_SEARCH D-SRCH-17).

Code computes the changes (guidance/changes.py, reaffirmations skipped) and
selects the passages of each announcing release around the guidance sentence
(its passage and the next one in the same section). The model may only quote
those passages, and only from the release that announced the change.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from engine.guidance.changes import Change, changes_for
from engine.llm.runs import Citation, Observation, Request
from engine.llm.verify import quote_found, unsupported_numbers

# the "next passage" is often only legal boilerplate; it is not sent (saves tokens)
_BOILERPLATE = re.compile(r"\s*(?:\S+\s+){0,12}?(?:contains )?forward-looking statements", re.I)

USE_CASE = "guidance_reasons"
PROMPT_VERSION = "guidance_reasons-1"
SYSTEM = (Path(__file__).parent / "prompts" / "guidance_reasons_1.md").read_text(encoding="utf-8")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reasons": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "change_id": {"type": "string"},
                    "reason_stated": {"type": "boolean"},
                    "summary": {"type": "string"},
                    "quotes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "passage_id": {"type": "string"},
                                "quote": {"type": "string"},
                            },
                            "required": ["passage_id", "quote"],
                        },
                    },
                },
                "required": ["change_id", "reason_stated", "summary", "quotes"],
            },
        }
    },
    "required": ["reasons"],
}


@dataclass(frozen=True)
class SourcePassage:
    label: str  # P1, P2, ...
    passage_id: int
    accession: str
    filename: str
    section: str
    start: int
    end: int
    text: str
    doc_sha256: str
    filed: str


def fmt_value(v: Decimal, unit: str) -> str:
    if unit == "USD":
        a = abs(v)
        sign = "-" if v < 0 else ""
        if a >= 10**9:
            return f"{sign}${(a / 10**9).normalize():f} billion"
        if a >= 10**6:
            return f"{sign}${(a / 10**6).normalize():f} million"
        return f"{sign}${a.normalize():f}"
    if unit == "%":
        return f"{v.normalize():f}%"
    return f"{(v / 10**6).normalize():f} million"


def fmt_range(lo: Decimal, hi: Decimal, unit: str) -> str:
    return fmt_value(lo, unit) if lo == hi else f"{fmt_value(lo, unit)} – {fmt_value(hi, unit)}"


def describe(c: Change) -> str:
    prev = fmt_range(c.prev_low, c.prev_high, c.unit)
    new = fmt_range(c.new_low, c.new_high, c.unit)
    how = "earlier release" if c.source == "releases" else "prior stated in the same sentence"
    basis = "" if c.basis == "unspecified" else f" ({c.basis})"  # shown only when stated
    return (
        f"{c.metric}{basis} for {c.period}: {c.kind} from {prev} ({how}) to {new}, "
        f"announced in release {c.accession} filed {c.stated_on}."
    )


def change_line(cid: str, c: Change) -> str:
    return f"{cid}: {describe(c)}"


def _facts(c: Change) -> list[Decimal]:
    facts = [c.prev_low, c.prev_high, c.new_low, c.new_high]
    for part in c.period.split():
        if part.startswith("FY"):
            facts.append(Decimal(part[2:]))
        elif part.startswith("Q"):
            facts.append(Decimal(part[1:]))
    return facts


def _passages(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, changes: list[Change]
) -> list[SourcePassage]:
    out: dict[int, SourcePassage] = {}
    for c in changes:
        g = engine.execute(
            "SELECT quote_start FROM guidance WHERE guidance_id = ?", (c.guidance_id,)
        ).fetchone()
        doc = corpus.execute(
            "SELECT doc_id, sha256 FROM document WHERE accession = ? AND filename = ?",
            (c.accession, c.filename),
        ).fetchone()
        if g is None or doc is None:
            continue
        hit = corpus.execute(
            "SELECT section_id, seq FROM passage WHERE doc_id = ? AND start_offset <= ? "
            "AND end_offset > ?",
            (doc["doc_id"], g["quote_start"], g["quote_start"]),
        ).fetchone()
        if hit is None:
            continue
        for p in corpus.execute(
            "SELECT p.passage_id, p.start_offset, p.end_offset, s.label, "
            "substr(d.text, p.start_offset + 1, p.end_offset - p.start_offset) AS body "
            "FROM passage p JOIN section s ON s.section_id = p.section_id "
            "JOIN document d ON d.doc_id = p.doc_id "
            "WHERE p.section_id = ? AND p.seq IN (?, ?) ORDER BY p.seq",
            (hit["section_id"], hit["seq"], hit["seq"] + 1),
        ):
            if p["passage_id"] not in out and not _BOILERPLATE.match(p["body"]):
                out[p["passage_id"]] = SourcePassage(
                    "",
                    p["passage_id"],
                    c.accession,
                    c.filename,
                    p["label"],
                    p["start_offset"],
                    p["end_offset"],
                    p["body"],
                    doc["sha256"],
                    c.stated_on,
                )
    ordered = sorted(out.values(), key=lambda s: (s.filed, s.accession, s.start))
    return [replace(s, label=f"P{i}") for i, s in enumerate(ordered, 1)]


def _check(changes: dict[str, Change], passages: dict[str, SourcePassage]):
    def check(reply: Any) -> list[Observation]:
        out: list[Observation] = []
        answered: set[str] = set()
        for r in reply["reasons"]:
            cid = str(r["change_id"])
            c = changes.get(cid)
            subject: dict[str, Any] = {"change_id": cid}
            if c is not None:
                subject = {
                    "change_id": cid,
                    "change": change_line(cid, c),
                    "guidance_id": c.guidance_id,
                    "prev_guidance_id": c.prev_guidance_id,
                }
            claim = str(r["summary"]).strip()
            problems: list[str] = []
            cites: list[Citation] = []
            if c is None:
                problems.append(f"unknown change id {cid}")
            elif cid in answered:
                problems.append(f"{cid} answered twice")
            answered.add(cid)
            quotes = r.get("quotes") or []
            if r["reason_stated"] and not quotes:
                problems.append("reason stated without a quote")
            for q in quotes:
                p = passages.get(str(q["passage_id"]))
                text = str(q["quote"])
                if p is None:
                    problems.append(f"unknown passage {q['passage_id']}")
                    continue
                if c is not None and p.accession != c.accession:
                    problems.append(f"{p.label} is not from the announcing release")
                if not quote_found(text, p.text):
                    problems.append(f"quote not found in {p.label}: {text[:80]!r}")
                cites.append(
                    Citation(
                        p.accession, p.filename, p.passage_id, p.start, p.end, text, p.doc_sha256
                    )  # fmt: skip
                )
            if c is not None:
                bad = unsupported_numbers(claim, [str(q["quote"]) for q in quotes], _facts(c))
                if bad:
                    problems.append(
                        "numbers not in quotes or change: " + ", ".join(sorted(map(str, bad)))
                    )
            out.append(
                Observation(subject, claim, not problems, "; ".join(problems) or None, tuple(cites))
            )
        for cid in changes:
            if cid not in answered:
                out.append(
                    Observation(
                        {"change_id": cid, "change": change_line(cid, changes[cid])},
                        "",
                        False,
                        "no answer for this change",
                    )  # fmt: skip
                )
        return out

    return check


@dataclass(frozen=True)
class Prepared:
    request: Request | None
    changes: list[Change]  # all computed changes, reaffirmations included
    asked: dict[str, Change]
    passages: list[SourcePassage]


def prepare(engine: sqlite3.Connection, corpus: sqlite3.Connection, cik: str) -> Prepared:
    all_changes = changes_for(engine, cik)
    moved = [c for c in all_changes if c.kind != "reaffirmed"]
    asked = {f"C{i}": c for i, c in enumerate(moved, 1)}
    passages = _passages(engine, corpus, moved)
    if not asked or not passages:
        return Prepared(None, all_changes, asked, passages)
    name = engine.execute("SELECT name FROM entity WHERE cik = ?", (cik,)).fetchone()
    lines = [f"Company: {name['name'] if name else cik}", "", "Changes:"]
    lines += [change_line(cid, c) for cid, c in asked.items()]
    lines += ["", "Passages:"]
    for p in passages:
        lines += [
            f"[{p.label}] release {p.accession} filed {p.filed}, section {p.section}",
            p.text.strip(),
            "",
        ]
    by_label = {p.label: p for p in passages}
    req = Request(
        USE_CASE, cik, PROMPT_VERSION, SYSTEM, "\n".join(lines), SCHEMA, _check(asked, by_label)
    )
    return Prepared(req, all_changes, asked, passages)
