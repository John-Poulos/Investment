"""M07 Part 1: form4-2 holdings, CMP classes, buy / sale / net-flow signals (M07_OWNERSHIP.md)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from engine.news.fetch import Fetcher
from engine.ownership import classes, rows, short_interest, step, views
from engine.ownership.cards import Market, build_cards
from engine.sec.client import iso
from engine.sec.documents import filing_folder
from engine.sec.insiders import (
    PARSER_VERSION,
    history_plan,
    parse_form4,
    record_coverage,
    reparse_cached,
    store_form4,
)
from engine.sec.submissions import Filing, store_filings
from engine.sec.xbrl_facts import rebuild_series
from engine.signals import Source
from engine.store.http import SqliteCache
from tests.conftest import FakeTransport, fixture_bytes, ok

NVDA, TSLA, INTC, XSEM = "0001045810", "0001318605", "0000050863", "0000000042"
HUANG_ACC, MUSK_ACC, TAN_ACC = (
    "0001045810-25-000143",
    "0001104659-25-089693",
    "0001127602-25-010360",
)
HUANG = fixture_bytes("m07/huang_nvda_0001045810-25-000143.xml")
MUSK = fixture_bytes("m07/musk_tsla_0001104659-25-089693.xml")
TAN = fixture_bytes("m07/tan_intc_0001127602-25-010360.xml")
TODAY = date(2026, 10, 7)
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
PLAN_NOTE = "The sales were effected pursuant to a Rule 10b5-1 trading plan."


# --- helpers -------------------------------------------------------------------------------


def filing(acc: str, cik: str, filed: str, form: str = "4", primary="xslF345X05/form4.xml"):
    return Filing(
        accession=acc, cik=cik, form=form, filed=filed, accepted_at=None, report_date=None,
        items=(), primary_doc=primary, primary_doc_desc="FORM 4", is_xbrl=False,
        is_inline_xbrl=False, size=None,
    )  # fmt: skip


def put(engine, xml: bytes, acc: str, cik: str, filed: str, form: str = "4") -> Filing:
    f = filing(acc, cik, filed, form)
    engine.execute("BEGIN")
    store_filings(engine, [f], NOW)
    store_form4(engine, f, "form4.xml", parse_form4(xml), NOW)
    engine.execute("COMMIT")
    return f


def form4(
    issuer: str,
    owner_cik: str,
    owner_name: str,
    txns: list[tuple],
    *,
    doc_type: str = "4",
    aff: int | None = 0,
    footnotes: dict[str, str] | None = None,
    holdings: list[tuple] = (),
) -> bytes:
    """txns: (date, code, shares, price, A/D, after, D/I, footnote ids)."""
    body = ""
    for d, code, sh, price, ad, after, di, *fns in txns:
        ids = "".join(f'<footnoteId id="{i}"/>' for i in (fns[0] if fns else ()))
        pv = f"<value>{price}</value>" if price is not None else ""
        body += (
            "<nonDerivativeTransaction><securityTitle><value>Common Stock</value></securityTitle>"
            f"<transactionDate><value>{d}</value></transactionDate><transactionCoding>"
            f"<transactionCode>{code}</transactionCode>{ids}</transactionCoding>"
            f"<transactionAmounts><transactionShares><value>{sh}</value></transactionShares>"
            f"<transactionPricePerShare>{pv}</transactionPricePerShare>"
            f"<transactionAcquiredDisposedCode><value>{ad}</value>"
            "</transactionAcquiredDisposedCode></transactionAmounts><postTransactionAmounts>"
            f"<sharesOwnedFollowingTransaction><value>{after}</value>"
            "</sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature>"
            f"<directOrIndirectOwnership><value>{di}</value></directOrIndirectOwnership>"
            "</ownershipNature></nonDerivativeTransaction>"
        )
    for sh, di in holdings:
        body += (
            "<nonDerivativeHolding><securityTitle><value>Common Stock</value></securityTitle>"
            f"<postTransactionAmounts><sharesOwnedFollowingTransaction><value>{sh}</value>"
            "</sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature>"
            f"<directOrIndirectOwnership><value>{di}</value></directOrIndirectOwnership>"
            "<natureOfOwnership><value>By Trust</value></natureOfOwnership></ownershipNature>"
            "</nonDerivativeHolding>"
        )
    notes = "".join(f'<footnote id="{k}">{v}</footnote>' for k, v in (footnotes or {}).items())
    aff_xml = "" if aff is None else f"<aff10b5One>{aff}</aff10b5One>"
    return (
        f'<?xml version="1.0"?><ownershipDocument><documentType>{doc_type}</documentType>'
        f"<periodOfReport>{txns[0][0]}</periodOfReport>{aff_xml}<issuer><issuerCik>{issuer}"
        "</issuerCik><issuerName>Example</issuerName><issuerTradingSymbol>XSEM"
        "</issuerTradingSymbol></issuer><reportingOwner><reportingOwnerId><rptOwnerCik>"
        f"{owner_cik}</rptOwnerCik><rptOwnerName>{owner_name}</rptOwnerName></reportingOwnerId>"
        "<reportingOwnerRelationship><isOfficer>1</isOfficer><officerTitle>Officer"
        "</officerTitle></reportingOwnerRelationship></reportingOwner>"
        f"<nonDerivativeTable>{body}</nonDerivativeTable><footnotes>{notes}</footnotes>"
        "</ownershipDocument>"
    ).encode()


_seq = iter(range(1, 10_000))


def trade(engine, issuer, owner, name, d, code, sh, price, *, filed=None, aff=0, notes=None,
          after=100_000, doc_type="4", acc=None) -> str:  # fmt: skip
    acc = acc or f"{issuer}-{d[2:4]}-{next(_seq):06d}"
    fns = list(notes or {})
    ad = "A" if code in ("P", "A", "M") else "D"
    xml = form4(issuer, owner, name, [(d, code, sh, price, ad, after, "D", fns)],
                doc_type=doc_type, aff=aff, footnotes=notes)  # fmt: skip
    put(engine, xml, acc, issuer, filed or d, "4/A" if doc_type == "4/A" else "4")
    return acc


def cover(engine, cik, day, value, acc="cov-1"):
    engine.execute(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession, "
        "form, filed) VALUES (?, 'dei', 'EntityCommonStockSharesOutstanding', 'shares', NULL, ?, "
        "?, ?, '10-Q', ?)",
        (cik, day, value, acc, day),
    )


def signals(engine, cik, name, tf="MY", *, missing=False):
    """Stored M07 rows; `insider_buy` day rows only unless `missing` (D-M07-13 rows)."""
    rows = engine.execute(
        "SELECT * FROM signal WHERE cik = ? AND module_id = 'M07' AND signal = ? AND "
        "timeframe = ? ORDER BY as_of",
        (cik, name, tf),
    ).fetchall()
    if name != "insider_buy":
        return rows
    is_missing = [r["value"] is None and r["value_text"] is None for r in rows]
    return [r for r, m in zip(rows, is_missing, strict=True) if m == missing]


def collector() -> tuple[list[str], object]:
    out: list[str] = []
    return out, lambda *lines: out.extend(lines)


def run_pass(engine, cik, ticker="XSEM", *, force=True, now=NOW):
    return step.company_pass(engine, ticker, cik, now, today=TODAY, force=force)


# --- form4-2: holdings and the cache re-parse (D-SEC-27) ------------------------------------


def test_huang_holding_lines_are_parsed_and_stored(dbs):
    engine, _ = dbs
    form = parse_form4(HUANG)
    assert len(form.transactions) == 8 and len(form.holdings) == 8
    assert sum(h.shares for h in form.holdings) == 783_375_400
    assert {h.direct_indirect for h in form.holdings} == {"I"}
    put(engine, HUANG, HUANG_ACC, NVDA, "2025-06-24")
    n = engine.execute("SELECT count(*), sum(shares) FROM form4_holding").fetchone()
    assert tuple(n) == (8, 783_375_400)
    assert engine.execute("SELECT parser_version FROM form4_doc").fetchone()[0] == PARSER_VERSION


def test_reparse_from_cache_sends_no_request_and_counts_misses(make_client, dbs, clock):
    engine, corpus = dbs
    put(engine, HUANG, HUANG_ACC, NVDA, "2025-06-24")
    put(engine, MUSK, MUSK_ACC, TSLA, "2025-09-15")
    # as stored by form4-1: no holding lines, older version
    engine.execute("UPDATE form4_doc SET parser_version = 'form4-1'")
    engine.execute("DELETE FROM form4_holding")
    cache = SqliteCache(corpus)
    url = f"{filing_folder(NVDA, HUANG_ACC)}/form4.xml"
    cache.put(url, url, 200, HUANG, "text/xml", "ok", clock.now(), clock.now() + timedelta(days=9))
    rp = reparse_cached(engine, cache, NVDA, clock.now())
    assert (rp.stale, rp.reparsed, rp.misses, rp.holdings) == (1, 1, [], 8)
    miss = reparse_cached(engine, cache, TSLA, clock.now())
    assert miss.misses == [MUSK_ACC] and miss.reparsed == 0  # counted, not fetched
    transport = FakeTransport({f"{filing_folder(TSLA, MUSK_ACC)}/form4.xml": [ok(MUSK)]})
    got = reparse_cached(engine, cache, TSLA, clock.now(), client=make_client(transport))
    assert got.fetched == 1 and len(transport.calls) == 1
    assert engine.execute("SELECT count(*) FROM form4_doc WHERE parser_version = ?",
                          (PARSER_VERSION,)).fetchone()[0] == 2  # fmt: skip


def test_history_plan_is_the_exact_request_count(dbs, clock):
    engine, corpus = dbs
    cache = SqliteCache(corpus)
    stored = put(engine, HUANG, HUANG_ACC, NVDA, "2025-06-24")
    listed = [
        filing("0001045810-23-000001", NVDA, "2023-01-05"),  # not stored, not cached: 1
        filing("0001045810-23-000002", NVDA, "2023-01-06", primary="form4.htm"),  # name unknown: 2
        filing("0001045810-23-000003", NVDA, "2023-01-07"),  # in the cache: 0
        filing("0001045810-21-000009", NVDA, "2021-01-07"),  # before the window
    ]
    engine.execute("BEGIN")
    store_filings(engine, listed, NOW)
    engine.execute("COMMIT")
    url = f"{filing_folder(NVDA, '0001045810-23-000003')}/form4.xml"
    cache.put(url, url, 200, HUANG, "text/xml", "ok", clock.now(), clock.now() + timedelta(days=9))
    p = history_plan(engine, cache, NVDA, "2022-10-07", clock.now())
    assert (p.listed, p.pending, p.cached, p.to_fetch, p.requests) == (4, 3, 1, 2, 3)
    assert stored.accession not in {"pending"}


# --- rows: kinds, plan status, 4/A -------------------------------------------------------------


def test_purchase_from_issuer_and_non_discretionary_codes(dbs):
    engine, _ = dbs
    put(engine, TAN, TAN_ACC, INTC, "2025-03-25")
    issuer = rows.load(engine, INTC)
    [r] = issuer.rows
    assert r.code == "A" and r.kind == "issuer_buy"
    # P bought in an offering → issuer purchase; a gift, an F and an A grant stay "other"
    offering = {"F1": "Shares purchased in the Issuer's underwritten public offering."}
    trade(engine, XSEM, "0000000101", "Buyer B", "2026-03-02", "P", 1000, 10, notes=offering)
    trade(engine, XSEM, "0000000102", "Giver G", "2026-03-02", "G", 500, 0)
    trade(engine, XSEM, "0000000102", "Giver G", "2026-03-03", "F", 400, 12)
    trade(engine, XSEM, "0000000102", "Giver G", "2026-03-04", "A", 900, None)
    kinds = sorted((r.owner_name, r.code, r.kind) for r in rows.load(engine, XSEM).rows)
    assert kinds == [("Buyer B", "P", "issuer_buy"), ("Giver G", "A", "other"),
                     ("Giver G", "F", "other"), ("Giver G", "G", "other")]  # fmt: skip


def test_plan_status_plan_plan_na_and_non_plan(dbs):
    engine, _ = dbs
    a = trade(engine, XSEM, "0000000201", "Plan P", "2026-05-04", "S", 100, 10, aff=1,
              notes={"F1": PLAN_NOTE})  # fmt: skip
    b = trade(engine, XSEM, "0000000202", "Box B", "2026-05-04", "S", 100, 10, aff=1,
              notes={"F1": "Weighted average price."})  # fmt: skip
    c = trade(engine, XSEM, "0000000203", "None N", "2026-05-04", "S", 100, 10, aff=0)
    d = trade(engine, XSEM, "0000000204", "Old O", "2026-05-04", "S", 100, 10, aff=None)
    plan = {r.accession: r.plan for r in rows.load(engine, XSEM).rows}
    assert plan == {a: "plan", b: "plan_na", c: "non_plan", d: "non_plan"}


def test_amendment_replaces_original_and_keeps_its_day(dbs):
    engine, _ = dbs
    put(engine, fixture_bytes("m07/amend_original.xml"), "0000000042-25-000501", XSEM,
        "2025-11-05")  # fmt: skip
    put(engine, fixture_bytes("m07/amend_4a.xml"), "0000000042-25-000601", XSEM, "2025-11-20",
        "4/A")  # fmt: skip
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    cp = run_pass(engine, XSEM)
    assert cp.links == 1
    replaced = engine.execute("SELECT accession, line, code, replaced_by FROM insider_txn "
                              "WHERE replaced_by IS NOT NULL").fetchall()  # fmt: skip
    assert [tuple(r) for r in replaced] == [("0000000042-25-000501", 1, "S",
                                             "0000000042-25-000601")]  # fmt: skip
    [sale] = signals(engine, XSEM, "insider_sale")
    assert sale["as_of"] == "2025-11-05" and float(sale["value"]) == 5000 * 51.0  # corrected
    assert "G 1,000 sh" in sale["method"]  # the gift stays "not in total" on the original
    assert len(signals(engine, XSEM, "insider_sale", "ST")) == 1  # no row on the 4/A's day


def test_amended_buy_does_not_alert_twice(dbs):
    engine, _ = dbs
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    run_pass(engine, XSEM)  # first pass: baseline
    trade(engine, XSEM, "0000000301", "New Buyer", "2026-09-28", "P", 2000, 20,
          filed="2026-09-29")  # fmt: skip
    first = run_pass(engine, XSEM)
    assert len(first.alerts) == 1 and "unclassified" in first.alerts[0]
    trade(engine, XSEM, "0000000301", "New Buyer", "2026-09-28", "P", 2000, 21,
          filed="2026-10-02", doc_type="4/A")  # fmt: skip
    again = run_pass(engine, XSEM)
    assert again.alerts == []
    buys = signals(engine, XSEM, "insider_buy")
    assert [b["as_of"] for b in buys] == ["2026-09-29"] and float(buys[0]["value"]) == 42_000
    assert step.recent_alerts(engine, NOW + timedelta(hours=1)) == first.alerts


# --- CMP classes (S09; D-M07-1, -2) -----------------------------------------------------------


def history(engine):
    """The brief's illustrative Director X / CFO Y / CEO Z (M07 pack Round 1)."""
    for d in ("2023-02-10", "2023-08-10", "2024-02-12", "2025-02-11", "2025-11-12"):
        trade(engine, XSEM, "0000000401", "Director X", d, "S", 100, 10)
    for d in ("2023-05-10", "2024-09-10"):
        trade(engine, XSEM, "0000000402", "CFO Y", d, "S", 100, 10)
    for d in ("2023-03-10", "2024-06-10", "2025-12-10"):
        trade(engine, XSEM, "0000000403", "CEO Z", d, "P", 100, 10)
    for d, c in (("2024-03-01", "A"), ("2024-06-01", "M"), ("2025-03-01", "F"),
                 ("2025-04-01", "G")):  # fmt: skip
        trade(engine, XSEM, "0000000404", "Grant Only", d, c, 100, 0)


