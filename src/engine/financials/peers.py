"""Ranked SIC peer shortlist (D-M04-4, S6.2; M04 Part 1c).

- **Listed:** the companies EDGAR's browse-by-SIC lists under the target's 4-digit SIC
  (`sec/browse.py`, one browse per SIC, capped at 10 pages; the form parameter does not
  filter the list, live check 1).
- **Active:** a 10-K, 20-F or 40-F (amendments and 10-KT included) filed in the last 12
  months, read from the stored quarterly form indexes (0 requests). A 10-K-only filter
  would drop foreign filers such as GlobalFoundries (PROBE_RESULTS S1). Quarters of the
  12-month window missing from the stored index are named (active count partial).
- **Ranked** by revenue closeness to the target, |ln(peer ÷ target)|, on calendar-year
  revenue from 3 XBRL frames (us-gaap RevenueFromContractWithCustomerExcludingAssessedTax,
  us-gaap Revenues, ifrs-full Revenue; USD). Active names without a frame value follow,
  marked "revenue missing". The shortlist is the top `SHORTLIST`† per target.
- **Revenue suspect** (live check 1: TIGO ENERGY at 103.5B, a scaling error in its filing):
  CY ÷ CY−1 frame value (the 2 us-gaap tags) above 10× or below 0.1×, or the CY frame value
  more than 10× off the company's own stored fiscal-year revenue nearest the frame period
  (when facts exist). Suspect names keep their value, are ranked after the valued ones
  (before "revenue missing") and are marked, never dropped.
- **Owner:** one `m04_peer` item per target from the shortlist only (setup batch, outside
  the weekly cap, D-M04-71): strike names, add product-market peers outside the SIC
  (WDC and QCOM for MU), store non-SEC peers by name ("missing: not an SEC filer": SK
  hynix, Samsung), confirm. Confirmed sets go to `peer_group` / `peer_member`.
- A model tag overrides SIC (D-M04-8): a tagged company (MSTR `asset_treasury`, SIC 6199)
  gets no SIC shortlist, only owner-added peers; `fund` / `financial` get no peer item.

Part 2 — matching peer periods in time (D-M04-5):

- **Offsets:** 12-month flows (fiscal year or TTM) count when the peer's period ends within
  ±45 days† of the company's; quarters and balance-sheet instants within ±40 days†. The
  closest end inside the tolerance is used and its offset shown. Outside → "no comparable
  period" (missing, counted toward the < 5 fallback, D-M04-52); when the peer's latest
  period ends before the company's and its next quarter would land inside the tolerance,
  the note reads "awaiting peer filing" (WDC 62 days behind Micron until 2023-11-07).
- **53-week year:** a 12-month period of 370 days or more (52 weeks = 364) is flagged; it
  adds about 2% to flows (AMD FY2022, NVIDIA FY2018).
- **Acquisition year:** flagged when, in the 12 months to the matched end, cash paid for
  businesses (`PaymentsToAcquireBusinessesNetOfCashAcquired`) is at least 10%† of revenue,
  or goodwill rose by at least 10%† of revenue against a year earlier — the second test
  catches stock deals that pay little cash (AMD FY2022: Xilinx, goodwill 289M → 24.2B).
  Flags inform; the peer stays in the comparison.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from engine.sec.client import SecClient, iso
from engine.sec.frames import fetch_frame
from engine.sec.identity import normalize_cik
from engine.sec.results import Ok
from engine.sec.xbrl_facts import Concept

SHORTLIST = 10  # starting value per target
ACTIVE_DAYS = 365
REVENUE_FRAMES = (
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    ("us-gaap", "Revenues"),
    ("ifrs-full", "Revenue"),
)
PRIOR_FRAMES = REVENUE_FRAMES[:2]  # CY−1 for the suspect guard (ifrs-full CY2025 was a 404)
SUSPECT_RATIO = 10.0
SUSPECT = "revenue suspect: "
NOT_SEC = "missing: not an SEC filer"


class PeerError(ValueError):
    """An owner peer entry cannot be stored (unknown ticker, duplicate)."""


def frame_year(today: date) -> int:
    """The latest calendar year whose annual frame is mostly filed (10-Ks by ~April)."""
    return today.year - 1 if today.month >= 5 else today.year - 2


# --- Inputs ----------------------------------------------------------------------------------


def fetch_revenue_frames(
    client: SecClient, engine: sqlite3.Connection, year: int, now: datetime
) -> list[str]:
    """Store the 3 revenue frames for CY<year> (ranking) and the 2 us-gaap frames for
    CY<year−1> (suspect guard); each re-used for 30 days. Lines for the log."""
    lines = []
    for y, frames in ((year, REVENUE_FRAMES), (year - 1, PRIOR_FRAMES)):
        for tax, tag in frames:
            res = fetch_frame(client, engine, tax, tag, "USD", f"CY{y}", now)
            if isinstance(res, Ok):
                lines.append(f"  frame {tax}:{tag} USD CY{y}: {res.data:,} companies"
                             + (" (stored, re-used)" if res.from_cache else ""))  # fmt: skip
            else:
                lines.append(f"  frame {tax}:{tag} USD CY{y}: {res}")
    return lines


def money(v: float) -> str:
    return f"{v / 1e9:,.1f}B" if abs(v) >= 1e9 else f"{v / 1e6:,.1f}M"


def _off(a: float, b: float) -> bool:
    return a > 0 and b > 0 and not (1 / SUSPECT_RATIO <= a / b <= SUSPECT_RATIO)


def revenue_suspect(
    engine: sqlite3.Connection, cik: str, year: int, value: float, as_of: str,
    prior: dict[str, tuple[float, str]] | None = None,
) -> str:  # fmt: skip
    """Why a CY<year> frame revenue looks wrong ("" when it does not): a > 10× jump or
    drop against CY<year−1>, or > 10× off the company's own stored fiscal-year revenue."""
    prior = frame_revenue(engine, year - 1, PRIOR_FRAMES) if prior is None else prior
    p = prior.get(cik)
    if p and _off(value, p[0]):
        return f"CY{year} {money(value)} vs CY{year - 1} {money(p[0])}"
    from engine.financials.capex import fy_points

    pts = fy_points(engine, cik, "revenue", as_of)
    if pts:
        row = engine.execute(
            "SELECT period_end FROM frame_value WHERE cik = ? AND frame = ? AND unit = 'USD' "
            "AND period_end IS NOT NULL LIMIT 1",
            (cik, f"CY{year}"),
        ).fetchone()
        end = date.fromisoformat(row[0]) if row else date(year, 12, 31)
        near = min(pts.values(), key=lambda q: abs((date.fromisoformat(q.end) - end).days))
        if abs((date.fromisoformat(near.end) - end).days) <= 200 and _off(value, near.value):
            return f"CY{year} {money(value)} vs stored FY to {near.end} {money(near.value)}"
    return ""


