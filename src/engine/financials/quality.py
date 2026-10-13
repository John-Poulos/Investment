"""Earnings-quality scores (M04 Part 6; D-M04-14, -20, -90, -91; S2.1–S2.4; SB.12, SB.18).

Screens and persistence warnings, never return signals (D-M04-14). Every input is the value
**as first reported** in a periodic filing (the backtest reading, S1.1/S6.1), with its tag
and accession; missing stays missing, never zero (D-M04-9).

- `eq_cash`: 3-year CFO ÷ net income on the operating basis — net income less identified
  non-cash, non-operating items (securities and crypto fair-value gains taxed at 21% from
  2018, 35% before; the valuation-allowance change as reported) when they exceed 25%† of
  |net income| that year (S2.1). Not meaningful when the 3-year net income is ≤ 0 or below
  1% of revenue, and for `asset_treasury`. Stage routing (D-M04-20): < 0.8† warns for a
  confirmed mature or decline stage, a note for introduction, growth and shake-out; with no
  confirmed stage both readings are shown, labelled, not counted (D-M04-7).
- `eq_accruals`: cash-flow accruals (net income − CFO) ÷ average total assets against the
  company's own 5 prior years; shown, never a warning (D-M04-20).
- `mscore` / `mscore_sgi1`: Beneish M with the cash-flow ACCR, and with SGI = 1; the
  `m04_mscore` review opens only when the SGI = 1 version is above −1.78, else a raw M above
  −1.78 is a "growth-driven" note (D-M04-14). Incomplete when an input is missing; not
  meaningful when gross margin is ≤ 0 in either year or the company is `asset_treasury`.
- `misstate_f`: Dechow et al. (2011) Model 1, labelled "approximation"; bands > 1.00 and
  > 2.45 shown, never a trigger; `issue` with no proceeds tag for the year is unknown →
  missing, never 0 (D-M04-14, S2.4).
- `contract_asset_gap` / `deferred_rev_gap` (S2.2): fiscal-year readings; contract assets
  growing > 10 pp† faster than revenue in the latest 2 readings, or deferred revenue falling
  while revenue grows in the latest 2 readings → watch. A reading whose line changed tag
  (an alias such as GE's `ge:ContractAsset` → `UnbilledContractsReceivable`) reads
  "definition changed" and is not scored (D-M04-3 rule).
- Non-operating swings by tag (MSTR's bitcoin fair value, securities gains, valuation-
  allowance changes): shown with their share of net income, not scored (SB.12).

Optional balance-sheet lines (short- and long-term investments, current debt, preferred
stock, long-term debt) absent in both years are "none on the balance sheet (no tag)",
named in the method; present in one year only is a suspected tag switch → incomplete
(D-M04-90). DSO stays M02's (`financing/credit.dso`, D-M02-47): shown as context only.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from engine.financials.capex import fiscal_label, is_fy_end, near
from engine.financials.peers import GOODWILL, acquisition_note
from engine.moneyflow.periods import fiscal_year_end
from engine.sec.asof import FOREIGN_INTERIM_FORMS, PERIODIC_FORMS, is_foreign_filer
from engine.sec.identity import normalize_cik
from engine.sec.xbrl_facts import ALL_CONCEPTS, Concept, classify, concept_for, concept_rows

# Starting values (†), not tuned inside the build (D6).
M_CUT = -1.78  # Beneish: investigate above
F_BANDS = (1.00, 2.45)  # Dechow Model 1 score bands
CFO_NI_WARN = 0.8  # 3-year CFO/NI (D-M04-20)
NI_MIN_SHARE = 0.01  # |NI| below 1% of revenue → not meaningful (S2.1)
OPERATING_SWITCH = 0.25  # identified non-operating items above 25% of |NI| → operating basis
GAP_PP = 10.0  # contract assets faster than revenue (S2.2)
READINGS = 2
HISTORY_YEARS = 5

C, F, I = "currency", "flow", "instant"  # noqa: E741
# S&M: Amazon tags `MarketingExpense` (no selling line) beside G&A (live check 1)
SM = Concept(
    "selling_marketing",
    (("us-gaap", "SellingAndMarketingExpense"), ("us-gaap", "MarketingExpense")),
    C,
    F,
)
GA = Concept("general_admin", (("us-gaap", "GeneralAndAdministrativeExpense"),), C, F)
# Receivables for Part 6: the shared concept plus the IFRS trade-receivable variants
# (GlobalFoundries, live check 1). Local, so stored `series` rows do not change.
_REC = ALL_CONCEPTS["receivables"]
RECEIVABLES = Concept(
    "receivables",
    _REC.tags
    + tuple(
        ("ifrs-full", t)
        for t in (
            "CurrentTradeReceivables",
            "TradeAndOtherCurrentReceivablesDueFromRelatedParties",
            "TradeReceivables",
            "TradeAndOtherReceivables",
        )
    ),
    C,
    I,
    marks=_REC.marks,
)
LIAB_EQUITY = Concept(
    "liabilities_and_equity", (("us-gaap", "LiabilitiesAndStockholdersEquity"),), C, I
)
EQUITY_NCI = Concept(
    "equity_incl_nci",
    (
        ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        ("us-gaap", "StockholdersEquity"),
    ),
    C,
    I,
)
# Crypto fair-value lines (ASU 2023-08): gain/loss tags, + = gain. The older loss-only tag
# in EXTRA_CONCEPTS is read with its sign flipped.
CRYPTO_GAIN = Concept(
    "crypto_gain",
    (
        ("us-gaap", "CryptoAssetUnrealizedGainLossOperating"),
        ("us-gaap", "CryptoAssetUnrealizedGainLossNonoperating"),
        ("us-gaap", "CryptoAssetGainLoss"),
    ),
    C,
    F,
)
LOCAL = {c.name: c for c in (SM, GA, LIAB_EQUITY, EQUITY_NCI, CRYPTO_GAIN, RECEIVABLES, GOODWILL)}
# Totals a cost-of-revenue component sum is checked against (ORCL presents every cost as an
# operating expense, live check 1)
COST_TOTALS = ("CostsAndExpenses", "OperatingExpenses")
COST_TOTAL_TAGS = ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold")
OTHER_OPEX = (
    "SellingGeneralAndAdministrativeExpense",
    "SellingAndMarketingExpense",
    "MarketingExpense",
    "GeneralAndAdministrativeExpense",
    "ResearchAndDevelopmentExpense",
    "AmortizationOfIntangibleAssets",
    "RestructuringCharges",
    "AcquisitionRelatedCostsAndOtherOperatingExpenses",
    "OtherCostAndExpenseOperating",
)
SGA_PARTS = ("SellingAndMarketingExpense", "MarketingExpense", "GeneralAndAdministrativeExpense")
COST_MATCH = 0.005  # components + other lines within 0.5% of the total

# `issue` (D-M04-90): M02's financing roles "debt_raised" and "equity_issued" (built-ins
# and the owner's `fin_tag_map`, D-M02-31) plus the stock-plan and debt tags below.
ISSUE_EXTRA = tuple(
    f"us-gaap:{t}"
    for t in (
        "ProceedsFromIssuanceOfCommonStock",
        "ProceedsFromStockPlans",
        "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlans",
        "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlansIncludingStockOptions",
        "ProceedsFromStockOptionsExercised",
        "ProceedsFromEmployeeStockPurchasePlan",
        "ProceedsFromIssuanceOfLongTermDebt",
        "ProceedsFromIssuanceOfDebt",
        "ProceedsFromIssuanceOfSeniorLongTermDebt",
        "ProceedsFromDebtNetOfIssuanceCosts",
        "ProceedsFromIssuanceOfCommercialPaper",
        "ProceedsFromShortTermDebt",
    )
) + tuple(
    f"ifrs-full:{t}"  # IFRS filers (GlobalFoundries)
    for t in (
        "ProceedsFromIssuingShares",
        "ProceedsFromExerciseOfOptions",
        "ProceedsFromBorrowingsClassifiedAsFinancingActivities",
        "ProceedsFromNoncurrentBorrowings",
        "ProceedsFromCurrentBorrowings",
        "ProceedsFromIssueOfBondsNotesAndDebentures",
    )
)
ISSUE_ROLES = ("debt_raised", "equity_issued")

SWINGS = (
    ("equity_securities_gain", "gains on equity securities (fair value)", 1),
    ("crypto_gain", "digital-asset fair-value change (ASU 2023-08)", 1),
    ("crypto_unrealized", "digital-asset unrealized loss", -1),
    ("valuation_allowance_change", "valuation-allowance change (tax-rate reconciliation)", 0),
    ("nonoperating", "non-operating income (expense), total", 1),
)


def tax_rate(end: str) -> float:
    """21% from 2018, 35% before (labelled approximation, S2.1)."""
    return 0.21 if end >= "2018-01-01" else 0.35


@dataclass(frozen=True)
class Val:
    value: float
    tag: str  # taxonomy:tag
    accession: str
    filed: str
    form: str
    end: str
    start: str | None = None
    mark: str = ""

    def ref(self) -> str:
        return f"{self.tag} {self.accession}"


class Facts:
    """First-reported fiscal-year flows and year-end instants of one company, by concept."""

    def __init__(self, engine: sqlite3.Connection, cik: str) -> None:
        self.engine = engine
        self.cik = normalize_cik(cik) or cik
        self._fy: dict[str, dict[str, Val]] = {}
        self._inst: dict[str, dict[str, Val]] = {}
        self._allowed = set(PERIODIC_FORMS)
        if is_foreign_filer(engine, self.cik):
            self._allowed |= FOREIGN_INTERIM_FORMS
        self.fye = fiscal_year_end(engine, self.cik)
        self._ends: list[str] | None = None

    def _concept(self, name: str) -> Concept:
        return concept_for(self.cik, LOCAL.get(name) or ALL_CONCEPTS[name])

    def _load(self, name: str, instant: bool) -> dict[str, Val]:
        return self.load_concept(self._concept(name), instant)

    def fy_of(self, con: Concept) -> dict[str, Val]:
        """Fiscal-year values of any concept (not cached by name; e.g. one issuance tag)."""
        key = f"concept:{con.name}:{con.tags}"
        if key not in self._fy:
            pts = self.load_concept(con, instant=False)
            self._fy[key] = {e: v for e, v in pts.items() if is_fy_end(e, self.fye)}
        return self._fy[key]

    def load_concept(self, con: Concept, instant: bool) -> dict[str, Val]:
        rank = {t: i for i, t in enumerate(con.tags)}
        best: dict[str, tuple] = {}
        for r in concept_rows(self.engine, [self.cik], con):
            if r["form"] not in self._allowed or r["unit"] != "USD":
                continue
            if instant != (r["period_start"] is None):
                continue
            if not instant and classify(r["period_start"], r["period_end"]) != "FY":
                continue
            key = (r["filed"], rank[(r["taxonomy"], r["tag"])], r["accession"])
            cur = best.get(r["period_end"])
            if cur is None or key < cur[0]:
                best[r["period_end"]] = (key, r)
        out = {}
        for end, (_, r) in best.items():
            out[end] = Val(
                float(r["value"]),
                f"{r['taxonomy']}:{r['tag']}",
                r["accession"],
                r["filed"],
                r["form"] or "",
                end,
                r["period_start"],
                con.mark(r["taxonomy"], r["tag"]),
            )
        return out

    def fy(self, name: str) -> dict[str, Val]:
        if name not in self._fy:
            pts = self._load(name, instant=False)
            self._fy[name] = {e: v for e, v in pts.items() if is_fy_end(e, self.fye)}
        return self._fy[name]

    def inst(self, name: str) -> dict[str, Val]:
        if name not in self._inst:
            self._inst[name] = self._load(name, instant=True)
        return self._inst[name]

    def at(self, name: str, end: str, instant: bool = False) -> Val | None:
        pts = self.inst(name) if instant else self.fy(name)
        if end in pts:
            return pts[end]
        return next((v for e, v in pts.items() if near(e, end)), None)

    def reported_by(self, name: str, accession: str, end: str) -> bool:
        """The annual report `accession` tags the concept at (or near) `end`."""
        con = self._concept(name)
        return any(
            r["accession"] == accession and r["period_start"] is None and near(r["period_end"], end)
            for r in concept_rows(self.engine, [self.cik], con)
        )

    def ends(self) -> list[str]:
        """Fiscal year ends (first-reported revenue, else net income), oldest first."""
        if self._ends is None:
            pts = self.fy("revenue") or self.fy("net_income")
            self._ends = sorted(pts)
        return self._ends

    def prior(self, end: str) -> str | None:
        e = date.fromisoformat(end)
        return next(
            (p for p in reversed(self.ends()) if 350 <= (e - date.fromisoformat(p)).days <= 380),
            None,
        )

    def filing_of(self, end: str) -> tuple[str, str] | None:
        """(accession, filed) of the annual report that first reported the fiscal year."""
        v = self.at("revenue", end) or self.at("net_income", end)
        return (v.accession, v.filed) if v else None


# --- Input gathering ------------------------------------------------------------------------


@dataclass
class Inputs:
    """Values used by a score, with what was substituted and what is missing."""

    vals: dict[str, float] = field(default_factory=dict)
    used: list[Val] = field(default_factory=list)
    subs: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def take(self, key: str, v: Val | None, label: str) -> float | None:
        if v is None:
            self.missing.append(label)
            return None
        self.vals[key] = v.value
        self.used.append(v)
        if v.mark:
            self.subs.append(f"{label}: {v.tag} [{v.mark}]")
        return v.value

    def put(self, key: str, value: float | None, label: str) -> float | None:
        if value is None:
            self.missing.append(label)
            return None
        self.vals[key] = value
        return value

    def method(self) -> str:
        parts = []
        if self.subs:
            parts.append("substitutions: " + "; ".join(dict.fromkeys(self.subs)))
        return "; ".join(parts)


def _year(fx: Facts, end: str) -> str:
    return fiscal_label(end)


def sga(fx: Facts, end: str) -> tuple[Val | None, str]:
    """SG&A; else selling and marketing (or marketing) + general and administrative; else
    G&A alone, labelled "G&A only" (Boeing tags no selling line). Method-tagged."""
    v = fx.at("sga", end)
    if v is not None:
        return v, ""
    sm, ga = fx.at("selling_marketing", end), fx.at("general_admin", end)
    if sm is not None and ga is not None:
        what = "marketing" if sm.tag.endswith(":MarketingExpense") else "S&M"
        return (
            Val(
                sm.value + ga.value,
                f"{sm.tag} + {ga.tag}",
                sm.accession,
                sm.filed,
                sm.form,
                end,
                sm.start,
            ),
            f"SG&A = {what} + G&A",
        )
    if ga is not None and sm is None:
        return ga, "SG&A = G&A only (no selling or marketing tag)"
    return None, ""


def depreciation(fx: Facts, end: str) -> tuple[Val | None, str]:
    v = fx.at("depreciation", end)
    if v is not None:
        return v, ""
    v = fx.at("da", end)
    return (v, "D&A for depreciation") if v is not None else (None, "")


def cogs(fx: Facts, end: str) -> tuple[Val | None, str]:
    v = fx.at("cost_of_revenue", end)
    if v is not None:
        return v, ""
    rev, gp = fx.at("revenue", end), fx.at("gross_profit", end)
    if rev is not None and gp is not None:
        return (
            Val(
                rev.value - gp.value,
                f"{rev.tag} − {gp.tag}",
                gp.accession,
                gp.filed,
                gp.form,
                end,
                gp.start,
            ),
            "cost of revenue = revenue − gross profit",
        )
    return cost_components(fx, end)


def _fy_rows(fx: Facts, end: str, where: str, args: tuple) -> list[sqlite3.Row]:
    """us-gaap fiscal-year facts at `end` from the report that first reported the year."""
    f = fx.filing_of(end)
    if f is None:
        return []
    rows = fx.engine.execute(
        "SELECT tag, value, period_start, period_end, accession, filed, form FROM fact WHERE "
        f"cik = ? AND taxonomy = 'us-gaap' AND unit = 'USD' AND accession = ? AND {where}",
        (fx.cik, f[0], *args),
    ).fetchall()
    return [
        r
        for r in rows
        if r["period_start"]
        and near(r["period_end"], end)
        and classify(r["period_start"], r["period_end"]) == "FY"
    ]


def cost_components(fx: Facts, end: str) -> tuple[Val | None, str]:
    """No cost-of-revenue or gross-profit tag: the sum of the year's `CostOf…` lines, taken
    only when it is unambiguous — those lines plus the other tagged operating lines equal a
    tagged total (`CostsAndExpenses`, else `OperatingExpenses`) within 0.5%. Otherwise
    missing, with the reason in the method (ORCL, live check 1)."""
    rows = _fy_rows(fx, end, "tag LIKE 'CostOf%'", ())
    parts = {r["tag"]: r for r in rows if r["tag"] not in COST_TOTAL_TAGS}
    if not parts:
        return None, "no CostOfRevenue, GrossProfit or CostOf… tag"
    marks = ",".join("?" * (len(COST_TOTALS) + len(OTHER_OPEX)))
    more = {
        r["tag"]: r for r in _fy_rows(fx, end, f"tag IN ({marks})", (*COST_TOTALS, *OTHER_OPEX))
    }
    total = next((more[t] for t in COST_TOTALS if t in more), None)
    names = " + ".join(sorted(parts))
    comp = sum(float(r["value"]) for r in parts.values())
    if total is None:
        return None, (
            f"CostOf… lines {names} but no CostsAndExpenses "
            "or OperatingExpenses total to check them against (ambiguous)"
        )
    others = [more[t] for t in OTHER_OPEX if t in more]
    if "SellingGeneralAndAdministrativeExpense" in more:
        others = [r for r in others if r["tag"] not in SGA_PARTS]
    check = comp + sum(float(r["value"]) for r in others)
    tv = float(total["value"])
    if not tv or abs(check - tv) > COST_MATCH * abs(tv):
        return None, (
            f"CostOf… lines {names} {comp / 1e6:,.0f}M + "
            f"other operating lines {(check - comp) / 1e6:,.0f}M ≠ {total['tag']} "
            f"{tv / 1e6:,.0f}M (ambiguous)"
        )
    r0 = next(iter(parts.values()))
    return (
        Val(
            comp,
            " + ".join(f"us-gaap:{t}" for t in sorted(parts)),
            r0["accession"],
            r0["filed"],
            r0["form"] or "",
            end,
            r0["period_start"],
        ),  # fmt: skip
        f"cost of revenue = sum of CostOf… lines ({names}), checked against {total['tag']}",
    )


def liabilities(fx: Facts, end: str) -> tuple[Val | None, str]:
    v = fx.at("total_liabilities", end, instant=True)
    if v is not None:
        return v, ""
    le, eq = fx.at("liabilities_and_equity", end, True), fx.at("equity_incl_nci", end, True)
    if le is not None and eq is not None:
        return (
            Val(le.value - eq.value, f"{le.tag} − {eq.tag}", le.accession, le.filed, le.form, end),
            "total liabilities = liabilities and equity − equity incl. NCI",
        )
    return None, ""


def cash_at(fx: Facts, end: str) -> tuple[Val | None, str]:
    """Cash and equivalents at a year end; else the gate's fallbacks (D-M04-32, Part 4a live
    check 1): the cash-flow total including restricted cash minus restricted cash tagged at
    the date, else `us-gaap:Cash`; labelled."""
    from engine.financials.gate import CASH_ONLY, CASH_WITH_RESTRICTED

    v = fx.at("cash", end, instant=True)
    if v is not None:
        return v, ""
    pts = fx.load_concept(CASH_WITH_RESTRICTED, instant=True)
    cr = pts.get(end) or next((x for e, x in pts.items() if near(e, end)), None)
    if cr is not None:
        rc = fx.at("restricted_cash", end, instant=True)
        if rc is not None:
            return (
                Val(
                    cr.value - rc.value,
                    f"{cr.tag} − {rc.tag}",
                    cr.accession,
                    cr.filed,
                    cr.form,
                    end,
                ),  # fmt: skip
                f"cash {fiscal_label(end)} = cash incl. restricted {money(cr.value)}M − "
                f"restricted {money(rc.value)}M (fallback: no cash-and-equivalents tag)",
            )
        return cr, (
            f"cash {fiscal_label(end)} = {cr.tag} (fallback: no cash-and-equivalents tag; "
            "restricted cash, if any, inside)"
        )
    pts = fx.load_concept(CASH_ONLY, instant=True)
    co = pts.get(end) or next((x for e, x in pts.items() if near(e, end)), None)
    if co is not None:
        return co, f"cash {fiscal_label(end)} = us-gaap:Cash (fallback: no equivalents tag)"
    return None, ""


def long_term_debt(fx: Facts, end: str) -> tuple[Val | None, str]:
    v = fx.at("long_term_debt", end, instant=True)
    if v is not None:
        return v, ""
    v = fx.at("long_term_debt_total", end, instant=True)
    return (v, "LongTermDebt (≈ includes the current portion)") if v else (None, "")


OPTIONAL = {
    "short_term_investments": "short-term investments",
    "lt_investments": "long-term investments",
    "debt_current": "debt in current liabilities",
    "preferred_value": "preferred stock",
    "inventory": "inventory",
}


def optional_pair(
    fx: Facts, name: str, t: str, p: str, inp: Inputs, getter=None
) -> tuple[float | None, float | None]:
    """An optional balance-sheet line (D-M04-90): absent in both years → none on the balance
    sheet (named). Tagged for the prior year only: when the current year's annual report
    still tags the prior year, the line ended (current = none, named); when it does not, the
    tag changed → missing (NVIDIA FY2026 short-term investments). Tagged for the current
    year only (no comparative tagged anywhere) → a new line, prior = none (named)."""
    label = OPTIONAL.get(name, name.replace("_", " "))
    if getter is None:
        vt, vp = fx.at(name, t, True), fx.at(name, p, True)
        mt = mp = ""
    else:
        (vt, mt), (vp, mp) = getter(fx, t), getter(fx, p)
    if vt is None and vp is None:
        inp.subs.append(f"{label}: no tag either year (taken as none on the balance sheet)")
        return 0.0, 0.0
    if vt is None:
        acc = (fx.filing_of(t) or ("", ""))[0]
        names = ("long_term_debt", "long_term_debt_total") if getter else (name,)
        if acc and any(fx.reported_by(n, acc, p) for n in names):
            inp.subs.append(
                f"{label}: none in {fiscal_label(t)} (its report tags only {fiscal_label(p)})"
            )
            inp.used.append(vp)
            return 0.0, vp.value
        inp.missing.append(
            f"{label} {fiscal_label(t)} (tagged for {fiscal_label(p)} only, not "
            f"in the {fiscal_label(t)} report: tag switch?)"
        )
        return None, None
    if vp is None:
        inp.subs.append(
            f"{label}: new in {fiscal_label(t)} (no {fiscal_label(p)} value tagged; taken as none)"
        )
        inp.used.append(vt)
        return vt.value, 0.0
    for v, m in ((vt, mt), (vp, mp)):
        inp.used.append(v)
        if m:
            inp.subs.append(f"{label}: {m}")
        elif v.mark:
            inp.subs.append(f"{label}: {v.tag} [{v.mark}]")
    return vt.value, vp.value


def _ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


# --- Beneish M-score (D-M04-14, S2.3) -------------------------------------------------------


@dataclass
class MScore:
    end: str
    label: str
    state: str  # ok | incomplete | not_meaningful
    m: float | None = None
    m_sgi1: float | None = None
    components: dict[str, float] = field(default_factory=dict)
    inputs: Inputs = field(default_factory=Inputs)
    why: str = ""
    filed: str = ""
    accession: str = ""

    @property
    def reading(self) -> str:
        """review | growth_driven | below | incomplete | not_meaningful."""
        if self.state != "ok" or self.m is None or self.m_sgi1 is None:
            return self.state
        if self.m_sgi1 > M_CUT:
            return "review"
        if self.m > M_CUT:
            return "growth_driven"
        return "below"


BENEISH = {
    "DSRI": 0.920,
    "GMI": 0.528,
    "AQI": 0.404,
    "SGI": 0.892,
    "DEPI": 0.115,
    "SGAI": -0.172,
    "ACCR": 4.679,
    "LVGI": -0.327,
}
BENEISH_CONST = -4.84


def mscore(fx: Facts, end: str, tag: str | None = None) -> MScore:
    p = fx.prior(end)
    out = MScore(end, fiscal_label(end), "incomplete")
    f = fx.filing_of(end)
    if f:
        out.accession, out.filed = f
    if tag == "asset_treasury":
        out.state, out.why = "not_meaningful", "model tag asset_treasury (D-M04-8)"
        return out
    if p is None:
        out.why = "no prior fiscal year stored"
        out.inputs.missing.append("prior fiscal year")
        return out
    inp = out.inputs
    g = {}
    for y, e in (("t", end), ("p", p)):
        g[f"rev_{y}"] = inp.take(f"rev_{y}", fx.at("revenue", e), f"revenue {fiscal_label(e)}")
        v, m = cogs(fx, e)
        if m and v is not None:
            inp.subs.append(m)
        g[f"cogs_{y}"] = inp.take(
            f"cogs_{y}",
            v,
            f"cost of revenue {fiscal_label(e)}" + (f" ({m})" if m and v is None else ""),
        )
        for key, name in (
            ("rec", "receivables"),
            ("ca", "current_assets"),
            ("ppe", "ppe_net"),
            ("ta", "total_assets"),
            ("cl", "current_liabilities"),
        ):
            g[f"{key}_{y}"] = inp.take(
                f"{key}_{y}", fx.at(name, e, True), f"{name.replace('_', ' ')} {fiscal_label(e)}"
            )
        v, m = depreciation(fx, e)
        if m:
            inp.subs.append(m)
        g[f"dep_{y}"] = inp.take(f"dep_{y}", v, f"depreciation {fiscal_label(e)}")
        v, m = sga(fx, e)
        if m:
            inp.subs.append(m)
        g[f"sga_{y}"] = inp.take(f"sga_{y}", v, f"SG&A {fiscal_label(e)}")
    g["ltd_t"], g["ltd_p"] = optional_pair(fx, "long_term_debt", end, p, inp, long_term_debt)
    ni = fx.at("income_cont_ops", end)
    if ni is None:
        ni = fx.at("net_income", end)
    else:
        inp.subs.append("ACCR on income from continuing operations")
    g["ni_t"] = inp.take("ni_t", ni, f"net income {out.label}")
    g["cfo_t"] = inp.take(
        "cfo_t", fx.at("operating_cash_flow", end), f"operating cash flow {out.label}"
    )
    if inp.missing:
        out.why = "missing: " + ", ".join(inp.missing)
        return out
    try:
        gm_t = (g["rev_t"] - g["cogs_t"]) / g["rev_t"]
        gm_p = (g["rev_p"] - g["cogs_p"]) / g["rev_p"]
        c = {
            "DSRI": (g["rec_t"] / g["rev_t"]) / (g["rec_p"] / g["rev_p"]),
            "GMI": gm_p / gm_t,
            "AQI": (1 - (g["ca_t"] + g["ppe_t"]) / g["ta_t"])
            / (1 - (g["ca_p"] + g["ppe_p"]) / g["ta_p"]),
            "SGI": g["rev_t"] / g["rev_p"],
            "DEPI": (g["dep_p"] / (g["dep_p"] + g["ppe_p"]))
            / (g["dep_t"] / (g["dep_t"] + g["ppe_t"])),
            "SGAI": (g["sga_t"] / g["rev_t"]) / (g["sga_p"] / g["rev_p"]),
            "ACCR": (g["ni_t"] - g["cfo_t"]) / g["ta_t"],
            "LVGI": ((g["cl_t"] + g["ltd_t"]) / g["ta_t"]) / ((g["cl_p"] + g["ltd_p"]) / g["ta_p"]),
        }
    except ZeroDivisionError:
        out.why = "missing: a zero base in a ratio"
        inp.missing.append("zero base")
        return out
    out.components = c
    out.m = BENEISH_CONST + sum(BENEISH[k] * v for k, v in c.items())
    out.m_sgi1 = out.m - BENEISH["SGI"] * (c["SGI"] - 1)
    if gm_t <= 0 or gm_p <= 0:
        out.state = "not_meaningful"
        out.why = (
            f"gross margin ≤ 0 ({fiscal_label(p)} {gm_p:.1%}, {out.label} {gm_t:.1%}): "
            f"GMI {c['GMI']:.2f} has no meaning; raw M {out.m:.2f}"
        )
        return out
    out.state = "ok"
    return out


# --- Dechow misstatement score (D-M04-14, S2.4) --------------------------------------------


DECHOW = {
    "rsst_acc": 0.790,
    "ch_rec": 2.518,
    "ch_inv": 1.191,
    "soft_assets": 1.979,
    "ch_cs": 0.171,
    "ch_roa": -0.932,
    "issue": 1.029,
}
DECHOW_CONST = -7.893
DECHOW_BASE = 0.0037  # unconditional misstatement rate (score = probability ÷ 0.0037)


@dataclass
class FScore:
    end: str
    label: str
    state: str  # ok | incomplete | not_meaningful
    score: float | None = None
    components: dict[str, float] = field(default_factory=dict)
    inputs: Inputs = field(default_factory=Inputs)
    why: str = ""

    @property
    def band(self) -> str:
        if self.score is None:
            return self.state
        if self.score > F_BANDS[1]:
            return "above_2.45"
        if self.score > F_BANDS[0]:
            return "above_1.00"
        return "below_1.00"


def issue_tags(engine: sqlite3.Connection, cik: str) -> list[str]:
    """`taxonomy:tag` read for `issue`: M02's equity-issued and debt-raised roles (built-ins
    overlaid by the owner's `fin_tag_map`, D-M02-31) plus `ISSUE_EXTRA`, in that order."""
    from engine.moneyflow.allocation import mappings

    roles = mappings(engine, cik)
    tags = [t for t, r in roles.items() if r in ISSUE_ROLES]
    return list(dict.fromkeys(tags + [t for t in ISSUE_EXTRA if roles.get(t, "") != "ignore"]))


