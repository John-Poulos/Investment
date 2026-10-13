"""Peer facts: one trimmed companyfacts download per confirmed SEC peer (D-M04-75, SB.16;
M04 Part 2).

- **Who:** the members of each confirmed peer set (`peer_group` "M04 peers <cik>", written
  by the Part 1c setup page). A company with no confirmed set gets nothing fetched and reads
  "peers not confirmed on the M04 setup page". Non-SEC peers (no CIK) are "missing: not an
  SEC filer". A peer that is itself a covered company (watchlist, promoted or tracked) uses
  the facts the refresh keeps for it: no download.
- **What is kept:** only the tags in M04's concept map — every tag of `xbrl_facts.CONCEPTS`
  and `EXTRA_CONCEPTS` (us-gaap, ifrs-full and dei; Parts 1a–1b), the capex definitions'
  PP&E and productive-assets tags, the D&A tags of the capex split, and goodwill (the
  acquisition-year flag, `peers.GOODWILL`). IFRS filers (20-F, `ifrs-full`) keep their
  mapped IFRS tags; a concept with no IFRS tag stays missing. Everything is stored in
  `fact` under the peer's CIK (all versions, as for covered companies); `series` is not
  built for peers (display only; M04 reads `facts_as_of`).
- **The file is not cached** (`ttl_s=0`; a ~3.4 MB median file would otherwise sit in
  corpus.db, SB.16). `peer_fetch` records the tags and rows kept, the rows new and the MB
  downloaded per peer.
- **Fiscal year end:** a peer has no submissions row; its fiscal year end (MMDD) is taken
  from its latest annual fact (10-K/20-F/40-F, fiscal-year duration) and stored in `entity`
  (inserted with the companyfacts name when the peer has no entity row; an existing row's
  year end is only filled when empty), so `fy_points` can tell fiscal years from
  trailing-twelve-month cash flows.
- **Refresh (D-M04-70):** the refresh marks a fetched peer "due" when the daily index shows
  its new 10-K, 10-Q, 20-F or 40-F (or an amendment; `mark_due`); the M04 SEC part
  re-fetches due peers (`refetch_due`). A 6-K is not a trigger (whether it carries XBRL is
  unknown for a company whose filing index is not stored); a 20-F filer's facts update on
  its 20-F. First downloads are owner-run (`scripts/run_financials.py peers`).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime

from engine.financials import capex as capex_mod
from engine.sec.client import SecClient, iso
from engine.sec.identity import normalize_cik
from engine.sec.results import Failed, NotFound, Ok
from engine.sec.xbrl_facts import (
    CONCEPTS,
    EXTRA_CONCEPTS,
    FACTS_URL,
    REFRESH_FORMS,
    classify,
    iter_facts,
    store_facts,
)

GROUP = "M04 peers {cik}"
NOT_CONFIRMED = "peers not confirmed on the M04 setup page"
NOT_SEC = "missing: not an SEC filer"
NOT_FETCHED = "missing: facts not fetched yet (run_financials.py peers)"
STEP_BUDGET_S = 90.0
ANNUAL_FORMS = ("10-K", "10-K/A", "10-KT", "20-F", "20-F/A", "40-F", "40-F/A")
GOODWILL_TAGS = (("us-gaap", "Goodwill"), ("ifrs-full", "Goodwill"))


def keep_tags() -> frozenset[tuple[str, str]]:
    """(taxonomy, tag) pairs M04 reads (1a/1b concept map, capex definitions, goodwill)."""
    tags: set[tuple[str, str]] = set()
    for c in CONCEPTS + EXTRA_CONCEPTS:
        tags.update(c.tags)
    tags.update(capex_mod.PPE_TAGS)
    tags.update(capex_mod.PRODUCTIVE_TAGS)
    tags.update(capex_mod.DA_TAGS)
    tags.update(GOODWILL_TAGS)
    return frozenset(tags)


KEEP = keep_tags()


def trim(data: dict) -> tuple[dict, int, int]:
    """Only M04's tags. Returns (trimmed document, tags in the file, tags kept)."""
    facts = data.get("facts") or {}
    total = sum(len(tags) for tags in facts.values())
    out: dict[str, dict] = {}
    for tax, tags in facts.items():
        for tag, body in tags.items():
            if (tax, tag) in KEEP:
                out.setdefault(tax, {})[tag] = body
    kept = sum(len(t) for t in out.values())
    return {"cik": data.get("cik"), "entityName": data.get("entityName"), "facts": out}, total, kept


