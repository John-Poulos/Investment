"""Financing links: text passages → owner review; holdings → stored records; loop flags.

Text passages (`fin_text`) work like supply links (part 5): one `m02_finlink` item per
company pair and kind; confirm / flip / reject (the confirm form may change the kind)
apply to every passage of that pair and kind, and later passages follow the decision.
Structured holdings (13F, 13D/13G) are stored automatically (D-M02-42); each record has
a "wrong?" button that removes it and keeps it out of later runs.

Loop flag (D-M02-43), confirmed supply links and stored/confirmed financing only:
1 A invests in B and A supplies B · 2 A backstops B's revenue and A supplies B ·
3 A grants equity to customer B (K2) · 4 A finances customer B (K4). A customer funding
its supplier is shown ("supply financing"), not flagged. Indirect loops are not traced.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from engine.financing import thirteenf
from engine.financing.find import KIND_LABELS, FinFound
from engine.sec.client import iso
from engine.supply.aliases import Company
from engine.supply.links import Doc, pair_key, side

SAMPLES = 3
LOOP_CASES = {
    1: "invests in a customer it supplies",
    2: "backstops the revenue of a customer it supplies",
    3: "grants equity to a customer",
    4: "finances a customer",
}


def registry_name(engine: sqlite3.Connection, cik: str | None) -> str | None:
    """The SEC company name for a CIK (stored entity, else the ticker list): "Amazon.com,
    Inc." rather than the longest alias, "Amazon Web Services" (live check 1)."""
    if not cik:
        return None
    row = engine.execute("SELECT name FROM entity WHERE cik = ?", (cik,)).fetchone()
    if row is None:
        row = engine.execute(
            "SELECT name FROM ticker WHERE cik = ? AND name IS NOT NULL LIMIT 1", (cik,)
        ).fetchone()
    return row[0] if row and row[0] else None


def store(
    engine: sqlite3.Connection,
    a_cik: str | None,
    a_name: str,
    a_company: Company | None,
    doc: Doc,
    found: list[FinFound],
    now: datetime,
) -> int:
    n = 0
    a_side = side(a_cik, a_company, a_name)
    a_name = registry_name(engine, a_cik) or a_name
    for f in found:
        b_side = side(f.b.cik, f.b, f.b_name)
        b_name = registry_name(engine, f.b.cik) or f.b.name
        if b_side == a_side:
            continue
        existing = engine.execute(
            "SELECT text_id FROM fin_text WHERE accession = ? AND filename = ? "
            "AND quote_start = ? AND b_side = ?",
            (doc.accession, doc.filename, f.start, b_side),
        ).fetchone()
        amount = str(f.amount) if f.amount is not None else None
        if existing is not None:
            engine.execute(
                "UPDATE fin_text SET seen_at = ?, how = ?, kind = CASE WHEN status = "
                "'candidate' THEN ? ELSE kind END, direction = CASE WHEN status = 'candidate' "
                "THEN ? ELSE direction END, amount_usd = ?, instrument = ?, a_name = ?, "
                "b_name = ? WHERE text_id = ?",
                (
                    iso(now),
                    f.how,
                    f.kind,
                    f.direction,
                    amount,
                    f.instrument,
                    a_name,
                    b_name,
                    existing[0],
                ),
            )
            continue
        cur = engine.execute(
            "INSERT OR IGNORE INTO fin_text (kind, a_cik, a_name, b_cik, b_name, direction, "
            "amount_usd, instrument, accession, filename, form, filed, quote, quote_start, "
            "quote_end, how, a_side, b_side, pair_key, discovered_at, seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f.kind,
                a_cik,
                a_name,
                f.b.cik,
                b_name,
                f.direction,
                amount,
                f.instrument,
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
    """After a full re-read: undecided passages the rules no longer produce are removed."""
    n = engine.execute(
        "DELETE FROM fin_text WHERE status = 'candidate' AND (seen_at IS NULL OR seen_at < ?)",
        (iso(since),),
    ).rowcount
    engine.execute(
        "DELETE FROM m02_proposal WHERE kind = 'm02_finlink' AND status = 'overflow' AND "
        "substr(prop_key, 13) NOT IN (SELECT pair_key || ':' || kind FROM fin_text)"
    )
    return n


def follow_decisions(engine: sqlite3.Connection) -> int:
    return engine.execute(
        "UPDATE fin_text SET status = (SELECT d.status FROM fin_text d WHERE d.pair_key = "
        "fin_text.pair_key AND d.kind = fin_text.kind AND d.status != 'candidate' LIMIT 1), "
        "direction = coalesce((SELECT CASE WHEN d.a_side = fin_text.a_side THEN d.direction "
        "WHEN d.direction = 'a_to_b' THEN 'b_to_a' WHEN d.direction = 'b_to_a' THEN 'a_to_b' "
        "END FROM fin_text d WHERE d.pair_key = fin_text.pair_key AND d.kind = fin_text.kind "
        "AND d.status = 'confirmed' LIMIT 1), direction) "
        "WHERE status = 'candidate' AND EXISTS (SELECT 1 FROM fin_text d WHERE "
        "d.pair_key = fin_text.pair_key AND d.kind = fin_text.kind AND d.status != 'candidate')"
    ).rowcount


def _rows(engine: sqlite3.Connection, key: str, kind: str) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT * FROM fin_text WHERE pair_key = ? AND kind = ? ORDER BY filed DESC, text_id",
        (key, kind),
    ).fetchall()


