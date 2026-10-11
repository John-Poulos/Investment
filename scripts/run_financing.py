"""Financing and equity links (M02 part 5b, D-M02-41…45): 13F, 13D/13G, text passages,
credit-quality series, loop flags.

    uv run python scripts/run_financing.py              # live check (SEC)
    uv run python scripts/run_financing.py --no-sec     # stored data only
    uv run python scripts/run_financing.py --rescan     # re-read with the current rules

SEC requests, first run: 13F of our filers for the last 8 quarters (index + cover + table,
~3 per filing), one index page per XML 13D/13G schedule listed under our companies
(once each) + the XML of relevant ones, ≤ --f302-cap 8-K Item 3.02 filings (index +
exhibits), the targeted searches (5 phrases per company name, repeated after 30 days)
and ≤ --hit-cap hit documents. Writes logs/financing_<time>.txt.
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
from engine.financing import credit, links, thirteenf  # noqa: E402
from engine.financing.step import run_financing_step  # noqa: E402
from engine.refresh import load_config  # noqa: E402
from engine.store.db import open_db  # noqa: E402
from engine.themes import tiers  # noqa: E402


def companies(engine) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in load_config(ROOT / "config" / "watchlist.toml").tickers:
        if cik := symbol_cik(engine, t):
            out[t] = cik
    for m in tiers.members(engine):
        out.setdefault(m.ticker, m.cik)
    return out


def _b(x) -> str:
    return "—" if x is None else f"${float(x) / 1e9:,.2f}B"


def summary(engine, comps: dict[str, str], now: datetime) -> list[str]:
    lines = ["", "13F holdings, latest quarter per filer (top 10 by value):"]
    for t, cik in sorted(comps.items()):
        periods = thirteenf.current(engine, cik)
        if not periods:
            continue
        p = max(periods)
        rows = periods[p]
        st = Counter(r["status"] for r in rows)
        lines.append(
            f"  {t} {p}: {len(rows)} holding(s) {dict(st)}; quarters stored {len(periods)}"
        )
        for r in rows[:10]:
            lines.append(
                f"    {r['issuer_name']} · {r['title']} · {r['cusip']} · {_b(r['value_usd'])} · "
                f"{float(r['shares'] or 0):,.0f} {r['share_type'] or ''} · {r['status']}"
                + (f" ({r['resolved_how']})" if r["resolved_how"] else "")
                + (f" — {r['check_note']}" if r["check_note"] else "")
            )
    lines.append("")
    lines.append("13D/13G stakes stored:")
    for r in engine.execute(
        "SELECT * FROM fin_holding WHERE source IN ('13D', '13G') ORDER BY filed DESC LIMIT 25"
    ):
        lines.append(
            f"  {r['filer_name']} → {r['issuer_name']} · {r['source']} {r['period']} · "
            f"{float(r['shares'] or 0):,.0f} sh · {r['pct_class']}% · {r['status']}"
        )
    hdr = engine.execute(
        "SELECT count(*), sum(relevant), sum(xml_read) FROM fin_schedule"
    ).fetchone()
    lines.append(f"  headers read {hdr[0]}, relevant {hdr[1] or 0}, XML read {hdr[2] or 0}")
    un = engine.execute(
        "SELECT issuer_name, cusip, count(*) n, max(resolved_how) how, max(period) last "
        "FROM fin_holding WHERE status = 'unresolved' "
        "GROUP BY substr(cusip, 1, 6) ORDER BY n DESC LIMIT 30"
    ).fetchall()
    if un:
        lines.append("")
        lines.append(f"Unresolved 13F issuers ({len(un)} shown):")
        lines += [
            f"  {r['issuer_name']} ({r['cusip']}) × {r['n']} · {r['how']} · latest {r['last']}"
            for r in un
        ]
    lines.append("")
    lines.append("Text passages by kind and status:")
    for r in engine.execute(
        "SELECT kind, status, count(*) n, count(DISTINCT pair_key) p FROM fin_text "
        "GROUP BY kind, status ORDER BY kind, status"
    ):
        lines.append(f"  {r['kind']} {r['status']}: {r['n']} passage(s), {r['p']} pair(s)")
    seen = set()
    lines.append("Pairs (up to 30):")
    for r in engine.execute(
        "SELECT * FROM fin_text ORDER BY amount_usd IS NULL, filed DESC"
    ).fetchall():
        k = (r["pair_key"], r["kind"])
        if k in seen:
            continue
        seen.add(k)
        d = {"a_to_b": f"{r['a_name']} → {r['b_name']}", "b_to_a": f"{r['b_name']} → {r['a_name']}"}
        lines.append(
            f"  [{r['kind']}] {d.get(r['direction'], r['a_name'] + ' – ' + r['b_name'] + ' (?)')}"
            f" · {_b(r['amount_usd'])} · {r['instrument'] or ''} · {r['form'] or ''} "
            f"{r['filed'] or ''}"
        )
        lines.append(f"      “{' '.join(r['quote'].split())[:300]}”")
        if len(seen) >= 30:
            break
    lines.append("")
    lps = links.loops(engine)
    lines.append(f"Loops: {sum(lp.flagged for lp in lps)} flagged, "
                 f"{sum(not lp.flagged for lp in lps)} supply financing")  # fmt: skip
    for lp in lps:
        a = links.registry_name(engine, lp.edge.financer) or lp.edge.financer
        b = links.registry_name(engine, lp.edge.other) or lp.edge.other
        lines.append(f"  {a} → {b}: {lp.text} ({lp.edge.label})")
    lines.append("")
    lines.append("Credit series (latest; alerts marked !):")
    for t, cik in sorted(comps.items()):
        parts = []
        for s in credit.company_series(engine, cik):
            if not s.obs:
                continue
            o = s.latest
            v = (f"{o.value:.0f}d" if s.unit == "days" else _b(o.value) if s.unit == "usd"
                 else f"{100 * o.value:.2f}%")  # fmt: skip
            stale = " not tagged since" if s.stale(now.date()) else ""
            ch = (f" {o.change:+.0%} y/y {credit.band(o.change)}"
                  if s.key == "dso" and o.change is not None else "")  # fmt: skip
            parts.append(f"{s.key} {v}{ch} ({stale}{o.end}){' !' if s.alert else ''}")
        lines.append(f"  {t}: " + ("; ".join(parts) or "no series"))
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-sec", action="store_true", help="stored data only")
    ap.add_argument("--rescan", action="store_true", help="re-read stored documents")
    ap.add_argument("--force-search", action="store_true", help="repeat the searches now")
    ap.add_argument("--no-search", action="store_true", help="skip the targeted searches")
    ap.add_argument("--f302-cap", type=int, default=10, help="8-K Item 3.02 filings to fetch")
    ap.add_argument("--hit-cap", type=int, default=30, help="search hit documents to fetch")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if (ROOT / "data" / "refresh.lock").exists():
        print("data/refresh.lock exists: the refresh is running; try again later.")
        return 1
    os.chdir(ROOT)
    engine = open_db("engine", ROOT / "data")
    corpus = open_db("corpus", ROOT / "data")
    now = datetime.now(UTC)
    comps = companies(engine)
    client = None
    if not args.no_sec:
        from engine.sec.client import SecClient, user_agent_from_env
        from engine.store.http import SqliteCache, SqliteFetchLog

        client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus),
                           log=SqliteFetchLog(engine))  # fmt: skip
    lines = [f"run_financing {now:%Y-%m-%d %H:%M} UTC · {len(comps)} companies"]
    lines += run_financing_step(client, engine, corpus, comps, now, f302_cap=args.f302_cap,
                                hit_cap=args.hit_cap, force_search=args.force_search,
                                rescan=args.rescan, search=not args.no_search)  # fmt: skip
    lines += summary(engine, comps, now)
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"financing_{datetime.now():%Y%m%d-%H%M%S}.txt"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:40]))
    print(f"… {len(lines)} lines; log written to: {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
