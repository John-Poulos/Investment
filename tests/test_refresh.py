from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from engine.refresh import (
    Config,
    business_days,
    days_to_read,
    format_report,
    index_url,
    last_success,
    load_config,
    parse_master_index,
    run_refresh,
)
from engine.sec.documents import filing_folder
from engine.sec.identity import EXCHANGE_URL, SUBMISSIONS_URL, TICKERS_URL
from engine.sec.submissions import PAGE_URL
from engine.sec.xbrl_facts import FACTS_URL
from tests.conftest import FakeTransport, fixture_bytes, ok

ROOT = Path(__file__).resolve().parent.parent
CIK = "0000000042"
EIGHT_K = "0000000042-26-000004"
FORM4 = "0001234567-26-000001"

MASTER = (
    "Description:           Daily Index of EDGAR Dissemination Feed by Company Name\n"
    "Last Data Received:    Oct 6, 2026\n"
    "\n"
    "CIK|Company Name|Form Type|Date Filed|Filename\n"
    "--------------------------------------------------------------------------------\n"
    f"42|Example Semis Inc.|8-K|20261006|edgar/data/42/{EIGHT_K}.txt\n"
    f"42|Example Semis Inc.|4|20261006|edgar/data/42/{FORM4}.txt\n"
    "1234567|Doe Jane|4|20261006|edgar/data/1234567/0001234567-26-000001.txt\n"
    "999|Other Co|10-Q|20261006|edgar/data/999/0000000999-26-000001.txt\n"
)


def test_parse_master_index():
    entries = parse_master_index(MASTER)
    assert len(entries) == 4
    e = entries[0]
    assert (e.cik, e.form, e.filed, e.accession) == (CIK, "8-K", "2026-10-06", EIGHT_K)
    with pytest.raises(ValueError):
        parse_master_index("no header here")


def test_index_url_and_business_days():
    assert index_url(date(2026, 10, 6)).endswith("/daily-index/2026/QTR4/master.20261006.idx")
    assert index_url(date(2026, 3, 31)).endswith("/2026/QTR1/master.20260331.idx")
    days = business_days(date(2026, 10, 2), date(2026, 10, 6))  # Fri .. Tue
    assert days == [date(2026, 10, 2), date(2026, 10, 5), date(2026, 10, 6)]


def test_days_to_read_catches_up_and_rechecks(dbs):
    engine, _ = dbs
    wednesday = date(2026, 10, 7)
    assert days_to_read(engine, wednesday, 1) == [date(2026, 10, 6)]  # first run: yesterday
    engine.execute(
        "INSERT INTO refresh_day (day, status, processed_at) VALUES "
        "('2026-10-01', 'processed', 'x'), ('2026-09-30', 'pending', 'x')"
    )
    # PC off Fri–Tue: read Fri, Mon, Tue; recheck Thu; retry the pending Wed before.
    assert days_to_read(engine, wednesday, 1) == [
        date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5),
        date(2026, 10, 6),
    ]  # fmt: skip


def test_load_config_reads_owner_watchlist():
    config = load_config(ROOT / "config" / "watchlist.toml")
    assert config.tickers[0] == "AAPL" and len(config.tickers) == 16
    assert {"SPCX", "ETV", "INFQ", "GOOG"} <= set(config.tickers)
    assert config.form4_years == 3 and "8-K" in config.document_forms


def routes(day_index=None, today_index=None):
    exchange = json.dumps(
        {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[42, "Example Semis Inc.", "XSEM", "Nasdaq"]],
        }
    ).encode()
    folder = filing_folder(CIK, EIGHT_K)
    f4_folder = filing_folder(CIK, FORM4)
    r = {
        EXCHANGE_URL: [ok(exchange)],
        TICKERS_URL: [ok(b"{}")],
        SUBMISSIONS_URL.format(cik=CIK): [ok(fixture_bytes("sec/submissions_CIK0000000042.json"))],
        PAGE_URL.format(name="CIK0000000042-submissions-001.json"): [
            ok(fixture_bytes("sec/CIK0000000042-submissions-001.json"))
        ],
        FACTS_URL.format(cik=CIK): [ok(b"", 404)],
        f"{f4_folder}/form4.xml": [ok(fixture_bytes("sec/form4/new_10b51_checkbox.xml"))],
        f"{folder}/{EIGHT_K}-index.htm": [ok(fixture_bytes(f"sec/filing/{EIGHT_K}-index.htm"))],
        f"{folder}/xsem-8k_20260730.htm": [ok(fixture_bytes("sec/filing/xsem-8k_20260730.htm"))],
        f"{folder}/ex99-1.htm": [ok(fixture_bytes("sec/filing/ex99-1.htm"))],
        index_url(date(2026, 10, 6)): [day_index or ok(MASTER.encode())],
    }  # fmt: skip
    if today_index is not None:
        r[index_url(date(2026, 10, 7))] = [today_index]
    return r


CONFIG = Config(tickers=("XSEM", "NOPE"), earnings_8k=0, latest_annual=False,
                latest_quarterly=False)  # fmt: skip


