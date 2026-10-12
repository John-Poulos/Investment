from __future__ import annotations

import sqlite3

import pytest

from engine.store import db
from engine.store.db import connect, current_version, migrate, migrations, open_db


@pytest.mark.parametrize("name", db.DATABASES)
def test_migrate_empty_db_to_latest(tmp_path, name):
    conn = open_db(name, tmp_path)
    latest = len(migrations(name))
    assert current_version(conn) == latest
    assert migrate(conn, name) == latest  # idempotent
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    conn.close()


def test_failed_migration_rolls_back(tmp_path, monkeypatch):
    good = migrations("engine")
    bad = (len(good) + 1, "broken", "CREATE TABLE half_done (x INTEGER);\nNOT VALID SQL;\n")
    conn = open_db("engine", tmp_path)
    monkeypatch.setattr(db, "migrations", lambda name: [*good, bad])
    with pytest.raises(sqlite3.OperationalError):
        migrate(conn, "engine")
    assert current_version(conn) == len(good)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "half_done" not in tables


def test_signal_record_constraints(tmp_path):
    conn = open_db("engine", tmp_path)
    cols = ("cik, ticker, module_id, signal, timeframe, as_of, value, value_text, "
            "evidence_grade, source_ref, method")  # fmt: skip
    sql = f"INSERT INTO signal ({cols}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    row = ("0000000042", "XYZ", "M07", "opportunistic_buy", "MY", "2026-09-12", 1, None, "A",
           "Form 4 x", "filter")  # fmt: skip
    conn.execute(sql, row)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, (*row[:4], "XX", *row[5:]))  # bad timeframe
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, (*row[:5], "2026-09-13", 1, None, "D", *row[9:]))  # bad grade
    with pytest.raises(sqlite3.IntegrityError):  # text never in value (D-M04-9)
        conn.execute(sql, (*row[:5], "2026-09-14", "CYCLICAL_TROUGH", None, *row[8:]))
    with pytest.raises(sqlite3.IntegrityError):  # empty row must say why it is missing
        conn.execute(sql, (*row[:5], "2026-09-15", None, None, None, None, "filter"))
    conn.execute(sql, (*row[:5], "2026-09-15", None, None, None, None, "missing: not filed"))


def test_migration_0029_moves_signal_rows_to_cik(tmp_path, monkeypatch):
    conn = connect(tmp_path / "engine.db")
    all_engine = migrations("engine")
    monkeypatch.setattr(db, "migrations", lambda name: all_engine[:28])
    migrate(conn, "engine")
    conn.execute("INSERT INTO ticker (ticker, cik, valid_from, valid_to, source) VALUES "
                 "('BBBY', '0000886158', '2000-01-01', '2023-09-29', 't'), "
                 "('BBBY', '0001130713', '2025-08-25', NULL, 't')")  # fmt: skip
    conn.execute("INSERT INTO signal VALUES ('BBBY', 'M04', 'cvd_state', 'MY', '2022-05-01', "
                 "'STRUCTURAL_DECLINE', 'A', '10-K x', 'grid')")  # fmt: skip
    conn.execute(
        "INSERT INTO signal VALUES ('ZZZ', 'M04', 'x', 'MY', '2022-05-01', 2, 'A', 'r', 'm')"
    )
    monkeypatch.setattr(db, "migrations", lambda name: all_engine)
    migrate(conn, "engine")
    rows = {r["ticker"]: r for r in conn.execute("SELECT * FROM signal")}
    old = rows["BBBY"]
    assert old["cik"] == "0000886158"  # the ticker's holder on as_of, not today's
    assert old["value"] is None and old["value_text"] == "STRUCTURAL_DECLINE"
    assert rows["ZZZ"]["cik"] == "0000000000" and rows["ZZZ"]["method"].startswith("cik unresolved")
    assert conn.execute("SELECT count(*) FROM entity_link").fetchone()[0] == 3


def test_fact_key_treats_instants_as_one_key(tmp_path):
    conn = open_db("engine", tmp_path)
    sql = (
        "INSERT INTO fact (cik, taxonomy, tag, unit, period_start, period_end, value, accession,"
        " filed) VALUES ('0000320193', 'us-gaap', 'Cash', 'USD', NULL, '2025-09-27', 1, 'a', 'f')"
    )
    conn.execute(sql)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql)


def test_fts5_domain_terms(tmp_path):
    conn = connect(":memory:")
    migrate(conn, "corpus")
    body = (
        "Sales under a Rule 10b5-1 trading plan. We began volume shipments of HBM3E "
        "to a major customer and expect capacity constraints to persist."
    )
    conn.execute(
        "INSERT INTO section_fts (rowid, label, body) VALUES (1, '10-K Item 7', ?)", (body,)
    )

    def hits(query: str) -> int:
        return conn.execute(
            "SELECT count(*) FROM section_fts WHERE section_fts MATCH ?", (query,)
        ).fetchone()[0]

    assert hits('"10b5-1"') == 1
    assert hits("HBM3E") == 1
    assert hits('"hbm3e"') == 1
    assert hits("constraint") == 1  # porter stemming
    assert hits('NEAR("volume" "HBM3E", 3)') == 1
    assert hits('label:"Item 7"') == 1
    snippet = conn.execute(
        "SELECT snippet(section_fts, 1, '[', ']', '…', 8) FROM section_fts "
        "WHERE section_fts MATCH 'HBM3E'"
    ).fetchone()[0]
    assert "[HBM3E]" in snippet


def test_migration_0002_maps_old_empty_rows(tmp_path, monkeypatch):
    conn = connect(tmp_path / "engine.db")
    all_engine = migrations("engine")
    monkeypatch.setattr(db, "migrations", lambda name: all_engine[:1])
    migrate(conn, "engine")
    conn.execute(
        "INSERT INTO fetch_log (url, outcome, status, from_cache, detail, at) "
        "VALUES ('u', 'empty', 404, 0, 'HTTP 404', '2026-10-07T00:00:00+00:00')"
    )
    monkeypatch.setattr(db, "migrations", lambda name: all_engine)
    assert migrate(conn, "engine") == len(all_engine)
    assert conn.execute("SELECT outcome FROM fetch_log").fetchone()[0] == "not_found"
