"""scripts/probe_m04.py: registry, selection, local probes on scratch DBs, read-only SEC path.
No network: SEC replies come from FakeTransport."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from engine.sec.client import Breaker, RateLimiter, SecClient
from engine.store.http import SqliteCache, SqliteFetchLog
from tests.conftest import AGENT, FakeTransport, ok

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("probe_m04", ROOT / "scripts" / "probe_m04.py")
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
sys.modules["probe_m04"] = probe  # dataclasses look the module up
spec.loader.exec_module(probe)


def test_registry_and_selection():
    ids = [p.id for p in probe.PROBES]
    assert len(ids) == len(set(ids))
    assert {p.kind for p in probe.PROBES} == {"local", "sec", "tiingo"}
    assert probe.parse_only(" s5, t2,S5 ") == ["S5", "T2"]
    assert probe.parse_only(None) == []
    with pytest.raises(ValueError, match="X9"):
        probe.parse_only("S1,X9")
    chosen = probe.select(probe.PROBES, [], no_sec=True, no_tiingo=True)
    assert chosen and all(p.kind == "local" for p in chosen)
    assert [p.id for p in probe.select(probe.PROBES, ["T1", "S2"])] == ["S2", "T1"]
    assert probe.main(["--only", "nope"]) == 2


def _seed_company(engine):
    cik, acc, end = "0000050863", "0000050863-26-000011", "2025-12-27"
    engine.execute(
        "INSERT INTO ticker (ticker, cik, exchange, name, valid_from, source) VALUES "
        "('INTC', ?, 'Nasdaq', 'INTEL CORP', '2026-01-01', 'test')",
        (cik,),
    )
    engine.execute(
        "INSERT INTO entity (cik, name, sic, source_ref, fetched_at) VALUES (?, 'INTEL CORP', "
        "'3674', 'test', '2026-01-01')",
        (cik,),
    )
    values = {
        "AssetsCurrent": (None, 60e9), "LiabilitiesCurrent": (None, 30e9),
        "Assets": (None, 200e9), "Liabilities": (None, 90e9),
        "RetainedEarningsAccumulatedDeficit": (None, 50e9),
        "OperatingIncomeLoss": ("2024-12-29", 2e9),
        "Revenues": ("2024-12-29", 53e9),
        "PropertyPlantAndEquipmentNet": (None, 100e9),
    }  # fmt: skip
    for tag, (start, v) in values.items():
        engine.execute(
            "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, "
            "accession, form, filed) VALUES (?, 'us-gaap', ?, 'USD', ?, ?, ?, ?, '10-K', "
            "'2026-01-30')",
            (cik, tag, start, end, v, acc),
        )
    engine.execute(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession,"
        " form, filed) VALUES (?, 'dei', 'EntityCommonStockSharesOutstanding', 'shares', NULL, "
        "'2026-01-23', 4.4e9, ?, '10-K', '2026-01-30')",
        (cik, acc),
    )
    engine.execute(
        "INSERT INTO price_bar (symbol, date, close, source, fetched_at) VALUES "
        "('INTC', '2025-12-26', 20.0, 'tiingo', '2026-01-01')"
    )


def test_local_probes_run_on_scratch_dbs(dbs):
    engine, corpus = dbs
    _seed_company(engine)
    ctx = probe.Ctx(engine, corpus)
    for p in probe.PROBES:
        if p.kind != "local":
            continue
        lines = probe.run_one(ctx, p)
        assert not any("ERROR" in line for line in lines), (p.id, lines)
        assert lines[-1].startswith("  -- 0 SEC request(s)")
    z = "\n".join(probe.run_one(ctx, next(p for p in probe.PROBES if p.id == "L7")))
    # X1 .15 X2 .25 X3 .01 X4 4.4e9*20/90e9 = .978 X5 .265 → 1.2*.15+1.4*.25+3.3*.01+.6*.978+.265
    assert "INTC SIC 3674" in z and "Z = 1.41" in z
    gw = "\n".join(probe.run_one(ctx, next(p for p in probe.PROBES if p.id == "L1")))
    assert "PropertyPlantAndEquipmentNet: 2025 100,000" in gw


def _concept(rows: list[dict]) -> bytes:
    return json.dumps({"units": {"USD": rows}}).encode()


def test_sec_probe_reads_without_writing_cache(dbs, clock):
    engine, corpus = dbs
    base = "https://data.sec.gov/api/xbrl/companyconcept/CIK0001501134"
    rev = [
        {"start": "2019-01-01", "end": "2019-03-31", "val": 40.6e6, "form": "10-Q",
         "filed": "2019-05-08", "accn": "a"},
        {"start": "2019-01-01", "end": "2019-03-31", "val": 41.0e6, "form": "10-Q",
         "filed": "2020-05-08", "accn": "b"},
    ]  # fmt: skip
    cost = [{"start": "2019-01-01", "end": "2019-03-31", "val": 21.3e6, "form": "10-Q",
             "filed": "2019-05-08", "accn": "a"}]  # fmt: skip
    transport = FakeTransport(
        {
            f"{base}/dei/EntityCommonStockSharesOutstanding.json": [ok(b"", status=404)],
            f"{base}/dei/EntityPublicFloat.json": [ok(b"", status=404)],
            f"{base}/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json": [
                ok(_concept(rev))
            ],
            f"{base}/us-gaap/Revenues.json": [ok(b"", status=404)],
            f"{base}/us-gaap/CostOfRevenue.json": [ok(_concept(cost))],
        }
    )
    ctx = probe.Ctx(engine, corpus)
    ctx._client = SecClient(
        AGENT,
        transport=transport,
        cache=probe.ReadOnlyCache(SqliteCache(corpus)),
        log=probe.CountingLog(SqliteFetchLog(engine), ctx),
        limiter=RateLimiter(rate=1e9, clock=clock.mono, sleep=clock.sleep),
        breaker=Breaker(clock=clock.mono),
        now=clock.now,
        sleep=clock.sleep,
    )
    lines = probe.run_one(ctx, next(p for p in probe.PROBES if p.id == "S2"))
    text = "\n".join(lines)
    assert "Q  2019-01-01..2019-03-31: rev 40.6 | — · cost 21.3 (10-Q 2019-05-08)" in text
    assert "dei:EntityPublicFloat: not found" in text
    assert ctx.sec_sent == 5 and len(transport.calls) == 5
    assert corpus.execute("SELECT count(*) FROM http_cache").fetchone()[0] == 0
    assert engine.execute("SELECT count(*) FROM fetch_log").fetchone()[0] == 5


def test_instance_helpers():
    xml = b"""<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:nvda="http://www.nvidia.com/20130127" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
 <xbrli:context id="FY"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier>
  </xbrli:entity><xbrli:period><xbrli:startDate>2012-01-30</xbrli:startDate>
  <xbrli:endDate>2013-01-27</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="SEG"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier>
  <xbrli:segment><xbrldi:explicitMember dimension="a:b">a:c</xbrldi:explicitMember>
  </xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2013-01-27</xbrli:instant>
  </xbrli:period></xbrli:context>
 <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
 <nvda:PurchasesRelatedToPropertyAndEquipmentAndIntangibleAssets contextRef="FY" unitRef="usd"
   decimals="-6">183000000</nvda:PurchasesRelatedToPropertyAndEquipmentAndIntangibleAssets>
 <nvda:Other contextRef="SEG" unitRef="usd" decimals="-6">5</nvda:Other>
