"""M04 Part 8a inside the refresh and the `cvd` script (D-M04-1, -56, -58, -100…105).

`cvd_pass` (local, 0 requests) evaluates the CvD grid for every covered company as of
today (`cvd.evaluate`), writes the Part 8a signals, opens or withdraws `m04_cvd` items
(group 2, inside the weekly cap of 5; core and promoted only, D-M04-80) and stores one
summary line per company for the M04 tab's watchlist table (`refresh_state`
`m04_cvd_line:<cik>`). Hooked into `scripts/run_refresh.py` after the gate and quality
local passes (`financials_cvd_local_step`), so filing status, the gate and the latest
facts are current.

Signals (final "Signals out", D-M04-103): `cvd_state`, `cvd_confidence`,
`cvd_coverage_q1`, `cvd_coverage_q2`, `deeper_than_peers`, `f_quality`, `f_score`,
`g_score`, `market_share_chg_pp`; the deferred ones (`normalized_ep_cur`,
`normalized_ep_cyc`, `overreaction_gap`, `burn_no_share_gain`) are written as missing rows
"deferred (MVP, D31)" so the gap shows in every timeframe (D10). `as_of` = the latest
quarter's filing date (the annual report's for the health scores), so the logon pass
updates the same rows.

`m04_cvd` (D-M04-56, -102): opens when the computed state is AMBIGUOUS, STUMBLE or
CYCLE_PLUS_DAMAGE — not while the gate fails (the gate alert covers it) and not while a
question lacks rows only because a peer's period is not filed yet (S6.1). One item per
company and computed state; the owner's answer (a state) becomes the effective state while
the computed state stays the same; when the computed state leaves review the answer is
cleared, so a later episode asks again.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from engine.financials import cvd, models, queue
from engine.financials.profile import full_scope
from engine.sec.client import iso
from engine.sec.identity import normalize_cik
from engine.signals import Source, write_signal

MODULE = "M04"
LINE_KEY = "m04_cvd_line:{cik}"
SIGNALS = (
    "cvd_state",
    "cvd_confidence",
    "cvd_coverage_q1",
    "cvd_coverage_q2",
    "deeper_than_peers",
    "f_quality",
    "f_score",
    "g_score",
    "market_share_chg_pp",
)
DEFERRED_SIGNALS = (
    ("normalized_ep_cur", ("MY", "PT", "ST")),
    ("normalized_ep_cyc", ("MY", "PT", "ST")),
    ("overreaction_gap", ("ST",)),
    ("burn_no_share_gain", ("ST",)),
)
DEFERRED_WHY = {
    "normalized_ep_cur": "deferred (MVP, D31): normalized earnings power and the gauge (gauge.py)",
    "normalized_ep_cyc": "deferred (MVP, D31): normalized earnings power and the gauge (gauge.py)",
    "overreaction_gap": "deferred (MVP, D31): the overreaction gauge informs only (D-M04-62)",
    "burn_no_share_gain": "deferred (MVP, D31): Red Flag 1 row (D-M04-30)",
}


@dataclass
class CompanyCvd:
    ticker: str
    cik: str
    c: cvd.CvD | None = None
    queued: dict[str, str] = field(default_factory=dict)
    withdrawn: int = 0
    signals: int = 0
    error: str = ""


@dataclass
class CvdPass:
    companies: dict[str, CompanyCvd]
    flushed: int = 0


def _tx(engine: sqlite3.Connection, fn: Callable, *args, **kw):
    engine.execute("BEGIN")
    try:
        out = fn(*args, **kw)
        engine.execute("COMMIT")
        return out
    except Exception:
        engine.execute("ROLLBACK")
        raise


def _grade_sources(c: cvd.CvD) -> list[Source]:
    """Deciding inputs: the latest filing plus every present row's inputs (an owner share
    entry is grade B, D-M04-9)."""
    out = list(c.sources)
    for r in c.rows:
        if r.counted and r.present:
            out += r.sources
    return out


def write_signals(engine: sqlite3.Connection, c: cvd.CvD, today: str) -> int:
    """The Part 8a rows; caller owns the transaction."""
    n = 0
    common = dict(engine=engine, cik=c.cik, ticker=c.ticker, module_id=MODULE)
    as_of = c.latest_filed or today
    base = c.sources or [Source("facts", as_of, "A", "stored facts")]

    def missing(name: str, why: str, info=("ST",), date: str | None = None, method: str = ""):
        nonlocal n
        n += write_signal(
            **common,
            signal=name,
            as_of=date or as_of,
            method=method,
            missing=why,
            info=info,
            sources=base if c.sources else (),
        )

    def n_add(k: int) -> None:
        nonlocal n
        n += k

    if c.excluded or c.missing:
        why = c.excluded or c.missing
        for s in ("cvd_state", "cvd_confidence", "deeper_than_peers", "market_share_chg_pp"):
            missing(s, why)
        for s in ("cvd_coverage_q1", "cvd_coverage_q2"):
            missing(s, why, ("MY", "PT", "ST"))
        if not c.excluded:
            _health_signals(c, common, as_of, missing, n_add)
        else:
            for s, info in (
                ("f_quality", ("ST",)),
                ("f_score", ("MY", "PT", "ST")),
                ("g_score", ("MY", "PT", "ST")),
            ):
                missing(s, why, info)
        for name, info in DEFERRED_SIGNALS:
            missing(name, DEFERRED_WHY[name], info)
        return n

    method = c.method()
    n += write_signal(
        **common,
        signal="cvd_state",
        as_of=as_of,
        value_text=c.state,
        method=method,
        sources=_grade_sources(c),
        info=("ST",),
    )
    if c.active and c.confidence is not None:
        n += write_signal(
            **common,
            signal="cvd_confidence",
            as_of=as_of,
            value=c.confidence,
            method=f"lower of the two winning shares (D-M04-56); {c.coverage_text()}",
            sources=_grade_sources(c),
            info=("ST",),
        )
    else:
        missing("cvd_confidence", "not active (NO_SLOWDOWN)")
    for q, name in ((c.q1, "cvd_coverage_q1"), (c.q2, "cvd_coverage_q2")):
        if c.active and q is not None and q.coverage is not None:
            n += write_signal(
                **common,
                signal=name,
                as_of=as_of,
                value=round(q.coverage, 4),
                method=f"{q.present} of {q.applicable} applicable rows present; {q.text()}",
                sources=base,
                info=("MY", "PT", "ST"),
            )
        else:
            missing(name, "not active (NO_SLOWDOWN)", ("MY", "PT", "ST"))
    rev = c.row("revenue_vs_peers")
    if not c.active:
        missing("deeper_than_peers", "not active (NO_SLOWDOWN)")
    elif c.deeper is None:
        missing("deeper_than_peers", f"revenue row missing: {rev.why if rev else 'no row'}")
    else:
        n += write_signal(
            **common,
            signal="deeper_than_peers",
            as_of=as_of,
            value_text="flagged" if c.deeper else "none",
            method=f"{rev.value}; {rev.why}",
            sources=base,
            info=("ST",),
        )
    sh = c.share
    if sh is not None and sh.change_pp is not None:
        n += write_signal(
            **common,
            signal="market_share_chg_pp",
            as_of=sh.as_of or as_of,
            value=round(sh.change_pp, 2),
            method=f"{sh.reading}: {sh.text}",
            sources=sh.sources,
            info=("ST",),
        )
    else:
        missing("market_share_chg_pp", sh.text if sh else "no share data")
    _health_signals(c, common, as_of, missing, n_add)
    for name, info in DEFERRED_SIGNALS:
        missing(name, DEFERRED_WHY[name], info)
    return n


def _health_signals(c: cvd.CvD, common: dict, as_of: str, missing, add) -> None:
    for sc, info in (
        (c.f_quality, ("ST",)),
        (c.f_score, ("MY", "PT", "ST")),
        (c.g_score, ("MY", "PT", "ST")),
    ):
        if sc is None:
            continue
        date = sc.filed or as_of
        method = f"{sc.label}: {sc.text()}"
        if sc.kind == "f_quality" and sc.band:
            method = (
                f"{sc.band} ({sc.known} of 5; ≥ 4 intact, 3 neutral, ≤ 2 weakening; "
                f"D-M04-53, -59, -65); {method}"
            )
        elif sc.kind == "g_score" and not sc.missing:
            method = f"G {sc.known} of {sc.n} (8 possible); shown, not voted (D-M04-53); {method}"
        elif sc.kind == "f_score" and not sc.missing:
            method = f"Piotroski F {sc.known} of 9; shown, not voted (D-M04-53); {method}"
        if sc.missing or not sc.sources or (sc.kind == "f_quality" and sc.band is None):
            missing(sc.kind, sc.missing or "no inputs", info, date, method)
        else:
            add(
                write_signal(
                    **common,
                    signal=sc.kind,
                    as_of=date,
                    value=sc.known,
                    value_text=sc.band if sc.kind == "f_quality" else None,
                    method=method,
                    sources=sc.sources,
                    info=info,
                )
            )


# --- m04_cvd items ---------------------------------------------------------------------------


def _payload(c: cvd.CvD) -> dict:
    return {
        "ticker": c.ticker,
        "computed": c.raw_state,
        "confidence": c.confidence,
        "coverage": c.coverage_text(),
        "period_end": c.ref_end,
        "basis": c.ref_kind,
        "filed": c.latest_filed,
        "q1": c.q1.text() if c.q1 else "",
        "q2": c.q2.text() if c.q2 else "",
        "rows": [
            {"q": r.q, "label": r.label, "reading": r.reading, "value": r.value, "why": r.why}
            for r in c.rows
        ],
        "gate": c.gate.state if c.gate else None,
        "m01": c.m01.text() if c.m01 else "",
        "activation": "; ".join(c.triggers),
    }


def _awaiting_peers(c: cvd.CvD) -> bool:
    for q in (c.q1, c.q2):
        if q is None or q.present >= cvd.MIN_PRESENT:
            continue
        if any(r.awaiting for r in c.rows if r.q == q.q):
            return True
    return False


def _clear(engine: sqlite3.Connection, cik: str) -> None:
    engine.execute("DELETE FROM refresh_state WHERE name = ?", (cvd.ANSWER_KEY.format(cik=cik),))
    # a resolved proposal row would suppress the next episode's item: drop the routing rows
    # whose items are answered (the review history stays in review_queue)
    engine.execute(
        "DELETE FROM m04_proposal WHERE kind = 'm04_cvd' AND cik = ? AND item_id IN "
        "(SELECT item_id FROM review_queue WHERE resolved_at IS NOT NULL)",
        (cik,),
    )


def propose_items(engine: sqlite3.Connection, cc: CompanyCvd, now: datetime) -> None:
    c = cc.c
    live: set[str] = set()
    want = (
        c is not None
        and not c.excluded
        and not c.missing
        and c.raw_state in cvd.REVIEW
        and not (c.gate and c.gate.state == "fail")
        and not _awaiting_peers(c)
    )
    if c is not None and c.raw_state not in cvd.REVIEW:
        _clear(engine, cc.cik)
    if want and c.answer is None:
        key = f"{cc.cik}:{c.raw_state}"
        live.add(key)
        a = cvd.stored_answer(engine, cc.cik)
        if a and a.get("raw_state") != c.raw_state:
            _clear(engine, cc.cik)
        conf = f"{c.confidence:.2f}" if c.confidence is not None else "—"
        reason = (
            f"{c.ticker or c.cik}: CvD {c.raw_state} (confidence {conf}; coverage "
            f"{c.coverage_text()}) on the {c.ref_kind} to {c.ref_end} — choose the state "
            "(your answer becomes the state, D-M04-56)"
        )
        status = queue.propose(
            engine, "m04_cvd", key, reason, _payload(c), now, cik=cc.cik, filed=c.latest_filed
        )
        cc.queued[f"m04_cvd:{c.raw_state}"] = status
    elif want:
        live.add(f"{cc.cik}:{c.raw_state}")
    cc.withdrawn = queue.withdraw_stale(
        engine,
        "m04_cvd",
        cc.cik,
        live,
        now,
        "recomputed: the CvD state no longer needs review (or the gate fails, or peers are "
        "awaited)",
    )


def answer(
    engine: sqlite3.Connection,
    item_id: int,
    payload: dict,
    cik: str | None,
    target: str,
    note: str,
    by: str,
    now: datetime,
) -> str:
    """The owner's state for an `m04_cvd` item (queue.apply calls it inside the closing
    transaction): stored per company with the computed state it answers, and written into
    the latest `cvd_state` rows."""
    chosen = cvd.ANSWERS.get((target or "").strip().lower())
    if chosen is None:
        raise queue.QueueError(
            "Choose a state: cyclical trough, stumble, cycle + damage or structural decline."
        )
    if not note.strip():
        raise queue.QueueError("A note is required: say why (D-M04-56).")
    if not cik:
        raise queue.QueueError("This item names no company.")
    raw = payload.get("computed")
    detail = {
        "raw_state": raw,
        "answer": chosen,
        "item_id": item_id,
        "by": by,
        "at": iso(now),
        "note": note.strip(),
        "period_end": payload.get("period_end"),
    }
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, "
        "'m04_cvd', ?, ?) ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
        "detail = excluded.detail",
        (cvd.ANSWER_KEY.format(cik=cik), iso(now), json.dumps(detail)),
    )
    row = engine.execute(
        "SELECT max(as_of) FROM signal WHERE cik = ? AND module_id = 'M04' AND "
        "signal = 'cvd_state'",
        (cik,),
    ).fetchone()
    if row and row[0]:
        engine.execute(
            "UPDATE signal SET value_text = ?, method = method || ? WHERE cik = ? AND module_id "
            "= 'M04' AND signal = 'cvd_state' AND as_of = ?",
            (
                chosen,
                f"; owner answer {chosen} (computed {raw}; item {item_id}, {by}, "
                f"{now.date().isoformat()}; D-M04-56)",
                cik,
                row[0],
            ),
        )
    return f"set_state {chosen} (computed {raw})"


# --- The pass --------------------------------------------------------------------------------


def summary(c: cvd.CvD) -> dict:
    return {
        "ticker": c.ticker,
        "state": c.state if not (c.excluded or c.missing) else None,
        "raw": c.raw_state,
        "confidence": c.confidence,
        "coverage": c.coverage_text(),
        "gate": c.gate.state if c.gate else None,
        "m01": c.m01.rule3 if c.m01 else "",
        "exit": "; ".join(c.m01.rule4) if c.m01 else "",
        "why": c.excluded or c.missing,
        "stale": c.stale,
        "overdue": c.overdue,
        "as_of": c.as_of,
    }


def company_cvd(
    engine: sqlite3.Connection,
    ticker: str,
    cik: str,
    now: datetime,
    *,
    mf: models.ModelFile | None = None,
    queue_items: bool = True,
    cache: dict | None = None,
) -> CompanyCvd:
    today = now.date().isoformat()
    norm = normalize_cik(cik) or cik
    ent = engine.execute("SELECT category FROM entity WHERE cik = ?", (norm,)).fetchone()
    cc = CompanyCvd(ticker, norm)
    cc.c = cvd.evaluate(
        engine,
        norm,
        ticker,
        today,
        models=mf,
        cache=cache,
        live_category=ent["category"] if ent and ent["category"] else None,
    )

    def work():
        cc.signals = write_signals(engine, cc.c, today)
        if queue_items:
            propose_items(engine, cc, now)
        engine.execute(
            "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, "
            "'cvd_step', ?, ?) ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
            "detail = excluded.detail",
            (LINE_KEY.format(cik=norm), iso(now), json.dumps(summary(cc.c))),
        )

    _tx(engine, work)
    return cc


def cvd_pass(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    mf: models.ModelFile | None = None,
) -> CvdPass:
    """Part 8a for every covered company (0 requests); one company's error does not stop the
    others."""
    scope = set(full_scope(engine, companies).values())
    mf = mf if mf is not None else models.load_safe()
    cache: dict = {}
    out: dict[str, CompanyCvd] = {}
    for ticker, cik in sorted(companies.items()):
        try:
            out[ticker] = company_cvd(
                engine, ticker, cik, now, mf=mf, queue_items=cik in scope, cache=cache
            )
        except Exception as e:
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            out[ticker] = CompanyCvd(ticker, cik, error=f"{type(e).__name__}: {e}")
    flushed = _tx(engine, queue.flush_overflow, engine, now)
    return CvdPass(out, flushed)


def local_lines(cp: CvdPass, seconds: float = 0.0) -> list[str]:
    states: dict[str, int] = {}
    for c in cp.companies.values():
        if c.c is not None:
            k = c.c.state or ("excluded" if c.c.excluded else "missing")
            states[k] = states.get(k, 0) + 1
    queued = sum(1 for c in cp.companies.values() for v in c.queued.values() if v == "queued")
    lines = [
        f"M04 CvD — local pass (Part 8a, 0 SEC requests) ({seconds:.1f} s): "
        + ", ".join(f"{k} {v}" for k, v in sorted(states.items()))
        + f"; m04_cvd queued {queued}; {cp.flushed} overflow item(s) flushed"
    ]
    lines += [f"  {c.ticker}: error — {c.error}" for c in cp.companies.values() if c.error]
    return lines


def run_local_part(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    """The refresh hook (after the gate and quality local passes). Never fails."""
    t0 = clock()
    try:
        return local_lines(cvd_pass(engine, companies, now), clock() - t0)
    except Exception as e:
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        return [f"M04 CvD — local pass: error — {type(e).__name__}: {e}"]


def company_line(cc: CompanyCvd) -> str:
    if cc.error:
        return f"{cc.ticker}: error — {cc.error}"
    s = summary(cc.c)
    if s["state"] is None:
        return f"{cc.ticker}: {s['why']}"
    conf = f"{s['confidence']:.2f}" if s["confidence"] is not None else "—"
    return (
        f"{cc.ticker}: {s['state']} · conf {conf} · {s['coverage']} · gate {s['gate']} · "
        f"M01 {s['m01']}" + (f" · exit warning: {s['exit']}" if s["exit"] else "")
    )


def stored_lines(engine: sqlite3.Connection, companies: dict[str, str]) -> list[dict]:
    """The watchlist summary from the last pass (M04 tab, /m04)."""
    out = []
    for ticker, cik in sorted(companies.items()):
        r = engine.execute(
            "SELECT detail, fetched_at FROM refresh_state WHERE name = ?",
            (LINE_KEY.format(cik=normalize_cik(cik) or cik),),
        ).fetchone()
        d = json.loads(r["detail"]) if r and r["detail"] else {}
        out.append({"ticker": ticker, "cik": cik, "at": r["fetched_at"] if r else None, **d})
    return out


def open_items(engine: sqlite3.Connection) -> list[str]:
    out = []
    for r in engine.execute(
        "SELECT item_id, cik, reason, created_at FROM review_queue WHERE kind = 'm04_cvd' AND "
        "resolved_at IS NULL ORDER BY item_id"
    ):
        out.append(f"m04_cvd (item {r['item_id']}, opened {r['created_at'][:10]}): {r['reason']}")
    return out