def fiscal_year_end(rows: Iterable[tuple]) -> str | None:
    """MMDD of the latest fiscal-year fact filed on an annual form (iter_facts rows)."""
    best = None
    for r in rows:
        start, end, form = r[4], r[5], r[8]
        if form in ANNUAL_FORMS and classify(start, end) == "FY" and (best is None or end > best):
            best = end
    if best is None:
        return None
    d = date.fromisoformat(best)
    return f"{d.month:02d}{d.day:02d}"


# --- Who ---------------------------------------------------------------------------------------


@dataclass
class PeerSet:
    ticker: str
    cik: str
    confirmed: bool
    members: list[sqlite3.Row] = field(default_factory=list)  # cik, name, source

    @property
    def sec(self) -> list[sqlite3.Row]:
        return [m for m in self.members if m["cik"]]


def peer_set(engine: sqlite3.Connection, ticker: str, cik: str) -> PeerSet:
    norm = normalize_cik(cik) or cik
    g = engine.execute(
        "SELECT group_id FROM peer_group WHERE name = ?", (GROUP.format(cik=norm),)
    ).fetchone()
    if g is None:
        return PeerSet(ticker, norm, False)
    rows = engine.execute(
        "SELECT cik, name, source FROM peer_member WHERE group_id = ? ORDER BY name", (g[0],)
    ).fetchall()
    return PeerSet(ticker, norm, True, list(rows))


def peer_sets(
    engine: sqlite3.Connection, targets: dict[str, str]
) -> dict[str, PeerSet]:  # fmt: skip
    """ticker → its peer set, for the given targets (ticker → cik)."""
    return {t: peer_set(engine, t, c) for t, c in sorted(targets.items())}


def has_facts(engine: sqlite3.Connection, cik: str) -> bool:
    return engine.execute("SELECT 1 FROM fact WHERE cik = ? LIMIT 1", (cik,)).fetchone() is not None


def stored(engine: sqlite3.Connection, cik: str) -> sqlite3.Row | None:
    return engine.execute("SELECT * FROM peer_fetch WHERE cik = ?", (cik,)).fetchone()


# --- Fetch -------------------------------------------------------------------------------------


@dataclass
class PeerFetch:
    cik: str
    name: str
    outcome: str  # ok | not_found | failed
    mb: float = 0.0
    tags_total: int = 0
    tags_kept: int = 0
    rows_kept: int = 0
    rows_new: int = 0
    fye: str | None = None
    latest_end: str | None = None
    latest_filed: str | None = None
    detail: str = ""
    throttled: bool = False

    def line(self) -> str:
        if self.outcome != "ok":
            return f"{self.name} ({self.cik}): {self.outcome}: {self.detail}"
        return (f"{self.name} ({self.cik}): {self.mb:.2f} MB; tags kept {self.tags_kept} of "
                f"{self.tags_total}; rows kept {self.rows_kept:,}, new {self.rows_new:,}; "
                f"FYE {self.fye or 'unknown'}; latest period {self.latest_end or '—'} filed "
                f"{self.latest_filed or '—'}")  # fmt: skip


