"""Debt, FCF-burn and negative-equity rows beside the gate (M04 Part 4a; D-M04-29, -39,
S4.8). Information rows, except `negative_equity` (a warning).

- `debt_to_revenue` = total debt (incl. current) ÷ TTM revenue; `net_debt_ebitda` = (total
  debt − cash − short-term investments) ÷ (TTM operating income + TTM D&A), EBITDA ≤ 0 →
  not meaningful. Each against the company's own fiscal-year values of the last 3 years
  and, for `debt_to_revenue`, the confirmed peers' robust z at the latest fiscal year
  (same formula both sides; D-M04-52 statistics). No vote until Part 8 (D-M04-29).
- `fcf_burn` = TTM FCF on total capex ÷ TTM revenue (value) and ÷ cash and investments,
  with the gate's tier (cash burner / capex-funded / self-funding) and the latest
  `capex_split` growth capex as context (D-M04-39).
- `negative_equity`: equity < 0 with an accumulated deficit, a TTM operating loss or a
  negative TTM OCF → warn; equity < 0 with none of them (buyback-funded) → note (S4.8).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

from engine.financials import peers as peers_mod
from engine.financials import stats
from engine.financials.gate import DEBT_CURRENT, LTD_CURRENT, Gate, money
from engine.sec.asof import AsOfPoint, facts_as_of
from engine.sec.identity import normalize_cik
from engine.signals import Source

YEARS = 3  # own range (D-M04-29)
PEER_TOL = 45


def _pts(engine, cik, concept, as_of, ptype) -> dict[str, AsOfPoint]:
    return {p.end: p for p in facts_as_of(engine, cik, concept, as_of, ptype=ptype).points}


def _at(points: dict[str, AsOfPoint], end: str, days: int = 10) -> AsOfPoint | None:
    if end in points:
        return points[end]
    d = date.fromisoformat(end)
    return next(
        (p for e, p in points.items() if abs((date.fromisoformat(e) - d).days) <= days), None
    )


@dataclass
class DebtPoint:
    end: str
    total_debt: float | None
    debt_text: str
    revenue: float | None
    ebitda: float | None
    cash: float | None
    ratio: float | None = None  # debt ÷ revenue
    nd_ebitda: float | None = None
    nd_text: str = ""
    sources: list[Source] = field(default_factory=list)


class _Book:
    """The points one company's debt rows read (once per company)."""

    def __init__(self, engine: sqlite3.Connection, cik: str, as_of: str) -> None:
        c = normalize_cik(cik) or cik
        self.ltd = _pts(engine, c, "long_term_debt", as_of, "I")
        self.ltd_total = _pts(engine, c, "long_term_debt_total", as_of, "I")
        self.dc = _pts(engine, c, DEBT_CURRENT, as_of, "I")
        self.ltdc = _pts(engine, c, LTD_CURRENT, as_of, "I")
        self.stb = _pts(engine, c, "short_term_borrowings", as_of, "I")
        self.cash = _pts(engine, c, "cash", as_of, "I")
        self.sti = _pts(engine, c, "short_term_investments", as_of, "I")
        self.rev = {
            **_pts(engine, c, "revenue", as_of, "FY"),
            **_pts(engine, c, "revenue", as_of, "TTM"),
        }
        self.fy_rev = _pts(engine, c, "revenue", as_of, "FY")
        self.oi = {
            **_pts(engine, c, "operating_income", as_of, "FY"),
            **_pts(engine, c, "operating_income", as_of, "TTM"),
        }
        self.da = {**_pts(engine, c, "da", as_of, "FY"), **_pts(engine, c, "da", as_of, "TTM")}

    def point(self, end: str) -> DebtPoint:
        srcs: list[Source] = []

        def take(p: AsOfPoint | None, what: str) -> float | None:
            if p is None:
                return None
            srcs.append(Source(p.accession, p.filed, "A", what))
            return float(p.value)

        cur, ctext = None, ""
        dc, ltdc, stb = _at(self.dc, end), _at(self.ltdc, end), _at(self.stb, end)
        if dc is not None:
            cur, ctext = take(dc, "DebtCurrent"), "DebtCurrent"
        elif ltdc is not None or stb is not None:
            cur = (take(ltdc, "LongTermDebtCurrent") or 0.0) + (
                take(stb, "ShortTermBorrowings") or 0.0
            )
            ctext = " + ".join(
                n
                for n, p in (("LongTermDebtCurrent", ltdc), ("ShortTermBorrowings", stb))
                if p is not None
            )
        nonc = _at(self.ltd, end)
        total = None
        text = ""
        if nonc is not None:
            total = take(nonc, "long-term debt") + (cur or 0.0)
            text = "long-term debt + " + (ctext or "no current-debt tag (taken as none, named)")
        elif (lt := _at(self.ltd_total, end)) is not None:
            total = take(lt, "LongTermDebt (incl. current)") + (
                take(stb, "ShortTermBorrowings") if stb is not None else 0.0
            )
            text = "LongTermDebt (incl. current maturities)" + (
                " + ShortTermBorrowings" if stb is not None else ""
            )
        elif cur is not None:
            total, text = cur, ctext + " (no long-term debt tag)"
        cash = _at(self.cash, end)
        sti = _at(self.sti, end)
        cash_v = take(cash, "cash")
        if cash_v is not None:
            cash_v += take(sti, "short-term investments") or 0.0
        rev = take(_at(self.rev, end), "revenue (12 months)")
        oi = _at(self.oi, end)
        da = _at(self.da, end)
        ebitda = None
        if oi is not None and da is not None:
            ebitda = take(oi, "operating income") + take(da, "D&A")
        dp = DebtPoint(end, total, text or "no debt tags", rev, ebitda, cash_v, sources=srcs)
        if total is not None and rev:
            dp.ratio = total / rev
        if total is not None and ebitda is not None and cash_v is not None:
            if ebitda <= 0:
                dp.nd_text = "not_meaningful"
            else:
                dp.nd_ebitda = (total - cash_v) / ebitda
        return dp


