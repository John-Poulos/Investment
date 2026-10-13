"""Capex the way each use needs it, and the maintenance/growth split (M04 Part 1b).

Three definitions, one per use (D-M04-3, D-M04-78):

- **Company definition (display):** M02's recipe from `moneyflow/actuals.py` (clause-derived,
  `config/capex_definitions.toml` overrides, approximate label and shown-actual rule;
  D-M02-29, -32, -34), so the Money flow and Financials tabs show one value.
- **Total capex (own history):** one consistent tag series. Tags fall in two
  definitions: PP&E payments (`PaymentsToAcquirePropertyPlantAndEquipment`, the IFRS
  equivalent) and the broader productive-assets tag (`PaymentsToAcquireProductiveAssets`,
  NVIDIA's extension `nvda:PurchasesOfPropertyAndEquipmentAndIntangibleAssets` for
  FY2013–21 — same caption, so one definition across the switch). The definition that
  covers more of the displayed window (the last 8 fiscal years with capex) is the series,
  tie → PP&E tag (Part 1b live check 1: Amazon's older PP&E-tag years must not push the
  window off the broader tag); a year filled from the other one reads "definition
  changed" and is not scored. A broader tag carries the marker "broader tag: <what it
  adds>" (and its gap to the PP&E tag where both exist: Amazon FY2016 +15.8%), worded
  apart from M02's "≈, gap X%". Consumers (FCF, runway, Q2 capex row) use this series.
- **Peers:** PP&E tag only; fallback-only names are "not like-for-like" (Part 2).

Capex split (D-M04-6): disclosed → project-level → depreciation (default, capped at total
capex) → D&A (marked last rung) → "not split"; one rung per company for the displayed
window, named on every value. The disclosed and project-level rungs have no finder yet
(Part 1b), so they are never found. Greenwald beside it as a cross-check only: average of
the yearly PP&E ÷ revenue ratios over the five prior years × the revenue change; shown on
net and on gross PP&E only when inside 0…total capex, else counted "out of range". A
depreciation fall ≥ 20%† while gross PP&E grows marks that year's depreciation rung
"useful-life change?" (S2.7; Intel 2023 −29.5%). Owner earnings = OCF − maintenance capex
− SBC; information only. Missing stays missing, never zero (D-M04-9).
"""

from __future__ import annotations

import calendar
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

from engine.calls.transcripts import _fye
from engine.moneyflow.actuals import (
    Actual,
    Book,
    actual_for,
    latest_clause,
    overrides_by_cik,
    recipe_for,
)
from engine.moneyflow.periods import fiscal_year_end
from engine.moneyflow.stated import stated_for
from engine.sec.asof import AsOfPoint, facts_as_of
from engine.sec.identity import normalize_cik
from engine.sec.xbrl_facts import ALIASES, Concept

WINDOW = 8  # fiscal years shown and counted (MU: Greenwald out of range in 6 of 8)
GREENWALD_YEARS = 5
USEFUL_LIFE_DROP = 0.20  # starting value (S2.7)
NEAR_DAYS = 10

PPE_TAGS = (
    ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
    ("ifrs-full", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),
)
PRODUCTIVE_TAGS = (("us-gaap", "PaymentsToAcquireProductiveAssets"),)
PRODUCTIVE_ADDS = "includes software and intangibles"
DA_TAGS = (
    ("us-gaap", "DepreciationDepletionAndAmortization"),
    ("us-gaap", "DepreciationAmortizationAndAccretionNet"),
    ("ifrs-full", "DepreciationAndAmortisationExpense"),
)
RUNG_METHOD = {
    "depreciation": "depreciation, capped at total capex",
    "da": "D&A, capped at total capex (last rung: includes amortization)",
    "not_split": "not split",
}


def _concept(name: str, tags: tuple[tuple[str, str], ...], kind: str = "flow") -> Concept:
    return Concept(name, tags, "currency", kind)


def fiscal_label(end: str) -> str:
    """FY label = the year the fiscal year ends in; an end in the first week of January
    belongs to the year before (52/53-week years, as `calls.transcripts._fye`)."""
    return f"FY{(date.fromisoformat(end) - timedelta(days=7)).year}"


