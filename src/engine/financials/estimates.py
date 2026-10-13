"""Estimate changes in annual reports (M04 Part 6; D-M04-17, -18, -92; S2.7).

- **Where:** the current annual report and the two before it (Part 3 stores the prior two,
  D-M04-17, DS7), stored text only (0 requests). Code finds the sentences (FTS5 on estimate
  wording: "change in estimate", "useful lives", "catch-up", "booking rate", "estimated
  profitability", …); a sentence counts when it states an amount and what it moved (net
  income, operating or pretax income, earnings, depreciation or another expense). Gemini is
  never called here (D28).
- **Amount and basis (D-M04-18):** one amount per sentence, chosen by basis: after-tax
  (net income, net earnings) first, then pre-tax (operating income, pretax, earnings,
  profit), then an expense line (depreciation, amortization; its income effect has the
  opposite sign). Direction from the verb before the amount (increase, benefit, favorable
  → +; decrease, reduction, unfavorable → −); both directions are kept (Amazon 2025 −$1.0B).
- **Denominator (D-M04-18):** the company figure on the amount's tax basis for the year the
  sentence names (else the report's fiscal year), as known on the report's filing date:
  after-tax ÷ net income; pre-tax ÷ operating income, else pretax income from continuing
  operations (GE tags no operating income). Not meaningful when ≤ 0 or below 1% of revenue.
- **Bands (D-M04-17):** < 10% note, 10–25% watch, ≥ 25% elevated (starting values);
  `m04_estimate` review at ≥ 10% in either direction (group 7). The same direction in all
  three disclosures adds a recurrence flag. Amounts are stored by filing version: a later
  report that restates an amount (GE 2016: $2.2B → $0.7B) is a new row; the old one stays.
- **Catch-up revenue** (`ContractWithCustomerPerformanceObligationSatisfiedInPreviousPeriod`,
  ASC 606): revenue, not profit, so shown against the company's own history only
  (Lockheed $2.2B 2019 … $1.2B 2024); the same sign three years running is flagged.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from engine.financials.capex import fiscal_label, near
from engine.financials.text import clean, doc_scale, numbers, sentence_at, sentences
from engine.sec.asof import facts_as_of
from engine.sec.identity import normalize_cik

NOTE_BELOW, ELEVATED_FROM = 0.10, 0.25  # D-M04-17 starting values
NI_MIN_SHARE = 0.01
ANNUAL_FORMS = ("10-K", "10-KT", "20-F", "40-F")
DISCLOSURES = 3
DEDUPE_TOL = 0.03  # the same amount stated twice in one report at different rounding
PASS_STATE = "m04_estimates_pass:{cik}"  # the company's latest estimate pass (superseded rows)

QUERY = (
    '"change in estimate" OR "changes in estimate" OR "changes in estimates" OR '
    '"change in accounting estimate" OR "changes in accounting estimates" OR "useful life" OR '
    '"useful lives" OR "catch-up" OR "booking rate" OR "booking rates" OR '
    '"estimated profitability" OR "estimate changes" OR "changes in estimated" OR '
    '"revisions in estimates" OR "revisions to estimates" OR "estimates at completion" OR '
    '"effect of this change" OR "impact of this change"'
)
# Estimate wording (D-M04-92, live check 1: in the same sentence as the amount, or in the
# sentence directly before one that refers to "this change"; GE's long-term service
# agreements: "total estimated profitability", "cumulative catch-up adjustments")
ESTIMATE = re.compile(
    r"change[sd]? in (?:accounting )?estimates?|estimate changes|useful li(?:fe|ves)|"
    r"catch[- ]up|booking rates?|estimated (?:profitability|margins?|revenues? and costs?)|"
    r"changes? (?:in|to) (?:the |our )?(?:total )?estimated|"
    r"revisions? (?:in|to|of) (?:our |the )?(?:contract |cost )?estimates?|"
    r"estimates? (?:at|to) complet\w+|(?:effect|impact) of (?:this|these) changes?",
    re.I,
)
# Wording that itself names an estimate change: only these let a sentence with variance
# wording through ("… catch-up adjustments of $5,196 million compared to 2024" does not).
STRICT = re.compile(
    r"change[sd]? in (?:accounting )?estimates?|estimate changes|useful li(?:fe|ves)|"
    r"changes? (?:in|to) (?:the |our )?(?:total )?estimated|estimated profitability|"
    r"revisions? (?:in|to|of) (?:our |the )?(?:contract |cost )?estimates?|"
    r"(?:effect|impact) of (?:this|these) changes?",
    re.I,
)
REFERS = re.compile(r"\b(?:this|these|such) (?:changes?|adjustments?|revisions?)\b", re.I)
VARIANCE = re.compile(
    r"\bcompared (?:with|to)\b|\byear[- ]over[- ]year\b|\bversus\b|\bor \d+(?:\.\d+)?\s?%",
    re.I,
)
TABLE_LABEL = re.compile(r"\b(?:increase|decrease)\s*/?\s*\(?(?:increase|decrease)\b", re.I)
PER_SHARE_ROW = re.compile(r"per (?:basic |diluted )?share|\bEPS\b", re.I)
RESPECTIVELY = re.compile(r"\brespectively\b", re.I)
# Schedule rows are not estimate changes (Part 6 re-run 1: Intel "Future amortization
# expenses $ 998 $ 858 $ 655 …"): future / expected amortization, maturities, "thereafter"
SCHEDULE = re.compile(
    r"\bfuture\b|\bexpected (?:future )?amortization|\bmaturit(?:y|ies)\b|\bthereafter\b|"
    r"\bremaining (?:amortization|payments?|obligations?)\b",
    re.I,
)
SCHEDULE_ROW_MIN = 3  # amounts in a row without an estimate phrase in its label
# "a change in estimated profitability of $2,131 million" (GE FY2017): the amount is the
# change itself, an earnings effect (pre-tax)
CHANGE_OF = re.compile(
    r"changes? in (?:the |our )?(?:total )?estimated profitability (?:of|totall?ing)\s*\(?$",
    re.I,
)
TABLE_LOOKBACK = 3  # sentences before a table row searched for the estimate wording
KIND = (
    ("useful_life", re.compile(r"useful li(?:fe|ves)", re.I)),
    ("catch_up", re.compile(r"catch[- ]up|booking rates?", re.I)),
    ("contract", re.compile(r"contract|profitability|long-term (?:product )?service", re.I)),
)
HYPOTHETICAL = re.compile(r"\b(?:may|could|might|if)\b", re.I)
OBJECTS = (
    ("after_tax", re.compile(r"net (?:income|earnings|loss)|after[- ]tax|attributable to", re.I)),
    (
        "pre_tax",
        re.compile(
            r"operating (?:income|profit|earnings)|income from operations|"
            r"pre-?tax|before (?:income )?taxes|segment profit|\bprofit\b|"
            r"\bearnings\b|\bmargins?\b",
            re.I,
        ),
    ),
    ("expense", re.compile(r"depreciation|amortization|expense", re.I)),
)
BASIS_ORDER = ("after_tax", "pre_tax", "expense")
UP = re.compile(
    r"increas\w*|higher|favorabl\w*|benefit\w*|improv\w*|rais\w*|\badd\w*|gains?\b", re.I
)
DOWN = re.compile(
    r"decreas\w*|reduc\w*|lower\w*|unfavorabl\w*|negativ\w*|declin\w*|charges?\b", re.I
)
# "$2.5 billion increase to gross margin": the object after the amount (Intel)
TRAIL = re.compile(
    r"\s*(?:of\s+)?(?P<dir>increase|decrease|reduction|benefit|improvement|decline)s?\s+"
    r"(?:in|to|of|on)\s+(?:our\s+|the\s+)?",
    re.I,
)
TRAIL_UP = ("increase", "benefit", "improvement")
YEAR = re.compile(r"\b(?:fiscal (?:year )?)?((?:19|20)\d{2})\b")
PER_SHARE = re.compile(r"^\s*(?:per|a)\s+(?:basic|diluted|share)", re.I)
YEAR_AFTER = 60  # characters after an amount searched for the year it is for


def band(share: float | None) -> str:
    if share is None:
        return "missing"
    a = abs(share)
    if a < NOTE_BELOW:
        return "note"
    if a < ELEVATED_FROM:
        return "watch"
    return "elevated"


@dataclass
class Candidate:
    """One amount in a sentence with what it moved."""

    amount: float  # signed income effect
    basis: str
    raw: str
    year: str | None
    at: int = 0  # offset of the amount in the sentence
    listed: bool = False  # mapped to its year by a "…, respectively" list


@dataclass
class Finding:
    cik: str
    accession: str
    doc_ref: str
    form: str
    filed: str
    start: int
    quote: str
    kind: str
    amount: float
    basis: str
    fiscal_label: str
    period_end: str | None
    denominator: float | None = None
    denominator_what: str = ""
    share: float | None = None
    band: str = "missing"
    passage_id: int | None = None
    others: list[str] = field(default_factory=list)
    why: str = ""

    @property
    def key(self) -> str:
        return f"{self.cik}:{self.accession}:{self.start}"


def _direction(window: str) -> int:
    ups = [m.end() for m in UP.finditer(window)]
    downs = [m.end() for m in DOWN.finditer(window)]
    if not ups and not downs:
        return 0
    return 1 if (max(ups) if ups else -1) > (max(downs) if downs else -1) else -1


def candidates(sentence: str, scale: float) -> list[Candidate]:
    """Amounts with a basis, in sentence order (per-share figures and bare numbers skipped)."""
    out: list[Candidate] = []
    ends: list[int] = []
    prev_end = 0
    last_basis, last_dir = None, 0
    for n in numbers(sentence, 0, len(sentence), scale):
        if n.start < prev_end:
            continue  # inside a trailing object already read
        if "$" not in n.raw and not re.search(r"million|billion|thousand", n.raw, re.I):
            prev_end = n.end
            continue
        if PER_SHARE.match(sentence[n.end : n.end + 20]):
            prev_end = n.end
            continue
        window = sentence[prev_end : n.start]
        basis, d, used_to = _trailing(sentence, n.end)
        if basis is None and CHANGE_OF.search(sentence[: n.start]):
            # "driven by a change in estimated profitability of $2,131 million" (GE)
            basis, d, used_to = "pre_tax", _direction(sentence[: n.start]), n.end
        if basis is None:
            best: tuple[int, int] = (-1, 0)
            for name, rx in OBJECTS:  # the object nearest the amount; "net earnings" first
                for m in rx.finditer(window):
                    if (m.end(), -m.start()) > best:
                        best, basis = (m.end(), -m.start()), name
            d = _direction(window)
            used_to = n.end
        if basis is None:
            basis, d = last_basis, d or last_dir
        if basis is None or d == 0:
            prev_end = n.end
            continue
        sign = d * (-1 if basis == "expense" else 1)
        years = YEAR.findall(window)
        after = YEAR.findall(sentence[n.end : n.end + YEAR_AFTER])
        before = YEAR.findall(sentence[: n.start])
        year = years[-1] if years else after[0] if after else before[-1] if before else None
        out.append(Candidate(sign * n.value, basis, n.raw, year, n.start))
        ends.append(n.end)
        last_basis, last_dir, prev_end = basis, d, used_to
    # "… by $2.2 billion, $1.4 billion and $1.6 billion in 2016, 2015 and 2014, respectively"
    if len(out) >= 2 and RESPECTIVELY.search(sentence):
        listed = YEAR.findall(sentence[ends[-1] :])
        if len(listed) == len(out):
            for c, y in zip(out, listed, strict=True):
                c.year, c.listed = y, True
    return out


def _trailing(sentence: str, at: int) -> tuple[str | None, int, int]:
    """(basis, direction, end) for an object named right after the amount ("$2.5 billion
    increase to gross margin"), else (None, 0, at)."""
    m = TRAIL.match(sentence, at)
    if m is None:
        return None, 0, at
    rest = sentence[m.end() : m.end() + 40]
    for name, rx in OBJECTS:
        om = rx.match(rest)
        if om is not None:
            d = 1 if m.group("dir").lower() in TRAIL_UP else -1
            return name, d, m.end() + om.end()
    return None, 0, at


def table_candidate(row: str, scale: float, label: str | None) -> Candidate | None:
    """A table row ("Decrease/increase to Earnings/(loss) from operations ($1,377) ($6,562)
    ($2,943)"): the first column is the report's fiscal year, parentheses are negative,
    the basis comes from the row label; per-share rows are skipped (live check 1)."""
    nums = numbers(row, 0, len(row), scale)
    if len(nums) < 2:
        return None
    first = nums[0]
    head = row[: first.start]
    if PER_SHARE_ROW.search(head):
        return None
    basis = None
    for name in BASIS_ORDER:
        rx = dict(OBJECTS)[name]
        if rx.search(head):
            basis = name
            break
    if basis is None:
        return None
    value = -first.value if "(" in first.raw else first.value
    if basis == "expense":
        value = -value
    year = label[2:] if label and label.startswith("FY") else None
    return Candidate(value, basis, first.raw, year)


def is_schedule_row(sentence: str, table: bool) -> bool:
    """A schedule row (future amortization, maturities, "thereafter"), not an estimate change:
    schedule wording before the first amount (in a table row: anywhere in it), or a table row
    of ≥ 3 amounts whose label names no estimate (Part 6 re-run 1, Intel)."""
    nums = numbers(sentence, 0, len(sentence), 1.0)
    if len(nums) < 2:
        return False
    head = sentence[: nums[0].start]
    if SCHEDULE.search(head) or (table and SCHEDULE.search(sentence)):
        return True
    return (
        table
        and len(nums) >= SCHEDULE_ROW_MIN
        and not ESTIMATE.search(head)
        and not TABLE_LABEL.search(head)
    )


def is_table_row(sentence: str) -> bool:
    """A table row: two or more figures under a "Decrease/increase" label, or tab-separated
    cells with no direction verb (a prose sentence states its direction)."""
    nums = numbers(sentence, 0, len(sentence), 1.0)
    if len(nums) < 2:
        return False
    if TABLE_LABEL.search(sentence):
        return True
    head = sentence[: nums[0].start]
    return "\t" in sentence and not UP.search(head) and not DOWN.search(head)


def pick(cands: list[Candidate]) -> Candidate | None:
    for b in BASIS_ORDER:
        for c in cands:
            if c.basis == b:
                return c
    return None


def kind_of(sentence: str) -> str:
    return next((k for k, rx in KIND if rx.search(sentence)), "other")


@dataclass(frozen=True)
class Annual:
    accession: str
    form: str
    filed: str
    report_date: str | None


def annual_reports(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    cik: str,
    n: int = DISCLOSURES,
    accessions: list[str] | None = None,
) -> list[Annual]:
    """The newest `n` annual reports (original forms) with stored text, newest first. A
    company outside the filing index (GE, a reference case) uses its stored documents and the
    filing dates of its facts. `accessions` names the reports to read (GE's FY2016 and FY2017
    10-Ks: Part 3 stores newer GE annual reports, so "the newest 3" missed them)."""
    marks = ",".join("?" * len(ANNUAL_FORMS))
    rows = engine.execute(
        f"SELECT f.accession, f.form, f.filed, f.report_date FROM filing f JOIN filing_cik c ON "
        f"c.accession = f.accession WHERE c.cik = ? AND f.form IN ({marks}) "
        "ORDER BY f.filed DESC, f.accession DESC",
        (cik, *ANNUAL_FORMS),
    ).fetchall()
    if accessions is not None:
        rows = [r for r in rows if r["accession"] in accessions]
    out = [Annual(r["accession"], r["form"], r["filed"], r["report_date"]) for r in rows[:n]]
    if out:
        return out
    docs = corpus.execute(
        "SELECT DISTINCT accession, doc_type FROM document WHERE cik = ? AND doc_type IN "
        f"({marks})",
        (cik, *ANNUAL_FORMS),
    ).fetchall()
    if accessions is not None:
        docs = [d for d in docs if d["accession"] in accessions]
    found = []
    for d in docs:
        r = engine.execute(
            "SELECT filed, max(period_end) AS e FROM fact WHERE accession = ? GROUP BY filed "
            "ORDER BY filed LIMIT 1",
            (d["accession"],),
        ).fetchone()
        if r is not None:
            found.append(Annual(d["accession"], d["doc_type"], r["filed"], r["e"]))
    return sorted(found, key=lambda a: a.filed, reverse=True)[:n]


def report_fy(engine: sqlite3.Connection, cik: str, a: Annual) -> tuple[str | None, str | None]:
    """(fiscal label, period end) of an annual report."""
    end = a.report_date
    if not end:
        r = engine.execute(
            "SELECT max(period_end) FROM fact WHERE accession = ? AND period_start IS NOT NULL",
            (a.accession,),
        ).fetchone()
        end = r[0] if r else None
    return (fiscal_label(end), end) if end else (None, None)


def _denominator(
    engine: sqlite3.Connection, cik: str, basis: str, end: str | None, as_of: str
) -> tuple[float | None, str, str]:
    """(value, what, state) for the amount's basis and year as known on `as_of`."""
    if end is None:
        return None, "", "missing: the year the amount is for has no fiscal year end stored"
    names = ("net_income",) if basis == "after_tax" else ("operating_income", "pretax_income")
    for name in names:
        pts = facts_as_of(engine, cik, name, as_of, ptype="FY").points
        p = next((p for p in pts if p.end == end or near(p.end, end)), None)
        if p is not None:
            what = (
                f"{name.replace('_', ' ')} {fiscal_label(p.end)} {p.value / 1e6:,.0f}M "
                f"({p.method.split(';')[0]}; {p.accession}, as of {as_of})"
            )
            return p.value, what, ""
    return None, "", f"missing: no {' or '.join(n.replace('_', ' ') for n in names)} for the year"


def _revenue(engine: sqlite3.Connection, cik: str, end: str, as_of: str) -> float | None:
    pts = facts_as_of(engine, cik, "revenue", as_of, ptype="FY").points
    p = next((p for p in pts if p.end == end or near(p.end, end)), None)
    return p.value if p else None


def _year_end(engine: sqlite3.Connection, cik: str, label: str, fallback: str | None) -> str | None:
    rows = engine.execute(
        "SELECT DISTINCT period_end FROM fact WHERE cik = ? AND period_start IS NOT NULL AND "
        "form IN ('10-K', '10-K/A', '20-F', '40-F', '10-KT') ORDER BY period_end",
        (cik,),
    ).fetchall()
    ends = [r[0] for r in rows if fiscal_label(r[0]) == label]
    if fallback and fiscal_label(fallback) == label:
        return fallback
    return ends[-1] if ends else None


def _prev_sentence(text: str, spans: list[tuple[int, int]], i: int) -> str:
    if i > 0:
        return text[spans[i - 1][0] : spans[i - 1][1]]
    s = spans[i][0]
    if s <= 0:
        return ""
    a, b = sentence_at(text, max(0, s - 3))
    return text[a:b] if b <= s else ""


AMOUNT_START = re.compile(r"\$\s?\d|\d\s*(?:million|billion)\b", re.I)


def _clauses(sent: str) -> tuple[str, str]:
    """(the clauses before the one with the first amount, that clause on): GE's "Revisions
    may affect … total estimated profitability resulting in an adjustment of earnings; such
    adjustments increased earnings by $2.1 billion …" is a general statement, then a fact."""
    m = AMOUNT_START.search(sent)
    cut = sent.rfind(";", 0, m.start()) if m else -1
    return (sent[: cut + 1], sent[cut + 1 :]) if cut >= 0 else ("", sent)


def qualifies(sent: str, prev: str) -> tuple[bool, str]:
    """(counts, context) for a prose sentence (D-M04-92 as amended at live check 1): the
    estimate wording in the sentence itself, or in the sentence directly before one that
    refers to "this change" / "such adjustments"; variance wording ("increased $X compared
    with", "or 31%", "year over year") only when the sentence itself names an estimate
    change; never a hypothetical (may / could / might / if) in the clause with the amount —
    a general clause before a ";" may hold one when the amount's clause refers back to it
    ("such adjustments increased earnings by …", GE; Part 6 re-run 1)."""
    head, tail = _clauses(sent)
    if HYPOTHETICAL.search(tail):
        return False, ""
    if head and HYPOTHETICAL.search(head) and not (REFERS.search(tail) and ESTIMATE.search(head)):
        return False, ""
    # a sentence cut by a line break inside it ("… included in “Property and equipment,\n\n
    # net” as of …", Amazon) continues the one before: its wording counts too
    cut = bool(prev) and prev.rstrip()[-1:] not in (".", "!", "?", ";", ":")
    if not ESTIMATE.search(sent) and not (
        prev and (REFERS.search(sent) or cut) and ESTIMATE.search(prev)
    ):
        return False, ""
    context = (prev + " " + sent).strip()  # the kind may be named in the sentence before
    if VARIANCE.search(sent) and not STRICT.search(sent):
        return False, ""
    return True, context


def scan(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    cik: str,
    accessions: list[str] | None = None,
) -> list[Finding]:
    """Estimate-change findings in the company's last three annual reports (0 requests), or
    in the named `accessions`. One row per filing, fiscal year and amount (the first
    sentence that states it)."""
    from engine.search.query import search

    norm = normalize_cik(cik) or cik
    if corpus is None:
        return []
    out: list[Finding] = []
    for a in annual_reports(engine, corpus, norm, accessions=accessions):
        label, end = report_fy(engine, norm, a)
        hits = search(corpus, QUERY, ciks=[norm], accessions=[a.accession], limit=200)
        seen: set[tuple[int, int]] = set()
        kept: list[tuple[str, float]] = []
        for h in sorted(hits, key=lambda h: (h.doc_id, h.start)):
            text = corpus.execute(
                "SELECT text FROM document WHERE doc_id = ?", (h.doc_id,)
            ).fetchone()[0]
            scale = doc_scale(text)
            spans = list(sentences(text, h.start, h.end))
            for i, (s, e) in enumerate(spans):
                if (h.doc_id, s) in seen:
                    continue
                seen.add((h.doc_id, s))
                sent = text[s:e]
                table = is_table_row(sent)
                if is_schedule_row(sent, table):
                    continue
                if table:
                    look = [text[x:y] for x, y in spans[max(0, i - TABLE_LOOKBACK) : i]]
                    if not any(ESTIMATE.search(t) for t in look):
                        continue
                    context = " ".join(look + [sent])
                    best = table_candidate(sent, scale, label)
                    cands = [best] if best else []
                else:
                    ok, context = qualifies(sent, _prev_sentence(text, spans, i))
                    if not ok:
                        continue
                    cands = candidates(sent, scale)
                    best = pick(cands)
                if best is None:
                    continue
                # "…, respectively": one row per listed year; the first keeps the sentence
                # offset, the others take their amount's offset (the row key stays unique)
                listed = [c for c in cands if c.listed and c.basis == best.basis]
                for c in listed or [best]:
                    fy = f"FY{c.year}" if c.year else label
                    if _same_amount(kept, fy or "", c.amount):
                        continue  # already stated in this report (GFS 76M ×3)
                    kept.append((fy or "", c.amount))
                    start = s if not listed or c is listed[0] else s + c.at
                    f = Finding(
                        norm,
                        a.accession,
                        f"{a.accession}/{h.filename}",
                        a.form,
                        a.filed,
                        start,
                        clean(sent),
                        kind_of(context),
                        c.amount,
                        c.basis,
                        fy or "unknown",
                        _year_end(engine, norm, fy, end) if fy else None,
                        passage_id=h.passage_id,
                        others=[f"{o.raw} ({o.basis})" for o in cands if o is not c],
                    )
                    _rate(engine, norm, f, a.filed)
                    out.append(f)
    return out


def _same_amount(kept: list[tuple[str, float]], fy: str, amount: float) -> bool:
    """The same amount for the same year already stated in this report: same sign, within
    3% (GFS 76M three times; GE "$2.1 billion" and "$2,131 million" for 2017)."""
    return any(
        k == fy
        and (v > 0) == (amount > 0)
        and abs(v - amount) <= DEDUPE_TOL * max(abs(v), abs(amount))
        for k, v in kept
    )


def _rate(engine: sqlite3.Connection, cik: str, f: Finding, filed: str) -> None:
    """Denominator, share and band as known on the report's filing date (D-M04-18)."""
    den, what, state = _denominator(engine, cik, f.basis, f.period_end, filed)
    f.denominator_what = what
    if den is None:
        f.band, f.why = "missing", state
    elif den <= 0:
        f.band, f.why = "not_meaningful", f"denominator ≤ 0 ({what})"
        f.denominator = den
    else:
        rev = _revenue(engine, cik, f.period_end, filed) if f.period_end else None
        f.denominator = den
        if rev and den < NI_MIN_SHARE * rev:
            f.band, f.why = "not_meaningful", "denominator below 1% of revenue"
        else:
            f.share = f.amount / den
            f.band = band(f.share)


NEAR_MISS = re.compile(r"estimat\w*|catch[- ]up|profitability|service agreements?", re.I)


def near_misses(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    cik: str,
    accessions: list[str] | None = None,
    n: int = 3,
) -> list[tuple[int, str, str]]:
    """When the finder finds nothing: the `n` best candidate sentences (score, accession,
    first 200 characters) — estimate wording 3, a $ amount 2, what it moved 1, a direction
    1, service-agreement wording 1 — so the log shows why none qualified."""
    if corpus is None:
        return []
    norm = normalize_cik(cik) or cik
    scored: list[tuple[int, str, str]] = []
    for a in annual_reports(engine, corpus, norm, accessions=accessions):
        for d in corpus.execute(
            "SELECT text FROM document WHERE accession = ? AND doc_type IN ('10-K', '10-KT', "
            "'20-F', '40-F')",
            (a.accession,),
        ).fetchall():
            text = d[0]
            done: set[int] = set()
            for m in NEAR_MISS.finditer(text):
                s, e = sentence_at(text, m.start())
                if s in done or e - s > 1500:
                    continue
                done.add(s)
                sent = text[s:e]
                score = (
                    3 * bool(ESTIMATE.search(sent))
                    + 2 * bool(re.search(r"\$\s?\d", sent))
                    + any(rx.search(sent) for _, rx in OBJECTS)
                    + bool(UP.search(sent) or DOWN.search(sent))
                    + bool(re.search(r"service agreements?", sent, re.I))
                )
                scored.append((score, a.accession, clean(sent)[:200]))
    scored.sort(key=lambda x: -x[0])
    return scored[:n]


def recurrence(findings: list[Finding]) -> str:
    """'income-increasing' / 'income-decreasing' when the dominant change of each of three
    disclosures has the same sign (D-M04-17, S2.7), else ''."""
    by_acc: dict[str, Finding] = {}
    for f in findings:
        if f.share is None and f.amount == 0:
            continue
        cur = by_acc.get(f.accession)
        if cur is None or abs(f.share or 0) > abs(cur.share or 0):
            by_acc[f.accession] = f
    if len(by_acc) < DISCLOSURES:
        return ""
    signs = {1 if f.amount > 0 else -1 for f in by_acc.values()}
    if len(signs) == 1:
        return "income-increasing" if signs == {1} else "income-decreasing"
    return ""


def recurrence_rows(rows: list[sqlite3.Row]) -> str:
    """`recurrence` on stored `estimate_change` rows (the tab)."""
    by_acc: dict[str, tuple[float, float]] = {}
    for r in rows:
        share = abs(float(r["share"])) if r["share"] is not None else 0.0
        cur = by_acc.get(r["accession"])
        if cur is None or share > cur[0]:
            by_acc[r["accession"]] = (share, float(r["amount"]))
    if len(by_acc) < DISCLOSURES:
        return ""
    signs = {1 if a > 0 else -1 for _, a in list(by_acc.values())[:DISCLOSURES]}
    if len(signs) == 1:
        return "income-increasing" if signs == {1} else "income-decreasing"
    return ""


# --- Storage --------------------------------------------------------------------------------


def store(
    engine: sqlite3.Connection,
    findings: list[Finding],
    cik: str,
    now_iso: str,
    baseline: bool,
) -> None:
    """Upsert this scan's rows (owner answers kept). A row whose sentence is no longer found
    is deleted when it has neither an owner answer nor a linked review item; one that has
    either is kept unchanged as history — its `computed_at` stays at the last pass that
    found it, which marks it "no longer found" (`superseded`; Part 6 re-run 1). Caller owns
    the transaction."""
    keys = set()
    for f in findings:
        keys.add((f.accession, f.start))
        engine.execute(
            "INSERT INTO estimate_change (cik, accession, start_offset, doc_ref, form, filed, "
            "fiscal_label, period_end, kind, amount, basis, denominator, denominator_what, share, "
            "band, quote, passage_id, baseline, first_seen_at, computed_at) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (cik, accession, start_offset) DO UPDATE SET doc_ref = excluded.doc_ref, "
            "form = excluded.form, filed = excluded.filed, fiscal_label = excluded.fiscal_label, "
            "period_end = excluded.period_end, kind = excluded.kind, amount = excluded.amount, "
            "basis = excluded.basis, denominator = excluded.denominator, "
            "denominator_what = excluded.denominator_what, share = excluded.share, "
            "band = excluded.band, quote = excluded.quote, passage_id = excluded.passage_id, "
            "computed_at = excluded.computed_at",
            (
                f.cik,
                f.accession,
                f.start,
                f.doc_ref,
                f.form,
                f.filed,
                f.fiscal_label,
                f.period_end,
                f.kind,
                f.amount,
                f.basis,
                f.denominator,
                f.denominator_what or f.why,
                f.share,
                f.band,
                f.quote,
                f.passage_id,
                int(baseline),
                now_iso,
                now_iso,
            ),
        )
    for r in engine.execute(
        "SELECT accession, start_offset FROM estimate_change WHERE cik = ? AND "
        "owner_outcome IS NULL AND item_id IS NULL",
        (cik,),
    ).fetchall():
        if (r[0], r[1]) not in keys:
            engine.execute(
                "DELETE FROM estimate_change WHERE cik = ? AND accession = ? AND start_offset = ?",
                (cik, r[0], r[1]),
            )
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
        "detail = excluded.detail",
        (PASS_STATE.format(cik=cik), cik, now_iso, f"{len(findings)} sentence(s)"),
    )


