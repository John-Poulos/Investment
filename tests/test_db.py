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
    row = ("XYZ", "M07", "opportunistic_buy", "MY", "2026-09-12", 1, "A", "Form 4 x", "filter")
    sql = "INSERT INTO signal VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    conn.execute(sql, row)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, (*row[:3], "XX", *row[4:]))  # bad timeframe
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, (*row[:4], "2026-09-13", 1, "D", *row[7:]))  # bad grade


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