def near(a: str, b: str, days: int = NEAR_DAYS) -> bool:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days) <= days


def at(points: dict[str, AsOfPoint], end: str) -> AsOfPoint | None:
    """The point whose end lies within ten days of `end`."""
    if end in points:
        return points[end]
    return next((p for e, p in points.items() if near(e, end)), None)


def is_fy_end(end: str, fye: str | None) -> bool:
    """The date lies within ten days of the company's fiscal year end (Amazon's 10-Qs carry
    trailing-twelve-month cash flows that look like fiscal years, D-M02-34 (3)). Unknown
    year end → accepted."""
    f = _fye(fye)
    if f is None:
        return True
    d = date.fromisoformat(end)
    month, day = f
    for year in (d.year - 1, d.year, d.year + 1):
        target = date(year, month, min(day, calendar.monthrange(year, month)[1]))
        if abs((d - target).days) <= NEAR_DAYS:
            return True
    return False


def fy_points(
    engine: sqlite3.Connection, cik: str, concept: str | Concept, as_of: str, ptype: str = "FY"
) -> dict[str, AsOfPoint]:
    """Points by end date; fiscal-year flows and year-end instants only end at the fiscal
    year end (`ptype` 'FY' or 'I'); 'TTM' and 'Q' are returned as they are."""
    pts = facts_as_of(engine, cik, concept, as_of, ptype=ptype).points
    if ptype == "FY":
        fye = fiscal_year_end(engine, cik)
        pts = tuple(p for p in pts if is_fy_end(p.end, fye))
    return {p.end: p for p in pts}


# --- Total capex: the own-history series (D-M04-3, D-M04-78) -----------------------------


@dataclass(frozen=True)
class Definition:
    key: str  # ppe | productive
    label: str
    tags: tuple[tuple[str, str, str], ...]  # (taxonomy, tag, mark)


def definitions(cik: str) -> tuple[Definition, Definition]:
    ext = tuple(
        (a.taxonomy, a.tag, a.mark.removeprefix("≈ "))
        for a in ALIASES.get(normalize_cik(cik) or cik, ())
        if a.concept == "capex"
    )
    ppe = Definition("ppe", "PP&E payments", tuple((t, g, "") for t, g in PPE_TAGS))
    prod = Definition(
        "productive",
        "productive assets (broader)",
        tuple((t, g, f"broader tag: {PRODUCTIVE_ADDS}") for t, g in PRODUCTIVE_TAGS) + ext,
    )
    return ppe, prod


@dataclass(frozen=True)
class TotalCapex:
    end: str
    label: str
    value: float
    tag: str  # taxonomy:tag
    mark: str  # "broader tag: …" or ""
    accession: str
    filed: str
    definition: str  # ppe | productive
    definition_changed: bool
    note: str  # "definition changed: …", "+15.8% vs the PP&E tag"


def _per_definition(
    engine: sqlite3.Connection, cik: str, d: Definition, as_of: str
) -> dict[str, tuple[AsOfPoint, str, str]]:
    """end → (point, taxonomy:tag, mark), first tag of the definition with a value."""
    out: dict[str, tuple[AsOfPoint, str, str]] = {}
    for tax, tag, mark in d.tags:
        for end, p in fy_points(
            engine, cik, _concept(f"{tax}:{tag}", ((tax, tag),)), as_of
        ).items():
            if at({e: v[0] for e, v in out.items()}, end) is None:
                out[end] = (p, f"{tax}:{tag}", mark)
    return out