def frame_revenue(
    engine: sqlite3.Connection, year: int, frames: tuple[tuple[str, str], ...] = REVENUE_FRAMES
) -> dict[str, tuple[float, str]]:
    """cik → (revenue, reference) from the stored frames, first tag in `frames` wins."""
    out: dict[str, tuple[float, str]] = {}
    for tax, tag in frames:
        for r in engine.execute(
            "SELECT cik, value, accession FROM frame_value WHERE taxonomy = ? AND tag = ? "
            "AND unit = 'USD' AND frame = ?",
            (tax, tag, f"CY{year}"),
        ):
            out.setdefault(
                r["cik"],
                (float(r["value"]), f"CY{year} {tax}:{tag} {r['accession'] or ''}".strip()),
            )
    return out  # fmt: skip


def own_revenue(engine: sqlite3.Connection, cik: str, as_of: str) -> tuple[float, str] | None:
    from engine.financials.capex import fy_points

    pts = fy_points(engine, cik, "revenue", as_of)
    if not pts:
        return None
    p = pts[max(pts)]
    return float(p.value), f"FY to {p.end} {p.method} {p.accession}"


def active_filers(
    engine: sqlite3.Connection, ciks: Iterable[str], today: date
) -> dict[str, tuple[str, str]]:
    """cik → (form, filed) of the latest 10-K/20-F/40-F (incl. amendments, 10-KT) in the
    last 12 months, from the stored form indexes."""
    wanted = {normalize_cik(c) or c for c in ciks}
    since = (today - timedelta(days=ACTIVE_DAYS)).isoformat()
    out: dict[str, tuple[str, str]] = {}
    for r in engine.execute(
        "SELECT cik, form, filed FROM form_filing WHERE family IN ('10-K', '20-F') "
        "AND filed >= ? ORDER BY filed",
        (since,),
    ):
        if r["cik"] in wanted:
            out[r["cik"]] = (r["form"], r["filed"])
    return out


