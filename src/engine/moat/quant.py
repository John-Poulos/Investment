"""M06 quant leg: `moat_quant` from 10 fiscal years of book ROIC (rule 1; D-M06-1, -2).

Per company, the last `window_years` (10) fiscal years with operating income, each with
ROIC from M04's `trends.roic_series` (D-M04-107: S6.5 NOPAT ÷ average invested capital, the
year before as the opening balance, so 10 years need 11 balance sheets), gross margin
(`trends._gross`: reported, else revenue − cost of revenue, labelled) and operating margin.
These standard rows are computed for every company, N_A ones included (D32).

Class on the years with a computable ROIC (missing and `not_meaningful` years left out,
never interpolated, never zero):

- fewer than 7 → `short_history` (7–9 → "short window" in the method);
- ROIC > hurdle (8%†) in ≥ 80%† of them → `persistent`;
- else the window median > hurdle **and** ≥ 1 of the last 3 computable years above it →
  `through_cycle` (the guard keeps a decline like INTC's out; D32: built on MU's memory
  cycle, so a single boom elsewhere can lift the median — checked at tuning);
- else `weak`;
- average invested capital ≤ 0 in most of the window's years → `not_meaningful`;
- a model tag fund, financial (incl. untagged SIC 6000–6999 via `models.route`), reit,
  asset_treasury or spac_shell on the latest period → `not_applicable`; a tag that covers
  only earlier periods (INFQ's shell years) leaves those years out, labelled.
  `issuance_funded` is rated normally.

`value` = share of window years above the hurdle (0–1). The method carries the class at
hurdle ± 2 pp, the years within the ±2 pp band, every year's ROIC, the GM median and
dispersion (IQR ÷ 1.35), the peer GM robust z (M04 Part 2) and the labels: "excludes leases",
"consolidated only", R&D-heavy (label only), M04's acquisition flag per year.
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass, field

from engine.financials import models as models_mod
from engine.financials import trends
from engine.financials.capex import at, fy_points, near
from engine.financials.trends import NM
from engine.moat.params import Params
from engine.sec.identity import normalize_cik
from engine.signals import Source

NA_TAGS = ("fund", "financial", "reit", "asset_treasury", "spac_shell")
STATES = ("persistent", "through_cycle", "weak", "short_history", "not_meaningful",
          "not_applicable")  # fmt: skip
LABELS = (
    "excludes leases (unmapped)",
    "consolidated only (a segment moat, e.g. AWS inside AMZN, is invisible)",
)
TAG_TEXT = {
    "fund": "fund: ROIC shown, not rated",
    "financial": "financial: book ROIC meaningless for banks and insurers; shown, not rated",
    "reit": "REIT: ROIC shown, not rated",
    "asset_treasury": "asset vehicle: ROIC shown, not rated",
    "spac_shell": "SPAC shell period: ROIC shown, not rated",
}


@dataclass(frozen=True)
class Year:
    label: str
    end: str
    roic: float | None
    roic_text: str  # method, or "missing: …" / "not_meaningful: …"
    gm: float | None  # percent
    gm_text: str
    om: float | None  # percent
    om_text: str
    accession: str = ""  # operating income point (the 10-K behind the year)
    filed: str = ""
    excluded: str = ""  # a tag period: shown, not rated
    flags: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return self.roic is not None and not self.excluded

    @property
    def not_meaningful(self) -> bool:
        return self.roic is None and self.roic_text.startswith(NM) and not self.excluded


@dataclass(frozen=True)
class Reading:
    """The class on one hurdle."""

    state: str
    share: float | None
    above: int
    n: int
    median: float | None
    recent_above: int
    recent_n: int


def classify(values: list[float], hurdle: float, p: Params) -> Reading:
    """Rule 1 on the window's computable ROIC values, oldest first."""
    n = len(values)
    above = sum(v > hurdle for v in values)
    share = above / n if n else None
    med = statistics.median(values) if n else None
    recent = values[-p.recent_years :]
    ra = sum(v > hurdle for v in recent)
    if n < p.min_years:
        state = "short_history"
    elif above >= p.persistent_share * n - 1e-9:
        state = "persistent"
    elif med is not None and med > hurdle and ra >= 1:
        state = "through_cycle"
    else:
        state = "weak"
    return Reading(state, share, above, n, med, ra, len(recent))


