"""XBRL company facts → point-in-time facts and normalized series (M00_SEC_DATA xbrl_facts.py).

1. Every reported fact is stored in `fact` with its filed date and accession. A
   value repeated in later filings (comparatives, restatements) keeps every version.
2. Concept map: ordered candidate tags per concept. For each period the value
   comes from the highest-priority tag reporting it, so tag switches merge.
   Units are checked; concepts with no tag are reported with the tags checked,
   never guessed by substring.
3. Periods are labeled from start/end dates (not fy/fp): ~quarter, 6M, 9M, FY,
   instant. Missing discrete quarters are derived from year-to-date facts with
   the same start (Q2 = 6M − Q1, Q3 = 9M − 6M, Q4 = FY − 9M). TTM = four
   contiguous discrete quarters, else missing. Per-share and other non-additive
   concepts are never derived or summed.
4. `series` keeps first-reported and latest value per period (point-in-time).
   Missing stays missing; nothing is coerced to zero. `series` is for display; M04
   signals read `sec/asof.py` (`facts_as_of`, S1.1).
5. A tag that means something broader or narrower than its concept is marked in the
   method ("≈ broader tag: <what it adds>", S1.4, D-M04-3); per-company aliases apply
   to one CIK only (GE, NVDA; SB.18) and are marked too.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Any

from engine.sec.client import SecClient, iso
from engine.sec.identity import normalize_cik
from engine.sec.results import Empty, Failed, Ok, Probe, Result

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
FACTS_BACKSTOP = timedelta(days=7)
CACHE_TTL_S = 6 * 3600
# facts-2 (M04 Part 1a): share series, sbc, public float, `da` and `ppe_net` fixes, tag
# marks. Series are rebuilt from stored `fact` rows (no download): `rebuild_series`.
PARSER_VERSION = "facts-2"
# Forms whose filing makes companyfacts due (SB.11); an XBRL 6-K counts too (see _due).
REFRESH_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "10-KT", "10-KT/A", "10-QT", "10-QT/A",
                 "20-F", "20-F/A", "40-F", "40-F/A")  # fmt: skip
XBRL_6K_FORMS = ("6-K", "6-K/A")

_CURRENCY = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class Concept:
    name: str
    tags: tuple[tuple[str, str], ...]  # (taxonomy, tag) in priority order
    unit: str  # currency | shares | per_share
    kind: str  # flow | instant
    additive: bool = True  # quarters may be derived and summed into TTM
    marks: tuple[tuple[str, str, str], ...] = ()  # (taxonomy, tag, mark shown in the method)

    def mark(self, taxonomy: str, tag: str) -> str:
        return next((m for t, g, m in self.marks if (t, g) == (taxonomy, tag)), "")

    def label(self, taxonomy: str, tag: str) -> str:
        """`us-gaap:Tag` plus its mark, e.g. `[≈ broader tag: includes intangibles]`."""
        mark = self.mark(taxonomy, tag)
        return f"{taxonomy}:{tag}" + (f" [{mark}]" if mark else "")


def _gaap(*tags: str) -> tuple[tuple[str, str], ...]:
    return tuple(("us-gaap", t) for t in tags)


def _ifrs(*tags: str) -> tuple[tuple[str, str], ...]:
    return tuple(("ifrs-full", t) for t in tags)


C, F, I = "currency", "flow", "instant"  # noqa: E741
S = "shares"
_FL = "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAsset"
BROADER_PPE = ("us-gaap", f"{_FL}AfterAccumulatedDepreciationAndAmortization")
BROADER_PPE_GROSS = ("us-gaap", f"{_FL}BeforeAccumulatedDepreciationAndAmortization")
_MATURITY = "LongTermDebtMaturitiesRepaymentsOfPrincipal"

# Initial concept map (M00_SEC_DATA). Tags within a concept must mean the same thing;
# a broader tag (e.g. LongTermDebt incl. current portion) is not a fallback.
CONCEPTS: tuple[Concept, ...] = (
    Concept("revenue", _gaap("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
            "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueGoodsNet") + _ifrs("Revenue"), C, F),
    Concept("cost_of_revenue", _gaap("CostOfGoodsAndServicesSold", "CostOfRevenue",
            "CostOfGoodsSold") + _ifrs("CostOfSales"), C, F),
    Concept("gross_profit", _gaap("GrossProfit") + _ifrs("GrossProfit"), C, F),
    Concept("operating_income", _gaap("OperatingIncomeLoss")
            + _ifrs("ProfitLossFromOperatingActivities"), C, F),
    Concept("net_income", _gaap("NetIncomeLoss")
            + _ifrs("ProfitLossAttributableToOwnersOfParent"), C, F),
    Concept("eps_diluted", _gaap("EarningsPerShareDiluted")
            + _ifrs("DilutedEarningsLossPerShare"), "per_share", F, additive=False),
    Concept("rd", _gaap("ResearchAndDevelopmentExpense",
            "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost")
            + _ifrs("ResearchAndDevelopmentExpense"), C, F),
    Concept("sga", _gaap("SellingGeneralAndAdministrativeExpense")
            + _ifrs("SellingGeneralAndAdministrativeExpense"), C, F),
    # `DepreciationAndAmortization` is the nonproduction concept (INTC $200M vs $9,204M
    # depreciation, S1.3): dropped. `Depreciation` alone is the last, marked fallback.
    Concept("da", _gaap("DepreciationDepletionAndAmortization",
            "DepreciationAmortizationAndAccretionNet")
            + _ifrs("DepreciationAndAmortisationExpense") + _gaap("Depreciation"), C, F,
            marks=(("us-gaap", "Depreciation", "≈ narrower tag: depreciation only, "
                    "no amortization"),)),
    Concept("capex", _gaap("PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets")
            + _ifrs("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"), C, F,
            marks=(("us-gaap", "PaymentsToAcquireProductiveAssets",
                    "≈ broader tag: includes software and intangibles"),)),
    Concept("operating_cash_flow", _gaap("NetCashProvidedByUsedInOperatingActivities")
            + _ifrs("CashFlowsFromUsedInOperatingActivities"), C, F),
    Concept("interest_expense", _gaap("InterestExpense", "InterestExpenseNonoperating",
            "InterestExpenseDebt"), C, F),
    Concept("ppe_net", _gaap("PropertyPlantAndEquipmentNet")
            + _ifrs("PropertyPlantAndEquipment") + (BROADER_PPE,), C, I,
            marks=((*BROADER_PPE, "≈ broader tag: includes finance-lease right-of-use "
                    "assets"),)),
    Concept("inventory", _gaap("InventoryNet") + _ifrs("Inventories"), C, I),
    Concept("receivables", _gaap("AccountsReceivableNetCurrent")
            + _ifrs("TradeAndOtherCurrentReceivables"), C, I),
    Concept("cash", _gaap("CashAndCashEquivalentsAtCarryingValue")
            + _ifrs("CashAndCashEquivalents"), C, I),
    Concept("short_term_investments", _gaap("ShortTermInvestments", "MarketableSecuritiesCurrent",
            "AvailableForSaleSecuritiesDebtSecuritiesCurrent"), C, I),
    Concept("total_assets", _gaap("Assets") + _ifrs("Assets"), C, I),
    Concept("current_assets", _gaap("AssetsCurrent") + _ifrs("CurrentAssets"), C, I),
    Concept("current_liabilities", _gaap("LiabilitiesCurrent") + _ifrs("CurrentLiabilities"), C, I),
    Concept("total_liabilities", _gaap("Liabilities") + _ifrs("Liabilities"), C, I),
    Concept("long_term_debt", _gaap("LongTermDebtNoncurrent",
            "LongTermDebtAndCapitalLeaseObligations"), C, I),
    Concept("retained_earnings", _gaap("RetainedEarningsAccumulatedDeficit")
            + _ifrs("RetainedEarnings"), C, I),
    Concept("equity", _gaap("StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
            + _ifrs("EquityAttributableToOwnersOfParent"), C, I),
    # Legacy display row: mixes balance-sheet and cover dates. M04 reads the four share
    # series below instead (D-M04-2).
    Concept("shares_outstanding", _gaap("CommonStockSharesOutstanding")
            + (("dei", "EntityCommonStockSharesOutstanding"),), S, I, additive=False),
    Concept("rpo", _gaap("RevenueRemainingPerformanceObligation"), C, I),
    # Share series (D-M04-2). Cover counts carry the cover date, not the balance-sheet
    # date; multi-class filers without a total read their R1 page (`sec/cover.py`).
    Concept("shares_period_end", _gaap("CommonStockSharesOutstanding"), S, I, additive=False),
    Concept("shares_cover", (("dei", "EntityCommonStockSharesOutstanding"),), S, I,
            additive=False),
    Concept("shares_basic_wavg", _gaap("WeightedAverageNumberOfSharesOutstandingBasic")
            + _ifrs("WeightedAverageShares"), S, F, additive=False),
    Concept("shares_diluted_wavg", _gaap("WeightedAverageNumberOfDilutedSharesOutstanding")
            + _ifrs("AdjustedWeightedAverageShares"), S, F, additive=False),
    Concept("sbc", _gaap("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense")
            + _ifrs("AdjustmentsForSharebasedPayments"), C, F,
            marks=(("us-gaap", "AllocatedShareBasedCompensationExpense",
                    "≈ expense tag: may differ from the cash-flow add-back"),)),
    # $ value of non-affiliate equity at the end of the second fiscal quarter (10-K cover).
    Concept("public_float", (("dei", "EntityPublicFloat"),), C, I),
)  # fmt: skip
CONCEPT_BY_NAME = {c.name: c for c in CONCEPTS}

# M04 extra concepts (S1.3): read through `facts_as_of`, never written to `series`; a
# company without any of the tags is listed in the extra-tag report, never read as zero.
EXTRA_CONCEPTS: tuple[Concept, ...] = (
    Concept("depreciation", _gaap("Depreciation") + _ifrs("DepreciationExpense"), C, F),
    Concept("income_tax", _gaap("IncomeTaxExpenseBenefit")
            + _ifrs("IncomeTaxExpenseContinuingOperations"), C, F),
    Concept("pretax_income", _gaap(
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments")
            + _ifrs("ProfitLossBeforeTax"), C, F),
    Concept("income_cont_ops", _gaap("IncomeLossFromContinuingOperations"), C, F),
    Concept("debt_current", _gaap("DebtCurrent", "LongTermDebtCurrent"), C, I),
    Concept("short_term_borrowings", _gaap("ShortTermBorrowings"), C, I),
    Concept("commercial_paper", _gaap("CommercialPaper"), C, I),
    Concept("long_term_debt_total", _gaap("LongTermDebt"), C, I),
    Concept("debt_due_y1", _gaap(f"{_MATURITY}InNextTwelveMonths"), C, I),
    Concept("debt_due_y2", _gaap(f"{_MATURITY}InYearTwo"), C, I),
    Concept("debt_due_y3", _gaap(f"{_MATURITY}InYearThree"), C, I),
    Concept("debt_due_y4", _gaap(f"{_MATURITY}InYearFour"), C, I),
    Concept("debt_due_y5", _gaap(f"{_MATURITY}InYearFive"), C, I),
    Concept("debt_due_after5", _gaap(f"{_MATURITY}AfterYearFive"), C, I),
    Concept("credit_capacity", _gaap("LineOfCreditFacilityRemainingBorrowingCapacity"), C, I),
    Concept("restricted_cash", _gaap("RestrictedCashCurrent", "RestrictedCash"), C, I),
    Concept("contract_liabilities", _gaap("ContractWithCustomerLiabilityCurrent",
            "DeferredRevenueCurrent"), C, I,
            marks=(("us-gaap", "DeferredRevenueCurrent", "≈ pre-2018 tag (before ASC 606)"),)),
    Concept("contract_assets", _gaap("ContractWithCustomerAssetNetCurrent",
            "UnbilledContractsReceivable"), C, I,
            marks=(("us-gaap", "UnbilledContractsReceivable",
                    "≈ pre-2018 alias (before ASC 606)"),)),
    Concept("revenue_prior_obligations",
            _gaap("ContractWithCustomerPerformanceObligationSatisfiedInPreviousPeriod"), C, F),
    Concept("proceeds_common", _gaap("ProceedsFromIssuanceOfCommonStock"), C, F),
    Concept("proceeds_plans", _gaap(
            "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlans",
            "ProceedsFromStockOptionsExercised"), C, F),
    Concept("proceeds_lt_debt", _gaap("ProceedsFromIssuanceOfLongTermDebt"), C, F),
    Concept("lt_investments", _gaap("LongTermInvestments"), C, I),
    Concept("preferred_value", _gaap("PreferredStockValue"), C, I),
    Concept("accrued_taxes", _gaap("AccruedIncomeTaxesCurrent"), C, I),
    Concept("investing_cf", _gaap("NetCashProvidedByUsedInInvestingActivities")
            + _ifrs("CashFlowsFromUsedInInvestingActivities"), C, F),
    Concept("financing_cf", _gaap("NetCashProvidedByUsedInFinancingActivities")
            + _ifrs("CashFlowsFromUsedInFinancingActivities"), C, F),
    Concept("acquisitions", _gaap("PaymentsToAcquireBusinessesNetOfCashAcquired"), C, F),
    Concept("divestiture_proceeds", _gaap("ProceedsFromDivestitureOfBusinessesNetOfCashDivested",
            "ProceedsFromDivestitureOfBusinesses"), C, F),
    Concept("asset_sale_proceeds", _gaap("ProceedsFromSaleOfPropertyPlantAndEquipment"), C, F),
    Concept("inventory_writedown", _gaap("InventoryWriteDown"), C, F),
    Concept("impairment", _gaap("AssetImpairmentCharges"), C, F),
    Concept("goodwill_impairment", _gaap("GoodwillImpairmentLoss"), C, F),
    Concept("restructuring", _gaap("RestructuringCharges"), C, F),
    Concept("advertising", _gaap("AdvertisingExpense"), C, F),
    Concept("nonoperating", _gaap("NonoperatingIncomeExpense"), C, F),
    Concept("equity_securities_gain", _gaap("EquitySecuritiesFvNiGainLoss"), C, F),
    Concept("valuation_allowance_change",
            _gaap("IncomeTaxReconciliationChangeInDeferredTaxAssetsValuationAllowance"), C, F),
    Concept("crypto_unrealized", _gaap("CryptoAssetUnrealizedLossOperating"), C, F),
    Concept("crypto_fair_value", _gaap("CryptoAssetFairValue"), C, I),
    Concept("ppe_gross", _gaap("PropertyPlantAndEquipmentGross") + (BROADER_PPE_GROSS,), C, I,
            marks=((*BROADER_PPE_GROSS, "≈ broader tag: includes finance-lease right-of-use "
                    "assets"),)),
)  # fmt: skip
ALL_CONCEPTS = {c.name: c for c in CONCEPTS + EXTRA_CONCEPTS}


@dataclass(frozen=True)
class Alias:
    """A tag read for one company only (SB.18): never part of a general concept."""

    concept: str
    taxonomy: str
    tag: str
    mark: str


# Per-company aliases, lowest priority, always marked. `us-gaap:CommodityContractAssetNoncurrent`
# is a derivative concept: GE double-tagged its FY2016 contract assets with it (probe S5);
# it is never mapped for anyone else. Extension tags (`ge:`, `nvda:`) exist only where the
# filing instance was read (`moneyflow/instance.py`).
ALIASES: dict[str, tuple[Alias, ...]] = {
    "0000040545": (  # GE
        Alias("contract_assets", "us-gaap", "CommodityContractAssetNoncurrent",
              "alias, GE only: FY2016 contract assets double-tagged as a derivative concept"),
        Alias("contract_assets", "ge", "ContractAsset", "alias, GE only: company extension tag"),
    ),
    "0001045810": (  # NVIDIA (probe L2: 51,951 at FY2026 under the extension)
        Alias("short_term_investments", "nvda", "MarketableSecuritiesAndEquitySecuritiesFVNI",
              "alias, NVDA only: company extension tag (instance read)"),
        # FY2013–FY2021 capex exists only under the extension (probe S4: FY2021 1,128.0M,
        # FY2013 183.3M); same caption as the later PaymentsToAcquireProductiveAssets, so
        # one definition across the switch (D-M04-3; M04 Part 1b, `run_financials.py capex`).
        Alias("capex", "nvda", "PurchasesOfPropertyAndEquipmentAndIntangibleAssets",
              "≈ broader tag: includes intangibles (NVDA extension tag, instance read)"),
    ),
}  # fmt: skip


def concept_for(cik: str, concept: Concept) -> Concept:
    """The concept with this company's aliases appended (lowest priority, marked)."""
    extra = [a for a in ALIASES.get(normalize_cik(cik) or cik, ()) if a.concept == concept.name]
    if not extra:
        return concept
    return replace(
        concept,
        tags=concept.tags + tuple((a.taxonomy, a.tag) for a in extra),
        marks=concept.marks + tuple((a.taxonomy, a.tag, a.mark) for a in extra),
    )