def issue_flag(fx: Facts, end: str, inp: Inputs) -> float | None:
    """1 when any equity or debt proceeds above 0 are tagged for the year (the tag named);
    0 when none is, provided the company tags at least one of them in some year; else
    unknown → missing (D-M04-90)."""
    tagged_somewhere: list[str] = []
    zero: list[Val] = []
    for tt in issue_tags(fx.engine, fx.cik):
        tax, tag = tt.split(":", 1)
        pts = fx.fy_of(Concept(f"issue_{tag}", ((tax, tag),), C, F))
        if not pts:
            continue
        tagged_somewhere.append(tt)
        v = pts.get(end) or next((x for e, x in pts.items() if near(e, end)), None)
        if v is None:
            continue
        if v.value > 0:
            inp.used.append(v)
            inp.subs.append(f"issue {fiscal_label(end)} = 1: {v.tag} {money(v.value)}M")
            return 1.0
        zero.append(v)
    if not tagged_somewhere:
        inp.missing.append(f"issue {fiscal_label(end)} (no equity- or debt-proceeds tag: unknown)")
        return None
    inp.used += zero
    inp.subs.append(
        f"issue {fiscal_label(end)} = 0: no proceeds above 0 tagged for the year (the company "
        f"tags {', '.join(t.split(':', 1)[1] for t in tagged_somewhere[:3])} in other years)"
    )
    return 0.0


