"""M05 Part 2: committed future spend (docs/M05_FUTURE_SPEND.md rules 5–8; D-M05-2, -3,
D-M05-18…; D-SEC-31; D-STO-32).

Reads stored facts and stored corpus text only (0 requests).

- **XBRL, per tag (D-SEC-31):** every instant of `purchase_obligation`,
  `purchase_obligation_unrecorded`, `purchase_obligation_recorded` and
  `contractual_obligation` — one concept per tag, never merged. A tag's scope is "as tagged"
  unless a quote at the same date states the same amount (±1%), which labels it (Meta's
  `Unrecorded…` = leases not yet commenced).
- **Text finder (rule 7):** a narrow pass over the main documents of stored 10-K / 10-Q
  filings. A sentence is read when it names a commitment (purchase obligations, supply and
  capacity, aircraft purchase commitments, leases not yet commenced, ...) or customer
  deposits. Each dollar amount in it gets a category from the words tied to it, a date
  (the sentence's "as of", else the report's period end), the cancellable flag
  ("cancelable / rescheduled / adjustable" in the sentence or the next one; "non-cancelable"
  never sets it) and the after-period flag (signed after the period). Amounts set aside, with
  the reason: no dollar amount, table rows (schedules are deferred, S2.3), hypothetical or
  forward-looking wording before the amount, a change rather than a balance, a schedule
  line, an earlier date (a comparative), a repeat; since live check 1 (D-M05-25) also a period
  charge / provision / flow, the earlier amount of "from $X … to $Y", a trade-in or
  contingent repurchase commitment, a prepaid balance. Several dates with as many amounts are
  paired in order; a sentence about leases not yet commenced is always that line; an amount
  is read once even when two clipped spans overlap. Quotes are cut from the stored text by
  offset and verified against the stored passage (D21); an unverified quote is never stored.
- **`commitment_cover` (rule 6, D-M05-3):** numerator = the stated supply-and-capacity total
  (fabless, outsourced) or the PP&E total (every other channel); other categories are shown
  beside, never added; leases not yet commenced and amounts signed after the period are
  separate dated lines, never summed. Denominator = TTM cost of revenue (fabless,
  outsourced) or TTM capex (others), at the commitment's date. The cover is compared with
  the same series a year earlier (±10%† → RISING / FALLING, else FLAT); no point a year
  earlier, or only a different series there → `short_history`, the other series shown across
  a labelled break.

Every † value is a labelled starting value, calibrated at tuning, not on the watchlist
(D32). Labelled "hypothesis, not backtested".
"""

from __future__ import annotations

import calendar
import json
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date, datetime

from engine.financials.text import clean, doc_scale, docs_for, numbers, passages_for, sentence_at
from engine.future_spend import channels as channels_mod
from engine.llm.verify import quote_found
from engine.sec.asof import facts_as_of
from engine.sec.identity import normalize_cik
from engine.sec.xbrl_facts import get_series

FINDER_VERSION = "commit-2"  # live check 1 fixes (D-M05-25)
STATE_KEY = "m05_commit:{cik}"
LABEL = "hypothesis, not backtested"
COVER_STEP = 0.10  # † ±10% YoY sets RISING / FALLING (as bookings_cover)
MARK_GAP = 0.05  # † XBRL and text more than 5% apart → both shown with a mark
LABEL_MATCH = 0.01  # a quote within 1% of a tag's value labels the tag's scope
STALE_DAYS = 100  # a commitment ending this long before the newest report is not current
COMPARATIVE_DAYS = 20  # a stated date this far before the period end is a comparative
MAIN_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")
XBRL_CONCEPTS = (
    ("purchase_obligation", "us-gaap:PurchaseObligation"),
    ("purchase_obligation_unrecorded",
     "us-gaap:UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount"),
    ("purchase_obligation_recorded", "us-gaap:RecordedUnconditionalPurchaseObligation"),
    ("contractual_obligation", "us-gaap:ContractualObligation"),
)  # fmt: skip
XBRL_NUMERATOR_TAG = "us-gaap:PurchaseObligation"  # fallback numerator, fabless / outsourced
CATEGORY_LABEL = {
    "supply_capacity": "supply and capacity",
    "ppe": "PP&E",
    "cloud": "cloud services",
    "investment": "investments",
    "other": "other",
    "purchase_total": "purchase obligations (scope not split)",
    "lease_not_commenced": "leases not yet commenced",
    "customer_deposit": "customer deposits",
    "as_tagged": "as tagged",
}

_MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|"
           "December")  # fmt: skip
