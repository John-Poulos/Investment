"""Seasonal pass (M02 part 6, D-M02-8, -10, -14, -49…52): mine, test, propose.

    uv run python scripts/run_seasonal.py --dry-run        # due season, plan, estimate (no SEC)
    uv run python scripts/run_seasonal.py                  # run (or resume) the due season
    uv run python scripts/run_seasonal.py --season 2026-08 # a given season
    uv run python scripts/run_seasonal.py --calibrate      # spread calibration round (D-M02-52)
    uv run python scripts/run_seasonal.py --gemini-name all        # use case 4 estimate
    uv run python scripts/run_seasonal.py --gemini-name all --yes  # run it

Steps: form indexes for the season windows → year-ago twins of core + promoted names
(≤ 120 filings a run) → phrase mining (local) → EFTS screen (page 1, both windows) →
full test of the ≤ 30 strongest → crowding, theme, samples → ≤ 10 proposals, the rest
listed on the Themes page → theme phrases counted in the latest window → ≤ 25 candidate
companies read, flagged and proposed. Stops at the 45-minute budget or an SEC throttle;
run it again (or with --resume) to continue — every count is stored. Takes
data/refresh.lock. Writes logs/seasonal_<YYYYMMDD-HHMMSS>.txt.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.calls.transcripts import symbol_cik  # noqa: E402
from engine.refresh import load_config  # noqa: E402
from engine.store.db import open_db  # noqa: E402
from engine.themes import industries, mining, seasonal, tiers, twins  # noqa: E402

CALIBRATION = ("pillar two", "cybersecurity incident", "tariffs", "one big beautiful bill",
               "risk factors")  # fmt: skip


def core_and_promoted(engine) -> dict[str, str]:
    """cik → ticker for the owner's watchlist and promoted names (D-M02-52 (1))."""
    out: dict[str, str] = {}
    for t in load_config(ROOT / "config" / "watchlist.toml").tickers:
        if cik := symbol_cik(engine, t):
            out.setdefault(cik, t)
    for m in tiers.members(engine):
        if m.tier == "promoted":
            out.setdefault(m.cik, m.ticker)
    return out


def _client(engine, corpus):
    from engine.sec.client import SecClient, user_agent_from_env
    from engine.store.http import SqliteCache, SqliteFetchLog

    return SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=SqliteFetchLog(engine))


def mine_lines(engine, corpus, s, comps, now) -> list[str]:
    res = mining.mine(engine, corpus, comps, s.day, exclude=seasonal.known_phrases(engine),
                      cap=200)  # fmt: skip
    added = seasonal.store_mined(engine, s, res, now)
    out = [f"\nmining (current {res.current[0]}..{res.current[1]} vs year ago "
           f"{res.year_ago[0]}..{res.year_ago[1]}): {len(res.compared)} companies compared, "
           f"{res.above_floor} phrases with ≥ 2 new adopters, {len(res.candidates)} kept, "
           f"{added} new this run"]  # fmt: skip
    for cik, kinds in sorted(res.compared.items()):
        out.append(f"  {comps.get(cik, cik)}: compared {', '.join(kinds)}")
    for cik, why in sorted(res.not_compared.items()):
        out.append(f"  {comps.get(cik, cik)}: not compared — {why}")
    out.append("  top 25 (adopters − droppers, adopters, phrase):")
    for m in res.candidates[:25]:
        out.append(f"    {m.score:>3} {len(m.adopters):>3}  {m.phrase}  "
                   f"[{', '.join(comps.get(c, c) for c in m.adopters)}]")  # fmt: skip
    return out


def stage_lines(engine, s) -> list[str]:
    counts = seasonal.stage_counts(engine, s.key)
    out = [f"\nstages: {counts}"]
    for r in engine.execute(
        "SELECT * FROM seasonal_phrase WHERE season = ? AND stage IN ('passed', 'proposed', "
        "'listed', 'failed') ORDER BY stage, p_value", (s.key,)
    ):  # fmt: skip
        sp = json.loads(r["spread"] or "{}")
        groups = "; ".join(f"{g} {n}" for g, n in sp.get("groups", [])[:3])
        crowd = json.loads(r["crowding"] or "{}")
        theme = engine.execute("SELECT key FROM theme WHERE theme_id = ?",
                               (r["theme_id"],)).fetchone() if r["theme_id"] else None  # fmt: skip
        out.append(f"  [{r['stage']}] {r['phrase']}: {r['reason']}")
        if r["stage"] != "failed":
            out.append(
                f"      spread: {groups} · finance {sp.get('finance')} · blank "
                f"{sp.get('blank_check')} · no SIC {sp.get('unknown')} · fund filings "
                f"{crowd.get('prior')} → {crowd.get('latest')}"
                f"{' (crowding)' if crowd.get('flag') else ''} · theme "
                f"{theme[0] if theme else 'new'} (overlap {r['overlap'] or 0:.0%})"
            )
    out.append("  screened out (first 30):")
    for r in engine.execute("SELECT phrase, reason FROM seasonal_phrase WHERE season = ? AND "
                            "stage = 'screened_out' ORDER BY rank LIMIT 30", (s.key,)):  # fmt: skip
        out.append(f"    {r[0]}: {r[1]}")
    return out


