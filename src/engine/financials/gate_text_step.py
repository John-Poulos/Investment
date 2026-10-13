"""M04 Part 4b-lite inside the refresh and the `gate-text` script (D-M04-34, -71, -95…98).

`text_pass` (local, 0 SEC requests; the refresh hooks it right before the Part 4a gate
pass, so the gate reads fresh text classes):

- per covered company: scan the stored documents not scanned yet at this classifier
  version (`gate_text.scan_company`), then read the current report's classes;
- signals `gc_language` and `covenant_status` (the current report's most severe class and
  its quote; "none" / "silent" when the report has no such sentence; missing when no
  periodic text is stored);
- review items for core and promoted names (tracked: rows only, D-M04-80), from the
  **current report only** (history rows are shown, never queued; live check 1): a fail
  class opens `m04_gate_fail` (alert, uncapped; one per report), a warn class opens
  `m04_gc_text` or `m04_covenant` (priority 1, capped; one per report and class),
  hypothetical wording opens `m04_gc_text` only while the runway is below 8 quarters. Keys
  hash the sentences (`<cik>:text|<class>|hypothetical:<sentence key>`), so a later report
  repeating the same sentences is the same finding, and an owner's answer is carried to
  the same sentence in later reports. The first scan of a company is a baseline: recorded,
  not queued, except reports filed in the last 12 months and a current fail (D-M04-71). A
  finding that no longer holds is withdrawn (Part 3 pattern); answered items are kept.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from engine.financials import gate, gate_text, models, queue
from engine.financials.profile import full_scope
from engine.sec.client import iso
from engine.signals import Source, write_signal

MODULE = "M04"
SIGNALS = ("gc_language", "covenant_status")
KINDS = ("m04_gc_text", "m04_covenant")
EMPTY = {"going_concern": "none", "covenant": "silent"}


@dataclass
class CompanyText:
    ticker: str
    cik: str
    scan: gate_text.CompanyScan | None = None
    tg: gate_text.TextGate | None = None
    review_hypo: bool = False
    runway_why: str = ""
    gate_state: str = ""
    queued: dict[str, str] = field(default_factory=dict)  # kind:key → status
    held: list[str] = field(default_factory=list)  # kinds a tracked name would open
    withdrawn: int = 0
    signals: dict[str, str] = field(default_factory=dict)  # signal → value_text or missing
    error: str = ""


@dataclass
class TextPass:
    companies: dict[str, CompanyText]
    flushed: int = 0
    alerts: list[str] = field(default_factory=list)


def sentence_key(rows: list[sqlite3.Row] | list[dict]) -> str:
    """12 hex characters over the group's distinct quotes, sorted: the same sentences in a
    later report give the same key (one item per company and sentence text)."""
    text = "\n".join(sorted({r["quote"] for r in rows}))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def text_alert_keys(engine: sqlite3.Connection, cik: str) -> set[str]:
    """Text alerts' keys (`<cik>:text:<sentence key>`): Part 4a's withdrawal leaves them."""
    prefix = "m04_gate_fail:"
    return {
        r[0][len(prefix) :]
        for r in engine.execute(
            "SELECT prop_key FROM m04_proposal WHERE kind = 'm04_gate_fail' AND cik = ? "
            "AND prop_key LIKE ?",
            (cik, f"{prefix}{cik}:text:%"),
        )
    }


# --- Signals ---------------------------------------------------------------------------------


def _best(rows: list[sqlite3.Row]) -> sqlite3.Row | None:
    return max(
        rows,
        key=lambda r: (gate_text.SEVERITY[gate_text.effective(r)], r["filed"], -r["start_offset"]),
        default=None,
    )


def write_signals(engine: sqlite3.Connection, ct: CompanyText, today: str) -> int:
    """`gc_language` and `covenant_status`. Caller owns the transaction."""
    n = 0
    tg = ct.tg
    cur = tg.current if tg else None
    common = dict(engine=engine, cik=ct.cik, ticker=ct.ticker, module_id=MODULE)
    for family, sig in gate_text.SIGNAL_OF_FAMILY.items():
        if cur is None or not cur.accessions:
            why = "no stored periodic text"
            if ct.scan and ct.scan.no_text:
                why += f" ({len(ct.scan.no_text)} periodic filing(s) without stored text)"
            n += write_signal(**common, signal=sig, as_of=today, method="D-M04-34", missing=why)
            ct.signals[sig] = f"missing: {why}"
            continue
        rep = cur.report or {}
        rep_text = (
            f"current report {rep.get('form')} {rep.get('accession')} filed {rep.get('filed')}"
            if rep
            else "current report: 6-Ks of the last 400 days"
        ) + (f"; {cur.note}" if cur.note else "")
        rows = [r for r in tg.rows if r["family"] == family]
        best = _best(rows)
        if best is None:
            acc = rep.get("accession") or sorted(cur.accessions)[-1]
            filed = rep.get("filed") or today
            n += write_signal(
                **common,
                signal=sig,
                as_of=filed,
                value_text=EMPTY[family],
                method=(
                    "no going-concern sentence"
                    if family == "going_concern"
                    else "no covenant sentence (silent: not the same as compliant)"
                )
                + f"; {rep_text}; D-M04-34",
                sources=[Source(acc, filed, "A", f"{rep.get('form') or '6-K'} text")],
            )
            ct.signals[sig] = EMPTY[family]
            continue
        eff = gate_text.effective(best)
        value = "excluded" if eff == "excluded" else best["class"]
        others = sorted({r["class"] for r in rows if r is not best})
        method = (
            f"{gate_text.label(best['class'])}: “{best['quote']}” ({best['form']} "
            f"{best['accession']}, period {best['period_end'] or '—'}, filed {best['filed']}); "
            f"effect {gate_text.effect_text(best, True, ct.review_hypo)}"
            + (f"; {best['note']}" if best["note"] else "")
            + (f"; other classes in the report: {', '.join(others)}" if others else "")
            + f"; {rep_text}; D-M04-34"
        )
        n += write_signal(
            **common,
            signal=sig,
            as_of=best["filed"],
            value_text=value,
            method=method,
            sources=[Source(best["accession"], best["filed"], "A", f"{best['form']} text")],
        )
        ct.signals[sig] = value
    return n


# --- Review items ------------------------------------------------------------------------------


def _payload(ct: CompanyText, r: sqlite3.Row, is_current: bool, classes: list[str]) -> dict:
    return {
        "ticker": ct.ticker,
        "gate_text": True,
        "class": r["class"],
        "classes": classes,
        "class_label": gate_text.label(r["class"]),
        "family": r["family"],
        "effect": gate_text.effective(r),
        "quote": r["quote"],
        "note": r["note"],
        "accession": r["accession"],
        "filename": r["filename"],
        "offsets": [r["start_offset"], r["end_offset"]],
        "doc": f"{r['accession']}/{r['filename']}",
        "passage_id": r["passage_id"],
        "form": r["form"],
        "filed": r["filed"],
        "period_end": r["period_end"],
        "current": is_current,
        "runway": ct.runway_why,
    }


def propose_items(
    engine: sqlite3.Connection, ct: CompanyText, now: datetime, *, queue_items: bool = True
) -> None:
    """The text items. Caller owns the transaction."""
    cik, who = ct.cik, ct.ticker or ct.cik
    cur = ct.tg.current.accessions if ct.tg and ct.tg.current else set()
    first = bool(ct.scan and ct.scan.first)
    # Only the current report opens items (live check 1, D-M04-96/-97): history rows are
    # shown, never queued. Answered rows (and sentences carrying an answer) open nothing.
    by_report: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
    for r in gate_text.rows_for(engine, cik):
        if r["accession"] not in cur or r["owner_outcome"] is not None:
            continue
        eff = gate_text.effective(r)
        if eff == "fail":
            g = ("m04_gate_fail", r["accession"], "text")
        elif eff == "warn":
            g = (gate_text.KIND_OF_FAMILY[r["family"]], r["accession"], r["class"])
        elif eff == "hypothetical" and ct.review_hypo:
            g = ("m04_gc_text", r["accession"], "hypothetical")
        else:
            continue
        by_report.setdefault(g, []).append(r)
    # One item per company and sentence text, not per filing: the key hashes the quotes,
    # so a later report repeating the same sentences is the same finding (live check 1)
    groups: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for (kind, _, part), rows in by_report.items():
        groups.setdefault((kind, f"{cik}:{part}:{sentence_key(rows)}"), []).extend(rows)
    live: dict[str, set[str]] = {
        "m04_gate_fail": set(),
        "m04_gc_text": set(),
        "m04_covenant": set(),
    }
    for (kind, key), rows in groups.items():
        live[kind].add(key)
        if not queue_items:
            ct.held.append(f"{kind} ({rows[0]['class']})")
            continue
        r = rows[0]
        classes = sorted({x["class"] for x in rows})
        where = f"{r['form']} filed {r['filed']} (period {r['period_end'] or '—'})"
        if kind == "m04_gate_fail":
            reason = (
                f"{who}: fail-class text — {', '.join(gate_text.label(c) for c in classes)} in "
                f"{where}; the gate fails on it while the report is current (D-M04-34)"
            )
        elif r["class"] == "hypothetical":
            reason = (
                f"{who}: hypothetical going-concern wording in {where} with {ct.runway_why} "
                f"(reviewed below {gate_text.HYPO_RUNWAY_Q:g} quarters, D-M04-34)"
            )
        else:
            reason = (
                f"{who}: {gate_text.label(r['class'])} in {where} — the gate warns while the "
                "report is current (D-M04-34)"
            )
        status = queue.propose(
            engine,
            kind,
            key,
            reason,
            _payload(ct, r, True, classes),
            now,
            cik=cik,
            baseline=first,  # the first scan: recorded unless recent or a current fail
            filed=r["filed"],
            current_fail=kind == "m04_gate_fail",
        )
        ct.queued[f"{kind}:{key}"] = status
        item = engine.execute(
            "SELECT item_id FROM m04_proposal WHERE prop_key = ?", (f"{kind}:{key}",)
        ).fetchone()
        if item is not None and item["item_id"]:
            engine.executemany(
                "UPDATE gate_text SET item_id = ? WHERE accession = ? AND filename = ? AND "
                "start_offset = ? AND item_id IS NULL",
                [(item["item_id"], x["accession"], x["filename"], x["start_offset"]) for x in rows],
            )
    if not queue_items:
        return
    why = "finding no longer holds (Part 4b recompute)"
    for kind in KINDS:
        ct.withdrawn += queue.withdraw_stale(engine, kind, cik, live[kind], now, why)
    for key in text_alert_keys(engine, cik) - live["m04_gate_fail"]:
        ct.withdrawn += int(queue.withdraw(engine, "m04_gate_fail", key, now, why))


# --- The pass ----------------------------------------------------------------------------------


def company_text(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    ticker: str,
    cik: str,
    now: datetime,
    *,
    mf: models.ModelFile | None = None,
    queue_items: bool = True,
) -> CompanyText:
    today = now.date().isoformat()
    mf = mf if mf is not None else models.load_safe()
    ct = CompanyText(ticker, cik)
    ct.scan = gate_text.scan_company(engine, corpus, cik, ticker, now, mf=mf)
    g = gate.evaluate(engine, cik, ticker, today, models=mf, today=today)
    ct.gate_state = g.state
    ct.review_hypo, ct.runway_why = gate_text.runway_reviews(g.runway, g.tier, g.scope)
    ct.tg = gate_text.gate_lines(engine, cik, today)
    engine.execute("BEGIN")
    try:
        write_signals(engine, ct, today)
        propose_items(engine, ct, now, queue_items=queue_items)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return ct


def text_pass(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    mf: models.ModelFile | None = None,
) -> TextPass:
    """Part 4b-lite for every covered company (0 requests); one company's error does not
    stop the others."""
    start = iso(now)
    mf = mf if mf is not None else models.load_safe()
    scope = set(full_scope(engine, companies).values())
    out: dict[str, CompanyText] = {}
    for ticker, cik in sorted(companies.items()):
        try:
            out[ticker] = company_text(
                engine, corpus, ticker, cik, now, mf=mf, queue_items=cik in scope
            )
        except Exception as e:
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            out[ticker] = CompanyText(ticker, cik, error=f"{type(e).__name__}: {e}")
    engine.execute("BEGIN")
    try:
        flushed = queue.flush_overflow(engine, now)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return TextPass(out, flushed, alert_lines(engine, start))


def alert_lines(engine: sqlite3.Connection, since: str) -> list[str]:
    """Text alerts (`m04_gate_fail`, key `…:text:…`) opened at or after `since`."""
    return [
        r["reason"]
        for r in engine.execute(
            "SELECT q.reason FROM review_queue q JOIN m04_proposal p ON p.item_id = q.item_id "
            "WHERE q.kind = 'm04_gate_fail' AND p.prop_key LIKE 'm04_gate_fail:%:text:%' "
            "AND q.created_at >= ? ORDER BY q.created_at, q.item_id",
            (since,),
        )
    ]


def class_counts(ct: CompanyText) -> dict[str, int]:
    out: dict[str, int] = {}
    if ct.tg is None:
        return out
    for r in ct.tg.rows:
        out[r["class"]] = out.get(r["class"], 0) + 1
    return out


def local_lines(tp: TextPass) -> list[str]:
    scanned = sum(c.scan.docs_read for c in tp.companies.values() if c.scan)
    rows = sum(c.scan.rows_new for c in tp.companies.values() if c.scan)
    queued = sum(1 for c in tp.companies.values() for v in c.queued.values() if v == "queued")
    fails = [c.ticker for c in tp.companies.values() if c.tg and c.tg.fails]
    warns = [c.ticker for c in tp.companies.values() if c.tg and c.tg.warns and not c.tg.fails]
    lines = [
        f"Part 4b: {scanned} new document(s) scanned, {rows} text row(s) added; current-report "
        f"fail {len(fails)}{' (' + ', '.join(fails) + ')' if fails else ''}, warn {len(warns)}"
        f"{' (' + ', '.join(warns) + ')' if warns else ''}; {queued} item(s) queued; "
        f"{tp.flushed} overflow item(s) flushed"
    ]
    lines += [f"  {c.ticker}: error — {c.error}" for c in tp.companies.values() if c.error]
    if tp.alerts:
        lines.append("  M04 text alerts new this run (m04_gate_fail):")
        lines += [f"    {a}" for a in tp.alerts]
    return lines


def run_local_part(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    companies: dict[str, str],
    now: datetime,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    """The refresh hook (right before the Part 4a gate pass). Never fails."""
    t0 = clock()
    try:
        if corpus is None:
            lines = ["  Part 4b: no corpus connection: skipped"]
        else:
            lines = local_lines(text_pass(engine, corpus, companies, now))
    except Exception as e:
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        lines = [f"  Part 4b: error — {type(e).__name__}: {e}"]
    return [
        f"M04 gate text — local pass (Part 4b-lite, 0 SEC requests) ({clock() - t0:.1f} s):",
        *lines,
    ]


def open_items(engine: sqlite3.Connection) -> list[str]:
    """Open Part 4b items: "kind company (item N, opened <date>): reason"."""
    out = []
    for r in engine.execute(
        "SELECT q.item_id, q.kind, q.cik, q.reason, q.payload, q.created_at FROM review_queue q "
        "WHERE q.resolved_at IS NULL AND (q.kind IN ('m04_gc_text', 'm04_covenant') OR "
        "(q.kind = 'm04_gate_fail' AND q.payload LIKE '%\"gate_text\": true%')) "
        "ORDER BY q.kind, q.item_id"
    ):
        try:
            who = json.loads(r["payload"] or "{}").get("ticker") or r["cik"]
        except json.JSONDecodeError:
            who = r["cik"]
        out.append(
            f"{r['kind']} {who} (item {r['item_id']}, opened {r['created_at'][:10]}): {r['reason']}"
        )
    return out
