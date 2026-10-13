"""Core trend rows and ROIC (outline "Analyze the financials" 1–4; D-M04-11, S6.5; Part 1b).

Information rows, no vote in CvD or confluence until Part 8 (D-M04-11), each against the
company's own history and, from Part 2, as peer robust z (`peer_z.py`, written into each
signal's method):

- `rev_yoy` — revenue growth year over year (TTM for the signal, fiscal years in the table);
- `rev_cagr3` — 3-year revenue CAGR;
- `fcf_growth` — FCF on total capex (D-M04-78), and `fcf_growth_oe` on owner earnings
  (OCF − maintenance capex − SBC, D-M04-6); a base ≤ 0 or below 1% of revenue is "not
  meaningful" (S2.1); a capex definition change in either year is not scored (D-M04-3);
- `gm_trend_pp` — gross-margin change in percentage points (4 quarters on TTM, 3 years
  on fiscal years); gross profit derived as revenue − cost of revenue where no gross-profit
  tag exists, labelled (AMZN, GOOG, META, SPCX, INFQ);
- `opex_vs_sales` — operating-expense growth minus revenue growth, pp (operating
  leverage); opex = gross profit − operating income;
- ROIC (S6.5) — NOPAT ÷ average invested capital; NOPAT = operating income × (1 − tax ÷
  pretax, bounded 0–35%), or operating income alone when pretax ≤ 0; invested capital =
  equity + long-term debt + current debt − cash − short-term investments; "not meaningful"
  when invested capital ≤ 0. Display only here; consumed by D-M04-54 in Part 8a.

Values come from `facts_as_of` (latest known version, periodic forms only). Missing stays
missing with its reason (D-M04-9): only the debt and short-term-investment terms of
invested capital may be absent, and the method then names them ("no fact: taken as none
on the balance sheet").
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import date

from engine.financials.capex import CapexView, at, fiscal_label, fy_points, near
from engine.sec.asof import AsOfPoint
from engine.sec.identity import normalize_cik

YEARS = 8
NEAR_ZERO = 0.01  # base below 1% of revenue → not meaningful (S2.1)
TAX_CAP = 0.35
NM = "not_meaningful"
# Replaced by the peer robust z text (`peer_z.annotate`, Part 2); left as is when no peer
# comparison was run for the view.
PEER_TOKEN = "peer z: not computed"


@dataclass(frozen=True)
class Cell:
    value: float | None
    text: str = ""  # "not meaningful: …" / "missing: …" when value is None; else the method
    filed: str = ""
    accession: str = ""

    @property
    def shown(self) -> bool:
        return self.value is not None


@dataclass
class Row:
    key: str
    label: str
    unit: str  # pct | pp | usd | ratio
    cells: dict[str, Cell] = field(default_factory=dict)  # fiscal label → cell
    note: str = ""


@dataclass(frozen=True)
class Signal:
    name: str
    value: float | None
    text: str | None  # value_text (not_meaningful) or None
    missing: str | None
    method: str
    sources: tuple[tuple[str, str], ...]  # (accession, filed)
    as_of: str


@dataclass
class TrendsView:
    labels: list[str]
    rows: list[Row]
    signals: list[Signal]
    gp_derived: bool


def _growth(now: float | None, base: float | None, scale: float | None = None) -> Cell:
    if now is None or base is None:
        return Cell(None, "missing: " + ("no base year" if base is None else "no value"))
    if base <= 0:
        return Cell(None, f"{NM}: base ≤ 0")
    if scale is not None and abs(base) < NEAR_ZERO * scale:
        return Cell(None, f"{NM}: base below 1% of revenue")
    return Cell(now / base - 1)


def _pt(p: AsOfPoint | None) -> float | None:
    return float(p.value) if p is not None else None


def _prior(points: dict[str, AsOfPoint], end: str, days: tuple[int, int] = (350, 380)):
    e = date.fromisoformat(end)
    for k, p in points.items():
        d = (e - date.fromisoformat(k)).days
        if days[0] <= d <= days[1]:
            return p
    return None


def _gross(
    rev: dict[str, AsOfPoint], gp: dict[str, AsOfPoint], cost: dict[str, AsOfPoint], end: str
) -> tuple[float | None, str, AsOfPoint | None]:
    """(gross profit, how, deciding point)."""
    g = at(gp, end)
    if g is not None:
        return float(g.value), "reported gross profit", g
    r, c = at(rev, end), at(cost, end)
    if r is not None and c is not None:
        return float(r.value - c.value), "derived: revenue − cost of revenue", c
    return None, "no gross-profit or cost-of-revenue fact", None


def trends_view(
    engine: sqlite3.Connection, cik: str, as_of: str, capex: CapexView | None = None
) -> TrendsView:
    norm = normalize_cik(cik) or cik
    rev = fy_points(engine, norm, "revenue", as_of)
    gp = fy_points(engine, norm, "gross_profit", as_of)
    cost = fy_points(engine, norm, "cost_of_revenue", as_of)
    oi = fy_points(engine, norm, "operating_income", as_of)
    ends = sorted(rev)
    ends = [e for i, e in enumerate(ends) if not any(near(e, x) for x in ends[:i])]
    shown = ends[-YEARS:]
    labels = [fiscal_label(e) for e in shown]
    capex_years = {y.label: y for y in (capex.years if capex else [])}
    ric = roic_inputs(engine, norm, as_of)

    def val(points, end):
        return _pt(at(points, end))

    def prev_end(end: str, back: int = 1) -> str | None:
        i = ends.index(end)
        return ends[i - back] if i - back >= 0 else None

    rows = {k: Row(k, lbl, u) for k, lbl, u in (
        ("rev_yoy", "Revenue YoY", "pct"),
        ("rev_cagr3", "Revenue 3-yr CAGR", "pct"),
        ("fcf_total", "FCF on total capex", "usd"),
        ("fcf_growth", "FCF growth (total capex)", "pct"),
        ("owner_earnings", "Owner earnings (OCF − maintenance − SBC)", "usd"),
        ("fcf_growth_oe", "FCF growth (owner earnings)", "pct"),
        ("gm", "Gross margin", "pct"),
        ("gm_trend_pp", "Gross-margin change vs prior year", "pp"),
        ("opex_vs_sales", "Opex growth − revenue growth", "pp"),
        ("roic", "ROIC (S6.5)", "pct"),
    )}  # fmt: skip
    gp_derived = False
    for end, label in zip(shown, labels, strict=True):
        r = val(rev, end)
        p1, p3 = prev_end(end), prev_end(end, 3)
        rows["rev_yoy"].cells[label] = _growth(r, val(rev, p1) if p1 else None)
        c3 = _growth(r, val(rev, p3) if p3 else None)
        if c3.value is not None:
            c3 = Cell((1 + c3.value) ** (1 / 3) - 1)
        rows["rev_cagr3"].cells[label] = c3

        cy = capex_years.get(label)
        py = capex_years.get(fiscal_label(p1)) if p1 else None
        for key, attr in (("fcf_total", "fcf_total"), ("owner_earnings", "owner_earnings")):
            v = getattr(cy, attr) if cy else None
            why = (cy.missing(attr) if cy else "no total capex this year") or ""
            rows[key].cells[label] = Cell(v, "" if v is not None else f"missing: {why}")
        for key, attr in (("fcf_growth", "fcf_total"), ("fcf_growth_oe", "owner_earnings")):
            if (
                cy
                and py
                and (
                    (cy.total and cy.total.definition_changed)
                    or (py.total and py.total.definition_changed)
                )
            ):
                rows[key].cells[label] = Cell(None, "missing: capex definition changed (D-M04-3)")
                continue
            now_v = getattr(cy, attr) if cy else None
            base_v = getattr(py, attr) if py else None
            rows[key].cells[label] = _growth(now_v, base_v, py.revenue if py else None)

        g, how, _ = _gross(rev, gp, cost, end)
        gp_derived = gp_derived or how.startswith("derived")
        gm = (g / r * 100) if g is not None and r else None
        rows["gm"].cells[label] = Cell(gm, how if gm is not None else f"missing: {how}")
        if p1:
            g0, _, _ = _gross(rev, gp, cost, p1)
            r0 = val(rev, p1)
            gm0 = (g0 / r0 * 100) if g0 is not None and r0 else None
            ok = gm is not None and gm0 is not None
            rows["gm_trend_pp"].cells[label] = (
                Cell(gm - gm0) if ok else Cell(None, "missing: gross margin")
            )
            o, o0 = val(oi, end), val(oi, p1)
            if g is not None and g0 is not None and o is not None and o0 is not None:
                opex, opex0 = g - o, g0 - o0
                go = _growth(opex, opex0)
                gr = _growth(r, r0)
                rows["opex_vs_sales"].cells[label] = (
                    Cell((go.value - gr.value) * 100)
                    if go.value is not None and gr.value is not None
                    else Cell(None, go.text or gr.text)
                )
            else:
                rows["opex_vs_sales"].cells[label] = Cell(
                    None, "missing: gross profit or operating income"
                )
        else:
            rows["gm_trend_pp"].cells[label] = Cell(None, "missing: no base year")
            rows["opex_vs_sales"].cells[label] = Cell(None, "missing: no base year")
        rows["roic"].cells[label] = roic(ric, end, prev_end(end), oi)
    if gp_derived:
        rows["gm"].note = "gross profit derived (revenue − cost of revenue): no gross-profit tag"
    signals = _signals(engine, norm, as_of, rows, labels, shown, rev, gp, cost, oi, capex_years)
    return TrendsView(labels, list(rows.values()), signals, gp_derived)


# --- ROIC (S6.5) ---------------------------------------------------------------------------

_IC_TERMS = (
    ("equity", 1, True),
    ("long_term_debt", 1, False),
    ("debt_current", 1, False),
    ("cash", -1, True),
    ("short_term_investments", -1, False),
)


def roic_inputs(engine: sqlite3.Connection, cik: str, as_of: str) -> dict[str, dict]:
    """Points read once per company: balance-sheet terms, pretax income and tax."""
    out = {name: fy_points(engine, cik, name, as_of, "I") for name, _, _ in _IC_TERMS}
    out["pretax_income"] = fy_points(engine, cik, "pretax_income", as_of)
    out["income_tax"] = fy_points(engine, cik, "income_tax", as_of)
    return out


def invested_capital(inputs: dict[str, dict], end: str) -> tuple[float | None, str]:
    total, absent = 0.0, []
    for name, sign, required in _IC_TERMS:
        p = at(inputs[name], end)
        if p is None:
            if required:
                return None, f"missing: {name} at {end}"
            absent.append(name)
            continue
        total += sign * float(p.value)
    how = "equity + LT debt + current debt − cash − ST investments"
    if absent:
        how += f"; no fact: {', '.join(absent)} (taken as none on the balance sheet)"
    return total, how


def roic(inputs: dict[str, dict], end: str, prev: str | None, oi: dict[str, AsOfPoint]) -> Cell:
    o = at(oi, end)
    if o is None:
        return Cell(None, "missing: operating income")
    if prev is None:
        return Cell(None, "missing: no opening invested capital")
    pre, tax = at(inputs["pretax_income"], end), at(inputs["income_tax"], end)
    if pre is None:
        return Cell(None, "missing: pretax income")
    if pre.value <= 0:
        nopat, how_tax = float(o.value), "pretax ≤ 0: NOPAT = operating income"
    elif tax is None:
        return Cell(None, "missing: income tax")
    else:
        rate = min(max(float(tax.value) / float(pre.value), 0.0), TAX_CAP)
        nopat, how_tax = float(o.value) * (1 - rate), f"tax rate {rate:.1%} (bounded 0–35%)"
    ic1, how1 = invested_capital(inputs, end)
    ic0, how0 = invested_capital(inputs, prev)
    if ic1 is None or ic0 is None:
        return Cell(None, how1 if ic1 is None else how0)
    avg = (ic1 + ic0) / 2
    if avg <= 0:
        return Cell(None, f"{NM}: average invested capital ≤ 0 ({avg / 1e6:,.0f}M)")
    return Cell(nopat / avg, f"{how_tax}; {how1}", o.filed, o.accession)


# --- Signals ---------------------------------------------------------------------------------


def _own(row: Row) -> str:
    vals = [c.value for c in row.cells.values() if c.value is not None]
    if len(vals) < 3:
        return "own history: fewer than 3 years"
    scale = 100 if row.unit == "pct" else 1
    unit = "%" if row.unit == "pct" else " pp"
    return (
        f"own {len(vals)}-yr median {statistics.median(vals) * scale:+.1f}{unit}, "
        f"range {min(vals) * scale:+.1f}…{max(vals) * scale:+.1f}{unit}"
    )


def _signals(engine, cik, as_of, rows, labels, ends, rev, gp, cost, oi, capex_years):
    out: list[Signal] = []
    if not ends:
        for name in ("rev_yoy", "rev_cagr3", "fcf_growth", "fcf_growth_oe", "gm_trend_pp",
                     "opex_vs_sales"):  # fmt: skip
            out.append(Signal(name, None, None, "no fiscal-year revenue stored", "", (), as_of))
        return out
    last_end, last = ends[-1], labels[-1]
    srcs = tuple(
        (p.accession, p.filed) for p in (at(rev, last_end), at(oi, last_end)) if p is not None
    )
    newest = max((f for _, f in srcs), default=last_end)
    peer = PEER_TOKEN

    # TTM-based rows when a TTM a year earlier exists, else fiscal years.
    ttm_rev = fy_points(engine, cik, "revenue", as_of, "TTM")
    ttm_gp = fy_points(engine, cik, "gross_profit", as_of, "TTM")
    ttm_cost = fy_points(engine, cik, "cost_of_revenue", as_of, "TTM")
    ttm_oi = fy_points(engine, cik, "operating_income", as_of, "TTM")
    t_end = max(ttm_rev) if ttm_rev else None
    t_prev = _prior(ttm_rev, t_end) if t_end else None

    def add(name: str, cell: Cell, method: str, as_of_: str, sources) -> None:
        if cell.value is not None:
            out.append(Signal(name, round(cell.value, 6), None, None, method, sources, as_of_))
        elif cell.text.startswith(NM):
            out.append(Signal(name, None, NM, None, f"{cell.text}; {method}", sources, as_of_))
        else:
            out.append(
                Signal(
                    name, None, None, cell.text.removeprefix("missing: "), method, sources, as_of_
                )
            )

    # rev_yoy
    if t_end and t_prev is not None and t_end > last_end:
        now_p = ttm_rev[t_end]
        cell = _growth(float(now_p.value), float(t_prev.value))
        add("rev_yoy", cell, f"TTM to {t_end} vs TTM to {t_prev.end}; {_own(rows['rev_yoy'])}; "
            f"{peer}", now_p.filed, ((now_p.accession, now_p.filed),))  # fmt: skip
    else:
        add("rev_yoy", rows["rev_yoy"].cells[last], f"{last} vs prior fiscal year; "
            f"{_own(rows['rev_yoy'])}; {peer}", newest, srcs)  # fmt: skip
    add("rev_cagr3", rows["rev_cagr3"].cells[last], f"{last} vs 3 fiscal years earlier; {peer}",
        newest, srcs)  # fmt: skip

    cy = capex_years.get(last)
    csrc = srcs + (((cy.total.accession, cy.total.filed),) if cy and cy.total else ())
    cnew = max([newest] + ([cy.filed] if cy and cy.filed else []))
    add("fcf_growth", rows["fcf_growth"].cells[last], f"{last}: (OCF − total capex) vs prior year; "
        f"total capex = own-history series (D-M04-78); {_own(rows['fcf_growth'])}; {peer}",
        cnew, csrc)  # fmt: skip
    add("fcf_growth_oe", rows["fcf_growth_oe"].cells[last], f"{last}: owner earnings (OCF − "
        f"maintenance capex − SBC, D-M04-6) vs prior year; {_own(rows['fcf_growth_oe'])}; {peer}",
        cnew, csrc)  # fmt: skip

    # gm_trend_pp: 4-quarter change on TTM, 3-year change on fiscal years in the method.
    def gm_at(revp, gpp, costp, end):
        g, how, _ = _gross(revp, gpp, costp, end)
        r = _pt(at(revp, end))
        return ((g / r * 100) if g is not None and r else None), how

    g3 = rows["gm"].cells
    three = ""
    if len(labels) >= 4 and g3[labels[-1]].value is not None and g3[labels[-4]].value is not None:
        three = f"3-yr change {g3[labels[-1]].value - g3[labels[-4]].value:+.1f} pp"
    else:
        three = "3-yr change: missing"
    if t_end and t_prev is not None:
        a, how = gm_at(ttm_rev, ttm_gp, ttm_cost, t_end)
        b, _ = gm_at(ttm_rev, ttm_gp, ttm_cost, t_prev.end)
        cell = (
            Cell(a - b)
            if a is not None and b is not None
            else Cell(None, "missing: TTM gross margin")
        )
        add("gm_trend_pp", cell, f"4-quarter change, TTM to {t_end} vs {t_prev.end} ({how}); "
            f"{three}; {peer}", ttm_rev[t_end].filed, ((ttm_rev[t_end].accession,
            ttm_rev[t_end].filed),))  # fmt: skip
    else:
        add("gm_trend_pp", rows["gm_trend_pp"].cells[last], f"{last} vs prior fiscal year "
            f"(no TTM); {three}; {peer}", newest, srcs)  # fmt: skip

    # opex_vs_sales
    if t_end and t_prev is not None:
        g1, _, _ = _gross(ttm_rev, ttm_gp, ttm_cost, t_end)
        g0, _, _ = _gross(ttm_rev, ttm_gp, ttm_cost, t_prev.end)
        o1, o0 = _pt(at(ttm_oi, t_end)), _pt(at(ttm_oi, t_prev.end))
        if None in (g1, g0, o1, o0):
            cell = Cell(None, "missing: TTM gross profit or operating income")
        else:
            go = _growth(g1 - o1, g0 - o0)
            gr = _growth(float(ttm_rev[t_end].value), float(t_prev.value))
            cell = (Cell((go.value - gr.value) * 100) if go.value is not None
                    and gr.value is not None else Cell(None, go.text or gr.text))  # fmt: skip
        add("opex_vs_sales", cell, f"TTM to {t_end} vs {t_prev.end}: opex (gross profit − "
            f"operating income) growth − revenue growth; {peer}", ttm_rev[t_end].filed,
            ((ttm_rev[t_end].accession, ttm_rev[t_end].filed),))  # fmt: skip
    else:
        add("opex_vs_sales", rows["opex_vs_sales"].cells[last], f"{last} vs prior fiscal year; "
            f"{peer}", newest, srcs)  # fmt: skip
    return out
