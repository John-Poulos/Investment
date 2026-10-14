"""Cycle vs Decline (CvD) assembly, classification and M01's reading (M04 Part 8a, MVP).

D-M04-1 as amended by D-M04-52…68 and built per D-M04-100…105 (M04_FINANCIALS.md "Cycle
vs. Decline (CvD) profile"). `evaluate(engine, cik, ticker, as_of)` reads facts as known on
`as_of`, so live rows and the regression cases run the same code.

- **Activation** (D-M04-55, -67): on the latest 12-month period (TTM, else fiscal year):
  TTM revenue down; gross margin down ≥ 3 pp†; operating income down ≥ 25%† (positive
  base); or the latest quarter's revenue ≥ 10%† below a year earlier. It switches off only
  after 2 straight quarters with none (S6.9): active = a trigger now or at the previous
  filing (facts as known the day before the latest filing). Else NO_SLOWDOWN.
- **Q1 — is the slump shared?** revenue growth vs peers (Part 2 robust z; fixed gap below
  5 peers; persistence 2 quarters for company-specific), industry pricing ("missing
  (DS13)"), inventory days (average inventory, write-downs added back), supply response
  (capex cut together with peers), cycle history (prior XBRL downturns of similar depth
  that recovered).
- **Q2 — is the franchise intact?** market share (owner entries, D-M04-68), gross-margin
  gap to the peer median (≥ 3 comparable peers), trough vs prior trough (5 pp turning
  points, write-down adjusted, ROIC agreeing), capex intensity and R&D level (surge > 1.5×
  into falling revenue → neutral, pointer to M05), customer row (deferred, Part 7b),
  guidance record (`guidance_hit_rate`), health vote (F-quality 0–5). Moat "not applicable
  until M06" and the R12 vote (Part 7b; counts only when it fires) stay out of coverage.
- **Resolution** (D-M04-56): missing rows leave the denominator; ≥ 2 present rows; one side
  holding ≥ 2/3† of present weight; confidence = the lower of the two winning shares;
  coverage = present ÷ applicable per question. An active grid with a question below 2
  present rows cannot resolve: `insufficient_data`, no review item, M01 blocked
  (D-M04-102 as amended, Part 8a live check 1).
- **asset_treasury** (D-M04-8): activation's operating-income test excludes the
  digital-asset fair-value line inside operating income (D-M04-100 as amended).
- **Overrides:** an owner's `m04_cvd` answer becomes the state (D-M04-56); the survival gate
  overrides the grid for M01 (D-M04-31); stale / overdue (D-M04-61); open 4.02 marks the
  inputs "under non-reliance" (D-M04-21).

Deferred (owner, MVP D31): the overreaction gauge and normalized earnings power, the Red
Flag 1 row; rows from Parts 5 and 7b and M06 read "missing: deferred (MVP)" / "not
applicable until M06" and leave the denominator. Missing stays missing, never zero.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from engine import m01_rules
from engine.financials import capex as capex_mod
from engine.financials import gate, health, market_share, peer_facts, peer_z, peers, restate, trends
from engine.financials import models as models_mod
from engine.financials import stage as stage_mod
from engine.financials import status as status_mod
from engine.financials.capex import at, fiscal_label, fy_points, near
from engine.sec.asof import AsOfPoint, facts_as_of
from engine.sec.identity import normalize_cik
from engine.sec.xbrl_facts import Concept
from engine.signals import Source

MODULE = "M04"
# Starting values † (D6: tuned only at Part 8b / the High review)
GM_DROP_PP = 3.0  # D-M04-55
OI_DROP = 0.25  # D-M04-55
QUARTER_DROP = 0.10  # D-M04-67
Z_DEEP = -1.0  # deeper_than_peers (D-M04-55)
Z_SPECIFIC = -1.5  # company-specific, 2 quarters (D-M04-1, -55)
GAP_PP = 10.0  # fixed-gap fallback (D-M04-55)
MAJORITY = (2, 3)  # 2/3 of present weight (D-M04-56)
MIN_PRESENT = 2
TOGETHER = (2, 3)  # supply response: 2/3 of comparable peers move one way (D-M04-100)
CYCLE_DEPTH = 0.5  # a prior decline at least half as deep (D-M04-100)
CYCLE_GM_PP = 5.0  # … or a gross-margin low within 5 pp of today's
RECOVER_YEARS = 4
RECOVER_GM_PP = 10.0
MIN_HISTORY = 5  # fiscal years before the episode, else "insufficient history"
GM_GAP_INTACT, GM_GAP_WEAK, GM_GAP_PEERS = -3.0, -5.0, 3  # D-M04-1, S6.10
SWING_PP = 5.0  # turning points (D-M04-54)
SURGE = 1.5  # D-M04-64
CUT = 0.20  # S6.4
REV_ROSE = 0.10  # revenue > 10%† above its own 3-year average → capex read on the level
INSUFFICIENT = "insufficient_data"  # D-M04-102 as amended (Part 8a live check 1)
INSUFFICIENT_WHY = "fewer than 2 rows present in Q1/Q2"
# Digital-asset fair-value lines inside operating income (ASU 2023-08; Part 6 swing tags):
# (concept, sign of a gain) — the gain/loss tag is + for a gain, the loss-only tag + for a loss
CRYPTO_OPERATING = (
    (Concept("crypto_gl_operating", (("us-gaap", "CryptoAssetUnrealizedGainLossOperating"),),
             "currency", "flow"), 1),
    (Concept("crypto_loss_operating", (("us-gaap", "CryptoAssetUnrealizedLossOperating"),),
             "currency", "flow"), -1),
)  # fmt: skip
EXCLUDED = ("fund", "financial", "reit", "spac_shell")  # D-M04-8 table: CvD excluded

STATES = (
    "CYCLICAL_TROUGH",
    "CYCLE_PLUS_DAMAGE",
    "STUMBLE",
    "STRUCTURAL_DECLINE",
    "AMBIGUOUS",
    "NO_SLOWDOWN",
)
REVIEW = frozenset({"AMBIGUOUS", "STUMBLE", "CYCLE_PLUS_DAMAGE"})
ANSWERS = {
    "cyclical_trough": "CYCLICAL_TROUGH",
    "stumble": "STUMBLE",
    "cycle_plus_damage": "CYCLE_PLUS_DAMAGE",
    "structural_decline": "STRUCTURAL_DECLINE",
}
ANSWER_KEY = "m04_cvd:{cik}"
SIDES = {"Q1": ("shared", "company_specific"), "Q2": ("intact", "weakening")}
DEFERRED = "deferred (MVP, D31)"


@dataclass
class Row:
    q: str  # Q1 | Q2
    key: str
    label: str
    reading: str  # a side, neutral, missing, not_applicable
    value: str = ""
    why: str = ""
    counted: bool = True  # in the applicable count (coverage)
    sources: list[Source] = field(default_factory=list)
    number: float | None = None
    awaiting: bool = False  # missing only because a peer's period is not filed yet

    @property
    def present(self) -> bool:
        return self.reading not in ("missing", "not_applicable")


@dataclass
class Question:
    q: str
    present: int
    applicable: int
    counts: dict[str, int]
    lead: str | None
    share: float  # the leading side's share of present weight (0 below 2 present rows)
    resolved: bool

    @property
    def coverage(self) -> float | None:
        return self.present / self.applicable if self.applicable else None

    def text(self) -> str:
        if self.present < MIN_PRESENT:
            return f"{self.present} of {self.applicable} present (fewer than {MIN_PRESENT})"
        parts = ", ".join(f"{k.replace('_', '-')} {v}" for k, v in self.counts.items() if v)
        verdict = self.lead.replace("_", "-") if self.resolved and self.lead else "split"
        return f"{verdict} {self.share:.2f} ({parts}; {self.present} of {self.applicable})"


@dataclass
class M01:
    rule3: str  # tranches
    rule7: str  # strength beyond 2σ
    rule4: list[str]  # exit-warning reasons
    notes: list[str] = field(default_factory=list)  # red flags, never blocking

    def text(self) -> str:
        r4 = "; ".join(self.rule4) if self.rule4 else "none"
        out = (
            f"rule 3 tranches: {self.rule3} · rule 7 strength: {self.rule7} · "
            f"rule 4 exit warning: {r4}"
        )
        if self.notes:
            out += " · red flags (listed, never blocking): " + "; ".join(self.notes)
        return out


@dataclass
class CvD:
    cik: str
    ticker: str | None
    as_of: str
    state: str | None = None  # the effective state (owner answer applied)
    raw_state: str | None = None  # as computed
    active: bool = False
    triggers: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    ref_end: str | None = None
    ref_kind: str = ""
    latest_filed: str = ""
    rows: list[Row] = field(default_factory=list)
    q1: Question | None = None
    q2: Question | None = None
    confidence: float | None = None
    deeper: bool | None = None
    gate: gate.Gate | None = None
    status: str = ""  # current | stale | overdue | not evaluated
    status_text: str = ""
    non_reliance: str = ""
    answer: dict | None = None
    m01: M01 | None = None
    f_quality: health.Score | None = None
    f_score: health.Score | None = None
    g_score: health.Score | None = None
    share: market_share.ShareReading | None = None
    tag: str | None = None
    stage: str | None = None
    excluded: str = ""  # "not applicable (<tag>)"
    missing: str = ""  # no CvD at all (no 12-month revenue)
    notes: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    peers: list[str] = field(default_factory=list)  # the confirmed SEC peers used (today's set)

    @property
    def insufficient(self) -> bool:
        return self.raw_state == INSUFFICIENT

    @property
    def stale(self) -> bool:
        return self.status == "stale"

    @property
    def overdue(self) -> bool:
        return self.status == "overdue"

    def row(self, key: str) -> Row | None:
        return next((r for r in self.rows if r.key == key), None)

    def coverage_text(self) -> str:
        if not self.q1 or not self.q2:
            return "—"
        return (
            f"Q1 {self.q1.present} of {self.q1.applicable}, "
            f"Q2 {self.q2.present} of {self.q2.applicable}"
        )

    def method(self) -> str:
        if self.excluded or self.missing:
            return self.excluded or self.missing
        bits = [f"{self.ref_kind} to {self.ref_end}" if self.ref_end else "no 12-month period"]
        bits.append(
            "active: " + ("; ".join(self.triggers) if self.triggers else "no trigger")
            if self.active
            else "not active: " + "; ".join(self.tests)
        )
        if self.q1 and self.q2:
            bits.append(f"Q1 {self.q1.text()}; Q2 {self.q2.text()}")
        if self.insufficient:
            bits.append(
                f"{INSUFFICIENT_WHY}: the grid cannot resolve, no review item (D-M04-56, -102)"
            )
        if self.raw_state and self.state != self.raw_state:
            a = self.answer or {}
            bits.append(
                f"owner answer {self.state} (computed {self.raw_state}; item "
                f"{a.get('item_id')}, {str(a.get('at', ''))[:10]})"
            )
        if self.gate is not None:
            bits.append(f"gate {self.gate.state}")
        if self.status:
            bits.append(
                f"filing status {self.status}"
                + (f" ({self.status_text})" if self.status in ("stale", "overdue") else "")
            )
        if self.non_reliance:
            bits.append(self.non_reliance)
        if self.m01:
            bits.append("M01: " + self.m01.text())
        bits += self.notes
        return "; ".join(bits)


# --- Small helpers ---------------------------------------------------------------------------


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:+.1f}%"


def _src(p: AsOfPoint | None, what: str = "") -> list[Source]:
    return [Source(p.accession, p.filed, "A", what or f"{p.concept} {p.end}")] if p else []


def _points(engine, cik, concept, as_of, ptype) -> dict[str, AsOfPoint]:
    return {p.end: p for p in facts_as_of(engine, cik, concept, as_of, ptype=ptype).points}


def _year_before(points: dict[str, AsOfPoint], end: str, tol: tuple[int, int] = (350, 380)):
    e = _d(end)
    cands = [k for k in points if tol[0] <= (e - _d(k)).days <= tol[1]]
    return min(cands, key=lambda k: abs((e - _d(k)).days - 364)) if cands else None


def _awaiting(text: str) -> bool:
    return "awaiting peer filing" in text


# --- Activation ------------------------------------------------------------------------------


@dataclass
class Activation:
    ref: str | None
    kind: str
    triggers: list[str]
    tests: list[str]
    rev_growth: float | None
    filed: str
    sources: list[Source]


def crypto_operating(engine, cik: str, as_of: str, end: str | None):
    """The digital-asset fair-value change inside operating income for the 12 months to
    `end` (+ = gain) and its tag; (None, "") when no such line is tagged (D-M04-8, -100)."""
    if end is None:
        return None, ""
    for con, sign in CRYPTO_OPERATING:
        p = at(peer_z.twelve(engine, cik, con, as_of), end)
        if p is not None:
            return sign * float(p.value), f"{con.tags[0][0]}:{con.tags[0][1]}"
    return None, ""


def activation(
    engine: sqlite3.Connection, cik: str, as_of: str, *, treasury: bool = False
) -> Activation:
    """`treasury` (model tag `asset_treasury`, D-M04-8): the operating-income test runs on
    operating income less the digital-asset fair-value line, or reads "not meaningful" when
    that line is not tagged for both 12-month periods (D-M04-100 as amended)."""
    f = peer_z.Facts(engine, cik, as_of)
    if not f.rev:
        return Activation(None, "", [], ["no 12-month revenue stored"], None, "", [])
    ref = max(f.rev)
    pt = f.rev[ref]
    kind = "TTM" if pt.ptype == "TTM" else "fiscal year"
    prev = peer_z._prior_end(f.rev, ref)
    trig, tests = [], []
    r1, r0 = peer_z._v(f.rev, ref), peer_z._v(f.rev, prev)
    growth = r1 / r0 - 1 if r1 is not None and r0 else None
    if growth is None:
        tests.append("revenue: no 12-month period a year earlier")
    elif growth < 0:
        trig.append(f"{kind} revenue {_pct(growth)}")
    else:
        tests.append(f"{kind} revenue {_pct(growth)}")
    g1, g0 = peer_z._gm(f, ref), peer_z._gm(f, prev)
    if g1 is None or g0 is None:
        tests.append("gross margin: missing")
    elif g1 - g0 <= -GM_DROP_PP:
        trig.append(f"gross margin {g1 - g0:+.1f} pp (≤ −{GM_DROP_PP:.0f} pp†)")
    else:
        tests.append(f"gross margin {g1 - g0:+.1f} pp")
    o1, o0 = peer_z._v(f.oi, ref), peer_z._v(f.oi, prev)
    oi_name = "operating income"
    if treasury and o1 is not None and o0 is not None:
        c1, tag1 = crypto_operating(engine, f.cik, as_of, ref)
        c0, tag0 = crypto_operating(engine, f.cik, as_of, prev)
        if c1 is None or c0 is None:
            gone = ", ".join(e for e, c in ((prev, c0), (ref, c1)) if c is None)
            tests.append(
                "operating income: not meaningful for asset_treasury — no digital-asset "
                f"fair-value line tagged for the 12 months to {gone}, so bitcoin's price "
                "cannot be taken out (D-M04-8, -100)"
            )
            o1 = o0 = None
            oi_name = ""
        else:
            o1, o0 = o1 - c1, o0 - c0
            oi_name = (
                f"operating income ex digital-asset fair value ({tag1 or tag0}: "
                f"{c0 / 1e6:,.0f}M → {c1 / 1e6:,.0f}M, D-M04-8)"
            )
    if not oi_name:
        pass  # not meaningful, named above
    elif o1 is None or o0 is None:
        tests.append(f"{oi_name}: missing")
    elif o0 <= 0:
        tests.append(f"{oi_name}: base ≤ 0, not meaningful")
    elif o1 / o0 - 1 <= -OI_DROP:
        trig.append(f"{oi_name} {_pct(o1 / o0 - 1)} (≤ −{OI_DROP:.0%}†)")
    else:
        tests.append(f"{oi_name} {_pct(o1 / o0 - 1)}")
    q = _points(engine, f.cik, "revenue", as_of, "Q")
    srcs = _src(pt, f"revenue {kind} {ref}")
    if not q:
        tests.append("latest quarter: no quarterly revenue (annual filer)")
    else:
        qe = max(q)
        qb = _year_before(q, qe)
        if qb is None or not q[qb].value:
            tests.append(f"latest quarter {qe}: no quarter a year earlier")
        else:
            qg = float(q[qe].value) / float(q[qb].value) - 1
            if qg <= -QUARTER_DROP:
                trig.append(
                    f"latest quarter ({qe}) revenue {_pct(qg)} vs a year earlier "
                    f"(≤ −{QUARTER_DROP:.0%}†, D-M04-67)"
                )
            else:
                tests.append(f"latest quarter {_pct(qg)}")
            srcs += _src(q[qe], f"revenue quarter {qe}")
    filed = max([pt.filed] + ([q[max(q)].filed] if q else []))
    return Activation(ref, kind, trig, tests, growth, filed, srcs)


# --- Q1 rows ---------------------------------------------------------------------------------

ABOVE_PEERS = (
    "growing at or above the growing peers' median: no slump here, neither shared nor "
    "company-specific → neutral (D-M04-55)"
)


def _rev_reading(comp: peer_z.Comparison) -> tuple[str, str, str, bool | None, bool, float | None]:
    """(reading, value, why, deeper, candidate company-specific, z or gap)."""
    if comp.status:
        return "missing", "", comp.status, None, False, None
    row = comp.rows.get("rev_yoy")
    if row is None or row.missing:
        return "missing", "", row.missing if row else "no peer row", None, False, None
    r = row.result
    if r is None or r.median is None:
        why = "; ".join(f"{m.name}: {m.why}" for m in row.members if not m.included)
        return "missing", "", f"no comparable peer ({why or 'no peers'})", None, False, None
    gap = r.gap * 100
    if r.fallback:
        val = f"gap {gap:+.1f} pp vs median {r.median * 100:+.1f}% (n {r.n}, fixed-gap fallback)"
        if r.median < 0:
            deep = gap <= -GAP_PP
            return (
                "shared",
                val,
                "peers falling"
                + (f"; ≥ {GAP_PP:.0f} pp below → deeper_than_peers" if deep else ""),
                deep,
                False,
                gap,
            )
        if gap <= -GAP_PP:
            return "neutral", val, f"≥ {GAP_PP:.0f} pp below growing peers", False, True, gap
        if gap >= 0:
            return "neutral", val, ABOVE_PEERS, False, False, gap
        return (
            "neutral",
            val,
            f"peers growing, gap within {GAP_PP:.0f} pp below (D-M04-55)",
            False,
            False,
            gap,
        )
    val = f"z {r.z:+.2f}, gap {gap:+.1f} pp vs median {r.median * 100:+.1f}% (n {r.n})"
    if r.median < 0:
        deep = r.z is not None and r.z <= Z_DEEP
        return (
            "shared",
            val,
            "peers falling" + ("; z ≤ −1 → deeper_than_peers" if deep else ""),
            deep,
            False,
            r.z,
        )
    if r.z is not None and r.z <= Z_SPECIFIC:
        return "neutral", val, f"z ≤ {Z_SPECIFIC} while peers grow", False, True, r.z
    if gap >= 0:
        return "neutral", val, ABOVE_PEERS, False, False, r.z
    return "neutral", val, f"peers growing and z > {Z_SPECIFIC} (D-M04-55)", False, False, r.z


def revenue_row(engine, cik, ticker, as_of, prev_as_of, cache) -> tuple[Row, bool | None]:
    comp = peer_z.compare(engine, ticker or cik, cik, as_of, cache=cache)
    reading, val, why, deep, cand, num = _rev_reading(comp)
    row = Row(
        "Q1",
        "revenue_vs_peers",
        "Revenue growth vs peers (12 months)",
        reading,
        val,
        why,
        number=num,
    )
    if reading == "missing":
        row.awaiting = _awaiting(why)
        return row, None
    rr = comp.rows["rev_yoy"]
    row.why = f"{why}; {rr.text()}"
    if cand:
        before = peer_z.compare(engine, ticker or cik, cik, prev_as_of, cache=cache)
        r0, _, _, _, cand0, _ = _rev_reading(before)
        if cand0:
            row.reading = "company_specific"
            row.why = f"company-specific for 2 straight quarters (D-M04-1); {row.why}"
        else:
            row.why = (
                f"company-specific reading this quarter only (needs 2 straight "
                f"quarters; previous: {r0}); {row.why}"
            )
    return row, deep


@dataclass
class Days:
    end: str
    reported: float
    adjusted: float
    text: str
    sources: list[Source]


def inventory_days(engine, cik: str, as_of: str, basis: str, end: str) -> Days | str:
    """Average inventory ÷ cost of revenue × days in the period; the period's inventory
    write-down added back to closing inventory and taken out of cost (R1 brief, probe L9:
    Micron Q2 FY2023 153.1 → 235.0 days)."""
    ptype = "Q" if basis == "Q" else "FY"
    cost = _points(engine, cik, "cost_of_revenue", as_of, ptype)
    c = at(cost, end)
    how = ""
    if c is None:
        rev = at(_points(engine, cik, "revenue", as_of, ptype), end)
        gp = at(_points(engine, cik, "gross_profit", as_of, ptype), end)
        if rev is None or gp is None:
            return "no cost-of-revenue fact"
        cogs, start, cend = float(rev.value - gp.value), rev.start, rev.end
        how, srcp = "cost derived (revenue − gross profit)", rev
    else:
        cogs, start, cend, srcp = float(c.value), c.start, c.end, c
    if not start or cogs <= 0:
        return "cost of revenue ≤ 0"
    inv = fy_points(engine, cik, "inventory", as_of, "I")
    close = at(inv, cend)
    opening = at(inv, (_d(start) - timedelta(days=1)).isoformat())
    if close is None or opening is None:
        return "no inventory fact at the period's start or end (no inventory tag?)"
    wd = at(_points(engine, cik, "inventory_writedown", as_of, ptype), cend)
    w = float(wd.value) if wd is not None else 0.0
    days = (_d(cend) - _d(start)).days + 1
    rep = (float(opening.value) + float(close.value)) / 2 / cogs * days
    adj_cost = cogs - w
    if adj_cost <= 0:
        return "cost of revenue after the write-down ≤ 0"
    adj = (float(opening.value) + float(close.value) + w) / 2 / adj_cost * days
    wtxt = f"write-down {w / 1e6:,.0f}M added back" if wd is not None else "no write-down tagged"
    text = (
        f"{rep:.1f} days ({adj:.1f} with the write-down added back; inventory "
        f"{opening.value / 1e6:,.0f}/{close.value / 1e6:,.0f}M, cost {cogs / 1e6:,.0f}M over "
        f"{days} d; {wtxt}{'; ' + how if how else ''})"
    )
    return Days(cend, rep, adj, text, _src(srcp) + _src(close, f"inventory {cend}"))


def _basis(engine, cik, as_of, ref: str | None) -> tuple[str, str | None]:
    q = _points(engine, cik, "cost_of_revenue", as_of, "Q") or _points(
        engine, cik, "revenue", as_of, "Q"
    )
    if ref and q:
        e = max(q)
        if near(e, ref):
            return "Q", e
    fy = fy_points(engine, cik, "revenue", as_of)
    return "FY", (max(fy) if fy else None)


def _days_change(engine, cik, as_of, basis, end) -> tuple[float | None, str, Days | None]:
    now = inventory_days(engine, cik, as_of, basis, end)
    if isinstance(now, str):
        return None, now, None
    pts = _points(engine, cik, "revenue", as_of, "Q" if basis == "Q" else "FY")
    pts |= _points(engine, cik, "cost_of_revenue", as_of, "Q" if basis == "Q" else "FY")
    prev_end = _year_before(pts, end)
    if prev_end is None:
        return None, f"{now.text}; no period a year earlier", now
    then = inventory_days(engine, cik, as_of, basis, prev_end)
    if isinstance(then, str):
        return None, f"{now.text}; a year earlier: {then}", now
    return now.adjusted - then.adjusted, f"{then.adjusted:.1f} → {now.adjusted:.1f} days", now


def inventory_row(engine, cik, ticker, as_of, ref, peer_list) -> Row:
    basis, end = _basis(engine, cik, as_of, ref)
    row = Row(
        "Q1",
        "inventory_days",
        "Inventory days (average inventory, write-downs added back)",
        "missing",
    )
    if end is None:
        row.why = "no period"
        return row
    chg, text, now = _days_change(engine, cik, as_of, basis, end)
    if chg is None:
        row.why = text
        return row
    row.number = now.adjusted
    span = "quarter" if basis == "Q" else "fiscal year"
    row.value = f"{now.text}; change {chg:+.1f} days ({text}; {span})"
    row.sources = now.sources
    if chg <= 0:
        row.reading, row.why = "neutral", "not rising here"
        return row
    tol = peers.POINT_TOL if basis == "Q" else peers.TTM_TOL
    vals, notes = [], []
    for name, pcik in peer_list:
        pts = _points(engine, pcik, "cost_of_revenue", as_of, "Q" if basis == "Q" else "FY")
        if not pts:
            pts = _points(engine, pcik, "revenue", as_of, "Q" if basis == "Q" else "FY")
        mt = peers.match_period(pts, end, tol) if pts else None
        if mt is None or not mt.ok:
            notes.append(f"{name}: " + (f"{peers.NO_PERIOD} ({mt.note})" if mt else "no facts"))
            continue
        pc, ptext, _ = _days_change(engine, pcik, as_of, basis, mt.end)
        if pc is None:
            notes.append(f"{name}: {ptext}")
            continue
        vals.append(pc)
        notes.append(f"{name} {ptext} ({pc:+.1f})")
    if not vals:
        row.why = "rising here; no comparable peer period (" + "; ".join(notes) + ")"
        row.awaiting = any(_awaiting(n) for n in notes)
        row.reading = "missing"
        return row
    med = statistics.median(vals)
    row.reading = "shared" if med > 0 else "company_specific"
    row.why = (
        ("rising across peers" if med > 0 else "rising only here")
        + f" (peer median change {med:+.1f} days, n {len(vals)}): "
        + "; ".join(notes)
    )
    return row


def _own_capex_concept(engine, cik, as_of) -> tuple[Concept | None, str]:
    tc = capex_mod.total_capex(engine, cik, as_of)
    if not tc:
        return None, "no total capex"
    tax, tag = tc[-1].tag.split(":", 1)
    return Concept("capex_own", ((tax, tag),), "currency", "flow"), tc[-1].tag


def _change(points: dict[str, AsOfPoint], end: str, tol: int | None = None):
    if tol is not None:
        m = peers.match_period(points, end, tol)
        if not m.ok:
            return None, m.note
        end = m.end
    p1 = at(points, end)
    pe = _year_before(points, end)
    p0 = points.get(pe) if pe else None
    if p1 is None or p0 is None or not p0.value:
        return None, "no 12-month capex a year earlier"
    return float(p1.value) / float(p0.value) - 1, f"{_pct(float(p1.value) / float(p0.value) - 1)}"


def supply_row(engine, cik, as_of, ref, peer_list, cache) -> Row:
    row = Row("Q1", "supply_response", "Supply response (capex cut with peers)", "missing")
    con, tag = _own_capex_concept(engine, cik, as_of)
    if con is None or ref is None:
        row.why = tag if con is None else "no 12-month period"
        return row
    own = peer_z.twelve(engine, cik, con, as_of)
    chg, txt = _change(own, ref)
    if chg is None:
        row.why = f"own capex ({tag}): {txt}"
        return row
    row.number = chg
    row.sources = _src(at(own, ref), f"capex {tag}")
    vals, notes = [], []
    for name, pcik in peer_list:
        if pcik in peer_z.NOT_LIKE_FOR_LIKE:
            notes.append(f"{name}: capex not like-for-like, excluded (D-M04-3)")
            continue
        f = peer_z._facts(engine, pcik, as_of, cache)
        c, t = _change(f.capex, ref, peers.TTM_TOL)
        if c is None:
            notes.append(f"{name}: {t}")
            continue
        vals.append(c)
        notes.append(f"{name} {t}")
    row.value = f"own capex {txt} ({tag}); peers: " + ("; ".join(notes) or "none")
    if not vals:
        row.why = (
            f"own capex {txt}; no comparable peer capex (" + ("; ".join(notes) or "no peers") + ")"
        )
        row.awaiting = any(_awaiting(n) for n in notes)
        return row
    down = sum(1 for v in vals if v < 0)
    up = sum(1 for v in vals if v > 0)
    n = len(vals)
    if down * TOGETHER[1] >= TOGETHER[0] * n and chg < 0:
        row.reading, row.why = "shared", f"peers cutting together ({down} of {n}) and own capex cut"
    elif up * TOGETHER[1] >= TOGETHER[0] * n:
        row.reading, row.why = "company_specific", f"peers expanding ({up} of {n})"
    elif down * TOGETHER[1] >= TOGETHER[0] * n:
        row.reading, row.why = "neutral", f"peers cutting ({down} of {n}) but own capex not cut"
    else:
        row.reading, row.why = "neutral", f"mixed ({down} cutting, {up} expanding of {n})"
    return row


@dataclass
class Episode:
    start: str  # the peak before the decline
    trough: str
    depth: float
    gm_low: float | None
    recovered: str  # "" or how


def _series(bk: health.Book, ref: str | None):
    """[(end, revenue, gross margin %)] on fiscal years ending by the 12-month ref."""
    out = []
    for e in bk.ends:
        r = bk.v("revenue", e)
        if r is None or (ref and e > ref and not near(e, ref)):
            continue
        g = bk.gross(e)
        out.append((e, r, (g / r * 100) if g is not None and r else None))
    return out


PEAK_DAYS = 760  # the current episode's peak: the highest fiscal year in ~2 years before


def _episode_start(s, ref: str, ref_rev: float, falling: bool) -> tuple[int, float]:
    """(index of the pre-episode peak in `s`, depth of the current fall from it)."""
    before = [k for k, x in enumerate(s) if 10 < (_d(ref) - _d(x[0])).days <= PEAK_DAYS]
    if not falling or not before:
        last = max((k for k, x in enumerate(s) if (_d(ref) - _d(x[0])).days > 10), default=0)
        return last, 0.0
    k = max(before, key=lambda n: s[n][1])
    return k, ref_rev / s[k][1] - 1


def _runs(series) -> list[Episode]:
    eps, i = [], 1
    while i < len(series):
        if series[i][1] < series[i - 1][1]:
            j = i
            while j + 1 < len(series) and series[j + 1][1] < series[j][1]:
                j += 1
            peak, trough = series[i - 1], series[j]
            gms = [g for _, _, g in series[i : j + 1] if g is not None]
            eps.append(
                Episode(peak[0], trough[0], trough[1] / peak[1] - 1, min(gms) if gms else None, "")
            )
            i = j + 1
        else:
            i += 1
    return eps


def cycle_row(engine, cik, as_of, ref, ref_rev, gm_now, bk: health.Book, falling: bool) -> Row:
    row = Row("Q1", "cycle_history", "Cycle history (XBRL fiscal years)", "missing")
    s = _series(bk, ref)
    if len(s) < 2 or ref is None or ref_rev is None:
        row.why = "insufficient history: fewer than 2 fiscal years in XBRL"
        return row
    # the current episode: from the highest fiscal year in the ~2 years before the 12-month
    # ref (D-M04-100); a margin-only slump has no revenue depth
    i, cur_depth = _episode_start(s, ref, ref_rev, falling)
    cur_gm = gm_now if gm_now is not None else s[-1][2]
    history = s[: i + 1]
    first = fiscal_label(s[0][0])
    if len(history) < MIN_HISTORY:
        row.why = (
            f"insufficient history: {len(history)} fiscal years before this episode "
            f"(XBRL from {first}); never 'first deep decline' (D-M04-1)"
        )
        return row
    eps = _runs(history)
    similar = []
    for ep in eps:
        deep = cur_depth < 0 and ep.depth <= CYCLE_DEPTH * cur_depth
        gm_like = cur_gm is not None and ep.gm_low is not None and ep.gm_low <= cur_gm + CYCLE_GM_PP
        if not (deep or gm_like):
            continue
        k = next(n for n, x in enumerate(s) if x[0] == ep.trough)
        peak_rev = next(x[1] for x in s if x[0] == ep.start)
        for later in s[k + 1 : k + 1 + RECOVER_YEARS]:
            if later[1] >= peak_rev:
                ep.recovered = (
                    f"revenue regained its {fiscal_label(ep.start)} peak by "
                    f"{fiscal_label(later[0])}"
                )
                break
        if not ep.recovered and ep.gm_low is not None:
            for later in s[k + 1 : k + 3]:
                if later[2] is not None and later[2] >= ep.gm_low + RECOVER_GM_PP:
                    ep.recovered = (
                        f"gross margin {ep.gm_low:.1f}% → {later[2]:.1f}% by "
                        f"{fiscal_label(later[0])}"
                    )
                    break
        similar.append((ep, "depth" if deep else "gross-margin low"))
    gm_txt = f", gross margin {cur_gm:.1f}%" if cur_gm is not None else ""
    row.value = (
        f"this episode {_pct(cur_depth)} from {fiscal_label(s[i][0])}{gm_txt}; "
        f"{len(eps)} earlier decline(s) since {first}"
    )
    row.sources = []
    done = [(e, how) for e, how in similar if e.recovered]
    if done:
        e, how = done[-1]
        row.reading = "shared"
        row.why = (
            f"prior downturn of similar {how} recovered: {fiscal_label(e.start)}→"
            f"{fiscal_label(e.trough)} {_pct(e.depth)}"
            + (f", gross margin low {e.gm_low:.1f}%" if e.gm_low is not None else "")
            + f"; {e.recovered}"
        )
    elif similar:
        e, _ = similar[-1]
        row.reading = "company_specific"
        row.why = f"prior decline of similar depth did not recover ({fiscal_label(e.trough)})"
    else:
        deepest = min(eps, key=lambda e: e.depth) if eps else None
        row.reading = "company_specific"
        row.why = "first deep decline in XBRL history" + (
            f" (deepest earlier: {fiscal_label(deepest.trough)} {_pct(deepest.depth)})"
            if deepest
            else ""
        )
    return row


# --- Q2 rows ---------------------------------------------------------------------------------


def gm_gap_row(engine, cik, as_of, comp_facts: peer_z.Facts, ref, peer_list, cache) -> Row:
    row = Row("Q2", "gm_gap", "Gross-margin gap to peer median (change over 4 quarters)", "missing")
    if ref is None:
        row.why = "no 12-month period"
        return row
    g1 = peer_z._gm(comp_facts, ref)
    prev = peer_z._prior_end(comp_facts.rev, ref)
    g0 = peer_z._gm(comp_facts, prev)
    if g1 is None or g0 is None:
        row.why = "not like-for-like: no gross-profit or cost-of-revenue line (S5.12)"
        return row
    now_v, then_v, notes = [], [], []
    for name, pcik in peer_list:
        f = peer_z._facts(engine, pcik, as_of, cache)
        m1, m0 = (
            peers.match_period(f.rev, ref, peers.TTM_TOL),
            peers.match_period(f.rev, prev, peers.TTM_TOL),
        )
        a = peer_z._gm(f, m1.end) if m1.ok else None
        b = peer_z._gm(f, m0.end) if m0.ok else None
        if a is None or b is None:
            notes.append(
                f"{name}: "
                + (m1.note if not m1.ok else m0.note if not m0.ok else "no gross margin")
            )
            continue
        now_v.append(a)
        then_v.append(b)
        notes.append(f"{name} {b:.1f}% → {a:.1f}%")
    gap_txt = f"company {g0:.1f}% → {g1:.1f}%"
    if len(now_v) < GM_GAP_PEERS:
        if now_v:
            gap = g1 - statistics.median(now_v)
            gap_txt += f"; gap now {gap:+.1f} pp vs {len(now_v)} peer(s)"
        row.value = gap_txt
        row.why = (
            f"fewer than {GM_GAP_PEERS} comparable peers ({len(now_v)}): shown, not "
            f"counted (S6.10); " + "; ".join(notes)
        )
        row.awaiting = any(_awaiting(n) for n in notes) and not now_v
        return row
    gap1, gap0 = g1 - statistics.median(now_v), g0 - statistics.median(then_v)
    chg = gap1 - gap0
    row.number = chg
    row.value = f"gap {gap0:+.1f} → {gap1:+.1f} pp = {chg:+.1f} pp ({gap_txt}; n {len(now_v)})"
    row.sources = _src(at(comp_facts.rev, ref))
    if chg >= GM_GAP_INTACT:
        row.reading, row.why = "intact", f"change ≥ {GM_GAP_INTACT:.0f} pp"
    elif chg < GM_GAP_WEAK:
        row.reading, row.why = "weakening", f"change < {GM_GAP_WEAK:.0f} pp"
    else:
        row.reading, row.why = "neutral", "change between −5 and −3 pp"
    row.why += "; " + "; ".join(notes)
    return row


def turning_points(vals: list[float], swing: float = SWING_PP):
    """(troughs, peaks, current low) by index; a turning point is confirmed by a reversal
    of at least `swing` (D-M04-54)."""
    if not vals:
        return [], [], None
    mode, lo, hi = None, 0, 0
    troughs, peaks = [], []
    for i in range(1, len(vals)):
        v = vals[i]
        if mode is None:
            if v > vals[hi]:
                hi = i
            if v < vals[lo]:
                lo = i
            if lo < i and v - vals[lo] >= swing:
                troughs.append(lo)
                mode, hi = "up", i
            elif hi < i and vals[hi] - v >= swing:
                peaks.append(hi)
                mode, lo = "down", i
        elif mode == "up":
            if v > vals[hi]:
                hi = i
            elif vals[hi] - v >= swing:
                peaks.append(hi)
                mode, lo = "down", i
        else:
            if v < vals[lo]:
                lo = i
            elif v - vals[lo] >= swing:
                troughs.append(lo)
                mode, hi = "up", i
    return troughs, peaks, (lo if mode == "down" else None)


def _weakening(vals: list[float | None], lows: list[int], peaks: list[int]) -> bool | None:
    """Lower lows and lower highs over the last 2 cycles (S6.5); None when a value is
    missing."""
    l3, l2, l1 = lows[-3:]
    highs = [next((p for p in peaks if a < p < b), None) for a, b in ((l3, l2), (l2, l1))]
    if any(h is None for h in highs):
        return False
    xs = [vals[k] for k in (l3, l2, l1, *highs)]
    if any(x is None for x in xs):
        return None
    a, b, c, h1, h2 = xs
    return a > b > c and h1 > h2


def trough_row(engine, cik, as_of, bk: health.Book) -> Row:
    row = Row("Q2", "trough", "Trough vs prior trough (gross margin and ROIC)", "missing")
    oi = fy_points(engine, bk.cik, "operating_income", as_of)
    ric = trends.roic_inputs(engine, bk.cik, as_of)
    years, gms, roics = [], [], []
    for k, e in enumerate(bk.ends):
        r, g = bk.v("revenue", e), bk.gross(e)
        if r is None or g is None or not r:
            continue
        wd = bk_wd(engine, bk, e, as_of)
        years.append(e)
        gms.append((g + wd) / r * 100)
        cell = trends.roic(ric, e, bk.ends[k - 1] if k else None, oi)
        roics.append(cell.value * 100 if cell.value is not None else None)
    if len(gms) < 3:
        row.why = "insufficient history: fewer than 3 fiscal years with gross margin"
        return row
    troughs, peaks, cur = turning_points(gms)
    lows = troughs + ([cur] if cur is not None else [])
    lab = [fiscal_label(e) for e in years]
    row.value = (
        "gross-margin lows "
        + ", ".join(f"{lab[i]} {gms[i]:.1f}%" for i in lows)
        + "; highs "
        + ", ".join(f"{lab[i]} {gms[i]:.1f}%" for i in peaks)
    )
    if len(troughs) < 2 or len(lows) < 3:
        row.why = (
            f"insufficient history: {len(troughs)} confirmed prior trough(s) on 5 pp "
            "turning points (needs 2; D-M04-54)"
        )
        return row
    gw, rw = _weakening(gms, lows, peaks), _weakening(roics, lows, peaks)
    rtxt = ", ".join(
        f"{lab[i]} {roics[i]:.1f}%" if roics[i] is not None else f"{lab[i]} —"
        for i in sorted(set(lows[-3:] + peaks[-3:]))
    )
    row.value += f"; ROIC at those years {rtxt}"
    if rw is None:
        row.reading = "neutral"
        row.why = (
            "ROIC not computable at a turning-point year: intact needs ROIC agreeing "
            "with gross margin (D-M04-54)"
        )
    elif gw and rw:
        row.reading, row.why = "weakening", "lower lows and lower highs over 2 cycles in both"
    elif not gw and not rw:
        row.reading, row.why = (
            "intact",
            "neither gross margin nor ROIC shows 2 cycles of lower lows and highs",
        )
    else:
        row.reading, row.why = "neutral", "gross margin and ROIC disagree (D-M04-54)"
    row.why += "; write-down years adjusted with the tagged inventory write-down"
    return row


def bk_wd(engine, bk: health.Book, end: str, as_of: str) -> float:
    pts = getattr(bk, "_wd", None)
    if pts is None:
        pts = fy_points(engine, bk.cik, "inventory_writedown", as_of)
        bk._wd = pts  # type: ignore[attr-defined]
    p = at(pts, end)
    return float(p.value) if p is not None else 0.0


def capex_rd_row(engine, cik, as_of, bk: health.Book, rev_falling: bool, peer_list) -> Row:
    row = Row("Q2", "capex_rd", "Capex intensity and R&D level vs own 3-year average", "missing")
    tc = capex_mod.total_capex(engine, bk.cik, as_of)
    if not tc:
        row.why = "no total capex"
        return row
    ratios = []
    for t in tc:
        r = bk.v("revenue", t.end)
        ratios.append((t, t.value / r if r else None))
    usable = [(t, x) for t, x in ratios if x is not None]
    if len(usable) < 4:
        row.why = "fewer than 4 fiscal years with capex and revenue (needs the 3-year average)"
        return row
    window = usable[-4:]
    if any(t.definition_changed for t, _ in window):
        row.why = "not scored: capex definition changed inside the window (D-M04-3)"
        return row
    (te, ratio), prior = window[-1], window[:-1]
    latest = bk.latest()
    if latest and not near(te.end, latest):
        row.why = (
            f"no capex with revenue for the latest fiscal year {fiscal_label(latest)} as known "
            f"then (latest with both: {te.label}); an older year is not read"
        )
        return row
    avg = sum(x for _, x in prior) / 3
    mult = ratio / avg if avg else None
    # D-M04-100 as amended (live check 1; D-M04-54, -64): when revenue rose over the window,
    # a falling intensity is the revenue, not a cut — read the capex level instead
    revs = [bk.v("revenue", t.end) or 0.0 for t, _ in window]
    rev_avg = sum(revs[:-1]) / 3
    rev_chg = revs[-1] / rev_avg - 1 if rev_avg > 0 else None
    lvl_avg = sum(t.value for t, _ in prior) / 3
    lvl = te.value / lvl_avg if lvl_avg > 0 else None
    on_level = rev_chg is not None and rev_chg > REV_ROSE
    rd = bk.v("rd", te.end)
    rd_prior = [bk.v("rd", t.end) for t, _ in prior]
    rd_avg = sum(rd_prior) / 3 if rd is not None and all(v is not None for v in rd_prior) else None
    rd_txt = (
        f"R&D {rd / 1e6:,.0f}M vs 3-yr avg {rd_avg / 1e6:,.0f}M ({rd / rd_avg - 1:+.0%})"
        if rd_avg
        else "R&D not tagged: judged on capex alone"
    )
    lvl_txt = (
        f"capex {te.value / 1e6:,.0f}M vs 3-yr avg {lvl_avg / 1e6:,.0f}M = {lvl:.2f}×"
        if lvl is not None
        else "capex level: no positive 3-yr average"
    )
    basis = (
        f"revenue {_pct(rev_chg)} vs its 3-yr average"
        + (
            f" (> +{REV_ROSE:.0%}†): read on the capex level, not intensity"
            if on_level
            else ": read on intensity"
        )
        if rev_chg is not None
        else "revenue average ≤ 0: read on intensity"
    )
    row.value = (
        f"{te.label}: capex ÷ revenue {ratio:.1%} vs 3-yr avg {avg:.1%} = "
        f"{mult:.2f}× ({te.tag}); {lvl_txt}; {basis}; {rd_txt}"
    )
    row.number = lvl if on_level else mult
    row.sources = [Source(te.accession, te.filed, "A", f"capex {te.label}")]
    if mult is not None and mult > SURGE and rev_falling:
        row.reading = "neutral"
        row.why = (
            f"capex surge > {SURGE}×† its own average into falling revenue → neutral; "
            "see M05 (growth capex × ROIC; D-M04-64)"
        )
        return row
    cut_c = (
        (lvl is not None and lvl < 1 - CUT) if on_level else (mult is not None and mult < 1 - CUT)
    )
    cut_r = rd_avg is not None and rd < (1 - CUT) * rd_avg
    if not (cut_c or cut_r):
        row.reading = "intact"
        row.why = (
            "capex level (revenue rose) and R&D held near the own 3-year average (D-M04-100)"
            if on_level
            else "capex intensity and R&D held near the own 3-year average"
        )
        return row
    held = []
    for _name, pcik in peer_list:
        if pcik in peer_z.NOT_LIKE_FOR_LIKE:
            continue
        pb = health.Book(engine, pcik, as_of)
        mt = peers.match_period(pb.fy["revenue"], te.end, peers.TTM_TOL)
        if not mt.ok:
            continue
        pc = fy_points(engine, pcik, peer_z.PPE_CAPEX, as_of)
        cur = at(pc, mt.end)
        prs = [pb.prior(mt.end, k) for k in (1, 2, 3)]
        vals = [at(pc, e) if e else None for e in prs]
        prevs = [pb.v("revenue", e) for e in prs]
        r0 = pb.v("revenue", mt.end)
        if cur is None or None in vals or None in prevs or not r0:
            continue
        if on_level:  # like with like: the peer's capex level vs its own 3-year average
            pavg = sum(float(v.value) for v in vals) / 3
            if pavg > 0:
                held.append(float(cur.value) / pavg)
            continue
        pavg = sum(float(v.value) / r for v, r in zip(vals, prevs, strict=True)) / 3
        if pavg:
            held.append((float(cur.value) / r0) / pavg)
    what = ("capex level" if on_level else "capex intensity") if cut_c else "R&D"
    if not held:
        row.reading = "weakening"
        row.why = (
            f"{what} cut > {CUT:.0%}† below its own average; peers not compared (none comparable)"
        )
    elif statistics.median(held) >= 1 - CUT:
        row.reading = "weakening"
        row.why = (
            f"{what} cut > {CUT:.0%}† while peers hold (median {statistics.median(held):.2f}×)"
        )
    else:
        row.reading = "neutral"
        row.why = (
            f"{what} cut together with peers (median {statistics.median(held):.2f}×): "
            "a supply response"
        )
    return row


def guidance_row(engine, cik, as_of) -> Row:
    row = Row("Q2", "guidance", "Guidance record (guidance_hit_rate)", "missing")
    r = engine.execute(
        "SELECT * FROM signal WHERE cik = ? AND module_id = 'M04' AND signal = "
        "'guidance_hit_rate' AND timeframe = 'MY' AND as_of <= ? ORDER BY as_of DESC LIMIT 1",
        (cik, as_of),
    ).fetchone()
    if r is None:
        row.why = (
            f"no guidance_hit_rate row on or before {as_of} (the ledger holds 2025–26 releases)"
        )
        return row
    if r["value"] is None:
        row.why = (r["method"] or "missing").removeprefix("missing: ").split("; inputs:")[0]
        return row
    removed = engine.execute(
        "SELECT as_of FROM signal WHERE cik = ? AND module_id = 'M04' AND signal = "
        "'guidance_removed' AND timeframe = 'MY' AND value_text = 'removed' AND as_of <= ? "
        "AND as_of >= ? ORDER BY as_of DESC LIMIT 1",
        (cik, as_of, (_d(as_of) - timedelta(days=365)).isoformat()),
    ).fetchone()
    rate = float(r["value"])
    row.number = rate
    row.value = f"hit rate {rate:.0f}% (as of {r['as_of']})"
    row.sources = [
        Source(
            r["source_ref"] or "guidance",
            r["as_of"],
            r["evidence_grade"] or "A",
            "guidance_hit_rate",
        )
    ]
    repeated = "repeated: yes" in (r["method"] or "")
    if repeated or removed:
        row.reading = "weakening"
        row.why = (
            "2† misses in the last 4 guided quarters"
            if repeated
            else f"a core guide quietly removed ({removed['as_of']}, S1.7)"
        )
    else:
        row.reading = "intact"
        row.why = "no repeated misses and no quiet removal in 12 months (hit rate steady)"
    return row


def health_row(fq: health.Score) -> Row:
    row = Row("Q2", "health", "Health vote (F-quality 0–5)", "missing")
    row.value = f"{fq.known} of 5" + (f" ({fq.n} known)" if fq.n < 5 else "") + f" — {fq.text()}"
    row.sources = fq.sources
    if fq.band is None:
        row.why = fq.missing or "missing"
        return row
    row.reading = fq.band
    row.number = float(fq.known)
    row.why = "≥ 4 intact, 3 neutral, ≤ 2 weakening (D-M04-53, -59)"
    return row


def share_row(sh: market_share.ShareReading) -> Row:
    row = Row("Q2", "market_share", "Market share (owner entries, D-M04-68)", sh.reading)
    row.value = sh.text if sh.change_pp is not None else ""
    row.why = sh.text if sh.change_pp is None else ""
    row.number = sh.change_pp
    row.sources = sh.sources
    return row


# --- Resolution ------------------------------------------------------------------------------


def resolve(q: str, rows: list[Row]) -> Question:
    mine = [r for r in rows if r.q == q]
    applicable = sum(1 for r in mine if r.counted)
    present = [r for r in mine if r.counted and r.present]
    a, b = SIDES[q]
    counts = {
        a: sum(1 for r in present if r.reading == a),
        b: sum(1 for r in present if r.reading == b),
        "neutral": sum(1 for r in present if r.reading == "neutral"),
    }
    n = len(present)
    if n < MIN_PRESENT:
        return Question(q, n, applicable, counts, None, 0.0, False)
    lead = a if counts[a] >= counts[b] else b
    share = counts[lead] / n
    ok = (
        counts[lead] * MAJORITY[1] >= MAJORITY[0] * n
        and counts[lead] > counts[a if lead == b else b]
    )
    return Question(q, n, applicable, counts, lead, share, ok)


TABLE = {
    ("shared", "intact"): "CYCLICAL_TROUGH",
    ("shared", "weakening"): "CYCLE_PLUS_DAMAGE",
    ("company_specific", "intact"): "STUMBLE",
    ("company_specific", "weakening"): "STRUCTURAL_DECLINE",
}


def classify(active: bool, q1: Question, q2: Question) -> tuple[str, float | None]:
    """D-M04-56 as amended by D-M04-102 (live check 1): an active grid with a question below
    2 present rows cannot resolve → `insufficient_data` with no confidence (missing, never
    0.00) and no review item; M01 blocks tranches until the rows exist."""
    if not active:
        return "NO_SLOWDOWN", None
    if q1.present < MIN_PRESENT or q2.present < MIN_PRESENT:
        return INSUFFICIENT, None
    conf = round(min(q1.share, q2.share), 2)
    if q1.resolved and q2.resolved:
        return TABLE[(q1.lead, q2.lead)], conf
    return "AMBIGUOUS", conf


# --- M01 reading (D-M04-58 = D-M01-5) --------------------------------------------------------

RED_FLAGS = (
    ("distress_score", ("distress",)),
    ("non_reliance", ("open",)),
    ("restatement", ("4.02", "escalated")),
    ("special_items", ("warn",)),
    ("eq_cash", ("warn",)),
    ("negative_equity", ("warn",)),
    ("financing_pressure", ("warn",)),
)


def _latest_text(engine, cik, name, as_of) -> sqlite3.Row | None:
    return engine.execute(
        "SELECT value_text, as_of FROM signal WHERE cik = ? AND module_id = 'M04' AND signal = ? "
        "AND timeframe = 'MY' AND as_of <= ? ORDER BY as_of DESC LIMIT 1",
        (cik, name, as_of),
    ).fetchone()


def m04_rows(engine, c: CvD) -> m01_rules.M04Rows:
    """The live CvD as the M04 rows M01 reads (`m01_rules`, the single M01 reader; M09 Part 2,
    D-M09-15): gate state, filing status, the effective state (an owner answer named in the
    method, as `cvd_step` writes it), the open runway review and guidance removed as of
    `c.as_of`."""
    rows = m01_rules.M04Rows(c.cik)
    if c.gate is not None:
        rows.gate = m01_rules.Row(c.gate.state, c.as_of, "gate")
        if c.gate.runway_review:
            rows.runway = m01_rules.Row(None, c.as_of, "capex-funded review open (m04_runway)")
    if c.status in ("current", "stale", "overdue"):
        rows.filing = m01_rules.Row(c.status, c.as_of, "status")
    if c.state is not None:
        if c.state == INSUFFICIENT:
            method = f"missing: {INSUFFICIENT_WHY}"
        elif c.answer:
            method = f"owner answer {c.state} (computed {c.raw_state})"
        else:
            method = "computed"
        rows.cvd = m01_rules.Row(c.state, c.as_of, method)
    rows.guidance_removed = m01_rules.guidance_removed(engine, c.cik, c.as_of)
    return rows


OPEN = ("allowed", "first_tranche")  # m01_rules.rule3 states that let a tranche through


def m01_reading(engine, c: CvD) -> M01:
    """M01's reading of this CvD (D-M04-58 = D-M01-5). `m01_rules` decides on the live CvD
    (the single M01 reader, M09 Part 2, D-M09-15); the words are the M04 tab's since 8a."""
    rows = m04_rows(engine, c)
    r3, r7 = m01_rules.rule3(rows), m01_rules.rule7(rows)
    notes = []
    for name, bad in RED_FLAGS:
        r = _latest_text(engine, c.cik, name, c.as_of)
        if r is not None and r["value_text"] in bad:
            notes.append(f"{name} {r['value_text']}")
    return M01(_rule3_words(c, r3), _rule7_words(c, r3, r7), m01_rules.rule4(rows), notes)


