"""Guidance changes between releases, computed by code (R19, D-SRCH-17 use case 1).

For one company, ledger rows with the same metric, basis and period are compared
release to release (by filing date). A row's own stated prior ("narrowed from
our prior outlook of $125-145 billion") is also a change, even when the earlier
release is not stored. Flagged rows (`not_meaningful`, D-SRCH-15) are skipped.

Kinds, on (low, high):
- reaffirmed: same range
- raised / lowered: both ends moved up / down (or one moved, the other held)
- narrowed / widened: low up and high down / low down and high up
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Change:
    cik: str
    metric: str
    basis: str
    period: str
    unit: str
    kind: str  # raised | lowered | narrowed | widened | reaffirmed
    source: str  # releases | stated_prior
    prev_low: Decimal
    prev_high: Decimal
    new_low: Decimal
    new_high: Decimal
    guidance_id: int  # the newer row
    prev_guidance_id: int | None  # None when the prior was stated in the same sentence
    accession: str  # release announcing the newer value
    filename: str
    stated_on: str


def classify(prev: tuple[Decimal, Decimal], new: tuple[Decimal, Decimal]) -> str:
    (pl, ph), (nl, nh) = prev, new
    dl = (nl > pl) - (nl < pl)
    dh = (nh > ph) - (nh < ph)
    if dl == 0 and dh == 0:
        return "reaffirmed"
    if dl >= 0 and dh >= 0:
        return "raised"
    if dl <= 0 and dh <= 0:
        return "lowered"
    return "narrowed" if dl > 0 else "widened"


def _d(x: object) -> Decimal:
    return Decimal(str(x))


def changes_for(engine: sqlite3.Connection, cik: str) -> list[Change]:
    rows = engine.execute(
        "SELECT guidance_id, metric, basis, period, unit, low, high, prior_low, prior_high, "
        "accession, filename, stated_on FROM guidance "
        "WHERE cik = ? AND flag IS NULL ORDER BY metric, basis, period, stated_on, guidance_id",
        (cik,),
    ).fetchall()
    out: list[Change] = []
    prev = None
    for r in rows:
        key = (r["metric"], r["basis"], r["period"])
        new = (_d(r["low"]), _d(r["high"]))
        common = dict(
            cik=cik,
            metric=r["metric"],
            basis=r["basis"],
            period=r["period"],
            unit=r["unit"],
            new_low=new[0],
            new_high=new[1],
            guidance_id=r["guidance_id"],
            accession=r["accession"],
            filename=r["filename"],
            stated_on=r["stated_on"],
        )
        if prev is not None and prev[0] == key and prev[1]["accession"] != r["accession"]:
            p = prev[1]
            old = (_d(p["low"]), _d(p["high"]))
            out.append(
                Change(
                    kind=classify(old, new),
                    source="releases",
                    prev_low=old[0],
                    prev_high=old[1],
                    prev_guidance_id=p["guidance_id"],
                    **common,
                )
            )
        elif r["prior_low"] is not None:
            old = (_d(r["prior_low"]), _d(r["prior_high"]))
            out.append(
                Change(
                    kind=classify(old, new),
                    source="stated_prior",
                    prev_low=old[0],
                    prev_high=old[1],
                    prev_guidance_id=None,
                    **common,
                )
            )
        prev = (key, r)
    return sorted(out, key=lambda c: (c.stated_on, c.metric, c.basis, c.period))
