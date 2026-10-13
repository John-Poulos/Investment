"""Unit KPIs and credits (M04 Part 7a; D-M04-42, S5.5–S5.7; DS2, DS14).

Read from stored text only (0 requests): earnings-release exhibits (EX-99.1, EX-99.2) and
10-K/10-Q text in the corpus.

- **Tesla DS2 extractor:** the quarterly Update's operational summary (rows "Model 3/Y
  production", "Other models deliveries", "Total deliveries", "Storage deployed (MWh)" under
  a header of quarter labels Q4-2022 … Q4-2023, so each release carries the prior quarter
  and the quarter a year ago) and the production-and-deliveries release table ("Model 3/Y
  | production | deliveries"). The financial summary's "Automotive regulatory credits" row
  is stored as a **credit**, never netted into a KPI (S5.5). Both tables are read as a
  token stream, so a row split one cell per line (filer HTML with a <div> per cell) reads
  like a tab-separated one (live check 1).
- **Sentences** (any company): "produced N vehicles … and delivered M vehicles", "delivered
  N vehicles/airplanes", "billable volume of N" with a stated period ("fourth quarter of
  2025", "in 2024"). A figure with "approximately"/"over" is stored as stated, marked.
- Contribution margins are stored only when a company states them (kind `non_gaap`); this
  module never computes one (S5.8).

Each row keeps its period label as stated, the mapped dates, the verbatim row or sentence,
the accession and the extractor. Category breaks (a new model line, a renamed category)
open an `m04_unit_kpi` review item; series are never merged across a break (D-M04-42).
"""

from __future__ import annotations

import calendar
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from engine.sec.client import iso

EXTRACTOR_TABLE = "tesla-ds2-2"
EXTRACTOR_PD = "pd-table-2"
EXTRACTOR_SENTENCE = "sentence-2"
# bump to re-scan stored documents; a re-scan replaces the document's rows from these
# extractors (any version), so a fixed extractor also drops its own earlier misreads
SCAN_VERSION = "units-2"
EXTRACTOR_FAMILIES = ("tesla-ds2-%", "pd-table-%", "sentence-%")
SCAN_TYPES = ("EX-99.1", "EX-99.2", "10-K", "10-Q", "20-F")

QUARTER_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4}
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}


@dataclass(frozen=True)
class Metric:
    metric: str
    line: str
    period_label: str
    start: str | None
    end: str
    value: float
    unit: str
    kind: str  # kpi | credit | non_gaap
    basis: str
    quote: str
    extractor: str


# --- Periods ---------------------------------------------------------------------------------


def _month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def quarter_dates(q: int, fy: int, fye: str | None = "1231") -> tuple[str, str]:
    """Start and end of fiscal quarter q of fiscal year fy (fiscal year named by its end
    year; month ends, so a 52/53-week year is off by a few days, labelled as stated)."""
    m_end = int((fye or "1231")[:2])
    end_month = m_end - 3 * (4 - q)
    year = fy
    while end_month <= 0:
        end_month += 12
        year -= 1
    end = _month_end(year, end_month)
    sm, sy = end_month - 2, year
    if sm <= 0:
        sm, sy = sm + 12, sy - 1
    return date(sy, sm, 1).isoformat(), end.isoformat()


def year_dates(fy: int, fye: str | None = "1231") -> tuple[str, str]:
    m_end = int((fye or "1231")[:2])
    end = _month_end(fy, m_end)
    sm, sy = m_end + 1, fy - 1
    if sm > 12:
        sm, sy = 1, fy
    return date(sy, sm, 1).isoformat(), end.isoformat()


def fiscal_year_end(engine: sqlite3.Connection, cik: str) -> str:
    row = engine.execute("SELECT fiscal_year_end FROM entity WHERE cik = ?", (cik,)).fetchone()
    return (row[0] if row and row[0] else None) or "1231"


# --- Numbers and cells ---------------------------------------------------------------------

_NUM = re.compile(r"^\(?-?\$?\s?[\d,]*\.?\d+\)?$")


def number(cell: str) -> float | None:
    """'419,088' → 419088; '(1,234)' → −1234; '$' or '12%' → None."""
    c = cell.strip().replace("−", "-")
    if not c or c.endswith("%") or not _NUM.match(c):
        return None
    neg = c.startswith("(") and c.endswith(")")
    c = c.strip("()").replace("$", "").replace(",", "").strip()
    try:
        v = float(c)
    except ValueError:
        return None
    return -v if neg else v


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.split("\t") if c.strip() and c.strip() != "$"]


# --- Tesla operational summary (quarter-label header) --------------------------------------

_QLABEL = re.compile(r"^Q([1-4])\s*[-–']?\s*(\d{4}|\d{2})$")
_ROW = re.compile(
    r"^(?P<line>model [^\t]+?|other models|total)\s+(?P<what>production|deliveries)$", re.I
)
_STORAGE = re.compile(r"^(?:energy\s+)?storage deployed\s*\((?P<unit>mwh|gwh)\)$", re.I)
_CREDITS = re.compile(r"regulatory credits", re.I)


