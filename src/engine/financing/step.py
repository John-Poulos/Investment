"""The financing step of a refresh run (M02 part 5b, D-M02-41…45). Never fails the run.

Order: 13F filings of our filers (last 8 quarters, then each new one) → 13D/13G XML
schedule headers (once each) and stakes → review items for unresolved 13F issuers and
records that failed a check (operational, not capped) → text passages (stored documents,
8-K Item 3.02 exhibits ≤ `f302_cap`, targeted searches each 30 days, hit documents ≤
`hit_cap`) → decided pairs absorb new passages → one `m02_finlink` item per undecided
pair and kind → weekly-digest alerts: new loop flags and credit-series rises.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from engine.financing import credit, links, scan, schedules, thirteenf
from engine.financing.find import KIND_LABELS
from engine.sec.client import SecClient
from engine.supply import aliases

F302_CAP = 10
HIT_CAP = 30


def issuer_items(engine: sqlite3.Connection, now: datetime) -> int:
    from engine.moneyflow.views import dollars
    from engine.themes.proposals import propose

    n = 0
    for r in engine.execute(
        "SELECT substr(cusip, 1, 6) AS c6, max(issuer_name) AS name, max(cusip) AS cusip, "
        "group_concat(DISTINCT filer_name) AS filers, count(*) AS rows_n, max(value_usd) AS v, "
        "max(title) AS title, max(period) AS period FROM fin_holding "
        "WHERE status = 'unresolved' GROUP BY c6"
    ):
        payload = {
            "issuer": r["name"],
            "cusip": r["cusip"],
            "title": r["title"],
            "filers": r["filers"],
            "rows": r["rows_n"],
            "period": r["period"],
            "largest_value": dollars(r["v"]) if r["v"] is not None else "not stated",
            "why": "no single SEC company matches this 13F issuer name",
        }
        res = propose(
            engine,
            "m02_13f_issuer",
            r["c6"],
            f"13F issuer to map: {r['name']} ({r['cusip']})",
            payload,
            now,
        )
        n += res == "queued"
    return n


def check_items(engine: sqlite3.Connection, now: datetime) -> int:
    from engine.moneyflow.views import dollars
    from engine.themes.proposals import propose

    n = 0
    for r in engine.execute("SELECT * FROM fin_holding WHERE status = 'held'"):
        payload = {
            "holding_id": r["holding_id"],
            "source": r["source"],
            "filer": r["filer_name"],
            "issuer": r["issuer_name"],
            "cusip": r["cusip"],
            "period": r["period"],
            "shares": r["shares"],
            "value": dollars(float(r["value_usd"])) if r["value_usd"] is not None else None,
            "pct_class": r["pct_class"],
            "check": r["check_note"],
            "why": "a structured record failed a check (D-M02-42)",
        }
        res = propose(
            engine,
            "m02_fin_check",
            f"{r['source']}:{r['accession']}:{r['cusip']}",
            f"{r['filer_name']} → {r['issuer_name']}: {r['check_note']}",
            payload,
            now,
            cik=r["filer_cik"],
        )
        n += res == "queued"
    return n


def loop_alerts(engine: sqlite3.Connection, now: datetime) -> int:
    from engine.themes.proposals import propose

    n = 0
    for lp in links.loops(engine):
        if not lp.flagged:
            continue
        e = lp.edge
        names = {
            c: (engine.execute("SELECT name FROM entity WHERE cik = ?", (c,)).fetchone() or [c])[0]
            for c in (e.financer, e.other)
        }
        why = (
            f"{names[e.financer]} {links.LOOP_CASES[lp.case]} — {names[e.other]} "
            f"({KIND_LABELS[e.kind]}, {e.label})"
        )
        payload = {
            "loop": lp.case,
            "financer": names[e.financer],
            "other": names[e.other],
            "kind": KIND_LABELS[e.kind],
            "source": e.label,
            "amount": e.amount if e.amount is not None else "not stated",
            "share": lp.share_pct / 100 if lp.share_pct is not None else "not stated",
            "why": why,
            "note": "hypothesis, not scored (D-M02-41)",
        }
        res = propose(
            engine,
            "m02_fin_alert",
            f"loop:{e.financer}:{e.other}:{lp.case}",
            f"New loop: {why}",
            payload,
            now,
            cik=e.financer,
        )
        n += res in ("queued", "overflow")
    return n


def run_financing_step(
    client: SecClient | None,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    f302_cap: int = F302_CAP,
    hit_cap: int = HIT_CAP,
    force_search: bool = False,
    rescan: bool = False,
    search: bool = True,
    alias_path: Path = aliases.ALIASES,
) -> list[str]:
    lines = ["Financing links (M02 part 5b):"]
    try:
        ciks = sorted(set(companies.values()))
        matcher = aliases.Matcher(aliases.load(engine, alias_path))
        known = set(ciks) | {c.cik for c in matcher.companies if c.cik}
        r13 = thirteenf.Report13F()
        thirteenf.run(client, engine, ciks, now, r13)
        lines += r13.lines()
        rs = schedules.ReportSchedules()
        schedules.run(client, engine, set(ciks), known, now, rs)
        lines += rs.lines()
        lines.append(
            f"review: {issuer_items(engine, now)} 13F issuer(s) to map, "
            f"{check_items(engine, now)} record(s) held by a check"
        )
        rep = scan.ScanReport()
        if matcher.companies:
            scan.read_stored(engine, corpus, matcher, ciks, now, rep, rescan=rescan)
            scan.fetch_302(client, engine, corpus, ciks, now, rep, f302_cap)
            if client is not None and search:
                for c in matcher.companies:
                    if c.cik in ciks and not scan.search_company(
                        client, engine, c, now, rep, force=force_search
                    ):
                        break
            scan.fetch_hits(client, engine, corpus, matcher, now, rep, hit_cap)
            if rescan:
                scan.reread_hits(engine, corpus, matcher, now, rep)
                lines.append(
                    f"re-read: {links.prune(engine, now)} passage(s) no longer produced removed"
                )
        lines += rep.lines()
        waiting = engine.execute(
            "SELECT count(*) FROM fin_fetch WHERE status = 'queued'"
        ).fetchone()[0]
        lines.append(f"hit documents still queued: {waiting}")
        followed = links.follow_decisions(engine)
        counts = links.propose_pairs(engine, now)
        lines.append(
            f"financing link proposals: {counts or 'none new'}"
            + (f"; {followed} passage(s) joined decided pairs" if followed else "")
        )
        lines.append(
            f"alerts: {loop_alerts(engine, now)} new loop(s), "
            f"{credit.queue_alerts(engine, companies, now)} credit-series rise(s)"
        )
    except Exception as e:  # the financing step must not break the run report
        lines.append(f"error — {type(e).__name__}: {e}")
    return lines
