"""Parse company guidance from earnings-release text (R19, M00_SEARCH D-SRCH-8).

Pure functions over the stored document text; no LLM. Every item carries the
offsets of the sentence or table row it came from (its quote) and of the text
that gave its period, so provenance is exact by construction.

Sentences: scanned when they contain a forward-looking verb (expect, anticipate,
forecast, "outlook/guidance to/of/is/for") and a value. Metric mentions
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
A row with a digit cell that no value pattern reads goes to review (columns are
never guessed). Negatives are read: "$(0.14)", "($0.14)", "-$0.14", "(4.5)%".
Money without a scale word is used only for per-share metrics or when the lines
above the table state "(in millions/billions)".

Periods: "third quarter (of fiscal) 2026", "third-quarter 2026", "Q3 2026",
"Q3 FY2027", "FQ1-27", "full year (fiscal) 2026", "fiscal 2027", "FY26",
"remaining quarters of 2026", else a bare year. Years are the company's own
fiscal labels. Periods after "compared with/to", "versus", "vs." are comparisons
and ignored. No period in the sentence → the nearest outlook heading above.
Normalized as "FY2027 Q3", "FY2026", "FY2026 remaining".

A % spread on a % value ("74%, plus or minus 1%") is read as percentage points.
"calendar (year) 2026" / "CY26" → "CY2026" (Microsoft guides capex by calendar year).

Calls (`parse_call`, D-M02-20): only management turns are read; the call's fiscal
quarter anchors spoken periods ("next quarter", "the fourth quarter", "next fiscal
year"; "this year"/"full year" except on a Q4 call, where it is ambiguous). Spoken
cues are wider ("will", "plan to", "going to"). A capex sentence with a forward cue,
a direction word and no figure becomes a direction-only item ("FY27 capex to grow");
growth-rate wording, mixed directions or no period go to review. Unparsed sentences
are queued only when they mention capex; the rest are counted as skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from decimal import Decimal

PARSER_VERSION = "guidance-7"

# --- Metrics -----------------------------------------------------------------

METRICS: tuple[tuple[str, str], ...] = (  # (alias regex, canonical), longest first
    (r"diluted weighted[- ]average shares(?: outstanding)?", "shares_diluted"),
    (r"basic weighted[- ]average shares(?: outstanding)?", "shares_basic"),
    (r"diluted (?:net income|earnings) per share", "eps_diluted"),
    (r"earnings \(loss\) per share", "eps_diluted"),
    (r"(?:net income|earnings) per (?:diluted )?share", "eps_diluted"),
    (r"eps", "eps_diluted"),
    (r"net income", "net_income"),
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
_SCALE = r"(?:\s*(?i:trillion|billion|million|thousand|bn|tn)\b|(?:B|M|K)\b)"  # "Million" too
_SCALES = {
    "trillion": Decimal(10) ** 12,
    "tn": Decimal(10) ** 12,
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
# negatives: "$(0.14)", "($0.14)", "-$0.14", "(4.5)%"
_MONEY_NEG = re.compile(
    rf"(?:-\s?\$\s?(?P<a>{_NUM})|\$\s?\(\s?(?P<b>{_NUM})\s?\)|\(\s?\$\s?(?P<c>{_NUM})\s?\))"
    rf"(?P<sa>{_SCALE})?"
)
_PCT_NEG = re.compile(rf"\(\s?(?P<a>{_NUM})\s?\)\s?%")
_COUNT = re.compile(
    rf"(?<![\d.,$])(?P<a>{_NUM})\s*(?P<sa>billion|million|thousand)\b", re.IGNORECASE
)
_APPROX = re.compile(
    r"(?:approximately|about|roughly|around|nearly|almost|close to|~)\s*$", re.IGNORECASE
)
# "more than $25 billion" is a floor, "up to $5 billion" a ceiling: not a point (live check)
_FLOOR = re.compile(
    r"(?:more than|over|at least|greater than|in excess of|north of|above)\s*$", re.IGNORECASE
)
_CEILING = re.compile(r"(?:up to|less than|under|below|no more than|at most)\s*$", re.IGNORECASE)


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
    bound: str | None = None  # floor ("more than $X") | ceiling ("up to $X")


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
    for m in _MONEY_NEG.finditer(text):
        sa = _scale(m["sa"])
        a = -_num(m["a"] or m["b"] or m["c"]) * (sa or 1)
        found.append(Value("point", "USD", a, a, a, None, None, sa is not None, m.start(), m.end()))
    for m in _PCT_NEG.finditer(text):
        a = -_num(m["a"])
        found.append(Value("point", "%", a, a, a, None, None, True, m.start(), m.end()))
    for m in _COUNT.finditer(text):
        a = _num(m["a"]) * (_scale(m["sa"]) or 1)
        found.append(Value("point", "count", a, a, a, None, None, True, m.start(), m.end()))

    found.sort(key=lambda v: (v.start, -(v.end - v.start)))
    out: list[Value] = []
    for v in found:
        if out and v.start < out[-1].end:
            continue
        before = text[max(0, v.start - 16) : v.start]
        if v.kind == "point" and _APPROX.search(before):
            v = replace(v, kind="approx")
        elif v.kind == "point" and _FLOOR.search(before):
            v = replace(v, bound="floor")
        elif v.kind == "point" and _CEILING.search(before):
            v = replace(v, bound="ceiling")
        out.append(v)
    return out


# --- Periods -----------------------------------------------------------------

_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_YEAR = r"(?:fiscal\s+(?:year\s+)?)?(?:FY\s?)?'?(?P<y>\d{4}|\d{2})"
_PERIODS = (
    re.compile(r"\b(?:calendar(?:\s+year)?\s+|CY\s?'?)(?P<y>\d{4}|\d{2})\b(?P<cy>)", re.I),
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
    # spoken two-digit fiscal years: "fiscal 28", "fiscal '27", "fiscal year 26"
    re.compile(r"\bfiscal\s+(?:year\s+)?'?(?P<y>\d{2})\b(?![\d,.%-])", re.I),
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


# spoken periods, resolved against the call's own fiscal quarter (anchor)
_NOT_YEAR = r"(?!\s+(?:of\s+)?(?:fiscal\s+)?(?:year\s+)?(?:FY\s?)?'?\d)"
_RELATIVE = (
    (re.compile(r"\bnext quarter\b", re.I), "next_q"),
    (re.compile(rf"\b(?P<q>first|second|third|fourth)[- ]quarter\b{_NOT_YEAR}", re.I), "q"),
    (re.compile(r"\bQ(?P<qn>[1-4])\b(?!\s*(?:FY|fiscal)?\s*'?\d)", re.I), "q"),
    (re.compile(r"\bnext (?:fiscal )?year\b", re.I), "next_y"),
    (
        re.compile(
            r"\b(?:this|the current) (?:fiscal )?year\b|\bthe fiscal year\b"
            rf"|\b(?:the )?full[- ]year\b{_NOT_YEAR}",
            re.I,
        ),
        "this_y",
    ),
)


def _relative(m: re.Match[str], how: str, anchor: tuple[int, int]) -> str | None:
    fy, q = anchor
    if how == "next_q":
        return f"FY{fy + 1} Q1" if q == 4 else f"FY{fy} Q{q + 1}"
    if how == "q":
        t = _ORD[m["q"].lower()] if m.groupdict().get("q") else int(m["qn"])
        return f"FY{fy if t > q else fy + 1} Q{t}"
    if how == "next_y":
        return f"FY{fy + 1}"
    return None if q == 4 else f"FY{fy}"  # on a Q4 call "this year" may mean either year


def find_periods(
    text: str, *, bare_years: bool = True, anchor: tuple[int, int] | None = None
) -> list[Period]:
    """Forward periods in text (comparison periods excluded), in order.

    anchor = (fiscal year, quarter) of a call: spoken relative periods are resolved
    against it; without an anchor they are not periods.
    """
    out: list[Period] = []
    for rx in _PERIODS:
        for m in rx.finditer(text):
            if any(p.start < m.end() and m.start() < p.end for p in out):
                continue
            year = _year(m["y"])
            gd = m.groupdict()
            if gd.get("cy") is not None:
                label = f"CY{year}"
            elif gd.get("q"):
                label = f"FY{year} Q{_ORD[gd['q'].lower()]}"
            elif gd.get("qn"):
                label = f"FY{year} Q{gd['qn']}"
            elif gd.get("rem") is not None:
                label = f"FY{year} remaining"
            else:
                label = f"FY{year}"
            out.append(Period(label, m.start(), m.end()))
    if anchor is not None:
        for rx, how in _RELATIVE:
            for m in rx.finditer(text):
                if any(p.start < m.end() and m.start() < p.end for p in out):
                    continue
                if (label := _relative(m, how, anchor)) is not None:
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


@dataclass(frozen=True)
class Direction:
    """Direction-only guidance from a call ("FY27 capex to grow"): no figure (D-M02-20)."""

    metric: str
    period: str
    direction: str  # up | down | flat
    quote_start: int
    quote_end: int
    period_start: int
    period_end: int


@dataclass
class ParseResult:
    items: list[Item] = field(default_factory=list)
    unparsed: list[Unparsed] = field(default_factory=list)
    candidates: int = 0
    directions: list[Direction] = field(default_factory=list)
    skipped: int = 0  # guidance-like sentences not queued (calls: only capex goes to review)
    skipped_spans: list[Unparsed] = field(default_factory=list)  # sampled by the audit

    def skip(self, start: int, end: int, reason: str) -> None:
        self.skipped += 1
        self.skipped_spans.append(Unparsed(start, end, reason))


_CUE = re.compile(
    r"\b(?:expect(?:s|ed|ing)?|anticipat(?:e|es|ed|ing)|forecast(?:s|ed|ing)?)\b"
    r"|\b(?:outlook|guidance)\s+(?:to|of|is|for)\b",
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
_YEAR_AGO = re.compile(
    r"\W*(?:a year ago|last year|in the (?:prior|previous|year-ago)|year[- ]over[- ]year|"
    r"in (?:the )?(?:same|prior) (?:quarter|period)|last quarter)",
    re.IGNORECASE,
)
# words that may stand right before "revenue" when it means the company total
_REVENUE_LEAD = frozenset((
    "a", "an", "the", "our", "its", "total", "net", "consolidated", "overall", "company",
    "quarterly", "annual", "year", "fiscal", "gaap", "expect", "expects", "expected",
    "anticipate", "anticipates", "forecast", "forecasts", "of", "for", "in", "on", "and", "to",
    "with", "that", "be", "see", "guide", "guiding", "record", "reported", "q1", "q2", "q3", "q4",
    "quarter", "first", "second", "third", "fourth", "this", "next", "is", "are", "will",
    "announces", "announced", "provides", "issues", "reiterates", "reaffirms", "raises",
    "lowers", "updates", "initiates", "sets", "outlook", "guidance",
))  # fmt: skip
_PARTY = (
    r"\b(?:hyperscale\w*|customers?'?|industry|cloud providers?|peers|competitors|"
    r"the market|partners'?|data center operators?|analysts?|consensus|the street)\b"
)
# "In Productivity and Business Processes, we expect revenue of ..." (Microsoft guides by
# segment on its call): a sentence opening with a named unit is about that unit
_SCOPE = re.compile(
    r"^\s*(?:In|For|Within|At)\s+(?:the\s+)?(?P<name>[A-Z][\w&'-]*(?:\s+(?:and|&|of|[A-Z][\w&'-]*))*)\s*,"
)
_NOT_UNIT = re.compile(
    r"^(?:Q[1-4]|FY|Fiscal|Calendar|Addition|Total|Summary|Aggregate|Closing|Short|Particular|"
    r"General|Conclusion|Turn|Terms|Constant|January|February|March|April|May|June|July|"
    r"August|September|October|November|December|First|Second|Third|Fourth|Fiscal|The)\b"
)
SEGMENT_METRICS = frozenset({"revenue", "gross_margin", "operating_income", "operating_margin",
                             "operating_expenses"})  # fmt: skip


def segment_scope(sent: str) -> str | None:
    """The named business unit a sentence opens with ('In Intelligent Cloud, ...'), if any."""
    m = _SCOPE.match(sent)
    if m is None or _NOT_UNIT.match(m["name"]) or find_periods(m["name"]):
        return None
    return m["name"]


_PARTY_BEFORE = re.compile(_PARTY + r"[^.;]{0,25}$", re.IGNORECASE)
_PARTY_AFTER = re.compile(r"\s+(?:by|of|from|among|across)\b[^.,;]{0,40}?" + _PARTY, re.I)


def segment_revenue(clause: str, start: int) -> bool:
    """True when the word before 'revenue' names a segment ('AI revenue')."""
    words = re.findall(r"[A-Za-z][\w-]*", clause[max(0, start - 40) : start])
    return bool(words) and words[-1].lower().split("-")[-1] not in _REVENUE_LEAD


def third_party(clause: str, m: re.Match[str]) -> bool:
    """A capex mention about someone else's spending ('CapEx by the top five hyperscalers')."""
    return bool(
        _PARTY_BEFORE.search(clause[max(0, m.start() - 40) : m.start()])
        or _PARTY_AFTER.match(clause, m.end())
    )


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
        return values[:2]
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


