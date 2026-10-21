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
from engine.valuation import step
from engine.valuation.asof import latest_close_day
from engine.valuation.measures import LABELS, MODULE, STANDARD_KEYS, UNITS, fmt
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
    r = step.evaluate(engine, ticker, cik, day, today, p, mf)
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
    for key in STANDARD_KEYS:
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
    return v


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
