"""Parse company guidance from earnings-release text (R19, M00_SEARCH D-SRCH-8).

Pure functions over the stored document text; no LLM. Every item carries the
offsets of the sentence or table row it came from (its quote) and of the text
that gave its period, so provenance is exact by construction.

Sentences: scanned when they contain a forward-looking verb (expect, anticipate,
forecast, project, "outlook to/of/is/for") and a $ or % value. Metric mentions
split a clause into segments; each segment's first value belongs to its metric.
"GAAP and non-GAAP ... X and Y, respectively" gives two items; a value stated
shortly after "from" ("narrowed from our prior outlook of $125-145 billion",
"up from $43 million") is the prior guidance. A forward verb must precede each
value, so reported results earlier in the same sentence are not taken; the
period is the one stated nearest before the value. A value before its metric is
taken only in spend phrasing ("invest about $200 billion in capital
expenditures"). Sentences over 600 chars, forward-looking-statement and risk
boilerplate, and noun uses ("projects", "than anticipated") are not candidates.
Candidates that yield no item are returned as unparsed (→ review queue), except
assumption sentences (FX headwind/tailwind/impact without a metric).

Tables (cells separated by tabs in stored text): read only under a header with
exactly one period that says outlook/guidance, or whose lead-in line just above
does (short, or ending with ":"); headers saying "results" are excluded. Rows
start with a known metric label; values sit on the label line or, if that line
has no digits, on a short next line. Header with "GAAP" and "Non-GAAP" → first
value GAAP, last value non-GAAP (adjustment columns between are ignored); one
value → both bases, or GAAP only when the header has an adjustments column.
Money without a scale word is used only for per-share metrics or when the lines
above the table state "(in millions/billions)".

Periods: "third quarter (of fiscal) 2026", "third-quarter 2026", "Q3 2026",
"Q3 FY2027", "FQ1-27", "full year (fiscal) 2026", "fiscal 2027", "FY26",
"remaining quarters of 2026", else a bare year. Years are the company's own
fiscal labels. Periods after "compared with/to", "versus", "vs." are comparisons
and ignored. No period in the sentence → the nearest outlook heading above.
Normalized as "FY2027 Q3", "FY2026", "FY2026 remaining".

A % spread on a % value ("74%, plus or minus 1%") is read as percentage points.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from decimal import Decimal

PARSER_VERSION = "guidance-2"

# --- Metrics -----------------------------------------------------------------

METRICS: tuple[tuple[str, str], ...] = (  # (alias regex, canonical), longest first
    (r"diluted weighted[- ]average shares(?: outstanding)?", "shares_diluted"),
    (r"basic weighted[- ]average shares(?: outstanding)?", "shares_basic"),
    (r"diluted (?:net income|earnings) per share", "eps_diluted"),
    (r"earnings \(loss\) per share", "eps_diluted"),
    (r"(?:net income|earnings) per (?:diluted )?share", "eps_diluted"),
    (r"eps", "eps_diluted"),
    (r"gross margins? percentage", "gross_margin"),
    (r"gross margins?", "gross_margin"),
    (r"operating expenses", "operating_expenses"),
    (r"total expenses|costs and expenses", "total_expenses"),
    (r"operating income", "operating_income"),
    (r"operating margin", "operating_margin"),
    (r"capital expenditures|capex(?: investments)?|capital investments?", "capex"),
    (r"(?:effective )?tax rates?", "tax_rate"),
    (r"other income(?:,? net)?", "other_income"),
    (r"(?:total |net )?revenues?|net sales", "revenue"),
)
_METRIC = re.compile(
    r"\b(?:" + "|".join(f"(?P<m{i}>{a})" for i, (a, _) in enumerate(METRICS)) + r")(?![\w-])",
    re.IGNORECASE,
)
PER_SHARE = {"eps_diluted"}
COUNTS = {"shares_diluted", "shares_basic"}
PERCENTS = {"gross_margin", "operating_margin", "tax_rate"}


def _metric_name(m: re.Match[str]) -> str:
    for i, (_, name) in enumerate(METRICS):
        if m.group(f"m{i}"):
            return name
    raise AssertionError(m.group(0))


# --- Values ------------------------------------------------------------------

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_SCALE = r"(?:\s*(?:billion|million|thousand|bn)\b|(?:B|M|K)\b)"
_SCALES = {
    "billion": Decimal(10) ** 9,
    "bn": Decimal(10) ** 9,
    "b": Decimal(10) ** 9,
    "million": Decimal(10) ** 6,
    "m": Decimal(10) ** 6,
    "thousand": Decimal(10) ** 3,
    "k": Decimal(10) ** 3,
}
_DASH = r"\s*(?:-|–|—|to)\s*"
_PM = r"\s*,?\s*(?:±|\+/-|\+/−|plus or minus)\s*"

_MONEY_RANGE = re.compile(
    rf"\$\s?(?P<a>{_NUM})(?P<sa>{_SCALE})?{_DASH}\$?\s?(?P<b>{_NUM})(?P<sb>{_SCALE})?"
)
_MONEY_BETWEEN = re.compile(
    rf"between\s+\$\s?(?P<a>{_NUM})(?P<sa>{_SCALE})?\s+and\s+\$?\s?(?P<b>{_NUM})(?P<sb>{_SCALE})?",
    re.IGNORECASE,
)
_PCT_RANGE = re.compile(rf"(?<![\d.$])(?P<a>{_NUM})\s?%?{_DASH}(?P<b>{_NUM})\s?%")
_PCT_BETWEEN = re.compile(rf"between\s+(?P<a>{_NUM})\s?%?\s+and\s+(?P<b>{_NUM})\s?%", re.IGNORECASE)
_MONEY_PM = re.compile(
    rf"\$\s?(?P<a>{_NUM})(?P<sa>{_SCALE})?{_PM}"
    rf"(?:\$\s?(?P<d>{_NUM})(?P<sd>{_SCALE})?|(?P<p>{_NUM})\s?%)",
    re.IGNORECASE,
)
_PCT_PM = re.compile(
    rf"(?<![\d.$])(?P<a>{_NUM})\s?%{_PM}(?:(?P<bp>{_NUM})\s*basis points|(?P<p>{_NUM})\s?%)",
    re.IGNORECASE,
)
_MONEY = re.compile(rf"\$\s?(?P<a>{_NUM})(?P<sa>{_SCALE})?")
_PCT = re.compile(rf"(?<![\d.$])(?P<a>{_NUM})\s?%")
_COUNT = re.compile(
    rf"(?<![\d.,$])(?P<a>{_NUM})\s*(?P<sa>billion|million|thousand)\b", re.IGNORECASE
)
_APPROX = re.compile(r"(?:approximately|about|~)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Value:
    kind: str  # range | plusminus | approx | point
    unit: str  # USD | % | count
    low: Decimal
    high: Decimal
    point: Decimal | None
    spread: Decimal | None  # as stated: dollars (abs), percent (pct) or basis points (bps)
    spread_kind: str | None  # abs | pct | bps
    scaled: bool  # money/count carried a scale word (or needs none)
    start: int  # offsets of the value expression
    end: int


def _num(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


def _scale(s: str | None) -> Decimal | None:
    return _SCALES[s.strip().lower()] if s else None


def find_values(text: str) -> list[Value]:
    """Every value expression in text, left to right; the longest wins on overlap."""
    found: list[Value] = []
    for m in _MONEY_PM.finditer(text):
        sa = _scale(m["sa"])
        a = _num(m["a"]) * (sa or 1)
        if m["d"] is not None:
            d = _num(m["d"]) * (_scale(m["sd"]) or sa or 1)
            v = Value("plusminus", "USD", a - d, a + d, a, d, "abs", sa is not None, 0, 0)
        else:
            p = _num(m["p"])
            lo, hi = a * (1 - p / 100), a * (1 + p / 100)
            v = Value("plusminus", "USD", lo, hi, a, p, "pct", sa is not None, 0, 0)
        found.append(replace(v, start=m.start(), end=m.end()))
    for m in _PCT_PM.finditer(text):
        a = _num(m["a"])
        if m["bp"] is not None:
            bp = _num(m["bp"])
            v = Value("plusminus", "%", a - bp / 100, a + bp / 100, a, bp, "bps", True, 0, 0)
        else:
            p = _num(m["p"])
            v = Value("plusminus", "%", a - p, a + p, a, p, "pct", True, 0, 0)
        found.append(replace(v, start=m.start(), end=m.end()))
    for rx in (_MONEY_BETWEEN, _MONEY_RANGE):
        for m in rx.finditer(text):
            sb = _scale(m["sb"])
            sa = _scale(m["sa"]) or sb
            lo, hi = _num(m["a"]) * (sa or 1), _num(m["b"]) * (sb or sa or 1)
            found.append(
                Value("range", "USD", lo, hi, None, None, None, sa is not None, m.start(), m.end())
            )
    for rx in (_PCT_BETWEEN, _PCT_RANGE):
        for m in rx.finditer(text):
            lo, hi = _num(m["a"]), _num(m["b"])
            found.append(Value("range", "%", lo, hi, None, None, None, True, m.start(), m.end()))
    for m in _MONEY.finditer(text):
        sa = _scale(m["sa"])
        a = _num(m["a"]) * (sa or 1)
        found.append(Value("point", "USD", a, a, a, None, None, sa is not None, m.start(), m.end()))
    for m in _PCT.finditer(text):
        a = _num(m["a"])
        found.append(Value("point", "%", a, a, a, None, None, True, m.start(), m.end()))
    for m in _COUNT.finditer(text):
        a = _num(m["a"]) * (_scale(m["sa"]) or 1)
        found.append(Value("point", "count", a, a, a, None, None, True, m.start(), m.end()))

    found.sort(key=lambda v: (v.start, -(v.end - v.start)))
    out: list[Value] = []
    for v in found:
        if out and v.start < out[-1].end:
            continue
        if v.kind == "point" and _APPROX.search(text[max(0, v.start - 16) : v.start]):
            v = replace(v, kind="approx")
        out.append(v)
    return out


# --- Periods -----------------------------------------------------------------

_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_YEAR = r"(?:fiscal\s+(?:year\s+)?)?(?:FY\s?)?'?(?P<y>\d{4}|\d{2})"
_PERIODS = (
    re.compile(rf"\b(?P<q>first|second|third|fourth)[- ]quarter\s+(?:of\s+)?{_YEAR}\b", re.I),
    re.compile(r"\bQ(?P<qn>[1-4])\s*(?:FY|fiscal\s+)?\s*'?(?P<y>\d{4}|\d{2})\b", re.I),
    re.compile(r"\bFQ(?P<qn>[1-4])[- ](?P<y>\d{4}|\d{2})\b", re.I),
    re.compile(r"\bremaining quarters of (?:fiscal\s+)?(?P<y>\d{4})\b(?P<rem>)", re.I),
    re.compile(
        r"\b(?:full[- ]year|fiscal year|fiscal)\s+(?:fiscal\s+)?(?:year\s+)?"
        r"(?:FY\s?)?(?P<y>\d{4})\b",
        re.I,
    ),
    re.compile(r"\bFY\s?'?(?P<y>\d{4}|\d{2})\b", re.I),
)
_BARE_YEAR = re.compile(r"(?<![\d,/])\b(?P<y>20\d{2})\b")
_COMPARISON = re.compile(
    r"\b(?:compared (?:with|to)|versus|vs\.?|relative to|in the prior)\b(?:(?!\.\s)[^;])*$",
    re.IGNORECASE,
)
_DATE_BEFORE = re.compile(
    r"(?:january|february|march|april|may|june|july|august|september|october|november|"
    r"december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.?\s+\d{1,2},\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Period:
    label: str  # FY2027 Q3 | FY2026 | FY2026 remaining
    start: int
    end: int


def _year(y: str) -> int:
    n = int(y)
    return 2000 + n if n < 100 else n


def find_periods(text: str, *, bare_years: bool = True) -> list[Period]:
    """Forward periods in text (comparison periods excluded), in order."""
    out: list[Period] = []
    for rx in _PERIODS:
        for m in rx.finditer(text):
            if any(p.start < m.end() and m.start() < p.end for p in out):
                continue
            year = _year(m["y"])
            gd = m.groupdict()
            if gd.get("q"):
                label = f"FY{year} Q{_ORD[gd['q'].lower()]}"
            elif gd.get("qn"):
                label = f"FY{year} Q{gd['qn']}"
            elif gd.get("rem") is not None:
                label = f"FY{year} remaining"
            else:
                label = f"FY{year}"
            out.append(Period(label, m.start(), m.end()))
    if bare_years and not out:
        for m in _BARE_YEAR.finditer(text):
            if not _DATE_BEFORE.search(text[: m.start()]):
                out.append(Period(f"FY{m['y']}", m.start(), m.end()))
    out = [p for p in out if not _COMPARISON.search(text[: p.start])]
    return sorted(out, key=lambda p: p.start)


# --- Items -------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    metric: str
    basis: str  # GAAP | non-GAAP | unspecified
    period: str
    value: Value  # offsets into the document text
    prior: Value | None
    source: str  # sentence | table
    quote_start: int  # sentence or table row, offsets into the document text
    quote_end: int
    period_start: int  # where the period was read (sentence or heading)
    period_end: int


@dataclass(frozen=True)
class Unparsed:
    start: int
    end: int
    reason: str


@dataclass
class ParseResult:
    items: list[Item] = field(default_factory=list)
    unparsed: list[Unparsed] = field(default_factory=list)
    candidates: int = 0


_CUE = re.compile(
    r"\b(?:expect(?:s|ed|ing)?|anticipat(?:e|es|ed|ing)|forecast(?:s|ed|ing)?)\b"
    r"|\boutlook\s+(?:to|of|is|for)\b",
    re.IGNORECASE,
)
_NOT_CUE = re.compile(
    r"than[- ](?:expected|anticipated)|unexpected|anticipated (?:benefits|synergies)"
    r"|expected timeframe",
    re.IGNORECASE,
)
_CONTEXT = re.compile(r"\b(?:outlook|guidance|forecast\w*)\b", re.IGNORECASE)
_ASSUMPTION = re.compile(r"\b(?:headwind|tailwind|impact|assum\w+)\b", re.IGNORECASE)
_RESPECTIVELY = re.compile(r"\brespectively\b", re.IGNORECASE)
_PRIOR = re.compile(r"\bfrom\b", re.IGNORECASE)
_TRAILING_PM = re.compile(
    rf"^\W*(?:respectively\W*)?(?:±|\+/-|plus or minus)\s*(?:(?P<bp>{_NUM})\s*basis points"
    rf"|(?P<p>{_NUM})\s?%)",
    re.IGNORECASE,
)
_SENT_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z•▪“\"(])")
_BULLET = re.compile(r"^[\s•▪◦●]+")
_TABLE_SCALE = re.compile(r"\(\s*(?:\$\s*)?in\s+(billions|millions|thousands)", re.IGNORECASE)
_BOILERPLATE = re.compile(
    r"forward-looking statements?|risks? (?:related to|and uncertainties)|\(\d+\).*\(\d+\)",
    re.IGNORECASE,
)
_CELL = re.compile(r"\t|\s\|\s")
# value before its metric only in spend phrasing ("invest about $200 billion in capex")
_SPEND = re.compile(r"\b(?:invest|spend)\w*\b", re.IGNORECASE)
MAX_SENTENCE = 600  # longer "sentences" are flattened tables or legal boilerplate


def _bases(prefix: str) -> tuple[str, ...]:
    """Basis stated just before (or in) a metric mention."""
    t = prefix[-40:].lower()
    if re.search(r"(?<!non-)\bgaap and non-gaap", t):
        return ("GAAP", "non-GAAP")
    if "non-gaap" in t:
        return ("non-GAAP",)
    if re.search(r"(?<!non-)\bgaap\b", t):
        return ("GAAP",)
    return ("unspecified",)


def _fits(metric: str, v: Value, table_scale: Decimal | None = None) -> Value | None:
    """The value adjusted for the metric's unit, or None if it cannot belong to it."""
    if metric in PERCENTS:
        return v if v.unit == "%" else None
    if metric in COUNTS:
        return v if v.unit == "count" else None
    if v.unit != "USD":
        return None
    if metric in PER_SHARE:
        return None if v.scaled else v
    if v.scaled:
        return v
    if table_scale is None:
        return None
    f = table_scale
    return replace(
        v,
        low=v.low * f,
        high=v.high * f,
        point=v.point * f if v.point is not None else None,
        spread=v.spread * f if v.spread is not None and v.spread_kind == "abs" else v.spread,
        scaled=True,
    )