def _parse_sentence(
    text: str,
    s: int,
    e: int,
    context: Period | None,
    out: ParseResult,
    *,
    cue: re.Pattern[str] = _CUE,
    anchor: tuple[int, int] | None = None,
) -> None:
    sent = text[s:e]
    cue_text = _NOT_CUE.sub(lambda m: "_" * len(m.group(0)), sent)
    if not cue.search(cue_text) or not find_values(sent):
        return
    if len(sent) > MAX_SENTENCE or _BOILERPLATE.search(sent):
        return
    out.candidates += 1
    sent_periods = find_periods(sent, anchor=anchor)
    scope = segment_scope(sent)

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
            if metric == "revenue" and segment_revenue(clause, m.start()):
                continue  # "AI revenue", "Data Center revenue": a segment, not the company total
            if metric in SEGMENT_METRICS and scope is not None:
                continue  # "In Intelligent Cloud, we expect revenue of ...": one unit
            if metric == "capex" and third_party(clause, m):
                continue  # "CapEx by the top five hyperscalers": someone else's spending
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
            if not cue.search(cue_text[c0 : c0 + fitted[0].start]):
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
            window = find_periods(clause[prev_end:main_start], anchor=anchor)
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
                tail = (
                    clause[pm.end() + after[0].end : pm.end() + after[0].end + 30] if after else ""
                )
                if after and not _YEAR_AGO.match(tail):  # "down from 78% a year ago" = actual
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
            raw = find_values(cells)
            values = [f for v in raw if (f := _fits(metric, v, scale)) is not None]
            if sum(bool(re.search(r"\d", c)) for c in _cells(cells)) > len(raw):
                # a cell with digits was not read (new format): never guess the columns
                out.unparsed.append(Unparsed(x, end, "table row not fully read"))
                values = []
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