def misstate_f(fx: Facts, end: str, tag: str | None = None) -> FScore:
    out = FScore(end, fiscal_label(end), "incomplete")
    if tag == "asset_treasury":
        out.state, out.why = "not_meaningful", "model tag asset_treasury (D-M04-8)"
        return out
    p = fx.prior(end)
    pp = fx.prior(p) if p else None
    inp = out.inputs
    if p is None or pp is None:
        out.why = "missing: two prior fiscal years needed (average assets, ROA a year earlier)"
        inp.missing.append("prior fiscal years")
        return out
    v = {}
    for y, e in (("t", end), ("p", p)):
        for key, name in (
            ("ta", "total_assets"),
            ("ca", "current_assets"),
            ("cl", "current_liabilities"),
            ("rec", "receivables"),
        ):
            v[f"{key}_{y}"] = inp.take(
                f"{key}_{y}", fx.at(name, e, True), f"{name.replace('_', ' ')} {fiscal_label(e)}"
            )
        cv, m = cash_at(fx, e)
        if m and cv is not None:
            inp.subs.append(m)
        v[f"cash_{y}"] = inp.take(f"cash_{y}", cv, f"cash {fiscal_label(e)}")
        lv, m = liabilities(fx, e)
        if m:
            inp.subs.append(m)
        v[f"tl_{y}"] = inp.take(f"tl_{y}", lv, f"total liabilities {fiscal_label(e)}")
        v[f"rev_{y}"] = inp.take(f"rev_{y}", fx.at("revenue", e), f"revenue {fiscal_label(e)}")
        v[f"ni_{y}"] = inp.take(f"ni_{y}", fx.at("net_income", e), f"net income {fiscal_label(e)}")
    v["ta_pp"] = inp.take(
        "ta_pp", fx.at("total_assets", pp, True), f"total assets {fiscal_label(pp)}"
    )
    v["rec_pp"] = inp.take(
        "rec_pp", fx.at("receivables", pp, True), f"receivables {fiscal_label(pp)}"
    )
    v["ppe_t"] = inp.take("ppe_t", fx.at("ppe_net", end, True), f"PP&E {out.label}")
    for name in OPTIONAL:
        v[f"{name}_t"], v[f"{name}_p"] = optional_pair(fx, name, end, p, inp)
    v["ltd_t"], v["ltd_p"] = optional_pair(fx, "long_term_debt", end, p, inp, long_term_debt)
    v["issue"] = issue_flag(fx, end, inp)
    if inp.missing:
        out.why = "missing: " + ", ".join(inp.missing)
        return out
    try:

        def wc(y):
            return (v[f"ca_{y}"] - v[f"cash_{y}"] - v[f"short_term_investments_{y}"]) - (
                v[f"cl_{y}"] - v[f"debt_current_{y}"]
            )

        def nco(y):
            return (v[f"ta_{y}"] - v[f"ca_{y}"] - v[f"lt_investments_{y}"]) - (
                v[f"tl_{y}"] - v[f"cl_{y}"] - v[f"ltd_{y}"]
            )

        def fin(y):
            return (v[f"short_term_investments_{y}"] + v[f"lt_investments_{y}"]) - (
                v[f"ltd_{y}"] + v[f"debt_current_{y}"] + v[f"preferred_value_{y}"]
            )

        avg_t = (v["ta_t"] + v["ta_p"]) / 2
        avg_p = (v["ta_p"] + v["ta_pp"]) / 2
        cs_t = v["rev_t"] - (v["rec_t"] - v["rec_p"])
        cs_p = v["rev_p"] - (v["rec_p"] - v["rec_pp"])
        c = {
            "rsst_acc": ((wc("t") - wc("p")) + (nco("t") - nco("p")) + (fin("t") - fin("p")))
            / avg_t,
            "ch_rec": (v["rec_t"] - v["rec_p"]) / avg_t,
            "ch_inv": (v["inventory_t"] - v["inventory_p"]) / avg_t,
            "soft_assets": (v["ta_t"] - v["ppe_t"] - v["cash_t"]) / v["ta_t"],
            "ch_cs": cs_t / cs_p - 1,
            "ch_roa": v["ni_t"] / avg_t - v["ni_p"] / avg_p,
            "issue": v["issue"],
        }
    except ZeroDivisionError:
        out.why = "missing: a zero base in a ratio"
        return out
    x = DECHOW_CONST + sum(DECHOW[k] * val for k, val in c.items())
    prob = math.exp(x) / (1 + math.exp(x))
    out.components, out.score, out.state = c, prob / DECHOW_BASE, "ok"
    return out


