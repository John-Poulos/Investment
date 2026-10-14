"""M07 Part 2: followed managers' 13F-HR → `followed_manager_13f` (D-M07-6, -7, -18…22).

Managers come from the owner-edited `config/m07_managers.toml` (Duquesne Family Office and
Berkshire Hathaway to start; "CEO of equity" not identified, DESIGN Q3). A manager without a
CIK in the file is resolved by name: a stored entity or ticker name first, then (owner script
only, never the refresh) one EDGAR company-name search.

**Filing sync (D-SEC-28).** `sync_filings` stores the manager's filing list (every
submissions page once), so `thirteenf.due` finds its 13F-HRs of the last 8 quarters; each
is read once with `thirteenf.read_filing` (index, cover, table: 3 requests) behind a
**keep-filter**: a row is stored only when it resolves to one of our companies (core,
promoted, tracked), when the owner maps its CUSIP in the config `[cusips]` table, or when
its issuer name is ambiguous and one candidate is ours ("possibly ours", stored unresolved
with the CUSIP shown). Every other row is left out and counted in the log, so it never
reaches `fin_holding`, M02's K1 edges or `m02_13f_issuer` items; the manager's filer CIK
is recorded as `m07_manager:<cik>` and M02's views skip it (D-M02-62). A manager that is
also one of our companies stays an M02 filer (all rows, read by M02's financing step).

**Refresh.** The daily index marks a followed manager due when it lists a new 13F-HR
(`mark_due`); the SEC part then re-reads its submissions (1 request) and reads each new
filing (3), so about 4 requests per new 13F-HR and 0 when none. The signal pass is local
and runs when a manager's stored 13F rows changed.

**Signal (D-M07-6, rule 8).** Per company and manager quarter: common-share rows (SH, no
put/call) summed over CUSIPs and classes; put/call and PRN rows are listed apart, never in
the change. Quarter-over-quarter against the manager's previous stored quarter (splits in
between applied): `new`, `add`, `cut`, `exit`, `hold`; value = Δ shares; Δ and before/after
as % of the cover count known on each filing date (M04, D-M04-2). A manager's first stored
quarter is the baseline (no row). A quarter with no stored 13F is never an `exit`: the next
filing compares with the last stored quarter and names the gap. A held row (a check failed)
or an unresolved "possibly ours" row gives "missing: …" for that company and quarter.
Amendments: a RESTATEMENT replaces the quarter (dated on its own filing day); a NEW HOLDINGS
amendment adds rows (confidential treatment ended), dated on its filing day and flagged.
as_of = the filing day; same-day filings of several managers aggregate into one row
(value = summed Δ, `mixed` when directions differ; M07 rule 6). MY carries a soft vote;
PT and ST are info (weight 0). The method states the lag ("quarter ended …, filed … N days
later; 13F-HR is due 45 days after the quarter").
"""

from __future__ import annotations

import json
import sqlite3
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from engine.financing import issuers, thirteenf
from engine.ownership.cards import Market
from engine.sec.client import SecClient, iso
from engine.sec.identity import normalize_cik
from engine.sec.results import Failed, Ok
from engine.signals import Source, write_signal

MODULE = "M07"
SIGNAL = "followed_manager_13f"
CONFIG = Path(__file__).resolve().parents[3] / "config" / "m07_managers.toml"
FOLLOWED = thirteenf.FOLLOWED_STATE  # refresh_state `m07_manager:<cik>` = synced, followed
DUE_STATE = "m07_manager_due:"  # refresh_state: the daily index listed a new 13F-HR
PASS_STATE = "m07_managers_pass"  # fingerprint of the last signal pass
LAG_DAYS = 45  # 13F-HR due 45 days after the quarter end (S15)
TEXTS = ("new", "add", "cut", "exit", "hold")
# The pack's reference (S243): Berkshire's 13F-HRs for 2024-03-31 and 2024-06-30 (AAPL
# 789,368,450 → 400,000,000 shares, cut). Read by the owner script, outside the 8 quarters.
BERKSHIRE = "0001067983"
REFERENCE = {BERKSHIRE: ("0000950123-24-005622", "0000950123-24-008740")}


# --- config ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Manager:
    name: str
    cik: str | None
    note: str = ""
    how: str = "config"  # config | stored name | EDGAR company search | unresolved: …


@dataclass
class ManagersConfig:
    managers: list[Manager] = field(default_factory=list)
    cusips: dict[str, str] = field(default_factory=dict)  # cusip6 → ticker or CIK
    problems: list[str] = field(default_factory=list)
    text: str = ""


