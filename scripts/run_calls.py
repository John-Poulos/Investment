"""Call guidance: import, fetch and scan earnings-call transcripts (M02 part 4).

    uv run python scripts/run_calls.py --import-probe          # store the probe's saved replies
    uv run python scripts/run_calls.py --fetch 6               # up to 6 Alpha Vantage requests
    uv run python scripts/run_calls.py                         # scan only (no network)
    uv run python scripts/run_calls.py --force                 # re-scan every release and call

Order: import → scan releases → fetch due transcripts (newest releases first,
watchlist + tracked names) → scan calls → download reminders. Interactive budget:
at most 25 Alpha Vantage requests in 24 hours, counted with the scheduled runs.
Writes logs/calls_<YYYYMMDD-HHMMSS>.txt: per call document the speaker roles, the
ledger rows, direction-only rows, release matches/conflicts and the capex sentences
sent to review. Does not run while the nightly refresh holds data/refresh.lock.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.calls.alpha_vantage import (  # noqa: E402
    DAILY_LIMIT,
    AlphaVantageClient,
    MissingKey,
    key_from_env,
)
from engine.calls.transcripts import (  # noqa: E402
    fetch_due,
    import_files,
    queue_reminders,
    symbol_cik,
)
from engine.guidance.calls import scan_calls  # noqa: E402
from engine.guidance.ledger import scan_all  # noqa: E402
from engine.refresh import load_config  # noqa: E402
from engine.store.db import open_db  # noqa: E402
from engine.themes import tiers  # noqa: E402


def fmt(v: object, unit: str) -> str:
    if v is None:
        return "-"
    d = Decimal(str(v))
    if unit == "USD" and abs(d) >= 10**6:
        return f"${d / 10**9:,.3f}B" if abs(d) >= 10**9 else f"${d / 10**6:,.1f}M"
    return f"{d}%" if unit == "%" else f"{d}"


def companies(engine) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in load_config(ROOT / "config" / "watchlist.toml").tickers:
        if cik := symbol_cik(engine, t):
            out[t] = cik
    for m in tiers.members(engine):
        out.setdefault(m.ticker, m.cik)
    return out


def describe_calls(engine, corpus, scans) -> list[str]:
    lines: list[str] = []
    for s in scans:
        cd = s.doc
        lines.append(
            f"\n## {cd.symbol} {cd.quarter} ({cd.source}, {cd.doc_kind}) {cd.accession}  "
            f"release {cd.stated_on or 'NOT FOUND'}  {s.outcome}: rows {s.items}, "
            f"direction {s.directions}, matched {s.matched}, conflicts {s.conflicts}, "
            f"review {s.unparsed}, skipped {s.skipped}, candidates {s.candidates}"
        )
        doc = corpus.execute("SELECT doc_id FROM document WHERE accession = ?",
                             (cd.accession,)).fetchone()  # fmt: skip
        if doc:
            roles: dict[str, Counter] = {}
            for r in corpus.execute("SELECT label, title FROM section WHERE doc_id = ?",
                                    (doc[0],)):  # fmt: skip
                title = (
                    (r["title"] or "").split(" — ", 1)[-1] if " — " in (r["title"] or "") else ""
                )
                roles.setdefault(r["label"], Counter())[title or "(no title)"] += 1
            for label, titles in sorted(roles.items()):
                top = ", ".join(f"{t} ×{n}" for t, n in titles.most_common(6))
                lines.append(f"  {label}: {sum(titles.values())} turns — {top}")
        for g in engine.execute(
            "SELECT * FROM guidance WHERE accession = ? ORDER BY period, metric, basis",
            (cd.accession,),
        ):
            if g["kind"] == "direction":
                value = f"direction {g['direction']}"
            elif g["low"] == g["high"]:
                value = fmt(g["low"], g["unit"])
            else:
                value = f"{fmt(g['low'], g['unit'])} – {fmt(g['high'], g['unit'])}"
            value = {"floor": "more than ", "ceiling": "up to "}.get(g["bound"], "") + value
            extra = f"  matched {g['matched_accession']}" if g["matched_accession"] else ""
            extra += f"  clause: {g['clause']}" if g["clause"] else ""
            lines.append(f"  {g['period']:<14}{g['metric']:<20}{g['basis']:<12}{g['grade']} "
                         f"{value}{extra}  \"{' '.join(g['quote'].split())[:160]}\"")  # fmt: skip
        for q in engine.execute(
            "SELECT kind, reason, payload FROM review_queue WHERE resolved_at IS NULL "
            "AND kind IN ('guidance_unparsed', 'guidance_conflict') "
            "AND json_extract(payload, '$.accession') = ?",
            (cd.accession,),
        ):
            p = json.loads(q["payload"])
            body = p.get("text") or f"release: {p.get('kept')} | call: {p.get('other')}"
            lines.append(f"  REVIEW {q['reason']}")
            lines.append(f"    {' '.join(body.split())[:300]}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--import-probe", nargs="?", const=str(ROOT / "data/probe/alpha_vantage"),
                    help="import saved replies (default data/probe/alpha_vantage)")  # fmt: skip
    ap.add_argument("--fetch", type=int, default=0, help="Alpha Vantage requests (max)")
    ap.add_argument("--force", action="store_true", help="re-scan every release and call")
    args = ap.parse_args()
    if (ROOT / "data" / "refresh.lock").exists():
        print("data/refresh.lock exists: the refresh is running; try again later.")
        return 1
    engine = open_db("engine", ROOT / "data")
    corpus = open_db("corpus", ROOT / "data")
    now = datetime.now(UTC)
    lines = [f"run_calls {now:%Y-%m-%d %H:%M} UTC"]
    if args.import_probe:
        lines += import_files(engine, corpus, Path(args.import_probe).glob("*.json"), now)
    releases = scan_all(engine, corpus, now, force=args.force)
    lines.append(f"releases scanned: {len(releases)} {dict(Counter(r.outcome for r in releases))}")
    if args.fetch:
        try:
            client = AlphaVantageClient(key_from_env(), engine, daily_budget=DAILY_LIMIT)
            rep = fetch_due(engine, corpus, client, companies(engine), now, limit=args.fetch)
            lines += rep.lines()
        except MissingKey as e:
            lines.append(f"fetch skipped: {e}")
    else:
        lines += [f"download reminder queued: {r}" for r in queue_reminders(engine, now)]
    scans = scan_calls(engine, corpus, now, force=args.force,
                       ciks={r.release.cik for r in releases})  # fmt: skip
    lines.append(f"calls scanned: {len(scans)} {dict(Counter(s.outcome for s in scans))}")
    lines += describe_calls(engine, corpus, scans)
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"calls_{datetime.now():%Y%m%d-%H%M%S}.txt"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(ln for ln in lines if not ln.startswith(("  ", "\n##"))))
    print(f"Log written to: {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
