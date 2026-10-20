"""The "Future spend (M05)" section of the Money flow tab (D-UI-37; M05 Part 1).

Computed on the fly from stored facts and rows with the refresh's own functions
(`step.name_result`), so the section and the stored D13 rows read the same; nothing here
writes. Shown: the three signal rows (with the rule-4 vote), an 8-FY capex ÷ depreciation
strip (each year read on its own prior window), the deposits line ("repayable, not
revenue"), M04's ≥ 10% customers and M04's capex guidance outcomes (the track record), with
M04's `cvd_state`, `runway_q` and `survival_gate` beside the vote.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date

from engine import m01_rules
from engine.financials import models as models_mod
from engine.future_spend import channels as channels_mod
from engine.future_spend import demand, step

SIGNAL_LABELS = {
    "capex_demand": "Capex against demand",
    "growth_capex_roic": "Growth capex × ROIC",
    "bookings_cover": "Bookings cover (RPO ÷ TTM revenue)",
}


@dataclass(frozen=True)
class SignalRow:
    signal: str
    label: str
    state: str  # value_text or "missing"
    value: str
    method: str
    as_of: str
    weight: str  # "MY ✓ · PT ✓ · ST info"


@dataclass
class FutureSpendView:
    ticker: str
    channel: str
    channel_error: str
    not_applicable: str | None
    rows: list[SignalRow]
    vote: str
    beside: list[str]
    strip: list[demand.Demand]
    rung: str
    deposits: str
    customers: list = field(default_factory=list)  # units_view.CustomerYear, newest first
    guidance: list[sqlite3.Row] = field(default_factory=list)
    guide: str = ""
    errors: list[str] = field(default_factory=list)


def _value(o: step.Out) -> str:
    if o.missing is not None or o.value is None:
        return "—"
    if o.signal == "growth_capex_roic":
        return f"ROIC {o.value:.1%}".replace("-", "−")
    if o.signal == "bookings_cover":
        return f"{o.value:.2f} years"
    return f"{o.value:.2f}×"


def _weight(o: step.Out) -> str:
    return " · ".join(f"{tf} {'info' if tf in o.info else '✓'}" for tf in step.ALL)


def capex_guidance(engine: sqlite3.Connection, cik: str, limit: int = 8) -> list[sqlite3.Row]:
    """M04's capex guidance outcomes (`guidance_outcome`, metric capex), newest first."""
    return engine.execute(
        "SELECT * FROM guidance_outcome WHERE cik = ? AND metric = 'capex' "
        "ORDER BY period DESC, kind LIMIT ?",
        (cik, limit),
    ).fetchall()


def company_view(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str,
    today: date,
    *,
    chf: channels_mod.ChannelFile | None = None,
    mf: models_mod.ModelFile | None = None,
) -> FutureSpendView:
    chf = chf if chf is not None else channels_mod.load_safe()
    mf = mf if mf is not None else models_mod.load_safe()
    r = step.name_result(engine, ticker, cik, today, chf=chf, mf=mf)
    rows = [
        SignalRow(o.signal, SIGNAL_LABELS[o.signal], o.text or "missing", _value(o),
                  (f"missing: {o.missing}; " if o.missing else "") + o.method, o.as_of, _weight(o))
        for o in r.rows
    ]  # fmt: skip
    m04 = m01_rules.read_m04(engine, r.cik)
    beside = [m01_rules.m04_line(m04)]
    if m04.runway is not None:
        beside.append(f"runway_q {m04.runway.text or 'missing'} ({m04.runway.as_of})")
    s = r.series
    view = FutureSpendView(
        ticker=ticker,
        channel=r.channel.text(),
        channel_error=chf.error,
        not_applicable=r.not_applicable,
        rows=rows,
        vote=r.vote.text if r.vote else "vote: none (no capex_demand state)",
        beside=beside,
        strip=demand.strip(s) if s is not None and s.years else [],
        rung=demand.RUNG_NAME.get(s.rung, "not split") if s is not None else "not split",
        deposits=r.deposits.text() if r.deposits else demand.deposits_line(s).text() if s else "",
        guide=r.guide,
    )
    try:
        from engine.financials.units_view import major_customers

        view.customers = list(reversed(major_customers(engine, r.cik)))[:3]
    except Exception as e:  # noqa: BLE001 — a display read must not break the tab
        view.errors.append(f"≥ 10% customers not read ({type(e).__name__})")
    view.guidance = capex_guidance(engine, r.cik)
    return view