@dataclass
class DebtRows:
    latest: DebtPoint | None
    history: list[DebtPoint]
    peer: stats.RobustZ | None = None
    peer_note: str = ""
    peer_ref: str = ""

    def range_text(self, attr: str) -> str:
        vals = [getattr(p, attr) for p in self.history if getattr(p, attr) is not None]
        if not vals:
            return "own range: no fiscal-year values"
        lo, hi = min(vals), max(vals)
        now = getattr(self.latest, attr) if self.latest else None
        pos = ""
        if now is not None:
            pos = (
                " — above own range"
                if now > hi
                else " — below own range"
                if now < lo
                else " — top of own range"
                if hi > lo and now >= lo + 0.8 * (hi - lo)
                else ""
            )
        return f"own {YEARS}-year range {lo:.2f}–{hi:.2f} ({len(vals)} fiscal years){pos}"


def debt_rows(
    engine: sqlite3.Connection,
    cik: str,
    as_of: str,
    end: str | None,
    *,
    with_peers: bool = True,
) -> DebtRows:
    """`end` = the gate's balance-sheet date (latest 12-month period ending there)."""
    book = _Book(engine, cik, as_of)
    latest = book.point(end) if end else None
    cutoff = (date.fromisoformat(as_of) - timedelta(days=365 * YEARS + 10)).isoformat()
    hist = [book.point(e) for e in sorted(book.fy_rev) if e >= cutoff]
    out = DebtRows(latest, hist)
    if with_peers and book.fy_rev:
        _peer_z(engine, cik, as_of, book, out)
    return out


def _peer_z(engine, cik, as_of, book: _Book, out: DebtRows) -> None:
    norm = normalize_cik(cik) or cik
    confirmed = [r for r in peers_mod.confirmed_peers(engine, norm) if r["cik"]]
    if not confirmed:
        out.peer_note = "peer z: missing: no confirmed SEC peers"
        return
    ref = max(book.fy_rev)
    me = book.point(ref).ratio
    if me is None:
        out.peer_note = f"peer z: missing: no company value at {ref}"
        return
    vals = []
    for r in confirmed:
        pb = _Book(engine, r["cik"], as_of)
        ends = [
            e
            for e in pb.fy_rev
            if abs((date.fromisoformat(e) - date.fromisoformat(ref)).days) <= PEER_TOL
        ]
        if not ends:
            continue
        v = pb.point(
            min(ends, key=lambda e: abs((date.fromisoformat(e) - date.fromisoformat(ref)).days))
        ).ratio
        if v is not None:
            vals.append((r["name"], v))
    if not vals:
        out.peer_note = f"peer z: missing: no comparable peer fiscal year (±{PEER_TOL} d of {ref})"
        return
    out.peer = stats.robust_z(me, vals)
    out.peer_ref = ref
    rz = out.peer
    z = (f"{rz.z:+.2f}" + (" (info)" if rz.z_info else "")) if rz.z is not None else "no z"
    out.peer_note = (
        f"peer z {z} (n {rz.n}, median {rz.median:.2f}, {rz.method}; fiscal year "
        f"{ref}, peers ±{PEER_TOL} d)"
    )


