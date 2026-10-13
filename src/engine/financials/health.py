"""Health scores for the CvD grid (D-M04-53, -59, -65; S6.7; M04 Part 8a).

- **F-quality (0–5), the only health vote in Q2:** accruals (CFO > NI), leverage (long-term
  debt ÷ average total assets fell), liquidity (current ratio rose), equity (no extreme
  issuance, D-M04-65) and CFO > 0 (D-M04-59). ≥ 4 intact, 3 neutral, ≤ 2 weakening.
  A point whose input is missing is missing; the vote is decided only when the missing
  points cannot move it out of its band (D-M04-56 spirit: missing never counts as 0).
- **Equity point (D-M04-65) while Part 5 is deferred (MVP, D31):** the Round 3 measure is
  the change in basic weighted-average shares, both years from one annual report where
  possible (split-safe, D-M04-22); with no issuance band yet (Part 5), the point is kept
  unless shares rose more than 10%† (below D-M04-23's CY2025 extreme cut of +12.1%, so the
  stricter reading) — D-M04-101. Routed by tag then stage: an unconfirmed stage → missing
  (D-M04-65); `issuance_funded` → missing ("financing_pressure not built", Part 5).
- **Piotroski F (0–9), shown, not voted:** ROA, CFO, ΔROA, accruals, Δleverage, Δcurrent
  ratio, no equity issued (net basic-share growth ≤ 2%, S6.7), Δgross margin, Δasset
  turnover; ROA and turnover on beginning-of-year assets (pack worked example C).
- **Mohanram G (0–8), shown, not voted:** each signal against the confirmed peers' median
  at matched fiscal years (±45 d): ROA, CFO ÷ assets, accruals ÷ assets (lower scores),
  VARROA and VARSGR over 8 quarters (lower scores), R&D, capex (PP&E tag; NVDA/AMZN not
  like-for-like) and advertising ÷ assets; end-of-year assets (pack: NVDA FY2023 10.6%).
  Needs ≥ 5 comparable peers (S6.7); "n of 8" = signals with inputs. Mohanram's low
  book-to-market population is not checked (shown for every name; D-M04-104).

Values are as known on `as_of` (`facts_as_of`, latest version). Missing stays missing.
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass, field

from engine.financials import peer_facts, peer_z, peers
from engine.financials.capex import at, fiscal_label, fy_points, near
from engine.sec.asof import AsOfPoint, facts_as_of
from engine.sec.identity import normalize_cik
from engine.signals import Source

EQUITY_LOSS = 0.10  # MVP starting value † (Part 5 deferred; D-M04-101)
F_EQUITY = 0.02  # Piotroski equity signal: net basic-share growth > 2% (S6.7)
INTACT_AT, WEAK_AT = 4, 2  # F-quality bands (D-M04-59)
G_MIN_PEERS = 5  # S6.7
G_MIN_INPUTS = 6
FY_CONCEPTS = (
    "revenue",
    "gross_profit",
    "cost_of_revenue",
    "net_income",
    "operating_cash_flow",
    "shares_basic_wavg",
    "rd",
    "advertising",
)
I_CONCEPTS = ("total_assets", "long_term_debt", "current_assets", "current_liabilities")


@dataclass(frozen=True)
class Pt:
    name: str
    value: int | None  # 1 / 0 / None (missing)
    text: str


@dataclass
class Score:
    kind: str  # f_quality | f_score | g_score
    end: str | None
    label: str
    points: list[Pt] = field(default_factory=list)
    band: str | None = None  # intact | neutral | weakening (F-quality only)
    missing: str = ""  # why there is no value
    sources: list[Source] = field(default_factory=list)
    filed: str = ""
    note: str = ""

    @property
    def known(self) -> int:
        return sum(p.value or 0 for p in self.points if p.value is not None)

    @property
    def n(self) -> int:
        return sum(1 for p in self.points if p.value is not None)

    @property
    def value(self) -> int | None:
        if self.missing:
            return None
        return self.known

    def text(self) -> str:
        out = "; ".join(
            f"{p.name} {'—' if p.value is None else p.value} ({p.text})" for p in self.points
        )
        return out + (f"; {self.note}" if self.note else "")


class Book:
    """One company's fiscal-year flows and instants as known on `as_of`."""

    def __init__(self, engine: sqlite3.Connection, cik: str, as_of: str) -> None:
        self.cik = normalize_cik(cik) or cik
        self.as_of = as_of
        self.fy = {c: fy_points(engine, self.cik, c, as_of) for c in FY_CONCEPTS}
        self.i = {c: fy_points(engine, self.cik, c, as_of, "I") for c in I_CONCEPTS}
        ends: list[str] = []
        for e in sorted(self.fy["revenue"]) or sorted(self.fy["net_income"]):
            if not any(near(e, x) for x in ends):
                ends.append(e)
        self.ends = ends

    def v(self, concept: str, end: str | None) -> float | None:
        if end is None:
            return None
        src = self.fy.get(concept) if concept in self.fy else self.i.get(concept)
        p = at(src or {}, end)
        return float(p.value) if p is not None else None

    def p(self, concept: str, end: str | None) -> AsOfPoint | None:
        if end is None:
            return None
        src = self.fy.get(concept) if concept in self.fy else self.i.get(concept)
        return at(src or {}, end)

    def prior(self, end: str, back: int = 1) -> str | None:
        i = next((k for k, e in enumerate(self.ends) if near(e, end)), None)
        if i is None or i - back < 0:
            return None
        return self.ends[i - back]

    def gross(self, end: str | None) -> float | None:
        g = self.v("gross_profit", end)
        if g is not None:
            return g
        r, c = self.v("revenue", end), self.v("cost_of_revenue", end)
        return r - c if r is not None and c is not None else None

    def latest(self) -> str | None:
        return self.ends[-1] if self.ends else None


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _avg(a: float | None, b: float | None) -> float | None:
    return (a + b) / 2 if a is not None and b is not None else None