_DATE = re.compile(rf"\b({_MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})\b")
_AS_OF_DATE = re.compile(rf"\b(?:as of|at)\s+({_MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})\b", re.I)
_EVENT_DATE = re.compile(
    rf"\b(?:in|on|during)\s+({_MONTHS})(?:\s+(\d{{1,2}}),)?\s+(\d{{4}})\b", re.I
)
_SIGNED = re.compile(r"\b(?:entered into|signed|executed|agreed to|committed to)\b", re.I)
_SUBSEQUENT = re.compile(
    r"\bsubsequent to (?:the end of )?(?:the |our )?(?:quarter|period|fiscal|year)|"
    r"\bsubsequent event|\bafter the end of the (?:quarter|period|fiscal year)",
    re.I,
)
TRIGGER = re.compile(
    r"purchase (?:obligation|commitment)s?|"
    r"(?:contractual|capital|purchase|firm|unconditional|non-?cancell?able) "
    r"(?:commitment|obligation)s?|"
    r"commit(?:ted|ments?) to (?:purchase|acquire|buy|spend)|"
    r"commitments (?:of|for|totaling|totalling|were|was)\b|"
    r"supply and capacity|capacity obligations?|"
    r"aircraft (?:purchase|order|delivery) (?:commitment|obligation)s?|"
    r"not yet commenced",
    re.I,
)
DEPOSIT = re.compile(
    r"customer (?:deposits|prepayments|advances)|"
    r"(?:prepayments|advances|deposits) (?:received )?from customers|"
    r"advance payments from customers",
    re.I,
)
_CANCEL = re.compile(
    r"\b(non-?|not\s+|un)?(cancell?able|cancell?ed|reschedul(?:ed|able)|adjustable)\b", re.I
)
_MODAL = re.compile(r"\b(?:could|may|might|would)\b", re.I)
_FORWARD = re.compile(
    r"\b(?:expect|anticipate|plan|intend|estimate|project|forecast)(?:s|ed|ing)?\b", re.I
)
_CHANGE_BEFORE = re.compile(
    r"\b(?:increase|decrease|grew|rose|fell|declin\w*|up|down|higher|lower|change)\w*"
    r"(?:\s+(?:of|by))?(?:\s+(?:approximately|about))?\s*$",
    re.I,
)
_SCHEDULE = re.compile(
    r"\b(?:due|payable)\s+(?:in|within|during)\b|\bremainder of\b|\bthereafter\b|"
    r"\bin (?:the )?(?:next|following) (?:twelve|12)\b|\bin fiscal (?:year )?\d{4}\b|"
    r"\bin (?:fiscal )?20\d\d\b",
    re.I,
)
# Period flows (P&L charges, provisions, expenses, amounts "for the quarter"), not balances
# (live check 1: NVDA's provisions and charges, MRVL's restructuring expense).
_FLOW_WORDS = re.compile(
    r"\b(?:charges?|provisions? (?:for|release)|provision releases?|(?<!prepaid )expenses?|"
    r"expensed|restructuring|gains?|impairments?|write-?(?:offs?|downs?)|incurred|"
    r"non-recurrence)\b",
    re.I,
)
_FLOW_PERIOD = re.compile(
    r"\b(?:for|during) (?:the )?(?:(?:first|second|third|fourth) (?:quarter|half)|"
    r"fiscal (?:years?|quarters?) (?:20\d\d|ended))\b|"
    r"\b(?:three|six|nine|twelve)(?: and (?:three|six|nine|twelve))? months ended\b|"
    r"\b(?:fiscal )?years? ended\b|\bquarters? ended\b",
    re.I,
)
_NOT_PURCHASE = re.compile(r"\btrade-?in commitments?\b|\brepurchase commitments?\b", re.I)
_PREPAID = re.compile(r"\bprepaid\b", re.I)
_LEASE_NOT_COMMENCED = re.compile(
    r"\bleases?\b.*\b(?:not yet commenced|have not commenced|had not commenced|yet to commence)",
    re.I | re.S,
)
_LIST_GAP = re.compile(r"^\s*(?:,\s*)?(?:and\s+)?$", re.I)
_FROM_BEFORE = re.compile(r"\bfrom\s*$", re.I)
_TO_GAP = re.compile(r"^[^$.;]{0,40}\bto\s*$", re.I)
_YEAR_LIST = re.compile(r",?\s*and\s+(\d{4})\b")  # used with .match(sent, pos)
_RESPECTIVELY = re.compile(r"\brespectively\b", re.I)
REASON_FLOW = "a period charge/provision, not an outstanding commitment"
REASON_PERIOD = "an amount for a period (a flow), not an outstanding commitment"
REASON_FROM = "earlier amount in a from–to sentence"
REASON_NOT_PURCHASE = ("not a purchase obligation (aircraft trade-in or contingent repurchase "
                       "commitment)")  # fmt: skip
REASON_PREPAID = "a prepayment (an asset), not an outstanding commitment"
_FOR_LEAD = re.compile(
    r"^\s*(?:,\s*)?(?:of|for|in|related to|relating to|to purchase|to acquire|"
    r"primarily (?:for|related to))\b",
    re.I,
)
# Category words, first match wins, read in the words tied to the amount.
_CATEGORIES = (
    ("lease_not_commenced", re.compile(r"not yet commenced|have not commenced|yet to commence",
                                       re.I)),
    ("customer_deposit", DEPOSIT),
    ("cloud", re.compile(r"\bcloud\b", re.I)),
    ("investment", re.compile(r"\binvest(?:ment|ing)?s?\b", re.I)),
    ("other", re.compile(r"non-inventory|\bother\b", re.I)),
    ("ppe", re.compile(
        r"property,? plant|capital expenditure|\bconstruction\b|\baircraft\b|\bequipment\b|"
        r"\bfacilit(?:y|ies)\b|data cent(?:er|re)s?|\bbuildings?\b|capital projects?|"
        r"\bfleet\b|\bvessels?\b|\brail ?cars?\b|\bfabs?\b", re.I)),
    ("supply_capacity", re.compile(
        r"\binventory\b|\bsupply\b|\bcapacity\b|\bwafers?\b|\bcomponents?\b|\bmaterials?\b|"
        r"\bmanufactur\w*|\bmerchandise\b|\bgoods\b|\bfuel\b", re.I)),
)  # fmt: skip


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _month(name: str) -> int:
    return _MONTHS.split("|").index(name.capitalize()) + 1