def company_lines(engine, s) -> list[str]:
    out = ["\ncompanies (this season):"]
    for r in engine.execute(
        "SELECT c.*, t.key FROM seasonal_company c JOIN theme t USING (theme_id) WHERE "
        "c.season = ? ORDER BY c.tier, t.key, c.name", (s.key,)
    ):  # fmt: skip
        fl = json.loads(r["flags"] or "[]")
        out.append(f"  [{r['tier']}] {r['key']}: {r['ticker'] or '-'} {r['name']} · "
                   f"{r['section'] or '-'}{' · quantified' if r['quantified'] else ''} · first "
                   f"{r['first_mention']} · {r['size_label']}"
                   + (f" · FLAGS: {'; '.join(fl)}" if fl else ""))  # fmt: skip
    return out


def calibrate(client, engine, s, now) -> list[str]:
    """D-M02-52 (3): spread of phrases that rose everywhere vs the active seed phrases."""
    out = [f"\ncalibration ({s.family}, {s.latest[0]}..{s.latest[1]}, ≤ "
           f"{seasonal.TEST_PAGES} pages; finance shown apart):"]  # fmt: skip
    phrases = [*CALIBRATION, *[r[0].strip('"') for r in engine.execute(
        "SELECT p.phrase FROM theme_phrase p JOIN theme t USING (theme_id) WHERE "
        "t.status = 'active' AND p.status = 'active' ORDER BY p.phrase")]]  # fmt: skip
    for ph in phrases:
        c = seasonal.count(client, engine, s, ph, s.family, s.latest, seasonal.TEST_PAGES, now)
        if c.documents is None:
            out.append(f"  {ph}: failed ({c.error})")
            continue
        sp = industries.spread(c.sics.items())
        pct = lambda v: "—" if v is None else f"{v:.0%}"  # noqa: E731
        tag = "CAL " if ph in CALIBRATION else "seed"
        out.append(
            f"  {tag} {ph:<36} cos {'≥' if c.lower_bound else ''}{sp.operating:>5} "
            f"fin {sp.finance:>4} known {sum(n for _, n in sp.groups):>5} top1 "
            f"{pct(sp.top1_share):>4} top2 {pct(sp.top2_share):>4} top3 "
            f"{pct(sp.top3_share):>4}  [{'; '.join(f'{g} {n}' for g, n in sp.groups[:3])}]"
        )
    return out


def gemini(engine, corpus, s, which: str, yes: bool, now) -> list[str]:
    from engine.llm import theme_names
    from engine.llm.provider import GeminiProvider, estimate_tokens, load_settings
    from engine.llm.runs import run as llm_run

    rows = engine.execute(
        "SELECT phrase FROM seasonal_phrase WHERE season = ? AND stage IN "
        "('proposed', 'listed', 'passed') ORDER BY phrase",
        (s.key,),
    ).fetchall()
    phrases = [r[0] for r in rows if which == "all" or r[0] == which.lower()]
    llm = load_settings()
    reqs = [(p, r) for p in phrases if (r := theme_names.request(engine, corpus, s.key, p))]
    cost = sum(float(llm.cost(estimate_tokens(r.system + r.user), 400)) for _, r in reqs)
    out = [f"\ngemini use case 4: {len(reqs)} phrase(s), estimated ${cost:.4f} ({llm.model})"]
    if not yes:
        return out + ["  estimate only; add --yes to run"]
    provider = GeminiProvider()
    for p, r in reqs:
        res = llm_run(engine, provider, llm, r, now)
        info = theme_names.apply(engine, s.key, p, res, now)
        out.append(f"  {p}: name {info['name']!r}; variants {info['variants']} "
                   f"({info['added']} new candidates); rejected {len(info['rejected'])}; "
                   f"${res.cost_usd or 0:.4f}")  # fmt: skip
    return out


