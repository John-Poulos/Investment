"""Store link passages, propose one `m02_link` item per company pair, apply the decision.

A pair (unordered) collects every passage that ties the two companies, from any rung.
The review item states a claimed direction — who supplies whom — from the strongest
evidence: a stated L2/L1 direction, else Gemini's label, else "not stated" (L3). The
owner confirms (the claimed direction), flips it, or rejects the link. A confirmed link
whose supplier is a known SEC company outside the watchlist and tracked tier is proposed
as an `m02_candidate`; a tracked supplier gets a promotion suggestion (D-M02-11). A
decided pair absorbs later passages without a new item. Missing link = unknown.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from engine.sec.client import iso
from engine.supply.aliases import Company
from engine.supply.find import Found

SAMPLES = 3
RUNG_ORDER = {"L2": 0, "L1": 1, "L3": 2}
GRADE = {"L1": "A", "L2": "A", "L3": "A"}


@dataclass(frozen=True)
class Doc:
    accession: str
    filename: str
    form: str | None
    filed: str | None
    text: str


def side(cik: str | None, company: Company | None, name: str) -> str:
    if cik:
        return cik
    if company is not None:
        return f"key:{company.key}"
    return f"name:{name}"


def pair_key(a: str, b: str) -> str:
    return "|".join(sorted((a, b)))


def store(
    engine: sqlite3.Connection,
    a_cik: str | None,
    a_name: str,
    a_company: Company | None,
    doc: Doc,
    found: list[Found],
    now: datetime,
) -> int:
    """Insert new passages → count of new rows. A passage found again marks `seen_at`; an
    undecided one also takes the current rules' direction, share and reason."""
    n = 0
    a_side = side(a_cik, a_company, a_name)
    for f in found:
        b_side = side(f.b.cik, f.b, f.b_name)
        if b_side == a_side:
            continue
        existing = engine.execute(
            "SELECT link_id FROM supply_link WHERE accession = ? AND filename = ? "
            "AND quote_start = ? AND a_name = ? AND b_name = ?",
            (doc.accession, doc.filename, f.start, a_name, f.b.name),
        ).fetchone()
        if existing is not None:
            engine.execute(
                "UPDATE supply_link SET seen_at = ?, stale = 0, direction = CASE WHEN "
                "status = 'candidate' THEN ? ELSE direction END, share_pct = CASE WHEN "
                "status = 'candidate' THEN ? ELSE share_pct END, how = ? WHERE link_id = ?",
                (iso(now), f.direction,
                 str(f.share_pct) if f.share_pct is not None else None, f.how, existing[0]),
            )  # fmt: skip
            continue
        cur = engine.execute(
            "INSERT OR IGNORE INTO supply_link (rung, grade, a_cik, a_name, b_cik, b_name, "
            "direction, share_pct, accession, filename, form, filed, quote, quote_start, "
            "quote_end, how, a_side, b_side, pair_key, discovered_at, seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f.rung,
                GRADE[f.rung],
                a_cik,
                a_name,
                f.b.cik,
                f.b.name,
                f.direction,
                str(f.share_pct) if f.share_pct is not None else None,
                doc.accession,
                doc.filename,
                doc.form,
                doc.filed,
                doc.text[f.start : f.end].strip(),
                f.start,
                f.end,
                f.how,
                a_side,
                b_side,
                pair_key(a_side, b_side),
                iso(now),
                iso(now),
            ),
        )
        n += cur.rowcount
    return n


