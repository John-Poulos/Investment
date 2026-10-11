# ruff: noqa: E501  (fixture text)
"""M02 part 5b: financing and equity links — 13F, 13D/13G, text passages, loops, credit."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from engine import review
from engine.financing import credit, issuers, links, scan, schedules, thirteenf
from engine.financing.find import find
from engine.financing.step import run_financing_step
from engine.sec.client import Response
from engine.sec.documents import filing_folder
from engine.store.db import open_db
from engine.supply import aliases
from engine.supply import links as supply_links
from tests.conftest import FakeTransport
from tests.test_ui import client  # noqa: F401  (fixture)

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
NVDA, INTC, CRWV, AMZN, FUND = "0001045810", "0000050863", "0001769628", "0001018724", "0000315066"
ALIASES = """
[NVDA]
ticker = "NVDA"
names = ["NVIDIA Corporation", "NVIDIA"]
customer = true
[INTC]
ticker = "INTC"
names = ["Intel Corporation", "Intel"]
[CRWV]
ticker = "CRWV"
names = ["CoreWeave, Inc.", "CoreWeave"]
[AMZN]
ticker = "AMZN"
names = ["Amazon.com, Inc.", "Amazon Web Services", "Amazon.com", "Amazon"]
[MRVL]
names = ["Marvell Technology", "Marvell"]
"""


@pytest.fixture
def matcher(dbs, tmp_path: Path):
    engine, _ = dbs
    for t, c, n in (
        ("NVDA", NVDA, "NVIDIA CORP"),
        ("INTC", INTC, "INTEL CORP"),
        ("CRWV", CRWV, "CoreWeave, Inc."),
        ("AMZN", AMZN, "AMAZON COM INC"),
    ):
        engine.execute(
            "INSERT INTO ticker (ticker, cik, name, valid_from, source) VALUES "
            "(?, ?, ?, '2020-01-01', 't')",
            (t, c, n),
        )
        engine.execute("INSERT INTO entity (cik, name, fiscal_year_end, source_ref, fetched_at) "
                       "VALUES (?, ?, '1231', 't', 'n')", (c, n))  # fmt: skip
    p = tmp_path / "aliases.toml"
    p.write_text(ALIASES, encoding="utf-8")
    return aliases.Matcher(aliases.load(engine, p))


def _co(matcher, key):
    return next(c for c in matcher.companies if c.key == key)


# --- text finders ---------------------------------------------------------------------------


def test_k1_share_sale_to_a_company_reads_who_invests(matcher):
    text = (
        "On September 15, 2025, we entered into an agreement to issue and sell 215 million shares of our common stock to NVIDIA at a price of $23.28 per share, representing an aggregate cash purchase price of $5.0 billion.\n"
        "NVIDIA also agreed to invest $5.0 billion in Intel common stock.\n"
    )
    found = find(text, matcher, {"INTC"})
    assert [(f.kind, f.b.key, f.direction) for f in found] == [("K1", "NVDA", "b_to_a")] * 2
    assert (
        found[1].amount == Decimal("5.0") * Decimal("1E9") and found[0].instrument == "common stock"
    )


def test_k1_own_investment_k3_backstop_k2_warrant(matcher):
    own = find(
        "In fiscal 2026 we invested $2.0 billion in Marvell preferred stock.\n", matcher, {"NVDA"}
    )
    assert [(f.kind, f.b.key, f.direction, f.instrument) for f in own] == [
        ("K1", "MRVL", "a_to_b", "preferred stock")
    ]
    cw = find(
        "In April 2025, NVIDIA agreed to purchase any unsold capacity under the agreement through 2032.\n",
        matcher,
        {"CRWV"},
    )
    assert [(f.kind, f.b.key, f.direction) for f in cw] == [("K3", "NVDA", "b_to_a")]
    w = find(
        "We issued a warrant to Amazon to purchase up to 7.9 million shares, vesting with Amazon's purchases.\n",
        matcher,
        set(),
    )
    assert [(f.kind, f.b.key, f.direction, f.instrument) for f in w] == [
        ("K2", "AMZN", "a_to_b", "warrants (7,900,000 shares)")
    ]


def test_competition_and_products_are_not_financing(matcher):
    text = (
        "We compete with Intel, which has invested in its own foundry shares.\n"
        "Our joint venture builds servers with NVIDIA DGX systems.\n"
    )
    assert find(text, matcher, set()) == []


# --- text links: propose, confirm with a kind change, flip, follow ---------------------------


def _store(engine, matcher, a_cik, a_name, text, acc, mine, form="10-K"):
    doc = supply_links.Doc(acc, "d.htm", form, "2026-02-01", text)
    return links.store(
        engine, a_cik, a_name, matcher.by_cik(a_cik), doc, find(text, matcher, mine), NOW
    )


def _item(engine, kind):
    return engine.execute("SELECT * FROM review_queue WHERE kind = ? ORDER BY item_id DESC",
                          (kind,)).fetchone()  # fmt: skip


def test_text_link_item_confirm_with_kind_change_and_followers(dbs, matcher):
    engine, _ = dbs
    _store(
        engine,
        matcher,
        INTC,
        "Intel Corporation",
        "We agreed to sell 215 million shares of our common stock to NVIDIA for $5.0 billion.\n",
        "i1",
        {"INTC"},
    )
    assert links.propose_pairs(engine, NOW) == {"queued": 1}
    it = review.get(engine, _item(engine, "m02_finlink")["item_id"])
    assert it.payload["claim"] == "NVIDIA CORP invests in INTEL CORP"  # SEC registry names
    assert it.payload["amount"] == "$5,000,000,000" and it.payload["kind"] == "K1"
    review.m02_action(engine, it.item_id, "confirm", "", "owner", NOW, target="K6")
    r = engine.execute("SELECT kind, status, direction FROM fin_text").fetchone()
    assert tuple(r) == ("K6", "confirmed", "b_to_a")
    # a later K6 passage of the same pair takes the decision; no new item
    _store(
        engine,
        matcher,
        INTC,
        "Intel Corporation",
        "Our equity method investments include a stake held in NVIDIA ventures.\n",
        "i2",
        {"INTC"},
    )
    assert links.follow_decisions(engine) == 1
    assert links.propose_pairs(engine, NOW) == {}
    assert {r[0] for r in engine.execute("SELECT status FROM fin_text")} == {"confirmed"}


def test_flip_and_reject(dbs, matcher):
    engine, _ = dbs
    _store(
        engine,
        matcher,
        CRWV,
        "CoreWeave, Inc.",
        "NVIDIA agreed to purchase any unsold capacity through 2032.\n",
        "c1",
        {"CRWV"},
    )
    links.propose_pairs(engine, NOW)
    review.m02_action(engine, _item(engine, "m02_finlink")["item_id"], "flip", "", "owner", NOW)
    assert engine.execute("SELECT direction FROM fin_text").fetchone()[0] == "a_to_b"
    _store(
        engine,
        matcher,
        CRWV,
        "CoreWeave, Inc.",
        "We compete with NVIDIA in cloud services; a joint venture with Intel builds servers.\n",
        "c2",
        {"CRWV"},
    )
    assert engine.execute("SELECT count(*) FROM fin_text").fetchone()[0] == 1  # competition skipped
    _store(
        engine,
        matcher,
        CRWV,
        "CoreWeave, Inc.",
        "Our joint venture with Intel builds servers.\n",
        "c3",
        {"CRWV"},
    )
    assert links.propose_pairs(engine, NOW) == {"queued": 1}
    review.m02_action(engine, _item(engine, "m02_finlink")["item_id"], "reject", "", "owner", NOW)
    assert (
        engine.execute("SELECT status FROM fin_text WHERE kind = 'K6'").fetchone()[0] == "rejected"
    )


# --- 13F --------------------------------------------------------------------------------------

COVER = b"""<edgarSubmission xmlns="http://www.sec.gov/edgar/thirteenffiler"><formData><coverPage>
<reportCalendarOrQuarter>{period}</reportCalendarOrQuarter><isAmendment>false</isAmendment></coverPage>
<summaryPage><tableEntryTotal>3</tableEntryTotal><tableValueTotal>{total}</tableValueTotal></summaryPage>
</formData><headerData><filerInfo><periodOfReport>{period}</periodOfReport></filerInfo></headerData></edgarSubmission>"""


def _table(rows):
    body = "".join(
        f"<infoTable><nameOfIssuer>{n}</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>{c}</cusip>"
        f"<value>{v}</value><shrsOrPrnAmt><sshPrnamt>{s}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType>"
        "</shrsOrPrnAmt><investmentDiscretion>SOLE</investmentDiscretion></infoTable>"
        for n, c, v, s in rows
    )
    return f'<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">{body}</informationTable>'.encode()


def _index(folder, docs):
    path = folder.removeprefix("https://www.sec.gov")
    rows = "".join(
        f'<tr><td>{i}</td><td></td><td><a href="{path}/{fn}">{fn}</a></td><td>{t}</td><td>1</td></tr>'
        for i, (fn, t) in enumerate(docs, 1)
    )
    head = ('<span class="companyName">NVIDIA CORP (Filed by) <acronym>CIK</acronym>: '
            f'<a href="x">{NVDA} (see all)</a></span>')  # fmt: skip
    return (head + '<table class="tableFile" summary="Document Format Files">'
            "<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>"
            f"{rows}</table>").encode()  # fmt: skip


def _filing(engine, acc, cik, form, filed):
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, ingested_at) VALUES (?, ?, ?, ?, 'n')",
        (acc, cik, form, filed),
    )
    engine.execute("INSERT INTO filing_cik (accession, cik) VALUES (?, ?)", (acc, cik))


def _13f_routes(acc, cover, table):
    folder = filing_folder(NVDA, acc)
    return {
        f"{folder}/{acc}-index.htm": [Response(200, _index(folder, [("primary_doc.xml", "13F-HR"),
                                                                    ("infotable.xml", "INFORMATION TABLE")]), {})],
        f"{folder}/primary_doc.xml": [Response(200, cover, {})],
        f"{folder}/infotable.xml": [Response(200, table, {})],
    }  # fmt: skip


def test_13f_rows_summed_resolved_and_unit_by_filing_date(dbs, matcher, make_client):
    engine, _ = dbs
    acc_old, acc_new = "0001045810-22-000001", "0001045810-26-000065"
    _filing(engine, acc_old, NVDA, "13F-HR", "2025-02-14")
    _filing(engine, acc_new, NVDA, "13F-HR", "2026-08-14")
    old_rows = [("INTEL CORP", "458140100", 1000, 100), ("ACME WIDGETS HLDGS", "000000AA1", 50, 10)]
    new_rows = [
        ("INTEL CORP", "458140100", 29989261126, 214776632),
        ("COREWEAVE INC", "21873S108", 2000000000, 23606676),
        ("COREWEAVE INC", "21873S108", 2699617158, 23606677),
    ]
    routes = _13f_routes(
        acc_old,
        COVER.replace(b"{period}", b"12-31-2024").replace(b"{total}", b"1050"),
        _table(old_rows),
    )
    routes |= _13f_routes(
        acc_new,
        COVER.replace(b"{period}", b"06-30-2026").replace(b"{total}", b"34688878284"),
        _table(new_rows),
    )
    rep = thirteenf.Report13F()
    thirteenf.run(make_client(FakeTransport(routes), cached=False), engine, [NVDA], NOW, rep)
    assert rep.read == 2 and rep.unresolved == 1
    rows = {(r["period"], r["issuer_name"]): r for r in engine.execute("SELECT * FROM fin_holding")}
    assert float(rows[("2024-12-31", "INTEL CORP")]["value_usd"]) == 1000  # filed 2025: dollars
    cw = rows[("2026-06-30", "COREWEAVE INC")]
    assert (
        float(cw["value_usd"]) == 4699617158 and float(cw["shares"]) == 47213353
    )  # summed by CUSIP
    assert cw["issuer_cik"] == CRWV and cw["resolved_how"] == "name" and cw["status"] == "automatic"
    intel = rows[("2026-06-30", "INTEL CORP")]
    assert intel["status"] == "held" and "10× the prior quarter" in intel["check_note"]
    assert thirteenf.scale_for("2022-11-15") == 1000


def test_issuer_names_and_owner_map(dbs, matcher):
    engine, _ = dbs
    names = issuers.Names(engine)
    assert issuers.norm("Nebius Group N.V.") == ("NEBIUS", "GROUP")
    assert issuers.resolve(engine, names, "458140100", "INTEL CORPORATION") == (INTC, "name")
    engine.execute(
        "INSERT INTO ticker (ticker, cik, name, valid_from, source) VALUES "
        "('SPCX', '0001181412', 'Space Exploration Technologies Corp', '2026-01-01', 't')"
    )
    names = issuers.Names(engine)
    assert (
        issuers.resolve(engine, names, "84615Q103", "SPACE EXPLORATION TECHN CORP")[0]
        == "0001181412"
    )
    assert issuers.resolve(engine, names, "000000AA1", "ACME WIDGETS HLDGS") == (None, "no match")
    issuers.owner_map(engine, "000000AA1", "NVDA", "owner", NOW)
    assert issuers.resolve(engine, names, "000000AA1", "anything") == (NVDA, "owner")
    with pytest.raises(ValueError, match="No current ticker"):
        issuers.owner_map(engine, "000000BB1", "ZZZZ", "owner", NOW)


def test_unresolved_issuer_item_maps_every_row(dbs, matcher):
    engine, _ = dbs
    from engine.financing.step import check_items, issuer_items

    engine.execute("INSERT INTO fin_13f (accession, filer_cik, form, period, filed, scale, status, "
                   "read_at) VALUES ('a1', ?, '13F-HR', '2026-06-30', '2026-08-14', 1, 'read', 'n')",
                   (NVDA,))  # fmt: skip
    engine.execute("INSERT INTO fin_holding (source, accession, filer_cik, filer_name, issuer_name, cusip, "
                   "shares, value_usd, period, filed, status, discovered_at) VALUES ('13F', 'a1', ?, "
                   "'NVIDIA CORP', 'ACME WIDGETS HLDGS', '000000AA1', 10, 5000, '2026-06-30', "
                   "'2026-08-14', 'unresolved', 'n')", (NVDA,))  # fmt: skip
    assert issuer_items(engine, NOW) == 1 and check_items(engine, NOW) == 0
    it = review.get(engine, _item(engine, "m02_13f_issuer")["item_id"])
    with pytest.raises(review.ReviewError, match="Enter the ticker"):
        review.m02_action(engine, it.item_id, "map", "", "owner", NOW)
    review.m02_action(engine, it.item_id, "map", "", "owner", NOW, target="INTC")
    r = engine.execute("SELECT issuer_cik, status, resolved_how FROM fin_holding").fetchone()
    assert tuple(r) == (INTC, "automatic", "owner")


def test_wrong_record_is_kept_out_and_undo_restores(dbs, matcher):
    engine, _ = dbs
    engine.execute("INSERT INTO fin_holding (source, accession, filer_cik, filer_name, issuer_cik, issuer_name, "
                   "cusip, shares, value_usd, period, filed, status, discovered_at) VALUES ('13F', 'a1', ?, "
                   "'NVIDIA CORP', ?, 'INTEL CORP', '458140100', 10, 5000, '2026-06-30', '2026-08-14', "
                   "'automatic', 'n')", (NVDA, INTC))  # fmt: skip
    hid = engine.execute("SELECT holding_id FROM fin_holding").fetchone()[0]
    links.wrong_holding(engine, hid, "owner", NOW)
    assert engine.execute("SELECT status FROM fin_holding").fetchone()[0] == "wrong"
    assert thirteenf.suppressed(engine, f"13F:{NVDA}:458140")
    links.undo_wrong(engine, f"13F:{NVDA}:458140")
    assert engine.execute("SELECT status FROM fin_holding").fetchone()[0] == "automatic"


# --- 13D/13G ----------------------------------------------------------------------------------

SCHED = b"""<edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13g"><formData><coverPageHeader>
<eventDateRequiresFilingThisStatement>06/30/2026</eventDateRequiresFilingThisStatement>
<issuerInfo><issuerCik>0002088896</issuerCik><issuerName>X-Energy, Inc.</issuerName>
<issuerCusipNumber>98386P102</issuerCusipNumber></issuerInfo></coverPageHeader>
<coverPageHeaderReportingPersonDetails><reportingPersonName>Amazon.com, Inc.</reportingPersonName>
<reportingPersonBeneficiallyOwnedAggregateNumberOfShares>65836948.00</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
<classPercent>22.9</classPercent></coverPageHeaderReportingPersonDetails></formData></edgarSubmission>"""


def _sched_index(folder, filer, filer_cik, subject, subject_cik):
    path = folder.removeprefix("https://www.sec.gov")
    return (
        f'<span class="companyName">{subject} (Subject) <acronym>CIK</acronym>: <a href="x">{subject_cik} (see all)</a></span>'
        f'<span class="companyName">{filer} (Filed by) <acronym>CIK</acronym>: <a href="y">{filer_cik} (see all)</a></span>'
        '<table class="tableFile" summary="Document Format Files">'
        "<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>"
        f'<tr><td>1</td><td></td><td><a href="{path}/primary_doc.xml">primary_doc.xml</a></td><td>SCHEDULE 13G</td><td>1</td></tr>'
        "</table>"
    ).encode()


def test_schedules_read_header_once_and_xml_when_ours(dbs, matcher, make_client):
    engine, _ = dbs
    mine, fund = "0001104659-26-092071", "0000315066-26-002069"
    _filing(engine, mine, AMZN, "SCHEDULE 13G", "2026-08-06")
    _filing(engine, fund, AMZN, "SCHEDULE 13G/A", "2026-08-06")
    f1, f2 = filing_folder(AMZN, mine), filing_folder(AMZN, fund)
    t = FakeTransport({
        f"{f1}/{mine}-index.htm": [Response(200, _sched_index(f1, "AMAZON COM INC", AMZN, "X-Energy, Inc.", "0002088896"), {})],
        f"{f1}/primary_doc.xml": [Response(200, SCHED, {})],
        f"{f2}/{fund}-index.htm": [Response(200, _sched_index(f2, "FMR LLC", FUND, "AMAZON COM INC", AMZN), {})],
    })  # fmt: skip
    rep = schedules.ReportSchedules()
    schedules.run(make_client(t, cached=False), engine, {AMZN}, {AMZN, NVDA}, NOW, rep)
    assert (rep.headers, rep.relevant, rep.stakes) == (2, 1, 1)
    h = engine.execute("SELECT * FROM fin_holding").fetchone()
    assert (
        h["source"],
        h["filer_cik"],
        h["issuer_cik"],
        float(h["pct_class"]),
        h["period"],
        h["status"],
    ) == ("13G", AMZN, "0002088896", 22.9, "2026-06-30", "automatic")
    assert issuers.mapped(engine, "98386P102")["cik"] == "0002088896"  # teaches the 13F map
    n = len(t.calls)
    schedules.run(
        make_client(t, cached=False), engine, {AMZN}, {AMZN}, NOW, schedules.ReportSchedules()
    )
    assert len(t.calls) == n  # headers read once


# --- loops ------------------------------------------------------------------------------------


def _holding(engine, filer, issuer, value=4.7e9):
    engine.execute("INSERT INTO fin_holding (source, accession, filer_cik, filer_name, issuer_cik, issuer_name, "
                   "cusip, shares, value_usd, period, filed, status, discovered_at) VALUES ('13F', ?, ?, 'F', ?, "
                   "'I', ?, 1, ?, '2026-06-30', '2026-08-14', 'automatic', 'n')",
                   (f"a{issuer}", filer, issuer, issuer[-6:], value))  # fmt: skip


def _supply(engine, supplier, customer):
    engine.execute("INSERT INTO supply_link (rung, grade, a_cik, a_name, b_cik, b_name, direction, accession, "
                   "filename, quote, quote_start, quote_end, how, a_side, b_side, pair_key, status, "
                   "discovered_at) VALUES ('L2', 'A', ?, 'S', ?, 'C', 'a_to_b', ?, 'x', 'q', 0, 1, 'h', ?, ?, "
                   "?, 'confirmed', 'n')",
                   (supplier, customer, f"s{supplier}{customer}", supplier, customer, f"{customer}|{supplier}"))  # fmt: skip


def test_loop_flag_needs_a_confirmed_supply_link_and_alerts_once(dbs, matcher):
    engine, _ = dbs
    from engine.financing.step import loop_alerts

    _holding(engine, NVDA, CRWV)
    assert links.loops(engine) == []
    _supply(engine, NVDA, CRWV)  # NVIDIA supplies CoreWeave and holds its shares → case 1
    _holding(engine, AMZN, INTC)
    _supply(
        engine, INTC, AMZN
    )  # Intel supplies Amazon, Amazon holds Intel → customer funds supplier
    lps = {(lp.edge.financer, lp.case) for lp in links.loops(engine)}
    assert lps == {(NVDA, 1), (AMZN, 5)}
    assert loop_alerts(engine, NOW) == 1 and loop_alerts(engine, NOW) == 0


# --- credit series ----------------------------------------------------------------------------


def _series(engine, cik, concept, ptype, end, value, start=None):
    engine.execute("INSERT INTO series (cik, concept, period_end, period_type, period_start, unit, first_value, "
                   "first_accession, first_filed, latest_value, latest_accession, latest_filed, method, "
                   "parser_version) VALUES (?, ?, ?, ?, ?, 'USD', ?, 'a', ?, ?, 'a', ?, 'reported', 'p')",
                   (cik, concept, end, ptype, start, value, end, value, end))  # fmt: skip


def _fact(engine, cik, tag, end, value):
    engine.execute(
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_end, value, accession, form, filed) "
        "VALUES (?, 'us-gaap', ?, 'USD', ?, ?, ?, '10-Q', ?)",
        (cik, tag, end, value, f"a{end}", end),
    )


QS = [
    ("2025-09-30", "2025-07-01"),
    ("2025-12-31", "2025-10-01"),
    ("2026-03-31", "2026-01-01"),
    ("2026-06-30", "2026-04-01"),
]


def test_dso_allowance_guarantees_and_book(dbs):
    engine, _ = dbs
    for (end, start), ar, allow, guar in zip(
        QS,
        (40e9, 40e9, 46e9, 52e9),
        (1.0e9, 1.1e9, 1.3e9, 1.6e9),
        (10e9, 20e9, 30e9, 40e9),
        strict=True,
    ):
        _series(engine, NVDA, "revenue", "Q", end, 92e9, start)
        _series(engine, NVDA, "revenue", "TTM", end, 368e9)
        _series(engine, NVDA, "receivables", "I", end, ar)
        _series(engine, NVDA, "total_assets", "I", end, 400e9)
        _fact(engine, NVDA, "AllowanceForDoubtfulAccountsReceivableCurrent", end, allow)
        _fact(engine, NVDA, "GuaranteeObligationsMaximumExposure", end, guar)
        _fact(engine, NVDA, "EquitySecuritiesFvNi", end, 40e9)
    _fact(engine, NVDA, "EquityMethodInvestments", "2026-06-30", 10e9)
    s = {x.key: x for x in credit.company_series(engine, NVDA)}
    assert round(s["dso"].latest.value) == 51
    assert s["dso"].alert is None  # no year-earlier quarters yet (D-M02-47)
    assert s["allowance"].alert and round(s["allowance"].latest.value, 4) == round(1.6 / 53.6, 4)
    assert s["guarantees"].alert and s["fin_receivables"].obs == []
    assert (
        s["equity_book"].latest.value == pytest.approx(0.125)
        and "equity-method $10.0B" in s["equity_book"].latest.parts
    )
    assert credit.queue_alerts(engine, {"NVDA": NVDA}, NOW) == 2  # allowance, guarantees
    assert credit.queue_alerts(engine, {"NVDA": NVDA}, NOW) == 0


def _dso_company(engine, cik, receivables):
    """Eight quarters (Jul 2024 – Jun 2026), revenue flat at $10B; DSO = AR ÷ 10B × days."""
    ends = [
        ("2024-09-30", "2024-07-01"),
        ("2024-12-31", "2024-10-01"),
        ("2025-03-31", "2025-01-01"),
        ("2025-06-30", "2025-04-01"),
        *QS,
    ]
    for (end, start), ar in zip(ends, receivables, strict=True):
        _series(engine, cik, "revenue", "Q", end, 10e9, start)
        _series(engine, cik, "receivables", "I", end, ar)


def test_dso_compares_with_the_same_quarter_a_year_earlier(dbs):
    engine, _ = dbs
    # Microsoft-like: receivables peak every June (annual billing), same level each year
    _dso_company(engine, NVDA, (4e9, 5e9, 4.5e9, 8e9, 4e9, 5e9, 4.6e9, 8.2e9))
    d = credit.dso(engine, NVDA)
    assert d.alert is None and credit.band(d.latest.change) == "normal"
    # a real deterioration: above the year-earlier quarter twice, the latest by 30%
    _dso_company(engine, INTC, (4e9, 4e9, 4e9, 4e9, 4e9, 4e9, 4.4e9, 5.2e9))
    d = credit.dso(engine, INTC)
    assert d.latest.change == pytest.approx(0.30, abs=0.01)
    assert "+10%, then +30% (elevated)" in d.alert
    assert credit.band(0.5) == "at the revenue-overstater mean (Beneish)"


def test_tag_dropped_years_ago_shows_not_tagged_since(dbs):
    engine, _ = dbs
    _series(engine, NVDA, "receivables", "I", "2018-01-28", 1e9)
    _fact(engine, NVDA, "AllowanceForDoubtfulAccountsReceivableCurrent", "2018-01-28", 13e6)
    a = credit.allowance(engine, NVDA)
    assert a.last_tagged == "2018-01-28" and a.stale(NOW.date())


# --- step, search, UI -------------------------------------------------------------------------


def test_search_names_and_phrases(matcher):
    assert scan.search_names(_co(matcher, "AMZN")) == ["Amazon", "Amazon.com", "Amazon.com, Inc."]
    assert "warrant to NVIDIA" in scan.phrases(_co(matcher, "NVDA"))


def test_step_without_sec_reads_stored_documents_once(dbs, matcher, tmp_path):
    engine, corpus = dbs
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, ingested_at) VALUES ('i1', ?, '10-K', '2026-01-30', 'n')",
        (INTC,),
    )
    corpus.execute(
        "INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, fetched_at) VALUES "
        "('i1', ?, 'i.htm', '10-K', 'u1', ?, 'h', 'n')",
        (
            INTC,
            "We agreed to issue and sell shares of our common stock to NVIDIA for $5.0 billion.\n",
        ),
    )
    ap = tmp_path / "aliases.toml"
    lines = run_financing_step(None, engine, corpus, {"INTC": INTC}, NOW, alias_path=ap)
    assert any("text: 1 document(s) read, 1 new passage(s)" in ln for ln in lines), lines
    lines = run_financing_step(None, engine, corpus, {"INTC": INTC}, NOW, alias_path=ap)
    assert any("text: 0 document(s) read" in ln for ln in lines)
    lines = run_financing_step(
        None, engine, corpus, {"INTC": INTC}, NOW, alias_path=ap, rescan=True
    )
    assert any("re-read: 0 passage(s)" in ln for ln in lines)


def test_money_tab_sections_and_wrong_button(client, tmp_path):  # noqa: F811
    from tests.test_ui import CIK

    engine = open_db("engine", client.app.state.settings.data_dir)
    engine.execute(
        "INSERT INTO fin_13f (accession, filer_cik, form, period, filed, scale, status, read_at) "
        "VALUES ('q1', ?, '13F-HR', '2026-06-30', '2026-08-14', 1, 'read', 'n')",
        (CIK,),
    )
    engine.execute(
        "INSERT INTO fin_holding (source, accession, filer_cik, filer_name, issuer_cik, issuer_name, "
        "cusip, title, shares, share_type, value_usd, period, filed, status, discovered_at) VALUES "
        "('13F', 'q1', ?, 'Meta Platforms, Inc.', ?, 'INTEL CORP', '458140100', 'COM', 1000, 'SH', "
        "25000, '2026-06-30', '2026-08-14', 'automatic', 'n')",
        (CIK, INTC),
    )
    engine.close()
    tab = client.get("/c/META?tab=money").text
    assert "Financing and equity links" in tab and "INTEL CORP" in tab and "wrong?" in tab
    assert "Days sales in receivables" in tab and "Credit quality and investment book" in tab
    hid = (
        open_db("engine", client.app.state.settings.data_dir)
        .execute("SELECT holding_id FROM fin_holding")
        .fetchone()[0]
    )
    r = client.post(
        f"/fin/holding/{hid}/wrong", data={"back": "/c/META?tab=money"}, follow_redirects=False
    )
    assert r.status_code == 303
    assert "wrong?" not in client.get("/c/META?tab=money").text
    runs = client.get("/runs").text
    assert "Financing records marked wrong" in runs and "INTEL CORP" in runs


# --- live check 1 (2026-10-11, D-M02-47) -----------------------------------------------------


def test_live_check_1_wording(matcher):
    marvell = find(
        "On March 31, 2026, the Company completed the issuance and sale of 2.0 million shares "
        "of Series A Convertible Preferred Stock, par value $0.002 per share, to NVIDIA "
        "Corporation, for an aggregate purchase price of $2.0 billion.\n",
        matcher,
        {"MRVL"},
    )
    assert [(f.kind, f.direction, f.amount) for f in marvell] == [
        ("K1", "b_to_a", Decimal("2.0E9"))
    ]
    held = find(
        "(2) Includes $14.1 billion of Intel shares subject to long-term restrictions.\n",
        matcher,
        {"NVDA"},
    )
    assert [(f.b.key, f.direction) for f in held] == [("INTC", "a_to_b")]
    ex = find(
        "The Warrant may be exercised by Amazon at a price per share of $9.42 before 2027.\n",
        matcher,
        set(),
    )
    assert [(f.kind, f.direction, f.amount) for f in ex] == [("K2", "a_to_b", None)]
    own = find("We hold warrants to purchase shares of Intel Corporation.\n", matcher, {"NVDA"})
    assert [(f.kind, f.direction) for f in own] == [("K2", "b_to_a")]


def test_live_check_1_issuer_names_and_exits(dbs, matcher):
    engine, _ = dbs
    for t, c, n in (
        ("CRWD", "0001535527", "CrowdStrike Holdings, Inc."),
        ("RXRX", "0001601830", "Recursion Pharmaceuticals, Inc."),
        ("ARM", "0001973239", "Arm Holdings plc /UK"),
    ):
        engine.execute("INSERT INTO ticker (ticker, cik, name, valid_from, source) VALUES "
                       "(?, ?, ?, '2020-01-01', 't')", (t, c, n))  # fmt: skip
    names = issuers.Names(engine)
    assert issuers.resolve(engine, names, "22788C105", "CROWDSTRIKE HLDGS INC")[0] == "0001535527"
    assert (
        issuers.resolve(engine, names, "75629V104", "RECURSION PHARMACEUTICALS IN")[0]
        == "0001601830"
    )
    assert issuers.resolve(engine, names, "042068205", "ARM HOLDINGS PLC")[0] == "0001973239"
    assert issuers.norm("AIR TRANSPORT SERVICES GRP I") == ("AIR", "TRANSPORT", "SERVICES", "GROUP")
    # a row resolved by name lends its CIK to the same CUSIP under another name
    _holding(engine, INTC, "0001910139")
    engine.execute("UPDATE fin_holding SET cusip = '60741F104'")
    assert issuers.resolve(engine, names, "60741F104", "Mobileye, Inc.") == (
        "0001910139",
        "same CUSIP",
    )
    # a 0% schedule is an exit: no investment edge
    engine.execute("INSERT INTO fin_holding (source, accession, filer_cik, filer_name, issuer_cik, issuer_name, "
                   "cusip, shares, pct_class, period, filed, status, discovered_at) VALUES ('13G', 'g1', ?, "
                   "'AMAZON', '0000894081', 'ATSG', '00922R105', 0, 0, '2025-04-11', '2025-04-11', "
                   "'automatic', 'n')", (AMZN,))  # fmt: skip
    assert all(e.other != "0000894081" for e in links.financing_edges(engine))