def index_gaps(engine: sqlite3.Connection, today: date) -> list[str]:
    """Quarters of the last 12 months missing from the stored form indexes."""
    since = today - timedelta(days=ACTIVE_DAYS)
    have = {(r[0], r[1]) for r in engine.execute("SELECT year, quarter FROM form_index")}
    gaps, y, q = [], since.year, (since.month - 1) // 3 + 1
    while (y, q) <= (today.year, (today.month - 1) // 3 + 1):
        if (y, q) not in have:
            gaps.append(f"{y}Q{q}")
        y, q = (y, q + 1) if q < 4 else (y + 1, 1)
    return gaps


# --- Shortlist -------------------------------------------------------------------------------


@dataclass
class Candidate:
    cik: str | None
    name: str
    sic: str | None
    rank: int | None
    active: str  # "10-K 2026-02-20"
    revenue: float | None
    revenue_ref: str
    source: str = "sic"
    status: str = "proposed"

    @property
    def key(self) -> str:
        return self.cik or f"name:{self.name}"

    @property
    def suspect(self) -> str:
        """The suspect-revenue reason stored at the head of revenue_ref, or ""."""
        if not self.revenue_ref.startswith(SUSPECT):
            return ""
        return self.revenue_ref[len(SUSPECT) :].split(" · ")[0]


@dataclass
class Shortlist:
    target: str
    sic: str | None
    listed: int
    active: int
    target_revenue: float | None
    target_revenue_ref: str
    candidates: list[Candidate] = field(default_factory=list)
    note: str = ""
    suspects: list[tuple[str, str]] = field(default_factory=list)  # (name, why), whole pool


def shortlist(
    engine: sqlite3.Connection,
    target: str,
    sic: str | None,
    today: date,
    *,
    year: int | None = None,
    n: int = SHORTLIST,
    exclude: Iterable[str] = (),
) -> Shortlist:
    """Rank the active companies listed under the target's SIC by revenue closeness."""
    target = normalize_cik(target) or target
    year = year or frame_year(today)
    listed = {r["cik"]: r["name"] for r in engine.execute(
        "SELECT cik, name FROM sic_listing WHERE sic = ?", (sic,))} if sic else {}  # fmt: skip
    active = active_filers(engine, listed, today)
    revenue = frame_revenue(engine, year)
    tv = revenue.get(target) or own_revenue(engine, target, today.isoformat())
    out = Shortlist(target, sic, len(listed), len(active), tv[0] if tv else None,
                    tv[1] if tv else "missing: no revenue")  # fmt: skip
    if not sic:
        out.note = "missing: no SIC stored for the company"
        return out
    if not listed:
        out.note = f"missing: SIC {sic} not browsed yet (run_financials.py profile)"
        return out
    skip = {target} | {normalize_cik(c) or c for c in exclude}
    prior = frame_revenue(engine, year - 1, PRIOR_FRAMES)
    pool = []
    for cik, (form, filed) in active.items():
        if cik in skip:
            continue
        rv = revenue.get(cik)
        dist, why = None, ""
        if rv:
            why = revenue_suspect(engine, cik, year, rv[0], today.isoformat(), prior)
        if rv and rv[0] > 0 and out.target_revenue and out.target_revenue > 0:
            dist = abs(math.log(rv[0] / out.target_revenue))
        if why:
            out.suspects.append((listed[cik], why))
        # valued (by closeness) → revenue suspect (by closeness) → revenue missing (by name)
        tier = (0 if dist is not None else 2) + (1 if why else 0)
        pool.append((tier, dist if dist is not None else 0.0, listed[cik], cik, form, filed, rv,
                     why))  # fmt: skip
    pool.sort(key=lambda t: t[:3])
    out.suspects.sort()
    for i, (_, _, name, cik, form, filed, rv, why) in enumerate(pool[:n], 1):
        ref = rv[1] if rv else f"missing: no CY{year} revenue frame value"
        out.candidates.append(Candidate(cik, name, sic, i, f"{form} {filed}",
                                        rv[0] if rv else None,
                                        f"{SUSPECT}{why} · {ref}" if why else ref))  # fmt: skip
    if out.target_revenue is None:
        out.note = "target revenue missing: ranked by name"
    return out


def store_shortlist(engine: sqlite3.Connection, s: Shortlist, now: datetime) -> str:
    """Replace the target's proposed SIC candidates (owner rows and decisions are kept).
    A target whose set is already confirmed only gains new names. Returns 'replaced' or
    'confirmed'. Caller owns the transaction."""
    ts = iso(now)
    done = engine.execute("SELECT 1 FROM peer_candidate WHERE target_cik = ? AND status = "
                          "'confirmed' LIMIT 1", (s.target,)).fetchone()  # fmt: skip
    if not done:
        engine.execute("DELETE FROM peer_candidate WHERE target_cik = ? AND source = 'sic' AND "
                       "status = 'proposed'", (s.target,))  # fmt: skip
    for c in s.candidates:
        engine.execute(
            "INSERT INTO peer_candidate (target_cik, candidate_cik, name, sic, rank, "
            "active_forms, revenue, revenue_ref, source, status, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'sic', 'proposed', ?) "
            "ON CONFLICT DO NOTHING",
            (s.target, c.cik, c.name, c.sic, c.rank, c.active, c.revenue, c.revenue_ref, ts),
        )
    return "confirmed" if done else "replaced"


def candidates(engine: sqlite3.Connection, target: str) -> list[Candidate]:
    rows = engine.execute(
        "SELECT * FROM peer_candidate WHERE target_cik = ? ORDER BY source = 'sic' DESC, "
        "rank IS NULL, rank, name",
        (normalize_cik(target) or target,),
    ).fetchall()
    return [Candidate(r["candidate_cik"], r["name"], r["sic"], r["rank"], r["active_forms"] or "",
                      r["revenue"], r["revenue_ref"] or "", r["source"], r["status"])
            for r in rows]  # fmt: skip


# --- Owner actions ---------------------------------------------------------------------------


def add_peer(
    engine: sqlite3.Connection, target: str, text: str, not_sec: bool, now: datetime,
    today: date | None = None,
) -> Candidate:  # fmt: skip
    """The owner's peer: a ticker or CIK (any SIC), or a non-SEC company by name."""
    target = normalize_cik(target) or target
    text = " ".join(text.split())
    if not text:
        raise PeerError("Enter a ticker, a CIK, or a company name.")
    ts = iso(now)
    if not_sec:
        if engine.execute("SELECT 1 FROM peer_candidate WHERE target_cik = ? AND name = ?",
                          (target, text)).fetchone():  # fmt: skip
            raise PeerError(f"{text} is already listed.")
        engine.execute(
            "INSERT INTO peer_candidate (target_cik, candidate_cik, name, sic, rank, active_forms, "
            "revenue, revenue_ref, source, status, added_at) VALUES (?, NULL, ?, NULL, NULL, NULL, "
            "NULL, ?, 'owner_name', 'proposed', ?)",
            (target, text, NOT_SEC, ts),
        )
        return Candidate(None, text, None, None, "", None, NOT_SEC, "owner_name")
    cik = normalize_cik(text) if text.isdigit() else None
    if cik is None:
        row = engine.execute(
            "SELECT cik FROM ticker WHERE upper(ticker) = upper(?) AND valid_to IS NULL "
            "ORDER BY valid_from DESC LIMIT 1",
            (text,),
        ).fetchone()
        if row is None:
            raise PeerError(f"Unknown ticker {text!r}. Tick 'not an SEC filer' to store it by "
                            "name.")  # fmt: skip
        cik = row["cik"]
    if cik == target:
        raise PeerError("That is the company itself.")
    ent = engine.execute("SELECT name, sic FROM entity WHERE cik = ?", (cik,)).fetchone()
    tick = engine.execute("SELECT ticker, name FROM ticker WHERE cik = ? AND valid_to IS NULL "
                          "LIMIT 1", (cik,)).fetchone()  # fmt: skip
    name = (ent["name"] if ent else None) or (tick["name"] if tick and tick["name"] else None) \
        or (tick["ticker"] if tick else cik)  # fmt: skip
    sic = ent["sic"] if ent else None
    day = today or now.date()
    act = active_filers(engine, [cik], day).get(cik)
    rev = frame_revenue(engine, frame_year(day)).get(cik)
    old = engine.execute("SELECT status, source FROM peer_candidate WHERE target_cik = ? AND "
                         "candidate_cik = ?", (target, cik)).fetchone()  # fmt: skip
    if old is not None:
        if old["status"] == "struck":  # adding a struck name back keeps it
            engine.execute(
                "UPDATE peer_candidate SET status = 'proposed', decided_at = ? "
                "WHERE target_cik = ? AND candidate_cik = ?",
                (ts, target, cik),
            )
            return Candidate(cik, name, sic, None, "", None, "", old["source"])
        raise PeerError(f"{name} is already listed.")
    engine.execute(
        "INSERT INTO peer_candidate (target_cik, candidate_cik, name, sic, rank, active_forms, "
        "revenue, revenue_ref, source, status, added_at) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, "
        "'owner', 'proposed', ?)",
        (target, cik, name, sic, f"{act[0]} {act[1]}" if act else "none in 12 months",
         rev[0] if rev else None, rev[1] if rev else "missing: no revenue frame value", ts),
    )  # fmt: skip
    return Candidate(cik, name, sic, None, "", None, "", "owner")


def confirm(
    engine: sqlite3.Connection, target: str, keep: Iterable[str], by: str, now: datetime
) -> tuple[int, int, int]:
    """Kept candidates → confirmed, the rest → struck; the confirmed set replaces the
    target's `peer_group` members. Returns (kept, struck, owner-added kept)."""
    target = normalize_cik(target) or target
    keep = set(keep)
    ts = iso(now)
    rows = candidates(engine, target)
    kept = struck = added = 0
    for c in rows:
        status = "confirmed" if c.key in keep else "struck"
        engine.execute(
            "UPDATE peer_candidate SET status = ?, decided_at = ? WHERE target_cik = ? AND "
            + ("candidate_cik = ?" if c.cik else "candidate_cik IS NULL AND name = ?"),
            (status, ts, target, c.cik or c.name),
        )
        if status == "confirmed":
            kept += 1
            added += c.source != "sic"
        else:
            struck += 1
    sic = engine.execute("SELECT sic FROM entity WHERE cik = ?", (target,)).fetchone()
    name = f"M04 peers {target}"
    engine.execute(
        "INSERT INTO peer_group (name, source, sic, created_at) VALUES (?, 'sic', ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET sic = excluded.sic",
        (name, sic[0] if sic else None, ts),
    )
    gid = engine.execute("SELECT group_id FROM peer_group WHERE name = ?", (name,)).fetchone()[0]
    engine.execute("DELETE FROM peer_member WHERE group_id = ?", (gid,))
    for c in rows:
        if c.key in keep:
            engine.execute(
                "INSERT INTO peer_member (group_id, cik, name, source) VALUES (?, ?, ?, ?)",
                (gid, c.cik, c.name, "sic" if c.source == "sic" else "owner"),
            )
    return kept, struck, added


TTM_TOL = 45  # days, 12-month flows (D-M04-5 starting value)
POINT_TOL = 40  # days, quarters and instants (D-M04-5 starting value)
WEEK53_DAYS = 370
ACQ_SHARE = 0.10  # starting value: acquisition spend or goodwill rise ÷ revenue
NO_PERIOD = "no comparable period"
GOODWILL = Concept("goodwill", (("us-gaap", "Goodwill"), ("ifrs-full", "Goodwill")),
                   "currency", "instant")  # fmt: skip


@dataclass(frozen=True)
class Match:
    end: str | None  # the peer period end used; None = not comparable
    offset: int | None  # days, peer end − company end
    note: str  # "awaiting peer filing: …", "latest period ends N days before", ""
    latest: str | None  # the peer's latest period end of this kind

    @property
    def ok(self) -> bool:
        return self.end is not None


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(a) - date.fromisoformat(b)).days