# --- Cash conversion and accruals (D-M04-20, S2.1) ------------------------------------------


@dataclass
class YearNI:
    end: str
    label: str
    ni: Val | None
    cfo: Val | None
    revenue: Val | None
    basis_ni: float | None
    items: list[tuple[str, float]] = field(default_factory=list)  # (what, after-tax effect)
    operating: bool = False


def swings(fx: Facts, end: str) -> list[tuple[str, Val, float]]:
    """(what, tagged value, effect on net income after tax) per identified item (SB.12)."""
    out = []
    for name, what, sign in SWINGS:
        v = fx.at(name, end)
        if v is None or v.value == 0:
            continue
        # valuation allowance (sign 0): a tax line, as reported (a release < 0 lifts NI)
        effect = -v.value if sign == 0 else sign * v.value * (1 - tax_rate(end))
        out.append((what, v, effect))
    return out


def year_ni(fx: Facts, end: str) -> YearNI:
    y = YearNI(
        end,
        fiscal_label(end),
        fx.at("net_income", end),
        fx.at("operating_cash_flow", end),
        fx.at("revenue", end),
        None,
    )
    if y.ni is None:
        return y
    ni = y.ni.value
    # `nonoperating` totals the others: used only when no item line is tagged
    items = [(w, e) for w, v, e in swings(fx, end) if w != SWINGS[4][1]]
    effect = sum(e for _, e in items)
    y.items = items
    if items and ni != 0 and abs(effect) > OPERATING_SWITCH * abs(ni):
        y.basis_ni, y.operating = ni - effect, True
    else:
        y.basis_ni = ni
    return y


