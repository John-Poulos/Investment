"""R22 buy and sale cards per Form 4 (M07 rules 1, 3, 4, 5; D-M07-3, -4).

- Stake (D-M07-4) = every non-derivative line on the form: the last `shares_after` of each
  traded line (security, D/I, nature) plus every non-derivative holding line (form4-2).
  Derivative lines are counted apart, never in the stake. A form parsed before form4-2 has
  no holding lines: its stake is "traded lines only" until the re-parse.
  Buy: % of the stake after. Sale: % of the stake before = stake after + the form's S shares
  (Huang: 100,000 / (859,048,625 + 100,000) = 0.012%).
- Cover count and implied float from M04 (`financials/shares.py`, D-M04-2): the latest value
  dated on or before the trade, both split-adjusted to today, so the trade's shares are
  scaled by the splits after the trade date. No cover → missing; no float → "float
  unknown" (20-F filer, new listing), never 0.
- ADV: mean raw volume of the 20 bars up to the trade date, earlier bars scaled by any split
  inside the window (the `splits_after` guard); fewer than 20 bars → missing.
"""

from __future__ import annotations

import sqlite3
from bisect import bisect_right
from dataclasses import dataclass, field

from engine.financials import shares as fshares
from engine.ownership.classes import Verdict, class_of
from engine.ownership.rows import HoldingLine, Issuer, Row

ADV_DAYS = 20
WARN_STAKE_PCT = 10.0  # † D-M07-3: non_plan_unclassified warns at ≥ 10% of stake


@dataclass(frozen=True)
class Measure:
    """A denominator: value (today's shares) with its source, or the reason it is missing."""

    value: float | None
    text: str  # "3,225,448,889 (dei:EntityCommonStockSharesOutstanding, 2025-07-17)" or why

    def pct(self, shares: float | None) -> float | None:
        if self.value is None or not self.value or shares is None:
            return None
        return shares / self.value * 100


class Market:
    """Per-company denominators (cover count, implied float, splits, volume), loaded once."""

    def __init__(self, engine: sqlite3.Connection, cik: str) -> None:
        self.engine = engine
        self.cik = cik
        self._covers: list | None = None
        self._floats: list | None = None
        self._splits: list[tuple[str, float]] | None = None
        self._bars: dict[str, list[tuple[str, float | None, float]]] = {}

    # splits ---------------------------------------------------------------------------
    def splits(self) -> list[tuple[str, float]]:
        if self._splits is None:
            symbols = fshares.price_symbols(self.engine, self.cik)
            out: dict[str, float] = {}
            if symbols:
                marks = ",".join("?" * len(symbols))
                for r in self.engine.execute(
                    f"SELECT date, split_factor FROM price_bar WHERE symbol IN ({marks}) AND "
                    "split_factor IS NOT NULL AND split_factor != 1 ORDER BY date",
                    symbols,
                ):
                    out.setdefault(r["date"], float(r["split_factor"]))  # GOOG = GOOGL split
            self._splits = sorted(out.items())
        return self._splits

    def factor_after(self, day: str) -> float:
        f = 1.0
        for d, s in self.splits():
            if d > day:
                f *= s
        return f

    # cover and float ------------------------------------------------------------------
    def cover(self, day: str) -> Measure:
        if self._covers is None:
            self._covers = fshares.cover_counts(self.engine, self.cik)
        for v in self._covers:
            if v.date <= day and v.value:
                src = f"{v.tag}, {v.date}" + (f", {v.accession}" if v.accession else "")
                note = f"; {v.note}" if v.note else ""
                return Measure(float(v.value), f"{v.value:,.0f} ({src}{note})")
        if not self._covers:
            return Measure(None, f"missing: {fshares.cover_missing_reason(self.engine, self.cik)}")
        return Measure(None, f"missing: no cover count on or before {day}")

    def float_(self, day: str) -> Measure:
        if self._floats is None:
            self._floats = fshares.implied_float(self.engine, self.cik)
        if not self._floats:
            return Measure(None, "float unknown (no dei:EntityPublicFloat stored: 20-F filer or "
                                 "new listing)")  # fmt: skip
        for v in self._floats:
            if v.date <= day:
                if v.value is None:
                    return Measure(None, f"float unknown ({v.note})")
                return Measure(float(v.value), f"{v.value:,.0f} ({v.note})")
        return Measure(None, f"float unknown (first float date {self._floats[-1].date} is after "
                             f"{day})")  # fmt: skip

    # volume -----------------------------------------------------------------------------
    def _symbol_bars(self) -> tuple[str | None, list[tuple[str, float | None, float]]]:
        for s in fshares.price_symbols(self.engine, self.cik):
            if s not in self._bars:
                self._bars[s] = [
                    (r["date"], None if r["volume"] is None else float(r["volume"]),
                     float(r["split_factor"] or 1))
                    for r in self.engine.execute(
                        "SELECT date, volume, split_factor FROM price_bar WHERE symbol = ? "
                        "ORDER BY date", (s,))
                ]  # fmt: skip
            if self._bars[s]:
                return s, self._bars[s]
        return None, []

    def adv(self, day: str) -> Measure:
        symbol, bars = self._symbol_bars()
        if symbol is None:
            return Measure(None, "missing: no price bars stored")
        idx = bisect_right([b[0] for b in bars], day)
        window = [b for b in bars[:idx] if b[1] is not None][-ADV_DAYS:]
        if len(window) < ADV_DAYS:
            return Measure(None, f"missing: {len(window)} bars with volume up to {day} "
                                 f"(needs {ADV_DAYS})")  # fmt: skip
        splits = [(b[0], b[2]) for b in bars[:idx] if b[2] != 1 and b[0] > window[0][0]]
        vols = []
        for d, v, _ in window:
            f = 1.0
            for sd, s in splits:
                if sd > d:
                    f *= s
            vols.append(v * f)  # type: ignore[operator]
        adv = sum(vols) / len(vols)
        note = f"{symbol}, {window[0][0]} to {window[-1][0]}"
        if splits:
            note += "; split inside the window " + ", ".join(f"{d} ×{s:g}" for d, s in splits) + \
                    ", earlier volume scaled"  # fmt: skip
        return Measure(adv, f"{adv:,.0f} shares a day ({note})")