def test_routine_opportunistic_unclassified(dbs):
    engine, _ = dbs
    history(engine)
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    run_pass(engine, XSEM)
    got = {r["owner_cik"]: (r["class"], r["reason"]) for r in engine.execute(
        "SELECT * FROM insider_class WHERE issuer_cik = ? AND year = 2026", (XSEM,))}  # fmt: skip
    assert got["0000000401"][0] == "routine" and "month 02" in got["0000000401"][1]
    assert got["0000000402"] == ("unclassified", "no P/S in 2025")
    assert got["0000000403"][0] == "opportunistic"
    assert "0000000404" not in got  # A/M/F/G only: never classified (case 3)
    row = engine.execute("SELECT years_used, months_seen FROM insider_class WHERE owner_cik = "
                         "'0000000401' AND year = 2026").fetchone()  # fmt: skip
    assert json.loads(row[0]) == [2023, 2024, 2025]
    assert json.loads(row[1])["2025"] == [2, 11]


def test_short_history_is_unclassified_but_a_seen_common_month_is_routine():
    m = {2023: {8}, 2024: {8, 3}, 2025: {8}}
    assert classes.classify("o", m, 2026, "2023-06-01").cls == "routine"
    z = {2023: {9}, 2024: {6}, 2025: {12}}
    v = classes.classify("o", z, 2026, "2023-06-01")
    assert (v.cls, v.reason) == ("unclassified", "history starts 2023-06-01 (needs 2023-01-01)")
    assert classes.classify("o", z, 2026, None).cls == "unclassified"
    assert classes.classify("o", z, 2026, "2023-01-01").cls == "opportunistic"


