"""13F-HR holdings of watchlist/tracked companies that file one (D-M02-42, D-M02-45 (1)).

Probe 2026-10-10: filers AMZN, GOOG, INTC, NVDA. The filing index lists `primary_doc.xml`
(cover page: period, `tableEntryTotal`, `tableValueTotal`, amendment type) and the
information table (type "INFORMATION TABLE", filename varies), each twice (raw and an
XSL rendering under `xslForm13F_…/`). Values are thousands of dollars in filings made
before 2023-01-03 and dollars after. One issuer can have several rows (other managers)
→ summed by CUSIP, title and put/call. The row sum must equal `tableValueTotal`.

Checks before a row is stored automatically (else held for review, `m02_fin_check`):
the filing's row sum matches its total; value within 25% of shares × the stored closing
price when the issuer has prices; shares no more than 10× the prior quarter's unless that
price check confirms them (D-M02-46 amendment). A filing made after 2023-01-03 whose priced
rows are all ≈ 1/1000 of shares × close is read in thousands (D-SEC-28 amendment).

Followed managers (M07 Part 2, D-SEC-28): `read_filing` / `store_rows` take a `keep`
filter, so a manager's rows of companies that are not ours are never stored (and never
queued as `m02_13f_issuer`); a manager's filer CIK is recorded in `refresh_state` as
`m07_manager:<cik>` and M02's views and review items skip those filers (`not_followed`,
D-M02-63).
"""

from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

from engine.financing import issuers
from engine.sec.client import SecClient, iso
from engine.sec.documents import IndexDoc, fetch_filing_index
from engine.sec.results import Failed, Ok

FORMS = ("13F-HR", "13F-HR/A")
DOLLARS_FROM = "2023-01-03"  # SEC: values rounded to the nearest dollar from this date
QUARTERS = 8  # first run: last 8 quarters (D-M02-45 (1))
DOC_TTL_S = 3650 * 86400  # filings are immutable
PRICE_TOLERANCE = 0.25
JUMP = 10
# A followed manager's filer CIK (M07, D-SEC-28): refresh_state name `m07_manager:<cik>`.
FOLLOWED_STATE = "m07_manager:"


def not_followed(column: str = "filer_cik") -> str:
    """SQL condition: the filer is not a followed manager (D-M02-63: M02's K1 edges, Money
    flow rows and review items skip the managers M07 follows)."""
    n = len(FOLLOWED_STATE)
    return (f"{column} NOT IN (SELECT substr(name, {n + 1}) FROM refresh_state WHERE "
            f"substr(name, 1, {n}) = '{FOLLOWED_STATE}')")  # fmt: skip


def followed_filers(engine: sqlite3.Connection) -> set[str]:
    n = len(FOLLOWED_STATE)
    return {
        r[0]
        for r in engine.execute(
            f"SELECT substr(name, {n + 1}) FROM refresh_state WHERE substr(name, 1, {n}) = ?",
            (FOLLOWED_STATE,),
        )
    }


# keep(row, issuer_cik, how) → None = not stored; else (issuer_cik, how, note) to store
Keep = Callable[["Row", "str | None", str], "tuple[str | None, str, str | None] | None"]


@dataclass(frozen=True)
class Row:
    issuer: str
    title: str
    cusip: str
    value: float  # dollars
    shares: float | None
    share_type: str | None
    put_call: str


@dataclass(frozen=True)
class Cover:
    period: str  # YYYY-MM-DD
    entries: int | None
    value_total: float | None  # as reported (unscaled)
    amend_type: str | None


@dataclass
class Report13F:
    read: int = 0
    rows: int = 0
    automatic: int = 0
    held: int = 0
    unresolved: int = 0
    re_resolved: int = 0
    problems: list[str] = field(default_factory=list)
    skipped: list[Row] = field(default_factory=list)  # rows a keep filter left out

    def lines(self) -> list[str]:
        out = [
            f"13F: {self.read} filing(s) read, {self.rows} holding(s): {self.automatic} "
            f"stored automatically, {self.held} held for a check, {self.unresolved} issuer(s) "
            "not resolved"
            + (f"; {self.re_resolved} earlier row(s) resolved now" if self.re_resolved else "")
        ]
        return out + [f"  problem: {p}" for p in self.problems]


