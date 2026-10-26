"""M06 Part 1 inside the refresh and the `quant` script (D-M06-1…8; D-M06-9…).

`moat_pass` (local, 0 requests): the refresh hooks it after M05 and before M03 (MVP_PLAN
local-step order). Per covered name (watchlist, promoted, tracked): the quant leg, the
engine's proposal, the owner's verdict in force and the gate, written as three D13 rows —
`moat_quant`, `moat_verdict`, `moat_gate` — in one short transaction per name with the
`m06_verdict` review item when one is due (setup batch, or a quant class changed at a new
10-K). `challenger_max_rung` is Part 2's and is not written here.

Rows carry `as_of` = the newest deciding input's date (the newest 10-K behind the quant
leg; for the verdict and the gate, the later of that and the verdict's date), so a rerun on
unchanged facts updates the same rows. Timeframes: `moat_quant` and `moat_verdict` MY ✓ PT
✓ ST info; `moat_gate` MY ✓ (the gate), PT and ST info.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from engine.financials import models as models_mod
from engine.moat import gate as gate_mod
from engine.moat import params as params_mod
from engine.moat import quant as quant_mod
from engine.moat import verdict as verdict_mod
from engine.sec.identity import normalize_cik
from engine.signals import Source, write_signal

MODULE = "M06"
SIGNALS = ("moat_quant", "moat_verdict", "moat_gate")
INFO = {"moat_quant": ("ST",), "moat_verdict": ("ST",), "moat_gate": ("PT", "ST")}


@dataclass
class Out:
    signal: str
    as_of: str
    method: str
    value: float | None = None
    text: str | None = None
    missing: str | None = None
    sources: list[Source] = field(default_factory=list)
    info: tuple[str, ...] = ()


@dataclass
class NameResult:
    ticker: str
    cik: str
    quant: quant_mod.Quant
    proposal: verdict_mod.Proposal
    verdict: sqlite3.Row | None
    gate: gate_mod.Gate
    rows: list[Out]
    item: str = "none"  # queued | none

    def row(self, signal: str) -> Out | None:
        return next((o for o in self.rows if o.signal == signal), None)


def _na_source(q: quant_mod.Quant, day: str) -> list[Source]:
    """N_A rows: the routing is the deciding input — an owner model tag (grade B) or the SEC
    industry code (A, with the newest 10-K behind the years)."""
    if q.route_how.startswith("model tag"):
        return [Source(f"config/company_models.toml: {q.tag}", q.as_of or day, "B",
                       "owner model tag")]  # fmt: skip
    newest = sorted(q.sources, key=lambda s: s.date)[-1:] if q.sources else []
    return [Source(s.ref, s.date, "A", "SEC SIC routing; " + s.what) for s in newest] or [
        Source("SEC entity SIC", q.as_of or day, "A", "SEC SIC routing")
    ]


def verdict_sources(engine: sqlite3.Connection, v: sqlite3.Row) -> list[Source]:
    if v["grade"] == "A" and v["passage_ref"]:
        acc = v["passage_ref"].split("/", 1)[0]
        row = engine.execute("SELECT filed FROM filing WHERE accession = ?", (acc,)).fetchone()
        return [
            Source(
                acc,
                (row[0] if row else v["as_of"])[:10],
                "A",
                f"verified quote {v['passage_ref']}; owner verdict {v['verdict_id']}",
            )
        ]
    return [Source(f"M06 verdict {v['verdict_id']}", v["as_of"], "B",
                   f"owner entry by {v['decided_by']}")]  # fmt: skip


def verdict_method(v: sqlite3.Row, q: quant_mod.Quant, prop: verdict_mod.Proposal,
                   stale: str) -> str:  # fmt: skip
    bits = [
        f"{v['verdict']} (owner, {v['decided_at'][:10]})",
        f"sources: {verdict_mod.source_text(v['sources'])}",
        f"catch-up band {verdict_mod.band_text(v['band'])}",
        f"reason: {v['reason']}",
        (f"quote verified in {v['passage_ref']} (grade A)" if v["grade"] == "A"
         else "owner entry without a verified filing quote (grade B)"),
        f"quant at entry: {v['quant_class'] or '—'} ({v['quant_fy'] or '—'}); now: "
        f"{q.state or 'missing'}",
        f"engine proposal now: {prop.verdict}",
        stale or "current (no newer 10-K)",
    ]  # fmt: skip
    if v["override"]:
        bits.append(f"gate override {v['override']}: {v['override_reason']}")
    return "; ".join(bits)


def name_result(
    engine: sqlite3.Connection,
    ticker: str,
    cik: str,
    now: datetime,
    *,
    p: params_mod.Params,
    mf: models_mod.ModelFile,
    peers: bool = True,
) -> NameResult:
    norm = normalize_cik(cik) or cik
    day = now.date().isoformat()
    q = quant_mod.compute(engine, norm, ticker, day, p, mf, peers=peers)
    prop = verdict_mod.propose(q)
    v = verdict_mod.current(engine, norm)
    g = gate_mod.compute(v, q.state, p.my_horizon_years, q.newest_filed)
    rows: list[Out] = []
    q_as_of = q.as_of or day

    # moat_quant
    method = q.method()
    if q.state is None:
        rows.append(Out("moat_quant", q_as_of, method, missing=q.missing,
                        info=INFO["moat_quant"]))  # fmt: skip
    elif q.state in ("not_applicable",):
        rows.append(Out("moat_quant", q_as_of, method, text=q.state,
                        sources=_na_source(q, day), info=INFO["moat_quant"]))  # fmt: skip
    else:
        val = round(q.value, 4) if q.value is not None else None
        rows.append(Out("moat_quant", q_as_of, method, value=val, text=q.state,
                        sources=list(q.sources), info=INFO["moat_quant"]))  # fmt: skip

    # moat_verdict
    if q.state == "not_applicable":
        v_as_of = max(q_as_of, v["as_of"]) if v is not None else q_as_of
        rows.append(Out("moat_verdict", v_as_of, f"N_A: {q.headline()}; {q.route_how}",
                        text="N_A", sources=_na_source(q, day),
                        info=INFO["moat_verdict"]))  # fmt: skip
    elif v is None:
        item = verdict_mod.open_item(engine, norm)
        where = f" (item {item['item_id']})" if item else ""
        rows.append(Out("moat_verdict", q_as_of, f"engine proposal: {prop.verdict} — {prop.why}"
                        f"; enter it on the M06 setup page{where}",
                        missing="no owner verdict yet", info=INFO["moat_verdict"]))  # fmt: skip
    else:
        v_as_of = max(q_as_of, v["as_of"])
        rows.append(Out("moat_verdict", v_as_of, verdict_method(v, q, prop, g.stale),
                        text=v["verdict"], sources=verdict_sources(engine, v),
                        info=INFO["moat_verdict"]))  # fmt: skip

    # moat_gate (grade = the verdict's grade)
    tail = f"MY horizon {p.my_horizon_years} years (D-M06-6); survival gate is M01 rule 1's"
    if g.state is None:
        rows.append(Out("moat_gate", q_as_of, f"{tail}; a first MY entry stays blocked "
                        "(D-M01-9)", missing=g.why, info=INFO["moat_gate"]))  # fmt: skip
    else:
        na = g.state == "not_applicable" or v is None
        srcs = _na_source(q, day) if na else verdict_sources(engine, v)
        g_as_of = max(q_as_of, v["as_of"]) if v is not None else q_as_of
        why = g.why + (f"; {g.stale}" if g.stale else "") + f"; {tail}"
        rows.append(Out("moat_gate", g_as_of, why, text=g.state, sources=srcs,
                        info=INFO["moat_gate"]))  # fmt: skip
    return NameResult(ticker, norm, q, prop, v, g, rows)


def write_rows(engine: sqlite3.Connection, r: NameResult) -> int:
    """Rows written. Caller owns the transaction."""
    n = 0
    for o in r.rows:
        common = dict(engine=engine, cik=r.cik, ticker=r.ticker, module_id=MODULE,
                      signal=o.signal, as_of=o.as_of, info=o.info)  # fmt: skip
        if o.missing is not None:
            n += write_signal(**common, method=o.method, missing=o.missing, sources=o.sources)
        else:
            n += write_signal(**common, method=o.method, value=o.value, value_text=o.text,
                              sources=o.sources)  # fmt: skip
    return n


def write_one(engine: sqlite3.Connection, r: NameResult, now: datetime, *,
              items: bool = True) -> int:  # fmt: skip
    """Rows and the due review item of one name in one short transaction."""
    engine.execute("BEGIN")
    try:
        n = write_rows(engine, r)
        if items:
            r.item = verdict_mod.propose_item(engine, r.quant, now)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return n


@dataclass
class MoatPass:
    results: dict[str, NameResult]
    written: int = 0
    queued: int = 0
    errors: dict[str, str] = field(default_factory=dict)
    params_error: str = ""
    models_error: str = ""


def moat_pass(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    p: params_mod.Params | None = None,
    params_error: str = "",
    mf: models_mod.ModelFile | None = None,
    items: bool = True,
) -> MoatPass:
    """M06 for every covered name (0 requests); one name's error does not stop the others."""
    if p is None:
        p, params_error = params_mod.load_safe()
    mf = mf if mf is not None else models_mod.load_safe()
    mp = MoatPass({}, params_error=params_error, models_error=mf.error)
    for ticker, cik in sorted(companies.items()):
        if not cik:
            continue
        try:
            r = name_result(engine, ticker, cik, now, p=p, mf=mf)
            mp.written += write_one(engine, r, now, items=items)
            mp.queued += r.item == "queued"
            mp.results[ticker] = r
        except Exception as e:
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            mp.errors[ticker] = f"{type(e).__name__}: {e}"
    return mp