def stored(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT * FROM estimate_change WHERE cik = ? ORDER BY filed DESC, start_offset",
        (normalize_cik(cik) or cik,),
    ).fetchall()


def last_pass(engine: sqlite3.Connection, cik: str) -> str | None:
    r = engine.execute(
        "SELECT fetched_at FROM refresh_state WHERE name = ?", (PASS_STATE.format(cik=cik),)
    ).fetchone()
    return r[0] if r else None


def superseded(engine: sqlite3.Connection, cik: str, rows: list[sqlite3.Row]) -> set[tuple]:
    """(accession, offset) of kept rows the company's latest pass no longer found: an
    answered or linked row keeps its last `computed_at`; every row a pass finds gets that
    pass's time (recorded in `refresh_state`)."""
    last = last_pass(engine, normalize_cik(cik) or cik)
    if last is None:
        return set()
    return {(r["accession"], r["start_offset"]) for r in rows if r["computed_at"] < last}


def current(engine: sqlite3.Connection, cik: str, rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    gone = superseded(engine, cik, rows)
    return [r for r in rows if (r["accession"], r["start_offset"]) not in gone]


# --- Catch-up revenue (ASC 606 tag) ---------------------------------------------------------


@dataclass
class CatchUp:
    years: list[tuple[str, float, str]]  # (label, value, accession)
    flag: str  # "same sign 3 years" or ""


def catch_up(engine: sqlite3.Connection, cik: str) -> CatchUp | None:
    from engine.financials.quality import Facts

    fx = Facts(engine, cik)
    pts = fx.fy("revenue_prior_obligations")
    if not pts:
        return None
    years = [(fiscal_label(e), v.value, v.accession) for e, v in sorted(pts.items())]
    last = [v for _, v, _ in years[-3:]]
    flag = ""
    if len(last) == 3 and (all(v > 0 for v in last) or all(v < 0 for v in last)):
        flag = "same sign 3 years"
    return CatchUp(years, flag)
