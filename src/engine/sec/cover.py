"""R1 cover reader: class-summed cover share counts (D-M04-2; M04 Part 1a).

Multi-class filers (GOOG, META, MSTR, SPCX) report `dei:EntityCommonStockSharesOutstanding`
per class only, on a dimension, so companyfacts (no dimensional facts) has no cover count.
EDGAR renders each XBRL filing as R pages; R1 is normally the cover ("Cover",
"Document and Entity Information"). This module fetches R1 (one request; `R1.xml` for old
filings rendered without HTML), reads every "Entity Common Stock, Shares Outstanding"
value with its class and the cover date, sums the classes, and keeps
`DocumentFinStmtErrorCorrectionFlag` (Part 3 reuses it).

Two layouts exist: classes as row groups (a member row, then the share row) and classes
as column headers; both are read. An R1 page that is not a cover (Google Inc. Q2 2009: the
balance sheet) is recorded as `not_cover`; consumers then fall back to basic weighted
average shares, labelled (`financials/shares.py`). Raw counts are stored as filed; splits
are applied when read (split guard: MSTR's 2011 counts predate its 2024 10-for-1 split).
"""

from __future__ import annotations

import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser

from engine.sec.client import SecClient, iso
from engine.sec.documents import filing_folder
from engine.sec.results import Failed, NotFound, Ok, Result

R_PAGE_TTL_S = 3650 * 86400  # filings are immutable
SHARES_LABEL = "entity common stock, shares outstanding"
FLAG_LABEL = "document fin stmt error correction"
COVER_LABELS = ("document type", "entity registrant name", "entity central index key",
                SHARES_LABEL)  # fmt: skip
_MONTHS = {
    m: i
    for i, m in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1
    )
}
_DATE = re.compile(r"\b([A-Z][a-z]{2})[a-z]*\.? (\d{1,2}), (\d{4})\b")
_SCALE = re.compile(r"shares in (thousands|millions|billions)", re.IGNORECASE)
_FOOTNOTE = re.compile(r"\[\d+\]")
_MEMBER_WORDS = re.compile(r"\[member\]|\bclass\b|common|ordinary|stock|shares|series",
                           re.IGNORECASE)  # fmt: skip
_STRUCTURE = re.compile(r"\[(abstract|axis|table|line items|domain)\]", re.IGNORECASE)


@dataclass
class RPage:
    title: str
    columns: list[list[str]]  # per value column: its header labels, top to bottom
    rows: list[tuple[str, list[str], bool]]  # (label, cells, member-row flag)


@dataclass
class CoverRead:
    is_cover: bool
    title: str
    cover_date: str | None = None
    classes: list[tuple[str, float]] = field(default_factory=list)  # (class label, shares)
    error_correction_flag: bool | None = None
    document_type: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> float | None:
        return sum(v for _, v in self.classes) if self.classes else None


# --- Parsing ---------------------------------------------------------------------------