def _qlabel(cell: str) -> tuple[int, int] | None:
    m = _QLABEL.match(cell.strip())
    if not m:
        return None
    y = int(m.group(2))
    return int(m.group(1)), (y + 2000 if y < 100 else y)


def _line_name(raw: str) -> str:
    low = raw.strip().lower()
    if low == "total":
        return ""
    if low == "other models":
        return "Other models"
    return raw.strip()[0].upper() + raw.strip()[1:]


def _scale(text: str) -> float:
    head = text.lower()
    if "in millions" in head:
        return 1e6
    if "in thousands" in head:
        return 1e3
    return 1.0


def tokens(text: str) -> list[str]:
    """Every non-empty table cell or text line in reading order. Filer HTML often wraps each
    cell's text in its own <div>/<p> (Workiva, Tesla's Update), so the stored text puts each
    cell on its own line; a token stream reads both layouts the same way."""
    out = []
    for line in text.split("\n"):
        out += cells(line)
    return out


_GAP = {"—", "–", "-", "n/a", "N/A", "NM", "nm", "*"}  # a column with no figure


def _values(toks: list[str], i: int, n: int) -> tuple[list[float | None], list[str], int] | None:
    """The n column values after token i (values, their tokens, the next token's index):
    numbers or dashes, skipping lone '%' and '$' tokens and footnote marks; None when the
    row has fewer than n values."""
    vals: list[float | None] = []
    raw: list[str] = []
    j = i + 1
    while j < len(toks) and len(vals) < n:
        t = toks[j].strip()
        j += 1
        if t in ("%", "$", ")", "("):
            continue
        if re.fullmatch(r"\(\d\)|\[\d\]", t) and not vals:
            continue  # footnote mark after the label
        if t in _GAP:
            vals.append(None)
        elif t.endswith("%") and number(t[:-1]) is not None:
            vals.append(None)  # a percentage column (YoY, lease share): not a count
        else:
            v = number(t)
            if v is None:
                return None
            vals.append(v)
        raw.append(t)
    while j < len(toks) and toks[j].strip() == "%":
        j += 1  # the last column's own '%' cell
    return (vals, raw, j) if len(vals) == n else None


def _clean_label(t: str) -> str:
    return re.sub(r"\s*(?:\(\d\))+\s*$", "", t.strip())


def quarter_table(text: str, fye: str | None = "1231") -> list[Metric]:
    """Rows under a header of quarter labels (Tesla's Update): production and deliveries by
    model line, storage deployed, and regulatory-credit revenue (kept as a credit). Reads
    tab-separated rows and one-cell-per-line tables alike (see `tokens`)."""
    out: list[Metric] = []
    toks = tokens(text)
    cols: list[tuple[int, int]] | None = None
    money_scale = _scale(text)
    i = 0
    while i < len(toks):
        run = []
        while i + len(run) < len(toks) and _qlabel(toks[i + len(run)]):
            run.append(_qlabel(toks[i + len(run)]))
        if len(run) >= 3:
            cols = run
            i += len(run)
            continue
        label = _clean_label(toks[i])
        if cols is None:
            i += 1
            continue
        m, s = _ROW.match(label), _STORAGE.match(label)
        cr = _CREDITS.search(label) if len(label) <= 60 else None
        if not (m or s or cr) or number(label) is not None:
            i += 1
            continue
        got = _values(toks, i, len(cols))
        if got is None:
            i += 1
            continue
        vals, raw, _ = got
        quote = "\t".join([toks[i], *raw])
        if m:
            metric = m.group("what").lower()
            line, unit, kind, scale = _line_name(m.group("line")), "vehicles", "kpi", 1.0
        elif s:
            metric, line, unit, kind, scale = (
                "storage_deployed",
                "",
                s.group("unit").upper().replace("WH", "Wh"),
                "kpi",
                1.0,
            )
        else:
            metric, line, unit, kind, scale = "regulatory_credits", "", "USD", "credit", money_scale
        i += 1
        for (q, y), v in zip(cols, vals, strict=False):
            if v is None:
                continue
            start, end = quarter_dates(q, y, fye)
            out.append(
                Metric(
                    metric,
                    line,
                    f"Q{q}-{y}",
                    start,
                    end,
                    v * scale,
                    unit,
                    kind,
                    "stated",
                    quote,
                    EXTRACTOR_TABLE,
                )
            )
    return out


# --- Production-and-deliveries release table -----------------------------------------------

_QTEXT = re.compile(r"\bQ([1-4])\s+(\d{4})\b")
_PD_LINE = re.compile(r"^(model [^\t]+|other models|total)$", re.I)


