"""Peer robust z on the core trend rows (D-M04-11, -29, -52; M04 Part 2).

For one company and its confirmed peer set (`peer_facts.peer_set`), every core trend row
is computed the same way for the company and for each peer, at matched periods:

- **Latest 12 months** (`rev_yoy`, gross margin, `gm_trend_pp`, `opex_vs_sales`): the
  company's latest 12-month period (TTM or fiscal year, whichever ends later — the basis
  of the signals); a peer's 12-month period counts within ±45 days† (D-M04-5).
- **Latest fiscal year** (`rev_cagr3`, `fcf_growth`, `fcf_growth_oe`): the company's
  latest fiscal year (the trend table's last column); peers' 12-month periods ±45 days†.
- **ROIC:** balance-sheet instants, so the peer's fiscal year end must lie within ±40
  days† of the company's.
- **Capex rows** (`fcf_growth`, `fcf_growth_oe`): PP&E tag only for the company and every
  peer (D-M04-3); NVIDIA and Amazon are "not like-for-like" and excluded in every year
  (SB.18), as is any peer without a PP&E-tag value; when the company itself is one of them
  the row reads missing. Owner earnings for the comparison = OCF − min(depreciation, else
  D&A, PP&E capex) − SBC.
- Dollar rows (FCF and owner earnings in $) are not compared across companies of different
  size: "not compared: dollar level".

Statistics per `stats.robust_z` (D-M04-52); peers outside the tolerance, without facts or
without a value are listed with the reason and count toward the < 5 fallback. Results are
information rows (no vote until Part 8, D-M04-11); the signal method carries the peer text.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from engine.financials import capex as capex_mod
from engine.financials import peer_facts, peers, stats, trends
from engine.financials.capex import at, fy_points
from engine.financials.trends import NM, Cell
from engine.sec.asof import AsOfPoint, facts_as_of
from engine.sec.identity import normalize_cik

# Excluded from peer capex statistics in every year (D-M04-3, SB.18): NVIDIA has no
# PP&E-only capex tag in any year; Amazon's capex is on the broader (fallback) tag.
NOT_LIKE_FOR_LIKE = {"0001045810": "NVIDIA", "0001018724": "Amazon"}
NO_PEERS = "no peers confirmed"  # the owner confirmed an empty set (not the fallback)
CAPEX_NOTE = "PP&E tag only; NVDA/AMZN not like-for-like, excluded (D-M04-3)"
PPE_CAPEX = capex_mod._concept("capex_ppe", capex_mod.PPE_TAGS)
DA = capex_mod._concept("d_and_a", capex_mod.DA_TAGS)


def twelve(engine: sqlite3.Connection, cik: str, concept, as_of: str) -> dict[str, AsOfPoint]:
    """12-month points by end: fiscal years (at the fiscal year end) and TTM; a fiscal
    year wins over a TTM point ending within ten days of it."""
    fy = fy_points(engine, cik, concept, as_of)
    ttm = fy_points(engine, cik, concept, as_of, "TTM")
    out = {e: p for e, p in ttm.items() if at(fy, e) is None}
    out.update(fy)
    return dict(sorted(out.items()))


class Facts:
    """One company's points, read once per pass (peers recur across peer sets)."""

    def __init__(self, engine: sqlite3.Connection, cik: str, as_of: str) -> None:
        self.cik = normalize_cik(cik) or cik
        c = self.cik
        self.rev = twelve(engine, c, "revenue", as_of)
        self.gp = twelve(engine, c, "gross_profit", as_of)
        self.cost = twelve(engine, c, "cost_of_revenue", as_of)
        self.oi = twelve(engine, c, "operating_income", as_of)
        self.ocf = twelve(engine, c, "operating_cash_flow", as_of)
        self.capex = twelve(engine, c, PPE_CAPEX, as_of)
        self.dep = twelve(engine, c, "depreciation", as_of)
        self.da = twelve(engine, c, DA, as_of)
        self.sbc = twelve(engine, c, "sbc", as_of)
        self.acq = twelve(engine, c, "acquisitions", as_of)
        self.goodwill = {p.end: p for p in facts_as_of(engine, c, peers.GOODWILL, as_of,
                                                       ptype="I").points}  # fmt: skip
        self.fy_rev = fy_points(engine, c, "revenue", as_of)
        self.fy_oi = fy_points(engine, c, "operating_income", as_of)
        self.ric = trends.roic_inputs(engine, c, as_of)

    @property
    def empty(self) -> bool:
        return not self.rev


