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
from engine.financials.text import clean, doc_scale, numbers, sentences
from engine.sec.asof import facts_as_of
from engine.sec.identity import normalize_cik

NOTE_BELOW, ELEVATED_FROM = 0.10, 0.25  # D-M04-17 starting values
NI_MIN_SHARE = 0.01
ANNUAL_FORMS = ("10-K", "10-KT", "20-F", "40-F")
DISCLOSURES = 3

QUERY = (
    '"change in estimate" OR "changes in estimate" OR "changes in estimates" OR '
    '"change in accounting estimate" OR "changes in accounting estimates" OR "useful life" OR '
    '"useful lives" OR "catch-up" OR "booking rate" OR "booking rates" OR '
    '"estimated profitability" OR "estimate changes"'
)
ESTIMATE = re.compile(
    r"change[sd]? in (?:accounting )?estimates?|estimate changes|useful li(?:fe|ves)|"
    r"catch[- ]up|booking rates?|estimated profitability|changes? (?:in|to) (?:the )?estimated",
    re.I,
)
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
YEAR = re.compile(r"\b(?:fiscal (?:year )?)?((?:19|20)\d{2})\b")
PER_SHARE = re.compile(r"^\s*(?:per|a)\s+(?:basic|diluted|share)", re.I)


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
    prev_end = 0
    last_basis, last_dir = None, 0
    for n in numbers(sentence, 0, len(sentence), scale):
        if "$" not in n.raw and not re.search(r"million|billion|thousand", n.raw, re.I):
            prev_end = n.end
            continue
        if PER_SHARE.match(sentence[n.end : n.end + 20]):
            prev_end = n.end
            continue
        window = sentence[prev_end : n.start]
        basis = None
        best: tuple[int, int] = (-1, 0)
        for name, rx in OBJECTS:  # the object nearest the amount; "net earnings" over "earnings"
            for m in rx.finditer(window):
                if (m.end(), -m.start()) > best:
                    best, basis = (m.end(), -m.start()), name
        d = _direction(window)
        if basis is None:
            basis, d = last_basis, d or last_dir
        if basis is None or d == 0:
            prev_end = n.end
            continue
        sign = d * (-1 if basis == "expense" else 1)
        years = YEAR.findall(window)
        after = YEAR.findall(sentence[n.end : n.end + 30])
        before = YEAR.findall(sentence[: n.start])
        year = years[-1] if years else after[0] if after else before[-1] if before else None
        out.append(Candidate(sign * n.value, basis, n.raw, year))
        last_basis, last_dir, prev_end = basis, d, n.end
    return out


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
    engine: sqlite3.Connection, corpus: sqlite3.Connection, cik: str, n: int = DISCLOSURES
) -> list[Annual]:
    """The newest `n` annual reports (original forms) with stored text, newest first. A
    company outside the filing index (GE, a reference case) uses its stored documents and the
    filing dates of its facts."""
    marks = ",".join("?" * len(ANNUAL_FORMS))
    rows = engine.execute(
        f"SELECT f.accession, f.form, f.filed, f.report_date FROM filing f JOIN filing_cik c ON "
        f"c.accession = f.accession WHERE c.cik = ? AND f.form IN ({marks}) "
        "ORDER BY f.filed DESC, f.accession DESC",
        (cik, *ANNUAL_FORMS),
    ).fetchall()
    out = [Annual(r["accession"], r["form"], r["filed"], r["report_date"]) for r in rows[:n]]
    if out:
        return out
    docs = corpus.execute(
        "SELECT DISTINCT accession, doc_type FROM document WHERE cik = ? AND doc_type IN "
        f"({marks})",
        (cik, *ANNUAL_FORMS),
    ).fetchall()
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


def scan(engine: sqlite3.Connection, corpus: sqlite3.Connection | None, cik: str) -> list[Finding]:
    """Estimate-change findings in the company's last three annual reports (0 requests)."""
    from engine.search.query import search

    norm = normalize_cik(cik) or cik
    if corpus is None:
        return []
    out: list[Finding] = []
    for a in annual_reports(engine, corpus, norm):
        label, end = report_fy(engine, norm, a)
        hits = search(corpus, QUERY, ciks=[norm], accessions=[a.accession], limit=200)
        seen: set[tuple[int, int]] = set()
        for h in sorted(hits, key=lambda h: (h.doc_id, h.start)):
            text = corpus.execute(
                "SELECT text FROM document WHERE doc_id = ?", (h.doc_id,)
            ).fetchone()[0]
            scale = doc_scale(text)
            for s, e in sentences(text, h.start, h.end):
                if (h.doc_id, s) in seen:
                    continue
                seen.add((h.doc_id, s))
                sent = text[s:e]
                # the estimate wording may sit in the sentence before ("… adjusted the useful
                # life … The effect of this change … was …"): look back up to 400 characters
                context = text[max(h.start, s - 400) : e]
                if not ESTIMATE.search(context) or HYPOTHETICAL.search(sent):
                    continue
                cands = candidates(sent, scale)
                best = pick(cands)
                if best is None:
                    continue
                fy = f"FY{best.year}" if best.year else label
                pend = _year_end(engine, norm, fy, end) if fy else None
                f = Finding(
                    norm,
                    a.accession,
                    f"{a.accession}/{h.filename}",
                    a.form,
                    a.filed,
                    s,
                    clean(sent),
                    kind_of(context),
                    best.amount,
                    best.basis,
                    fy or "unknown",
                    pend,
                    passage_id=h.passage_id,
                    others=[f"{c.raw} ({c.basis})" for c in cands if c is not best],
                )
                den, what, state = _denominator(engine, norm, best.basis, pend, a.filed)
                f.denominator_what = what
                if den is None:
                    f.band, f.why = "missing", state
                elif den <= 0:
                    f.band, f.why = "not_meaningful", f"denominator ≤ 0 ({what})"
                    f.denominator = den
                else:
                    rev = _revenue(engine, norm, pend, a.filed) if pend else None
                    f.denominator = den
                    if rev and den < NI_MIN_SHARE * rev:
                        f.band, f.why = "not_meaningful", "denominator below 1% of revenue"
                    else:
                        f.share = best.amount / den
                        f.band = band(f.share)
                out.append(f)
    return out


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
    """Upsert this scan's rows (owner answers kept); a row whose sentence is no longer found
    (and has no answer) is deleted. Caller owns the transaction."""
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
        "owner_outcome IS NULL",
        (cik,),
    ).fetchall():
        if (r[0], r[1]) not in keys:
            engine.execute(
                "DELETE FROM estimate_change WHERE cik = ? AND accession = ? AND start_offset = ?",
                (cik, r[0], r[1]),
            )


def stored(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT * FROM estimate_change WHERE cik = ? ORDER BY filed DESC, start_offset",
        (normalize_cik(cik) or cik,),
    ).fetchall()


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
