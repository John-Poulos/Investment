# ruff: noqa: E501  (fixture rows)
"""M04 Part 1c: model tags, life-cycle stage, the M04 queue, browse-by-SIC and the peer
shortlist, the setup page and the Financials-tab Profile block (docs/M04_BUILD_LOG.md
Part 1c).

Fixtures: tests/fixtures/m04/stage_cases_20261012.json (hand-built cash-flow totals whose
signs and revenue CAGRs follow the R1 brief) and browse_sic3674_page_trimmed.htm (EDGAR
browse-by-SIC layout); sources in tests/fixtures/m04/README.md."""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from engine import review
from engine.financials import models, peers, profile, queue, stage
from engine.sec import browse
from engine.signals import latest_signal
from engine.themes import proposals
from tests.conftest import FIXTURES, FakeTransport, ok

M04 = FIXTURES / "m04"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
TODAY = NOW.date()
M = 1_000_000
CASES = json.loads((M04 / "stage_cases_20261012.json").read_text(encoding="utf-8"))["companies"]
ETV = "0001300000"  # placeholder CIK: the tag file keys ETV by ticker
TAGS = {
    "years": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInInvestingActivities",
        "NetCashProvidedByUsedInFinancingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
        "ProceedsFromDivestitureOfBusinessesNetOfCashDivested",
    ),
}
REAL_MODELS = models.load(Path(__file__).resolve().parent.parent / "config" / "company_models.toml")


def _fact(engine, cik, tag, start, end, value, n):
    filed = (date.fromisoformat(end) + timedelta(days=40)).isoformat()
    engine.execute(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession, "
        "form, filed) VALUES (?, 'us-gaap', ?, 'USD', ?, ?, ?, ?, '10-K', ?)",
        (cik, tag, start, end, value, f"{cik}-{end[2:4]}-9{n:05d}", filed),
    )


def load_case(engine, ticker: str) -> str:
    c = CASES[ticker]
    cik = c["cik"]
    engine.execute(
        "INSERT OR REPLACE INTO entity (cik, name, sic, fiscal_year_end, source_ref, fetched_at) "
        "VALUES (?, ?, ?, ?, 't', 'n')",
        (cik, f"{ticker} fixture", c["sic"], c["fye"]),
    )
    engine.execute(
        "INSERT OR IGNORE INTO ticker (ticker, cik, valid_from, source) VALUES (?, ?, '2000-01-01', 't')",
        (ticker, cik),
    )
    n = 0
    for end, vals in c["years"].items():
        start = (date.fromisoformat(end) - timedelta(days=364)).isoformat()
        for tag, v in zip(TAGS["years"], vals, strict=True):
            if v == 0 and tag.startswith(("PaymentsToAcquireBusinesses", "ProceedsFrom")):
                continue  # no fact: taken as none (named in the method)
            n += 1
            _fact(engine, cik, tag, start, end, v * M, n)
    for end, v in c["revenue"].items():
        start = (date.fromisoformat(end) - timedelta(days=364)).isoformat()
        n += 1
        _fact(
            engine, cik, "RevenueFromContractWithCustomerExcludingAssessedTax", start, end, v * M, n
        )
    return cik


def load_all(engine) -> dict[str, str]:
    comps = {t: load_case(engine, t) for t in CASES}
    engine.execute(
        "INSERT INTO entity (cik, name, sic, source_ref, fetched_at) VALUES (?, 'Eaton Vance fund', NULL, 't', 'n')",
        (ETV,),
    )
    engine.execute(
        "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES ('ETV', ?, '2000-01-01', 't')",
        (ETV,),
    )
    comps["ETV"] = ETV
    return comps


# --- Model tags (D-M04-8) ---------------------------------------------------------------------


def test_tag_file_loads_three_entries_and_rejects_unknown_tags():
    assert REAL_MODELS.error == ""
    assert [(e.ticker, e.tag) for e in REAL_MODELS.entries] == [
        ("MSTR", "asset_treasury"), ("ETV", "fund"), ("INFQ", "spac_shell")]  # fmt: skip
    with pytest.raises(models.ModelFileError, match="unknown tag 'bank'"):
        models.parse({"company": [{"ticker": "JPM", "tag": "bank", "reason": "r", "source": "s"}]})
    with pytest.raises(models.ModelFileError, match="missing reason"):
        models.parse({"company": [{"ticker": "O", "tag": "reit", "source": "s"}]})
    with pytest.raises(models.ModelFileError, match="cik must be 10 digits"):
        models.parse({"company": [{"cik": "1050446", "tag": "reit", "reason": "r", "source": "s"}]})
    bad = models.ModelFile("x", (), "entry 1: unknown tag 'bank'")
    assert bad.for_company(CASES["MSTR"]["cik"], "MSTR") is None  # a rejected file applies no tag


