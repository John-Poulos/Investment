"""The "Moat (M06)" section of the Financials tab and the M06 setup page (D-UI-40; Part 1).

Computed on the fly with the refresh's own functions (`step.name_result`), so the page and
the stored D13 rows read the same; nothing here writes (the verdict form posts to its own
route, which stores the entry and rewrites the three rows). Shown for every company (D32):
the 10-year ROIC, gross margin and operating margin, N_A names included with their label.
The verdict card shows the evidence for and against beside the engine's proposal, so the
proposal is not the only thing in view (case 20, anchoring): the quant years above and below
the hurdle, the ±2 pp classes, the labels, and the switching-cost evidence that is shown, not
scored — RPO, contract liabilities, confirmed supply links and ≥ 10% customers.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from engine.financials import models as models_mod
from engine.moat import params as params_mod
from engine.moat import quant as quant_mod
from engine.moat import step
from engine.moat import verdict as verdict_mod

SIGNAL_LABELS = {
    "moat_quant": "Quant leg (10-year ROIC record)",
    "moat_verdict": "Owner verdict",
    "moat_gate": "MY gate (R1 + A3)",
}


@dataclass(frozen=True)
class SignalRow:
    signal: str
    label: str
    state: str  # value_text or "missing"
    value: str
    method: str
    as_of: str
    weight: str
    grade: str


@dataclass
class Card:
    """One company's verdict card (Financials tab and setup page)."""

    ticker: str
    cik: str
    quant: quant_mod.Quant
    proposal: verdict_mod.Proposal
    verdict: sqlite3.Row | None
    gate_state: str
    gate_why: str
    gate_override: bool
    stale: str
    rows: list[SignalRow]
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    switching: list[str] = field(default_factory=list)
    links: list[sqlite3.Row] = field(default_factory=list)
    history: list[sqlite3.Row] = field(default_factory=list)
    item_id: int | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def not_applicable(self) -> bool:
        return self.quant.state == "not_applicable"


@dataclass
class MoatView:
    card: Card
    params_note: str
    sources: dict[str, str]
    bands: dict[str, tuple]
    horizon: int


def _money(v: float | None) -> str:
    if v is None:
        return "—"
    a = abs(v)
    s = f"${a / 1e9:,.2f}B" if a >= 1e9 else f"${a / 1e6:,.0f}M"
    return ("−" if v < 0 else "") + s


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.1f}%".replace("-", "−")


def _weight(o: step.Out) -> str:
    return " · ".join(f"{tf} {'info' if tf in o.info else '✓'}" for tf in ("MY", "PT", "ST"))


def _value(o: step.Out) -> str:
    if o.value is None:
        return "—"
    return f"{o.value:.0%} of years above the hurdle" if o.signal == "moat_quant" else str(o.value)


def _grade(o: step.Out) -> str:
    gs = [s.grade for s in o.sources if s.grade]
    return max(gs, key=("A", "B", "C").index) if gs else "—"


def switching_evidence(engine: sqlite3.Connection, cik: str, today: date) -> tuple[list[str], list]:
    """RPO, contract liabilities, ≥ 10% customers (lines) and confirmed supply links (rows):
    shown, never scored (rule 2; switching costs, outline Moat 4)."""
    lines: list[str] = []
    try:
        from engine.moneyflow import views as mf_views

        rp = mf_views.rpo(engine, cik)
        if rp.reported and rp.rows:
            r = rp.rows[-1]
            cover = f", {r.cover:.2f} years of TTM revenue" if r.cover is not None else ""
            lines.append(f"RPO {_money(r.value)} at {r.end}{cover} ({r.accession})")
        else:
            lines.append("RPO: not tagged (unknown, not none)")
    except Exception as e:  # noqa: BLE001 — a display read must not break the tab
        lines.append(f"RPO not read ({type(e).__name__})")
    try:
        from engine.sec.asof import facts_as_of

        day = today.isoformat()
        tot = facts_as_of(engine, cik, "contract_liabilities_total", day, ptype="I").points
        cur = facts_as_of(engine, cik, "contract_liabilities", day, ptype="I").points
        if tot:
            p = tot[-1]
            lines.append(f"Contract liabilities {_money(p.value)} at {p.end} (total; repayable, "
                         f"not revenue; {p.accession})")  # fmt: skip
        elif cur:
            p = cur[-1]
            lines.append(f"Contract liabilities {_money(p.value)} at {p.end} (current only, "
                         f"labelled; {p.accession})")  # fmt: skip
        else:
            lines.append("Contract liabilities: not tagged (unknown, not none)")
    except Exception as e:  # noqa: BLE001
        lines.append(f"Contract liabilities not read ({type(e).__name__})")
    try:
        from engine.financials.units_view import major_customers

        years = major_customers(engine, cik)
        if years:
            y = years[-1]
            names = ", ".join(f"{n} {v:.0%}" for n, v in y.customers)
            lines.append(f"≥ 10% customers {y.label}: {names} (M04 store)")
        else:
            lines.append("≥ 10% customers: none tagged (unknown, not none)")
    except Exception as e:  # noqa: BLE001
        lines.append(f"≥ 10% customers not read ({type(e).__name__})")
    links = engine.execute(
        "SELECT rung, grade, a_name, b_name, a_cik, b_cik, direction, quote, accession, filed "
        "FROM supply_link WHERE status = 'confirmed' AND (a_cik = ? OR b_cik = ?) "
        "ORDER BY filed DESC LIMIT 6",
        (cik, cik),
    ).fetchall()
    return lines, links