def prune(engine: sqlite3.Connection, since: datetime) -> int:
    """After a full re-read: undecided passages the current rules did not produce again are
    removed; precision-set passages stay (the answer key) but are marked stale (D-M02-40).
    Waiting proposals of pairs with no live passage go too."""
    old = "status = 'candidate' AND (seen_at IS NULL OR seen_at < ?)"
    engine.execute(
        f"UPDATE supply_link SET stale = ({old}) WHERE link_id IN (SELECT link_id FROM link_gold)",
        (iso(since),),
    )
    n = engine.execute(
        f"DELETE FROM supply_link WHERE {old} AND link_id NOT IN (SELECT link_id FROM link_gold)",
        (iso(since),),
    ).rowcount
    engine.execute(
        "DELETE FROM m02_proposal WHERE kind = 'm02_link' AND status = 'overflow' AND "
        "substr(prop_key, 10) NOT IN (SELECT pair_key FROM supply_link WHERE stale = 0)"
    )
    return n


# --- Claimed direction ------------------------------------------------------------------


def _sides(r: sqlite3.Row) -> tuple[tuple[str, str], tuple[str, str]]:
    """((side, name) of A, (side, name) of B); side = cik, key:<alias> or name:<text>."""
    return (r["a_side"], r["a_name"]), (r["b_side"], r["b_name"])


def _supplier_of(r: sqlite3.Row) -> tuple[str, str] | None:
    """(side, name) of the supplier a link row claims, or None when not stated."""
    d = r["direction"] or (
        r["llm_direction"] if r["llm_direction"] in ("a_to_b", "b_to_a") else None
    )
    if d is None:
        return None
    a, b = _sides(r)
    return a if d == "a_to_b" else b


def claimed(rows: list[sqlite3.Row]) -> tuple[str, str, str, str, str] | None:
    """(supplier side, supplier name, customer side, customer name, basis), strongest row."""
    for r in sorted(rows, key=lambda r: (RUNG_ORDER[r["rung"]], r["direction"] is None)):
        sup = _supplier_of(r)
        if sup is None:
            continue
        a, b = _sides(r)
        cust = b if sup == a else a
        basis = f"{r['rung']} wording" if r["direction"] else "Gemini label"
        return sup[0], sup[1], cust[0], cust[1], basis
    return None


def _rows(engine: sqlite3.Connection, key: str) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT * FROM supply_link WHERE pair_key = ? AND stale = 0 ORDER BY rung, filed DESC",
        (key,),
    ).fetchall()


def propose_pairs(engine: sqlite3.Connection, now: datetime) -> dict[str, int]:
    """One `m02_link` proposal per undecided pair; L2 with a revenue share first."""
    from engine.themes.proposals import propose

    keys = [
        r[0]
        for r in engine.execute(
            "SELECT pair_key, min(CASE rung WHEN 'L2' THEN 0 WHEN 'L1' THEN 1 ELSE 2 END) AS o, "
            "max(share_pct IS NOT NULL) AS s FROM supply_link WHERE stale = 0 GROUP BY pair_key "
            "HAVING sum(status != 'candidate') = 0 ORDER BY s DESC, o, pair_key"
        )
    ]
    counts: dict[str, int] = {}
    for key in keys:
        rows = _rows(engine, key)
        c = claimed(rows)
        first = rows[0]
        names = sorted({first["a_name"], first["b_name"]})
        best = sorted(rows, key=lambda r: (RUNG_ORDER[r["rung"]], -(r["share_pct"] or 0)))
        samples = [
            f"{r['quote']} [{r['rung']} · {r['a_name']} {r['form'] or ''} {r['filed'] or ''}"
            + (f" · {r['share_pct']}% of revenue" if r["share_pct"] is not None else "")
            + "]"
            for r in best[:SAMPLES]
        ]
        share = next((float(r["share_pct"]) for r in best if r["share_pct"] is not None), None)
        claim = f"{c[1]} supplies {c[3]} ({c[4]})" if c else "direction not stated (contract only)"
        payload = {
            "pair": key,
            "companies": 2,
            "supplier_side": c[0] if c else None,
            "supplier_claimed": c[1] if c else None,
            "customer_side": c[2] if c else None,
            "customer_claimed": c[3] if c else None,
            "claim": claim,
            "rungs": sorted({r["rung"] for r in rows}),
            "passages": len(rows),
            "share_pct": share,
            "samples": samples,
            "money_flow": share is not None,
            "why": f"{names[0]} – {names[1]}: {claim}",
        }
        cik = first["a_cik"] or first["b_cik"]
        reason = f"Link {names[0]} – {names[1]}: {claim}"
        res = propose(engine, "m02_link", key, reason, payload, now, cik=cik)
        counts[res] = counts.get(res, 0) + 1
    return counts