def leverage(bk: Book, end: str) -> tuple[float | None, str]:
    """Long-term debt ÷ average total assets; no long-term-debt fact → none on the balance
    sheet (named). Average needs the prior year's assets, else the year-end assets."""
    ltd = bk.v("long_term_debt", end)
    how = ""
    if ltd is None:
        ltd, how = 0.0, "no long-term-debt fact: taken as none"
    ta, ta0 = bk.v("total_assets", end), bk.v("total_assets", bk.prior(end))
    base = _avg(ta, ta0)
    if base is None:
        base, how = ta, (how + "; " if how else "") + "year-end assets (no prior year)"
    return _div(ltd, base), how


def _cr(bk: Book, end: str | None) -> float | None:
    return _div(bk.v("current_assets", end), bk.v("current_liabilities", end))


def equity_change(bk: Book, end: str) -> tuple[float | None, str]:
    """Basic weighted-average shares, this year vs last (D-M04-22); one filing when the
    latest annual report carries both years."""
    p1, p0 = bk.p("shares_basic_wavg", end), bk.p("shares_basic_wavg", bk.prior(end))
    if p1 is None or p0 is None or not p0.value:
        return None, "missing: basic weighted-average shares for both years"
    same = (
        "both years from one filing"
        if p1.accession == p0.accession
        else ("years from different filings (split check by the filing's own values not possible)")
    )
    return float(p1.value) / float(p0.value) - 1, same


def _sources(bk: Book, end: str, names: tuple[str, ...]) -> list[Source]:
    out, seen = [], set()
    for n in names:
        p = bk.p(n, end)
        if p is not None and p.accession not in seen:
            seen.add(p.accession)
            out.append(Source(p.accession, p.filed, "A", f"{p.concept} {p.end}"))
    return out


def band(known: int, unknown: int) -> str | None:
    """The F-quality band, decided only when the unknown points cannot change it."""

    def b(x: int) -> str:
        return "intact" if x >= INTACT_AT else "weakening" if x <= WEAK_AT else "neutral"

    lo, hi = b(known), b(known + unknown)
    return lo if lo == hi else None


