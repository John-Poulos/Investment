"""Capital allocation per spender (D-M02-19 (3), D-M02-31).

Trailing four quarters with the last fiscal year beside it: operating cash flow, capex
on the company's own definition, OCF ÷ capex, debt raised and repaid (every mapped
tag summed), equity issued, buybacks, shares withheld for employee taxes, dividends,
finance-lease principal (in capex when the definition includes it, otherwise its own
line; never in debt repayment). Association, not cause.

Coverage: the mapped financing lines are checked against the reported net cash from
financing. Coverage = mapped gross flows ÷ (mapped gross flows + |unexplained residual|),
so a small net total does not make the ratio jump. Below 80% the block reads
"partial: X% of financing flows mapped" and the company's unmapped financing-looking
facts for the window are raised as `m02_tag` review items (map as debt raised / debt
repaid / equity issued / buybacks / dividends / other / ignore). A standard tag's
mapping applies to every company; a company extension tag to that company only.
Mappings live in `fin_tag_map` (who/when, undoable); built-ins below.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime

from engine.moneyflow.actuals import LEASE_PRINCIPAL, Book, compute, recipe_for
from engine.moneyflow.periods import Span, point_at
from engine.sec.client import iso

COVERAGE_MIN = 0.80
OCF = "us-gaap:NetCashProvidedByUsedInOperatingActivities"
FINANCING = "us-gaap:NetCashProvidedByUsedInFinancingActivities"
ROLES = (
    "debt_raised",
    "debt_repaid",
    "equity_issued",
    "buybacks",
    "withholding",
    "dividends",
    "lease_principal",
    "debt_net",
    "other",
    "ignore",
)
OWNER_ROLES = (
    "debt_raised",
    "debt_repaid",
    "equity_issued",
    "buybacks",
    "dividends",
    "other",
    "ignore",
)
# Sign of each role in net financing cash: inflows +, outflows −. debt_net and other are
# reported signed ("ProceedsFromRepaymentsOf…": + when net raised).
SIGN = {
    "debt_raised": 1,
    "equity_issued": 1,
    "debt_repaid": -1,
    "buybacks": -1,
    "withholding": -1,
    "dividends": -1,
    "lease_principal": -1,
    "debt_net": 1,
}


def _g(*tags: str) -> list[str]:
    return [f"us-gaap:{t}" for t in tags]


BUILT_IN: dict[str, str] = {
    **{
        t: "debt_raised"
        for t in _g(
            "ProceedsFromIssuanceOfLongTermDebt",
            "ProceedsFromIssuanceOfDebt",
            "ProceedsFromIssuanceOfSeniorLongTermDebt",
            "ProceedsFromShortTermDebt",
            "ProceedsFromDebtMaturingInMoreThanThreeMonths",
            "ProceedsFromIssuanceOfCommercialPaper",
            "ProceedsFromIssuanceOfUnsecuredDebt",
            "ProceedsFromIssuanceOfSecuredDebt",
            "ProceedsFromConvertibleDebt",
            "ProceedsFromLinesOfCredit",
            "ProceedsFromIssuanceOfLongTermDebtAndCapitalSecuritiesNet",
        )
    },
    **{
        t: "debt_repaid"
        for t in _g(
            "RepaymentsOfLongTermDebt",
            "RepaymentsOfDebt",
            "RepaymentsOfSeniorDebt",
            "RepaymentsOfShortTermDebt",
            "RepaymentsOfDebtMaturingInMoreThanThreeMonths",
            "RepaymentsOfCommercialPaper",
            "RepaymentsOfUnsecuredDebt",
            "RepaymentsOfSecuredDebt",
            "RepaymentsOfConvertibleDebt",
            "RepaymentsOfLinesOfCredit",
        )
    },
    **{
        t: "debt_net"
        for t in _g(
            "ProceedsFromRepaymentsOfShortTermDebt",
            "ProceedsFromRepaymentsOfCommercialPaper",
            "ProceedsFromRepaymentsOfShortTermDebtMaturingInThreeMonthsOrLess",
            "ProceedsFromRepaymentsOfDebt",
            "ProceedsFromRepaymentsOfLinesOfCredit",
        )
    },
    **{
        t: "equity_issued"
        for t in _g("ProceedsFromIssuanceOfCommonStock", "ProceedsFromIssuanceOrSaleOfEquity")
    },
    "us-gaap:PaymentsForRepurchaseOfCommonStock": "buybacks",
    "us-gaap:PaymentsRelatedToTaxWithholdingForShareBasedCompensation": "withholding",
    **{t: "dividends" for t in _g("PaymentsOfDividends", "PaymentsOfDividendsCommonStock")},
    LEASE_PRINCIPAL: "lease_principal",
}
# Tags that are alternatives (a total and its common-stock part): only the first present.
ALTERNATIVES = (
    ("us-gaap:PaymentsOfDividends", "us-gaap:PaymentsOfDividendsCommonStock"),
    ("us-gaap:ProceedsFromIssuanceOfCommonStock", "us-gaap:ProceedsFromIssuanceOrSaleOfEquity"),
    ("us-gaap:RepaymentsOfDebt", "us-gaap:RepaymentsOfLongTermDebt"),
    ("us-gaap:ProceedsFromIssuanceOfDebt", "us-gaap:ProceedsFromIssuanceOfLongTermDebt"),
)
# Cash-flow tag names that look like financing lines (discovery only; owner decides).
_FIN_NAME = re.compile(r"^(?:Proceeds|Repayments?|Payments)(?:From|Of|For|To|Related)?")
_NOT_FIN = re.compile(
    r"Acquire|PropertyPlant|ProductiveAssets|Investments?|Securities|Businesses|Intangible|"
    r"Divestiture|SaleOfOtherAssets|Insurance|Interest|IncomeTax|Royalt|Collection|Loans?To",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Line:
    role: str
    value: float | None  # None = not reported (never zero)
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Window:
    label: str  # "TTM to 2026-06-30" | "FY2025 (to 2025-12-31)"
    ptype: str  # TTM | FY
    end: str
    ocf: float | None
    capex: float | None
    capex_note: str
    financing: float | None
    lines: dict[str, Line]
    coverage: float | None
    unmapped: tuple[tuple[str, float], ...] = field(default_factory=tuple)
    lease_in_capex: bool = False  # finance-lease principal counted in capex (own definition)

    @property
    def ocf_cover(self) -> float | None:
        if self.ocf is None or not self.capex:
            return None
        return self.ocf / self.capex

    @property
    def net_debt(self) -> float | None:
        parts = [self.lines[r].value for r in ("debt_raised", "debt_net") if r in self.lines]
        rep = self.lines.get("debt_repaid")
        vals = [v for v in parts if v is not None]
        if not vals and (rep is None or rep.value is None):
            return None
        return sum(vals) - (rep.value or 0 if rep else 0)

    @property
    def net_equity(self) -> float | None:
        vals = {
            r: self.lines[r].value
            for r in ("equity_issued", "buybacks", "withholding")
            if r in self.lines and self.lines[r].value is not None
        }
        if not vals:
            return None
        return vals.get("equity_issued", 0) - vals.get("buybacks", 0) - vals.get("withholding", 0)

    @property
    def coverage_text(self) -> str:
        if self.coverage is None:
            return "coverage unknown (no financing total)"
        if self.coverage < COVERAGE_MIN:
            return f"partial: {self.coverage:.0%} of financing flows mapped"
        return f"coverage: {self.coverage:.0%} of financing flows mapped"


def mappings(engine: sqlite3.Connection, cik: str) -> dict[str, str]:
    """Built-in map overlaid by the owner's decisions (standard tags global, extensions per
    company)."""
    out = dict(BUILT_IN)
    for r in engine.execute(
        "SELECT taxonomy, tag, role FROM fin_tag_map WHERE cik IS NULL OR cik = ? "
        "ORDER BY cik IS NOT NULL",
        (cik,),
    ):
        out[f"{r['taxonomy']}:{r['tag']}"] = r["role"]
    return out


def _value(book: Book, term: str, ptype: str, end: date) -> float | None:
    p = point_at(book.points(term), ptype, end)
    return float(p.latest.value) if p else None


def _candidates(engine: sqlite3.Connection, cik: str, end: str) -> list[str]:
    """Duration facts of this company ending at the window end, financing-looking names."""
    rows = engine.execute(
        "SELECT DISTINCT taxonomy, tag FROM fact WHERE cik = ? AND period_start IS NOT NULL "
        "AND period_end BETWEEN date(?, '-10 days') AND date(?, '+10 days') "
        "AND taxonomy NOT IN ('dei', 'srt')",
        (cik, end, end),
    )
    return [
        f"{r['taxonomy']}:{r['tag']}"
        for r in rows
        if _FIN_NAME.match(r["tag"]) and not _NOT_FIN.search(r["tag"])
    ]


def window(
    engine: sqlite3.Connection,
    book: Book,
    ptype: str,
    end: date,
    clause: str | None,
    override: dict | None,
) -> Window:
    recipe = recipe_for(clause, override)
    rv = compute(book, recipe, Span(ptype, ptype, end))
    lease_in_capex = LEASE_PRINCIPAL in recipe.plus
    maps = mappings(engine, book.cik)
    skip = {b for a, b in ALTERNATIVES if _value(book, a, ptype, end) is not None}

    lines: dict[str, list[tuple[str, float]]] = {}
    for term, role in maps.items():
        if role == "ignore" or term in skip:
            continue
        if role == "lease_principal" and lease_in_capex:
            continue  # counted in capex (Meta), never twice
        v = _value(book, term, ptype, end)
        if v is not None:
            lines.setdefault(role, []).append((term, v))
    financing = _value(book, FINANCING, ptype, end)

    explained = gross = 0.0
    for role, items in lines.items():
        for term, v in items:
            sign = SIGN.get(role)
            if sign is None:  # 'other': signed by its name
                sign = -1 if term.split(":")[1].startswith(("Payments", "Repayment")) else 1
            explained += sign * v
            gross += abs(v)
    if lease_in_capex and (lp := _value(book, LEASE_PRINCIPAL, ptype, end)) is not None:
        explained -= lp  # paid in financing even when the definition counts it as capex
        gross += abs(lp)
    coverage = unmapped = None
    if financing is not None:
        residual = abs(financing - explained)
        coverage = gross / (gross + residual) if gross + residual > 0 else 1.0
        if coverage < COVERAGE_MIN:
            known = set(maps)
            unmapped = tuple(
                (t, v)
                for t in _candidates(engine, book.cik, end.isoformat())
                if t not in known and (v := _value(book, t, ptype, end)) is not None
            )

    out_lines = {
        role: Line(role, sum(v for _, v in items), tuple(t for t, _ in items))
        for role, items in lines.items()
    }
    label = f"TTM to {end.isoformat()}" if ptype == "TTM" else f"fiscal year to {end.isoformat()}"
    return Window(
        label,
        ptype,
        end.isoformat(),
        _value(book, OCF, ptype, end),
        rv.value if rv else None,
        (rv.recipe.label + (f"; {rv.note}" if rv.note else "")) if rv else "no capex reported",
        financing,
        out_lines,
        coverage,
        unmapped or (),
        lease_in_capex,
    )


def allocation(
    engine: sqlite3.Connection, cik: str, clause: str | None, override: dict | None = None
) -> list[Window]:
    """TTM to the latest quarter, and the last fiscal year."""
    book = Book(engine, cik)
    ocf = book.points(OCF)
    out = []
    for ptype in ("TTM", "FY"):
        pts = [p for p in ocf if p.ptype == ptype]
        if pts:
            out.append(
                window(engine, book, ptype, date.fromisoformat(pts[-1].end), clause, override)
            )
    return out


def raise_tag_items(
    engine: sqlite3.Connection, cik: str, ticker: str, windows: list[Window], now: datetime
) -> int:
    """One m02_tag item per unmapped financing-looking tag (coverage < 80%)."""
    from engine.themes.proposals import propose

    n = 0
    for w in windows:
        for term, v in w.unmapped:
            taxonomy, tag = term.split(":", 1)
            scope = "all" if taxonomy in ("us-gaap", "ifrs-full") else cik
            payload = {
                "ticker": ticker,
                "taxonomy": taxonomy,
                "tag": tag,
                "value": v,
                "window": w.label,
                "coverage": w.coverage,
                "scope": scope,
                "why": f"{w.coverage_text}; {tag} = {v / 1e6:,.0f}M in {w.label}",
            }
            res = propose(
                engine,
                "m02_tag",
                f"{scope}:{term}",
                f"{ticker}: how does {term} count in financing flows?",
                payload,
                now,
                cik=cik,
            )
            n += res in ("queued", "overflow")
    return n


def map_tag(
    engine: sqlite3.Connection,
    payload: dict,
    role: str,
    item_id: int | None,
    by: str,
    now: datetime,
) -> None:
    if role not in OWNER_ROLES:
        raise ValueError(f"unknown role {role}")
    cik = None if payload.get("scope") == "all" else payload.get("scope")
    engine.execute(
        "INSERT INTO fin_tag_map (cik, taxonomy, tag, role, item_id, mapped_by, mapped_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (ifnull(cik, ''), taxonomy, tag) DO UPDATE "
        "SET role = excluded.role, item_id = excluded.item_id, mapped_by = excluded.mapped_by, "
        "mapped_at = excluded.mapped_at",
        (cik, payload["taxonomy"], payload["tag"], role, item_id, by, iso(now)),
    )


def unmap(engine: sqlite3.Connection, map_id: int, by: str, now: datetime) -> bool:
    """Undo an owner mapping: the row goes and its m02_tag item returns to the queue."""
    row = engine.execute("SELECT * FROM fin_tag_map WHERE map_id = ?", (map_id,)).fetchone()
    if row is None:
        return False
    scope = row["cik"] or "all"
    key = f"m02_tag:{scope}:{row['taxonomy']}:{row['tag']}"
    engine.execute("DELETE FROM fin_tag_map WHERE map_id = ?", (map_id,))
    prop = engine.execute("SELECT item_id FROM m02_proposal WHERE prop_key = ?", (key,)).fetchone()
    if prop and prop[0]:
        engine.execute(
            "UPDATE review_queue SET resolved_at = NULL, resolution = NULL, resolved_by = NULL, "
            "note = coalesce(note, '') || ? WHERE item_id = ? AND resolved_at IS NOT NULL",
            (f" [mapping undone by {by} {iso(now)[:16]}]", prop[0]),
        )
    return True


def mapping_list(engine: sqlite3.Connection) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT m.*, e.name FROM fin_tag_map m LEFT JOIN entity e ON e.cik = m.cik "
        "ORDER BY mapped_at DESC"
    ).fetchall()
