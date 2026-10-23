"""The Valuation tab and the Overview line (D-UI-36; M08 Part 1, built to the brief).

`company_view` computes today's line live at the newest stored close with the refresh's own
functions (`step.evaluate`: 0 requests, nothing written) and shows the stored row set of the
newest completed week beside it (D-M08-8). `overview_row` reads the newest stored MY rows.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from engine.financials import models as models_mod
from engine.signals import latest_signal
from engine.technicals import bars
from engine.valuation import estimates, step
from engine.valuation.asof import latest_close_day
from engine.valuation.measures import LABELS, MODULE, ROW_KEYS, UNITS, fmt
from engine.valuation.params import Params


@dataclass
class Row:
    key: str
    label: str
    shown: str
    missing: str | None
    detail: str
    pctile: str
    headline: bool
    stored: str
    stored_as_of: str


@dataclass
class ValView:
    ticker: str
    cik: str
    as_of: str | None
    missing: str = ""
    headline_label: str = ""
    headline_value: str = ""
    headline_code: str = ""
    route_why: str = ""
    route_basis: str = ""
    headline_pctile: str = ""
    peer: str = ""
    flag: str = ""
    cyclical: bool | None = None
    nep: str = ""
    cap: str = ""
    ev: str = ""
    twelve: str = ""
    trap: str = ""
    notes: list[str] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    history: list[tuple[str, str]] = field(default_factory=list)  # headline at quarter-ends
    version: str = ""
    est: EstBlock | None = None  # Part 2 (D-UI-38)


@dataclass
class EstLine:
    name: str  # FY1, FY2, or "" for other horizons
    horizon: str
    period_end: str
    avg: str
    high: str
    low: str
    count: str
    rev30: str
    rev90: str
    breadth: str
    dispersion: str
    nulls: str


@dataclass
class EstSignal:
    key: str
    shown: str
    missing: str
    method: str
    stored: str
    stored_as_of: str


@dataclass
class EstBlock:
    """The Estimates block (D-UI-38): the snapshot, FY1/FY2 and every horizon row, the three
    Part 2 rows computed live, the next-report estimate and the walk-down window."""

    snapshot: str = ""
    missing: str = ""
    mapping: str = ""
    coverage: str = ""
    lines: list[EstLine] = field(default_factory=list)
    signals: list[EstSignal] = field(default_factory=list)
    next_report: str = ""
    walk: str = ""
    walk_on: bool = False
    snapshots: int = 0


def _stored(engine: sqlite3.Connection, cik: str, key: str) -> tuple[str, str]:
    r = latest_signal(engine, cik, MODULE, key, "MY")
    if r is None:
        return "not stored yet", ""
    if r["value"] is not None:
        return fmt(key, float(r["value"])) if key in UNITS else f"{float(r['value']):.1f}", r[
            "as_of"
        ]
    if r["value_text"] is not None:
        return r["value_text"], r["as_of"]
    return "missing: " + (r["method"] or "")[len("missing: ") :].split(";")[0], r["as_of"]


def company_view(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str,
    now: datetime,
    p: Params | None = None,
    mf: models_mod.ModelFile | None = None,
) -> ValView:
    p = p or Params()
    mf = mf if mf is not None else models_mod.load_safe()
    today = bars.eastern_today(now).isoformat()
    v = ValView(ticker, cik, None, version=p.version)
    day = latest_close_day(engine, cik, today)
    if day is None:
        v.missing = "no stored close"
        return v
    r = step.evaluate(engine, ticker, cik, day, today, p, mf, est_upto=today)
    s, hl, rt = r.snap, r.headline, r.route
    v.as_of = r.as_of
    v.missing = s.missing
    v.route_why, v.route_basis = rt.why, rt.basis
    if hl.measure:
        v.headline_label = LABELS[hl.measure]
        v.headline_value = fmt(hl.measure, hl.value) if hl.value is not None else (hl.text or "")
        if hl.measure == "val_ps" and rt.measure != "val_ps":
            v.headline_label = f"{LABELS[rt.measure]} → P/S (EV incomplete: {s.ev_missing})"
    else:
        v.headline_code = hl.text or f"missing: {hl.missing}"
        if hl.missing:
            v.headline_code = f"missing: {hl.missing}"
    hp = r.headline_pctile
    v.headline_pctile = hp.text() if hp is not None else ""
    v.peer = r.peer.text() if r.peer is not None else ""
    if r.flag is not None:
        v.flag, v.cyclical = r.flag.text(), r.flag.cyclical
    if s.nep is not None:
        v.nep = s.nep.text()
    v.cap = getattr(s.cap, "text", "") if s.cap is not None else ""
    v.ev = s.ev_text or (f"EV incomplete: {s.ev_missing}" if s.ev_missing else "")
    v.twelve, v.trap, v.notes = s.twelve, r.trap, list(r.notes)
    for key in ROW_KEYS:
        m = s.m(key)
        pc = r.pctiles.get(key)
        stored, stored_as_of = _stored(engine, cik, key)
        v.rows.append(
            Row(
                key,
                LABELS[key],
                m.shown,
                m.missing,
                m.detail,
                pc.text() if pc else "",
                hl.measure == key,
                stored,
                stored_as_of,
            )
        )
    if r.history is not None and hl.measure:
        v.history = [(d, fmt(hl.measure, x)) for d, x in r.history.series(hl.measure)[-8:]][::-1]
    v.est = est_block(engine, cik, r, p)
    return v


def _n(x: float | None, digits: int = 4) -> str:
    return "null" if x is None else f"{x:,.{digits}f}"


def est_block(engine: sqlite3.Connection, cik: str, r: step.NameResult, p: Params) -> EstBlock:
    b = EstBlock()
    e = r.est
    b.snapshots = len(estimates.snapshot_dates(engine, cik))
    if r.blocked:
        b.missing = r.blocked
    elif e is None or e.snap is None:
        b.missing = e.missing if e is not None else "no estimate reading"
    else:
        b.snapshot = f"{e.snap.snapshot_date} ({e.snap.source.ref})"
        b.mapping = "; ".join(e.notes)
        b.coverage = e.coverage()
        named = {id(h.row): h for h in (e.fy1, e.fy2) if h is not None}
        for row in sorted(e.snap.rows, key=lambda x: (not x.is_year, x.period_end)):
            h = named.get(id(row)) or estimates.horizon("", row, p)
            v = row.v
            b.lines.append(
                EstLine(
                    h.name,
                    row.horizon,
                    row.period_end,
                    _n(v["eps_avg"]),
                    _n(v["eps_high"]),
                    _n(v["eps_low"]),
                    "null" if v["eps_count"] is None else f"{v['eps_count']:g}",
                    h.rev30.shown(),
                    h.rev90.shown(),
                    h.breadth30.shown("ratio"),
                    h.dispersion.shown(digits=1).lstrip("+"),
                    ", ".join(k.replace("eps_estimate_", "") for k in row.nulls()) or "none",
                )
            )
    for o in r.rows:
        if o.signal not in ("val_pe_fwd", "peg", "est_revision"):
            continue
        if o.missing:
            shown = "—"
        elif o.value is not None:
            unit = "×" if o.signal == "val_pe_fwd" else ("%" if o.signal == "est_revision" else "")
            shown = (f"{o.value:.1f}×" if unit == "×" else f"{o.value:.2f}{unit}") + (
                f" {o.text}" if o.text else ""
            )
        else:
            shown = o.text or "—"
        stored, stored_as_of = _stored(engine, cik, o.signal)
        b.signals.append(EstSignal(o.signal, shown, o.missing or "", o.method, stored,
                                   stored_as_of))  # fmt: skip
    if r.next_report is not None:
        b.next_report = r.next_report.text()
        b.walk_on = bool(r.walk[0])
        b.walk = r.walk[1]
    return b


def overview_row(engine: sqlite3.Connection, cik: str) -> dict | None:
    """The newest stored M08 headline and percentile (MY) for the Overview; None before a run."""
    got = {}
    for key in ("valuation_multiple", "valuation_pctile"):
        r = latest_signal(engine, cik, MODULE, key, "MY")
        if r is None:
            continue
        missing = None
        if r["value"] is None and r["value_text"] is None:
            missing = (r["method"] or "")[len("missing: ") :].split(";")[0]
        got[key] = {
            "as_of": r["as_of"],
            "value": r["value"],
            "text": r["value_text"],
            "missing": missing,
            "what": (r["method"] or "").split(";")[0],
        }
    if not got:
        return None
    return {"as_of": max(x["as_of"] for x in got.values()), **got}
