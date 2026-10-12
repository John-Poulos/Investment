"""Point-in-time facts: what was known on a date (S1.1, M04 Part 1a).

`facts_as_of(engine, cik, concept, as_of)` reads the `fact` table, not `series`:

1. Periodic forms only: 10-K, 10-Q, 10-KT, 10-QT, 20-F, 40-F and their amendments, plus
   6-K (and 6-K/A) for a filer whose annual report is a 20-F or 40-F. Values that also
   arrive in 8-Ks, proxy statements (DEF 14A), S-1 or S-4 are never "latest" (Alphabet's
   2023 net income re-appeared in a DEF 14A filed 2026-04-24).
2. Time first, then tag priority: only facts filed on or before `as_of` are seen, and the
   concept's tag order is applied to what is left. The first version is the earliest filed
   under any tag (Micron FY2018 revenue: first filed 2018-10-15 under `Revenues`, not
   2019-10-17 under the ASC 606 tag).
3. Entity boundaries (`entity_link`): a predecessor CIK's facts filed up to the boundary
   are read for the successor and labelled; for a de-SPAC shell under the same CIK, facts
   from documents whose period ends before the closing are the shell's and are left out
   (keyed on period end, D-M04-8).
4. Quarters are derived from year-to-date facts and TTM from four contiguous quarters, as
   in `series` (`xbrl_facts.points_from_rows`).

Every point carries its tag, accession and filed date (S1.4). Missing stays missing.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from engine.sec.identity import entity_links, normalize_cik
from engine.sec.xbrl_facts import ALL_CONCEPTS, Concept, concept_for, concept_rows, points_from_rows

PERIODIC_FORMS = frozenset({
    "10-K", "10-K/A", "10-Q", "10-Q/A", "10-KT", "10-KT/A", "10-QT", "10-QT/A",
    "20-F", "20-F/A", "40-F", "40-F/A",
})  # fmt: skip
FOREIGN_ANNUAL_FORMS = frozenset({"20-F", "20-F/A", "40-F", "40-F/A"})
FOREIGN_INTERIM_FORMS = frozenset({"6-K", "6-K/A"})


@dataclass(frozen=True)
class AsOfPoint:
    concept: str
    start: str | None
    end: str
    ptype: str  # Q | FY | TTM | I
    unit: str
    value: float
    accession: str
    filed: str
    first_value: float
    first_accession: str
    first_filed: str
    method: str  # tag(s) with marks, derivation, boundary labels

    @property
    def restated(self) -> bool:
        return self.first_value != self.value


@dataclass(frozen=True)
class AsOfResult:
    concept: str
    as_of: str
    points: tuple[AsOfPoint, ...]
    excluded: dict[str, int] = field(default_factory=dict)  # reason → fact rows left out

    def get(self, end: str, ptype: str) -> AsOfPoint | None:
        return next((p for p in self.points if p.end == end and p.ptype == ptype), None)

    def latest(self, ptype: str) -> AsOfPoint | None:
        pts = [p for p in self.points if p.ptype == ptype]
        return max(pts, key=lambda p: p.end) if pts else None


def is_foreign_filer(engine: sqlite3.Connection, cik: str) -> bool:
    """Annual report on 20-F or 40-F (its 6-Ks then count as periodic, S1.1)."""
    marks = ",".join("?" * len(FOREIGN_ANNUAL_FORMS))
    forms = sorted(FOREIGN_ANNUAL_FORMS)
    row = engine.execute(
        f"SELECT 1 FROM filing WHERE cik = ? AND form IN ({marks}) "
        f"UNION ALL SELECT 1 FROM fact WHERE cik = ? AND form IN ({marks}) LIMIT 1",
        (cik, *forms, cik, *forms),
    ).fetchone()
    return row is not None


def _document_period_ends(engine: sqlite3.Connection, cik: str) -> dict[str, str]:
    """accession → period the document reports on: filing.report_date, else the latest
    period end among that accession's facts."""
    out = {
        r["accession"]: r["report_date"]
        for r in engine.execute(
            "SELECT accession, report_date FROM filing WHERE cik = ? AND report_date IS NOT NULL",
            (cik,),
        )
    }
    for r in engine.execute(
        "SELECT accession, max(period_end) AS e FROM fact WHERE cik = ? GROUP BY accession", (cik,)
    ):
        out.setdefault(r["accession"], r["e"])
    return out


def facts_as_of(
    engine: sqlite3.Connection,
    cik: str,
    concept: str | Concept,
    as_of: str,
    *,
    ptype: str | None = None,
    include_shell: bool = False,
) -> AsOfResult:
    """Points of `concept` as known on `as_of` (ISO date), oldest first."""
    norm = normalize_cik(cik) or cik
    base = ALL_CONCEPTS[concept] if isinstance(concept, str) else concept
    con = concept_for(norm, base)
    links = entity_links(engine, norm)
    predecessors = {lk.predecessor_cik: lk for lk in links if lk.kind == "predecessor"}
    shells = [lk for lk in links if lk.kind == "spac_shell"]

    allowed = set(PERIODIC_FORMS)
    if is_foreign_filer(engine, norm):
        allowed |= FOREIGN_INTERIM_FORMS
    doc_end = _document_period_ends(engine, norm) if shells else {}

    excluded: Counter[str] = Counter()
    kept, from_predecessor = [], set()
    for r in concept_rows(engine, [norm, *predecessors], con):
        if r["filed"] > as_of:
            excluded["filed after as-of date"] += 1
            continue
        if r["form"] not in allowed:
            excluded[f"form {r['form'] or 'unknown'} (not a periodic report)"] += 1
            continue
        if r["cik"] != norm:
            link = predecessors[r["cik"]]
            if r["filed"] > link.boundary_date:
                excluded["predecessor CIK filing after the boundary"] += 1
                continue
            from_predecessor.add(r["accession"])
        elif shells and not include_shell:
            end = doc_end.get(r["accession"], r["period_end"])
            if any(end < lk.boundary_date for lk in shells):
                excluded["shell (pre-closing document)"] += 1
                continue
        kept.append(r)

    built = points_from_rows(con, kept, first_any_tag=True)
    points = []
    for p in built.points if built else ():
        if ptype and p.ptype != ptype:
            continue
        method = p.method
        if p.latest.accession in from_predecessor or p.first.accession in from_predecessor:
            names = ", ".join(f"{lk.name} ({c})" for c, lk in predecessors.items())
            method += f"; predecessor CIK: {names}"
        if shells and include_shell:
            method += "; shell periods included"
        points.append(
            AsOfPoint(
                base.name,
                p.start,
                p.end,
                p.ptype,
                p.unit,
                p.latest.value,
                p.latest.accession,
                p.latest.filed,
                p.first.value,
                p.first.accession,
                p.first.filed,
                f"{method}; as of {as_of}",
            )  # fmt: skip
        )
    return AsOfResult(base.name, as_of, tuple(points), dict(excluded))
