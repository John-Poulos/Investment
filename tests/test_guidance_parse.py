# ruff: noqa: E501  (fixtures are verbatim release lines)
from __future__ import annotations

from decimal import Decimal

from engine.guidance.parse import find_periods, find_values, parse_release

B = Decimal(10) ** 9
M = Decimal(10) ** 6


def items(text: str):
    """{(metric, basis, period): (low, high)} plus the result."""
    r = parse_release(text)
    return {(i.metric, i.basis, i.period): (i.value.low, i.value.high) for i in r.items}, r


# --- values and periods --------------------------------------------------------


def test_value_forms():
    (v,) = find_values("$56-59 billion")
    assert (v.kind, v.low, v.high) == ("range", 56 * B, 59 * B)
    (v,) = find_values("between $197.0 billion and $202.0 billion")
    assert (v.low, v.high) == (197 * B, 202 * B)
    (v,) = find_values("$108.0 billion, plus or minus 2%")
    assert (v.kind, v.point, v.spread_kind) == ("plusminus", 108 * B, "pct")
    assert (v.low, v.high) == (Decimal("105.84") * B, Decimal("110.16") * B)
    (v,) = find_values("$61.5 billion ± $1.5 billion")
    assert (v.low, v.high) == (60 * B, 63 * B)
    (v,) = find_values("74.0%, plus or minus 50 basis points")
    assert (v.low, v.high, v.spread) == (Decimal("73.5"), Decimal("74.5"), 50)
    (v,) = find_values("$0.53 +/- $0.05 per share")
    assert (v.low, v.high, v.scaled) == (Decimal("0.48"), Decimal("0.58"), False)
    (v,) = find_values("approximately $9.2 billion")
    assert (v.kind, v.low) == ("approx", Decimal("9.2") * B)
    (v,) = find_values("between 15-17%")
    assert (v.unit, v.low, v.high) == ("%", 15, 17)
    (v,) = find_values("52.9% to 53.9%")
    assert (v.low, v.high) == (Decimal("52.9"), Decimal("53.9"))
    (v,) = find_values("$43M")
    assert v.low == 43 * M
    (v,) = find_values("expected to be 900 million.")
    assert (v.unit, v.low) == ("count", 900 * M)


def test_periods():
    labels = lambda t: [p.label for p in find_periods(t)]  # noqa: E731
    assert labels("for the third quarter of fiscal 2027 is") == ["FY2027 Q3"]
    assert labels("Forecasting third-quarter 2026 revenue") == ["FY2026 Q3"]
    assert labels("Q3 FY2027 Outlook") == ["FY2027 Q3"]
    assert labels("FQ1-27") == ["FY2027 Q1"]
    assert labels("For the full year fiscal 2027, NVIDIA expects") == ["FY2027"]
    assert labels("for the remaining quarters of 2026 to be") == ["FY2026 remaining"]
    assert labels("We anticipate 2026 capital expenditures") == ["FY2026"]
    assert labels("$22.5 billion, compared with $17.4 billion in third quarter 2025.") == []
    assert labels("expectations as of July 30, 2026, and") == []


# --- sentences -----------------------------------------------------------------

META = """CFO Outlook Commentary
We expect third quarter 2026 total revenue to be in the range of $61-64 billion. Our guidance assumes foreign currency is an approximately 1% headwind to year-over-year total revenue growth, based on current exchange rates.
We now expect full year 2026 total expenses to be in the range of $165-169 billion.
We continue to expect to deliver operating income this year that is above 2025 operating income.
We anticipate 2026 capital expenditures, including principal payments on finance leases, to be in the range of $130-145 billion, narrowed from our prior outlook of $125-145 billion.
Absent any changes to our tax landscape, we expect our tax rate for the remaining quarters of 2026 to be between 15-17%, an increase from our prior outlook of 13-16%.
"""


