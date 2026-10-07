"""
financial_intelligence.py — Financial Intelligence Deep Dive (Step 16)

  1. guidance_revisions   — LLM-extracted forward guidance from a dedicated,
                             UNFILTERED fetch of the most recent earnings
                             filing (8-K/6-K body + Exhibit 99.1 press
                             release). The extractor pulls BOTH the new range
                             AND any explicitly-stated prior range
                             ("raising guidance from $80-83B to $82-85B") plus
                             a linked_asset if the text attributes the change
                             to a specific drug/program. Falls back to last
                             week's snapshot for direction/delta only when the
                             text doesn't state a prior range itself.
  2. cash_runway          — XBRL cash+ST-investments / operating cash flow ->
                             runway_months + R&D-allocation ratio. SCOPED TO
                             small_caps + private_watchlist only — runway
                             isn't a meaningful BD metric for large
                             multinational pharma, and their XBRL quarterly
                             cash-flow coverage (esp. foreign private issuers
                             like NVO/AZN) is frequently incomplete, which
                             previously surfaced as noisy "no data" warnings.
  3. product_revenue      — per-product revenue (Mounjaro/Zepbound,
                             Ozempic/Wegovy/Rybelsus, ...) extracted via LLM
                             from the same dedicated filing text (regex
                             fallback if no resolver / nothing found),
                             currency-aware, with QoQ trend vs last week.
  4. financial_pressure_signals — shelf registrations (S-3/S-1) + going-
                             concern/covenant/credit-rating language, for
                             competitors AND small caps.
"""

import os
import re
import time
from datetime import datetime, date
from typing import Optional

import requests

from tools.sec_edgar import (resolve_cik, resolve_cik_with_paths,
                             CIK_LOOKUP_METHOD, get_rd_spend,
                             get_company_filings, get_filing_text)
from tools.bd_tools  import resolve_filing_documents
from utils.text      import extract_relevant_paragraphs, sanitize_source_text_audit

USER_AGENT       = os.getenv("SEC_USER_AGENT", "PharmaAgent contact@pharmaagent.com")
HEADERS          = {"User-Agent": USER_AGENT}
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts"
REQUEST_DELAY    = 0.15


# ---------------------------------------------------------------------------
# XBRL candidate tags
# ---------------------------------------------------------------------------