def match_period(ends: Iterable[str], ref: str, tol: int = TTM_TOL) -> Match:
    """The peer period end closest to `ref` within ±tol days (D-M04-5)."""
    ends = sorted(set(ends))
    latest = ends[-1] if ends else None
    near_ = [(abs(_days(e, ref)), e) for e in ends if abs(_days(e, ref)) <= tol]
    if near_:
        _, e = min(near_)
        return Match(e, _days(e, ref), "", latest)
    if latest is None:
        return Match(None, None, "no period stored", None)
    gap = _days(ref, latest)
    if gap > 0:
        if gap <= 92 + tol:
            return Match(None, -gap, f"awaiting peer filing: latest period ends {gap} days before",
                         latest)  # fmt: skip
        return Match(None, -gap, f"latest period ends {gap} days before", latest)
    first = ends[0]
    return Match(None, _days(first, ref), f"periods start {_days(first, ref)} days after", latest)


def week53(start: str | None, end: str) -> bool:
    """A 12-month period of 370 days or more (a 53-week fiscal year)."""
    return start is not None and _days(end, start) + 1 >= WEEK53_DAYS


def acquisition_note(
    revenue: float | None,
    acquisitions: float | None,
    goodwill_now: float | None,
    goodwill_before: float | None,
) -> str:
    """'acquisition year: …' when cash for businesses or the goodwill rise is ≥ 10%† of
    the 12-month revenue; '' otherwise (or when revenue is missing)."""
    if not revenue or revenue <= 0:
        return ""
    parts = []
    if acquisitions is not None and acquisitions >= ACQ_SHARE * revenue:
        parts.append(f"cash for businesses {money(acquisitions)} ({acquisitions / revenue:.0%} "
                     "of revenue)")  # fmt: skip
    if goodwill_now is not None and goodwill_before is not None:
        rise = goodwill_now - goodwill_before
        if rise >= ACQ_SHARE * revenue:
            parts.append(f"goodwill {money(goodwill_before)} → {money(goodwill_now)} "
                         f"(+{rise / revenue:.0%} of revenue)")  # fmt: skip
    return ("acquisition year: " + "; ".join(parts)) if parts else ""


def confirmed_peers(engine: sqlite3.Connection, target: str) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT m.cik, m.name, m.source FROM peer_member m JOIN peer_group g ON g.group_id = "
        "m.group_id WHERE g.name = ? ORDER BY m.source DESC, m.name",
        (f"M04 peers {normalize_cik(target) or target}",),
    ).fetchall()
