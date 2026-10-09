"""Call guidance: import, fetch and scan earnings-call transcripts (M02 part 4).

    uv run python scripts/run_calls.py --import-probe          # store the probe's saved replies
    uv run python scripts/run_calls.py --fetch 6               # up to 6 Alpha Vantage requests
    uv run python scripts/run_calls.py                         # scan only (no network)
    uv run python scripts/run_calls.py --force                 # re-scan every release and call
    uv run python scripts/run_calls.py --check-labels          # re-check accuracy labels
    uv run python scripts/run_calls.py --gemini-check 100      # cost estimate; --yes to run

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
from engine.guidance import labels  # noqa: E402
from engine.guidance.calls import scan_calls  # noqa: E402
from engine.guidance.ledger import scan_all  # noqa: E402
from engine.guidance.sources import stated_prefix  # noqa: E402
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
            value = stated_prefix(g["kind"], g["bound"]) + value
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


def gemini_check(engine, corpus, now, days: int, yes: bool) -> list[str]:
    """Owner-triggered per season (D-M02-24): estimate first, call only with --yes."""
    from datetime import timedelta

    from engine.llm import call_check
    from engine.llm.provider import GeminiProvider, estimate_tokens, load_settings
    from engine.llm.runs import cached_call
    from engine.llm.runs import run as llm_run

    llm = load_settings()
    since = (now.date() - timedelta(days=days)).isoformat()
    docs = engine.execute(
        "SELECT accession, filename FROM call_document WHERE stated_on >= ? ORDER BY stated_on",
        (since,),
    ).fetchall()
    todo, total = [], 0.0
    for d in docs:
        prep = call_check.prepare(engine, corpus, d[0], d[1])
        if prep is None or prep.request is None or cached_call(engine, prep.request, llm.model):
            continue
        cost = float(llm.cost(estimate_tokens(prep.request.system + prep.request.user), 1500))
        todo.append((prep, cost))
        total += cost
    out = [f"gemini check: {len(todo)} call(s) since {since} not yet checked, estimated "
           f"${total:.4f} ({llm.model})"]  # fmt: skip
    if not yes:
        return out + ["  estimate only; add --yes to run"]
    provider = GeminiProvider()
    for prep, _ in todo:
        try:
            res = llm_run(engine, provider, llm, prep.request, now)
        except Exception as e:  # one call failing must not stop the others
            out.append(f"  {prep.accession}: error {type(e).__name__}: {e}")
            continue
        text = corpus.execute("SELECT text FROM document WHERE accession = ? AND filename = ?",
                              (prep.accession, prep.filename)).fetchone()[0]  # fmt: skip
        q = call_check.queue_missed(engine, prep, res, text, now)
        st = Counter(o.subject.get("status", "rejected") for o in res.observations)
        out.append(f"  {prep.accession}: {dict(st)}; {q} queued for review; "
                   f"${res.cost_usd or 0:.4f}")  # fmt: skip
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--import-probe", nargs="?", const=str(ROOT / "data/probe/alpha_vantage"),
                    help="import saved replies (default data/probe/alpha_vantage)")  # fmt: skip
    ap.add_argument("--fetch", type=int, default=0, help="Alpha Vantage requests (max)")
    ap.add_argument("--force", action="store_true", help="re-scan every release and call")
    ap.add_argument("--check-labels", action="store_true",
                    help="re-run the parser over every accuracy label (no network)")  # fmt: skip
    ap.add_argument("--gemini-check", type=int, metavar="DAYS",
                    help="Gemini cross-check of calls from the last DAYS days")  # fmt: skip
    ap.add_argument("--yes", action="store_true", help="with --gemini-check: make the calls")
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
    lines.append(
        f"accuracy checks: {labels.check_plausibility(engine, now)} implausible, "
        f"{labels.queue_audit(engine, corpus, now)} weekly sample item(s) queued"
    )
    lines += ["accuracy: " + labels.accuracy_line(a) for a in labels.accuracy(engine)]
    if args.check_labels:
        lines += labels.check_labels(engine, corpus)
    if args.gemini_check:
        lines += gemini_check(engine, corpus, now, args.gemini_check, args.yes)
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