def _ensure_entity(
    engine: sqlite3.Connection, cik: str, name: str, fye: str | None, now: datetime
) -> None:
    row = engine.execute("SELECT fiscal_year_end FROM entity WHERE cik = ?", (cik,)).fetchone()
    if row is None:
        engine.execute(
            "INSERT INTO entity (cik, name, fiscal_year_end, source_ref, fetched_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (cik, name, fye, FACTS_URL.format(cik=cik) + " (M04 peer; FYE inferred)", iso(now)),
        )
    elif not row[0] and fye:
        engine.execute("UPDATE entity SET fiscal_year_end = ? WHERE cik = ?", (fye, cik))


def _record(engine: sqlite3.Connection, f: PeerFetch, now: datetime) -> None:
    ts = iso(now)
    if f.outcome == "ok":
        engine.execute(
            "INSERT INTO peer_fetch (cik, name, fetched_at, outcome, ok_at, tags_total, tags_kept, "
            "rows_kept, rows_new, mb, fiscal_year_end, latest_end, latest_filed, due_accession, "
            "due_form, due_filed, detail) VALUES (?, ?, ?, 'ok', ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, "
            "NULL, NULL, NULL) ON CONFLICT (cik) DO UPDATE SET name = excluded.name, "
            "fetched_at = excluded.fetched_at, outcome = 'ok', ok_at = excluded.ok_at, "
            "tags_total = excluded.tags_total, tags_kept = excluded.tags_kept, "
            "rows_kept = excluded.rows_kept, rows_new = excluded.rows_new, mb = excluded.mb, "
            "fiscal_year_end = excluded.fiscal_year_end, latest_end = excluded.latest_end, "
            "latest_filed = excluded.latest_filed, due_accession = NULL, due_form = NULL, "
            "due_filed = NULL, detail = NULL",
            (f.cik, f.name, ts, ts, f.tags_total, f.tags_kept, f.rows_kept, f.rows_new,
             round(f.mb, 3), f.fye, f.latest_end, f.latest_filed),
        )  # fmt: skip
    else:
        engine.execute(
            "INSERT INTO peer_fetch (cik, name, fetched_at, outcome, detail) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (cik) DO UPDATE SET "
            "fetched_at = excluded.fetched_at, outcome = excluded.outcome, "
            "detail = excluded.detail",
            (f.cik, f.name, ts, f.outcome, f.detail),
        )


def fetch_peer(
    client: SecClient, engine: sqlite3.Connection, cik: str, name: str, now: datetime
) -> PeerFetch:
    """Download the peer's companyfacts (not cached), keep M04's tags, store, record."""
    norm = normalize_cik(cik) or cik
    url = FACTS_URL.format(cik=norm)
    res = client.get_bytes(url, ttl_s=0)  # SB.16: stored as facts; the file is not kept
    if isinstance(res, NotFound):
        f = PeerFetch(norm, name, "not_found", detail="no companyfacts file (HTTP 404)")
    elif not isinstance(res, Ok):
        reason = res.reason if isinstance(res, Failed) else str(res)
        f = PeerFetch(norm, name, "failed", detail=reason,
                      throttled=isinstance(res, Failed) and res.throttled)  # fmt: skip
    else:
        mb = len(res.data) / 1e6
        try:
            data = json.loads(res.data)
        except ValueError as e:
            data = None
            f = PeerFetch(norm, name, "failed", mb, detail=f"invalid JSON: {e}")
        if data is not None:
            if not isinstance(data, dict) or "facts" not in data:
                f = PeerFetch(
                    norm, name, "failed", mb, detail="companyfacts unreadable: no 'facts'"
                )
            else:
                doc, total, kept = trim(data)
                rows = list(iter_facts(norm, doc))
                f = PeerFetch(norm, data.get("entityName") or name, "ok", mb, total, kept,
                              len(rows), 0, fiscal_year_end(rows))  # fmt: skip
                if rows:
                    f.latest_end = max(r[5] for r in rows)
                    f.latest_filed = max(r[9] for r in rows if r[9]) or None
                engine.execute("BEGIN")
                try:
                    _, f.rows_new = store_facts(engine, norm, doc)
                    _ensure_entity(engine, norm, f.name, f.fye, now)
                    _record(engine, f, now)
                    engine.execute("COMMIT")
                except Exception:
                    engine.execute("ROLLBACK")
                    raise
                return f
    engine.execute("BEGIN")
    _record(engine, f, now)
    engine.execute("COMMIT")
    return f