def recompute_one(engine: sqlite3.Connection, ticker: str, cik: str, now: datetime) -> NameResult:
    """After an owner entry (UI): the three rows rewritten at once (no item proposed)."""
    p, _ = params_mod.load_safe()
    r = name_result(engine, ticker, cik, now, p=p, mf=models_mod.load_safe())
    write_one(engine, r, now, items=False)
    return r


def _share(v: float | None) -> str:
    return f"{v:.0%}" if v is not None else "—"


def line(r: NameResult) -> str:
    """One line per name for the log."""
    q = r.quant
    if q.state is None:
        qtext = f"missing: {q.missing}"
    elif q.reading is not None:
        rd = q.reading
        med = f"{rd.median * 100:.1f}%" if rd.median is not None else "—"
        qtext = (f"{q.state} {_share(rd.share)} ({rd.above}/{rd.n} > {q.params.hurdle:.0%}, "
                 f"median {med}, last {rd.recent_n} above {rd.recent_above})")  # fmt: skip
        sens = ", ".join(f"{h:.0%} {s.state}" for h, s in q.sensitivity)
        if sens:
            qtext += f" [±2 pp: {sens}]"
    else:
        qtext = q.state
    gm = f"GM median {q.gm_median:.1f}%" if q.gm_median is not None else "GM missing"
    v = r.verdict["verdict"] if r.verdict is not None else (
        "N_A" if q.state == "not_applicable" else "no verdict")  # fmt: skip
    gate = r.gate.state or f"missing ({r.gate.why})"
    if r.gate.override:
        gate += " (override)"
    if r.gate.stale:
        gate += f", {r.gate.stale}"
    item = " · item queued" if r.item == "queued" else ""
    return (f"{r.ticker}: quant {qtext}; {gm}; proposal {r.proposal.verdict}; verdict {v}; "
            f"gate {gate}{item}")  # fmt: skip


