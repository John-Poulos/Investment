"""Normalized earnings power (NEP), the shared helper (D-M04-106; M08 Part 1, D-M08-3).

One definition for M08 now (cyclical headline `val_ev_nebit`, `val_p_neps`) and M04's
deferred Part 8b gauge later (`normalized_ep_*`, `overreaction_gap`; D-M04-54, -57, -83).
Pure functions on fiscal-year facts; the caller chooses which facts are known (today's
read, or first-filed values at a past quarter-end, D-M08-2).

- **Cycle series.** The CvD trough series (`cvd.trough_row`): annual gross margin with the
  tagged inventory write-down added back. A company with fewer than 3 fiscal years of gross
  margin (no cost of revenue: banks, many services firms) uses operating margin, labelled.
- **Window (D-M04-83).** Turning points confirmed by a 5 pp† reversal (`cvd.turning_points`,
  D-M04-54). The latest completed cycle runs from the earlier of the last two confirmed
  troughs **up to the year before the later one**: each trough year is counted once across
  consecutive cycles (endpoint convention, D-M04-106). Fewer than two confirmed troughs →
  the longest available history, labelled "no completed cycle". Fewer than 3† fiscal years
  with revenue and operating income in the window → missing.
- **Normalized EBIT** = cycle-average revenue × cycle-average operating margin (ratio of
  sums; equals the average operating income), and on the current-revenue base = the same
  margin × TTM revenue (M04's gauge base, D-M04-54); both are returned.
- **Normalized EPS** = cycle-average net income attributable ÷ the latest diluted weighted
  shares (split-adjusted by the caller): split-safe and buyback-aware, unlike an average of
  reported EPS, which mixes share counts across splits (D-M04-106).
- Reported basis only; the ex-items basis (D-M04-66) arrives with M04 8b.

Missing stays missing: a year without revenue or operating income is left out and named.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from engine.financials.capex import fiscal_label, is_fy_end, near
from engine.financials.cvd import turning_points
from engine.sec.asof import AsOfPoint
from engine.sec.xbrl_facts import Concept
from engine.signals import Source

SWING_PP = 5.0  # D-M04-54
MIN_YEARS = 3  # † fiscal years in the window (D-M04-106)
MIN_GM_YEARS = 3  # gross-margin years for the CvD series (as `cvd.trough_row`)

Points = Callable[[str | Concept, str], dict[str, AsOfPoint]]


@dataclass(frozen=True)
class Year:
    end: str
    revenue: float | None = None
    oi: float | None = None
    ni: float | None = None
    gross: float | None = None
    writedown: float = 0.0
    eps: float | None = None  # reported diluted EPS (cyclical flag, display)
    sources: tuple[Source, ...] = ()

    @property
    def label(self) -> str:
        return fiscal_label(self.end)

    @property
    def op_margin(self) -> float | None:
        if self.revenue is None or self.oi is None or self.revenue <= 0:
            return None
        return self.oi / self.revenue * 100


def years(points: Points, fye: str | None = None) -> list[Year]:
    """Fiscal years (oldest first) from FY points; ends within 10 days are one year."""

    def fy(concept: str) -> dict[str, AsOfPoint]:
        return {e: p for e, p in points(concept, "FY").items() if is_fy_end(e, fye)}

    rev, oi, ni = fy("revenue"), fy("operating_income"), fy("net_income")
    gp, cost, wd, eps = (
        fy("gross_profit"),
        fy("cost_of_revenue"),
        fy("inventory_writedown"),
        fy("eps_diluted"),
    )
    ends: list[str] = []
    for e in sorted(set(rev) | set(oi) | set(ni)):
        if not any(near(e, x) for x in ends):
            ends.append(e)
    out = []
    for e in ends:

        def get(d: dict[str, AsOfPoint], end: str = e) -> AsOfPoint | None:
            return d.get(end) or next((p for x, p in d.items() if near(x, end)), None)

        r, o, n, g, c, w, s = (get(d) for d in (rev, oi, ni, gp, cost, wd, eps))
        gross = float(g.value) if g is not None else None
        if gross is None and r is not None and c is not None:
            gross = float(r.value) - float(c.value)
        srcs = tuple(
            Source(p.accession, p.filed, "A", what)
            for p, what in ((r, "revenue"), (o, "operating income"), (n, "net income"))
            if p is not None
        )
        out.append(
            Year(
                e,
                *(float(p.value) if p is not None else None for p in (r, o, n)),
                gross,
                float(w.value) if w is not None else 0.0,
                float(s.value) if s is not None else None,
                srcs,
            )
        )
    return out


@dataclass
class Window:
    years: list[Year]  # the window's years with revenue and operating income
    kind: str  # trough_to_trough | longest_history | missing
    series: str  # which margin series found the turning points
    troughs: list[str] = field(default_factory=list)  # confirmed trough labels
    dropped: list[str] = field(default_factory=list)  # window years without revenue / OI
    missing: str = ""

    @property
    def span(self) -> str:
        if not self.years:
            return "none"
        return f"{self.years[0].label}–{self.years[-1].label}"

    def text(self) -> str:
        if self.kind == "missing":
            return f"NEP window missing: {self.missing}"
        tr = ", ".join(self.troughs) or "none"
        how = (
            f"trough to trough on {self.series} 5 pp turning points (confirmed troughs {tr}; "
            "later trough year excluded; D-M04-83, -106)"
            if self.kind == "trough_to_trough"
            else f"no completed cycle on {self.series} (confirmed troughs {tr}): longest "
            "history, labelled (D-M04-83)"
        )
        drop = (
            f"; left out (no revenue or operating income): {', '.join(self.dropped)}"
            if (self.dropped)
            else ""
        )
        return f"NEP window {self.span} ({len(self.years)} years): {how}{drop}"


def margin_series(ys: list[Year]) -> tuple[str, list[tuple[Year, float]]]:
    gm = [
        (y, (y.gross + y.writedown) / y.revenue * 100)
        for y in ys
        if y.gross is not None and y.revenue
    ]
    if len(gm) >= MIN_GM_YEARS:
        return "gross margin (write-down added back; the CvD trough series)", gm
    om = [(y, m) for y in ys if (m := y.op_margin) is not None]
    return "operating margin (fewer than 3 gross-margin years)", om


def window(ys: list[Year], *, swing: float = SWING_PP, min_years: int = MIN_YEARS) -> Window:
    name, series = margin_series(ys)
    troughs, _peaks, _cur = turning_points([m for _, m in series], swing)
    labels = [series[i][0].label for i in troughs]
    if len(troughs) >= 2:
        a, b = series[troughs[-2]][0].end, series[troughs[-1]][0].end
        span = [y for y in ys if a <= y.end < b and not near(y.end, b)]
        kind = "trough_to_trough"
    else:
        span, kind = list(ys), "longest_history"
    use = [y for y in span if y.revenue is not None and y.oi is not None and y.revenue > 0]
    w = Window(use, kind, name, labels, [y.label for y in span if y not in use])
    if len(use) < min_years:
        w.kind = "missing"
        w.missing = (
            f"{len(use)} fiscal year(s) with revenue and operating income in the "
            f"{'cycle' if kind == 'trough_to_trough' else 'stored history'} (needs {min_years})"
        )
    return w


@dataclass
class NEP:
    window: Window
    margin: float | None = None  # ratio of sums, fraction
    rev_avg: float | None = None
    nebit_cycle: float | None = None  # cycle-average revenue × margin
    nebit_current: float | None = None  # margin × TTM revenue
    ttm_revenue: float | None = None
    ttm_label: str = ""
    ni_avg: float | None = None
    shares: float | None = None
    shares_label: str = ""
    neps: float | None = None
    neps_missing: str = ""
    sources: list[Source] = field(default_factory=list)

    @property
    def missing(self) -> str:
        return self.window.missing if self.window.kind == "missing" else ""

    def text(self) -> str:
        w = self.window.text()
        if self.missing:
            return w
        m = lambda v: f"{v / 1e6:,.0f}M"  # noqa: E731
        n = len(self.window.years)
        oi = sum(y.oi or 0.0 for y in self.window.years)
        rev = sum(y.revenue or 0.0 for y in self.window.years)
        parts = [
            w,
            f"cycle-average operating margin {self.margin * 100:.1f}% ({m(oi)} ÷ {m(rev)})",
            f"normalized EBIT {m(self.nebit_cycle)} on cycle-average revenue {m(self.rev_avg)}",
        ]
        if self.nebit_current is not None:
            parts.append(
                f"{m(self.nebit_current)} on {self.ttm_label or 'TTM'} revenue "
                f"{m(self.ttm_revenue)} (current-revenue base)"
            )
        else:
            parts.append("current-revenue base missing: no 12-month revenue")
        if self.neps is not None:
            parts.append(
                f"normalized EPS {self.neps:.2f} = average net income "
                f"{m(self.ni_avg)} over {n} years ÷ {self.shares / 1e6:,.1f}M "
                f"diluted shares ({self.shares_label})"
            )
        else:
            parts.append(f"normalized EPS missing: {self.neps_missing}")
        return "; ".join(parts) + "; reported basis (ex-items with M04 8b, D-M04-66)"


def normalize(
    w: Window,
    *,
    ttm_revenue: float | None = None,
    ttm_label: str = "",
    shares: float | None = None,
    shares_label: str = "",
) -> NEP:
    """Normalized EBIT on both bases and normalized EPS over the window."""
    out = NEP(
        w, ttm_revenue=ttm_revenue, ttm_label=ttm_label, shares=shares, shares_label=shares_label
    )
    if w.kind == "missing":
        return out
    ys = w.years
    rev = sum(y.revenue for y in ys if y.revenue is not None)
    oi = sum(y.oi for y in ys if y.oi is not None)
    out.margin = oi / rev
    out.rev_avg = rev / len(ys)
    out.nebit_cycle = out.rev_avg * out.margin
    if ttm_revenue is not None:
        out.nebit_current = out.margin * ttm_revenue
    out.sources = [s for y in ys for s in y.sources]
    nis = [y.ni for y in ys if y.ni is not None]
    if len(nis) < len(ys):
        out.neps_missing = "net income missing for " + ", ".join(
            y.label for y in ys if y.ni is None
        )
    elif not shares or shares <= 0:
        out.neps_missing = "no diluted weighted-average share count"
    else:
        out.ni_avg = sum(nis) / len(nis)
        out.neps = out.ni_avg / shares
    return out
