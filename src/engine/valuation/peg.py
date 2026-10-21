"""Forward P/E and R6 PEG (M08 Part 2; D-M08-4, -5, rule 6).

- `val_pe_fwd` (D32 standard row): close ÷ FY1 consensus EPS, "vendor basis (non-GAAP)";
  FY1 EPS ≤ 0 → `not_meaningful`; MSTR keeps its value with `fair_value_earnings`
  (D-M08-7).
- `peg` = forward P/E ÷ (100 × g), g = FY2 ÷ FY1 consensus − 1, all on the vendor basis.
  Scored only when 0 < g ≤ 50%† (D-M08-5); first failing check wins, every failing check
  is named: `fair_value_earnings`, `eps_nonpositive` (TTM GAAP EPS ≤ 0, R6 "EPS > 0"),
  `cyclical` (M08's flag, R6), `growth_missing` (no FY1 or FY2 consensus), `base_nonpositive`
  (FY1 consensus ≤ 0: no growth base), `growth_nonpositive`, `growth_above_cap` (the uncapped
  PEG in `method`, not scored). Bands ≤1 / 1–2 / >2 (outline PEG item 2).
- The trailing 3-year GAAP EPS CAGR (net income ÷ split-scaled diluted shares) is shown
  beside it, never substituted (D-M08-4); R6's sales fallback is the EV/Sales row and its
  percentile, named in `method` whenever the PEG is not scored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from engine.signals import Source
from engine.valuation.estimates import Horizon
from engine.valuation.measures import FAIR_VALUE, NM, Measure

ORDER = (
    "fair_value_earnings",
    "eps_nonpositive",
    "cyclical",
    "growth_missing",
    "base_nonpositive",
    "growth_nonpositive",
    "growth_above_cap",
)


def forward_pe(
    close: float | None, fy1: Horizon | None, *, treasury: bool, sources: list[Source]
) -> Measure:
    m = Measure("val_pe_fwd", sources=list(sources))
    if close is None:
        m.missing = "no close"
        return m
    if fy1 is None or fy1.avg is None:
        m.missing = "no FY1 consensus EPS in the snapshot"
        return m
    eps = fy1.avg
    m.detail = (
        f"close ${close:,.2f} ÷ FY1 {fy1.row.period_end} consensus EPS {eps:.4f} "
        "(vendor basis, non-GAAP)"
    )
    if eps <= 0:
        m.text = NM
        m.detail += "; FY1 EPS ≤ 0"
    else:
        m.value = close / eps
    if treasury:
        m.text = FAIR_VALUE
        m.detail += "; EPS moves with bitcoin under ASU 2023-08 (D-M08-7)"
    return m


def band(x: float) -> str:
    return "≤1" if x <= 1 else ("1–2" if x <= 2 else ">2")


@dataclass
class Peg:
    value: float | None = None
    text: str | None = None
    missing: str = ""
    scored: bool = False
    g: float | None = None  # percent
    uncapped: float | None = None
    codes: list[str] = field(default_factory=list)
    detail: list[str] = field(default_factory=list)

    @property
    def shown(self) -> str:
        if self.missing:
            return "missing"
        if self.value is not None:
            return f"{self.value:.2f} ({self.text})"
        return self.text or "—"


def peg(
    *,
    fwd: Measure,
    fy1: Horizon | None,
    fy2: Horizon | None,
    ttm_pe: Measure,
    cyclical: bool,
    treasury: bool,
    cap_pct: float,
    have_snapshot: bool,
) -> Peg:
    """R6 PEG; `ttm_pe` gives the trailing GAAP EPS sign (value > 0, or not_meaningful)."""
    out = Peg()
    fails: list[str] = []
    if treasury:
        fails.append("fair_value_earnings")
    if ttm_pe.text == NM:
        fails.append("eps_nonpositive")
    elif ttm_pe.missing:
        out.detail.append(f"TTM GAAP EPS sign unknown ({ttm_pe.missing}): check skipped")
    if cyclical:
        fails.append("cyclical")
    a1 = fy1.avg if fy1 is not None else None
    a2 = fy2.avg if fy2 is not None else None
    if a1 is None or a2 is None:
        fails.append("growth_missing")
    elif a1 <= 0:
        fails.append("base_nonpositive")
    else:
        g = (a2 / a1 - 1) * 100
        out.g = g
        out.detail.append(
            f"g = FY2 {fy2.row.period_end} {a2:.4f} ÷ FY1 {fy1.row.period_end} {a1:.4f} − 1 = "
            f"{g:.1f}% (vendor basis)"
        )
        if g <= 0:
            fails.append("growth_nonpositive")
        else:
            if fwd.value is not None:
                out.uncapped = fwd.value / g
            if g > cap_pct:
                fails.append("growth_above_cap")
    if out.uncapped is not None:
        out.detail.append(
            f"PEG = forward P/E {fwd.value:.1f}× ÷ {out.g:.1f} = {out.uncapped:.2f}"
            + (" (uncapped, not scored)" if "growth_above_cap" in fails else "")
        )
    out.codes = [c for c in ORDER if c in fails]
    if out.codes:
        if out.codes[0] == "growth_missing" and not have_snapshot:
            out.missing = "no estimate snapshot (budget / no coverage)"
        else:
            out.text = out.codes[0]
        if len(out.codes) > 1:
            out.detail.append("failing checks: " + ", ".join(out.codes))
        return out
    out.value, out.text, out.scored = out.uncapped, band(out.uncapped), True
    return out


def trailing_cagr(k, pts, close_day: str) -> str:
    """Trailing 3-year GAAP EPS CAGR (net income ÷ split-scaled diluted shares), as text."""
    ni, sh = pts("net_income", "FY"), pts("shares_diluted_wavg", "FY")
    ends = sorted(e for e in ni if e in sh)
    if not ends:
        return "trailing 3-year GAAP EPS CAGR missing: no fiscal-year EPS inputs"
    e1 = ends[-1]
    target = date.fromisoformat(e1).toordinal() - 1096  # three years back (52/53-week years too)
    e0 = next((e for e in ends if abs(date.fromisoformat(e).toordinal() - target) <= 20), None)
    if e0 is None:
        return f"trailing 3-year GAAP EPS CAGR missing: no fiscal year 3 years before {e1}"

    def eps(e: str) -> float:
        # a share count is on the basis of the filing that stated it (later 10-Ks restate
        # older years after a split): scale from `filed`, not the period end (live check 1:
        # NVDA FY2023 EPS read 0.02, the 2024 ×10 split applied twice)
        f, _ = k.factor(sh[e].filed, close_day)
        return float(ni[e].value) / (float(sh[e].value) * f)

    a, b = eps(e0), eps(e1)
    if a <= 0 or b <= 0:
        return (
            f"trailing 3-year GAAP EPS CAGR n/m (EPS {a:.2f} at {e0}, {b:.2f} at {e1}: ≤ 0); "
            "never substituted (D-M08-4)"
        )
    c = ((b / a) ** (1 / 3) - 1) * 100
    return (
        f"trailing 3-year GAAP EPS CAGR {c:.1f}% (EPS {a:.2f} at {e0} → {b:.2f} at {e1}); "
        "beside, never substituted (D-M08-4)"
    )