def _shift(v: Value, offset: int) -> Value:
    return replace(v, start=v.start + offset, end=v.end + offset)


def _lines(text: str) -> list[tuple[int, int]]:
    out, pos = [], 0
    while pos < len(text):
        nl = text.find("\n", pos)
        end = len(text) if nl == -1 else nl
        out.append((pos, end))
        pos = end + 1
    return out


def _sentences(text: str, a: int, b: int) -> list[tuple[int, int]]:
    lead = _BULLET.match(text, a, b)
    start = lead.end() if lead else a
    out = []
    for m in _SENT_END.finditer(text, start, b):
        out.append((start, m.start()))
        start = m.end()
    out.append((start, b))
    return [(s, e) for s, e in out if text[s:e].strip()]


def _spread_both(seg: str, values: list[Value]) -> list[Value]:
    """'74.8% and 75.0%, respectively, plus or minus 50 basis points' → spread on both."""
    m = _TRAILING_PM.match(seg[values[1].end :])
    if not m:
        return values
    out = []
    for v in values[:2]:
        if m["bp"] is not None and v.unit == "%":
            d, spread, kind = _num(m["bp"]) / 100, _num(m["bp"]), "bps"
        elif m["p"] is not None and v.unit == "%":
            d, spread, kind = _num(m["p"]), _num(m["p"]), "pct"
        elif m["p"] is not None:
            d, spread, kind = v.low * _num(m["p"]) / 100, _num(m["p"]), "pct"
        else:
            out.append(v)
            continue
        out.append(replace(v, kind="plusminus", low=v.low - d, high=v.high + d, point=v.low,
                           spread=spread, spread_kind=kind))  # fmt: skip
    return out