def load_config(path: Path = CONFIG) -> ManagersConfig:
    """The owner's manager list; a missing or broken file gives no managers (and a problem)."""
    out = ManagersConfig()
    try:
        out.text = path.read_text(encoding="utf-8")
        raw = tomllib.loads(out.text)
    except OSError:
        out.problems.append(f"no manager list at {path}")
        return out
    except tomllib.TOMLDecodeError as e:
        out.problems.append(f"{path.name} unreadable: {e}")
        return out
    for i, m in enumerate(raw.get("manager") or [], 1):
        name = str(m.get("name") or "").strip()
        if not name:
            out.problems.append(f"manager {i}: no name; skipped")
            continue
        raw_cik = str(m.get("cik") or "").strip()
        cik = normalize_cik(raw_cik) if raw_cik else None
        if raw_cik and cik is None:
            out.problems.append(f"{name}: cik {raw_cik!r} is not a CIK; resolved by name")
        out.managers.append(Manager(name, cik, str(m.get("note") or "")))
    for k, v in (raw.get("cusips") or {}).items():
        out.cusips[str(k).strip().upper()[:6]] = str(v).strip().upper()
    return out


def _stored_names(engine: sqlite3.Connection, name: str) -> set[str]:
    key = issuers.norm(name)
    return {
        r[1]
        for r in engine.execute(
            "SELECT name, cik FROM entity UNION SELECT name, cik FROM ticker WHERE name IS NOT NULL"
        )
        if r[0] and issuers.norm(r[0]) == key
    }


def resolve(engine: sqlite3.Connection, m: Manager, client: SecClient | None = None) -> Manager:
    """The manager's filer CIK: config, else one stored entity/ticker name, else (client
    given) one EDGAR company-name search whose single exact-name hit is taken."""
    if m.cik:
        return m
    stored = _stored_names(engine, m.name)
    if len(stored) == 1:
        return replace(m, cik=next(iter(stored)), how="stored name")
    if len(stored) > 1:
        listed = ", ".join(sorted(stored))
        return replace(m, how=f"unresolved: {len(stored)} stored companies named {m.name!r} "
                              f"({listed}); write the CIK in the config")  # fmt: skip
    if client is None:
        return replace(m, how="unresolved: no stored company of that name; the owner script "
                              "resolves it (one EDGAR company search)")  # fmt: skip
    from engine.sec.browse import company_search

    res = company_search(client, m.name)
    if not isinstance(res, Ok):
        return replace(m, how=f"unresolved: EDGAR company search failed ({res})")
    key = issuers.norm(m.name)
    hits = {c: n for c, n in res.data if issuers.norm(n) == key}
    if len(hits) == 1:
        cik, found = next(iter(hits.items()))
        return replace(m, cik=cik, how=f"EDGAR company search ({found})")
    listed = "; ".join(f"{n} {c}" for c, n in res.data[:6]) or "no company"
    return replace(m, how=f"unresolved: EDGAR company search found {len(hits)} exact name "
                          f"match(es) among: {listed}; write the CIK in the config")  # fmt: skip


def cusip_targets(engine: sqlite3.Connection, cfg: ManagersConfig, ours: dict[str, str]
                  ) -> tuple[dict[str, str], list[str]]:  # fmt: skip
    """Config `[cusips]` → {cusip6: cik} for our companies; others reported."""
    out, problems = {}, []
    by_ticker = {t.upper(): c for c, t in ours.items() if t}
    for c6, target in cfg.cusips.items():
        cik = normalize_cik(target) if target.isdigit() else by_ticker.get(target)
        if cik is None and not target.isdigit():
            row = engine.execute("SELECT cik FROM ticker WHERE ticker = ? AND valid_to IS NULL",
                                 (target,)).fetchone()  # fmt: skip
            cik = row[0] if row else None
        if cik is None or cik not in ours:
            problems.append(f"[cusips] {c6} = {target}: not one of our companies; ignored")
            continue
        out[c6] = cik
    return out, problems


def keep_filter(names: issuers.Names, ours: dict[str, str], cmap: dict[str, str]) -> thirteenf.Keep:
    """D-SEC-28 keep-filter (rule 8): our companies only; "possibly ours" kept unresolved."""

    def keep(row: thirteenf.Row, cik: str | None, how: str):
        mapped = cmap.get(row.cusip[:6].upper())
        if mapped:
            return mapped, "owner (m07_managers.toml)", None
        if cik is not None:
            return (cik, how, None) if cik in ours else None
        cands = sorted(names.match(row.issuer) & set(ours))
        if cands:
            who = ", ".join(f"{ours[c] or c} {c}" for c in cands)
            note = f"possibly ours: {who} (CUSIP {row.cusip}; map it in m07_managers.toml)"
            return None, how, note
        return None

    return keep


# --- filing sync (SEC) ------------------------------------------------------------------------


@dataclass
class FilingRead:
    accession: str
    form: str
    filed: str
    kept: int = 0
    skipped: int = 0
    unresolved: int = 0
    held: int = 0
    problems: list[str] = field(default_factory=list)


@dataclass
class ManagerSync:
    manager: Manager
    status: str = ""  # synced | M02 filer | unresolved | failed | throttled
    listed_13f: int = 0
    reads: list[FilingRead] = field(default_factory=list)
    skipped_rows: list[thirteenf.Row] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    throttled: bool = False