@dataclass
class Card:
    """One Form 4 as the Insiders tab shows it."""

    accession: str
    filed: str
    doc_type: str
    owner_cik: str | None
    owner_name: str | None
    role: str | None
    rows: list[Row]
    buys: list[Row] = field(default_factory=list)  # effective open-market P
    issuer_buys: list[Row] = field(default_factory=list)
    sales: list[Row] = field(default_factory=list)  # effective S
    others: list[Row] = field(default_factory=list)  # not in total
    replaced: list[Row] = field(default_factory=list)  # replaced by a later 4/A
    stake_after: float | None = None
    stake_lines: int = 0
    stake_note: str = ""
    derivative_lines: int = 0
    classes: dict[str, Verdict | None] = field(default_factory=dict)  # owner → class this year
    cover: Measure | None = None
    float_: Measure | None = None
    adv: Measure | None = None

    # totals -------------------------------------------------------------------------
    @staticmethod
    def _sum(rows: list[Row], attr: str) -> float | None:
        vals = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
        return sum(vals) if vals else None

    @property
    def buy_shares(self) -> float | None:
        return self._sum(self.buys, "shares")

    @property
    def buy_usd(self) -> float | None:
        return self._sum(self.buys, "usd")

    @property
    def sale_shares(self) -> float | None:
        return self._sum(self.sales, "shares")

    @property
    def sale_usd(self) -> float | None:
        return self._sum(self.sales, "usd")

    @property
    def issuer_usd(self) -> float | None:
        return self._sum(self.issuer_buys, "usd")

    @property
    def stake_before_sale(self) -> float | None:
        if self.stake_after is None:
            return None
        sold = sum(r.shares or 0 for r in self.rows if r.kind == "sale")
        return self.stake_after + sold

    def pct_stake_after_buy(self) -> float | None:
        if not self.stake_after or self.buy_shares is None:
            return None
        return self.buy_shares / self.stake_after * 100

    def pct_stake_before_sale(self) -> float | None:
        before = self.stake_before_sale
        if not before or self.sale_shares is None:
            return None
        return self.sale_shares / before * 100

    @property
    def last_trade(self) -> str:
        dates = [r.txn_date for r in (self.buys + self.sales + self.issuer_buys) if r.txn_date]
        return max(dates) if dates else self.filed

    def scaled(self, shares: float | None, market: Market) -> float | None:
        """Shares at the trade date in today's shares (splits after the trade)."""
        return None if shares is None else shares * market.factor_after(self.last_trade)

    def sale_status(self, r: Row) -> str:
        """plan | plan_na | non_plan_<class> for a sale row."""
        p = r.plan
        if p != "non_plan":
            return p or ""
        v = self.classes.get(r.owner_cik or "")
        return f"non_plan_{v.cls if v else 'unclassified'}"

    def warning(self) -> str | None:
        """D-M07-3: non-plan opportunistic, or non-plan unclassified ≥ 10% of stake."""
        statuses = {self.sale_status(r) for r in self.sales}
        if "non_plan_opportunistic" in statuses:
            return "non-plan sale by an opportunistic insider (D-M07-3)"
        pct = self.pct_stake_before_sale()
        if "non_plan_unclassified" in statuses and pct is not None and pct >= WARN_STAKE_PCT:
            return (f"non-plan sale by an unclassified insider, {pct:.1f}% of stake "
                    f"≥ {WARN_STAKE_PCT:g}% (D-M07-3)")  # fmt: skip
        return None


