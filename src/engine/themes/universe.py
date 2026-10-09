"""Denominators for theme breadth: distinct filers per form family per window (D-M02-14).

Source: EDGAR's quarterly full index by form type (one request per quarter; the
compressed `form.gz` first, `form.idx` if that is missing). Only the tracked form
families are kept, one row per filing and filer (co-registrants count once each).
A closed quarter is fetched once; the open quarter is re-read when older than a day.
A window is counted only when every quarter it touches is stored; otherwise the
denominator is missing (None), never zero.
"""

from __future__ import annotations

import gzip
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from engine.sec.client import SecClient, iso
from engine.sec.identity import normalize_cik
from engine.sec.results import Failed, NotFound, Ok

INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/{name}"

# Form family → base forms. EFTS `forms` matches root forms, so amendments (…/A) are
# part of the family on both sides of the share (confirm with the live probe).
FAMILIES: dict[str, tuple[str, ...]] = {
    "10-K": ("10-K", "10-K405", "10-KT", "10-KSB"),
    "10-Q": ("10-Q", "10-QT", "10-QSB"),
    "8-K": ("8-K",),
    "20-F": ("20-F", "40-F"),
}
_FAMILY_OF = {form: fam for fam, forms in FAMILIES.items() for form in forms}
OPEN_QUARTER_TTL = timedelta(days=1)


def family_of(form: str) -> str | None:
    base = form.strip().upper()
    if base.endswith("/A"):
        base = base[:-2]
    return _FAMILY_OF.get(base)


@dataclass(frozen=True)
class IndexRow:
    accession: str
    cik: str
    family: str
    form: str
    filed: str


def parse_form_index(text: str) -> list[IndexRow]:
    """Rows of the tracked families from a form.idx file (fixed-width columns located
    from the header line; the form is cut at the Company Name column)."""
    lines = text.splitlines()
    try:
        head = next(i for i, ln in enumerate(lines) if ln.startswith("Form Type"))
    except StopIteration:
        raise ValueError("form index has no 'Form Type' header") from None
    company_col = lines[head].index("Company Name")
    out = []
    for ln in lines[head + 1 :]:
        if not ln.strip() or set(ln.strip()) == {"-"}:
            continue
        parts = ln.split()
        if len(parts) < 4 or not parts[-1].startswith("edgar/"):
            continue
        form = ln[:company_col].strip() if ln[company_col - 1 : company_col] == " " else parts[0]
        fam = family_of(form)
        if fam is None:
            continue
        cik = normalize_cik(parts[-3])
        filed = parts[-2]
        accession = parts[-1].rsplit("/", 1)[-1].removesuffix(".txt")
        if cik and len(filed) == 10:
            out.append(IndexRow(accession, cik, fam, form, filed))
    return out


def quarter_of(d: date) -> tuple[int, int]:
    return d.year, (d.month - 1) // 3 + 1


def quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    start = date(year, 3 * quarter - 2, 1)
    nxt = date(year + (quarter == 4), 1 if quarter == 4 else 3 * quarter + 1, 1)
    return start, nxt - timedelta(days=1)


def quarters_between(start: date, end: date) -> list[tuple[int, int]]:
    out, (y, q) = [], quarter_of(start)
    while (y, q) <= quarter_of(end):
        out.append((y, q))
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)
    return out


@dataclass(frozen=True)
class QuarterResult:
    year: int
    quarter: int
    status: str  # stored, fetched, failed
    rows: int | None = None
    detail: str | None = None


def ensure_quarters(
    client: SecClient,
    engine: sqlite3.Connection,
    quarters: Iterable[tuple[int, int]],
    now: datetime,
) -> list[QuarterResult]:
    """Fetch every quarter not yet stored (or open and stale). A throttle stops the run."""
    out = []
    today = now.date()
    for year, quarter in quarters:
        row = engine.execute("SELECT closed, fetched_at FROM form_index WHERE year = ? AND "
                             "quarter = ?", (year, quarter)).fetchone()  # fmt: skip
        if row is not None and (
            row["closed"] or now - datetime.fromisoformat(row["fetched_at"]) < OPEN_QUARTER_TTL
        ):
            out.append(QuarterResult(year, quarter, "stored"))
            continue
        res = _fetch_index(client, year, quarter)
        if not isinstance(res, Ok):
            detail = res.reason if isinstance(res, Failed) else "not published"
            out.append(QuarterResult(year, quarter, "failed", detail=detail))
            if isinstance(res, Failed) and res.throttled:
                break
            continue
        try:
            rows = parse_form_index(res.data)
        except ValueError as e:
            out.append(QuarterResult(year, quarter, "failed", detail=str(e)))
            continue
        closed = quarter_bounds(year, quarter)[1] < today
        _store(engine, year, quarter, rows, closed, res.source_ref, now)
        out.append(QuarterResult(year, quarter, "fetched", rows=len(rows)))
    return out


def _fetch_index(client: SecClient, year: int, quarter: int) -> Ok[str] | Failed | NotFound:
    gz = client.get_bytes(INDEX_URL.format(year=year, quarter=quarter, name="form.gz"), ttl_s=0)
    if isinstance(gz, Ok):
        try:
            text = gzip.decompress(gz.data).decode("latin-1")
        except (OSError, EOFError) as e:
            return Failed(f"form.gz unreadable: {e}")
        return Ok(text, source_ref=gz.source_ref, fetched_at=gz.fetched_at)
    if isinstance(gz, Failed) and (gz.throttled or (gz.status or 0) >= 500):
        return gz
    return client.get_text(INDEX_URL.format(year=year, quarter=quarter, name="form.idx"),
                           ttl_s=0)  # fmt: skip


def _store(
    engine: sqlite3.Connection,
    year: int,
    quarter: int,
    rows: list[IndexRow],
    closed: bool,
    source_ref: str,
    now: datetime,
) -> None:
    engine.execute("BEGIN")
    try:
        engine.executemany(
            "INSERT INTO form_filing (accession, cik, family, form, filed) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            [(r.accession, r.cik, r.family, r.form, r.filed) for r in rows],
        )
        engine.execute(
            "INSERT INTO form_index (year, quarter, rows, last_filed, closed, source_ref, "
            "fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (year, quarter) DO UPDATE "
            "SET rows = excluded.rows, last_filed = excluded.last_filed, closed = excluded.closed,"
            " source_ref = excluded.source_ref, fetched_at = excluded.fetched_at",
            (year, quarter, len(rows), max((r.filed for r in rows), default=None), int(closed),
             source_ref, iso(now)),
        )  # fmt: skip
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise


def data_through(engine: sqlite3.Connection) -> str | None:
    """Latest filing date in the stored index (the end of a year-to-date window)."""
    row = engine.execute("SELECT max(last_filed) FROM form_index").fetchone()
    return row[0] if row else None


def filers(engine: sqlite3.Connection, family: str, start: str, end: str) -> int | None:
    """Distinct filers of the family in [start, end]; None unless every quarter is stored
    and the index reaches the window's end."""
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    for y, q in quarters_between(s, e):
        row = engine.execute("SELECT last_filed, closed FROM form_index WHERE year = ? AND "
                             "quarter = ?", (y, q)).fetchone()  # fmt: skip
        if row is None:
            return None
        q_end = min(quarter_bounds(y, q)[1], e)
        if not row["closed"] and (row["last_filed"] or "") < q_end.isoformat():
            return None
    return engine.execute(
        "SELECT count(DISTINCT cik) FROM form_filing WHERE family = ? AND filed BETWEEN ? AND ?",
        (family, start, end),
    ).fetchone()[0]