def test_infq_spac_shell_keyed_on_period_end(dbs):
    engine, _ = dbs
    infq, mstr = CASES["INFQ"]["cik"], CASES["MSTR"]["cik"]
    assert REAL_MODELS.for_company(infq, "INFQ", "2025-12-31").tag == "spac_shell"
    assert REAL_MODELS.for_company(infq, "INFQ", "2026-02-12").tag == "spac_shell"
    assert REAL_MODELS.for_company(infq, "INFQ", "2026-03-31") is None
    assert REAL_MODELS.for_company(infq, "INFQ") is None  # today: the shell years are over
    assert REAL_MODELS.for_company(mstr, None).tag == "asset_treasury"  # keyed by CIK
    assert REAL_MODELS.for_company(ETV, "ETV").tag == "fund"  # keyed by ticker
    load_case(engine, "MSTR")
    assert (
        models.route(engine, REAL_MODELS, mstr, "MSTR")[0] == "asset_treasury"
    )  # tag over SIC 6199
    engine.execute("INSERT INTO entity (cik, name, sic, source_ref, fetched_at) VALUES "
                   "('0000000099', 'Some REIT', '6798', 't', 'n')")  # fmt: skip
    tag, how = models.route(engine, REAL_MODELS, "0000000099", "XREIT")
    assert tag == "financial" and "not applicable" in how and "reit" in how


# --- Stage (D-M04-7, -46) ---------------------------------------------------------------------


def test_dickinson_patterns():
    assert stage.dickinson(1, -1, 1) == "growth"
    assert stage.dickinson(-1, -1, 1) == "introduction"
    assert stage.dickinson(1, -1, -1) == "mature"
    assert {stage.dickinson(*s) for s in ((-1, -1, -1), (1, 1, 1), (1, 1, -1))} == {"shake_out"}
    assert {stage.dickinson(*s) for s in ((-1, 1, 1), (-1, 1, -1))} == {"decline"}


@pytest.mark.parametrize(
    ("ticker", "computed", "reasons", "cagr"),
    [
        ("AAPL", "mature", [], 0.018),
        ("INTC", "growth", ["growth_falling"], -0.057),
        ("TSLA", "growth", [], 0.052),
        ("NVDA", "mature", ["mature_fast"], 1.000),
        ("MU", "mature", ["mature_fast"], 1.046),
        ("BA", None, ["no_stage"], 0.103),
        ("MRVL", "mature", [], 0.114),
        ("META", "mature", [], 0.199),
        ("MSTR", "introduction", ["intro_falling"], -0.015),
        ("SPCX", None, ["short_history"], None),
        ("INFQ", None, ["short_history"], None),
    ],
)
def test_stage_cases(dbs, ticker, computed, reasons, cagr):
    engine, _ = dbs
    cik = load_case(engine, ticker)
    r = stage.compute(engine, cik, TODAY.isoformat())
    assert r.computed == computed
    assert r.reasons == reasons
    if cagr is None:
        assert r.cagr3 is None
    else:
        assert round(r.cagr3, 3) == cagr
    if ticker == "AAPL":  # shake-out on total investing (maturing securities), mature on core
        assert [y.stage_total for y in r.years] == ["shake_out"] * 3
        assert [y.signs for y in r.years] == ["+ − −"] * 3
        assert r.total_note.startswith("on total investing") and "holds shake-out" in r.total_note
    if ticker == "MU":
        assert [y.stage for y in r.years] == ["mature", "mature", "growth"]
    if ticker == "MRVL":  # latest year's divestiture → shake-out on core too; mature holds
        assert r.years[-1].stage == "shake_out" and r.years[-1].core > 0
    if ticker == "BA":
        assert [y.stage for y in r.years] == ["mature", "introduction", "shake_out"]
    if ticker == "SPCX":
        assert len(r.years) == 1 and r.computed is None
    if ticker == "INTC":
        assert "acquisitions" in r.method  # no fact: taken as none, named


def test_flag_sets_per_stage():
    assert stage.flag_set("introduction").sets == ("young",)
    g = stage.flag_set("growth")
    assert g.sets == ("young",) and g.sga_rule
    assert stage.flag_set("decline").reversion_prior == "unused"
    assert stage.flag_set("shake_out").sets == ("all-stage",)
    u = stage.flag_set(None)
    assert u.sets == ("young", "mature") and not u.counted and "unconfirmed" in u.label
    assert stage.flag_set("mature", "fund").label == "not applicable (fund)"


# --- First run, confirmation, routing (D-M04-12, -71) -----------------------------------------


def stage_items(engine):
    return engine.execute(
        "SELECT * FROM review_queue WHERE kind = 'm04_stage' ORDER BY item_id"
    ).fetchall()


