"""XBRL frames → peer values and robust peer statistics (M00_SEC_DATA frames.py; R24, CvD).

A frame is one value per company for one tag, unit and calendar period, for every
filer (https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{period}.json).
Periods: CY2025Q2 (quarter), CY2025 (year), CY2025Q2I (instant). SEC aligns each
company's fiscal period to the nearest calendar period.

- A concept may be reported under several tags, so every candidate tag's frame is
  read and each company gets the value of its highest-priority tag (same order as
  xbrl_facts). The tag used stays with the value, so a fallback tag is visible.
- Peer statistics: median, quartiles, robust z = (x − median) ÷ (IQR ÷ 1.35).
  Peers without a value are listed, never counted as zero; fewer than five peers
  is flagged low confidence (M04 switches to its fixed-gap fallback).
- Frame TTM = four calendar-quarter frames summed, only for companies with all
  four. Live 2026-10-07: calendar-Q4 frames are sparse (most companies report Q4
  only inside the annual figure), so frame TTM misses most companies. Peer TTM,
  quarterly flows and growth therefore come from each peer's own xbrl_facts
  series (series_values, series_yoy), which derives Q4 and TTM and avoids
  calendar alignment for off-calendar fiscal years. Frames remain the source
  for instants, annual values and market-wide breadth.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from engine.sec.client import SecClient, iso
from engine.sec.identity import normalize_cik
from engine.sec.results import Failed, NotFound, Ok, Probe, Result
from engine.sec.xbrl_facts import CONCEPT_BY_NAME, Concept, get_series

FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{period}.json"
FRAME_BACKSTOP = timedelta(days=30)
CACHE_TTL_S = 20 * 3600
MIN_PEERS = 5  # below this M04 uses its fixed-gap fallback (low confidence)
IQR_TO_SD = 1.35  # IQR of a normal distribution ≈ 1.35 σ


# --- Period names --------------------------------------------------------------


def frame_name(year: int, quarter: int | None = None, *, instant: bool = False) -> str:
    if quarter is None:
        if instant:
            raise ValueError("instant frames are quarterly (CY2025Q4I)")
        return f"CY{year}"
    if not 1 <= quarter <= 4:
        raise ValueError(f"quarter must be 1-4, got {quarter}")
    return f"CY{year}Q{quarter}{'I' if instant else ''}"


def calendar_quarter(start: str | None, end: str) -> tuple[int, int]:
    """Calendar quarter a fiscal period maps to: midpoint for durations, end for instants."""
    e = date.fromisoformat(end)
    point = e if not start else date.fromisoformat(start) + (e - date.fromisoformat(start)) / 2
    return point.year, (point.month - 1) // 3 + 1


def previous_quarters(year: int, quarter: int, n: int) -> list[tuple[int, int]]:
    """The n calendar quarters ending at (year, quarter), oldest first."""
    out = []
    y, q = year, quarter
    for _ in range(n):
        out.append((y, q))
        y, q = (y, q - 1) if q > 1 else (y - 1, 4)
    return out[::-1]


# --- Fetch and store -----------------------------------------------------------


@dataclass(frozen=True)
class FrameValue:
    cik: str
    value: float | int
    tag: str  # taxonomy:tag that supplied the value
    accession: str | None
    start: str | None
    end: str | None
    entity_name: str | None


def _state_name(taxonomy: str, tag: str, unit: str, period: str) -> str:
    return f"frame:{taxonomy}:{tag}:{unit}:{period}"


def fetch_frame(
    client: SecClient,
    engine: sqlite3.Connection,
    taxonomy: str,
    tag: str,
    unit: str,
    period: str,
    now: datetime,
    *,
    force: bool = False,
) -> Result[int]:
    """Store one frame (all companies) unless stored within 30 days. Ok(count stored)."""
    state = _state_name(taxonomy, tag, unit, period)
    row = engine.execute(
        "SELECT fetched_at, detail FROM refresh_state WHERE name = ?", (state,)
    ).fetchone()
    if row and not force and now - datetime.fromisoformat(row["fetched_at"]) < FRAME_BACKSTOP:
        detail = json.loads(row["detail"] or "{}")
        if detail.get("not_found"):
            return NotFound(FRAMES_URL.format(taxonomy=taxonomy, tag=tag, unit=unit, period=period))
        return Ok(detail.get("count", 0), fetched_at=row["fetched_at"], from_cache=True)

    url = FRAMES_URL.format(taxonomy=taxonomy, tag=tag, unit=unit, period=period)
    res = client.get_json(url, ttl_s=CACHE_TTL_S)
    if isinstance(res, NotFound):
        _mark(engine, state, url, now, {"not_found": True})  # no filer used this tag/period
        return res
    if not isinstance(res, Ok):
        return res
    data = res.data.get("data") if isinstance(res.data, dict) else None
    if not isinstance(data, list):
        return Failed("frame unreadable: no 'data' list", url=url)

    rows = []
    for d in data:
        cik = normalize_cik(d.get("cik", ""))
        if cik is None or d.get("val") is None:
            continue
        rows.append(
            (taxonomy, tag, unit, period, cik, d.get("entityName"), d["val"], d.get("accn"),
             d.get("end"), d.get("start"), iso(now))
        )  # fmt: skip
    engine.execute("BEGIN")
    try:
        engine.execute(
            "DELETE FROM frame_value WHERE taxonomy = ? AND tag = ? AND unit = ? AND frame = ?",
            (taxonomy, tag, unit, period),
        )
        engine.executemany(
            "INSERT INTO frame_value (taxonomy, tag, unit, frame, cik, entity_name, value, "
            "accession, period_end, period_start, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        _mark(engine, state, url, now, {"count": len(rows)})
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return Ok(len(rows), source_ref=url, fetched_at=iso(now))


def _mark(engine: sqlite3.Connection, name: str, url: str, now: datetime, detail: Any) -> None:
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET source_ref = excluded.source_ref, "
        "fetched_at = excluded.fetched_at, detail = excluded.detail",
        (name, url, iso(now), json.dumps(detail)),
    )


@dataclass(frozen=True)
class ConceptFrame:
    concept: str
    period: str
    unit: str
    values: dict[str, FrameValue]  # cik → value from its highest-priority tag
    tags_missing: tuple[Probe, ...] = field(default_factory=tuple)  # 404: tag unused that period
    tags_failed: tuple[str, ...] = field(default_factory=tuple)  # fetch failures (incomplete)

    @property
    def complete(self) -> bool:
        return not self.tags_failed


def _frame_unit(concept: Concept, currency: str) -> str:
    return {"currency": currency, "shares": "shares", "per_share": f"{currency}/shares"}[
        concept.unit
    ]


def concept_frame(
    client: SecClient,
    engine: sqlite3.Connection,
    concept: str,
    period: str,
    now: datetime,
    *,
    currency: str = "USD",
) -> Result[ConceptFrame]:
    """Every company's value for a concept and calendar period, by tag priority."""
    spec = CONCEPT_BY_NAME[concept]
    if period.endswith("I") != (spec.kind == "instant"):
        kind = "instant (CY2025Q2I)" if spec.kind == "instant" else "duration (CY2025Q2, CY2025)"
        return Failed(f"{concept} needs a {kind} frame, got {period}")
    unit = _frame_unit(spec, currency)

    values: dict[str, FrameValue] = {}
    missing, failed = [], []
    for taxonomy, tag in spec.tags:  # priority order: first tag seen for a cik wins
        res = fetch_frame(client, engine, taxonomy, tag, unit, period, now)
        if isinstance(res, NotFound):
            missing.append(Probe("frame", f"{taxonomy}:{tag} {unit} {period}", "HTTP 404"))
            continue
        if not isinstance(res, Ok):
            failed.append(f"{taxonomy}:{tag}: {res.reason if isinstance(res, Failed) else res}")
            continue
        for r in engine.execute(
            "SELECT cik, value, accession, period_start, period_end, entity_name FROM frame_value "
            "WHERE taxonomy = ? AND tag = ? AND unit = ? AND frame = ?",
            (taxonomy, tag, unit, period),
        ):
            values.setdefault(
                r["cik"],
                FrameValue(r["cik"], r["value"], f"{taxonomy}:{tag}", r["accession"],
                           r["period_start"], r["period_end"], r["entity_name"]),
            )  # fmt: skip
    return Ok(ConceptFrame(concept, period, unit, values, tuple(missing), tuple(failed)))