def _as_date(m: re.Match) -> date | None:
    try:
        y, mo = int(m.group(3)), _month(m.group(1))
        return date(y, mo, int(m.group(2))) if m.group(2) else _month_end(y, mo)
    except ValueError, IndexError:
        return None


def listed_dates(sent: str) -> list[tuple[int, date]]:
    """Every stated date in order, with "December 31, 2025 and 2024" read as two dates
    (offset in `sent`, date)."""
    out: list[tuple[int, date]] = []
    for m in _DATE.finditer(sent):
        d = _as_date(m)
        if d is None:
            continue
        out.append((m.start(), d))
        y = _YEAR_LIST.match(sent, m.end())
        if y and not (d.month == 2 and d.day == 29):
            out.append((y.start(1), d.replace(year=int(y.group(1)))))
    return out


def _m(x: float | None) -> str:
    if x is None:
        return "—"
    sign = "−" if x < 0 else ""
    x = abs(x)
    return f"{sign}${x / 1e9:,.2f}B" if x >= 1e9 else f"{sign}${x / 1e6:,.0f}M"


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:+.1%}".replace("-", "−")


# --- Text finder ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    category: str
    amount: float
    as_of: str
    start: int  # sentence span
    end: int
    amount_start: int
    amount_end: int
    raw: str
    quote: str
    scope_label: str
    cancellable: bool
    after_period: bool
    stated_date: str | None = None
    passage_id: int | None = None


@dataclass(frozen=True)
class SetAside:
    start: int
    reason: str
    quote: str
    raw: str = ""


@dataclass
class TextScan:
    findings: list[Finding] = field(default_factory=list)
    set_aside: list[SetAside] = field(default_factory=list)
    sentences: int = 0


def classify(window: str) -> str | None:
    for cat, rx in _CATEGORIES:
        if rx.search(window):
            return cat
    return None


def cancellable(text: str, s: int, e: int) -> str:
    """'' or where the cancellable wording is ("in the sentence", "in the next sentence");
    "non-cancelable", "not cancellable" and "uncancelled" never count."""
    for where, (a, b) in (("in the sentence", (s, e)), ("in the next sentence", _next(text, e))):
        for m in _CANCEL.finditer(text, a, b):
            if not m.group(1):
                return where
    return ""


def _next(text: str, e: int) -> tuple[int, int]:
    """The next sentence of the same paragraph (empty span after a blank line)."""
    gap = text[e : e + 4]
    if "\n\n" in gap or e >= len(text):
        return e, e
    a, b = sentence_at(text, min(len(text) - 1, e + 1))
    return (a, b) if a >= e else (e, e)


def scan_text(text: str, period_end: str | None) -> TextScan:
    """Commitment and deposit amounts in one stored document (pure; offsets into `text`)."""
    out = TextScan()
    scale = doc_scale(text)
    pe = date.fromisoformat(period_end) if period_end else None
    seen: set[tuple[int, int]] = set()
    dup: set[tuple[str, float, str, bool]] = set()
    read: set[int] = set()  # amount offsets already read: overlapping spans read each once
    hits = sorted([m.start() for m in TRIGGER.finditer(text)]
                  + [m.start() for m in DEPOSIT.finditer(text)])  # fmt: skip
    for pos in hits:
        s, e = sentence_at(text, pos)
        if (s, e) in seen or any(a <= pos < b for a, b in seen):
            continue
        seen.add((s, e))
        out.sentences += 1
        _sentence(text, s, e, scale, pe, out, dup, read)
    return out


def _category(text: str, sent: str, s: int, amounts: list, i: int) -> str | None:
    """The category tied to amount `i`: the words after "of / for …", else the clause before."""
    n = amounts[i]
    lo = amounts[i - 1].end if i else s
    hi = amounts[i + 1].start if i + 1 < len(amounts) else s + len(sent)
    before, after = text[lo : n.start], text[n.end : hi]
    cat = classify(after) if _FOR_LEAD.search(after) else None
    if cat is None:
        tail = re.split(r",\s+(?:and\s+)?|;\s+", before)[-1] if i else before
        cat = classify(tail) or classify(before)
    return cat