@dataclass
class FcfBurn:
    value: float | None  # TTM FCF ÷ TTM revenue
    to_liquidity: float | None
    fcf: float | None
    basis: str
    tier: str
    context: str
    missing: str = ""
    sources: list[Source] = field(default_factory=list)


def fcf_burn(engine: sqlite3.Connection, g: Gate, as_of: str) -> FcfBurn:
    """From the gate's burn bases (one computation, D-M04-39)."""
    if not g.bases:
        return FcfBurn(
            None,
            None,
            None,
            "",
            "",
            "",
            missing="no burn basis (" + ("; ".join(g.missing) or "gate not computed") + ")",
        )
    b = next((x for x in g.bases if x.name == "TTM ÷ 4"), None) or next(
        (x for x in g.bases if x.name == "fiscal year ÷ 4"), None
    )
    scale = 1.0
    if b is None:
        b, scale = g.bases[0], 2.0  # last two quarters × 2, labelled
    fcf = b.fcf * scale
    basis = {"TTM ÷ 4": "TTM", "fiscal year ÷ 4": "fiscal year"}.get(
        b.name, "last two quarters × 2"
    )
    rev = None
    if scale == 2.0:  # the same two quarters × 2
        q = _pts(engine, g.cik, "revenue", as_of, "Q")
        last = _at(q, b.end)
        prev = [
            p
            for e, p in q.items()
            if last and 60 <= (date.fromisoformat(last.end) - date.fromisoformat(e)).days <= 120
        ]
        if last is not None and prev:
            rev = (float(last.value) + float(max(prev, key=lambda p: p.end).value)) * 2
    for ptype in ("TTM", "FY") if rev is None else ():
        p = _at(_pts(engine, g.cik, "revenue", as_of, ptype), b.end)
        if p is not None:
            rev = float(p.value)
            break
    ctx = []
    row = engine.execute(
        "SELECT fiscal_label, growth, total FROM capex_split WHERE cik = ? ORDER BY period_end "
        "DESC LIMIT 1",
        (g.cik,),
    ).fetchone()
    if row is not None and row["growth"] is not None:
        ctx.append(
            f"{row['fiscal_label']} growth capex {money(row['growth'])} of "
            f"{money(row['total'])} (capex_split)"
        )
    if g.ocf_only:
        ctx.append("capex untagged: FCF = OCF")
    if g.capex_mark:
        ctx.append(f"total capex [{g.capex_mark}]")
    out = FcfBurn(
        fcf / rev if rev else None,
        fcf / g.liquidity_cash if g.liquidity_cash else None,
        fcf,
        basis,
        g.tier_text,
        "; ".join(ctx),
        sources=list(g.sources),
    )
    if rev is None:
        out.missing = "no revenue for the period" if fcf is not None else ""
    return out


@dataclass
class NegEquity:
    state: str  # warn | note | none | missing
    equity: float | None
    reasons: list[str]
    sources: list[Source]
    end: str | None = None


def negative_equity(engine: sqlite3.Connection, cik: str, as_of: str) -> NegEquity:
    norm = normalize_cik(cik) or cik
    eqs = _pts(engine, norm, "equity", as_of, "I")
    if not eqs:
        return NegEquity("missing", None, ["no equity tagged"], [])
    end = max(eqs)
    e = eqs[end]
    srcs = [Source(e.accession, e.filed, "A", "equity")]
    if float(e.value) >= 0:
        return NegEquity("none", float(e.value), [], srcs, end)
    reasons = []
    re_ = _at(_pts(engine, norm, "retained_earnings", as_of, "I"), end)
    if re_ is not None and float(re_.value) < 0:
        reasons.append(f"accumulated deficit {money(re_.value)}")
    for concept, what in (
        ("operating_income", "TTM operating loss"),
        ("operating_cash_flow", "negative TTM OCF"),
    ):
        p = _at(_pts(engine, norm, concept, as_of, "TTM"), end) or _at(
            _pts(engine, norm, concept, as_of, "FY"), end
        )
        if p is not None and float(p.value) < 0:
            reasons.append(f"{what} {money(p.value)}")
            srcs.append(Source(p.accession, p.filed, "A", concept))
    if reasons:
        return NegEquity("warn", float(e.value), reasons, srcs, end)
    return NegEquity(
        "note",
        float(e.value),
        ["retained earnings, operating income and OCF not negative: buyback-funded"],
        srcs,
        end,
    )
