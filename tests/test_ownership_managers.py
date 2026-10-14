"""M07 Part 2: followed managers' 13F-HR (D-SEC-28, D-M02-63, D-UI-34, D-M07-18…)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from engine.financing import issuers, links, thirteenf
from engine.financing import views as fin_views
from engine.financing.step import check_items, issuer_items
from engine.ownership import managers as mg
from engine.refresh import IndexEntry
from engine.sec.browse import parse_company_search
from engine.sec.documents import filing_folder
from engine.sec.identity import SUBMISSIONS_URL
from tests.conftest import FakeTransport, fixture_bytes, ok

BRK, DUQ = "0001067983", "0009999901"  # DUQ: fictional CIK for a Duquesne-style manager
AAPL, NVDA, GOOG, MSFT, KO, ACME, ACME2 = (
    "0000320193", "0001045810", "0001652044", "0000789019", "0000021344", "0000000771",
    "0000000772",
)  # fmt: skip
OURS = {AAPL: "AAPL", NVDA: "NVDA", GOOG: "GOOG", MSFT: "MSFT", ACME: "ACME"}
NOW = datetime(2024, 10, 1, 12, 0, tzinfo=UTC)
REF_Q1, REF_Q2, OLD = "0000950123-24-005622", "0000950123-24-008740", "0000950123-22-099901"
FIX = {REF_Q1: "brk_2024q1", REF_Q2: "brk_2024q2", OLD: "brk_2022q3"}
CONFIG = """
[[manager]]
name = "Berkshire Hathaway Inc"
cik = "0001067983"
note = "Warren Buffett"

[[manager]]
name = "Duquesne Family Office LLC"
cik = ""
note = "Stanley Druckenmiller"

