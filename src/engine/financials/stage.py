"""Life-cycle stage (D-M04-7, D-M04-12, D-M04-46; M04 Part 1c).

- **Computed:** Dickinson signs of (operating, investing, financing) cash flow per fiscal
  year, with **core** investing = −(capex + acquisitions − business and asset sale
  proceeds), so maturing securities (Apple) and partner financing do not decide the
  investing sign. Capex is the own-history total capex (D-M04-3). Acquisitions and sale
  proceeds without a fact are taken as none and named in the method.
  introduction (−, −, +) · growth (+, −, +) · mature (+, −, −) · shake-out (−, −, −),
  (+, +, +), (+, +, −) · decline (−, +, +), (−, +, −). A value > 0 is "+", else "−".
- A stage **holds** when 2 of the last 3 fiscal years agree.
- **Review (`m04_stage`)** when no stage holds, the held stage is shake-out, the stage
  conflicts with the 3-year revenue CAGR (introduction/growth with CAGR < 0; mature/decline
  with CAGR > 20%†, the OECD-Eurostat high-growth line), or fewer than 3 fiscal years
  exist. The owner confirms every company's first stage once (setup batch), then computed
  changes and ambiguous cases per new 10-K (D-M04-12); owner override at any time.
- **Routing:** the owner's last confirmed stage routes until the owner changes it. With
  none, the young and the mature flag sets are both computed, labelled "stage
  unconfirmed" and not counted in D13 (D-M04-7). Stage routes flags only; R12,
  inventory-vs-sales and the survival gate run at every stage. Stage → flag set per
  D-M04-46 (`flag_set`). A model tag routes first (D-M04-8).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from engine.financials.capex import at, fiscal_label, fy_points, near, total_capex
from engine.sec.identity import normalize_cik
from engine.signals import Source, write_signal

STAGES = ("introduction", "growth", "mature", "shake_out", "decline")
STAGE_NAMES = {"introduction": "introduction", "growth": "growth", "mature": "mature",
               "shake_out": "shake-out", "decline": "decline"}  # fmt: skip
DICKINSON = {
    ("−", "−", "+"): "introduction",
    ("+", "−", "+"): "growth",
    ("+", "−", "−"): "mature",
    ("−", "−", "−"): "shake_out",
    ("+", "+", "+"): "shake_out",
    ("+", "+", "−"): "shake_out",
    ("−", "+", "+"): "decline",
    ("−", "+", "−"): "decline",
}
CAGR_HIGH = 0.20  # starting value (D-M04-7, OECD-Eurostat high-growth line)
CAGR_LOW = 0.0
WINDOW = 3
MODULE = "M04"

REASONS = {
    "first": "first confirmation",
    "short_history": "short history (fewer than 3 fiscal years)",
    "no_stage": "no stage holds 2 of 3",
    "shake_out": "held stage is shake-out",
    "growth_falling": "growth with falling revenue (CAGR < 0%)",
    "mature_fast": "mature with CAGR > 20%",
    "tag_first": "model tag routes first",
    "changed": "computed stage differs from the confirmed stage",
}
AMBIGUOUS = frozenset({"short_history", "no_stage", "shake_out", "growth_falling", "mature_fast"})


def sign(v: float) -> str:
    return "+" if v > 0 else "−"


def dickinson(cfo: float, cfi: float, cff: float) -> str:
    return DICKINSON[(sign(cfo), sign(cfi), sign(cff))]


@dataclass
class Year:
    end: str
    label: str
    cfo: float | None = None
    core: float | None = None  # core investing cash flow (negative = investing)
    total: float | None = None  # reported investing cash flow
    cff: float | None = None
    stage: str | None = None  # on core investing
    stage_total: str | None = None
    missing: str = ""
    absent: list[str] = field(default_factory=list)  # optional terms taken as none
    sources: list[tuple[str, str]] = field(default_factory=list)  # (accession, filed)

    @property
    def signs(self) -> str:
        if self.stage is None:
            return "—"
        return " ".join(sign(v) for v in (self.cfo, self.core, self.cff))  # type: ignore[arg-type]

    @property
    def signs_total(self) -> str:
        if self.cfo is None or self.total is None or self.cff is None:
            return "—"
        return " ".join(sign(v) for v in (self.cfo, self.total, self.cff))

    def as_dict(self) -> dict:
        return {"end": self.end, "label": self.label, "cfo": self.cfo, "core": self.core,
                "total": self.total, "cff": self.cff, "stage": self.stage,
                "stage_total": self.stage_total, "signs": self.signs,
                "signs_total": self.signs_total, "missing": self.missing,
                "absent": self.absent, "sources": self.sources}  # fmt: skip


@dataclass
class StageResult:
    cik: str
    period_end: str | None
    label: str
    years: list[Year]
    computed: str | None
    cagr3: float | None
    cagr_note: str
    reasons: list[str]  # codes, see REASONS (ambiguity only; "first"/"changed" are added later)
    total_note: str
    method: str

    @property
    def held_count(self) -> int:
        return sum(1 for y in self.years if y.stage == self.computed) if self.computed else 0


def _held(stages: list[str | None]) -> str | None:
    known = [s for s in stages if s is not None]
    if len(known) < WINDOW:
        return None
    for s in STAGES:
        if known.count(s) >= 2:
            return s
    return None


def _cagr3(engine: sqlite3.Connection, cik: str, end: str, as_of: str) -> tuple[float | None, str]:
    rev = fy_points(engine, cik, "revenue", as_of)
    ends: list[str] = []
    for e in sorted(rev):
        if not any(near(e, x) for x in ends):
            ends.append(e)
    now = at(rev, end)
    if now is None:
        return None, "missing: no revenue for the latest fiscal year"
    i = next((k for k, e in enumerate(ends) if near(e, end)), None)
    if i is None or i < 3:
        return None, "missing: fewer than 4 fiscal years of revenue"
    base = rev[ends[i - 3]]
    if base.value <= 0:
        return None, "not meaningful: base ≤ 0"
    g = (float(now.value) / float(base.value)) ** (1 / 3) - 1
    return g, f"{fiscal_label(ends[i - 3])}→{fiscal_label(end)} revenue {now.value / 1e6:,.0f}M"


def compute(engine: sqlite3.Connection, cik: str, as_of: str) -> StageResult:
    """The computed stage on the last 3 fiscal years (latest known values as of `as_of`)."""
    norm = normalize_cik(cik) or cik
    cfo = fy_points(engine, norm, "operating_cash_flow", as_of)
    cfi = fy_points(engine, norm, "investing_cf", as_of)
    cff = fy_points(engine, norm, "financing_cf", as_of)
    acq = fy_points(engine, norm, "acquisitions", as_of)
    div = fy_points(engine, norm, "divestiture_proceeds", as_of)
    sale = fy_points(engine, norm, "asset_sale_proceeds", as_of)
    capex = {t.end: t for t in total_capex(engine, norm, as_of)}
    ends: list[str] = []
    for e in sorted(cfo):
        if not any(near(e, x) for x in ends):
            ends.append(e)
    window = ends[-WINDOW:]
    years: list[Year] = []
    for end in window:
        y = Year(end, fiscal_label(end))
        o, f, t = at(cfo, end), at(cff, end), at(cfi, end)
        cx = next((c for e, c in capex.items() if near(e, end)), None)
        y.cfo = float(o.value) if o else None
        y.cff = float(f.value) if f else None
        y.total = float(t.value) if t else None
        for p in (o, f, t):
            if p is not None:
                y.sources.append((p.accession, p.filed))
        if cx is not None:
            y.sources.append((cx.accession, cx.filed))
            out = cx.value
            for name, pts, sgn in (("acquisitions", acq, 1), ("business sale proceeds", div, -1),
                                   ("asset sale proceeds", sale, -1)):  # fmt: skip
                p = at(pts, end)
                if p is None:
                    y.absent.append(name)
                else:
                    out += sgn * float(p.value)
                    y.sources.append((p.accession, p.filed))
            y.core = -out
        missing = [n for n, v in (("operating cash flow", y.cfo), ("financing cash flow", y.cff),
                                  ("capex", y.core)) if v is None]  # fmt: skip
        if missing:
            y.missing = "missing: " + ", ".join(missing)
        else:
            y.stage = dickinson(y.cfo, y.core, y.cff)  # type: ignore[arg-type]
        if y.cfo is not None and y.total is not None and y.cff is not None:
            y.stage_total = dickinson(y.cfo, y.total, y.cff)
        years.append(y)

    period_end = window[-1] if window else None
    label = fiscal_label(period_end) if period_end else "no fiscal year"
    classified = [y for y in years if y.stage is not None]
    computed = _held([y.stage for y in years]) if len(classified) == WINDOW else None
    reasons: list[str] = []
    if len(classified) < WINDOW:
        reasons.append("short_history")
    elif computed is None:
        reasons.append("no_stage")
    elif computed == "shake_out":
        reasons.append("shake_out")
    cagr, cagr_note = (None, "missing: no fiscal year")
    if period_end:
        cagr, cagr_note = _cagr3(engine, norm, period_end, as_of)
    if computed in ("introduction", "growth") and cagr is not None and cagr < CAGR_LOW:
        reasons.append("growth_falling")
    if computed in ("mature", "decline") and cagr is not None and cagr > CAGR_HIGH:
        reasons.append("mature_fast")

    held_total = _held([y.stage_total for y in years])
    total_note = ""
    if any(y.stage_total and y.stage_total != y.stage for y in years if y.stage):
        per = ", ".join(f"{y.label} {STAGE_NAMES[y.stage_total]}" for y in years if y.stage_total)
        total_note = (f"on total investing: {per}"
                      + (f" (holds {STAGE_NAMES[held_total]})" if held_total else "")
                      + " — securities flows or partner financing move the total")  # fmt: skip
    absent = sorted({a for y in years for a in y.absent})
    method = ("Dickinson signs (CFO, core investing, CFF), 2 of the last 3 fiscal years; core "
              "investing = capex (own-history total) + acquisitions − business and asset sale "
              "proceeds")  # fmt: skip
    if absent:
        method += f"; no fact: {', '.join(absent)} (taken as none in some years)"
    method += f"; revenue CAGR 3y: {cagr_note}"
    return StageResult(norm, period_end, label, years, computed, cagr, cagr_note, reasons,
                       total_note, method)  # fmt: skip


# --- Store, route, signal ------------------------------------------------------------------


def store(engine: sqlite3.Connection, r: StageResult, now: str) -> None:
    """Upsert the computed row; the owner's confirmation fields are kept."""
    if r.period_end is None:
        return
    engine.execute(
        "INSERT INTO company_stage (cik, period_end, fiscal_label, computed, years, rev_cagr3, "
        "reasons, method, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (cik, period_end) DO UPDATE SET fiscal_label = excluded.fiscal_label, "
        "computed = excluded.computed, years = excluded.years, rev_cagr3 = excluded.rev_cagr3, "
        "reasons = excluded.reasons, method = excluded.method, computed_at = excluded.computed_at",
        (r.cik, r.period_end, r.label, r.computed, json.dumps([y.as_dict() for y in r.years]),
         r.cagr3, json.dumps(r.reasons), r.method + (f"; {r.total_note}" if r.total_note else ""),
         now),
    )  # fmt: skip


