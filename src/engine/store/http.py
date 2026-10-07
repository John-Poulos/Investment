"""SQLite-backed raw HTTP cache (corpus.db) and fetch log (engine.db) for SecClient."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime

from engine.sec.client import CachedResponse, iso


class SqliteCache:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.Lock()

    def get(self, key: str, now: datetime) -> CachedResponse | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT status, body, content_type, outcome, fetched_at FROM http_cache "
                "WHERE cache_key = ? AND expires_at > ?",
                (key, iso(now)),
            ).fetchone()
        if row is None:
            return None
        return CachedResponse(
            row["status"],
            bytes(row["body"]),
            row["content_type"] or "",
            row["outcome"],
            row["fetched_at"],
        )

    def put(
        self,
        key: str,
        url: str,
        status: int,
        body: bytes,
        content_type: str,
        outcome: str,
        fetched_at: datetime,
        expires_at: datetime,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO http_cache (cache_key, url, status, content_type, body, outcome, "
                "fetched_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (cache_key) DO UPDATE SET url = excluded.url, "
                "status = excluded.status, content_type = excluded.content_type, "
                "body = excluded.body, outcome = excluded.outcome, "
                "fetched_at = excluded.fetched_at, expires_at = excluded.expires_at",
                (key, url, status, content_type, body, outcome, iso(fetched_at), iso(expires_at)),
            )


class SqliteFetchLog:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.Lock()

    def write(
        self,
        url: str,
        outcome: str,
        detail: str,
        status: int | None,
        from_cache: bool,
        at: datetime,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO fetch_log (url, outcome, status, from_cache, detail, at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (url, outcome, status, int(from_cache), detail, iso(at)),
            )