def strip_lines(r: NameResult) -> list[str]:
    """ROIC / GM / OM per fiscal year (the standard rows, D32)."""
    q = r.quant
    if not q.years:
        return [f"  {r.ticker}: no fiscal years stored"]

    def pct(v, d=1):
        return f"{v:.{d}f}%" if v is not None else "—"

    out = [f"  {r.ticker} ({q.years[0].label}–{q.years[-1].label}):"]
    for y in q.years:
        roic = pct(y.roic * 100) if y.roic is not None else (
            "n/m" if y.roic_text.startswith(quant_mod.NM) else "—")  # fmt: skip
        extra = f" [{y.excluded}]" if y.excluded else ""
        why = "" if y.roic is not None else f" ({y.roic_text[:60]})"
        out.append(f"    {y.label}: ROIC {roic}{why}, GM {pct(y.gm)}, OM {pct(y.om)}{extra}")
    return out


def summary_lines(mp: MoatPass) -> list[str]:
    states: dict[str, int] = {}
    verdicts: dict[str, int] = {}
    gates: dict[str, int] = {}
    for r in mp.results.values():
        k = r.quant.state or "missing"
        states[k] = states.get(k, 0) + 1
        vk = r.verdict["verdict"] if r.verdict is not None else (
            "N_A" if r.quant.state == "not_applicable" else "none")  # fmt: skip
        verdicts[vk] = verdicts.get(vk, 0) + 1
        gk = r.gate.state or "missing"
        gates[gk] = gates.get(gk, 0) + 1
    open_items = sum(1 for r in mp.results.values() if r.proposal.needs_item and r.verdict is None)

    def fmt(d):
        return ", ".join(f"{k} {v}" for k, v in sorted(d.items())) or "—"

    out = [
        f"M06 moat: {len(mp.results)} names; {mp.written} rows written; "
        f"{mp.queued} m06_verdict item(s) queued this pass",
        f"  moat_quant: {fmt(states)}",
        f"  moat_verdict: {fmt(verdicts)} · names awaiting a verdict (setup batch): {open_items}",
        f"  moat_gate (MY): {fmt(gates)}",
    ]
    if mp.params_error:
        out.append(f"  moat.toml rejected: {mp.params_error}")
    if mp.models_error:
        out.append(f"  model tag file rejected, no tags apply: {mp.models_error}")
    out += [f"  {t}: error — {e}" for t, e in sorted(mp.errors.items())]
    return out


def run_local_part(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    """The refresh hook (after M05, before M03). Never fails."""
    t0 = clock()
    try:
        lines = summary_lines(moat_pass(engine, companies, now))
    except Exception as e:
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        lines = [f"  M06: error — {type(e).__name__}: {e}"]
    return [f"M06 moat — local pass (Part 1, 0 requests) ({clock() - t0:.1f} s):", *lines]