def f_quality(
    engine: sqlite3.Connection,
    cik: str,
    as_of: str,
    *,
    stage: str | None,
    tag: str | None = None,
    end: str | None = None,
    book: Book | None = None,
) -> Score:
    bk = book or Book(engine, cik, as_of)
    end = end or bk.latest()
    sc = Score("f_quality", end, fiscal_label(end) if end else "—")
    if end is None:
        sc.missing = "no fiscal-year revenue or net income stored"
        return sc
    p = bk.prior(end)
    ni, cfo = bk.v("net_income", end), bk.v("operating_cash_flow", end)
    pts = sc.points
    if ni is None or cfo is None:
        pts.append(Pt("accruals", None, "missing: net income or CFO"))
    else:
        pts.append(Pt("accruals", int(cfo > ni), f"CFO {cfo / 1e6:,.0f}M vs NI {ni / 1e6:,.0f}M"))
    lv1, h1 = leverage(bk, end)
    lv0, h0 = leverage(bk, p) if p else (None, "")
    if lv1 is None or lv0 is None:
        pts.append(Pt("leverage", None, "missing: total assets for this or the prior year"))
    else:
        none_both = bk.v("long_term_debt", end) is None and bk.v("long_term_debt", p) is None
        got = 1 if none_both or lv1 < lv0 else 0
        extra = "; no long-term debt either year" if none_both else ""
        pts.append(
            Pt(
                "leverage",
                got,
                f"LT debt ÷ average assets {lv0:.1%} → {lv1:.1%}{extra}"
                + (f" ({h1})" if h1 and not none_both else ""),
            )
        )
    c1, c0 = _cr(bk, end), _cr(bk, p)
    if c1 is None or c0 is None:
        pts.append(Pt("liquidity", None, "missing: current assets or liabilities"))
    else:
        pts.append(Pt("liquidity", int(c1 > c0), f"current ratio {c0:.2f} → {c1:.2f}"))
    pts.append(_equity_point(bk, end, stage, tag))
    if cfo is None:
        pts.append(Pt("cfo_positive", None, "missing: CFO"))
    else:
        pts.append(Pt("cfo_positive", int(cfo > 0), f"CFO {cfo / 1e6:,.0f}M"))
    unknown = sum(1 for x in pts if x.value is None)
    sc.band = band(sc.known, unknown)
    if sc.band is None:
        sc.missing = (
            f"{unknown} point(s) missing and they decide the band ({sc.known} of "
            f"{5 - unknown} known)"
        )
    elif unknown:
        sc.note = (
            f"band decided without the missing point(s): {sc.known} known + {unknown} "
            "missing cannot leave it"
        )
    sc.sources = _sources(
        bk,
        end,
        (
            "net_income",
            "operating_cash_flow",
            "total_assets",
            "current_assets",
            "shares_basic_wavg",
        ),
    )
    sc.filed = max((s.date for s in sc.sources), default="")
    return sc


def _equity_point(bk: Book, end: str, stage: str | None, tag: str | None) -> Pt:
    chg, how = equity_change(bk, end)
    shown = f"basic shares {chg:+.1%} ({how})" if chg is not None else how
    if tag == "issuance_funded":
        return Pt(
            "equity",
            None,
            f"missing: issuance_funded — the point follows "
            f"financing_pressure, not built (Part 5 deferred, D-M04-65); {shown}",
        )
    if stage is None:
        return Pt("equity", None, f"missing: stage unconfirmed (D-M04-65); {shown}")
    if chg is None:
        return Pt("equity", None, shown)
    lost = chg > EQUITY_LOSS
    return Pt(
        "equity",
        int(not lost),
        f"{shown}; Part 5 deferred: no issuance band — kept "
        f"unless shares rose > {EQUITY_LOSS:.0%}† (D-M04-101); stage {stage}",
    )