def test_class_is_per_owner_and_issuer(dbs):
    engine, _ = dbs
    other = "0000000043"
    for d in ("2023-03-10", "2024-06-10", "2025-12-10"):
        trade(engine, XSEM, "0000000403", "CEO Z", d, "P", 100, 10)
    trade(engine, other, "0000000403", "CEO Z", "2025-12-10", "P", 100, 10)
    for cik in (XSEM, other):
        record_coverage(engine, cik, "2022-10-01", NOW)
        run_pass(engine, cik)
    got = dict(engine.execute("SELECT issuer_cik, class FROM insider_class WHERE owner_cik = "
                              "'0000000403' AND year = 2026").fetchall())  # fmt: skip
    assert got == {XSEM: "opportunistic", other: "unclassified"}


# --- cards and signals -----------------------------------------------------------------------


def test_huang_sale_card_stake_over_all_lines(dbs):
    engine, _ = dbs
    put(engine, HUANG, HUANG_ACC, NVDA, "2025-06-24")
    cover(engine, NVDA, "2025-05-23", 24_400_000_000)
    record_coverage(engine, NVDA, "2022-10-01", NOW)
    cp = run_pass(engine, NVDA, "NVDA")
    [card] = cp.cards
    assert card.sale_usd == pytest.approx(14_403_585, abs=1)
    assert card.sale_shares == 100_000 and {card.sale_status(r) for r in card.sales} == {"plan"}
    [f] = card.others
    assert f.code == "F" and f.usd == pytest.approx(5_788_292, abs=1)  # not in total
    assert card.stake_lines == 9 and card.stake_after == 859_048_625
    assert card.pct_stake_before_sale() == pytest.approx(100_000 / 859_148_625 * 100)  # 0.012%
    assert round(card.pct_stake_before_sale(), 3) == 0.012
    assert round(100_000 / (75_673_225 + 100_000) * 100, 2) == 0.13  # direct line alone: 11×
    assert card.cover.pct(card.scaled(100_000, Market(engine, NVDA))) == pytest.approx(
        100_000 / 24_400_000_000 * 100
    )
    [sale] = signals(engine, NVDA, "insider_sale")
    assert sale["value_text"] == "plan" and float(sale["value"]) == pytest.approx(14_403_585, abs=1)
    assert sale["method"].endswith("info (weight 0)")  # plan sale: MY info
    assert "F 40,163 sh $5.79M" in sale["method"] and sale["source_ref"] == HUANG_ACC
    assert "dei:EntityCommonStockSharesOutstanding, 2025-05-23" in sale["method"]
    assert "row footnote: under 10b5-1 plan" in sale["method"]


def test_musk_buy_unclassified_alert_and_cover(dbs):
    engine, _ = dbs
    cover(engine, TSLA, "2025-07-17", 3_225_448_889)
    record_coverage(engine, TSLA, "2023-10-01", NOW)
    run_pass(engine, TSLA, "TSLA")  # baseline
    put(engine, MUSK, MUSK_ACC, TSLA, "2025-09-15")
    cp = run_pass(engine, TSLA, "TSLA")
    [card] = cp.cards
    assert len(card.buys) == 25 and card.buy_shares == 2_568_732
    assert card.buy_usd == pytest.approx(999_960_000, rel=1e-6)
    assert card.stake_after == 509_362_808
    assert round(card.pct_stake_after_buy(), 2) == 0.50
    assert round(card.cover.pct(card.buy_shares), 3) == 0.080
    [buy] = signals(engine, TSLA, "insider_buy")
    assert buy["value_text"] == "unclassified" and buy["as_of"] == "2025-09-15"
    assert buy["method"].endswith("info (weight 0)")  # unclassified: alert, no score (D-M07-2)
    assert "history starts 2023-10-01" in buy["method"]
    assert "alert (M01 rule 6) when filed within 30 days of the run, ≥ $10,000" in buy["method"]
    # filed 2025-09-15, more than 30 days before the run: baseline, not alerted (D-M07-17)
    assert (
        cp.alerts == []
        and len(cp.older) == 1
        and cp.older[0].startswith("TSLA 2025-09-15: insider buy $999.96M by Musk Elon")
    )
    assert buy["cik"] == TSLA and buy["ticker"] == "TSLA"  # keyed by CIK (D-M04-74)


