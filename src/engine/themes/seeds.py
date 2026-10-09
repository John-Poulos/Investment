"""Seed themes from config/themes.toml into the database (M02 D-M02-16).

The file is the owner's; the app never writes it. Syncing is idempotent: new themes,
phrases and company links get today's discovery date; names update in place; anything
removed from the file is archived, never deleted (discovery dates are kept for
point-in-time backtests, D-M02-15). Phrases are normalized exactly as EFTS receives
them, so a phrase EFTS would reject is reported, not stored.
"""

from __future__ import annotations

import re
import sqlite3
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from engine.sec.client import iso
from engine.sec.fulltext import QueryError, normalize_phrase

_KEY = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class SeedTheme:
    key: str
    name: str
    phrases: tuple[str, ...]  # normalized (quoted)
    companies: tuple[str, ...]  # tickers, upper case


@dataclass
class SeedReport:
    themes_added: list[str] = field(default_factory=list)
    themes_archived: list[str] = field(default_factory=list)
    phrases_added: list[str] = field(default_factory=list)  # "key: phrase"
    phrases_archived: list[str] = field(default_factory=list)
    companies_added: list[str] = field(default_factory=list)
    companies_archived: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)  # entries not stored, with reason


def load_seeds(path: Path) -> tuple[list[SeedTheme], list[str]]:
    """Themes from the file, plus problems found (bad keys, duplicate keys, bad phrases)."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    themes, problems, seen = [], [], set()
    for i, t in enumerate(raw.get("theme") or []):
        key = str(t.get("key", "")).strip()
        name = str(t.get("name", "")).strip()
        if not _KEY.match(key) or not name:
            problems.append(f"theme #{i + 1}: needs a lower-case key (a-z, 0-9, _) and a name")
            continue
        if key in seen:
            problems.append(f"theme {key}: duplicate key, later entry ignored")
            continue
        seen.add(key)
        phrases = []
        for p in t.get("phrases") or []:
            try:
                phrases.append(normalize_phrase(str(p)))
            except QueryError as e:
                problems.append(f"{key}: phrase {p!r} rejected: {e}")
        companies = [str(c).strip().upper() for c in t.get("companies") or [] if str(c).strip()]
        themes.append(SeedTheme(key, name, tuple(dict.fromkeys(phrases)),
                                tuple(dict.fromkeys(companies))))  # fmt: skip
    return themes, problems


def sync_seeds(engine: sqlite3.Connection, path: Path, now: datetime) -> SeedReport:
    themes, problems = load_seeds(path)
    report = SeedReport(rejected=problems)
    ts = iso(now)
    engine.execute("BEGIN")
    try:
        file_keys = {t.key for t in themes}
        for t in themes:
            row = engine.execute("SELECT theme_id, status FROM theme WHERE key = ?",
                                 (t.key,)).fetchone()  # fmt: skip
            if row is None:
                theme_id = engine.execute(
                    "INSERT INTO theme (key, name, source, status, discovered_at, updated_at) "
                    "VALUES (?, ?, 'seed', 'active', ?, ?)",
                    (t.key, t.name, ts, ts),
                ).lastrowid
                report.themes_added.append(t.key)
            else:
                theme_id = row["theme_id"]
                engine.execute(
                    "UPDATE theme SET name = ?, status = 'active', updated_at = ? "
                    "WHERE theme_id = ? AND (name != ? OR status != 'active')",
                    (t.name, ts, theme_id, t.name),
                )
            _sync_children(engine, "theme_phrase", "phrase", theme_id, t.key, t.phrases, ts,
                           report.phrases_added, report.phrases_archived)  # fmt: skip
            _sync_children(engine, "theme_company", "ticker", theme_id, t.key, t.companies, ts,
                           report.companies_added, report.companies_archived)  # fmt: skip
        for row in engine.execute(
            "SELECT theme_id, key FROM theme WHERE source = 'seed' AND status = 'active'"
        ).fetchall():
            if row["key"] not in file_keys:
                engine.execute("UPDATE theme SET status = 'archived', updated_at = ? "
                               "WHERE theme_id = ?", (ts, row["theme_id"]))  # fmt: skip
                report.themes_archived.append(row["key"])
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return report


def _sync_children(
    engine: sqlite3.Connection,
    table: str,
    col: str,
    theme_id: int,
    key: str,
    values: tuple[str, ...],
    ts: str,
    added: list[str],
    archived: list[str],
) -> None:
    """Seed rows of one theme: add new, re-activate returning, archive removed."""
    stored = {r[col]: r["status"] for r in engine.execute(
        f"SELECT {col}, status FROM {table} WHERE theme_id = ? AND source = 'seed'",
        (theme_id,))}  # fmt: skip
    for v in values:
        if v not in stored:
            engine.execute(
                f"INSERT INTO {table} (theme_id, {col}, source, status, discovered_at, "
                "updated_at) VALUES (?, ?, 'seed', 'active', ?, ?) "
                f"ON CONFLICT (theme_id, {col}) DO UPDATE SET status = 'active', updated_at = ?",
                (theme_id, v, ts, ts, ts),
            )
            added.append(f"{key}: {v}")
        elif stored[v] != "active":
            engine.execute(f"UPDATE {table} SET status = 'active', updated_at = ? "
                           f"WHERE theme_id = ? AND {col} = ?", (ts, theme_id, v))  # fmt: skip
            added.append(f"{key}: {v} (re-activated)")
    for v, status in stored.items():
        if v not in values and status == "active":
            engine.execute(f"UPDATE {table} SET status = 'archived', updated_at = ? "
                           f"WHERE theme_id = ? AND {col} = ?", (ts, theme_id, v))  # fmt: skip
            archived.append(f"{key}: {v}")


def active_themes(engine: sqlite3.Connection) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT * FROM theme WHERE status = 'active' ORDER BY theme_id"
    ).fetchall()


def active_phrases(engine: sqlite3.Connection, theme_id: int) -> list[str]:
    return [r["phrase"] for r in engine.execute(
        "SELECT phrase FROM theme_phrase WHERE theme_id = ? AND status = 'active' "
        "ORDER BY phrase_id", (theme_id,))]  # fmt: skip