def piotroski(
    engine: sqlite3.Connection,
    cik: str,
    as_of: str,
    *,
    end: str | None = None,
    book: Book | None = None,
) -> Score:
    bk = book or Book(engine, cik, as_of)
    end = end or bk.latest()
    sc = Score("f_score", end, fiscal_label(end) if end else "—")
    if end is None:
        sc.missing = "no fiscal-year revenue or net income stored"
        return sc
    p, pp = bk.prior(end), bk.prior(end, 2)
    ni, ni0 = bk.v("net_income", end), bk.v("net_income", p)
    cfo = bk.v("operating_cash_flow", end)
    ta0, ta00 = bk.v("total_assets", p), bk.v("total_assets", pp)
    roa, roa0 = _div(ni, ta0), _div(ni0, ta00)
    pts = sc.points

    def add(name: str, ok: bool | None, text: str) -> None:
        pts.append(Pt(name, None if ok is None else int(ok), text))

    add(
        "roa",
        None if roa is None else roa > 0,
        f"ROA {roa:.1%}" if roa is not None else "missing: NI or beginning assets",
    )
    add(
        "cfo",
        None if cfo is None else cfo > 0,
        f"CFO {cfo / 1e6:,.0f}M" if cfo is not None else "missing: CFO",
    )
    add(
        "d_roa",
        None if roa is None or roa0 is None else roa > roa0,
        f"ROA {roa0:.1%} → {roa:.1%}"
        if roa is not None and roa0 is not None
        else "missing: prior ROA",
    )
    add(
        "accruals",
        None if cfo is None or ni is None else cfo > ni,
        "CFO > NI"
        if cfo is not None and ni is not None and cfo > ni
        else ("CFO ≤ NI" if cfo is not None and ni is not None else "missing"),
    )
    lv1, _ = leverage(bk, end)
    lv0, _ = leverage(bk, p) if p else (None, "")
    add(
        "d_leverage",
        None if lv1 is None or lv0 is None else lv1 < lv0,
        f"{lv0:.1%} → {lv1:.1%}" if lv1 is not None and lv0 is not None else "missing",
    )
    c1, c0 = _cr(bk, end), _cr(bk, p)
    add(
        "d_current",
        None if c1 is None or c0 is None else c1 > c0,
        f"{c0:.2f} → {c1:.2f}" if c1 is not None and c0 is not None else "missing",
    )
    chg, _ = equity_change(bk, end)
    add(
        "no_equity",
        None if chg is None else chg <= F_EQUITY,
        f"basic shares {chg:+.1%} (≤ {F_EQUITY:.0%})" if chg is not None else "missing",
    )
    g1, g0 = _div(bk.gross(end), bk.v("revenue", end)), _div(bk.gross(p), bk.v("revenue", p))
    add(
        "d_gross_margin",
        None if g1 is None or g0 is None else g1 > g0,
        f"{g0:.1%} → {g1:.1%}" if g1 is not None and g0 is not None else "missing",
    )
    t1, t0 = _div(bk.v("revenue", end), ta0), _div(bk.v("revenue", p), ta00)
    add(
        "d_turnover",
        None if t1 is None or t0 is None else t1 > t0,
        f"{t0:.3f} → {t1:.3f}" if t1 is not None and t0 is not None else "missing",
    )
    gone = [x.name for x in pts if x.value is None]
    if gone:
        sc.missing = f"inputs missing for {', '.join(gone)} ({sc.known} of {sc.n} known)"
    sc.sources = _sources(bk, end, ("net_income", "operating_cash_flow", "total_assets"))
    sc.filed = max((s.date for s in sc.sources), default="")
    return sc


# --- Mohanram G -------------------------------------------------------------------------------

G_SIGNALS = (
    ("roa", "higher"),
    ("cfo_assets", "higher"),
    ("accruals_assets", "lower"),
    ("varroa", "lower"),
    ("varsgr", "lower"),
    ("rd_assets", "higher"),
    ("capex_assets", "higher"),
    ("adv_assets", "higher"),
)


def g_points(
    company: dict[str, float | None], peer_values: list[dict[str, float | None]]
) -> list[Pt]:
    """G signals against the peer median (pure; the pack's worked example C)."""
    out = []
    for name, better in G_SIGNALS:
        mine = company.get(name)
        vals = [p[name] for p in peer_values if p.get(name) is not None]
        if mine is None:
            out.append(Pt(name, None, "missing: company input"))
            continue
        if not vals:
            out.append(Pt(name, None, "missing: no peer value"))
            continue
        med = statistics.median(vals)
        ok = mine > med if better == "higher" else mine < med
        out.append(
            Pt(
                name,
                int(ok),
                f"{mine:.1%} vs median {med:.1%} (n {len(vals)}; "
                f"{'higher' if better == 'higher' else 'lower'} scores)",
            )
        )
    return out