def _parse_sentence(text: str, s: int, e: int, context: Period | None, out: ParseResult) -> None:
    sent = text[s:e]
    cue_text = _NOT_CUE.sub(lambda m: "_" * len(m.group(0)), sent)
    if not _CUE.search(cue_text) or not find_values(sent):
        return
    if len(sent) > MAX_SENTENCE or _BOILERPLATE.search(sent):
        return
    out.candidates += 1
    sent_periods = find_periods(sent)

    items: list[Item] = []
    no_period = False
    c0 = 0  # clause offset within the sentence
    for clause in sent.split(";"):
        mentions = list(_METRIC.finditer(clause))
        prev_end = 0
        for i, m in enumerate(mentions):
            seg_end = mentions[i + 1].start() if i + 1 < len(mentions) else len(clause)
            metric = _metric_name(m)
            seg_start = m.end()
            fitted = [
                _shift(f, seg_start)
                for v in find_values(clause[seg_start:seg_end])
                if (f := _fits(metric, v)) is not None
            ]
            if not fitted and len(mentions) == 1 and _SPEND.search(clause[: m.start()]):
                # value stated before the metric (spend phrasing)
                fitted = [
                    f
                    for v in find_values(clause[: m.start()])
                    if (f := _fits(metric, v)) is not None
                ][-1:]
            if not fitted:
                continue
            # a forward verb must precede the value: past results in the sentence are not guidance
            if not _CUE.search(cue_text[c0 : c0 + fitted[0].start]):
                continue
            bases = _bases(clause[: m.end()])
            if (
                len(bases) == 2
                and len(fitted) >= 2
                and _RESPECTIVELY.search(clause[seg_start:seg_end])
            ):
                pairs = list(zip(bases, _spread_both(clause, fitted), strict=True))
            else:
                pairs = [(b, fitted[0]) for b in bases]
            main_end = max(v.end for _, v in pairs)
            main_start = min(v.start for _, v in pairs)
            # period: nearest stated before this value, else anywhere in the sentence, else heading
            window = find_periods(clause[prev_end:main_start])
            if window:
                p = window[-1]
                period = Period(p.label, s + c0 + prev_end + p.start, s + c0 + prev_end + p.end)
            elif sent_periods:
                p = sent_periods[0]
                period = Period(p.label, s + p.start, s + p.end)
            else:
                period = context
            prev_end = main_end
            if period is None:
                no_period = True
                continue
            prior = None
            pm = _PRIOR.search(clause, main_end, seg_end if seg_end > main_end else len(clause))
            if pm and pm.start() - main_end < 60:
                after = [
                    f
                    for v in find_values(clause[pm.end() : pm.end() + 60])
                    if (f := _fits(metric, v)) is not None
                ]
                if after:
                    prior = _shift(after[0], s + c0 + pm.end())
            for basis, v in pairs:
                items.append(
                    Item(
                        metric,
                        basis,
                        period.label,
                        _shift(v, s + c0),
                        prior,
                        "sentence",
                        s,
                        e,
                        period.start,
                        period.end,
                    )  # fmt: skip
                )
        c0 += len(clause) + 1
    if items:
        out.items.extend(items)
    elif no_period:
        out.unparsed.append(Unparsed(s, e, "no period"))
    elif _ASSUMPTION.search(sent) and not _METRIC.search(sent):
        out.candidates -= 1  # assumption (FX impact etc.), not guidance
    else:
        out.unparsed.append(Unparsed(s, e, "no metric/value pair"))


