from __future__ import annotations

import json

import pytest

from engine.sec.results import NotFound, Ok
from engine.sec.xbrl_facts import FACTS_URL, classify, get_series, sync_facts
from tests.conftest import FakeTransport, ok

CIK = "0000000042"
URL = FACTS_URL.format(cik=CIK)

# Fiscal year ends late September (52/53 weeks), like Apple.
FY23 = ("2022-09-25", "2023-09-30")  # 53 weeks
Q1, Q2, Q3, Q4 = (
    ("2023-10-01", "2023-12-30"),
    ("2023-12-31", "2024-03-30"),
    ("2024-03-31", "2024-06-29"),
    ("2024-06-30", "2024-09-28"),
)
H1, M9, FY24 = (
    ("2023-10-01", "2024-03-30"),
    ("2023-10-01", "2024-06-29"),
    ("2023-10-01", "2024-09-28"),
)
Q1_25 = ("2024-09-29", "2024-12-28")


def f(period, val, accn, filed, form="10-Q"):
    start, end = period
    return {"start": start, "end": end, "val": val, "accn": accn, "fy": 2024, "fp": "Q1",
            "form": form, "filed": filed}  # fmt: skip


def inst(end, val, accn, filed, form="10-K"):
    return {"end": end, "val": val, "accn": accn, "form": form, "filed": filed}


A_Q1, A_Q2, A_Q3, A_K24, A_Q1_25, A_K23 = (
    "0000000042-24-000001",
    "0000000042-24-000002",
    "0000000042-24-000003",
    "0000000042-24-000004",
    "0000000042-25-000001",
    "0000000042-23-000009",
)

FACTS = {
    "cik": 42,
    "entityName": "Example Semis Inc.",
    "facts": {
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {
                    "USD": [
                        f(Q1, 100, A_Q1, "2024-02-02"),
                        f(Q1, 102, A_Q1_25, "2025-01-31"),  # restated in next year's comparative
                        f(Q2, 90, A_Q2, "2024-05-03"),
                        f(H1, 190, A_Q2, "2024-05-03"),
                        f(Q3, 85, A_Q3, "2024-08-02"),
                        f(M9, 275, A_Q3, "2024-08-02"),
                        f(FY24, 400, A_K24, "2024-11-01", "10-K"),
                        f(Q1_25, 110, A_Q1_25, "2025-01-31"),
                    ],
                    "EUR": [f(Q1, 92, A_Q1, "2024-02-02")],
                }
            },
            "SalesRevenueNet": {  # older tag, before the switch
                "units": {"USD": [f(FY23, 380, A_K23, "2023-11-03", "10-K")]}
            },
            "PaymentsToAcquirePropertyPlantAndEquipment": {  # cash flow: year-to-date only
                "units": {
                    "USD": [
                        f(Q1, 10, A_Q1, "2024-02-02"),
                        f(H1, 25, A_Q2, "2024-05-03"),
                        f(M9, 33, A_Q3, "2024-08-02"),
                        f(FY24, 50, A_K24, "2024-11-01", "10-K"),
                    ]
                }
            },
            "EarningsPerShareDiluted": {
                "units": {
                    "USD/shares": [
                        f(Q1, 1.5, A_Q1, "2024-02-02"),
                        f(M9, 4.0, A_Q3, "2024-08-02"),
                        f(FY24, 6.0, A_K24, "2024-11-01", "10-K"),
                    ]
                }
            },
            "CashAndCashEquivalentsAtCarryingValue": {
                "units": {
                    "USD": [
                        inst("2023-12-30", 28, A_Q1, "2024-02-02", "10-Q"),
                        inst("2024-09-28", 30, A_K24, "2024-11-01"),
                        inst("2024-09-28", 30, A_Q1_25, "2025-01-31", "10-Q"),
                    ]
                }
            },
        },
        "dei": {
            "EntityCommonStockSharesOutstanding": {
                "units": {"shares": [inst("2024-10-18", 15000, A_K24, "2024-11-01")]}
            }
        },
    },
}


def facts_route(data=None):
    return {URL: [ok(json.dumps(data or FACTS).encode())]}


def values(rows, which="latest"):
    return [(r.end, getattr(r, which).value) for r in rows]


@pytest.mark.parametrize(
    ("start", "end", "label"),
    [
        (None, "2024-09-28", "I"),
        ("2023-10-01", "2023-12-30", "Q"),
        ("2024-06-30", "2024-10-05", "Q"),  # 14-week quarter
        ("2023-10-01", "2024-03-30", "6M"),
        ("2023-10-01", "2024-06-29", "9M"),
        ("2023-10-01", "2024-09-28", "FY"),
        ("2022-09-25", "2023-09-30", "FY"),  # 53-week year
        ("2024-01-01", "2024-01-31", None),  # one month: not a reporting period
    ],
)
def test_classify(start, end, label):
    assert classify(start, end) == label


@pytest.fixture
def synced(make_client, dbs, clock):
    engine, _ = dbs
    result = sync_facts(make_client(FakeTransport(facts_route())), engine, CIK, clock.now())
    assert isinstance(result, Ok)
    return engine, result.data