def _rule3_words(c: CvD, r3: m01_rules.Reading) -> str:
    st, g = c.state, c.gate
    gs = g.state if g else "missing"
    if r3.state in OPEN:
        out = "allowed"
        if st == "STUMBLE":
            out = "allowed: you resolved the m04_cvd item as STUMBLE (D-M01-5)"
        if gs == "warn":
            out += " (gate warn counts as pass, D-M04-31)"
        if r3.state == "first_tranche":
            out += (
                "; stale: the first tranche may use the carried state, later tranches wait "
                "for the filing (D-M04-61)"
            )
        return out
    # blocked: the cause m01_rules found, in its order, in the tab's words
    if gs == "fail":
        return "blocked: survival gate fail overrides the grid (D-M04-31)"
    if gs not in m01_rules.PASS:
        why = ", ".join(g.missing) if g and g.missing else gs
        return f"blocked: gate {gs} ({why}; D-M04-35)"
    if c.overdue:
        return "blocked: filing overdue (D-M04-58, -61)"
    if st == INSUFFICIENT:
        qs = ", ".join(
            f"{q.q} {q.present} of {q.applicable}"
            for q in (c.q1, c.q2)
            if q is not None and q.present < MIN_PRESENT
        )
        return (
            f"blocked: CvD insufficient data ({INSUFFICIENT_WHY}: {qs}; no review item; "
            "D-M04-56, -58, -102)"
        )
    if st in m01_rules.DAMAGE:
        if st == "CYCLE_PLUS_DAMAGE" and not c.answer:
            return "blocked; the m04_cvd item asks you to confirm (D-M04-56, -58)"
        return "blocked (D-M04-58)"
    if st in ("AMBIGUOUS", "STUMBLE"):
        return (
            "blocked until you answer the m04_cvd item; your answer becomes the state "
            "(D-M04-56, -58)"
        )
    if st is None:
        return "blocked: no CvD state"
    return r3.text


