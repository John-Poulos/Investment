"""M05 Part 1: capex against demand (docs/M05_FUTURE_SPEND.md rules 1–4, 6; D-M05-4…7).

Pure reads of stored facts and M04 rows (0 requests); nothing here writes.

- **Series (D-M05-4, D-M05-9):** fiscal-year total capex on M04's own-history definition
  (`financials/capex.total_capex`, all stored years: `capex_split` keeps only 8, the median
  needs 9) ÷ the depreciation rung — `Depreciation`, else D&A (marked), one rung for the
  whole series, chosen like `capex_view` (the latest year's), never mixed. Revenue on the
  fiscal year (= TTM at the year end).
- **`capex_demand`** (rule 1, first match wins): AHEAD_OF_DEMAND (capex ÷ revenue > 1.5×†
  its own prior-3-FY average while revenue falls = D-M04-64, needs 3 prior years only; or
  expanding while revenue falls and no bookings line rises), BUILD_INTO_DEMAND (expanding:
  ratio above its own prior-8-FY median and capex YoY > 0, while revenue or a bookings line
  rises), CUTTING (capex YoY ≤ −20%†), MAINTENANCE (ratio 0.8–1.2†), STEADY. States 2–5 need
  8 prior years on the rung, else INSUFFICIENT_HISTORY. A `definition_changed` year is not
  scored (D-M04-3) and is left out of a later year's median window.
- **Bookings lines (D-M05-6):** RPO and deposits (contract liabilities: total, else current
  + noncurrent, else current only — labelled) at the fiscal year end vs a year earlier; a
  line "rises" when it is higher. Deposits are "repayable, not revenue", never added to RPO;
  a deposit balance more than doubling is marked only (the deposit wording is read in
  Part 2).
- **`growth_capex_roic`** (rule 3, D-M05-5): growth share from M04's `capex_split` row;
  ROIC from `trends.roic_series` (D-M04-107), now vs 3 FYs earlier.
- **Vote** (rule 4, D-M05-7, D-M02-62): positive only on BUILD_INTO_DEMAND with OCF ÷ capex
  ≥ 1 (D-M02-31) and a CvD state that is present and not STRUCTURAL_DECLINE or
  CYCLE_PLUS_DAMAGE; otherwise neutral with the reason ("CvD unresolved" when `cvd_state`
  is missing or `insufficient_data`).

Every † value is a labelled starting value, calibrated at tuning, not on the watchlist
(D32). Labelled "hypothesis, not backtested".
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import date

from engine.financials.capex import DA_TAGS, TotalCapex, at, fy_points, near, total_capex
from engine.sec.asof import AsOfPoint
from engine.sec.identity import normalize_cik
from engine.sec.xbrl_facts import Concept

MEDIAN_YEARS = 8
INTENSITY_YEARS = 3
AHEAD_MULT = 1.5  # † = D-M04-64's surge test
CUT = -0.20  # †
MAINT_LO, MAINT_HI = 0.8, 1.2  # †
GROWTH_SHARE_MIN = 0.25  # †
ROIC_BACK = 3
ROIC_DROP = 0.03  # 3 pp †
DEPOSIT_JUMP = 1.0  # † a deposit balance more than doubling is marked (no text check yet)
STALE_DAYS = 100  # a deposit balance ending this long before the newest fiscal year is stale
LABEL = "hypothesis, not backtested"
DAMAGE = ("STRUCTURAL_DECLINE", "CYCLE_PLUS_DAMAGE")
DA = Concept("d_and_a", DA_TAGS, "currency", "flow")
RUNG_NAME = {"depreciation": "depreciation", "da": "D&A (last rung: includes amortization)"}


def _prior_point(points: dict[str, AsOfPoint], end: str) -> AsOfPoint | None:
    """The point 350–380 days before `end` (a year earlier)."""
    e = date.fromisoformat(end)
    for k, p in points.items():
        if 350 <= (e - date.fromisoformat(k)).days <= 380:
            return p
    return None


def _m(x: float | None) -> str:
    if x is None:
        return "—"
    sign = "−" if x < 0 else ""
    x = abs(x)
    return f"{sign}${x / 1e9:,.2f}B" if x >= 1e9 else f"{sign}${x / 1e6:,.0f}M"


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:+.1%}".replace("-", "−")


# --- Series ------------------------------------------------------------------------------------


@dataclass
class DemandYear:
    end: str
    label: str
    capex: TotalCapex
    rung_value: float | None
    revenue: AsOfPoint | None
    dep_point: AsOfPoint | None = None

    @property
    def ratio(self) -> float | None:
        if self.rung_value is None or self.rung_value <= 0:
            return None
        return self.capex.value / self.rung_value

    @property
    def intensity(self) -> float | None:
        if self.revenue is None or self.revenue.value <= 0:
            return None
        return self.capex.value / float(self.revenue.value)

    @property
    def filed(self) -> str:
        return max([self.capex.filed] + [p.filed for p in (self.revenue, self.dep_point) if p])


@dataclass
class Series:
    cik: str
    rung: str  # depreciation | da | not_split
    years: list[DemandYear]
    rpo: dict[str, AsOfPoint]
    deposits: dict[str, dict[str, AsOfPoint]]  # concept → end → point
    ocf: dict[str, AsOfPoint]


def build_series(engine: sqlite3.Connection, cik: str, as_of: str) -> Series:
    norm = normalize_cik(cik) or cik
    totals = total_capex(engine, norm, as_of, window=MEDIAN_YEARS + 1)
    dep = fy_points(engine, norm, "depreciation", as_of)
    da = fy_points(engine, norm, DA, as_of)
    rev = fy_points(engine, norm, "revenue", as_of)
    rung = "not_split"
    if totals:
        last = totals[-1].end
        rung = "depreciation" if at(dep, last) else "da" if at(da, last) else "not_split"
    src = dep if rung == "depreciation" else da if rung == "da" else {}
    years = []
    for t in totals:
        d = at(src, t.end)
        years.append(DemandYear(t.end, t.label, t, float(d.value) if d else None, at(rev, t.end),
                                d))  # fmt: skip
    deposits = {
        c: fy_points(engine, norm, c, as_of, "I")
        for c in ("contract_liabilities_total", "contract_liabilities",
                  "contract_liabilities_noncurrent")
    }  # fmt: skip
    return Series(norm, rung, years, fy_points(engine, norm, "rpo", as_of, "I"), deposits,
                  fy_points(engine, norm, "operating_cash_flow", as_of))  # fmt: skip


# --- Bookings lines: RPO and deposits ----------------------------------------------------------


@dataclass(frozen=True)
class Deposit:
    end: str
    value: float
    how: str  # "total" | "current + noncurrent" | "current only"
    points: tuple[AsOfPoint, ...]

    @property
    def filed(self) -> str:
        return max(p.filed for p in self.points)

    @property
    def accession(self) -> str:
        return max(self.points, key=lambda p: (p.filed, p.accession)).accession


def deposit_at(s: Series, end: str) -> Deposit | None:
    tot = at(s.deposits["contract_liabilities_total"], end)
    if tot is not None:
        return Deposit(tot.end, float(tot.value), "total", (tot,))
    cur = at(s.deposits["contract_liabilities"], end)
    non = at(s.deposits["contract_liabilities_noncurrent"], end)
    if cur is not None and non is not None:
        return Deposit(cur.end, float(cur.value + non.value), "current + noncurrent", (cur, non))
    if cur is not None:
        return Deposit(cur.end, float(cur.value), "current only (no noncurrent tag)", (cur,))
    return None


@dataclass(frozen=True)
class DepositsLine:
    """Customer deposits = contract liabilities: "repayable, not revenue" (D-M05-6)."""

    now: Deposit | None
    prior: Deposit | None
    stale: str | None = None  # newest deposit tag ends well before the newest fiscal year
    # Part 2 (rule 6): the deposit sentence found in stored text; None = not read, "" = none
    wording: str | None = None

    @property
    def yoy(self) -> float | None:
        if self.now is None or self.prior is None or self.prior.value <= 0:
            return None
        if self.now.how != self.prior.how:
            return None  # a different basis a year earlier is not compared
        return self.now.value / self.prior.value - 1

    @property
    def jump(self) -> bool:
        return self.yoy is not None and self.yoy > DEPOSIT_JUMP

    def text(self) -> str:
        if self.stale:
            return f"deposits (contract liabilities): {self.stale}"
        if self.now is None:
            return "deposits (contract liabilities): not tagged"
        out = (f"deposits {_m(self.now.value)} at {self.now.end} (contract liabilities, "
               f"{self.now.how}; repayable, not revenue, never added to RPO)")  # fmt: skip
        if self.prior is None:
            out += "; no balance a year earlier"
        elif self.yoy is None:
            out += (f"; a year earlier {_m(self.prior.value)} on another basis "
                    f"({self.prior.how}), not compared")  # fmt: skip
        else:
            out += f"; a year earlier {_m(self.prior.value)} ({_pct(self.yoy)})"
        if self.jump:
            if self.wording is None:
                out += ("; mark: balance more than doubled — deposit wording not read yet "
                        "(M05 Part 2 commitments pass not run), mark only")  # fmt: skip
            elif self.wording:
                out += ("; mark: balance more than doubled — deposit wording found: "
                        f"{self.wording}")  # fmt: skip
            else:
                out += ("; mark: balance more than doubled — no deposit wording in the stored "
                        "10-K / 10-Q text, mark only (rule 6)")  # fmt: skip
        return out


def deposits_line(s: Series, end: str | None = None) -> DepositsLine:
    """At `end` (a fiscal year end) or at the latest stored balance."""
    if end is None:
        ends = [e for pts in s.deposits.values() for e in pts]
        if not ends:
            return DepositsLine(None, None)
        end = max(ends)
        # live check 1 (INTC: last tagged 2021-12-25): a balance older than the newest
        # fiscal year end by more than a quarter is not shown as the current balance
        newest = max((y.end for y in s.years), default=None)
        if newest and (date.fromisoformat(newest) - date.fromisoformat(end)).days > STALE_DAYS:
            return DepositsLine(None, None, stale=f"missing: last tagged {end}, before the "
                                f"newest fiscal year ({newest})")  # fmt: skip
    now = deposit_at(s, end)
    if now is None:
        return DepositsLine(None, None)
    e = date.fromisoformat(now.end)
    prior = None
    for k in sorted({x for pts in s.deposits.values() for x in pts}):
        if 350 <= (e - date.fromisoformat(k)).days <= 380:
            prior = deposit_at(s, k)
            if prior is not None and prior.how == now.how:
                break
    return DepositsLine(now, prior)


@dataclass(frozen=True)
class Bookings:
    rpo_now: AsOfPoint | None
    rpo_prior: AsOfPoint | None
    deposits: DepositsLine

    @property
    def rpo_yoy(self) -> float | None:
        if self.rpo_now is None or self.rpo_prior is None or self.rpo_prior.value <= 0:
            return None
        return float(self.rpo_now.value / self.rpo_prior.value) - 1

    @property
    def rising(self) -> list[str]:
        out = []
        if self.rpo_yoy is not None and self.rpo_yoy > 0:
            out.append(f"RPO {_pct(self.rpo_yoy)}")
        if self.deposits.yoy is not None and self.deposits.yoy > 0:
            out.append(f"deposits {_pct(self.deposits.yoy)}")
        return out

    @property
    def stored(self) -> bool:
        return self.rpo_now is not None or self.deposits.now is not None

    def text(self) -> str:
        bits = []
        if self.rpo_now is None:
            bits.append("RPO not tagged at the year end")
        elif self.rpo_yoy is None:
            bits.append(f"RPO {_m(float(self.rpo_now.value))}, none a year earlier")
        else:
            bits.append(f"RPO {_m(float(self.rpo_now.value))} ({_pct(self.rpo_yoy)})")
        d = self.deposits
        if d.now is None:
            bits.append("deposits not tagged")
        elif d.yoy is None:
            bits.append(f"deposits {_m(d.now.value)} ({d.now.how}), not comparable a year earlier")
        else:
            bits.append(
                f"deposits {_m(d.now.value)} ({d.now.how}, {_pct(d.yoy)})"
                + ("; mark: more than doubled, wording not checked" if d.jump else "")
            )
        return "bookings: " + "; ".join(bits)


def bookings_at(s: Series, end: str) -> Bookings:
    now = at(s.rpo, end)
    prior = _prior_point(s.rpo, now.end) if now else None
    return Bookings(now, prior, deposits_line(s, end) if _has_deposit(s, end) else
                    DepositsLine(None, None))  # fmt: skip


def _has_deposit(s: Series, end: str) -> bool:
    return any(at(pts, end) is not None for pts in s.deposits.values())


# --- capex_demand ------------------------------------------------------------------------------


@dataclass
class Demand:
    label: str
    end: str
    state: str | None  # None → missing
    missing: str | None = None
    ratio: float | None = None
    median: float | None = None
    capex_yoy: float | None = None
    rev_yoy: float | None = None
    intensity: float | None = None
    intensity_avg: float | None = None
    bookings: Bookings | None = None
    why: str = ""
    notes: list[str] = field(default_factory=list)
    year: DemandYear | None = None

    @property
    def expanding(self) -> bool:
        return (self.ratio is not None and self.median is not None and self.ratio > self.median
                and self.capex_yoy is not None and self.capex_yoy > 0)  # fmt: skip


def classify(s: Series, idx: int) -> Demand:
    """`capex_demand` for the fiscal year `s.years[idx]` (rule 1, first match wins)."""
    y = s.years[idx]
    d = Demand(y.label, y.end, None, year=y)
    prev = s.years[idx - 1] if idx > 0 else None
    if prev is not None and not near_year(prev.end, y.end):
        prev = None
    d.capex_yoy = (y.capex.value / prev.capex.value - 1) if prev and prev.capex.value > 0 else None
    if y.revenue is not None and prev is not None and prev.revenue is not None and \
            prev.revenue.value > 0:  # fmt: skip
        d.rev_yoy = float(y.revenue.value / prev.revenue.value) - 1
    d.ratio = y.ratio
    d.intensity = y.intensity
    d.bookings = bookings_at(s, y.end)
    if y.capex.definition_changed:
        d.missing = "capex definition changed this year, not scored (D-M04-3)"
        return d
    # 1a. AHEAD_OF_DEMAND = D-M04-64: intensity > 1.5× its own prior-3-FY average while
    # revenue falls (needs 3 prior years only, runs first).
    prior3 = s.years[max(0, idx - INTENSITY_YEARS) : idx]
    ints = [p.intensity for p in prior3 if not p.capex.definition_changed]
    if len(prior3) == INTENSITY_YEARS and all(v is not None for v in ints) and \
            len(ints) == INTENSITY_YEARS and d.intensity is not None:  # fmt: skip
        d.intensity_avg = sum(ints) / INTENSITY_YEARS  # type: ignore[arg-type]
        if d.rev_yoy is not None and d.rev_yoy < 0 and d.intensity > AHEAD_MULT * d.intensity_avg:
            d.state = "AHEAD_OF_DEMAND"
            d.why = (f"capex ÷ revenue {d.intensity:.1%} = {d.intensity / d.intensity_avg:.2f}× "
                     f"its own 3-FY average {d.intensity_avg:.1%} (> {AHEAD_MULT}×†) while revenue "
                     f"{_pct(d.rev_yoy)} (D-M04-64 test)")  # fmt: skip
            return d
    if s.rung == "not_split":
        d.missing = "no depreciation or D&A (not split)"
        return d
    if d.ratio is None:
        d.missing = f"no {RUNG_NAME[s.rung]} fact this year (rung never mixed)"
        return d
    window = s.years[max(0, idx - MEDIAN_YEARS) : idx]
    usable = [p for p in window if p.ratio is not None and not p.capex.definition_changed]
    if len(window) < MEDIAN_YEARS or len(usable) < MEDIAN_YEARS:
        d.state = "INSUFFICIENT_HISTORY"
        d.why = (f"{len(usable)} of {MEDIAN_YEARS} prior fiscal years with capex ÷ "
                 f"{RUNG_NAME[s.rung]} (a definition-changed year or a year without the rung "
                 "does not count)")  # fmt: skip
        return d
    d.median = statistics.median(p.ratio for p in usable)  # type: ignore[misc]
    rising = d.bookings.rising
    rev_up = d.rev_yoy is not None and d.rev_yoy > 0
    rev_down = d.rev_yoy is not None and d.rev_yoy < 0
    base = (f"capex ÷ {RUNG_NAME[s.rung]} {d.ratio:.2f} vs own prior-{MEDIAN_YEARS}-FY median "
            f"{d.median:.2f}, capex {_pct(d.capex_yoy)}")  # fmt: skip
    if d.expanding and rev_down and not rising:
        d.state = "AHEAD_OF_DEMAND"
        d.why = f"expanding ({base}) while revenue {_pct(d.rev_yoy)} and no bookings line rises" + (
            "" if d.bookings.stored else " (no RPO or deposits stored)"
        )
    elif d.expanding and (rev_up or rising):
        d.state = "BUILD_INTO_DEMAND"
        ev = ([f"revenue {_pct(d.rev_yoy)}"] if rev_up else []) + rising
        d.why = f"expanding ({base}) into {', '.join(ev)}"
    elif d.capex_yoy is not None and d.capex_yoy <= CUT:
        d.state = "CUTTING"
        d.why = f"capex {_pct(d.capex_yoy)} (≤ {CUT:.0%}†); {base}"
    elif MAINT_LO <= d.ratio <= MAINT_HI:
        d.state = "MAINTENANCE"
        d.why = f"capex ÷ {RUNG_NAME[s.rung]} {d.ratio:.2f} within {MAINT_LO}–{MAINT_HI}†"
    else:
        d.state = "STEADY"
        d.why = base + (" (expanding, revenue flat or unknown and no bookings line rises)"
                        if d.expanding else "")  # fmt: skip
    if d.rev_yoy is None:
        d.notes.append("revenue YoY missing (neither rising nor falling)")
    return d


def near_year(a: str, b: str) -> bool:
    """`a` is the fiscal year before `b` (330–400 days apart)."""
    return 330 <= (date.fromisoformat(b) - date.fromisoformat(a)).days <= 400


def strip(s: Series, n: int = MEDIAN_YEARS) -> list[Demand]:
    """The last `n` fiscal years, each read on its own prior window (the UI strip)."""
    return [classify(s, i) for i in range(max(0, len(s.years) - n), len(s.years))]


# --- The vote (rule 4) -------------------------------------------------------------------------


@dataclass(frozen=True)
class Vote:
    positive: bool
    text: str


def vote(state: str | None, ocf_cover: float | None, ocf_how: str, cvd_state: str | None,
         cvd_missing: str | None) -> Vote:  # fmt: skip
    """Rule 4 (D-M05-7, D-M02-62): positive only when all three hold."""
    if state != "BUILD_INTO_DEMAND":
        return Vote(False, f"vote: neutral — state {state or 'missing'}, not BUILD_INTO_DEMAND")
    if ocf_cover is None:
        return Vote(False, f"vote: neutral — OCF ÷ capex missing ({ocf_how})")
    if ocf_cover < 1:
        return Vote(False, f"vote: neutral — OCF ÷ capex {ocf_cover:.2f} < 1 ({ocf_how}; "
                    "D-M02-31)")  # fmt: skip
    if cvd_state is None:
        return Vote(False, f"vote: neutral — CvD unresolved ({cvd_missing}; conservative "
                    "reading of D-M04-102)")  # fmt: skip
    if cvd_state in DAMAGE:
        return Vote(False, f"vote: neutral — CvD {cvd_state}")
    return Vote(True, f"vote: positive — BUILD_INTO_DEMAND, OCF ÷ capex {ocf_cover:.2f} "
                f"({ocf_how}), CvD {cvd_state} (D-M05-7)")  # fmt: skip


def ocf_cover(engine: sqlite3.Connection, s: Series, y: DemandYear) -> tuple[float | None, str]:
    """OCF ÷ capex for the scored fiscal year: M02's capital-allocation window on the
    company's own capex definition (D-M02-31) when its fiscal year is this one, else OCF ÷
    M04's own-history total capex, labelled."""
    try:
        from engine.moneyflow.actuals import latest_clause, overrides_by_cik
        from engine.moneyflow.allocation import allocation

        for w in allocation(engine, s.cik, latest_clause(engine, s.cik),
                            overrides_by_cik(engine).get(s.cik)):  # fmt: skip
            if w.ptype == "FY" and near(w.end, y.end) and w.ocf_cover is not None:
                if w.ocf is not None and w.ocf < 0:
                    return w.ocf_cover, f"{w.label}, negative OCF; own-definition capex"
                return w.ocf_cover, f"{w.label}, own-definition capex (D-M02-31)"
    except Exception as e:  # noqa: BLE001 — the M02 recipe must not stop the M05 row
        fallback_note = f"M02 window not read: {type(e).__name__}"
    else:
        fallback_note = "M02 window not for this year"
    o = at(s.ocf, y.end)
    if o is None or y.capex.value <= 0:
        return None, f"no operating cash flow for {y.label}"
    return float(o.value) / y.capex.value, (f"{y.label} OCF ÷ total capex on {y.capex.tag} "
                                            f"({fallback_note})")  # fmt: skip