def _main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--season", help="season key YYYY-MM (default: the latest season date)")
    ap.add_argument("--dry-run", action="store_true", help="plan and estimate, no SEC requests")
    ap.add_argument("--resume", action="store_true", help="continue a stopped pass (the default)")
    ap.add_argument("--no-sec", action="store_true", help="mine only (local)")
    ap.add_argument("--calibrate", action="store_true", help="spread calibration round")
    ap.add_argument("--gemini-name", metavar="PHRASE|all", help="Gemini use case 4 (estimate)")
    ap.add_argument("--yes", action="store_true", help="run Gemini after the estimate")
    ap.add_argument("--minutes", type=float, default=seasonal.TIME_BUDGET_S / 60)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import os

    os.chdir(ROOT)
    engine = open_db("engine", ROOT / "data")
    corpus = open_db("corpus", ROOT / "data")
    now = datetime.now(UTC)
    today = now.date()
    s = seasonal.season_for_key(args.season) if args.season else seasonal.latest_season(today)
    comps = core_and_promoted(engine)
    lines = [f"run_seasonal {now:%Y-%m-%d %H:%M} UTC · season {s.key} ({s.day}) · family "
             f"{s.family} · latest {s.latest[0]}..{s.latest[1]} vs {s.prior[0]}..{s.prior[1]} "
             f"· {len(comps)} core/promoted companies"]  # fmt: skip
    row = seasonal.run_row(engine, s.key)
    lines.append(f"state: {row['status'] if row else 'not started'}")

    if args.gemini_name:
        lines += gemini(engine, corpus, s, args.gemini_name, args.yes, now)
        return _write(lines)
    if args.dry_run or args.no_sec:
        todo, missing = twins.plan(engine, corpus, comps, s.day)
        lines.append(f"year-ago twins to fetch: {len(todo)} filings (~{3 * len(todo)} requests); "
                     f"{len(missing)} current documents without a twin in the index")  # fmt: skip
        if args.no_sec:
            seasonal.ensure_run(engine, s, now)
            lines += mine_lines(engine, corpus, s, comps, now)
        est = seasonal.estimate(engine, s.key)
        lines.append(f"estimate: screen {est['screen']} requests, full tests ≤ {est['test_max']}, "
                     f"theme phrases ≤ {10 * len(seasonal.known_phrases(engine))}, candidates "
                     f"≤ {2 * 25}; at ~2 requests/s (D-M02-52 (6))")  # fmt: skip
        return _write(lines)

    from engine.themes.universe import ensure_quarters, quarters_between

    client = _client(engine, corpus)
    if args.calibrate:
        ensure_quarters(
            client, engine, quarters_between(date.fromisoformat(s.prior[0]), s.day), now
        )
        lines += calibrate(client, engine, s, now)
        return _write(lines)

    budget = seasonal.Budget(args.minutes * 60)
    seasonal.ensure_run(engine, s, now)
    try:
        qs = ensure_quarters(
            client, engine, quarters_between(date.fromisoformat(s.prior[0]), s.day), now
        )
        lines.append(f"form indexes: {sum(q.status == 'fetched' for q in qs)} fetched, "
                     f"{sum(q.status == 'failed' for q in qs)} failed; p0 = "
                     f"{seasonal.p0(engine, s):.3f}")  # fmt: skip
        tw = twins.fetch_twins(client, engine, corpus, comps, s.day, now)
        lines += tw.lines()
        if tw.throttled:
            raise seasonal.Throttled(tw.throttled)
        lines += mine_lines(engine, corpus, s, comps, now)
        seasonal.set_status(engine, s.key, "testing", now)
        n = seasonal.screen(client, engine, s, now, budget, progress=print)
        lines.append(f"\nscreened {n} phrases this run")
        n = seasonal.test(client, engine, corpus, s, now, budget, progress=print)
        lines.append(f"fully tested {n} phrases this run")
        lines.append(f"proposals: {seasonal.propose_pass(engine, s, now, comps)}")
        from engine.themes.candidates import run_candidates

        rep = run_candidates(client, engine, corpus, s, set(comps), now, budget.over)
        lines += rep.lines()
        left = seasonal.stage_counts(engine, s.key)
        if budget.over():
            lines.append("\nSTOPPED at the time budget; run again to continue.")
        elif left.get("candidate") or left.get("screened"):
            lines.append("\nNot finished (candidates left); run again to continue.")
        else:
            seasonal.set_status(engine, s.key, "done", now, {"stages": left})
            lines.append(f"\nseason {s.key} done.")
    except seasonal.Throttled as e:
        lines.append(f"\nSTOPPED by SEC throttle: {e}; run again later to continue.")
    lines += stage_lines(engine, s)
    lines += company_lines(engine, s)
    sent = engine.execute("SELECT count(*) FROM fetch_log WHERE at >= ? AND from_cache = 0",
                          (now.isoformat(timespec="seconds"),)).fetchone()[0]  # fmt: skip
    lines.append(f"\nSEC requests sent this run: {sent:,} in {(datetime.now(UTC) - now).seconds} s")
    return _write(lines)


def _write(lines: list[str]) -> int:
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"seasonal_{datetime.now():%Y%m%d-%H%M%S}.txt"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nlog written to: {log}")
    return 0


def main() -> int:
    if "--dry-run" in sys.argv[1:]:
        return _main()  # reads only: no lock needed
    from engine.store.lock import run_script

    return run_script(ROOT, "run_seasonal", _main)


if __name__ == "__main__":
    sys.exit(main())
