"""The calls step of a refresh run (M02 part 4): local scans, then transcripts.

1. Scan stored earnings releases not yet scanned by this parser (no network).
2. Request due transcripts from Alpha Vantage within the run budget (20/day).
3. Scan new call documents, and every call of a company whose releases were just
   re-scanned (release vs call matching depends on both).
4. Queue download reminders for calls still missing 30 days after the release.
5. Accuracy checks (D-M02-24): plausibility flags, this week's random sample.
Never fails the run: errors are reported in its lines.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime

from engine.calls.alpha_vantage import AlphaVantageClient
from engine.calls.transcripts import fetch_due, queue_reminders
from engine.guidance import labels
from engine.guidance.calls import scan_calls
from engine.guidance.ledger import scan_all


def run_calls_step(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    client: AlphaVantageClient | None,
    companies: dict[str, str],
    now: datetime,
    *,
    no_client_reason: str = "no client",
    limit: int | None = None,
) -> list[str]:
    lines = ["Calls and guidance (M02 part 4):"]
    try:
        releases = scan_all(engine, corpus, now)
        out = Counter(r.outcome for r in releases)
        lines.append(f"releases scanned: {len(releases)} {dict(out) if releases else ''}".rstrip())
        if client is None:
            lines.append(f"transcripts: skipped — {no_client_reason}")
            lines += [f"  download reminder queued: {r}" for r in queue_reminders(engine, now)]
        else:
            lines += fetch_due(engine, corpus, client, companies, now, limit=limit).lines()
        calls = scan_calls(engine, corpus, now, ciks={r.release.cik for r in releases})
        if calls:
            c = Counter(s.outcome for s in calls)
            lines.append(
                f"calls scanned: {len(calls)} {dict(c)}; rows {sum(s.items for s in calls)}, "
                f"direction-only {sum(s.directions for s in calls)}, matched to a release "
                f"{sum(s.matched for s in calls)}, conflicts {sum(s.conflicts for s in calls)}, "
                f"capex sentences to review {sum(s.unparsed for s in calls)}, "
                f"other sentences skipped {sum(s.skipped for s in calls)}"
            )
        stale = labels.close_stale(engine, now)
        implausible = labels.check_plausibility(engine, now)
        audit = labels.queue_audit(engine, corpus, now)
        lines.append(
            f"accuracy checks: {stale} stale check(s) closed, {implausible} implausible "
            f"row(s) queued, {audit} weekly sample item(s) queued"
        )
        for a in labels.accuracy(engine)[:2]:
            lines.append("  " + labels.accuracy_line(a))
    except Exception as e:  # the calls step must not break the SEC run report
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        if corpus.in_transaction:
            corpus.execute("ROLLBACK")
        lines.append(f"error — {type(e).__name__}: {e}")
    return lines