# --- Refresh: due peers (D-M04-70) -------------------------------------------------------------


def mark_due(engine: sqlite3.Connection, entries: Iterable) -> int:
    """Daily-index entries (cik, form, filed, accession): a fetched peer's new periodic
    filing marks it due for a re-fetch. Returns rows marked. Own short transaction."""
    forms = set(REFRESH_FORMS)
    hits = [e for e in entries if e.form in forms]
    if not hits:
        return 0
    known = {r[0]: r[1] for r in engine.execute("SELECT cik, ok_at FROM peer_fetch")}
    n = 0
    for e in hits:
        if e.cik not in known:
            continue
        ok_at = (known[e.cik] or "")[:10]
        if ok_at and e.filed < ok_at:
            continue
        engine.execute(
            "UPDATE peer_fetch SET due_accession = ?, due_form = ?, due_filed = ? "
            "WHERE cik = ? AND (due_filed IS NULL OR due_filed < ?)",
            (e.accession, e.form, e.filed, e.cik, e.filed),
        )
        n += 1
    return n


def due_peers(engine: sqlite3.Connection) -> list[sqlite3.Row]:
    """Due peers that are still members of a confirmed M04 peer set."""
    return engine.execute(
        "SELECT p.* FROM peer_fetch p WHERE p.due_filed IS NOT NULL AND EXISTS (SELECT 1 FROM "
        "peer_member m JOIN peer_group g ON g.group_id = m.group_id WHERE m.cik = p.cik AND "
        "g.name LIKE 'M04 peers %') ORDER BY p.due_filed, p.cik"
    ).fetchall()


def unfetched_peers(engine: sqlite3.Connection, covered: Iterable[str]) -> list[sqlite3.Row]:
    """Confirmed SEC peers never fetched and not covered (owner-run backfill)."""
    cov = set(covered)
    rows = engine.execute(
        "SELECT DISTINCT m.cik, m.name FROM peer_member m JOIN peer_group g ON g.group_id = "
        "m.group_id WHERE g.name LIKE 'M04 peers %' AND m.cik IS NOT NULL AND m.cik NOT IN "
        "(SELECT cik FROM peer_fetch WHERE outcome = 'ok') ORDER BY m.name"
    ).fetchall()
    return [r for r in rows if r["cik"] not in cov]


def refetch_due(
    client: SecClient,
    engine: sqlite3.Connection,
    now: datetime,
    *,
    budget_s: float = STEP_BUDGET_S,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    """Re-fetch due peers (per-new-filing work, inside the refresh lock). Lines for the
    run report; a time budget or a throttle leaves the rest due for the next run."""
    due = due_peers(engine)
    lines: list[str] = []
    got = mb = 0.0
    start = clock()
    left = 0
    for i, r in enumerate(due):
        if clock() - start > budget_s:
            left = len(due) - i
            lines.append(f"  time budget reached; {left} peer(s) stay due for the next run")
            break
        f = fetch_peer(client, engine, r["cik"], r["name"] or r["cik"], now)
        lines.append(f"  {r['due_form']} filed {r['due_filed']}: {f.line()}")
        if f.outcome == "ok":
            got += 1
            mb += f.mb
        if f.throttled:
            left = len(due) - i - 1
            lines.append("  SEC throttle: the rest stays due for the next run")
            break
    head = (f"M04 peer facts: {len(due)} due (new periodic filing in the daily index); "
            f"re-fetched {got:.0f} ({mb:.1f} MB), left {left}")  # fmt: skip
    return [head, *lines]