# --- Calls -------------------------------------------------------------------

CALL_CUE = re.compile(  # not "guide": "as noted in our guide" is a noun (live check)
    _CUE.pattern + r"|\b(?:will|plan(?:s|ning)? to|going to|guiding)\b", re.IGNORECASE
)
_RECOUNT = re.compile(
    r"\b(?:we (?:had )?(?:said|guided|indicated)|earlier this year|previously|"
    r"last quarter,? we|on our last call|our (?:prior|previous) (?:guidance|outlook))\b",
    re.IGNORECASE,
)
_UPDATE = re.compile(r"\b(?:now|today|updat\w*|rais\w*|lower\w*|revis\w*)\b", re.IGNORECASE)
_MULTI_YEAR = re.compile(
    r"\b(?:next|coming|over the next|for the next)\s+(?:two|three|four|five|few|several|\d+)"
    r"\b[\w\s-]{0,15}?\byears\b",
    re.IGNORECASE,
)
CAPEX_WORDS = re.compile(
    r"\b(?:capital expenditures?|capex|capital spending|capital investments?)\b", re.IGNORECASE
)
_DIRECTIONS = (
    ("up", re.compile(r"\b(?:grow|grows|growing|increas\w*|ris(?:e|es|ing)|higher|above|"
                      r"exceed\w*|accelerat\w*|step(?:ping)? up|ramp(?:ing)? up)\b", re.I)),
    ("down", re.compile(r"\b(?:declin\w*|decreas\w*|lower|below|reduc\w*|fall|falling)\b",
                        re.I)),
    ("flat", re.compile(r"\b(?:flat|roughly the same|similar to)\b", re.I)),
)  # fmt: skip
_RATE = re.compile(r"\bgrowth rates?\b|\brate of (?:growth|increase)\b|\bpace of\b", re.I)
# a period after these words is the comparison ("above fiscal Q4 levels"), not the target
_THAN = re.compile(
    r"\b(?:than|above|below|versus|vs\.?|over|from|exceed\w*|compared (?:to|with)|relative to)"
    r"\s+(?:in\s+|for\s+|the\s+)?$",
    re.IGNORECASE,
)
_NO_GUIDANCE = re.compile(
    r"\b(?:not|n't|no longer)\s+(?:\w+\s+)?(?:providing|giving|guiding|provide|give)\b"
    r"|\bno (?:specific |formal )?(?:outlook|guidance)\b",
    re.IGNORECASE,
)
_CLAUSE = re.compile(
    r"\b(?:including|excluding|inclusive of|exclusive of|net of)\b[^,.;:()]{3,120}", re.IGNORECASE
)


