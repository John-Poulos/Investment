"""M04 Part 4a inside the refresh and the `gate` script (D-M04-31…39, -61, -70, -71, -86).

`gate_pass` (local, 0 SEC requests; the refresh hooks it after the other M04 local work,
after prices, so filing status, Part 3's events and the latest closes are current):

- per covered company: the gate (`gate.evaluate` as of today), the distress score (the
  latest close, its date in the method), the debt rows, `fcf_burn`, `negative_equity`;
- signals `survival_gate`, `runway_q`, `maturity_wall`, `distress_score`, `fcf_burn`,
  `debt_to_revenue`, `net_debt_ebitda`, `negative_equity` (one row per timeframe; `as_of`
  = the newest input's filing date, or the due date when overdue, so rows do not repeat
  daily; price-dependent values are updated in place with the close date in `method`);
- review items for core and promoted names only (tracked: rows, no items, D-M04-80):
  `m04_gate_fail` when the gate turns fail or incomplete (alert, uncapped, priority 1;
  a first run that finds a fail or incomplete queues it too), `m04_runway` when a
  capex-funded runway turns below 6 quarters (D-M04-38), `m04_score_gap` when the score
  turns distress while the gate passes (S4.8), `m04_gate_input` per missing or untagged
  non-financing input (operational, uncapped). A turn is remembered in `refresh_state`
  (`m04_gate:<cik>`), so a state that holds opens no new item; an unanswered item whose
  condition no longer holds is withdrawn (Part 3 pattern).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from engine.financials import debt, distress, gate, models, queue
from engine.financials.profile import full_scope
from engine.financials.shares import latest_periodic
from engine.sec.client import iso
from engine.signals import Source, write_signal

MODULE = "M04"
STATE_KEY = "m04_gate:{cik}"
SIGNALS = (
    "survival_gate",
    "runway_q",
    "maturity_wall",
    "distress_score",
    "fcf_burn",
    "debt_to_revenue",
    "net_debt_ebitda",
    "negative_equity",
)


@dataclass
class CompanyGate:
    ticker: str
    cik: str
    gate: gate.Gate | None = None
    score: distress.Score | None = None
    debt: debt.DebtRows | None = None
    fcf: debt.FcfBurn | None = None
    neg: debt.NegEquity | None = None
    queued: dict[str, str] = field(default_factory=dict)  # kind → status
    held: list[str] = field(default_factory=list)  # kinds a tracked name would open (D-M04-80)
    withdrawn: int = 0
    error: str = ""


@dataclass
class GatePass:
    companies: dict[str, CompanyGate]
    flushed: int = 0
    alerts: list[str] = field(default_factory=list)


def _fallback_source(engine: sqlite3.Connection, cik: str, g: gate.Gate) -> list[Source]:
    if g.sources:
        return g.sources
    if g.scope == "not_applicable":
        if g.tag in ("fund", "financial") and "model tag" in g.scope_text:
            return [Source("config/company_models.toml", g.as_of, "B", f"model tag {g.tag}")]
        return [Source(f"entity SIC {cik}", g.as_of, "A", "SEC industry code")]
    lp = latest_periodic(engine, cik)
    return [Source(lp["accession"], lp["filed"], "A", lp["form"])] if lp else []


def write_signals(engine: sqlite3.Connection, cg: CompanyGate, today: str) -> int:
    """The eight Part 4a signals. Caller owns the transaction."""
    g, s = cg.gate, cg.score
    n = 0
    common = dict(engine=engine, cik=cg.cik, ticker=cg.ticker, module_id=MODULE)
    as_of = g.signal_as_of or today
    srcs = _fallback_source(engine, cg.cik, g)

    def put(
        signal: str,
        *,
        value=None,
        text=None,
        method: str,
        sources=srcs,
        missing=None,
        info=(),
        at=as_of,
    ) -> int:
        if missing is None and not sources:
            missing = "no inputs stored"
        if missing is not None:
            return write_signal(
                **common,
                signal=signal,
                as_of=at,
                method=method,
                missing=missing,
                sources=sources,
                info=info,
            )
        return write_signal(
            **common,
            signal=signal,
            as_of=at,
            value=value,
            value_text=text,
            method=method,
            sources=sources,
            info=info,
        )

    n += put("survival_gate", text=g.state, method=g.method())
    na = f"not applicable ({g.tag or g.scope})" if g.scope == "not_applicable" else None
    # runway_q
    rmethod = (
        (f"tier {g.tier_text}; " if g.tier else "")
        + (f"burn {gate.money(g.burn)}/q on {g.burn_basis}; " if g.burn else "")
        + (
            "bases: "
            + ", ".join(
                f"{k} {v:.1f} q" if v is not None else f"{k} no burn"
                for k, v in g.runway_by_basis.items()
            )
            + "; "
            if g.runway_by_basis
            else ""
        )
        + f"liquidity {g.liquidity_parts()}"
        + (f"; cash-only {g.runway_cash:.1f} q" if g.runway_cash is not None else "")
        + (f"; {g.runway_test[1]}" if g.runway_test[1] else "")
        + (f"; {g.basis_note}" if g.basis_note else "")
        + ("; OCF-only (capex untagged)" if g.ocf_only else "")
        + (
            "; capex-funded review open (m04_runway): rule-3 adds allowed, rule-7 strength "
            "blocked (D-M04-38)"
            if g.runway_review
            else ""
        )
        + (f"; raised in the last 4 quarters: {g.raised} (S4.13)" if g.raised else "")
    )
    answer = (_state(engine, cg.cik) or {}).get("runway_answer")
    if g.runway_review and answer:
        rmethod += (
            "; owner: capex can be cut, rule-7 strength allowed"
            if answer["answer"] == "allow_strength"
            else "; owner: keep rule-7 strength blocked"
        )
    if na:
        n += put("runway_q", method="runway", missing=na, info=("ST",))
    elif g.scope == "trust_only":
        n += put(
            "runway_q", method=rmethod, missing="not tested: trust only (spac_shell)", info=("ST",)
        )
    elif g.tier == "self_funding":
        n += put("runway_q", text="self-funding", method=rmethod, info=("ST",))
    elif g.runway is not None:
        n += put("runway_q", value=round(g.runway, 2), method=rmethod, info=("ST",))
    else:
        n += put(
            "runway_q",
            method=rmethod,
            missing="; ".join(g.missing) or "no burn basis",
            info=("ST",),
        )
    # maturity_wall
    wmethod = f"(12-month debt + 4 × burn) ÷ liquidity; {g.wall_test[1]}" + (
        f"; 24-month wall: {g.debt24_text}" if g.debt24_text else ""
    )
    if na:
        n += put("maturity_wall", method="wall", missing=na, info=("ST",))
    elif g.wall_ratio is not None:
        n += put("maturity_wall", value=round(g.wall_ratio, 4), method=wmethod, info=("ST",))
    else:
        n += put(
            "maturity_wall", method=wmethod, missing=g.wall_test[1] or "not computed", info=("ST",)
        )
    # distress_score
    if s is None:
        n += put(
            "distress_score", method="distress score", missing=na or "not computed", info=("ST",)
        )
    elif s.not_meaningful == "not_meaningful":
        n += put(
            "distress_score",
            text="not_meaningful",
            method=s.method(),
            sources=s.sources or srcs,
            info=("ST",),
        )
    elif s.not_meaningful:
        n += put(
            "distress_score", method=s.method(), missing=f"not applicable ({g.tag})", info=("ST",)
        )
    elif s.value is None:
        n += put(
            "distress_score", method=s.method(), missing=s.missing, sources=s.sources, info=("ST",)
        )
    else:
        n += put(
            "distress_score",
            value=round(s.value, 3),
            text=s.zone,
            method=s.method() + ("" if s.counted else "; not counted"),
            sources=s.sources,
            info=("ST",),
        )
    # fcf_burn (information)
    info_all = ("MY", "PT", "ST")
    f = cg.fcf
    if na or f is None:
        n += put("fcf_burn", method="fcf burn", missing=na or "not computed", info=info_all)
    elif f.value is None:
        n += put(
            "fcf_burn",
            method=f.context,
            missing=f.missing or "no revenue",
            sources=f.sources,
            info=info_all,
        )
    else:
        n += put(
            "fcf_burn",
            value=round(f.value, 4),
            text=g.tier or None,
            method=(
                f"{f.basis} FCF {gate.money(f.fcf)} ÷ revenue; ÷ cash and investments "
                + (f"{f.to_liquidity:.2f}" if f.to_liquidity is not None else "—")
                + f"; tier {f.tier}"
                + (f"; {f.context}" if f.context else "")
                + "; threshold at Part 8 (D-M04-39)"
            ),
            sources=f.sources,
            info=info_all,
        )
    # debt rows (information)
    d = cg.debt
    lp = d.latest if d else None
    dsrc = lp.sources if lp and lp.sources else srcs
    if na or lp is None:
        n += put("debt_to_revenue", method="debt", missing=na or "no balance sheet", info=info_all)
        n += put("net_debt_ebitda", method="debt", missing=na or "no balance sheet", info=info_all)
    else:
        m = f"{lp.debt_text}; {d.range_text('ratio')}" + (f"; {d.peer_note}" if d.peer_note else "")
        if lp.ratio is None:
            n += put(
                "debt_to_revenue",
                method=m,
                sources=dsrc,
                info=info_all,
                missing="no debt tags" if lp.total_debt is None else "no 12-month revenue",
            )
        else:
            n += put(
                "debt_to_revenue", value=round(lp.ratio, 4), method=m, sources=dsrc, info=info_all
            )
        m2 = (
            "net debt = total debt − cash − short-term investments; EBITDA = operating "
            f"income + D&A (12 months); {d.range_text('nd_ebitda')}"
        )
        if lp.nd_text == "not_meaningful":
            n += put(
                "net_debt_ebitda",
                text="not_meaningful",
                method=m2 + "; EBITDA ≤ 0",
                sources=dsrc,
                info=info_all,
            )
        elif lp.nd_ebitda is None:
            n += put(
                "net_debt_ebitda",
                method=m2,
                sources=dsrc,
                info=info_all,
                missing="debt, cash, operating income or D&A missing",
            )
        else:
            n += put(
                "net_debt_ebitda",
                value=round(lp.nd_ebitda, 3),
                method=m2,
                sources=dsrc,
                info=info_all,
            )
    # negative_equity
    ne = cg.neg
    if na or ne is None:
        n += put("negative_equity", method="equity", missing=na or "not computed", info=("ST",))
    elif ne.state == "missing":
        n += put("negative_equity", method="equity", missing="no equity tagged", info=("ST",))
    else:
        n += put(
            "negative_equity",
            text=ne.state,
            info=("ST",),
            sources=ne.sources or srcs,
            method=(
                f"equity {gate.money(ne.equity)} at {ne.end}"
                + (f"; {', '.join(ne.reasons)}" if ne.reasons else "")
                + "; S4.8"
            ),
        )
    return n


# --- Turns and review items ---------------------------------------------------------------


def _state(engine: sqlite3.Connection, cik: str) -> dict | None:
    row = engine.execute(
        "SELECT detail FROM refresh_state WHERE name = ?", (STATE_KEY.format(cik=cik),)
    ).fetchone()
    try:
        return json.loads(row["detail"]) if row and row["detail"] else None
    except json.JSONDecodeError:
        return None


def _save_state(engine: sqlite3.Connection, cik: str, st: dict, now: datetime) -> None:
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
        "detail = excluded.detail",
        (STATE_KEY.format(cik=cik), "M04 Part 4a", iso(now), json.dumps(st, sort_keys=True)),
    )


def _payload(cg: CompanyGate, **extra) -> dict:
    g = cg.gate
    return {
        "ticker": cg.ticker,
        "state": g.state,
        "scope": g.scope_text,
        "balance_date": g.balance_date,
        "liquidity": g.liquidity_parts() if g.liquidity is not None else "",
        "runway": g.runway_text(),
        "runway_bases": {
            k: (round(v, 2) if v is not None else None) for k, v in g.runway_by_basis.items()
        },
        "tier": g.tier_text,
        "wall": g.wall_test[1],
        "wall24": g.debt24_text,
        "triggers": g.triggers,
        "missing": g.missing,
        "warnings": g.warnings,
        "filing_status": g.filing_status,
        "as_of": g.signal_as_of,
    } | extra


def _turn(st: dict, name: str, active: bool, since: str) -> str | None:
    """Remember when a condition started; returns its start key while it holds."""
    if not active:
        st.pop(name, None)
        return None
    st.setdefault(name, since)
    return st[name]


def propose_items(
    engine: sqlite3.Connection, cg: CompanyGate, now: datetime, *, queue_items: bool = True
) -> None:
    """Turn bookkeeping and the four Part 4a kinds. Caller owns the transaction."""
    g, s = cg.gate, cg.score
    cik, who = cg.cik, cg.ticker or cg.cik
    st = _state(engine, cik) or {}
    since = g.balance_date or g.as_of
    bad = g.state in ("fail", "incomplete")
    prev = st.get("state")
    key_fail = None
    for name in ("gate_fail", "gate_incomplete"):
        got = _turn(st, name, bad and name == f"gate_{g.state}", since)
        key_fail = key_fail or got
    key_runway = _turn(st, "runway", g.runway_review, since)
    if not key_runway or (st.get("runway_answer") or {}).get("since") not in (None, key_runway):
        st.pop("runway_answer", None)
    gap = bool(s and s.warning and g.state in ("pass", "warn"))
    key_gap = _turn(st, "score_gap", gap, since)
    st.update(state=g.state, balance=g.balance_date, at=iso(now))
    _save_state(engine, cik, st, now)
    if not queue_items:  # tracked tier: rows only, no review items (D-M04-80)
        cg.held = [
            k
            for k, on in (
                ("m04_gate_fail", key_fail),
                ("m04_runway", key_runway),
                ("m04_score_gap", key_gap),
            )
            if on
        ] + [f"m04_gate_input:{inp}" for inp, _ in g.gate_inputs]
        return
    filed = g.signal_as_of
    live: dict[str, set[str]] = {
        k: set() for k in ("m04_gate_fail", "m04_runway", "m04_score_gap", "m04_gate_input")
    }
    if key_fail:
        key = f"{cik}:{key_fail}:{g.state}"
        live["m04_gate_fail"].add(key)
        why = "; ".join(g.triggers) if g.state == "fail" else "; ".join(g.missing)
        turned = f"turned {g.state}" + (f" (was {prev})" if prev and prev != g.state else "")
        cg.queued["m04_gate_fail"] = queue.propose(
            engine,
            "m04_gate_fail",
            key,
            f"{who}: survival gate {turned} — {why}",
            _payload(cg),
            now,
            cik=cik,
            filed=filed,
        )
    if key_runway:
        key = f"{cik}:{key_runway}"
        live["m04_runway"].add(key)
        cg.queued["m04_runway"] = queue.propose(
            engine,
            "m04_runway",
            key,
            f"{who}: capex-funded runway {g.runway_text()} below {gate.FAIL_Q:g} quarters "
            "(rule-7 strength blocked while open, D-M04-38)",
            _payload(cg, ocf=[round(b.ocf) for b in g.bases]),
            now,
            cik=cik,
            filed=filed,
        )
    if key_gap:
        key = f"{cik}:{key_gap}:{s.variant}"
        live["m04_score_gap"].add(key)
        cg.queued["m04_score_gap"] = queue.propose(
            engine,
            "m04_score_gap",
            key,
            f"{who}: {s.variant} {s.value:.2f} in the distress zone while the gate reads "
            f"{g.state} (S4.8)",
            _payload(cg, score=s.text(), score_method=s.method()),
            now,
            cik=cik,
            filed=filed,
        )
    for inp, why in g.gate_inputs:
        key = f"{cik}:{inp}"
        live["m04_gate_input"].add(key)
        cg.queued[f"m04_gate_input:{inp}"] = queue.propose(
            engine,
            "m04_gate_input",
            key,
            f"{who}: gate input {inp.replace('_', ' ')} — {why}",
            _payload(cg, input=inp, why=why),
            now,
            cik=cik,
            filed=filed,
        )
    # Part 4b-lite's text alerts share the kind; their own pass withdraws them
    from engine.financials.gate_text_step import text_alert_keys

    live["m04_gate_fail"] |= text_alert_keys(engine, cik)
    for kind, keys in live.items():
        cg.withdrawn += queue.withdraw_stale(
            engine, kind, cik, keys, now, "condition no longer holds (Part 4a recompute)"
        )


# --- The pass ------------------------------------------------------------------------------


def company_gate(
    engine: sqlite3.Connection,
    ticker: str,
    cik: str,
    now: datetime,
    *,
    mf: models.ModelFile | None = None,
    queue_items: bool = True,
    with_peers: bool = True,
) -> CompanyGate:
    """Recompute, store and queue one company (today)."""
    today = now.date().isoformat()
    mf = mf if mf is not None else models.load_safe()
    cg = CompanyGate(ticker, cik)
    cg.gate = gate.evaluate(engine, cik, ticker, today, models=mf, today=today)
    if cg.gate.scope in ("full", "liquidity_only"):
        cg.gate.raised = gate.raised_share(engine, cg.gate)
    if cg.gate.scope != "not_applicable":
        cg.score = distress.score(engine, cik, ticker, today, models=mf, close_day=today)
        cg.debt = debt.debt_rows(engine, cik, today, cg.gate.balance_date, with_peers=with_peers)
        cg.fcf = debt.fcf_burn(engine, cg.gate, today)
        cg.neg = debt.negative_equity(engine, cik, today)
    engine.execute("BEGIN")
    try:
        write_signals(engine, cg, today)
        propose_items(engine, cg, now, queue_items=queue_items)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return cg


def gate_pass(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    mf: models.ModelFile | None = None,
) -> GatePass:
    """Part 4a for every covered company (0 requests); one company's error does not stop
    the others."""
    start = iso(now)
    mf = mf if mf is not None else models.load_safe()
    scope = set(full_scope(engine, companies).values())
    out: dict[str, CompanyGate] = {}
    for ticker, cik in sorted(companies.items()):
        try:
            out[ticker] = company_gate(engine, ticker, cik, now, mf=mf, queue_items=cik in scope)
        except Exception as e:
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            out[ticker] = CompanyGate(ticker, cik, error=f"{type(e).__name__}: {e}")
    engine.execute("BEGIN")
    try:
        flushed = queue.flush_overflow(engine, now)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return GatePass(out, flushed, alert_lines(engine, start))


def alert_lines(engine: sqlite3.Connection, since: str) -> list[str]:
    """`m04_gate_fail` items opened at or after `since` (alerts, uncapped; D-M04-71)."""
    return [
        r["reason"]
        for r in engine.execute(
            "SELECT reason FROM review_queue WHERE kind = 'm04_gate_fail' AND created_at >= ? "
            "ORDER BY created_at, item_id",
            (since,),
        )
    ]


def company_line(cg: CompanyGate) -> str:
    """The one line per company the log prints and the tab's all-companies table mirrors."""
    if cg.error:
        return f"{cg.ticker}: error — {cg.error}"
    g = cg.gate
    rb = (
        " · ".join(
            f"{k} {v:.1f}" if v is not None else f"{k} —" for k, v in g.runway_by_basis.items()
        )
        or "—"
    )
    trig = "; ".join(g.triggers or g.missing or g.warnings) or "—"
    s = cg.score
    dist = s.text() if s else "—"
    if s and s.zpp is not None and s.variant == "Z":
        dist += f" (Z'' {s.zpp:.2f})"
    f = cg.fcf
    fb = f"{f.value:+.1%} of revenue" if f and f.value is not None else "—"
    lp = cg.debt.latest if cg.debt else None
    dr = f"debt/revenue {lp.ratio:.2f}" if lp and lp.ratio is not None else "debt/revenue —"
    nd = (
        f"net debt/EBITDA {lp.nd_ebitda:.2f}"
        if lp and lp.nd_ebitda is not None
        else "net debt/EBITDA " + (lp.nd_text or "—")
        if lp
        else "net debt/EBITDA —"
    )
    neg = cg.neg.state if cg.neg else "—"
    liq = g.liquidity_parts() if g.liquidity is not None else "—"
    return (
        f"{cg.ticker}: {g.state} [{g.scope_name}] trigger: {trig} | runway {g.runway_text()}"
        f" ({g.tier_text}; {rb}) | liquidity {liq}"
        f" as of {g.balance_date or '—'} | wall 12m {gate.money(g.debt12)} ({g.wall_test[0]})"
        f", 24m {g.debt24_text or '—'} | distress {dist} | fcf_burn {fb} | {dr}, {nd} | "
        f"negative equity {neg}"
    )