def _sentence(text, s, e, scale, pe: date | None, out: TextScan, dup, read=None) -> None:
    sent = text[s:e]
    quote = clean(sent)
    short = quote[:220] + ("…" if len(quote) > 220 else "")
    if "\t" in sent:
        out.set_aside.append(SetAside(s, "table row (parsed schedules deferred, S2.3)", short))
        return
    if e - s > 1500:
        out.set_aside.append(SetAside(s, "span too long to be one sentence", short))
        return
    amounts = [n for n in numbers(text, s, e, scale) if "$" in n.raw]
    if read is not None:
        fresh = [n for n in amounts if n.start not in read]
        if amounts and not fresh:
            return  # every amount already read in an overlapping span
        amounts = fresh
        read.update(n.start for n in amounts)
    if not amounts:
        out.set_aside.append(SetAside(s, "no dollar amount", short))
        return
    head = text[s : amounts[0].start]
    if _MODAL.search(head):
        out.set_aside.append(SetAside(s, "hypothetical wording before the amount", short))
        return
    if _FORWARD.search(head):
        out.set_aside.append(SetAside(s, "forward-looking wording (guidance is M02's)", short))
        return
    sentence_date = _AS_OF_DATE.search(sent)
    sdate = _as_date(sentence_date) if sentence_date else None
    after_words = bool(_SUBSEQUENT.search(sent))
    event = None
    if _SIGNED.search(sent):
        for m in _EVENT_DATE.finditer(sent):
            d = _as_date(m)
            if d is not None and pe is not None and (d - pe).days > 5:
                event = d
                break
    cancel_where = cancellable(text, s, e)
    noncancel = bool(re.search(r"\bnon-?cancell?able\b", sent, re.I))
    # categories first: a list ("$2.8 billion and $160 million of customer advances") takes
    # the category of its last member; "from $X … to $Y": Y takes X's (live check 1)
    cats = [_category(text, sent, s, amounts, i) for i in range(len(amounts))]
    gaps = [text[amounts[i].end : amounts[i + 1].start] for i in range(len(amounts) - 1)]
    for i in range(len(amounts) - 2, -1, -1):
        if cats[i] is None and _LIST_GAP.match(gaps[i]):
            cats[i] = cats[i + 1]
    from_to = {
        i
        for i in range(len(amounts) - 1)
        if _FROM_BEFORE.search(text[amounts[i - 1].end if i else s : amounts[i].start])
        and _TO_GAP.match(gaps[i])
    }
    for i in sorted(from_to):
        cats[i + 1] = cats[i + 1] or cats[i]
    lease = bool(_LEASE_NOT_COMMENCED.search(sent))
    # several dates and as many amounts ("At June 30, 2026, and December 31, 2025, … were
    # $1,130 and $1,267"; "…, respectively"): paired in order
    dates = listed_dates(sent)
    paired: list[date] | None = None
    if (
        len(amounts) >= 2
        and len(dates) == len(amounts)
        and (_RESPECTIVELY.search(sent) or dates[-1][0] < amounts[0].start - s)
    ):
        paired = [d for _, d in dates]
    flow = _FLOW_WORDS.search(sent)
    period = _FLOW_PERIOD.search(sent)
    for i, n in enumerate(amounts):
        lo = amounts[i - 1].end if i else s
        hi = amounts[i + 1].start if i + 1 < len(amounts) else e
        before, after = text[lo : n.start], text[n.end : hi]
        if _CHANGE_BEFORE.search(before[-40:]):
            out.set_aside.append(SetAside(s, "a change, not a balance", short, n.raw))
            continue
        if _SCHEDULE.search(after[:60]) or _SCHEDULE.search(before[-50:]):
            out.set_aside.append(SetAside(s, "a schedule line (parsed schedules deferred, S2.3)",
                                          short, n.raw))  # fmt: skip
            continue
        if flow or period:
            out.set_aside.append(SetAside(s, REASON_FLOW if flow else REASON_PERIOD, short,
                                          n.raw))  # fmt: skip
            continue
        if _NOT_PURCHASE.search(sent):
            out.set_aside.append(SetAside(s, REASON_NOT_PURCHASE, short, n.raw))
            continue
        if _PREPAID.search(sent) and not DEPOSIT.search(sent):
            out.set_aside.append(SetAside(s, REASON_PREPAID, short, n.raw))
            continue
        if i in from_to:
            out.set_aside.append(SetAside(s, REASON_FROM, short, n.raw))
            continue
        cat = "lease_not_commenced" if lease else cats[i]
        if cat is None and TRIGGER.search(sent):
            cat = "purchase_total"
        if cat is None:
            out.set_aside.append(SetAside(s, "no commitment category tied to the amount", short,
                                          n.raw))  # fmt: skip
            continue
        own = _AS_OF_DATE.search(before) or _AS_OF_DATE.search(after)
        d = paired[i] if paired else (_as_date(own) if own else sdate)
        after_period = after_words or event is not None
        stated = event.isoformat() if event is not None else None
        if pe is not None and d is not None and not after_period:
            if (pe - d).days > COMPARATIVE_DAYS:
                why = f"comparative as of {d.isoformat()} (an earlier period, not this report's)"
                if paired:
                    why += "; dates paired with amounts in order"
                out.set_aside.append(SetAside(s, why, short, n.raw))
                continue
            if (d - pe).days > 5:
                after_period, stated = True, d.isoformat()
        as_of = pe.isoformat() if pe is not None else (d.isoformat() if d else "")
        if not as_of:
            out.set_aside.append(SetAside(s, "no date (no period end, none stated)", short,
                                          n.raw))  # fmt: skip
            continue
        k = (cat, round(n.value), as_of, after_period)
        if k in dup:
            out.set_aside.append(SetAside(s, "repeated (same amount stated earlier in the "
                                          "document)", short, n.raw))  # fmt: skip
            continue
        dup.add(k)
        label = CATEGORY_LABEL[cat] + (" (non-cancelable as stated)" if noncancel else "")
        out.findings.append(Finding(
            cat, n.value, as_of, s, e, n.start, n.end, n.raw, quote, label,
            bool(cancel_where) and cat != "customer_deposit", after_period, stated,
        ))  # fmt: skip


