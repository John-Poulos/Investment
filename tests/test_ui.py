# ruff: noqa: E501  (fixture rows)
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from engine.sec.sections import resplit
from engine.store.db import open_db
from engine.ui.app import create_app, fmt_number
from engine.ui.settings import UiSettings
from engine.ui.viewer import OWNER, current_viewer

CIK = "0001326801"
REL = "Meta Reports Third Quarter 2025 Results\nCFO Outlook Commentary\nWe expect fourth quarter 2025 total revenue to be in the range of $56-59 billion.\n"


@pytest.fixture
def client(tmp_path: Path, clock):
    data = tmp_path / "data"
    engine = open_db("engine", data)
    corpus = open_db("corpus", data)
    engine.execute(
        "INSERT INTO entity (cik, name, sic, sic_description, fiscal_year_end, source_ref, fetched_at) "
        "VALUES (?, 'Meta Platforms, Inc.', '7370', 'Services-Computer Programming', '1231', 't', 'n')",
        (CIK,),
    )
    engine.execute(
        "INSERT INTO ticker (ticker, cik, valid_from, source) VALUES ('META', ?, '2020-01-01', 't')",
        (CIK,),
    )
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, items, ingested_at) VALUES ('0001628280-25-047114', ?, '8-K', '2025-10-29', '2.02,9.01', 'n')",
        (CIK,),
    )
    engine.execute(
        "INSERT INTO event (accession, item, cik, form, filed, category, severity, title, modules, amended, catalog) "
        "VALUES ('0001628280-25-047114', '2.02', ?, '8-K', '2025-10-29', 'earnings', 'medium', 'Results of operations', '[]', 0, 'c1')",
        (CIK,),
    )
    engine.execute(
        "INSERT INTO series (cik, concept, period_end, period_type, period_start, unit, first_value, first_accession, first_filed, "
        "latest_value, latest_accession, latest_filed, method, parser_version) "
        "VALUES (?, 'revenue', '2025-09-30', 'Q', '2025-07-01', 'USD', 51242000000, 'a1', '2025-10-30', 51242000000, 'a1', '2025-10-30', 'reported', 'p')",
        (CIK,),
    )
    doc_id = corpus.execute(
        "INSERT INTO document (accession, cik, filename, doc_type, url, text, sha256, fetched_at) "
        "VALUES ('0001628280-25-047114', ?, 'ex991.htm', 'EX-99.1', 'https://www.sec.gov/x/ex991.htm', ?, 'sha1', 'n')",
        (CIK, REL),
    ).lastrowid
    resplit(corpus, doc_id, clock.now())
    engine.close()
    corpus.close()
    watch = tmp_path / "watchlist.toml"
    watch.write_text('[watchlist]\ntickers = ["META", "ZZZZ"]\n', encoding="utf-8")
    app = create_app(UiSettings(data_dir=data, watchlist=watch))
    with TestClient(app) as c:
        yield c


def test_home_redirects_to_first_resolved_company(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/c/META"


def test_company_page_layout_and_side_panel(client):
    r = client.get("/c/meta")
    assert r.status_code == 200
    html = r.text
    assert "Meta Platforms, Inc." in html
    assert "ZZZZ — not resolved" in html  # unresolved tickers stay visible, never dropped
    assert "ER 2025-10-29" in html  # earnings marker from stored events
    assert "waits for Tiingo prices" in html
    assert "Results of operations" in html


def test_tabs_render_from_stored_data(client):
    fin = client.get("/c/META?tab=financials").text
    assert "51.24B" in fin and "2025-09-30" in fin
    assert "No Form 4 transactions stored." in client.get("/c/META?tab=insiders").text
    assert "build step 3" in client.get("/c/META?tab=guidance").text


def test_search_tab_and_phrase_fallback(client):
    r = client.get("/c/META?tab=search&q=revenue")
    assert "ex991.htm" in r.text or "EX-99.1" in r.text
    r = client.get("/c/META?tab=search&q=56-59")  # not valid FTS5 syntax → exact phrase
    assert "Searched as an exact phrase." in r.text


def test_source_viewer_highlights_and_detects_changed_text(client):
    start = REL.index("We expect")
    end = REL.index("billion.") + len("billion.")
    r = client.get(f"/source/0001628280-25-047114/ex991.htm?start={start}&end={end}&sha=sha1")
    assert "<mark>We expect fourth quarter 2025 total revenue" in r.text
    assert "text changed" not in r.text
    r = client.get(f"/source/0001628280-25-047114/ex991.htm?start={start}&end={end}&sha=other")
    assert "The stored text changed since this was cited" in r.text
    assert client.get("/source/none/x.htm").status_code == 404


def test_unknown_ticker_is_404(client):
    assert client.get("/c/NOPE").status_code == 404


def test_viewer_is_owner_on_this_pc():
    assert current_viewer(None) is OWNER and OWNER.is_owner


def test_missing_values_are_dashes_not_zero():
    assert fmt_number(None) == "—"
    assert fmt_number(0) == "0"
    assert fmt_number(51242000000) == "51.24B"
    assert fmt_number(-2.16, "per_share") == "-2.16"
    assert fmt_number(1234567, "shares_exact") == "1,234,567"
