"""Own-history and peer percentiles (D-M08-2).

- **Own history:** calendar quarter-ends before today's close, each computed by
  `measures.snapshot` on first-filed values with a close within 5 days (recomputed each run;
  no table). A row's percentile = mid-rank of today's value among its history values
  (share of points below, plus half the ties), scored only with ≥ 20† points; quarters where
  the row was `not_meaningful` are left out and counted. Never a sell signal (D16).
- **Peers:** the headline measure at today's close for confirmed peers (with a CIK) that
  have stored prices; ≥ 5† values → a percentile shown in `method`, not scored; fewer →
  "missing: n priced peers". Peer facts are what is stored (peers keep mapped tags only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


def quarter_ends(first: str, before: str) -> list[str]:
    """Calendar quarter-ends from the one on or after `first` to the last before `before`."""
    d = date.fromisoformat(first)
    y, q = d.year, (d.month - 1) // 3 + 1
    out = []
    while True:
        m = q * 3
        end = date(y, m, 31 if m in (3, 12) else 30).isoformat()
        if end >= before:
            return out
        if end >= first:
            out.append(end)
        q += 1
        if q == 5:
            y, q = y + 1, 1


def midrank(x: float, values: list[float]) -> float:
    below = sum(1 for v in values if v < x)
    ties = sum(1 for v in values if v == x)
    return 100.0 * (below + 0.5 * ties) / len(values)


@dataclass
class Pctile:
    value: float | None
    n: int
    nm: int = 0  # not_meaningful quarters left out
    first: str = ""
    last: str = ""
    missing: str = ""

    def text(self) -> str:
        nm = f", {self.nm} n/m quarter(s) left out" if self.nm else ""
        if self.value is None:
            return f"own pctile missing: {self.missing}{nm}"
        return (
            f"own pctile {self.value:.0f} of {self.n} quarters ({self.first}…{self.last}, "
            f"first-filed values){nm}"
        )


@dataclass
class History:
    """Per row: [(quarter-end, value)] and the not_meaningful count."""

    points: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    nm: dict[str, int] = field(default_factory=dict)
    quarters: int = 0  # quarter-ends tried

    def add(self, key: str, day: str, value: float | None, text: str | None) -> None:
        if value is not None:
            self.points.setdefault(key, []).append((day, value))
        elif text == "not_meaningful":
            self.nm[key] = self.nm.get(key, 0) + 1

    def pctile(self, key: str, current: float | None, min_points: int) -> Pctile:
        pts = self.points.get(key, [])
        nm = self.nm.get(key, 0)
        first, last = (pts[0][0], pts[-1][0]) if pts else ("", "")
        if current is None:
            return Pctile(None, len(pts), nm, first, last, "no current value")
        if len(pts) < min_points:
            return Pctile(None, len(pts), nm, first, last, f"{len(pts)}/{min_points} quarters")
        return Pctile(midrank(current, [v for _, v in pts]), len(pts), nm, first, last)

    def series(self, key: str) -> list[tuple[str, float]]:
        return self.points.get(key, [])


@dataclass
class Peer:
    value: float | None
    n: int
    names: list[str]
    missing: str = ""

    def text(self) -> str:
        if self.value is None:
            return f"peer pctile missing: {self.missing} (shown, not scored; D-M08-2)"
        return (
            f"peer pctile {self.value:.0f} among {self.n} priced confirmed peers "
            f"({', '.join(self.names[:8])}; shown, not scored; D-M08-2)"
        )


def peer(
    current: float | None, values: list[tuple[str, float]], min_peers: int, confirmed: int
) -> Peer:
    names = [n for n, _ in values]
    if confirmed == 0:
        return Peer(None, 0, [], "no confirmed SEC peers")
    if current is None:
        return Peer(None, len(values), names, "no current value")
    if len(values) < min_peers:
        return Peer(
            None, len(values), names, f"{len(values)} priced peers with a value (needs {min_peers})"
        )
    return Peer(midrank(current, [v for _, v in values]), len(values), names)