def test_first_run_opens_15_setup_items_outside_the_cap(dbs):
    engine, _ = dbs
    comps = load_all(engine)
    assert len(comps) == 16
    sp = profile.stage_pass(engine, comps, REAL_MODELS, NOW)
    items = stage_items(engine)
    assert len(items) == 15 and set(sp.opened.values()) == {"queued"}
    assert "ETV" in sp.excluded and "fund" in sp.excluded["ETV"]
    props = engine.execute("SELECT DISTINCT capped, priority FROM m04_proposal").fetchall()
    assert [tuple(p) for p in props] == [(0, 0)]  # setup: outside the weekly cap
    assert queue.queued_this_week(engine, NOW) == 0
    by = {json.loads(r["payload"])["ticker"]: json.loads(r["payload"]) for r in items}
    assert by["MSTR"]["why"] == ["first", "intro_falling", "tag_first"]
    assert stage.REASONS["intro_falling"] == "introduction with falling revenue (CAGR < 0%)"
    assert by["AAPL"]["why"] == ["first"] and by["AAPL"]["computed"] == "mature"
    assert by["BA"]["why"] == ["first", "no_stage"]
    assert by["SPCX"]["why"] == ["first", "short_history"]
    # Signals: unconfirmed until the owner answers; ETV missing (fund).
    s = latest_signal(engine, CASES["AAPL"]["cik"], "M04", "lifecycle_stage")
    assert (
        s["value_text"] == "unconfirmed" and s["value"] is None and "both computed" in s["method"]
    )
    e = latest_signal(engine, ETV, "M04", "lifecycle_stage")
    assert e["value_text"] is None and e["method"].startswith("missing: not applicable (fund)")
    # A second pass opens nothing new.
    sp2 = profile.stage_pass(engine, comps, REAL_MODELS, NOW + timedelta(days=1))
    assert set(sp2.opened.values()) == {"suppressed"} and len(stage_items(engine)) == 15


def test_confirm_routes_until_changed_and_new_10k_reopens(dbs):
    engine, _ = dbs
    comps = {t: load_case(engine, t) for t in ("AAPL", "BA", "TSLA")}
    profile.stage_pass(engine, comps, REAL_MODELS, NOW)
    items = {json.loads(r["payload"])["ticker"]: r["item_id"] for r in stage_items(engine)}
    done = review.m04_action(engine, items["AAPL"], "confirm", "ok", "owner", NOW)
    assert done == "confirm mature (as computed)"
    with pytest.raises(review.ReviewError, match="choose one"):
        review.m04_action(engine, items["BA"], "confirm", "", "owner", NOW)
    review.m04_action(engine, items["BA"], "confirm", "", "owner", NOW, target="mature")
    review.m04_action(engine, items["TSLA"], "confirm", "", "owner", NOW, target="introduction")
    aapl = CASES["AAPL"]["cik"]
    assert stage.confirmed(engine, aapl)["confirmed"] == "mature"
    s = latest_signal(engine, aapl, "M04", "lifecycle_stage", "PT")
    assert s["value_text"] == "mature" and "owner-confirmed mature" in s["method"]
    assert "info (weight 0)" in s["method"]
    t = review.get(engine, items["TSLA"])
    assert t.resolution.startswith("confirm introduction (override (computed growth))")
    # Same fiscal year again: nothing new, the owner's stage keeps routing.
    profile.stage_pass(engine, comps, REAL_MODELS, NOW + timedelta(days=1))
    assert len(stage_items(engine)) == 3
    # A new 10-K: AAPL turns growth (financing inflow) → a capped item in group 2.
    start, end = "2025-10-01", "2026-09-30"
    for i, (tag, v) in enumerate(
        zip(TAGS["years"][:4], (120000, -10000, 20000, 14000), strict=True)
    ):
        _fact(engine, aapl, tag, start, end, v * M, 900 + i)
    engine.execute(  # FY2025 financing restated in the FY2026 10-K: an inflow
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession, form, filed) "
        "VALUES (?, 'us-gaap', 'NetCashProvidedByUsedInFinancingActivities', 'USD', '2024-10-01', '2025-09-30', ?, "
        "'0000320193-26-999999', '10-K', '2026-11-09')",
        (aapl, 5000 * M),
    )
    later = datetime(2026, 11, 20, tzinfo=UTC)
    sp = profile.stage_pass(engine, comps, REAL_MODELS, later)
    assert sp.opened.get("AAPL") == "queued"
    p = engine.execute(
        "SELECT * FROM m04_proposal WHERE prop_key = ?", (f"m04_stage:{aapl}:2026-09-30",)
    ).fetchone()
    assert (p["priority"], p["capped"]) == (2, 1)
    assert json.loads(p["payload"])["why"][0] == "changed"
    assert stage.confirmed(engine, aapl)["confirmed"] == "mature"  # still routes until answered


def test_owner_override_without_an_item(dbs):
    engine, _ = dbs
    comps = {"META": load_case(engine, "META")}
    profile.stage_pass(engine, comps, REAL_MODELS, NOW)
    item = stage_items(engine)[0]["item_id"]
    review.m04_action(engine, item, "confirm", "", "owner", NOW)
    done = review.m04_override(
        engine,
        CASES["META"]["cik"],
        "META",
        "growth",
        "AI build-out",
        "owner",
        NOW + timedelta(hours=1),
    )
    assert done.startswith("confirm growth")
    assert stage.confirmed(engine, CASES["META"]["cik"])["confirmed"] == "growth"
    assert len(stage_items(engine)) == 2  # the override is in the review history


# --- Queue: cap 5, priority, baselines; M02 unchanged --------------------------------------------