def follow_decisions(engine: sqlite3.Connection) -> int:
    """New passages of a decided pair take the pair's decision."""
    return engine.execute(
        "UPDATE supply_link SET status = (SELECT d.status FROM supply_link d WHERE "
        "d.pair_key = supply_link.pair_key AND d.status != 'candidate' LIMIT 1) "
        "WHERE status = 'candidate' AND EXISTS (SELECT 1 FROM supply_link d WHERE "
        "d.pair_key = supply_link.pair_key AND d.status != 'candidate')"
    ).rowcount


def decide(
    engine: sqlite3.Connection,
    payload: dict,
    action: str,
    by: str,
    now: datetime,
    core: set[str] = frozenset(),
) -> None:
    """confirm (claimed direction) / flip / reject every passage of the pair."""
    key = payload["pair"]
    rows = _rows(engine, key)
    if action == "reject":
        engine.execute(
            "UPDATE supply_link SET status = 'rejected', decided_at = ? WHERE pair_key = ?",
            (iso(now), key),
        )
        return
    sup = payload.get("supplier_side")
    if action == "flip":
        sup = payload.get("customer_side")
        if sup is None:  # not stated: the flip of "A supplies B" for the first row
            sup = _sides(rows[0])[1][0]
    supplier_cik = sup_name = None
    for r in rows:
        direction = None
        if sup is not None:
            a, b = _sides(r)
            direction = "a_to_b" if a[0] == sup else "b_to_a"
            sup_name = a[1] if direction == "a_to_b" else b[1]
            supplier_cik = r["a_cik"] if direction == "a_to_b" else r["b_cik"]
        engine.execute(
            "UPDATE supply_link SET status = 'confirmed', direction = coalesce(?, direction), "
            "decided_at = ? WHERE link_id = ?",
            (direction, iso(now), r["link_id"]),
        )
    if supplier_cik:
        _follow_up(engine, supplier_cik, sup_name or "", rows, by, now, core)


def _follow_up(
    engine: sqlite3.Connection, cik: str, name: str, rows, by: str, now: datetime, core
) -> None:
    """A confirmed supplier outside the watchlist → candidate; tracked → promotion."""
    from engine.themes import proposals, tiers

    r = rows[0]
    customer = r["b_name"] if r["a_cik"] == cik else r["a_name"]
    m = tiers.member(engine, cik)
    if m is not None and m.tier == "tracked":
        proposals.suggest_promotion(
            engine, cik, f"confirmed supplier of {customer}", "supply_link", now
        )
        return
    if m is not None or cik in core:
        return
    ticker = engine.execute(
        "SELECT ticker FROM ticker WHERE cik = ? AND valid_to IS NULL "
        "ORDER BY length(ticker) LIMIT 1",
        (cik,),
    ).fetchone()
    payload = {
        "ticker": ticker[0] if ticker else None,
        "name": name,
        "kind": "supplier",
        "why": f"confirmed supplier of {customer} (D-M02-7)",
        "money_flow": True,
        "companies": 1,
    }
    proposals.propose(
        engine,
        "m02_candidate",
        cik,
        f"{payload['ticker'] or name}: supplier of {customer}",
        payload,
        now,
        cik=cik,
    )


def company_links(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    """Every passage involving the company, confirmed first."""
    return engine.execute(
        "SELECT * FROM supply_link WHERE (a_cik = ? OR b_cik = ?) AND stale = 0 "
        "ORDER BY status = 'confirmed' DESC, status = 'rejected', rung, filed DESC",
        (cik, cik),
    ).fetchall()
