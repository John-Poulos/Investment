"""View model: "Financing and equity links" and "Credit quality and investment book" on
the company's Money flow tab (D-M02-43, D-M02-45; mock-up approved 2026-10-10).

Rows on both companies' pages. Structured holdings: the filer's latest 13F quarter (shares
compared with the quarter before), the latest 13D/13G per filer and issuer. Text links:
one row per pair and kind (strongest passage). The largest five holdings get their own
row; the rest are grouped. Labelled hypothesis, not scored.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date

from engine.financing import credit, links, thirteenf
from engine.financing.find import KIND_LABELS

OWN_ROWS = 5


@dataclass
class FinRow:
    other: str
    kind: str
    direction: str  # "NVIDIA → Intel"
    amount: float | None
    detail: str
    source: str
    status: str  # automatic | confirmed | to review
    flag: str | None = None
    holding_id: int | None = None
    quote: str | None = None
    accession: str | None = None
    filename: str | None = None
    quote_start: int | None = None
    other_cik: str | None = None


@dataclass
class Grouped:
    names: list[tuple[str, float | None]]
    source: str


@dataclass
class FinancingView:
    rows: list[FinRow] = field(default_factory=list)
    grouped: Grouped | None = None
    series: list[credit.Series] = field(default_factory=list)
    today: date | None = None
    loops: int = 0


def _name(engine: sqlite3.Connection, cik: str | None, fallback: str) -> str:
    if not cik:
        return fallback
    row = engine.execute(
        "SELECT ticker FROM ticker WHERE cik = ? AND valid_to IS NULL ORDER BY length(ticker), "
        "ticker LIMIT 1",
        (cik,),
    ).fetchone()
    return f"{fallback} ({row[0]})" if row else fallback


def _sec(engine: sqlite3.Connection, cik: str | None, stated: str) -> str:
    """The SEC company name when resolved; otherwise the name as the filing states it
    (13F names are often cut short: "SPACE EXPLORATION TECHN CORP")."""
    if cik:
        row = engine.execute("SELECT name FROM entity WHERE cik = ?", (cik,)).fetchone()
        if row is None:
            row = engine.execute(
                "SELECT name FROM ticker WHERE cik = ? AND name IS NOT NULL LIMIT 1", (cik,)
            ).fetchone()
        if row and row[0]:
            return row[0]
    return stated


def _arrow(engine: sqlite3.Connection, r: sqlite3.Row) -> str:
    """'NVIDIA CORP → INTEL CORP': who holds whom."""
    filer = _sec(engine, r["filer_cik"], r["filer_name"])
    return f"{filer} → {_sec(engine, r['issuer_cik'], r['issuer_name'])}"


def _holding_rows(engine: sqlite3.Connection, cik: str) -> list[tuple[FinRow, float]]:
    out: list[tuple[FinRow, float]] = []
    # this company as a 13F filer: its latest quarter, shares vs the quarter before
    periods = thirteenf.current(engine, cik)
    if periods:
        ordered = sorted(periods)
        latest = periods[ordered[-1]]
        prior = {r["cusip"]: r for r in periods[ordered[-2]]} if len(ordered) > 1 else {}
        for r in latest:
            if r["status"] != "automatic":
                continue
            p = prior.get(r["cusip"])
            change = (
                "new this quarter"
                if p is None and prior
                else "unchanged"
                if p and p["shares"] == r["shares"]
                else f"was {float(p['shares']):,.0f} sh"
                if p and p["shares"] is not None
                else ""
            )
            detail = (
                f"{float(r['shares']):,.0f} {r['share_type'] or ''} · {r['title']}"
                if r["shares"] is not None
                else r["title"]
            )
            row = FinRow(
                _name(engine, r["issuer_cik"], _sec(engine, r["issuer_cik"], r["issuer_name"])),
                "K1",
                _arrow(engine, r),
                float(r["value_usd"]) if r["value_usd"] is not None else None,
                detail + (f" · {change}" if change else ""),
                f"13F {r['period']} · A",
                "automatic",
                holding_id=r["holding_id"],
                other_cik=r["issuer_cik"],
            )
            out.append((row, float(r["value_usd"] or 0)))
    # other filers' 13F rows naming this company (their latest quarter only)
    for r in engine.execute(
        "SELECT h.* FROM fin_holding h WHERE h.source = '13F' AND h.issuer_cik = ? AND "
        "h.filer_cik != ? AND h.status = 'automatic' AND h.period = (SELECT max(period) FROM "
        "fin_13f f WHERE f.filer_cik = h.filer_cik AND f.status = 'read')",
        (cik, cik),
    ):
        row = FinRow(
            _name(engine, r["filer_cik"], _sec(engine, r["filer_cik"], r["filer_name"])),
            "K1",
            _arrow(engine, r),
            float(r["value_usd"]) if r["value_usd"] is not None else None,
            f"{float(r['shares'] or 0):,.0f} {r['share_type'] or ''} · {r['title']}",
            f"13F {r['period']} · A",
            "automatic",
            holding_id=r["holding_id"],
            other_cik=r["filer_cik"],
        )
        out.append((row, float(r["value_usd"] or 0)))
    # 13D/13G: latest schedule per filer and issuer, either side
    for r in engine.execute(
        "SELECT h.* FROM fin_holding h WHERE h.source IN ('13D', '13G') AND h.status = "
        "'automatic' AND (h.filer_cik = ? OR h.issuer_cik = ?) AND h.filed = (SELECT max(filed) "
        "FROM fin_holding x WHERE x.source IN ('13D', '13G') AND x.filer_cik = h.filer_cik AND "
        "x.issuer_cik IS h.issuer_cik)",
        (cik, cik),
    ):
        mine = r["filer_cik"] == cik
        other = _name(
            engine,
            r["issuer_cik"] if mine else r["filer_cik"],
            r["issuer_name"] if mine else r["filer_name"],
        )
        pct = f"{float(r['pct_class']):.1f}% of class" if r["pct_class"] is not None else ""
        sh = f"{float(r['shares']):,.0f} sh" if r["shares"] is not None else ""
        exited = r["shares"] == 0 or r["pct_class"] == 0  # an exit filing (D-M02-47)
        if exited:
            sh, pct = "stake sold (0% of class)", ""
        row = FinRow(
            other,
            "K1",
            _arrow(engine, r),
            None,
            " · ".join(x for x in (sh, pct) if x),
            f"Schedule {r['source']} {r['period']} · A",
            "exited" if exited else "automatic",
            holding_id=r["holding_id"],
            other_cik=r["issuer_cik"] if mine else r["filer_cik"],
        )
        # 5%+ stakes always get their own row; exits sort last
        out.append((row, -1.0 if exited else float("inf")))
    return out


def _text_rows(engine: sqlite3.Connection, cik: str) -> list[FinRow]:
    best: dict[tuple[str, str], sqlite3.Row] = {}
    for r in engine.execute(
        "SELECT * FROM fin_text WHERE (a_cik = ? OR b_cik = ?) AND status != 'rejected' "
        "ORDER BY status = 'confirmed' DESC, amount_usd IS NULL, filed DESC",
        (cik, cik),
    ):
        best.setdefault((r["pair_key"], r["kind"]), r)
    out = []
    for r in best.values():
        me_a = r["a_cik"] == cik
        other = _name(
            engine, r["b_cik"] if me_a else r["a_cik"], r["b_name"] if me_a else r["a_name"]
        )
        if r["direction"] == "a_to_b":
            d = f"{r['a_name']} → {r['b_name']}"
        elif r["direction"] == "b_to_a":
            d = f"{r['b_name']} → {r['a_name']}"
        else:
            d = "direction not stated"
        out.append(
            FinRow(
                other,
                r["kind"],
                d,
                float(r["amount_usd"]) if r["amount_usd"] is not None else None,
                r["instrument"] or "",
                f"{r['form'] or 'text'} {r['filed'] or ''} · A",
                "confirmed" if r["status"] == "confirmed" else "to review",
                quote=r["quote"],
                accession=r["accession"],
                filename=r["filename"],
                quote_start=r["quote_start"],
                other_cik=r["b_cik"] if me_a else r["a_cik"],
            )
        )
    return out


def company_view(engine: sqlite3.Connection, cik: str, today: date) -> FinancingView:
    v = FinancingView(today=today)
    holdings = _holding_rows(engine, cik)
    holdings.sort(key=lambda x: -x[1])
    own = [r for r, _ in holdings[:OWN_ROWS]]
    rest = holdings[OWN_ROWS:]
    if len(rest) == 1:
        own.append(rest[0][0])
    elif rest:
        v.grouped = Grouped(
            [(r.other, r.amount) for r, _ in rest],
            ", ".join(sorted({r.source.split(" · ")[0] for r, _ in rest})),
        )
    v.rows = own + _text_rows(engine, cik)
    flags = {}
    for lp in links.loops(engine):
        if cik in (lp.edge.financer, lp.edge.other):
            flags.setdefault((lp.edge.financer, lp.edge.other, lp.edge.kind), lp)
    for row in v.rows:
        for (a, b, kind), lp in flags.items():
            if row.kind == kind and row.other_cik and {a, b} == {cik, row.other_cik}:
                share = f"; supply link share {lp.share_pct:g}% of revenue" if lp.share_pct else ""
                row.flag = lp.text + share
    v.loops = sum(1 for lp in flags.values() if lp.flagged)
    v.series = credit.company_series(engine, cik)
    return v


__all__ = ["KIND_LABELS", "FinancingView", "company_view"]
