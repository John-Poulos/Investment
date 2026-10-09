"""Spenders derived from XBRL frames, not listed (D-M02-19 (1), D-M02-20 (6), D-M02-30 (2)).

Reported capex for every filer comes from annual frames (calendar-year aligned by SEC):
level, growth vs the year before and share of all-filer capex. Size alone is dominated
by energy, utilities and telecoms, so a company is proposed as an `m02_candidate` only
when capex ≥ $1B in the latest year, it ranks in the top 25 by level or by growth, and
it already appears in stored full-text hits for an active theme phrase. Not yet core or
tracked. Proposals go through the weekly cap, largest first; the rest wait on the
Themes page. A spender counts toward a theme only through a confirmed quoted sentence
(links.py), never by size.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from engine.sec.client import SecClient
from engine.sec.frames import concept_frame, frame_name
from engine.sec.results import Ok

MIN_CAPEX = 1e9
TOP_N = 25


@dataclass(frozen=True)
class Spender:
    cik: str
    name: str | None
    year: int
    capex: float
    prior: float | None
    tag: str

    @property
    def growth(self) -> float | None:
        if not self.prior or self.prior <= 0:
            return None
        return self.capex / self.prior - 1


def fetch_frames(
    client: SecClient, engine: sqlite3.Connection, years: list[int], now: datetime
) -> list[str]:
    """Annual capex frames (each candidate tag) → problems."""
    problems = []
    for y in years:
        res = concept_frame(client, engine, "capex", frame_name(y), now)
        if not isinstance(res, Ok):
            problems.append(f"CY{y}: {getattr(res, 'reason', res)}")
        elif res.data.tags_failed:
            problems.extend(f"CY{y}: {f}" for f in res.data.tags_failed)
    return problems


def _year_values(engine: sqlite3.Connection, year: int) -> dict[str, tuple[float, str, str]]:
    """cik → (value, tag, entity) by tag priority, from stored frames."""
    from engine.sec.xbrl_facts import CONCEPT_BY_NAME

    out: dict[str, tuple[float, str, str]] = {}
    for taxonomy, tag in CONCEPT_BY_NAME["capex"].tags:
        for r in engine.execute(
            "SELECT cik, value, entity_name FROM frame_value WHERE taxonomy = ? AND tag = ? "
            "AND unit = 'USD' AND frame = ?",
            (taxonomy, tag, frame_name(year)),
        ):
            out.setdefault(r["cik"], (float(r["value"]), f"{taxonomy}:{tag}", r["entity_name"]))
    return out


def spenders(engine: sqlite3.Connection, year: int) -> tuple[list[Spender], float | None]:
    """Every filer's capex for a calendar year, and the all-filer total (None if no frame)."""
    now_v, prev_v = _year_values(engine, year), _year_values(engine, year - 1)
    if not now_v:
        return [], None
    out = [
        Spender(cik, name, year, v, prev_v.get(cik, (None,))[0], tag)
        for cik, (v, tag, name) in now_v.items()
    ]
    total = sum(s.capex for s in out if s.capex > 0)
    return sorted(out, key=lambda s: -s.capex), total


def theme_hits(engine: sqlite3.Connection) -> dict[str, list[str]]:
    """cik → active theme keys whose phrases have stored full-text hits for that company."""
    out: dict[str, set[str]] = {}
    for r in engine.execute(
        "SELECT DISTINCT h.cik, t.key FROM fulltext_hit h "
        "JOIN fulltext_query q ON q.query_id = h.query_id "
        "JOIN theme_phrase p ON p.phrase = q.phrase AND p.status = 'active' "
        "JOIN theme t ON t.theme_id = p.theme_id AND t.status = 'active' "
        "WHERE h.cik IS NOT NULL"
    ):
        out.setdefault(r["cik"], set()).add(r["key"])
    return {k: sorted(v) for k, v in out.items()}


def candidates(
    engine: sqlite3.Connection, year: int, exclude: set[str]
) -> list[tuple[Spender, list[str], str]]:
    """(spender, themes, why) for D-M02-20 (6), largest first."""
    rows, total = spenders(engine, year)
    big = [s for s in rows if s.capex >= MIN_CAPEX]
    by_level = {s.cik for s in big[:TOP_N]}
    growers = sorted((s for s in big if s.growth is not None), key=lambda s: -(s.growth or 0))
    by_growth = {s.cik for s in growers[:TOP_N]}
    hits = theme_hits(engine)
    out = []
    for s in big:
        if s.cik in exclude or s.cik not in hits or not (s.cik in by_level or s.cik in by_growth):
            continue
        why = []
        if s.cik in by_level:
            share = f", {s.capex / total:.1%} of all-filer capex" if total else ""
            why.append(f"top {TOP_N} by capex (${s.capex / 1e9:,.1f}B in {year}{share})")
        if s.cik in by_growth and s.growth is not None:
            why.append(f"top {TOP_N} by capex growth ({s.growth:+.0%} vs {year - 1})")
        out.append((s, hits[s.cik], "; ".join(why)))
    return out


def propose_candidates(
    engine: sqlite3.Connection, year: int, exclude: set[str], now: datetime
) -> dict[str, int]:
    from engine.themes.proposals import propose

    counts: dict[str, int] = {}
    _, total = spenders(engine, year)
    for s, themes, why in candidates(engine, year, exclude):
        ticker = engine.execute(
            "SELECT ticker FROM ticker WHERE cik = ? AND valid_to IS NULL ORDER BY ticker LIMIT 1",
            (s.cik,),
        ).fetchone()
        payload = {
            "ticker": ticker[0] if ticker else None,
            "name": s.name,
            "year": year,
            "capex": s.capex,
            "growth": s.growth,
            "tag": s.tag,
            "share": (s.capex / total) if total else None,
            "themes": themes,
            "theme_key": themes[0],
            "why": why,
            "money_flow": True,
            "kind": "spender",
        }
        reason = f"{payload['ticker'] or s.name}: capex spender — {why}"
        res = propose(engine, "m02_candidate", s.cik, reason, payload, now, cik=s.cik)
        counts[res] = counts.get(res, 0) + 1
    return counts