def card(
    engine: sqlite3.Connection,
    ticker: str,
    cik: str,
    now: datetime,
    *,
    p: params_mod.Params,
    mf: models_mod.ModelFile,
    peers: bool = True,
) -> Card:
    r = step.name_result(engine, ticker, cik, now, p=p, mf=mf, peers=peers)
    q = r.quant
    rows = [
        SignalRow(o.signal, SIGNAL_LABELS[o.signal], o.text or "missing", _value(o),
                  (f"missing: {o.missing}; " if o.missing else "") + o.method, o.as_of,
                  _weight(o), _grade(o))
        for o in r.rows
    ]  # fmt: skip
    item = verdict_mod.open_item(engine, r.cik)
    c = Card(ticker, r.cik, q, r.proposal, r.verdict, r.gate.state or "missing", r.gate.why,
             r.gate.override, r.gate.stale, rows, item_id=item["item_id"] if item else None,
             history=verdict_mod.history(engine, r.cik))  # fmt: skip
    rd = q.reading
    if rd is not None and rd.n:
        above = [y.label for y in q.window if y.roic > p.hurdle]
        below = [y.label for y in q.window if y.roic <= p.hurdle]
        c.evidence_for.append(f"ROIC above {p.hurdle:.0%}† in {rd.above} of {rd.n} years"
                              + (f" ({', '.join(above)})" if above else ""))  # fmt: skip
        if below:
            c.evidence_against.append(f"at or below the hurdle in {len(below)} years "
                                      f"({', '.join(below)})")  # fmt: skip
        if rd.median is not None:
            (c.evidence_for if rd.median > p.hurdle else c.evidence_against).append(
                f"window median {_pct(rd.median)}"
            )
        flips = [f"at {h:.0%} {s.state}" for h, s in q.sensitivity if s.state != q.state]
        if flips:
            c.evidence_against.append("the class flips within ±2 pp: " + ", ".join(flips))
    if q.gm_median is not None:
        disp = (f", dispersion {q.gm_dispersion:.1f} pp" if q.gm_dispersion is not None
                else "")  # fmt: skip
        c.evidence_for.append(f"GM median {q.gm_median:.1f}% over {q.gm_n} years{disp} "
                              "(stability is evidence, not proof)")  # fmt: skip
    c.evidence_for.append(q.peer_gm)
    c.evidence_against += q.labels
    try:
        c.switching, c.links = switching_evidence(engine, r.cik, now.date())
    except Exception as e:  # noqa: BLE001 — a display read must not break the tab
        c.errors.append(f"switching evidence not read ({type(e).__name__}: {e})")
    return c


def company_view(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str,
    now: datetime,
    *,
    p: params_mod.Params | None = None,
    params_note: str = "",
    mf: models_mod.ModelFile | None = None,
) -> MoatView:
    if p is None:
        p, params_note = params_mod.load_safe()
    mf = mf if mf is not None else models_mod.load_safe()
    return MoatView(card(engine, ticker, cik, now, p=p, mf=mf), params_note,
                    verdict_mod.SOURCES, verdict_mod.BANDS, p.my_horizon_years)  # fmt: skip


@dataclass
class SetupView:
    rated: list[Card]  # companies that take a verdict (open items first)
    not_applicable: list[Card]
    errors: dict[str, str]
    params_note: str
    sources: dict[str, str]
    bands: dict[str, tuple]
    horizon: int
    open_items: int


def setup_view(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime | None = None,
    *,
    p: params_mod.Params | None = None,
    params_note: str = "",
    mf: models_mod.ModelFile | None = None,
) -> SetupView:
    now = now or datetime.now(UTC)
    if p is None:
        p, params_note = params_mod.load_safe()
    mf = mf if mf is not None else models_mod.load_safe()
    rated, na, errors = [], [], {}
    for t, cik in sorted(companies.items()):
        if not cik:
            continue
        try:
            c = card(engine, t, cik, now, p=p, mf=mf, peers=False)
        except Exception as e:  # noqa: BLE001 — one company must not break the page
            errors[t] = f"{type(e).__name__}: {e}"
            continue
        (na if c.not_applicable else rated).append(c)
    rated.sort(key=lambda c: (c.item_id is None, c.verdict is not None, c.ticker))
    return SetupView(rated, na, errors, params_note, verdict_mod.SOURCES, verdict_mod.BANDS,
                     p.my_horizon_years, sum(c.item_id is not None for c in rated))  # fmt: skip
