"""M04 Part 3 inside the refresh and the `flags` script: restatement walk, filing events,
rating sentences and their signals (D-M04-15, -16, -21, -37, -71, -77).

- `run_sec_part` (refresh SEC part, per-new-filing work only, D-M04-70): the text of a new
  8-K whose item needs it (3.01, 4.01, 4.02, 2.04, 1.03), filed in the last 30 days and not
  stored yet (the nightly document step usually stored it already: 0 requests). Old
  filings, prior 10-Ks and R1 history are owner-run (`scripts/run_financials.py flags`).
- `flags_pass` (local, 0 requests): walk, events, ratings, signals `restatement`,
  `non_reliance`, `restate_delta`; review items (cap 5, D-M04-71) for core and promoted
  names only (tracked names: rows, no items, D-M04-80).
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from engine.financials import events, filings, queue, ratings, restate
from engine.financials.profile import full_scope
from engine.sec.client import SecClient, iso
from engine.signals import Source, write_signal

MODULE = "M04"
NEW_DAYS = 30


@dataclass
class CompanyFlags:
    ticker: str
    cik: str
    steps: list[restate.Step] = field(default_factory=list)
    walk: dict[str, int] = field(default_factory=dict)
    events: list[events.EventRow] = field(default_factory=list)
    event_counts: dict[str, int] = field(default_factory=dict)
    ratings: list[ratings.RatingSentence] = field(default_factory=list)
    rating_counts: dict[str, int] = field(default_factory=dict)
    restatement: str = ""
    non_reliance: str = ""
    restate_delta: str = ""
    error: str = ""


@dataclass
class FlagsPass:
    companies: dict[str, CompanyFlags]
    flushed: int = 0
    alerts: list[str] = field(default_factory=list)


def _latest_periodic(engine: sqlite3.Connection, cik: str) -> sqlite3.Row | None:
    return engine.execute(
        "SELECT f.accession, f.form, f.filed FROM filing f JOIN filing_cik c ON c.accession = "
        "f.accession WHERE c.cik = ? AND f.form IN ('10-K', '10-Q', '20-F', '40-F', '10-KT', "
        "'10-K/A', '10-Q/A') ORDER BY f.filed DESC LIMIT 1",
        (cik,),
    ).fetchone()


def write_flag_signals(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    cik: str,
    ticker: str | None,
    now: datetime,
) -> tuple[str, str, str]:
    """`restatement`, `non_reliance` (all timeframes) and `restate_delta` (ST info).
    Caller owns the transaction. Returns the three states."""
    today = now.date()
    since = restate.window_start(today)
    latest = _latest_periodic(engine, cik)
    base_src = [Source(latest["accession"], latest["filed"], "A", latest["form"])] if latest else []
    base_date = latest["filed"] if latest else today.isoformat()
    common = dict(engine=engine, cik=cik, ticker=ticker, module_id=MODULE)

    # restatement (D-M04-15)
    found: dict[str, list[tuple[str, str, str]]] = {
        "escalated": [],
        "4.02": [],
        "dei": [],
        "little_r": [],
    }
    for r in engine.execute(
        "SELECT accession, item, filed, class FROM m04_event WHERE cik = ? "
        "AND filed >= ? AND (item = '4.02' OR class = 'escalated')",
        (cik, since),
    ):
        key = "4.02" if r["item"] == "4.02" else "escalated"
        found[key].append((r["accession"], r["filed"], f"8-K {r['item']} {r['class']}"))
    flags = restate.dei_flags(engine, cik, since)
    found["dei"] = [
        (f.accession, f.filed, f"{f.form} dei error flag true") for f in flags if f.state == "true"
    ]
    found["little_r"] = [
        (h.accession, h.filed, f"{h.form} little r: “{h.quote[:160]}”")
        for h in restate.little_r_text(engine, corpus, cik, since)
    ]
    for r in restate.stored_steps(engine, cik):
        owner = r["owner_outcome"] == "error"
        if r["to_filed"] >= since and ('"family": "error"' in r["labels"] or owner):
            found["little_r"].append(
                (
                    r["to_accession"],
                    r["to_filed"],
                    f"walk {r['concept']} {r['period_end']} "
                    + ("owner: error" if owner else "labelled error"),
                )
            )
    # one entry per filing: text and walk findings in the same filing count once
    found["little_r"] = list({a: (a, d, w) for a, d, w in reversed(found["little_r"])}.values())
    state = next((k for k in ("escalated", "4.02", "dei", "little_r") if found[k]), "none")
    srcs = [Source(a, d, "A", w) for k in found for a, d, w in found[k]]
    dei_read = sum(1 for f in flags if f.state in ("true", "false"))
    dei_due = sum(1 for f in flags if f.state != "not required")
    method = (
        f"restatement sources, {since} on (D-M04-15): 4.02 {len(found['4.02'])}, dei flag "
        f"true {len(found['dei'])} (read {dei_read} of {dei_due} annual covers filed from "
        f"{restate.DEI_FROM}), little r {len(found['little_r'])}, escalated 4.01 "
        f"{len(found['escalated'])}"
    )
    if srcs:
        write_signal(
            **common,
            signal="restatement",
            as_of=max(s.date for s in srcs),
            value_text=state,
            method=method,
            sources=srcs,
        )
    elif base_src:
        write_signal(
            **common,
            signal="restatement",
            as_of=base_date,
            value_text="none",
            method=method + "; none found",
            sources=base_src,
        )
    else:
        write_signal(
            **common,
            signal="restatement",
            as_of=base_date,
            method=method,
            missing="no periodic filing stored",
        )

    # non_reliance (D-M04-21)
    nr = restate.non_reliance(engine, cik)
    if nr is not None:
        write_signal(
            **common,
            signal="non_reliance",
            as_of=nr.filed,
            value_text="open",
            method=nr.mark + "; adds not blocked (D-M04-21)",
            sources=[Source(nr.accession, nr.filed, "A", "8-K 4.02")],
        )
        nr_state = "open"
    elif base_src:
        write_signal(
            **common,
            signal="non_reliance",
            as_of=base_date,
            value_text="none",
            method="no open 8-K 4.02",
            sources=base_src,
        )
        nr_state = "none"
    else:
        write_signal(
            **common,
            signal="non_reliance",
            as_of=base_date,
            method="open 4.02",
            missing="no periodic filing stored",
        )
        nr_state = "missing"

    # restate_delta (D-M04-16): steps filed in the window
    rows = [r for r in restate.stored_steps(engine, cik) if r["to_filed"] >= since]
    open_review = [
        r for r in rows if r["outcome"] == "review" and (r["owner_outcome"] or "") != "explained"
    ]
    watch = [r for r in rows if r["outcome"] == "watch"]
    delta_state = "review" if open_review else "watch" if watch else "explained" if rows else "none"
    method = (
        f"walk steps filed {since} on: {len(rows)} ({len(open_review)} review, "
        f"{len(watch)} watch); tolerance 0.5% and $0.1M after the ordered labels "
        "(D-M04-16)"
    )
    if open_review:
        worst = max(open_review, key=lambda r: abs(float(r["residual"])))
        method += (
            f"; largest: {worst['concept']} {worst['period_end']} residual "
            f"{restate.money(float(worst['residual']))} in {worst['to_accession']}"
        )
    pcts = [float(r["residual_pct"]) * 100 for r in open_review if r["residual_pct"] is not None]
    dsrc = [
        Source(r["to_accession"], r["to_filed"], "A", r["concept"])
        for r in (open_review or watch or rows)
    ]
    if dsrc:
        write_signal(
            **common,
            signal="restate_delta",
            as_of=max(s.date for s in dsrc),
            value=round(max(pcts), 3) if pcts else None,
            value_text=delta_state,
            method=method,
            sources=dsrc,
            info=("ST",),
        )
    elif base_src:
        write_signal(
            **common,
            signal="restate_delta",
            as_of=base_date,
            value_text="none",
            method=method,
            sources=base_src,
            info=("ST",),
        )
    else:
        write_signal(
            **common,
            signal="restate_delta",
            as_of=base_date,
            method=method,
            missing="no periodic filing stored",
            info=("ST",),
        )
    return state, nr_state, delta_state


def _tx(engine: sqlite3.Connection, fn: Callable, *args, **kw):
    engine.execute("BEGIN")
    try:
        out = fn(*args, **kw)
        engine.execute("COMMIT")
        return out
    except Exception:
        engine.execute("ROLLBACK")
        raise


def company_flags(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    ticker: str,
    cik: str,
    now: datetime,
    *,
    queue_items: bool = True,
) -> CompanyFlags:
    cf = CompanyFlags(ticker, cik)
    cf.steps = restate.walk(engine, corpus, cik)
    cf.walk = _tx(
        engine, restate.store, engine, cik, ticker, cf.steps, now, queue_items=queue_items
    )
    evidence = restate.evidence_dates(engine, corpus, cik)
    cf.events = events.classify(engine, corpus, cik, now.date(), evidence)
    cf.event_counts = _tx(
        engine, events.store, engine, cik, ticker, cf.events, now, queue_items=queue_items
    )
    cf.ratings = ratings.scan(engine, corpus, cik)
    cf.rating_counts = _tx(
        engine, ratings.store, engine, cik, ticker, cf.ratings, now, queue_items=queue_items
    )
    cf.restatement, cf.non_reliance, cf.restate_delta = _tx(
        engine, write_flag_signals, engine, corpus, cik, ticker, now
    )
    return cf


def flags_pass(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    companies: dict[str, str],
    now: datetime,
) -> FlagsPass:
    """Part 3 for every covered company (0 requests). One company's error does not stop
    the others."""
    start = iso(now)
    scope = set(full_scope(engine, companies).values())
    out: dict[str, CompanyFlags] = {}
    for ticker, cik in sorted(companies.items()):
        try:
            out[ticker] = company_flags(engine, corpus, ticker, cik, now, queue_items=cik in scope)
        except Exception as e:
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            out[ticker] = CompanyFlags(ticker, cik, error=f"{type(e).__name__}: {e}")
    flushed = _tx(engine, queue.flush_overflow, engine, now)
    return FlagsPass(out, flushed, events.alert_lines(engine, start))


def run_sec_part(
    client: SecClient,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    """Per-new-filing: texts of new 8-Ks whose item class needs them (D-M04-70)."""
    t0 = clock()
    since = (now - timedelta(days=NEW_DAYS)).date().isoformat()
    todo = [
        a
        for _, c in sorted(companies.items())
        for a in events.text_wanted(engine, corpus, c, since)
    ]
    got = filings.fetch_all(client, engine, corpus, todo, now) if todo else []
    stored = sum(1 for f in got if f.outcome == "stored")
    line = (
        f"M04 filing-event texts (Part 3): {len(todo)} new 8-K(s) need text; stored "
        f"{stored}"
        + ("; throttled, the rest waits" if any(f.throttled for f in got) else "")
        + f" ({clock() - t0:.1f} s)"
    )
    return [line]


def local_lines(fp: FlagsPass) -> list[str]:
    """Summary lines for the refresh report (alerts uncapped, D-M04-77)."""
    steps = sum(len(c.steps) for c in fp.companies.values())
    review = sum(c.walk.get("review", 0) for c in fp.companies.values())
    evs = sum(len(c.events) for c in fp.companies.values())
    rat = sum(len(c.ratings) for c in fp.companies.values())
    lines = [
        f"Part 3: walk {steps} steps ({review} over tolerance), {evs} filing events "
        f"(3 years), {rat} rating sentences; {fp.flushed} overflow item(s) flushed"
    ]
    lines += [f"  {c.ticker}: error — {c.error}" for c in fp.companies.values() if c.error]
    if fp.alerts:
        lines.append("  M04 filing events new this run (alerts, D-M04-77):")
        lines += [f"    {a}" for a in fp.alerts]
    return lines
