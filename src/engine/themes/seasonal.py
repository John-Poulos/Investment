"""Seasonal pass (M02 part 6; D-M02-8, -10, -14, -49…52).

Season dates: 15 Apr, 20 May, 19 Aug, 19 Nov (about 50 days after a quarter end, mid-April
for the 10-K wave). A season's key (2026-08) fixes its windows — year to date at the
season date vs the same span a year earlier — and its form family (10-K for the April and
May passes, 10-Q for August and November), so a late or resumed run tests the same thing.

Steps, each resumable (state per season and phrase, counts per window in seasonal_count):
1. mine: phrases newly used by watchlist companies vs their year-ago twins (mining.py);
2. screen: EFTS page 1 in both windows — ≥ 5 companies and a rise beyond chance on the
   counts available (companies when complete, else documents);
3. test (≤ 30 strongest survivors): up to 10 pages per window — ≥ 5 operating companies
   (blank checks apart) and the conditional binomial rise test, p ≤ 0.10, p0 = the
   window's share of the family's filers (D-M02-49, -52 (2)); industry spread shown,
   finance apart, not enforced (D-M02-52 (3)); crowding = N-1A + 485APOS filings;
4. propose: theme by co-occurrence with an active theme's phrases in our corpus (→
   m02_phrase) or a new theme (m02_theme); at most 10 per pass in priority order, the
   rest listed on the Themes page (D-M02-51). A longer phrase that keeps ≥ 90% of a
   shorter one's companies covers it.
Code only; Gemini names a proposal only when the owner asks (use case 4).
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from math import exp, lgamma, log
from typing import Any

from engine.sec.client import SecClient, iso
from engine.sec.fulltext import normalize_phrase
from engine.themes import industries
from engine.themes.breadth import count_detail, year_back
from engine.themes.mining import MineResult
from engine.themes.universe import FAMILIES, filers

SEASONS = ((4, 15), (5, 20), (8, 19), (11, 19))
FAMILY_BY_MONTH = {4: "10-K", 5: "10-K", 8: "10-Q", 11: "10-Q"}
FUND = "fund"
FUND_FORMS = ("N-1A", "485APOS")  # new fund registrations (D-M02-52 (4))
MIN_COMPANIES = 5
P_MAX = 0.10
SCREEN_PAGES = 1
TEST_PAGES = 10
TEST_CAP = 30
PROPOSE_CAP = 10
OVERLAP_MIN = 0.30
COVER_SHARE = 0.90
TIME_BUDGET_S = 45 * 60


class Throttled(Exception):
    """SEC throttled us; the pass stops and resumes next time."""


# --- Seasons -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Season:
    key: str
    day: date
    family: str
    latest: tuple[str, str]
    prior: tuple[str, str]


def season_at(day: date) -> Season:
    if (day.month, day.day) not in SEASONS:
        raise ValueError(f"{day} is not a season date")
    prior_end = year_back(day)
    return Season(f"{day:%Y-%m}", day, FAMILY_BY_MONTH[day.month],
                  (f"{day.year}-01-01", day.isoformat()),
                  (f"{prior_end.year}-01-01", prior_end.isoformat()))  # fmt: skip


def season_for_key(key: str) -> Season:
    y, m = (int(x) for x in key.split("-"))
    d = next(dd for mm, dd in SEASONS if mm == m)
    return season_at(date(y, m, d))


def latest_season(today: date) -> Season:
    dates = [date(y, m, d) for y in (today.year - 1, today.year) for m, d in SEASONS]
    return season_at(max(x for x in dates if x <= today))


def run_row(engine: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    return engine.execute("SELECT * FROM seasonal_run WHERE season = ?", (key,)).fetchone()


def due(engine: sqlite3.Connection, today: date) -> Season | None:
    s = latest_season(today)
    r = run_row(engine, s.key)
    return None if r is not None and r["status"] == "done" else s


def reminder(engine: sqlite3.Connection, today: date) -> str | None:
    """The refresh report's line until the due season's pass is done (D-M02-51)."""
    s = due(engine, today)
    if s is None:
        return None
    r = run_row(engine, s.key)
    state = "not started" if r is None else f"{r['status']}, resume with --resume"
    return (
        f"Seasonal pass {s.key} (due {s.day}) — {state}: "
        "uv run python scripts/run_seasonal.py --dry-run (estimate), then without it"
    )


def p_rise(n1: int, n0: int, p: float = 0.5) -> float:
    """One-sided conditional binomial: P(X ≥ n1) with X ~ Bin(n0 + n1, p) (D-M02-49)."""
    n = n0 + n1
    if n == 0 or n1 == 0:
        return 1.0
    if not 0 < p < 1:
        return 0.0 if p >= 1 else 1.0
    lp, lq, ln = log(p), log(1 - p), lgamma(n + 1)
    # log space: document counts reach thousands, where comb() overflows a float
    terms = [ln - lgamma(k + 1) - lgamma(n - k + 1) + k * lp + (n - k) * lq
             for k in range(n1, n + 1)]  # fmt: skip
    top = max(terms)
    return min(1.0, exp(top) * sum(exp(t - top) for t in terms))


def p0(engine: sqlite3.Connection, s: Season) -> float:
    """Share of the family's filers in the latest window (D-M02-52 (2)); 0.5 if missing."""
    f1, f0 = filers(engine, s.family, *s.latest), filers(engine, s.family, *s.prior)
    return f1 / (f1 + f0) if f1 and f0 else 0.5