def test_tan_purchase_from_issuer_is_shown_not_scored(dbs):
    engine, _ = dbs
    put(engine, TAN, TAN_ACC, INTC, "2025-03-25")
    record_coverage(engine, INTC, "2022-10-01", NOW)
    run_pass(engine, INTC, "INTC")
    [buy] = signals(engine, INTC, "insider_buy")
    assert buy["value_text"] == "purchase_from_issuer" and buy["value"] is None
    assert "purchase from issuer 1,043,406 shares $25.00M" in buy["method"]
    assert buy["method"].endswith("info (weight 0)")
    assert engine.execute("SELECT count(*) FROM insider_class").fetchone()[0] == 0


def test_opportunistic_buy_votes_and_cluster(dbs):
    engine, _ = dbs
    for owner in ("0000000501", "0000000502", "0000000503"):
        for d in ("2023-03-10", "2024-06-10", "2025-12-10"):
            trade(engine, XSEM, owner, f"Buyer {owner[-1]}", d, "P", 100, 10)
        trade(engine, XSEM, owner, f"Buyer {owner[-1]}", "2026-08-03", "P", 1000, 20)
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    run_pass(engine, XSEM)
    my = signals(engine, XSEM, "insider_buy")[-1]
    assert my["as_of"] == "2026-08-03" and my["value_text"] == "opportunistic"
    assert float(my["value"]) == 60_000  # same-day forms aggregate: 3 × 1,000 × $20
    assert "info (weight 0)" not in my["method"]  # MY vote
    assert "vote: opportunistic +1 in MY" in my["method"]
    assert "cluster: 3 distinct opportunistic buyer(s)" in my["method"]
    assert "(≥ 3: cluster)" in my["method"]
    pt = signals(engine, XSEM, "insider_buy", "PT")[-1]
    assert pt["method"].endswith("info (weight 0)")


def test_same_day_sales_aggregate_with_strongest_class_and_warnings(dbs):
    engine, _ = dbs
    for d in ("2023-03-10", "2024-06-10", "2025-12-10"):
        trade(engine, XSEM, "0000000601", "Seller O", d, "S", 10, 10)
    trade(engine, XSEM, "0000000601", "Seller O", "2026-06-01", "S", 500, 10, after=99_500)
    trade(engine, XSEM, "0000000602", "Planner", "2026-06-01", "S", 300, 10, aff=1,
          notes={"F1": PLAN_NOTE})  # fmt: skip
    trade(engine, XSEM, "0000000603", "New Big", "2026-07-01", "S", 50_000, 10, after=50_000)
    trade(engine, XSEM, "0000000604", "New Small", "2026-07-02", "S", 1_000, 10, after=99_000)
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    run_pass(engine, XSEM)
    by_day = {s["as_of"]: s for s in signals(engine, XSEM, "insider_sale")}
    june = by_day["2026-06-01"]
    assert june["value_text"] == "non_plan_opportunistic" and float(june["value"]) == 8_000
    assert "warning: non-plan sale by an opportunistic insider" in june["method"]
    assert "info (weight 0)" not in june["method"]
    big = by_day["2026-07-01"]  # unclassified, 50% of stake → warning
    assert big["value_text"] == "non_plan_unclassified" and "≥ 10% (D-M07-3)" in big["method"]
    small = by_day["2026-07-02"]  # unclassified, 1% of stake → info
    assert "warning" not in small["method"] and small["method"].endswith("info (weight 0)")


def test_net_flow_plan_sales_beside_and_missing_history(dbs):
    engine, _ = dbs
    trade(engine, XSEM, "0000000701", "Buyer", "2026-09-20", "P", 1000, 50)  # $50,000
    trade(engine, XSEM, "0000000702", "Seller", "2026-08-01", "S", 400, 50)  # non-plan $20,000
    trade(engine, XSEM, "0000000703", "Planner", "2026-09-25", "S", 9_000, 50, aff=1,
          notes={"F1": PLAN_NOTE})  # fmt: skip
    trade(engine, XSEM, "0000000704", "Old", "2025-01-15", "S", 100, 50)  # outside MY
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    cp = run_pass(engine, XSEM)
    my, pt, st = (cp.net[t] for t in ("MY", "PT", "ST"))
    assert (my.text, my.value) == ("net_buy", 30_000)
    assert my.plan_usd == 450_000 and my.gross_usd == 470_000 and my.insiders == 3
    assert (pt.text, pt.value) == ("net_buy", 30_000)
    assert (st.text, st.value) == ("net_buy", 50_000)  # the August sale is outside 30 days
    [row] = signals(engine, XSEM, "insider_net_flow")
    assert row["as_of"] == "2026-10-07" and row["method"].endswith("info (weight 0)")
    assert "beside, not netted: plan S 9,000 sh $450,000" in row["method"]
    # plan only, none, and a window before the stored history
    other = "0000000044"
    trade(engine, other, "0000000705", "Planner", "2026-09-25", "S", 10, 5, aff=1,
          notes={"F1": PLAN_NOTE})  # fmt: skip
    record_coverage(engine, other, "2026-08-01", NOW)
    cp2 = run_pass(engine, other)
    assert cp2.net["ST"].text == "plan_only" and cp2.net["ST"].value is None
    assert cp2.net["MY"].missing == "history starts 2026-08-01"
    [miss] = signals(engine, other, "insider_net_flow")
    assert miss["value"] is None and miss["value_text"] is None
    assert miss["method"].startswith("missing: history starts 2026-08-01")
    latest = Source("0000000044-26-000001", "2026-09-25", "A", "latest Form 4")
    issuer = rows.load(engine, other)
    none = step.net_flow(issuer, "ST", date(2026, 9, 1), "2026-08-01", None, latest)
    assert (none.text, none.value, none.sources) == ("none", None, [latest])
    nothing = step.net_flow(issuer, "ST", date(2026, 9, 1), "2026-08-01", None, None)
    assert nothing.missing == "no Form 4 stored for this company"


def pass_on(engine, cik, day: date, ticker="XSEM", force=True):
    now = datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)
    return step.company_pass(engine, ticker, cik, now, today=day, force=force)


def test_no_qualifying_buy_missing_row_written_on_change(dbs):
    """D-M07-13: explicit missing row per timeframe, only when the state changes."""
    engine, _ = dbs
    trade(engine, XSEM, "0000000711", "Buyer", "2026-09-20", "P", 1000, 50)
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    cp = pass_on(engine, XSEM, TODAY)  # the buy is in every window
    assert cp.no_buy == {"MY": None, "PT": None, "ST": None}
    assert signals(engine, XSEM, "insider_buy", "ST", missing=True) == []
    # the buy leaves the 30-day window → one ST missing row on that day
    cp = pass_on(engine, XSEM, date(2026, 10, 25))
    assert cp.no_buy == {"MY": None, "PT": None, "ST": "written"}
    [st] = signals(engine, XSEM, "insider_buy", "ST", missing=True)
    assert st["as_of"] == "2026-10-25" and st["value"] is None and st["value_text"] is None
    assert st["method"].startswith("missing: no qualifying buy in 30 days; window 30 days")
    assert "last open-market buy filed 2026-09-20" in st["method"]
    assert st["method"].endswith("info (weight 0)")
    # next days: unchanged, never a new identical row; the day row is kept
    for d in (date(2026, 10, 26), date(2026, 11, 2)):
        assert pass_on(engine, XSEM, d, force=False).no_buy["ST"] == "unchanged"
    assert len(signals(engine, XSEM, "insider_buy", "ST", missing=True)) == 1
    assert [r["as_of"] for r in signals(engine, XSEM, "insider_buy", "ST")] == ["2026-09-20"]
    # a new buy, then it ages out again → a second missing row
    trade(engine, XSEM, "0000000712", "Buyer 2", "2026-11-03", "P", 10, 50, filed="2026-11-04")
    assert pass_on(engine, XSEM, date(2026, 11, 5)).no_buy["ST"] is None
    assert pass_on(engine, XSEM, date(2026, 12, 10)).no_buy["ST"] == "written"
    got = [r["as_of"] for r in signals(engine, XSEM, "insider_buy", "ST", missing=True)]
    assert got == ["2026-10-25", "2026-12-10"]
    assert signals(engine, XSEM, "insider_buy", "MY", missing=True) == []