def _cells(row: str) -> list[str]:
    return _CELL.split(row)


def _norm_cells(row: str) -> str:
    """Join split table cells: '41.0<tab>%' → '41.0%', '$<tab>0.31' → '$0.31'."""
    row = re.sub(r"\s*(?:\t|\|)\s*%", "%", row)
    row = re.sub(r"\$\s*(?:\t|\|)\s*", "$", row)
    return " | ".join(c.strip() for c in _cells(row))


def _label_metric(label: str) -> tuple[str, tuple[str, ...]] | None:
    """(metric, basis from label) when a table label names a known metric."""
    m = re.match(r"\s*(?:total\s+)?(?P<b>(?:non-)?gaap\s+)?(?:total\s+)?", label, re.IGNORECASE)
    assert m
    rest = label[m.end() :].strip()
    mm = _METRIC.match(rest)
    if not mm:
        return None
    tail = rest[mm.end() :]
    if re.match(r"\s*[A-Za-z]", tail) and not re.match(
        r"\s*(?:attributable|outstanding|percentage)", tail, re.IGNORECASE
    ):
        return None  # longer label (e.g. "Revenue Trend") → not a metric row
    if m["b"]:
        return _metric_name(mm), ("non-GAAP",) if m["b"].lower().startswith("non") else ("GAAP",)
    return _metric_name(mm), ()