@dataclass
class CashConversion:
    state: str  # ok | warn | note | warn_or_note | not_meaningful | missing
    ratio3: float | None
    latest: float | None
    years: list[YearNI]
    stage: str | None
    why: str = ""
    accruals: float | None = None
    accruals_hist: list[tuple[str, float]] = field(default_factory=list)
    accruals_text: str = ""
    sources: list[Val] = field(default_factory=list)


def cash_conversion(fx: Facts, stage: str | None, tag: str | None = None) -> CashConversion:
    ends = fx.ends()
    cc = CashConversion("missing", None, None, [], stage)
    if tag == "asset_treasury":
        cc.state, cc.why = "not_meaningful", "model tag asset_treasury (D-M04-8)"
        return cc
    years = [year_ni(fx, e) for e in ends]
    full = [y for y in years if y.ni is not None and y.cfo is not None]
    if len(full) < 3:
        cc.why = f"{len(full)} fiscal year(s) with net income and operating cash flow (3 needed)"
        cc.years = full
        return cc
    last3 = full[-3:]
    cc.years = last3
    cc.sources = [v for y in last3 for v in (y.ni, y.cfo) if v]
    ni = sum(y.basis_ni for y in last3)
    cfo = sum(y.cfo.value for y in last3)
    rev = [y.revenue.value for y in last3 if y.revenue]
    if ni <= 0 or (len(rev) == 3 and abs(ni) < NI_MIN_SHARE * sum(rev)):
        cc.state = "not_meaningful"
        cc.why = (
            f"3-year net income {ni / 1e6:,.0f}M "
            + ("≤ 0" if ni <= 0 else "below 1% of revenue")
            + " (S2.1)"
        )
    else:
        cc.ratio3 = cfo / ni
        y = last3[-1]
        cc.latest = y.cfo.value / y.basis_ni if y.basis_ni and y.basis_ni > 0 else None
        if cc.ratio3 >= CFO_NI_WARN:
            cc.state = "ok"
        elif stage in ("mature", "decline"):
            cc.state = "warn"
        elif stage in ("introduction", "growth", "shake_out"):
            cc.state = "note"
        else:
            cc.state = "warn_or_note"
    # accruals vs own history (no warning)
    hist = []
    for y in full:
        ta_t = fx.at("total_assets", y.end, True)
        p = fx.prior(y.end)
        ta_p = fx.at("total_assets", p, True) if p else None
        if ta_t is None or ta_p is None or y.basis_ni is None:
            continue
        hist.append((y.label, (y.basis_ni - y.cfo.value) / ((ta_t.value + ta_p.value) / 2)))
    if hist:
        cc.accruals = hist[-1][1]
        prior = [v for _, v in hist[:-1]][-HISTORY_YEARS:]
        cc.accruals_hist = hist[-(HISTORY_YEARS + 1) :]
        if len(prior) < 3:
            cc.accruals_text = "short_history"
        elif cc.accruals > max(prior):
            cc.accruals_text = "above_own_range"
        elif cc.accruals < min(prior):
            cc.accruals_text = "below_own_range"
        else:
            cc.accruals_text = "within_own_range"
    return cc


