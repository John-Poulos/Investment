"""Related-industry groups for the phrase spread test (D-M02-49).

Fama–French 12 industries from 4-digit SIC codes (Ken French's Siccodes12 definitions):
chips, computers, networking, instruments and software fall in one "business
equipment" group, so a technology phrase used across them reads as concentrated, not
generic. FF12's catch-all "Other" (mining, construction, transport, services …) is split
by 2-digit SIC major group, the fallback D-M02-49 names; otherwise unrelated industries
would look like one group. A filer without a SIC is "industry unknown" and blank-check
companies (SIC 6770) are not operating companies. Finance filers (funds, REITs, banks,
crypto companies) mention themes as holdings or risks, so they are counted apart
(D-M02-52); the spread is shown, not enforced, until the calibration round sets a rule.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

BLANK_CHECK = "6770"
UNKNOWN = "industry unknown"

# (group number, short name, label, ranges inclusive); order as in Siccodes12.
FF12: tuple[tuple[int, str, str, tuple[tuple[int, int], ...]], ...] = (
    (1, "NoDur", "consumer non-durables", (
        (100, 999), (2000, 2399), (2700, 2749), (2770, 2799), (3100, 3199), (3940, 3989))),
    (2, "Durbl", "consumer durables", (
        (2500, 2519), (2590, 2599), (3630, 3659), (3710, 3711), (3714, 3714), (3716, 3716),
        (3750, 3751), (3792, 3792), (3900, 3939), (3990, 3999))),
    (3, "Manuf", "manufacturing", (
        (2520, 2589), (2600, 2699), (2750, 2769), (3000, 3099), (3200, 3569), (3580, 3629),
        (3700, 3709), (3712, 3713), (3715, 3715), (3717, 3749), (3752, 3791), (3793, 3799),
        (3830, 3839), (3860, 3899))),
    (4, "Enrgy", "oil, gas and coal", ((1200, 1399), (2900, 2999))),
    (5, "Chems", "chemicals", ((2800, 2829), (2840, 2899))),
    (6, "BusEq", "business equipment (chips, computers, software)", (
        (3570, 3579), (3660, 3692), (3694, 3699), (3810, 3829), (7370, 7379))),
    (7, "Telcm", "telecom", ((4800, 4899),)),
    (8, "Utils", "utilities", ((4900, 4949),)),
    (9, "Shops", "wholesale, retail, some services", (
        (5000, 5999), (7200, 7299), (7600, 7699))),
    (10, "Hlth", "healthcare and drugs", ((2830, 2839), (3693, 3693), (3840, 3859), (8000, 8099))),
    (11, "Money", "finance", ((6000, 6999),)),
)  # fmt: skip

# 2-digit SIC major groups for FF12 "Other" (SEC/OSHA division names, shortened)
MAJOR: dict[int, str] = {
    10: "metal mining", 14: "non-metal mining", 15: "construction", 16: "heavy construction",
    17: "construction trades", 40: "railroads", 41: "transit", 42: "trucking",
    44: "water transport", 45: "air transport", 46: "pipelines", 47: "transport services",
    70: "hotels", 73: "business services", 75: "auto services", 78: "motion pictures",
    79: "amusement", 80: "health services", 81: "legal services", 82: "education",
    83: "social services", 87: "engineering and management services", 89: "other services",
    99: "non-classifiable",
}  # fmt: skip


def ff12(sic: str | int | None) -> int | None:
    """FF12 group 1–11, 12 for Other, None when the SIC is missing or unreadable."""
    try:
        code = int(str(sic).strip())
    except TypeError, ValueError:
        return None
    for num, _, _, ranges in FF12:
        if any(lo <= code <= hi for lo, hi in ranges):
            return num
    return 12


def group_of(sic: str | int | None) -> str:
    """Spread-test group label: an FF12 label, or 'other: <2-digit major>' for Other."""
    num = ff12(sic)
    if num is None:
        return UNKNOWN
    if num == 12:
        major = int(str(sic).strip()) // 100
        return f"other: {MAJOR.get(major, f'SIC {major:02d}xx')}"
    return next(label for n, _, label, _ in FF12 if n == num)


@dataclass(frozen=True)
class Spread:
    operating: int  # companies counted toward the ≥ 5 floor (blank checks excluded)
    blank_check: int
    unknown: int  # no SIC: counted toward the floor, not toward spread
    finance: int  # FF12 finance (funds, REITs, banks, crypto): shown apart (D-M02-52)
    groups: tuple[tuple[str, int], ...]  # other known industries, largest first
    top1_share: float | None  # of companies in `groups`
    top2_share: float | None
    top3_share: float | None

    @property
    def generic_d49(self) -> bool | None:
        """D-M02-49's working cut-offs (largest group < 50% and top two < 75%). Shown only:
        the spread rule is re-proposed after the calibration round (D-M02-52)."""
        if self.top1_share is None or self.top2_share is None:
            return None
        return self.top1_share < GENERIC_TOP1 and self.top2_share < GENERIC_TOP2

    def to_json(self) -> dict:
        return {
            "operating": self.operating, "blank_check": self.blank_check,
            "unknown": self.unknown, "finance": self.finance,
            "groups": [list(g) for g in self.groups], "top1": self.top1_share,
            "top2": self.top2_share, "top3": self.top3_share, "generic_d49": self.generic_d49,
        }  # fmt: skip


GENERIC_TOP1 = 0.50  # working cut-offs (D-M02-49); not enforced until re-proposed (D-M02-52)
GENERIC_TOP2 = 0.75
FINANCE = next(label for n, _, label, _ in FF12 if n == 11)


def spread(companies: Iterable[tuple[str, str | None]]) -> Spread:
    """(cik, first SIC or None) per distinct company → spread components."""
    seen: dict[str, str | None] = {}
    for cik, sic in companies:
        if cik not in seen or (seen[cik] is None and sic):
            seen[cik] = sic
    blank = sum(1 for s in seen.values() if s and str(s).strip() == BLANK_CHECK)
    counts: Counter[str] = Counter()
    unknown = finance = 0
    for s in seen.values():
        if s and str(s).strip() == BLANK_CHECK:
            continue
        g = group_of(s)
        if g == UNKNOWN:
            unknown += 1
        elif g == FINANCE:
            finance += 1
        else:
            counts[g] += 1
    known = sum(counts.values())
    ranked = tuple(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def top(n: int) -> float | None:
        return sum(c for _, c in ranked[:n]) / known if known else None

    return Spread(len(seen) - blank, blank, unknown, finance, ranked, top(1), top(2), top(3))
