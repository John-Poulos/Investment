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
   Missing stays missing; nothing is coerced to zero.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from engine.sec.client import SecClient, iso
from engine.sec.identity import normalize_cik
from engine.sec.results import Empty, Failed, Ok, Probe, Result

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
FACTS_BACKSTOP = timedelta(days=7)
CACHE_TTL_S = 6 * 3600
PARSER_VERSION = "facts-1"
REFRESH_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F")

_CURRENCY = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class Concept:
    name: str
    tags: tuple[tuple[str, str], ...]  # (taxonomy, tag) in priority order
    unit: str  # currency | shares | per_share
    kind: str  # flow | instant
    additive: bool = True  # quarters may be derived and summed into TTM


def _gaap(*tags: str) -> tuple[tuple[str, str], ...]:
    return tuple(("us-gaap", t) for t in tags)


def _ifrs(*tags: str) -> tuple[tuple[str, str], ...]:
    return tuple(("ifrs-full", t) for t in tags)


C, F, I = "currency", "flow", "instant"  # noqa: E741

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
    Concept("da", _gaap("DepreciationDepletionAndAmortization",
            "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization")
            + _ifrs("DepreciationAndAmortisationExpense"), C, F),
    Concept("capex", _gaap("PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets")
            + _ifrs("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"), C, F),
    Concept("operating_cash_flow", _gaap("NetCashProvidedByUsedInOperatingActivities")
            + _ifrs("CashFlowsFromUsedInOperatingActivities"), C, F),
    Concept("interest_expense", _gaap("InterestExpense", "InterestExpenseNonoperating",
            "InterestExpenseDebt"), C, F),
    Concept("ppe_net", _gaap("PropertyPlantAndEquipmentNet")
            + _ifrs("PropertyPlantAndEquipment"), C, I),
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
    Concept("shares_outstanding", _gaap("CommonStockSharesOutstanding")
            + (("dei", "EntityCommonStockSharesOutstanding"),), "shares", I, additive=False),
    Concept("rpo", _gaap("RevenueRemainingPerformanceObligation"), C, I),
)  # fmt: skip
CONCEPT_BY_NAME = {c.name: c for c in CONCEPTS}


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


def build_concept(engine: sqlite3.Connection, cik: str, concept: Concept) -> ConceptResult | None:
    """Normalized points for one concept, or None if no candidate tag has facts."""
    rank = {tag: i for i, tag in enumerate(concept.tags)}
    clauses = " OR ".join("(taxonomy = ? AND tag = ?)" for _ in concept.tags)
    args: list[Any] = [cik] + [x for pair in concept.tags for x in pair]
    rows = engine.execute(
        "SELECT taxonomy, tag, unit, period_start, period_end, value, accession, filed "
        f"FROM fact WHERE cik = ? AND ({clauses})",
        args,
    ).fetchall()
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
    for period, group in by_period.items():
        best = min(rank[(r["taxonomy"], r["tag"])] for r in group)
        chosen = sorted(
            (r for r in group if rank[(r["taxonomy"], r["tag"])] == best),
            key=lambda r: (r["filed"], r["accession"]),
        )
        tag = f"{chosen[0]['taxonomy']}:{chosen[0]['tag']}"
        first, last = chosen[0], chosen[-1]
        reported[period] = (
            tag,
            Version(first["value"], first["accession"], first["filed"]),
            Version(last["value"], last["accession"], last["filed"]),
        )
    tags_used = tuple(sorted({t for t, _, _ in reported.values()}))

    points: list[Point] = []
    if concept.kind == "instant":
        for (start, end), (tag, first, latest) in sorted(reported.items(), key=lambda kv: kv[0][1]):
            if start is None:
                points.append(Point(None, end, "I", unit, first, latest, f"reported {tag}"))
        return ConceptResult(concept.name, tuple(points), tags_used, tuple(skipped))

    typed = {p: (classify(p[0], p[1]), v) for p, v in reported.items() if p[0] is not None}
    quarters: dict[str, Point] = {}  # by end date
    for (start, end), (ptype, (tag, first, latest)) in typed.items():
        if ptype == "Q":
            quarters.setdefault(end, Point(start, end, "Q", unit, first, latest, f"reported {tag}"))
        elif ptype == "FY":
            points.append(Point(start, end, "FY", unit, first, latest, f"reported {tag}"))

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
        "OR (f.form IN ('8-K', '8-K/A') AND ',' || f.items || ',' LIKE '%,2.02,%')) LIMIT 1",
        (cik, fetched.date().isoformat(), *REFRESH_FORMS),
    ).fetchone()
    return newer is not None


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
        res = client.get_json(url, ttl_s=CACHE_TTL_S)
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