def test_first_run_backfills_and_processes_new_filings(make_client, dbs, clock):
    engine, corpus = dbs
    report = run_refresh(make_client(FakeTransport(routes())), engine, corpus, CONFIG,
                         clock.now(), trigger="scheduled")  # fmt: skip
    assert report.status == "ok", format_report(report)
    assert report.days == {"2026-10-06": "processed"}
    assert "NOPE" in report.unresolved
    [c] = report.companies
    assert (c.ticker, c.cik, c.backfilled, c.failures) == ("XSEM", CIK, True, [])
    assert c.new_filings == [f"8-K {EIGHT_K}", f"4 {FORM4}"]
    assert any("2.02 medium" in e for e in c.notable_events)
    assert c.insider_rows == 1 and len(c.insider_trades) == 1 and " S 10,000 @ 201.55" in (
        c.insider_trades[0])  # fmt: skip
    assert c.facts.startswith("no XBRL company facts")
    assert c.documents == 2  # 8-K + EX-99.1
    text = format_report(report)
    assert "first run: backfilled" in text and "unresolved tickers" in text
    row = engine.execute("SELECT status, companies FROM refresh_run").fetchone()
    assert tuple(row) == ("ok", 1) and last_success(engine) is not None


def test_next_night_skips_quiet_companies_and_keeps_unpublished_day_pending(
    make_client, dbs, clock
):
    engine, corpus = dbs
    run_refresh(make_client(FakeTransport(routes())), engine, corpus, CONFIG, clock.now())
    clock.advance(86400)  # Thursday 2026-10-08
    quiet = MASTER.split("-----\n")[0] + "-" * 80 + "\n"  # index with no rows
    transport = FakeTransport(routes(day_index=ok(quiet.encode()), today_index=ok(b"", 404)))
    report = run_refresh(make_client(transport), engine, corpus, CONFIG, clock.now())
    assert report.days == {"2026-10-06": "processed", "2026-10-07": "pending"}
    assert report.companies == []  # already backfilled and nothing new filed
    assert report.status == "partial"  # a day is still pending; retried next run


def test_old_missing_index_is_a_holiday(make_client, dbs, clock):
    engine, corpus = dbs
    engine.execute(
        "INSERT INTO refresh_day (day, status, processed_at) VALUES ('2026-09-30', 'pending', 'x')"
    )
    r = routes()
    r[index_url(date(2026, 9, 30))] = [ok(b"", 404)]
    report = run_refresh(make_client(FakeTransport(r)), engine, corpus,
                         replace(CONFIG, tickers=("NOPE",)), clock.now())  # fmt: skip
    assert report.days["2026-09-30"] == "no_index"


def test_throttle_stops_run_and_marks_nothing(make_client, dbs, clock):
    engine, corpus = dbs
    transport = FakeTransport(routes(day_index=ok(b"", 429)))
    report = run_refresh(make_client(transport), engine, corpus, CONFIG, clock.now())
    assert report.status == "partial" and "throttle" in report.error
    assert engine.execute("SELECT count(*) FROM refresh_day").fetchone()[0] == 0
    assert last_success(engine) is None  # a stopped run does not count as done


def test_market_date_is_eastern_not_utc():
    from datetime import UTC, datetime

    from engine.refresh import market_date

    # 21:32 in New York on Oct 7 is already Oct 8 in UTC (the first live run).
    assert market_date(datetime(2026, 10, 8, 1, 32, tzinfo=UTC)) == date(2026, 10, 7)


def test_evening_run_reads_yesterday_eastern_and_403_index_is_pending(make_client, dbs, clock):
    engine, corpus = dbs
    from datetime import UTC, datetime

    evening = datetime(2026, 10, 8, 1, 32, tzinfo=UTC)  # Oct 7, 21:32 ET
    r = routes()
    report = run_refresh(make_client(FakeTransport(r)), engine, corpus,
                         replace(CONFIG, tickers=("NOPE",)), evening)  # fmt: skip
    assert report.days == {"2026-10-06": "processed"}  # not the unfinished Oct 7

    r[index_url(date(2026, 10, 7))] = [ok(b"<Error><Code>AccessDenied</Code></Error>", 403)]
    later = datetime(2026, 10, 8, 14, 0, tzinfo=UTC)  # Oct 8 morning ET: Oct 7 now due
    report = run_refresh(make_client(FakeTransport(r)), engine, corpus,
                         replace(CONFIG, tickers=("NOPE",)), later)  # fmt: skip
    assert report.days["2026-10-07"] == "pending" and report.error is None


def test_one_company_error_does_not_stop_the_run(make_client, dbs, clock, monkeypatch):
    engine, corpus = dbs
    import engine.refresh as refresh_mod

    def boom(*args, **kwargs):
        raise RuntimeError("simulated bug")

    monkeypatch.setattr(refresh_mod, "sync_facts", boom)
    report = run_refresh(make_client(FakeTransport(routes())), engine, corpus, CONFIG,
                         clock.now())  # fmt: skip
    [c] = report.companies
    assert any("internal error: RuntimeError: simulated bug" in f for f in c.failures)
    assert report.status == "partial" and report.error is None
    assert report.days == {"2026-10-06": "processed"}  # the run still finished its days
    assert not engine.execute(
        "SELECT 1 FROM refresh_state WHERE name = 'backfill:0000000042'"
    ).fetchone()  # backfill retried next run