# --- Run state -----------------------------------------------------------------------------


def ensure_run(engine: sqlite3.Connection, s: Season, now: datetime) -> sqlite3.Row:
    engine.execute(
        "INSERT OR IGNORE INTO seasonal_run (season, season_date, family, latest_start, "
        "latest_end, prior_start, prior_end, status, started_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'mined', ?)",
        (s.key, s.day.isoformat(), s.family, *s.latest, *s.prior, iso(now)),
    )
    row = run_row(engine, s.key)
    assert row is not None
    return row


def set_status(engine: sqlite3.Connection, key: str, status: str, now: datetime,
               detail: dict[str, Any] | None = None) -> None:  # fmt: skip
    engine.execute(
        "UPDATE seasonal_run SET status = ?, finished_at = ?, detail = coalesce(?, detail) "
        "WHERE season = ?",
        (status, iso(now) if status == "done" else None,
         json.dumps(detail) if detail is not None else None, key),
    )  # fmt: skip


def known_phrases(engine: sqlite3.Connection) -> set[str]:
    """Every theme phrase in any status, lowercase and unquoted (mining skips them)."""
    return {r[0].strip('"').lower() for r in engine.execute("SELECT phrase FROM theme_phrase")}


def store_mined(engine: sqlite3.Connection, s: Season, mined: MineResult, now: datetime) -> int:
    """New candidates for the season; rows already there (a resumed run) keep their stage."""
    n = 0
    for rank, m in enumerate(mined.candidates, 1):
        n += engine.execute(
            "INSERT OR IGNORE INTO seasonal_phrase (season, phrase, source, adopters, droppers, "
            "adopter_ciks, rank, stage, discovered_at, updated_at) "
            "VALUES (?, ?, 'mined', ?, ?, ?, ?, 'candidate', ?, ?)",
            (s.key, m.phrase, len(m.adopters), m.droppers, json.dumps(list(m.adopters)), rank,
             iso(now), iso(now)),
        ).rowcount  # fmt: skip
    return n


def add_phrases(engine: sqlite3.Connection, s: Season, phrases: Iterable[str], source: str,
                now: datetime) -> int:  # fmt: skip
    """Gemini variants or calibration phrases join the season as candidates."""
    n = 0
    for p in phrases:
        n += engine.execute(
            "INSERT OR IGNORE INTO seasonal_phrase (season, phrase, source, rank, stage, "
            "discovered_at, updated_at) VALUES (?, ?, ?, 0, 'candidate', ?, ?)",
            (s.key, " ".join(p.lower().split()), source, iso(now), iso(now)),
        ).rowcount
    return n


