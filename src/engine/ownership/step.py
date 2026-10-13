"""M07 Part 1 local pass: 4/A links, CMP classes and the three insider signals (0 SEC requests).

Runs in the refresh after the M04 local steps (MVP_PLAN refresh order) and from
`scripts/run_ownership.py insiders`. Per company (core and promoted; the tracked tier stores
no Form 4s, D-M02-4):

- classes and the per-day `insider_buy` / `insider_sale` rows are recomputed only when a
  Form 4 was parsed since the last pass, the calendar year changed (CMP's 1 January reset)
  or the pass is forced (per-new-filing work);
- `insider_net_flow` is written every pass, one row per timeframe with as_of = the run's
  market date, because its window rolls with the calendar.

Signal rules (M07_OWNERSHIP.md "Signals out", D-M07-2, -3, -5; D-M04-9, -74):
- one row per company and filing day (rule 6): value = summed $, value_text = the
  strongest class present; per-form detail goes in `method` and the Insiders tab;
- `insider_buy` votes only in MY and only when opportunistic (+1, D-M07-2); routine,
  unclassified and purchase_from_issuer rows are info; PT and ST are info until M01
  designs those columns;
- `insider_sale` is a MY warning for non-plan opportunistic sales and for non-plan
  unclassified sales of ≥ 10%† of stake (D-M07-3); otherwise info;
- `insider_net_flow` is info everywhere (D-M07-5).
Alerts (M01 rule 6): an opportunistic or unclassified open-market buy alerts once per company
and filing day, in the end-of-run box; a company's first pass is a baseline (LESSONS).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from engine.ownership import classes as cls_mod
from engine.ownership import rows as rows_mod
from engine.ownership.cards import Card, Market, build_cards
from engine.ownership.rows import Issuer, Row
from engine.sec.client import iso
from engine.sec.insiders import coverage_start
from engine.signals import Source, write_signal

MODULE = "M07"
BUY_ORDER = ("opportunistic", "unclassified", "routine", "purchase_from_issuer")
SALE_ORDER = ("non_plan_opportunistic", "non_plan_unclassified", "non_plan_routine", "plan_na",
              "plan")  # fmt: skip
ALERT_CLASSES = ("opportunistic", "unclassified")
CLUSTER_DAYS = 90  # MY cluster window
CLUSTER_MIN = 3  # † distinct opportunistic buyers
WINDOWS = (("MY", "12 months"), ("PT", "3 months"), ("ST", "30 days"))
NET_TEXTS = ("net_buy", "net_sell", "plan_only", "none")


def window_start(end: date, tf: str) -> date:
    if tf == "ST":
        return end - timedelta(days=30)
    months = 12 if tf == "MY" else 3
    y, m = divmod(end.month - 1 - months, 12)
    year, month = end.year + y, m + 1
    for day in (end.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise AssertionError("unreachable")


def money(v: float | None) -> str:
    if v is None:
        return "n/a"
    sign, a = ("−" if v < 0 else ""), abs(v)
    if a >= 1e9:
        return f"{sign}${a / 1e9:,.2f}B"
    if a >= 1e6:
        return f"{sign}${a / 1e6:,.2f}M"
    return f"{sign}${a:,.0f}"


def pct(v: float | None, digits: int = 3) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}%"


def shares_txt(v: float | None) -> str:
    return "n/a" if v is None else f"{v:,.0f}"


# --- per-day signals ---------------------------------------------------------------------


@dataclass
class DayRow:
    signal: str
    day: str
    text: str
    value: float | None
    method: str
    sources: list[Source]
    info: tuple[str, ...]
    alert: str | None = None  # alert line for an opportunistic / unclassified buy


def _sources(rows: Iterable[Row]) -> list[Source]:
    seen: dict[str, Source] = {}
    for r in rows:
        seen.setdefault(r.accession, Source(r.accession, r.filed, "A", f"Form {r.doc_type}"))
        if r.restates:
            seen.setdefault(r.restates, Source(r.restates, r.day, "A", "replaced by Form 4/A"))
    return list(seen.values())


def _forms(rows: Iterable[Row]) -> list[str]:
    """Accessions of the day's rows, with the originals that 4/A rows replaced."""
    out: list[str] = []
    for r in rows:
        out.append(r.accession)
        if r.restates:
            out.append(r.restates)
    return list(dict.fromkeys(out))