CASH_TAGS = [
    ("us-gaap",   "CashAndCashEquivalentsAtCarryingValue"),
    ("us-gaap",   "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    ("ifrs-full", "CashAndCashEquivalents"),
]

ST_INVESTMENT_TAGS = [
    ("us-gaap",   "ShortTermInvestments"),
    ("us-gaap",   "MarketableSecuritiesCurrent"),
    ("us-gaap",   "AvailableForSaleSecuritiesCurrent"),
    ("ifrs-full", "OtherShortTermInvestments"),
]

OPERATING_CF_TAGS = [
    ("us-gaap",   "NetCashProvidedByUsedInOperatingActivities"),
    ("us-gaap",   "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
    ("ifrs-full", "CashFlowsFromUsedInOperatingActivities"),
]

RUNWAY_DISTRESSED_MONTHS = 12
RUNWAY_MODERATE_MONTHS   = 24

# R&D spend is a COMPONENT of operating burn, so R&D expressed as a percent of
# burn cannot legitimately exceed ~100%. When it does, the R&D figure and the
# operating-cash-flow burn figure are on inconsistent bases (different periods,
# or a cash-flow burn understated by large non-cash add-backs / working-capital
# swings) and any runway derived from them is unreliable. In that case we do NOT
# assert a "Distressed" call — we surface the figures with an integrity caveat.
# (Root case: Viking Therapeutics rendered "R&D 131.7% of burn → 8mo → Distressed"
# in the 2026-07-15 report while actually well-capitalized into 2028.)
RD_BURN_INCONSISTENCY_PCT = 100.0

SHELF_FORM_TYPES = ["S-3", "S-3ASR", "S-1", "S-1/A", "S-3/A"]

# ── 3c (NSP 109 item 1; ruling D3, TRACK §6.34g) ────────────────────────────
# compute_guidance_revision emits one of exactly four `direction` values, and
# until now they existed only as bare literals inside that function. A
# consumer deciding whether a guidance row is NEWS has to know which of them
# assert that something moved — and a consumer that re-lists the strings
# itself is a second spelling waiting to drift from this one.
#
# Three of the four declare movement. "Maintained" is the odd one: it is a
# real, correctly-computed answer that says the figures did NOT move, so a
# What's New section that treats it as a change re-reports a source that
# keeps restating the same guidance week after week (the 0031 failures).
#
# The set is DECLARED here rather than refactoring the emitting function,
# and test_fc3c_guidance_change_filter.py AST-pins this tuple equal to the
# literals compute_guidance_revision can actually assign — so the two cannot
# come apart even though the function still writes its own strings.
GUIDANCE_DIRECTIONS = ("Raised", "Lowered", "Maintained", "Initiated")
GUIDANCE_MOVEMENT_DIRECTIONS = ("Raised", "Lowered", "Initiated")


def guidance_direction_declares_movement(direction) -> bool:
    """True when a guidance record's own `direction` asserts that something
    moved — Raised, Lowered or Initiated. False for "Maintained" (the source
    restated the same figures), and False for anything absent, empty or not a
    string: a row whose direction nobody computed does not get to claim
    movement by default."""
    return (isinstance(direction, str)
            and direction in GUIDANCE_MOVEMENT_DIRECTIONS)

PRESSURE_SIGNAL_TERMS = {
    "Going Concern Language": ["going concern", "substantial doubt"],
    "Covenant Language":      ["covenant", "in default", "waiver of"],
    "Credit Rating Action":   ["credit rating", "downgrade", "negative outlook"],
}

REALLOCATION_ACCEL_TERMS = [
    "accelerat", "increase investment", "incremental investment",
    "ramping up", "ramp up", "additional investment", "ahead of plan",
    "prioritiz",
]

# value + unit, e.g. "$2.3 billion" / "$450 million" / "$1.2B"
DOLLAR_VALUE_RE = r"\$\s?([\d,]+(?:\.\d+)?)\s?(billion|million|bn|b|m)\b"

_PERIOD_RE_VARIANTS = [
    re.compile(r"Q(\d)\s*[, ]?\s*(\d{4})", re.IGNORECASE),
    re.compile(r"(\d)Q\s*(\d{2,4})", re.IGNORECASE),
    re.compile(r"(\d{4})\s*Q(\d)", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Low-level XBRL helpers (used only for small_caps cash_runway)
# ---------------------------------------------------------------------------

def _get_company_facts(cik: str) -> dict:
    time.sleep(REQUEST_DELAY)
    try:
        resp = requests.get(f"{COMPANYFACTS_URL}/CIK{cik}.json", headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as e:
        print(f"  FinancialIntel: companyfacts fetch failed for CIK{cik}: {e}")
        return {}


def _latest_instant_value(facts_root: dict, candidate_tags: list[tuple]) -> Optional[dict]:
    best = None
    for taxonomy, tag in candidate_tags:
        fact_data = facts_root.get(taxonomy, {}).get(tag)
        if not fact_data:
            continue
        for unit_key, facts in fact_data.get("units", {}).items():
            for f in facts:
                if f.get("start"):
                    continue
                end = f.get("end")
                if not end:
                    continue
                if best is None or end > best["end"]:
                    best = {"end": end, "val": f.get("val"), "unit": unit_key}
    return best


def _latest_quarterly_flow(facts_root: dict, candidate_tags: list[tuple],
                            min_days: int = 75, max_days: int = 105) -> Optional[dict]:
    """Most recent ~quarterly duration fact. Falls back to scanning ALL
    us-gaap/ifrs-full tags containing 'Cash'+'Operating' if the named
    candidates don't yield a quarterly-length duration (mirrors
    sec_edgar.get_rd_spend's last-resort tag scan)."""
    def _scan(tag_pairs):
        best = None
        for taxonomy, tag in tag_pairs:
            fact_data = facts_root.get(taxonomy, {}).get(tag)
            if not fact_data:
                continue
            for unit_key, facts in fact_data.get("units", {}).items():
                for f in facts:
                    start, end = f.get("start"), f.get("end")
                    if not (start and end):
                        continue
                    try:
                        days = (datetime.strptime(end, "%Y-%m-%d")
                                - datetime.strptime(start, "%Y-%m-%d")).days
                    except ValueError:
                        continue
                    if not (min_days <= days <= max_days):
                        continue
                    if best is None or end > best["end"]:
                        best = {"start": start, "end": end, "val": f.get("val"), "unit": unit_key}
        return best

    best = _scan(candidate_tags)
    if best:
        return best

    fallback_pairs = [
        (tax, tag)
        for tax in ("us-gaap", "ifrs-full")
        for tag in facts_root.get(tax, {})
        if "cash" in tag.lower() and "operating" in tag.lower()
    ]
    return _scan(fallback_pairs)


# T112b — the runway ladder's STRUCTURAL keys. bd_classification is a reader-
# facing sentence; a consumer that has to decide "is this the well-capitalized
# band?" must not re-read that prose, so the ladder emits a key beside it and
# the key is what other passes compare on. Owned here because the thresholds
# and the bands are this tool's contract (rules 1/10); no drug, class or
# company appears. The three keys below the ladder are set at the three sites
# that build a runway record WITHOUT consulting the ladder (no CIK resolved,
# companyfacts unavailable, private watchlist) — enumerated rather than left
# blank so a consumer can tell "not in the band" from "never classified".
RUNWAY_CLASS_WELL_CAPITALIZED = "well_capitalized"
RUNWAY_CLASS_MODERATE         = "moderate"
RUNWAY_CLASS_DISTRESSED       = "distressed"
RUNWAY_CLASS_INDETERMINATE    = "indeterminate"
RUNWAY_CLASS_UNKNOWN          = "unknown"
RUNWAY_CLASS_NO_CIK           = "no_cik"
RUNWAY_CLASS_PRIVATE          = "private"

# ── 3b (NSP 109 item 1; ruling D2, TRACK §6.34g) ────────────────────────────
# The ladder above yields SEVEN class keys, and only three of them are a
# VERDICT about a company's runway. The other four record that no verdict was
# reached, each for a different, stated reason. Consumers had no way to tell
# the two apart — every class key is a non-empty string — so a withheld
# verdict cleared a "has a class?" test and was then read as "not
# well-capitalized", i.e. compared and clean (F-C-1, the Viking case).
#
# This is the vocabulary OWNER declaring the split, the same way the
# pressure-signal severity map owns the signal side. A consumer asks
# `runway_class_is_verdict`; none re-lists these keys. Adding a class to the
# ladder without adding it here makes it a non-verdict by default — the safe
# direction: a new class is withheld until someone declares it a verdict.
#
# The reader-facing CAUSE is NOT restated here: every record already carries
# its own `bd_classification` sentence and `data_note` source from the ladder
# and the builders above, and a consumer states the non-classification by
# quoting the record rather than composing a second wording that could drift.
RUNWAY_VERDICT_CLASSES = (RUNWAY_CLASS_WELL_CAPITALIZED,
                          RUNWAY_CLASS_MODERATE,
                          RUNWAY_CLASS_DISTRESSED)
RUNWAY_NON_VERDICT_CLASSES = (RUNWAY_CLASS_INDETERMINATE,
                              RUNWAY_CLASS_UNKNOWN,
                              RUNWAY_CLASS_NO_CIK,
                              RUNWAY_CLASS_PRIVATE)


def runway_class_is_verdict(runway_class) -> bool:
    """True only for a class that states a runway VERDICT
    (well_capitalized / moderate / distressed). False for the four
    non-classifications — indeterminate (the R&D-vs-burn integrity gate
    withheld the call), unknown (insufficient data), no_cik (identity not
    resolved) and private (not a filer) — and for anything absent, empty or
    not a string. A consumer that treats "has a class" as "was classified"
    reports a withheld verdict as a clean one; this is the test that
    distinguishes them."""
    return (isinstance(runway_class, str)
            and runway_class in RUNWAY_VERDICT_CLASSES)


# ── D7 (operator ruling, session 109) ───────────────────────────────────────
# The four non-verdicts do NOT have one meaning. Three of them describe a
# state something could be done about; one of them is a correct, permanent,
# final answer:
#
#   indeterminate  R&D exceeds operating burn, so the two figures are on
#                  inconsistent bases. Often the ENGINE's own doing — where no
#                  filed quarterly R&D exists the annual figure is divided by
#                  four and compared against a real filed quarter, and the two
#                  sides are not required to be the same quarter. Sometimes a
#                  company whose collaboration revenue makes R&D exceed NET
#                  burn structurally. Either way, a person can read the filing
#                  and settle it.
#   unknown        companyfacts returned nothing. A single failed fetch heals
#                  itself on the next run; a persistent one does not.
#   no_cik         no CIK resolved — the record itself says this is a checked
#                  negative and NOT a finding that the company is private, so
#                  it is frequently a missing alias.
#   private        the company does not file with the SEC. Nothing to correct,
#                  now or ever.
#
# A queue that reports `private` every week reports a permanent fact as an
# open item and teaches its readers to ignore it. SETTLED is therefore not
# suppression: the company keeps its row in the cash-runway table with its own
# bd_classification sentence, exactly as before, and the split governs only
# whether a REVIEW is asked for.
RUNWAY_WITHHELD_ACTIONABLE_CLASSES = (RUNWAY_CLASS_INDETERMINATE,
                                      RUNWAY_CLASS_UNKNOWN,
                                      RUNWAY_CLASS_NO_CIK)
RUNWAY_WITHHELD_SETTLED_CLASSES = (RUNWAY_CLASS_PRIVATE,)


def runway_withholding_is_actionable(runway_class) -> bool:
    """True when a withheld classification names something a person could act
    on. False for a SETTLED non-verdict (private) and for every verdict class
    — a verdict needs no review — and False for anything absent or malformed:
    a class nobody has classified is not silently made actionable. Consumers
    ask this rather than re-listing the class keys."""
    return (isinstance(runway_class, str)
            and runway_class in RUNWAY_WITHHELD_ACTIONABLE_CLASSES)


def classify_runway(runway_months: Optional[float],
                    rd_allocation_pct: Optional[float] = None) -> tuple[str, str]:
    """(structural class key, reader-facing sentence) from ONE ladder.

    The sentences are unchanged byte-for-byte from the pre-T112b
    `_classify_runway`, which is now a sentence-only view onto this function so
    the bands cannot come to exist in two places and drift.
    """
    # Integrity gate: an R&D-%-of-burn above ~100% means the R&D and burn inputs
    # are inconsistent (see RD_BURN_INCONSISTENCY_PCT). The runway built from that
    # burn is not trustworthy, so we withhold the distress/health call rather than
    # print a false "Distressed" — the raw figures remain in the record for review.
    if (rd_allocation_pct is not None
            and rd_allocation_pct > RD_BURN_INCONSISTENCY_PCT):
        return (RUNWAY_CLASS_INDETERMINATE,
                "Indeterminate — R&D reported at "
                f"{rd_allocation_pct:.0f}% of operating burn (>100%), so the burn "
                "and R&D figures are on inconsistent bases and the runway estimate "
                "is unreliable; verify cash + investments and burn against the "
                "latest 10-Q/10-K before treating as a financing/deal signal")
    if runway_months is None:
        return (RUNWAY_CLASS_UNKNOWN,
                "Unknown — insufficient cash-flow data to estimate runway")
    if runway_months < RUNWAY_DISTRESSED_MONTHS:
        return (RUNWAY_CLASS_DISTRESSED,
                f"Distressed — ~{runway_months:.0f}mo runway; potential forced "
                f"financing, partnership, or acquisition target within 12 months")
    if runway_months < RUNWAY_MODERATE_MONTHS:
        return (RUNWAY_CLASS_MODERATE,
                f"Moderate — ~{runway_months:.0f}mo runway; financing event "
                f"likely within 18-24 months")
    return (RUNWAY_CLASS_WELL_CAPITALIZED,
            f"Well-capitalized — ~{runway_months:.0f}mo runway; unlikely near-term forced deal")


def _classify_runway(runway_months: Optional[float],
                     rd_allocation_pct: Optional[float] = None) -> str:
    """Sentence-only view onto classify_runway. Kept so existing callers and
    the T18 reconciliation fixtures read the same string they always did."""
    return classify_runway(runway_months, rd_allocation_pct)[1]


def get_cash_and_burn(ticker: str, name_hint: str = "") -> dict:
    """cash_runway record for a SMALL-CAP ticker (see scoping note in
    build_financial_deep_dive). mode='private' if no CIK resolves.

    T110: `name_hint` is the company name the run's entity resolver holds for
    this ticker (profile-declared; see utils.text.build_entity_resolver). It
    gives the EDGAR name search something to search FOR — without it the
    lookup asked for a company literally named "GPCR" and declared a listed
    company private. When every path still fails, the record carries the paths
    that were tried: "no CIK" becomes a checked negative rather than a claim
    (T104 doctrine).
    """
    cik, cik_paths = resolve_cik_with_paths(ticker, name_hint)
    if not cik:
        tried = "; ".join(f"{p['path']} ({p['query']}) -> {p['result']}"
                          for p in cik_paths) or "no lookup attempted"
        return {
            "company": name_hint or ticker, "mode": "private",
            "cash_position_usd": None, "quarterly_burn_usd": None,
            "rd_allocation_pct": None, "runway_months": None,
            "bd_classification": "No EDGAR CIK resolved — treated as private",
            "runway_class": RUNWAY_CLASS_NO_CIK,
            "cik_lookup_paths": cik_paths,
            "data_note": (
                f"No SEC EDGAR CIK could be resolved for '{ticker}'"
                + (f" (declared name: {name_hint})" if name_hint else "")
                + f". Paths checked: {tried}. Method: {CIK_LOOKUP_METHOD}. "
                  "This is a checked negative, not a finding that the company "
                  "is private; a company that files under a name this run did "
                  "not hold would look the same."),
        }

    facts = _get_company_facts(cik)
    if not facts:
        return {
            "company": ticker, "mode": "public",
            "cash_position_usd": None, "quarterly_burn_usd": None,
            "rd_allocation_pct": None, "runway_months": None,
            "bd_classification": "Unknown — XBRL companyfacts unavailable",
            "runway_class": RUNWAY_CLASS_UNKNOWN,
            "data_note": "SEC companyfacts API returned no data.",
        }

    company_name = facts.get("entityName", ticker)
    facts_root   = facts.get("facts", {})

    cash_fact = _latest_instant_value(facts_root, CASH_TAGS)
    st_fact   = _latest_instant_value(facts_root, ST_INVESTMENT_TAGS)
    op_cf     = _latest_quarterly_flow(facts_root, OPERATING_CF_TAGS)

    cash   = cash_fact["val"] if cash_fact else 0
    st_inv = st_fact["val"]   if st_fact   else 0
    cash_position = cash + st_inv
    currency = (cash_fact or st_fact or op_cf or {}).get("unit", "USD")

    quarterly_burn = abs(op_cf["val"]) if (op_cf and op_cf["val"] < 0) else None

    rd_spend_quarterly = None
    rd_records = get_rd_spend(ticker)
    quarterly_rd = [r for r in rd_records if r.get("period_type") == "quarterly"]
    if quarterly_rd:
        rd_spend_quarterly = quarterly_rd[0]["value"]
    elif rd_records:
        annual = [r for r in rd_records if r.get("period_type") == "annual"]
        if annual:
            rd_spend_quarterly = annual[0]["value"] / 4

    runway_months = round((cash_position / quarterly_burn) * 3, 1) if quarterly_burn else None
    rd_allocation_pct = (
        round(min(rd_spend_quarterly / quarterly_burn * 100, 999), 1)
        if rd_spend_quarterly and quarterly_burn else None
    )

    currency_note = "" if currency == "USD" else f" — figures in {currency}, not USD."
    data_note = (
        f"Cash+ST investments as of "
        f"{(cash_fact or st_fact or {}).get('end', 'latest balance-sheet date')}; "
        f"quarterly burn from operating cash flow "
        + (f"{op_cf['start']} to {op_cf['end']}" if op_cf else "unavailable")
        + "." + currency_note
    )

    runway_class, runway_verdict = classify_runway(runway_months, rd_allocation_pct)
    return {
        "company": company_name,
        "mode": "public",
        "currency": currency,
        "cash_position_usd": round(cash_position / 1_000_000, 1) if cash_position else None,
        "quarterly_burn_usd": round(quarterly_burn / 1_000_000, 1) if quarterly_burn else None,
        "rd_allocation_pct": rd_allocation_pct,
        "runway_months": runway_months,
        "bd_classification": runway_verdict,
        "runway_class": runway_class,
        "data_note": data_note,
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _company_match(a: str, b: str) -> bool:
    drop = {"inc", "co", "corp", "company", "the", "ltd", "plc", "llc"}
    a_tokens = set(re.findall(r"[a-z]+", a.lower())) - drop
    b_tokens = set(re.findall(r"[a-z]+", b.lower())) - drop
    if not a_tokens or not b_tokens:
        return False
    overlap = a_tokens & b_tokens
    return bool(overlap) and len(overlap) / min(len(a_tokens), len(b_tokens)) >= 0.5


def _get_primary_filing_text(ticker: str, days_back: int = 100, max_chars: int = 120000) -> str:
    """
    Dedicated, NON-keyword-filtered fetch of the most recent earnings filing
    — resolves BOTH the primary document and any Exhibit 99.1 press release,
    since product-revenue tables and "raising guidance from X to Y" language
    usually live in the press-release exhibit, not the 8-K cover page (and,
    for foreign filers, often only in the 6-K exhibit).
    """
    try:
        filings = get_company_filings(ticker, form_types=["8-K", "6-K", "20-F"], days_back=days_back)
    except Exception as e:
        print(f"    FinancialIntel: filing lookup failed for {ticker}: {e}")
        return ""
    if not filings:
        return ""

    filing = filings[0]   # newest first
    urls = resolve_filing_documents(filing.get("filing_index", ""))

    parts = []
    for url in (urls.get("exhibit_99"), urls.get("primary")):
        if url:
            text = get_filing_text(url, max_chars=max_chars)
            if text:
                parts.append(text)
    return "\n".join(parts)[:max_chars]


def _gather_financial_texts(ticker: str, company_name: str,
                             edgar_filing_text: list[dict],
                             earnings_call_intel: list[dict]) -> str:
    parts = []
    for rec in earnings_call_intel:
        if rec.get("ticker") == ticker:
            parts.extend(rec.get("guidance_statements", []))
            parts.extend(rec.get("pipeline_commentary", []))
    for filing in edgar_filing_text:
        if filing.get("form_type") in ("8-K", "6-K") and _company_match(filing.get("company", ""), company_name):
            parts.append(filing.get("content", ""))
    # Dedicated unfiltered fetch — primary source for revenue tables and
    # explicit "raising guidance from X to Y" language.
    parts.append(_get_primary_filing_text(ticker))
    return "\n".join(p for p in parts if p)[:14000]


# ---------------------------------------------------------------------------
# Guidance revisions
# ---------------------------------------------------------------------------

def compute_guidance_revision(company: str, current_figure: dict, prior_financials: dict) -> dict:
    metric = current_figure.get("metric", "")
    period = current_figure.get("period", "")
    key    = f"{company}|{metric}|{period}"

    # `current_figure` is LLM-extracted and is NOT validated upstream. A point
    # estimate arrives as low == high and was rendered as the range
    # "67.0-67.0 USD B" — a fabricated interval. Normalize and flag; never
    # present a point estimate as a range.
    _lo, _hi = current_figure.get("low"), current_figure.get("high")
    _flags: list[str] = []
    if _lo is not None and _hi is not None:
        if _hi < _lo:
            _lo, _hi = _hi, _lo
            _flags.append("guidance low/high were inverted; swapped")
    _is_point = (_lo is not None and _lo == _hi)
    if _is_point:
        _flags.append("point estimate reported (low == high) — render as a single "
                      "value, not a range")
    # The unit is LLM-extracted like low/high, and is just as capable of being
    # missing — but a figure with no scale is WORSE than a bad range: "82.0-85.0"
    # could be millions or billions, a 1000x difference. Flag it the same way the
    # range problems above are flagged, so every downstream consumer can see the gap
    # instead of rendering an ambiguous number.
    _unit = (current_figure.get("unit") or "").strip()
    if not _unit and (_lo is not None or _hi is not None):
        _flags.append("unit not stated in source — figure scale is unknown; "
                      "do not compare or aggregate this value")
    new_range = {
        "low": _lo, "high": _hi, "unit": _unit,
        "is_point_estimate": _is_point,
        "data_quality_flags": _flags,
        "source_note": "LLM-extracted from earnings call / 8-K; not deterministically parsed",
    }

    # 1. Prefer the prior range stated explicitly in the SAME text
    #    ("raising guidance from $80-83B to $82-85B").
    text_prior_low  = current_figure.get("prior_low")
    text_prior_high = current_figure.get("prior_high")
    if text_prior_low is not None and text_prior_high is not None:
        prior_range = {"low": text_prior_low, "high": text_prior_high}
    else:
        # 2. Fall back to last week's snapshot.
        snap = (prior_financials or {}).get("guidance", {}).get(key)
        prior_range = {"low": snap.get("low"), "high": snap.get("high")} if snap else {"low": None, "high": None}

    if prior_range["low"] is None or prior_range["high"] is None:
        direction, delta = "Initiated", None
    else:
        prior_mid = (prior_range["low"] + prior_range["high"]) / 2
        new_mid   = ((new_range["low"] or 0) + (new_range["high"] or 0)) / 2
        delta = round(new_mid - prior_mid, 2)
        if delta > 0.01:
            direction = "Raised"
        elif delta < -0.01:
            direction = "Lowered"
        else:
            direction = "Maintained"

    return {
        "company": company, "metric": metric, "period": period,
        "prior_range": prior_range, "new_range": new_range,
        "direction": direction, "delta_usd": delta,
        "linked_asset": current_figure.get("linked_asset"),
        "pipeline_signal": _pipeline_signal_text(direction, delta, new_range.get("unit", "")),
        "source_url": None,
        "source_label": "Earnings call / 8-K guidance (LLM-extracted)",
    }


def _pipeline_signal_text(direction: str, delta: Optional[float], unit: str) -> str:
    is_pct = "%" in (unit or "") or "cer" in (unit or "").lower()
    if direction == "Raised":
        if is_pct:
            return f"Guidance raised by ~{abs(delta):.1f} points ({unit}) — signals improved outlook."
        if delta and abs(delta) >= 1.0:
            return (f"Guidance raised by ~{abs(delta):.1f} {unit} — signals increased "
                    f"management confidence and likely accelerated R&D/commercial spend.")
        return f"Guidance raised by ~{abs(delta or 0):.2f} {unit}."
    if direction == "Lowered":
        return (f"Guidance lowered by ~{abs(delta or 0):.1f} {unit} — monitor "
                f"pipeline_commentary for any associated reprioritization.")
    if direction == "Initiated":
        return "Initial guidance for this period — no prior baseline stated or available for comparison."
    return "Guidance maintained — no material change in outlook this period."


def _find_linked_asset(ticker: str, earnings_call_intel: list[dict],
                        pipeline_drug_names: list[str]) -> Optional[str]:
    """Fallback only — primary linked_asset comes from the guidance
    extractor's same-text read. This scans pipeline_commentary for
    acceleration language naming a pipeline drug."""
    if not pipeline_drug_names:
        return None
    for rec in earnings_call_intel:
        if rec.get("ticker") != ticker:
            continue
        for commentary in rec.get("pipeline_commentary", []):
            cl = commentary.lower()
            if any(t in cl for t in REALLOCATION_ACCEL_TERMS):
                for drug in pipeline_drug_names:
                    if drug.lower() in cl:
                        return drug
    return None


# ---------------------------------------------------------------------------
# Product-level revenue
# ---------------------------------------------------------------------------

def _to_millions(value_str: str, unit_str: str) -> float:
    val  = float(value_str.replace(",", ""))
    unit = unit_str.lower()
    return val * 1000.0 if unit in ("billion", "bn", "b") else val


def _parse_unit(unit: str) -> tuple[str, float]:
    """Returns (currency_code, multiplier_to_millions)."""
    u = (unit or "USD M").upper()
    currency = "USD"
    for code in ("USD", "DKK", "EUR", "GBP"):
        if code in u:
            currency = code
            break
    multiplier = 1000.0 if re.search(r"\bB(N|ILLION)?\b", u) else 1.0
    return currency, multiplier


def _period_label(d: date) -> str:
    q = (d.month - 1) // 3 + 1
    return f"Q{q} {d.year}"


def _prior_quarter_label(period: str) -> Optional[str]:
    m = re.match(r"Q(\d) (\d{4})", period or "")
    if not m:
        return None
    q, y = int(m.group(1)), int(m.group(2))
    return f"Q4 {y-1}" if q == 1 else f"Q{q-1} {y}"


def _normalize_period(period: str) -> str:
    """Best-effort coercion of LLM-returned period strings to 'Q# YYYY'."""
    if not period:
        return _prior_quarter_label(_period_label(date.today())) or _period_label(date.today())
    for pat in _PERIOD_RE_VARIANTS:
        m = pat.search(period)
        if m:
            nums = [int(x) for x in m.groups()]
            q = next((n for n in nums if 1 <= n <= 4), None)
            y = next((n for n in nums if n > 4), None)
            if q and y:
                if y < 100:
                    y += 2000
                return f"Q{q} {y}"
    return period



def _cross_validate_revenue(
    llm_cur_rev: float,
    llm_yoy_rev: float | None,
    text: str,
    product: str,
    aliases: list[str],
    tolerance: float = 0.35,
) -> tuple[float | None, str | None]:
    """
    Independently re-derive the YoY comparator from the SAME filing text via
    the existing regex extractor (_extract_revenue_for_product), and only
    trust the LLM-extracted yoy_revenue if both sources agree within
    `tolerance` (default 35% relative difference — wide enough to tolerate
    minor rounding/period differences, tight enough to catch a unit or
    period mismatch like the Mounjaro/Zepbound case, where the LLM and a
    plausible reading of the filing differed by ~80 percentage points).
 
    This does NOT replace the regex extractor as primary — the LLM resolver
    remains primary because it handles table formats regex cannot. This is
    a SECOND OPINION gate, not a replacement extraction path.
 
    Returns:
        (validated_yoy_or_None, validation_note_or_None)
        If validation_note is non-None, the caller MUST set yoy_growth_pct to
        null in the final record AND surface validation_note in
        financial_intelligence.data_warnings — never silently drop it.
    """
    if llm_yoy_rev is None:
        return None, None  # nothing to validate — LLM found no prior-year figure
  
    regex_result = _extract_revenue_for_product(text, [product] + list(aliases))
    if regex_result is None:
        # Regex found nothing either — can't cross-check, but don't block the
        # LLM figure on an extractor that simply didn't match this filing's
        # phrasing. Note the absence of a second opinion rather than failing.
        return llm_yoy_rev, None
 
    _, regex_yoy_rev = regex_result
    if regex_yoy_rev is None:
        return llm_yoy_rev, None
 
    denom = max(abs(regex_yoy_rev), 1.0)
    rel_diff = abs(llm_yoy_rev - regex_yoy_rev) / denom
 
    if rel_diff > tolerance:
        note = (
            f"YoY figure for {product} suppressed: LLM extraction (${llm_yoy_rev:,.0f}M) "
            f"and an independent regex re-derivation of the same filing text "
            f"(${regex_yoy_rev:,.0f}M) disagree by {rel_diff*100:.0f}% — likely a "
            f"unit or reporting-period mismatch. Verify the prior-year comparator "
            f"against the source 8-K/6-K/20-F directly before reporting a YoY change "
            f"for this product."
        )
        return None, note
 
    return llm_yoy_rev, None



def _extract_revenue_for_product(text: str, aliases: list[str]) -> Optional[tuple[float, Optional[float]]]:
    """Regex fallback. Returns (current_revenue_millions, yoy_revenue_millions_or_None)."""
    for alias in aliases:
        esc = re.escape(alias)
        two_value = rf"{esc}[^.]{{0,150}}?{DOLLAR_VALUE_RE}[^.]{{0,150}}?{DOLLAR_VALUE_RE}"
        m = re.search(two_value, text, re.IGNORECASE)
        if m:
            return _to_millions(m.group(1), m.group(2)), _to_millions(m.group(3), m.group(4))
        one_value = rf"{esc}[^.]{{0,150}}?{DOLLAR_VALUE_RE}"
        m = re.search(one_value, text, re.IGNORECASE)
        if m:
            return _to_millions(m.group(1), m.group(2)), None
    return None


# T99 — engine-authored notes carry their methodology (sourcing doctrine:
# every synthesized claim states its method; a label-only citation routes to
# the Sources & Methodology endnotes). These are the note_sources entries the
# engine attaches to the notes IT writes, so the T93 2/2 prose-sourcing check
# audits engine output under the same contract as model prose instead of
# firing on it (measured 2026-08-08 across 300 retained exports: 100% of the
# check's fires on current-vintage artifacts were these engine notes; zero
# were model violations). Fresh dict per row via _engine_note_sources() — a
# shared literal would alias across rows.
_ENGINE_TREND_NOTE_LABEL = (
    "Engine-computed from this row's reported revenue figures and "
    "prior-period snapshot history (deterministic QoQ/YoY arithmetic; "
    "no external source consulted)")
_ENGINE_VALIDATION_NOTE_LABEL = (
    "Engine validation — figure withheld; basis stated in this row's "
    "data warning")


def _engine_note_sources(label: str) -> list:
    """One fresh usable entry (source_label set, no URL — never fabricated)."""
    return [{"source_url": None, "source_label": label}]


def _product_revenue_note(trend_flag: str, qoq: Optional[float], yoy: Optional[float]) -> str:
    if trend_flag == "Decelerating":
        return (f"QoQ growth slowed to {qoq:+.1f}% (still {yoy:+.1f}% YoY) — "
                f"early deceleration signal worth monitoring.")
    if trend_flag == "Accelerating":
        return f"QoQ growth accelerated to {qoq:+.1f}% ({yoy:+.1f}% YoY)."
    if qoq is None:
        return "QoQ comparison unavailable — prior-quarter figure not yet in snapshot history."
    return f"Growth stable at {qoq:+.1f}% QoQ ({yoy:+.1f}% YoY)."


def _build_product_revenue_record(company_name, product, period, cur_rev, yoy_rev,
                                   currency, prior_pr) -> dict:
    period = _normalize_period(period)
    yoy_growth_pct = round((cur_rev - yoy_rev) / yoy_rev * 100, 1) if yoy_rev else None

    qoq_growth_pct, prior_qoq = None, None
    prior_q_label = _prior_quarter_label(period)
    if prior_q_label:
        prior_entry = prior_pr.get(f"{company_name}|{product}|{prior_q_label}")
        if prior_entry:
            prior_rev = prior_entry.get("revenue_usd")
            prior_qoq = prior_entry.get("qoq_growth_pct")
            if prior_rev:
                qoq_growth_pct = round((cur_rev - prior_rev) / prior_rev * 100, 1)

    trend_flag = "Stable"
    if qoq_growth_pct is not None and prior_qoq is not None:
        if qoq_growth_pct < prior_qoq - 1:
            trend_flag = "Decelerating"
        elif qoq_growth_pct > prior_qoq + 1:
            trend_flag = "Accelerating"

    return {
        "company": company_name, "product": product, "period": period,
        "revenue_usd": round(cur_rev, 1), "currency": currency,
        "qoq_growth_pct": qoq_growth_pct, "yoy_growth_pct": yoy_growth_pct,
        "trend_flag": trend_flag,
        "note": _product_revenue_note(trend_flag, qoq_growth_pct, yoy_growth_pct),
        "note_sources": _engine_note_sources(_ENGINE_TREND_NOTE_LABEL),
    }


def get_product_revenue(ticker: str, company_name: str, products: dict[str, list[str]],
                         text: str, prior_financials: dict,
                         product_revenue_resolver=None,
                         commercial_status: Optional[dict[str, str]] = None,
                         guidance_quarterly_usd_m: Optional[float] = None) -> list[dict]:
    # DYNAMIC corroboration inputs (no hardcoded dollar ceilings — those don't
    # survive inflation or product ramp). Each per-product figure is checked
    # against sources INDEPENDENT of our own prior output, recomputed fresh
    # from THIS filing every run, so a bad value can never be laundered by a
    # self-referential baseline:
    #   • commercial_status: OPTIONAL {product: "pre_commercial"|"marketed"}
    #       from the profile. The ONLY qualitative fact worth stating (a drug
    #       either is or isn't on the market); it does not drift with inflation.
    #       Absent → treated as marketed (no pre-commercial gate).
    #   • guidance_quarterly_usd_m: company annual revenue-guidance midpoint / 4,
    #       used as a fallback "expected quarterly total" when the filing's
    #       explicit total can't be parsed. Self-scaling.
    # The company TOTAL revenue for the period (primary share-of-total anchor)
    # is parsed from the resolver output below.
    commercial_status = commercial_status or {}
    if not text:
        return []

    prior_pr = (prior_financials or {}).get("product_revenue", {})
    records: list[dict] = []

    if product_revenue_resolver:
        try:
            extracted = product_revenue_resolver(text, company_name, list(products.keys()))
        except Exception as e:
            print(f"    Product revenue extractor failed for {ticker}: {e}")
            extracted = {"products": [], "company_total_revenue": None}

        # Back-compat: tolerate a bare list (old resolver contract) as well as
        # the new {"products": [...], "company_total_revenue": ...} object.
        if isinstance(extracted, list):
            extracted = {"products": extracted, "company_total_revenue": None}
        elif not isinstance(extracted, dict):
            extracted = {"products": [], "company_total_revenue": None}

        # Company total for the period → the primary share-of-total anchor.
        company_total_usd_m = None
        total_raw = extracted.get("company_total_revenue")
        if total_raw is not None:
            _, tmult = _parse_unit(extracted.get("company_total_unit", "USD M"))
            try:
                company_total_usd_m = float(total_raw) * tmult
            except (TypeError, ValueError):
                company_total_usd_m = None

        for item in extracted.get("products", []):
            product = item.get("product")
            cur_rev = item.get("current_revenue")
            # Skip if product not in our tracked map or no current revenue reported
            if product not in products or cur_rev is None:
                continue
            currency, mult = _parse_unit(item.get("unit", ""))
            cur_rev_scaled = cur_rev * mult

            # Sanity-check: current revenue must be a plausible positive number
            if cur_rev_scaled <= 0:
                print(f"    Product revenue: skipping {product} — non-positive revenue {cur_rev_scaled}")
                continue

            yoy = item.get("yoy_revenue")
            yoy_scaled = (yoy * mult) if yoy is not None else None

            aliases = products.get(product, [])
            validated_yoy, validation_note = _cross_validate_revenue(
                cur_rev_scaled, yoy_scaled, text, product, aliases,
            )

            rec = _build_product_revenue_record(
                company_name, product, item.get("period", ""),
                cur_rev_scaled, validated_yoy, currency, prior_pr,
            )
            if validation_note:
                rec["validation_note"] = validation_note
            # Carry provenance (verbatim source span) for the Layer-2 check.
            rec["_source_span"] = item.get("source_span", "")
            rec["_aliases"]     = [product] + list(aliases)
            records.append(rec)

        if records:
            corroboration = {
                "company_total_usd_m":      company_total_usd_m,
                "guidance_quarterly_usd_m": guidance_quarterly_usd_m,
                "commercial_status":        commercial_status,
            }
            return _validate_revenue_records(records, company_name, ticker, corroboration)
        # LLM found nothing or all were filtered — fall through to regex

    # Regex fallback path
    current_period = _prior_quarter_label(_period_label(date.today())) or _period_label(date.today())
    for product, aliases in products.items():
        extracted = _extract_revenue_for_product(text, [product] + list(aliases))
        if not extracted:
            continue
        cur_rev, yoy_rev = extracted
        rec = _build_product_revenue_record(
            company_name, product, current_period, cur_rev, yoy_rev, "USD", prior_pr,
        )
        rec["_aliases"] = [product] + list(aliases)
        records.append(rec)
    corroboration = {
        "company_total_usd_m":      None,   # regex path has no parsed total
        "guidance_quarterly_usd_m": guidance_quarterly_usd_m,
        "commercial_status":        commercial_status,
    }
    return _validate_revenue_records(records, company_name, ticker, corroboration)


# ── Dynamic corroboration primitives (no hardcoded dollar ceilings) ──────────
# A single product being nearly half of a diversified pharma's TOTAL revenue is
# already implausible; this ratio auto-scales with inflation and product growth
# forever (it is a share, not a dollar amount). Lilly's largest single product
# runs ~30% of company total; a $7B mis-bind is ~54% → caught.
_SINGLE_PRODUCT_SHARE_CEIL = 0.45
# Minimum revenue (USD millions) for the duplicate-figure check to fire. Two
# products sharing a small figure could be coincidence; identical SUBSTANTIAL
# figures to the dollar are the fingerprint of one number assigned to several
# products (e.g. Mounjaro + Zepbound both $7,000M). Aligned with the other
# substantiality floors in _validate_revenue_records.
_DUP_FIGURE_MIN_USD_M = 200.0
# Phrases that indicate a figure is a company/segment AGGREGATE, not a single
# product line. Kept tight to avoid false positives on real product rows.
_AGGREGATE_KEYWORDS = (
    "total revenue", "total company", "total worldwide", "worldwide revenue",
    "consolidated revenue", "consolidated net", "segment revenue",
    "total net revenue", "group revenue", "company total", "revenue in total",
    "total revenues", "net revenues in total",
)


def _provenance_failure(rec: dict) -> Optional[str]:
    """
    Layer 2 — verify the extracted figure actually belongs to the product, using
    the verbatim source span the resolver returned. Independent of any dollar
    threshold and of our own history: it just checks the number's origin text.
    Returns a reason string if provenance FAILS, else None. Returns None when no
    span is available (can't corroborate → defer to other layers).
    """
    span = (rec.get("_source_span") or "").strip().lower()
    if not span:
        return None
    aliases = [a.lower() for a in (rec.get("_aliases") or []) if a]
    if aliases and not any(a in span for a in aliases):
        return ("the product name does not appear in the verbatim source span "
                "the figure was taken from — the number was bound to the wrong line")
    for kw in _AGGREGATE_KEYWORDS:
        if kw in span:
            return (f"the source span is governed by an aggregate label "
                    f"('{kw}') — this is a company/segment total, not a "
                    f"single-product figure")
    return None


def _validate_revenue_records(records: list[dict], company_name: str, ticker: str,
                              corroboration: Optional[dict] = None) -> list[dict]:
    """
    Post-extraction sanity checks to prevent hallucinated / mis-bound revenue
    figures from reaching the LLM context. Adds data_warnings to anomalous
    records rather than dropping them — the LLM is instructed to surface these.

    Checks applied:
      0. DYNAMIC magnitude corroboration (the durable fix for the recurring
         "$7.0B on an Eli Lilly product" anomaly). Rather than a hardcoded
         dollar ceiling (which inflation and product ramp make wrong within a
         couple of quarters, and which a poisoned snapshot can launder), the
         CURRENT figure is corroborated against sources INDEPENDENT of our own
         prior output, recomputed from THIS filing every run:
           • Provenance (Layer 2): the verbatim source span must contain the
             product name and must NOT be governed by an aggregate label
             ("total revenue", "segment", "consolidated"…). Attacks the root
             cause — a nearby aggregate bound to a product name.
           • Share-of-total (Layer 1): no single product can be ~half of a
             diversified company's total revenue. Flag rev/total >
             _SINGLE_PRODUCT_SHARE_CEIL, and flag when tracked products SUM to
             more than the company total (double-count / aggregate present).
             The total is parsed from the same filing; a guidance-derived
             quarterly envelope (annual guidance midpoint / 4) is the fallback.
           • Round-billions fingerprint (Layer 5): an exact multiple of $1,000M
             at/above $1B is the "$X.0 billion ×1000" scaling tell — used only
             as a BACKSTOP when no total/provenance is available to corroborate.
           • Pre-commercial (profile-optional): a not-yet-marketed asset cannot
             post material product revenue. "On the market or not" is the only
             qualitative fact taken from the profile; it carries no dollar value
             and does not drift with inflation.
         A figure is suppressed when any INDEPENDENT hard corroboration fails;
         the warning names the corroborating figures (total, share%, span) so
         the methodology is auditable.
      1. YoY growth anomaly: ANY negative YoY for a blockbuster (revenue >$500M)
         is almost certainly a data extraction error for a growing market leader.
      2. YoY figure too close to current revenue — same quarter extracted twice.
      3. Cross-product sum sanity: possible double-counting.
      4. DKK/USD confusion for Novo Nordisk.
    """
    if not records:
        return records

    corroboration           = corroboration or {}
    company_total_usd_m     = corroboration.get("company_total_usd_m")
    guidance_quarterly_usd_m = corroboration.get("guidance_quarterly_usd_m")
    commercial_status       = corroboration.get("commercial_status", {}) or {}
    # Anchor for share-of-total: prefer the filing's explicit total; fall back
    # to the guidance-derived quarterly envelope. Both are independent of our
    # own snapshot history.
    total_anchor      = company_total_usd_m or guidance_quarterly_usd_m
    total_anchor_src  = ("company total revenue" if company_total_usd_m
                         else ("guidance-derived quarterly envelope"
                               if guidance_quarterly_usd_m else None))
    # Group by period for cross-product sum check
    by_period: dict[str, list[dict]] = {}
    for r in records:
        by_period.setdefault(r.get("period", ""), []).append(r)

    for period, period_records in by_period.items():
        total = sum(r.get("revenue_usd", 0) or 0 for r in period_records)

        # Period-level sum-vs-total anchor (Layer 1, double-count / aggregate):
        # if tracked products sum to MORE than the company total, at least one
        # figure is an aggregate or double-counted. The single largest product
        # is the most likely culprit and is marked for suppression below.
        sum_suspect_product = None
        if total_anchor and total > total_anchor * 1.05:
            sum_suspect_product = max(
                period_records, key=lambda x: x.get("revenue_usd", 0) or 0
            ).get("product", "")

        # Duplicate-figure detection (Layer 1b): two DISTINCT products in the same
        # period carrying the IDENTICAL revenue figure is the fingerprint of one
        # number extracted/assigned to multiple products (root case: Mounjaro and
        # Zepbound both exactly $7,000M / -45.3% YoY). Coincident revenue equal to
        # the dollar across different products is implausible, so both are withheld
        # pending source verification. Maps each affected product -> (figure, co-
        # products) so the warning can name them. Only substantial figures qualify.
        _rev_groups: dict[float, list[str]] = {}
        for _r in period_records:
            _rev = _r.get("revenue_usd")
            if _rev and _rev > _DUP_FIGURE_MIN_USD_M:
                _rev_groups.setdefault(float(_rev), []).append(_r.get("product", ""))
        dup_figure = {
            p: (rev, [q for q in prods if q != p])
            for rev, prods in _rev_groups.items() if len(set(prods)) >= 2
            for p in prods
        }

        for r in period_records:
            rev      = r.get("revenue_usd", 0) or 0
            yoy_pct  = r.get("yoy_growth_pct")
            yoy_rev  = None  # reconstruct from pct if possible
            product  = r.get("product", "")
            currency = r.get("currency", "USD")

            # Reconstruct approximate yoy_revenue for the same-quarter check
            if yoy_pct is not None and rev > 0:
                yoy_rev = rev / (1 + yoy_pct / 100) if yoy_pct != -100 else None

            # ── Check 0: DYNAMIC magnitude corroboration ─────────────────────
            status         = (commercial_status.get(product) or "").lower()
            round_billions = rev >= 1000.0 and abs(rev % 1000.0) < 0.5
            share          = (rev / total_anchor) if total_anchor else None
            suppress_reason = None

            # (a) Pre-commercial asset with material revenue — mis-attribution.
            if status == "pre_commercial" and rev > 50.0:
                suppress_reason = (
                    f"{product} is flagged pre-commercial (not yet marketed) in "
                    f"the profile, so it cannot post ${rev:,.0f}M in product "
                    f"revenue — this is a mis-attributed company/segment figure"
                )
            # (b) Provenance (Layer 2) — figure's own source text disowns it.
            if suppress_reason is None:
                prov = _provenance_failure(r)
                if prov:
                    suppress_reason = f"provenance check failed — {prov}"
            # (c) Share-of-total (Layer 1) — implausibly large slice of company.
            if suppress_reason is None and share is not None and share > _SINGLE_PRODUCT_SHARE_CEIL:
                suppress_reason = (
                    f"${rev:,.0f}M is {share*100:.0f}% of the {total_anchor_src} "
                    f"(${total_anchor:,.0f}M) — above the {_SINGLE_PRODUCT_SHARE_CEIL*100:.0f}% "
                    f"single-product ceiling; almost certainly a company/segment "
                    f"total mis-bound to this one product"
                )
            # (d) Sum-vs-total (Layer 1) — this product tipped the period sum
            #     over the company total.
            if suppress_reason is None and product == sum_suspect_product:
                suppress_reason = (
                    f"tracked products for {period} sum to ${total:,.0f}M, which "
                    f"exceeds the {total_anchor_src} (${total_anchor:,.0f}M); "
                    f"${rev:,.0f}M ({product}) is the largest and most likely an "
                    f"aggregate or double-counted figure"
                )
            # (d2) Duplicate figure (Layer 1b) — the SAME revenue reported for two
            #      or more distinct products in this period (extraction artifact).
            if suppress_reason is None and product in dup_figure:
                _dfig, _co = dup_figure[product]
                suppress_reason = (
                    f"${rev:,.0f}M is reported IDENTICALLY for {product} and "
                    f"{', '.join(c for c in _co if c) or 'another product'} in "
                    f"{period}; the same figure to the dollar across distinct "
                    f"products is an extraction artifact, not real coincident "
                    f"revenue — both are withheld pending source verification"
                )
            # (e) Round-billions fingerprint (Layer 5) — BACKSTOP only, used
            #     when there is NO independent way to corroborate (no total and
            #     no source span). With corroboration available and passing, we
            #     trust it over the fingerprint.
            if (suppress_reason is None and round_billions and currency == "USD"
                    and total_anchor is None and not (r.get("_source_span") or "").strip()):
                suppress_reason = (
                    f"${rev:,.0f}M is an exact multiple of $1,000M — the "
                    f"fingerprint of a billions-denominated aggregate "
                    f"(a '$X.0 billion' figure) scaled to millions — and no "
                    f"company total or source span was available to corroborate it"
                )

            if suppress_reason:
                warning = (
                    f"IMPLAUSIBLE PRODUCT REVENUE SUPPRESSED: {company_name} "
                    f"{product} — {suppress_reason}. The revenue figure has "
                    f"been withheld (set to null) and must be verified against "
                    f"the primary 8-K/6-K/10-Q product-revenue table before "
                    f"citing. Do NOT report a revenue number or growth rate for "
                    f"this product this period."
                )
                print(f"  FinancialIntel VALIDATION WARNING: {warning}")
                r["_data_warning"]   = warning
                r["revenue_usd"]     = None
                r["yoy_growth_pct"]  = None
                r["qoq_growth_pct"]  = None
                r["trend_flag"]      = "Unverified"
                r["note"] = ("Revenue withheld pending source verification — see "
                             "data warning.")
                # The trend-arithmetic label no longer describes this note —
                # its basis is the validation event (T99).
                r["note_sources"] = _engine_note_sources(
                    _ENGINE_VALIDATION_NOTE_LABEL)
                continue  # figure is gone; downstream YoY/sum checks are moot

            # ── Check 1: anomalous negative YoY for blockbusters ─────────────
            # Threshold: -10% for large blockbusters (>$1B), -20% for mid ($500M-$1B)
            neg_threshold = -10.0 if rev > 1000.0 else -20.0
            if yoy_pct is not None and yoy_pct < neg_threshold and rev > 500.0:
                warning = (
                    f"ANOMALOUS YoY: {company_name} {product} shows "
                    f"{yoy_pct:.1f}% YoY decline at ${rev:,.0f}M — "
                    f"this is implausible for a blockbuster in a growing market "
                    f"(threshold: {neg_threshold:.0f}% for this revenue tier). "
                    f"Likely a period mismatch (e.g. LLM extracted prior-quarter "
                    f"revenue instead of prior-year revenue). "
                    f"Verify against source 8-K/6-K before distributing. "
                    f"YoY field set to null to prevent false reporting."
                )
                print(f"  FinancialIntel VALIDATION WARNING: {warning}")
                r["_data_warning"] = warning
                r["yoy_growth_pct"] = None
                # Do NOT relabel as "Stable" — that dressed an anomalous row up
                # as normal. Mark it "Unverified" so the note and renderer show
                # the figure is under a data-quality flag.
                r["trend_flag"] = "Unverified"
                r["note"] = ("YoY withheld pending source verification — see data "
                             "warning.")
                r["note_sources"] = _engine_note_sources(
                    _ENGINE_VALIDATION_NOTE_LABEL)

            # ── Check 2: current ≈ yoy → same-quarter extracted twice ────────
            # Only check when yoy_rev can be reconstructed and is substantial
            elif yoy_pct is not None and yoy_rev is not None and rev > 200.0 and yoy_rev > 200.0:
                similarity = abs(rev - yoy_rev) / max(rev, 1.0)
                if similarity < 0.05:
                    warning = (
                        f"DUPLICATE PERIOD WARNING: {company_name} {product} "
                        f"current revenue (${rev:,.0f}M) and YoY comparator "
                        f"(${yoy_rev:,.0f}M) differ by only {similarity*100:.1f}% — "
                        f"LLM likely extracted the same period twice instead of "
                        f"current vs prior-year. YoY field set to null."
                    )
                    print(f"  FinancialIntel VALIDATION WARNING: {warning}")
                    r["_data_warning"] = warning
                    r["yoy_growth_pct"] = None
                    r["trend_flag"] = "Unverified"
                    r["note"] = ("YoY withheld pending source verification — see "
                                 "data warning.")
                    r["note_sources"] = _engine_note_sources(
                        _ENGINE_VALIDATION_NOTE_LABEL)

            # ── Check 3: DKK/USD confusion for Novo Nordisk ──────────────────
            if "novo" in company_name.lower() and currency == "DKK":
                if rev < 1000.0:
                    r["_data_warning"] = (
                        f"DKK SANITY: {product} revenue {rev:,.0f} DKK M appears low "
                        f"for a Novo Nordisk blockbuster. Verify unit extraction "
                        f"(DKK billions vs millions) against source filing."
                    )
                    print(f"  FinancialIntel VALIDATION WARNING: {r['_data_warning']}")

        # ── Check 4: cross-product sum implausibly large for same period ─────
        if len(period_records) > 1 and total > 50_000.0 and currency == "USD":
            warning = (
                f"CROSS-PRODUCT SUM WARNING: {company_name} products for {period} "
                f"sum to ${total:,.0f}M — this appears implausibly large and may "
                f"indicate double-counting or a unit mismatch across products."
            )
            print(f"  FinancialIntel VALIDATION WARNING: {warning}")
            for r in period_records:
                r.setdefault("_data_warning", warning)

    # Strip internal-only provenance helpers so they never reach the snapshot,
    # the LLM context, or the rendered report.
    for r in records:
        r.pop("_source_span", None)
        r.pop("_aliases", None)

    return records


# ---------------------------------------------------------------------------
# Financial pressure signals
# ---------------------------------------------------------------------------

def _pressure_bd_implication(signal_type: str, company: str) -> str:
    if signal_type == "Going Concern Language":
        return (f"Going-concern language is a severe distress signal — {company} "
                f"may be forced into an asset sale, licensing deal, or "
                f"acquisition within 6-12 months.")
    if signal_type == "Covenant Language":
        return (f"Covenant/default language suggests lender pressure on {company} "
                f"— may accelerate a partnership or divestiture to raise cash.")
    if signal_type == "Credit Rating Action":
        return (f"A credit rating action raises {company}'s cost of capital — "
                f"increases the attractiveness of non-dilutive financing such "
                f"as royalty monetization or asset out-licensing.")
    return f"Monitor {company} for financing-driven BD activity."


# T112b — implied financing-pressure severity per signal_type. It lives HERE,
# beside the implication text it must stay consistent with, because "what this
# filing type implies about financing pressure" is a regulatory/financial-
# process fact owned by the producing tool (rules 1/10). No drug, class or
# company appears, and nothing here adjudicates: the map says what a signal
# TYPE implies, never whether a particular filing's language is real.
#
# The keys are the FULL emitted vocabulary, not PRESSURE_SIGNAL_TERMS alone:
# "Shelf Registration" is emitted by get_financial_pressure_signals from
# SHELF_FORM_TYPES and never reaches _pressure_bd_implication. Its own
# bd_implication already says forward-looking capacity is not an active raise,
# so it maps to NONE; omitted, a consumer defaulting it either way would fire
# against every small-cap holding an S-3.
#
# "Credit Rating Action" is ELEVATED, not DISTRESS: a higher cost of capital is
# pressure, but it does not contradict a funded balance sheet the way going-
# concern language or a covenant default does. Widening it is an evidence
# decision for a later pass, as `Moderate` is on the runway side.
#
# An unrecognised signal_type is UNKNOWN and must be REPORTED by the consumer,
# never defaulted: read as NONE it would hide a new distress type on the day it
# is added, read as DISTRESS it would fire on anything. T110's rule applied to
# a vocabulary — nothing is guessed in either direction.
PRESSURE_SEVERITY_DISTRESS = "distress"
PRESSURE_SEVERITY_ELEVATED = "elevated"
PRESSURE_SEVERITY_NONE     = "none"
PRESSURE_SEVERITY_UNKNOWN  = "unknown"

PRESSURE_SIGNAL_SEVERITY: dict[str, str] = {
    "Going Concern Language": PRESSURE_SEVERITY_DISTRESS,
    "Covenant Language":      PRESSURE_SEVERITY_DISTRESS,
    "Credit Rating Action":   PRESSURE_SEVERITY_ELEVATED,
    "Shelf Registration":     PRESSURE_SEVERITY_NONE,
}

# The methodology this classification carries wherever it is published. Pinned:
# the reconciliation audit reproduces it verbatim, and tests assert it.
PRESSURE_SEVERITY_METHOD = (
    "signal severity read from the filing TYPE only (tools."
    "financial_intelligence.PRESSURE_SIGNAL_SEVERITY, the owner of that "
    "vocabulary), never from the filing's language or from the runway figure; "
    "an unmapped type is reported as unknown rather than assumed benign or "
    "adverse")


def pressure_signal_severity(signal_type: str) -> str:
    """Implied financing-pressure severity for one signal_type.

    Returns a PRESSURE_SEVERITY_* constant; an unmapped type returns UNKNOWN,
    which the caller must surface rather than collapse into either end of the
    scale.
    """
    return PRESSURE_SIGNAL_SEVERITY.get(
        (signal_type or "").strip(), PRESSURE_SEVERITY_UNKNOWN)


def get_financial_pressure_signals(ticker: str, company_name: str, days_back: int = 180) -> list[dict]:
    signals = []

    try:
        for f in get_company_filings(ticker, form_types=SHELF_FORM_TYPES, days_back=days_back):
            signals.append({
                "company": company_name,
                "signal_type": "Shelf Registration",
                "filed_date": f.get("filed_date", ""),
                "description": (
                    f"{f.get('form_type')} shelf registration filed "
                    f"{f.get('filed_date')} — gives the company standing capacity "
                    f"to raise capital quickly (equity, debt, or as acquisition currency)."
                ),
                "filing_index_url": f.get("filing_index", ""),
                "bd_implication": (
                    "Shelf registrations are forward-looking capital-raise capacity, "
                    "not an active raise — but combined with a near-term cash need "
                    "(see cash_runway) this may signal an imminent financing event, "
                    "partnership, or M&A."
                ),
            })
    except Exception as e:
        print(f"  FinancialIntel: shelf filing lookup failed for {ticker}: {e}")

    try:
        filings = get_company_filings(ticker, form_types=["10-K", "10-Q", "8-K"], days_back=days_back)
    except Exception as e:
        print(f"  FinancialIntel: filing lookup failed for {ticker}: {e}")
        filings = []

    checked = 0
    for f in filings:
        if checked >= 3 or not f.get("document_url"):
            continue
        text = get_filing_text(f["document_url"], max_chars=60000)
        if not text:
            continue
        checked += 1
        text_lower = text.lower()
        for signal_type, terms in PRESSURE_SIGNAL_TERMS.items():
            if any(t in text_lower for t in terms):
                # R4: extract wide, then let the ONE sanitiser clamp at the
                # cell limit on a word boundary WITH disclosure (the old 600-char
                # extract cut mid-word and silently). The basis record travels
                # with the row so the renderer can print the method beside it.
                excerpt = extract_relevant_paragraphs(text, terms, context_sentences=1, max_total_chars=4000)
                excerpt, description_basis = sanitize_source_text_audit(excerpt, max_chars=600)
                description_basis["excerpt_present"] = bool(excerpt)
                signals.append({
                    "company": company_name,
                    "signal_type": signal_type,
                    "filed_date": f.get("filed_date", ""),
                    "description": excerpt or f"'{signal_type}' language detected in {f.get('form_type')}.",
                    "description_basis": description_basis,
                    "filing_index_url": f.get("filing_index", ""),
                    "bd_implication": _pressure_bd_implication(signal_type, company_name),
                })

    return signals


# ---------------------------------------------------------------------------
# Private-company watchlist (Kailera, Carnot — no EDGAR CIK)
# ---------------------------------------------------------------------------

# Finance/funding relevance signals for a private-company web snippet. Generic
# (company-agnostic): a snippet is only usable as a funding note if it is about
# THIS company (a distinctive name token appears) AND about its financing /
# commercial status (one of these terms appears). Without the gate the top web
# result was dumped verbatim — e.g. a Windows-registry help page for "Physiogenix"
# and a story about "Carmot" attached to "Carnot" (GLP_1_..._0138 report).
_PRIVATE_FUNDING_TERMS = (
    "funding", "raised", "raise", "series ", "seed", "financing", "venture",
    "round", "million", "billion", "investment", "invested", "valuation",
    "ipo", "acqui", "merger", "backed", "led by", "capital", "$",
)
_COMPANY_STOP_TOKENS = {
    "pharma", "pharmaceuticals", "therapeutics", "therapeutic", "bio", "biotech",
    "biosciences", "sciences", "science", "inc", "ltd", "plc", "llc", "co", "corp",
    "holdings", "group", "labs", "laboratories", "ag", "sa", "the", "and",
}
_FUNDING_AMOUNT_RE = re.compile(r"\$\s?\d[\d,.]*\s?(?:billion|million|bn|b|m)\b", re.I)
_ROUND_RE = re.compile(r"\b(series\s+[a-f]|pre-seed|seed|ipo)\b", re.I)


def _company_tokens(name: str) -> list[str]:
    """Distinctive lowercase tokens of a company name (corporate/generic
    designators removed) used to require a snippet is actually about the company."""
    toks = re.findall(r"[a-z0-9]+", (name or "").lower())
    distinctive = [t for t in toks if len(t) > 3 and t not in _COMPANY_STOP_TOKENS]
    return distinctive or toks


def _snippet_is_relevant(text: str, tokens: list[str]) -> bool:
    t = (text or "").lower()
    return (any(tok in t for tok in tokens)
            and any(term in t for term in _PRIVATE_FUNDING_TERMS))


# ── Web-funding result identity (R2, closes F9c) ────────────────────────────
# The relevance gate above proves a result mentions the requested company's
# token and financing terms. It does NOT prove the result is ABOUT the
# requested company: a PitchBook profile for "Carnot Laboratories" passes the
# gate for "Carnot Pharma" (the GLP_1 F9c shipped-wrong-company defect). The
# check below extracts the result TITLE's own entity name and routes it
# through the run's ONE resolver (utils.text, T110). Identity is a declared
# fact, never a similarity call: attach on an exact canonical-key match or a
# profile-declared alias, withhold on a profile-declared distinct pair, and
# withhold pending adjudication when neither is declared. The mechanism knows
# no company names; declarations live in the profile's entity_aliases with
# mandatory source and as_of.

PRIVATE_FUNDING_ENTITY_METHOD = (
    "web-funding result identity check: the company name in the result's "
    "title is routed through the run's entity resolver (utils.text, T110) and "
    "compared to the requested watchlist name on full identity keys "
    "(descriptors retained; similarity is not identity); the result is "
    "attached only on an exact or profile-declared match, withheld when the "
    "profile declares the pair distinct, and withheld pending entity_aliases "
    "adjudication when identity is unconfirmed")

FUNDING_ENTITY_CONFIRMED   = "confirmed"
FUNDING_ENTITY_DISTINCT    = "declared_distinct"
FUNDING_ENTITY_UNCONFIRMED = "unconfirmed"
FUNDING_ENTITY_UNCHECKED   = "unchecked"

_TITLE_ENTITY_RE = re.compile(r"[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*")

# Generic capitalized title furniture ("Carnot Laboratories Company Profile",
# "Carmot Therapeutics Raises ...") trimmed from the END of an extracted
# phrase. Title grammar, not company knowledge — the same words follow every
# company name in these page titles. Mis-trim fails CONSERVATIVE: a phrase
# left too long can only downgrade a match to unconfirmed (withheld and
# disclosed), never upgrade a mismatch to attached.
_TITLE_TRAILING_NOISE = {
    "company", "profile", "overview", "news", "funding", "valuation",
    "raises", "announces", "closes", "secures", "completes", "launches",
}


def _extract_result_entity(title: str, tokens: list[str]) -> str:
    """The capitalized name phrase in a result TITLE that contains one of the
    requested company's distinctive tokens ('' when none), with generic
    trailing title words trimmed. TITLE only: a title names its subject,
    while a snippet may merely mention neighbours."""
    for m in _TITLE_ENTITY_RE.finditer(title or ""):
        phrase = m.group(0).strip()
        low = phrase.lower()
        if not any(tok in low for tok in tokens):
            continue
        words = phrase.split()
        while words and words[-1].lower().strip(".,:;") in _TITLE_TRAILING_NOISE:
            words.pop()
        trimmed = " ".join(words).strip()
        if trimmed and any(tok in trimmed.lower() for tok in tokens):
            return trimmed
        return phrase
    return ""


def _funding_result_entity_state(company_name: str, result_entity: str,
                                 entity_resolver) -> str:
    """Classify the result's entity against the requested name. UNCHECKED
    when no resolver was supplied or no name could be extracted — recorded as
    such in the note, never silently upgraded to a match."""
    if entity_resolver is None or not result_entity:
        return FUNDING_ENTITY_UNCHECKED
    if entity_resolver.same_entity(result_entity, company_name):
        return FUNDING_ENTITY_CONFIRMED
    if entity_resolver.declared_distinct(result_entity, company_name):
        return FUNDING_ENTITY_DISTINCT
    return FUNDING_ENTITY_UNCONFIRMED


def _extract_funding_context(results: list[dict], tokens: list[str],
                             company_name: str = "",
                             entity_resolver=None) -> Optional[dict]:
    """From the first RELEVANT web result, extract a concise funding signal
    (round / amount / acquisition) plus its source URL and recency, and
    classify the result's OWN entity name against the requested company
    (entity_state / result_entity keys). Returns None if no result is about
    this company's financing. The first relevant result is THE candidate —
    scanning past a mismatched one would quietly attach a lower-ranked result
    whose entity could not be read, sidestepping the very gate F9c needs."""
    for r in (results or []):
        title   = (r.get("title") or "").strip()
        snippet = (r.get("snippet") or "").strip()
        blob    = f"{title}. {snippet}"
        if not _snippet_is_relevant(blob, tokens):
            continue
        bits = []
        rnd = _ROUND_RE.search(blob)
        amt = _FUNDING_AMOUNT_RE.search(blob)
        if rnd:
            bits.append(rnd.group(0).title())
        if amt:
            bits.append(amt.group(0).replace(" ", ""))
        if not bits and re.search(r"\bacqui", blob, re.I):
            bits.append("acquisition reported")
        summary = ", ".join(bits) if bits else (title or "funding activity reported")
        pub = r.get("published")
        ent = _extract_result_entity(title, tokens)
        state = _funding_result_entity_state(company_name, ent, entity_resolver)
        return {"summary": summary, "url": r.get("url") or "",
                "when": f" ({pub[:10]})" if pub else "",
                "result_entity": ent, "entity_state": state}
    return None


def get_private_company_snapshot(company_name: str, web_search_fn=None,
                                 entity_resolver=None) -> dict:
    tokens = _company_tokens(company_name)
    ctx, failed = None, None
    if web_search_fn:
        try:
            results = web_search_fn(f"{company_name} funding round financing") or []
            ctx = _extract_funding_context(results, tokens,
                                           company_name=company_name,
                                           entity_resolver=entity_resolver)
        except Exception as e:
            failed = str(e)

    state = (ctx or {}).get("entity_state")
    warning = None
    if ctx and state == FUNDING_ENTITY_DISTINCT:
        src = f" [withheld result source: {ctx['url']}]" if ctx.get("url") else ""
        data_note = (f"{company_name} is a private company — no EDGAR CIK. A web "
                     f"funding result was WITHHELD: its title names "
                     f"'{ctx['result_entity']}', which the profile declares "
                     f"distinct from '{company_name}' (entity_aliases "
                     f"distinct_from).{src} Method: "
                     f"{PRIVATE_FUNDING_ENTITY_METHOD}.")
        warning = (f"web funding result WITHHELD for private company "
                   f"'{company_name}': result title names "
                   f"'{ctx['result_entity']}' (declared distinct).")
    elif ctx and state == FUNDING_ENTITY_UNCONFIRMED:
        src = f" [withheld result source: {ctx['url']}]" if ctx.get("url") else ""
        data_note = (f"{company_name} is a private company — no EDGAR CIK. A web "
                     f"funding result was WITHHELD: its title names "
                     f"'{ctx['result_entity']}' and identity with "
                     f"'{company_name}' is unconfirmed — no profile declaration "
                     f"either way. Pending entity_aliases adjudication (aliases "
                     f"if the same company, distinct_from if not).{src} Method: "
                     f"{PRIVATE_FUNDING_ENTITY_METHOD}.")
        warning = (f"web funding result WITHHELD for private company "
                   f"'{company_name}': result title names "
                   f"'{ctx['result_entity']}' (identity unconfirmed; pending "
                   f"entity_aliases adjudication).")
    elif ctx:
        src = f" [source: {ctx['url']}]" if ctx.get("url") else ""
        if state == FUNDING_ENTITY_CONFIRMED:
            ident = (f" [result entity '{ctx['result_entity']}' confirmed as "
                     f"'{company_name}' by profile declaration / exact "
                     f"identity key]")
        else:
            ident = (" [result entity not separately verified: no resolver "
                     "supplied or no company name extracted from the result "
                     "title; relevance gate only]")
        data_note = (f"Web-sourced funding signal{ctx['when']}: "
                     f"{ctx['summary']}.{src}{ident}")
    elif failed:
        data_note = (f"{company_name} is a private company — no EDGAR CIK; web "
                     f"search failed ({failed}).")
    else:
        data_note = (f"{company_name} is a private company — no EDGAR CIK; no "
                     f"relevant funding information retrieved via web search.")

    snap = {
        "company": company_name, "mode": "private",
        "cash_position_usd": None, "quarterly_burn_usd": None,
        "rd_allocation_pct": None, "runway_months": None,
        "bd_classification": "Private company — financials not publicly disclosed",
        "runway_class": RUNWAY_CLASS_PRIVATE,
        "data_note": data_note,
        "funding_entity_state": state,
        "funding_result_entity": (ctx or {}).get("result_entity", ""),
    }
    if warning:
        snap["_data_warning"] = warning
    return snap


# ---------------------------------------------------------------------------
# Entry point for runner.py Step 16
# ---------------------------------------------------------------------------

def build_financial_deep_dive(
    competitors: list[str],
    small_caps: list[str],
    private_watchlist: list[str],
    edgar_filing_text: list[dict],
    earnings_call_intel: list[dict],
    product_revenue_map: dict[str, dict[str, list[str]]],
    prior_financials: Optional[dict] = None,
    guidance_resolver=None,
    web_search_fn=None,
    pipeline_drug_names: Optional[list[str]] = None,
    product_revenue_resolver=None,
    competitor_company_names: Optional[dict[str, str]] = None,
    product_commercial_status: Optional[dict[str, dict[str, str]]] = None,
    entity_resolver=None,
) -> dict:
    # entity_resolver: OPTIONAL utils.text.EntityResolver for this run (T110).
    # Used only to look up the declared company name behind a ticker before
    # EDGAR is asked; it never renames a company in the output, and a run
    # without one behaves exactly as it did pre-T110.
    # product_commercial_status: OPTIONAL per-ticker → per-product qualitative
    # status from the profile ({ticker: {product: "pre_commercial"|"marketed"}}).
    # This is the ONLY product-specific fact taken from the profile and it
    # carries NO dollar value — "on the market or not" does not drift with
    # inflation. Everything else (the company total, the guidance envelope, the
    # source span) is corroborated dynamically from the current filing. Absent →
    # all products treated as marketed.
    product_commercial_status = product_commercial_status or {}
    prior_financials          = prior_financials or {"guidance": {}, "runway": {}, "product_revenue": {}}
    pipeline_drug_names        = pipeline_drug_names or []
    competitor_company_names   = competitor_company_names or {}

    guidance_revisions: list[dict] = []
    cash_runway:        list[dict] = []
    product_revenue:    list[dict] = []
    pressure_signals:   list[dict] = []

    # ── Competitors: guidance + product revenue + pressure signals ─────────
    # NOT cash_runway — see module docstring.
    for ticker in competitors:
        company_name = competitor_company_names.get(ticker, ticker)
        print(f"  FinancialIntel: {ticker} ({company_name})")

        text = _gather_financial_texts(ticker, company_name, edgar_filing_text, earnings_call_intel)

        guidance_quarterly_usd_m = None
        if guidance_resolver and text:
            try:
                for fig in guidance_resolver(text, company_name):
                    rev = compute_guidance_revision(company_name, fig, prior_financials)
                    if not rev["linked_asset"]:
                        rev["linked_asset"] = _find_linked_asset(ticker, earnings_call_intel, pipeline_drug_names)
                    if rev["linked_asset"] and rev["direction"] == "Raised":
                        rev["pipeline_signal"] = (
                            f"{rev['linked_asset'].title()}: " + rev["pipeline_signal"] +
                            f" Tied to {rev['linked_asset']} per company commentary."
                        )
                    guidance_revisions.append(rev)
                    # Derive a fallback quarterly-total envelope from ANNUAL
                    # revenue guidance (midpoint / 4). Independent of our own
                    # snapshot; only used when the filing's explicit total is
                    # not parseable. Skip %-denominated (e.g. EPS/CER) guidance.
                    metric = (rev.get("metric") or "").lower()
                    nr     = rev.get("new_range") or {}
                    unit   = (nr.get("unit") or "")
                    # Requires a KNOWN unit: the old code fell back to "USD B", so a
                    # figure actually stated in millions produced an envelope 1000x too
                    # large. With no unit we cannot scale the number at all, so skip
                    # this derivation rather than fabricate a magnitude.
                    if ("revenue" in metric and unit and "%" not in unit
                            and nr.get("low") is not None and nr.get("high") is not None):
                        _, gmult = _parse_unit(unit)
                        annual_mid_m = ((nr["low"] + nr["high"]) / 2.0) * gmult
                        q = annual_mid_m / 4.0
                        if guidance_quarterly_usd_m is None or q > guidance_quarterly_usd_m:
                            guidance_quarterly_usd_m = q
            except Exception as e:
                print(f"    Guidance extraction failed for {ticker}: {e}")

        products = product_revenue_map.get(ticker, {})
        if products and text:
            product_revenue.extend(get_product_revenue(
                ticker, company_name, products, text, prior_financials, product_revenue_resolver,
                commercial_status=product_commercial_status.get(ticker, {}),
                guidance_quarterly_usd_m=guidance_quarterly_usd_m,
            ))

        pressure_signals.extend(get_financial_pressure_signals(ticker, company_name))

    # ── Small caps: cash runway (+ pressure signals) ────────────────────────
    # T110: the run's entity resolver supplies the declared company name for a
    # ticker, so the EDGAR name fallback has something to search for. Absent a
    # resolver the profile's own ticker map is used, and absent both the
    # behaviour is exactly pre-T110 — no engine default invents a name.
    for ticker in small_caps:
        print(f"  FinancialIntel: {ticker} (small cap)")
        hint = ""
        if entity_resolver is not None:
            try:
                resolved, _basis = entity_resolver.canonical(ticker)
                hint = resolved if resolved and resolved != ticker else ""
            except Exception as e:                       # never fail a run on a hint
                print(f"    entity resolver unavailable for {ticker}: {e}")
        if not hint:
            hint = competitor_company_names.get(ticker, "")
        cr = get_cash_and_burn(ticker, hint)
        cash_runway.append(cr)
        if cr.get("mode") != "private":
            pressure_signals.extend(get_financial_pressure_signals(ticker, cr.get("company", ticker)))

    # ── Private watchlist: cash runway (web-search narrative only) ─────────
    for company_name in private_watchlist:
        print(f"  FinancialIntel: {company_name} (private)")
        cash_runway.append(get_private_company_snapshot(
            company_name, web_search_fn, entity_resolver=entity_resolver))

    return {
        "guidance_revisions": guidance_revisions,
        "cash_runway": cash_runway,
        "product_revenue": product_revenue,
        "financial_pressure_signals": pressure_signals,
        # data_warnings: collect all _data_warning fields from product_revenue records
        # so the LLM can surface them in financial_intelligence.data_warnings without
        # having to scan all records itself.
        "data_warnings": [
            r["_data_warning"]
            for r in product_revenue
            if r.get("_data_warning")
        ] + [
            # R2: withheld web-funding attachments (entity unresolved) surface
            # here so the warn ladder reaches the run's warning block instead
            # of dying in stdout.
            r["_data_warning"]
            for r in cash_runway
            if r.get("_data_warning")
        ],
    }