def _direction(
    text: str,
    s: int,
    e: int,
    anchor: tuple[int, int] | None,
    context: Period | None = None,
) -> Direction | str:
    """A direction-only capex item, or the reason it goes to review."""
    sent = text[s:e]
    m = CAPEX_WORDS.search(sent)
    assert m
    if _RATE.search(sent):
        return "growth-rate wording (kept for review, D-UI-15)"
    if _MULTI_YEAR.search(sent):
        return "multi-year wording, no single period"
    tail = sent[m.end() :]
    found = [(d, w) for d, rx in _DIRECTIONS if (w := rx.search(tail))]
    if len(found) != 1:
        return "no direction word" if not found else "mixed directions"
    direction, w = found[0]
    word_at = m.end() + w.start()
    periods = [
        p
        for p in find_periods(sent, anchor=anchor)
        if not _THAN.search(sent[max(0, p.start - 20) : p.start])
    ]
    if not periods and context is not None:
        return Direction("capex", context.label, direction, s, e, context.start, context.end)
    if not periods:
        return "no period"
    before = [p for p in periods if p.start < word_at]
    p = before[-1] if before else periods[0]
    return Direction("capex", p.label, direction, s, e, s + p.start, s + p.end)


def clause_of(text: str, item: Item) -> str | None:
    """The "including/excluding ..." clause stated with a capex value (D-M02-5)."""
    if item.metric != "capex":
        return None
    start = item.quote_start
    for m in CAPEX_WORDS.finditer(text, item.quote_start, item.value.start):
        start = m.start()
    m = _CLAUSE.search(text, start, min(item.quote_end, item.value.end + 120))
    return " ".join(m.group(0).split()) if m else None