def _buy_class(r: Row, verdicts) -> str:
    if r.kind == "issuer_buy":
        return "purchase_from_issuer"
    v = cls_mod.class_of(verdicts, r.owner_cik, r.txn_date)
    return v.cls if v else "unclassified"


def _cluster(eff: list[Row], verdicts, day: str) -> int:
    lo = (date.fromisoformat(day) - timedelta(days=CLUSTER_DAYS)).isoformat()
    return len({r.owner_cik for r in eff if r.kind == "buy" and r.owner_cik
                and lo < r.day <= day and _buy_class(r, verdicts) == "opportunistic"})  # fmt: skip


def buy_days(ticker: str, issuer: Issuer, cards: dict[str, Card], verdicts, market: Market | None,
             ) -> list[DayRow]:  # fmt: skip
    eff = issuer.effective()
    days: dict[str, list[Row]] = {}
    for r in eff:
        if r.kind in ("buy", "issuer_buy"):
            days.setdefault(r.day, []).append(r)
    out = []
    for day, rows in sorted(days.items()):
        open_rows = [r for r in rows if r.kind == "buy"]
        present = {_buy_class(r, verdicts) for r in rows}
        text = next(c for c in BUY_ORDER if c in present)
        usd = [r.usd for r in open_rows if r.usd is not None]
        value = sum(usd) if usd else None
        parts = []
        if open_rows:
            sh = sum(r.shares or 0 for r in open_rows)
            parts.append(
                f"open-market P: {len(open_rows)} row(s), {shares_txt(sh)} shares, "
                f"{money(value)}"
                + (
                    f" ({len(open_rows) - len(usd)} without a price, not in $)"
                    if len(usd) < len(open_rows)
                    else ""
                )
            )
        buyers: dict[str, str] = {}
        for r in rows:
            v = cls_mod.class_of(verdicts, r.owner_cik, r.txn_date)
            label = _buy_class(r, verdicts)
            why = f"; {v.reason}" if v and r.kind == "buy" else ""
            buyers.setdefault(f"{r.owner_name or r.owner_cik or 'owner n/a'}",
                              f"{label}{why}")  # fmt: skip
        parts.append("buyers: " + "; ".join(f"{k} = {v}" for k, v in buyers.items()))
        for acc in _forms(rows):
            c = cards.get(acc)
            if c is None:
                continue
            bits = [f"{acc}"]
            if c.buys:
                bits.append(f"{pct(c.pct_stake_after_buy())} of stake after "
                            f"({shares_txt(c.stake_after)}; {c.stake_note})")  # fmt: skip
                if market is not None and c.cover is not None:
                    bits.append(f"{pct(c.cover.pct(c.scaled(c.buy_shares, market)))} of cover "
                                f"count {c.cover.text}")  # fmt: skip
            if c.issuer_buys:
                ish = sum(r.shares or 0 for r in c.issuer_buys)
                bits.append(f"purchase from issuer {shares_txt(ish)} shares {money(c.issuer_usd)} "
                            "(not open market: shown, not scored, not in net flow)")  # fmt: skip
            bits += [f"plan basis: {r.plan_basis or 'not disclosed'}" for r in c.buys[:1]]
            if c.replaced or any(r.restates for r in c.buys):
                bits.append("4/A replaces the original rows (matched on owner, date, shares)")
            parts.append("form " + ", ".join(bits))
        n = _cluster(eff, verdicts, day)
        parts.append(f"cluster: {n} distinct opportunistic buyer(s) in {CLUSTER_DAYS} days to {day}"
                     + (f" (≥ {CLUSTER_MIN}: cluster)" if n >= CLUSTER_MIN else ""))  # fmt: skip
        vote = text == "opportunistic"
        parts.append("vote: opportunistic +1 in MY (D-M07-2)" if vote else
                     "no vote (D-M07-2: only opportunistic buys vote)")  # fmt: skip
        alert = None
        if present & set(ALERT_CLASSES) and open_rows:
            who = ", ".join(dict.fromkeys(r.owner_name or r.owner_cik or "?" for r in open_rows))
            alert = (
                f"{ticker} {day}: insider buy {money(value)} by {who} "
                f"({'/'.join(c for c in BUY_ORDER if c in present)})"
            )
            parts.append("alert (M01 rule 6)")
        out.append(DayRow("insider_buy", day, text, value, "; ".join(parts), _sources(rows),
                          ("PT", "ST") if vote else ("MY", "PT", "ST"), alert))  # fmt: skip
    return out


