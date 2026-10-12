"""Shared pieces of the official-feed adapters (D-M02-13, D-M02-60).

- `Budget`: an in-Python time budget for one run (the logon refresh shares a 3-h task limit,
  D-M02-12); an adapter stops when it is spent and leaves the rest for the next run.
- `active_phrases`: active phrases of active themes, unquoted, with their theme ids.
- `state_get` / `state_set`: per-feed progress in `refresh_state`.
- `write`: one short write transaction (the app writes during refresh runs, D-M02-12).
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from engine.news.items import SNIPPET_MAX, clean
from engine.sec.client import iso


class Budget:
    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._end = clock() + seconds
        self.stopped: set[str] = set()

    def left(self) -> float:
        return self._end - self._clock()

    def spent(self, source: str) -> bool:
        if self.left() <= 0:
            self.stopped.add(source)
            return True
        return False


@dataclass(frozen=True)
class Phrase:
    theme_id: int
    phrase: str  # unquoted, as written in the theme

    @property
    def key(self) -> str:
        return self.phrase.lower()


def active_phrases(engine: sqlite3.Connection) -> list[Phrase]:
    return [
        Phrase(r["theme_id"], r["phrase"].strip().strip('"'))
        for r in engine.execute(
            "SELECT p.theme_id, p.phrase FROM theme_phrase p JOIN theme t USING (theme_id) "
            "WHERE t.status = 'active' AND p.status = 'active' ORDER BY p.phrase_id"
        )
    ]


def distinct_phrases(phrases: list[Phrase]) -> list[str]:
    """Each phrase once (lowercase key order kept), for per-phrase queries."""
    seen: dict[str, str] = {}
    for p in phrases:
        seen.setdefault(p.key, p.phrase)
    return list(seen.values())


def snip(text: str | None) -> str | None:
    t = clean(text)
    if not t:
        return None
    return t if len(t) <= SNIPPET_MAX else t[: SNIPPET_MAX - 1].rstrip() + "…"


def state_get(engine: sqlite3.Connection, name: str) -> str | None:
    r = engine.execute("SELECT fetched_at FROM refresh_state WHERE name = ?", (name,)).fetchone()
    return r[0] if r else None


def state_detail(engine: sqlite3.Connection, name: str) -> str | None:
    r = engine.execute("SELECT detail FROM refresh_state WHERE name = ?", (name,)).fetchone()
    return r[0] if r else None


def state_set(engine: sqlite3.Connection, name: str, ref: str, now: datetime, detail: str) -> None:
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET source_ref = excluded.source_ref, "
        "fetched_at = excluded.fetched_at, detail = excluded.detail",
        (name, ref, iso(now), detail),
    )


@contextmanager
def write(engine: sqlite3.Connection) -> Iterator[None]:
    engine.execute("BEGIN")
    try:
        yield
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise


def link_theme(
    engine: sqlite3.Connection,
    source: str,
    ref: str,
    theme_id: int,
    phrase: str,
    now: datetime,
    prominent: bool | None = None,
) -> None:
    """prominent: the phrase is in the title or abstract (Federal Register, D-M02-61 (4))."""
    p = None if prominent is None else int(prominent)
    engine.execute(
        "INSERT INTO official_theme (source, ref, theme_id, phrase, found_at, prominent) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO UPDATE SET "
        "prominent = CASE WHEN excluded.prominent IS NULL THEN prominent "
        "ELSE max(coalesce(prominent, 0), excluded.prominent) END",
        (source, ref, theme_id, phrase, iso(now), p),
    )