def test_m04_cap_priority_flush_and_baselines(dbs):
    engine, _ = dbs
    kinds = [
        "m04_mscore",
        "m04_restate",
        "m04_stage",
        "m04_event",
        "m04_dilution",
        "m04_runway",
        "m04_customer",
    ]
    out = [
        queue.propose(engine, k, f"k{i}", f"r{i}", {}, NOW + timedelta(minutes=i))
        for i, k in enumerate(kinds)
    ]
    assert out == ["queued"] * 5 + ["overflow"] * 2
    assert queue.queued_this_week(engine, NOW) == 5
    # Setup, operational and alert kinds are outside the cap.
    assert queue.propose(engine, "m04_peer", "p", "r", {}, NOW, setup=True) == "queued"
    assert queue.propose(engine, "m04_gate_fail", "g", "r", {}, NOW) == "queued"
    assert queue.propose(engine, "m04_credit_line", "c", "r", {}, NOW) == "queued"
    assert queue.queued_this_week(engine, NOW) == 5
    # M02's cap of 10 counts only M02 items.
    assert proposals.queued_this_week(engine, NOW) == 0
    # Overflow flushes next week by group (runway = 1 before customer = 6), oldest first.
    nxt = NOW + timedelta(days=7)
    assert queue.flush_overflow(engine, nxt) == 2
    order = [
        r[0]
        for r in engine.execute(
            "SELECT kind FROM review_queue WHERE created_at >= ? ORDER BY item_id",
            (nxt.isoformat(timespec="seconds"),),
        )
    ]
    assert order == ["m04_runway", "m04_customer"]
    # Repeats are suppressed.
    assert queue.propose(engine, "m04_mscore", "k0", "r", {}, nxt) == "suppressed"
    # Baselines: recorded, not queued, except items filed in the last 12 months and a current fail.
    assert (
        queue.propose(engine, "m04_restate", "old", "r", {}, nxt, baseline=True, filed="2019-03-01")
        == "baseline"
    )
    assert (
        queue.propose(engine, "m04_restate", "new", "r", {}, nxt, baseline=True, filed="2026-05-01")
        == "queued"
    )
    assert queue.propose(
        engine,
        "m04_gc_text",
        "fail",
        "r",
        {},
        nxt,
        baseline=True,
        filed="2018-01-01",
        current_fail=True,
    ) in ("queued", "overflow")
    pr = engine.execute(
        "SELECT priority FROM m04_proposal WHERE prop_key = 'm04_gc_text:fail'"
    ).fetchone()[0]
    assert pr == 1
    assert [r["prop_key"] for r in queue.baselines(engine)] == ["m04_restate:old"]


# --- Browse-by-SIC and the shortlist (D-M04-4, S6.2) --------------------------------------------

ROW = (
    '<tr>\n<td valign="top"><a href="/cgi-bin/browse-edgar?action=getcompany&amp;CIK={cik}&amp;type={form}'
    '&amp;dateb=&amp;owner=include&amp;count=100">{cik}</a></td>\n<td valign="top">{name}</td>\n'
    '<td valign="top">CA</td>\n</tr>\n'
)


def page(rows: list[tuple[str, str]], form: str = "10-K") -> bytes:
    body = "".join(ROW.format(cik=c, name=n, form=form) for c, n in rows)
    return (
        f'<html><body><table class="tableFile2" summary="Results">\n<tr><th scope="col">CIK</th>'
        f'<th scope="col">Company</th><th scope="col">State/Country</th></tr>\n{body}</table>'
        "</body></html>"
    ).encode()


def test_browse_page_parser_on_the_fixture():
    rows = browse.parse_browse(
        (M04 / "browse_sic3674_page_trimmed.htm").read_text(encoding="utf-8")
    )
    assert len(rows) == 5
    assert rows[2] == ("0000056978", "KULICKE & SOFFA INDUSTRIES INC")
    assert rows[3] == ("0000723125", "MICRON TECHNOLOGY INC")


SEMIS = {"MU": "0000723125", "NVDA": "0001045810", "INTC": "0000050863", "MRVL": "0001835632"}
GFS = "0001709048"