def sale_days(issuer: Issuer, cards: dict[str, Card], market: Market | None) -> list[DayRow]:
    eff = issuer.effective()
    days: dict[str, list[Row]] = {}
    for r in eff:
        if r.kind == "sale":
            days.setdefault(r.day, []).append(r)
    out = []
    for day, rows in sorted(days.items()):
        statuses = {cards[r.accession].sale_status(r) for r in rows if r.accession in cards}
        text = next((c for c in SALE_ORDER if c in statuses), "non_plan_unclassified")
        usd = [r.usd for r in rows if r.usd is not None]
        value = sum(usd) if usd else None
        sh = sum(r.shares or 0 for r in rows)
        parts = [f"S rows: {len(rows)}, {shares_txt(sh)} shares, {money(value)}"
                 + (f" ({len(rows) - len(usd)} without a price, not in $)"
                    if len(usd) < len(rows) else "")]  # fmt: skip
        warnings = []
        for acc in _forms(rows):
            c = cards.get(acc)
            if c is None:
                continue
            if not c.sales:  # an original whose rows a 4/A replaced
                by = ", ".join(sorted({r.replaced_by or "" for r in c.replaced}))
                bits = [f"{acc}: S rows replaced by Form 4/A {by}"]
                if c.others:
                    bits.append(
                        "not in total: "
                        + "; ".join(
                            f"{r.code} {shares_txt(r.shares)} sh {money(r.usd)}" for r in c.others
                        )
                    )
                parts.append("form " + ", ".join(bits))
                continue
            st = ", ".join(sorted({c.sale_status(r) for r in c.sales}))
            basis = ", ".join(sorted({r.plan_basis or "not disclosed" for r in c.sales}))
            bits = [f"{acc} {c.owner_name or c.owner_cik or ''}: {st} (plan basis: {basis})",
                    f"{pct(c.pct_stake_before_sale())} of stake before "
                    f"({shares_txt(c.stake_before_sale)}; {c.stake_note})"]  # fmt: skip
            if market is not None:
                scaled = c.scaled(c.sale_shares, market)
                if c.cover is not None:
                    bits.append(f"{pct(c.cover.pct(scaled), 4)} of cover count {c.cover.text}")
                if c.float_ is not None:
                    bits.append(
                        f"{pct(c.float_.pct(scaled), 4)} of implied float {c.float_.text}"
                        if c.float_.value
                        else c.float_.text
                    )
                if c.adv is not None:
                    bits.append(f"{pct(c.adv.pct(c.sale_shares), 2)} of 20-day ADV {c.adv.text}"
                                if c.adv.value else f"ADV share {c.adv.text}")  # fmt: skip
            if c.others:
                bits.append(
                    "not in total: "
                    + "; ".join(
                        f"{r.code} {shares_txt(r.shares)} sh {money(r.usd)}" for r in c.others
                    )
                )
            parts.append("form " + ", ".join(bits))
            w = c.warning()
            if w:
                warnings.append(w)
        if warnings:
            parts.append("warning: " + "; ".join(dict.fromkeys(warnings)))
        else:
            parts.append("info: plan, plan_na and routine sales are noise (R7, D-M07-3)")
        out.append(DayRow("insider_sale", day, text, value, "; ".join(parts), _sources(rows),
                          ("PT", "ST") if warnings else ("MY", "PT", "ST")))  # fmt: skip
    return out


# --- net flow ----------------------------------------------------------------------------


