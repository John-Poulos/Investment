# ruff: noqa: E501  (fixture text)
"""M02 part 7b: official feeds — arXiv, USAspending, Federal Register, Congress.gov
(D-M02-13, -15, -58, -60).

Every reply here is synthetic, in each API's documented shape; no live calls.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from engine.news.fetch import Fetcher
from engine.official import arxiv, congress, fedreg, usaspending
from engine.official.common import Budget, active_phrases
from engine.official.step import run_official_step
from engine.themes.seeds import sync_seeds

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
BA, NVDA = "0000012927", "0001045810"
COMPANIES = {"BA": BA, "NVDA": NVDA}
SEEDS = """
[[theme]]
key = "quantum"
name = "Quantum computing"
phrases = ["quantum computing", "qubit"]

[[theme]]
key = "space"
name = "Space economy"
phrases = ["launch vehicle"]
"""


class Transport:
    """GET routes by (url, a distinguishing param) or url; POST routes by (url, term, group)."""

    def __init__(self, routes=None, posts=None):
        self.routes, self.posts = routes or {}, posts or {}
        self.calls, self.post_calls = [], []

    def __call__(self, url, params, headers):
        self.calls.append((url, dict(params), dict(headers)))
        for k in (params.get("search_query"), params.get("conditions[term]"),
                  params.get("offset")):  # fmt: skip
            if k is not None and (url, k) in self.routes:
                return self._pick(self.routes[(url, k)])
        if url in self.routes:
            return self._pick(self.routes[url])
        raise AssertionError(f"unexpected request {url} {params}")

    def post(self, url, body, headers):
        self.post_calls.append((url, body, dict(headers)))
        f = body["filters"]
        group = "contracts" if f["award_type_codes"][0] == "A" else "grants"
        key = (url, f["recipient_search_text"][0], group, body["page"])
        r = self.posts.get(key) or self.posts.get((url, f["recipient_search_text"][0], group))
        if r is None:
            return 200, json.dumps(USA_EMPTY).encode(), {}
        return self._pick(r)

    @staticmethod
    def _pick(r):
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        if isinstance(r, Exception):
            raise r
        return r


def make_fetcher(engine, routes=None, posts=None, secrets=()):
    t = Transport(routes, posts)
    f = Fetcher(engine, transport=t, post_transport=t.post, now=lambda: NOW,
                clock=lambda: 0.0, sleep=lambda s: None, intervals={}, secrets=secrets)  # fmt: skip
    return f, t


def budget(seconds=1000.0):
    return Budget(seconds, clock=lambda: 0.0)


@pytest.fixture
def db(dbs, tmp_path: Path):
    engine, corpus = dbs
    p = tmp_path / "themes.toml"
    p.write_text(SEEDS, encoding="utf-8")
    sync_seeds(engine, p, NOW - timedelta(days=30))
    for t, c, name in (("BA", BA, "BOEING CO"), ("NVDA", NVDA, "NVIDIA CORP")):
        engine.execute("INSERT INTO ticker (ticker, cik, valid_from, source) VALUES (?, ?, '2020-01-01', 't')",
                       (t, c))  # fmt: skip
        engine.execute("INSERT INTO entity (cik, name, source_ref, fetched_at) VALUES (?, ?, 's', '2026-10-01')",
                       (c, name))  # fmt: skip
    return engine, corpus


# --- arXiv -----------------------------------------------------------------------------------


def atom(total: int) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <title type="html">ArXiv Query: search_query=all:"qubit"</title>
  <opensearch:totalResults>{total}</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
</feed>""".encode()


ARXIV_ERROR = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry><id>http://arxiv.org/api/errors#incorrect_id_format</id><title>Error</title>
  <summary>malformed query</summary></entry>