# --- Contract assets and deferred revenue (S2.2) --------------------------------------------


@dataclass
class Reading:
    end: str
    label: str
    line: Val
    prior: Val
    line_growth: float
    revenue_growth: float | None
    state: str  # scored | definition_changed | no_revenue | acquisition_year
    note: str = ""

    @property
    def gap_pp(self) -> float | None:
        if self.revenue_growth is None:
            return None
        return (self.line_growth - self.revenue_growth) * 100


@dataclass
class Gap:
    concept: str
    state: str  # watch | none | short_history | missing
    readings: list[Reading]
    why: str = ""

    @property
    def latest(self) -> Reading | None:
        return self.readings[-1] if self.readings else None


def acquisition_year(fx: Facts, end: str, p: str | None) -> str:
    """Part 2's acquisition-year test on the fiscal year (cash for businesses or the goodwill
    rise ≥ 10%† of revenue, `peers.acquisition_note`); '' when not one."""
    rev = fx.at("revenue", end)
    acq = fx.at("acquisitions", end)
    gw = fx.at("goodwill", end, True)
    gw_p = fx.at("goodwill", p, True) if p else None
    return acquisition_note(
        rev.value if rev else None,
        acq.value if acq else None,
        gw.value if gw else None,
        gw_p.value if gw_p else None,
    )