def pd_table(text: str, fye: str | None = "1231") -> list[Metric]:
    """'Q4 2023 | Production | Deliveries' tables: one quarter, by model line."""
    out: list[Metric] = []
    toks = tokens(text)
    low = [t.lower() for t in toks]
    for i, t in enumerate(low):
        if t != "production" or "deliveries" not in low[i + 1 : i + 3]:
            continue
        ctx = " ".join(toks[max(0, i - 4) : i])
        q = _QTEXT.search(ctx)
        if not q:
            continue
        qn, y = int(q.group(1)), int(q.group(2))
        start, end = quarter_dates(qn, y, fye)
        # header = the column names after the quarter label, up to the first row label
        head = []
        j = i
        while j < len(toks) and not _PD_LINE.match(toks[j]) and len(head) < 8:
            head.append(low[j])
            j += 1
        p_i, d_i = head.index("production"), head.index("deliveries")
        rows_seen = 0
        while j < len(toks) and rows_seen < 6:
            if not _PD_LINE.match(toks[j]):
                break
            got = _values(toks, j, len(head))
            if got is None:
                break
            vals, raw, nxt = got
            line = _line_name(toks[j])
            rc = [toks[j], *raw]
            j = nxt
            rows_seen += 1
            for metric, k in (("production", p_i), ("deliveries", d_i)):
                v = vals[k]
                if v is not None:
                    out.append(
                        Metric(
                            metric,
                            line,
                            f"Q{qn}-{y}",
                            start,
                            end,
                            v,
                            "vehicles",
                            "kpi",
                            "stated",
                            "\t".join(rc),
                            EXTRACTOR_PD,
                        )
                    )
    return out


# --- Sentences -----------------------------------------------------------------------------

_AMT = (
    r"(?P<q{n}>approximately |about |over |more than |nearly )?"
    r"(?P<n{n}>\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?)(?!,?\d)(?!\s?%)(?P<m{n}> million)?"
)
# Tesla's 10-K/10-Q say "consumer vehicles" (live check 1, 2026-10-12)
_VEH = r"(?:consumer |electric |commercial |total )?(?P<u{n}>vehicles)"
_PROD_DELIV = re.compile(
    r"produced "
    + _AMT.format(n=1)
    + r"(?: (?:consumer |electric |commercial |total )?vehicles)?[^.]{0,80}?\bdelivered "
    + _AMT.format(n=2)
    + " "
    + _VEH.format(n=2),
    re.I,
)
_DELIV = re.compile(
    r"\bdelivered "
    + _AMT.format(n=1)
    + r" (?:consumer |electric |commercial |total )?(?P<u1>vehicles|airplanes|aircraft)\b",
    re.I,
)
_PROD = re.compile(r"\bproduced " + _AMT.format(n=1) + " " + _VEH.format(n=1) + r"\b", re.I)
# Billable volume: the number must be attached to the phrase ("billable volume of N",
# "billable volume in 2021 grew 71% to N", "N billable tests"); a year in between is the
# period, never the count (live check 1: "2,021" from "billable volume in 2021 …").
_BILL_PERIOD = (
    r"(?:,?\s+(?:in|for|during)\s+(?:the\s+)?(?:(?:first|second|third|fourth)\s+quarter"
    r"(?:\s+of)?\s+|full[- ]year\s+|fiscal(?:\s+year)?\s+)?\d{4},?)?"
)
_BILL_LINK = (
    r"(?:\s+(?:of|was|were|totaled|totalled|reached|grew|increased|rose|to|\d+(?:\.\d+)?%))*"
)
_BILLABLE = re.compile(
    r"billable (?:volume|units|tests|samples)"
    + _BILL_PERIOD
    + _BILL_LINK
    + r"\s+"
    + _AMT.format(n=1),
    re.I,
)
_BILLABLE_REV = re.compile(_AMT.format(n=1) + r"\s+billable (?:tests|units|samples)\b", re.I)
_PER_Q = re.compile(
    r"\b(first|second|third|fourth) quarter(?: of)?(?: fiscal)?(?: year)? (\d{4})\b", re.I
)
_PER_Q_ENDED = re.compile(r"(?:quarter|three months) ended (\w+) (\d{1,2}), (\d{4})", re.I)
_PER_YTD = re.compile(r"\b(?:six|nine) months ended \w+ \d{1,2}, \d{4}", re.I)
_PER_Y = re.compile(
    r"\b(?:full[- ]year|fiscal(?: year)?|year ended \w+ \d{1,2},|for the year|in|during|for)"
    r" (\d{4})\b",
    re.I,
)
_YEAR_WORD = re.compile(
    r"\b(?:quarter|year|fiscal|fy|in|during|for|ended|since|through|of|from)\s*$", re.I
)


def _sentences(text: str) -> Iterable[str]:
    for para in text.split("\n"):
        para = " ".join(para.replace("\t", " ").split())
        if not para:
            continue
        yield from re.split(r"(?<=[.;])\s+(?=[A-Z•])", para)


Period = tuple[str, str | None, str]