def total_capex(
    engine: sqlite3.Connection, cik: str, as_of: str, window: int = WINDOW
) -> list[TotalCapex]:
    """Fiscal-year total capex, oldest first, on the definition that covers the displayed
    window (the last `window` fiscal years with capex) in more years; tie → PP&E tag."""
    ppe_def, prod_def = definitions(cik)
    series = {
        "ppe": _per_definition(engine, cik, ppe_def, as_of),
        "productive": _per_definition(engine, cik, prod_def, as_of),
    }
    labels = {"ppe": ppe_def.label, "productive": prod_def.label}
    ends: list[str] = []
    for end in sorted(set(series["ppe"]) | set(series["productive"])):
        if not any(near(end, e) for e in ends):
            ends.append(end)
    shown = ends[-window:]

    def covered(key: str) -> int:
        pts = {e: v[0] for e, v in series[key].items()}
        return sum(1 for e in shown if at(pts, e) is not None)

    main = "productive" if covered("productive") > covered("ppe") else "ppe"
    other = "ppe" if main == "productive" else "productive"
    out = []
    for end in sorted(ends):
        hit = at({e: v[0] for e, v in series[main].items()}, end)
        changed = hit is None
        src = series[other] if changed else series[main]
        key = next(e for e in src if near(e, end))
        point, tag, mark = src[key]
        note = ""
        if changed:
            note = f"definition changed: {labels[other]} this year (not scored)"
        elif main == "productive":
            ppe = at({e: v[0] for e, v in series["ppe"].items()}, end)
            if ppe is not None and ppe.value:
                note = (
                    f"{point.value / ppe.value - 1:+.1%} vs the PP&E tag ({ppe.value / 1e6:,.0f}M)"
                )
        out.append(
            TotalCapex(end, fiscal_label(end), float(point.value), tag, mark, point.accession,
                       point.filed, other if changed else main, changed, note)
        )  # fmt: skip
    return out


# --- The year table ------------------------------------------------------------------------


@dataclass
class CapexYear:
    end: str
    label: str
    total: TotalCapex | None
    display: Actual | None = None
    display_label: str = ""
    depreciation: float | None = None
    depreciation_ref: str = ""
    da: float | None = None
    rung: str = "not_split"
    rung_value: float | None = None
    maintenance: float | None = None
    growth: float | None = None
    method: str = ""
    marks: list[str] = field(default_factory=list)
    greenwald_net: float | None = None  # maintenance, raw (may be out of range)
    greenwald_gross: float | None = None
    greenwald_net_note: str = ""
    greenwald_gross_note: str = ""
    ocf: float | None = None
    sbc: float | None = None
    revenue: float | None = None
    filed: str = ""  # newest input filing date

    @property
    def gw_net_in(self) -> bool:
        return _in_range(self.greenwald_net, self.total)

    @property
    def gw_gross_in(self) -> bool:
        return _in_range(self.greenwald_gross, self.total)

    @property
    def fcf_total(self) -> float | None:
        if self.ocf is None or self.total is None:
            return None
        return self.ocf - self.total.value

    @property
    def fcf_maintenance(self) -> float | None:
        if self.ocf is None or self.maintenance is None:
            return None
        return self.ocf - self.maintenance

    @property
    def owner_earnings(self) -> float | None:
        if self.ocf is None or self.maintenance is None or self.sbc is None:
            return None
        return self.ocf - self.maintenance - self.sbc

    def missing(self, what: str) -> str:
        """Why a derived row is empty this year ("" when it has a value)."""
        if self.total is None:
            return "no total capex"
        needs = {
            "fcf_total": ("ocf",),
            "maintenance": ("maintenance",),
            "growth": ("maintenance",),
            "fcf_maintenance": ("maintenance", "ocf"),
            "owner_earnings": ("maintenance", "ocf", "sbc"),
        }[what]
        why = {
            "ocf": "no operating cash flow fact",
            "sbc": "no share-based compensation fact",
            "maintenance": self.method or "not split",
        }
        for n in needs:
            if getattr(self, n) is None:
                return why[n]
        return ""


def _in_range(maint: float | None, total: TotalCapex | None) -> bool:
    return maint is not None and total is not None and 0 <= maint <= total.value


@dataclass
class CapexView:
    cik: str
    years: list[CapexYear]
    rung: str
    recipe_label: str
    gw_net_out: tuple[int, int]  # (out of range, computable)
    gw_gross_out: tuple[int, int]
    definition: str  # label of the own-history definition
    definition_mark: str
    changed_years: list[str]

    def gw_line(self, which: str) -> str:
        out, n = self.gw_net_out if which == "net" else self.gw_gross_out
        if n == 0:
            return f"Greenwald ({which} PP&E): not computable (needs {GREENWALD_YEARS} prior years)"
        return f"Greenwald ({which} PP&E): out of range in {out} of {n} years"


_NET_STATED = re.compile(r"\bnet (?:capex|capital expenditures?|cap ex)\b", re.IGNORECASE)


