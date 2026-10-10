# ruff: noqa: E501  (fixture text)
"""M02 part 5: supplier discovery L0–L3, review decisions, precision set, Gemini checks."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine import review
from engine.llm import supply_labels
from engine.llm.runs import RunResult
from engine.sec.client import Response
from engine.sec.fulltext import EFTS_URL
from engine.store.db import open_db
from engine.supply import aliases, gold, links
from engine.supply.find import find_l1, find_l2, find_l3
from engine.supply.step import run_supply_step
from tests.conftest import FakeTransport
from tests.test_ui import client  # noqa: F401  (fixture)

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
NVDA, MU, SUPPLIER = "0001045810", "0000723125", "0000999001"
ALIASES = """
[NVDA]
ticker = "NVDA"
names = ["NVIDIA Corporation", "NVIDIA"]
customer = true
[MU]
ticker = "MU"
names = ["Micron Technology", "Micron"]
[TSM]
names = ["Taiwan Semiconductor Manufacturing", "TSMC"]
[SAMSUNG]
names = ["Samsung Electronics", "Samsung"]
[AAPL]
ticker = "AAPL"
names = ["Apple"]
[AMD]
names = ["AMD"]
"""


@pytest.fixture
def matcher(dbs, tmp_path: Path):
    engine, _ = dbs
    for t, c, n in (("NVDA", NVDA, "NVIDIA CORP"), ("MU", MU, "MICRON TECHNOLOGY INC")):
        engine.execute("INSERT INTO ticker (ticker, cik, valid_from, source) VALUES "
                       "(?, ?, '2020-01-01', 't')", (t, c))  # fmt: skip
        engine.execute("INSERT INTO entity (cik, name, fiscal_year_end, source_ref, fetched_at) "
                       "VALUES (?, ?, '0125', 't', 'n')", (c, n))  # fmt: skip
    p = tmp_path / "aliases.toml"
    p.write_text(ALIASES, encoding="utf-8")
    return aliases.Matcher(aliases.load(engine, p))


# --- finding --------------------------------------------------------------------------------


def test_names_match_whole_words_longest_first(matcher):
    text = "Applied Materials and Apple Inc.; Samsung Electronics supplies memory."
    found = [(m.company.key, m.name) for m in matcher.find(text)]
    assert found == [("AAPL", "Apple"), ("SAMSUNG", "Samsung Electronics")]


def test_l1_customer_names_supplier_and_skips_competitors(matcher):
    text = ("We rely on TSMC to manufacture our GPUs and on Samsung for memory.\n"
            "We compete with AMD and Samsung in several markets.\n")  # fmt: skip
    found = find_l1(text, matcher, {"NVDA"})
    assert [(f.b.key, f.direction, f.rung) for f in found] == [
        ("TSM", "b_to_a", "L1"), ("SAMSUNG", "b_to_a", "L1")]  # fmt: skip


def test_l2_supplier_names_customer_with_share(matcher):
    text = ("Sales to NVIDIA accounted for 12% of our net revenue in fiscal 2026.\n"
            "Our products work with NVIDIA platforms.\n")  # fmt: skip
    nvda = next(c for c in matcher.companies if c.key == "NVDA")
    [f] = find_l2(text, matcher, nvda, {"MU"})
    assert (f.b.key, f.direction, str(f.share_pct)) == ("NVDA", "a_to_b", "12")


def test_l3_contract_names_counterparty_once(matcher):
    text = ("This Supply Agreement is entered into by Micron Technology and NVIDIA Corporation.\n"
            "Micron Technology shall supply wafers under this agreement.\n")  # fmt: skip
    found = find_l3(text, matcher, {"MU"})
    assert [(f.b.key, f.direction) for f in found] == [("NVDA", None)]


# --- store, propose, decide -----------------------------------------------------------------


def _store(engine, matcher, a_cik, a_name, text, finder, *args, acc="acc", form="10-K"):
    a_co = matcher.by_cik(a_cik)
    doc = links.Doc(acc, "doc.htm", form, "2026-03-01", text)
    return links.store(engine, a_cik, a_name, a_co, doc, finder(text, matcher, *args), NOW)


def _item(engine, kind="m02_link"):
    return engine.execute("SELECT * FROM review_queue WHERE kind = ? ORDER BY item_id DESC",
                          (kind,)).fetchone()  # fmt: skip


def test_l1_and_l2_of_one_pair_make_one_item_and_confirm_proposes_supplier(dbs, matcher):
    engine, _ = dbs
    nvda = next(c for c in matcher.companies if c.key == "NVDA")
    _store(engine, matcher, NVDA, "NVIDIA Corporation",
           "We purchase memory from Micron and others.\n", find_l1, {"NVDA"}, acc="n1")  # fmt: skip
    _store(engine, matcher, MU, "Micron Technology",
           "Sales to NVIDIA accounted for 12% of our revenue.\n", find_l2, nvda, {"MU"}, acc="m1")  # fmt: skip
    assert links.propose_pairs(engine, NOW) == {"queued": 1}
    it = review.get(engine, _item(engine)["item_id"])
    assert it.payload["claim"] == "Micron Technology supplies NVIDIA Corporation (L2 wording)"
    assert it.payload["share_pct"] == 12.0 and it.payload["rungs"] == ["L1", "L2"]
    review.m02_action(engine, it.item_id, "confirm", "", "owner", NOW)
    rows = engine.execute(
        "SELECT a_cik, direction, status FROM supply_link ORDER BY link_id"
    ).fetchall()
    assert [tuple(r) for r in rows] == [(NVDA, "b_to_a", "confirmed"), (MU, "a_to_b", "confirmed")]
    cand = _item(engine, "m02_candidate")
    assert cand["cik"] == MU and "supplier of NVIDIA" in cand["reason"]


def test_flip_reverses_direction_and_new_passages_follow_decisions(dbs, matcher):
    engine, _ = dbs
    _store(engine, matcher, NVDA, "NVIDIA Corporation",
           "We rely on Micron to supply memory.\n", find_l1, {"NVDA"}, acc="n1")  # fmt: skip
    links.propose_pairs(engine, NOW)
    review.m02_action(engine, _item(engine)["item_id"], "flip", "", "owner", NOW, core={MU})
    assert engine.execute("SELECT direction FROM supply_link").fetchone()[0] == "a_to_b"
    _store(engine, matcher, NVDA, "NVIDIA Corporation",
           "Micron is a sole-source supplier of memory.\n", find_l1, {"NVDA"}, acc="n2")  # fmt: skip
    assert links.follow_decisions(engine) == 1
    assert links.propose_pairs(engine, NOW) == {}


def test_reject_and_unknown_direction_contract(dbs, matcher):
    engine, _ = dbs
    _store(engine, matcher, MU, "Micron Technology",
           "This Supply Agreement is between Micron Technology and NVIDIA Corporation.\n",
           find_l3, {"MU"}, acc="c1", form="8-K")  # fmt: skip
    links.propose_pairs(engine, NOW)
    it = review.get(engine, _item(engine)["item_id"])
    assert it.payload["claim"] == "direction not stated (contract only)"
    review.m02_action(engine, it.item_id, "reject", "", "owner", NOW)
    assert engine.execute("SELECT status FROM supply_link").fetchone()[0] == "rejected"


# --- L2 search and fetch --------------------------------------------------------------------


def _efts(hits):
    return json.dumps({"hits": {"total": {"value": len(hits), "relation": "eq"}, "hits": [
        {"_id": f"{acc}:{fn}", "_source": {"ciks": [cik], "display_names": [f"{name}  (CIK {cik})"],
                                           "form": "10-K", "file_date": "2026-02-15",
                                           "sics": [sic]}}
        for acc, fn, cik, name, sic in hits]}}).encode()  # fmt: skip


def test_l2_search_queues_hits_fetches_and_reads_the_sentence(dbs, matcher, make_client, tmp_path):
    engine, corpus = dbs
    hit = ("0000999001-26-000001", "sup-10k.htm", SUPPLIER, "Example Optics Inc", "3674")
    doc_url = "https://www.sec.gov/Archives/edgar/data/999001/000099900126000001/sup-10k.htm"
    t = FakeTransport({
        EFTS_URL: [Response(200, _efts([hit]), {})],
        doc_url: [Response(200, b"<p>Sales to NVIDIA Corporation represented 31% of our revenue.</p>", {})],
    })  # fmt: skip
    sec = make_client(t, cached=False)
    ap = tmp_path / "aliases.toml"
    lines = run_supply_step(sec, engine, corpus, {}, NOW, customers={"NVDA"}, probe=True,
                            l2_cap=5, alias_path=ap)  # fmt: skip
    assert any("L2: 8 search(es), 1 hit document(s) queued, 1 fetched, 1 new" in ln for ln in lines)
    row = engine.execute("SELECT * FROM supply_link").fetchone()
    assert (row["rung"], row["a_cik"], row["b_cik"], float(row["share_pct"])) == (
        "L2",
        SUPPLIER,
        NVDA,
        31.0,
    )
    assert any(
        "hardware/semiconductor filer(s), 0 not found by the targeted phrases" in ln for ln in lines
    )
    calls = len(t.calls)
    run_supply_step(sec, engine, corpus, {}, NOW, customers={"NVDA"}, alias_path=ap)
    assert len(t.calls) == calls  # searches repeat only after 30 days; nothing queued


# --- precision set and Gemini checks --------------------------------------------------------


def _three_links(engine, matcher):
    nvda = next(c for c in matcher.companies if c.key == "NVDA")
    _store(engine, matcher, NVDA, "NVIDIA Corporation", "We rely on TSMC for wafers.\n",
           find_l1, {"NVDA"}, acc="n1")  # fmt: skip
    _store(engine, matcher, MU, "Micron Technology",
           "Sales to NVIDIA accounted for 12% of revenue.\n", find_l2, nvda, {"MU"}, acc="m1")  # fmt: skip
    _store(engine, matcher, MU, "Micron Technology",
           "This supply agreement with Samsung covers wafers.\n", find_l3, {"MU"}, acc="c1")  # fmt: skip


def test_gold_set_is_mixed_once_and_labels_validate(dbs, matcher):
    engine, _ = dbs
    _three_links(engine, matcher)
    assert gold.build(engine) == 3 and gold.build(engine) == 3  # picked once
    c = gold.card(engine)
    assert c.position == 1 and c.total == 3 and c.labelled == 0
    with pytest.raises(ValueError, match="who supplies whom"):
        gold.label(engine, c.gold_id, "supply", None, "owner", NOW)
    gold.label(engine, c.gold_id, "supply", "a_to_b", "owner", NOW)
    assert gold.card(engine).position == 2


def test_gemini_labels_are_verified_and_measured(dbs, matcher):
    engine, _ = dbs
    _three_links(engine, matcher)
    gold.build(engine)
    rows = {r["rung"]: r for r in engine.execute("SELECT * FROM supply_link")}
    for g in engine.execute("SELECT * FROM link_gold ORDER BY position").fetchall():
        rung = engine.execute(
            "SELECT rung FROM supply_link WHERE link_id = ?", (g["link_id"],)
        ).fetchone()[0]
        answer = {
            "L2": ("supply", "a_to_b"),
            "L1": ("supply", "b_to_a"),
            "L3": ("supply", "unclear"),
        }[rung]
        gold.label(engine, g["gold_id"], *answer, "owner", NOW)
    [req] = supply_labels.label_requests(engine, gold.link_ids(engine))
    assert "L2" not in req.user and "accounted for" in req.user  # no hint of the code's reading
    reply = {"answers": [
        {"id": f"P{rows['L2']['link_id']}", "type": "supply", "direction": "a_to_b", "quote": "Sales to NVIDIA accounted for 12% of revenue"},
        {"id": f"P{rows['L1']['link_id']}", "type": "supply", "direction": "a_to_b", "quote": "We rely on TSMC for wafers"},
        {"id": f"P{rows['L3']['link_id']}", "type": "partner", "direction": "unclear", "quote": "invented words"},
    ]}  # fmt: skip
    obs = req.check(reply)
    assert [o.verified for o in obs] == [True, True, False]
    assert supply_labels.apply_labels(engine, RunResult(1, False, obs)) == 2
    acc = gold.accuracy(engine)
    assert (
        acc.compared,
        acc.supply_said,
        acc.supply_right,
        acc.direction_n,
        acc.direction_right,
    ) == (2, 2, 2, 2, 1)
    assert acc.precision == 1.0 and acc.direction_accuracy == 0.5


def test_input_categories_become_review_items(dbs, matcher):
    engine, corpus = dbs
    text = "Item 1. Business\nWe rely on third parties to manufacture our wafers.\nSupply of high-bandwidth memory is limited.\n"
    corpus.execute("INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, "
                   "fetched_at) VALUES ('k1', ?, 'k.htm', '10-K', 'https://x/k1', ?, 'sha', 'n')",
                   (NVDA, text))  # fmt: skip
    req, meta = supply_labels.input_request(engine, corpus, NVDA)
    obs = req.check({"categories": [
        {"category": "wafer manufacturing (foundry)", "quote": "We rely on third parties to manufacture our wafers."},
        {"category": "high-bandwidth memory", "quote": "Supply of high-bandwidth memory is limited."},
        {"category": "made up", "quote": "We buy unicorns."}]})  # fmt: skip
    assert [o.verified for o in obs] == [True, True, False]
    assert supply_labels.apply_inputs(engine, NVDA, "NVDA", RunResult(7, False, obs), NOW) == 2
    item = _item(engine, "m02_input")
    review.m02_action(engine, item["item_id"], "confirm", "", "owner", NOW)
    assert (
        engine.execute("SELECT count(*) FROM input_category WHERE status = 'confirmed'").fetchone()[
            0
        ]
        == 1
    )


# --- UI --------------------------------------------------------------------------------------


def test_label_page_and_money_tab_section(client, tmp_path):  # noqa: F811
    from tests.test_ui import CIK

    engine = open_db("engine", client.app.state.settings.data_dir)
    p = tmp_path / "aliases.toml"
    p.write_text(ALIASES, encoding="utf-8")
    m = aliases.Matcher(aliases.load(engine, p))
    links.store(engine, CIK, "Meta Platforms", None,
                links.Doc("k1", "k.htm", "10-K", "2026-01-29", "We purchase GPUs from NVIDIA Corporation.\n"),
                find_l1("We purchase GPUs from NVIDIA Corporation.\n", m, set()), NOW)  # fmt: skip
    gold.build(engine)
    engine.close()
    html = client.get("/m02/labels").text
    assert "Passage 1 of 1" in html and "NVIDIA Corporation supplies Meta Platforms" in html
    assert "L1" not in html  # blind: no rung or suggestion shown
    gid = (
        open_db("engine", client.app.state.settings.data_dir)
        .execute("SELECT gold_id FROM link_gold")
        .fetchone()[0]
    )
    r = client.post(
        f"/m02/labels/{gid}", data={"gold_type": "supply", "direction": "b_to_a", "pos": 1}
    )
    assert r.status_code == 200 and "All 1 passages are labelled" in r.text
    tab = client.get("/c/META?tab=money").text
    assert "Suppliers and customers named in filings" in tab and "supplier to this company" in tab
    assert "precision set: 1 labelled" in client.get("/runs").text


# --- live check 1 fixes (2026-10-09) ------------------------------------------------------


def test_market_lists_are_not_suppliers(matcher):
    text = ("suppliers of CPUs and companies with internal platforms, such as Micron and Apple;\n"
            "suppliers and licensors of hardware for GPUs, such as Micron;\n"
            "We purchase memory from Micron.\n")  # fmt: skip
    assert [f.b.key for f in find_l1(text, matcher, {"NVDA"})] == ["MU"]


def test_purchases_reverse_direction_and_ambiguous_shares_are_dropped(matcher):
    nvda = next(c for c in matcher.companies if c.key == "NVDA")
    text = ("Product purchases from Acme Corp, Beta Inc., and NVIDIA accounted for approximately "
            "25%, 21%, and 13%, respectively, of our total product purchases.\n"
            "Other than NVIDIA, no other customer accounted for 5% or more of our revenue.\n")  # fmt: skip
    first, second = find_l2(text, matcher, nvda, set())
    assert (first.direction, first.share_pct) == ("b_to_a", None)
    assert (second.direction, second.share_pct) == ("a_to_b", None)


def test_rescan_updates_kept_passages_and_prunes_the_rest(dbs, matcher):
    engine, _ = dbs
    text = "We purchase memory from Micron and rely on TSMC.\n"
    _store(engine, matcher, NVDA, "NVIDIA Corporation", text, find_l1, {"NVDA"}, acc="n1")
    first = engine.execute(
        "SELECT discovered_at FROM supply_link WHERE b_name = 'Micron Technology'"
    ).fetchone()[0]
    later = datetime(2026, 10, 10, tzinfo=UTC)
    doc = links.Doc("n1", "doc.htm", "10-K", "2026-03-01", text)
    only_mu = [f for f in find_l1(text, matcher, {"NVDA"}) if f.b.key == "MU"]
    links.store(engine, NVDA, "NVIDIA Corporation", matcher.by_cik(NVDA), doc, only_mu, later)
    assert links.prune(engine, later) == 1  # the TSMC passage was not produced again
    row = engine.execute("SELECT discovered_at, seen_at FROM supply_link").fetchone()
    assert row[0] == first and row[1].startswith("2026-10-10")


def test_bare_name_trial_reads_customer_lists_and_marks_them(matcher):
    nvda = next(c for c in matcher.companies if c.key == "NVDA")
    text = ("Our customers include NVIDIA and other GPU makers.\n"
            "We purchase GPUs from NVIDIA for our servers.\n"
            "Our software runs on NVIDIA platforms.\n"
            "We compete with NVIDIA.\n")  # fmt: skip
    from engine.supply.find import find_bare

    found = find_bare(text, matcher, nvda, set())
    assert [(f.direction, f.how.startswith("(c)")) for f in found] == [
        ("a_to_b", True),
        ("b_to_a", True),
    ]


# --- live check 2 fixes (2026-10-10) ------------------------------------------------------


def test_share_sales_products_and_competition_lists_are_noise(matcher):
    nvda = next(c for c in matcher.companies if c.key == "NVDA")
    from engine.supply.find import find_bare

    text = ("We completed the sale of preferred stock to NVIDIA Corporation for $2.0 billion.\n"
            "Our transceivers are a leading supplier option supporting NVIDIA NVLink.\n"
            "We sell our modules to NVIDIA Corporation.\n")  # fmt: skip
    assert [f.how for f in find_bare(text, matcher, nvda, set())] == [
        "(c) bare name: sell our modules to"
    ]
    competition = ("Competition. Our competitors include several companies.\n"
                   "Memory products from Micron, Samsung Electronics and Apple are offered widely by vendors.\n"
                   "We purchase memory from Micron, Samsung Electronics and Apple.\n")  # fmt: skip
    assert len(find_l1(competition, matcher, {"NVDA"})) == 3  # only the purchase sentence
