"""Run one grounded LLM request: cache, call, check, store (M00_SEARCH D-SRCH-18/19).

The caller prepares the exact prompt and a `check` function that turns the
parsed reply into observations, each verified or rejected with a reason.
Identical requests (use case, model, prompt version, prompt text) reuse the
stored result unless `rerun` is set, so asking twice costs nothing. Every call
is logged with tokens and cost; rejected observations are stored with their
reason and open an `llm_rejected` review item, never stored as fact.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from engine.llm.provider import Provider, Settings
from engine.sec.client import iso


@dataclass(frozen=True)
class Citation:
    accession: str
    filename: str
    passage_id: int | None
    start: int
    end: int
    quote: str
    doc_sha256: str


@dataclass(frozen=True)
class Observation:
    subject: dict[str, Any]
    claim: str
    verified: bool
    detail: str | None
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True)
class Request:
    use_case: str
    cik: str | None
    prompt_version: str
    system: str
    user: str
    schema: dict[str, Any]
    check: Callable[[Any], list[Observation]]

    def input_hash(self) -> str:
        return hashlib.sha256((self.system + "\x00" + self.user).encode("utf-8")).hexdigest()


@dataclass
class RunResult:
    call_id: int
    cached: bool
    observations: list[Observation] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None


def cached_call(engine: sqlite3.Connection, req: Request, model: str) -> int | None:
    row = engine.execute(
        "SELECT call_id FROM llm_call WHERE use_case = ? AND model = ? AND prompt_version = ? "
        "AND input_hash = ? AND status = 'ok' ORDER BY call_id DESC LIMIT 1",
        (req.use_case, model, req.prompt_version, req.input_hash()),
    ).fetchone()
    return row["call_id"] if row else None


def load_observations(engine: sqlite3.Connection, call_id: int) -> list[Observation]:
    out = []
    for o in engine.execute(
        "SELECT * FROM llm_observation WHERE call_id = ? ORDER BY obs_id", (call_id,)
    ):
        cites = tuple(
            Citation(
                c["accession"],
                c["filename"],
                c["passage_id"],
                c["start_offset"],
                c["end_offset"],
                c["quote"],
                c["doc_sha256"],
            )
            for c in engine.execute(
                "SELECT * FROM llm_citation WHERE obs_id = ? ORDER BY citation_id", (o["obs_id"],)
            )
        )
        out.append(
            Observation(
                json.loads(o["subject"]), o["claim"], bool(o["verified"]), o["detail"], cites
            )
        )
    return out


def run(
    engine: sqlite3.Connection,
    provider: Provider,
    settings: Settings,
    req: Request,
    now: datetime,
    *,
    rerun: bool = False,
) -> RunResult:
    if not rerun and (call_id := cached_call(engine, req, settings.model)) is not None:
        row = engine.execute(
            "SELECT input_tokens, output_tokens FROM llm_call WHERE call_id = ?", (call_id,)
        ).fetchone()
        return RunResult(
            call_id, True, load_observations(engine, call_id), row[0], row[1], Decimal(0)
        )

    at = iso(now)
    base = (
        req.use_case,
        req.cik,
        provider.name,
        settings.model,
        req.prompt_version,
        req.input_hash(),
        req.user,
    )
    try:
        done = provider.complete(
            settings.model, req.system, req.user, req.schema, settings.temperature
        )
    except Exception as e:
        engine.execute(
            "INSERT INTO llm_call (use_case, cik, provider, model, prompt_version, input_hash, "
            "request, status, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'error', ?, ?)",
            (*base, f"{type(e).__name__}: {e}", at),
        )
        raise
    out_tokens = (done.output_tokens or 0) + (done.thought_tokens or 0)
    cost = settings.cost(done.input_tokens or 0, out_tokens)
    try:
        observations = req.check(json.loads(done.text))
        status, error = "ok", None
    except (ValueError, KeyError, TypeError) as e:  # invalid JSON or shape
        observations, status, error = [], "error", f"unreadable reply: {e}"

    engine.execute("BEGIN")
    try:
        call_id = engine.execute(
            "INSERT INTO llm_call (use_case, cik, provider, model, prompt_version, input_hash, "
            "request, response, input_tokens, output_tokens, thought_tokens, cost_usd, status, "
            "error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                *base,
                done.text,
                done.input_tokens,
                done.output_tokens,
                done.thought_tokens,
                format(cost, "f"),
                status,
                error,
                at,
            ),
        ).lastrowid
        assert call_id is not None
        for ob in observations:
            obs_id = engine.execute(
                "INSERT INTO llm_observation (call_id, cik, use_case, subject, claim, verified, "
                "detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    call_id,
                    req.cik,
                    req.use_case,
                    json.dumps(ob.subject, sort_keys=True),
                    ob.claim,
                    int(ob.verified),
                    ob.detail,
                    at,
                ),
            ).lastrowid
            for c in ob.citations:
                engine.execute(
                    "INSERT INTO llm_citation (obs_id, accession, filename, passage_id, "
                    "start_offset, end_offset, quote, doc_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        obs_id,
                        c.accession,
                        c.filename,
                        c.passage_id,
                        c.start,
                        c.end,
                        c.quote,
                        c.doc_sha256,
                    ),  # fmt: skip
                )
            if not ob.verified:
                engine.execute(
                    "INSERT INTO review_queue (module_id, kind, cik, reason, payload, created_at) "
                    "VALUES ('M00', 'llm_rejected', ?, ?, ?, ?)",
                    (
                        req.cik,
                        f"{req.use_case}: {ob.detail}",
                        json.dumps({"call_id": call_id, "subject": ob.subject, "claim": ob.claim}),
                        at,
                    ),
                )
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    if status == "error":
        raise ValueError(f"LLM reply could not be read (call {call_id}): {error}")
    return RunResult(call_id, False, observations, done.input_tokens, out_tokens, cost)