def _update(engine: sqlite3.Connection, s: Season, phrase: str, now: datetime, **cols: Any) -> None:
    sets = ", ".join(f"{k} = ?" for k in cols)
    vals = [json.dumps(v) if isinstance(v, dict | list) else v for v in cols.values()]
    engine.execute(f"UPDATE seasonal_phrase SET {sets}, updated_at = ? "
                   "WHERE season = ? AND phrase = ?", (*vals, iso(now), s.key, phrase))  # fmt: skip


# --- Counting ------------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowCount:
    documents: int | None
    filings: int | None
    companies: int | None
    lower_bound: bool
    sics: dict[str, str | None]
    error: str | None

    @property
    def operating(self) -> int | None:
        """Companies without blank checks (D-M02-49 (1))."""
        if self.companies is None:
            return None
        blank = sum(1 for v in self.sics.values() if v == industries.BLANK_CHECK)
        return self.companies - blank


def count(
    client: SecClient,
    engine: sqlite3.Connection,
    s: Season,
    phrase: str,
    family: str,
    window: tuple[str, str],
    max_pages: int,
    now: datetime,
) -> WindowCount:
    """One EFTS count, stored per season (resume) — a stored success is never re-fetched."""
    key = (s.key, phrase, family, *window, max_pages)
    row = engine.execute(
        "SELECT * FROM seasonal_count WHERE season = ? AND phrase = ? AND family = ? AND "
        "start_date = ? AND end_date = ? AND max_pages = ?", key).fetchone()  # fmt: skip
    if row is not None and row["documents"] is not None:
        return WindowCount(row["documents"], row["filings"], row["companies"],
                           bool(row["lower_bound"]), json.loads(row["sics"] or "{}"),
                           row["error"])  # fmt: skip
    forms = FUND_FORMS if family == FUND else FAMILIES[family]
    c, sics, _ = count_detail(client, engine, phrase, forms, *window, now, max_pages)
    if c.documents is None and client.paused_for() > 0:
        raise Throttled(f'"{phrase}" {family} {window[0]}..{window[1]}: {c.error}')
    engine.execute(
        "INSERT OR REPLACE INTO seasonal_count (season, phrase, family, start_date, end_date, "
        "max_pages, documents, filings, companies, lower_bound, sics, error, computed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (*key, c.documents, c.filings, c.companies, int(c.lower_bound), json.dumps(sics),
         c.error, iso(now)),
    )  # fmt: skip
    return WindowCount(c.documents, c.filings, c.companies, c.lower_bound, sics, c.error)


# --- Screen and test -----------------------------------------------------------------------


@dataclass
class Budget:
    seconds: float = TIME_BUDGET_S
    started: float = 0.0

    def __post_init__(self) -> None:
        self.started = time.monotonic()

    def over(self) -> bool:
        return time.monotonic() - self.started > self.seconds


def _fmt(c: WindowCount) -> str:
    return "—" if c.companies is None else f"{'≥' if c.lower_bound else ''}{c.operating}"