def test_no_buy_first_computation_and_contradicted_row(dbs):
    engine, _ = dbs
    other = "0000000045"
    trade(engine, other, "0000000721", "Seller", "2026-06-01", "S", 100, 10)
    record_coverage(engine, other, "2022-10-01", NOW)
    cp = pass_on(engine, other, TODAY)  # first computation: one row per timeframe
    assert cp.no_buy == {"MY": "written", "PT": "written", "ST": "written"}
    [my] = signals(engine, other, "insider_buy", "MY", missing=True)
    assert my["method"].startswith("missing: no qualifying buy in 12 months")
    assert "info (weight 0)" not in my["method"]  # MY: the vote's missing state (D-M07-2)
    assert "last open-market buy filed none stored" in my["method"]
    assert pass_on(engine, other, date(2026, 10, 8)).no_buy["MY"] == "unchanged"
    # a late-stored buy filed before the missing row contradicts it: the row goes
    trade(engine, other, "0000000722", "Late Buyer", "2026-09-30", "P", 10, 10,
          filed="2026-10-01")  # fmt: skip
    cp = pass_on(engine, other, date(2026, 10, 9))
    assert cp.no_buy == {"MY": None, "PT": None, "ST": None}
    for tf in ("MY", "PT", "ST"):
        assert signals(engine, other, "insider_buy", tf, missing=True) == []
    assert [r["as_of"] for r in signals(engine, other, "insider_buy")] == ["2026-10-01"]
    # the Overview reads the latest buy day, never the missing row
    assert views.overview_row(engine, other)["buy"]["as_of"] == "2026-10-01"


def test_net_flow_written_only_on_change(dbs):
    """D-M07-14: one row per timeframe per change; as_of = the run date of the change."""
    engine, _ = dbs
    trade(engine, XSEM, "0000000731", "Buyer", "2026-09-20", "P", 1000, 50)
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    cp = pass_on(engine, XSEM, TODAY)
    assert all(nf.written for nf in cp.net.values())
    cp = pass_on(engine, XSEM, date(2026, 10, 8))
    assert not any(nf.written for nf in cp.net.values())
    assert [r["as_of"] for r in signals(engine, XSEM, "insider_net_flow")] == ["2026-10-07"]
    # the buy leaves the ST window: only ST changes (net_buy → none)
    cp = pass_on(engine, XSEM, date(2026, 10, 21))
    assert [tf for tf, nf in cp.net.items() if nf.written] == ["ST"]
    st = signals(engine, XSEM, "insider_net_flow", "ST")
    assert [(r["as_of"], r["value_text"]) for r in st] == [("2026-10-07", "net_buy"),
                                                           ("2026-10-21", "none")]  # fmt: skip
    # a sale changes MY on its day; a same-day revert removes that day's row again
    acc = trade(engine, XSEM, "0000000732", "Seller", "2026-10-21", "S", 100, 50,
                filed="2026-10-22")  # fmt: skip
    pass_on(engine, XSEM, date(2026, 10, 22))
    my = signals(engine, XSEM, "insider_net_flow")
    assert [(r["as_of"], float(r["value"])) for r in my] == [("2026-10-07", 50_000),
                                                             ("2026-10-22", 45_000)]  # fmt: skip
    engine.execute("DELETE FROM insider_txn WHERE accession = ?", (acc,))
    engine.execute("DELETE FROM form4_doc WHERE accession = ?", (acc,))
    pass_on(engine, XSEM, date(2026, 10, 22))
    assert [r["as_of"] for r in signals(engine, XSEM, "insider_net_flow")] == ["2026-10-07"]
    # a missing reading is written once, then unchanged
    other = "0000000046"
    trade(engine, other, "0000000733", "Seller", "2026-09-25", "S", 10, 5)
    record_coverage(engine, other, "2026-08-01", NOW)
    pass_on(engine, other, TODAY)
    assert not pass_on(engine, other, date(2026, 10, 9)).net["MY"].written
    [miss] = signals(engine, other, "insider_net_flow")
    assert miss["method"].startswith("missing: history starts 2026-08-01")


def test_same_reading_rounds_to_the_dollar():
    nf = step.NetFlow("MY", "a", "b", "net_buy", 30_000.4, "m")
    row = {"value": 30_000.2, "value_text": "net_buy", "method": "m"}
    assert step._same_reading(row, nf)
    assert not step._same_reading({**row, "value": 30_001.0}, nf)
    assert not step._same_reading({**row, "value_text": "net_sell"}, nf)
    gone = step.NetFlow("MY", "a", "b", None, None, "m", missing="history starts 2026-08-01")
    prev = {"value": None, "value_text": None, "method": "missing: history starts 2026-08-01; w"}
    assert step._same_reading(prev, gone)
    assert not step._same_reading({**prev, "method": "missing: history starts 2026-07-01; w"},
                                  gone)  # fmt: skip


def test_amendment_fallback_on_owner_date_and_code(dbs):
    """D-M07-15: a 4/A that corrects the shares replaces the only same-code candidate."""
    engine, _ = dbs
    o = "0000000741"
    trade(engine, XSEM, o, "Corrector", "2026-05-04", "S", 200, 10, filed="2026-05-05")
    a = trade(engine, XSEM, o, "Corrector", "2026-05-04", "S", 250, 10, filed="2026-05-20",
              doc_type="4/A")  # fmt: skip
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    cp = run_pass(engine, XSEM)
    assert (cp.links, cp.links_by_code, cp.link_log) == (1, 1, [])
    [sale] = signals(engine, XSEM, "insider_sale")
    assert sale["as_of"] == "2026-05-05" and float(sale["value"]) == 2_500  # the 4/A's shares
    assert "on owner, date and code — the only candidate, D-M07-15" in sale["method"]
    [r] = [x for x in rows.load(engine, XSEM).rows if x.accession == a]
    assert r.match == "code" and r.day == "2026-05-05"


