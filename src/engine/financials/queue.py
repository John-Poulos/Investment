"""M04 proposals in the review queue (D-M04-71; M04_BUILD_LOG "Review order and cap").

The M02 pattern (`themes/proposals.py`, D-M02-18, -53), with M04's own cap and order;
M02's cap of 10 is unchanged and counts only M02 items:

- one review item per proposal key (kind:key); a repeat while it is open, or after it
  was resolved, is suppressed (a later part that wants a new item uses a new key, e.g.
  a new fiscal year);
- **weekly cap 5** per Monday–Sunday week (UTC)†, counted over M04 judgment items only;
  the rest wait as overflow and are flushed by priority group, oldest first within a tie:
  1 survival · 2 CvD review and stage changes · 3 filing events · 4 restatement ·
  5 dilution and overhang · 6 margin cause, customer, unit KPI · 7 estimate and M-score;
- uncapped: alerts (`m04_gate_fail`), operational items (`m04_credit_line`,
  `m04_gate_input`) and the **setup batch** (first stages and peer shortlists), which comes
  before Part 3;
- **baselines:** the first run of a history scan is recorded (status 'baseline') and
  shown, never queued, except items filed in the last 12 months (their own group) and a
  current gate fail or incomplete (priority 1);
- **recomputed findings** (events, ratings, restatement steps): an open item takes the new
  reason and payload; one that no longer holds is withdrawn (closed as `withdrawn` by
  "engine"; an answered item is kept).

Actions that change data are applied by `apply()` (review.m04_action closes the item).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from engine.sec.client import iso
from engine.themes.proposals import week_start

MODULE = "M04"
WEEKLY_CAP = 5  # starting value (S4.8)
BASELINE_RECENT_DAYS = 365

# D-M04-71 priority group per kind (0 = outside the cap: alert, operational or setup).
GROUP = {
    "m04_gate_fail": 1, "m04_runway": 1, "m04_gc_text": 1, "m04_covenant": 1,
    "m04_score_gap": 1,
    "m04_cvd": 2, "m04_stage": 2,
    "m04_event": 3, "m04_rating": 3,
    "m04_restate": 4,
    "m04_dilution": 5, "m04_overhang": 5, "m04_financing_doc": 5,
    "m04_margin_cause": 6, "m04_customer": 6, "m04_unit_kpi": 6,
    "m04_estimate": 7, "m04_mscore": 7,
    "m04_peer": 0, "m04_credit_line": 0, "m04_gate_input": 0,
}  # fmt: skip
UNCAPPED = frozenset({"m04_gate_fail", "m04_credit_line", "m04_gate_input", "m04_peer"})
# Findings recomputed on every pass: an open item takes the new reason and payload, and a
# finding that no longer holds is withdrawn (`withdraw_stale`).
RECOMPUTED = frozenset({"m04_event", "m04_rating", "m04_restate"})
GROUP_NAMES = {0: "setup / operational", 1: "survival", 2: "CvD review and stage changes",
               3: "filing events", 4: "restatement", 5: "dilution and overhang",
               6: "margin cause, customer, unit KPI", 7: "estimate and M-score"}  # fmt: skip

# Kinds built so far (Parts 1c, 3); later parts add theirs here.
KIND_LABELS = {
    "m04_stage": "M04: life-cycle stage to confirm",
    "m04_peer": "M04: peer shortlist to confirm",
    "m04_event": "M04: filing event (8-K item or late filing)",
    "m04_restate": "M04: restatement step not explained",
    "m04_rating": "M04: credit-rating action",
}
ACTIONS = {
    "m04_stage": ("confirm",),  # target = the stage chosen (default: the computed stage)
    "m04_peer": ("confirm",),  # keep = candidates kept; the rest are struck
    "m04_event": ("resolve", "noted"),  # resolve clears a fail/warn (D-M04-37)
    "m04_restate": ("explained", "error"),  # the owner's reading of the residual
    "m04_rating": ("noted",),
}


class QueueError(ValueError):
    """An M04 action cannot be applied (bad stage, nothing to confirm)."""


def queued_this_week(engine: sqlite3.Connection, now: datetime) -> int:
    return engine.execute(
        "SELECT count(*) FROM m04_proposal p JOIN review_queue r ON r.item_id = p.item_id "
        "WHERE p.capped = 1 AND r.created_at >= ?",
        (iso(week_start(now)),),
    ).fetchone()[0]


def _enqueue(engine, kind, cik, reason, payload, now) -> int:
    return engine.execute(
        "INSERT INTO review_queue (module_id, kind, cik, reason, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (MODULE, kind, cik, reason, json.dumps(payload), iso(now)),
    ).lastrowid


def is_recent(filed: str | None, now: datetime) -> bool:
    if not filed:
        return False
    return date.fromisoformat(filed[:10]) >= (now - timedelta(days=BASELINE_RECENT_DAYS)).date()


def propose(
    engine: sqlite3.Connection,
    kind: str,
    key: str,
    reason: str,
    payload: dict[str, Any],
    now: datetime,
    *,
    cik: str | None = None,
    setup: bool = False,
    baseline: bool = False,
    filed: str | None = None,
    current_fail: bool = False,
) -> str:
    """Queue an M04 proposal → 'queued' | 'overflow' | 'baseline' | 'suppressed'.

    `setup`: part of the setup batch (outside the cap). `baseline`: found by the first run
    of a history scan; it queues only when `filed` lies in the last 12 months or it is a
    current gate fail or incomplete (`current_fail`, then at priority 1)."""
    if kind not in GROUP:
        raise ValueError(f"unknown M04 kind {kind}")
    pk = f"{kind}:{key}"
    ts = iso(now)
    row = engine.execute("SELECT * FROM m04_proposal WHERE prop_key = ?", (pk,)).fetchone()
    if row is not None:
        engine.execute("UPDATE m04_proposal SET reason = ?, payload = ?, last_seen_at = ? "
                       "WHERE prop_key = ? AND status IN ('overflow', 'baseline')",
                       (reason, json.dumps(payload), ts, pk))  # fmt: skip
        if kind in RECOMPUTED and row["status"] == "queued" and row["item_id"]:
            # a recomputed finding refreshes its open item (quote, labels, class)
            cur = engine.execute("UPDATE review_queue SET reason = ?, payload = ? "
                                 "WHERE item_id = ? AND resolved_at IS NULL",
                                 (reason, json.dumps(payload), row["item_id"]))  # fmt: skip
            if cur.rowcount:
                engine.execute("UPDATE m04_proposal SET reason = ?, payload = ? WHERE prop_key = ?",
                               (reason, json.dumps(payload), pk))  # fmt: skip
        engine.execute("UPDATE m04_proposal SET last_seen_at = ? WHERE prop_key = ?", (ts, pk))
        return row["status"] if row["status"] in ("overflow", "baseline") else "suppressed"
    priority = 0 if setup else GROUP[kind]
    capped = int(not setup and kind not in UNCAPPED)
    status = "queued"
    if baseline:
        if current_fail:
            priority = 1
        elif not is_recent(filed, now):
            status = "baseline"
    if status == "queued" and capped and queued_this_week(engine, now) >= WEEKLY_CAP:
        status = "overflow"
    item_id = _enqueue(engine, kind, cik, reason, payload, now) if status == "queued" else None
    engine.execute(
        "INSERT INTO m04_proposal (prop_key, kind, cik, reason, payload, priority, capped, "
        "baseline, status, item_id, first_seen_at, last_seen_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (pk, kind, cik, reason, json.dumps(payload), priority, capped, int(baseline), status,
         item_id, ts, ts),
    )  # fmt: skip
    return status


def withdraw(engine: sqlite3.Connection, kind: str, key: str, now: datetime, why: str) -> bool:
    """Drop a proposal whose finding no longer holds after a recomputation (Part 3 live
    check 1): a waiting one (overflow, baseline) is deleted; a queued one whose item is
    still open is closed as `withdrawn` (by "engine", with `why`) and deleted. An item you
    already answered is kept. Caller owns the transaction."""
    pk = f"{kind}:{key}"
    row = engine.execute("SELECT * FROM m04_proposal WHERE prop_key = ?", (pk,)).fetchone()
    if row is None:
        return False
    if row["status"] == "queued" and row["item_id"]:
        cur = engine.execute(
            "UPDATE review_queue SET resolved_at = ?, resolution = 'withdrawn', "
            "resolved_by = 'engine', note = ? WHERE item_id = ? AND resolved_at IS NULL",
            (iso(now), why, row["item_id"]),
        )
        if not cur.rowcount:
            return False
    engine.execute("DELETE FROM m04_proposal WHERE prop_key = ?", (pk,))
    return True


def withdraw_stale(
    engine: sqlite3.Connection, kind: str, cik: str, live: set[str], now: datetime, why: str
) -> int:
    """Withdraw every proposal of `kind` for the company whose key is not in `live`."""
    n = 0
    prefix = f"{kind}:"
    for r in engine.execute(
        "SELECT prop_key FROM m04_proposal WHERE kind = ? AND cik = ?", (kind, cik)
    ).fetchall():
        key = r["prop_key"][len(prefix) :]
        if key not in live and withdraw(engine, kind, key, now, why):
            n += 1
    return n


def flush_overflow(engine: sqlite3.Connection, now: datetime) -> int:
    """Move waiting proposals into the queue by priority group (D-M04-71), oldest first
    within a group, while this week has room."""
    moved = 0
    rows = engine.execute(
        "SELECT * FROM m04_proposal WHERE status = 'overflow' "
        "ORDER BY priority, first_seen_at, prop_key"
    ).fetchall()
    for r in rows:
        if queued_this_week(engine, now) >= WEEKLY_CAP:
            break
        item_id = _enqueue(engine, r["kind"], r["cik"], r["reason"],
                           json.loads(r["payload"] or "{}"), now)  # fmt: skip
        engine.execute("UPDATE m04_proposal SET status = 'queued', item_id = ? WHERE prop_key = ?",
                       (item_id, r["prop_key"]))  # fmt: skip
        moved += 1
    return moved


def overflow(engine: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(r) | {"label": KIND_LABELS.get(r["kind"], r["kind"]),
                   "group": GROUP_NAMES.get(r["priority"], str(r["priority"]))}
        for r in engine.execute(
            "SELECT prop_key, kind, cik, reason, priority, first_seen_at FROM m04_proposal "
            "WHERE status = 'overflow' ORDER BY priority, first_seen_at"
        )
    ]  # fmt: skip


def baselines(engine: sqlite3.Connection) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT prop_key, kind, cik, reason, first_seen_at FROM m04_proposal "
        "WHERE status = 'baseline' ORDER BY kind, first_seen_at"
    ).fetchall()


def apply(
    engine: sqlite3.Connection,
    item_id: int,
    kind: str,
    action: str,
    payload: dict[str, Any],
    cik: str | None,
    by: str,
    now: datetime,
    *,
    target: str = "",
    keep: tuple[str, ...] | None = None,
    note: str = "",
) -> str:
    """Data changes behind an M04 action (the caller closes the item). Returns the
    resolution text stored on the item."""
    if kind == "m04_event":
        from engine.financials import events

        acc, item = payload.get("accession"), payload.get("item")
        if not acc or not item:
            raise QueueError("This item names no filing event.")
        if action == "resolve":
            events.resolve(engine, acc, item, note.strip() or f"resolved by {by}", now)
            return "resolve"
        return "noted (event state unchanged)"
    if kind == "m04_restate":
        acc = payload.get("accession")
        engine.execute(
            "UPDATE restate_step SET owner_outcome = ?, owner_at = ? WHERE item_id = ?",
            (action, iso(now), item_id),
        )
        if engine.execute("SELECT changes()").fetchone()[0] == 0 and acc:
            raise QueueError("The walk step behind this item is no longer stored.")
        return action
    if kind == "m04_rating" and action == "noted":
        return "noted"
    if kind == "m04_stage" and action == "confirm":
        from engine.financials import stage

        chosen = (target or payload.get("computed") or "").strip()
        if not chosen:
            raise QueueError("No stage holds for this company: choose one.")
        if chosen not in stage.STAGES:
            raise QueueError(f"Unknown stage {chosen!r}.")
        if not cik:
            raise QueueError("This item names no company.")
        stage.confirm(engine, cik, payload.get("period_end"), chosen, by, now, item_id)
        computed = payload.get("computed")
        how = "as computed" if chosen == computed else (
            f"override (computed {stage.STAGE_NAMES.get(computed, 'none') if computed else 'none'})"
        )  # fmt: skip
        return f"confirm {chosen} ({how})"
    if kind == "m04_peer" and action == "confirm":
        from engine.financials import peers

        if not cik:
            raise QueueError("This item names no company.")
        kept, struck, added = peers.confirm(engine, cik, keep or (), by, now)
        return f"confirm: {kept} peer(s) kept, {struck} struck, {added} added by the owner"
    raise QueueError(f"'{action}' is not an action for {kind}.")