def screen(
    client: SecClient,
    engine: sqlite3.Connection,
    s: Season,
    now: datetime,
    budget: Budget,
    progress: Callable[[str], None] | None = None,
) -> int:
    """Page 1 of every candidate in both windows. Returns how many were screened now."""
    base = p0(engine, s)
    done = 0
    for r in engine.execute("SELECT phrase FROM seasonal_phrase WHERE season = ? AND stage = "
                            "'candidate' ORDER BY rank, phrase", (s.key,)).fetchall():  # fmt: skip
        if budget.over():
            break
        ph = r[0]
        a = count(client, engine, s, ph, s.family, s.latest, SCREEN_PAGES, now)
        b = count(client, engine, s, ph, s.family, s.prior, SCREEN_PAGES, now)
        done += 1
        cols: dict[str, Any] = {
            "latest_companies": a.operating,
            "prior_companies": b.operating,
            "latest_docs": a.documents,
            "prior_docs": b.documents,
            "lower_bound": int(a.lower_bound or b.lower_bound),
            "p0": base,
        }
        if a.documents is None or b.documents is None:
            _update(engine, s, ph, now, stage="screened_out",
                    reason=f"EFTS failed: {a.error or b.error}", **cols)  # fmt: skip
            continue
        exact = not (a.lower_bound or b.lower_bound)
        n1, n0 = (a.operating or 0, b.operating or 0) if exact else (a.documents, b.documents)
        p = p_rise(n1, n0, base)
        unit = "companies" if exact else "documents"
        if (a.operating or 0) < MIN_COMPANIES:
            stage, why = "screened_out", f"fewer than {MIN_COMPANIES} companies ({_fmt(a)})"
        elif p > P_MAX:
            stage, why = "screened_out", f"no rise beyond chance ({n0} → {n1} {unit}, p {p:.3f})"
        else:
            stage, why = "screened", f"screen: {n0} → {n1} {unit}, p {p:.3f}"
        _update(engine, s, ph, now, stage=stage, reason=why, p_value=p, **cols)
        if progress:
            progress(f"  screen {ph!r}: {why}")
    return done


def test(
    client: SecClient,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    s: Season,
    now: datetime,
    budget: Budget,
    progress: Callable[[str], None] | None = None,
) -> int:
    """Full test of the strongest screened phrases (≤ TEST_CAP per season)."""
    base = p0(engine, s)
    f1, f0 = filers(engine, s.family, *s.latest), filers(engine, s.family, *s.prior)
    tested = engine.execute("SELECT count(*) FROM seasonal_phrase WHERE season = ? AND stage IN "
                            "('passed', 'failed', 'proposed', 'listed') AND p_value IS NOT NULL",
                            (s.key,)).fetchone()[0]  # fmt: skip
    rows = engine.execute(
        "SELECT phrase FROM seasonal_phrase WHERE season = ? AND stage = 'screened' "
        "ORDER BY p_value, latest_companies DESC, phrase LIMIT ?",
        (s.key, max(0, TEST_CAP - tested)),
    ).fetchall()
    done = 0
    for r in rows:
        if budget.over():
            break
        ph = r[0]
        a = count(client, engine, s, ph, s.family, s.latest, TEST_PAGES, now)
        b = count(client, engine, s, ph, s.family, s.prior, TEST_PAGES, now)
        done += 1
        if a.documents is None or b.documents is None:
            _update(engine, s, ph, now, stage="failed", reason=f"EFTS failed: {a.error or b.error}")
            continue
        n1, n0 = a.operating or 0, b.operating or 0
        p = p_rise(n1, n0, base)
        lower = a.lower_bound or b.lower_bound
        sp = industries.spread(a.sics.items())
        growth = 100 * (n1 / f1 - n0 / f0) if f1 and f0 else None
        cols: dict[str, Any] = {
            "latest_companies": n1, "prior_companies": n0, "latest_docs": a.documents,
            "prior_docs": b.documents, "lower_bound": int(lower), "p_value": p, "p0": base,
            "growth_pts": growth, "spread": sp.to_json() | {"blank_note": _blank(a)},
        }  # fmt: skip
        if n1 < MIN_COMPANIES:
            why, stage = f"fewer than {MIN_COMPANIES} operating companies ({_fmt(a)})", "failed"
        elif p > P_MAX:
            why, stage = f"no rise beyond chance ({n0} → {n1} companies, p {p:.3f})", "failed"
        else:
            why, stage = f"{n0} → {n1} companies, p {p:.3f}", "passed"
        _update(engine, s, ph, now, stage=stage, reason=why, **cols)
        if stage == "passed":
            crowd = crowding(client, engine, s, ph, now)
            tid, overlap = assign_theme(engine, corpus, ph)
            _update(engine, s, ph, now, crowding=crowd, theme_id=tid, overlap=overlap,
                    samples=samples(engine, corpus, ph, sp))  # fmt: skip
        if progress:
            progress(f"  test {ph!r}: {why}")
    return done