# --- Periods -----------------------------------------------------------------


def classify(start: str | None, end: str) -> str | None:
    """'I' instant, 'Q' ~quarter, '6M', '9M', 'FY'; None for other lengths."""
    if not start:
        return "I"
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    for label, low, high in (("Q", 80, 105), ("6M", 170, 195), ("9M", 260, 290), ("FY", 350, 380)):
        if low <= days <= high:
            return label
    return None


def _contiguous(prev_end: str, next_start: str) -> bool:
    gap = (date.fromisoformat(next_start) - date.fromisoformat(prev_end)).days
    return 1 <= gap <= 7


def _day_after(d: str) -> str:
    return (date.fromisoformat(d) + timedelta(days=1)).isoformat()


# --- Fact storage --------------------------------------------------------------


def iter_facts(cik: str, data: dict[str, Any]):
    """Yield fact rows from a companyfacts JSON document."""
    for taxonomy, tags in (data.get("facts") or {}).items():
        for tag, body in tags.items():
            for unit, facts in (body.get("units") or {}).items():
                for f in facts:
                    if f.get("val") is None or not f.get("end") or not f.get("accn"):
                        continue
                    yield (
                        cik, taxonomy, tag, unit, f.get("start"), f["end"], f["val"], f["accn"],
                        f.get("form"), f.get("filed") or "", f.get("fy"), f.get("fp"),
                        f.get("frame"),
                    )  # fmt: skip