def _strip(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _leaf(root: ET.Element, name: str) -> str | None:
    for el in root.iter():
        if _strip(el.tag) == name and len(el) == 0:
            return (el.text or "").strip() or None
    return None


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def parse_cover(xml: bytes) -> Cover:
    root = ET.fromstring(xml)
    period = _leaf(root, "periodOfReport") or _leaf(root, "reportCalendarOrQuarter")
    if period is None:
        raise ValueError("cover page has no period")
    mm, dd, yyyy = period.split("-")
    entries = _num(_leaf(root, "tableEntryTotal"))
    return Cover(
        f"{yyyy}-{mm}-{dd}",
        int(entries) if entries is not None else None,
        _num(_leaf(root, "tableValueTotal")),
        _leaf(root, "amendmentType")
        if (_leaf(root, "isAmendment") or "").lower() == "true"
        else None,
    )


def parse_table(xml: bytes, scale: int) -> list[Row]:
    """Information-table rows summed by CUSIP, title and put/call; values in dollars."""
    root = ET.fromstring(xml)
    acc: dict[tuple[str, str, str], dict] = {}
    for it in root:
        if _strip(it.tag) != "infoTable":
            continue
        f = {_strip(el.tag): (el.text or "").strip() for el in it.iter() if len(el) == 0}
        cusip = (f.get("cusip") or "").upper()
        key = (cusip, f.get("titleOfClass") or "", (f.get("putCall") or "").upper())
        a = acc.setdefault(
            key,
            {
                "issuer": f.get("nameOfIssuer") or cusip,
                "value": 0.0,
                "shares": 0.0,
                "type": f.get("sshPrnamtType"),
                "has_shares": False,
            },
        )
        a["value"] += (_num(f.get("value")) or 0.0) * scale
        if (n := _num(f.get("sshPrnamt"))) is not None:
            a["shares"] += n
            a["has_shares"] = True
    return [
        Row(
            a["issuer"],
            k[1],
            k[0],
            a["value"],
            a["shares"] if a["has_shares"] else None,
            a["type"],
            k[2],
        )
        for k, a in acc.items()
    ]


def scale_for(filed: str) -> int:
    return 1 if filed >= DOLLARS_FROM else 1000


def _xml(index: list[IndexDoc], doc_type: str) -> IndexDoc | None:
    return next(
        (
            d
            for d in index
            if (d.doc_type or "").upper() == doc_type
            and d.filename.lower().endswith(".xml")
            and "xsl" not in d.url.lower()
        ),
        None,
    )


def due(engine: sqlite3.Connection, cik: str, now: datetime) -> list[sqlite3.Row]:
    """13F filings of the last 8 quarters not read yet (failed reads retried), oldest first."""
    since = (now.date() - timedelta(days=92 * QUARTERS + 50)).isoformat()
    return engine.execute(
        "SELECT f.accession, f.form, f.filed FROM filing f JOIN filing_cik c ON c.accession = "
        "f.accession WHERE c.cik = ? AND f.form IN ('13F-HR', '13F-HR/A') AND f.filed >= ? "
        "AND f.accession NOT IN (SELECT accession FROM fin_13f WHERE status != 'failed') "
        "ORDER BY f.filed, f.accession",
        (cik, since),
    ).fetchall()


def filer_name(engine: sqlite3.Connection, cik: str) -> str:
    row = engine.execute("SELECT name FROM entity WHERE cik = ?", (cik,)).fetchone()
    return row[0] if row else cik


def read_filing(
    client: SecClient,
    engine: sqlite3.Connection,
    cik: str,
    f: sqlite3.Row,
    names: issuers.Names,
    now: datetime,
    rep: Report13F,
    keep: Keep | None = None,
) -> bool:
    """Read one filing → False when SEC throttled us (stop the batch). `keep` filters the
    rows before they are stored (followed managers, D-SEC-28)."""
    idx = fetch_filing_index(client, cik, f["accession"])
    if isinstance(idx, Failed) and idx.throttled:
        rep.problems.append(f"{f['accession']}: throttled")
        return False
    if not isinstance(idx, Ok):
        rep.problems.append(f"{f['accession']}: index {getattr(idx, 'reason', idx)}")
        _record(engine, cik, f, None, 1, "failed", "index unreadable", now)
        return True
    cover_doc, table_doc = _xml(idx.data, f["form"]), _xml(idx.data, "INFORMATION TABLE")
    if cover_doc is None:
        _record(engine, cik, f, None, 1, "no_table", "no XML cover page (paper or text)", now)
        return True
    cov = client.get_bytes(cover_doc.url, ttl_s=DOC_TTL_S)
    if not isinstance(cov, Ok):
        return _failed(engine, cik, f, cov, rep, now)
    try:
        cover = parse_cover(cov.data)
    except (ET.ParseError, ValueError) as e:
        _record(engine, cik, f, None, 1, "failed", f"cover unreadable: {e}", now)
        return True
    scale = scale_for(f["filed"])
    rows: list[Row] = []
    if table_doc is not None:
        tab = client.get_bytes(table_doc.url, ttl_s=DOC_TTL_S)
        if not isinstance(tab, Ok):
            return _failed(engine, cik, f, tab, rep, now)
        try:
            rows = parse_table(tab.data, scale)
        except ET.ParseError as e:
            _record(engine, cik, f, cover, scale, "failed", f"table unreadable: {e}", now)
            return True
    row_sum = sum(r.value for r in rows)
    total = cover.value_total * scale if cover.value_total is not None else None
    sum_ok = total is None or abs(row_sum - total) <= max(scale, 0.001 * total)
    _record(
        engine,
        cik,
        f,
        cover,
        scale,
        "read" if rows else "no_table",
        None if sum_ok else f"row sum {row_sum:,.0f} ≠ total {total:,.0f}",
        now,
        row_sum=row_sum,
    )
    rep.read += 1
    store_rows(engine, cik, f, cover, rows, names, now, rep, sum_ok, keep=keep)
    return True


def _failed(engine, cik, f, res, rep: Report13F, now) -> bool:
    if isinstance(res, Failed) and res.throttled:
        rep.problems.append(f"{f['accession']}: throttled")
        return False
    rep.problems.append(f"{f['accession']}: {getattr(res, 'reason', res)}")
    _record(engine, cik, f, None, 1, "failed", str(getattr(res, "reason", res)), now)
    return True


def _record(
    engine,
    cik,
    f,
    cover: Cover | None,
    scale: int,
    status: str,
    detail,
    now,
    row_sum: float | None = None,
) -> None:
    engine.execute(
        "INSERT INTO fin_13f (accession, filer_cik, form, period, filed, amend_type, scale, "
        "entries, value_total, row_sum, status, detail, read_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (accession) DO UPDATE SET "
        "status = excluded.status, detail = excluded.detail, read_at = excluded.read_at",
        (
            f["accession"],
            cik,
            f["form"],
            cover.period if cover else "",
            f["filed"],
            cover.amend_type if cover else None,
            scale,
            cover.entries if cover else None,
            cover.value_total * scale if cover and cover.value_total is not None else None,
            row_sum,
            status,
            detail,
            iso(now),
        ),
    )


def _close(engine: sqlite3.Connection, cik: str | None, period: str) -> float | None:
    """Closing price on the last trading day ≤ period end, for a company with stored bars."""
    if not cik:
        return None
    row = engine.execute(
        "SELECT b.close FROM price_bar b JOIN ticker t ON t.ticker = b.symbol AND "
        "t.valid_to IS NULL WHERE t.cik = ? AND b.date <= ? AND b.date >= ? "
        "ORDER BY b.date DESC LIMIT 1",
        (cik, period, (date.fromisoformat(period) - timedelta(days=7)).isoformat()),
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _prior_shares(
    engine, cik: str, cusip: str, period: str, put_call: str = "", issuer_cik: str | None = None
) -> float | None:
    """The prior quarter's shares of the same kind of row (a call row is not compared with
    the common shares, D-M07-19), scaled by the issuer's splits between the two quarters."""
    row = engine.execute(
        "SELECT shares, period FROM fin_holding WHERE source = '13F' AND filer_cik = ? AND "
        "cusip = ? AND put_call = ? AND period < ? AND status != 'wrong' ORDER BY period DESC "
        "LIMIT 1",
        (cik, cusip, put_call or "", period),
    ).fetchone()
    if not row or row[0] is None:
        return None
    if not issuer_cik:
        return float(row[0])
    from engine.financials.shares import splits_after

    before, _ = splits_after(engine, issuer_cik, row[1])
    after, _ = splits_after(engine, issuer_cik, period)
    return float(row[0]) * (before / after if after else 1.0)


def checks(engine, cik: str, row: Row, issuer_cik: str | None, period: str) -> list[str]:
    """Why a row is held (empty = passes)."""
    out = []
    price = None if row.put_call or row.share_type == "PRN" else _close(engine, issuer_cik, period)
    priced = False  # the value agrees with shares × close: the share count is confirmed
    if price and row.shares:
        implied = row.shares * price
        if implied and abs(row.value / implied - 1) > PRICE_TOLERANCE:
            out.append(
                f"value ${row.value:,.0f} vs shares × close ${implied:,.0f} (close ${price:,.2f})"
            )
        else:
            priced = bool(implied)
    prior = _prior_shares(engine, cik, row.cusip, period, row.put_call, issuer_cik)
    # a share jump alone does not hold a priced row (owner, M07 Part 2 live check 3, D-M02-46)
    if prior and row.shares and row.shares > JUMP * prior and not priced:
        out.insert(0, f"shares {row.shares:,.0f} > {JUMP}× the prior quarter's {prior:,.0f}")
    return out


def filer_thousands(engine, rows: list[tuple[Row, str | None]], period: str, scale: int) -> str:
    """A filing made after 2023-01-03 whose values are still thousands (Duquesne, M07 Part 2
    live check 1): every priced row of ours is about 1/1000 of shares × close. Returns the
    note (rows are then ×1000), or "" when the filing reads in dollars."""
    if scale != 1:
        return ""
    ratios = []
    for r, issuer_cik in rows:
        if r.put_call or r.share_type == "PRN" or not r.shares or not issuer_cik:
            continue
        price = _close(engine, issuer_cik, period)
        if price:
            ratios.append(r.value / (r.shares * price))
    if not ratios or any(abs(x * 1000 - 1) > PRICE_TOLERANCE for x in ratios):
        return ""
    return (f"values filed in thousands after {DOLLARS_FROM} (the filer's units: "
            f"{len(ratios)} priced row(s) ≈ 1/1000 of shares × close) — ×1000")  # fmt: skip


def _mark_thousands(engine: sqlite3.Connection, accession: str, note: str) -> None:
    engine.execute(
        "UPDATE fin_13f SET scale = 1000, value_total = value_total * 1000, row_sum = row_sum * "
        "1000, detail = CASE WHEN detail IS NULL THEN ? ELSE detail || '; ' || ? END WHERE "
        "accession = ?",
        (note, note, accession),
    )


def rescale_stored(engine: sqlite3.Connection) -> int:
    """Stored filings read as dollars whose rows are really thousands (`filer_thousands`):
    rows ×1000 and re-checked; 0 requests. Returns the number of filings rescaled."""
    n = 0
    for f in engine.execute(
        "SELECT accession, filer_cik, period, filed FROM fin_13f WHERE status = 'read' AND "
        "scale = 1 AND filed >= ?",
        (DOLLARS_FROM,),
    ).fetchall():
        hs = engine.execute(
            "SELECT * FROM fin_holding WHERE source = '13F' AND accession = ?", (f["accession"],)
        ).fetchall()
        rows = [(Row(h["issuer_name"], h["title"], h["cusip"], h["value_usd"], h["shares"],
                     h["share_type"], h["put_call"] or ""), h) for h in hs]  # fmt: skip
        note = filer_thousands(engine, [(r, h["issuer_cik"]) for r, h in rows], f["period"], 1)
        if not note:
            continue
        _mark_thousands(engine, f["accession"], note)
        for r, h in rows:
            r = replace(r, value=r.value * 1000)
            status, check = h["status"], h["check_note"]
            if status in ("held", "automatic"):
                notes = checks(engine, f["filer_cik"], r, h["issuer_cik"], f["period"])
                status = "held" if notes else "automatic"
                check = "; ".join(notes + [note])
            engine.execute(
                "UPDATE fin_holding SET value_usd = ?, status = ?, check_note = ? WHERE "
                "holding_id = ?",
                (r.value, status, check, h["holding_id"]),
            )
        n += 1
    return n


def recheck_followed(engine: sqlite3.Connection) -> int:
    """Followed managers' held rows re-run through `checks` (0 requests) after a check rule
    changed; a row that now passes becomes automatic, other notes are kept. M02 filers' held
    rows are left to their `m02_fin_check` review items. Returns the rows released."""
    n = 0
    for h in engine.execute(
        f"SELECT * FROM fin_holding WHERE source = '13F' AND status = 'held' AND issuer_cik IS "
        f"NOT NULL AND NOT ({not_followed()})"
    ).fetchall():
        note = h["check_note"] or ""
        if "do not add up" in note:
            continue  # a filing-level problem, not a row check
        r = Row(h["issuer_name"], h["title"], h["cusip"], h["value_usd"], h["shares"],
                h["share_type"], h["put_call"] or "")  # fmt: skip
        notes = checks(engine, h["filer_cik"], r, h["issuer_cik"], h["period"])
        if notes:
            continue
        kept = [x for x in note.split("; ") if x.startswith("values filed in thousands")]
        engine.execute(
            "UPDATE fin_holding SET status = 'automatic', check_note = ? WHERE holding_id = ?",
            ("; ".join(kept) or None, h["holding_id"]),
        )
        n += 1
    return n


def suppressed(engine: sqlite3.Connection, key: str) -> bool:
    return engine.execute("SELECT 1 FROM fin_suppress WHERE key = ?", (key,)).fetchone() is not None


def store_rows(
    engine: sqlite3.Connection,
    cik: str,
    f: sqlite3.Row,
    cover: Cover,
    rows: list[Row],
    names: issuers.Names,
    now: datetime,
    rep: Report13F,
    sum_ok: bool = True,
    *,
    keep: Keep | None = None,
) -> None:
    fname = filer_name(engine, cik)
    todo = []
    for r in rows:
        issuer_cik, how = issuers.resolve(engine, names, r.cusip, r.issuer)
        extra = None
        if keep is not None:
            kept = keep(r, issuer_cik, how)
            if kept is None:
                rep.skipped.append(r)
                continue
            issuer_cik, how, extra = kept
        todo.append((r, issuer_cik, how, extra))
    units = filer_thousands(engine, [(r, c) for r, c, _, _ in todo], cover.period,
                            scale_for(f["filed"]))  # fmt: skip
    if units:
        todo = [(replace(r, value=r.value * 1000), c, h, e) for r, c, h, e in todo]
        _mark_thousands(engine, f["accession"], units)
    for r, issuer_cik, how, extra in todo:
        notes = [] if sum_ok else ["the filing's rows do not add up to its stated total"]
        if extra and issuer_cik is None:
            notes.append(extra)  # unresolved: why it was kept (shown with the CUSIP)
        notes += checks(engine, cik, r, issuer_cik, cover.period)
        if suppressed(engine, f"13F:{cik}:{r.cusip[:6]}"):
            status = "wrong"
        elif issuer_cik is None:
            status = "dismissed" if how == "dismissed" else "unresolved"
        elif notes:
            status = "held"
        else:
            status = "automatic"
        cur = engine.execute(
            "INSERT OR IGNORE INTO fin_holding (source, accession, filer_cik, filer_name, "
            "issuer_cik, issuer_name, cusip, title, put_call, shares, share_type, value_usd, "
            "period, filed, resolved_how, status, check_note, discovered_at) "
            "VALUES ('13F', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f["accession"],
                cik,
                fname,
                issuer_cik,
                r.issuer,
                r.cusip,
                r.title,
                r.put_call,
                r.shares,
                r.share_type,
                r.value,
                cover.period,
                f["filed"],
                how,  # unresolved rows keep the reason (ambiguous (n) | no match)
                status,
                "; ".join(notes + ([units] if units else [])) or None,
                iso(now),
            ),
        )
        if not cur.rowcount:
            continue
        rep.rows += 1
        rep.automatic += status == "automatic"
        rep.held += status == "held"
        rep.unresolved += status == "unresolved"


def current(engine: sqlite3.Connection, filer_cik: str) -> dict[str, list[sqlite3.Row]]:
    """Holdings per period as the filer last stated them: the latest original or
    restatement, plus NEW HOLDINGS amendments filed after it. {period: rows}."""
    by_period: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for f in engine.execute(
        "SELECT * FROM fin_13f WHERE filer_cik = ? AND status = 'read' ORDER BY period, filed",
        (filer_cik,),
    ):
        by_period[f["period"]].append(f)
    out: dict[str, list[sqlite3.Row]] = {}
    for period, fs in by_period.items():
        base = [x for x in fs if x["amend_type"] in (None, "RESTATEMENT")]
        if not base:
            continue
        b = base[-1]
        accs = [b["accession"]] + [
            x["accession"]
            for x in fs
            if x["amend_type"] == "NEW HOLDINGS" and x["filed"] >= b["filed"]
        ]
        marks = ",".join("?" * len(accs))
        out[period] = engine.execute(
            f"SELECT * FROM fin_holding WHERE source = '13F' AND accession IN ({marks}) "
            "ORDER BY value_usd DESC",
            accs,
        ).fetchall()
    return out


def run(
    client: SecClient | None,
    engine: sqlite3.Connection,
    ciks: list[str],
    now: datetime,
    rep: Report13F,
) -> None:
    names = issuers.Names(engine)
    rep.re_resolved = re_resolve_all(engine, names)
    for cik in ciks:
        for f in due(engine, cik, now):
            if client is None:
                break
            if not read_filing(client, engine, cik, f, names, now, rep):
                return


def re_resolve(engine: sqlite3.Connection, cusip6: str, now: datetime) -> int:
    """After an owner mapping: unresolved rows of that issuer take the mapped company."""
    m = issuers.mapped(engine, cusip6)
    if m is None:
        return 0
    rows = engine.execute(
        "SELECT * FROM fin_holding WHERE substr(cusip, 1, 6) = ? AND status = 'unresolved'",
        (cusip6.upper(),),
    ).fetchall()
    for r in rows:
        if m["cik"] is None:
            engine.execute(
                "UPDATE fin_holding SET status = 'dismissed' WHERE holding_id = ?",
                (r["holding_id"],),
            )
            continue
        row = Row(
            r["issuer_name"],
            r["title"],
            r["cusip"],
            float(r["value_usd"] or 0),
            float(r["shares"]) if r["shares"] is not None else None,
            r["share_type"],
            r["put_call"],
        )
        notes = (
            checks(engine, r["filer_cik"], row, m["cik"], r["period"])
            if r["source"] == "13F"
            else []
        )
        engine.execute(
            "UPDATE fin_holding SET issuer_cik = ?, resolved_how = 'owner', status = ?, "
            "check_note = ? WHERE holding_id = ?",
            (m["cik"], "held" if notes else "automatic", "; ".join(notes) or None, r["holding_id"]),
        )
    return len(rows)


def re_resolve_all(engine: sqlite3.Connection, names: issuers.Names) -> int:
    """Unresolved rows tried again with the current issuer rules and maps (each run)."""
    n = 0
    for r in engine.execute(
        "SELECT * FROM fin_holding WHERE source = '13F' AND status = 'unresolved'"
    ).fetchall():
        cik, how = issuers.resolve(engine, names, r["cusip"], r["issuer_name"])
        if cik is None:
            if how != r["resolved_how"]:
                engine.execute(
                    "UPDATE fin_holding SET resolved_how = ?, status = ? WHERE holding_id = ?",
                    (how, "dismissed" if how == "dismissed" else "unresolved", r["holding_id"]),
                )
            continue
        row = Row(
            r["issuer_name"],
            r["title"],
            r["cusip"],
            float(r["value_usd"] or 0),
            float(r["shares"]) if r["shares"] is not None else None,
            r["share_type"],
            r["put_call"],
        )
        notes = checks(engine, r["filer_cik"], row, cik, r["period"])
        engine.execute(
            "UPDATE fin_holding SET issuer_cik = ?, resolved_how = ?, status = ?, check_note = ? "
            "WHERE holding_id = ?",
            (cik, how, "held" if notes else "automatic", "; ".join(notes) or None,
             r["holding_id"]),
        )  # fmt: skip
        n += 1
    return n