def confirmed(engine: sqlite3.Connection, cik: str) -> sqlite3.Row | None:
    """The owner's latest confirmation (it routes until changed)."""
    return engine.execute(
        "SELECT * FROM company_stage WHERE cik = ? AND confirmed IS NOT NULL "
        "ORDER BY confirmed_at DESC, period_end DESC LIMIT 1",
        (normalize_cik(cik) or cik,),
    ).fetchone()


def latest_row(engine: sqlite3.Connection, cik: str) -> sqlite3.Row | None:
    return engine.execute(
        "SELECT * FROM company_stage WHERE cik = ? ORDER BY period_end DESC LIMIT 1",
        (normalize_cik(cik) or cik,),
    ).fetchone()


def confirm(
    engine: sqlite3.Connection, cik: str, period_end: str | None, stage: str, by: str,
    now: datetime, item_id: int | None = None,
) -> None:  # fmt: skip
    """Store the owner's stage on the row it answered (caller owns the transaction)."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r} (one of {', '.join(STAGES)})")
    norm = normalize_cik(cik) or cik
    at_ = now.isoformat(timespec="seconds")
    label = fiscal_label(period_end) if period_end else "no fiscal year"
    if period_end is None:  # no fiscal year stored (short history): keyed on today
        period_end = at_[:10]
    engine.execute(
        "INSERT INTO company_stage (cik, period_end, fiscal_label, computed, years, reasons, "
        "method, confirmed, confirmed_by, confirmed_at, item_id, computed_at) "
        "VALUES (?, ?, ?, NULL, '[]', '[\"short_history\"]', 'owner entry without computed "
        "row', ?, ?, ?, ?, ?) ON CONFLICT (cik, period_end) DO UPDATE SET "
        "confirmed = excluded.confirmed, confirmed_by = excluded.confirmed_by, "
        "confirmed_at = excluded.confirmed_at, item_id = coalesce(excluded.item_id, item_id)",
        (norm, period_end, label, stage, by, at_, item_id, at_),
    )


@dataclass(frozen=True)
class FlagSet:
    stage: str | None  # routing stage (owner-confirmed) or None
    label: str
    sets: tuple[str, ...]  # young | mature | all-stage
    sga_rule: bool
    reversion_prior: str  # used | unused | n/a
    counted: bool  # counted in D13 confluence


def flag_set(stage: str | None, tag: str | None = None) -> FlagSet:
    """Stage → flag set (D-M04-46); tag first (D-M04-8); unconfirmed → both, uncounted."""
    if tag in ("fund", "financial", "spac_shell"):
        return FlagSet(stage, f"not applicable ({tag})", (), False, "n/a", False)
    if stage is None:
        return FlagSet(None, "stage unconfirmed: young and mature sets both computed, "
                       "labelled, not counted (D-M04-7)", ("young", "mature"), True, "used",
                       False)  # fmt: skip
    table = {
        "introduction": (("young",), False, "used", "young set"),
        "growth": (("young",), True, "used", "young set + SG&A rule"),
        "mature": (("mature",), False, "used", "mature set"),
        "decline": (("mature",), False, "unused", "mature set, reversion prior unused"),
        "shake_out": (("all-stage",), False, "n/a", "all-stage flags only"),
    }
    sets, sga, rev, label = table[stage]
    return FlagSet(stage, label, sets, sga, rev, True)


def stage_signal(
    engine: sqlite3.Connection, cik: str, ticker: str | None, today: str,
    tag: str | None = None, tag_how: str = "",
) -> int:  # fmt: skip
    """`lifecycle_stage` (routing only, information in every timeframe): the owner's stage,
    or "unconfirmed"; missing when no fiscal year is stored or a tag excludes the company."""
    norm = normalize_cik(cik) or cik
    row = latest_row(engine, norm)
    conf = confirmed(engine, norm)
    common = dict(engine=engine, cik=norm, ticker=ticker, module_id=MODULE,
                  signal="lifecycle_stage", info=("MY", "PT", "ST"))  # fmt: skip
    if tag in ("fund", "financial"):
        return write_signal(**common, as_of=(row["period_end"] if row else today),
                            method=tag_how, missing=f"not applicable ({tag})")  # fmt: skip
    years = json.loads(row["years"]) if row else []
    srcs = [Source(a, f, "A", "cash-flow totals") for y in years for a, f in y["sources"] if a]
    seen: dict[str, Source] = {}
    for s in srcs:
        seen.setdefault(s.ref, s)
    srcs = list(seen.values())
    as_of = max((s.date for s in srcs), default=row["period_end"] if row else today)
    computed = row["computed"] if row else None
    reasons = json.loads(row["reasons"]) if row else ["short_history"]
    method = (f"computed {STAGE_NAMES.get(computed, 'none') if computed else 'none'} "
              f"({row['fiscal_label'] if row else 'no fiscal year'}"
              + (f"; review: {', '.join(REASONS[c] for c in reasons)}" if reasons else "")
              + ")")  # fmt: skip
    if tag_how:
        method += f"; {tag_how}"
    fs = flag_set(conf["confirmed"] if conf else None, tag)
    if conf is not None:
        method = (f"owner-confirmed {STAGE_NAMES[conf['confirmed']]} on "
                  f"{(conf['confirmed_at'] or '')[:10]} by {conf['confirmed_by']}; {method}; "
                  f"flag set: {fs.label} (D-M04-46)")  # fmt: skip
        if not srcs:
            srcs = [Source(f"owner {conf['confirmed_at'][:10]}", conf["confirmed_at"][:10], "B",
                           "owner entry without a filing")]  # fmt: skip
            as_of = conf["confirmed_at"][:10]
        return write_signal(**common, as_of=as_of, value_text=conf["confirmed"], method=method,
                            sources=srcs)  # fmt: skip
    if not srcs:
        return write_signal(**common, as_of=as_of, method=method,
                            missing="no fiscal-year cash-flow totals stored")  # fmt: skip
    return write_signal(**common, as_of=as_of, value_text="unconfirmed",
                        method=f"{method}; flag set: {fs.label}", sources=srcs)  # fmt: skip