</feed>"""


def test_arxiv_months_query_and_parse():
    assert arxiv.months_due(date(2026, 10, 14), 3) == ["2026-09", "2026-08", "2026-07"]
    assert arxiv.months_due(date(2026, 10, 2), 1) == ["2026-08"]  # September not settled
    assert arxiv.months_due(date(2026, 1, 20), 2) == ["2025-12", "2025-11"]
    q = arxiv.query("quantum computing", "2026-02")
    assert q == 'all:"quantum computing" AND submittedDate:[202602010000 TO 202602282359]'
    assert arxiv.parse_total(atom(37)) == 37
    assert arxiv.parse_total(atom(0)) == 0
    assert arxiv.parse_total(ARXIV_ERROR).startswith("arXiv error: malformed")
    assert "totalResults" in arxiv.parse_total(b"<feed xmlns='http://www.w3.org/2005/Atom'/>")


def test_arxiv_run_counts_newest_first_cap_and_failure_left_missing(db):
    engine, _ = db
    q_sep = arxiv.query("qubit", "2026-09")
    routes = {
        (arxiv.URL, arxiv.query("quantum computing", "2026-09")): (200, atom(120), {}),
        (arxiv.URL, q_sep): (200, ARXIV_ERROR, {}),
        (arxiv.URL, arxiv.query("launch vehicle", "2026-09")): (200, atom(0), {}),
        (arxiv.URL, arxiv.query("quantum computing", "2026-08")): (429, b"Rate exceeded.", {}),
    }
    f, t = make_fetcher(engine, routes)
    r = arxiv.run(engine, f, active_phrases(engine), NOW, budget(), max_requests=10, back=2)
    assert r.counted == 2 and r.stopped == "throttled (HTTP 429)"
    assert any("qubit 2026-09" in x for x in r.failures)
    rows = {(x["phrase"], x["month"]): x["n"] for x in engine.execute("SELECT * FROM arxiv_count")}
    assert rows == {("quantum computing", "2026-09"): 120, ("launch vehicle", "2026-09"): 0}
    assert ("qubit", "2026-09") not in rows  # failed = missing, never zero
    assert t.calls[0][1]["max_results"] == "1"
    # a second run asks only for what is still missing, within the cap
    f2, t2 = make_fetcher(engine, {arxiv.URL: (200, atom(5), {})})
    r2 = arxiv.run(engine, f2, active_phrases(engine), NOW, budget(), max_requests=2, back=2)
    assert r2.counted == 2 and r2.stopped.startswith("request cap")
    asked = [c[1]["search_query"] for c in t2.calls]
    assert asked[0] == q_sep and arxiv.query("quantum computing", "2026-09") not in asked


def test_arxiv_respects_time_budget(db):
    engine, _ = db
    f, t = make_fetcher(engine, {arxiv.URL: (200, atom(1), {})})
    r = arxiv.run(engine, f, active_phrases(engine), NOW, budget(0), max_requests=10)
    assert r.counted == 0 and r.stopped == "time budget spent" and not t.calls


# --- Federal Register --------------------------------------------------------------------------

FR = {
    "description": "Documents matching '\"quantum computing\"'",
    "count": 2,
    "total_pages": 1,
    "results": [
        {
            "document_number": "2026-20023",
            "type": "Notice",
            "title": "Request for Information Regarding Post-Quantum Cryptography Migration",
            "abstract": "<p>The agency requests information on quantum computing risks.</p> "
            + "x" * 400,
            "html_url": "https://www.federalregister.gov/documents/2026/10/01/2026-20023/rfi",
            "publication_date": "2026-10-01",
            "agencies": [
                {"raw_name": "COMMERCE DEPARTMENT", "name": "Commerce Department", "id": 54},
                {
                    "raw_name": "NATIONAL INSTITUTE OF STANDARDS AND TECHNOLOGY",
                    "name": "National Institute of Standards and Technology",
                },
            ],
        },
        {
            "document_number": "2026-19999",
            "type": "Rule",
            "title": "Export Controls on Quantum Items",
            "abstract": None,
            "html_url": "https://www.federalregister.gov/d/2026-19999",
            "publication_date": "2026-09-28",
            "agencies": [{"name": "Industry and Security Bureau"}],
        },
    ],
}


def test_fedreg_parse_store_and_incremental(db):
    engine, _ = db
    docs, pages = fedreg.parse(json.dumps(FR).encode())
    assert pages == 1 and len(docs) == 2
    assert docs[0].agencies == "Commerce Department; National Institute of Standards and Technology"
    assert len(docs[0].abstract) <= 300 and "<p>" not in docs[0].abstract
    assert docs[1].abstract is None
    assert fedreg.parse(b'{"errors": {"conditions": "bad"}}').startswith("error")
    empty = json.dumps({"count": 0, "results": []}).encode()
    routes = {
        (fedreg.URL, '"quantum computing"'): (200, json.dumps(FR).encode(), {}),
        (fedreg.URL, '"qubit"'): (500, b"oops", {}),
        (fedreg.URL, '"launch vehicle"'): (200, empty, {}),
    }
    f, t = make_fetcher(engine, routes)
    r = fedreg.run(engine, f, active_phrases(engine), NOW, budget())
    assert (r.phrases, r.seen, r.new) == (2, 2, 2)
    assert r.failures == ["qubit: HTTP 500"]
    p = t.calls[0][1]
    assert p["conditions[type][]"] == ["RULE", "PRORULE", "NOTICE"]
    assert p["conditions[publication_date][gte]"] == "2025-10-14"  # first run: a year back
    themes = engine.execute(
        "SELECT o.ref, th.key FROM official_theme o JOIN theme th USING (theme_id)"
    ).fetchall()
    assert {(x[0], x[1]) for x in themes} == {("2026-20023", "quantum"), ("2026-19999", "quantum")}
    # same day: no repeat for done phrases; the failed phrase is retried
    f2, t2 = make_fetcher(engine, {fedreg.URL: (200, empty, {})})
    fedreg.run(engine, f2, active_phrases(engine), NOW, budget())
    assert [c[1]["conditions[term]"] for c in t2.calls] == ['"qubit"']
    # next day: from the last success minus the overlap
    f3, t3 = make_fetcher(engine, {fedreg.URL: (200, empty, {})})
    fedreg.run(engine, f3, active_phrases(engine), NOW + timedelta(days=1), budget())
    first = t3.calls[0][1]
    assert first["conditions[term]"] == '"quantum computing"'
    assert first["conditions[publication_date][gte]"] == "2026-10-11"


# --- Congress.gov ------------------------------------------------------------------------------

BILLS_P1 = {
    "bills": [
        {
            "congress": 119,
            "type": "HR",
            "number": "1234",
            "originChamber": "House",
            "title": "National Quantum Computing Workforce Act",
            "latestAction": {
                "actionDate": "2026-09-20",
                "text": "Referred to the Committee on Science, Space, and Technology.",
            },
            "updateDate": "2026-09-21",
            "url": "https://api.congress.gov/v3/bill/119/hr/1234?format=json",
        },
        {
            "congress": 119,
            "type": "S",
            "number": "77",
            "originChamber": "Senate",
            "title": "A bill to rename a post office",
            "latestAction": {"actionDate": "2026-09-01", "text": "Read twice."},
            "updateDate": "2026-09-02",
            "url": "https://api.congress.gov/v3/bill/119/s/77?format=json",
        },
    ],
    "pagination": {
        "count": 3,
        "next": "https://api.congress.gov/v3/bill/119?offset=250&limit=250&format=json",
    },
}
BILLS_P2 = {
    "bills": [
        {
            "congress": 119,
            "type": "S",
            "number": "900",
            "title": "Commercial Launch Vehicle Licensing Act",
            "latestAction": {"actionDate": "2026-08-01", "text": "Became Public Law No: 119-55."},
            "updateDate": "2026-08-02",
        },
    ],
    "pagination": {"count": 3},
}
SUMMARIES = {
    "summaries": [
        {
            "actionDate": "2026-07-01",
            "actionDesc": "Introduced in House",
            "bill": {
                "congress": 119,
                "type": "HR",
                "number": "555",
                "originChamber": "House",
                "title": "American Technology Leadership Act",
                "url": "https://api.congress.gov/v3/bill/119/hr/555?format=json",
            },
            "text": "<p>This bill establishes a grant program for <strong>qubit</strong> fabrication research.</p>",
            "updateDate": "2026-07-10",
            "versionCode": "00",
        },
        {
            "actionDate": "2026-07-02",
            "actionDesc": "Introduced in Senate",
            "bill": {"congress": 119, "type": "S", "number": "78", "title": "Farm bill"},
            "text": "<p>Agriculture.</p>",
            "updateDate": "2026-07-10",
            "versionCode": "00",
        },
    ],
    "pagination": {"count": 2},
}
DETAIL_555 = {"bill": {"congress": 119, "type": "HR", "number": "555",
                       "title": "American Technology Leadership Act",
                       "latestAction": {"actionDate": "2026-07-15", "text": "Referred to committee."},
                       "laws": []}}  # fmt: skip


def test_congress_helpers():
    assert congress.current_congress(date(2026, 10, 14)) == 119
    assert congress.current_congress(date(2027, 1, 5)) == 120
    assert congress.ordinal(119) == "119th" and congress.ordinal(121) == "121st"
    assert (
        congress.page_url(119, "HR", "1234")
        == "https://www.congress.gov/bill/119th-congress/house-bill/1234"
    )
    assert congress.status_of("Became Public Law No: 119-55.") == "enacted"
    assert congress.status_of("Passed Senate.") == "introduced"
    assert congress.status_of(None, [{"type": "Public Law", "number": "119-1"}]) == "enacted"


def test_congress_run_titles_summaries_and_key_handling(db):
    engine, _ = db
    base = congress.BASE
    routes = {
        (f"{base}/bill/119", "0"): (200, json.dumps(BILLS_P1).encode(), {}),
        (f"{base}/bill/119", "2"): (200, json.dumps(BILLS_P2).encode(), {}),
        (f"{base}/summaries/119", "0"): (200, json.dumps(SUMMARIES).encode(), {}),
        f"{base}/bill/119/hr/555": (200, json.dumps(DETAIL_555).encode(), {}),
    }
    f, t = make_fetcher(engine, routes, secrets=("CGKEY",))
    r = congress.run(engine, f, "CGKEY", active_phrases(engine), NOW, budget())
    assert not r.failures, r.failures
    bills = {b["bill_id"]: dict(b) for b in engine.execute("SELECT * FROM congress_bill")}
    assert set(bills) == {"119-hr-1234", "119-s-900", "119-hr-555"}  # post office / farm not stored
    assert bills["119-hr-1234"]["status"] == "introduced"
    assert bills["119-s-900"]["status"] == "enacted"
    assert bills["119-hr-555"]["latest_action"] == "Referred to committee."  # read from detail
    assert "qubit" in bills["119-hr-555"]["summary"] and "<p>" not in bills["119-hr-555"]["summary"]
    assert bills["119-hr-1234"]["url"].endswith("/119th-congress/house-bill/1234")
    links = {
        (x[0], x[1])
        for x in engine.execute("SELECT ref, phrase FROM official_theme WHERE source = 'congress'")
    }
    assert links == {("119-hr-1234", "quantum computing"), ("119-s-900", "launch vehicle"),
                     ("119-hr-555", "qubit")}  # fmt: skip
    # key in the header, never in params or the fetch log
    assert all(c[2].get("X-Api-Key") == "CGKEY" and "api_key" not in c[1] for c in t.calls)
    logged = " ".join(
        r[0] + (r[1] or "") for r in engine.execute("SELECT url, detail FROM fetch_log")
    )
    assert "CGKEY" not in logged
    # incremental listing next day: fromDateTime = last listing − 1 day; status change counted
    p2 = dict(BILLS_P1, bills=[dict(BILLS_P1["bills"][0], latestAction={
        "actionDate": "2026-10-14", "text": "Became Public Law No: 119-60."})], pagination={"count": 1})  # fmt: skip
    f2, t2 = make_fetcher(engine, {f"{base}/bill/119": (200, json.dumps(p2).encode(), {}),
                                   f"{base}/summaries/119": (200, json.dumps({"summaries": [], "pagination": {}}).encode(), {})})  # fmt: skip
    r2 = congress.run(
        engine, f2, "CGKEY", active_phrases(engine), NOW + timedelta(days=1), budget()
    )
    assert r2.enacted_new == 1
    assert t2.calls[0][1]["fromDateTime"] == "2026-10-13T00:00:00Z"


def test_congress_header_refused_falls_back_to_query_once(db):
    engine, _ = db
    base = congress.BASE
    empty_b = json.dumps({"bills": [], "pagination": {"count": 0}}).encode()
    empty_s = json.dumps({"summaries": [], "pagination": {"count": 0}}).encode()
    routes = {f"{base}/bill/119": [(403, b'{"error": {"code": "API_KEY_MISSING"}}', {}), (200, empty_b, {})],
              f"{base}/summaries/119": (200, empty_s, {})}  # fmt: skip
    f, t = make_fetcher(engine, routes, secrets=("CGKEY",))
    r = congress.run(engine, f, "CGKEY", active_phrases(engine), NOW, budget())
    assert not r.failures
    assert t.calls[1][1]["api_key"] == "CGKEY" and t.calls[2][1]["api_key"] == "CGKEY"
    logged = " ".join(
        r[0] + (r[1] or "") for r in engine.execute("SELECT url, detail FROM fetch_log")
    )
    assert "CGKEY" not in logged


def test_congress_without_key_is_skipped(db):
    engine, _ = db
    f, t = make_fetcher(engine)
    r = congress.run(engine, f, None, active_phrases(engine), NOW, budget())
    assert r.stopped.startswith("skipped") and not t.calls


def test_congress_budget_stop_resumes_at_offset(db):
    engine, _ = db
    base = congress.BASE
    f, _t = make_fetcher(
        engine, {(f"{base}/bill/119", "0"): (200, json.dumps(BILLS_P1).encode(), {})}
    )
    ticks = iter([0.0, 0.0, 0.0, 5000.0, 5000.0, 5000.0, 5000.0])
    b = Budget(100.0, clock=lambda: next(ticks, 5000.0))
    r = congress.run(engine, f, "K", active_phrases(engine), NOW, b)
    assert r.stopped.startswith("time budget spent")
    assert (
        engine.execute(
            "SELECT detail FROM refresh_state WHERE name = 'official:congress:bills:119:offset'"
        ).fetchone()[0]
        == "2"
    )
    f2, t2 = make_fetcher(engine, {(f"{base}/bill/119", "2"): (200, json.dumps(BILLS_P2).encode(), {}),
                                   f"{base}/summaries/119": (200, json.dumps({"summaries": []}).encode(), {})})  # fmt: skip
    congress.run(engine, f2, "K", active_phrases(engine), NOW, budget())
    assert t2.calls[0][1]["offset"] == "2" and "fromDateTime" not in t2.calls[0][1]
    assert (
        engine.execute("SELECT status FROM congress_bill WHERE bill_id = '119-s-900'").fetchone()[0]
        == "enacted"
    )


# --- USAspending -------------------------------------------------------------------------------

USA_EMPTY = {"spending_level": "awards", "limit": 100, "results": [],
             "page_metadata": {"page": 1, "hasNext": False}}  # fmt: skip


def award(
    aid, name, rid, amount, base="2026-03-02", uei="UEI1", agency="Department of Defense", **kw
):
    return {"internal_id": hash(aid) % 10**8, "Award ID": aid, "Recipient Name": name,
            "Recipient UEI": uei, "recipient_id": rid, "Award Amount": amount,
            "Base Obligation Date": base, "Start Date": base, "Last Modified Date": "2026-07-13 12:49:03",
            "Awarding Agency": agency, "Awarding Sub Agency": "Department of the Air Force",
            "Contract Award Type": "DEFINITIVE CONTRACT", "Description": "KC-46 TANKER SUSTAINMENT",
            "generated_internal_id": f"CONT_AWD_{aid}_9700_-NONE-_-NONE-"} | kw  # fmt: skip


USA_BA = {"spending_level": "awards", "limit": 100, "results": [
    award("FA1", "THE BOEING COMPANY", "r-ba-C", 1.5e9),
    award("FA2", "BOEING SERVICE COMPANY", "r-bsc-C", 2.0e6, uei="UEI2"),
    award("FA3", "BOEING PRECISION GEARS LLC", "r-bpg-R", 50000.0, uei="UEI3"),
    award("FA4", "THE BOEING COMPANY", "r-ba-C", None),
], "page_metadata": {"page": 1, "hasNext": False}}  # fmt: skip


def test_usaspending_norm_terms_and_parse():
    n = usaspending.norm
    assert n("THE BOEING COMPANY") == n("BOEING CO") == n("The Boeing Co.") == "BOEING"
    assert n("NVIDIA CORP") == n("NVIDIA Corporation") == "NVIDIA"
    assert n("Amazon Web Services, Inc.") == "AMAZON WEB SERVICES"
    assert n("BOEING SERVICE COMPANY") == "BOEING SERVICE"  # a subsidiary is not the parent
    co = usaspending.Company("AMZN", "0001018724", ("AMAZON COM INC", "Amazon.com, Inc.",
                             "Amazon Web Services", "Amazon", "AWS"))  # fmt: skip
    assert co.terms() == ["AMAZON"]  # covers the longer names; AWS too short
    g = usaspending.Company("GOOG", "0001652044", ("Alphabet Inc.", "Alphabet", "Google"))
    assert sorted(g.terms()) == ["ALPHABET", "GOOGLE"]
    awards, more = usaspending.parse(json.dumps(USA_BA).encode(), "contracts")
    assert len(awards) == 4 and not more
    assert awards[3].amount is None  # missing stays missing
    assert awards[0].award_type == "DEFINITIVE CONTRACT"
    err = b'{"message": "\'award_type_codes\' must only contain types from one group."}'
    assert usaspending.parse(err, "contracts").startswith("error: 'award_type_codes'")
    b = usaspending.body("BOEING", "grants", date(2025, 10, 14), date(2026, 10, 14), 1)
    assert b["filters"]["award_type_codes"] == ["02", "03", "04", "05"]
    assert b["filters"]["time_period"][0]["date_type"] == "new_awards_only"
    assert "Award Type" in b["fields"] and "Contract Award Type" not in b["fields"]


def test_usaspending_run_maps_by_name_and_parent_conservatively(db):
    engine, _ = db
    url = usaspending.SEARCH_URL
    posts = {(url, "BOEING", "contracts"): (200, json.dumps(USA_BA).encode(), {})}
    profiles = {
        usaspending.RECIPIENT_URL.format("r-bsc-C"): (200, json.dumps({
            "name": "BOEING SERVICE COMPANY", "uei": "UEI2", "recipient_id": "r-bsc-C",
            "recipient_level": "C", "parent_name": "THE BOEING COMPANY", "parent_uei": "UEI1",
            "parents": []}).encode(), {}),
        usaspending.RECIPIENT_URL.format("r-bpg-R"): (200, json.dumps({
            "name": "BOEING PRECISION GEARS LLC", "uei": "UEI3", "recipient_id": "r-bpg-R",
            "recipient_level": "R", "parent_name": None, "parent_uei": None}).encode(), {}),
    }  # fmt: skip
    f, t = make_fetcher(engine, profiles, posts)
    r = usaspending.run(engine, f, COMPANIES, NOW, budget())
    assert not r.failures, r.failures
    assert r.companies == 2 and r.new == 4 and r.profiles == 2 and r.by_parent == 1
    rec = {
        x["recipient_id"]: (x["cik"], x["how"])
        for x in engine.execute("SELECT * FROM usa_recipient")
    }
    assert rec == {"r-ba-C": (BA, "name"), "r-bsc-C": (BA, "parent"), "r-bpg-R": (None, "none")}
    terms = [(c[1]["filters"]["recipient_search_text"][0], c[1]["filters"]["award_type_codes"][0])
             for c in t.post_calls]  # fmt: skip
    assert terms == [("BOEING", "A"), ("BOEING", "02"), ("NVIDIA", "A"), ("NVIDIA", "02")]
    assert t.post_calls[0][1]["filters"]["time_period"][0]["start_date"] == "2025-10-14"
    # weekly: nothing due the next day; after 7 days, from the last success − 120 days
    f2, t2 = make_fetcher(engine, {}, {})
    usaspending.run(engine, f2, COMPANIES, NOW + timedelta(days=1), budget())
    assert not t2.post_calls
    f3, t3 = make_fetcher(engine, {}, {})
    usaspending.run(engine, f3, COMPANIES, NOW + timedelta(days=7), budget())
    assert t3.post_calls[0][1]["filters"]["time_period"][0]["start_date"] == "2026-06-16"
    assert engine.execute("SELECT count(*) FROM usa_award").fetchone()[0] == 4  # nothing lost


def test_usaspending_failure_is_not_marked_checked(db):
    engine, _ = db
    posts = {(usaspending.SEARCH_URL, "BOEING", "contracts"): (500, b"error", {})}
    f, _t = make_fetcher(engine, {}, posts)
    r = usaspending.run(engine, f, {"BA": BA}, NOW, budget())
    assert r.companies == 0 and r.failures == ["BA BOEING contracts: HTTP 500"]
    assert engine.execute("SELECT 1 FROM refresh_state WHERE name = ?",
                          (f"official:usaspending:{BA}",)).fetchone() is None  # fmt: skip


# --- the step ---------------------------------------------------------------------------------


def test_run_official_step_end_to_end_never_fails(db):
    engine, _ = db
    empty_fr = json.dumps({"count": 0, "results": []}).encode()
    routes = {
        fedreg.URL: (200, json.dumps(FR).encode(), {}),
        arxiv.URL: (200, atom(3), {}),
        f"{congress.BASE}/bill/119": (200, json.dumps(BILLS_P2).encode(), {}),
        f"{congress.BASE}/summaries/119": (200, json.dumps({"summaries": []}).encode(), {}),
    }
    posts = {
        (usaspending.SEARCH_URL, "BOEING", "contracts"): (200, json.dumps(USA_BA).encode(), {})
    }
    f, _t = make_fetcher(engine, routes, posts, secrets=("CGKEY",))
    rep = run_official_step(engine, COMPANIES, NOW, fetcher=f, congress_key="CGKEY",
                            arxiv_requests=4, clock=lambda: 0.0)  # fmt: skip
    text = "\n".join(rep.lines)
    assert "error" not in text, text
    assert "active theme phrases: 3" in text
    assert "Federal Register: 3 phrase(s) searched, 6 document(s) seen, 2 new" in text
    assert "Congress.gov: 1 bill/summary record(s) read, 1 phrase match(es), 1 new bill(s)" in text
    assert "USAspending: 2 compan(ies) searched, 4 award(s) seen, 4 new" in text
    assert "arXiv: 4 monthly count(s) stored" in text and "stopped: request cap 4" in text
    assert empty_fr  # (kept for readability)
    # an unexpected error inside the step is reported, never raised
    rep2 = run_official_step(engine, COMPANIES, NOW, fetcher=object(), congress_key=None)  # type: ignore[arg-type]
    assert any(line.startswith("error —") for line in rep2.lines)
