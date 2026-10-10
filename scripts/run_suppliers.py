"""Suppliers L0–L3 (M02 part 5): find link passages, build the precision set, run Gemini.

    uv run python scripts/run_suppliers.py --customers NVDA --probe   # live check
    uv run python scripts/run_suppliers.py --no-sec                   # local rungs only
    uv run python scripts/run_suppliers.py --label-set                # pick the ~30 passages
    uv run python scripts/run_suppliers.py --gemini-labels --gold     # estimate; --yes runs
    uv run python scripts/run_suppliers.py --gemini-labels            # label open candidates
    uv run python scripts/run_suppliers.py --gemini-inputs NVDA,MU    # use case 5b (L0)

SEC requests: L3 ≤ --l3-cap new Item 1.01 filings (index + exhibits), L2 searches for the
customers (4 phrases per alias, repeated after 30 days; --force-search to repeat now) and
≤ --l2-cap hit documents; --probe adds ≤ 10 pages per bare alias (counts only).
Gemini runs only with --yes, after the estimate. Writes logs/suppliers_<time>.txt.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.calls.transcripts import symbol_cik  # noqa: E402
from engine.refresh import load_config  # noqa: E402
from engine.store.db import open_db  # noqa: E402
from engine.supply import gold  # noqa: E402
from engine.supply.step import run_supply_step  # noqa: E402
from engine.themes import tiers  # noqa: E402


def companies(engine) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in load_config(ROOT / "config" / "watchlist.toml").tickers:
        if cik := symbol_cik(engine, t):
            out[t] = cik
    for m in tiers.members(engine):
        out.setdefault(m.ticker, m.cik)
    return out


def summary(engine) -> list[str]:
    lines = ["", "Passages by rung and status:"]
    for r in engine.execute(
        "SELECT rung, status, count(*) n, count(DISTINCT pair_key) p FROM "
        "supply_link WHERE stale = 0 GROUP BY rung, status ORDER BY rung, status"
    ):
        lines.append(f"  {r['rung']} {r['status']}: {r['n']} passage(s), {r['p']} pair(s)")
    lines.append("")
    lines.append("Pairs (strongest passage, up to 40):")
    rows = engine.execute(
        "SELECT pair_key, rung, a_name, b_name, direction, share_pct, quote, form, filed "
        "FROM supply_link WHERE stale = 0 "
        "ORDER BY CASE rung WHEN 'L2' THEN 0 WHEN 'L1' THEN 1 ELSE 2 END, "
        "share_pct IS NULL, filed DESC"
    ).fetchall()
    seen = set()
    for r in rows:
        if r["pair_key"] in seen:
            continue
        seen.add(r["pair_key"])
        d = {
            "a_to_b": f"{r['a_name']} → {r['b_name']}",
            "b_to_a": f"{r['b_name']} → {r['a_name']}",
        }.get(r["direction"], f"{r['a_name']} – {r['b_name']} (?)")
        share = f" {r['share_pct']}%" if r["share_pct"] is not None else ""
        lines.append(f"  [{r['rung']}] {d}{share} · {r['form'] or ''} {r['filed'] or ''}")
        lines.append(f"      “{r['quote'][:300]}”")
        if len(seen) >= 40:
            break
    return lines


def gemini_labels(engine, now, use_gold: bool, yes: bool) -> list[str]:
    from engine.llm import supply_labels
    from engine.llm.provider import GeminiProvider, estimate_tokens, load_settings
    from engine.llm.runs import cached_call
    from engine.llm.runs import run as llm_run

    if use_gold:
        ids = gold.link_ids(engine)
    else:
        ids = [
            r[0]
            for r in engine.execute(
                "SELECT link_id FROM supply_link WHERE status = 'candidate' AND llm_type IS NULL"
            )
        ]
    if not ids:
        return ["gemini labels: nothing to label"]
    llm = load_settings()
    reqs = [
        r
        for r in supply_labels.label_requests(engine, ids)
        if not cached_call(engine, r, llm.model)
    ]
    cost = sum(
        float(llm.cost(estimate_tokens(r.system + r.user), 60 * supply_labels.BATCH)) for r in reqs
    )
    out = [
        f"gemini labels: {len(ids)} passage(s) in {len(reqs)} new request(s), estimated "
        f"${cost:.4f} ({llm.model})"
    ]
    if not yes:
        return out + ["  estimate only; add --yes to run"]
    provider = GeminiProvider()
    for r in supply_labels.label_requests(engine, ids):
        try:
            res = llm_run(engine, provider, llm, r, now)
        except Exception as e:  # one batch failing must not stop the others
            out.append(f"  error {type(e).__name__}: {e}")
            continue
        n = supply_labels.apply_labels(engine, res)
        rejected = sum(not o.verified for o in res.observations)
        out.append(
            f"  {n} label(s) stored, {rejected} rejected (quote not verified); "
            f"${res.cost_usd or 0:.4f}"
        )
    if use_gold:
        out.append("  " + gold.accuracy(engine).line())
        if trial := gold.trial_line(engine):
            out.append("  " + trial)
    return out


def gemini_inputs(engine, corpus, tickers: list[str], now, yes: bool) -> list[str]:
    from engine.llm import supply_labels
    from engine.llm.provider import GeminiProvider, estimate_tokens, load_settings
    from engine.llm.runs import run as llm_run

    llm = load_settings()
    out = []
    for t in tickers:
        cik = symbol_cik(engine, t)
        prep = supply_labels.input_request(engine, corpus, cik) if cik else None
        if prep is None:
            out.append(f"inputs {t}: no stored 10-K")
            continue
        req, _ = prep
        cost = float(llm.cost(estimate_tokens(req.system + req.user), 2000))
        out.append(f"inputs {t}: ~{estimate_tokens(req.user):,} tokens, estimated ${cost:.4f}")
        if not yes:
            continue
        res = llm_run(engine, GeminiProvider(), llm, req, now)
        n = supply_labels.apply_inputs(engine, cik, t, res, now)
        rej = sum(not o.verified for o in res.observations)
        out.append(
            f"  {n} new categor(ies) queued for review, {rej} rejected; ${res.cost_usd or 0:.4f}"
        )
    if not yes and tickers:
        out.append("  estimate only; add --yes to run")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-sec", action="store_true", help="no SEC requests (L1, stored only)")
    ap.add_argument("--customers", help="L2 customers (aliases keys/tickers), default all")
    ap.add_argument("--probe", action="store_true", help="counts-only probe of option (c)")
    ap.add_argument("--force-search", action="store_true", help="repeat L2 searches now")
    ap.add_argument(
        "--rescan",
        action="store_true",
        help="re-read stored documents with the current rules (after a rule change)",
    )
    ap.add_argument("--l2-cap", type=int, default=30, help="L2 hit documents to fetch")
    ap.add_argument("--l3-cap", type=int, default=10, help="new Item 1.01 filings to read")
    ap.add_argument("--label-set", action="store_true", help="pick the precision set once")
    ap.add_argument("--gemini-labels", action="store_true", help="Gemini use case 5")
    ap.add_argument("--gold", action="store_true", help="with --gemini-labels: the set only")
    ap.add_argument("--gemini-inputs", help="Gemini use case 5b for these tickers")
    ap.add_argument("--yes", action="store_true", help="make the Gemini calls")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if (ROOT / "data" / "refresh.lock").exists():
        print("data/refresh.lock exists: the refresh is running; try again later.")
        return 1
    os.chdir(ROOT)  # config/ and logs/ are relative to the repo
    engine = open_db("engine", ROOT / "data")
    corpus = open_db("corpus", ROOT / "data")
    now = datetime.now(UTC)
    lines = [f"run_suppliers {now:%Y-%m-%d %H:%M} UTC"]
    gemini_only = args.label_set or args.gemini_labels or args.gemini_inputs
    if not gemini_only:
        client = None
        if not args.no_sec:
            from engine.sec.client import SecClient, user_agent_from_env
            from engine.store.http import SqliteCache, SqliteFetchLog

            client = SecClient(
                user_agent_from_env(), cache=SqliteCache(corpus), log=SqliteFetchLog(engine)
            )
        wanted = {c.strip().upper() for c in args.customers.split(",")} if args.customers else None
        lines += run_supply_step(
            client,
            engine,
            corpus,
            companies(engine),
            now,
            l3_cap=args.l3_cap,
            l2_cap=args.l2_cap,
            customers=wanted,
            probe=args.probe,
            rescan=args.rescan,
            force_search=args.force_search,
        )
        lines += summary(engine)
    if args.label_set:
        n = gold.build(engine)
        lines.append(f"precision set: {n} passage(s); label them at /m02/labels in the app")
        mix = Counter(
            r[0]
            for r in engine.execute(
                "SELECT l.rung FROM link_gold g JOIN supply_link l ON l.link_id = g.link_id"
            )
        )
        lines.append(f"  by rung: {dict(mix)}")
    if args.gemini_labels:
        lines += gemini_labels(engine, now, args.gold, args.yes)
    if args.gemini_inputs:
        tickers = [t.strip().upper() for t in args.gemini_inputs.split(",") if t.strip()]
        lines += gemini_inputs(engine, corpus, tickers, now, args.yes)
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"suppliers_{datetime.now():%Y%m%d-%H%M%S}.txt"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"Log written to: {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