# --- growth_capex_roic (rule 3) ----------------------------------------------------------------


@dataclass
class GrowthRoic:
    state: str | None
    value: float | None = None  # ROIC now
    missing: str | None = None
    why: str = ""
    label: str = ""
    filed: str = ""
    sources: list[tuple[str, str, str]] = field(default_factory=list)  # accession, filed, what


def split_row(engine: sqlite3.Connection, cik: str) -> sqlite3.Row | None:
    return engine.execute(
        "SELECT * FROM capex_split WHERE cik = ? ORDER BY period_end DESC LIMIT 1",
        (normalize_cik(cik) or cik,),
    ).fetchone()


def growth_roic(engine: sqlite3.Connection, cik: str, as_of: str) -> GrowthRoic:
    from engine.financials import peers, trends

    norm = normalize_cik(cik) or cik
    row = split_row(engine, norm)
    if row is None:
        return GrowthRoic(None, missing="no capex_split row (M04 local pass not run)")
    g = GrowthRoic(None, label=row["fiscal_label"], filed=row["total_filed"] or "")
    if row["total_accession"]:
        g.sources.append((row["total_accession"], row["total_filed"] or "", "capex_split"))
    if row["definition_changed"]:
        g.missing = f"{row['fiscal_label']}: capex definition changed, not scored (D-M04-3)"
        return g
    if row["total"] is None or row["growth"] is None or not row["total"]:
        g.missing = ("no depreciation or D&A (not split)" if row["rung"] == "not_split"
                     else f"{row['fiscal_label']}: {row['method'] or 'not split'}")  # fmt: skip
        return g
    share = float(row["growth"]) / float(row["total"])
    marks = f"; capex_split marks: {row['marks']}" if row["marks"] else ""
    head = (f"{row['fiscal_label']}: growth share {share:.1%} = growth {_m(row['growth'])} ÷ "
            f"total {_m(row['total'])} ({row['method']}){marks}")  # fmt: skip
    series = trends.roic_series(engine, norm, as_of, years=ROIC_BACK + 1)
    now = next((r for r in series if near(r.end, row["period_end"])), None)
    then = None
    if now is not None:
        target = f"FY{int(now.label[2:]) - ROIC_BACK}"
        then = next((r for r in series if r.label == target), None)
    if now is not None and now.cell.accession:
        g.sources.append((now.cell.accession, now.cell.filed, "operating income"))
        g.filed = max(g.filed, now.cell.filed)
    rev = fy_points(engine, norm, "revenue", as_of)
    acq = fy_points(engine, norm, "acquisitions", as_of)
    gw = fy_points(engine, norm, peers.GOODWILL, as_of, "I")
    r_, a_ = at(rev, row["period_end"]), at(acq, row["period_end"])
    g1 = at(gw, row["period_end"])
    g0 = _prior_point(gw, g1.end) if g1 else None
    acq_note = peers.acquisition_note(float(r_.value) if r_ else None,
                                      float(a_.value) if a_ else None,
                                      float(g1.value) if g1 else None,
                                      float(g0.value) if g0 else None)  # fmt: skip
    tail = f"; {acq_note} (inflates invested capital)" if acq_note else ""
    if share < GROWTH_SHARE_MIN:
        g.state = "MAINTENANCE_ONLY"
        g.value = now.cell.value if now and now.cell.value is not None else None
        g.why = (
            f"{head} < {GROWTH_SHARE_MIN:.0%}†"
            + (f"; ROIC {now.cell.value:.1%} shown" if g.value is not None else "")
            + tail
        )
        return g
    if now is None:
        g.missing = f"no ROIC for {row['fiscal_label']} (no operating income)"
        return g
    if now.cell.value is None:
        if now.cell.text.startswith(trends.NM):
            g.state = trends.NM
            g.why = f"{head}; ROIC {now.cell.text}" + tail
            return g
        g.missing = f"ROIC {now.cell.text.removeprefix('missing: ')}"
        g.why = head
        return g
    g.value = now.cell.value
    roic_how = f"ROIC {now.label} {now.cell.value:.1%} ({now.cell.text})"
    if then is None or then.cell.value is None:
        why = then.cell.text if then is not None else f"no fiscal year {ROIC_BACK} years earlier"
        g.state = "INSUFFICIENT_HISTORY"
        g.why = f"{head}; {roic_how}; ROIC {ROIC_BACK} FYs earlier missing ({why})" + tail
        return g
    diff = now.cell.value - then.cell.value
    cmp_ = f"vs {then.label} {then.cell.value:.1%} ({diff * 100:+.1f} pp)".replace("-", "−")
    if now.cell.value <= 0:  # owner, live check 1 (amends D-M05-5): RIVN −114.6% read ACCRETIVE
        g.state = "NEGATIVE_ROIC"
        trend = "improving" if diff >= 0 else "worsening"
        g.why = f"{head}; {roic_how} {cmp_}; {trend}, not yet earning a return" + tail
        return g
    if diff >= 0:
        g.state = "ACCRETIVE"
    elif diff < -ROIC_DROP:
        g.state = "DILUTING"
    else:
        g.state = "ACCRETIVE"
        cmp_ += f"; mark: flat (within {ROIC_DROP * 100:.0f} pp†)"
    g.why = f"{head}; {roic_how} {cmp_}" + tail
    return g