def verified(text: str, passage: str, f: Finding) -> bool:
    """The quote is the stored span, it holds the amount, and it is found in its passage."""
    if not (0 <= f.start <= f.amount_start < f.amount_end <= f.end <= len(text)):
        return False
    if (
        clean(text[f.start : f.end]) != f.quote
        or f.raw not in text[f.amount_start : f.amount_end + 1]
    ):
        return False
    return quote_found(f.quote, passage)


# --- The company's stored reports and the scan ------------------------------------------------


@dataclass(frozen=True)
class Report:
    accession: str
    form: str
    filed: str
    period_end: str | None


def reports(engine: sqlite3.Connection, cik: str) -> list[Report]:
    """Stored 10-K / 10-Q filings of the company (filing index), newest first."""
    marks = ",".join("?" * len(MAIN_FORMS))
    out = []
    for r in engine.execute(
        f"SELECT f.accession, f.form, f.filed, f.report_date FROM filing f JOIN filing_cik c "
        f"ON c.accession = f.accession WHERE c.cik = ? AND f.form IN ({marks}) "
        "ORDER BY f.filed DESC, f.accession DESC",
        (cik, *MAIN_FORMS),
    ):
        end = r["report_date"]
        if not end:
            got = engine.execute(
                "SELECT max(period_end) FROM fact WHERE accession = ?", (r["accession"],)
            ).fetchone()
            end = got[0] if got else None
        out.append(Report(r["accession"], r["form"], r["filed"], end))
    return out


def _main_doc(doc_type: str | None, form: str) -> bool:
    t = (doc_type or "").upper()
    return not t or t == form.upper() or t in MAIN_FORMS


@dataclass
class ReportScan:
    report: Report
    filename: str = ""
    findings: list[Finding] = field(default_factory=list)
    set_aside: list[SetAside] = field(default_factory=list)
    unverified: int = 0
    no_text: bool = False


@dataclass
class CompanyScan:
    cik: str
    reports: list[ReportScan] = field(default_factory=list)
    xbrl: dict[str, list] = field(default_factory=dict)  # tag → AsOfPoints
    rows_written: int = 0
    duplicates: int = 0  # repeated keys skipped at store

    @property
    def newest_period(self) -> str | None:
        ends = [r.report.period_end for r in self.reports if r.report.period_end]
        return max(ends) if ends else None


def _passage_text(corpus, doc_id: int, text: str, s: int, e: int) -> tuple[int | None, str]:
    for pid, a, b in passages_for(corpus, doc_id):
        if a <= s and e <= b:
            return pid, text[a:b]
    return None, text  # no passages, or the sentence straddles two: the document itself


def scan_company(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, cik: str, today: str
) -> CompanyScan:
    """Read the stored reports and the purchase-obligation tags (no writes)."""
    norm = normalize_cik(cik) or cik
    cs = CompanyScan(norm)
    for rep in reports(engine, norm):
        rs = ReportScan(rep)
        docs = [d for d in docs_for(corpus, rep.accession) if _main_doc(d.doc_type, rep.form)]
        if not docs:
            rs.no_text = True
        for d in docs[:1]:
            rs.filename = d.filename
            ts = scan_text(d.text, rep.period_end)
            rs.set_aside = ts.set_aside
            for f in ts.findings:
                pid, passage = _passage_text(corpus, d.doc_id, d.text, f.start, f.end)
                if verified(d.text, passage, f):
                    rs.findings.append(replace(f, passage_id=pid))
                else:
                    rs.unverified += 1  # never stored (D21)
        cs.reports.append(rs)
    for concept, tag in XBRL_CONCEPTS:
        pts = facts_as_of(engine, norm, concept, today, ptype="I").points
        if pts:
            by_end: dict = {}
            for p in pts:  # one point per instant (two fact rows can share an end)
                cur = by_end.get(p.end)
                if cur is None or (p.filed or "") >= (cur.filed or ""):
                    by_end[p.end] = p
            cs.xbrl[tag] = [by_end[k] for k in sorted(by_end)]
    return cs