def readings(fx: Facts, concept: str) -> list[Reading]:
    out = []
    for end in fx.ends():
        p = fx.prior(end)
        line = fx.at(concept, end, True)
        prev = fx.at(concept, p, True) if p else None
        if line is None or prev is None or prev.value == 0:
            continue
        rev, rev_p = fx.at("revenue", end), (fx.at("revenue", p) if p else None)
        rg = rev.value / rev_p.value - 1 if rev and rev_p and rev_p.value else None
        state, note = "scored", ""
        if line.tag != prev.tag:
            state = "definition_changed"
        elif rg is None:
            state = "no_revenue"
        elif note := acquisition_year(fx, end, p):
            state = "acquisition_year"
        out.append(
            Reading(
                end, fiscal_label(end), line, prev, line.value / prev.value - 1, rg, state, note
            )
        )
    return out


def latest_run(fx: Facts, rs: list[Reading]) -> list[Reading]:
    """The readings of consecutive fiscal years ending at the latest fiscal year (live check
    1: Micron's FY2017, FY2018 and FY2025 readings are not "the last 2")."""
    ends = fx.ends()
    if not rs or not ends or rs[-1].end != ends[-1]:
        return []
    run = [rs[-1]]
    for r in reversed(rs[:-1]):
        if fx.prior(run[0].end) != r.end:
            break
        run.insert(0, r)
    return run