def mark_followed(engine: sqlite3.Connection, m: Manager, now: datetime) -> None:
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, 'M07', ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
        "detail = excluded.detail",
        (FOLLOWED + (m.cik or ""), iso(now), m.name),
    )


def is_followed(engine: sqlite3.Connection, cik: str) -> bool:
    return engine.execute("SELECT 1 FROM refresh_state WHERE name = ?",
                          (FOLLOWED + cik,)).fetchone() is not None  # fmt: skip


def _read_due(
    client: SecClient,
    engine: sqlite3.Connection,
    m: Manager,
    filings: list[sqlite3.Row],
    keep: thirteenf.Keep,
    names: issuers.Names,
    now: datetime,
    out: ManagerSync,
) -> None:
    for f in filings:
        rep = thirteenf.Report13F()
        ok = thirteenf.read_filing(client, engine, m.cik or "", f, names, now, rep, keep=keep)
        fr = FilingRead(f["accession"], f["form"], f["filed"], rep.rows, len(rep.skipped),
                        rep.unresolved, rep.held, list(rep.problems))  # fmt: skip
        out.reads.append(fr)
        out.skipped_rows += rep.skipped
        if not ok:
            out.throttled = True
            out.status = "throttled"
            return


def reference_filings(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    accs = REFERENCE.get(cik, ())
    if not accs:
        return []
    marks = ",".join("?" * len(accs))
    return engine.execute(
        f"SELECT accession, form, filed FROM filing WHERE accession IN ({marks}) AND accession "
        "NOT IN (SELECT accession FROM fin_13f WHERE status != 'failed') ORDER BY filed",
        accs,
    ).fetchall()


def sync_manager(
    client: SecClient,
    engine: sqlite3.Connection,
    m: Manager,
    ours: dict[str, str],
    cmap: dict[str, str],
    names: issuers.Names,
    now: datetime,
    *,
    reference: bool = False,
    fresh: bool = True,
) -> ManagerSync:
    """Filing list, then every unread 13F-HR of the last 8 quarters (plus the reference
    filings when asked) behind the keep-filter. Never raises for SEC errors."""
    from engine.sec.identity import load_entity
    from engine.sec.submissions import sync_filings

    out = ManagerSync(m)
    if not m.cik:
        out.status = "unresolved"
        out.problems.append(m.how)
        return out
    if m.cik in ours:
        out.status = "M02 filer"  # its 13F-HRs are read whole by M02's financing step
        return out
    mark_followed(engine, m, now)  # before any row is stored: M02 skips this filer
    fs = sync_filings(client, engine, m.cik, now, fresh=fresh)
    if isinstance(fs, Failed) and fs.throttled:
        out.status, out.throttled = "throttled", True
        out.problems.append(f"filing list: {fs.reason}")
        return out
    if not isinstance(fs, Ok):
        out.status = "failed"
        out.problems.append(f"filing list: {fs}")
        return out
    out.problems += [f"submissions page {p}" for p in fs.data.pages_failed]
    load_entity(client, engine, m.cik, now)  # name from the cached submissions file
    out.listed_13f = engine.execute(
        "SELECT count(*) FROM filing f JOIN filing_cik c ON c.accession = f.accession WHERE "
        "c.cik = ? AND f.form IN ('13F-HR', '13F-HR/A')",
        (m.cik,),
    ).fetchone()[0]
    keep = keep_filter(names, ours, cmap)
    todo = thirteenf.due(engine, m.cik, now)
    if reference:
        seen = {f["accession"] for f in todo}
        todo = reference_filings(engine, m.cik) + [f for f in todo if f["accession"] not in seen]
    _read_due(client, engine, m, todo, keep, names, now, out)
    if not out.throttled:
        out.status = "synced"
        engine.execute("DELETE FROM refresh_state WHERE name = ?", (DUE_STATE + m.cik,))
    return out


def plan(engine: sqlite3.Connection, m: Manager, ours: dict[str, str], now: datetime,
         *, reference: bool = False) -> tuple[int, str]:  # fmt: skip
    """Dry-run request count (0 requests): (requests, how it was counted)."""
    if not m.cik:
        return 0, m.how
    if m.cik in ours:
        return 0, "M02 filer: read by M02's financing step"
    synced = engine.execute("SELECT detail FROM refresh_state WHERE name = ?",
                            (f"submissions:{m.cik}",)).fetchone()  # fmt: skip
    if synced is None:
        est = thirteenf.QUARTERS + 1
        refs = len(REFERENCE.get(m.cik, ())) if reference else 0
        n = 1 + 3 * (est + refs)
        return n, (f"first sync: 1 submissions request + its older pages (listed in that file, "
                   f"read once each; not known before it is read) + about {est} 13F-HR × 3 "
                   f"(index, cover, table)" + (f" + {refs} reference filing(s) × 3" if refs else "")
                   + f" ≈ {n}+ requests")  # fmt: skip
    detail = json.loads(synced[0] or "{}")
    pages = len(detail.get("pages_failed") or ())  # loaded pages are read once, then skipped
    due = thirteenf.due(engine, m.cik, now)
    refs = reference_filings(engine, m.cik) if reference else []
    n = 1 + max(pages, 0) + 3 * (len(due) + len(refs))
    return n, (f"1 submissions request (fresh) + {max(pages, 0)} page(s) + {len(due)} unread "
               f"13F-HR × 3" + (f" + {len(refs)} reference filing(s) × 3" if refs else "")
               + f" = {n} requests")  # fmt: skip


# --- refresh hooks ------------------------------------------------------------------------------


def mark_due(engine: sqlite3.Connection, entries) -> int:
    """Daily-index entries: a followed manager's new 13F-HR marks it due (its own short
    writes; never fails the refresh)."""
    hits = [e for e in entries if e.form in thirteenf.FORMS]
    if not hits:
        return 0
    filers = thirteenf.followed_filers(engine)
    n = 0
    for e in hits:
        if e.cik not in filers:
            continue
        done = engine.execute("SELECT 1 FROM fin_13f WHERE accession = ? AND status != 'failed'",
                              (e.accession,)).fetchone()  # fmt: skip
        if done:
            continue
        engine.execute(
            "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, "
            "'daily index', ?, ?) ON CONFLICT (name) DO UPDATE SET fetched_at = "
            "excluded.fetched_at, detail = excluded.detail",
            (DUE_STATE + e.cik, e.filed, f"{e.form} {e.accession} filed {e.filed}"),
        )
        n += 1
    return n


def run_sec_part(
    client: SecClient | None,
    engine: sqlite3.Connection,
    ours: dict[str, str],
    now: datetime,
    *,
    path: Path = CONFIG,
) -> list[str]:
    """Refresh SEC part: per-new-filing work for followed managers only (0 requests when the
    daily index showed no new 13F-HR and no earlier read failed). Never raises."""
    head = "M07 followed managers — SEC part"
    try:
        cfg = load_config(path)
        lines: list[str] = []
        if not cfg.managers:
            return [f"{head}: no managers ({'; '.join(cfg.problems) or 'list empty'})"]
        cmap, _ = cusip_targets(engine, cfg, ours)
        names = issuers.Names(engine)
        done, waiting = [], []
        for m in (resolve(engine, x) for x in cfg.managers):
            if not m.cik:
                waiting.append(f"{m.name} (CIK not resolved: run scripts/run_ownership.py "
                               "managers)")  # fmt: skip
                continue
            if m.cik in ours:
                continue  # M02 filer
            if not is_followed(engine, m.cik):
                waiting.append(f"{m.name} (not synced yet: run scripts/run_ownership.py managers)")
                continue
            due_mark = engine.execute("SELECT detail FROM refresh_state WHERE name = ?",
                                      (DUE_STATE + m.cik,)).fetchone()  # fmt: skip
            unread = thirteenf.due(engine, m.cik, now)
            if due_mark is None and not unread:
                continue
            if client is None:
                waiting.append(f"{m.name} (due, no SEC client)")
                continue
            if due_mark is not None:
                s = sync_manager(client, engine, m, ours, cmap, names, now)
            else:  # an earlier read failed: retry it without the submissions request
                s = ManagerSync(m, "synced")
                _read_due(client, engine, m, unread, keep_filter(names, ours, cmap), names, now, s)
            done.append(s)
            if s.throttled:
                break
        if not done:
            lines.append(f"{head}: 0 due (no new 13F-HR from a followed manager in the daily "
                         "index); 0 requests")  # fmt: skip
        for s in done:
            lines.append(
                f"{head}: {s.manager.name} — {s.status}; "
                + (
                    ", ".join(
                        f"{r.form} {r.accession} filed {r.filed}: {r.kept} kept, "
                        f"{r.skipped} not ours"
                        for r in s.reads
                    )
                    or "no new 13F-HR"
                )
            )
            lines += [f"  problem: {p}" for p in s.problems + [x for r in s.reads
                                                               for x in r.problems]]  # fmt: skip
        lines += [f"  waiting: {w}" for w in waiting]
        return lines
    except Exception as e:  # must not break the refresh report
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        return [f"{head}: error — {type(e).__name__}: {e}"]


# --- quarters and positions (local) ----------------------------------------------------------


@dataclass
class Period:
    period: str
    accession: str  # the base filing (original or the latest RESTATEMENT)
    form: str
    filed: str
    restates: list[tuple[str, str]] = field(default_factory=list)  # earlier base (acc, filed)
    adds: list[tuple[str, str]] = field(default_factory=list)  # NEW HOLDINGS (acc, filed)

    @property
    def accessions(self) -> list[str]:
        return [self.accession] + [a for a, _ in self.adds]


def periods(engine: sqlite3.Connection, filer: str) -> list[Period]:
    """The filer's stored quarters as last stated (thirteenf.current's rule), oldest first.
    Unreadable and table-less filings are not quarters (missing, never "exit")."""
    by: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for f in engine.execute(
        "SELECT * FROM fin_13f WHERE filer_cik = ? AND status = 'read' ORDER BY period, filed, "
        "accession",
        (filer,),
    ):
        by[f["period"]].append(f)
    out = []
    for period, fs in sorted(by.items()):
        base = [x for x in fs if x["amend_type"] in (None, "RESTATEMENT")]
        if not base:
            continue
        b = base[-1]
        out.append(Period(
            period, b["accession"], b["form"], b["filed"],
            restates=[(x["accession"], x["filed"]) for x in base[:-1]],
            adds=[(x["accession"], x["filed"]) for x in fs
                  if x["amend_type"] == "NEW HOLDINGS" and x["filed"] >= b["filed"]],
        ))  # fmt: skip
    return out


@dataclass
class Position:
    shares: float = 0.0  # common shares (SH rows, no put/call), summed over CUSIPs
    value: float = 0.0
    rows: int = 0
    titles: list[str] = field(default_factory=list)
    apart: list[str] = field(default_factory=list)  # put/call and PRN rows, never in Δ
    held: list[str] = field(default_factory=list)  # check notes of held rows
    filed: str = ""  # the latest filing day the company's rows came from
    accessions: set[str] = field(default_factory=set)
    revealed: list[str] = field(default_factory=list)  # NEW HOLDINGS amendments


def positions(engine: sqlite3.Connection, p: Period, ours: dict[str, str]) -> dict[str, Position]:
    filed_of = {p.accession: p.filed} | dict(p.adds)
    marks = ",".join("?" * len(p.accessions))
    out: dict[str, Position] = {}
    for r in engine.execute(
        f"SELECT * FROM fin_holding WHERE source = '13F' AND accession IN ({marks}) AND "
        "issuer_cik IS NOT NULL AND status IN ('automatic', 'held') ORDER BY cusip, title",
        p.accessions,
    ):
        cik = r["issuer_cik"]
        if cik not in ours:
            continue
        pos = out.setdefault(cik, Position(filed=p.filed))
        sh = float(r["shares"]) if r["shares"] is not None else None
        v = float(r["value_usd"] or 0)
        if r["put_call"] or (r["share_type"] or "SH") != "SH":
            kind = r["put_call"] or r["share_type"]
            pos.apart.append(f"{kind} {r['title']} {sh or 0:,.0f} {'sh' if r['put_call'] else ''}"
                             .strip() + f" (${v:,.0f})")  # fmt: skip
            continue
        if r["status"] == "held":
            pos.held.append(r["check_note"] or "held by a check")
        pos.shares += sh or 0.0
        pos.value += v
        pos.rows += 1
        pos.titles.append(f"{r['title']} {r['cusip']}")
        pos.accessions.add(r["accession"])
        if r["accession"] != p.accession:
            pos.filed = max(pos.filed, filed_of[r["accession"]])
            pos.revealed.append(f"{r['accession']} filed {filed_of[r['accession']]}")
    return out


def unresolved_possibly(engine: sqlite3.Connection, p: Period, cik: str) -> list[str]:
    marks = ",".join("?" * len(p.accessions))
    return [
        f"{r['issuer_name']} (CUSIP {r['cusip']}, {float(r['shares'] or 0):,.0f} sh)"
        for r in engine.execute(
            f"SELECT * FROM fin_holding WHERE source = '13F' AND accession IN ({marks}) AND "
            "status = 'unresolved' AND check_note LIKE ?",
            [*p.accessions, f"%possibly ours:%{cik}%"],
        )
    ]


def quarter_ends_between(a: str, b: str) -> list[str]:
    """Quarter ends strictly between two quarter ends (the quarters with no stored 13F)."""
    out = []
    d = date.fromisoformat(a)
    while True:
        y, m = (d.year, d.month + 3) if d.month < 10 else (d.year + 1, 3)
        nxt = date(y, m, 30 if m in (6, 9) else 31)
        if nxt.isoformat() >= b:
            return out
        out.append(nxt.isoformat())
        d = nxt


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.3f}%"