@dataclass
class Quant:
    cik: str
    ticker: str
    params: Params
    years: list[Year]  # the displayed window, oldest first (every company, D32)
    state: str | None = None  # one of STATES; None = missing
    missing: str | None = None
    reading: Reading | None = None
    tag: str | None = None
    route_how: str = ""
    sensitivity: list[tuple[float, Reading]] = field(default_factory=list)
    near_hurdle: list[str] = field(default_factory=list)
    nm_years: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    gm_median: float | None = None
    gm_dispersion: float | None = None  # IQR ÷ 1.35, pp
    gm_n: int = 0
    peer_gm: str = "peer z: not computed"
    sources: list[Source] = field(default_factory=list)
    as_of: str = ""

    @property
    def value(self) -> float | None:
        return self.reading.share if self.reading is not None else None

    @property
    def window(self) -> list[Year]:
        return [y for y in self.years if y.usable]

    @property
    def newest_fy(self) -> str | None:
        """The newest fiscal year with a 10-K behind it (re-open rule, D-M06-8)."""
        ys = [y for y in self.years if y.accession]
        return ys[-1].label if ys else None

    @property
    def newest_filed(self) -> str | None:
        return max((y.filed for y in self.years if y.filed), default=None)

    def headline(self) -> str:
        if self.state is None:
            return f"missing: {self.missing}"
        if self.state == "not_applicable":
            return TAG_TEXT.get(self.tag or "", "not applicable")
        r = self.reading
        if r is None or r.share is None:
            return self.state
        return f"{self.state}: {r.above} of {r.n} years above {self.params.hurdle:.0%}†"

    def method(self) -> str:
        p = self.params
        parts: list[str] = []
        if self.state == "not_applicable":
            parts.append(f"{TAG_TEXT.get(self.tag or '', 'not applicable')} ({self.route_how})")
        elif self.state == "not_meaningful":
            parts.append(f"not_meaningful: average invested capital ≤ 0 in "
                         f"{len(self.nm_years)} of the window's years "
                         f"({', '.join(self.nm_years)}); the class is not rated")  # fmt: skip
        elif self.reading is not None:
            r = self.reading
            head = (f"{self.state}: ROIC > {p.hurdle:.0%}† in {r.above} of {r.n} fiscal years "
                    f"({_pct(r.share)}; persistent ≥ {p.persistent_share:.0%}†)")  # fmt: skip
            if r.n:
                head += (f"; window median {_pct(r.median, 1)}; last {r.recent_n} years above: "
                         f"{r.recent_above}")  # fmt: skip
            parts.append(head)
            if self.window:
                w = self.window
                span = f"window {w[0].label}–{w[-1].label}"
                if p.min_years <= r.n < p.window_years:
                    span += f" (short window: {r.n} computable years)"
                parts.append(span)
            if self.sensitivity:
                sens = "; ".join(f"at {h:.0%}: {s.state} ({_pct(s.share)})"
                                 for h, s in self.sensitivity)  # fmt: skip
                parts.append(f"±{p.band_pp * 100:.0f} pp (D-M06-1): {sens}")
            if self.near_hurdle:
                parts.append(f"within ±{p.band_pp * 100:.0f} pp of the hurdle: "
                             f"{', '.join(self.near_hurdle)}")  # fmt: skip
            if self.state == "through_cycle":
                parts.append("D32: through_cycle was built on MU's memory cycle; elsewhere one "
                             "boom can lift the median (guard: the last-3-years rule)")  # fmt: skip
        yrs = []
        for y in self.years:
            if y.roic is not None:
                txt = _pct(y.roic, 1)
            elif y.roic_text.startswith(NM):
                txt = "n/m (IC ≤ 0)"
            else:
                txt = "—"
            if y.excluded:
                txt += f" [{y.excluded}]"
            yrs.append(f"{y.label} {txt}")
        if yrs:
            parts.append("ROIC per year: " + ", ".join(yrs))
        if self.gm_median is not None:
            disp = (f", dispersion (IQR ÷ 1.35) {self.gm_dispersion:.1f} pp"
                    if self.gm_dispersion is not None else "")  # fmt: skip
            parts.append(f"GM median {self.gm_median:.1f}% over {self.gm_n} years{disp}")
        else:
            parts.append("GM: missing (no gross profit or cost of revenue)")
        parts.append(self.peer_gm)
        parts += self.labels
        if self.state != "not_applicable" and self.route_how:
            parts.append(self.route_how)
        parts.append(f"S6.5 book ROIC (M04 trends.roic_series); {p.version}")
        return "; ".join(x for x in parts if x)


def _pct(v: float | None, digits: int = 0) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.{digits}f}%".replace("-", "−")


def _ends(points: dict) -> list[str]:
    ends = sorted(points)
    return [e for i, e in enumerate(ends) if not any(near(e, x) for x in ends[:i])]


def _margin(num, rev, end: str, what: str) -> tuple[float | None, str]:
    r = at(rev, end)
    if r is None or not r.value:
        return None, "missing: no revenue"
    if num is None:
        return None, f"missing: {what}"
    return float(num) / float(r.value) * 100, ""


