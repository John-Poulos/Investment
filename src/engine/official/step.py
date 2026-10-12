"""The official-feeds step of a refresh run (M02 part 7b, D-M02-13, D-M02-58, D-M02-60).

Order: Federal Register, Congress.gov, USAspending, arXiv — each with its own slice of the
time budget, so a slow source cannot starve the others (the logon run shares a 3-h task
limit, D-M02-12). Shown on pages only: no review items (part-7b question 1). Never fails
the run: errors are reported in its lines; every write is a short transaction.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from engine.news.fetch import Fetcher
from engine.official import arxiv, congress, fedreg, usaspending
from engine.official.common import Budget, active_phrases, distinct_phrases

# seconds per source a run (≈ 3 minutes in all; steady-state runs take far less); arXiv is
# also capped by requests (3 s each)
BUDGETS = {"fedreg": 40.0, "congress": 50.0, "usaspending": 50.0, "arxiv": 48.0}
ARXIV_REQUESTS = 15


@dataclass
class OfficialReport:
    lines: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def run_official_step(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    fetcher: Fetcher | None = None,
    congress_key: str | None = None,
    budgets: dict[str, float] | None = None,
    arxiv_requests: int = ARXIV_REQUESTS,
    clock: Callable[[], float] = time.monotonic,
    sources: tuple[str, ...] = ("fedreg", "congress", "usaspending", "arxiv"),
) -> OfficialReport:
    """companies: ticker → cik for core, promoted and tracked names."""
    rep = OfficialReport(lines=["Official feeds (M02 part 7b):"])
    try:
        _run(engine, companies, now, rep, fetcher, congress_key, budgets or BUDGETS,
             arxiv_requests, clock, sources)  # fmt: skip
    except Exception as e:  # the step must not break the run report
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        rep.lines.append(f"error — {type(e).__name__}: {e}")
    for f in rep.failures[:30]:
        rep.lines.append(f"  failed: {f}")
    if len(rep.failures) > 30:
        rep.lines.append(f"  … {len(rep.failures) - 30} more failure(s)")
    return rep


def _stop(text: str) -> str:
    return f" — stopped: {text}" if text else ""


def _run(engine, companies, now, rep, fetcher, congress_key, budgets, arxiv_requests, clock,
         sources) -> None:  # fmt: skip
    fetcher = fetcher or Fetcher(engine, secrets=(congress_key,) if congress_key else ())
    phrases = active_phrases(engine)
    n_phr = len(distinct_phrases(phrases))
    rep.lines.append(f"active theme phrases: {n_phr}")

    def budget(name: str) -> Budget:
        return Budget(budgets.get(name, 60.0), clock)

    if "fedreg" in sources:
        r = fedreg.run(engine, fetcher, phrases, now, budget("fedreg"))
        rep.failures += [f"Federal Register {f}" for f in r.failures]
        rep.lines.append(
            f"Federal Register: {r.phrases} phrase(s) searched, {r.seen} document(s) seen, "
            f"{r.new} new" + (f"; newest 200 only for: {', '.join(r.capped)}" if r.capped else "")
            + (f"; {r.filled} older match(es) marked title/abstract or body" if r.filled else "")
            + _stop(r.stopped)
        )  # fmt: skip
    if "congress" in sources:
        r = congress.run(engine, fetcher, congress_key, phrases, now, budget("congress"))
        rep.failures += [f"Congress.gov {f}" for f in r.failures]
        if not congress_key:
            rep.lines.append(f"Congress.gov: {r.stopped}")
        else:
            rep.lines.append(
                f"Congress.gov: {r.listed} bill/summary record(s) read, {r.matched} phrase "
                f"match(es), {r.new} new bill(s), {r.enacted_new} newly enacted"
                + _stop(r.stopped)
            )  # fmt: skip
    if "usaspending" in sources:
        r = usaspending.run(engine, fetcher, companies, now, budget("usaspending"))
        rep.failures += [f"USAspending {f}" for f in r.failures]
        rep.lines.append(
            f"USAspending: {r.companies} compan(ies) searched, {r.seen} award(s) seen, {r.new} "
            f"new; recipient profiles read {r.profiles}, mapped by parent {r.by_parent}"
            + _stop(r.stopped)
        )  # fmt: skip
        if r.retermed:
            rep.lines.append(
                f"  search names changed: {r.retermed} unmapped award(s) from the old search "
                "terms dropped; those companies searched again now"
            )
        if r.no_list:
            rep.lines.append(
                "  no exact recipient list (searched by name parts; add `usaspending = [...]` "
                "to config/aliases.toml): " + ", ".join(r.no_list)
            )
    if "arxiv" in sources:
        r = arxiv.run(engine, fetcher, phrases, now, budget("arxiv"), max_requests=arxiv_requests)
        rep.failures += [f"arXiv {f}" for f in r.failures]
        rep.lines.append(
            f"arXiv: {r.counted} monthly count(s) stored, {r.due} (phrase, month) pair(s) "
            f"still to count" + _stop(r.stopped)
        )