@dataclass
class Event:
    manager: str
    filer: str
    cik: str
    period: str
    filed: str
    accession: str
    prior: str | None
    text: str | None = None
    delta: float | None = None
    cur: float = 0.0
    prev: float = 0.0
    value: float = 0.0
    pct_before: float | None = None
    pct_after: float | None = None
    pct_delta: float | None = None
    cover: str = ""
    missing: str | None = None
    notes: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)

    def line(self) -> str:
        days = _days(self.period, self.filed)
        lag = (f"lagged: quarter ended {self.period}, filed {self.filed} ({days} days later; "
               f"13F-HR is due {LAG_DAYS} days after the quarter)")  # fmt: skip
        if self.missing:
            return f"{self.manager}: missing — {self.missing}; {lag}"
        sign = "+" if (self.delta or 0) > 0 else ""
        out = (f"{self.manager}: {self.text} {sign}{self.delta:,.0f} sh ({self.prev:,.0f} → "
               f"{self.cur:,.0f} vs {self.prior}; {_pct(self.pct_before)} → {_pct(self.pct_after)}"
               f" of shares outstanding, Δ {_pct(self.pct_delta)}; cover {self.cover}; "
               f"${self.value:,.0f}); {lag}")  # fmt: skip
        return out + "".join(f"; {n}" for n in self.notes)


