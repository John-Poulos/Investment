"""Cohen-Malloy-Pomorski insider classes (S09; M07 rule 2; D-M07-1, -2).

Per (owner CIK, issuer CIK) and calendar year Y, from the owner's open-market P/S rows
(rows module: kinds `buy` and `sale`, 4/A-replaced rows left out) in Y−3, Y−2 and Y−1:

- a P/S row in the same calendar month of each of the three years → `routine`;
- P/S rows in all three years without a common month → `opportunistic`;
- any of the three years without a P/S row → `unclassified`, never defaulted.

Stored history (D-M07-9 (2)): a year that starts before the issuer's Form 4 coverage is only
partly seen. A common month found in the seen part is still a common month, so `routine`
holds; otherwise the class is `unclassified` with "history starts <date>" (a month in the
unseen part could make the owner routine, and a gap there is unknown). Rows with no owner
CIK are `unclassified`. One owner CIK per person: rows carry the first joint owner
(D-SEC-10).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from engine.ownership.rows import Issuer
from engine.sec.client import iso

CLASSES = ("routine", "opportunistic", "unclassified")


@dataclass(frozen=True)
class Verdict:
    owner_cik: str
    year: int
    cls: str
    years: tuple[int, int, int]
    months: dict[int, list[int]]
    reason: str


def classify(
    owner_cik: str, months: dict[int, set[int]], year: int, history_start: str | None
) -> Verdict:
    years = (year - 3, year - 2, year - 1)
    seen = {y: sorted(months.get(y, set())) for y in years}
    common = set.intersection(*(set(seen[y]) for y in years))
    if common:
        why = f"P/S in month {min(common):02d} of {years[0]}, {years[1]} and {years[2]}"
        return Verdict(owner_cik, year, "routine", years, seen, why)
    partial = history_start is None or history_start > f"{years[0]}-01-01"
    if partial:
        start = history_start or "none stored"
        return Verdict(owner_cik, year, "unclassified", years, seen,
                       f"history starts {start} (needs {years[0]}-01-01)")  # fmt: skip
    empty = [y for y in years if not seen[y]]
    if empty:
        return Verdict(owner_cik, year, "unclassified", years, seen,
                       "no P/S in " + ", ".join(str(y) for y in empty))  # fmt: skip
    return Verdict(owner_cik, year, "opportunistic", years, seen,
                   "P/S in each of the 3 years, no common month")  # fmt: skip


def trade_months(issuer: Issuer) -> dict[str, dict[int, set[int]]]:
    """owner CIK → {year: months with an open-market P/S row}."""
    out: dict[str, dict[int, set[int]]] = {}
    for r in issuer.effective():
        if r.kind not in ("buy", "sale") or not r.owner_cik or not r.txn_date:
            continue
        y, m = int(r.txn_date[:4]), int(r.txn_date[5:7])
        out.setdefault(r.owner_cik, {}).setdefault(y, set()).add(m)
    return out


def compute(
    issuer: Issuer, history_start: str | None, current_year: int
) -> dict[tuple[str, int], Verdict]:
    """A verdict for every owner with P/S rows, for each year they traded and this year."""
    out = {}
    for owner, months in trade_months(issuer).items():
        for y in sorted(set(months) | {current_year}):
            out[(owner, y)] = classify(owner, months, y, history_start)
    return out


def store(
    engine: sqlite3.Connection, cik: str, verdicts: dict[tuple[str, int], Verdict], now: datetime
) -> int:
    """Replace the issuer's classes. Caller owns the transaction."""
    engine.execute("DELETE FROM insider_class WHERE issuer_cik = ?", (cik,))
    engine.executemany(
        "INSERT INTO insider_class (owner_cik, issuer_cik, year, class, years_used, months_seen, "
        "reason, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                v.owner_cik,
                cik,
                v.year,
                v.cls,
                json.dumps(list(v.years)),
                json.dumps({str(y): m for y, m in v.months.items()}),
                v.reason,
                iso(now),
            )
            for v in verdicts.values()
        ],  # fmt: skip
    )
    return len(verdicts)


def class_of(
    verdicts: dict[tuple[str, int], Verdict], owner_cik: str | None, txn_date: str | None
) -> Verdict | None:
    if not owner_cik or not txn_date:
        return None
    return verdicts.get((owner_cik, int(txn_date[:4])))
