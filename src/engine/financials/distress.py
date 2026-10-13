"""`distress_score` (M04 Part 4a; D-M04-31, S4.4, S4.8): Altman Z for manufacturers (SIC
2000–3999, GFS included), Z'' otherwise, and Ohlson's O as information. Never a gate input.

- **Z** = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5 (X1 working capital ÷ assets, X2
  retained earnings ÷ assets, X3 EBIT ÷ assets with TTM operating income as the EBIT
  proxy, X4 market value of equity ÷ total liabilities, X5 TTM revenue ÷ assets); zones
  distress < 1.81, grey 1.81–2.99, safe > 2.99 (S-new-36). Market value = the class-summed
  cover count (D-M04-2) × the close; the close date is in the method. Z without X4 shown.
- **Z''** = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4' (X4' book equity ÷ total liabilities),
  stored without the +3.25 constant against 1.10 / 2.60 (Altman's 4.35 / 5.85 with it,
  S-new-r4-1). For a manufacturer it is shown beside Z (Rivian Q2 2026: −5.37).
- **Ohlson O** (Model 1, S-new-r4-2): total assets in dollars, the GNP implicit price
  deflator rebased to 1968 = 100 for the year before the balance sheet, OCF as the FUTL
  proxy (labelled); P = 1 ÷ (1 + e^−O) beside the paper's 0.038 cut-off. Information only.
- In the distress zone → warning; while the gate passes → `m04_score_gap` review (S4.8).
  Stage-labelled from the owner-confirmed stage (D-M04-7: unconfirmed → labelled, not
  counted). `asset_treasury` → not meaningful; `fund`, `financial`, untagged FF12 group 11,
  `reit` and `spac_shell` → not applicable (D-M04-8).
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

from engine.financials import models as models_mod
from engine.financials import shares, stage
from engine.sec.asof import AsOfPoint, facts_as_of
from engine.sec.identity import normalize_cik
from engine.signals import Source

Z_ZONES = (1.81, 2.99)
ZPP_ZONES = (1.10, 2.60)
KINDS = {"Z": "manufacturer, SIC 2000–3999", "Z''": "non-manufacturer, no constant"}
O_CUTOFF = 0.038  # Ohlson (1980) p. 126: minimises the sum of error rates
# GNP implicit price deflator (FRED GNPDEF, 2017 = 100) rebased to 1968 = 100 (1968 average
# 18.24), annual; the values the M04 review read (S-new-r4-2). A missing year leaves O
# missing (the owner may add years from FRED here).
GNPDEF_1968 = {2020: 577.0, 2021: 603.0, 2025: 706.0}


def zone(variant: str, value: float) -> str:
    lo, hi = Z_ZONES if variant == "Z" else ZPP_ZONES
    return "distress" if value < lo else ("grey" if value <= hi else "safe")


def is_manufacturer(sic: str | None) -> bool:
    return bool(sic) and sic.isdigit() and 2000 <= int(sic) <= 3999


@dataclass
class Score:
    cik: str
    variant: str | None = None  # "Z" | "Z''"
    value: float | None = None
    zone: str = ""
    x: dict[str, float] = field(default_factory=dict)
    without_x4: float | None = None
    zpp: float | None = None  # Z'' beside Z for a manufacturer
    zpp_zone: str = ""
    o_value: float | None = None
    o_p: float | None = None
    o_note: str = ""
    balance_date: str | None = None
    close_note: str = ""
    stage_label: str = ""
    counted: bool = True
    missing: str = ""
    not_meaningful: str = ""
    notes: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)

    @property
    def warning(self) -> bool:
        return self.zone == "distress"

    def text(self) -> str:
        if self.not_meaningful:
            return self.not_meaningful
        if self.value is None:
            return f"missing: {self.missing}"
        return f"{self.variant} {self.value:.2f} {self.zone}"

    def method(self) -> str:
        bits = []
        if self.variant:
            bits.append(
                f"{self.variant} ({KINDS[self.variant]}); "
                f"zones {'1.81 / 2.99' if self.variant == 'Z' else '1.10 / 2.60'}"
            )
        if self.x:
            bits.append(", ".join(f"{k} {v:.3f}" for k, v in self.x.items()))
        if self.without_x4 is not None:
            bits.append(f"without X4 {self.without_x4:.2f}")
        if self.zpp is not None and self.variant == "Z":
            bits.append(f"Z'' {self.zpp:.2f} {self.zpp_zone} (shown beside)")
        if self.close_note:
            bits.append(self.close_note)
        if self.balance_date:
            bits.append(f"balance sheet {self.balance_date}")
        if self.o_p is not None:
            bits.append(
                f"Ohlson O {self.o_value:.2f}, P {self.o_p:.3f} vs {O_CUTOFF} cut-off "
                "(information; OCF as the FUTL proxy)"
            )
        elif self.o_note:
            bits.append(f"Ohlson O: {self.o_note}")
        if self.stage_label:
            bits.append(self.stage_label)
        bits += self.notes
        bits.append("warning only, never a gate input (D-M04-31)")
        return "; ".join(bits)


def _pts(engine, cik, concept, as_of, ptype) -> dict[str, AsOfPoint]:
    return {p.end: p for p in facts_as_of(engine, cik, concept, as_of, ptype=ptype).points}


def _at(points: dict[str, AsOfPoint], end: str, days: int = 10) -> AsOfPoint | None:
    if end in points:
        return points[end]
    d = date.fromisoformat(end)
    return next(
        (p for e, p in points.items() if abs((date.fromisoformat(e) - d).days) <= days), None
    )


def twelve_at(engine, cik, concept, as_of, end) -> AsOfPoint | None:
    """TTM at `end`, else the fiscal year ending there."""
    return _at(_pts(engine, cik, concept, as_of, "TTM"), end) or _at(
        _pts(engine, cik, concept, as_of, "FY"), end
    )


def stage_label(engine: sqlite3.Connection, cik: str) -> tuple[str, bool]:
    conf = stage.confirmed(engine, cik)
    if conf:
        return f"stage {stage.STAGE_NAMES[conf['confirmed']]} (confirmed)", True
    return "stage unconfirmed: labelled, not counted (D-M04-7)", False


def market_value(
    engine: sqlite3.Connection, cik: str, as_of: str, close_day: str | None
) -> tuple[float | None, str, list[Source]]:
    covers = [
        v for v in shares.cover_counts(engine, cik) if v.value is not None and v.date <= as_of
    ]
    if not covers:
        return None, "missing: no cover share count", []
    v = covers[0]
    close = shares.close_on(engine, cik, close_day or as_of)
    if close is None:
        return None, f"missing: no close on or before {close_day or as_of}", []
    mv = v.value * close[0]
    note = (
        f"market value {mv / 1e6:,.0f}M = cover shares {v.value:,.0f} ({v.date}) × close "
        f"${close[0]:,.2f} of {close[1]}"
    )
    return (
        mv,
        note,
        [
            Source(v.accession, v.first_filed or v.date, "A", "cover shares"),
            Source(f"close {close[1]}", close[1], "A", "Tiingo close"),
        ],
    )


def score(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str | None,
    as_of: str,
    *,
    models: models_mod.ModelFile | None = None,
    close_day: str | None = None,
) -> Score:
    norm = normalize_cik(cik) or cik
    mf = models if models is not None else models_mod.load_safe()
    s = Score(norm)
    ta_pts = _pts(engine, norm, "total_assets", as_of, "I")
    b = s.balance_date = max(ta_pts) if ta_pts else None
    tag, how = models_mod.route(engine, mf, norm, ticker, b)
    if tag == "asset_treasury":
        s.not_meaningful = "not_meaningful"
        s.notes.append(f"asset_treasury: Z not meaningful (D-M04-8; {how})")
        return s
    if tag in ("fund", "financial", "reit", "spac_shell"):
        s.not_meaningful = "not_applicable"
        s.notes.append(f"{tag}: excluded (D-M04-8; {how})")
        return s
    if not ta_pts:
        s.missing = "no total assets tagged"
        return s
    s.stage_label, s.counted = stage_label(engine, norm)
    sic = (engine.execute("SELECT sic FROM entity WHERE cik = ?", (norm,)).fetchone() or [None])[0]
    s.variant = "Z" if is_manufacturer(sic) else "Z''"
    ta = ta_pts[b]
    vals: dict[str, AsOfPoint | None] = {
        "current_assets": _at(_pts(engine, norm, "current_assets", as_of, "I"), b),
        "current_liabilities": _at(_pts(engine, norm, "current_liabilities", as_of, "I"), b),
        "total_liabilities": _at(_pts(engine, norm, "total_liabilities", as_of, "I"), b),
        "retained_earnings": _at(_pts(engine, norm, "retained_earnings", as_of, "I"), b),
        "equity": _at(_pts(engine, norm, "equity", as_of, "I"), b),
        "operating_income": twelve_at(engine, norm, "operating_income", as_of, b),
        "revenue": twelve_at(engine, norm, "revenue", as_of, b),
    }
    TA = float(ta.value)
    s.sources.append(Source(ta.accession, ta.filed, "A", "total assets"))
    for k, p in vals.items():
        if p is not None:
            s.sources.append(Source(p.accession, p.filed, "A", k.replace("_", " ")))
    tl = float(vals["total_liabilities"].value) if vals["total_liabilities"] else None
    eq = float(vals["equity"].value) if vals["equity"] else None
    if tl is None and eq is not None:
        tl = TA - eq
        s.notes.append("total liabilities = assets − equity (derived; Liabilities untagged)")
    need = [
        k
        for k in ("current_assets", "current_liabilities", "retained_earnings", "operating_income")
        if vals[k] is None
    ]
    if tl is None:
        need.append("total_liabilities")
    if need or TA <= 0:
        s.missing = "inputs missing: " + ", ".join(n.replace("_", " ") for n in need)
        return s
    x1 = (float(vals["current_assets"].value) - float(vals["current_liabilities"].value)) / TA
    x2 = float(vals["retained_earnings"].value) / TA
    x3 = float(vals["operating_income"].value) / TA
    if eq is not None and tl:
        s.zpp = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * (eq / tl)
        s.zpp_zone = zone("Z''", s.zpp)
    if s.variant == "Z''":
        if s.zpp is None:
            s.missing = "inputs missing: equity"
            return s
        s.x = {"X1": x1, "X2": x2, "X3": x3, "X4": eq / tl}
        s.value, s.zone = s.zpp, s.zpp_zone
    else:
        if vals["revenue"] is None:
            s.missing = "inputs missing: revenue"
            return s
        mv, note, msrc = market_value(engine, norm, as_of, close_day)
        if mv is None:
            s.missing = note.removeprefix("missing: ") + " (Z needs the market value)"
            return s
        s.close_note = note
        s.sources += msrc
        x4 = mv / tl
        x5 = float(vals["revenue"].value) / TA
        s.x = {"X1": x1, "X2": x2, "X3": x3, "X4": x4, "X5": x5}
        s.value = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
        s.without_x4 = s.value - 0.6 * x4
        s.zone = zone("Z", s.value)
    _ohlson(engine, norm, as_of, s, TA, tl, vals)
    return s


def _ohlson(engine, cik, as_of, s: Score, TA: float, tl: float, vals) -> None:
    b = s.balance_date
    year = date.fromisoformat(b).year - 1
    idx = GNPDEF_1968.get(year)
    if idx is None:
        s.o_note = f"missing: no GNP deflator for {year} (distress.GNPDEF_1968)"
        return
    ni = twelve_at(engine, cik, "net_income", as_of, b)
    prior_end = (date.fromisoformat(b) - timedelta(days=365)).isoformat()
    ni0 = twelve_at(engine, cik, "net_income", as_of, prior_end)
    ocf = twelve_at(engine, cik, "operating_cash_flow", as_of, b)
    if ni is None or ni0 is None or ocf is None or not tl:
        s.o_note = "missing: net income (two years) or OCF"
        return
    ca, cl = float(vals["current_assets"].value), float(vals["current_liabilities"].value)
    n1, n0 = float(ni.value), float(ni0.value)
    size = math.log(TA / idx)
    chin = (n1 - n0) / (abs(n1) + abs(n0)) if (abs(n1) + abs(n0)) else 0.0
    o = (
        -1.32
        - 0.407 * size
        + 6.03 * (tl / TA)
        - 1.43 * ((ca - cl) / TA)
        + 0.0757 * (cl / ca if ca else 0.0)
        - 1.72 * (1.0 if tl > TA else 0.0)
        - 2.37 * (n1 / TA)
        - 1.83 * (float(ocf.value) / tl)
        + 0.285 * (1.0 if n1 < 0 and n0 < 0 else 0.0)
        - 0.521 * chin
    )
    s.o_value = o
    s.o_p = 1.0 / (1.0 + math.exp(-o))