[cusips]
"999999" = "MSFT"
"""


@pytest.fixture
def world(dbs, tmp_path):
    engine, corpus = dbs
    for t, c, n in (("AAPL", AAPL, "Apple Inc."), ("NVDA", NVDA, "NVIDIA CORP"),
                    ("GOOG", GOOG, "Alphabet Inc."), ("MSFT", MSFT, "MICROSOFT CORP"),
                    ("KO", KO, "COCA COLA CO"), ("ACME", ACME, "Acme Holdings Inc."),
                    ("ACMX", ACME2, "ACME HOLDINGS INC /DE/"),
                    ("BRK-B", BRK, "BERKSHIRE HATHAWAY INC")):  # fmt: skip
        engine.execute("INSERT INTO ticker (ticker, cik, name, valid_from, source) VALUES "
                       "(?, ?, ?, '2020-01-01', 't')", (t, c, n))  # fmt: skip
    engine.execute("INSERT INTO entity (cik, name, source_ref, fetched_at) VALUES (?, ?, 't', ?)",
                   (DUQ, "Duquesne Family Office LLC", NOW.isoformat()))  # fmt: skip
    cfg = tmp_path / "m07_managers.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    return engine, corpus, cfg


def filing(engine, acc, cik, form, filed):
    engine.execute("INSERT OR IGNORE INTO filing (accession, cik, form, filed, ingested_at) VALUES "
                   "(?, ?, ?, ?, 'n')", (acc, cik, form, filed))  # fmt: skip
    engine.execute("INSERT OR IGNORE INTO filing_cik (accession, cik) VALUES (?, ?)", (acc, cik))


def brk_routes(*accs):
    out = {}
    for acc in accs:
        folder, tag = filing_folder(BRK, acc), FIX[acc]
        table = {REF_Q1: "32398.xml", REF_Q2: "34725.xml", OLD: "45678.xml"}[acc]
        out[f"{folder}/{acc}-index.htm"] = [ok(fixture_bytes(f"m07/13f/{tag}_index.htm"))]
        out[f"{folder}/primary_doc.xml"] = [ok(fixture_bytes(f"m07/13f/{tag}_primary_doc.xml"))]
        out[f"{folder}/{table}"] = [ok(fixture_bytes(f"m07/13f/{tag}_infotable.xml"))]
    return out


def submissions(cik, rows, name="Berkshire Hathaway Inc"):
    arrays = {k: [] for k in ("accessionNumber", "filingDate", "reportDate", "acceptanceDateTime",
                              "form", "primaryDocument", "primaryDocDescription")}  # fmt: skip
    for acc, form, filed in rows:
        for k, v in (
            ("accessionNumber", acc),
            ("filingDate", filed),
            ("reportDate", ""),
            ("acceptanceDateTime", f"{filed}T16:00:00.000Z"),
            ("form", form),
            ("primaryDocument", "primary_doc.xml"),
            ("primaryDocDescription", form),
        ):
            arrays[k].append(v)  # fmt: skip
    return ok(
        json.dumps(
            {
                "cik": cik,
                "name": name,
                "tickers": [],
                "exchanges": [],
                "filings": {"recent": arrays, "files": []},
            }
        ).encode()
    )


BRK_LIST = [
    (OLD, "13F-HR", "2022-11-14"),
    (REF_Q1, "13F-HR", "2024-05-15"),
    (REF_Q2, "13F-HR", "2024-08-14"),
    ("0001067983-24-000001", "4", "2024-06-01"),
]


def cover(engine, cik, day, value):
    engine.execute(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession, "
        "form, filed) VALUES (?, 'dei', 'EntityCommonStockSharesOutstanding', 'shares', NULL, ?, "
        "?, ?, '10-Q', ?)",
        (cik, day, value, f"cov-{day}", day),
    )


def sync_brk(engine, make_client, *, now=NOW, reference=False):
    transport = FakeTransport({SUBMISSIONS_URL.format(cik=BRK): [submissions(BRK, BRK_LIST)]}
                              | brk_routes(OLD, REF_Q1, REF_Q2))  # fmt: skip
    m = mg.Manager("Berkshire Hathaway Inc", BRK)
    s = mg.sync_manager(make_client(transport), engine, m, OURS, {}, issuers.Names(engine), now,
                        reference=reference)  # fmt: skip
    return s, transport


def test_config_placeholder_and_real_config_loads(world):
    _, _, cfg = world
    c = mg.load_config(cfg)
    assert [(m.name, m.cik) for m in c.managers] == [
        ("Berkshire Hathaway Inc", BRK),
        ("Duquesne Family Office LLC", None),
    ]
    real = mg.load_config(mg.CONFIG)  # the committed owner file
    assert [m.cik for m in real.managers] == [BRK, None] and not real.problems
    assert "CEO of equity" in real.text  # DESIGN Q3 stays open, not added
    broken = cfg.parent / "bad.toml"
    broken.write_text("[[manager]\n", encoding="utf-8")
    assert mg.load_config(broken).managers == [] and mg.load_config(broken).problems


def test_resolve_by_stored_name_then_company_search(world, make_client):
    engine, _, _ = world
    duq = mg.Manager("Duquesne Family Office LLC", None)
    assert mg.resolve(engine, duq).cik == DUQ  # stored entity, no request
    engine.execute("DELETE FROM entity WHERE cik = ?", (DUQ,))
    assert mg.resolve(engine, duq).cik is None  # no client: never the network
    one = ('<span class="companyName">Duquesne Family Office LLC <acronym title="Central Index '
           'Key">CIK</acronym>#: <a href="/cgi-bin/browse-edgar?action=getcompany&amp;CIK='
           f'{DUQ}&amp;owner=include">{DUQ} (see all company filings)</a></span>')  # fmt: skip
    assert parse_company_search(one) == [(DUQ, "Duquesne Family Office LLC")]
    url = "https://www.sec.gov/cgi-bin/browse-edgar"
    t = FakeTransport({url: [ok(one.encode())]})
    r = mg.resolve(engine, duq, make_client(t))
    assert r.cik == DUQ and r.how.startswith("EDGAR company search") and len(t.calls) == 1
    assert t.calls[0][1]["company"] == "Duquesne Family Office LLC"


def test_sync_reads_13f_with_keep_filter_and_thousands(world, make_client):
    engine, _, _ = world
    s, transport = sync_brk(engine, make_client)
    assert s.status == "synced" and s.listed_13f == 3 and len(s.reads) == 3
    # 1 submissions + 3 × (index, cover, table); load_entity used the cached submissions file
    assert len(transport.calls) == 10
    assert all(r.kept == 1 and r.skipped == 5 for r in s.reads)  # AAPL kept; 5 others left out
    names = {x.issuer for x in s.skipped_rows}
    assert names == {"BANK AMER CORP", "AMERICAN EXPRESS CO", "COCA COLA CO", "CHEVRON CORP NEW",
                     "OCCIDENTAL PETE CORP"}  # KO resolves, but is not ours  # fmt: skip
    rows = {r["period"]: r for r in engine.execute("SELECT * FROM fin_holding WHERE filer_cik = ?",
                                                   (BRK,))}  # fmt: skip
    assert set(rows) == {"2022-09-30", "2024-03-31", "2024-06-30"}
    assert all(r["issuer_cik"] == AAPL for r in rows.values())
    assert float(rows["2024-03-31"]["shares"]) == 789_368_450  # 12 rows summed by CUSIP
    assert float(rows["2024-06-30"]["value_usd"]) == 84_248_000_000
    assert float(rows["2022-09-30"]["value_usd"]) == 123_661_680_000  # thousands before 2023
    assert mg.is_followed(engine, BRK) and BRK in thirteenf.followed_filers(engine)
    again, t2 = sync_brk(engine, make_client)
    assert again.reads == [] and len(t2.calls) == 1  # only the submissions file: nothing due


def test_berkshire_apple_cut_reference(world, make_client):
    engine, _, _ = world
    cover(engine, AAPL, "2022-10-14", 15_908_118_000)
    cover(engine, AAPL, "2024-04-19", 15_334_082_000)
    cover(engine, AAPL, "2024-07-19", 15_204_137_000)
    sync_brk(engine, make_client)
    sp = mg.signal_pass(engine, [mg.Manager("Berkshire Hathaway Inc", BRK)], OURS)
    evs = {e.period: e for e in sp.events[AAPL]}
    assert "2022-09-30" not in evs  # the first stored quarter is the baseline
    q2 = evs["2024-06-30"]
    assert q2.text == "cut" and q2.delta == -389_368_450 and q2.prior == "2024-03-31"
    assert q2.pct_before == pytest.approx(5.148, abs=1e-3)
    assert q2.pct_after == pytest.approx(2.631, abs=1e-3)
    assert "filed 2024-08-14 (45 days later; 13F-HR is due 45 days" in q2.line()
    q1 = evs["2024-03-31"]
    assert q1.text == "cut" and "no 13F stored for 2022-12-31, 2023-03-31" in q1.line()
    row = engine.execute("SELECT * FROM signal WHERE cik = ? AND signal = ? AND timeframe = 'MY' "
                         "AND as_of = '2024-08-14'", (AAPL, mg.SIGNAL)).fetchone()  # fmt: skip
    assert row["value"] == -389_368_450 and row["value_text"] == "cut"
    assert row["evidence_grade"] == "A" and row["source_ref"] == f"{REF_Q2} +1"
    assert "soft vote" in row["method"] and "info (weight 0)" not in row["method"]
    st = engine.execute("SELECT method FROM signal WHERE cik = ? AND signal = ? AND timeframe = "
                        "'ST' AND as_of = '2024-08-14'", (AAPL, mg.SIGNAL)).fetchone()  # fmt: skip
    assert st["method"].endswith("info (weight 0)")


def test_reference_filings_outside_the_8_quarters(world, make_client):
    engine, _, _ = world
    late = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    s, _ = sync_brk(engine, make_client, now=late)
    assert s.reads == []  # all three are older than the last 8 quarters
    s, _ = sync_brk(engine, make_client, now=late, reference=True)
    assert [r.accession for r in s.reads] == [REF_Q1, REF_Q2]
    n, how = mg.plan(engine, mg.Manager("B", BRK), OURS, late, reference=True)
    assert n == 1 and "0 unread" in how


def test_m02_does_not_see_followed_manager_rows(world, make_client):
    engine, _, _ = world
    sync_brk(engine, make_client)
    # an M02 filer's own row (NVDA's 13F holding AAPL) stays visible
    filing(engine, "nv-1", NVDA, "13F-HR", "2024-08-14")
    engine.execute("INSERT INTO fin_13f (accession, filer_cik, form, period, filed, scale, status, "
                   "read_at) VALUES ('nv-1', ?, '13F-HR', '2024-06-30', '2024-08-14', 1, 'read', "
                   "'n')", (NVDA,))  # fmt: skip
    engine.execute("INSERT INTO fin_holding (source, accession, filer_cik, filer_name, issuer_cik, "
                   "issuer_name, cusip, shares, value_usd, period, filed, status, discovered_at) "
                   "VALUES ('13F', 'nv-1', ?, 'NVIDIA CORP', ?, 'APPLE INC', '037833100', 10, "
                   "2000, '2024-06-30', '2024-08-14', 'automatic', 'n')", (NVDA, AAPL))  # fmt: skip
    edges = links.financing_edges(engine)
    assert [(e.financer, e.other) for e in edges] == [(NVDA, AAPL)]  # no Berkshire K1 edge
    others = [r for r, _ in fin_views._holding_rows(engine, AAPL)]
    assert others and all("BERKSHIRE" not in r.other.upper() for r in others)
    # a held or unresolved manager row never becomes an M02 review item
    engine.execute("UPDATE fin_holding SET status = 'held', check_note = 'x' WHERE filer_cik = ?",
                   (BRK,))  # fmt: skip
    engine.execute("INSERT INTO fin_holding (source, accession, filer_cik, filer_name, "
                   "issuer_name, cusip, shares, value_usd, period, filed, status, discovered_at) "
                   "VALUES ('13F', ?, ?, 'Berkshire', 'ACME HLDGS INC', '000771AA1', 5, 50, "
                   "'2024-06-30', '2024-08-14', 'unresolved', 'n')", (REF_Q2, BRK))  # fmt: skip
    assert check_items(engine, NOW) == 0 and issuer_items(engine, NOW) == 0
    assert engine.execute("SELECT count(*) FROM review_queue").fetchone()[0] == 0


def test_store_rows_is_not_fed_rows_of_other_companies(world):
    engine, _, _ = world
    names = issuers.Names(engine)
    keep = mg.keep_filter(names, OURS, {"999999": MSFT})
    rows = [thirteenf.Row("APPLE INC", "COM", "037833100", 10, 1, "SH", ""),
            thirteenf.Row("COCA COLA CO", "COM", "191216100", 10, 1, "SH", ""),
            thirteenf.Row("BANK AMER CORP", "COM", "060505104", 10, 1, "SH", ""),
            thirteenf.Row("ACME HLDGS INC", "COM", "000771AA1", 10, 1, "SH", ""),
            thirteenf.Row("MYSTERY CO", "COM", "999999AB1", 10, 1, "SH", "")]  # fmt: skip
    filing(engine, "x-1", BRK, "13F-HR", "2024-08-14")
    f = engine.execute("SELECT accession, form, filed FROM filing WHERE accession = 'x-1'"
                       ).fetchone()  # fmt: skip
    rep = thirteenf.Report13F()
    cov = thirteenf.Cover("2024-06-30", 5, 50, None)
    thirteenf.store_rows(engine, BRK, f, cov, rows, names, NOW, rep, keep=keep)
    stored = {r["issuer_name"]: r for r in engine.execute("SELECT * FROM fin_holding")}
    assert set(stored) == {"APPLE INC", "ACME HLDGS INC", "MYSTERY CO"}
    assert [x.issuer for x in rep.skipped] == ["COCA COLA CO", "BANK AMER CORP"]
    acme = stored["ACME HLDGS INC"]
    assert acme["status"] == "unresolved" and acme["issuer_cik"] is None
    assert "possibly ours: ACME 0000000771 (CUSIP 000771AA1" in acme["check_note"]
    assert stored["MYSTERY CO"]["issuer_cik"] == MSFT  # owner's config CUSIP map
    assert stored["MYSTERY CO"]["resolved_how"] == "owner (m07_managers.toml)"


# --- a Duquesne-style manager (generated in EDGAR's layout) -------------------------------------

TABLE_NS = "http://www.sec.gov/edgar/document/thirteenf/informationtable"


def table(rows):
    body = "".join(
        f"<infoTable><nameOfIssuer>{n}</nameOfIssuer><titleOfClass>{t}</titleOfClass>"
        f"<cusip>{c}</cusip><value>{v}</value><shrsOrPrnAmt><sshPrnamt>{s}</sshPrnamt>"
        f"<sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>"
        + (f"<putCall>{pc}</putCall>" if pc else "")
        + "<investmentDiscretion>SOLE</investmentDiscretion></infoTable>"
        for n, t, c, v, s, pc in rows
    )
    return f'<informationTable xmlns="{TABLE_NS}">{body}</informationTable>'.encode()


def cover_xml(period, total, amend=None):
    p = f"{period[5:7]}-{period[8:10]}-{period[:4]}"
    am = (f"<isAmendment>true</isAmendment><amendmentInfo><amendmentType>{amend}</amendmentType>"
          "</amendmentInfo>") if amend else "<isAmendment>false</isAmendment>"  # fmt: skip
    return (f'<edgarSubmission xmlns="http://www.sec.gov/edgar/thirteenffiler"><headerData>'
            f"<filerInfo><periodOfReport>{p}</periodOfReport></filerInfo></headerData><formData>"
            f"<coverPage><reportCalendarOrQuarter>{p}</reportCalendarOrQuarter>{am}</coverPage>"
            f"<summaryPage><tableValueTotal>{total}</tableValueTotal></summaryPage></formData>"
            "</edgarSubmission>").encode()  # fmt: skip


def duq_filing(engine, acc, form, filed, period, rows, amend=None):
    filing(engine, acc, DUQ, form, filed)
    folder = filing_folder(DUQ, acc)
    path = folder.removeprefix("https://www.sec.gov")
    index = (
        '<table class="tableFile" summary="Document Format Files"><tr><th>Seq</th>'
        "<th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>"
        f'<tr><td>1</td><td></td><td><a href="{path}/primary_doc.xml">primary_doc.xml</a>'
        f'</td><td>{form}</td><td>1</td></tr><tr><td>2</td><td></td><td><a href="{path}/'
        'info.xml">info.xml</a></td><td>INFORMATION TABLE</td><td>1</td></tr></table>'
    )
    total = sum(r[3] for r in rows)
    return {f"{folder}/{acc}-index.htm": [ok(index.encode())],
            f"{folder}/primary_doc.xml": [ok(cover_xml(period, total, amend))],
            f"{folder}/info.xml": [ok(table(rows))]}  # fmt: skip


NV, GA, GC, MS = "67066G104", "02079K305", "02079K107", "594918104"


def duq_world(engine):
    """Q1 2024 → Q2 2024 (NVDA 10:1 split between) → Q3 missing → Q4 (+ restatement, + new
    holdings amendment)."""
    engine.execute("INSERT INTO price_fetch (symbol, cik) VALUES ('NVDA', ?)", (NVDA,))
    engine.execute("INSERT INTO price_bar (symbol, date, close, volume, split_factor, source, "
                   "fetched_at) VALUES ('NVDA', '2024-06-10', 120, 1, 10, 't', 'x')")  # fmt: skip
    routes = {}
    routes |= duq_filing(engine, "d-24q1", "13F-HR", "2024-05-15", "2024-03-31", [
        ("NVIDIA CORPORATION", "COM", NV, 900_000_000, 1_000_000, ""),
        ("NVIDIA CORPORATION", "COM", NV, 450_000_000, 500_000, "Call"),
        ("ALPHABET INC", "CAP STK CL A", GA, 15_000_000, 100_000, ""),
        ("COCA COLA CO", "COM", "191216100", 6_000_000, 100_000, ""),
    ])  # fmt: skip
    routes |= duq_filing(engine, "d-24q2", "13F-HR", "2024-08-14", "2024-06-30", [
        ("NVIDIA CORPORATION", "COM", NV, 990_000_000, 8_000_000, ""),
        ("ALPHABET INC", "CAP STK CL A", GA, 18_000_000, 100_000, ""),
        ("ALPHABET INC", "CAP STK CL C", GC, 9_000_000, 50_000, ""),
        ("MICROSOFT CORP", "COM", MS, 89_000_000, 200_000, ""),
    ])  # fmt: skip
    routes |= duq_filing(engine, "d-24q4", "13F-HR", "2025-02-14", "2024-12-31", [
        ("NVIDIA CORPORATION", "COM", NV, 1_070_000_000, 8_000_000, ""),
        ("ALPHABET INC", "CAP STK CL A", GA, 19_000_000, 100_000, ""),
        ("ALPHABET INC", "CAP STK CL C", GC, 9_500_000, 50_000, ""),
        ("ACME HLDGS INC", "COM", "000771AA1", 1_000_000, 10_000, ""),
    ])  # fmt: skip
    routes |= duq_filing(engine, "d-24q4a", "13F-HR/A", "2025-03-01", "2024-12-31", [
        ("NVIDIA CORPORATION", "COM", NV, 940_000_000, 7_000_000, ""),
        ("ALPHABET INC", "CAP STK CL A", GA, 19_000_000, 100_000, ""),
        ("ALPHABET INC", "CAP STK CL C", GC, 9_500_000, 50_000, ""),
    ], amend="RESTATEMENT")  # fmt: skip
    routes |= duq_filing(engine, "d-24q4n", "13F-HR/A", "2025-05-15", "2024-12-31", [
        ("APPLE INC", "COM", "037833100", 250_000_000, 1_000_000, ""),
    ], amend="NEW HOLDINGS")  # fmt: skip
    return routes


DUQ_NOW = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)


def read_duq(engine, make_client):
    routes = duq_world(engine)
    client = make_client(FakeTransport(routes))
    names = issuers.Names(engine)
    s = mg.ManagerSync(mg.Manager("Duquesne Family Office LLC", DUQ), "synced")
    mg.mark_followed(engine, s.manager, DUQ_NOW)
    mg._read_due(client, engine, s.manager, thirteenf.due(engine, DUQ, DUQ_NOW),
                 mg.keep_filter(names, OURS, {}), names, DUQ_NOW, s)  # fmt: skip
    return s


def test_cases_new_add_cut_exit_hold_split_options_amendments(world, make_client):
    engine, _, _ = world
    for c, d, v in (
        (NVDA, "2024-05-01", 2_460_000_000),
        (NVDA, "2024-08-01", 24_530_000_000),
        (MSFT, "2024-07-25", 7_433_000_000),
        (GOOG, "2024-07-20", 12_300_000_000),
    ):
        cover(engine, c, d, v)  # fmt: skip
    s = read_duq(engine, make_client)
    assert len(s.reads) == 5 and sum(r.skipped for r in s.reads) == 1  # KO left out
    duq = mg.Manager("Duquesne Family Office LLC", DUQ)
    sp = mg.signal_pass(engine, [duq], OURS)
    ev = {(e.cik, e.period): e for es in sp.events.values() for e in es}
    nv2 = ev[(NVDA, "2024-06-30")]
    assert nv2.missing is None, nv2.missing
    # 1,000,000 pre-split = 10,000,000 post-split → 8,000,000: a cut, not a 7× add
    assert nv2.text == "cut" and nv2.delta == -2_000_000 and "× 10 for a split" in nv2.line()
    assert "apart, not in Δ" not in nv2.line()  # the Q2 table has no call row
    g2 = ev[(GOOG, "2024-06-30")]
    assert g2.text == "add" and g2.delta == 50_000 and "classes summed" in g2.line()
    assert ev[(MSFT, "2024-06-30")].text == "new"
    # Q4 restated: as_of the restatement, the gap named, MSFT exit, NVDA cut
    nv4 = ev[(NVDA, "2024-12-31")]
    assert (
        nv4.text == "cut"
        and nv4.filed == "2025-03-01"
        and "no 13F stored for 2024-09-30" in nv4.line()
        and "restatement: replaces d-24q4 filed 2025-02-14" in nv4.line()
    )
    assert ev[(MSFT, "2024-12-31")].text == "exit" and ev[(GOOG, "2024-12-31")].text == "hold"
    # NEW HOLDINGS amendment: dated on its own day and flagged
    ap = ev[(AAPL, "2024-12-31")]
    assert ap.text == "new" and ap.filed == "2025-05-15" and "NEW HOLDINGS" in ap.line()
    # the original Q4's ACME row was dropped by the restatement: no ACME event
    assert not any(c == ACME for c, _ in ev)
    # options listed apart in Q1 (baseline: panel only)
    p = mg.panel(engine, NVDA, date(2025, 6, 1), path=world[2])
    q1 = next(r for r in p.rows if r.period == "2024-03-31")
    assert q1.text == "baseline" and any("CALL" in n for n in q1.notes)
    stored = {
        r["as_of"]: r
        for r in engine.execute(
            "SELECT * FROM signal WHERE cik = ? AND signal = ? AND timeframe = 'MY'",
            (NVDA, mg.SIGNAL),
        )
    }
    assert set(stored) == {"2024-08-14", "2025-03-01"}  # the original's day row is not kept


def test_same_day_managers_aggregate_mixed():
    e1 = mg.Event(
        "A", "1", AAPL, "2024-06-30", "2024-08-14", "a", "2024-03-31", text="cut", delta=-10
    )
    e2 = mg.Event(
        "B", "2", AAPL, "2024-06-30", "2024-08-14", "b", "2024-03-31", text="add", delta=4
    )
    assert mg.day_reading([e1, e2]) == (-6, "mixed", None)
    e3 = mg.Event(
        "C",
        "3",
        AAPL,
        "2024-06-30",
        "2024-08-14",
        "c",
        "2024-03-31",
        missing="row held by a check (x)",
    )
    assert mg.day_reading([e1, e3]) == (-10, "cut", None)
    assert mg.day_reading([e3]) == (None, None, "C: row held by a check (x)")


def test_held_row_gives_missing_never_a_direction(world, make_client):
    engine, _, _ = world
    sync_brk(engine, make_client)
    engine.execute("UPDATE fin_holding SET status = 'held', check_note = 'value vs close' WHERE "
                   "period = '2024-06-30'")  # fmt: skip
    mg.signal_pass(engine, [mg.Manager("Berkshire Hathaway Inc", BRK)], OURS)
    row = engine.execute("SELECT * FROM signal WHERE cik = ? AND as_of = '2024-08-14' AND "
                         "timeframe = 'MY'", (AAPL,)).fetchone()  # fmt: skip
    assert row["value"] is None and row["value_text"] is None
    assert row["method"].startswith("missing: Berkshire Hathaway Inc: row held by a check")


def test_manager_holding_none_of_ours(world, make_client):
    engine, _, _ = world
    sync_brk(engine, make_client)
    sp = mg.signal_pass(engine, [mg.Manager("Berkshire Hathaway Inc", BRK)], {NVDA: "NVDA"})
    assert sp.events == {} and sp.written == 0
    p = mg.panel(engine, NVDA, date(2024, 10, 1), path=world[2])
    assert p.rows == [] and p.managers[0].status.startswith("3 quarter(s) stored")
    assert (
        "no 13F stored for 2023-" not in p.managers[0].status
        or "missing quarters" in p.managers[0].status
    )


def test_quarter_gaps_and_due():
    assert mg.quarter_ends_between("2024-06-30", "2024-12-31") == ["2024-09-30"]
    assert mg.quarter_ends_between("2024-09-30", "2024-12-31") == []
    assert mg.next_due(date(2024, 10, 1)) == ("2024-06-30", "2024-08-14")
    assert mg.next_due(date(2024, 11, 14)) == ("2024-09-30", "2024-11-14")


def test_refresh_marks_due_reads_only_new_filings(world, make_client):
    engine, _, cfg = world
    sync_brk(engine, make_client)
    new = IndexEntry(BRK, "BERKSHIRE HATHAWAY INC", "13F-HR", "2024-11-14", "0000950123-24-012345")
    seen = IndexEntry(BRK, "BERKSHIRE HATHAWAY INC", "13F-HR", "2024-08-14", REF_Q2)
    other = IndexEntry("0000000999", "SOMEONE", "13F-HR", "2024-11-14", "0000000999-24-000001")
    assert mg.mark_due(engine, [seen, other]) == 0  # read already / not followed
    # nothing due: 0 requests
    t0 = FakeTransport({})
    lines = mg.run_sec_part(make_client(t0), engine, OURS, NOW, path=cfg)
    assert t0.calls == [] and "0 due" in lines[0]
    assert any("Duquesne Family Office LLC (CIK not resolved" in x or "not synced yet" in x
               for x in lines)  # fmt: skip
    assert mg.mark_due(engine, [new]) == 1
    listing = BRK_LIST + [("0000950123-24-012345", "13F-HR", "2024-11-14")]
    folder = filing_folder(BRK, "0000950123-24-012345")
    q3 = fixture_bytes("m07/13f/brk_2024q2_infotable.xml")
    t = FakeTransport({
        SUBMISSIONS_URL.format(cik=BRK): [submissions(BRK, listing)],
        f"{folder}/0000950123-24-012345-index.htm": [ok(fixture_bytes(
            "m07/13f/brk_2024q2_index.htm").replace(b"000095012324008740", b"000095012324012345"))],
        f"{folder}/primary_doc.xml": [ok(fixture_bytes("m07/13f/brk_2024q2_primary_doc.xml")
                                         .replace(b"06-30-2024", b"09-30-2024"))],
        f"{folder}/34725.xml": [ok(q3)],
    })  # fmt: skip
    later = datetime(2024, 11, 15, 12, 0, tzinfo=UTC)
    lines = mg.run_sec_part(make_client(t), engine, OURS, later, path=cfg)
    assert len(t.calls) == 4  # 1 submissions + index, cover, table
    assert "0000950123-24-012345 filed 2024-11-14: 1 kept, 5 not ours" in lines[0]
    assert engine.execute("SELECT count(*) FROM refresh_state WHERE name LIKE ?",
                          (mg.DUE_STATE + "%",)).fetchone()[0] == 0  # fmt: skip
    first = mg.run_local_part(engine, OURS, later, path=cfg)
    assert "signal rows written" in first[0]
    assert "unchanged" in mg.run_local_part(engine, OURS, later, path=cfg)[0]
    hold = engine.execute("SELECT value_text FROM signal WHERE cik = ? AND as_of = '2024-11-14' "
                          "AND timeframe = 'MY'", (AAPL,)).fetchone()  # fmt: skip
    assert hold[0] == "hold"


def test_m02_filer_manager_is_left_to_m02(world, make_client):
    engine, _, _ = world
    s = mg.sync_manager(make_client(FakeTransport({})), engine, mg.Manager("NVIDIA", NVDA), OURS,
                        {}, issuers.Names(engine), NOW)  # fmt: skip
    assert s.status == "M02 filer" and not mg.is_followed(engine, NVDA)


def test_managers_run_dry_run_no_sec_and_sec(world, make_client, tmp_path):
    engine, _, cfg = world
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import run_ownership

    out: list[str] = []

    def log(*xs):
        out.extend(xs)

    res = run_ownership.managers_run(engine, OURS, NOW, log, dry_run=True, path=cfg)
    assert res["planned"] > 0 and any("would send about" in x for x in out)
    assert engine.execute("SELECT count(*) FROM fin_13f").fetchone()[0] == 0
    out.clear()
    t = FakeTransport({SUBMISSIONS_URL.format(cik=BRK): [submissions(BRK, BRK_LIST)],
                       SUBMISSIONS_URL.format(cik=DUQ): [submissions(DUQ, [], "Duquesne Family "
                                                                   "Office LLC")]}
                      | brk_routes(OLD, REF_Q1, REF_Q2))  # fmt: skip
    res = run_ownership.managers_run(engine, OURS, NOW, log, client=make_client(t), path=cfg)
    assert res["syncs"]["Berkshire Hathaway Inc"].status == "synced"
    text = "\n".join(out)
    assert "largest rows not stored" in text and "BANK AMER CORP" in text
    assert "found: Berkshire Hathaway Inc: cut -389,368,450 sh" in text
    assert "Duquesne Family Office LLC: CIK 0009999901 (stored name)" in text
    out.clear()
    res = run_ownership.managers_run(engine, OURS, NOW, log, path=cfg)  # --no-sec
    assert any("skipped (--no-sec)" in x for x in out) and res["pass"].written > 0
    assert run_ownership.fetch_type_13f(SUBMISSIONS_URL.format(cik=BRK)) == "submissions"


def test_insiders_tab_shows_followed_managers_panel(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from engine.store.db import open_db
    from engine.ui.app import create_app
    from engine.ui.settings import UiSettings

    data = tmp_path / "data"
    engine = open_db("engine", data)
    engine.execute("INSERT INTO entity (cik, name, source_ref, fetched_at) VALUES (?, 'Apple "
                   "Inc.', 't', 'n')", (AAPL,))  # fmt: skip
    engine.execute("INSERT INTO ticker (ticker, cik, name, valid_from, source) VALUES ('AAPL', ?, "
                   "'Apple Inc.', '2020-01-01', 't')", (AAPL,))  # fmt: skip
    for acc, period, filed, sh in (
        (REF_Q1, "2024-03-31", "2024-05-15", 789_368_450),
        (REF_Q2, "2024-06-30", "2024-08-14", 400_000_000),
    ):
        engine.execute("INSERT INTO fin_13f (accession, filer_cik, form, period, filed, scale, "
                       "status, read_at) VALUES (?, ?, '13F-HR', ?, ?, 1, 'read', 'n')",
                       (acc, BRK, period, filed))  # fmt: skip
        engine.execute("INSERT INTO fin_holding (source, accession, filer_cik, filer_name, "
                       "issuer_cik, issuer_name, cusip, title, shares, share_type, value_usd, "
                       "period, filed, status, discovered_at) VALUES ('13F', ?, ?, 'Berkshire', ?, "
                       "'APPLE INC', '037833100', 'COM', ?, 'SH', 1, ?, ?, 'automatic', 'n')",
                       (acc, BRK, AAPL, sh, period, filed))  # fmt: skip
    engine.close()
    open_db("corpus", data).close()
    cfg = tmp_path / "m07_managers.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    monkeypatch.setattr(mg, "CONFIG", cfg)
    monkeypatch.setattr(mg.panel, "__kwdefaults__", {"path": cfg, "per_manager": 8})
    watch = tmp_path / "watchlist.toml"
    watch.write_text('[watchlist]\ntickers = ["AAPL"]\n', encoding="utf-8")
    app = create_app(UiSettings(data_dir=data, watchlist=watch))
    with TestClient(app) as c:
        html = c.get("/c/AAPL?tab=insiders").text
        assert "Followed managers (lagged)" in html and "filed up to 45 days" in html
        assert "Berkshire Hathaway Inc" in html and "-389,368,450 sh vs 2024-03-31" in html
        assert "baseline" in html and "Duquesne Family Office LLC" in html
        assert "object at 0x" not in html