def sic3674(engine, transport_routes: dict) -> list[tuple[str, str]]:
    """507 companies on the one browse (6 pages): 505 10-K-style names plus GFS and an old
    foreign filer (the type parameter does not filter the list, live check 1); 82 filed a
    10-K in the last 12 months; GFS filed a 20-F."""
    listed = [(c, f"SEMI FIXTURE {i:03d} INC") for i, c in
              enumerate((f"{9000000 + i:010d}" for i in range(501)), 1)]  # fmt: skip
    listed += [(c, f"{t} FIXTURE") for t, c in SEMIS.items()]
    full = sorted(listed + [(GFS, "GLOBALFOUNDRIES Inc."), ("0009999999", "FOREIGN OLD SEMI LTD")],
                  key=lambda r: r[1])  # fmt: skip
    listed.sort(key=lambda r: r[1])
    pages = [ok(page(full[i : i + 100])) for i in range(0, 507, 100)]
    transport_routes[browse.BROWSE_URL] = pages
    active = [c for c, _ in listed if c not in SEMIS.values()][:78] + list(SEMIS.values())
    for i, c in enumerate(active):
        engine.execute("INSERT INTO form_filing (accession, cik, family, form, filed) VALUES (?, ?, '10-K', ?, ?)",
                       (f"a{i}", c, "10-K/A" if i == 5 else "10-K", "2026-02-20"))  # fmt: skip
    for i, c in enumerate(
        [c for c, _ in listed if c not in active][:30]
    ):  # older 10-Ks: not active
        engine.execute("INSERT INTO form_filing (accession, cik, family, form, filed) VALUES (?, ?, '10-K', '10-K', '2024-03-01')",
                       (f"o{i}", c))  # fmt: skip
    engine.execute(
        "INSERT INTO form_filing (accession, cik, family, form, filed) VALUES ('g1', ?, '20-F', '20-F', '2026-03-14')",
        (GFS,),
    )
    engine.execute(
        "INSERT INTO form_filing (accession, cik, family, form, filed) VALUES ('g2', '0009999999', '20-F', '20-F', '2023-04-01')"
    )
    for y in (2025, 2026):
        for q in (1, 2, 3, 4):
            engine.execute(
                "INSERT INTO form_index (year, quarter, rows, closed, source_ref, fetched_at) VALUES (?, ?, 1, 1, 't', 'n')",
                (y, q),
            )
    return listed


def frames_routes(
    routes: dict, values: dict[str, float], prior: dict[str, float] | None = None
) -> None:
    """CY2025: the 3 ranking frames; CY2024: the 2 us-gaap frames of the suspect guard."""

    def rows(vals: dict[str, float], y: int) -> bytes:
        data = [{"cik": int(c), "entityName": c, "val": v, "accn": f"{c}-{y - 1999}-000001",
                 "end": f"{y}-12-31", "start": f"{y}-01-01"} for c, v in vals.items()]  # fmt: skip
        return json.dumps({"data": data}).encode()

    url = "https://data.sec.gov/api/xbrl/frames/{t}/{g}/USD/CY{y}.json"
    rfc = "RevenueFromContractWithCustomerExcludingAssessedTax"
    routes[url.format(t="us-gaap", g=rfc, y=2025)] = [ok(rows(values, 2025))]
    routes[url.format(t="us-gaap", g="Revenues", y=2025)] = [ok(b"", 404)]
    routes[url.format(t="ifrs-full", g="Revenue", y=2025)] = [ok(rows({}, 2025))]
    routes[url.format(t="us-gaap", g=rfc, y=2024)] = [ok(rows(prior or {}, 2024))]
    routes[url.format(t="us-gaap", g="Revenues", y=2024)] = [ok(b"", 404)]


def test_sic3674_browse_505_listed_82_active_and_20f_filer_counted(dbs, make_client):
    engine, _ = dbs
    routes: dict = {}
    sic3674(engine, routes)
    revenue = {c: 1e9 * (i + 1) for i, c in enumerate(f"{9000000 + i:010d}" for i in range(78))}
    revenue |= {
        SEMIS["MU"]: 37.4e9,
        SEMIS["NVDA"]: 130.5e9,
        SEMIS["INTC"]: 53.1e9,
        SEMIS["MRVL"]: 5.8e9,
        GFS: 6.75e9,
    }
    frames_routes(routes, revenue)
    transport = FakeTransport(routes)
    client = make_client(transport)
    b = browse.browse_sic(client, "3674")
    assert (b.pages, b.listed, len(b.companies), b.capped, b.partial) == (6, 507, 507, False, False)
    assert len(transport.calls) == 6 and transport.calls[0][1]["SIC"] == "3674"
    assert {c[1]["type"] for c in transport.calls} == {"10-K"}  # one browse, cached URLs kept
    engine.execute("BEGIN")
    # a stale row from the earlier per-form browses is replaced by the one browse row
    engine.execute("INSERT INTO sic_browse (sic, browsed, pages, listed, capped, fetched_at) "
                   "VALUES ('3674', '20-F', 3, 300, 1, 'n')")  # fmt: skip
    browse.store(engine, b, NOW)
    engine.execute("COMMIT")
    assert (
        engine.execute("SELECT count(*) FROM sic_listing WHERE browsed = '10-K'").fetchone()[0]
        == 507
    )
    assert [tuple(r) for r in engine.execute(
        "SELECT browsed, pages, listed, capped FROM sic_browse WHERE sic = '3674'")] == [
        ("10-K", 6, 507, 0)]  # fmt: skip
    ciks = [r[0] for r in engine.execute("SELECT cik FROM sic_listing")]
    act = peers.active_filers(engine, ciks, TODAY)
    on_10k = sum(1 for f, _ in act.values() if f.startswith("10-K"))
    assert (on_10k, len(act)) == (82, 83) and act[GFS] == ("20-F", "2026-03-14")
    assert "0009999999" not in act  # listed on the 20-F browse, last 20-F too old
    lines = peers.fetch_revenue_frames(client, engine, 2025, NOW)
    assert any("RevenueFromContract" in ln and "CY2025: 83 companies" in ln for ln in lines)
    assert len(transport.calls) == 6 + 5  # 3 CY2025 frames + 2 CY2024 (suspect guard)
    s = peers.shortlist(engine, SEMIS["MU"], "3674", TODAY, year=2025)
    assert (s.listed, s.active) == (507, 83) and len(s.candidates) == peers.SHORTLIST
    assert SEMIS["MU"] not in {c.cik for c in s.candidates}
    assert s.candidates[0].revenue == 37e9
    assert [c.rank for c in s.candidates] == list(range(1, 11))
    dists = [abs(__import__("math").log(c.revenue / 37.4e9)) for c in s.candidates]
    assert dists == sorted(dists)
    m = peers.shortlist(engine, SEMIS["MRVL"], "3674", TODAY, year=2025)
    assert GFS in {c.cik for c in m.candidates}  # a 20-F filer near MRVL's revenue is ranked


