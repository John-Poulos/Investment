"""Few-peer statistics (D-M04-52, S6.2; M04 Part 2).

Robust z = (company − peer median) ÷ scale:

- **10 or more peers:** scale = IQR ÷ 1.35 (quartiles by linear interpolation, Hyndman–Fan
  type 7, as `statistics.quantiles(method="inclusive")`).
- **5–9 peers:** scale = MAD × 1.4826 × b_n, b_n = Croux & Rousseeuw's small-sample factor
  (values read from the revss package, `bnMdADMdCR`; S-new-r6-3, M04_DESIGN_PACK Round 6).
- **Fewer than 5:** fixed-gap fallback, low confidence. The gap to the median decides (Part
  8a); z (MAD × 1.4826 × b_n where b_n exists) is shown as information only, with the spread
  of the four methods the review compared (IQR type 7, IQR type 6, MAD × 1.4826, MAD ×
  1.4826 × b_n) — Intel 2022 at n = 4 spreads −0.82 to −1.92.
- **Outliers:** with 5 or more peers, any peer whose own z against the peer set is beyond
  ±3 is dropped once and everything is recomputed; fewer than 5 left → fallback (NVIDIA
  2023 at z +8.97 → n = 4). Below 5 nothing is dropped (the median is the fallback's anchor).

Method, n, b_n and the dropped peers are returned with every result; the gap is always
shown (S6.2). A spread of 0 gives no z ("not meaningful"). Missing values never enter.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field

MAD_K = 1.4826
IQR_K = 1.35
MIN_Z = 5  # fewer peers → fixed-gap fallback
IQR_FROM = 10
DROP_Z = 3.0
# Croux & Rousseeuw (1992) small-sample MAD factors b_n, n = 2…9 (revss 3.1.0, read
# 2026-10-12; M04_DESIGN_PACK line 2619). Used for 5–9 peers; 2–4 only for the
# information z of the fallback.
B_N = {2: 1.196, 3: 1.495, 4: 1.363, 5: 1.206, 6: 1.200, 7: 1.140, 8: 1.129, 9: 1.107}

FALLBACK = "fewer than 5 → fixed-gap fallback, low confidence"


@dataclass(frozen=True)
class Scale:
    value: float | None
    method: str  # "IQR ÷ 1.35" | "MAD × 1.4826 × b_n" | "MAD × 1.4826"
    factor: float | None  # b_n where used


@dataclass
class RobustZ:
    company: float
    n_in: int  # comparable peers before the drop
    n: int  # peers scored (after the drop)
    median: float | None
    gap: float | None  # company − median, in the values' own unit
    z: float | None
    z_info: bool  # True = information only (fallback)
    method: str
    factor: float | None
    dropped: list[tuple[str, float]] = field(default_factory=list)  # (peer, its z)
    spread: tuple[float, float] | None = None  # fallback: min…max z over the four methods
    note: str = ""  # "not meaningful: peer spread is 0", "no comparable peer"

    @property
    def fallback(self) -> bool:
        return self.n < MIN_Z

    @property
    def confidence(self) -> str:
        return "low" if self.fallback else "normal"

    def text(self, unit_scale: float = 1.0, median_unit: str = " pp") -> str:
        """One line for a signal method or a table cell title. `unit_scale` turns the
        values into percent or pp (fractions × 100); the gap always reads in pp."""
        if self.median is None:
            return f"peers: {self.note or 'no comparable peer'} (n = 0)"
        gap = f"gap {self.gap * unit_scale:+.1f} pp" if self.gap is not None else ""
        med = f"median {self.median * unit_scale:+.1f}{median_unit}"
        parts = [f"peers n = {self.n}", med, gap]
        if self.z is not None:
            parts.append(f"z {self.z:+.2f}" + (" (information only)" if self.z_info else ""))
        elif self.note:
            parts.append(self.note)
        parts.append(self.method_text())
        return "; ".join(p for p in parts if p)

    def method_text(self) -> str:
        drop = ""
        if self.dropped:
            names = ", ".join(f"{n} z {z:+.2f}" for n, z in self.dropped)
            drop = f"; |z| > 3 dropped once ({len(self.dropped)} dropped: {names})"
        elif self.n_in >= MIN_Z:
            drop = "; |z| > 3 dropped once (0 dropped)"
        if self.fallback:
            spread = ""
            if self.spread is not None:
                spread = f"; methods spread {self.spread[0]:+.2f} to {self.spread[1]:+.2f}"
            return f"{FALLBACK}{spread}{drop}"
        b = f" (b_{self.n} = {self.factor:.3f})" if self.factor else ""
        return f"{self.method}{b}{drop}"


def mad(values: Sequence[float]) -> float:
    m = statistics.median(values)
    return statistics.median(abs(v - m) for v in values)


def iqr(values: Sequence[float], method: str = "inclusive") -> float | None:
    """Interquartile range; 'inclusive' = type 7, 'exclusive' = type 6. None below 2."""
    if len(values) < 2:
        return None
    q = statistics.quantiles(values, n=4, method=method)
    return q[2] - q[0]


def scale(values: Sequence[float]) -> Scale:
    """The D-M04-52 scale for this many peers (5–9: MAD × b_n; ≥ 10: IQR ÷ 1.35; below 5
    the information scale MAD × 1.4826 × b_n, or MAD × 1.4826 when no b_n exists)."""
    n = len(values)
    if n >= IQR_FROM:
        r = iqr(values)
        return Scale(r / IQR_K if r is not None else None, "IQR ÷ 1.35", None)
    if n == 0:
        return Scale(None, "no peers", None)
    b = B_N.get(n)
    s = mad(values) * MAD_K
    if b is None:
        return Scale(s, "MAD × 1.4826", None)
    return Scale(s * b, "MAD × 1.4826 × b_n", b)


def _z(x: float, med: float, s: float | None) -> float | None:
    if s is None or s <= 0:
        return None
    return (x - med) / s


def method_spread(company: float, values: Sequence[float]) -> tuple[float, float] | None:
    """z under the four methods the Round 6 review compared (fallback information)."""
    if len(values) < 2:
        return None
    med = statistics.median(values)
    zs = []
    for r in (iqr(values, "inclusive"), iqr(values, "exclusive")):
        if r:
            zs.append((company - med) / (r / IQR_K))
    m = mad(values) * MAD_K
    if m > 0:
        zs.append((company - med) / m)
        if len(values) in B_N:
            zs.append((company - med) / (m * B_N[len(values)]))
    return (min(zs), max(zs)) if zs else None


def robust_z(company: float, peers: Sequence[tuple[str, float]]) -> RobustZ:
    """Company value against named peer values (comparable periods only)."""
    vals = [(n, float(v)) for n, v in peers if v is not None]
    n_in = len(vals)
    if n_in == 0:
        return RobustZ(company, 0, 0, None, None, None, True, FALLBACK, None,
                       note="no comparable peer")  # fmt: skip
    dropped: list[tuple[str, float]] = []
    if n_in >= MIN_Z:
        values = [v for _, v in vals]
        med, sc = statistics.median(values), scale(values)
        for name, v in vals:
            z = _z(v, med, sc.value)
            if z is not None and abs(z) > DROP_Z:
                dropped.append((name, z))
        if dropped:
            gone = {n for n, _ in dropped}
            vals = [(n, v) for n, v in vals if n not in gone]
    values = [v for _, v in vals]
    med = statistics.median(values)
    sc = scale(values)
    z = _z(company, med, sc.value)
    fallback = len(values) < MIN_Z
    out = RobustZ(
        company=company,
        n_in=n_in,
        n=len(values),
        median=med,
        gap=company - med,
        z=z,
        z_info=fallback,
        method=sc.method,
        factor=sc.factor,
        dropped=dropped,
        spread=method_spread(company, values) if fallback else None,
    )
    if z is None:
        out.note = "z not meaningful: peer spread is 0" if len(values) > 1 else "one peer: gap only"
    return out