def ttm_frame(
    client: SecClient,
    engine: sqlite3.Connection,
    concept: str,
    year: int,
    quarter: int,
    now: datetime,
) -> Result[ConceptFrame]:
    """TTM per company = sum of four calendar-quarter frames ending at (year, quarter)."""
    spec = CONCEPT_BY_NAME[concept]
    if spec.kind != "flow" or not spec.additive:
        return Failed(f"{concept} is not an additive flow; no TTM")
    quarters = []
    for y, q in previous_quarters(year, quarter, 4):
        res = concept_frame(client, engine, concept, frame_name(y, q), now)
        if not isinstance(res, Ok):
            return res
        quarters.append(res.data)

    values = {}
    for cik in set.intersection(*(set(q.values) for q in quarters)):
        parts = [q.values[cik] for q in quarters]
        tags = sorted({p.tag for p in parts})
        values[cik] = FrameValue(
            cik, sum(p.value for p in parts), " + ".join(tags), parts[-1].accession,
            parts[0].start, parts[-1].end, parts[-1].entity_name,
        )  # fmt: skip
    period = f"TTM {frame_name(year, quarter)}"
    missing = tuple(p for q in quarters for p in q.tags_missing)
    failed = tuple(f for q in quarters for f in q.tags_failed)
    return Ok(ConceptFrame(concept, period, quarters[0].unit, values, missing, failed))