def _blank(c: WindowCount) -> int:
    return sum(1 for v in c.sics.values() if v == industries.BLANK_CHECK)


def crowding(client: SecClient, engine: sqlite3.Connection, s: Season, phrase: str,
             now: datetime) -> dict[str, Any]:  # fmt: skip
    """New fund registrations naming the phrase, latest vs prior window (D-M02-10, -52)."""
    a = count(client, engine, s, phrase, FUND, s.latest, 1, now)
    b = count(client, engine, s, phrase, FUND, s.prior, 1, now)
    if a.documents is None or b.documents is None:
        return {"latest": a.documents, "prior": b.documents, "flag": None,
                "note": "fund search failed"}  # fmt: skip
    p = p_rise(a.documents, b.documents)
    return {"latest": a.documents, "prior": b.documents, "p": p,
            "flag": a.documents > b.documents and p <= P_MAX,
            "note": "documents in N-1A + 485APOS filings"}  # fmt: skip


# --- Theme, samples, proposals -------------------------------------------------------------


def _fts(phrase: str) -> str:
    words = re.findall(r"[a-z0-9]+", phrase.lower())
    return '"' + " ".join(words) + '"'


def _rowids(corpus: sqlite3.Connection, query: str, limit: int = 2000) -> set[int]:
    try:
        return {
            r[0]
            for r in corpus.execute(
                "SELECT rowid FROM passage_fts WHERE passage_fts MATCH ? LIMIT ?", (query, limit)
            )
        }
    except sqlite3.OperationalError:
        return set()


def assign_theme(engine: sqlite3.Connection, corpus: sqlite3.Connection,
                 phrase: str) -> tuple[int | None, float | None]:  # fmt: skip
    """The active theme whose phrases share the most of this phrase's corpus passages, if
    ≥ 30% of them; else None (a new theme)."""
    own = _rowids(corpus, _fts(phrase))
    if not own:
        return None, None
    best: tuple[float, int | None] = (0.0, None)
    for t in engine.execute("SELECT theme_id FROM theme WHERE status = 'active'").fetchall():
        ps = [r[0] for r in engine.execute("SELECT phrase FROM theme_phrase WHERE theme_id = ? "
                                           "AND status = 'active'", (t[0],))]  # fmt: skip
        if not ps:
            continue
        theirs = _rowids(corpus, " OR ".join(_fts(p) for p in ps), 20000)
        share = len(own & theirs) / len(own)
        if share > best[0]:
            best = (share, t[0])
    return (best[1], best[0]) if best[0] >= OVERLAP_MIN else (None, best[0])


def samples(engine: sqlite3.Connection, corpus: sqlite3.Connection, phrase: str,
            sp: industries.Spread, n: int = 3) -> list[dict[str, Any]]:  # fmt: skip
    """Three corpus passages naming the phrase: two from the largest industry group of its
    EFTS companies, one from the next (D-M02-49), one per company where possible."""
    rows = corpus.execute(
        "SELECT p.passage_id, p.start_offset, p.end_offset, d.cik, d.accession, d.filename "
        "FROM passage_fts f JOIN passage p ON p.passage_id = f.rowid "
        "JOIN document d ON d.doc_id = p.doc_id WHERE passage_fts MATCH ? LIMIT 200",
        (_fts(phrase),),
    ).fetchall() if _rowids(corpus, _fts(phrase), 1) else []  # fmt: skip
    sic = {r[0]: r[1] for r in engine.execute("SELECT cik, sic FROM entity")}
    names = {r[0]: r[1] for r in engine.execute("SELECT cik, name FROM entity")}
    order = [g for g, _ in sp.groups[:2]]
    want = [order[0], order[0], order[1]] if len(order) > 1 else order * 3
    picked: list[sqlite3.Row] = []
    for g in want + [None] * n:
        for r in rows:
            if r in picked or len(picked) >= n:
                continue
            if g is not None and industries.group_of(sic.get(r["cik"])) != g:
                continue
            if any(p["cik"] == r["cik"] for p in picked) and g is not None:
                continue
            picked.append(r)
            break
    out = []
    for r in picked[:n]:
        text = corpus.execute(
            "SELECT substr(text, ?, ?) FROM document WHERE accession = ? AND filename = ?",
            (
                r["start_offset"] + 1,
                r["end_offset"] - r["start_offset"],
                r["accession"],
                r["filename"],
            ),
        ).fetchone()[0]
        at = text.lower().find(phrase.split()[0])
        lo = max(0, at - 250)
        out.append(
            {
                "passage_id": r["passage_id"],
                "cik": r["cik"],
                "name": names.get(r["cik"]),
                "group": industries.group_of(sic.get(r["cik"])),
                "accession": r["accession"],
                "filename": r["filename"],
                "text": " ".join(text[lo : lo + 600].split()),
            }
        )
    return out