def _quarters(engine, cik, concept, as_of) -> dict[str, AsOfPoint]:
    return {p.end: p for p in facts_as_of(engine, cik, concept, as_of, ptype="Q").points}


def _variance(xs: list[float]) -> float | None:
    return statistics.pvariance(xs) if len(xs) >= 2 else None


def g_inputs(
    engine: sqlite3.Connection, cik: str, as_of: str, end: str, book: Book | None = None
) -> dict[str, float | None]:
    """One company's G inputs at fiscal year `end` (end-of-year assets)."""
    bk = book or Book(engine, cik, as_of)
    ta = bk.v("total_assets", end)
    ni, cfo = bk.v("net_income", end), bk.v("operating_cash_flow", end)
    capex = at(peer_z.twelve(engine, bk.cik, peer_z.PPE_CAPEX, as_of), end)
    out: dict[str, float | None] = {
        "roa": _div(ni, ta),
        "cfo_assets": _div(cfo, ta),
        "accruals_assets": _div(ni - cfo, ta) if ni is not None and cfo is not None else None,
        "rd_assets": _div(bk.v("rd", end), ta),
        "capex_assets": None
        if bk.cik in peer_z.NOT_LIKE_FOR_LIKE or capex is None
        else _div(float(capex.value), ta),
        "adv_assets": _div(bk.v("advertising", end), ta),
    }
    qni, qrev = (
        _quarters(engine, bk.cik, "net_income", as_of),
        _quarters(engine, bk.cik, "revenue", as_of),
    )
    assets = bk.i["total_assets"]
    qs = sorted(e for e in qrev if e <= end)[-9:]
    roas = [
        float(qni[e].value) / float(a.value)
        for e in qs[-8:]
        if e in qni and (a := at(assets, e)) is not None and a.value
    ]
    out["varroa"] = (
        _variance(roas) ** 0.5 if len(roas) == 8 and _variance(roas) is not None else None
    )
    grow = [
        float(qrev[b].value) / float(qrev[a].value) - 1
        for a, b in zip(qs, qs[1:], strict=False)
        if qrev[a].value
    ]
    out["varsgr"] = _variance(grow[-8:]) ** 0.5 if len(grow) >= 8 else None
    return out


def mohanram(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str,
    as_of: str,
    *,
    cache: dict | None = None,
    book: Book | None = None,
) -> Score:
    bk = book or Book(engine, cik, as_of)
    end = bk.latest()
    sc = Score("g_score", end, fiscal_label(end) if end else "—")
    sc.note = "Mohanram's low book-to-market population not checked (D-M04-104)"
    if end is None:
        sc.missing = "no fiscal-year revenue stored"
        return sc
    ps = peer_facts.peer_set(engine, ticker, bk.cik)
    if not ps.confirmed:
        sc.missing = peer_facts.NOT_CONFIRMED
        return sc
    peer_vals, names = [], []
    for m in ps.sec:
        pb = Book(engine, m["cik"], as_of)
        mt = peers.match_period(pb.fy["revenue"], end, peers.TTM_TOL)
        if not mt.ok:
            continue
        peer_vals.append(g_inputs(engine, m["cik"], as_of, mt.end, pb))
        names.append(m["name"])
    sc.points = g_points(g_inputs(engine, bk.cik, as_of, end, bk), peer_vals)
    if len(peer_vals) < G_MIN_PEERS:
        sc.missing = (
            f"fewer than {G_MIN_PEERS} peers with a comparable fiscal year "
            f"({len(peer_vals)}: {', '.join(names) or 'none'}; S6.7)"
        )
    elif sc.n < G_MIN_INPUTS:
        sc.missing = f"{sc.n} of 8 inputs (needs ≥ {G_MIN_INPUTS}, S6.7)"
    sc.sources = _sources(bk, end, ("net_income", "operating_cash_flow", "total_assets"))
    sc.filed = max((s.date for s in sc.sources), default="")
    return sc