def claimed(rows: list[sqlite3.Row]) -> tuple[str, str, str, str] | None:
    """(financer side, name, other side, name) from the first row stating a direction."""
    for r in rows:
        if r["direction"] == "a_to_b":
            return r["a_side"], r["a_name"], r["b_side"], r["b_name"]
        if r["direction"] == "b_to_a":
            return r["b_side"], r["b_name"], r["a_side"], r["a_name"]
    return None


def claim_text(kind: str, c: tuple[str, str, str, str] | None) -> str:
    if c is None:
        return f"{KIND_LABELS[kind]}, direction not stated"
    verb = {
        "K1": "invests in",
        "K2": "grants equity to",
        "K3": "backstops the revenue of",
        "K4": "finances or guarantees",
        "K6": "holds a joint-venture / equity-method stake in",
    }[kind]
    return f"{c[1]} {verb} {c[3]}"


def propose_pairs(engine: sqlite3.Connection, now: datetime) -> dict[str, int]:
    from engine.moneyflow.views import dollars
    from engine.themes.proposals import propose

    keys = engine.execute(
        "SELECT pair_key, kind FROM fin_text GROUP BY pair_key, kind "
        "HAVING sum(status != 'candidate') = 0 ORDER BY max(amount_usd IS NOT NULL) DESC, "
        "pair_key, kind"
    ).fetchall()
    counts: dict[str, int] = {}
    for key, kind in keys:
        rows = _rows(engine, key, kind)
        c = claimed(rows)
        first = rows[0]
        names = sorted({first["a_name"], first["b_name"]})
        amount = next((float(r["amount_usd"]) for r in rows if r["amount_usd"] is not None), None)
        claim = claim_text(kind, c)
        if c is None:
            # no stated direction: Confirm reads the filer as the financer, the flip the
            # other company — both spelled out, so either answer stores a direction
            # (live check 2: CoreWeave's NVIDIA order form, D-M02-48)
            c = (first["a_side"], first["a_name"], first["b_side"], first["b_name"])
            claim += (
                f" — Confirm = {claim_text(kind, c)}; flipped = "
                f"{claim_text(kind, (c[2], c[3], c[0], c[1]))}"
            )
        payload = {
            "pair": key,
            "kind": kind,
            "kind_label": KIND_LABELS[kind],
            "companies": 2,
            "financer_side": c[0] if c else None,
            "financer_claimed": c[1] if c else None,
            "other_side": c[2] if c else None,
            "other_claimed": c[3] if c else None,
            "claim": claim,
            "amount": dollars(amount) if amount is not None else "not stated",
            "instrument": next((r["instrument"] for r in rows if r["instrument"]), None),
            "passages": len(rows),
            "samples": [
                f"{r['quote']} [{r['a_name']} {r['form'] or ''} {r['filed'] or ''}]"
                for r in rows[:SAMPLES]
            ],
            "accession": first["accession"],
            "filename": first["filename"],
            "offsets": [first["quote_start"], first["quote_end"]],
            "money_flow": amount is not None,
            "why": f"{names[0]} – {names[1]}: {claim}",
        }
        res = propose(
            engine,
            "m02_finlink",
            f"{key}:{kind}",
            f"Financing: {claim}",
            payload,
            now,
            cik=first["a_cik"] or first["b_cik"],
        )
        counts[res] = counts.get(res, 0) + 1
    return counts