def _periods(s: str, fye: str | None) -> list[tuple[int, int, int, Period | None]]:
    """Every period a sentence names: (start, end, rank, (label, start, end)); a year-to-date
    span ("six months ended …") is listed with None so a figure next to it is skipped."""
    out: list[tuple[int, int, int, Period | None]] = []
    for m in _PER_Q.finditer(s):
        q, y = QUARTER_WORDS[m.group(1).lower()], int(m.group(2))
        start, end = quarter_dates(q, y, fye)
        out.append((m.start(), m.end(), 0, (f"Q{q}-{y}", start, end)))
    for m in _PER_Q_ENDED.finditer(s):
        mon = MONTHS.get(m.group(1).lower())
        if mon:
            end_d = _month_end(int(m.group(3)), mon)
            start_d = (end_d - timedelta(days=88)).replace(day=1)
            q = (mon - 1) // 3 + 1 if (fye or "1231") == "1231" else None
            label = f"Q{q}-{end_d.year}" if q else f"quarter ended {end_d.isoformat()}"
            out.append((m.start(), m.end(), 1, (label, start_d.isoformat(), end_d.isoformat())))
    for m in _PER_YTD.finditer(s):
        out.append((m.start(), m.end(), 2, None))
    for m in _PER_Y.finditer(s):
        y = int(m.group(1))
        if 1990 <= y <= 2100 and not any(a <= m.start(1) < b for a, b, _, _ in out):
            start, end = year_dates(y, fye)
            out.append((m.start(), m.end(), 3, (f"FY{y}", start, end)))
    return out


def _period(s: str, fye: str | None, pos: int | None = None) -> Period | None:
    """(label, start, end) of the period a sentence names. With `pos` (where the figure
    stands), the nearest period phrase wins ("… 469,000 in 2019, and 120,000 in the
    fourth quarter"); without it, a quarter wins over a year."""
    ps = _periods(s, fye)
    if not ps:
        return None
    if pos is None:
        return min(ps, key=lambda p: (p[3] is None, p[2], p[0]))[3]

    def dist(p):
        a, b = p[0], p[1]
        return 0 if a <= pos < b else min(abs(pos - a), abs(pos - b))

    return min(ps, key=lambda p: (dist(p), p[2]))[3]


def _is_year(s: str, m: re.Match, n: int) -> bool:
    """A 4-digit figure 1990–2039 without a thousands separator next to a year or period
    word is a year, not a count."""
    raw = m.group(f"n{n}")
    if "," in raw or "." in raw or m.group(f"m{n}") or not re.fullmatch(r"\d{4}", raw):
        return False
    if not 1990 <= int(raw) <= 2039:
        return False
    before = s[max(0, m.start(f"n{n}") - 30) : m.start(f"n{n}")]
    after = s[m.end(f"n{n}") : m.end(f"n{n}") + 20]
    return bool(
        _YEAR_WORD.search(before)
        or re.match(r"^\s*(?:,|and\b|to\b|through\b|compared\b|was\b|were\b|[-–])", after)
        or not after.strip()
    )


def _amount(m: re.Match, n: int) -> tuple[float, str]:
    v = float(m.group(f"n{n}").replace(",", ""))
    if m.group(f"m{n}"):
        v *= 1e6
    qual = (m.group(f"q{n}") or "").strip()
    return v, ("stated" if not qual else f"stated ({qual})")


def sentence_metrics(text: str, fye: str | None = "1231") -> list[Metric]:
    out: list[Metric] = []

    def add(s: str, m: re.Match, n: int, metric: str, unit: str) -> None:
        if _is_year(s, m, n):
            return
        per = _period(s, fye, m.start(f"n{n}"))
        if per is None:
            return
        v, basis = _amount(m, n)
        label, start, end = per
        out.append(
            Metric(
                metric, "", label, start, end, v, unit, "kpi", basis, s[:600], EXTRACTOR_SENTENCE
            )
        )

    for s in _sentences(text):
        low = s.lower()
        if not any(w in low for w in ("produced", "delivered", "billable")):
            continue
        if not _periods(s, fye):
            continue
        if m := _PROD_DELIV.search(s):
            add(s, m, 1, "production", "vehicles")
            add(s, m, 2, "deliveries", "vehicles")
        else:
            for rx, metric in ((_DELIV, "deliveries"), (_PROD, "production")):
                if m := rx.search(s):
                    add(s, m, 1, metric, m.group("u1").lower())
        if m := (_BILLABLE.search(s) or _BILLABLE_REV.search(s)):
            add(s, m, 1, "billable_units", "units")
    return out


def extract(text: str, fye: str | None = "1231") -> list[Metric]:
    """Every extractor on one document; the first row per (metric, line, period) wins
    (tables before sentences)."""
    seen: set = set()
    out = []
    for m in quarter_table(text, fye) + pd_table(text, fye) + sentence_metrics(text, fye):
        key = (m.metric, m.line, m.period_label)
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


# --- Storage -------------------------------------------------------------------------------


