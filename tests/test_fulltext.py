from __future__ import annotations

import json
from urllib.parse import urlencode

import pytest

from engine.sec.fulltext import (
    EFTS_URL,
    VARIANT_PHRASE,
    VARIANT_TERMS,
    QueryError,
    count_by_window,
    merge_by_accession,
    normalize_phrase,
    search,
    search_page,
    yearly_windows,
)
from engine.sec.results import Failed, Ok
from tests.conftest import FakeTransport, ok

FORMS = ("10-K",)


class EftsTransport(FakeTransport):
    """Routes EFTS calls by their query parameters (one URL, many queries)."""

    def __init__(self, pages):
        super().__init__({})
        self.pages = pages  # (q, startdt, from) → list of responses

    def __call__(self, url, params, headers):
        self.calls.append((url, dict(params) if params else None, dict(headers)))
        assert url == EFTS_URL
        key = (params["q"], params["startdt"], int(params.get("from", 0)))
        queue = self.pages.get(key)
        if not queue:
            raise AssertionError(f"unexpected EFTS query {key}")
        return queue.pop(0) if len(queue) > 1 else queue[0]


def efts(total, hits, relation="eq"):
    return ok(json.dumps({
        "hits": {
            "total": {"value": total, "relation": relation},
            "hits": [
                {"_id": f"{acc}:{fname}",
                 "_source": {"ciks": [cik], "display_names": [f"{name}  (TCK)  (CIK {cik})"],
                             "form": "10-K", "root_forms": ["10-K"], "file_date": "2025-10-04",
                             "adsh": acc, "period_ending": "2025-08-28", "sics": sics,
                             "file_description": "10-K"}}
                for acc, fname, cik, name, sics in hits
            ],
        }
    }).encode())  # fmt: skip


HIT_MU = (
    "0000723125-25-000030",
    "mu-20250828.htm",
    "0000723125",
    "MICRON TECHNOLOGY INC",
    ["3674"],
)
HIT_NV = ("0001045810-25-000020", "nvda-20250126.htm", "0001045810", "NVIDIA CORP", ["3674"])
HIT_BANK = ("0000019617-25-000010", "jpm-10k.htm", "0000019617", "JPMORGAN CHASE", ["6021"])
HIT_NOSIC = ("0009999999-25-000001", "x.htm", "0009999999", "NO SIC CO", [])
Q = '"high bandwidth memory"'


@pytest.mark.parametrize(
    ("raw", "norm"),
    [("high bandwidth memory", Q), (Q, Q), ('  "HBM3E" ', '"HBM3E"'), ("a   b", '"a b"')],
)
def test_normalize_phrase(raw, norm):
    assert normalize_phrase(raw) == norm


@pytest.mark.parametrize(
    "bad",
    ['"license agreement" "milestone"', "license OR merger", "(hbm)", "file_date:[2026", '""',
     'half "quoted'],
)  # fmt: skip
def test_bad_queries_rejected(bad):
    with pytest.raises(QueryError):
        normalize_phrase(bad)


def test_search_parses_filters_and_stores(make_client, dbs, clock):
    engine, _ = dbs
    transport = EftsTransport(
        {(Q, "2025-01-01", 0): [efts(4, [HIT_MU, HIT_NV, HIT_BANK, HIT_NOSIC])]}
    )
    res = search(make_client(transport), engine, "high bandwidth memory", forms=FORMS,
                 start="2025-01-01", end="2025-12-31", now=clock.now(), sics=["3674"])  # fmt: skip
    assert isinstance(res, Ok)
    r = res.data
    assert (r.total, r.capped, r.variant) == (4, False, VARIANT_PHRASE)
    assert [h.entity_name for h in r.hits] == ["MICRON TECHNOLOGY INC", "NVIDIA CORP", "NO SIC CO"]
    assert r.sic_dropped == 1  # the bank; the hit without SIC codes is kept
    mu = r.hits[0]
    assert mu.url == ("https://www.sec.gov/Archives/edgar/data/723125/"
                      "000072312525000030/mu-20250828.htm")  # fmt: skip
    params = transport.calls[0][1]
    assert params == {"q": Q, "forms": "10-K", "dateRange": "custom", "startdt": "2025-01-01",
                      "enddt": "2025-12-31"}  # fmt: skip
    row = engine.execute("SELECT * FROM fulltext_query").fetchone()
    assert (row["total"], row["hits_kept"], row["sic_filter"]) == (4, 3, '["3674"]')
    assert engine.execute("SELECT count(*) FROM fulltext_hit").fetchone()[0] == 3


