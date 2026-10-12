"""Year-ago twins for phrase mining (D-M02-52 (1)).

For each core or promoted company, every stored 10-K, 10-Q, 20-F and earnings release
of the current mining period gets its twin: the same form filed about a year earlier
(300–430 days before, the closest to 365; a 10-Q also matches its report date within
45 days of a year earlier, so a fiscal quarter meets the same quarter). Missing twins are
fetched from SEC (filing index + documents, as the refresh does), capped per run; a
throttle stops the batch and the rest wait for the next run. Call transcripts are not
backfilled (Alpha Vantage budget): calls join the comparison when a year-old one exists.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from engine.sec.client import SecClient
from engine.sec.documents import ingest_filing
from engine.sec.results import Failed, Ok
from engine.sec.submissions import Filing, stored_filings
from engine.themes.mining import Doc, corpus_docs, periods

MIN_DAYS, MAX_DAYS = 300, 430
REPORT_TOLERANCE = 45
FETCH_CAP = 120  # filings per run (~3 requests each)


@dataclass
class TwinReport:
    planned: list[tuple[str, str, str]] = field(default_factory=list)  # (cik, form, accession)
    stored: int = 0
    failed: list[str] = field(default_factory=list)
    no_twin: list[str] = field(default_factory=list)  # "cik form accession: why"
    left: int = 0  # over the cap or after a throttle
    throttled: str | None = None

    def lines(self) -> list[str]:
        out = [
            f"year-ago twins: {len(self.planned)} to fetch, {self.stored} stored, "
            f"{len(self.failed)} failed, {self.left} left for the next run, "
            f"{len(self.no_twin)} current documents without a twin in the filing index"
        ]
        if self.throttled:
            out.append(f"  stopped by SEC throttle: {self.throttled}")
        out += [f"  failed {f}" for f in self.failed[:10]]
        return out


def _is_release(f: Filing) -> bool:
    return f.form == "8-K" and f.has_item("2.02")


def find_twin(f: Filing, filings: list[Filing]) -> Filing | None:
    """The same kind of filing about a year before `f`, or None."""
    d = date.fromisoformat(f.filed)
    best: tuple[int, Filing] | None = None
    for g in filings:
        if g.accession == f.accession:
            continue
        same = _is_release(g) if _is_release(f) else g.form == f.form
        if not same:
            continue
        gap = (d - date.fromisoformat(g.filed)).days
        if not MIN_DAYS <= gap <= MAX_DAYS:
            continue
        if f.form == "10-Q" and f.report_date and g.report_date:
            off = abs((date.fromisoformat(f.report_date) - date.fromisoformat(g.report_date)).days
                      - 365)  # fmt: skip
            if off > REPORT_TOLERANCE:
                continue
        score = abs(gap - 365)
        if best is None or score < best[0]:
            best = (score, g)
    return best[1] if best else None


def plan(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, ciks: Iterable[str], season_date: date
) -> tuple[list[Filing], list[str]]:
    """Twins to fetch (not stored yet) and the current documents that have none."""
    cur, _ = periods(season_date)
    docs: list[Doc] = corpus_docs(engine, corpus)
    stored_acc = {d.accession for d in docs if d.kind}
    todo: dict[str, Filing] = {}
    missing: list[str] = []
    for cik in ciks:
        filings = stored_filings(engine, cik)
        by_acc = {f.accession: f for f in filings}
        current = {d.accession for d in docs if d.cik == cik and d.kind in
                   ("10-K", "10-Q", "20-F", "release") and cur[0] <= d.dated <= cur[1]}  # fmt: skip
        for acc in sorted(current):
            f = by_acc.get(acc)
            if f is None:
                continue
            twin = find_twin(f, filings)
            if twin is None:
                missing.append(f"{cik} {f.form} {acc}: no filing of the same kind a year earlier")
            elif twin.accession not in stored_acc:
                todo[twin.accession] = twin
    return sorted(todo.values(), key=lambda f: (f.cik, f.filed)), missing


def fetch_twins(
    client: SecClient,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    ciks: Iterable[str],
    season_date: date,
    now: datetime,
    cap: int = FETCH_CAP,
) -> TwinReport:
    todo, missing = plan(engine, corpus, list(ciks), season_date)
    rep = TwinReport(planned=[(f.cik, f.form, f.accession) for f in todo], no_twin=missing)
    for i, f in enumerate(todo):
        if i >= cap:
            rep.left = len(todo) - i
            break
        res = ingest_filing(client, corpus, f, now)
        if isinstance(res, Failed) and res.throttled:
            rep.throttled, rep.left = res.reason, len(todo) - i
            break
        if isinstance(res, Ok):
            rep.stored += 1
            rep.failed += [f"{f.accession} {x}" for x in res.data.failed]
        else:
            rep.failed.append(f"{f.accession}: {getattr(res, 'reason', res)}")
    return rep


def season_ago(d: date) -> date:
    return d - timedelta(days=365)