def local_lines(gp: GatePass) -> list[str]:
    states: dict[str, int] = {}
    for c in gp.companies.values():
        if c.gate:
            states[c.gate.state] = states.get(c.gate.state, 0) + 1
    queued = sum(1 for c in gp.companies.values() for v in c.queued.values() if v == "queued")
    lines = [
        "Part 4a: survival gate "
        + ", ".join(f"{k} {v}" for k, v in sorted(states.items()))
        + f"; {queued} item(s) queued; {gp.flushed} overflow item(s) flushed"
    ]
    lines += [f"  {c.ticker}: error — {c.error}" for c in gp.companies.values() if c.error]
    if gp.alerts:
        lines.append("  M04 survival-gate alerts new this run (m04_gate_fail):")
        lines += [f"    {a}" for a in gp.alerts]
    return lines


def run_local_part(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    """The refresh hook (after prices and the other M04 local work). Never fails."""
    t0 = clock()
    try:
        lines = local_lines(gate_pass(engine, companies, now))
    except Exception as e:
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        lines = [f"  Part 4a: error — {type(e).__name__}: {e}"]
    return [
        f"M04 survival gate — local pass (Part 4a, 0 SEC requests) ({clock() - t0:.1f} s):",
        *lines,
    ]


KINDS = ("m04_gate_fail", "m04_runway", "m04_gate_input", "m04_score_gap")


def open_items(engine: sqlite3.Connection) -> list[str]:
    """Open Part 4a review items: "kind company (item N, opened <date>): reason"."""
    marks = ",".join("?" * len(KINDS))
    out = []
    for r in engine.execute(
        f"SELECT item_id, kind, cik, reason, payload, created_at FROM review_queue WHERE kind "
        f"IN ({marks}) AND resolved_at IS NULL ORDER BY kind, item_id",
        KINDS,
    ):
        try:
            who = json.loads(r["payload"] or "{}").get("ticker") or r["cik"]
        except json.JSONDecodeError:
            who = r["cik"]
        out.append(
            f"{r['kind']} {who} (item {r['item_id']}, opened {r['created_at'][:10]}): {r['reason']}"
        )
    return out


def recent_alerts(engine: sqlite3.Connection, now: datetime, hours: int = 24) -> list[str]:
    return alert_lines(engine, iso(now - timedelta(hours=hours)))