def test_search_pages_until_max_hits(make_client, dbs, clock):
    engine, _ = dbs
    transport = EftsTransport({
        (Q, "2025-01-01", 0): [efts(250, [HIT_MU, HIT_NV])],
        (Q, "2025-01-01", 2): [efts(250, [HIT_BANK, HIT_NOSIC])],
    })  # fmt: skip
    res = search(make_client(transport), engine, Q, forms=FORMS, start="2025-01-01",
                 end="2025-12-31", now=clock.now(), max_hits=3)  # fmt: skip
    assert isinstance(res, Ok) and len(res.data.hits) == 3 and res.data.total == 250


def test_cap_is_flagged(make_client, dbs, clock):
    engine, _ = dbs
    transport = EftsTransport({(Q, "2025-01-01", 0): [efts(10000, [HIT_MU], relation="gte")]})
    res = search(make_client(transport), engine, Q, forms=FORMS, start="2025-01-01",
                 end="2025-12-31", now=clock.now(), max_hits=1)  # fmt: skip
    assert res.data.capped and res.data.total == 10000


def test_server_error_falls_back_to_terms_and_labels_it(make_client, dbs, clock):
    engine, _ = dbs
    transport = EftsTransport({
        (Q, "2025-01-01", 0): [ok(b"", 500)],
        ("high bandwidth memory", "2025-01-01", 0): [efts(9, [HIT_MU])],
    })  # fmt: skip
    res = search_page(make_client(transport), Q, forms=FORMS, start="2025-01-01",
                      end="2025-12-31")  # fmt: skip
    assert isinstance(res, Ok) and res.data.variant == VARIANT_TERMS and res.data.total == 9


def test_client_error_does_not_fall_back(make_client, clock):
    transport = EftsTransport({(Q, "2025-01-01", 0): [ok(b"", 400)]})
    res = search_page(make_client(transport), Q, forms=FORMS, start="2025-01-01",
                      end="2025-12-31")  # fmt: skip
    assert isinstance(res, Failed) and res.status == 400 and len(transport.calls) == 1


def test_count_by_window_keeps_failures_missing(make_client, dbs, clock):
    engine, _ = dbs
    transport = EftsTransport({
        (Q, "2023-01-01", 0): [efts(40, [])],
        (Q, "2024-01-01", 0): [ok(b"", 503)],
        (Q, "2025-01-01", 0): [efts(310, [])],
    })  # fmt: skip
    counts = count_by_window(make_client(transport), engine, Q, forms=FORMS,
                             windows=yearly_windows(2023, 2025), now=clock.now())  # fmt: skip
    assert [(c.start, c.total) for c in counts] == [
        ("2023-01-01", 40), ("2024-01-01", None), ("2025-01-01", 310)
    ]  # fmt: skip
    assert counts[1].error and "503" in counts[1].error
    assert [c[1]["q"] for c in transport.calls].count("high bandwidth memory") == 0  # no fallback
    stored = engine.execute("SELECT start_date, total FROM fulltext_query ORDER BY 1").fetchall()
    assert [tuple(r) for r in stored] == [("2023-01-01", 40), ("2025-01-01", 310)]


def test_merge_by_accession(make_client, dbs, clock):
    engine, _ = dbs
    q2 = '"HBM3E"'
    transport = EftsTransport({
        (Q, "2025-01-01", 0): [efts(2, [HIT_MU, HIT_NV])],
        (q2, "2025-01-01", 0): [efts(1, [HIT_MU])],
    })  # fmt: skip
    client = make_client(transport)
    a = search(client, engine, Q, forms=FORMS, start="2025-01-01", end="2025-12-31",
               now=clock.now())  # fmt: skip
    b = search(client, engine, q2, forms=FORMS, start="2025-01-01", end="2025-12-31",
               now=clock.now())  # fmt: skip
    merged = merge_by_accession([a.data, b.data])
    assert merged[HIT_MU[0]] == [Q, q2] and merged[HIT_NV[0]] == [Q]


def test_cache_key_distinguishes_queries():
    # Same URL, different params must not share a cache entry.
    from engine.sec.client import cache_key

    one = cache_key(EFTS_URL, {"q": Q, "startdt": "2025-01-01"})
    two = cache_key(EFTS_URL, {"q": '"HBM3E"', "startdt": "2025-01-01"})
    assert one != two and urlencode({"q": Q}) in one