def _covered(rows: list[sqlite3.Row]) -> dict[str, str]:
    """Shorter phrase → longer phrase that keeps ≥ 90% of its companies."""
    out = {}
    for r in rows:
        for o in rows:
            inside = o["phrase"] != r["phrase"] and f" {r['phrase']} " in f" {o['phrase']} "
            keeps = (o["latest_companies"] or 0) >= COVER_SHARE * (r["latest_companies"] or 0)
            if inside and keeps:
                out[r["phrase"]] = o["phrase"]
    return out


def propose_pass(engine: sqlite3.Connection, s: Season, now: datetime,
                 tickers: dict[str, str] | None = None) -> dict[str, int]:  # fmt: skip
    """Queue ≤ 10 passed phrases (priority order), list the rest (D-M02-51)."""
    from engine.themes.proposals import priority, propose

    tickers = tickers or {}
    rows = engine.execute("SELECT * FROM seasonal_phrase WHERE season = ? AND stage = 'passed'",
                          (s.key,)).fetchall()  # fmt: skip
    already = engine.execute("SELECT count(*) FROM seasonal_phrase WHERE season = ? AND "
                             "stage = 'proposed'", (s.key,)).fetchone()[0]  # fmt: skip
    covered = _covered(rows)
    payloads = {r["phrase"]: _payload(engine, s, r, tickers) for r in rows}
    ranked = sorted(rows, key=lambda r: (priority("m02_phrase", payloads[r["phrase"]]),
                                         -(r["latest_companies"] or 0), r["phrase"]))  # fmt: skip
    out = {"proposed": 0, "listed": 0, "suppressed": 0}
    for r in ranked:
        ph = r["phrase"]
        if ph in covered:
            _update(engine, s, ph, now, stage="listed", reason=f'covered by "{covered[ph]}"')
            out["listed"] += 1
            continue
        if already + out["proposed"] >= PROPOSE_CAP:
            _update(engine, s, ph, now, stage="listed",
                    reason=f"over this pass's {PROPOSE_CAP} proposals")  # fmt: skip
            out["listed"] += 1
            continue
        p = payloads[ph] | _rows_for(engine, s, r, now)
        kind = "m02_phrase" if p.get("theme_key") and not p.get("new_theme") else "m02_theme"
        key = f"{p['theme_key']}:{ph}" if kind == "m02_phrase" else ph
        what = f"new phrase for {p['theme_name']}" if kind == "m02_phrase" else "new theme"
        reason = f'"{ph}" — {what}: {r["prior_companies"]} → {r["latest_companies"]} companies'
        res = propose(engine, kind, key, reason, p, now)
        if res == "suppressed":
            _update(
                engine, s, ph, now, stage="listed", reason="decided before (no material change)"
            )
            out["suppressed"] += 1
            continue
        _update(engine, s, ph, now, stage="proposed", reason=f"{kind}: {res}")
        out["proposed"] += 1
    return out