def store(
    engine: sqlite3.Connection,
    cik: str,
    metrics: Iterable[Metric],
    *,
    accession: str,
    filename: str | None,
    filed: str,
    source: str,
    now: datetime,
) -> int:
    """Insert rows (first extraction kept: filings are immutable). Returns rows added."""
    before = engine.total_changes
    engine.executemany(
        "INSERT OR IGNORE INTO unit_metric (cik, metric, line, period_label, period_start, "
        "period_end, value, unit, kind, basis, source, accession, filename, filed, quote, "
        "extractor, extracted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                cik,
                m.metric,
                m.line,
                m.period_label,
                m.start,
                m.end,
                m.value,
                m.unit,
                m.kind,
                m.basis,
                source,
                accession,
                filename,
                filed,
                m.quote,
                m.extractor,
                iso(now),
            )
            for m in metrics
        ],
    )
    return engine.total_changes - before


def _scan_state(doc_id: int) -> str:
    return f"unit_scan:{SCAN_VERSION}:{doc_id}"


@dataclass
class ScanResult:
    docs: int = 0
    rows: int = 0
    by_metric: dict | None = None


def scan_company(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    cik: str,
    now: datetime,
    *,
    rescan: bool = False,
) -> ScanResult:
    """Run the extractors on the company's stored releases and reports not scanned yet
    (0 requests). One short transaction per document."""
    fye = fiscal_year_end(engine, cik)
    marks = ",".join("?" * len(SCAN_TYPES))
    docs = corpus.execute(
        f"SELECT doc_id, accession, filename, doc_type FROM document WHERE cik = ? "
        f"AND doc_type IN ({marks}) ORDER BY accession",
        (cik, *SCAN_TYPES),
    ).fetchall()
    res = ScanResult(by_metric={})
    for d in docs:
        state = _scan_state(d["doc_id"])
        if (
            not rescan
            and engine.execute("SELECT 1 FROM refresh_state WHERE name = ?", (state,)).fetchone()
        ):
            continue
        f = engine.execute(
            "SELECT filed FROM filing WHERE accession = ?", (d["accession"],)
        ).fetchone()
        if f is None:
            continue  # not in the filing index yet: next pass
        text = corpus.execute(
            "SELECT text FROM document WHERE doc_id = ?", (d["doc_id"],)
        ).fetchone()[0]
        got = extract(text, fye)
        engine.execute("BEGIN")
        try:
            engine.execute(
                "DELETE FROM unit_metric WHERE cik = ? AND accession = ? AND ifnull(filename, '') "
                "= ifnull(?, '') AND ("
                + " OR ".join(["extractor LIKE ?"] * len(EXTRACTOR_FAMILIES))
                + ")",
                (cik, d["accession"], d["filename"], *EXTRACTOR_FAMILIES),
            )
            n = store(
                engine,
                cik,
                got,
                accession=d["accession"],
                filename=d["filename"],
                filed=f["filed"],
                source=d["doc_type"],
                now=now,
            )
            engine.execute(
                "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES "
                "(?, ?, ?, ?) ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
                "detail = excluded.detail",
                (state, d["accession"], iso(now), f'{{"rows": {len(got)}}}'),
            )
            engine.execute("COMMIT")
        except Exception:
            engine.execute("ROLLBACK")
            raise
        res.docs += 1
        res.rows += n
        for m in got:
            res.by_metric[m.metric] = res.by_metric.get(m.metric, 0) + 1
    return res


_PD_TITLE = re.compile(r"vehicle production\s*(?:&|and)\s*deliveries", re.I)


@dataclass(frozen=True)
class DocCoverage:
    """What one stored document can give the unit extractors (DS2 diagnosis)."""

    doc_type: str
    accession: str
    filename: str
    chars: int
    quarter_header: bool  # ≥ 3 quarter labels in a row (the Update's summaries)
    kpi_labels: int  # "Model 3/Y deliveries", "Total production", … tokens
    pd_release: bool  # a production-and-deliveries release
    rows: int  # unit_metric rows from this document

    def text(self) -> str:
        kind = (
            "production-and-deliveries release"
            if self.pd_release
            else ("operational summary" if self.quarter_header and self.kpi_labels else "")
        )
        bits = [f"{self.chars:,} chars"]
        if kind:
            bits.append(kind)
        elif self.chars < 3000:
            bits.append("almost no text (images or a cover page?)")
        else:
            bits.append(f"no KPI table ({self.kpi_labels} KPI row label(s))")
        bits.append(f"{self.rows} row(s)")
        return f"{self.doc_type} {self.accession} {self.filename}: " + ", ".join(bits)


