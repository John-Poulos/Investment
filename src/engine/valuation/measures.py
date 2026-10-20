"""EV and every standard valuation row at one date (D-M08-1, D32; rules 1, 2, 8, 10).

`snapshot(k, day, ...)` computes, for one company and one close date, the market cap, the
enterprise value and every standard row — P/E TTM, EV/EBITDA, EV/EBIT, EV/Sales, EV/Gross
profit, P/S, P/B, P/FCF, FCF yield, dividend yield, EV ÷ normalized EBIT, P ÷ normalized
EPS — plus mNAV (MSTR's headline, D-M08-7). The same function serves today's rows, the
own-history quarter-ends (first-filed values, D-M08-2) and the peers.

- **TTM** (rule 1): the newest 12-month point filed by the date: TTM (four quarters, Q4 =
  FY − 9M) or, when the fiscal year is newer (annual filers, a 20-F without 6-K quarters),
  the fiscal year "as of FY". Every row names its period.
- **EV** = market cap + debt (current and noncurrent as `debt.Book.point` states it; finance
  leases as tagged, labelled) + preferred + noncontrolling interest − cash − short-term
  investments, at the newest balance sheet filed by the date; operating leases excluded
  ("EV ex operating leases"). Cash untagged at that balance sheet, or debt tagged earlier
  but not there → every EV row "missing: EV incomplete (<component>)". A company that never
  tagged debt, preferred or a noncontrolling interest reads none, named (D-M04-90; D-M08-12).
- A denominator ≤ 0 (or EV ≤ 0) → `not_meaningful`, no value (D-SRCH-15). Missing stays
  missing, never zero (D-M04-9).
- A recast input (latest value ≠ first-filed value) flags a series break in the detail
  (rule 10; INFQ FY2025 net income −66.9M vs −32.2M).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from engine.financials import nep as nep_mod
from engine.financials.debt import Book, Points
from engine.financials.debt import _at as near_point
from engine.sec.asof import AsOfPoint
from engine.sec.xbrl_facts import ALL_CONCEPTS
from engine.signals import Source

MODULE = "M08"
# (signal, label, unit): unit "x" multiple, "%" percent of price or market cap
STANDARD = (
    ("val_pe_ttm", "P/E TTM (GAAP)", "x"),
    ("val_ev_ebitda", "EV/EBITDA", "x"),
    ("val_ev_ebit", "EV/EBIT", "x"),
    ("val_ev_sales", "EV/Sales", "x"),
    ("val_ev_gp", "EV/Gross profit", "x"),
    ("val_ps", "P/S", "x"),
    ("val_pb", "P/B", "x"),
    ("val_p_fcf", "P/FCF (total capex)", "x"),
    ("val_fcf_yield", "FCF yield", "%"),
    ("val_div_yield", "Dividend yield", "%"),
    ("val_ev_nebit", "EV/normalized EBIT", "x"),
    ("val_p_neps", "P/normalized EPS", "x"),
)
STANDARD_KEYS = tuple(s for s, _, _ in STANDARD)
LABELS = {s: label for s, label, _ in STANDARD} | {"mnav": "mNAV (market cap ÷ crypto fair value)"}
UNITS = {s: u for s, _, u in STANDARD} | {"mnav": "x"}
EV_ROWS = frozenset({"val_ev_ebitda", "val_ev_ebit", "val_ev_sales", "val_ev_gp", "val_ev_nebit"})
HEADLINE_KEYS = (*STANDARD_KEYS, "mnav")
NM = "not_meaningful"
FAIR_VALUE = "fair_value_earnings"


def money(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v / 1e6:,.0f}M" if abs(v) >= 1e6 else f"{v:,.0f}"


def fmt(key: str, v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}%" if UNITS.get(key) == "%" else f"{v:.1f}×"


@dataclass
class Measure:
    key: str
    value: float | None = None
    text: str | None = None  # value_text: not_meaningful, fair_value_earnings
    missing: str | None = None
    detail: str = ""
    sources: list[Source] = field(default_factory=list)

    @property
    def label(self) -> str:
        return LABELS[self.key]

    @property
    def shown(self) -> str:
        if self.missing:
            return "missing"
        if self.value is None:
            return self.text or "—"
        return fmt(self.key, self.value)


@dataclass
class Snapshot:
    day: str
    close: object | None = None  # asof.Close
    cap: object | None = None  # asof.Cap
    ev: float | None = None
    ev_text: str = ""
    ev_missing: str = ""
    twelve: str = ""  # the 12-month period the flows come from
    nep: nep_mod.NEP | None = None
    breaks: list[str] = field(default_factory=list)
    measures: dict[str, Measure] = field(default_factory=dict)
    missing: str = ""  # every row missing for this reason (no close, fund, shell)

    def m(self, key: str) -> Measure:
        return self.measures[key]


def _src(p: AsOfPoint, what: str) -> Source:
    return Source(p.accession, p.filed, "A", what)


STALE_DAYS = 100  # a 12-month value ending more than about a quarter before the newest report


def _newest_flow(pts: Points) -> str | None:
    """The newest period end of any reported flow (quarter, TTM or fiscal year)."""
    ends = [e for c in ("revenue", "net_income", "operating_income")
            for t in ("Q", "TTM", "FY") for e in pts(c, t)]  # fmt: skip
    return max(ends) if ends else None


def _twelve_any(pts: Points, concept: str) -> tuple[AsOfPoint | None, str]:
    ttm, fy = pts(concept, "TTM"), pts(concept, "FY")
    t = ttm[max(ttm)] if ttm else None
    f = fy[max(fy)] if fy else None
    if t is None and f is None:
        return None, ""
    if f is not None and (t is None or f.end > t.end):
        return f, f"fiscal year to {f.end} (as of FY)"
    return t, f"TTM to {t.end}"


def twelve(pts: Points, concept: str) -> tuple[AsOfPoint | None, str]:
    """The newest 12-month point: TTM, else a newer fiscal year ("as of FY"). A point
    ending more than STALE_DAYS before the newest reported flow is not used (live check 1:
    AVGO's P/E read FY2024 net income because FY2025 was missing): missing, see `no12`."""
    p, lab = _twelve_any(pts, concept)
    newest = _newest_flow(pts)
    if (
        p is not None
        and newest
        and (date.fromisoformat(newest) - date.fromisoformat(p.end)).days > STALE_DAYS
    ):
        return None, ""
    return p, lab


def _same_end(pts: Points, concept: str, end: str) -> AsOfPoint | None:
    for ptype in ("TTM", "FY"):
        p = near_point(pts(concept, ptype), end)
        if p is not None:
            return p
    return None


def _latest_instant(pts: Points, concept: str, end: str | None = None) -> AsOfPoint | None:
    d = pts(concept, "I")
    if not d:
        return None
    if end is not None:
        return near_point(d, end)
    return d[max(d)]


def no12(pts: Points, concept: str, excluded: dict[str, int] | None = None) -> str:
    """Why a 12-month value is missing: untagged, or quarters without four contiguous ones
    and no fiscal year (INFQ: its FY2025 10-K reports a period before the de-SPAC boundary,
    so its facts are the shell's and left out, D-M04-8)."""
    q = pts(concept, "Q")
    name = concept.replace("_", " ")
    old, old_lab = _twelve_any(pts, concept)
    newest = _newest_flow(pts)
    if old is not None and newest and old.end < newest:
        return (
            f"12-month {name} stale: the newest is {old_lab}, the company has reported "
            f"through {newest}, and no newer 12 months can be derived (a fiscal year or "
            "quarter missing)"
        )
    if q:
        return (
            f"no 12-month {name}: {len(q)} quarter(s) stored to {max(q)}, not four contiguous, "
            "and no fiscal year (documents before an entity boundary are left out)"
        )
    if excluded:
        left = ", ".join(f"{n} {why}" for why, n in sorted(excluded.items()))
        return f"no {name} in periodic reports (left out: {left})"
    return f"{name} untagged ({tags_checked(concept)})"


def tags_checked(concept: str) -> str:
    return ", ".join(f"{t}:{g}" for t, g in ALL_CONCEPTS[concept].tags)


def _ev(pts: Points, book: Book, cap: float, end: str) -> tuple[float | None, str, str, list]:
    """(EV, text, missing component, sources) at balance-sheet date `end`."""
    dp = book.point(end)
    srcs = list(dp.sources)
    if near_point(book.cash, end) is None:
        return None, "", f"cash (no cash tag at the {end} balance sheet)", srcs
    adds, notes = [f"market cap {money(cap)}"], []
    debt = dp.total_debt
    if debt is None:
        tagged = [e for d in (book.ltd, book.ltd_total, book.dc, book.ltdc, book.stb) for e in d]
        last = max(tagged) if tagged else None
        if last is None:  # live check 1 (GFS has debt): untagged is missing, never zero
            return None, "", "debt untagged (no debt tag ever stored)", srcs
        if (date.fromisoformat(end) - date.fromisoformat(last)).days <= 730:
            return None, "", f"debt (tagged until {last}, not at {end})", srcs
        debt = 0.0
        notes.append(f"debt none (last tagged {last}, over 2 years before: taken as none, named)")
    else:
        lt = near_point(book.ltd, end)
        lease = (
            " (finance leases included as tagged)"
            if lt is not None and ("CapitalLease" in lt.method or "FinanceLease" in lt.method)
            else ""
        )
        adds.append(f"+ debt {money(debt)} ({dp.debt_text}){lease}")
    extra = 0.0
    for concept, what in (
        ("preferred_value", "preferred"),
        ("minority_interest", "noncontrolling interest"),
    ):
        p = _latest_instant(pts, concept, end)
        if p is not None:
            extra += float(p.value)
            srcs.append(_src(p, what))
            adds.append(f"+ {what} {money(float(p.value))}")
        elif not pts(concept, "I"):
            notes.append(f"{what} none tagged")
        else:
            notes.append(f"{what} not at {end} (taken as none, named)")
    cash = dp.cash or 0.0
    adds.append(f"− cash and short-term investments {money(cash)}")
    ev = cap + debt + extra - cash
    text = f"EV {money(ev)} = " + " ".join(adds) + f" (balance sheet {end}; EV ex operating leases"
    text += ("; " + "; ".join(notes) if notes else "") + ")"
    return ev, text, "", srcs


def snapshot(
    k,  # asof.Known
    day: str,
    *,
    first: bool = False,
    fye: str | None = None,
    blocked: str = "",
    asset_treasury: bool = False,
    nep_swing: float = nep_mod.SWING_PP,
    nep_min_years: int = nep_mod.MIN_YEARS,
    tol: int = 5,
) -> Snapshot:
    from engine.valuation import asof

    s = Snapshot(day)
    keys = (*STANDARD_KEYS, "mnav")

    def all_missing(why: str) -> Snapshot:
        s.missing = why
        s.measures = {key: Measure(key, missing=why) for key in keys}
        return s

    if blocked:
        return all_missing(blocked)
    close = asof.close_at(k.engine, k.cik, day, tol)
    if close is None:
        return all_missing(f"no close within {tol} days of {day}")
    s.close = close
    pts = k.view(day, first=first)
    cap = asof.market_cap(k, day, close)
    s.cap = cap
    if cap.value is None:
        return all_missing(f"market cap: {cap.missing}")
    mc = cap.value
    base_src = list(cap.sources or [])

    ni, ni_lab = twelve(pts, "net_income")
    rev, rev_lab = twelve(pts, "revenue")
    s.twelve = rev_lab or ni_lab
    for p, what in ((ni, "net income"), (rev, "revenue")):
        if p is not None and p.restated:
            s.breaks.append(
                f"series break: {what} {p.end} recast {money(p.first_value)} → "
                f"{money(p.value)} (rule 10)"
            )

    # balance sheet: the newest one filed by the date
    ends = [e for c in ("cash", "total_assets", "equity") for e in pts(c, "I")]
    bs_end = max(ends) if ends else None
    book = Book(k.engine, k.cik, day, points=pts)
    if bs_end is None:
        s.ev_missing = "no balance sheet filed by this date"
    else:
        ev, s.ev_text, s.ev_missing, ev_src = _ev(pts, book, mc, bs_end)
        s.ev = ev
    ev_src = ev_src if bs_end is not None else []

    # diluted shares for P/E and normalized EPS (split-scaled to the close)
    dil = {**pts("shares_diluted_wavg", "FY"), **pts("shares_diluted_wavg", "Q")}
    shares = shares_lab = None
    if dil:
        e = max(dil)
        p = dil[e]
        f, seen = k.factor(e, close.day)
        shares = float(p.value) * f
        shares_lab = f"{p.ptype} to {e}" + (f", ×{f:g} split" if seen else "")
        dil_src = _src(p, "diluted shares")

    out: dict[str, Measure] = {}

    def ratio(key: str, num: float | None, den: float | None, what: str, srcs, extra=""):
        m = Measure(key, sources=[*base_src, *srcs])
        if den is None or num is None:
            m.missing = what
        elif den <= 0:
            m.text = NM
            m.detail = f"denominator ≤ 0 ({extra})"
        else:
            m.value = num / den
            m.detail = extra
        out[key] = m

    # P/E TTM
    m = Measure("val_pe_ttm", sources=list(base_src))
    if ni is None:
        m.missing = no12(pts, "net_income", k.excluded("net_income"))
    elif shares is None:
        m.missing = "no diluted weighted-average share count"
    else:
        m.sources += [_src(ni, "net income"), dil_src]
        eps = float(ni.value) / shares
        m.detail = (
            f"close ${close.value:,.2f} ÷ EPS {eps:.2f} = net income "
            f"{money(float(ni.value))} ({ni_lab}) ÷ {shares / 1e6:,.1f}M diluted shares "
            f"({shares_lab})"
        )
        if eps <= 0:
            m.text = NM
        else:
            m.value = close.value / eps
        if asset_treasury:
            m.text = FAIR_VALUE
            m.detail += "; EPS moves with bitcoin under ASU 2023-08 (D-M08-7)"
    out["val_pe_ttm"] = m

    # EV rows
    oi = _same_end(pts, "operating_income", rev.end) if rev is not None else None
    if oi is None:
        oi, _ = twelve(pts, "operating_income")
    gp = _same_end(pts, "gross_profit", rev.end) if rev is not None else None
    gp_val, gp_note = (float(gp.value), "gross profit") if gp is not None else (None, "")
    if gp is None and rev is not None:
        cost = _same_end(pts, "cost_of_revenue", rev.end)
        if cost is not None:
            gp_val, gp_note = float(rev.value) - float(cost.value), "revenue − cost of revenue"
    da = _same_end(pts, "da", oi.end) if oi is not None else None

    def ev_row(key: str, den: float | None, what_missing: str, srcs, desc: str):
        m = Measure(key, sources=[*base_src, *ev_src, *srcs])
        if s.ev is None:
            m.missing = f"EV incomplete ({s.ev_missing})"
        elif den is None:
            m.missing = what_missing
        elif s.ev <= 0:
            m.text, m.detail = NM, f"EV ≤ 0 ({money(s.ev)}: net cash above market cap)"
        elif den <= 0:
            m.text, m.detail = NM, f"denominator ≤ 0 ({desc} {money(den)})"
        else:
            m.value = s.ev / den
            m.detail = f"EV {money(s.ev)} ÷ {desc} {money(den)}"
        out[key] = m

    oi_v = float(oi.value) if oi is not None else None
    ebitda = oi_v + float(da.value) if oi is not None and da is not None else None
    if oi is None:
        da_missing = no12(pts, "operating_income", k.excluded("operating_income"))
    elif not pts("da", "FY") and not pts("da", "TTM"):
        da_missing = f"D&A untagged (checked: {tags_checked('da')})"
    else:
        da_missing = f"D&A not reported for the period ending {oi.end}"
    ev_row(
        "val_ev_ebitda",
        ebitda,
        da_missing,
        [_src(p, w) for p, w in ((oi, "operating income"), (da, "D&A")) if p is not None],
        f"EBITDA ({oi.end if oi else ''})",
    )
    ev_row(
        "val_ev_ebit",
        oi_v,
        no12(pts, "operating_income", k.excluded("operating_income")),
        [_src(oi, "operating income")] if oi else [],
        f"operating income ({oi.end if oi else ''})",
    )
    rev_v = float(rev.value) if rev is not None else None
    ev_row(
        "val_ev_sales",
        rev_v,
        no12(pts, "revenue", k.excluded("revenue")),
        [_src(rev, "revenue")] if rev else [],
        f"revenue ({rev_lab})",
    )
    ev_row(
        "val_ev_gp",
        gp_val,
        "gross profit and cost of revenue untagged",
        [_src(gp, "gross profit")] if gp else [],
        f"{gp_note or 'gross profit'} ({rev_lab})",
    )

    ratio(
        "val_ps",
        mc,
        rev_v,
        no12(pts, "revenue", k.excluded("revenue")),
        [_src(rev, "revenue")] if rev else [],
        f"market cap {money(mc)} ÷ revenue {money(rev_v)} ({rev_lab})",
    )
    eq = _latest_instant(pts, "equity", bs_end) if bs_end else None
    eq_v = float(eq.value) if eq is not None else None
    eq_note = (
        " [tag includes noncontrolling interest]"
        if eq is not None and ("IncludingPortionAttributableToNoncontrollingInterest" in eq.method)
        else ""
    )
    ratio(
        "val_pb",
        mc,
        eq_v,
        f"equity untagged at {bs_end}" if bs_end else "no balance sheet",
        [_src(eq, "equity")] if eq else [],
        f"market cap {money(mc)} ÷ equity {money(eq_v)} ({bs_end}){eq_note}",
    )

    ocf, ocf_lab = twelve(pts, "operating_cash_flow")
    capex = _same_end(pts, "capex", ocf.end) if ocf is not None else None
    fcf = float(ocf.value) - float(capex.value) if ocf is not None and capex is not None else None
    fcf_missing = (
        no12(pts, "operating_cash_flow", k.excluded("operating_cash_flow"))
        if ocf is None
        else f"capex untagged or not reported for {ocf.end} ({tags_checked('capex')})"
    )
    fcf_src = [_src(p, w) for p, w in ((ocf, "OCF"), (capex, "capex")) if p is not None]
    fcf_txt = (
        f"FCF {money(fcf)} = OCF − total capex ({ocf_lab}; D-M04-6)" if fcf is not None else ""
    )
    ratio("val_p_fcf", mc, fcf, fcf_missing, fcf_src, f"market cap {money(mc)} ÷ {fcf_txt}")
    m = Measure("val_fcf_yield", sources=[*base_src, *fcf_src])
    if fcf is None:
        m.missing = fcf_missing
    else:
        m.value = fcf / mc * 100
        m.detail = f"{fcf_txt} ÷ market cap {money(mc)}" + (
            " (negative: cash burn)" if fcf < 0 else ""
        )
    out["val_fcf_yield"] = m

    dv = asof.dividends(k.engine, k, close)
    m = Measure("val_div_yield", sources=list(base_src))
    if dv.per_share is None:
        m.missing = dv.missing
    else:
        m.value = dv.per_share / close.value * 100
        m.detail = dv.text
    out["val_div_yield"] = m

    # normalized earnings power (financials/nep.py, D-M04-106)
    ys = nep_mod.years(pts, fye)
    w = nep_mod.window(ys, swing=nep_swing, min_years=nep_min_years)
    s.nep = nep_mod.normalize(
        w, ttm_revenue=rev_v, ttm_label=rev_lab, shares=shares, shares_label=shares_lab or ""
    )
    n = s.nep
    nb = n.nebit_cycle
    ev_row(
        "val_ev_nebit",
        nb,
        f"NEP: {n.missing}",
        n.sources[-3:],
        f"normalized EBIT ({w.span}, cycle-average revenue)",
    )
    if out["val_ev_nebit"].value is not None and n.nebit_current:
        out["val_ev_nebit"].detail += (
            f"; on the current-revenue base {money(n.nebit_current)}: {s.ev / n.nebit_current:.1f}×"
            if n.nebit_current > 0
            else "; current-revenue base ≤ 0"
        )
    m = Measure("val_p_neps", sources=[*base_src, *n.sources[-3:]])
    if n.missing:
        m.missing = f"NEP: {n.missing}"
    elif n.neps is None:
        m.missing = f"normalized EPS: {n.neps_missing}"
    elif n.neps <= 0:
        m.text, m.detail = NM, f"normalized EPS {n.neps:.2f} ≤ 0 ({w.span})"
    else:
        m.value = close.value / n.neps
        m.detail = f"close ${close.value:,.2f} ÷ normalized EPS {n.neps:.2f} ({w.span})"
    out["val_p_neps"] = m

    # mNAV (MSTR headline, D-M08-7): computed for any company that tags crypto fair value
    cfv = _latest_instant(pts, "crypto_fair_value")
    ratio(
        "mnav",
        mc,
        float(cfv.value) if cfv is not None else None,
        "no CryptoAssetFairValue tagged",
        [_src(cfv, "crypto fair value")] if cfv else [],
        f"market cap {money(mc)} ÷ crypto assets at fair value "
        f"{money(float(cfv.value)) if cfv else '—'} ({cfv.end if cfv else ''}); crypto "
        "exposure (scope S1)",
    )

    for key, mm in out.items():
        if key != "mnav" and s.breaks and mm.missing is None:
            mm.detail += "; " + "; ".join(s.breaks)
    s.measures = out
    return s