def test_meta_sentences_and_priors():
    got, r = items(META)
    assert got == {
        ("revenue", "unspecified", "FY2026 Q3"): (61 * B, 64 * B),
        ("total_expenses", "unspecified", "FY2026"): (165 * B, 169 * B),
        ("capex", "unspecified", "FY2026"): (130 * B, 145 * B),
        ("tax_rate", "unspecified", "FY2026 remaining"): (15, 17),
    }
    assert r.unparsed == []  # FX assumption is skipped, not sent to review
    capex = next(i for i in r.items if i.metric == "capex")
    assert capex.prior is not None and (capex.prior.low, capex.prior.high) == (125 * B, 145 * B)
    assert META[capex.prior.start : capex.prior.end] == "$125-145 billion"
    assert META[capex.value.start : capex.value.end] == "$130-145 billion"
    assert META[capex.quote_start : capex.quote_end].startswith("We anticipate 2026 capital")
    tax = next(i for i in r.items if i.metric == "tax_rate")
    assert (tax.prior.low, tax.prior.high) == (13, 16)


NVDA = """Outlook
NVIDIA’s outlook for the third quarter of fiscal 2027 is as follows:
•Revenue is expected to be $108.0 billion, plus or minus 2%. NVIDIA is not assuming any Data Center compute revenue from China in its outlook.
•GAAP and non-GAAP gross margins are expected to be 74.0%, plus or minus 50 basis points.
•GAAP and non-GAAP operating expenses are expected to be approximately $9.2 billion and $9.0 billion, respectively.
For the full year fiscal 2027, NVIDIA expects GAAP and non-GAAP tax rates to be between 16.0% and 18.0%, excluding any discrete items and material changes to NVIDIA’s tax environment.
"""


def test_nvidia_bullets_heading_period_and_respectively():
    got, r = items(NVDA)
    assert got == {
        ("revenue", "unspecified", "FY2027 Q3"): (Decimal("105.84") * B, Decimal("110.16") * B),
        ("gross_margin", "GAAP", "FY2027 Q3"): (Decimal("73.5"), Decimal("74.5")),
        ("gross_margin", "non-GAAP", "FY2027 Q3"): (Decimal("73.5"), Decimal("74.5")),
        ("operating_expenses", "GAAP", "FY2027 Q3"): (Decimal("9.2") * B, Decimal("9.2") * B),
        ("operating_expenses", "non-GAAP", "FY2027 Q3"): (9 * B, 9 * B),
        ("tax_rate", "GAAP", "FY2027"): (16, 18),
        ("tax_rate", "non-GAAP", "FY2027"): (16, 18),
    }
    assert r.unparsed == []
    rev = next(i for i in r.items if i.metric == "revenue")
    assert NVDA[rev.period_start : rev.period_end] == "third quarter of fiscal 2027"


AMZN = """Third Quarter 2026 Guidance
•Net sales are expected to be between $197.0 billion and $202.0 billion, or to grow between 9% and 12% compared with third quarter 2025. Excluding the impact of Prime Day in both 2025 and 2026, third quarter 2026 year-over-year growth would be nearly 400 basis points higher. This guidance anticipates an unfavorable impact of approximately 80 basis points from foreign exchange rates.
•Operating income is expected to be between $22.5 billion and $26.5 billion, compared with $17.4 billion in third quarter 2025.
"""


def test_amazon_comparison_period_ignored():
    got, r = items(AMZN)
    assert got == {
        ("revenue", "unspecified", "FY2026 Q3"): (197 * B, 202 * B),
        ("operating_income", "unspecified", "FY2026 Q3"): (
            Decimal("22.5") * B,
            Decimal("26.5") * B,
        ),
    }
    assert r.unparsed == []


