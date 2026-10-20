"""The R6 cyclical flag (D-M08-3, rule 5; MVP_PLAN item 5: M08 owns the company-level flag).

Computed over the last 10† fiscal years (fewer labelled; fewer than 5† → not computed):

- a GAAP diluted EPS sign change between consecutive fiscal years (net income's sign when
  EPS is untagged, labelled), or
- an operating-margin range (max − min) ≥ 30 pp†.

The owner's `cyclical = true / false` in `config/valuation.toml` wins and is shown with the
computed tests beside it. D32 / D9: the rule's evidence is one memory company (MU) and the
PEG trap note (S18) — tech-only; a one-loss-year industrial flags and a low-margin cyclical
(retail, distribution) never reaches 30 pp. Both test values are always shown so the owner
can override.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.financials.nep import Year
from engine.valuation.params import Override, Params


@dataclass
class Flag:
    cyclical: bool | None  # None = not computed (too few years) and no override
    computed: bool | None
    n_years: int
    span: str
    eps_test: str
    margin_test: str
    override: Override | None = None

    @property
    def source(self) -> str:
        if self.override is not None and self.override.cyclical is not None:
            return "owner"
        return "computed" if self.computed is not None else "not computed"

    def text(self) -> str:
        if self.computed is None:
            comp = f"not computed: {self.n_years} fiscal years (needs 5)"
        else:
            comp = f"computed {'cyclical' if self.computed else 'not cyclical'}"
        head = {True: "cyclical", False: "not cyclical", None: "not flagged"}[self.cyclical]
        own = ""
        if self.source == "owner":
            own = f" (owner override: {self.override.reason}; {comp})"
        else:
            own = f" ({comp})"
        return (
            f"cyclical flag: {head}{own}; {self.span}: {self.eps_test}; "
            f"{self.margin_test} (rule 5, D-M08-3)"
        )


def flag(ys: list[Year], p: Params, override: Override | None = None) -> Flag:
    last = ys[-p.cyclical_years :]
    n = len(last)
    span = (
        f"{last[0].label}–{last[-1].label} ({n} of {p.cyclical_years} fiscal years)"
        if last
        else "no fiscal years"
    )
    # EPS sign change (net income's sign when EPS is untagged)
    signs, basis = [], "diluted EPS"
    for y in last:
        v = y.eps if y.eps is not None else y.ni
        if y.eps is None and y.ni is not None:
            basis = "diluted EPS (net income where EPS untagged)"
        if v is not None and v != 0:
            signs.append((y.label, v))
    flips = [
        f"{a[0]} {a[1]:+.2f} → {b[0]} {b[1]:+.2f}"
        for a, b in zip(signs, signs[1:], strict=False)
        if (a[1] > 0) != (b[1] > 0)
    ]
    eps_hit = bool(flips)
    eps_test = f"{basis} sign change {'yes: ' + '; '.join(flips[:3]) if flips else 'no'}"
    margins = [(y.label, m) for y in last if (m := y.op_margin) is not None]
    if margins:
        lo, hi = min(margins, key=lambda x: x[1]), max(margins, key=lambda x: x[1])
        rng = hi[1] - lo[1]
        m_hit = rng >= p.margin_range_pp
        margin_test = (
            f"operating-margin range {rng:.1f} pp ({lo[0]} {lo[1]:.1f}% to {hi[0]} "
            f"{hi[1]:.1f}%; line {p.margin_range_pp:g} pp†) → "
            f"{'yes' if m_hit else 'no'}"
        )
    else:
        m_hit, margin_test = False, "operating margin: no year with revenue and operating income"
    computed = None if n < p.cyclical_min_years else (eps_hit or m_hit)
    final = computed
    if override is not None and override.cyclical is not None:
        final = override.cyclical
    return Flag(final, computed, n, span, eps_test, margin_test, override)