def store_facts(engine: sqlite3.Connection, cik: str, data: dict[str, Any]) -> tuple[int, int]:
    """Insert every fact (all taxonomies). Returns (seen, new). Caller owns the transaction."""
    rows = list(iter_facts(cik, data))
    before = engine.total_changes
    engine.executemany(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession, "
        "form, filed, fy, fp, frame) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT DO NOTHING",
        rows,
    )
    return len(rows), engine.total_changes - before


CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{tag}.json"


def store_concept(engine: sqlite3.Connection, cik: str, data: dict[str, Any]) -> tuple[int, int]:
    """Insert the facts of one companyconcept JSON (one tag, all units). Returns (seen, new).

    Used for companies whose full companyfacts file is not wanted (fixtures per tag, SB.6;
    the Part 1a WDC as-of check). Caller owns the transaction."""
    wrapped = {"facts": {data["taxonomy"]: {data["tag"]: {"units": data.get("units") or {}}}}}
    return store_facts(engine, cik, wrapped)


# --- Series --------------------------------------------------------------------


@dataclass(frozen=True)
class Version:
    value: float | int
    accession: str
    filed: str


@dataclass(frozen=True)
class Point:
    start: str | None
    end: str
    ptype: str  # Q | FY | TTM | I (6M/9M kept only as derivation inputs)
    unit: str
    first: Version
    latest: Version
    method: str