</xbrli:xbrl>"""
    assert probe.instance_facts(xml) == [
        ("nvda", "PurchasesRelatedToPropertyAndEquipmentAndIntangibleAssets", "2012-01-30",
         "2013-01-27", 183e6)
    ]  # fmt: skip
    html = (
        '<a href="/Archives/edgar/data/1/2/x-20130127_cal.xml">c</a>'
        '<a href="/Archives/edgar/data/1/2/x-20130127.xml">i</a>'
    )
    assert probe.instance_href(html) == "https://www.sec.gov/Archives/edgar/data/1/2/x-20130127.xml"
    text = "Intro line.\nWe were in compliance with the covenants. Next sentence here."
    out = probe.snips(text, r"in compliance", cap=2, width=60)
    assert out[0].endswith("1 match(es)")
    assert "“We were in compliance with the covenants.”" in out[1]


def test_network_probes_survive_404s(dbs, clock):
    """Every SEC probe and the Tiingo meta probe report a 404 instead of crashing."""
    from engine.prices.tiingo import TiingoClient
    from engine.sec.client import Response

    engine, corpus = dbs
    _seed_company(engine)
    ctx = probe.Ctx(engine, corpus)
    ctx._client = SecClient(
        AGENT,
        transport=lambda url, params, headers: Response(404, b"", {}),
        cache=probe.ReadOnlyCache(SqliteCache(corpus)),
        log=probe.CountingLog(SqliteFetchLog(engine), ctx),
        limiter=RateLimiter(rate=1e9, clock=clock.mono, sleep=clock.sleep),
        breaker=Breaker(clock=clock.mono),
        now=clock.now,
        sleep=clock.sleep,
    )
    ctx._tiingo = TiingoClient(
        "test-token", engine, transport=lambda url, params, headers: (404, b"{}"),
        sleep=lambda s: None,
    )  # fmt: skip
    for p in probe.PROBES:
        if p.kind == "local" or p.id == "T1":  # T1 reads Tiingo's public file over the network
            continue
        lines = probe.run_one(ctx, p)
        assert not any("ERROR" in line for line in lines), (p.id, lines)
    assert corpus.execute("SELECT count(*) FROM http_cache").fetchone()[0] == 0
    assert engine.execute("SELECT count(*) FROM price_bar").fetchone()[0] == 1  # seeded only
