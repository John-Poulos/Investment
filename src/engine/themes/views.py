"""Read models for the Themes screens (M00_UI rule U4: pages call plain functions).

List: one row per active theme with its latest year-to-date breadth, the same span a
year earlier and the yearly share series. Detail: per-phrase companies per window.
Filers: the filings behind one phrase and window (from stored EFTS hits). Company
tab: themes linked to a company and its own filings that mention a theme phrase.
Missing stays missing (None → "—"); lower bounds carry their flag.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date

from engine.themes.breadth import THEME_ROW, BreadthRow, breadth_rows
from engine.themes.seeds import active_phrases
from engine.themes.universe import FAMILIES, data_through

__all__ = ["data_through"]  # re-exported for the UI


def families_with_data(engine: sqlite3.Connection) -> list[str]:
    have = {r[0] for r in engine.execute("SELECT DISTINCT family FROM theme_breadth")}
    return [f for f in FAMILIES if f in have] or ["10-K"]


def _is_full_year(r: BreadthRow) -> bool:
    return r.start.endswith("-01-01") and r.end.endswith("-12-31") and r.start[:4] == r.end[:4]


@dataclass
class ThemeSummary:
    key: str
    name: str
    tickers: list[str]
    phrases: int
    latest: BreadthRow | None  # newest window (year-to-date when the year is open)
    series: list[tuple[str, float | None, bool]]  # (label, share, lower bound) per year
    missing: bool  # some window failed
    lower_bound: bool  # some window is a lower bound


def _theme_rows(engine: sqlite3.Connection, theme_id: int, family: str) -> list[BreadthRow]:
    return [r for r in breadth_rows(engine, theme_id, family) if r.phrase == THEME_ROW]


def _series(rows: list[BreadthRow]) -> list[tuple[str, float | None, bool]]:
    full = [r for r in rows if _is_full_year(r)]
    out = [(r.start[:4], r.share, r.lower_bound) for r in full]
    newest = max(rows, key=lambda r: (r.end, r.start), default=None)
    if newest is not None and not _is_full_year(newest):
        out.append((f"{newest.start[:4]} YTD", newest.share, newest.lower_bound))
    return out


def theme_list(engine: sqlite3.Connection, family: str) -> list[ThemeSummary]:
    out = []
    for t in engine.execute("SELECT * FROM theme WHERE status = 'active' ORDER BY theme_id"):
        rows = _theme_rows(engine, t["theme_id"], family)
        latest = max(rows, key=lambda r: (r.end, r.start), default=None)
        tickers = [r["ticker"] for r in engine.execute(
            "SELECT ticker FROM theme_company WHERE theme_id = ? AND status = 'active' "
            "ORDER BY rowid", (t["theme_id"],))]  # fmt: skip
        out.append(ThemeSummary(
            t["key"], t["name"], tickers, len(active_phrases(engine, t["theme_id"])), latest,
            _series(rows), any(r.companies is None for r in rows),
            any(r.lower_bound for r in rows),
        ))  # fmt: skip
    out.sort(key=lambda s: -(s.latest.share or 0) if s.latest else 0)
    return out


@dataclass
class PhraseLine:
    phrase: str
    cells: list[BreadthRow | None]  # aligned with ThemeDetail.windows


@dataclass
class ThemeDetail:
    key: str
    name: str
    source: str
    discovered_at: str
    tickers: list[str]
    family: str
    windows: list[tuple[str, str]]
    theme_rows: list[BreadthRow | None]
    phrases: list[PhraseLine]
    series: list[tuple[str, float | None, bool]]
    latest: BreadthRow | None
    through: str | None
    notes: list[str] = field(default_factory=list)


def theme_detail(engine: sqlite3.Connection, key: str, family: str) -> ThemeDetail | None:
    t = engine.execute("SELECT * FROM theme WHERE key = ?", (key,)).fetchone()
    if t is None:
        return None
    rows = breadth_rows(engine, t["theme_id"], family)
    windows = sorted({(r.start, r.end) for r in rows}, key=lambda w: (w[0][:4], w[1], w[0]))
    by = {(r.phrase, r.start, r.end): r for r in rows}
    theme_rows = [by.get((THEME_ROW, s, e)) for s, e in windows]
    phrases = [PhraseLine(p, [by.get((p, s, e)) for s, e in windows])
               for p in active_phrases(engine, t["theme_id"])]  # fmt: skip
    trows = [r for r in theme_rows if r is not None]
    tickers = [r["ticker"] for r in engine.execute(
        "SELECT ticker FROM theme_company WHERE theme_id = ? AND status = 'active' ORDER BY rowid",
        (t["theme_id"],))]  # fmt: skip
    notes = sorted({f"{r.phrase} {r.start}..{r.end}: {r.error}" for r in rows
                    if r.error and r.phrase != THEME_ROW})  # fmt: skip
    stale = [p.phrase for p in phrases if all(c is None for c in p.cells)]
    if stale:
        notes.append(f"Not counted yet (added since the last run): {', '.join(stale)}")
    return ThemeDetail(
        t["key"], t["name"], t["source"], t["discovered_at"][:10], tickers, family, windows,
        theme_rows, phrases, _series(trows),
        max(trows, key=lambda r: (r.end, r.start), default=None), data_through(engine), notes,
    )  # fmt: skip


@dataclass(frozen=True)
class Filer:
    entity: str | None
    cik: str | None
    form: str | None
    file_date: str | None
    accession: str
    filename: str
    url: str | None


def phrase_filers(
    engine: sqlite3.Connection, phrase: str, family: str, start: str, end: str
) -> tuple[list[Filer], bool]:
    """Stored hits for a phrase in a window (the latest query per sub-window; a window
    split in halves reads both halves). Second value: the list is partial (lower bound)."""
    forms = ",".join(FAMILIES[family])
    queries = engine.execute(
        "SELECT max(query_id) AS q, total, hits_kept FROM fulltext_query WHERE phrase = ? "
        "AND forms = ? AND start_date >= ? AND end_date <= ? AND variant = 'phrase' "
        "GROUP BY start_date, end_date",
        (phrase, forms, start, end),
    ).fetchall()
    ids = [q["q"] for q in queries]
    partial = any(q["hits_kept"] < q["total"] for q in queries)
    if not ids:
        return [], False
    marks = ",".join("?" * len(ids))
    rows = engine.execute(
        f"SELECT * FROM fulltext_hit WHERE query_id IN ({marks}) ORDER BY entity_name, file_date",
        ids,
    ).fetchall()
    seen, out = set(), []
    for r in rows:
        if r["accession"] in seen:
            continue
        seen.add(r["accession"])
        url = None
        if r["cik"]:
            url = (f"https://www.sec.gov/Archives/edgar/data/{int(r['cik'])}/"
                   f"{r['accession'].replace('-', '')}/{r['filename']}")  # fmt: skip
        out.append(Filer(r["entity_name"], r["cik"], r["form"], r["file_date"], r["accession"],
                         r["filename"], url))  # fmt: skip
    return out, partial


@dataclass
class CompanyThemes:
    linked: list[dict]  # theme key, name, reason, discovered_at
    mentions: list[dict]  # accession, form, file_date, phrases, themes, url


def company_themes(engine: sqlite3.Connection, cik: str, ticker: str) -> CompanyThemes:
    linked = [dict(r) for r in engine.execute(
        "SELECT t.key, t.name, c.source, c.reason, c.discovered_at FROM theme_company c "
        "JOIN theme t USING (theme_id) WHERE c.ticker = ? AND c.status = 'active' "
        "AND t.status = 'active' ORDER BY t.name", (ticker,))]  # fmt: skip
    rows = engine.execute(
        "SELECT h.accession, h.filename, h.form, h.file_date, q.phrase, t.key, t.name "
        "FROM fulltext_hit h JOIN fulltext_query q USING (query_id) "
        "JOIN theme_phrase p ON p.phrase = q.phrase AND p.status = 'active' "
        "JOIN theme t ON t.theme_id = p.theme_id AND t.status = 'active' "
        "WHERE h.cik = ? ORDER BY h.file_date DESC",
        (cik,),
    ).fetchall()
    by_acc: dict[str, dict] = {}
    for r in rows:
        m = by_acc.setdefault(r["accession"], {
            "accession": r["accession"], "form": r["form"], "file_date": r["file_date"],
            "phrases": [], "themes": {},
            "url": (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{r['accession'].replace('-', '')}/{r['filename']}"),
        })  # fmt: skip
        if r["phrase"] not in m["phrases"]:
            m["phrases"].append(r["phrase"])
        m["themes"][r["key"]] = r["name"]
    return CompanyThemes(linked, list(by_acc.values()))


def window_label(start: str, end: str, today: date | None = None) -> str:
    """'2024' for a calendar year, else '2026 YTD' / '2025 to 10-08'."""
    if start.endswith("-01-01") and end.endswith("-12-31") and start[:4] == end[:4]:
        return start[:4]
    return f"{start[:4]} to {end[5:]}"
