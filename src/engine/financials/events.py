"""M04 filing events: 8-K triggers, their classes, states and clearing (M04 Part 3).

Read from the stored `event` table (8-K items, `sec/events.py`) and `filing` table (NT
10-K/10-Q/20-F), the 8-K text where a class needs it (D-M04-37, -15; S1.11; L8):

| Item | Class | State | Review | Clears |
|---|---|---|---|---|
| 1.03 | bankruptcy | fail | yes | never by itself: owner resolution |
| 2.04 | acceleration | fail | yes | a later periodic filing and owner resolution |
| 3.01 | delisting / missed cure | fail | yes | owner resolution |
| 3.01 | deficiency (cure period) | warn | yes | a later 8-K stating regained compliance, or owner |
| 3.01 | transfer (listing moved) | info | no | — |
| 3.01 | regained compliance | info | no | clears an earlier deficiency |
| 3.01 | unread (text not stored) | warn | yes | owner resolution |
| 4.01 | auditor change | info | no | — |
| 4.01 | post-de-SPAC change, no disagreements (≤ ~90 days of the closing) | info | no | — |
| 4.01 | escalated (a restatement within 12 months) | warn | yes | owner resolution |
| 4.02 | non-reliance | warn | yes | the restated filing (10-K/A, 10-Q/A or the next 10-K) |
| 2.06 | impairment | info | yes | — |
| 1.02 | financing (co-filed with 2.03) / termination | info | no | — (read in Part 7b) |
| NT | late filing | warn | yes | the late periodic report |

`m04_event` stores each one with its state; the gate reads them in Part 4a. Every event
is an uncapped alert line on the M04 tab and in the end-of-run summary box (D-M04-77); only
the `m04_event` judgment item counts against the weekly cap (group 3, D-M04-71). The first
scan of a company is a baseline (queued only when filed in the last 12 months; a current
fail queues at priority 1).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from engine.financials import queue
from engine.financials.text import clean, docs_for, sentence_at
from engine.sec.client import iso
from engine.sec.identity import entity_links, normalize_cik

M04_ITEMS = ("1.02", "1.03", "2.04", "2.06", "3.01", "4.01", "4.02")
TEXT_ITEMS = ("1.03", "2.04", "3.01", "4.01", "4.02")  # classes read from the 8-K text
NT_FORMS = ("NT 10-K", "NT 10-Q", "NT 20-F", "NT 10-K/A", "NT 10-Q/A", "NT 20-F/A")
DESPAC_DAYS = 90  # S1.11 "within ~90 days of a de-SPAC close"
ESCALATE_DAYS = 365  # D-M04-15
WINDOW_YEARS = 3
BASELINE_STATE = "m04_events_baseline:{cik}"

TRANSFER = re.compile(
    r"transfer(?:ring|red)? (?:the |its |our )?(?:listing|common stock|"
    r"shares|securities)[^.]{0,160}(?:to|from) (?:the )?(?:New York Stock "
    r"Exchange|NYSE|Nasdaq|NASDAQ)|(?:intends?|decided|elected|plans?) to "
    r"(?:transfer|move) (?:the )?listing",
    re.I,
)
DELIST = re.compile(
    r"Form 25\b|determined to (?:delist|commence proceedings to delist)|"
    r"suspend(?:ed)? trading|will be delisted|delisting (?:of|from)|"
    r"to delist the",
    re.I,
)
MISSED_CURE = re.compile(
    r"(?:did not|has not|failed to|not) regain(?:ed)? compliance|"
    r"no longer eligible for (?:an additional|a) (?:compliance|cure) period",
    re.I,
)
REGAINED = re.compile(r"(?<!not )(?<!not yet )regained compliance", re.I)
DEFICIENCY = re.compile(
    r"not in compliance|no longer (?:in compliance|complies|meets)|"
    r"(?:compliance|cure) period|to regain compliance|deficiency|"
    r"below (?:the )?(?:\$1\.00|minimum)",
    re.I,
)
NO_DISAGREE = re.compile(
    r"(?:were|was|have been) no (?:\"?disagreements|reportable events)|"
    r"no disagreements",
    re.I,
)
DISAGREE = re.compile(r"\bthere (?:were|was) (?:a )?disagreements?\b(?! with)", re.I)


@dataclass
class EventRow:
    accession: str
    item: str
    cik: str
    form: str
    filed: str
    klass: str
    base_state: str
    state: str
    review: bool
    clears_when: str
    note: str
    quote: str = ""
    doc_ref: str = ""
    cleared_at: str | None = None
    cleared_by: str | None = None
    owner_resolution: str | None = None

    @property
    def key(self) -> str:
        return f"{self.accession}:{self.item}"

    @property
    def label(self) -> str:
        return "8-K " + self.item if not self.item.startswith("NT") else self.item


# --- Text --------------------------------------------------------------------------------------


def event_text(corpus: sqlite3.Connection | None, accession: str) -> tuple[str, str]:
    """(text, doc ref) of the 8-K body and its exhibits; ('', '') when not stored."""
    if corpus is None:
        return "", ""
    docs = docs_for(corpus, accession)
    if not docs:
        return "", ""
    main = next((d for d in docs if (d.doc_type or "").startswith("8-K")), docs[0])
    return "\n\n".join(d.text for d in docs), main.ref


def _quote(text: str, m: re.Match) -> str:
    a, b = sentence_at(text, m.start())
    return clean(text[a:b])


HYPOTHETICAL = re.compile(r"\b(?:if|may|could|would|might|unless|in the event)\b", re.I)


def _first_real(rx: re.Pattern, text: str, hypothetical_ok: bool = False) -> re.Match | None:
    """The first match whose sentence is not hypothetical ("if the Company does not regain
    compliance … will be delisted" is a deficiency notice, not a delisting)."""
    for m in rx.finditer(text):
        a, b = sentence_at(text, m.start())
        if hypothetical_ok or not HYPOTHETICAL.search(text[a:b]):
            return m
    return None


def classify_301(text: str) -> tuple[str, str, str]:
    """(class, state, quote) for an Item 3.01 from its text (S1.11). A listing transfer is
    checked first (a voluntary move files a Form 25 too)."""
    if not text:
        return "unread", "warn", ""
    for klass, state, rx in (
        ("transfer", "info", TRANSFER),
        ("regained", "info", REGAINED),
        ("missed_cure", "fail", MISSED_CURE),
        ("delisting", "fail", DELIST),
        ("deficiency", "warn", DEFICIENCY),
    ):
        if m := _first_real(rx, text, hypothetical_ok=klass in ("transfer", "deficiency")):
            return klass, state, _quote(text, m)
    return "unread", "warn", ""


# --- Classification ----------------------------------------------------------------------------


def _items_by_accession(engine: sqlite3.Connection, cik: str, since: str) -> dict[str, list]:
    out: dict[str, list] = {}
    for r in engine.execute(
        "SELECT accession, item, form, filed FROM event WHERE cik = ? AND filed >= ? "
        "ORDER BY filed, accession",
        (cik, since),
    ):
        out.setdefault(r["accession"], []).append(r)
    return out


def _later_periodic(
    engine: sqlite3.Connection, cik: str, after: str, forms: tuple[str, ...]
) -> sqlite3.Row | None:
    marks = ",".join("?" * len(forms))
    return engine.execute(
        f"SELECT f.accession, f.form, f.filed FROM filing f JOIN filing_cik c ON c.accession = "
        f"f.accession WHERE c.cik = ? AND f.form IN ({marks}) AND f.filed > ? "
        "ORDER BY f.filed LIMIT 1",
        (cik, *forms, after),
    ).fetchone()


def classify(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    cik: str,
    today: date,
    restatements: list[tuple[str, str]] = (),
) -> list[EventRow]:
    """M04 events of the last 3 years for one company, classified and with their state.
    `restatements` = (date, what) of restatements found (for the 4.01 escalation)."""
    norm = normalize_cik(cik) or cik
    since = (today - timedelta(days=365 * WINDOW_YEARS)).isoformat()
    shells = [lk.boundary_date for lk in entity_links(engine, norm) if lk.kind == "spac_shell"]
    out: list[EventRow] = []
    by_acc = _items_by_accession(engine, norm, since)
    deficiencies: list[EventRow] = []
    for acc, rows in by_acc.items():
        items = {r["item"] for r in rows}
        for r in rows:
            item = r["item"]
            if item not in M04_ITEMS:
                continue
            base = dict(accession=acc, item=item, cik=norm, form=r["form"], filed=r["filed"])
            text, ref = event_text(corpus, acc) if item in TEXT_ITEMS else ("", "")
            if item == "1.03":
                out.append(
                    EventRow(
                        **base,
                        klass="bankruptcy",
                        base_state="fail",
                        state="fail",
                        review=True,
                        clears_when="never by itself: your resolution",
                        note="gate fail (D-M04-37)",
                        doc_ref=ref,
                    )
                )
            elif item == "2.04":
                later = _later_periodic(engine, norm, r["filed"], ("10-Q", "10-K", "20-F", "10-KT"))
                note = "gate fail until a later periodic filing and your resolution (D-M04-37)"
                if later:
                    note += f"; later periodic filing: {later['form']} {later['filed']}"
                out.append(
                    EventRow(
                        **base,
                        klass="acceleration",
                        base_state="fail",
                        state="fail",
                        review=True,
                        clears_when="a later clean periodic filing and "
                        "your resolution (going-concern check: Part 4b)",
                        note=note,
                        doc_ref=ref,
                    )
                )
            elif item == "3.01":
                klass, state, quote = classify_301(text)
                note = {
                    "unread": "text not stored: class unknown, read the 8-K",
                    "transfer": "listing transfer: information (S1.11)",
                    "deficiency": "cure-period deficiency: warn + review (D-M04-37)",
                    "delisting": "delisting: gate fail (D-M04-37)",
                    "missed_cure": "missed cure: gate fail (D-M04-37)",
                    "regained": "regained compliance: clears an earlier deficiency",
                }[klass]
                clears = {
                    "deficiency": "a later 8-K stating regained compliance, or your resolution",
                    "transfer": "—",
                    "regained": "—",
                }.get(klass, "your resolution")
                ev = EventRow(
                    **base,
                    klass=klass,
                    base_state=state,
                    state=state,
                    review=state != "info",
                    clears_when=clears,
                    note=note,
                    quote=quote,
                    doc_ref=ref,
                )
                out.append(ev)
                if klass == "deficiency":
                    deficiencies.append(ev)
                if klass == "regained":
                    for d in deficiencies:
                        if d.state == "warn":
                            d.state, d.cleared_at, d.cleared_by = "cleared", r["filed"], acc
            elif item == "4.01":
                out.append(_auditor(base, text, ref, shells, restatements))
            elif item == "4.02":
                later = _later_periodic(
                    engine, norm, r["filed"], ("10-K/A", "10-Q/A", "10-K", "20-F/A", "20-F")
                )
                ev = EventRow(
                    **base,
                    klass="non_reliance",
                    base_state="warn",
                    state="warn",
                    review=True,
                    clears_when="the restated filing (10-K/A, 10-Q/A or the next 10-K)",
                    note="rows reading the affected periods are "
                    'marked "inputs under non-reliance" (D-M04-21)',
                    doc_ref=ref,
                )
                if later:
                    ev.state, ev.cleared_at, ev.cleared_by = (
                        "cleared",
                        later["filed"],
                        later["accession"],
                    )
                out.append(ev)
            elif item == "2.06":
                out.append(
                    EventRow(
                        **base,
                        klass="impairment",
                        base_state="info",
                        state="info",
                        review=True,
                        clears_when="—",
                        note="material impairment: your judgment (damage or cycle?)",
                    )
                )
            elif item == "1.02":
                fin = "2.03" in items
                out.append(
                    EventRow(
                        **base,
                        klass="financing" if fin else "termination",
                        base_state="info",
                        state="info",
                        review=False,
                        clears_when="—",
                        note=(
                            "co-filed with 2.03: financing, not customer (L8)"
                            if fin
                            else "agreement ended: read in Part 7b (customer row)"
                        ),
                    )
                )
    out += _late_filings(engine, norm, since)
    return sorted(out, key=lambda e: (e.filed, e.accession, e.item), reverse=True)


def _auditor(
    base: dict, text: str, ref: str, shells: list[str], restatements: list[tuple[str, str]]
) -> EventRow:
    filed = date.fromisoformat(base["filed"])
    near = [
        (d, w)
        for d, w in restatements
        if abs((date.fromisoformat(d[:10]) - filed).days) <= ESCALATE_DAYS
    ]
    after_close = [s for s in shells if 0 <= (filed - date.fromisoformat(s)).days <= DESPAC_DAYS]
    disagree = bool(text and DISAGREE.search(text) and not NO_DISAGREE.search(text))
    quote = ""
    if text and (m := NO_DISAGREE.search(text) or DISAGREE.search(text)):
        quote = _quote(text, m)
    if after_close and not disagree:
        note = (
            f"post-de-SPAC auditor change ({(filed - date.fromisoformat(after_close[0])).days}"
            f" days after the closing {after_close[0]}): information (S1.11)"
        )
        note += "; no disagreements stated" if quote else "; text not stored (wording unchecked)"
        if near:
            note += (
                f"; restatement within 12 months ({near[0][1]}) not escalated: a routine "
                "post-de-SPAC change (S1.11)"
            )
        return EventRow(
            **base,
            klass="despac_auditor",
            base_state="info",
            state="info",
            review=False,
            clears_when="—",
            note=note,
            quote=quote,
            doc_ref=ref,
        )
    if near or disagree:
        why = []
        if near:
            why.append(f"restatement within 12 months: {near[0][1]} ({near[0][0][:10]})")
        if disagree:
            why.append("disagreements stated")
        return EventRow(
            **base,
            klass="escalated",
            base_state="warn",
            state="warn",
            review=True,
            clears_when="your resolution",
            note="auditor change escalates (D-M04-15): " + "; ".join(why),
            quote=quote,
            doc_ref=ref,
        )
    return EventRow(
        **base,
        klass="auditor_change",
        base_state="info",
        state="info",
        review=False,
        clears_when="—",
        note="auditor change, no restatement within 12 months",
        quote=quote,
        doc_ref=ref,
    )


def _late_filings(engine: sqlite3.Connection, cik: str, since: str) -> list[EventRow]:
    out = []
    marks = ",".join("?" * len(NT_FORMS))
    for r in engine.execute(
        f"SELECT f.accession, f.form, f.filed FROM filing f JOIN filing_cik c ON c.accession = "
        f"f.accession WHERE c.cik = ? AND f.form IN ({marks}) AND f.filed >= ? ORDER BY f.filed",
        (cik, *NT_FORMS, since),
    ):
        target = r["form"].replace("NT ", "").replace("/A", "")
        later = _later_periodic(engine, cik, r["filed"], (target, f"{target}/A"))
        ev = EventRow(
            r["accession"],
            r["form"].replace("/A", ""),
            cik,
            r["form"],
            r["filed"],
            "late_filing",
            "warn",
            "warn",
            True,
            f"the late {target}",
            f"notification of late filing ({target})",
        )
        if later:
            ev.state, ev.cleared_at, ev.cleared_by = "cleared", later["filed"], later["accession"]
            ev.note += f"; filed {later['filed']}"
        out.append(ev)
    return out


# --- Storage, review, alerts ------------------------------------------------------------------


def store(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str | None,
    rows: list[EventRow],
    now: datetime,
    *,
    queue_items: bool = True,
) -> dict[str, int]:
    """Upsert (owner resolution kept and applied), queue `m04_event` items; the first scan of
    a company is a baseline (D-M04-71). Caller owns the transaction."""
    at = iso(now)
    norm = normalize_cik(cik) or cik
    first = (
        engine.execute(
            "SELECT 1 FROM refresh_state WHERE name = ?", (BASELINE_STATE.format(cik=norm),)
        ).fetchone()
        is None
    )
    counts = {"events": len(rows), "queued": 0, "overflow": 0, "baseline": 0, "suppressed": 0}
    for e in rows:
        prior = engine.execute(
            "SELECT owner_resolution, resolved_at FROM m04_event WHERE accession = ? AND item = ?",
            (e.accession, e.item),
        ).fetchone()
        if prior and prior["owner_resolution"]:
            e.owner_resolution = prior["owner_resolution"]
            if e.state in ("fail", "warn"):
                if e.klass == "acceleration" and "later periodic filing:" not in e.note:
                    e.note += "; your resolution recorded, awaiting a later periodic filing"
                else:
                    e.state, e.cleared_at, e.cleared_by = "resolved", prior["resolved_at"], "owner"
        engine.execute(
            "INSERT INTO m04_event (accession, item, cik, form, filed, class, base_state, state, "
            "review, clears_when, cleared_at, cleared_by, quote, doc_ref, note, first_seen_at, "
            "computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (accession, item) DO UPDATE SET class = excluded.class, "
            "base_state = excluded.base_state, state = excluded.state, review = excluded.review, "
            "clears_when = excluded.clears_when, cleared_at = excluded.cleared_at, "
            "cleared_by = excluded.cleared_by, quote = excluded.quote, doc_ref = excluded.doc_ref, "
            "note = excluded.note, computed_at = excluded.computed_at",
            (
                e.accession,
                e.item,
                norm,
                e.form,
                e.filed,
                e.klass,
                e.base_state,
                e.state,
                int(e.review),
                e.clears_when,
                e.cleared_at,
                e.cleared_by,
                e.quote or None,
                e.doc_ref or None,
                e.note,
                at,
                at,
            ),
        )
        if not (e.review and queue_items) or e.state in ("cleared", "resolved"):
            continue
        status = queue.propose(
            engine,
            "m04_event",
            e.key,
            f"{ticker or norm}: {e.label} {e.klass.replace('_', ' ')} ({e.state}) filed {e.filed}",
            event_payload(ticker, e),
            now,
            cik=norm,
            baseline=first,
            filed=e.filed,
            current_fail=e.state == "fail",
        )
        counts[status] = counts.get(status, 0) + 1
        item = engine.execute(
            "SELECT item_id FROM m04_proposal WHERE prop_key = ?", (f"m04_event:{e.key}",)
        ).fetchone()
        if item and item["item_id"]:
            engine.execute(
                "UPDATE m04_event SET item_id = ? WHERE accession = ? AND item = ?",
                (item["item_id"], e.accession, e.item),
            )
    if first:
        engine.execute(
            "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (name) DO NOTHING",
            (
                BASELINE_STATE.format(cik=norm),
                "events.classify",
                at,
                json.dumps({"events": len(rows)}),
            ),
        )
    return counts


def event_payload(ticker: str | None, e: EventRow) -> dict:
    return {
        "ticker": ticker,
        "accession": e.accession,
        "item": e.item,
        "form": e.form,
        "filed": e.filed,
        "class": e.klass,
        "state": e.state,
        "clears_when": e.clears_when,
        "note": e.note,
        "quote": e.quote,
        "doc_ref": e.doc_ref,
    }


def resolve(
    engine: sqlite3.Connection, accession: str, item: str, text: str, now: datetime
) -> None:
    """The owner's resolution of an event (review action). Caller owns the transaction."""
    engine.execute(
        "UPDATE m04_event SET owner_resolution = ?, resolved_at = ? WHERE accession = ? "
        "AND item = ?",
        (text, iso(now), accession, item),
    )
    row = engine.execute(
        "SELECT class, note FROM m04_event WHERE accession = ? AND item = ?", (accession, item)
    ).fetchone()
    if row and (row["class"] != "acceleration" or "later periodic filing:" in row["note"]):
        engine.execute(
            "UPDATE m04_event SET state = 'resolved', cleared_at = ?, cleared_by = "
            "'owner' WHERE accession = ? AND item = ? AND state IN ('fail', 'warn')",
            (iso(now), accession, item),
        )


def stored_events(engine: sqlite3.Connection, cik: str, since: str | None = None) -> list:
    return engine.execute(
        "SELECT * FROM m04_event WHERE cik = ? AND (? IS NULL OR filed >= ?) "
        "ORDER BY filed DESC, accession DESC, item",
        (normalize_cik(cik) or cik, since, since),
    ).fetchall()


def alert_lines(engine: sqlite3.Connection, since: str) -> list[str]:
    """Events first seen at or after `since` (D-M04-77: uncapped alert lines)."""
    out = []
    for r in engine.execute(
        "SELECT e.*, (SELECT ticker FROM ticker t WHERE t.cik = e.cik AND t.valid_to IS NULL "
        "ORDER BY valid_from DESC LIMIT 1) AS ticker FROM m04_event e WHERE e.first_seen_at >= ? "
        "ORDER BY e.filed DESC",
        (since,),
    ):
        what = r["item"] if r["item"].startswith("NT") else f"8-K {r['item']}"
        out.append(
            f"{r['ticker'] or r['cik']} {what} {r['class'].replace('_', ' ')} "
            f"({r['state']}) filed {r['filed']}"
        )
    return out


def gate_inputs(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    """Open fail and warn events (Part 4a's gate reads these, D-M04-37)."""
    return engine.execute(
        "SELECT * FROM m04_event WHERE cik = ? AND state IN ('fail', 'warn') ORDER BY filed DESC",
        (normalize_cik(cik) or cik,),
    ).fetchall()


def text_wanted(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, cik: str, since: str
) -> list[str]:
    """8-K accessions with a text-class item in the window whose text is not stored."""
    marks = ",".join("?" * len(TEXT_ITEMS))
    accs = [
        r[0]
        for r in engine.execute(
            f"SELECT DISTINCT accession FROM event WHERE cik = ? AND item IN ({marks}) "
            "AND filed >= ? ORDER BY filed DESC",
            (normalize_cik(cik) or cik, *TEXT_ITEMS, since),
        )
    ]
    from engine.financials.filings import stored_accessions

    have = stored_accessions(corpus, accs)
    return [a for a in accs if a not in have]