def _v(points: dict[str, AsOfPoint], end: str | None) -> float | None:
    if end is None:
        return None
    p = at(points, end)
    return float(p.value) if p is not None else None


def _prior_end(points: dict[str, AsOfPoint], end: str, days=(350, 380)) -> str | None:
    p = trends._prior(points, end, days)
    return p.end if p is not None else None


def _gross(f: Facts, end: str) -> float | None:
    g = _v(f.gp, end)
    if g is not None:
        return g
    r, c = _v(f.rev, end), _v(f.cost, end)
    return r - c if r is not None and c is not None else None


def _gm(f: Facts, end: str | None) -> float | None:
    if end is None:
        return None
    g, r = _gross(f, end), _v(f.rev, end)
    return g / r * 100 if g is not None and r else None


def m_rev_yoy(f: Facts, end: str) -> Cell:
    return trends._growth(_v(f.rev, end), _v(f.rev, _prior_end(f.rev, end)))


def m_rev_cagr3(f: Facts, end: str) -> Cell:
    c = trends._growth(_v(f.rev, end), _v(f.rev, _prior_end(f.rev, end, (1080, 1110))))
    return Cell((1 + c.value) ** (1 / 3) - 1) if c.value is not None else c


def m_gm(f: Facts, end: str) -> Cell:
    v = _gm(f, end)
    return Cell(v) if v is not None else Cell(None, "missing: gross profit or cost of revenue")


def m_gm_trend(f: Facts, end: str) -> Cell:
    a, b = _gm(f, end), _gm(f, _prior_end(f.rev, end))
    return Cell(a - b) if a is not None and b is not None else Cell(None, "missing: gross margin")


def m_opex(f: Facts, end: str) -> Cell:
    p = _prior_end(f.rev, end)
    if p is None:
        return Cell(None, "missing: no base year")
    g1, g0, o1, o0 = _gross(f, end), _gross(f, p), _v(f.oi, end), _v(f.oi, p)
    if None in (g1, g0, o1, o0):
        return Cell(None, "missing: gross profit or operating income")
    go = trends._growth(g1 - o1, g0 - o0)
    gr = trends._growth(_v(f.rev, end), _v(f.rev, p))
    if go.value is None or gr.value is None:
        return Cell(None, go.text or gr.text)
    return Cell((go.value - gr.value) * 100)


def _fcf(f: Facts, end: str) -> float | None:
    o, c = _v(f.ocf, end), _v(f.capex, end)
    return o - c if o is not None and c is not None else None


def _oe(f: Facts, end: str) -> float | None:
    o, c, s = _v(f.ocf, end), _v(f.capex, end), _v(f.sbc, end)
    d = _v(f.dep, end)
    d = d if d is not None else _v(f.da, end)
    if None in (o, c, s, d):
        return None
    return o - min(d, c) - s


def _capex_growth(fn):
    def metric(f: Facts, end: str) -> Cell:
        if _v(f.capex, end) is None:
            return Cell(None, f"missing: no PP&E-tag capex at {end} (not like-for-like)")
        p = _prior_end(f.rev, end) or _prior_end(f.capex, end)
        if p is None or _v(f.capex, p) is None:
            return Cell(None, "missing: no PP&E-tag capex a year earlier")
        now, base = fn(f, end), fn(f, p)
        if now is None or base is None:
            return Cell(None, "missing: OCF, SBC or depreciation")
        return trends._growth(now, base, _v(f.rev, p))

    return metric


def m_roic(f: Facts, end: str) -> Cell:
    prev = _prior_end(f.fy_oi, end) or _prior_end(f.fy_rev, end)
    return trends.roic(f.ric, end, prev, f.fy_oi)


@dataclass(frozen=True)
class RowDef:
    key: str
    basis: str  # r12 | fy | fy_point
    scale: float  # × to percent / pp
    median_unit: str
    metric: object


ROWS = (
    RowDef("rev_yoy", "r12", 100, "%", m_rev_yoy),
    RowDef("rev_cagr3", "fy", 100, "%", m_rev_cagr3),
    RowDef("fcf_growth", "fy", 100, "%", _capex_growth(_fcf)),
    RowDef("fcf_growth_oe", "fy", 100, "%", _capex_growth(_oe)),
    RowDef("gm", "r12", 1, "%", m_gm),
    RowDef("gm_trend_pp", "r12", 1, " pp", m_gm_trend),
    RowDef("opex_vs_sales", "r12", 1, " pp", m_opex),
    RowDef("roic", "fy_point", 100, "%", m_roic),
)
DOLLAR_ROWS = {"fcf_total": "not compared: dollar level", "owner_earnings":
               "not compared: dollar level"}  # fmt: skip