def _payload(engine: sqlite3.Connection, s: Season, r: sqlite3.Row,
             tickers: dict[str, str]) -> dict[str, Any]:  # fmt: skip
    theme = engine.execute("SELECT key, name FROM theme WHERE theme_id = ?",
                           (r["theme_id"],)).fetchone() if r["theme_id"] else None  # fmt: skip
    adopters = json.loads(r["adopter_ciks"] or "[]")
    lb = "≥" if r["lower_bound"] else ""
    return {
        "phrase": r["phrase"],
        "season": s.key,
        "family": s.family,
        "windows": {"latest": list(s.latest), "prior": list(s.prior)},
        "companies": r["latest_companies"],
        "prior_companies": r["prior_companies"],
        "lower_bound": bool(r["lower_bound"]),
        "p": r["p_value"],
        "p0": r["p0"],
        "growth_pts": r["growth_pts"],
        "spread": json.loads(r["spread"] or "{}"),
        "crowding": json.loads(r["crowding"] or "{}"),
        "samples": json.loads(r["samples"] or "[]"),
        "adopters": [tickers.get(c, c) for c in adopters],
        "source": r["source"],
        "theme_key": theme["key"] if theme else None,
        "theme_name": theme["name"] if theme else None,
        "overlap": r["overlap"],
        "grade": "A",
        "money_flow": False,
        "first_detected": r["discovered_at"],
        "why": (
            f'{s.family} filers using "{r["phrase"]}": {r["prior_companies"]} → '
            f"{lb}{r['latest_companies']} ({s.prior[0]}..{s.prior[1]} vs "
            f"{s.latest[0]}..{s.latest[1]}), p {r['p_value']:.3f}"
        ),
    }


def _rows_for(engine: sqlite3.Connection, s: Season, r: sqlite3.Row,
              now: datetime) -> dict[str, Any]:  # fmt: skip
    """Proposed theme/phrase rows, so the owner's accept or reject sets their status."""
    quoted = normalize_phrase(r["phrase"])
    tid = r["theme_id"]
    new_theme = tid is None
    if new_theme:
        key = "mined-" + re.sub(r"[^a-z0-9]+", "-", r["phrase"]).strip("-")
        engine.execute("INSERT OR IGNORE INTO theme (key, name, source, status, discovered_at, "
                       "updated_at) VALUES (?, ?, 'engine', 'proposed', ?, ?)",
                       (key, r["phrase"], r["discovered_at"], iso(now)))  # fmt: skip
        t = engine.execute("SELECT theme_id, key, name FROM theme WHERE key = ?", (key,)).fetchone()
        tid = t["theme_id"]
    engine.execute("INSERT OR IGNORE INTO theme_phrase (theme_id, phrase, source, status, "
                   "discovered_at, updated_at) VALUES (?, ?, ?, 'proposed', ?, ?)",
                   (tid, quoted, "llm" if r["source"] == "llm" else "mined", r["discovered_at"],
                    iso(now)))  # fmt: skip
    pid = engine.execute("SELECT phrase_id FROM theme_phrase WHERE theme_id = ? AND phrase = ?",
                         (tid, quoted)).fetchone()[0]  # fmt: skip
    t = engine.execute("SELECT key, name FROM theme WHERE theme_id = ?", (tid,)).fetchone()
    out: dict[str, Any] = {"phrase_id": pid, "theme_key": t["key"], "theme_name": t["name"],
                           "new_theme": new_theme}  # fmt: skip
    if new_theme:
        out["theme_id"] = tid
    return out


def stage_counts(engine: sqlite3.Connection, key: str) -> dict[str, int]:
    return dict(engine.execute("SELECT stage, count(*) FROM seasonal_phrase WHERE season = ? "
                               "GROUP BY stage", (key,)).fetchall())  # fmt: skip


def estimate(engine: sqlite3.Connection, key: str) -> dict[str, int]:
    """Requests still needed (lower bound): 2 per candidate to screen, up to 2 × 10 pages
    + 2 fund pages per test slot."""
    c = stage_counts(engine, key)
    tested = sum(c.get(k, 0) for k in ("passed", "failed", "proposed", "listed"))
    slots = min(c.get("screened", 0) + c.get("candidate", 0), max(0, TEST_CAP - tested))
    return {"screen": 2 * c.get("candidate", 0), "test_max": slots * (2 * TEST_PAGES + 2)}
