"""View models for money flow: the company "Money flow" tab and the theme's spender list.

Labelled "hypothesis, not backtested"; guidance is a forecast, not a commitment. No
cross-company totals (D-M02-5): every spender keeps its own period label, and the theme
list shows each spender's own guided increase (its contribution), never a sum.
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import date

from engine.moneyflow import links
from engine.moneyflow.actuals import (
    Actual,
    Book,
    actual_for,
    latest_clause,
    overrides_by_cik,
    recipe_for,
)
from engine.moneyflow.allocation import Window, allocation
from engine.moneyflow.guided import GuidedLine, guided_lines, guided_vs_actual, no_guidance
from engine.moneyflow.stated import stated_for
from engine.sec.xbrl_facts import get_series

QUARTERS_SHOWN = 6


@dataclass(frozen=True)
class RpoRow:
    end: str
    value: float
    yoy: float | None


@dataclass(frozen=True)
class Rpo:
    rows: tuple[RpoRow, ...]
    own_median_yoy: float | None  # the company's own history (never across companies, S79)

    @property
    def reported(self) -> bool:
        return bool(self.rows)

    @property
    def latest_vs_own(self) -> float | None:
        if not self.rows or self.rows[-1].yoy is None or self.own_median_yoy is None:
            return None
        return self.rows[-1].yoy - self.own_median_yoy


def rpo(engine: sqlite3.Connection, cik: str) -> Rpo:
    pts = [p for p in get_series(engine, cik, "rpo", "I") if p.latest.value is not None]
    rows = []
    for i, p in enumerate(pts):
        end = date.fromisoformat(p.end)
        prior = next(
            (q for q in pts[:i] if 350 <= (end - date.fromisoformat(q.end)).days <= 380), None
        )
        yoy = (p.latest.value / prior.latest.value - 1) if prior and prior.latest.value else None
        rows.append(RpoRow(p.end, float(p.latest.value), yoy))
    history = [r.yoy for r in rows[-9:-1] if r.yoy is not None]
    return Rpo(tuple(rows[-8:]), statistics.median(history) if len(history) >= 3 else None)


@dataclass(frozen=True)
class ActualRow:
    period: str
    actual: Actual


@dataclass
class CompanyMoneyFlow:
    cik: str
    recipe_label: str
    recipe_source: str
    guided: list[GuidedLine]
    no_guidance: bool
    actuals: list[ActualRow]
    windows: list[Window]
    links: list[sqlite3.Row]
    rpo: Rpo
    verdicts: dict[str, str] = field(default_factory=dict)


def _quarter_labels(book: Book) -> list[str]:
    """Fiscal labels of the company's latest reported quarters and years, newest first."""
    from engine.calls.transcripts import fiscal_quarter

    pts = [
        p
        for p in book.points("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment")
        + book.points("us-gaap:PaymentsToAcquireProductiveAssets")
        if p.ptype == "Q"
    ]
    labels = []
    for p in sorted(pts, key=lambda p: p.end, reverse=True):
        # the quarter that ended on p.end = the last quarter before the day after it
        fq = fiscal_quarter(date.fromordinal(date.fromisoformat(p.end).toordinal() + 10), book.fye)
        if fq:
            label = f"FY{fq[0]} Q{fq[1]}"
            if label not in labels:
                labels.append(label)
    return labels[:QUARTERS_SHOWN]


def company_view(
    engine: sqlite3.Connection, cik: str, today: date, corpus: sqlite3.Connection | None = None
) -> CompanyMoneyFlow:
    override = overrides_by_cik(engine).get(cik)
    clause = latest_clause(engine, cik)
    recipe = recipe_for(clause, override)
    book = Book(engine, cik)
    stated = stated_for(engine, cik)
    labels = _quarter_labels(book)
    for lbl in list(labels):  # the fiscal years those quarters belong to
        fy = lbl.split()[0]
        if fy not in labels:
            labels.append(fy)
    rows = [ActualRow(lbl, actual_for(book, lbl, clause, override, stated)) for lbl in labels]
    lines = guided_lines(engine, cik, today, corpus, override)
    return CompanyMoneyFlow(
        cik=cik,
        recipe_label=recipe.label,
        recipe_source=recipe.source,
        guided=lines,
        no_guidance=no_guidance(engine, cik),
        actuals=[r for r in rows if r.actual.status != "missing"],
        windows=allocation(engine, cik, clause, override),
        links=links.company_links(engine, cik),
        rpo=rpo(engine, cik),
        verdicts={g.period: v for g in lines if (v := guided_vs_actual(g))},
    )


@dataclass(frozen=True)
class SpenderRow:
    cik: str
    ticker: str
    line: GuidedLine
    contribution: float | None  # guided increase vs last year, own definition (mid / floor)
    quote: str


@dataclass
class ThemeMoneyFlow:
    ranked: list[SpenderRow]
    unranked: list[SpenderRow]
    suppliers: list[tuple[str, str, Rpo]]  # ticker, cik, RPO
    open_links: int


def _ticker(engine: sqlite3.Connection, cik: str) -> str:
    row = engine.execute(
        "SELECT ticker FROM ticker WHERE cik = ? AND valid_to IS NULL "
        "ORDER BY length(ticker), ticker LIMIT 1",
        (cik,),
    ).fetchone()
    return row[0] if row else cik


def theme_view(
    engine: sqlite3.Connection,
    theme_id: int,
    theme_key: str,
    today: date,
    corpus: sqlite3.Connection | None = None,
) -> ThemeMoneyFlow:
    overrides = overrides_by_cik(engine)
    ranked, unranked = [], []
    for cik, link in links.confirmed(engine, theme_id).items():
        ticker = _ticker(engine, cik)
        for g in guided_lines(engine, cik, today, corpus, overrides.get(cik)):
            if g.ended or " Q" in g.period:
                continue  # annual, not yet ended: the money-flow horizon
            base = g.base.shown if g.base else None
            contrib = None
            if base is not None and g.low is not None:
                level = g.low if g.bound == "floor" else (g.low + g.high) / 2
                contrib = level - base
            row = SpenderRow(cik, ticker, g, contrib, link["quote"])
            (ranked if g.ranked else unranked).append(row)
    ranked.sort(key=lambda r: -r.line.rank_value)
    suppliers = []
    tickers = {
        r[0]
        for r in engine.execute(
            "SELECT ticker FROM theme_company WHERE theme_id = ? AND status = 'active'", (theme_id,)
        )
    }
    tickers |= {
        r[0]
        for r in engine.execute(
            "SELECT ticker FROM tier_member WHERE theme_key = ? AND status = 'active'", (theme_key,)
        )
    }
    spender_ciks = {r.cik for r in ranked + unranked}
    for t in sorted(tickers):
        row = engine.execute(
            "SELECT cik FROM ticker WHERE ticker = ? AND valid_to IS NULL", (t,)
        ).fetchone()
        if row and row[0] not in spender_ciks:
            suppliers.append((t, row[0], rpo(engine, row[0])))
    open_links = engine.execute(
        "SELECT count(DISTINCT cik) FROM spender_link WHERE theme_id = ? AND status = 'open'",
        (theme_id,),
    ).fetchone()[0]
    return ThemeMoneyFlow(ranked, unranked, suppliers, open_links)


def money(x: float | None) -> str:
    if x is None:
        return "—"
    sign = "−" if x < 0 else ""
    x = abs(x)
    if x >= 1e9:
        return f"{sign}${x / 1e9:,.2f}B"
    return f"{sign}${x / 1e6:,.0f}M"