def display_label(a: Actual) -> str:
    """'stated net capex' / 'stated capex' / the M02 label (D-M02-32 shown-actual rule)."""
    if a.source == "stated" and a.stated is not None:
        what = "net capex" if _NET_STATED.search(a.stated.quote or "") else "capex"
        src = f"{a.stated.origin} · {a.stated.grade}"
        return f"stated {what} ({src}); {a.label}"
    if a.recipe is not None:
        return f"{a.recipe.recipe.label}; {a.label}" + (
            f"; {a.recipe.note}" if a.recipe.note else ""
        )
    return a.label


def _greenwald(
    t: int,
    ends: list[str],
    revenue: dict[str, AsOfPoint],
    ppe: dict[str, AsOfPoint],
    total: float,
) -> tuple[float | None, str]:
    """Maintenance by Greenwald for year index t: capex − avg(PP&E/revenue over the five
    prior years) × (revenue_t − revenue_t−1)."""
    if t < GREENWALD_YEARS:
        return None, f"needs {GREENWALD_YEARS} prior years"
    ratios = []
    for e in ends[t - GREENWALD_YEARS : t]:
        r, p = at(revenue, e), at(ppe, e)
        if r is None or p is None or not r.value or r.value <= 0:
            return None, f"missing revenue or PP&E at {e}"
        ratios.append(p.value / r.value)
    r_now, r_prev = at(revenue, ends[t]), at(revenue, ends[t - 1])
    if r_now is None or r_prev is None:
        return None, "missing revenue"
    growth = sum(ratios) / len(ratios) * (r_now.value - r_prev.value)
    maint = total - growth
    if not 0 <= maint <= total:
        return maint, f"out of range ({maint / 1e6:,.0f}M vs 0…{total / 1e6:,.0f}M)"
    return maint, ""