def store(engine: sqlite3.Connection, cs: CompanyScan, now: datetime) -> int:
    """Replace the company's rows (first_seen_at carried by key). Caller owns the transaction."""
    ts = now.isoformat(timespec="seconds")
    first = {r[0]: r[1] for r in engine.execute(
        "SELECT key, first_seen_at FROM future_commitment WHERE cik = ?", (cs.cik,))}  # fmt: skip
    engine.execute("DELETE FROM future_commitment WHERE cik = ?", (cs.cik,))
    text_rows = [(rs, f) for rs in cs.reports for f in rs.findings]
    n = 0
    keys: set[str] = set()  # a key is written once: a repeat never fails the pass
    for rs, f in text_rows:
        key = f"text:{rs.report.accession}/{rs.filename}@{f.amount_start}"
        if key in keys:
            cs.duplicates += 1
            continue
        keys.add(key)
        engine.execute(
            "INSERT INTO future_commitment (key, cik, as_of, stated_date, category, amount, "
            "source, quote, accession, filename, form, filed, start_offset, end_offset, "
            "amount_start, amount_end, passage_id, scope_label, cancellable, after_period, "
            "grade, finder_version, first_seen_at, computed_at) VALUES (?, ?, ?, ?, ?, ?, "
            "'text', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'A', ?, ?, ?)",
            (key, cs.cik, f.as_of, f.stated_date, f.category, f.amount, f.quote,
             rs.report.accession, rs.filename, rs.report.form, rs.report.filed, f.start, f.end,
             f.amount_start, f.amount_end, f.passage_id, f.scope_label,
             int(f.cancellable), int(f.after_period), FINDER_VERSION, first.get(key, ts), ts),
        )  # fmt: skip
        n += 1
    for tag, pts in cs.xbrl.items():
        for p in pts:
            key = f"xbrl:{tag}@{p.end}"
            if key in keys:
                cs.duplicates += 1
                continue
            keys.add(key)
            label = tag_label(p.end, float(p.value), [f for _, f in text_rows])
            engine.execute(
                "INSERT INTO future_commitment (key, cik, as_of, category, amount, source, tag, "
                "accession, filed, scope_label, cancellable, after_period, grade, "
                "finder_version, first_seen_at, computed_at) VALUES (?, ?, ?, 'as_tagged', ?, "
                "'xbrl', ?, ?, ?, ?, 0, 0, 'A', ?, ?, ?)",
                (key, cs.cik, p.end, float(p.value), tag, p.accession, p.filed, label,
                 FINDER_VERSION, first.get(key, ts), ts),
            )  # fmt: skip
            n += 1
    cs.rows_written = n
    detail = json.dumps({"version": FINDER_VERSION, "reports": len(cs.reports),
                         "newest_period": cs.newest_period, "rows": n}, sort_keys=True)  # fmt: skip
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
        "detail = excluded.detail",
        (STATE_KEY.format(cik=cs.cik), "M05 Part 2", ts, detail),
    )
    return n


def scan_state(engine: sqlite3.Connection, cik: str) -> dict | None:
    """The last commitments pass for the company (`refresh_state` m05_commit:<cik>), or None."""
    row = engine.execute(
        "SELECT detail FROM refresh_state WHERE name = ?", (STATE_KEY.format(cik=cik),)
    ).fetchone()
    try:
        return json.loads(row["detail"]) if row and row["detail"] else None
    except json.JSONDecodeError:
        return None


def deposit_wording(engine: sqlite3.Connection, cik: str) -> str | None:
    """The newest customer-deposit sentence (Part 1's deposits mark, D-M05-11, rule 6):
    None = the commitments pass has not run for the company; "" = none found."""
    norm = normalize_cik(cik) or cik
    if scan_state(engine, norm) is None:
        return None
    r = engine.execute(
        "SELECT amount, as_of, form, accession, quote FROM future_commitment WHERE cik = ? AND "
        "category = 'customer_deposit' ORDER BY as_of DESC, filed DESC LIMIT 1",
        (norm,),
    ).fetchone()
    if r is None:
        return ""
    q = r["quote"] or ""
    return (f"{_m(r['amount'])} at {r['as_of']} ({r['form']} {r['accession']}): "
            f"“{q[:200]}{'…' if len(q) > 200 else ''}”")  # fmt: skip


def tag_label(end: str, value: float, findings: Iterable[Finding]) -> str:
    """ "as tagged; scope unstated", or labelled by a quote stating the same amount (±1%)."""
    for f in findings:
        if (
            f.as_of == end
            and not f.after_period
            and value
            and abs(f.amount / value - 1) <= LABEL_MATCH
        ):
            return f"labelled by the quote: {CATEGORY_LABEL[f.category]}"
    return "as tagged; scope unstated"


# --- commitment_cover ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Point:
    series: str  # "text:supply_capacity", "text:purchase_total", "xbrl:us-gaap:PurchaseObligation"
    as_of: str
    amount: float
    accession: str
    filed: str
    cancellable: bool
    quote: str | None
    form: str | None

    @property
    def label(self) -> str:
        if self.series.startswith("xbrl:"):
            return f"{self.series[5:]} (XBRL, as tagged)"
        return f"{CATEGORY_LABEL[self.series[5:]]} (text, verified quote)"


@dataclass(frozen=True)
class Denominator:
    what: str  # "TTM cost of revenue" | "TTM capex"
    value: float
    end: str
    basis: str  # TTM | FY
    accession: str
    filed: str