def _rule7_words(c: CvD, r3: m01_rules.Reading, r7: m01_rules.Reading) -> str:
    if r7.state == "stronger":
        return "yes (CYCLICAL_TROUGH with a gate pass, D27; gauge not required, D-M04-62)"
    if r3.state not in OPEN:
        return "no"
    if c.state == "CYCLICAL_TROUGH":  # open tranches, CT, no strength: the runway review
        return "no: capex-funded runway review open (D-M04-38)"
    return f"no ({c.state})"


# --- Assembly --------------------------------------------------------------------------------


def stored_answer(engine: sqlite3.Connection, cik: str) -> dict | None:
    r = engine.execute(
        "SELECT detail FROM refresh_state WHERE name = ?", (ANSWER_KEY.format(cik=cik),)
    ).fetchone()
    if r is None or not r["detail"]:
        return None
    try:
        return json.loads(r["detail"])
    except json.JSONDecodeError:
        return None


def evaluate(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str | None,
    as_of: str,
    *,
    models: models_mod.ModelFile | None = None,
    calendar: bool = True,
    live_category: str | None = None,
    cache: dict | None = None,
    use_answer: bool = True,
) -> CvD:
    """The CvD state as known on `as_of`. `calendar=False` skips the filing-status test
    (historical cases without stored filings), as `gate.evaluate` does."""
    norm = normalize_cik(cik) or cik
    mf = models if models is not None else models_mod.load_safe()
    cache = cache if cache is not None else {}
    c = CvD(norm, ticker, as_of)
    act = activation(engine, norm, as_of)
    c.ref_end, c.ref_kind, c.latest_filed = act.ref, act.kind, act.filed
    c.tag, how = models_mod.route(engine, mf, norm, ticker, act.ref)
    if c.tag in EXCLUDED:
        c.excluded = f"not applicable ({c.tag}): {how}"
        return c
    treasury = c.tag == "asset_treasury"
    if treasury:  # bitcoin's price taken out of the operating-income test (D-M04-8, -100)
        act = activation(engine, norm, as_of, treasury=True)
    srow = stage_mod.confirmed(engine, norm)
    c.stage = srow["confirmed"] if srow else None
    c.gate = gate.evaluate(engine, norm, ticker, as_of, models=mf, today=as_of, calendar=calendar)
    bk = health.Book(engine, norm, as_of)
    c.f_quality = health.f_quality(engine, norm, as_of, stage=c.stage, tag=c.tag, book=bk)
    c.f_score = health.piotroski(engine, norm, as_of, book=bk)
    c.g_score = health.mohanram(engine, norm, ticker or norm, as_of, cache=cache, book=bk)
    if act.ref is None:
        c.missing = "no 12-month revenue stored"
        c.m01 = m01_reading(engine, c)
        return c
    c.sources = act.sources
    prev_as_of = (_d(act.filed) - timedelta(days=1)).isoformat() if act.filed else as_of
    c.triggers, c.tests = act.triggers, act.tests
    before = activation(engine, norm, prev_as_of, treasury=treasury) if act.filed else None
    c.active = bool(act.triggers) or bool(
        before and before.ref and before.ref != act.ref and before.triggers
    )
    if not act.triggers and c.active:
        c.triggers = [
            f"previous filing ({before.ref}) triggered: {'; '.join(before.triggers)} — "
            "switches off after 2 straight clear quarters (S6.9)"
        ]
    ps = peer_facts.peer_set(engine, ticker or norm, norm)
    peer_list = [(m["name"], m["cik"]) for m in ps.sec]
    c.peers = [name for name, _ in peer_list]
    me = peer_z._facts(engine, norm, as_of, cache)
    rev_row, c.deeper = revenue_row(engine, norm, ticker, as_of, prev_as_of, cache)
    gm_now = peer_z._gm(me, act.ref)
    rev_falling = act.rev_growth is not None and act.rev_growth < 0
    rows = [
        rev_row,
        Row(
            "Q1",
            "pricing",
            "Industry pricing / volume",
            "missing",
            why="(DS13) no industry price or volume series stored",
        ),
        inventory_row(engine, norm, ticker, as_of, act.ref, peer_list),
        supply_row(engine, norm, as_of, act.ref, peer_list, cache),
        cycle_row(
            engine, norm, as_of, act.ref, peer_z._v(me.rev, act.ref), gm_now, bk, rev_falling
        ),
    ]
    c.share = market_share.reading(engine, norm, as_of)
    rows += [
        share_row(c.share),
        gm_gap_row(engine, norm, as_of, me, act.ref, peer_list, cache),
        trough_row(engine, norm, as_of, bk),
        capex_rd_row(engine, norm, as_of, bk, rev_falling, peer_list),
        Row(
            "Q2",
            "moat",
            "Moat and challengers (M06)",
            "not_applicable",
            why="not applicable until M06 (S6.11)",
            counted=False,
        ),
        Row(
            "Q2",
            "customer",
            "Customer base (stickiness class)",
            "missing",
            why=f"{DEFERRED}: the customer row is Part 7b",
        ),
        guidance_row(engine, norm, as_of),
        health_row(c.f_quality),
        Row(
            "Q2",
            "r12",
            "R12 cause vote",
            "missing",
            counted=False,
            why=f"{DEFERRED}: Part 7b; counts only when it fires (D-M04-44, -56)",
        ),
    ]
    c.rows = rows
    c.q1, c.q2 = resolve("Q1", rows), resolve("Q2", rows)
    c.raw_state, c.confidence = classify(c.active, c.q1, c.q2)
    c.state = c.raw_state
    if use_answer and c.raw_state in REVIEW:
        a = stored_answer(engine, norm)
        if a and a.get("raw_state") == c.raw_state and a.get("answer") in STATES:
            c.answer, c.state = a, a["answer"]
    if calendar:
        srows = status_mod.evaluate(engine, norm, as_of, live_category=live_category)
        rec = status_mod.record_of(srows)
        if rec is None:
            c.status, c.status_text = "not evaluated", "no 10-K/10-Q/20-F stored"
        else:
            c.status = rec.status
            c.status_text = f"{rec.form} period {rec.period_end}, due {rec.due_date}; {rec.note}"
    nr = restate.non_reliance(engine, norm, act.ref)
    c.non_reliance = nr.mark if nr else ""
    c.m01 = m01_reading(engine, c)
    return c


