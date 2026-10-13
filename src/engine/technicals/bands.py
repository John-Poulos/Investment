"""The M01 σ band on weekly closes (D27, D-M09-2): one function for the stored row and the
chart overlay (Part 2 computes the history with `band_history`; its newest value equals the
stored row).

- `band_z` (the trigger): z of ln(close) against the mean of ln(close) over the window
  (20 completed weeks, the current week included), σ of ln(close) over the same weeks.
- `price_band` (display only, owner amendment to D-M09-2): mean of the close over the
  same weeks ± 1σ / ± 2σ of the close; `z_price` = M01's z "as written".
- `pullback_sigma`: ln(close ÷ 20-week high) ÷ σ_w, σ_w = σ of the last 20 weekly log
  returns (21 closes); the 20-week high is the highest weekly close in the window.
- σ is the population standard deviation (divide by n), Bollinger's convention
  (D-M09-9). A window with σ = 0 (flat prices) gives no z.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


def mean_sd(xs: Sequence[float]) -> tuple[float, float]:
    n = len(xs)
    if n == 0:
        raise ValueError("empty window")
    m = sum(xs) / n
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / n)


def log_returns(closes: Sequence[float]) -> list[float]:
    return [math.log(b / a) for a, b in zip(closes, closes[1:], strict=False)]


@dataclass(frozen=True)
class Band:
    window: int
    close: float
    z: float | None  # band_z (log price)
    mean_log: float
    sd_log: float
    price_mean: float
    price_sd: float
    z_price: float | None
    high: float  # highest weekly close in the window
    pullback_sigma: float | None
    sigma_w: float | None  # σ of weekly log returns (pullback_sigma's scale)

    @property
    def geo_mean(self) -> float:
        """exp(mean ln close): where band_z is 0, in price."""
        return math.exp(self.mean_log)

    def levels(self) -> dict[str, float]:
        """Price-level band: −2σ, −1σ, mean, +1σ, +2σ of the close."""
        m, s = self.price_mean, self.price_sd
        return {"-2": m - 2 * s, "-1": m - s, "mean": m, "+1": m + s, "+2": m + 2 * s}

    @property
    def from_high(self) -> float:
        return self.close / self.high - 1


def band_at(
    closes: Sequence[float], i: int | None = None, *, window: int = 20, returns: int = 20
) -> Band | None:
    """The band at index `i` (default: the last close); None below `window` closes."""
    i = len(closes) - 1 if i is None else i
    if i < window - 1 or i >= len(closes):
        return None
    win = closes[i - window + 1 : i + 1]
    if any(c <= 0 for c in win):
        return None
    logs = [math.log(c) for c in win]
    ml, sl = mean_sd(logs)
    mp, sp = mean_sd(win)
    c = closes[i]
    z = (math.log(c) - ml) / sl if sl > 0 else None
    zp = (c - mp) / sp if sp > 0 else None
    high = max(win)
    pb = sw = None
    if i >= returns:
        seg = closes[i - returns : i + 1]
        if all(x > 0 for x in seg):
            _, sw = mean_sd(log_returns(seg))
            pb = math.log(c / high) / sw if sw > 0 else None
            if sw == 0:
                sw = None
    return Band(window, c, z, ml, sl, mp, sp, zp, high, pb, sw)


def band_history(
    closes: Sequence[float], *, window: int = 20, returns: int = 20
) -> list[Band | None]:
    """The band at every close (None before `window` closes): the overlay's series."""
    return [band_at(closes, i, window=window, returns=returns) for i in range(len(closes))]


def zone(z: float, z1: float = 1.0, z2: float = 2.0) -> str:
    """`below_2` (z ≤ −2), `below_1` (−2 < z ≤ −1), `inside`, `above_1`, `above_2` (z ≥ 2)."""
    if z <= -z2:
        return "below_2"
    if z <= -z1:
        return "below_1"
    if z >= z2:
        return "above_2"
    if z >= z1:
        return "above_1"
    return "inside"