@dataclass
class NetFlow:
    tf: str
    start: str
    end: str
    text: str | None  # None = missing
    value: float | None
    method: str
    missing: str | None = None
    sources: list[Source] = field(default_factory=list)
    p_usd: float | None = None
    p_shares: float = 0
    np_usd: float | None = None
    np_shares: float = 0
    plan_usd: float | None = None
    plan_shares: float = 0
    plan_na_usd: float | None = None
    plan_na_shares: float = 0
    gross_usd: float | None = None
    gross_shares: float = 0
    insiders: int = 0


def _usd(rows: list[Row]) -> float | None:
    vals = [r.usd for r in rows if r.usd is not None]
    return sum(vals) if vals else None


def net_flow(issuer: Issuer, tf: str, end: date, history_start: str | None,
             market: Market | None, latest_form: Source | None) -> NetFlow:  # fmt: skip
    start = window_start(end, tf)
    label = dict(WINDOWS)[tf]
    nf = NetFlow(tf, start.isoformat(), end.isoformat(), None, None, "")
    head = f"window {label} ({start.isoformat()} to {end.isoformat()}, by trade date)"
    if history_start is None:
        nf.missing, nf.method = "no Form 4 history stored", head
        return nf
    if start.isoformat() < history_start:
        nf.missing, nf.method = f"history starts {history_start}", head
        return nf
    rows = [r for r in issuer.effective() if r.txn_date and start.isoformat() < r.txn_date
            <= end.isoformat() and r.kind in ("buy", "sale")]  # fmt: skip
    p = [r for r in rows if r.kind == "buy"]
    s = [r for r in rows if r.kind == "sale"]
    npl = [r for r in s if r.plan == "non_plan"]
    plan = [r for r in s if r.plan == "plan"]
    pna = [r for r in s if r.plan == "plan_na"]
    nf.p_usd, nf.p_shares = _usd(p), sum(r.shares or 0 for r in p)
    nf.np_usd, nf.np_shares = _usd(npl), sum(r.shares or 0 for r in npl)
    nf.plan_usd, nf.plan_shares = _usd(plan), sum(r.shares or 0 for r in plan)
    nf.plan_na_usd, nf.plan_na_shares = _usd(pna), sum(r.shares or 0 for r in pna)
    nf.gross_usd, nf.gross_shares = _usd(s), sum(r.shares or 0 for r in s)
    nf.insiders = len({r.owner_cik for r in rows if r.owner_cik})
    nf.sources = _sources(rows) or ([latest_form] if latest_form else [])
    if not nf.sources:
        nf.missing, nf.method = "no Form 4 stored for this company", head
        return nf
    unpriced = sum(1 for r in p + npl if r.usd is None)
    if not rows:
        nf.text = "none"
    elif not p and not npl:
        nf.text = "plan_only"
    else:
        nf.value = (nf.p_usd or 0.0) - (nf.np_usd or 0.0)
        nf.text = "net_buy" if nf.value > 0 else "net_sell"
    parts = [
        head,
        f"open-market P {len(p)} row(s) {shares_txt(nf.p_shares)} sh {money(nf.p_usd)}",
        f"non-plan S {len(npl)} row(s) {shares_txt(nf.np_shares)} sh {money(nf.np_usd)}",
        f"beside, not netted: plan S {shares_txt(nf.plan_shares)} sh {money(nf.plan_usd)}, "
        f"plan_na S {shares_txt(nf.plan_na_shares)} sh {money(nf.plan_na_usd)}",
        f"gross S {shares_txt(nf.gross_shares)} sh {money(nf.gross_usd)}",
        f"insiders {nf.insiders}",
    ]
    if unpriced:
        parts.append(f"{unpriced} P / non-plan S row(s) without a price, not in $")
    if nf.text == "plan_only":
        parts.append("net $ not applicable: plan sales only")
    if nf.text == "none":
        parts.append("no open-market P or S in the window")
    if market is not None and rows:
        cover = market.cover(end.isoformat())
        flt = market.float_(end.isoformat())
        net_sh = nf.p_shares - nf.np_shares
        parts.append(f"net shares {shares_txt(net_sh)} = {pct(cover.pct(net_sh), 4)} of cover "
                     f"count; gross S {pct(cover.pct(nf.gross_shares), 4)} of cover count "
                     f"({cover.text})")  # fmt: skip
        parts.append(f"gross S {pct(flt.pct(nf.gross_shares), 4)} of implied float ({flt.text})"
                     if flt.value else flt.text)  # fmt: skip
    parts.append("purchase_from_issuer rows not in net flow; info (D-M07-5)")
    nf.method = "; ".join(parts)
    return nf