def _is_header(text: str, lines: list[tuple[int, int]], i: int) -> Period | None:
    """An outlook table header: one period, and 'outlook/guidance' in it or in the
    lead-in line just above (short, or ending with ':'). Results tables are excluded."""
    a, b = lines[i]
    line = text[a:b]
    if not 0 < len(line.strip()) <= 120 or re.search(r"\bresults\b", line, re.IGNORECASE):
        return None
    periods = find_periods(line, bare_years=False)
    if len({p.label for p in periods}) != 1:
        return None
    if not _CONTEXT.search(line):
        k = i - 1
        while k >= 0 and not text[lines[k][0] : lines[k][1]].strip():
            k -= 1
        above = text[lines[k][0] : lines[k][1]].strip() if k >= 0 else ""
        if not (_CONTEXT.search(above) and (len(above) <= 120 or above.endswith(":"))):
            return None
    return replace(periods[0], start=a + periods[0].start, end=a + periods[0].end)


def _parse_tables(text: str, lines: list[tuple[int, int]], out: ParseResult) -> None:
    i = 0
    while i < len(lines):
        period = _is_header(text, lines, i)
        if period is None:
            i += 1
            continue
        header = text[lines[i][0] : lines[i][1]]
        scale = None
        for x, y in lines[max(0, i - 3) : i + 1]:
            if sm := _TABLE_SCALE.search(text[x:y]):
                scale = _SCALES[sm.group(1).lower().rstrip("s")]
        j, rows = i + 1, 0
        while j < len(lines) and j < i + 80:
            x, y = lines[j]
            row = text[x:y]
            if not row.strip():
                j += 1
                continue
            label = _cells(row)[0]
            lm = _label_metric(label)
            if len(row) > 150 and not _CELL.search(row):
                break  # prose ends the table
            if lm is None and _is_header(text, lines, j):
                break  # next table
            if lm is None:
                if rows == 0:
                    header += " " + row
                j += 1
                continue
            rows += 1
            metric, label_basis = lm
            cells, end = _norm_cells(row[len(label) :]), y
            if not re.search(r"\d", cells):  # values on the next line
                k = j + 1
                while k < len(lines) and not text[lines[k][0] : lines[k][1]].strip():
                    k += 1
                if k < len(lines):
                    nxt = text[lines[k][0] : lines[k][1]]
                    if (
                        len(nxt) <= 150
                        and _label_metric(_cells(nxt)[0]) is None
                        and find_values(_norm_cells(nxt))
                    ):
                        cells, end, j = _norm_cells(nxt), lines[k][1], k
            values = [f for v in find_values(cells) if (f := _fits(metric, v, scale)) is not None]
            if values:
                h = header.lower()
                two_cols = bool(re.search(r"(?<!non-)\bgaap", h)) and "non-gaap" in h
                if label_basis:
                    pairs = [(label_basis[0], values[0])]
                elif two_cols and len(values) == 1 and "adjust" in h:
                    pairs = [("GAAP", values[0])]  # non-GAAP column not on this line
                elif two_cols:
                    pairs = [("GAAP", values[0]), ("non-GAAP", values[-1])]
                else:
                    pairs = [("unspecified", values[0])]
                for basis, v in pairs:
                    # cell offsets are not exact after joining cells; the row is the quote
                    out.items.append(
                        Item(
                            metric,
                            basis,
                            period.label,
                            replace(v, start=x, end=end),
                            None,
                            "table",
                            x,
                            end,
                            period.start,
                            period.end,
                        )  # fmt: skip
                    )
            j += 1
        i = j


def parse_release(text: str) -> ParseResult:
    """All guidance items in an earnings release: sentences in order, then tables."""
    result = ParseResult()
    lines = _lines(text)
    context: Period | None = None
    for a, b in lines:
        line = text[a:b]
        if not line.strip():
            continue
        if (_CONTEXT.search(line) or _CUE.search(line)) and len(line) <= 400:
            ps = find_periods(line, bare_years=False)
            if ps:
                context = replace(ps[0], start=a + ps[0].start, end=a + ps[0].end)
        if _CELL.search(line) and not _CUE.search(line):
            continue  # table rows are read by _parse_tables
        for s, e in _sentences(text, a, b):
            _parse_sentence(text, s, e, context, result)
    _parse_tables(text, lines, result)
    return result