def manager_events(engine: sqlite3.Connection, name: str, filer: str, ours: dict[str, str],
                   markets: dict[str, Market]) -> list[Event]:  # fmt: skip
    """Every quarter-over-quarter event of one manager for our companies (oldest first)."""
    ps = periods(engine, filer)
    out: list[Event] = []
    prev_pos: dict[str, Position] | None = None
    for i, p in enumerate(ps):
        cur_pos = positions(engine, p, ours)
        if prev_pos is None:
            prev_pos = cur_pos  # the first stored quarter is the baseline
            continue
        pp = ps[i - 1]
        gap = quarter_ends_between(pp.period, p.period)
        for cik in sorted(set(cur_pos) | set(prev_pos)):
            c, b = cur_pos.get(cik), prev_pos.get(cik)
            cur, prev = (c.shares if c else 0.0), (b.shares if b else 0.0)
            if not cur and not prev:
                continue  # options or bonds only: listed on the panel, no direction
            mk = markets.setdefault(cik, Market(engine, cik))
            fa_p, fa_pp = mk.factor_after(p.period), mk.factor_after(pp.period)
            prev_adj = prev * fa_pp / fa_p if fa_p else prev
            delta = cur - prev_adj
            filed = c.filed if c else p.filed
            acc = p.accession
            e = Event(name, filer, cik, p.period, filed, acc, pp.period, cur=cur, prev=prev_adj,
                      value=c.value if c else 0.0)  # fmt: skip
            e.sources = [
                Source(acc, p.filed, "A", f"13F-HR {name} {p.period}"),
                Source(pp.accession, pp.filed, "A", f"13F-HR {name} {pp.period}"),
            ]
            e.sources += [
                Source(a.split(" ")[0], a.rsplit(" ", 1)[-1], "A", "13F-HR/A new holdings")
                for a in (c.revealed if c else [])
            ]
            if c and c.held:
                e.missing = f"row held by a check ({'; '.join(c.held)})"
            elif not c and (pending := unresolved_possibly(engine, p, cik)):
                e.missing = (f"row unresolved, possibly this company: {'; '.join(pending)} — map "
                             "its CUSIP in config/m07_managers.toml")  # fmt: skip
            else:
                e.delta = delta
                e.text = (
                    "new"
                    if not prev_adj
                    else "exit"
                    if not cur
                    else "hold"
                    if abs(delta) < 0.5
                    else "add"
                    if delta > 0
                    else "cut"
                )
                cov = mk.cover(filed)
                cov_b = mk.cover(pp.filed)
                e.cover = cov.text
                e.pct_after = cov.pct(cur * fa_p)
                e.pct_before = cov_b.pct(prev_adj * fa_p)
                e.pct_delta = cov.pct(delta * fa_p)
            if fa_pp != fa_p:
                e.notes.append(f"prior shares {prev:,.0f} × {fa_pp / fa_p:g} for a split between "
                               "the quarters")  # fmt: skip
            if gap:
                e.notes.append(f"no 13F stored for {', '.join(gap)} (missing, not an exit); "
                               f"compared with {pp.period}")  # fmt: skip
            if p.restates:
                e.notes.append(
                    "restatement: replaces " + ", ".join(f"{a} filed {f}" for a, f in p.restates)
                )
            if c and c.revealed:
                e.notes.append("revealed by a NEW HOLDINGS amendment (confidential treatment "
                               f"ended): {', '.join(c.revealed)}")  # fmt: skip
            if c and len({t.rsplit(" ", 1)[-1] for t in c.titles}) > 1:
                e.notes.append(f"classes summed: {', '.join(sorted(set(c.titles)))}")
            if c and c.apart:
                e.notes.append(f"apart, not in Δ: {'; '.join(c.apart)}")
            out.append(e)
        prev_pos = cur_pos
    return out