def coverage(engine: sqlite3.Connection, corpus: sqlite3.Connection, cik: str) -> list[DocCoverage]:
    """Per stored document of the scanned types: size, whether it carries the Update's
    quarter-label summary or a production-and-deliveries table, and rows extracted."""
    marks = ",".join("?" * len(SCAN_TYPES))
    out = []
    for d in corpus.execute(
        f"SELECT accession, filename, doc_type, text FROM document WHERE cik = ? "
        f"AND doc_type IN ({marks}) ORDER BY accession",
        (cik, *SCAN_TYPES),
    ):
        toks = tokens(d["text"] or "")
        run = best = 0
        for t in toks:
            run = run + 1 if _qlabel(t) else 0
            best = max(best, run)
        labels = sum(1 for t in toks if _ROW.match(_clean_label(t)) or _STORAGE.match(t))
        low = [t.lower() for t in toks]
        pd = bool(_PD_TITLE.search(d["text"] or "")) or any(
            t == "production" and "deliveries" in low[i + 1 : i + 3] for i, t in enumerate(low)
        )
        n = engine.execute(
            "SELECT count(*) FROM unit_metric WHERE cik = ? AND accession = ? "
            "AND ifnull(filename, '') = ifnull(?, '')",
            (cik, d["accession"], d["filename"]),
        ).fetchone()[0]
        out.append(
            DocCoverage(
                d["doc_type"],
                d["accession"],
                d["filename"] or "",
                len(d["text"] or ""),
                best >= 3,
                labels,
                pd,
                n,
            )
        )
    return out


def coverage_lines(engine: sqlite3.Connection, corpus: sqlite3.Connection, cik: str) -> list[str]:
    """The DS2 line for the log: what the stored documents can and cannot give."""
    cov = coverage(engine, corpus, cik)
    if not cov:
        return ["no stored EX-99.1/EX-99.2/10-K/10-Q text for this company"]
    out = [c.text() for c in cov]
    if not any(c.pd_release for c in cov):
        out.append(
            "quarterly production-and-deliveries releases: none in the stored corpus (Tesla "
            "posts them on its IR site; they are not among the stored 8-K exhibits), so "
            "quarters come only from the Update letters' operational summary and 10-Q/10-K "
            "sentences"
        )
    return out


# --- Reads ---------------------------------------------------------------------------------


