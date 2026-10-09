"""Live checks for M02 part 1 (opt-in): EFTS behaviour the breadth counts rely on.

    uv run python scripts/run_live.py m02-probe tests/live/test_m02_live.py

About 10 SEC requests. Prints what EFTS returns; asserts only that calls succeed.
Answers (D-M02-14): entity_filter bucket count and sum_other_doc_count; whether
forms=10-K includes 10-K/A; NEAR(n) and OR through the API; form.gz availability.
"""

from __future__ import annotations

from collections import Counter

import pytest

from engine.sec.client import SecClient, user_agent_from_env, utc_now
from engine.sec.fulltext import EFTS_URL, parse_entities, search
from engine.sec.results import Ok
from engine.store.db import open_db
from engine.store.http import SqliteCache, SqliteFetchLog
from engine.themes.universe import ensure_quarters, filers

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    folder = tmp_path_factory.mktemp("m02live")
    engine = open_db("engine", folder)
    corpus = open_db("corpus", folder)
    client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=SqliteFetchLog(engine))
    yield client, engine
    engine.close()
    corpus.close()


def raw(client, q, forms="10-K", start="2025-01-01", end="2025-12-31"):
    params = {"q": q, "forms": forms, "dateRange": "custom", "startdt": start, "enddt": end}
    res = client.get_json(EFTS_URL, params, ttl_s=0)
    assert isinstance(res, Ok), res
    total = res.data["hits"]["total"]
    return res.data, total.get("value"), total.get("relation")


def test_entity_summary_and_amendments(live):
    client, engine = live
    data, total, rel = raw(client, '"artificial intelligence"')
    aggs = data.get("aggregations") or {}
    print(f"\n'artificial intelligence' 10-K 2025: total {total} ({rel})")
    print(f"aggregation keys: {sorted(aggs)}")
    ent = aggs.get("entity_filter") or {}
    print(f"entity_filter: {len(ent.get('buckets') or [])} buckets, keys {sorted(ent)}")
    entities, other = parse_entities(data)
    print(f"parsed entities: {len(entities)}, sum_other_doc_count: {other}")
    print(f"first bucket keys: {[b.get('key') for b in (ent.get('buckets') or [])[:3]]}")
    forms = Counter(h["_source"].get("form") for h in data["hits"]["hits"])
    print(f"forms among first 100 hits with forms=10-K: {dict(forms)}")
    _, amend_total, _ = raw(client, '"artificial intelligence"', forms="10-K/A")
    print(f"forms=10-K/A total: {amend_total}")
    res = search(client, engine, '"artificial intelligence"', forms=("10-K",),
                 start="2025-01-01", end="2025-12-31", now=utc_now(), max_hits=200,
                 allow_fallback=False)  # fmt: skip
    assert isinstance(res, Ok), res
    print(f"search(): {len(res.data.hits)} hits fetched in 2 pages, complete={res.data.complete}")


def test_near_and_or(live):
    client, _ = live
    _, hbm, _ = raw(client, '"high bandwidth memory"')
    _, near, _ = raw(client, '"high bandwidth memory" NEAR(10) capacity')
    _, cap, _ = raw(client, "capacity")
    print(f"\n'high bandwidth memory' {hbm}; NEAR(10) capacity {near}; capacity alone {cap}")
    _, a, _ = raw(client, '"HBM3E"')
    _, b, _ = raw(client, '"HBM4"')
    _, both, _ = raw(client, '"HBM3E" OR "HBM4"')
    print(f"'HBM3E' {a}; 'HBM4' {b}; OR {both} (a working OR is ≥ max and ≤ sum)")


def test_form_index_quarter(live):
    client, engine = live
    res = ensure_quarters(client, engine, [(2025, 1)], utc_now())
    print(f"\nform index 2025 Q1: {res}")
    src = engine.execute("SELECT source_ref FROM form_index").fetchone()
    print(f"source: {src[0] if src else None}")
    for fam in ("10-K", "10-Q", "8-K", "20-F"):
        print(f"  distinct filers {fam} 2025 Q1: {filers(engine, fam, '2025-01-01', '2025-03-31')}")
    assert res[0].status == "fetched"