def compute(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str,
    as_of: str,
    p: Params,
    mf: models_mod.ModelFile,
    *,
    peers: bool = True,
) -> Quant:
    """The quant leg for one company (0 requests; point-in-time on `as_of`)."""
    norm = normalize_cik(cik) or cik
    q = Quant(norm, ticker, p, [])
    series = trends.roic_series(engine, norm, as_of, years=p.window_years)
    rev = fy_points(engine, norm, "revenue", as_of)
    gp = fy_points(engine, norm, "gross_profit", as_of)
    cost = fy_points(engine, norm, "cost_of_revenue", as_of)
    oi = fy_points(engine, norm, "operating_income", as_of)
    rd = fy_points(engine, norm, "rd", as_of)
    if series:
        skeleton = [(y.label, y.end, y.cell) for y in series]
    else:  # no operating income at all (banks, funds): revenue years, ROIC missing
        skeleton = [(trends.fiscal_label(e), e, trends.Cell(None, "missing: operating income"))
                    for e in _ends(rev)[-p.window_years :]]  # fmt: skip
    latest = skeleton[-1][1] if skeleton else None
    q.tag, q.route_how = models_mod.route(engine, mf, norm, ticker, latest)
    for label, end, cell in skeleton:
        g, ghow, _ = trends._gross(rev, gp, cost, end)
        gm, gwhy = _margin(g, rev, end, ghow)
        o = at(oi, end)
        om, owhy = _margin(o.value if o else None, rev, end, "no operating income")
        ytag, _ = models_mod.route(engine, mf, norm, ticker, end)
        excluded = f"{ytag} period, not rated" if ytag in NA_TAGS else ""
        q.years.append(Year(
            label, end, cell.value, cell.text, gm, ghow if gm is not None else gwhy, om, owhy,
            o.accession if o else "", o.filed if o else "", excluded,
        ))  # fmt: skip
        if o is not None:
            q.sources.append(Source(o.accession, o.filed, "A", f"{label} operating income"))
    q.as_of = max((s.date for s in q.sources), default=as_of)
    _labels(engine, q, rev, rd, as_of)
    gms = [y.gm for y in q.years if y.gm is not None]
    q.gm_n = len(gms)
    if gms:
        q.gm_median = statistics.median(gms)
        if len(gms) >= 2:
            qs = statistics.quantiles(gms, n=4, method="inclusive")
            q.gm_dispersion = (qs[2] - qs[0]) / 1.35
    if peers and q.tag not in models_mod.EXCLUDED:
        try:
            from engine.financials import peer_z

            q.peer_gm = peer_z.compare(engine, ticker, norm, as_of).signal_text("gm")
        except Exception as e:  # noqa: BLE001 — a peer read must not stop the quant leg
            q.peer_gm = f"peer z: not read ({type(e).__name__})"
    elif q.tag in models_mod.EXCLUDED:
        q.peer_gm = f"peer z: missing: {q.tag} (no peers, D-M04-8)"
    else:
        q.peer_gm = "peer GM z: not read on this page (see the Financials tab)"

    if q.tag in NA_TAGS:
        q.state = "not_applicable"
        return q
    if not q.years:
        q.missing = "no fiscal-year operating income or revenue stored"
        return q
    if not q.sources:
        q.missing = "no fiscal-year operating income stored"
        return q
    values = [y.roic for y in q.window]
    q.nm_years = [y.label for y in q.years if y.not_meaningful]
    rated = len(values) + len(q.nm_years)
    if q.nm_years and len(q.nm_years) * 2 > rated:
        q.state = "not_meaningful"
        return q
    q.reading = classify(values, p.hurdle, p)
    q.state = q.reading.state
    if q.state != "short_history":
        q.sensitivity = [(h, classify(values, h, p))
                         for h in (p.hurdle - p.band_pp, p.hurdle + p.band_pp)]  # fmt: skip
    q.near_hurdle = [y.label for y in q.window if abs(y.roic - p.hurdle) <= p.band_pp + 1e-12]
    return q


def _labels(engine, q: Quant, rev, rd, as_of: str) -> None:
    q.labels = list(LABELS)
    if q.years:
        last = q.years[-1]
        r, d = at(rev, last.end), at(rd, last.end)
        if r is not None and d is not None and r.value:
            share = float(d.value) / float(r.value)
            if share >= q.params.rd_heavy_share:
                q.labels.append(f"R&D-heavy (R&D {share:.0%} of {last.label} revenue, "
                                f"expensed and left out of invested capital: book ROIC "
                                f"misreads the return; label only, "
                                f"≥ {q.params.rd_heavy_share:.0%}†)")  # fmt: skip
    try:
        from engine.financials import peer_z

        f = peer_z.Facts(engine, q.cik, as_of)
        flagged = []
        for i, y in enumerate(q.years):
            fl = tuple(x for x in peer_z._flags(f, y.end) if x)
            if fl:
                q.years[i] = Year(y.label, y.end, y.roic, y.roic_text, y.gm, y.gm_text, y.om,
                                  y.om_text, y.accession, y.filed, y.excluded, fl)  # fmt: skip
                flagged += [f"{y.label}: {x}" for x in fl if "53-week" not in x]
        if flagged:
            q.labels.append("M04 flags beside: " + "; ".join(flagged))
    except Exception as e:  # noqa: BLE001 — a flag read must not stop the quant leg
        q.labels.append(f"acquisition flags not read ({type(e).__name__})")
