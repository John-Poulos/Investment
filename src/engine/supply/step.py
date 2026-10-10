"""The supplier step of a refresh run (M02 part 5). Never fails the run.

Order: L1 over stored 10-K/10-Q text (local) → L3 exhibits (≤ `l3_cap` new Item 1.01
filings per run) → L2 searches for `customer = true` aliases (each repeated after 30
days) and hit documents (≤ `l2_cap` per run, newest first; the rest wait) → decided
pairs absorb new passages → one `m02_link` proposal per undecided pair (weekly cap).
Gemini runs only on the owner's request (scripts/run_suppliers.py).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from engine.sec.client import SecClient
from engine.supply import aliases, links, scan

L3_CAP = 10
L2_CAP = 30


def run_supply_step(
    client: SecClient | None,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    l3_cap: int = L3_CAP,
    l2_cap: int = L2_CAP,
    customers: set[str] | None = None,
    probe: bool = False,
    force_search: bool = False,
    rescan: bool = False,
    alias_path: Path = aliases.ALIASES,
) -> list[str]:
    lines = ["Suppliers (M02 part 5):"]
    try:
        matcher = aliases.Matcher(aliases.load(engine, alias_path))
        if not matcher.companies:
            return lines + ["skipped — config/aliases.toml has no companies"]
        rep = scan.ScanReport()
        fetched = 0
        for _, cik in sorted(companies.items()):
            scan.scan_l1(engine, corpus, matcher, cik, now, rep)
            fetched += scan.scan_l3(
                client, engine, corpus, matcher, cik, now, rep, max(0, l3_cap - fetched)
            )
        wanted = [
            c
            for c in matcher.companies
            if c.customer
            and (customers is None or c.key in customers or (c.ticker or "") in customers)
        ]
        if client is not None:
            for c in wanted:
                scan.search_l2(client, engine, c, now, rep, force=force_search)
                if c.bare:
                    scan.search_bare(client, engine, c, now, rep, force=force_search)
        scan.fetch_l2(client, engine, corpus, matcher, now, rep, l2_cap)
        if rescan:  # re-read every stored L2 document with the current rules, then prune
            by_key = {c.key: c for c in matcher.companies}
            for q in engine.execute(
                "SELECT * FROM supply_fetch WHERE status = 'stored'"
            ).fetchall():
                scan.read_l2(engine, corpus, matcher, q, by_key.get(q["customer_key"]), now, rep)
            lines.append(
                f"re-read: {links.prune(engine, now)} passage(s) no longer produced "
                "by the rules were removed"
            )
        if probe and client is not None:
            for c in wanted:
                rep.probe += scan.probe_c(client, engine, c, now)
        waiting = engine.execute(
            "SELECT count(*) FROM supply_fetch WHERE status = 'queued'"
        ).fetchone()[0]
        lines += rep.lines()
        lines.append(f"L2 hit documents still queued: {waiting}")
        followed = links.follow_decisions(engine)
        counts = links.propose_pairs(engine, now)
        lines.append(
            f"link proposals: {counts or 'none new'}"
            + (f"; {followed} passage(s) joined decided pairs" if followed else "")
        )
    except Exception as e:  # the supplier step must not break the run report
        lines.append(f"error — {type(e).__name__}: {e}")
    return lines