@dataclass
class Cover:
    cik: str
    numerator_category: str
    point: Point | None = None
    denom: Denominator | None = None
    prior: Point | None = None
    prior_denom: Denominator | None = None
    other_prior: Point | None = None  # a different series a year earlier (labelled break)
    missing: str | None = None
    marks: list[str] = field(default_factory=list)
    beside: list[str] = field(default_factory=list)
    leases: list[str] = field(default_factory=list)
    after_period: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    deposits: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)

    @property
    def value(self) -> float | None:
        if self.point is None or self.denom is None or self.denom.value <= 0:
            return None
        return self.point.amount / self.denom.value

    @property
    def prior_value(self) -> float | None:
        if self.prior is None or self.prior_denom is None or self.prior_denom.value <= 0:
            return None
        return self.prior.amount / self.prior_denom.value

    @property
    def change(self) -> float | None:
        if self.value is None or not self.prior_value:
            return None
        return self.value / self.prior_value - 1

    @property
    def state(self) -> str | None:
        if self.value is None:
            return None
        ch = self.change
        if ch is None:
            return "short_history"
        return "RISING" if ch >= COVER_STEP else "FALLING" if ch <= -COVER_STEP else "FLAT"


def _rows(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT * FROM future_commitment WHERE cik = ? ORDER BY as_of, filed, commitment_id",
        (cik,),
    ).fetchall()


def _point(series: str, r: sqlite3.Row) -> Point:
    return Point(series, r["as_of"], float(r["amount"]), r["accession"], r["filed"],
                 bool(r["cancellable"]), r["quote"], r["form"])  # fmt: skip


def series_points(rows: list[sqlite3.Row], series: str) -> dict[str, Point]:
    """One point per date: the newest filing; within it the largest stated amount."""
    out: dict[str, Point] = {}
    for r in rows:
        if r["after_period"]:
            continue
        if series.startswith("text:"):
            if r["source"] != "text" or r["category"] != series[5:]:
                continue
        elif r["source"] != "xbrl" or r["tag"] != series[5:]:
            continue
        p = _point(series, r)
        cur = out.get(p.as_of)
        if cur is None or (p.filed, p.amount) > (cur.filed, cur.amount):
            out[p.as_of] = p
    return out


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def _year_before(points: dict[str, Point], end: str) -> Point | None:
    return next((p for k, p in sorted(points.items()) if 350 <= _days(end, k) <= 380), None)


def denominator(engine: sqlite3.Connection, cik: str, lead: bool, end: str) -> Denominator | None:
    """TTM cost of revenue (fabless, outsourced) or TTM capex (others) within 10 days of
    `end`; at a fiscal year end the fiscal year is the TTM (D-M05-13)."""
    concept, what = ("cost_of_revenue", "TTM cost of revenue") if lead else ("capex", "TTM capex")
    for ptype in ("TTM", "FY"):
        for p in get_series(engine, cik, concept, ptype):
            v = p.latest.value
            if v and v > 0 and abs(_days(p.end, end)) <= 10:
                return Denominator(what, float(v), p.end, ptype, p.latest.accession or "",
                                   p.latest.filed or "")  # fmt: skip
    return None


def cover(
    engine: sqlite3.Connection, cik: str, channel: channels_mod.Channel, newest_period: str | None
) -> Cover:
    """`commitment_cover` from the stored rows (0 requests; nothing written)."""
    norm = normalize_cik(cik) or cik
    lead = channel.commitments_lead
    cat = "supply_capacity" if lead else "ppe"
    c = Cover(norm, cat)
    rows = _rows(engine, norm)
    newest = newest_period or max((r["as_of"] for r in rows), default=None)
    order = [f"text:{cat}"] + (
        ["text:purchase_total", f"xbrl:{XBRL_NUMERATOR_TAG}"] if lead else []
    )
    cands = {s: series_points(rows, s) for s in order}
    best: tuple[str, str] | None = None  # (as_of, series) newest first, priority on ties
    for s in order:
        if cands[s]:
            end = max(cands[s])
            if best is None or end > best[0]:
                best = (end, s)
    if best is not None and best[1].startswith("text:"):
        c.numerator_category = best[1][5:]  # purchase_total when only that is stated
    _lines(c, rows, newest)
    if best is None:
        c.missing = (f"no stated {CATEGORY_LABEL[cat]} commitment total"
                     + (" (other categories shown beside)" if c.beside else ""))  # fmt: skip
        return c
    end, s = best
    if newest and _days(newest, end) > STALE_DAYS:
        label = cands[s][end].label
        c.missing = f"last stated {end} ({label}), before the newest report ({newest})"
        return c
    c.point = cands[s][end]
    c.denom = denominator(engine, norm, lead, end)
    if c.denom is None:
        c.missing = f"no {'TTM cost of revenue' if lead else 'TTM capex'} at {end}"
        return c
    c.prior = _year_before(cands[s], end)
    if c.prior is not None:
        c.prior_denom = denominator(engine, norm, lead, c.prior.as_of)
    if c.prior is None or c.prior_denom is None:
        c.prior = None
        for other in order + [f"xbrl:{t}" for _, t in XBRL_CONCEPTS]:
            if other == s:
                continue
            pts = cands.get(other) if other in cands else series_points(rows, other)
            got = _year_before(pts or {}, end)
            if got is not None:
                c.other_prior = got
                break
    # XBRL vs text at the same date: > 5%† apart → both shown with a mark (rule 7)
    xb = series_points(rows, f"xbrl:{XBRL_NUMERATOR_TAG}")
    txt = {**series_points(rows, "text:purchase_total"), **series_points(rows, f"text:{cat}")}
    a = next((p for k, p in xb.items() if abs(_days(k, end)) <= 10), None)
    b = next((p for k, p in txt.items() if abs(_days(k, end)) <= 10), None)
    if a is not None and b is not None and b.amount:
        gap = a.amount / b.amount - 1
        if abs(gap) > MARK_GAP:
            pair = f"XBRL {XBRL_NUMERATOR_TAG} {_m(a.amount)} vs text {_m(b.amount)}"
            c.marks.append(f"mark: {pair} at {end} ({_pct(gap)}; > {MARK_GAP:.0%}† apart, both "
                           "shown)")  # fmt: skip
    return c


