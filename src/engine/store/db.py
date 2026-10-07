"""Connections and ordered migrations for engine.db and corpus.db (M00_STORAGE.md).

Settings: WAL, busy_timeout 5 s, foreign keys on, synchronous=NORMAL.
Migrations are SQL files in engine/store/migrations/<db>/NNNN_name.sql, applied
in order, each in one transaction together with its schema_version row.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

DATABASES = ("engine", "corpus")
_MIGRATION_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


def data_dir() -> Path:
    """Local data folder (outside synced folders, D20). Override with ENGINE_DATA_DIR."""
    return Path(os.getenv("ENGINE_DATA_DIR", "data"))


def connect(path: Path | str, *, check_same_thread: bool = True) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=check_same_thread, autocommit=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def migrations(db: str) -> list[tuple[int, str, str]]:
    """(version, name, sql) for every migration of `db`, in order."""
    if db not in DATABASES:
        raise ValueError(f"unknown database {db!r}")
    folder = resources.files("engine.store") / "migrations" / db
    found = []
    for entry in folder.iterdir():
        m = _MIGRATION_RE.match(entry.name)
        if m:
            found.append((int(m.group(1)), m.group(2), entry.read_text(encoding="utf-8")))
    found.sort()
    versions = [v for v, _, _ in found]
    if versions != list(range(1, len(versions) + 1)):
        raise RuntimeError(f"{db} migrations are not numbered 1..n: {versions}")
    return found


def current_version(conn: sqlite3.Connection) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if not exists:
        return 0
    row = conn.execute("SELECT max(version) FROM schema_version").fetchone()
    return row[0] or 0


def migrate(conn: sqlite3.Connection, db: str) -> int:
    """Apply pending migrations; return the resulting version."""
    version = current_version(conn)
    for number, name, sql in migrations(db):
        if number <= version:
            continue
        applied_at = datetime.now(UTC).isoformat(timespec="seconds")
        try:
            conn.execute("BEGIN")
            for statement in _statements(sql):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_version (version, name, applied_at) VALUES (?, ?, ?)",
                (number, name, applied_at),
            )
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        version = number
    return version


def open_db(db: str, folder: Path | None = None, **kwargs: bool) -> sqlite3.Connection:
    """Connect to data/<db>.db and bring it to the latest schema."""
    conn = connect((folder or data_dir()) / f"{db}.db", **kwargs)
    migrate(conn, db)
    return conn


def _statements(sql: str) -> list[str]:
    """Split a migration into complete statements (handles triggers' inner semicolons)."""
    out, buf = [], ""
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip() and not buf.strip().startswith("--"):
        raise ValueError(f"incomplete SQL statement in migration: {buf[:80]!r}")
    return out