@dataclass(frozen=True)
class ConceptResult:
    concept: str
    points: tuple[Point, ...]
    tags_used: tuple[str, ...]
    skipped_units: tuple[str, ...] = field(default_factory=tuple)


def _unit_ok(concept: Concept, unit: str, currency: str | None) -> bool:
    if concept.unit == "currency":
        return unit == currency
    if concept.unit == "shares":
        return unit == "shares"
    if concept.unit == "per_share":
        return unit == f"{currency}/shares"
    return False


def _pick_currency(units: Counter[str]) -> str | None:
    currencies = Counter()
    for unit, n in units.items():
        base = unit.split("/")[0]
        if _CURRENCY.match(base):
            currencies[base] += n
    if not currencies:
        return None
    return "USD" if "USD" in currencies else currencies.most_common(1)[0][0]


def pick_period(cands: list[Point]) -> Point:
    """Choose among points for the same period type and end date that differ only in start.

    Newest latest filing wins (ties: the longer period); the others are named in the
    method so the alternative is visible, not silently dropped.
    """
    if len(cands) == 1:
        return cands[0]
    ordered = sorted(cands, key=lambda p: (p.latest.filed, p.latest.accession, -_start_ord(p)),
                     reverse=True)  # fmt: skip
    best, others = ordered[0], ordered[1:]
    alt = ", ".join(f"{o.start}..{o.end} = {o.latest.value}" for o in others)
    return replace(best, method=f"{best.method}; also reported as {alt}")