# --- the pass ----------------------------------------------------------------------------


@dataclass
class CompanyPass:
    ticker: str
    cik: str
    history_start: str | None = None
    forms: int = 0
    rows: int = 0
    links: int = 0
    recomputed: bool = False
    classes: dict[str, int] = field(default_factory=dict)
    buys: list[DayRow] = field(default_factory=list)
    sales: list[DayRow] = field(default_factory=list)
    net: dict[str, NetFlow] = field(default_factory=dict)
    alerts: list[str] = field(default_factory=list)  # new this pass
    baseline: list[str] = field(default_factory=list)  # first pass: recorded, not shown
    signals: int = 0
    cards: list[Card] = field(default_factory=list)
    error: str = ""


@dataclass
class OwnershipPass:
    companies: dict[str, CompanyPass] = field(default_factory=dict)

    @property
    def alerts(self) -> list[str]:
        return [a for c in self.companies.values() for a in c.alerts]


def _state(engine: sqlite3.Connection, name: str) -> str | None:
    row = engine.execute("SELECT detail FROM refresh_state WHERE name = ?", (name,)).fetchone()
    return row[0] if row else None


def _put_state(engine: sqlite3.Connection, name: str, detail: str, now: datetime) -> None:
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, 'M07', ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
        "detail = excluded.detail",
        (name, iso(now), detail),
    )


def _fingerprint(engine: sqlite3.Connection, cik: str, year: int) -> str:
    row = engine.execute(
        "SELECT count(*), max(parsed_at) FROM form4_doc WHERE issuer_cik = ?", (cik,)
    ).fetchone()
    return json.dumps({"forms": row[0], "parsed": row[1], "year": year})


def _write(engine: sqlite3.Connection, cik: str, ticker: str, d: DayRow) -> int:
    return write_signal(engine, cik=cik, ticker=ticker, module_id=MODULE, signal=d.signal,
                        as_of=d.day, value=d.value, value_text=d.text, method=d.method,
                        sources=d.sources, info=d.info)  # fmt: skip