def followed(engine: sqlite3.Connection, cfg: ManagersConfig) -> list[Manager]:
    """Config managers with a CIK (config or stored name; never a network lookup)."""
    return [m for m in (resolve(engine, x) for x in cfg.managers) if m.cik]


@dataclass
class SignalPass:
    events: dict[str, list[Event]] = field(default_factory=dict)  # cik → events
    written: int = 0
    deleted: int = 0
    days: int = 0
    skipped: str = ""


def signal_pass(engine: sqlite3.Connection, managers: list[Manager], ours: dict[str, str],
                *, write: bool = True) -> SignalPass:  # fmt: skip
    """Recompute every `followed_manager_13f` row of our companies; rows no longer produced
    (a restated quarter's old day, a removed manager) are deleted. Own transaction."""
    out = SignalPass()
    markets: dict[str, Market] = {}
    for m in managers:
        for e in manager_events(engine, m.name, m.cik or "", ours, markets):
            out.events.setdefault(e.cik, []).append(e)
    if not write:
        return out
    engine.execute("BEGIN")
    try:
        for cik in sorted(ours):
            evs = out.events.get(cik, [])
            by_day: dict[str, list[Event]] = defaultdict(list)
            for e in evs:
                by_day[e.filed].append(e)
            for day, group in sorted(by_day.items()):
                out.written += _write_day(engine, cik, ours[cik], day, group)
                out.days += 1
            marks = ",".join("?" * len(by_day))
            out.deleted += engine.execute(
                "DELETE FROM signal WHERE cik = ? AND module_id = ? AND signal = ?"
                + (f" AND as_of NOT IN ({marks})" if by_day else ""),
                (cik, MODULE, SIGNAL, *sorted(by_day)),
            ).rowcount
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return out