def stake(rows: list[Row], holdings: list[HoldingLine]) -> tuple[float | None, int, int, str]:
    """(stake after, non-derivative lines counted, derivative lines, note) for one form."""
    lines: dict[tuple, float] = {}
    for r in sorted(rows, key=lambda x: x.line):
        if r.table_kind == "non_derivative" and r.shares_after is not None:
            lines[(r.title, r.direct_indirect, r.nature)] = r.shares_after
    held = [h for h in holdings if h.table_kind == "non_derivative" and h.shares is not None]
    deriv = sum(1 for r in rows if r.table_kind == "derivative") + sum(
        1 for h in holdings if h.table_kind == "derivative"
    )
    n = len(lines) + len(held)
    if not n:
        return None, 0, deriv, "missing: no non-derivative line with shares owned"
    total = sum(lines.values()) + sum(h.shares or 0 for h in held)
    note = f"{n} non-derivative line{'s' if n != 1 else ''}"
    if rows and rows[0].parser_version < "form4-2":
        note += " (traded lines only: holding lines not parsed yet, re-parse pending)"
    if deriv:
        note += f"; {deriv} derivative line{'s' if deriv != 1 else ''} apart"
    return total, n, deriv, note


def build_cards(
    issuer: Issuer, verdicts: dict[tuple[str, int], Verdict], market: Market | None = None
) -> list[Card]:
    """One card per stored form with a P, S or issuer purchase row, newest first."""
    cards = []
    for acc, rows in issuer.by_accession().items():
        first = rows[0]
        c = Card(acc, first.filed, first.doc_type, first.owner_cik, first.owner_name, first.role,
                 rows)  # fmt: skip
        for r in rows:
            if not r.effective:
                c.replaced.append(r)
                continue
            bucket = {"buy": c.buys, "sale": c.sales, "issuer_buy": c.issuer_buys}
            bucket.get(r.kind, c.others).append(r)
        if not (c.buys or c.sales or c.issuer_buys or c.replaced):
            continue
        c.stake_after, c.stake_lines, c.derivative_lines, c.stake_note = stake(
            rows, issuer.holdings.get(acc, [])
        )
        for r in c.buys + c.sales + c.issuer_buys:
            if r.owner_cik:
                c.classes.setdefault(r.owner_cik, class_of(verdicts, r.owner_cik, r.txn_date))
        if market is not None:
            day = c.last_trade
            c.cover = market.cover(day)
            if c.sales:
                c.float_ = market.float_(day)
                c.adv = market.adv(day)
        cards.append(c)
    return sorted(cards, key=lambda c: (c.filed, c.accession), reverse=True)
