"""Filing index per company from the submissions API (M00_SEC_DATA submissions.py).

The main file (CIK##########.json) holds the most recent filings under
`filings.recent`; older history is split into page files listed in
`filings.files`, each holding the same parallel arrays at top level. All pages
are read (the old engine read `recent` only). Page files cover closed date
ranges, so a page ingested once is not fetched again.

A page that fails or is not found leaves the sync marked incomplete with the
page named; the rows that did load are kept and the page is retried next sync.
Empty strings from SEC are stored as NULL (missing stays missing).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from engine.sec.client import SecClient, iso
from engine.sec.identity import CACHE_TTL_S, SUBMISSIONS_URL, normalize_cik
from engine.sec.results import Empty, Failed, NotFound, Ok, Probe, Result

PAGE_URL = "https://data.sec.gov/submissions/{name}"
PAGE_TTL_S = 30 * 86400  # older pages change rarely; ingested pages are skipped anyway
PARSER_VERSION = "submissions-1"

REQUIRED = ("accessionNumber", "filingDate", "form")


@dataclass(frozen=True)
class Filing:
    accession: str
    cik: str
    form: str
    filed: str
    accepted_at: str | None
    report_date: str | None
    items: tuple[str, ...]  # 8-K item codes, e.g. ("2.02", "9.01")
    primary_doc: str | None
    primary_doc_desc: str | None
    is_xbrl: bool | None
    is_inline_xbrl: bool | None
    size: int | None

    def has_item(self, code: str) -> bool:
        return code in self.items


@dataclass(frozen=True)
class FilingSync:
    cik: str
    filings_seen: int
    new: int
    pages_total: int
    pages_loaded: tuple[str, ...]
    pages_skipped: tuple[str, ...]  # already ingested in an earlier sync
    pages_failed: tuple[str, ...] = field(default_factory=tuple)  # "name: reason"

    @property
    def complete(self) -> bool:
        return not self.pages_failed


# --- Parsing -----------------------------------------------------------------


def _text(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _flag(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    return bool(int(value))


def _int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def parse_items(value: Any) -> tuple[str, ...]:
    text = _text(value)
    if text is None:
        return ()
    return tuple(code.strip() for code in text.split(",") if code.strip())


def parse_filing_arrays(cik: str, arrays: dict[str, Any]) -> list[Filing]:
    """Parallel arrays (filings.recent, or a page file) → Filing rows.

    Raises ValueError if a required array is missing or lengths disagree, so a
    malformed page is reported as a failure, never read as fewer filings.
    """
    missing = [k for k in REQUIRED if k not in arrays]
    if missing:
        raise ValueError(f"submissions arrays missing {missing}")
    n = len(arrays["accessionNumber"])
    for key, values in arrays.items():
        if isinstance(values, list) and len(values) != n:
            raise ValueError(f"submissions array {key} has {len(values)} entries, expected {n}")

    def col(key: str) -> Sequence[Any]:
        return arrays.get(key) or [None] * n

    acc, filed, form = col("accessionNumber"), col("filingDate"), col("form")
    accepted, report, items = col("acceptanceDateTime"), col("reportDate"), col("items")
    doc, desc = col("primaryDocument"), col("primaryDocDescription")
    xbrl, ixbrl, size = col("isXBRL"), col("isInlineXBRL"), col("size")

    out = []
    for i in range(n):
        accession = _text(acc[i])
        if accession is None:
            raise ValueError(f"submissions row {i} has no accession number")
        out.append(
            Filing(
                accession=accession,
                cik=cik,
                form=_text(form[i]) or "",
                filed=_text(filed[i]) or "",
                accepted_at=_text(accepted[i]),
                report_date=_text(report[i]),
                items=parse_items(items[i]),
                primary_doc=_text(doc[i]),
                primary_doc_desc=_text(desc[i]),
                is_xbrl=_flag(xbrl[i]),
                is_inline_xbrl=_flag(ixbrl[i]),
                size=_int(size[i]),
            )
        )
    return out


# --- Storage -----------------------------------------------------------------


def store_filings(conn: sqlite3.Connection, filings: Iterable[Filing], now: datetime) -> int:
    """Upsert filings and their CIK links. Returns the number of new accessions."""
    new = 0
    stamp = iso(now)
    for f in filings:
        cur = conn.execute(
            "INSERT INTO filing (accession, cik, form, filed, accepted_at, report_date, items, "
            "primary_doc, primary_doc_desc, is_xbrl, is_inline_xbrl, size, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (accession) DO NOTHING",
            (
                f.accession,
                f.cik,
                f.form,
                f.filed,
                f.accepted_at,
                f.report_date,
                ",".join(f.items) or None,
                f.primary_doc,
                f.primary_doc_desc,
                _db_flag(f.is_xbrl),
                _db_flag(f.is_inline_xbrl),
                f.size,
                stamp,
            ),
        )
        if cur.rowcount:
            new += 1
        else:
            # Known accession: fill fields SEC has since populated; never blank stored values.
            conn.execute(
                "UPDATE filing SET accepted_at = coalesce(accepted_at, ?), "
                "report_date = coalesce(report_date, ?), items = coalesce(items, ?), "
                "primary_doc = coalesce(primary_doc, ?), "
                "primary_doc_desc = coalesce(primary_doc_desc, ?), "
                "is_xbrl = coalesce(is_xbrl, ?), is_inline_xbrl = coalesce(is_inline_xbrl, ?), "
                "size = coalesce(size, ?) WHERE accession = ?",
                (
                    f.accepted_at,
                    f.report_date,
                    ",".join(f.items) or None,
                    f.primary_doc,
                    f.primary_doc_desc,
                    _db_flag(f.is_xbrl),
                    _db_flag(f.is_inline_xbrl),
                    f.size,
                    f.accession,
                ),
            )
        conn.execute(
            "INSERT INTO filing_cik (accession, cik) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (f.accession, f.cik),
        )
    return new


def _db_flag(value: bool | None) -> int | None:
    return None if value is None else int(value)


def _page_state(name: str) -> str:
    return f"submissions_page:{name}"


def _page_done(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM refresh_state WHERE name = ?", (_page_state(name),)).fetchone()
        is not None
    )


def _mark(conn: sqlite3.Connection, name: str, source_ref: str, now: datetime, detail: Any) -> None:
    conn.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET source_ref = excluded.source_ref, "
        "fetched_at = excluded.fetched_at, detail = excluded.detail",
        (name, source_ref, iso(now), json.dumps(detail)),
    )


# --- Sync --------------------------------------------------------------------


def sync_filings(
    client: SecClient,
    conn: sqlite3.Connection,
    cik: str,
    now: datetime,
    *,
    fresh: bool = False,
) -> Result[FilingSync]:
    """Bring the stored filing index for `cik` up to date with SEC (all pages).

    `fresh=True` refetches the main submissions file even if a cached copy exists
    (the nightly refresh uses it when the daily index shows a new filing).
    """
    norm = normalize_cik(cik)
    if norm is None:
        return Empty((Probe("CIK", str(cik), "not a CIK"),))

    url = SUBMISSIONS_URL.format(cik=norm)
    main = client.get_json(url, ttl_s=CACHE_TTL_S, fresh=fresh)
    if not isinstance(main, Ok):
        return main  # NotFound: no submissions file at this URL; Failed: retry later

    try:
        filings_root = main.data["filings"]
        recent = parse_filing_arrays(norm, filings_root["recent"])
        pages = [p["name"] for p in filings_root.get("files") or []]
    except (KeyError, TypeError, ValueError) as exc:
        return Failed(f"submissions unreadable: {exc}", url=url)

    conn.execute("BEGIN")
    try:
        new = store_filings(conn, recent, now)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    seen = len(recent)

    loaded, skipped, failed = [], [], []
    for name in pages:
        if _page_done(conn, name):
            skipped.append(name)
            continue
        page_url = PAGE_URL.format(name=name)
        res = client.get_json(page_url, ttl_s=PAGE_TTL_S)
        if isinstance(res, NotFound):
            failed.append(f"{name}: no file at {page_url} (HTTP 404)")
            continue
        if not isinstance(res, Ok):
            failed.append(f"{name}: {res.reason if isinstance(res, Failed) else res}")
            continue
        try:
            rows = parse_filing_arrays(norm, res.data)
        except (TypeError, ValueError, AttributeError) as exc:
            failed.append(f"{name}: unreadable ({exc})")
            continue
        conn.execute("BEGIN")
        try:
            new += store_filings(conn, rows, now)
            _mark(conn, _page_state(name), page_url, now, {"filings": len(rows)})
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        seen += len(rows)
        loaded.append(name)

    summary = FilingSync(norm, seen, new, len(pages), tuple(loaded), tuple(skipped), tuple(failed))
    detail = {**summary.__dict__, "complete": summary.complete, "parser": PARSER_VERSION}
    conn.execute("BEGIN")
    _mark(conn, f"submissions:{norm}", url, now, detail)
    conn.execute("COMMIT")
    return Ok(summary, source_ref=url, fetched_at=iso(now), from_cache=main.from_cache)


# --- Queries -----------------------------------------------------------------


def stored_filings(
    conn: sqlite3.Connection,
    cik: str,
    *,
    forms: Iterable[str] | None = None,
    since: str | None = None,
    item: str | None = None,
) -> list[Filing]:
    """Stored filings listed under `cik`, newest first. `item` filters 8-K item codes."""
    sql = "SELECT f.* FROM filing f JOIN filing_cik c ON c.accession = f.accession WHERE c.cik = ?"
    args: list[Any] = [normalize_cik(cik) or cik]
    form_list = list(forms or [])
    if form_list:
        sql += f" AND f.form IN ({', '.join('?' * len(form_list))})"
        args += form_list
    if since:
        sql += " AND f.filed >= ?"
        args.append(since)
    sql += " ORDER BY f.filed DESC, f.accession DESC"
    rows = [_filing_from_row(r, cik) for r in conn.execute(sql, args)]
    if item:
        rows = [f for f in rows if f.has_item(item)]
    return rows


def filing_by_accession(conn: sqlite3.Connection, accession: str) -> Filing | None:
    """One stored filing, attributed to the CIK that first listed it."""
    row = conn.execute("SELECT * FROM filing WHERE accession = ?", (accession,)).fetchone()
    return _filing_from_row(row, row["cik"]) if row else None


NEW_8K_ITEMS_FROM = "2004-08-23"  # Form 8-K item numbering changed on this date


def earnings_releases(conn: sqlite3.Connection, cik: str, since: str | None = None) -> list[Filing]:
    """8-Ks carrying Item 2.02 (results of operations), not just any 8-K (R19).

    Before 2004-08-23 the same item was numbered 12 (D-SEC-13), so those count too.
    """
    return [
        f
        for f in stored_filings(conn, cik, forms=("8-K", "8-K/A"), since=since)
        if f.has_item("2.02") or (f.filed < NEW_8K_ITEMS_FROM and f.has_item("12"))
    ]


def _filing_from_row(row: sqlite3.Row, cik: str) -> Filing:
    def flag(v: Any) -> bool | None:
        return None if v is None else bool(v)

    return Filing(
        accession=row["accession"],
        cik=normalize_cik(cik) or row["cik"],
        form=row["form"],
        filed=row["filed"],
        accepted_at=row["accepted_at"],
        report_date=row["report_date"],
        items=parse_items(row["items"]),
        primary_doc=row["primary_doc"],
        primary_doc_desc=row["primary_doc_desc"],
        is_xbrl=flag(row["is_xbrl"]),
        is_inline_xbrl=flag(row["is_inline_xbrl"]),
        size=row["size"],
    )
