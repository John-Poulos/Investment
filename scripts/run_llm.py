"""Run a grounded LLM analysis on request (M00_SEARCH D-SRCH-17/18/19).

    uv run python scripts/run_llm.py guidance-reasons --ticker META --dry-run
    uv run python scripts/run_llm.py guidance-reasons --ticker META
    uv run python scripts/run_llm.py guidance-reasons --ticker META --rerun

Always prints the code-computed guidance changes first (no LLM). Then:
--dry-run  writes the exact prompt to the log and stops; nothing is sent.
default    shows the token and cost estimate and asks "proceed? [y/N]"; a stored
           result for the identical request is shown instead, at no cost.
--rerun    calls again even if an identical request is stored.
--yes      skips the question (for when you have already reviewed the estimate).

Writes logs/llm_<use case>_<ticker>_<YYYYMMDD-HHMMSS>.txt. The Gemini key comes
from GEMINI_API_KEY in .env and is never printed.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.llm import guidance_reasons  # noqa: E402
from engine.llm.provider import GeminiProvider, estimate_tokens, load_settings  # noqa: E402
from engine.llm.runs import cached_call, load_observations, run  # noqa: E402
from engine.store.db import open_db  # noqa: E402

EXPECTED_OUTPUT_TOKENS = 1500  # rough allowance for the estimate (reply + thinking)


def resolve(engine, ticker: str) -> str | None:
    row = engine.execute(
        "SELECT cik FROM ticker WHERE upper(ticker) = upper(?) AND valid_to IS NULL "
        "ORDER BY valid_from DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    return row["cik"] if row else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("use_case", choices=["guidance-reasons"])
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rerun", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    engine = open_db("engine", ROOT / "data")
    corpus = open_db("corpus", ROOT / "data")
    settings = load_settings()
    cik = resolve(engine, args.ticker)
    if cik is None:
        print(f"unknown ticker {args.ticker}")
        return 1

    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"llm_{args.use_case}_{args.ticker.upper()}_{datetime.now():%Y%m%d-%H%M%S}.txt"
    lines: list[str] = []

    def out(s: str = "") -> None:
        lines.append(s)
        print(s)

    prep = guidance_reasons.prepare(engine, corpus, cik)
    out(f"{args.use_case} {args.ticker.upper()} ({cik}) — model {settings.model}")
    out("\n== Guidance changes (computed by code, no LLM) ==")
    if not prep.changes:
        out("none: fewer than two releases state the same metric/basis/period, and no prior stated")
    for c in prep.changes:
        out("  " + guidance_reasons.describe(c))

    def finish(code: int) -> int:
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nLog written to: {log}")
        return code

    req = prep.request
    if req is None:
        out("\nNothing to ask: no raised/lowered/narrowed/widened guidance with passages.")
        return finish(0)

    est_in = estimate_tokens(req.system + req.user)
    est_cost = settings.cost(est_in, EXPECTED_OUTPUT_TOKENS)
    out(
        f"\n== Request ==\n{len(prep.asked)} changes, {len(prep.passages)} passages, "
        f"~{est_in:,} input tokens, estimated cost ${est_cost:.4f} (rough, local estimate)"
    )
    if args.dry_run:
        out("\n== Prompt (system) ==\n" + req.system)
        out("== Prompt (user) ==\n" + req.user)
        out("\nDry run: nothing sent.")
        return finish(0)

    if not args.rerun and (call_id := cached_call(engine, req, settings.model)) is not None:
        out(f"Stored result for this exact request (call {call_id}); no new call, no cost.")
        observations = load_observations(engine, call_id)
    else:
        if not args.yes:
            answer = input("Proceed with the Gemini call? [y/N] ").strip().lower()
            if answer != "y":
                out("Not sent.")
                return finish(0)
        res = run(engine, GeminiProvider(), settings, req, datetime.now(UTC), rerun=args.rerun)
        out(
            f"Call {res.call_id}: {res.input_tokens} input + {res.output_tokens} output tokens, "
            f"cost ${res.cost_usd:.4f}"
        )
        observations = res.observations

    ok = sum(o.verified for o in observations)
    out(f"\n== Observations: {ok} verified, {len(observations) - ok} rejected ==")
    out("(Interpretations by the model; every verified quote was checked against the stored text.)")
    for o in observations:
        out(f"\n[{'VERIFIED' if o.verified else 'REJECTED'}] {o.subject.get('change', '')}")
        out(f"  reason: {o.claim or '-'}")
        for c in o.citations:
            out(f'  quote ({c.accession}, offsets {c.start}-{c.end}): "{c.quote}"')
        if o.detail:
            out(f"  rejected because: {o.detail}")
    return finish(0)


if __name__ == "__main__":
    sys.exit(main())