def day_reading(group: list[Event]) -> tuple[float | None, str | None, str | None]:
    """(value, value_text, missing reason) of one company and filing day (rule 6)."""
    valid = [e for e in group if not e.missing]
    if not valid:
        return None, None, "; ".join(f"{e.manager}: {e.missing}" for e in group)
    texts = {e.text for e in valid}
    return sum(e.delta or 0.0 for e in valid), (texts.pop() if len(texts) == 1 else "mixed"), None


def _write_day(engine: sqlite3.Connection, cik: str, ticker: str, day: str,
               group: list[Event]) -> int:  # fmt: skip
    value, text, missing = day_reading(group)
    managers = sorted({e.manager for e in group})
    method = ("followed managers' 13F-HR (long positions only; soft, lagged; D-M07-6): "
              + " | ".join(e.line() for e in group)
              + (f"; same-day filings of {len(managers)} managers aggregated (rule 6)"
                 if len(managers) > 1 else "")
              + "; MY: soft vote (D-M07-6)")  # fmt: skip
    sources = [s for e in group for s in e.sources]
    if missing is not None:
        return write_signal(engine, cik=cik, ticker=ticker, module_id=MODULE, signal=SIGNAL,
                            as_of=day, method=method, sources=sources, info=("PT", "ST"),
                            missing=missing)  # fmt: skip
    return write_signal(engine, cik=cik, ticker=ticker, module_id=MODULE, signal=SIGNAL,
                        as_of=day, value=round(value or 0.0), value_text=text, method=method,
                        sources=sources, info=("PT", "ST"))  # fmt: skip


def _fingerprint(engine: sqlite3.Connection, managers: list[Manager], ours: dict[str, str],
                 cfg: ManagersConfig) -> str:  # fmt: skip
    ciks = sorted(m.cik for m in managers if m.cik)
    marks = ",".join("?" * len(ciks)) or "''"
    f13 = engine.execute(f"SELECT count(*), max(read_at) FROM fin_13f WHERE filer_cik IN ({marks})",
                         ciks).fetchone()  # fmt: skip
    hold = engine.execute(
        f"SELECT count(*), count(issuer_cik), sum(status = 'held') FROM fin_holding WHERE "
        f"source = '13F' AND filer_cik IN ({marks})",
        ciks,
    ).fetchone()
    return json.dumps({"filers": ciks, "f13": list(f13), "hold": list(hold),
                       "ours": sorted(ours), "cfg": cfg.text})  # fmt: skip


def record_pass(engine: sqlite3.Connection, managers: list[Manager], ours: dict[str, str],
                cfg: ManagersConfig, now: datetime) -> None:  # fmt: skip
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, 'M07', "
        "?, ?) ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
        "detail = excluded.detail",
        (PASS_STATE, iso(now), _fingerprint(engine, managers, ours, cfg)),
    )


def run_local_part(
    engine: sqlite3.Connection,
    ours: dict[str, str],
    now: datetime,
    *,
    path: Path = CONFIG,
    force: bool = False,
) -> list[str]:
    """Refresh local pass (0 SEC requests): the signal pass when a followed manager's stored
    13F rows (or the manager list) changed. Never raises."""
    head = "M07 followed managers — local pass (0 SEC requests)"
    try:
        cfg = load_config(path)
        if not cfg.managers:
            return [f"{head}: not run — no managers ({'; '.join(cfg.problems) or 'list empty'})"]
        managers = followed(engine, cfg)
        fp = _fingerprint(engine, managers, ours, cfg)
        prev = engine.execute("SELECT detail FROM refresh_state WHERE name = ?",
                              (PASS_STATE,)).fetchone()  # fmt: skip
        if not force and prev is not None and prev[0] == fp:
            return [f"{head}: unchanged (no new 13F rows of {len(managers)} manager(s))"]
        sp = signal_pass(engine, managers, ours)
        engine.execute(
            "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, 'M07', "
            "?, ?) ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
            "detail = excluded.detail",
            (PASS_STATE, iso(now), fp),
        )
        return [f"{head}: {len(managers)} manager(s); {sum(len(v) for v in sp.events.values())} "
                f"event(s) on {sp.days} company-day(s); signal rows written {sp.written}, "
                f"removed {sp.deleted}"]  # fmt: skip
    except Exception as e:  # must not break the refresh report
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        return [f"{head}: error — {type(e).__name__}: {e}"]


