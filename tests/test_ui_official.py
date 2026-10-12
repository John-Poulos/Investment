# ruff: noqa: E501  (fixture text)
"""Official-feed screens (M02 part 7b): theme page sections and the Money flow tab's
federal awards. Synthetic rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from engine.official.arxiv import months_due
from engine.store.db import open_db
from tests.test_ui import CIK, client  # noqa: F401  (fixture)

T = datetime.now(UTC).isoformat(timespec="seconds")
TODAY = datetime.now(UTC).date()


def seed(e) -> None:
    """A theme linked to META, arXiv counts, a Federal Register notice, two bills and three
    awards (two mapped, one unmapped) — also usable for a scratch visual check."""
    e.execute("INSERT INTO theme (key, name, source, status, discovered_at, updated_at) VALUES "
              "('quantum', 'Quantum computing', 'seed', 'active', ?, ?)", (T, T))  # fmt: skip
    tid = e.execute("SELECT theme_id FROM theme WHERE key = 'quantum'").fetchone()[0]
    for p in ('"quantum computing"', '"qubit"'):
        e.execute("INSERT INTO theme_phrase (theme_id, phrase, source, status, discovered_at, updated_at) "
                  "VALUES (?, ?, 'seed', 'active', ?, ?)", (tid, p, T, T))  # fmt: skip
    e.execute("INSERT INTO theme_company (theme_id, ticker, source, status, discovered_at, updated_at) "
              "VALUES (?, 'META', 'seed', 'active', ?, ?)", (tid, T, T))  # fmt: skip
    months = months_due(TODAY, 24)
    for i, m in enumerate(months):  # 24 months of "quantum computing", 1 of "qubit"
        e.execute(
            "INSERT INTO arxiv_count VALUES ('quantum computing', ?, ?, 'q', ?)", (m, 100 + i, T)
        )
    e.execute("INSERT INTO arxiv_count VALUES ('qubit', ?, 0, 'q', ?)", (months[0], T))
    pub = (TODAY - timedelta(days=10)).isoformat()
    e.execute("INSERT INTO fedreg_doc VALUES ('2026-20023', 'Notice', 'Request for Information on Post-Quantum Migration', "
              "'Commerce Department', ?, 'https://www.federalregister.gov/d/2026-20023', 'The agency asks about quantum computing risks.', ?, ?)",
              (pub, T, T))  # fmt: skip
    e.execute(
        "INSERT INTO official_theme VALUES ('fedreg', '2026-20023', ?, 'quantum computing', ?, 1)",
        (tid, T),
    )
    e.execute("INSERT INTO congress_bill VALUES ('119-hr-1234', 119, 'HR', '1234', 'National Quantum Computing Workforce Act', NULL, "
              "'2026-09-20', 'Referred to committee.', 'introduced', 'https://www.congress.gov/bill/119th-congress/house-bill/1234', '2026-09-21', ?, ?, NULL)",
              (T, T))  # fmt: skip
    e.execute("INSERT INTO congress_bill VALUES ('119-s-900', 119, 'S', '900', 'Quantum Sandbox Act', 'Creates a qubit testbed.', "
              "'2026-08-01', 'Became Public Law No: 119-55.', 'enacted', NULL, '2026-08-02', ?, ?, ?)", (T, T, T))  # fmt: skip
    for ref, ph in (("119-hr-1234", "quantum computing"), ("119-s-900", "qubit")):
        e.execute(
            "INSERT INTO official_theme VALUES ('congress', ?, ?, ?, ?, NULL)", (ref, tid, ph, T)
        )
    base = (TODAY - timedelta(days=40)).isoformat()
    e.executemany(
        "INSERT INTO usa_award (award_key, award_id, award_group, award_type, recipient_name, recipient_uei, "
        "recipient_id, amount, base_date, start_date, last_modified, agency, sub_agency, description, "
        "searched_cik, search_term, first_seen_at, updated_at) VALUES (?, ?, 'contracts', 'DEFINITIVE CONTRACT', ?, ?, ?, ?, ?, ?, "
        "'2026-07-13 12:49:03', 'Department of Defense', 'Defense Advanced Research Projects Agency', ?, ?, 'META PLATFORMS', ?, ?)",
        [
            ("CONT_AWD_A1", "HR001126C0001", "META PLATFORMS, INC.", "U1", "r1-C", 12_500_000.0, base, base, "AI RESEARCH", CIK, T, T),
            ("CONT_AWD_A2", "HR001126C0002", "META PLATFORMS TECHNOLOGIES, LLC", "U2", "r2-C", None, base, base, "VR TRAINING", CIK, T, T),
            ("CONT_AWD_A3", "W91CRB26C0003", "METAPLATFORMS ENGINEERING CORP", "U3", "r3-R", 45_000.0, base, base, None, CIK, T, T),
        ],
    )  # fmt: skip
    e.executemany(
        "INSERT INTO usa_recipient (recipient_id, name, uei, level, parent_name, parent_uei, cik, how, profile_at, checked_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("r1-C", "META PLATFORMS, INC.", "U1", None, None, None, CIK, "name", None, T),
            ("r2-C", "META PLATFORMS TECHNOLOGIES, LLC", "U2", "C", "META PLATFORMS, INC.", "U1", CIK, "parent", T, T),
            ("r3-R", "METAPLATFORMS ENGINEERING CORP", "U3", "R", None, None, None, "none", T, T),
        ],
    )  # fmt: skip
    e.execute("INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, 'u', ?, '3 award(s) since 2025-10-12, terms META PLATFORMS')",
              (f"official:usaspending:{CIK}", T))  # fmt: skip


@pytest.fixture
def official(client):  # noqa: F811
    e = open_db("engine", client.app.state.settings.data_dir)
    seed(e)
    e.close()
    return client


def test_theme_page_official_sections(official):
    r = official.get("/themes/quantum")
    assert r.status_code == 200
    html = r.text
    assert "Research momentum: new arXiv preprints per month" in html
    assert "not money flow" in html
    months = months_due(TODAY, 24)
    last12 = sum(100 + i for i in range(12))
    prior12 = sum(100 + i for i in range(12, 24))
    assert f'<td class="num">{last12}</td><td class="num">{prior12}</td>' in html
    # qubit: one month counted (0), the rest missing (—), sums missing
    assert f'<th class="num">{months[0][2:]}</th>' in html
    assert (
        "Request for Information on Post-Quantum Migration" in html
        and "Commerce Department" in html
    )
    assert "National Quantum Computing Workforce Act" in html and ">introduced<" in html
    assert '<span class="warn">enacted</span>' in html
    assert "Federal awards to linked companies" in html and "$12.5M" in html
    assert "obligations" in html and "90-day delay" in html
    assert "object at 0x" not in html and "built-in method" not in html


def test_money_tab_federal_awards(official):
    html = official.get("/c/META?tab=money").text
    assert "Federal awards (USAspending)" in html
    assert "HR001126C0001" in html and "via parent META PLATFORMS, INC." in html
    assert "obligated in new awards, last 365 days: <b>$12.5M</b>" in html
    assert "Found by the search, not mapped to this company" in html
    assert "METAPLATFORMS ENGINEERING CORP" in html and "none stated" in html
    assert "https://www.usaspending.gov/award/CONT_AWD_A1" in html
    assert "object at 0x" not in html and "built-in method" not in html


def test_money_tab_not_searched_is_unknown_not_none(client):  # noqa: F811
    html = client.get("/c/META?tab=money").text
    assert "Not searched yet — unknown, not" in html
    html = client.get("/themes").text  # the themes list still renders
    assert "object at 0x" not in html


def test_body_only_matches_collapsed_and_weekly_item_section(official):
    from engine.news import digest

    e = open_db("engine", official.app.state.settings.data_dir)
    tid = e.execute("SELECT theme_id FROM theme WHERE key = 'quantum'").fetchone()[0]
    week = digest.last_week_start(datetime.now(UTC))
    seen = (week + timedelta(days=2)).isoformat(timespec="seconds")
    pub = (week + timedelta(days=1)).date().isoformat()
    for num, typ, title, prom in (
        ("2026-30001", "Notice", "Self-Regulatory Organizations; Nasdaq Fee Schedule", 0),
        ("2026-30002", "Rule", "Quantum Computing Export Controls", 1),
    ):
        e.execute("INSERT INTO fedreg_doc VALUES (?, ?, ?, 'SEC', ?, NULL, NULL, ?, ?)",
                  (num, typ, title, pub, seen, seen))  # fmt: skip
        e.execute("INSERT INTO official_theme VALUES ('fedreg', ?, ?, 'quantum computing', ?, ?)",
                  (num, tid, seen, prom))  # fmt: skip
    assert digest.propose_week(e, week, {CIK: "META"}, datetime.now(UTC)) == "queued"
    item = e.execute("SELECT item_id FROM review_queue WHERE kind = 'm02_news'").fetchone()[0]
    e.close()
    html = official.get("/themes/quantum").text
    assert "Phrase in the title or abstract: 2" in html
    assert "1 passing mention(s) in the body only" in html
    assert html.index("Quantum Computing Export Controls") < html.index("Nasdaq Fee Schedule")
    page = official.get(f"/review/{item}").text
    assert "Final rules and new laws on accepted themes" in page
    assert "Quantum Computing Export Controls" in page and "Nasdaq Fee Schedule" not in page
    assert "object at 0x" not in page