def _lines(c: Cover, rows: list[sqlite3.Row], newest: str | None) -> None:
    """Beside, lease, after-period, tag and deposit lines at the newest report's date."""
    for r in rows:
        when = r["as_of"]
        if (
            newest
            and when != newest
            and not (r["source"] == "xbrl" and abs(_days(newest, when)) <= 10)
        ):
            continue
        src = f"{r['form'] or 'XBRL'} {r['accession']}"
        flag = (
            " (cancelable / adjustable wording: flag shown, amount as stated)"
            if r["cancellable"]
            else ""
        )
        if r["after_period"]:
            c.after_period.append(f"signed after the period {_m(r['amount'])} "
                                  f"({CATEGORY_LABEL[r['category']]}; "
                                  f"{r['stated_date'] or 'date unstated'}; {src}; a separate dated "
                                  "line, never summed)")  # fmt: skip
        elif r["category"] == "lease_not_commenced":
            c.leases.append(f"leases not yet commenced {_m(r['amount'])} at {when} ({src}; a "
                            f"separate line, never summed)")  # fmt: skip
        elif r["category"] == "customer_deposit":
            c.deposits.append(f"customer deposit wording {_m(r['amount'])} at {when} ({src})")
        elif r["source"] == "xbrl":
            c.tags.append(f"{r['tag']} {_m(r['amount'])} at {when} ({r['scope_label']})")
        elif r["category"] != c.numerator_category:
            c.beside.append(f"{CATEGORY_LABEL[r['category']]} {_m(r['amount'])}{flag} ({src}; "
                            "beside, never added)")  # fmt: skip
    # a tag that stops: its last value, labelled (NVDA's PurchaseObligation, 2025-07-27)
    last: dict[str, sqlite3.Row] = {}
    for r in rows:
        if r["source"] == "xbrl":
            last[r["tag"]] = r
    for tag, r in sorted(last.items()):
        if newest and _days(newest, r["as_of"]) > STALE_DAYS:
            c.stale.append(f"{tag} last tagged {_m(r['amount'])} at {r['as_of']} (stopped; "
                           "series break labelled)")  # fmt: skip


def method_text(c: Cover, channel: channels_mod.Channel) -> str:
    parts = []
    if c.point is not None and c.denom is not None and c.value is not None:
        p, d = c.point, c.denom
        flag = (
            "; cancelable / adjustable wording: flag shown, amount as stated"
            if p.cancellable
            else ""
        )
        what = (
            CATEGORY_LABEL[c.numerator_category]
            if p.series.startswith("text:")
            else ("purchase obligations, scope as tagged (no stated text total)")
        )
        parts.append(f"commitments {what} {_m(p.amount)} at "
                     f"{p.as_of} [{p.label}; {p.form or 'XBRL'} {p.accession}{flag}] ÷ {d.what} "
                     f"{_m(d.value)} ({d.basis} at {d.end}) = {c.value:.2f} years")  # fmt: skip
        if c.prior is not None and c.prior_value is not None:
            parts.append(f"a year earlier {c.prior_value:.2f} ({c.prior.as_of}, same series): "
                         f"{_pct(c.change)} → {c.state} (±{COVER_STEP:.0%}†)")  # fmt: skip
        elif c.other_prior is not None:
            o = c.other_prior
            parts.append(f"no point a year earlier on this series (short_history); a year "
                         f"earlier on another series: {o.label} {_m(o.amount)} at {o.as_of} — "
                         "labelled break, not compared")  # fmt: skip
        else:
            parts.append("no point a year earlier (short_history)")
    elif c.point is not None:
        parts.append(f"commitments {_m(c.point.amount)} at {c.point.as_of} [{c.point.label}]")
    parts += c.marks
    if c.beside:
        parts.append("beside: " + "; ".join(c.beside))
    parts += c.leases + c.after_period
    if c.tags:
        parts.append("XBRL per tag (never merged): " + "; ".join(c.tags))
    parts += c.stale
    parts.append("own history only; " + channel.text())
    parts.append(LABEL)
    return "; ".join(x for x in parts if x)