def test_amendment_two_phase_match_and_logged_misses(dbs):
    engine, _ = dbs
    o = "0000000751"
    # original: S 100 and S 200; 4/A: S 250 (corrected) listed before S 100 (unchanged)
    put(engine, form4(XSEM, o, "Two Rows", [("2026-04-01", "S", 100, 10, "D", 900, "D"),
                                            ("2026-04-01", "S", 200, 10, "D", 700, "D")]),
        "0000000042-26-000801", XSEM, "2026-04-02")  # fmt: skip
    amend = form4(XSEM, o, "Two Rows", [("2026-04-01", "S", 250, 10, "D", 650, "D"),
                                        ("2026-04-01", "S", 100, 10, "D", 900, "D")],
                  doc_type="4/A")  # fmt: skip
    put(engine, amend, "0000000042-26-000802", XSEM, "2026-04-10", "4/A")
    link = rows.match_amendments(
        [
            (r.accession, r.line, r.owner_cik, r.txn_date, r.shares, r.code, r.doc_type)
            for r in rows.load(engine, XSEM).rows
        ]  # fmt: skip
    )
    assert sorted(x[4] for x in link.links) == ["code", "shares"] and link.unmatched == []
    # ambiguous: two same-code candidates; none: a P with no P on the original
    q = "0000000752"
    put(engine, form4(XSEM, q, "Ambiguous", [("2026-04-15", "S", 100, 10, "D", 900, "D"),
                                             ("2026-04-15", "S", 200, 10, "D", 700, "D")]),
        "0000000042-26-000803", XSEM, "2026-04-16")  # fmt: skip
    amend = form4(XSEM, q, "Ambiguous", [("2026-04-15", "S", 260, 10, "D", 640, "D"),
                                         ("2026-04-15", "P", 5, 10, "A", 645, "D")],
                  doc_type="4/A")  # fmt: skip
    put(engine, amend, "0000000042-26-000804", XSEM, "2026-04-20", "4/A")
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    cp = run_pass(engine, XSEM)
    assert (cp.links, cp.links_by_code) == (2, 1)
    assert len(cp.link_log) == 2
    assert (
        "2 of the same owner, date and code: ambiguous, kept apart (both count)" in (cp.link_log[0])
    )
    assert "none of the same owner, date and code: stands alone" in cp.link_log[1]
    sales = {s["as_of"]: float(s["value"]) for s in signals(engine, XSEM, "insider_sale")}
    assert sales["2026-04-02"] == 3_500  # 250 + 100 on the original's day
    assert sales["2026-04-16"] == 3_000 and sales["2026-04-20"] == 2_600  # both count
    engine.execute("DELETE FROM refresh_state WHERE name LIKE 'm07_pass:%'")
    lines = step.run_local_part(engine, {"XSEM": XSEM}, NOW)
    assert any("XSEM: Form 4/A 0000000042-26-000804 line 1" in x for x in lines)


def test_offering_purchases_stay_purchase_from_issuer(dbs):
    """D-M07-16: P rows in an underwritten or registered offering are not open-market buys."""
    engine, _ = dbs
    notes = (
        "Shares purchased in the Issuer's underwritten public offering.",
        "Purchased in a registered offering at $10.00 per share.",
        "Purchased in the Company's registered direct offering.",
        "Shares bought in the underwritten offering of the Issuer.",
        "Purchased in the offering at $10.00 per share.",
    )
    for i, n in enumerate(notes):
        trade(engine, XSEM, f"00000007{60 + i}", f"Buyer {i}", "2026-09-28", "P", 1000, 10,
              notes={"F1": n}, filed="2026-09-29")  # fmt: skip
    trade(engine, XSEM, "0000000770", "Open Buyer", "2025-01-10", "P", 10, 10,
          notes={"F1": "Weighted average price; open-market purchases."})  # fmt: skip
    kinds = {r.owner_name: r.kind for r in rows.load(engine, XSEM).rows}
    assert kinds.pop("Open Buyer") == "buy"
    assert set(kinds.values()) == {"issuer_buy"}
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    run_pass(engine, XSEM)  # baseline
    cp = run_pass(engine, XSEM)
    assert cp.alerts == [] and cp.net["MY"].text == "none"  # not in net flow
    buy = next(b for b in signals(engine, XSEM, "insider_buy") if b["as_of"] == "2026-09-29")
    assert buy["value_text"] == "purchase_from_issuer" and buy["value"] is None
    assert "no vote" in buy["method"] and buy["method"].endswith("info (weight 0)")
    assert cp.no_buy["MY"] == "unchanged"  # no qualifying buy: the D-M07-13 row stands


def test_float_unknown_adv_split_guard_and_no_bars(dbs):
    engine, _ = dbs
    trade(engine, XSEM, "0000000801", "Seller", "2026-06-30", "S", 3_000, 10)
    m = Market(engine, XSEM)
    assert m.float_("2026-06-30").text.startswith("float unknown (no dei:EntityPublicFloat")
    assert m.adv("2026-06-30").text == "missing: no price bars stored"
    engine.execute("INSERT INTO price_fetch (symbol, cik) VALUES ('XSEM', ?)", (XSEM,))
    days = [date(2026, 6, 1) + timedelta(days=i) for i in range(30)]
    for d in days:
        split = 2 if d == date(2026, 6, 20) else 1
        vol = 1_000 if d < date(2026, 6, 20) else 2_000  # same economic volume after a 2:1 split
        engine.execute("INSERT INTO price_bar (symbol, date, close, volume, split_factor, source, "
                       "fetched_at) VALUES ('XSEM', ?, 10, ?, ?, 't', 'x')",
                       (d.isoformat(), vol, split))  # fmt: skip
    adv = Market(engine, XSEM).adv("2026-06-30")
    assert adv.value == pytest.approx(2_000) and "split inside the window 2026-06-20 ×2" in adv.text
    assert Market(engine, XSEM).adv("2026-06-10").text.startswith("missing: 10 bars")
    # implied float: EntityPublicFloat ÷ close (D-M04-2)
    engine.execute(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession, "
        "form, filed) VALUES (?, 'dei', 'EntityPublicFloat', 'USD', NULL, '2026-06-01', 5000000, "
        "'k1', '10-K', '2026-07-01')",
        (XSEM,),
    )
    rebuild_series(engine, XSEM)
    flt = Market(engine, XSEM).float_("2026-06-30")
    assert flt.value == pytest.approx(5_000_000 / 10 * 2)  # split after the float date


def test_stake_traded_lines_only_before_reparse(dbs):
    engine, _ = dbs
    put(engine, HUANG, HUANG_ACC, NVDA, "2025-06-24")
    engine.execute("UPDATE form4_doc SET parser_version = 'form4-1'")
    engine.execute("DELETE FROM form4_holding")
    [card] = build_cards(rows.load(engine, NVDA), {}, None)
    assert card.stake_after == 75_673_225 and "traded lines only" in card.stake_note


# --- refresh hook, gating, alerts box ----------------------------------------------------------


def test_refresh_hook_recomputes_only_after_new_form4s(dbs):
    engine, _ = dbs
    trade(engine, XSEM, "0000000901", "Buyer", "2026-09-20", "P", 1000, 50)
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    comps = {"XSEM": XSEM}
    first = step.run_local_part(engine, comps, NOW)
    assert "recomputed after new Form 4s: XSEM" in first[0]
    again = step.run_local_part(engine, comps, NOW)
    assert "recomputed after new Form 4s: none" in again[0]
    trade(engine, XSEM, "0000000902", "Buyer 2", "2026-10-05", "P", 1000, 50, filed="2026-10-06")
    later = step.run_local_part(engine, comps, NOW + timedelta(minutes=5))
    assert "recomputed after new Form 4s: XSEM" in later[0] and "new alerts 1" in later[0]
    assert any("Buyer 2" in x for x in later)
    assert step.recent_alerts(engine, NOW + timedelta(minutes=10)) == [later[1].split(
        "alert: ", 1)[1]]  # fmt: skip


def test_waiting_summary_lists_insider_buy_alerts(dbs, monkeypatch):
    engine, _ = dbs
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_refresh

    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES "
        "('m07_alert:0000000042:2026-10-06', 'M07', ?, 'XSEM 2026-10-06: insider buy $500')",
        (iso(datetime.now(UTC)),),
    )
    text = run_refresh.waiting_summary(engine)
    assert "M07 insider buys (alerts):\n  XSEM 2026-10-06: insider buy $500" in text