def decide(
    engine: sqlite3.Connection, payload: dict, action: str, now: datetime, kind: str | None = None
) -> None:
    """confirm (claimed direction) / flip / reject every passage of the pair and kind; the
    owner may change the kind when confirming (K1–K4, K6)."""
    key, old = payload["pair"], payload["kind"]
    rows = _rows(engine, key, old)
    new = kind if kind in KIND_LABELS else old
    if action == "reject":
        engine.execute(
            "UPDATE fin_text SET status = 'rejected', decided_at = ? WHERE pair_key = ? "
            "AND kind = ?",
            (iso(now), key, old),
        )
        return
    fin = payload.get("financer_side")
    if action == "flip":
        fin = payload.get("other_side") or (rows[0]["b_side"] if rows else None)
    for r in rows:
        direction = None
        if fin is not None:
            direction = "a_to_b" if r["a_side"] == fin else "b_to_a"
        engine.execute(
            "UPDATE fin_text SET status = 'confirmed', kind = ?, direction = coalesce(?, "
            "direction), decided_at = ? WHERE text_id = ?",
            (new, direction, iso(now), r["text_id"]),
        )


def wrong_holding(engine: sqlite3.Connection, holding_id: int, by: str, now: datetime) -> None:
    """'wrong?' on a 13F/13D/13G record: removed now and kept out of later runs."""
    r = engine.execute("SELECT * FROM fin_holding WHERE holding_id = ?", (holding_id,)).fetchone()
    if r is None:
        return
    key = f"{r['source']}:{r['filer_cik']}:{r['cusip'][:6]}"
    engine.execute(
        "INSERT OR IGNORE INTO fin_suppress (key, reason, by_owner, at) VALUES (?, ?, ?, ?)",
        (key, f"wrong? on {r['issuer_name']} ({r['source']} {r['accession']})", by, iso(now)),
    )
    engine.execute(
        "UPDATE fin_holding SET status = 'wrong' WHERE source = ? AND filer_cik = ? AND "
        "substr(cusip, 1, 6) = ?",
        (r["source"], r["filer_cik"], r["cusip"][:6]),
    )


def undo_wrong(engine: sqlite3.Connection, key: str) -> None:
    source, filer, cusip6 = key.split(":", 2)
    engine.execute("DELETE FROM fin_suppress WHERE key = ?", (key,))
    engine.execute(
        "UPDATE fin_holding SET status = CASE WHEN issuer_cik IS NULL THEN 'unresolved' "
        "WHEN check_note IS NOT NULL THEN 'held' ELSE 'automatic' END WHERE source = ? AND "
        "filer_cik = ? AND substr(cusip, 1, 6) = ? AND status = 'wrong'",
        (source, filer, cusip6),
    )


# --- Edges and loops ------------------------------------------------------------------


@dataclass(frozen=True)
class Edge:
    kind: str
    financer: str  # cik
    other: str  # cik
    amount: float | None
    label: str
    source: str