def latest_rows(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    """One row per (metric, line, period): the latest-filed statement of it."""
    return engine.execute(
        "SELECT * FROM unit_metric u WHERE cik = ? AND NOT EXISTS (SELECT 1 FROM unit_metric v "
        "WHERE v.cik = u.cik AND v.metric = u.metric AND v.line = u.line AND v.period_label = "
        "u.period_label AND (v.filed > u.filed OR (v.filed = u.filed "
        "AND v.accession > u.accession))) "
        "ORDER BY metric, line, period_end",
        (cik,),
    ).fetchall()


def annual_from_quarters(rows: list[sqlite3.Row], fye: str = "1231") -> list[Metric]:
    """Calendar/fiscal-year totals as the sum of 4 stated quarters (labelled), for metrics
    stated only quarterly (Tesla deliveries)."""
    by: dict[tuple, dict[int, sqlite3.Row]] = {}
    for r in rows:
        m = re.match(r"^Q([1-4])-(\d{4})$", r["period_label"])
        if not m or r["kind"] != "kpi":
            continue
        by.setdefault((r["metric"], r["line"], r["unit"], int(m.group(2))), {})[int(m.group(1))] = r
    out = []
    for (metric, line, unit, y), qs in sorted(by.items()):
        if len(qs) != 4:
            continue
        start, end = year_dates(y, fye)
        total = sum(float(qs[q]["value"]) for q in (1, 2, 3, 4))
        accs = sorted({qs[q]["accession"] for q in qs})
        out.append(
            Metric(
                metric,
                line,
                f"FY{y}",
                start,
                end,
                total,
                unit,
                "kpi",
                "sum of 4 quarters",
                " + ".join(accs),
                "computed",
            )
        )
    return out


def _exact_first(rows: list[sqlite3.Row], fye: str) -> list[sqlite3.Row]:
    """Drop an approximate stated year ("over 1.8 million") where 4 exact stated quarters
    add up to the same year: the sum is the more precise figure (labelled as a sum)."""
    sums = {(m.metric, m.line, m.period_label) for m in annual_from_quarters(rows, fye)}
    return [
        r
        for r in rows
        if not (
            (r["metric"], r["line"], r["period_label"]) in sums
            and r["basis"].startswith("stated (")
        )
    ]


@dataclass(frozen=True)
class KpiRow:
    metric: str
    line: str
    unit: str
    kind: str
    earlier: tuple[str, float] | None  # label, value
    later: tuple[str, float]
    change: float | None  # ratio
    basis: str
    source: str  # accession · filename
    quote: str


def kpi_rows(engine: sqlite3.Connection, cik: str) -> list[KpiRow]:
    """Latest period per metric and line against the same period a year earlier (else the
    prior period); annual rows from stated years, else the sum of 4 stated quarters."""
    rows = _exact_first(latest_rows(engine, cik), fiscal_year_end(engine, cik))
    fye = fiscal_year_end(engine, cik)
    stated_years = {(r["metric"], r["line"], r["period_label"]) for r in rows}
    computed = [
        m
        for m in annual_from_quarters(rows, fye)
        if (m.metric, m.line, m.period_label) not in stated_years
    ]
    series: dict[tuple, list] = {}
    for r in rows:
        kind_q = "Q" if r["period_label"].startswith("Q") else "Y"
        series.setdefault((r["metric"], r["line"], r["unit"], r["kind"], kind_q), []).append(
            (
                r["period_end"],
                r["period_label"],
                float(r["value"]),
                r["basis"],
                f"{r['accession']} · {r['filename'] or r['source']}",
                r["quote"],
            )
        )
    for m in computed:
        series.setdefault((m.metric, m.line, m.unit, m.kind, "Y"), []).append(
            (m.end, m.period_label, m.value, m.basis, m.quote, "sum of the 4 stated quarters")
        )
    out = []
    for (metric, line, unit, kind, _), pts in sorted(series.items()):
        pts.sort()
        end, label, value, basis, src, quote = pts[-1]
        prior = None
        target = date.fromisoformat(end) - timedelta(days=365)
        for e2, l2, v2, *_ in pts[:-1]:
            if abs((date.fromisoformat(e2) - target).days) <= 20:
                prior = (l2, v2)
        if prior is None and len(pts) > 1:
            prior = (pts[-2][1], pts[-2][2])
        change = (value / prior[1] - 1) if prior and prior[1] else None
        out.append(
            KpiRow(metric, line, unit, kind, prior, (label, value), change, basis, src, quote)
        )
    return out


def change_between(
    engine: sqlite3.Connection, cik: str, metric: str, a: str, b: str, line: str = ""
) -> float | None:
    """Change from period label a to b (stated, else sum of 4 quarters)."""
    fye = fiscal_year_end(engine, cik)
    rows = _exact_first(latest_rows(engine, cik), fye)
    vals = {(r["metric"], r["line"], r["period_label"]): float(r["value"]) for r in rows}
    for m in annual_from_quarters(rows, fye):
        vals.setdefault((m.metric, m.line, m.period_label), m.value)
    va, vb = vals.get((metric, line, a)), vals.get((metric, line, b))
    if va is None or vb is None or va == 0:
        return None
    return vb / va - 1


def period_value(
    engine: sqlite3.Connection, cik: str, metric: str, label: str, line: str = ""
) -> tuple[float | None, str]:
    """(value, where from) for one period label: the latest stated row (its document
    type and accession), else the sum of 4 stated quarters, else (None, "missing: not in
    stored text")."""
    fye = fiscal_year_end(engine, cik)
    rows = _exact_first(latest_rows(engine, cik), fye)
    for r in rows:
        if (r["metric"], r["line"], r["period_label"]) == (metric, line, label):
            return float(r["value"]), f"{r['source']} {r['accession']}, {r['basis']}"
    for m in annual_from_quarters(rows, fye):
        if (m.metric, m.line, m.period_label) == (metric, line, label):
            return m.value, "sum of 4 stated quarters"
    return None, "missing: not in stored text"


# --- Category breaks (m04_unit_kpi) --------------------------------------------------------


@dataclass(frozen=True)
class Break:
    metric: str
    accession: str
    filed: str
    before: tuple[str, ...]
    after: tuple[str, ...]

    @property
    def added(self) -> tuple[str, ...]:
        return tuple(x for x in self.after if x not in self.before)

    @property
    def dropped(self) -> tuple[str, ...]:
        return tuple(x for x in self.before if x not in self.after)

    def text(self) -> str:
        parts = []
        if self.dropped:
            parts.append(f"no longer reported: {', '.join(self.dropped)}")
        if self.added:
            parts.append(f"new: {', '.join(self.added)}")
        return "; ".join(parts)


def breaks(engine: sqlite3.Connection, cik: str) -> list[Break]:
    """Per metric, the model lines or categories each release reports, compared with the
    release before: a new line (with or without one dropped) is a break."""
    by: dict[str, dict[tuple[str, str], set[str]]] = {}
    for r in engine.execute(
        "SELECT metric, line, accession, filed FROM unit_metric WHERE cik = ? AND kind = 'kpi' "
        "AND line != ''",
        (cik,),
    ):
        by.setdefault(r["metric"], {}).setdefault((r["filed"], r["accession"]), set()).add(
            r["line"]
        )
    out = []
    for metric, releases in sorted(by.items()):
        prev: set[str] | None = None
        for (filed, acc), lines in sorted(releases.items()):
            if prev is not None and lines - prev:
                out.append(Break(metric, acc, filed, tuple(sorted(prev)), tuple(sorted(lines))))
            prev = lines
    return out


def propose_breaks(engine: sqlite3.Connection, cik: str, ticker: str | None, now: datetime) -> dict:
    """One `m04_unit_kpi` item per break (group 6, capped). The first scan of a company is
    a baseline: recorded, queued only when filed in the last 12 months (D-M04-71)."""
    from engine.financials import queue

    state = f"unit_kpi_scan:{cik}"
    first = (
        engine.execute("SELECT 1 FROM refresh_state WHERE name = ?", (state,)).fetchone() is None
    )
    counts: dict[str, int] = {}
    engine.execute("BEGIN")
    try:
        for b in breaks(engine, cik):
            reason = (
                f"{ticker or cik}: {b.metric} categories changed in the release filed "
                f"{b.filed} — {b.text()}. Series are not merged across the break "
                "(D-M04-42)."
            )
            payload = {
                "metric": b.metric,
                "accession": b.accession,
                "filed": b.filed,
                "before": list(b.before),
                "after": list(b.after),
                "ticker": ticker,
            }
            st = queue.propose(
                engine,
                "m04_unit_kpi",
                f"{cik}:{b.metric}:{b.accession}",
                reason,
                payload,
                now,
                cik=cik,
                baseline=first,
                filed=b.filed,
            )
            counts[st] = counts.get(st, 0) + 1
        engine.execute(
            "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, 'm04', "
            "?, NULL) ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at",
            (state, iso(now)),
        )
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return counts


def owner_breaks(engine: sqlite3.Connection, cik: str) -> dict[tuple[str, str], str]:
    """(metric, accession) → the owner's answer on a resolved `m04_unit_kpi` item."""
    import json

    out = {}
    for r in engine.execute(
        "SELECT payload, resolution FROM review_queue WHERE kind = 'm04_unit_kpi' AND cik = ? "
        "AND resolved_at IS NOT NULL",
        (cik,),
    ):
        p = json.loads(r["payload"] or "{}")
        out[(p.get("metric", ""), p.get("accession", ""))] = r["resolution"] or ""
    return out


# --- Quarterly gross margin with the instance fallback (Target; D-M04-42) --------------------

REVENUE_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
)
COST_TAGS = ("CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold")