def _ended(label: str, anchor: tuple[int, int] | None) -> bool:
    """A period already over at the call (never carried to the next sentence)."""
    if anchor is None:
        return False
    m = re.fullmatch(r"FY(\d{4})(?: Q([1-4]))?", label)
    if not m:
        return False
    fy, q = int(m.group(1)), m.group(2)
    if q is None:
        return fy < anchor[0]
    return (fy, int(q)) <= anchor


def _signal(sent: str, anchor: tuple[int, int] | None) -> bool:
    """A capex sentence worth the owner's time: a figure, a direction word or a period."""
    m = CAPEX_WORDS.search(sent)
    tail = sent[m.end() :] if m else sent
    return bool(
        find_values(sent)
        or any(rx.search(tail) for _, rx in _DIRECTIONS)
        or find_periods(sent, anchor=anchor)
    )


def parse_call(
    text: str, turns: list[tuple[int, int]], anchor: tuple[int, int] | None
) -> ParseResult:
    """Guidance in the given management turns of a call document (D-M02-20).

    turns: (start, end) offsets of management speech; analysts and the operator are
    never read. anchor: the call's (fiscal year, quarter) for spoken periods.

    Live check 2026-10-09 (D-M02-23): a sentence without a period takes the period of
    one of the two sentences before it in the same turn when that one was itself
    forward-looking ("For Q1, we expect revenue … We expect CapEx spend will be over
    $50 billion"); multi-year phrasing ("the next two to three years") takes none.
    Sentences recounting earlier guidance ("Earlier this year, we said we plan to
    invest ~$200 billion") are skipped unless they also say "now"/"updated"; capex of
    other parties ("CapEx by the top five hyperscalers") is skipped; a capex sentence
    with no figure, direction word or period is counted, not queued.
    """
    out = ParseResult()
    lines = _lines(text)
    for a, b in turns:
        recent: list[Period | None] = []  # forward periods of the last sentences in this turn
        for la, lb in lines:
            if lb <= a or la >= b:
                continue
            for s, e in _sentences(text, max(la, a), min(lb, b)):
                sent = text[s:e]
                cue_text = _NOT_CUE.sub(lambda m: "_" * len(m.group(0)), sent)
                forward = bool(CALL_CUE.search(cue_text) or _CONTEXT.search(sent)) and not (
                    _NO_GUIDANCE.search(sent)
                    or (_RECOUNT.search(sent) and not _UPDATE.search(sent))
                )  # retold or "no guidance" sentences never set the period for the next one
                context = next((p for p in reversed(recent[-2:]) if p is not None), None)
                own = [p for p in (find_periods(sent, anchor=anchor) if forward else [])
                       if not _ended(p.label, anchor)]  # fmt: skip
                if own:
                    recent.append(Period(own[0].label, s + own[0].start, s + own[0].end))
                else:  # a forward sentence without its own period carries the context on
                    recent.append(context if forward else None)
                if _MULTI_YEAR.search(sent):
                    context = None
                if not CALL_CUE.search(cue_text):
                    continue
                if len(sent) > MAX_SENTENCE or _BOILERPLATE.search(sent):
                    continue
                if _RECOUNT.search(sent) and not _UPDATE.search(sent):
                    out.skip(s, e, "retells earlier guidance")
                    continue
                if _NO_GUIDANCE.search(sent):
                    out.skip(s, e, "says no guidance is given")
                    continue
                capex = CAPEX_WORDS.search(sent)
                if find_values(sent):
                    one = ParseResult()
                    _parse_sentence(text, s, e, context, one, cue=CALL_CUE, anchor=anchor)
                    out.candidates += one.candidates
                    out.items.extend(one.items)
                    for u in one.unparsed:
                        u_cap = CAPEX_WORDS.search(text[u.start : u.end])
                        if u_cap and not third_party(text[u.start : u.end], u_cap):
                            out.unparsed.append(u)
                        elif u_cap:
                            out.skip(u.start, u.end, "another party's capex")
                        else:
                            out.skip(u.start, u.end, f"not capex ({u.reason})")
                elif capex and third_party(sent, capex):
                    out.skip(s, e, "another party's capex")
                elif capex:
                    out.candidates += 1
                    d = _direction(text, s, e, anchor, context)
                    if isinstance(d, Direction):
                        out.directions.append(d)
                    elif _signal(sent, anchor):
                        out.unparsed.append(Unparsed(s, e, d))
                    else:
                        out.skip(s, e, "capex without figure, direction or period")
    return out