def row_lines(c: CvD, indent: str = "    ") -> list[str]:
    """Each Q1 and Q2 row with its reading, value and reason (the grid and the regression
    lines print the same text)."""
    out = []
    for r in c.rows:
        what = r.value if r.present else ""
        why = f"missing: {r.why}" if r.reading == "missing" else r.why
        out.append(
            f"{indent}{r.q} {r.label}: {r.reading}"
            + (f" — {what}" if what else "")
            + (f" [{why}]" if why else "")
        )
    return out


def grid_lines(c: CvD) -> list[str]:
    """One grid for the log: state, confidence, coverage, each row's value or reason."""
    head = c.ticker or c.cik
    if c.excluded or c.missing:
        return [f"{head}: {c.excluded or 'missing: ' + c.missing}"]
    conf = f"{c.confidence:.2f}" if c.confidence is not None else "—"
    state = c.state + (f" (computed {c.raw_state}, owner answer)" if c.state != c.raw_state else "")
    if c.insufficient:
        state += f" ({INSUFFICIENT_WHY}; no review item)"
    out = [
        f"{head}: {state} · confidence {conf} · coverage {c.coverage_text()} · "
        f"{c.ref_kind} to {c.ref_end} · gate {c.gate.state if c.gate else '—'}"
        + (" · STALE" if c.stale else "")
        + (" · OVERDUE" if c.overdue else "")
    ]
    out.append(
        "    activation: "
        + ("; ".join(c.triggers) if c.active else "not active — " + "; ".join(c.tests))
    )
    out += row_lines(c)
    for s in (c.f_score, c.g_score):
        if s is not None:
            v = f"{s.known} of {s.n}" if s.points else "—"
            out.append(
                f"    shown, not voted — {s.kind} {s.label}: {v}"
                + (f" (missing: {s.missing})" if s.missing else "")
            )
    if c.m01:
        out.append(f"    M01: {c.m01.text()}")
    if c.non_reliance:
        out.append(f"    {c.non_reliance}")
    return out