def test_page_cap_marks_partial_only_when_the_last_page_was_full(make_client):
    def full(k: int) -> bytes:
        return page([(f"{8000000 + k * 100 + i:010d}", f"CO {k}-{i:03d}") for i in range(100)])

    transport = FakeTransport({browse.BROWSE_URL: [ok(full(k)) for k in range(4)]})
    b = browse.browse_sic(make_client(transport), "7372", page_cap=4)  # every page full
    assert (b.pages, len(b.companies), b.capped, b.partial) == (4, 400, True, True)
    assert len(transport.calls) == 4
    # 800 listed and a cap of 10 (SIC 7372, live check 1): page 9 comes back empty → complete
    pages = [ok(full(k)) for k in range(8)] + [ok(page([]))]
    transport = FakeTransport({browse.BROWSE_URL: pages})
    b = browse.browse_sic(make_client(transport), "7373")  # another SIC: no shared cache
    assert (b.pages, len(b.companies), b.capped, b.partial) == (9, 800, False, False)
    # a short last page at the cap is the end of the list, not partial
    pages = [ok(full(k)) for k in range(3)] + [ok(page([("0008999999", "LAST CO")]))]
    b = browse.browse_sic(make_client(FakeTransport({browse.BROWSE_URL: pages})), "7374",
                          page_cap=4)  # fmt: skip
    assert (b.pages, len(b.companies), b.capped) == (4, 301, False)


def _suspect_setup(engine, make_client, facts: bool):
    """TIGO-like: a small 3674 filer whose CY2025 frame reads 103.5B (scaling error)."""
    routes: dict = {}
    sic3674(engine, routes)
    tigo = "0009000003"  # active in the fixture
    near = {"0009000001": 30e9, "0009000002": 45e9}
    frames_routes(routes, {SEMIS["MU"]: 37.4e9, tigo: 103.5e9, **near},
                  prior=None if facts else {tigo: 54e6, "0009000001": 28e9})  # fmt: skip
    client = make_client(FakeTransport(routes))
    b = browse.browse_sic(client, "3674")
    engine.execute("BEGIN")
    browse.store(engine, b, NOW)
    engine.execute("COMMIT")
    peers.fetch_revenue_frames(client, engine, 2025, NOW)
    return tigo


def test_suspect_revenue_ranks_after_valued_names_by_year_ratio(dbs, make_client):
    engine, _ = dbs
    tigo = _suspect_setup(engine, make_client, facts=False)
    s = peers.shortlist(engine, SEMIS["MU"], "3674", TODAY, year=2025)
    names = {c.cik: c for c in s.candidates}
    assert [c.cik for c in s.candidates[:2]] == [
        "0009000002",
        "0009000001",
    ]  # valued first (45B nearer 37.4B)
    t = names[tigo]
    assert t.rank == 3 and t.revenue == 103.5e9  # kept, value shown, not dropped
    assert t.suspect == "CY2025 103.5B vs CY2024 54.0M"
    assert t.revenue_ref.startswith(
        "revenue suspect: CY2025 103.5B vs CY2024 54.0M · CY2025 us-gaap:"
    )
    assert s.suspects == [("SEMI FIXTURE 004 INC", "CY2025 103.5B vs CY2024 54.0M")]
    assert not names["0009000001"].suspect  # 30B vs 28B: no flag
    assert all(c.revenue is None for c in s.candidates[3:])  # revenue missing after suspects
    # stored and read back: the setup page and the log show the mark
    engine.execute("BEGIN")
    peers.store_shortlist(engine, s, NOW)
    engine.execute("COMMIT")
    back = {c.cik: c for c in peers.candidates(engine, SEMIS["MU"])}
    assert back[tigo].suspect == "CY2025 103.5B vs CY2024 54.0M"


def test_suspect_revenue_against_stored_facts(dbs, make_client):
    engine, _ = dbs
    tigo = _suspect_setup(engine, make_client, facts=True)  # no CY2024 frame values
    _fact(engine, tigo, "RevenueFromContractWithCustomerExcludingAssessedTax", "2025-01-01",
          "2025-12-31", 103.5e6, 1)  # fmt: skip
    assert peers.revenue_suspect(engine, tigo, 2025, 103.5e9, TODAY.isoformat()) == (
        "CY2025 103.5B vs stored FY to 2025-12-31 103.5M"
    )
    assert peers.revenue_suspect(engine, tigo, 2025, 110e6, TODAY.isoformat()) == ""
    assert peers.revenue_suspect(engine, "0009000002", 2025, 45e9, TODAY.isoformat()) == ""
    s = peers.shortlist(engine, SEMIS["MU"], "3674", TODAY, year=2025)
    assert [c.cik for c in s.candidates[:3]] == ["0009000002", "0009000001", tigo]


