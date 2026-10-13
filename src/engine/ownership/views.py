"""Insiders tab (M07 Part 1, D-UI-32) and the Overview line, built from stored rows.

Per-form cards come from the stored Form 4 rows (rule 6), not from `signal`; the net-flow
strip is computed live for today with the same function the pass writes; the short-interest
line reads "missing" until a source is chosen (D-M07-8, DS18).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from engine.ownership import classes as cls_mod
from engine.ownership import rows as rows_mod
from engine.ownership.cards import Card, Market, build_cards
from engine.ownership.step import WINDOWS, NetFlow, money, net_flow, pct, shares_txt
from engine.sec.insiders import coverage_start
from engine.signals import latest_signal

SHORT_INTEREST_LINE = "missing: no short-interest source (D-M07-8; DATA_SOURCES DS18)"
CARD_LIMIT = 40


@dataclass
class CardView:
    accession: str
    filed: str
    doc_type: str
    kind: str  # buy | sale | issuer
    owner: str
    role: str
    class_text: str  # class this year with years used
    class_reason: str
    plan: str  # sale: statuses; buy: "—"
    plan_basis: str
    usd: str
    shares: str
    avg_price: str
    stake: str
    stake_note: str
    cover: str
    float_: str
    adv: str
    not_in_total: list[str] = field(default_factory=list)
    warning: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class InsiderView:
    cards: list[CardView]
    net: list[NetFlow]
    history_start: str | None
    classes: list[dict[str, Any]]
    txns: list[dict[str, Any]]
    short_interest: str = SHORT_INTEREST_LINE
    more_cards: int = 0


def _class_text(c: Card, owner: str | None) -> tuple[str, str]:
    v = c.classes.get(owner or "")
    if v is None:
        return "unclassified", "owner CIK missing" if not owner else "no class computed"
    return f"{v.cls} ({v.years[0]}–{v.years[2]})", v.reason


def _card_views(c: Card, market: Market) -> list[CardView]:
    out = []
    common = dict(accession=c.accession, filed=c.filed, doc_type=c.doc_type,
                  owner=c.owner_name or c.owner_cik or "—", role=c.role or "")  # fmt: skip
    cls_text, cls_reason = _class_text(c, c.owner_cik)
    notes = []
    if c.replaced:
        notes.append(
            f"{len(c.replaced)} row(s) replaced by a later Form 4/A "
            f"({', '.join(sorted({r.replaced_by or '' for r in c.replaced}))})"
        )
    if any(r.restates for r in c.rows):
        notes.append("Form 4/A: replaces the original's rows (owner, date, shares); counts on "
                     "the original's filing day")  # fmt: skip
    others = [f"{r.code} {shares_txt(r.shares)} sh × {r.price if r.price is not None else 'n/a'}"
              f" = {money(r.usd)} (not in total)" for r in c.others]  # fmt: skip
    if c.buys:
        sh = c.buy_shares
        out.append(CardView(
            **common, kind="buy", class_text=cls_text, class_reason=cls_reason, plan="—",
            plan_basis=", ".join(sorted({r.plan_basis or "not disclosed" for r in c.buys})),
            usd=money(c.buy_usd), shares=shares_txt(sh),
            avg_price=f"{c.buy_usd / sh:,.2f}" if c.buy_usd and sh else "n/a",
            stake=f"{pct(c.pct_stake_after_buy())} of stake after ({shares_txt(c.stake_after)})",
            stake_note=c.stake_note,
            cover=_m(c.cover, c.scaled(sh, market), 4),
            float_="—", adv="—", not_in_total=others, notes=list(notes),
        ))  # fmt: skip
    if c.issuer_buys:
        sh = sum(r.shares or 0 for r in c.issuer_buys)
        out.append(CardView(
            **common, kind="issuer", class_text="purchase_from_issuer",
            class_reason="bought from the issuer (code "
            + "/".join(sorted({r.code or '?' for r in c.issuer_buys}))
            + "): shown, not scored, not in net flow",
            plan="—", plan_basis="; ".join(sorted({" ".join(r.footnotes.values())[:200]
                                                   for r in c.issuer_buys})),
            usd=money(c.issuer_usd), shares=shares_txt(sh),
            avg_price=f"{c.issuer_usd / sh:,.2f}" if c.issuer_usd and sh else "n/a",
            stake=f"{pct(sh / c.stake_after * 100 if c.stake_after else None)} of stake after "
                  f"({shares_txt(c.stake_after)})",
            stake_note=c.stake_note, cover=_m(c.cover, c.scaled(sh, market), 4),
            float_="—", adv="—", notes=list(notes),
        ))  # fmt: skip
    if c.sales:
        sh = c.sale_shares
        statuses = sorted({c.sale_status(r) for r in c.sales})
        out.append(CardView(
            **common, kind="sale", class_text=cls_text, class_reason=cls_reason,
            plan=", ".join(statuses),
            plan_basis=", ".join(sorted({r.plan_basis or "not disclosed" for r in c.sales})),
            usd=money(c.sale_usd), shares=shares_txt(sh),
            avg_price=f"{c.sale_usd / sh:,.2f}" if c.sale_usd and sh else "n/a",
            stake=f"{pct(c.pct_stake_before_sale())} of stake before "
                  f"({shares_txt(c.stake_before_sale)})",
            stake_note=c.stake_note,
            cover=_m(c.cover, c.scaled(sh, market), 4),
            float_=_m(c.float_, c.scaled(sh, market), 4),
            adv=_m(c.adv, sh, 2),
            not_in_total=others, warning=c.warning(), notes=list(notes),
        ))  # fmt: skip
    return out


def _m(measure, shares: float | None, digits: int) -> str:
    if measure is None:
        return "—"
    if measure.value is None:
        return measure.text
    return f"{pct(measure.pct(shares), digits)} of {measure.text}"


def company_view(engine: sqlite3.Connection, cik: str, today: date) -> InsiderView:
    issuer = rows_mod.load(engine, cik)
    start = coverage_start(engine, cik)
    verdicts = cls_mod.compute(issuer, start, today.year)
    market = Market(engine, cik)
    cards = build_cards(issuer, verdicts, None)
    views: list[CardView] = []
    shown = cards[:CARD_LIMIT]
    for c in shown:
        day = c.last_trade
        c.cover = market.cover(day)
        if c.sales:
            c.float_ = market.float_(day)
            c.adv = market.adv(day)
        views += _card_views(c, market)
    latest = engine.execute(
        "SELECT accession, filed FROM form4_doc WHERE issuer_cik = ? ORDER BY filed DESC LIMIT 1",
        (cik,),
    ).fetchone()
    from engine.signals import Source

    src = Source(latest["accession"], latest["filed"], "A", "latest Form 4") if latest else None
    net = [net_flow(issuer, tf, today, start, market, src) for tf, _ in WINDOWS]
    owners: dict[str, str] = {}
    for r in issuer.rows:
        if r.owner_cik:
            owners.setdefault(r.owner_cik, r.owner_name or r.owner_cik)
    classes = [
        {"owner": owners.get(v.owner_cik, v.owner_cik), "year": v.year, "class": v.cls,
         "years": f"{v.years[0]}–{v.years[2]}", "reason": v.reason,
         "months": "; ".join(f"{y}: {', '.join(f'{m:02d}' for m in ms) or '—'}"
                             for y, ms in v.months.items())}
        for v in sorted(verdicts.values(), key=lambda x: (x.year, x.owner_cik), reverse=True)
        if v.year == today.year
    ]  # fmt: skip
    txns = []
    for r in sorted(issuer.rows, key=lambda x: (x.txn_date or "", x.accession, -x.line),
                    reverse=True)[:150]:  # fmt: skip
        v = cls_mod.class_of(verdicts, r.owner_cik, r.txn_date)
        kind = r.kind
        txns.append({
            "txn_date": r.txn_date, "owner_name": r.owner_name, "role": r.role,
            "code": r.code, "acquired_disposed": r.acquired_disposed,
            "table_kind": r.table_kind, "security_title": r.title, "shares": r.shares,
            "price": r.price, "shares_after": r.shares_after, "is_10b5_1": r.is_10b5_1,
            "accession": r.accession, "replaced_by": r.replaced_by,
            "class": ("purchase_from_issuer" if kind == "issuer_buy"
                      else (v.cls if v else "unclassified") if kind in ("buy", "sale")
                      else "not in total"),
            "plan": r.plan or ("—" if kind != "sale" else ""),
            "plan_basis": r.plan_basis or "not disclosed",
        })  # fmt: skip
    return InsiderView(views, net, start, classes, txns, more_cards=max(0, len(cards) - CARD_LIMIT))


def overview_row(engine: sqlite3.Connection, cik: str) -> dict[str, Any] | None:
    """The Overview's M07 line: the latest insider_buy and today's MY net flow."""
    buy = latest_signal(engine, cik, "M07", "insider_buy", "MY")
    net = latest_signal(engine, cik, "M07", "insider_net_flow", "MY")
    if buy is None and net is None:
        return None
    return {
        "buy": None if buy is None else {
            "as_of": buy["as_of"], "text": buy["value_text"],
            "usd": money(float(buy["value"])) if buy["value"] is not None else "n/a"},
        "net": None if net is None else {
            "as_of": net["as_of"], "text": net["value_text"],
            "usd": money(float(net["value"])) if net["value"] is not None else "—",
            "missing": net["method"] if net["value_text"] is None else None},
    }  # fmt: skip