def _start_ord(p: Point) -> int:
    return date.fromisoformat(p.start).toordinal() if p.start else 0


def concept_rows(engine: sqlite3.Connection, ciks: list[str], concept: Concept) -> list[Any]:
    """Every stored fact of the concept's tags for these CIKs (with form and cik)."""
    clauses = " OR ".join("(taxonomy = ? AND tag = ?)" for _ in concept.tags)
    marks = ",".join("?" * len(ciks))
    args: list[Any] = [*ciks] + [x for pair in concept.tags for x in pair]
    return engine.execute(
        "SELECT cik, taxonomy, tag, unit, period_start, period_end, value, accession, filed, "
        f"form FROM fact WHERE cik IN ({marks}) AND ({clauses})",
        args,
    ).fetchall()


def build_concept(engine: sqlite3.Connection, cik: str, concept: Concept) -> ConceptResult | None:
    """Normalized points for one concept, or None if no candidate tag has facts."""
    concept = concept_for(cik, concept)
    return points_from_rows(concept, concept_rows(engine, [cik], concept))


def points_from_rows(
    concept: Concept, rows: list[Any], *, first_any_tag: bool = False
) -> ConceptResult | None:
    """Points from fact rows (keys: taxonomy, tag, unit, period_start, period_end, value,
    accession, filed). Per period the highest-priority tag gives the value; with
    `first_any_tag` the first version is the earliest filed under any tag (S1.1: tag
    priority after time), named in the method when its tag differs."""
    rank = {tag: i for i, tag in enumerate(concept.tags)}
    if not rows:
        return None

    currency = _pick_currency(Counter(r["unit"] for r in rows))
    skipped = sorted({f"{r['tag']} [{r['unit']}]" for r in rows
                      if not _unit_ok(concept, r["unit"], currency)})  # fmt: skip
    unit = {"currency": currency, "shares": "shares", "per_share": f"{currency}/shares"}[
        concept.unit
    ]

    # Highest-priority tag per period; every filed version of that tag's value.
    by_period: dict[tuple[str | None, str], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        if _unit_ok(concept, r["unit"], currency):
            by_period[(r["period_start"], r["period_end"])].append(r)
    reported: dict[tuple[str | None, str], tuple[str, Version, Version]] = {}
    used: set[str] = set()
    for period, group in by_period.items():
        best = min(rank[(r["taxonomy"], r["tag"])] for r in group)
        chosen = sorted(
            (r for r in group if rank[(r["taxonomy"], r["tag"])] == best),
            key=lambda r: (r["filed"], r["accession"]),
        )
        used.add(f"{chosen[0]['taxonomy']}:{chosen[0]['tag']}")
        tag = concept.label(chosen[0]["taxonomy"], chosen[0]["tag"])
        first, last = chosen[0], chosen[-1]
        if first_any_tag:
            earliest = min(group, key=lambda r: (r["filed"], r["accession"]))
            if (earliest["filed"], earliest["accession"]) < (first["filed"], first["accession"]):
                first = earliest
                tag += (f"; first filed {earliest['filed']} under "
                        f"{concept.label(earliest['taxonomy'], earliest['tag'])}")  # fmt: skip
        reported[period] = (
            tag,
            Version(first["value"], first["accession"], first["filed"]),
            Version(last["value"], last["accession"], last["filed"]),
        )
    tags_used = tuple(sorted(used))

    points: list[Point] = []
    if concept.kind == "instant":
        for (start, end), (tag, first, latest) in sorted(reported.items(), key=lambda kv: kv[0][1]):
            if start is None:
                points.append(Point(None, end, "I", unit, first, latest, f"reported {tag}"))
        return ConceptResult(concept.name, tuple(points), tags_used, tuple(skipped))

    typed = {p: (classify(p[0], p[1]), v) for p, v in reported.items() if p[0] is not None}
    # One point per (type, end). Companies sometimes report the same period with start
    # dates a day or so apart; keep the version from the newest filing and note the other.
    candidates: dict[tuple[str, str], list[Point]] = defaultdict(list)
    for (start, end), (ptype, (tag, first, latest)) in typed.items():
        if ptype in ("Q", "FY"):
            candidates[(ptype, end)].append(
                Point(start, end, ptype, unit, first, latest, f"reported {tag}")
            )
    quarters: dict[str, Point] = {}  # by end date
    for (ptype, end), cands in candidates.items():
        chosen = pick_period(cands)
        if ptype == "Q":
            quarters[end] = chosen
        else:
            points.append(chosen)

    if concept.additive:
        # Year-to-date chains sharing a start: consecutive lengths differ by one quarter.
        chains: dict[str, list[tuple[str, str, Version, Version]]] = defaultdict(list)
        for (start, end), (ptype, (tag, first, latest)) in typed.items():
            if ptype in ("Q", "6M", "9M", "FY"):
                chains[start].append((end, tag, first, latest))
        for start, chain in chains.items():
            chain.sort()
            for (e1, _t1, f1, l1), (e2, t2, f2, l2) in zip(chain, chain[1:], strict=False):
                q_start = _day_after(e1)
                if classify(q_start, e2) != "Q" or e2 in quarters:
                    continue
                first = Version(f2.value - f1.value, f2.accession, max(f1.filed, f2.filed))
                latest = Version(l2.value - l1.value, l2.accession, max(l1.filed, l2.filed))
                method = f"derived {start}..{e2} − {start}..{e1} ({t2})"
                quarters[e2] = Point(q_start, e2, "Q", unit, first, latest, method)

    ordered = sorted(quarters.values(), key=lambda p: p.end)
    points.extend(ordered)
    if concept.additive:
        for i in range(3, len(ordered)):
            window = ordered[i - 3 : i + 1]
            if not all(
                _contiguous(a.end, b.start or "") for a, b in zip(window, window[1:], strict=False)
            ):
                continue
            first = Version(
                sum(q.first.value for q in window),
                window[-1].first.accession,
                max(q.first.filed for q in window),
            )
            latest = Version(
                sum(q.latest.value for q in window),
                window[-1].latest.accession,
                max(q.latest.filed for q in window),
            )
            method = "TTM sum of quarters ending " + ", ".join(q.end for q in window)
            points.append(
                Point(window[0].start, window[-1].end, "TTM", unit, first, latest, method)
            )

    points.sort(key=lambda p: (p.end, p.ptype))
    return ConceptResult(concept.name, tuple(points), tags_used, tuple(skipped))


def write_series(engine: sqlite3.Connection, cik: str, results: list[ConceptResult]) -> int:
    """Replace the cik's series rows. Caller owns the transaction."""
    engine.execute("DELETE FROM series WHERE cik = ?", (cik,))
    rows = [
        (
            cik,
            r.concept,
            p.end,
            p.ptype,
            p.start,
            p.unit,
            p.first.value,
            p.first.accession,
            p.first.filed,
            p.latest.value,
            p.latest.accession,
            p.latest.filed,
            p.method,
            PARSER_VERSION,
        )  # fmt: skip
        for r in results
        for p in r.points
    ]
    engine.executemany(
        "INSERT INTO series (cik, concept, period_end, period_type, period_start, unit, "
        "first_value, first_accession, first_filed, latest_value, latest_accession, "
        "latest_filed, method, parser_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


# --- Sync ----------------------------------------------------------------------


@dataclass(frozen=True)
class FactsSync:
    cik: str
    facts_seen: int
    facts_new: int
    series_rows: int
    concepts: dict[str, tuple[str, ...]]  # concept → tags used
    missing: tuple[Probe, ...]  # concepts with no candidate tag, with the tags checked
    skipped_units: dict[str, tuple[str, ...]]
    refreshed: bool


def _due(engine: sqlite3.Connection, cik: str, now: datetime) -> bool:
    row = engine.execute(
        "SELECT fetched_at FROM refresh_state WHERE name = ?", (f"companyfacts:{cik}",)
    ).fetchone()
    if row is None:
        return True
    fetched = datetime.fromisoformat(row["fetched_at"])
    if now - fetched >= FACTS_BACKSTOP:
        return True
    marks = ",".join("?" * len(REFRESH_FORMS))
    newer = engine.execute(
        "SELECT 1 FROM filing f JOIN filing_cik c ON c.accession = f.accession "
        f"WHERE c.cik = ? AND f.filed >= ? AND (f.form IN ({marks}) "
        "OR (f.form IN ('6-K', '6-K/A') AND f.is_xbrl = 1) "
        "OR (f.form IN ('8-K', '8-K/A') AND ',' || f.items || ',' LIKE '%,2.02,%')) LIMIT 1",
        (cik, fetched.date().isoformat(), *REFRESH_FORMS),
    ).fetchone()
    return newer is not None


def forces_facts(form: str, is_xbrl: bool | int | None) -> bool:
    """Whether a new filing of this form forces a companyfacts sync (SB.11): periodic
    forms, and a 6-K only when it carries XBRL (GFS 2024 Q1–Q2 6-Ks had none)."""
    if form in REFRESH_FORMS:
        return True
    return form in XBRL_6K_FORMS and bool(is_xbrl)


def rebuild_series(engine: sqlite3.Connection, cik: str) -> tuple[int, int]:
    """Rebuild a company's `series` from stored facts with the current concept map (0 SEC
    requests; used after a parser-version change). Returns (concepts built, rows)."""
    norm = normalize_cik(cik) or cik
    results = [r for c in CONCEPTS if (r := build_concept(engine, norm, c)) and r.points]
    engine.execute("BEGIN")
    try:
        rows = write_series(engine, norm, results)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return len(results), rows


def sync_facts(
    client: SecClient,
    engine: sqlite3.Connection,
    cik: str,
    now: datetime,
    *,
    force: bool = False,
) -> Result[FactsSync]:
    """Fetch companyfacts when due (7 days, or a newer 10-K/10-Q/earnings 8-K), store, rebuild."""
    norm = normalize_cik(cik)
    if norm is None:
        return Empty((Probe("CIK", str(cik), "not a CIK"),))

    url = FACTS_URL.format(cik=norm)
    seen = new = 0
    refreshed = force or _due(engine, norm, now)
    if refreshed:
        res = client.get_json(url, ttl_s=CACHE_TTL_S, fresh=force)
        if not isinstance(res, Ok):
            return res  # NotFound: no companyfacts file (e.g. no XBRL filer); Failed: retry
        if not isinstance(res.data, dict) or "facts" not in res.data:
            return Failed("companyfacts unreadable: no 'facts'", url=url)
        engine.execute("BEGIN")
        try:
            seen, new = store_facts(engine, norm, res.data)
            engine.execute(
                "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (name) DO UPDATE SET "
                "source_ref = excluded.source_ref, fetched_at = excluded.fetched_at, "
                "detail = excluded.detail",
                (f"companyfacts:{norm}", url, iso(now), json.dumps({"seen": seen, "new": new})),
            )
            engine.execute("COMMIT")
        except Exception:
            engine.execute("ROLLBACK")
            raise

    results, missing = [], []
    for concept in CONCEPTS:
        built = build_concept(engine, norm, concept)
        if built is None or not built.points:
            checked = ", ".join(f"{t}:{g}" for t, g in concept.tags)
            missing.append(Probe(f"concept {concept.name}", checked, "no facts for any tag"))
        else:
            results.append(built)
    engine.execute("BEGIN")
    try:
        rows = write_series(engine, norm, results)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise

    summary = FactsSync(
        cik=norm,
        facts_seen=seen,
        facts_new=new,
        series_rows=rows,
        concepts={r.concept: r.tags_used for r in results},
        missing=tuple(missing),
        skipped_units={r.concept: r.skipped_units for r in results if r.skipped_units},
        refreshed=refreshed,
    )
    return Ok(summary, source_ref=url, fetched_at=iso(now))


# --- Reads -----------------------------------------------------------------------


@dataclass(frozen=True)
class SeriesRow:
    concept: str
    start: str | None
    end: str
    ptype: str
    unit: str
    first: Version
    latest: Version
    method: str

    @property
    def restated(self) -> bool:
        return self.first.value != self.latest.value


def get_series(
    engine: sqlite3.Connection, cik: str, concept: str, ptype: str | None = None
) -> list[SeriesRow]:
    """Stored series for a concept, oldest first. ptype: Q, FY, TTM or I."""
    sql = "SELECT * FROM series WHERE cik = ? AND concept = ?"
    args: list[Any] = [normalize_cik(cik) or cik, concept]
    if ptype:
        sql += " AND period_type = ?"
        args.append(ptype)
    sql += " ORDER BY period_end, period_type"
    return [
        SeriesRow(
            r["concept"],
            r["period_start"],
            r["period_end"],
            r["period_type"],
            r["unit"],
            Version(r["first_value"], r["first_accession"], r["first_filed"]),
            Version(r["latest_value"], r["latest_accession"], r["latest_filed"]),
            r["method"],
        )  # fmt: skip
        for r in engine.execute(sql, args)
    ]