def capex_view(
    engine: sqlite3.Connection,
    cik: str,
    as_of: str,
    *,
    window: int = WINDOW,
    corpus: sqlite3.Connection | None = None,
) -> CapexView:
    """Total capex, company definition, split and FCF rows for the last `window` years."""
    norm = normalize_cik(cik) or cik
    totals = total_capex(engine, norm, as_of)
    rev = fy_points(engine, norm, "revenue", as_of)
    ppe_net = fy_points(engine, norm, "ppe_net", as_of, "I")
    ppe_gross = fy_points(engine, norm, "ppe_gross", as_of, "I")
    dep = fy_points(engine, norm, "depreciation", as_of)
    da = fy_points(engine, norm, _concept("d_and_a", DA_TAGS), as_of)
    ocf = fy_points(engine, norm, "operating_cash_flow", as_of)
    sbc = fy_points(engine, norm, "sbc", as_of)

    # Greenwald needs prior years beyond the window: the year axis = every revenue year.
    axis = sorted(set(rev) | {t.end for t in totals})
    axis = [e for i, e in enumerate(axis) if not any(near(e, x) for x in axis[:i])]
    shown = totals[-window:]
    override = overrides_by_cik(engine).get(norm)
    clause = latest_clause(engine, norm)
    book = Book(engine, norm)
    stated = stated_for(engine, norm)

    years: list[CapexYear] = []
    for tc in shown:
        y = CapexYear(tc.end, tc.label, tc)
        a = actual_for(book, tc.label, clause, override, stated)
        if a.shown is not None:
            y.display, y.display_label = a, display_label(a)
        d, x = at(dep, tc.end), at(da, tc.end)
        y.depreciation = float(d.value) if d else None
        y.depreciation_ref = f"{d.method.split(';')[0]} · {d.accession}" if d else ""
        y.da = float(x.value) if x else None
        o, s, r = at(ocf, tc.end), at(sbc, tc.end), at(rev, tc.end)
        y.ocf = float(o.value) if o else None
        y.sbc = float(s.value) if s else None
        y.revenue = float(r.value) if r else None
        y.filed = max([tc.filed] + [p.filed for p in (d, o, s) if p is not None])
        idx = next((i for i, e in enumerate(axis) if near(e, tc.end)), None)
        if idx is not None:
            y.greenwald_net, y.greenwald_net_note = _greenwald(idx, axis, rev, ppe_net, tc.value)
            y.greenwald_gross, y.greenwald_gross_note = _greenwald(
                idx, axis, rev, ppe_gross, tc.value
            )
        years.append(y)

    # One rung for the window: the highest rung with a value in the latest year.
    latest = years[-1] if years else None
    if latest is not None and latest.depreciation is not None:
        rung = "depreciation"
    elif latest is not None and latest.da is not None:
        rung = "da"
    else:
        rung = "not_split"
    for i, y in enumerate(years):
        base = y.depreciation if rung == "depreciation" else y.da if rung == "da" else None
        y.rung = rung
        if rung == "not_split":
            y.method = (
                "not split: no depreciation or D&A fact "
                "(disclosed and project-level rungs have no finder yet)"
            )
        elif base is None:
            what = "depreciation" if rung == "depreciation" else "D&A"
            y.method = f"not split: no {what} fact this year (window rung: {RUNG_METHOD[rung]})"
        else:
            y.rung_value = base
            y.maintenance = min(base, y.total.value) if y.total else None
            y.growth = (
                (y.total.value - y.maintenance) if y.total and y.maintenance is not None else None
            )
            y.method = RUNG_METHOD[rung] + (" (capped)" if y.total and base > y.total.value else "")
        if rung == "depreciation" and i > 0:
            prev = years[i - 1]
            g_now, g_prev = at(ppe_gross, y.end), at(ppe_gross, prev.end)
            if (
                y.depreciation is not None
                and prev.depreciation
                and g_now is not None
                and g_prev is not None
                and y.depreciation / prev.depreciation - 1 <= -USEFUL_LIFE_DROP
                and g_now.value > g_prev.value
            ):
                drop = y.depreciation / prev.depreciation - 1
                y.marks.append(
                    f"useful-life change? depreciation {drop:+.1%} "
                    f"while gross PP&E {g_now.value / g_prev.value - 1:+.1%} (S2.7)"
                )
        if y.total and y.total.definition_changed:
            y.marks.append(y.total.note)

    def count(attr: str) -> tuple[int, int]:
        vals = [(getattr(y, attr), y) for y in years]
        n = [(v, y) for v, y in vals if v is not None]
        return sum(1 for v, y in n if not _in_range(v, y.total)), len(n)

    ppe_def, prod_def = definitions(norm)
    main = next((t.definition for t in totals if not t.definition_changed), "ppe")
    main_label = prod_def.label if main == "productive" else ppe_def.label
    marks = sorted({t.mark for t in shown if t.mark and not t.definition_changed})
    return CapexView(
        cik=norm,
        years=years,
        rung=rung,
        recipe_label=recipe_for(clause, override).label,
        gw_net_out=count("greenwald_net"),
        gw_gross_out=count("greenwald_gross"),
        definition=main_label,
        definition_mark="; ".join(marks),
        changed_years=[t.label for t in shown if t.definition_changed],
    )


def store_split(engine: sqlite3.Connection, view: CapexView, now: str) -> int:
    """Replace the company's `capex_split` rows. Caller owns the transaction."""
    engine.execute("DELETE FROM capex_split WHERE cik = ?", (view.cik,))
    rows = []
    for y in view.years:
        t = y.total
        gn = y.greenwald_net if y.gw_net_in else None
        gg = y.greenwald_gross if y.gw_gross_in else None
        notes = "; ".join(
            f"{w}: {n}"
            for w, n in (("net", y.greenwald_net_note), ("gross", y.greenwald_gross_note))
            if n
        )
        rows.append((
            view.cik, y.end, y.label, t.value if t else None,
            (f"{t.tag}" + (f" [{t.mark}]" if t.mark else "")) if t else None,
            t.accession if t else None, t.filed if t else None,
            1 if t and t.definition_changed else 0, y.maintenance, y.growth, y.method, y.rung,
            y.rung_value, gn, gg, notes or None, "; ".join(y.marks) or None, now,
        ))  # fmt: skip
    engine.executemany(
        "INSERT INTO capex_split (cik, period_end, fiscal_label, total, total_tag, "
        "total_accession, total_filed, definition_changed, maintenance, growth, method, rung, "
        "rung_value, greenwald_net, greenwald_gross, greenwald_note, marks, computed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)