CAPEX_ROWS = {"fcf_growth", "fcf_growth_oe"}


@dataclass
class Member:
    name: str
    cik: str | None
    end: str | None
    offset: int | None
    value: float | None
    included: bool
    why: str = ""
    flags: list[str] = field(default_factory=list)


@dataclass
class PeerRow:
    key: str
    basis: str  # text: "12 months to 2022-12-31; peers ±45 d"
    company: Cell
    result: stats.RobustZ | None = None
    members: list[Member] = field(default_factory=list)
    missing: str = ""
    note: str = ""
    scale: float = 1.0
    median_unit: str = "%"

    def text(self) -> str:
        """The peer text for a signal method or the table's method column."""
        if self.missing:
            return f"peer z: missing: {self.missing}"
        r = self.result
        out = f"peer z ({self.basis}): " + r.text(self.scale, self.median_unit)
        if self.note:
            out += f"; {self.note}"
        out_n = [m.name for m in self.members if not m.included]
        if out_n:
            out += f"; not in comparison: {len(out_n)}"
        return out


@dataclass
class PeerLine:
    name: str
    cik: str | None
    latest_end: str | None
    offset: int | None
    in_comparison: str
    note: str


@dataclass
class Comparison:
    ticker: str
    cik: str
    confirmed: bool
    ref_end: str | None  # the company's latest 12-month end
    rows: dict[str, PeerRow] = field(default_factory=dict)
    lines: list[PeerLine] = field(default_factory=list)
    status: str = ""  # "peers not confirmed on the M04 setup page", "", …

    def signal_text(self, key: str) -> str:
        if self.status:
            return f"peer z: missing: {self.status}"
        row = self.rows.get(key)
        return row.text() if row else "peer z: missing: no row"


def _facts(engine, cik, as_of, cache: dict | None) -> Facts:
    key = (cik, as_of)
    if cache is not None and key in cache:
        return cache[key]
    f = Facts(engine, cik, as_of)
    if cache is not None:
        cache[key] = f
    return f


def _flags(f: Facts, end: str) -> list[str]:
    out = []
    p = f.rev.get(end)
    if p is not None and peers.week53(p.start, p.end):
        out.append("53-week year")
    gw_now = at_tol(f.goodwill, end, peers.POINT_TOL)
    year_before = (date.fromisoformat(end) - timedelta(days=364)).isoformat()
    gw_before = at_tol(f.goodwill, year_before, peers.POINT_TOL)
    acq = peers.acquisition_note(_v(f.rev, end), _v(f.acq, end),
                                 float(gw_now.value) if gw_now else None,
                                 float(gw_before.value) if gw_before else None)  # fmt: skip
    if acq:
        out.append(acq)
    return out


def at_tol(points: dict[str, AsOfPoint], end: str, tol: int) -> AsOfPoint | None:
    m = peers.match_period(points, end, tol)
    return points[m.end] if m.ok else None


def compare(
    engine: sqlite3.Connection,
    ticker: str,
    cik: str,
    as_of: str,
    *,
    cache: dict | None = None,
    covered: set[str] | None = None,
) -> Comparison:
    """The company against its confirmed peers, every core trend row."""
    norm = normalize_cik(cik) or cik
    ps = peer_facts.peer_set(engine, ticker, norm)
    me = _facts(engine, norm, as_of, cache)
    ref12 = max(me.rev) if me.rev else None
    ref_fy = max(me.fy_rev) if me.fy_rev else None
    comp = Comparison(ticker, norm, ps.confirmed, ref12)
    if not ps.confirmed:
        comp.status = peer_facts.NOT_CONFIRMED
        return comp
    if not ps.members:
        comp.status = NO_PEERS
        return comp
    covered = covered or set()
    pf = {m["cik"]: _facts(engine, m["cik"], as_of, cache) for m in ps.sec}

    # Peers table: latest 12-month period against the company's.
    for m in ps.members:
        if not m["cik"]:
            comp.lines.append(PeerLine(m["name"], None, None, None, "no", NOT_SEC_TEXT))
            continue
        f = pf[m["cik"]]
        notes = []
        if m["cik"] in covered:
            notes.append("own facts (covered company)")
        if f.empty:
            why = "; ".join(notes + [_no_facts(engine, m["cik"])])
            comp.lines.append(PeerLine(m["name"], m["cik"], None, None, "no", why))
            continue
        if ref12 is None:
            comp.lines.append(PeerLine(m["name"], m["cik"], max(f.rev), None, "no",
                                       "company has no 12-month revenue"))  # fmt: skip
            continue
        mt = peers.match_period(f.rev, ref12, peers.TTM_TOL)
        if mt.ok:
            notes += _flags(f, mt.end)
            inc = f"yes (±{peers.TTM_TOL} d)"
        else:
            inc = peers.NO_PERIOD
            notes.append(mt.note)
        if m["cik"] in NOT_LIKE_FOR_LIKE:
            notes.append("capex: not like-for-like, excluded (D-M04-3)")
        comp.lines.append(PeerLine(m["name"], m["cik"], mt.end or mt.latest,
                                   mt.offset, inc, "; ".join(n for n in notes if n)))  # fmt: skip

    for rd in ROWS:
        comp.rows[rd.key] = _row(rd, me, ref12, ref_fy, ps, pf)
    for key, why in DOLLAR_ROWS.items():
        comp.rows[key] = PeerRow(key, "", Cell(None), missing=why)
    return comp