def company_pass(
    engine: sqlite3.Connection,
    ticker: str,
    cik: str,
    now: datetime,
    *,
    today: date,
    force: bool = False,
    with_market: bool = True,
) -> CompanyPass:
    """One company's M07 pass. Each write is one short transaction."""
    cp = CompanyPass(ticker, cik)
    cp.history_start = coverage_start(engine, cik)
    fp = _fingerprint(engine, cik, today.year)
    due = force or _state(engine, f"m07_pass:{cik}") != fp
    first = _state(engine, f"m07_baseline:{cik}") is None

    engine.execute("BEGIN")
    try:
        cp.links = rows_mod.link_amendments(engine, cik)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    issuer = rows_mod.load(engine, cik)
    cp.forms = len(issuer.by_accession())
    cp.rows = len(issuer.rows)
    verdicts = cls_mod.compute(issuer, cp.history_start, today.year)
    for v in verdicts.values():
        if v.year == today.year:
            cp.classes[v.cls] = cp.classes.get(v.cls, 0) + 1
    market = Market(engine, cik) if with_market else None
    cards = build_cards(issuer, verdicts, market)
    cp.cards = cards
    by_acc = {c.accession: c for c in cards}

    engine.execute("BEGIN")
    try:
        if due:
            cp.recomputed = True
            cls_mod.store(engine, cik, verdicts, now)
            cp.buys = buy_days(ticker, issuer, by_acc, verdicts, market)
            cp.sales = sale_days(issuer, by_acc, market)
            for sig, rows in (("insider_buy", cp.buys), ("insider_sale", cp.sales)):
                keep = [d.day for d in rows]
                marks = ",".join("?" * len(keep)) or "''"
                engine.execute(
                    f"DELETE FROM signal WHERE cik = ? AND module_id = ? AND signal = ? AND "
                    f"as_of NOT IN ({marks})",
                    (cik, MODULE, sig, *keep),
                )  # stale days (a re-parse or a 4/A moved a row)
                for d in rows:
                    cp.signals += _write(engine, cik, ticker, d)
            for d in cp.buys:
                if d.alert is None:
                    continue
                key = f"m07_alert:{cik}:{d.day}"
                if _state(engine, key) is not None:
                    continue  # one alert per company and filing day (a 4/A keeps the day)
                if first:
                    _put_state(engine, key, f"baseline: {d.alert}", now)
                    cp.baseline.append(d.alert)
                else:
                    _put_state(engine, key, d.alert, now)
                    cp.alerts.append(d.alert)
            _put_state(engine, f"m07_pass:{cik}", fp, now)
            if first:
                _put_state(engine, f"m07_baseline:{cik}", iso(now), now)
        latest = engine.execute(
            "SELECT accession, filed, doc_type FROM form4_doc WHERE issuer_cik = ? "
            "ORDER BY filed DESC, accession DESC LIMIT 1",
            (cik,),
        ).fetchone()
        latest_src = (Source(latest["accession"], latest["filed"], "A",
                             "latest stored Form 4; no P/S in the window")
                      if latest else None)  # fmt: skip
        for tf, _ in WINDOWS:
            nf = net_flow(issuer, tf, today, cp.history_start, market, latest_src)
            cp.net[tf] = nf
            common = dict(cik=cik, ticker=ticker, module_id=MODULE, signal="insider_net_flow",
                          as_of=today.isoformat(), timeframes=(tf,), info=(tf,))  # fmt: skip
            if nf.missing is not None:
                cp.signals += write_signal(engine, **common, method=nf.method, missing=nf.missing)
            else:
                cp.signals += write_signal(engine, **common, method=nf.method, value=nf.value,
                                           value_text=nf.text, sources=nf.sources)  # fmt: skip
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return cp


def local_pass(
    engine: sqlite3.Connection,
    comps: dict[str, str],
    now: datetime,
    *,
    today: date | None = None,
    force: bool = False,
) -> OwnershipPass:
    """Every company (ticker → cik); one company's error never stops the others."""
    from engine.refresh import market_date

    day = today or market_date(now)
    out = OwnershipPass()
    for ticker, cik in sorted(comps.items()):
        try:
            out.companies[ticker] = company_pass(engine, ticker, cik, now, today=day, force=force)
        except Exception as e:  # recorded per company
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            out.companies[ticker] = CompanyPass(ticker, cik, error=f"{type(e).__name__}: {e}")
    return out


def run_local_part(engine: sqlite3.Connection, comps: dict[str, str], now: datetime) -> list[str]:
    """Refresh hook (0 SEC requests): one summary line plus new alerts and errors."""
    op = local_pass(engine, comps, now)
    cs = list(op.companies.values())
    recomputed = [c.ticker for c in cs if c.recomputed]
    lines = [
        f"M07 insiders — local pass (0 SEC requests): {len(cs)} companies; recomputed after "
        f"new Form 4s: {', '.join(recomputed) or 'none'}; signals written "
        f"{sum(c.signals for c in cs)}; new alerts {len(op.alerts)}"
    ]
    lines += [f"  alert: {a}" for a in op.alerts]
    lines += [f"  {c.ticker}: error — {c.error}" for c in cs if c.error]
    return lines


def recent_alerts(engine: sqlite3.Connection, now: datetime, hours: int = 24) -> list[str]:
    """Insider-buy alerts first recorded in the last `hours` (the end-of-run box)."""
    since = iso(now - timedelta(hours=hours))
    return [
        r[0]
        for r in engine.execute(
            "SELECT detail FROM refresh_state WHERE name LIKE 'm07_alert:%' AND fetched_at >= ? "
            "AND detail NOT LIKE 'baseline:%' ORDER BY fetched_at, name",
            (since,),
        )
    ]
