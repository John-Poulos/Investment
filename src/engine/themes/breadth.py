"""Theme breadth: how many distinct filers mention a theme, as a share of all filers of
the same form family, compared with the same window a year earlier (D-M02-1, -10, -14).

Per phrase and window, up to `max_pages` EFTS pages (100 hits each) are fetched. If
that covers every hit, filings and companies are exact; otherwise they are a lower
bound ("≥"), using the fetched hits plus EFTS's entity summary. A theme's own row
(phrase '') is the union of its phrases' filers. Failed windows stay missing (NULL),
never zero; a phrase with no hits is a real zero.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from engine.sec.client import SecClient, iso
from engine.sec.fulltext import EFTS_CAP, search
from engine.sec.results import Failed, Ok
from engine.themes.universe import FAMILIES, filers

MAX_PAGES = 10  # D-M02-14: ≤ 1,000 hits per phrase per window
PAGE = 100
THEME_ROW = ""  # phrase value of the theme's union row


def year_back(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # 29 February
        return d.replace(year=d.year - 1, day=28)


def breadth_windows(first_year: int, through: date) -> list[tuple[str, str]]:
    """Full calendar years first_year..last complete year, then year-to-date and the
    same span a year earlier (so the latest year compares like with like)."""
    out = [(f"{y}-01-01", f"{y}-12-31") for y in range(first_year, through.year)]
    if through < date(through.year, 12, 31):
        prior = year_back(through)
        out.append((f"{prior.year}-01-01", prior.isoformat()))
        out.append((f"{through.year}-01-01", through.isoformat()))
    else:
        out.append((f"{through.year}-01-01", through.isoformat()))
    return list(dict.fromkeys(out))


@dataclass(frozen=True)
class Count:
    phrase: str
    start: str
    end: str
    documents: int | None
    filings: int | None
    companies: int | None
    lower_bound: bool
    capped: bool
    error: str | None = None


def count_phrase(
    client: SecClient,
    engine: sqlite3.Connection,
    phrase: str,
    family: str,
    start: str,
    end: str,
    now: datetime,
    max_pages: int = MAX_PAGES,
    split: bool = True,
) -> tuple[Count, set[str], set[str]]:
    """One phrase in one window → (count, filer CIKs seen, accessions seen).

    EFTS answers some quoted phrases with a persistent server error on a long window
    (seen live: "advanced packaging", 2020). A failed window is retried once as two
    halves and merged; if a half fails too, the window stays missing.
    """
    res = search(client, engine, phrase, forms=FAMILIES[family], start=start, end=end, now=now,
                 max_hits=max_pages * PAGE, allow_fallback=False)  # fmt: skip
    if not isinstance(res, Ok):
        reason = res.reason if isinstance(res, Failed) else "not found"
        server_error = isinstance(res, Failed) and not res.throttled and (res.status or 0) >= 500
        s, e = date.fromisoformat(start), date.fromisoformat(end)
        if split and server_error and (e - s).days >= 2:
            mid = s + (e - s) // 2
            a = count_phrase(client, engine, phrase, family, start, mid.isoformat(), now,
                             max_pages, split=False)  # fmt: skip
            b = count_phrase(client, engine, phrase, family,
                             (mid + timedelta(days=1)).isoformat(), end, now, max_pages,
                             split=False)  # fmt: skip
            if a[0].documents is not None and b[0].documents is not None:
                return _merge(phrase, start, end, a, b, reason)
        return Count(phrase, start, end, None, None, None, False, False, reason), set(), set()
    r = res.data
    ciks = {c for h in r.hits for c in (h.ciks or ((h.cik,) if h.cik else ()))}
    accessions = {h.accession for h in r.hits}
    complete = r.complete
    companies = len(ciks) if complete else len(ciks | set(r.entities))
    count = Count(phrase, start, end, r.total, len(accessions), companies, not complete,
                  r.capped or r.total >= EFTS_CAP,
                  "; ".join(r.incomplete) or None)  # fmt: skip
    return count, ciks, accessions


def _merge(
    phrase: str,
    start: str,
    end: str,
    a: tuple[Count, set[str], set[str]],
    b: tuple[Count, set[str], set[str]],
    reason: str,
) -> tuple[Count, set[str], set[str]]:
    (ca, ka, xa), (cb, kb, xb) = a, b
    lower = ca.lower_bound or cb.lower_bound
    ciks, acc = ka | kb, xa | xb
    companies = len(ciks) if not lower else max(len(ciks), ca.companies or 0, cb.companies or 0)
    note = f"whole window failed ({reason}); counted as two halves"
    return (Count(phrase, start, end, (ca.documents or 0) + (cb.documents or 0), len(acc),
                  companies, lower, ca.capped or cb.capped, note), ciks, acc)  # fmt: skip


@dataclass(frozen=True)
class BreadthRun:
    theme_key: str
    family: str
    counts: list[Count]  # phrase rows, then theme rows (phrase '')


def compute_theme(
    client: SecClient,
    engine: sqlite3.Connection,
    theme_id: int,
    theme_key: str,
    phrases: Sequence[str],
    family: str,
    windows: Sequence[tuple[str, str]],
    now: datetime,
    max_pages: int = MAX_PAGES,
    progress: Callable[[str], None] | None = None,
) -> BreadthRun:
    counts: list[Count] = []
    for start, end in windows:
        union_ciks: set[str] = set()
        union_acc: set[str] = set()
        exact, failed, best = True, [], 0
        for phrase in phrases:
            c, ciks, acc = count_phrase(client, engine, phrase, family, start, end, now,
                                        max_pages)  # fmt: skip
            counts.append(c)
            union_ciks |= ciks
            union_acc |= acc
            if c.documents is None:
                failed.append(phrase)
            else:
                best = max(best, c.companies or 0)
                exact = exact and not c.lower_bound
            if progress:
                progress(_line(theme_key, family, c))
        counts.append(Count(
            THEME_ROW, start, end, None,
            len(union_acc) if not failed else None,
            max(len(union_ciks), best) if not failed else None,
            not exact, False,
            f"phrases failed: {', '.join(failed)}" if failed else None,
        ))  # fmt: skip
    _store(engine, theme_id, family, counts, now)
    return BreadthRun(theme_key, family, counts)


def _line(key: str, family: str, c: Count) -> str:
    if c.documents is None:
        return f"{key} {family} {c.start}..{c.end} {c.phrase}: failed ({c.error})"
    ge = "≥" if c.lower_bound else ""
    return (f"{key} {family} {c.start}..{c.end} {c.phrase}: {c.documents:,} docs, "
            f"{ge}{c.filings} filings, {ge}{c.companies} companies")  # fmt: skip


def _store(
    engine: sqlite3.Connection, theme_id: int, family: str, counts: list[Count], now: datetime
) -> None:
    engine.execute("BEGIN")
    try:
        for c in counts:
            engine.execute(
                "INSERT OR REPLACE INTO theme_breadth (theme_id, phrase, family, start_date, "
                "end_date, documents, filings, companies, lower_bound, capped, filers, error, "
                "computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (theme_id, c.phrase, family, c.start, c.end, c.documents, c.filings,
                 c.companies, int(c.lower_bound), int(c.capped),
                 filers(engine, family, c.start, c.end), c.error, iso(now)),
            )  # fmt: skip
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise


@dataclass(frozen=True)
class BreadthRow:
    phrase: str
    family: str
    start: str
    end: str
    documents: int | None
    filings: int | None
    companies: int | None
    lower_bound: bool
    filers: int | None
    share: float | None  # companies ÷ filers; a lower bound when lower_bound
    prior_share: float | None  # same window a year earlier
    error: str | None

    @property
    def change_pts(self) -> float | None:
        """Share change vs the same window a year earlier, in percentage points."""
        if self.share is None or self.prior_share is None:
            return None
        return 100 * (self.share - self.prior_share)


def breadth_rows(engine: sqlite3.Connection, theme_id: int, family: str) -> list[BreadthRow]:
    """Stored breadth with shares and the same-window-last-year comparison."""
    rows = engine.execute(
        "SELECT * FROM theme_breadth WHERE theme_id = ? AND family = ? "
        "ORDER BY phrase != '', phrase, start_date, end_date",
        (theme_id, family),
    ).fetchall()

    def share(r: sqlite3.Row) -> float | None:
        if r["companies"] is None or not r["filers"]:
            return None
        return r["companies"] / r["filers"]

    by_key = {(r["phrase"], r["start_date"], r["end_date"]): r for r in rows}
    out = []
    for r in rows:
        s, e = date.fromisoformat(r["start_date"]), date.fromisoformat(r["end_date"])
        prior = by_key.get((r["phrase"], year_back(s).isoformat(), year_back(e).isoformat()))
        out.append(BreadthRow(
            r["phrase"], family, r["start_date"], r["end_date"], r["documents"], r["filings"],
            r["companies"], bool(r["lower_bound"]), r["filers"], share(r),
            share(prior) if prior is not None else None, r["error"],
        ))  # fmt: skip
    return out
