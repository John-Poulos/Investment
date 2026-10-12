"""Gemini use case 4: name a mined phrase and suggest variants (D-M02-8; owner-triggered).

Code found the phrase and its sample passages; Gemini only names the theme and lists
other wordings the passages themselves use. Each variant must appear in its cited
passage and its sentence must be copied verbatim, or it is rejected (stored with the
reason, never used). Verified variants join the season as candidates (source 'llm') and
pass the same screen and tests as mined phrases (D-M02-8: weakest exactly on new themes,
S82). The name is a suggestion shown on the proposal; the owner decides.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.llm.runs import Citation, Observation, Request, RunResult
from engine.llm.verify import normalize, quote_found

PROMPTS = Path(__file__).parent / "prompts"
USE_CASE = "theme_names"
VERSION = "theme_names-1"
SYSTEM = (PROMPTS / "theme_names_1.md").read_text(encoding="utf-8")
MAX_VARIANTS = 5
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "phrase": {"type": "string"},
                    "passage": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["phrase", "passage", "quote"],
            },
        },
    },
    "required": ["name", "variants"],
}


def _passages(corpus: sqlite3.Connection, ids: list[int]) -> dict[str, dict[str, Any]]:
    out = {}
    for pid in ids:
        r = corpus.execute(
            "SELECT p.start_offset, p.end_offset, d.accession, d.filename, d.sha256, "
            "substr(d.text, p.start_offset + 1, p.end_offset - p.start_offset) AS body "
            "FROM passage p JOIN document d ON d.doc_id = p.doc_id WHERE p.passage_id = ?",
            (pid,),
        ).fetchone()
        if r is not None:
            out[f"S{pid}"] = dict(r)
    return out


def request(engine: sqlite3.Connection, corpus: sqlite3.Connection, season: str,
            phrase: str) -> Request | None:  # fmt: skip
    row = engine.execute("SELECT samples FROM seasonal_phrase WHERE season = ? AND phrase = ?",
                         (season, phrase)).fetchone()  # fmt: skip
    ids = [int(s["passage_id"]) for s in json.loads(row["samples"] or "[]")] if row else []
    passages = _passages(corpus, ids)
    if not passages:
        return None
    user = f'Phrase: "{phrase}"\n\n' + "\n\n".join(
        f"[{k}]\n{v['body'].strip()}" for k, v in passages.items()
    )
    return Request(USE_CASE, None, VERSION, SYSTEM, user, SCHEMA, _check(phrase, passages))


def _check(phrase: str, passages: dict[str, dict[str, Any]]):
    def check(reply: Any) -> list[Observation]:
        name = " ".join(str(reply.get("name", "")).split())[:80]
        out = [Observation({"kind": "name", "phrase": phrase, "name": name}, name, bool(name),
                           None if name else "empty name")]  # fmt: skip
        seen = {phrase.lower()}
        for v in list(reply.get("variants") or [])[: MAX_VARIANTS * 2]:
            var = " ".join(str(v.get("phrase", "")).split())
            subject = {"kind": "variant", "phrase": phrase, "variant": var.lower()}
            p = passages.get(str(v.get("passage", "")).strip("[] "))
            quote = str(v.get("quote", ""))
            words = len(var.split())
            if var.lower() in seen or not 2 <= words <= 4:
                out.append(Observation(subject, var, False, "repeat, or not 2–4 words"))
                continue
            if p is None:
                out.append(Observation(subject, var, False, f"unknown passage {v.get('passage')}"))
                continue
            if not quote_found(quote, p["body"]):
                out.append(
                    Observation(subject, var, False, f"quote not in passage: {quote[:80]!r}")
                )
                continue
            if not re.search(re.escape(normalize(var).lower()), normalize(quote).lower()):
                out.append(Observation(subject, var, False, "variant not in its quote"))
                continue
            seen.add(var.lower())
            at = p["body"].find(quote.strip())
            start = p["start_offset"] + max(at, 0)
            cite = Citation(p["accession"], p["filename"], None, start,
                            start + (len(quote.strip()) if at >= 0 else len(p["body"])),
                            quote, p["sha256"])  # fmt: skip
            out.append(Observation(subject, var, True, None, (cite,)))
        return out

    return check


def apply(engine: sqlite3.Connection, season: str, phrase: str, result: RunResult,
          now: datetime) -> dict[str, Any]:  # fmt: skip
    """Store the suggestion on the phrase; verified variants join the season."""
    from engine.themes.seasonal import add_phrases, season_for_key

    name = next((o.claim for o in result.observations
                 if o.subject.get("kind") == "name" and o.verified), None)  # fmt: skip
    variants = [o.subject["variant"] for o in result.observations
                if o.subject.get("kind") == "variant" and o.verified]  # fmt: skip
    rejected = [f"{o.claim}: {o.detail}" for o in result.observations
                if o.subject.get("kind") == "variant" and not o.verified]  # fmt: skip
    info = {"name": name, "variants": variants, "rejected": rejected, "call_id": result.call_id}
    engine.execute("UPDATE seasonal_phrase SET gemini = ? WHERE season = ? AND phrase = ?",
                   (json.dumps(info), season, phrase))  # fmt: skip
    added = add_phrases(engine, season_for_key(season), variants, "llm", now)
    if added:  # the pass has new candidates to screen: the reminder returns until resumed
        engine.execute("UPDATE seasonal_run SET status = 'testing', finished_at = NULL "
                       "WHERE season = ? AND status = 'done'", (season,))  # fmt: skip
    for r in engine.execute("SELECT prop_key, payload, item_id FROM m02_proposal WHERE kind IN "
                            "('m02_theme', 'm02_phrase')").fetchall():  # fmt: skip
        p = json.loads(r["payload"] or "{}")
        if p.get("phrase") != phrase or p.get("season") != season:
            continue
        p["gemini"] = {"name": name, "variants": variants}
        engine.execute("UPDATE m02_proposal SET payload = ? WHERE prop_key = ?",
                       (json.dumps(p), r["prop_key"]))  # fmt: skip
        if r["item_id"]:
            engine.execute("UPDATE review_queue SET payload = ? WHERE item_id = ? AND "
                           "resolved_at IS NULL", (json.dumps(p), r["item_id"]))  # fmt: skip
    return info | {"added": added}