# --- D-M07-17: alerts are for new filings, with a $ floor -------------------------------------


def alert_state(engine, day):
    row = engine.execute("SELECT detail FROM refresh_state WHERE name = ?",
                         (f"m07_alert:{XSEM}:{day}",)).fetchone()  # fmt: skip
    return row[0] if row else None


def test_history_fetch_buys_are_baseline_not_alerts(dbs):
    """The live-check finding: a 4th-year history fetch parses old Form 4s after the first
    pass; their buys are recorded as baseline (older filing), never alerted."""
    engine, _ = dbs
    record_coverage(engine, XSEM, "2023-10-01", NOW)
    trade(engine, XSEM, "0000000951", "Gelsinger", "2024-02-02", "P", 1000, 40)
    first = run_pass(engine, XSEM)
    assert first.baseline and first.alerts == []
    # the history fetch: old forms, filed 2022-11-08 and 2023-05-26 (outside the ST window)
    trade(engine, XSEM, "0000000952", "Mollenkopf", "2022-11-04", "P", 20_000, 208.5,
          filed="2022-11-08")  # fmt: skip
    trade(engine, XSEM, "0000000953", "Bezos", "2023-05-24", "P", 1, 115, filed="2023-05-26")
    # a fresh filing two days ago: the only alert
    trade(engine, XSEM, "0000000954", "New Buyer", "2026-10-02", "P", 1000, 25,
          filed="2026-10-05")  # fmt: skip
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    cp = run_pass(engine, XSEM)
    assert cp.alerts == ["XSEM 2026-10-05: insider buy $25,000 by New Buyer (unclassified)"]
    assert [a.split(":")[0] for a in cp.older] == ["XSEM 2022-11-08", "XSEM 2023-05-26"]
    assert alert_state(engine, "2022-11-08").startswith("baseline (older filing): XSEM")
    assert step.recent_alerts(engine, NOW + timedelta(hours=1)) == cp.alerts
    # the stored buy rows are kept (recorded, not alerted)
    days = [b["as_of"] for b in signals(engine, XSEM, "insider_buy")]
    assert {"2022-11-08", "2023-05-26", "2026-10-05"} <= set(days)
    # a re-run alerts nothing again
    assert run_pass(engine, XSEM).alerts == []


def test_filing_date_not_trade_date_decides(dbs):
    """A trade from 2026-08 filed late (2026-10-01) is new information: it alerts."""
    engine, _ = dbs
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    run_pass(engine, XSEM)  # baseline
    trade(engine, XSEM, "0000000961", "Late Filer", "2026-08-01", "P", 1000, 30,
          filed="2026-10-01")  # fmt: skip
    trade(engine, XSEM, "0000000962", "Edge", "2026-09-07", "P", 1000, 30, filed="2026-09-07")
    cp = run_pass(engine, XSEM)
    assert [a.split(":")[0] for a in cp.alerts] == ["XSEM 2026-10-01"]
    assert [a.split(":")[0] for a in cp.older] == ["XSEM 2026-09-07"]  # day 30: outside


def test_buys_under_the_floor_are_recorded_not_alerted(dbs, tmp_path):
    engine, _ = dbs
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    run_pass(engine, XSEM)  # baseline
    trade(engine, XSEM, "0000000971", "Small Buyer", "2026-10-01", "P", 1, 115,
          filed="2026-10-02")  # fmt: skip
    cp = run_pass(engine, XSEM)
    assert cp.alerts == [] and cp.below_floor == [
        "XSEM 2026-10-02: insider buy $115 by Small Buyer (unclassified)"
    ]
    assert alert_state(engine, "2026-10-02").startswith("baseline (below floor): ")
    [buy] = [b for b in signals(engine, XSEM, "insider_buy") if b["as_of"] == "2026-10-02"]
    assert float(buy["value"]) == 115  # recorded
    assert "below the $10,000† alert floor: recorded, not alerted (D-M07-17)" in buy["method"]
    assert step.recent_alerts(engine, NOW + timedelta(hours=1)) == []
    # a second form on the same filing day lifts the day over the floor: it alerts once
    trade(engine, XSEM, "0000000972", "Big Buyer", "2026-10-01", "P", 1000, 20,
          filed="2026-10-02")  # fmt: skip
    cp = run_pass(engine, XSEM)
    assert len(cp.alerts) == 1 and "$20,115" in cp.alerts[0]
    assert run_pass(engine, XSEM).alerts == []
    # the floor comes from config; a lower floor alerts the small buy
    trade(engine, XSEM, "0000000973", "Tiny", "2026-10-05", "P", 1, 115, filed="2026-10-06")
    assert len(step.company_pass(engine, "XSEM", XSEM, NOW, today=TODAY, force=True,
                                 floor=100).alerts) == 1  # fmt: skip


def test_stored_alerts_on_old_filings_convert_to_baseline(dbs):
    """The 13 alerts the history run stored become baseline on the next pass, also when no
    Form 4 changed (the refresh's local step); alerts that were recent when stored stay."""
    engine, _ = dbs
    trade(engine, XSEM, "0000000981", "Buyer", "2026-09-20", "P", 1000, 50)
    record_coverage(engine, XSEM, "2022-10-01", NOW)
    run_pass(engine, XSEM)  # baseline
    recorded = iso(NOW - timedelta(hours=2))
    for day, detail in (("2022-11-02", "XSEM 2022-11-02: insider buy $248,647 by G"),
                        ("2026-10-06", "XSEM 2026-10-06: insider buy $50,000 by H")):  # fmt: skip
        engine.execute(
            "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES "
            "(?, 'M07', ?, ?)",
            (f"m07_alert:{XSEM}:{day}", recorded, detail),
        )
    assert len(step.recent_alerts(engine, NOW)) == 2
    lines = step.run_local_part(engine, {"XSEM": XSEM}, NOW)  # nothing recomputed
    assert "recomputed after new Form 4s: none" in lines[0]
    assert "stored alerts converted to baseline 1" in lines[0]
    assert "  converted to baseline (older filing, D-M07-17): XSEM 2022-11-02: insider buy " \
        "$248,647 by G" in lines  # fmt: skip
    assert alert_state(engine, "2022-11-02") == (
        "baseline (older filing): XSEM 2022-11-02: insider buy $248,647 by G"
    )
    assert step.recent_alerts(engine, NOW) == ["XSEM 2026-10-06: insider buy $50,000 by H"]
    # a recent alert that later ages out of the window stays an alert (it was new when stored)
    later = step.local_pass(engine, {"XSEM": XSEM}, NOW + timedelta(days=60))
    assert later.converted == []
    assert alert_state(engine, "2026-10-06") == "XSEM 2026-10-06: insider buy $50,000 by H"


def test_alert_floor_config_matches_default_and_falls_back(tmp_path):
    assert step.load_floor() == step.BUY_FLOOR_USD == 10_000
    bad = tmp_path / "ownership.toml"
    bad.write_text("[alerts]\nbuy_floor_usd = 'ten'\n", encoding="utf-8")
    assert step.load_floor(bad) == step.BUY_FLOOR_USD
    bad.write_text("not toml [", encoding="utf-8")
    assert step.load_floor(bad) == step.BUY_FLOOR_USD
    assert step.load_floor(tmp_path / "missing.toml") == step.BUY_FLOOR_USD
    bad.write_text("[alerts]\nbuy_floor_usd = 25000\n", encoding="utf-8")
    assert step.load_floor(bad) == 25_000