def financing_edges(engine: sqlite3.Connection) -> list[Edge]:
    """Stored holdings (latest per filer and issuer) and confirmed text links with a stated
    direction, both sides resolved to a CIK."""
    out: list[Edge] = []
    for r in engine.execute(
        "SELECT h.* FROM fin_holding h WHERE h.status = 'automatic' AND h.issuer_cik IS NOT NULL "
        "AND h.period = (SELECT max(period) FROM fin_holding x WHERE x.source = h.source AND "
        "x.filer_cik = h.filer_cik AND x.issuer_cik = h.issuer_cik AND x.status = 'automatic') "
        "AND coalesce(h.shares, 1) != 0 AND coalesce(h.pct_class, 1) != 0 AND "
        + thirteenf.not_followed("h.filer_cik")
    ):  # a 0% schedule reports an exit: no stake (D-M02-47); followed managers are M07's
        # (D-M02-63)
        out.append(
            Edge(
                "K1",
                r["filer_cik"],
                r["issuer_cik"],
                float(r["value_usd"]) if r["value_usd"] is not None else None,
                f"{r['source']} {r['period']}",
                r["source"],
            )
        )
    for r in engine.execute(
        "SELECT * FROM fin_text WHERE status = 'confirmed' AND direction IS NOT NULL AND "
        "a_cik IS NOT NULL AND b_cik IS NOT NULL"
    ):
        a, b = (r["a_cik"], r["b_cik"]) if r["direction"] == "a_to_b" else (r["b_cik"], r["a_cik"])
        out.append(
            Edge(
                r["kind"],
                a,
                b,
                float(r["amount_usd"]) if r["amount_usd"] is not None else None,
                f"{r['form'] or ''} {r['filed'] or ''}".strip(),
                "text",
            )
        )
    return out


def supply_edges(engine: sqlite3.Connection) -> dict[tuple[str, str], float | None]:
    """{(supplier cik, customer cik): revenue share % if stated} from confirmed supply links."""
    out: dict[tuple[str, str], float | None] = {}
    for r in engine.execute(
        "SELECT a_cik, b_cik, direction, share_pct FROM supply_link WHERE status = 'confirmed' "
        "AND direction IS NOT NULL AND a_cik IS NOT NULL AND b_cik IS NOT NULL AND stale = 0"
    ):
        pair = (r["a_cik"], r["b_cik"]) if r["direction"] == "a_to_b" else (r["b_cik"], r["a_cik"])
        share = float(r["share_pct"]) if r["share_pct"] is not None else None
        if out.get(pair) is None:
            out[pair] = share
    return out


@dataclass(frozen=True)
class Loop:
    case: int  # 1–4 flagged; 5 = customer funds supplier (shown, not flagged)
    edge: Edge
    share_pct: float | None  # the supply link's revenue share, if stated

    @property
    def flagged(self) -> bool:
        return self.case != 5

    @property
    def text(self) -> str:
        if self.case == 5:
            return "supply financing: a customer funds its supplier (not flagged)"
        return f"loop {self.case}: {LOOP_CASES[self.case]}"


def loops(engine: sqlite3.Connection) -> list[Loop]:
    supply = supply_edges(engine)
    out = []
    for e in financing_edges(engine):
        pair = (e.financer, e.other)
        if e.kind == "K2":
            out.append(Loop(3, e, supply.get(pair)))
        elif e.kind == "K4":
            out.append(Loop(4, e, supply.get(pair)))
        elif e.kind in ("K1", "K3") and pair in supply:
            out.append(Loop(1 if e.kind == "K1" else 2, e, supply[pair]))
        elif e.kind == "K1" and (e.other, e.financer) in supply:
            out.append(Loop(5, e, supply[(e.other, e.financer)]))
    return out


def wrong_list(engine: sqlite3.Connection) -> list[sqlite3.Row]:
    """Records marked wrong, newest first (Runs page, with undo)."""
    return engine.execute("SELECT * FROM fin_suppress ORDER BY at DESC").fetchall()