def test_every_fact_version_is_stored(synced):
    engine, summary = synced
    assert summary.facts_seen == summary.facts_new == 21
    q1 = engine.execute(
        "SELECT value, filed FROM fact WHERE tag LIKE 'RevenueFromContract%' AND unit = 'USD' "
        "AND period_start = ? AND period_end = ? ORDER BY filed",
        Q1,
    ).fetchall()
    assert [tuple(r) for r in q1] == [(100, "2024-02-02"), (102, "2025-01-31")]


def test_quarters_reported_and_q4_derived(synced):
    engine, _ = synced
    quarters = get_series(engine, CIK, "revenue", "Q")
    assert values(quarters, "first") == [
        (Q1[1], 100),
        (Q2[1], 90),
        (Q3[1], 85),
        (Q4[1], 125),  # FY 400 − 9M 275
        (Q1_25[1], 110),
    ]
    q4 = quarters[3]
    assert q4.start == Q4[0] and q4.method.startswith("derived")
    assert q4.latest.accession == A_K24


def test_restatement_kept_point_in_time(synced):
    engine, _ = synced
    q1 = get_series(engine, CIK, "revenue", "Q")[0]
    assert (q1.first.value, q1.first.filed) == (100, "2024-02-02")
    assert (q1.latest.value, q1.latest.filed) == (102, "2025-01-31")
    assert q1.restated


def test_tag_switch_merges_into_one_series(synced):
    engine, summary = synced
    fy = get_series(engine, CIK, "revenue", "FY")
    assert values(fy) == [(FY23[1], 380), (FY24[1], 400)]
    assert "us-gaap:SalesRevenueNet" in fy[0].method
    assert set(summary.concepts["revenue"]) == {
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:SalesRevenueNet",
    }


def test_ttm_needs_four_contiguous_quarters(synced):
    engine, _ = synced
    ttm = get_series(engine, CIK, "revenue", "TTM")
    assert values(ttm, "first") == [(Q4[1], 400), (Q1_25[1], 410)]
    assert values(ttm, "latest") == [(Q4[1], 402), (Q1_25[1], 410)]  # restated Q1 flows through
    assert ttm[0].start == Q1[0]


def test_cash_flow_quarters_derived_from_year_to_date(synced):
    engine, _ = synced
    assert values(get_series(engine, CIK, "capex", "Q")) == [
        (Q1[1], 10),
        (Q2[1], 15),
        (Q3[1], 8),
        (Q4[1], 17),
    ]
    assert values(get_series(engine, CIK, "capex", "TTM")) == [(Q4[1], 50)]


def test_per_share_never_derived_or_summed(synced):
    engine, _ = synced
    assert values(get_series(engine, CIK, "eps_diluted", "Q")) == [(Q1[1], 1.5)]
    assert values(get_series(engine, CIK, "eps_diluted", "FY")) == [(FY24[1], 6.0)]
    assert get_series(engine, CIK, "eps_diluted", "TTM") == []


def test_instants(synced):
    engine, _ = synced
    cash = get_series(engine, CIK, "cash", "I")
    assert values(cash) == [("2023-12-30", 28), ("2024-09-28", 30)]
    assert cash[1].first.filed == "2024-11-01" and not cash[1].restated
    shares = get_series(engine, CIK, "shares_outstanding", "I")
    assert (
        shares[0].unit == "shares" and "dei:EntityCommonStockSharesOutstanding" in shares[0].method
    )


def test_units_checked_and_missing_concepts_reported(synced):
    _, summary = synced
    assert summary.skipped_units["revenue"] == (
        "RevenueFromContractWithCustomerExcludingAssessedTax [EUR]",
    )
    missing = {p.path: p for p in summary.missing}
    assert "concept rpo" in missing
    assert "us-gaap:RevenueRemainingPerformanceObligation" in missing["concept rpo"].query
    assert "concept revenue" not in missing


def test_not_refetched_until_due(make_client, dbs, clock):
    engine, _ = dbs
    transport = FakeTransport(facts_route())
    sync_facts(make_client(transport), engine, CIK, clock.now())
    clock.advance(86400)
    again = sync_facts(make_client(transport), engine, CIK, clock.now())
    assert isinstance(again, Ok) and not again.data.refreshed and len(transport.calls) == 1
    assert get_series(engine, CIK, "revenue", "Q")  # series still rebuilt from stored facts

    engine.execute(  # a new 10-Q after the last fetch makes facts due immediately
        "INSERT INTO filing (accession, cik, form, filed, ingested_at) "
        "VALUES ('0000000042-25-000099', ?, '10-Q', ?, 'x')",
        (CIK, clock.now().date().isoformat()),
    )
    engine.execute(
        "INSERT INTO filing_cik (accession, cik) VALUES ('0000000042-25-000099', ?)", (CIK,)
    )
    clock.advance(7 * 3600)  # past the raw cache TTL
    third = sync_facts(make_client(transport), engine, CIK, clock.now())
    assert isinstance(third, Ok) and third.data.refreshed and len(transport.calls) == 2
    assert third.data.facts_new == 0  # same facts: nothing duplicated


def test_no_companyfacts_file_is_not_found(make_client, dbs, clock):
    engine, _ = dbs
    transport = FakeTransport({URL: [ok(b"", 404)]})
    assert isinstance(sync_facts(make_client(transport), engine, CIK, clock.now()), NotFound)