# --- Peer confirmation (D-M04-4) -----------------------------------------------------------------


def test_peer_item_add_strike_non_sec_and_confirm(dbs, make_client):
    engine, _ = dbs
    routes: dict = {}
    sic3674(engine, routes)
    frames_routes(routes, {SEMIS["MU"]: 37.4e9, "0009000001": 30e9, "0009000002": 40e9})
    client = make_client(FakeTransport(routes))
    mu = load_case(engine, "MU")
    b = browse.browse_sic(client, "3674")
    engine.execute("BEGIN")
    browse.store(engine, b, NOW)
    engine.execute("COMMIT")
    peers.fetch_revenue_frames(client, engine, 2025, NOW)
    pp = profile.peer_pass(engine, {"MU": mu}, REAL_MODELS, NOW)
    assert pp.opened == {"MU": "queued"}
    item = engine.execute("SELECT * FROM review_queue WHERE kind = 'm04_peer'").fetchone()
    assert "confirm peers — 10 ranked from SIC 3674 (507 listed, 83 active)" in item["reason"]
    engine.execute(
        "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES ('WDC', '0000106040', '2000-01-01', 't')"
    )
    engine.execute(
        "INSERT INTO entity (cik, name, sic, source_ref, fetched_at) VALUES ('0000106040', 'WESTERN DIGITAL CORP', '3572', 't', 'n')"
    )
    engine.execute("BEGIN")
    wdc = peers.add_peer(engine, mu, "wdc", False, NOW)
    hynix = peers.add_peer(engine, mu, "SK hynix", True, NOW)
    engine.execute("COMMIT")
    assert (wdc.cik, wdc.name, wdc.source) == ("0000106040", "WESTERN DIGITAL CORP", "owner")
    assert hynix.cik is None and hynix.revenue_ref == peers.NOT_SEC
    with pytest.raises(peers.PeerError, match="Unknown ticker"):
        peers.add_peer(engine, mu, "QCOMX", False, NOW)
    cands = peers.candidates(engine, mu)
    keep = tuple(c.key for c in cands if c.cik != "0009000002")  # strike one SIC name
    done = review.m04_action(
        engine, item["item_id"], "confirm", "WDC: NAND", "owner", NOW, keep=keep
    )
    assert done == "confirm: 11 peer(s) kept, 1 struck, 2 added by the owner"
    members = peers.confirmed_peers(engine, mu)
    assert len(members) == 11
    assert any(r["cik"] is None and r["name"] == "SK hynix" for r in members)
    struck = engine.execute(
        "SELECT status FROM peer_candidate WHERE candidate_cik = '0009000002'"
    ).fetchone()[0]
    assert struck == "struck"
    pf = profile.company_profile(engine, REAL_MODELS, mu, "MU")
    assert (
        pf.peers_text == "11 confirmed" and "SK hynix (missing: not an SEC filer)" in pf.peer_names
    )


# --- The profile subcommand on a scratch database (dependency injection, no main()) ---------------


def run_financials_module():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_financials

    return run_financials


def test_profile_run_requests_and_owner_summary(dbs, make_client):
    engine, _ = dbs
    rf = run_financials_module()
    comps = load_all(engine)
    routes: dict = {}
    sic3674(engine, routes)
    routes[browse.BROWSE_URL] = [ok(page([(SEMIS["MU"], "MICRON")]))]  # one short page per browse
    frames_routes(routes, {SEMIS["MU"]: 37.4e9})
    transport = FakeTransport(routes)
    lines: list[str] = []
    rf.profile_run(
        engine, comps, REAL_MODELS, NOW, lambda *a: lines.extend(a), make_client(transport)
    )
    browses = [c for c in transport.calls if c[0] == browse.BROWSE_URL]
    sics = {c[1]["SIC"] for c in browses}
    assert sics == {
        "3571",
        "3674",
        "3711",
        "3721",
        "5961",
        "7370",
        "7372",
        "7374",
    }  # MSTR's 6199: tag overrides
    # 8 SICs × 1 browse (one short page each) + 3 CY2025 frames + 2 CY2024 frames
    assert len(browses) == 8 and len(transport.calls) == 13
    text = "\n".join(lines)
    assert "SIC 3674: 1 companies in 1 page(s)" in text and "PARTIAL" not in text
    assert "20-F browse" not in text and "40-F browse" not in text
    assert "MSTR: introduction" in text and "introduction with falling revenue (CAGR < 0%)" in text
    for want in ("loaded with 3 entries: MSTR asset_treasury (all periods); ETV fund (all periods); "
                 "INFQ spac_shell (periods ending before 2026-02-13)",
                 "Stages computed: 15", "Setup stage items: 15 queued now",
                 "Setup peer items: 15 queued now", "S1 re-probe — SIC 3674 full list",
                 "SIC 3674: listed", "Companies with no usable SIC peers",
                 "MSTR: model tag asset_treasury overrides SIC 6199",
                 "ETV: no stage — model tag fund"):  # fmt: skip
        assert want in text, want
    assert (
        engine.execute("SELECT count(*) FROM review_queue WHERE kind = 'm04_peer'").fetchone()[0]
        == 15
    )
    # A local re-run (no client): 0 requests, nothing new opened.
    n = len(transport.calls)
    lines.clear()
    rf.profile_run(
        engine, comps, REAL_MODELS, NOW + timedelta(hours=1), lambda *a: lines.extend(a), None
    )
    assert len(transport.calls) == n and "SEC skipped (--no-sec)" in "\n".join(lines)
    assert "Setup peer items: 0 queued now, 15 already open" in "\n".join(lines)