@dataclass(frozen=True)
class QuarterGM:
    end: str
    gm: float | None
    revenue: float | None
    cost: float | None
    basis: str  # where revenue and cost came from, or why missing


def _quarter_fact(engine, cik, tags, end) -> float | None:
    for tag in tags:
        r = engine.execute(
            "SELECT value FROM fact WHERE cik = ? AND taxonomy = 'us-gaap' AND tag = ? "
            "AND period_end = ? AND period_start IS NOT NULL AND julianday(period_end) - "
            "julianday(period_start) BETWEEN 80 AND 100 ORDER BY filed LIMIT 1",
            (cik, tag, end),
        ).fetchone()
        if r is not None:
            return float(r[0])
    return None


def quarter_gm(engine: sqlite3.Connection, cik: str, end: str) -> QuarterGM:
    """Gross margin of the discrete quarter ending `end`: companyfacts revenue and cost;
    where companyfacts lacks the cost line, the instance's dimensional pair on one product
    or service member (the 10-Q line companyfacts misses, D-M04-42), labelled."""
    rev = _quarter_fact(engine, cik, REVENUE_TAGS, end)
    cost = _quarter_fact(engine, cik, COST_TAGS, end)
    if rev is not None and cost is not None and rev:
        return QuarterGM(end, (rev - cost) / rev, rev, cost, "companyfacts")
    pairs: dict[str, dict[str, float]] = {}
    for r in engine.execute(
        "SELECT concept, member, dims, value FROM fact_dim WHERE cik = ? AND period_end = ? "
        "AND period_start IS NOT NULL AND julianday(period_end) - julianday(period_start) "
        "BETWEEN 80 AND 100 AND axis LIKE '%ProductOrServiceAxis' AND instr(dims, ';') = 0 "
        "ORDER BY filed",
        (cik, end),
    ):
        tag = r["concept"].split(":")[-1]
        role = "rev" if tag in REVENUE_TAGS else ("cost" if tag in COST_TAGS else None)
        if role:
            pairs.setdefault(r["member"], {}).setdefault(role, float(r["value"]))
    both = {m: v for m, v in pairs.items() if "rev" in v and "cost" in v and v["rev"]}
    if len(both) == 1:
        member, v = next(iter(both.items()))
        return QuarterGM(
            end,
            (v["rev"] - v["cost"]) / v["rev"],
            v["rev"],
            v["cost"],
            f"instance dimension {member} (cost line not in companyfacts)",
        )
    why = (
        (
            "missing: dimensional (cost line not in companyfacts and no single product pair "
            "in the instance)"
        )
        if rev is not None
        else "missing: no quarterly revenue"
    )
    return QuarterGM(end, None, rev, cost, why)


def gm_yoy_pp(
    engine: sqlite3.Connection, cik: str, end: str, prior_end: str
) -> tuple[float | None, QuarterGM, QuarterGM]:
    a, b = quarter_gm(engine, cik, prior_end), quarter_gm(engine, cik, end)
    if a.gm is None or b.gm is None:
        return None, b, a
    return (b.gm - a.gm) * 100, b, a