# --- Insiders tab panel (D-UI-34) -------------------------------------------------------------


@dataclass
class PanelRow:
    manager: str
    period: str
    filed: str
    lag: int
    shares: str
    value: str
    pct: str
    change: str
    text: str  # new | add | cut | exit | hold | baseline | missing
    notes: list[str]
    accession: str
    filer: str


@dataclass
class ManagerLine:
    name: str
    cik: str | None
    status: str


@dataclass
class ManagersPanel:
    rows: list[PanelRow] = field(default_factory=list)
    managers: list[ManagerLine] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    lag_note: str = (
        f"13F-HR: long positions only, filed up to {LAG_DAYS} days after the quarter "
        "end, so 2–3 months stale (lagged). Soft vote in MY, info in PT and ST "
        "(D-M07-6). A quarter without a stored 13F is missing, never an exit."
    )


def next_due(today: date) -> tuple[str, str]:
    """(latest quarter end whose 13F-HR is due by today, its due date)."""
    q = []
    for y in (today.year - 1, today.year):
        q += [date(y, 3, 31), date(y, 6, 30), date(y, 9, 30), date(y, 12, 31)]
    done = [d for d in q if d + timedelta(days=LAG_DAYS) <= today]
    d = done[-1]
    return d.isoformat(), (d + timedelta(days=LAG_DAYS)).isoformat()


def panel(engine: sqlite3.Connection, cik: str, today: date, *, path: Path = CONFIG,
          per_manager: int = 8) -> ManagersPanel:  # fmt: skip
    """Followed managers (lagged) for one company, built from stored rows."""
    out = ManagersPanel()
    cfg = load_config(path)
    out.problems += cfg.problems
    ours = {cik: ""}
    markets: dict[str, Market] = {}
    due_q, due_day = next_due(today)
    for m in (resolve(engine, x) for x in cfg.managers):
        if not m.cik:
            out.managers.append(ManagerLine(m.name, None, m.how))
            continue
        ps = periods(engine, m.cik)
        if not ps:
            out.managers.append(ManagerLine(m.name, m.cik, "no 13F-HR stored yet (run "
                                            "scripts/run_ownership.py managers)"))  # fmt: skip
            continue
        gaps = [q for a, b in zip(ps, ps[1:], strict=False)
                for q in quarter_ends_between(a.period, b.period)]  # fmt: skip
        status = f"{len(ps)} quarter(s) stored, {ps[0].period} to {ps[-1].period}"
        if ps[-1].period < due_q:
            status += f"; no 13F stored for {due_q} (due {due_day}): missing"
        if gaps:
            status += f"; missing quarters: {', '.join(gaps)}"
        out.managers.append(ManagerLine(m.name, m.cik, status))
        events = {e.period: e for e in manager_events(engine, m.name, m.cik, ours, markets)}
        rows: list[PanelRow] = []
        for i, p in enumerate(ps):
            pos = positions(engine, p, ours).get(cik)
            e = events.get(p.period)
            pending = unresolved_possibly(engine, p, cik)
            if pos is None and e is None and not pending:
                continue
            mk = markets.setdefault(cik, Market(engine, cik))
            shares = pos.shares if pos else 0.0
            pct = mk.cover(pos.filed if pos else p.filed).pct(shares * mk.factor_after(p.period))
            notes = list(e.notes) if e else []
            if pos and pos.apart and not e:
                notes.append(f"apart, not in Δ: {'; '.join(pos.apart)}")
            if pending and not e:
                notes.append(f"unresolved, possibly this company: {'; '.join(pending)}")
            if e is None:
                text = "baseline" if i == 0 else "—"
                change = "first stored quarter" if i == 0 else "—"
            elif e.missing:
                text, change = "missing", e.missing
            else:
                text = e.text or "—"
                change = f"{'+' if (e.delta or 0) > 0 else ''}{e.delta:,.0f} sh vs {e.prior}"
                if e.pct_delta is not None:
                    change += f" (Δ {_pct(e.pct_delta)} of shares outstanding)"
            filed = e.filed if e else (pos.filed if pos else p.filed)
            rows.append(PanelRow(
                m.name, p.period, filed, _days(p.period, filed), f"{shares:,.0f}",
                f"${pos.value:,.0f}" if pos else "—", _pct(pct), change, text, notes,
                p.accession, m.cik,
            ))  # fmt: skip
        out.rows += list(reversed(rows))[:per_manager]
    return out