def test_local_pass_runs_the_stage_pass(dbs):
    from engine.financials import step

    engine, corpus = dbs
    comps = {"AAPL": load_case(engine, "AAPL")}
    lines = step.run_local_part(engine, corpus, comps, NOW)
    assert "Parts 1a–1c" in lines[0]
    assert "stages computed for 1 companies, 1 stage item(s) opened" in lines[1]


# --- UI: setup page and Profile block --------------------------------------------------------------


def test_setup_page_actions_and_profile_block(tmp_path):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui.app import create_app
    from engine.ui.settings import UiSettings

    data = tmp_path / "data"
    engine = open_db("engine", data)
    open_db("corpus", data).close()
    tick = ["AAPL", "META", "BA", "MSTR", "MU"]
    comps = {t: load_case(engine, t) for t in tick}
    profile.stage_pass(engine, comps, REAL_MODELS, datetime.now(UTC))
    for t, (name, value) in {
        "3674": ("MICRON TECHNOLOGY INC", SEMIS["MU"]),
        "3571": ("APPLE INC", CASES["AAPL"]["cik"]),
    }.items():
        engine.execute(
            "INSERT INTO sic_listing (sic, cik, name, browsed, fetched_at) VALUES (?, ?, ?, '10-K', 'n')",
            (t, value, name),
        )
    engine.execute(
        "INSERT INTO sic_listing (sic, cik, name, browsed, fetched_at) VALUES ('3674', '0009000001', 'OTHER SEMI', '10-K', 'n')"
    )
    engine.execute("INSERT INTO form_filing (accession, cik, family, form, filed) VALUES ('x1', '0009000001', '10-K', '10-K', ?)",
                   ((datetime.now(UTC).date() - timedelta(days=30)).isoformat(),))  # fmt: skip
    profile.peer_pass(engine, comps, REAL_MODELS, datetime.now(UTC))
    mu_item = engine.execute(
        "SELECT item_id FROM review_queue WHERE kind = 'm04_peer' AND cik = ?", (SEMIS["MU"],)
    ).fetchone()[0]
    engine.close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text(
        '[watchlist]\ntickers = ["AAPL", "META", "BA", "MSTR", "MU"]\n', encoding="utf-8"
    )
    with TestClient(create_app(UiSettings(data_dir=data, watchlist=watch))) as c:
        html = c.get("/m04/setup").text
        for text in ("1. Life-cycle stages", "2. Peer shortlists", "3. Model tags", "Confirm mature",
                     "Confirm all 2 plain mature", "no stage holds 2 of 3", "mature with CAGR &gt; 20%",
                     "model tag routes first", "on total investing", "asset_treasury", "spac_shell",
                     "OTHER SEMI", "not an SEC filer", "Stage routes red flags only",
                     "keeps routing until you change it", "unknown tag is rejected",
                     "the engine never writes the file", "M04 setup",
                     "is marked \"revenue suspect\""):  # fmt: skip
            assert text in html, text
        assert "object at 0x" not in html
        r = c.post("/m04/stage/confirm-all", data={"items": [1, 3]}, follow_redirects=False)
        assert r.status_code == 303 and "2%20stage" in r.headers["location"]
        r = c.post(
            f"/m04/peer/{mu_item}/add",
            data={"peer": "Samsung Electronics", "not_sec": "1"},
            follow_redirects=False,
        )
        assert "Samsung" in r.headers["location"]
        r = c.post(f"/review/{mu_item}/confirm", data={"keep": ["0009000001", "name:Samsung Electronics"], "back": "/m04/setup"},
                   follow_redirects=False)  # fmt: skip
        assert r.headers["location"].startswith("/m04/setup?msg=")
        page_ = c.get("/m04/setup").text
        assert "Confirmed: OTHER SEMI, Samsung Electronics" in page_
        fin = c.get("/c/AAPL?tab=financials").text
        assert "Profile" in fin and "mature (confirmed" in fin and "flag set: mature set" in fin
        mu_fin = c.get("/c/MU?tab=financials").text
        assert "2 confirmed" in mu_fin and "unconfirmed" in mu_fin
        mstr = c.get("/c/MSTR?tab=financials").text
        assert "asset_treasury (all periods)" in mstr
        item = c.get("/review/4").text
        assert "Open on the M04 setup page" in item