# --- owner script (injected connections; never the real data folder) -------------------------


def test_insiders_run_no_sec_dry_run_and_history(make_client, dbs, clock, tmp_path):
    engine, corpus = dbs
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_ownership

    put(engine, HUANG, HUANG_ACC, NVDA, "2025-06-24")
    engine.execute("UPDATE form4_doc SET parser_version = 'form4-1'")
    engine.execute("DELETE FROM form4_holding")
    listed = filing("0001045810-23-000001", NVDA, "2023-01-05")
    engine.execute("BEGIN")
    store_filings(engine, [listed], NOW)
    engine.execute("COMMIT")
    lines, log = collector()
    comps = {"NVDA": NVDA}
    # --no-sec: the cache miss is counted, nothing is fetched
    res = run_ownership.insiders_run(engine, corpus, comps, clock.now(), log)
    assert res["misses"] == 1 and res["reparsed"] == 0
    assert any("missing: no short-interest source" in x for x in lines)
    # dry run: exact count, nothing written
    before = engine.execute("SELECT count(*) FROM form4_doc").fetchone()[0]
    dry, log = collector()
    res = run_ownership.insiders_run(engine, corpus, comps, clock.now(), log,
                                     history=True, dry_run=True)  # fmt: skip
    assert res["planned"] == 2 and any("would send 2 SEC requests" in x for x in dry)
    assert engine.execute("SELECT count(*) FROM form4_doc").fetchone()[0] == before
    # history with a client: the re-parse fetches the miss, sync fetches the 2023 filing
    xml23 = form4(NVDA, "0000000999", "Old Insider", [("2023-01-03", "S", 10, 100, "D", 90, "D")])
    transport = FakeTransport({
        f"{filing_folder(NVDA, HUANG_ACC)}/form4.xml": [ok(HUANG)],
        f"{filing_folder(NVDA, listed.accession)}/form4.xml": [ok(xml23)],
    })  # fmt: skip
    out, log = collector()
    res = run_ownership.insiders_run(engine, corpus, comps, clock.now(), log,
                                     client=make_client(transport), history=True,
                                     probe=lambda: ["probe line"])  # fmt: skip
    assert res["fetched"] == 1 and res["history"]["NVDA"].ingested == 1
    assert len(transport.calls) == 2
    assert engine.execute("SELECT detail FROM refresh_state WHERE name = ?",
                          (f"form4_since:{NVDA}",)).fetchone()[0] == "2022-10-08"  # fmt: skip
    assert any("Huang (NVDA 0001045810-25-000143)" in x for x in out)
    assert any("sale: 7 S rows 100,000 sh $14.40M [plan]" in x for x in out)
    assert any(x.startswith("=== Summary") for x in out) and "  probe line" in out


def test_run_ownership_list_and_unbuilt(capsys, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_ownership

    monkeypatch.setattr(sys, "argv", ["run_ownership.py", "--list"])
    assert run_ownership.main() == 0
    out = capsys.readouterr().out
    assert "insiders   Part 1" in out and "managers   Part 2" in out and "(not built)" not in out
    assert {"insiders", "managers"} == run_ownership.BUILT  # M07 Part 2 built
    assert run_ownership.fetch_type("https://www.sec.gov/Archives/x/form4.xml") == "Form 4 XML"


# --- Massive short-interest probe (D-M07-8) ----------------------------------------------------


def _fetcher(engine, status, body):
    calls = []

    def transport(url, params, headers):
        calls.append((url, dict(params), dict(headers)))
        return status, body, {}

    return Fetcher(engine, transport=transport, sleep=lambda s: None, secrets=("k3y",)), calls


def test_massive_probe_readable_and_not_on_plan(dbs):
    engine, _ = dbs
    body = json.dumps({"status": "OK", "results": [{"settlement_date": "2026-09-30",
                       "short_interest": 120_000_000, "avg_daily_volume": 50_000_000,
                       "days_to_cover": 2.4, "ticker": "AAPL"}]}).encode()  # fmt: skip
    f, calls = _fetcher(engine, 200, body)
    lines = short_interest.probe(f, "k3y")
    assert len(calls) == 1 and calls[0][2]["Authorization"] == "Bearer k3y"
    assert "settlement_date 2026-09-30" in lines[2] and "readable" in lines[3]
    f, _ = _fetcher(engine, 403, b'{"status":"NOT_AUTHORIZED"}')
    lines = short_interest.probe(f, "k3y")
    assert "not available on this key's plan" in lines[1]
    logged = [r[0] for r in engine.execute("SELECT url FROM fetch_log")]
    assert all("k3y" not in u for u in logged)


# --- UI (D-UI-32) -------------------------------------------------------------------------------


def test_view_and_overview_row(dbs):
    engine, _ = dbs
    put(engine, HUANG, HUANG_ACC, NVDA, "2025-06-24")
    put(engine, TAN, TAN_ACC, INTC, "2025-03-25")
    record_coverage(engine, NVDA, "2022-10-01", NOW)
    run_pass(engine, NVDA, "NVDA")
    v = views.company_view(engine, NVDA, TODAY)
    [card] = v.cards
    assert card.kind == "sale" and card.plan == "plan" and card.usd == "$14.40M"
    assert card.stake.startswith("0.012% of stake before (859,148,625)")
    assert card.not_in_total[0].startswith("F 40,163 sh × 144.12")
    assert [n.tf for n in v.net] == ["MY", "PT", "ST"] and v.short_interest.startswith("missing")
    row = views.overview_row(engine, NVDA)
    assert row["buy"] is None and row["net"]["text"] == "none"
    t = views.company_view(engine, INTC, TODAY)
    assert t.cards[0].kind == "issuer" and t.cards[0].class_text == "purchase_from_issuer"
    assert t.history_start == "2025-03-25"  # fallback: earliest stored Form 4


def test_insiders_tab_and_overview_render(tmp_path):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui.app import create_app
    from engine.ui.settings import UiSettings

    data = tmp_path / "data"
    engine = open_db("engine", data)
    engine.execute("INSERT INTO entity (cik, name, source_ref, fetched_at) VALUES (?, 'NVIDIA "
                   "CORP', 't', 'n')", (NVDA,))  # fmt: skip
    engine.execute("INSERT INTO ticker (ticker, cik, valid_from, source) VALUES ('NVDA', ?, "
                   "'2020-01-01', 't')", (NVDA,))  # fmt: skip
    put(engine, HUANG, HUANG_ACC, NVDA, "2025-06-24")
    record_coverage(engine, NVDA, "2022-10-01", NOW)
    run_pass(engine, NVDA, "NVDA")
    engine.close()
    open_db("corpus", data).close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text('[watchlist]\ntickers = ["NVDA"]\n', encoding="utf-8")
    app = create_app(UiSettings(data_dir=data, watchlist=watch))
    with TestClient(app) as c:
        html = c.get("/c/NVDA?tab=insiders").text
        assert "Insider net flow (M07)" in html and "Buy and sale cards" in html
        assert "0.012% of stake before (859,148,625)" in html and "$14.40M" in html
        assert "F 40,163 sh × 144.12" in html and "missing: no short-interest source" in html
        assert "plan basis: row footnote: under 10b5-1 plan" in html
        assert "object at 0x" not in html  # no Python object rendered (D-UI-7)
        over = c.get("/c/NVDA").text
        assert "Insiders (M07)" in over and "no open-market buy stored" in over