class _TableParser(HTMLParser):
    """Rows of the first `table.report` (cells: tag, class, colspan, rowspan, text)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0  # nesting inside the report table
        self.done = False
        self.rows: list[tuple[str, list[tuple[str, str, int, int, str]]]] = []
        self._row: list[tuple[str, str, int, int, str]] | None = None
        self._row_class = ""
        self._cell: list[str] | None = None
        self._cell_attrs: tuple[str, str, int, int] = ("td", "", 1, 1)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "table":
            if self.depth:
                self.depth += 1
            elif not self.done and "report" in a.get("class", "").split():
                self.depth = 1
            return
        if self.depth != 1:
            return
        if tag == "tr":
            self._row, self._row_class = [], a.get("class", "")
        elif tag in ("td", "th") and self._row is not None:
            span = int(a.get("colspan") or 1) if (a.get("colspan") or "1").isdigit() else 1
            rspan = int(a.get("rowspan") or 1) if (a.get("rowspan") or "1").isdigit() else 1
            self._cell, self._cell_attrs = [], (tag, a.get("class", ""), span, rspan)
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if not self.depth:
            return
        if tag == "table":
            self.depth -= 1
            if not self.depth:
                self.done = True
            return
        if self.depth != 1:
            return
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            text = " ".join("".join(self._cell).split())
            self._row.append((*self._cell_attrs, text))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append((self._row_class, self._row))
            self._row = None

    def handle_data(self, data: str) -> None:
        if self.depth == 1 and self._cell is not None:
            self._cell.append(data)


def parse_r_html(html: str) -> RPage:
    p = _TableParser()
    p.feed(html)
    title, headers, body = "", [], []
    for row_class, cells in p.rows:
        if cells and all(c[0] == "th" for c in cells):
            if not headers and cells[0][1] == "tl":
                title = cells[0][4]
                cells = cells[1:]
            expanded = [c[4] for c in cells for _ in range(c[2])]
            headers.append(expanded)
            continue
        if not cells:
            continue
        label = cells[0][4]
        values = [c[4] for c in cells[1:] for _ in range(c[2])]
        member = "rh" in row_class.split() or (
            not any(v.strip() for v in values)
            and bool(_MEMBER_WORDS.search(label))
            and not _STRUCTURE.search(label)
            and not _norm(label).startswith(("entity ", "document ", "security "))
        )
        body.append((label, values, member))
    n = max((len(v) for _, v, _ in body), default=0)
    columns = [[h[j] for h in headers if j < len(h) and h[j]] for j in range(n)]
    return RPage(title, columns, body)


def parse_r_xml(data: bytes) -> RPage:
    """Old XML-rendered R pages (`R1.xml`): columns with labels, rows with cells by id."""
    root = ET.fromstring(data)
    title = (root.findtext("ReportName") or "").strip()
    col_ids, columns = [], []
    for col in root.iter("Column"):
        col_ids.append((col.findtext("Id") or "").strip())
        labels = [lb.get("Label", "").strip() for lb in col.iter("Label")]
        columns.append([x for x in labels if x])
    body = []
    for row in root.iter("Row"):
        label = (row.findtext("Label") or "").strip()
        cells = {(c.findtext("Id") or "").strip(): c for c in row.iter("Cell")}
        values = []
        for cid in col_ids:
            c = cells.get(cid)
            if c is None:
                values.append("")
            elif (c.findtext("IsNumeric") or "").strip().lower() == "true":
                values.append((c.findtext("NumericAmount") or "").strip())
            else:
                values.append((c.findtext("NonNumbericText") or c.findtext("NonNumericText")
                               or "").strip())  # fmt: skip
        abstract = (row.findtext("IsAbstractGroupTitle") or "").strip().lower() == "true"
        member = abstract and bool(_MEMBER_WORDS.search(label)) and not _STRUCTURE.search(label)
        body.append((label, values, member))
    return RPage(title, columns, body)


def _date(text: str) -> str | None:
    m = _DATE.search(text)
    if not m or m.group(1).lower()[:3] not in _MONTHS:
        return None
    try:
        return date(int(m.group(3)), _MONTHS[m.group(1).lower()[:3]], int(m.group(2))).isoformat()
    except ValueError:
        return None


def _number(text: str) -> float | None:
    t = _FOOTNOTE.sub("", text).replace("$", "").replace(",", "").strip()
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").strip()
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _clean_class(label: str) -> str:
    """Class label as filed; a member label that names the class but not the stock
    (Alphabet's "Class C share repurchases") is cut to the class (e.g. "Class C")."""
    text = " ".join(_FOOTNOTE.sub("", label).replace("[Member]", "").split())
    m = _CLASS_NAME.search(text)
    if m and not _STOCK_WORDS.search(text):
        return m.group(0)
    return text


_CLASS_NAME = re.compile(r"Class [A-Z]")
_STOCK_WORDS = re.compile(r"(stock|common|capital|ordinary)", re.I)


def _norm(label: str) -> str:
    return " ".join(_FOOTNOTE.sub("", label).lower().split())


def read_cover(page: RPage) -> CoverRead:
    """Cover facts from a parsed R page; `is_cover` False when it is another statement."""
    labels = [_norm(lb) for lb, _, _ in page.rows]
    if not any(lb.startswith(c) for lb in labels for c in COVER_LABELS):
        return CoverRead(False, page.title, notes=["R1 is not a cover page"])
    scale = 1.0
    if m := _SCALE.search(page.title):
        scale = {"thousands": 1e3, "millions": 1e6, "billions": 1e9}[m.group(1).lower()]
    out = CoverRead(True, page.title)
    col_dates = [next((d for x in col if (d := _date(x))), None) for col in page.columns]
    col_members = [
        _clean_class(" ".join(_DATE.sub("", x) for x in col if "ended" not in x.lower()))
        for col in page.columns
    ]
    member = ""
    found: list[tuple[str, str | None, float]] = []
    for label, values, is_member in page.rows:
        key = _norm(label)
        if is_member:
            member = _clean_class(label)
            continue
        if key.startswith("document type") and out.document_type is None:
            out.document_type = next((v for v in values if v.strip()), None)
        elif key.startswith(FLAG_LABEL):
            flag = next((v.strip().lower() for v in values if v.strip()), "")
            out.error_correction_flag = {"true": True, "false": False}.get(flag)
        elif key.startswith(SHARES_LABEL):
            for j, v in enumerate(values):
                n = _number(v) if v.strip() else None
                if n is None:
                    continue
                cls = member or (col_members[j] if j < len(col_members) else "")
                found.append((cls, col_dates[j] if j < len(col_dates) else None, n * scale))
    if not found:
        out.notes.append("cover page without a share count")
        return out
    dates = sorted({d for _, d, _ in found if d})
    out.cover_date = dates[-1] if dates else None
    if len(dates) > 1:
        out.notes.append(f"share counts on several dates {', '.join(dates)}; latest kept")
    seen: dict[str, float] = {}
    for cls, d, n in found:
        if d == out.cover_date or d is None:
            if cls in seen and seen[cls] != n:
                out.notes.append(
                    f"class {cls or '(none)'} listed twice: {seen[cls]:,.0f}, {n:,.0f}"
                )
                continue
            seen[cls] = n
    out.classes = list(seen.items())
    return out


# --- Fetch and store ---------------------------------------------------------------------


def r1_urls(cik: str, accession: str) -> tuple[str, str]:
    folder = filing_folder(cik, accession)
    return f"{folder}/R1.htm", f"{folder}/R1.xml"


def _state(accession: str) -> str:
    return f"r1:{accession}"


def r1_done(engine: sqlite3.Connection, accession: str) -> bool:
    return (
        engine.execute(
            "SELECT 1 FROM refresh_state WHERE name = ?", (_state(accession),)
        ).fetchone()
        is not None
    )


def fetch_cover(
    client: SecClient, engine: sqlite3.Connection, cik: str, filing: sqlite3.Row | dict,
    now: datetime,
) -> Result[CoverRead]:  # fmt: skip
    """Fetch and store one filing's R1 cover (`filing`: accession, form, filed).

    One request (two when only an XML rendering exists). Stores the class rows and the
    outcome (`refresh_state` r1:<accession>), so a filing is read once."""
    accession = filing["accession"]
    url = None
    read: CoverRead | None = None
    for candidate in r1_urls(cik, accession):
        res = client.get_bytes(candidate, ttl_s=R_PAGE_TTL_S)
        if isinstance(res, NotFound):
            continue
        if not isinstance(res, Ok):
            return res  # failure or throttle: left pending for the next run
        url = candidate
        try:
            page = (parse_r_xml(res.data) if candidate.endswith(".xml")
                    else parse_r_html(res.data.decode("utf-8", errors="replace")))  # fmt: skip
        except (ET.ParseError, ValueError) as exc:
            return Failed(f"R1 page unreadable: {exc}", url=candidate)
        read = read_cover(page)
        break
    outcome = "not_found" if read is None else ("cover" if read.is_cover else "not_cover")
    store_cover(engine, cik, filing, read, url or r1_urls(cik, accession)[0], outcome, now)
    if read is None:
        return NotFound(r1_urls(cik, accession)[0])
    return Ok(read, source_ref=url or "", fetched_at=iso(now))


def store_cover(
    engine: sqlite3.Connection, cik: str, filing: sqlite3.Row | dict, read: CoverRead | None,
    url: str, outcome: str, now: datetime,
) -> None:  # fmt: skip
    detail = {"outcome": outcome, "url": url}
    if read is not None:
        detail |= {"title": read.title, "cover_date": read.cover_date, "notes": read.notes,
                   "classes": len(read.classes), "document_type": read.document_type}  # fmt: skip
    flag = None if read is None or read.error_correction_flag is None else int(
        read.error_correction_flag)  # fmt: skip
    engine.execute("BEGIN")
    try:
        engine.execute("DELETE FROM cover_shares WHERE accession = ?", (filing["accession"],))
        if read is not None and read.is_cover and read.cover_date:
            engine.executemany(
                "INSERT INTO cover_shares (accession, cik, class_label, shares, cover_date, "
                "error_correction_flag, form, filed, source_url, read_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(filing["accession"], cik, cls, n, read.cover_date, flag, filing["form"],
                  filing["filed"], url, iso(now)) for cls, n in read.classes],
            )  # fmt: skip
        engine.execute(
            "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (name) DO UPDATE SET source_ref = excluded.source_ref, "
            "fetched_at = excluded.fetched_at, detail = excluded.detail",
            (_state(filing["accession"]), url, iso(now), json.dumps(detail)),
        )
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise


def r1_outcome(engine: sqlite3.Connection, accession: str) -> dict | None:
    row = engine.execute(
        "SELECT detail FROM refresh_state WHERE name = ?", (_state(accession),)
    ).fetchone()
    return json.loads(row["detail"]) if row and row["detail"] else None
