# ruff: noqa: E501  (fixture rows)
"""M04 Part 2: peer facts, offsets, few-peer statistics and peer z on the trend rows
(docs/M04_BUILD_LOG.md Part 2; D-M04-3, -5, -52, -75).

Fixtures: tests/fixtures/m04/{amd,txn,nvda_peer,mu_peer,wdc}_companyfacts_trimmed_20261012.json
(hand-built; figures and placeholders in tests/fixtures/m04/README.md). Peers are fetched
through a fake transport (never SEC)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine.financials import peer_facts, peer_z, peers, stats, step, trends
from engine.refresh import IndexEntry
from engine.sec.xbrl_facts import FACTS_URL, store_facts
from tests.conftest import FIXTURES, FakeTransport, ok

M04 = FIXTURES / "m04"
INTC, AMD, NVDA, TXN, MU, WDC, AMZN = ("0000050863", "0000002488", "0001045810", "0000097476",
                                       "0000723125", "0000106040", "0001018724")  # fmt: skip
FILES = {AMD: "amd", NVDA: "nvda_peer", TXN: "txn", MU: "mu_peer", WDC: "wdc"}
NAMES = {AMD: "ADVANCED MICRO DEVICES INC", NVDA: "NVIDIA CORP", TXN: "TEXAS INSTRUMENTS INC",
         MU: "MICRON TECHNOLOGY INC", WDC: "WESTERN DIGITAL CORP", AMZN: "AMAZON COM INC"}  # fmt: skip
NOW = datetime(2023, 3, 31, 12, 0, tzinfo=UTC)


def body(cik: str) -> bytes:
    return (M04 / f"{FILES[cik]}_companyfacts_trimmed_20261012.json").read_bytes()


def entity(engine, cik, name, fye, ticker=None):
    engine.execute(
        "INSERT OR REPLACE INTO entity (cik, name, fiscal_year_end, source_ref, fetched_at) "
        "VALUES (?, ?, ?, 't', 'n')",
        (cik, name, fye),
    )
    if ticker:
        engine.execute(
            "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES (?, ?, '2000-01-01', 't')",
            (ticker, cik),
        )


def intc(engine):
    entity(engine, INTC, "INTEL CORP", "1231", "INTC")
    engine.execute("BEGIN")
    store_facts(engine, INTC, json.loads((M04 / "intc_companyfacts_trimmed_20261012.json")
                                         .read_text(encoding="utf-8")))  # fmt: skip
    engine.execute("COMMIT")


def confirm_set(engine, target, members):
    engine.execute(
        "INSERT INTO peer_group (name, source, sic, created_at) VALUES (?, 'sic', '3674', 't')",
        (f"M04 peers {target}",),
    )
    gid = engine.execute("SELECT max(group_id) FROM peer_group").fetchone()[0]
    for cik, name in members:
        engine.execute(
            "INSERT INTO peer_member (group_id, cik, name, source) VALUES (?, ?, ?, 'owner')",
            (gid, cik, name),
        )


def routes(*ciks):
    return {FACTS_URL.format(cik=c): [ok(body(c))] for c in ciks}


def fetch_all(make_client, engine, ciks, now=NOW):
    t = FakeTransport(routes(*ciks))
    client = make_client(t)
    out = [peer_facts.fetch_peer(client, engine, c, NAMES[c], now) for c in ciks]
    return out, t


# --- Statistics (D-M04-52) ----------------------------------------------------------------------


INTEL_2022 = [("AMD", 0.436), ("NVDA", 0.002), ("TXN", 0.092), ("MU", -0.083)]


def test_intel_2022_n4_is_the_fixed_gap_fallback():
    r = stats.robust_z(-0.202, INTEL_2022)
    assert r.n == 4 and r.fallback and r.z_info and r.confidence == "low"
    assert r.median == pytest.approx(0.047)
    assert r.gap * 100 == pytest.approx(-24.9)
    assert r.z == pytest.approx(-1.41, abs=0.01)  # MAD × 1.4826 × b_4 (1.363), information
    assert r.spread[0] == pytest.approx(-1.92, abs=0.01)  # MAD × 1.4826
    assert r.spread[1] == pytest.approx(-0.82, abs=0.01)  # IQR type 6
    assert "fewer than 5 → fixed-gap fallback, low confidence" in r.method_text()
    assert "methods spread −1.92 to −0.82".replace("−", "-") in r.method_text()


def test_n5_with_qcom_uses_mad_times_b5():
    r = stats.robust_z(-0.202, INTEL_2022 + [("QCOM", 0.192)])
    assert r.n == 5 and not r.fallback and not r.z_info
    assert r.factor == 1.206 and r.method == "MAD × 1.4826 × b_n"
    assert r.z == pytest.approx(-1.64, abs=0.01)
    assert "b_5 = 1.206" in r.method_text() and "0 dropped" in r.method_text()


@pytest.mark.parametrize("n,b", [(5, 1.206), (6, 1.200), (7, 1.140), (8, 1.129), (9, 1.107)])
def test_b_n_factors_for_5_to_9_peers(n, b):
    vals = [(f"p{i}", float(i)) for i in range(n)]  # 0…n−1
    r = stats.robust_z(100.0, vals)
    med = (n - 1) / 2
    mad = stats.mad([v for _, v in vals])
    assert r.factor == b and r.n == n
    assert r.z == pytest.approx((100.0 - med) / (mad * 1.4826 * b))


def test_ten_or_more_peers_use_iqr():
    vals = [(f"p{i}", float(i)) for i in range(10)]
    r = stats.robust_z(20.0, vals)
    q = __import__("statistics").quantiles([v for _, v in vals], n=4, method="inclusive")
    assert r.method == "IQR ÷ 1.35" and r.factor is None
    assert r.z == pytest.approx((20.0 - 4.5) / ((q[2] - q[0]) / 1.35))


def test_nvda_2023_outlier_dropped_then_fallback():
    peers_2023 = [("AMD", -0.039), ("NVDA", 1.259), ("TXN", -0.125), ("MU", -0.404),
                  ("QCOM", -0.155)]  # fmt: skip
    r = stats.robust_z(-0.140, peers_2023)
    assert [n for n, _ in r.dropped] == ["NVDA"]
    assert r.dropped[0][1] == pytest.approx(8.97, abs=0.1)
    assert r.n_in == 5 and r.n == 4 and r.fallback
    assert r.gap == pytest.approx(0.0, abs=1e-9)
    assert "1 dropped: NVDA z +" in r.method_text()


def test_outliers_are_dropped_once_only():
    # 100 is dropped; recomputed on the 4 left, 10 sits at z > 3 but stays (once only).
    r = stats.robust_z(2.0, [("a", 0.0), ("b", 1.0), ("c", 2.0), ("d", 10.0), ("e", 100.0)])
    assert [n for n, _ in r.dropped] == ["e"] and r.n == 4
    left = [0.0, 1.0, 2.0, 10.0]
    sc = stats.scale(left)
    assert (10.0 - 1.5) / sc.value > 3


def test_no_peers_and_zero_spread_are_not_zero():
    r = stats.robust_z(0.1, [])
    assert r.median is None and r.z is None and r.note == "no comparable peer"
    r = stats.robust_z(0.1, [("a", 0.05), ("b", 0.05)])
    assert r.z is None and "spread is 0" in r.note and r.gap == pytest.approx(0.05)


# --- Offsets and flags (D-M04-5) ----------------------------------------------------------------


def test_offsets_29_to_36_days_kept_two_months_not():
    m = peers.match_period(["2022-12-30"], "2022-12-01", peers.POINT_TOL)
    assert m.ok and m.offset == 29
    m = peers.match_period(["2023-01-06"], "2022-12-01", peers.POINT_TOL)
    assert m.ok and m.offset == 36
    m = peers.match_period(["2022-09-30"], "2022-12-01")  # 62 days behind
    assert not m.ok and m.note.startswith("awaiting peer filing: latest period ends 62 days")
    m = peers.match_period(["2023-01-31"], "2022-12-01")  # two months ahead
    assert not m.ok and "periods start 61 days after" in m.note


def test_53_week_and_acquisition_flags():
    assert peers.week53("2021-12-26", "2022-12-31")  # AMD FY2022, 371 days
    assert not peers.week53("2023-01-01", "2023-12-30")
    note = peers.acquisition_note(23_601e6, None, 24_177e6, 289e6)
    assert note.startswith("acquisition year: goodwill 289.0M → 24.2B")
    assert peers.acquisition_note(23_601e6, 100e6, 300e6, 289e6) == ""
    assert "cash for businesses" in peers.acquisition_note(10e9, 2e9, None, None)


# --- Peer facts (D-M04-75, SB.16) ---------------------------------------------------------------


def test_fetch_trims_to_m04_tags_records_and_is_not_cached(make_client, dbs):
    engine, corpus = dbs
    (f,), _ = fetch_all(make_client, engine, [AMD])
    assert f.outcome == "ok" and f.tags_total == 5 and f.tags_kept == 4  # AP change dropped
    assert f.rows_kept == 10 and f.rows_new == 10 and f.fye == "1230"
    assert f.mb == pytest.approx(len(body(AMD)) / 1e6)
    assert engine.execute("SELECT count(*) FROM fact WHERE cik = ? AND tag = "
                          "'IncreaseDecreaseInAccountsPayable'", (AMD,)).fetchone()[0] == 0  # fmt: skip
    row = peer_facts.stored(engine, AMD)
    assert row["rows_kept"] == 10 and row["outcome"] == "ok" and row["mb"] > 0
    ent = engine.execute(
        "SELECT name, fiscal_year_end FROM entity WHERE cik = ?", (AMD,)
    ).fetchone()
    assert tuple(ent) == ("ADVANCED MICRO DEVICES INC", "1230")  # latest FY end 2023-12-30
    assert corpus.execute("SELECT count(*) FROM http_cache").fetchone()[0] == 0


def test_keep_list_includes_ifrs_and_capex_tags():
    assert ("ifrs-full", "Revenue") in peer_facts.KEEP
    assert ("ifrs-full", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities") in (
        peer_facts.KEEP)  # fmt: skip
    assert ("us-gaap", "PaymentsToAcquireProductiveAssets") in peer_facts.KEEP
    assert ("us-gaap", "Goodwill") in peer_facts.KEEP


def test_failed_and_missing_files_are_recorded(make_client, dbs):
    engine, _ = dbs
    t = FakeTransport({FACTS_URL.format(cik=TXN): [ok(b"", 404)]})
    f = peer_facts.fetch_peer(make_client(t), engine, TXN, "TXN", NOW)
    assert f.outcome == "not_found" and peer_facts.stored(engine, TXN)["outcome"] == "not_found"
    assert engine.execute("SELECT count(*) FROM fact").fetchone()[0] == 0


# --- Peer z on the trend rows -------------------------------------------------------------------


def intel_case(make_client, engine, extra=()):
    intc(engine)
    confirm_set(engine, INTC, [(AMD, "AMD"), (NVDA, "NVDA"), (TXN, "TXN"), (MU, "MU"),
                               (None, "Samsung Electronics"), *extra])  # fmt: skip
    fetch_all(make_client, engine, [AMD, NVDA, TXN, MU])
    return peer_z.compare(engine, "INTC", INTC, "2023-03-31")


def test_intel_2022_revenue_vs_four_peers(make_client, dbs):
    engine, _ = dbs
    comp = intel_case(make_client, engine)
    assert comp.ref_end == "2022-12-31"
    row = comp.rows["rev_yoy"]
    assert row.company.value == pytest.approx(63054 / 79024 - 1)
    got = {m.name: m for m in row.members}
    assert got["AMD"].value == pytest.approx(23601 / 16434 - 1) and got["AMD"].offset == 0
    assert got["NVDA"].offset == 29 and got["MU"].offset == -30 and got["TXN"].offset == 0
    assert got["MU"].value == pytest.approx(27156 / 29619 - 1)  # TTM to 2022-12-01
    assert not got["Samsung Electronics"].included and got["Samsung Electronics"].why == (
        "missing: not an SEC filer")  # fmt: skip
    r = row.result
    assert r.n == 4 and r.fallback and r.z == pytest.approx(-1.41, abs=0.01)
    assert r.gap * 100 == pytest.approx(-24.9, abs=0.05)
    assert "53-week year" in got["AMD"].flags[0]
    assert got["AMD"].flags[1].startswith("acquisition year: goodwill")
    text = row.text()
    assert "fewer than 5 → fixed-gap fallback, low confidence" in text
    assert "12 months to 2022-12-31; peers ±45 d" in text
    lines = {p.name: p for p in comp.lines}
    assert lines["AMD"].in_comparison == "yes (±45 d)" and "acquisition year" in lines["AMD"].note
    assert lines["Samsung Electronics"].note == "missing: not an SEC filer"
    assert "capex: not like-for-like" in lines["NVDA"].note


def test_nvda_out_of_peer_capex_in_every_year(make_client, dbs):
    engine, _ = dbs
    comp = intel_case(make_client, engine)
    for key in ("fcf_growth", "fcf_growth_oe"):
        row = comp.rows[key]
        nv = next(m for m in row.members if m.name == "NVDA")
        assert not nv.included and "not like-for-like" in nv.why
        assert "PP&E tag only; NVDA/AMZN not like-for-like, excluded" in row.note
    # NVIDIA as the company: its own capex rows read missing, never a value.
    confirm_set(engine, NVDA, [(AMD, "AMD"), (TXN, "TXN")])
    own = peer_z.compare(engine, "NVDA", NVDA, "2023-03-31")
    assert own.rows["fcf_growth"].missing.startswith("NVIDIA's capex is not like-for-like")
    assert own.rows["rev_yoy"].result is not None


def test_amzn_fallback_capex_excluded(make_client, dbs):
    engine, _ = dbs
    entity(engine, AMZN, "AMAZON COM INC", "1231")
    engine.execute("BEGIN")
    store_facts(engine, AMZN, json.loads((M04 / "amzn_companyfacts_trimmed_20261012.json")
                                         .read_text(encoding="utf-8")))  # fmt: skip
    engine.execute("COMMIT")
    comp = intel_case(make_client, engine, extra=[(AMZN, "AMZN")])
    am = next(m for m in comp.rows["fcf_growth"].members if m.name == "AMZN")
    assert not am.included and "not like-for-like" in am.why
    tx = next(m for m in comp.rows["fcf_growth"].members if m.name == "TXN")
    assert tx.included  # TXN has PP&E-tag capex and OCF for 2021–22


def test_wdc_against_mu_kept_at_29_days_awaiting_before(make_client, dbs):
    engine, _ = dbs
    entity(engine, MU, "MICRON TECHNOLOGY INC", "0901", "MU")
    engine.execute("BEGIN")
    store_facts(engine, MU, json.loads(body(MU)))
    engine.execute("COMMIT")
    confirm_set(engine, MU, [(WDC, "WDC"), (None, "SK hynix")])
    fetch_all(make_client, engine, [WDC])
    before = peer_z.compare(engine, "MU", MU, "2023-01-31")  # WDC's Dec quarter not filed
    assert before.ref_end == "2022-12-01"
    wd = next(p for p in before.lines if p.name == "WDC")
    assert wd.in_comparison == "no comparable period" and wd.offset == -62
    assert "awaiting peer filing" in wd.note
    assert before.rows["rev_yoy"].result.n == 0
    after = peer_z.compare(engine, "MU", MU, "2023-02-28")
    wd = next(p for p in after.lines if p.name == "WDC")
    assert wd.in_comparison == "yes (±45 d)" and wd.offset == 29 and wd.latest_end == "2022-12-30"
    m = next(m for m in after.rows["rev_yoy"].members if m.name == "WDC")
    assert m.value == pytest.approx(15758 / 18943 - 1)


def test_not_confirmed_reads_so_and_signals_carry_peer_text(make_client, dbs):
    engine, corpus = dbs
    intc(engine)
    comp = peer_z.compare(engine, "INTC", INTC, "2023-03-31")
    assert comp.status == "peers not confirmed on the M04 setup page"
    got = step.part1b(engine, corpus, INTC, "INTC", NOW)
    sig = next(s for s in got.trends.signals if s.name == "rev_yoy")
    assert "peer z: missing: peers not confirmed on the M04 setup page" in sig.method
    assert trends.PEER_TOKEN not in sig.method
    confirm_set(engine, INTC, [(AMD, "AMD"), (NVDA, "NVDA"), (TXN, "TXN"), (MU, "MU")])
    fetch_all(make_client, engine, [AMD, NVDA, TXN, MU])
    step.part1b(engine, corpus, INTC, "INTC", NOW)
    method = engine.execute("SELECT method FROM signal WHERE cik = ? AND signal = 'rev_yoy' "
                            "AND timeframe = 'MY'", (INTC,)).fetchone()[0]  # fmt: skip
    assert "peer z (12 months to 2022-12-31; peers ±45 d): peers n = 4" in method
    assert "fixed-gap fallback" in method


# --- Editable peer sets (owner, Part 2) ---------------------------------------------------------


def peer_item(engine, cik, key="setup"):
    from engine.financials import queue

    engine.execute("BEGIN")
    queue.propose(engine, "m04_peer", f"{cik}:{key}", "confirm peers", {"ticker": "INTC"}, NOW,
                  cik=cik, setup=True)  # fmt: skip
    engine.execute("COMMIT")
    return engine.execute("SELECT max(item_id) FROM review_queue WHERE kind = 'm04_peer'"
                          ).fetchone()[0]  # fmt: skip


def candidates(engine, target, rows):
    for cik, name, source, rank in rows:
        engine.execute(
            "INSERT INTO peer_candidate (target_cik, candidate_cik, name, sic, rank, source, "
            "status, added_at) VALUES (?, ?, ?, '3674', ?, ?, 'proposed', 't')",
            (target, cik, name, rank, source),
        )


def test_empty_confirm_reads_no_peers_confirmed(dbs):
    from engine import review
    from engine.financials import profile

    engine, corpus = dbs
    intc(engine)
    candidates(engine, INTC, [(AMD, "AMD", "sic", 1)])
    item = peer_item(engine, INTC)
    review.m04_action(engine, item, "confirm", "", "owner", NOW, keep=())
    comp = peer_z.compare(engine, "INTC", INTC, "2023-03-31")
    assert comp.confirmed and comp.status == "no peers confirmed"
    assert comp.signal_text("rev_yoy") == "peer z: missing: no peers confirmed"
    got = step.part1b(engine, corpus, INTC, "INTC", NOW)
    sig = next(s for s in got.trends.signals if s.name == "rev_cagr3")
    assert "peer z: missing: no peers confirmed" in sig.method and "fallback" not in sig.method
    p = profile.company_profile(engine, profile.models_mod.load_safe(), INTC, "INTC")
    assert p.peers_text == "no peers confirmed (empty set)"


def test_edit_peers_reopens_a_confirmed_set(make_client, dbs):
    from engine import review
    from engine.financials import peers as peers_mod
    from engine.financials import profile

    engine, _ = dbs
    intc(engine)
    candidates(engine, INTC, [(AMD, "AMD", "sic", 1), (TXN, "TXN", "sic", 2),
                              (NVDA, "NVDA", "sic", 3)])  # fmt: skip
    item = peer_item(engine, INTC)
    review.m04_action(engine, item, "confirm", "", "owner", NOW, keep=(AMD, TXN))
    fetch_all(make_client, engine, [AMD, TXN])
    with pytest.raises(review.ReviewError):  # no set for another company
        review.m04_peer_reopen(engine, MU, "MU", "", "owner", NOW)
    new = review.m04_peer_reopen(engine, INTC, "INTC", "add MU", "owner", NOW)
    assert new != item
    with pytest.raises(review.ReviewError, match="already open"):
        review.m04_peer_reopen(engine, INTC, "INTC", "", "owner", NOW)
    row = engine.execute("SELECT kind, cik, resolved_at FROM review_queue WHERE item_id = ?",
                         (new,)).fetchone()  # fmt: skip
    assert tuple(row) == ("m04_peer", INTC, None)
    prop = engine.execute("SELECT priority, capped FROM m04_proposal WHERE item_id = ?",
                          (new,)).fetchone()  # fmt: skip
    assert tuple(prop) == (0, 0)  # setup kind, outside the weekly cap
    view = profile.setup_view(engine, {"INTC": INTC}, profile.models_mod.load_safe(), NOW)
    t = next(t for g in view.groups for t in g.targets if t.ticker == "INTC")
    assert t.item_id == new and t.reopened and t.set_confirmed
    status = {c.name: c.status for c in t.candidates}
    assert status == {"AMD": "confirmed", "TXN": "confirmed", "NVDA": "struck"}
    # The owner drops TXN and adds MU: MU is the only new download; TXN's facts stay.
    engine.execute("BEGIN")
    peers_mod.add_peer(engine, INTC, MU, False, NOW)
    engine.execute("COMMIT")
    review.m04_action(engine, new, "confirm", "", "owner", NOW, keep=(AMD, MU))
    assert [r["name"] for r in peers_mod.confirmed_peers(engine, INTC)] == ["AMD", MU]
    assert [r["cik"] for r in peer_facts.unfetched_peers(engine, [INTC])] == [MU]
    assert peer_facts.has_facts(engine, TXN)
    comp = peer_z.compare(engine, "INTC", INTC, "2023-03-31")
    assert {p.cik for p in comp.lines} == {AMD, MU}
    hist = engine.execute("SELECT count(*) FROM review_queue WHERE kind = 'm04_peer' AND cik = ? "
                          "AND resolved_at IS NOT NULL", (INTC,)).fetchone()[0]  # fmt: skip
    assert hist == 2


def test_setup_page_edit_peers_button_reopens(tmp_path):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui.app import create_app
    from engine.ui.settings import UiSettings

    data = tmp_path / "data"
    engine = open_db("engine", data)
    open_db("corpus", data).close()
    intc(engine)
    candidates(engine, INTC, [(AMD, "AMD", "sic", 1), (TXN, "TXN", "sic", 2)])
    item = peer_item(engine, INTC)
    engine.close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text('[watchlist]\ntickers = ["INTC"]\n', encoding="utf-8")
    with TestClient(create_app(UiSettings(data_dir=data, watchlist=watch))) as c:
        r = c.post(f"/review/{item}/confirm", data={"back": "/m04/setup"}, follow_redirects=False)
        assert r.status_code == 303  # nothing ticked: an empty set is a valid answer
        page = c.get("/m04/setup").text
        assert "no peers</b>" in page and "Edit peers" in page
        assert "no peers confirmed (empty set)" in c.get("/c/INTC?tab=financials").text
        r = c.post("/m04/peers/INTC/edit", data={"note": "add AMD"}, follow_redirects=False)
        assert "peer%20set%20reopened" in r.headers["location"]
        page = c.get("/m04/setup").text
        assert "Editing the confirmed set" in page and "Edit peers</button>" not in page


# --- Refresh: due peers (D-M04-70) --------------------------------------------------------------


def test_daily_index_marks_peer_due_and_sec_part_refetches(make_client, dbs, clock):
    engine, _ = dbs
    confirm_set(engine, INTC, [(TXN, "TXN")])
    fetch_all(make_client, engine, [TXN], now=datetime(2023, 3, 1, tzinfo=UTC))
    entries = [IndexEntry(TXN, "TEXAS INSTRUMENTS INC", "8-K", "2023-04-25", "a1"),
               IndexEntry(TXN, "TEXAS INSTRUMENTS INC", "10-Q", "2023-04-26", "a2"),
               IndexEntry(AMD, "AMD", "10-Q", "2023-05-03", "a3")]  # AMD: never fetched  # fmt: skip
    assert peer_facts.mark_due(engine, entries) == 1
    assert peer_facts.stored(engine, TXN)["due_accession"] == "a2"
    t = FakeTransport(routes(TXN))
    lines = step.run_sec_part(make_client(t), engine, {"INTC": INTC}, clock.now())
    text = "\n".join(lines)
    assert "M04 peer facts: 1 due" in text and "re-fetched 1" in text
    assert len(t.calls) == 1
    assert peer_facts.stored(engine, TXN)["due_filed"] is None
    step.run_sec_part(make_client(t), engine, {"INTC": INTC}, clock.now())
    assert len(t.calls) == 1  # nothing due any more


# --- Script and tab -----------------------------------------------------------------------------


def test_peers_run_fetches_confirmed_sets_only(make_client, dbs):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_financials

    engine, corpus = dbs
    intc(engine)
    entity(engine, MU, "MICRON TECHNOLOGY INC", "0901", "MU")
    confirm_set(engine, INTC, [(AMD, "AMD"), (NVDA, "NVDA"), (TXN, "TXN"), (MU, "MU"),
                               (None, "Samsung Electronics")])  # fmt: skip
    out: list[str] = []

    def log(*lines):
        out.extend(lines)

    t = FakeTransport(routes(AMD, NVDA, TXN))
    # MU is a covered company here: its own facts, no download.
    run_financials.peers_run(engine, {"INTC": INTC, "MU": MU}, NOW, log, make_client(t),
                             corpus=corpus)  # fmt: skip
    text = "\n".join(out)
    assert len(t.calls) == 3
    assert "MU: peers not confirmed on the M04 setup page — nothing fetched for MU" in text
    assert "MU (0000723125): own facts (covered company" in text
    assert (
        "Peer z on INTC revenue rows:" in text
        and "rev_yoy: peer z (12 months to 2022-12-31" in text
    )
    assert "Groups below 5 (fallback, low confidence):" in text
    assert "AMD (0000002488): 10 rows" in text
    out.clear()
    run_financials.peers_run(engine, {"INTC": INTC, "MU": MU}, NOW, log, make_client(t),
                             corpus=corpus)  # fmt: skip
    assert len(t.calls) == 3  # stored peers are not downloaded again
    assert "0 to fetch" in "\n".join(out)


def test_financials_tab_shows_peer_columns_and_peers_table(tmp_path):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui.app import create_app
    from engine.ui.settings import UiSettings

    data = tmp_path / "data"
    engine = open_db("engine", data)
    open_db("corpus", data).close()
    intc(engine)
    confirm_set(engine, INTC, [(AMD, "AMD"), (None, "Samsung Electronics")])
    engine.execute("BEGIN")
    store_facts(engine, AMD, json.loads(body(AMD)))
    engine.execute("COMMIT")
    entity(engine, AMD, "ADVANCED MICRO DEVICES INC", "1231")
    engine.close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text('[watchlist]\ntickers = ["INTC"]\n', encoding="utf-8")
    with TestClient(create_app(UiSettings(data_dir=data, watchlist=watch))) as c:
        html = c.get("/c/INTC?tab=financials").text
    for text in ("Peer median", "Robust z", "Peer method", "Peers — INTC", "no comparable period",
                 "missing: not an SEC filer", "PP&amp;E tag only; NVDA/AMZN not like-for-like",
                 "not compared: dollar level", "Peer facts: one companyfacts download"):  # fmt: skip
        assert text in html, text
    assert "object at 0x" not in html