MRVL = """Third Quarter of Fiscal 2027 Financial Outlook
•Net revenue is expected to be $3.150 billion +/- 5%.
•GAAP gross margin is expected to be 52.9% to 53.9%.
•Non-GAAP operating expenses are expected to be approximately $655 million.
•Diluted weighted-average shares outstanding are expected to be 921 million.
•Non-GAAP diluted net income per share is expected to be $1.10 +/- $0.05 per share.
Net revenue for the second quarter of fiscal 2027 was $2.739 billion, $39.0 million above the mid-point of the Company’s guidance provided on May 27, 2026.
"""


def test_marvell_bullets():
    got, r = items(MRVL)
    assert got == {
        ("revenue", "unspecified", "FY2027 Q3"): (Decimal("2.9925") * B, Decimal("3.3075") * B),
        ("gross_margin", "GAAP", "FY2027 Q3"): (Decimal("52.9"), Decimal("53.9")),
        ("operating_expenses", "non-GAAP", "FY2027 Q3"): (655 * M, 655 * M),
        ("shares_diluted", "unspecified", "FY2027 Q3"): (921 * M, 921 * M),
        ("eps_diluted", "non-GAAP", "FY2027 Q3"): (Decimal("1.05"), Decimal("1.15")),
    }
    assert r.unparsed == [] and r.candidates == 5  # past "guidance provided" is not a candidate


def test_intel_clauses_split_by_semicolon():
    text = (
        "▪Forecasting third-quarter 2026 revenue of $15.8 billion to $16.8 billion; expecting "
        "third-quarter EPS attributable to Intel of $0.31 and non-GAAP EPS attributable to "
        "Intel of $0.38.\n"
    )
    got, _ = items(text)
    assert got == {
        ("revenue", "unspecified", "FY2026 Q3"): (Decimal("15.8") * B, Decimal("16.8") * B),
        ("eps_diluted", "unspecified", "FY2026 Q3"): (Decimal("0.31"), Decimal("0.31")),
        ("eps_diluted", "non-GAAP", "FY2026 Q3"): (Decimal("0.38"), Decimal("0.38")),
    }


def test_infleqtion_outlook_with_prior():
    text = (
        "•2026 Outlook: Updated full-year revenue outlook to approximately $45.1 million, up "
        "from $43 million to include non-cash, accounting-based revenue adjustments.\n"
    )
    _, r = items(text)
    (item,) = r.items
    assert (item.metric, item.period, item.value.kind) == ("revenue", "FY2026", "approx")
    assert item.prior is not None and item.prior.low == 43 * M


def test_unparsed_candidate_goes_to_review():
    text = "Outlook\nWe expect fourth quarter 2026 bookings of $5 billion.\n"
    _, r = items(text)
    assert r.items == [] and len(r.unparsed) == 1
    assert text[r.unparsed[0].start : r.unparsed[0].end].startswith("We expect fourth")


def test_no_guidance_release():
    text = (
        "Business Outlook\nMicrosoft will provide forward-looking guidance in connection with "
        "this quarterly earnings announcement on its earnings conference call and webcast.\n"
        "Revenue was $90.0 billion and increased 18%\n"
    )
    _, r = items(text)
    assert r.items == [] and r.unparsed == [] and r.candidates == 0


# --- tables --------------------------------------------------------------------

INTEL = """Business Outlook
Intel's guidance for the third quarter of 2026 includes both GAAP and non-GAAP estimates as follows:
Q3 2026 | GAAP | Non-GAAP
Revenue
$15.8-16.8 billion
Gross margin | 41.0% | 42.0%
Tax Rate | 1% | 11%
Earnings (Loss) Per Share Attributable to Intel—Diluted | $0.31 | $0.38
Reconciliations between GAAP and non-GAAP financial measures are included below. Actual results may differ materially from Intel’s business outlook as a result of, among other things, the factors described under “Forward-Looking Statements” below.
Q2 2026 Financial Results
Q2 2026 | Q2 2025 | vs. Q2 2025
Revenue ($B) | $16.1 | $12.9 | up 25%
"""