NOT_SEC_TEXT = peer_facts.NOT_SEC


def _no_facts(engine: sqlite3.Connection, cik: str) -> str:
    row = peer_facts.stored(engine, cik)
    if row is not None and row["outcome"] != "ok":
        return f"missing: companyfacts {row['outcome']} ({row['detail'] or ''})".rstrip(" ()")
    if peer_facts.has_facts(engine, cik):
        return "missing: no revenue fact"
    return peer_facts.NOT_FETCHED


def _row(rd: RowDef, me: Facts, ref12, ref_fy, ps, pf) -> PeerRow:
    ref = ref12 if rd.basis == "r12" else ref_fy
    tol = peers.POINT_TOL if rd.basis == "fy_point" else peers.TTM_TOL
    what = "12 months" if rd.basis == "r12" else "fiscal year"
    row = PeerRow(rd.key, f"{what} to {ref}; peers ±{tol} d", Cell(None), scale=rd.scale,
                  median_unit=rd.median_unit)  # fmt: skip
    if rd.key in CAPEX_ROWS:
        row.note = CAPEX_NOTE
    if ref is None:
        row.missing = f"company has no {what} revenue"
        return row
    if rd.key in CAPEX_ROWS and me.cik in NOT_LIKE_FOR_LIKE:
        row.missing = (f"{NOT_LIKE_FOR_LIKE[me.cik]}'s capex is not like-for-like (no PP&E-only "
                       "tag in every year, D-M04-3)")  # fmt: skip
        return row
    row.company = rd.metric(me, ref)
    vals = []
    for m in ps.members:
        if not m["cik"]:
            row.members.append(Member(m["name"], None, None, None, None, False, NOT_SEC_TEXT))
            continue
        f = pf[m["cik"]]
        if rd.key in CAPEX_ROWS and m["cik"] in NOT_LIKE_FOR_LIKE:
            row.members.append(Member(m["name"], m["cik"], None, None, None, False,
                                      "capex not like-for-like, excluded (D-M04-3)"))  # fmt: skip
            continue
        ends = f.fy_rev if rd.basis == "fy_point" else f.rev
        if not ends:
            why = "missing: no revenue facts (see the Peers table)" if f.empty else (
                "missing: no fiscal-year revenue")  # fmt: skip
            row.members.append(Member(m["name"], m["cik"], None, None, None, False, why))
            continue
        mt = peers.match_period(ends, ref, tol)
        if not mt.ok:
            row.members.append(Member(m["name"], m["cik"], None, mt.offset, None, False,
                                      f"{peers.NO_PERIOD} ({mt.note})"))  # fmt: skip
            continue
        c = rd.metric(f, mt.end)
        if c.value is None:
            row.members.append(Member(m["name"], m["cik"], mt.end, mt.offset, None, False,
                                      c.text or "missing"))  # fmt: skip
            continue
        row.members.append(Member(m["name"], m["cik"], mt.end, mt.offset, c.value, True,
                                  flags=_flags(f, mt.end)))  # fmt: skip
        vals.append((m["name"], c.value))
    if row.company.value is None:
        why = row.company.text or "missing"
        row.missing = why if why.startswith(NM) else (
            f"company value missing ({why.removeprefix('missing: ')})")  # fmt: skip
        return row
    row.result = stats.robust_z(row.company.value, vals)
    return row


def annotate(tv: trends.TrendsView, comp: Comparison | None) -> trends.TrendsView:
    """Write the peer text into each trend signal's method (replaces the placeholder)."""
    if comp is None:
        return tv
    tv.signals = [
        replace(s, method=s.method.replace(trends.PEER_TOKEN, comp.signal_text(s.name)))
        for s in tv.signals
    ]
    return tv