def _gap(fx: Facts, concept: str, what: str, hit, watch_why: str) -> Gap:
    rs = readings(fx, concept)
    if not rs:
        return Gap(concept, "missing", [], f"no {what} tag in two consecutive fiscal years")
    run = latest_run(fx, rs)
    last = run[-READINGS:]
    if len(last) < READINGS:
        ends = fx.ends()
        why = (
            "one reading"
            if len(rs) == 1
            else f"no reading at the latest fiscal year {fiscal_label(ends[-1])}"
            if not run
            else f"one reading in consecutive fiscal years to {fiscal_label(ends[-1])} "
            "(older readings not counted)"
        )
        return Gap(concept, "short_history", rs, why)
    if any(r.state != "scored" for r in last):
        return Gap(
            concept,
            "none",
            rs,
            "a reading is not scored ("
            + ", ".join(
                f"{r.label} {r.state.replace('_', ' ')}" + (f": {r.note}" if r.note else "")
                for r in last
                if r.state != "scored"
            )
            + ")",
        )
    if all(hit(r) for r in last):
        return Gap(concept, "watch", rs, watch_why)
    return Gap(concept, "none", rs)


def contract_asset_gap(fx: Facts) -> Gap:
    return _gap(
        fx,
        "contract_assets",
        "contract-asset",
        lambda r: (r.gap_pp or 0) > GAP_PP,
        f"contract assets > {GAP_PP:.0f} pp faster than revenue in the last {READINGS} "
        "readings (S2.2)",
    )


def deferred_rev_gap(fx: Facts) -> Gap:
    return _gap(
        fx,
        "contract_liabilities",
        "deferred-revenue",
        lambda r: r.line_growth < 0 and (r.revenue_growth or 0) > 0,
        f"deferred revenue falling while revenue grows in the last {READINGS} readings (S2.2)",
    )


# --- Company bundle -------------------------------------------------------------------------


@dataclass
class Quality:
    cik: str
    ticker: str | None
    tag: str | None
    tag_how: str
    stage: str | None
    stage_label: str
    ends: list[str]
    mscores: list[MScore]
    fscores: list[FScore]
    cash: CashConversion
    contract: Gap
    deferred: Gap
    swings: list[tuple[str, str, Val, float, float | None]]  # (label, what, val, effect, share)
    excluded: str = ""  # "not applicable (<tag>)" for fund / financial / reit / spac_shell

    @property
    def latest_m(self) -> MScore | None:
        return self.mscores[-1] if self.mscores else None

    @property
    def latest_f(self) -> FScore | None:
        return self.fscores[-1] if self.fscores else None


EXCLUDED_TAGS = ("fund", "financial", "reit", "spac_shell")
SHOW_YEARS = 3


def compute(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str | None = None,
    *,
    models=None,
    stage: str | None = None,
    stage_label: str = "",
) -> Quality:
    """Every Part 6 score of one company (0 requests)."""
    from engine.financials import models as models_mod

    norm = normalize_cik(cik) or cik
    fx = Facts(engine, norm)
    ends = fx.ends()
    mf = models if models is not None else models_mod.load_safe()
    tag, how = models_mod.route(engine, mf, norm, ticker, ends[-1] if ends else None)
    q = Quality(
        norm,
        ticker,
        tag,
        how,
        stage,
        stage_label,
        ends,
        [],
        [],
        CashConversion("missing", None, None, [], stage),
        Gap("contract_assets", "missing", []),
        Gap("contract_liabilities", "missing", []),
        [],
    )
    if tag in EXCLUDED_TAGS:
        q.excluded = f"not applicable ({tag})"
        return q
    show = ends[-SHOW_YEARS:]
    q.mscores = [mscore(fx, e, tag) for e in show]
    q.fscores = [misstate_f(fx, e, tag) for e in show]
    q.cash = cash_conversion(fx, stage, tag)
    q.contract = contract_asset_gap(fx)
    q.deferred = deferred_rev_gap(fx)
    for e in ends[-4:]:
        ni = fx.at("net_income", e)
        for what, v, effect in swings(fx, e):
            share = effect / abs(ni.value) if ni is not None and ni.value else None
            q.swings.append((fiscal_label(e), what, v, effect, share))
    return q


def money(v: float | None, unit: float = 1e6) -> str:
    if v is None:
        return "—"
    return f"{v / unit:,.0f}".replace("-", "−")


def inputs_text(vals: Iterable[Val]) -> str:
    seen = dict.fromkeys(f"{v.tag} {fiscal_label(v.end)} {v.accession}" for v in vals)
    return "; ".join(seen)