def test_intel_outlook_table():
    got, r = items(INTEL)
    assert got == {
        ("revenue", "GAAP", "FY2026 Q3"): (Decimal("15.8") * B, Decimal("16.8") * B),
        ("revenue", "non-GAAP", "FY2026 Q3"): (Decimal("15.8") * B, Decimal("16.8") * B),
        ("gross_margin", "GAAP", "FY2026 Q3"): (41, 41),
        ("gross_margin", "non-GAAP", "FY2026 Q3"): (42, 42),
        ("tax_rate", "GAAP", "FY2026 Q3"): (1, 1),
        ("tax_rate", "non-GAAP", "FY2026 Q3"): (11, 11),
        ("eps_diluted", "GAAP", "FY2026 Q3"): (Decimal("0.31"), Decimal("0.31")),
        ("eps_diluted", "non-GAAP", "FY2026 Q3"): (Decimal("0.38"), Decimal("0.38")),
    }
    rev = next(i for i in r.items if i.metric == "revenue")
    assert INTEL[rev.quote_start : rev.quote_end] == "Revenue\n$15.8-16.8 billion"


MICRON = """Quarterly Business Unit Financial Results
FQ4-26 | FQ3-26 | FQ4-25
Revenue
$ | 16,283 | $ | 13,769 | $ | 4,543
Business Outlook
The following table presents Micron’s guidance for the first quarter of 2027:
FQ1-27
GAAP(1) Outlook

Non-GAAP(2) Outlook
Revenue
$61.5 billion ± $1.5 billion | $61.5 billion ± $1.5 billion
Gross margin
Approximately 85.95% | Approximately 86.25%
Operating expenses
Approximately $2.31 billion | Approximately $2.06 billion
Diluted earnings per share
$37.84 ± $1.00 | $38.15 ± $1.00
RECONCILIATION OF GAAP TO NON-GAAP OUTLOOK
FQ1-27 | GAAP Outlook | Adjustments | Non-GAAP Outlook
Gross margin
Approximately 85.95% | 0.30 | % | A | Approximately 86.25%
Operating expenses
Approximately $2.31 billion | $253 million | B | Approximately $2.06 billion
"""


def test_micron_tables_skip_results_and_read_adjustment_columns():
    got, r = items(MICRON)
    assert got == {
        ("revenue", "GAAP", "FY2027 Q1"): (60 * B, 63 * B),
        ("revenue", "non-GAAP", "FY2027 Q1"): (60 * B, 63 * B),
        ("gross_margin", "GAAP", "FY2027 Q1"): (Decimal("85.95"), Decimal("85.95")),
        ("gross_margin", "non-GAAP", "FY2027 Q1"): (Decimal("86.25"), Decimal("86.25")),
        ("operating_expenses", "GAAP", "FY2027 Q1"): (Decimal("2.31") * B, Decimal("2.31") * B),
        ("operating_expenses", "non-GAAP", "FY2027 Q1"): (Decimal("2.06") * B, Decimal("2.06") * B),
        ("eps_diluted", "GAAP", "FY2027 Q1"): (Decimal("36.84"), Decimal("38.84")),
        ("eps_diluted", "non-GAAP", "FY2027 Q1"): (Decimal("37.15"), Decimal("39.15")),
    }
    # reconciliation rows repeat the same values (deduplicated by the ledger)
    assert len(r.items) == 12


def test_unscaled_table_money_needs_scale_header():
    text = "Q3 FY2027 Outlook\nGAAP gross margin | 74.0 | %\nGAAP operating expenses | $ | 9.2\n"
    got, _ = items(text)
    assert got == {("gross_margin", "GAAP", "FY2027 Q3"): (74, 74)}
    scaled = "(In Billions; Unaudited)\n" + text
    got, _ = items(scaled)
    assert got[("operating_expenses", "GAAP", "FY2027 Q3")] == (Decimal("9.2") * B,) * 2