# --- Peer statistics -------------------------------------------------------------


@dataclass(frozen=True)
class PeerStats:
    n: int
    median: float | None
    q1: float | None
    q3: float | None
    robust_sd: float | None  # IQR ÷ 1.35
    members: tuple[str, ...]  # CIKs with a value
    missing: tuple[str, ...]  # requested peers without a value (not zero)

    @property
    def low_confidence(self) -> bool:
        return self.n < MIN_PEERS


def peer_stats(values: dict[str, float], peers: Iterable[str]) -> PeerStats:
    wanted = [normalize_cik(p) or p for p in peers]
    members = [p for p in wanted if p in values and values[p] is not None]
    missing = tuple(p for p in wanted if p not in members)
    xs = sorted(float(values[p]) for p in members)
    if not xs:
        return PeerStats(0, None, None, None, None, (), missing)
    median = statistics.median(xs)
    if len(xs) >= 2:
        q1, _, q3 = statistics.quantiles(xs, n=4, method="inclusive")
    else:
        q1 = q3 = xs[0]
    sd = (q3 - q1) / IQR_TO_SD
    return PeerStats(len(xs), median, q1, q3, sd if sd > 0 else None, tuple(members), missing)


def robust_z(value: float | None, stats: PeerStats) -> float | None:
    """(value − median) ÷ (IQR ÷ 1.35); None when either side is missing or IQR is zero."""
    if value is None or stats.median is None or stats.robust_sd is None:
        return None
    return (value - stats.median) / stats.robust_sd


def yoy_growth(now: ConceptFrame, year_ago: ConceptFrame) -> dict[str, float]:
    """Growth per company where both values exist and the earlier one is positive."""
    out = {}
    for cik, v in now.values.items():
        prior = year_ago.values.get(cik)
        if prior is not None and prior.value > 0:
            out[cik] = v.value / prior.value - 1
    return out


def values_of(frame: ConceptFrame) -> dict[str, float]:
    return {cik: v.value for cik, v in frame.values.items()}


# --- Peer values from each company's own series ------------------------------------


def series_values(
    engine: sqlite3.Connection,
    ciks: Iterable[str],
    concept: str,
    ptype: str,
    target_end: str,
    *,
    tolerance_days: int = 45,
    version: str = "latest",
) -> dict[str, FrameValue]:
    """Each peer's series point (Q, FY, TTM or I) ending closest to `target_end`.

    Requires sync_facts for each peer. Peers without a point within the tolerance
    are absent (missing, not zero); fiscal calendars that differ by up to the
    tolerance are compared as the same period.
    """
    target = date.fromisoformat(target_end)
    out = {}
    for raw in ciks:
        cik = normalize_cik(raw) or raw
        best, best_gap = None, None
        for row in get_series(engine, cik, concept, ptype):
            gap = abs((date.fromisoformat(row.end) - target).days)
            if gap <= tolerance_days and (best_gap is None or gap < best_gap):
                best, best_gap = row, gap
        if best is not None:
            v = getattr(best, version)
            out[cik] = FrameValue(
                cik, v.value, best.method, v.accession, best.start, best.end, None
            )
    return out


def series_yoy(
    engine: sqlite3.Connection,
    ciks: Iterable[str],
    concept: str,
    target_end: str,
    *,
    ptype: str = "TTM",
    tolerance_days: int = 45,
) -> dict[str, float]:
    """Year-over-year growth per peer from its own series (TTM by default)."""
    peers = list(ciks)
    now = series_values(engine, peers, concept, ptype, target_end, tolerance_days=tolerance_days)
    year_ago_end = (date.fromisoformat(target_end) - timedelta(days=364)).isoformat()
    before = series_values(
        engine, peers, concept, ptype, year_ago_end, tolerance_days=tolerance_days
    )
    out = {}
    for cik, v in now.items():
        prior = before.get(cik)
        if prior is not None and prior.value > 0 and v.end != prior.end:
            out[cik] = v.value / prior.value - 1
    return out
