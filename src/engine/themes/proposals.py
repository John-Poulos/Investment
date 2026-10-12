"""M02 proposals in the review queue (D-M02-10, D-M02-11).

Every engine suggestion goes through `propose()`:
- one review item per proposal key (kind:key); a repeat while it is open, or after it
  was accepted, is suppressed;
- a rejected proposal returns only on material change (distinct filers doubled, or
  hard money-flow evidence appeared), carrying the earlier decision and note;
- at most 10 new M02 items per week (Monday–Sunday, UTC); the rest wait as overflow
  (listed on the Themes page) and enter the queue as room frees up, strongest first:
  evidence grade, then money flow, then breadth growth (D-M02-51).
  Download reminders (`m02_ir_download`) are operational and not capped.

Generators live in their parts (money flow, call guidance, suppliers, seasonal pass,
news: one `m02_news` item per week, D-M02-58); this module is the shared plumbing.
Actions that change data are applied by `apply()`; the rest only close the item with
the owner's note.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from engine.sec.client import iso
from engine.themes import tiers

MODULE = "M02"
WEEKLY_CAP = 10
# operational items (downloads, tag mapping, reconciliation gaps) are not capped
UNCAPPED = frozenset(
    {
        "m02_ir_download",
        "m02_tag",
        "m02_capex_gap",
        "m02_13f_issuer",
        "m02_fin_check",
        "m02_ir_feed",
    }
)

KIND_LABELS = {
    "m02_theme": "M02: new theme proposed",
    "m02_phrase": "M02: new phrase for a theme",
    "m02_candidate": "M02: company proposed for the tracked tier",
    "m02_link": "M02: customer–supplier link to confirm",
    "m02_input": "M02: input category to confirm",
    "m02_ir_download": "M02: call document to download",
    "m02_promote": "M02: tracked company with new evidence",
    "m02_still_track": "M02: still track this company?",
    "m02_spender": "M02: does this company's spending count toward a theme?",
    "m02_tag": "M02: how does this cash-flow tag count?",
    "m02_capex_gap": "M02: capex recipe does not match the stated figure",
    "m02_finlink": "M02: financing or equity link to confirm",
    "m02_13f_issuer": "M02: 13F issuer to map",
    "m02_fin_check": "M02: financing record failed a check",
    "m02_fin_alert": "M02: financing alert (weekly digest)",
    "m02_news": "M02: news on accepted themes (weekly digest)",
    "m02_ir_feed": "M02: IR feed found for a company",
}
ACTIONS = {
    "m02_theme": ("accept", "reject"),
    "m02_phrase": ("accept", "reject"),
    "m02_candidate": ("accept", "reject"),
    "m02_link": ("confirm", "flip", "reject"),
    "m02_input": ("confirm", "reject"),
    "m02_ir_download": ("downloaded", "dismiss"),
    "m02_promote": ("promote", "keep_tracked"),
    "m02_still_track": ("keep", "remove"),
    "m02_spender": ("confirm", "reject"),
    "m02_tag": (
        "debt_raised",
        "debt_repaid",
        "equity_issued",
        "buybacks",
        "dividends",
        "other",
        "ignore",
    ),
    "m02_capex_gap": ("noted",),
    "m02_finlink": ("confirm", "flip", "reject"),
    "m02_13f_issuer": ("map", "dismiss"),
    "m02_fin_check": ("keep_record", "wrong_record"),
    "m02_fin_alert": ("noted",),
    "m02_news": ("noted",),  # leave open to come back to it (D-M02-58 (2))
    "m02_ir_feed": ("confirm", "reject"),  # D-M02-59
}
REJECTING = frozenset({"reject", "remove", "ignore"})


def week_start(now: datetime) -> datetime:
    day = now.astimezone(UTC).date() if now.tzinfo else now.date()
    monday = day - timedelta(days=day.weekday())
    return datetime(monday.year, monday.month, monday.day, tzinfo=UTC if now.tzinfo else None)


def queued_this_week(engine: sqlite3.Connection, now: datetime) -> int:
    marks = ",".join("?" * len(UNCAPPED))
    return engine.execute(
        f"SELECT count(*) FROM review_queue WHERE module_id = ? AND created_at >= ? "
        f"AND kind NOT IN ({marks})",
        (MODULE, iso(week_start(now)), *UNCAPPED),
    ).fetchone()[0]


def material_change(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """D-M02-10: distinct filers at least doubled, or hard money-flow evidence appeared."""
    o, n = old.get("companies"), new.get("companies")
    doubled = isinstance(o, int) and isinstance(n, int) and o > 0 and n >= 2 * o
    money = bool(new.get("money_flow")) and not old.get("money_flow")
    return doubled or money


def _enqueue(
    engine: sqlite3.Connection,
    kind: str,
    cik: str | None,
    reason: str,
    payload: dict[str, Any],
    now: datetime,
) -> int:
    return engine.execute(
        "INSERT INTO review_queue (module_id, kind, cik, reason, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (MODULE, kind, cik, reason, json.dumps(payload), iso(now)),
    ).lastrowid


def propose(
    engine: sqlite3.Connection,
    kind: str,
    key: str,
    reason: str,
    payload: dict[str, Any],
    now: datetime,
    *,
    cik: str | None = None,
) -> str:
    """Queue a proposal → 'queued' | 'overflow' | 'suppressed' | 'requeued'."""
    if kind not in KIND_LABELS:
        raise ValueError(f"unknown M02 kind {kind}")
    pk = f"{kind}:{key}"
    ts = iso(now)
    row = engine.execute("SELECT * FROM m02_proposal WHERE prop_key = ?", (pk,)).fetchone()
    outcome = "queued"
    if row is not None:
        if row["status"] == "overflow":
            engine.execute("UPDATE m02_proposal SET reason = ?, payload = ?, last_seen_at = ? "
                           "WHERE prop_key = ?", (reason, json.dumps(payload), ts, pk))  # fmt: skip
            return "overflow"
        item = engine.execute("SELECT resolved_at, resolution, note FROM review_queue "
                              "WHERE item_id = ?", (row["item_id"],)).fetchone()  # fmt: skip
        engine.execute("UPDATE m02_proposal SET last_seen_at = ? WHERE prop_key = ?", (ts, pk))
        if item is None or item["resolved_at"] is None:
            return "suppressed"
        old = json.loads(row["payload"] or "{}")
        if item["resolution"] not in REJECTING or not material_change(old, payload):
            return "suppressed"
        payload = payload | {"earlier": {"resolution": item["resolution"], "note": item["note"],
                                         "shown": old}}  # fmt: skip
        outcome = "requeued"
    capped = kind not in UNCAPPED and queued_this_week(engine, now) >= WEEKLY_CAP
    status = "overflow" if capped else "queued"
    item_id = None if capped else _enqueue(engine, kind, cik, reason, payload, now)
    engine.execute(
        "INSERT INTO m02_proposal (prop_key, kind, cik, reason, payload, status, item_id, "
        "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (prop_key) DO UPDATE SET reason = excluded.reason, payload = "
        "excluded.payload, status = excluded.status, item_id = excluded.item_id, "
        "last_seen_at = excluded.last_seen_at",
        (pk, kind, cik, reason, json.dumps(payload), status, item_id, ts, ts),
    )
    return "overflow" if capped else outcome


GRADE_RANK = {"A": 0, "B": 1, "C": 2}
KIND_GRADE = {"m02_input": "C"}  # Gemini-proposed input categories (rung L0)


def priority(kind: str, payload: dict[str, Any]) -> tuple[int, int, float]:
    """D-M02-10 order without a combined score (D-M02-51): evidence grade, then hard
    money flow present, then breadth growth (share change in points, larger first)."""
    grade = str(payload.get("grade") or KIND_GRADE.get(kind, "A"))[:1]
    growth = payload.get("growth_pts")
    return (GRADE_RANK.get(grade, 3), 0 if payload.get("money_flow") else 1,
            -float(growth) if isinstance(growth, int | float) else 0.0)  # fmt: skip


def flush_overflow(engine: sqlite3.Connection, now: datetime) -> int:
    """Move waiting proposals into the queue in priority order (grade → money flow →
    breadth growth; oldest first within a tie) while this week has room (D-M02-51)."""
    moved = 0
    rows = sorted(
        engine.execute(
            "SELECT * FROM m02_proposal WHERE status = 'overflow' ORDER BY first_seen_at, prop_key"
        ).fetchall(),
        key=lambda r: priority(r["kind"], json.loads(r["payload"] or "{}")),
    )  # stable sort keeps oldest-first within equal priority
    for r in rows:
        if queued_this_week(engine, now) >= WEEKLY_CAP:
            break
        item_id = _enqueue(engine, r["kind"], r["cik"], r["reason"],
                           json.loads(r["payload"] or "{}"), now)  # fmt: skip
        engine.execute("UPDATE m02_proposal SET status = 'queued', item_id = ? WHERE prop_key = ?",
                       (item_id, r["prop_key"]))  # fmt: skip
        moved += 1
    return moved


def overflow(engine: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(r) | {"label": KIND_LABELS.get(r["kind"], r["kind"])}
        for r in engine.execute(
            "SELECT prop_key, kind, cik, reason, first_seen_at FROM m02_proposal "
            "WHERE status = 'overflow' ORDER BY first_seen_at"
        )
    ]


def apply(
    engine: sqlite3.Connection,
    kind: str,
    action: str,
    payload: dict[str, Any],
    cik: str | None,
    by: str,
    now: datetime,
    core: set[str] = frozenset(),
    target: str = "",
) -> None:
    """Data changes behind an M02 action (the caller closes the item). `target`: the
    owner's input where an action takes one (13F issuer ticker/CIK, financing kind)."""
    if kind == "m02_candidate" and action == "accept":
        if not cik:
            raise tiers.TierError("This proposal names no company.")
        tiers.add_tracked(
            engine, cik, payload.get("ticker") or cik,
            reason=payload.get("why") or "accepted candidate",
            theme_key=payload.get("theme_key"), by=by, now=now, core=core,
        )  # fmt: skip
    elif kind == "m02_promote" and action == "promote" and cik:
        tiers.promote(engine, cik, by, now)
    elif kind == "m02_still_track" and cik:
        if action == "remove":
            tiers.remove(engine, cik, by, now)
        elif action == "keep":
            tiers.touch_evidence(engine, cik, now)
    elif kind in ("m02_theme", "m02_phrase") and action in ("accept", "reject"):
        status = "active" if action == "accept" else "rejected"
        if payload.get("phrase_id"):
            engine.execute("UPDATE theme_phrase SET status = ?, updated_at = ? WHERE phrase_id = ?",
                           (status, iso(now), payload["phrase_id"]))  # fmt: skip
        if kind == "m02_theme" and payload.get("theme_id"):
            engine.execute("UPDATE theme SET status = ?, updated_at = ? WHERE theme_id = ?",
                           (status, iso(now), payload["theme_id"]))  # fmt: skip
    elif kind == "m02_spender" and cik and payload.get("theme_id"):
        from engine.moneyflow.links import decide

        decide(engine, cik, int(payload["theme_id"]), action, None, now)
    elif kind == "m02_tag":
        from engine.moneyflow.allocation import map_tag

        map_tag(engine, payload, action, None, by, now)
    elif kind == "m02_link" and payload.get("pair"):
        from engine.supply.links import decide

        decide(engine, payload, action, by, now, core)
    elif kind == "m02_input" and cik and payload.get("category"):
        from engine.llm.supply_labels import decide_input

        decide_input(engine, cik, payload, action)
    elif kind == "m02_finlink" and payload.get("pair"):
        from engine.financing.links import decide as fin_decide

        fin_decide(engine, payload, action, now, target or None)
    elif kind == "m02_13f_issuer" and payload.get("cusip"):
        from engine.financing import issuers, thirteenf

        if action == "map" and not target.strip():
            raise tiers.TierError("Enter the ticker or CIK to map this issuer to.")
        try:
            issuers.owner_map(engine, payload["cusip"], target if action == "map" else None,
                              by, now)  # fmt: skip
        except ValueError as e:
            raise tiers.TierError(str(e)) from e
        thirteenf.re_resolve(engine, payload["cusip"][:6], now)
    elif kind == "m02_fin_check" and payload.get("holding_id"):
        if action == "wrong_record":
            from engine.financing.links import wrong_holding

            wrong_holding(engine, int(payload["holding_id"]), by, now)
        else:
            engine.execute("UPDATE fin_holding SET status = 'automatic' WHERE holding_id = ? "
                           "AND status = 'held'", (payload["holding_id"],))  # fmt: skip
    elif kind == "m02_ir_feed" and cik and payload.get("feed"):
        from engine.news.discover import decide as feed_decide

        feed_decide(engine, cik, payload["feed"], action, by, now)
    # m02_ir_download / m02_capex_gap / m02_fin_alert: the resolution itself is the
    # record; the parts that create them (5, 4, 3) read it.


def queue_still_track(engine: sqlite3.Connection, now: datetime) -> int:
    """'Still track?' for tracked names without new evidence for 12 months (D-M02-11)."""
    n = 0
    for m in tiers.stale_tracked(engine, now):
        key = f"{m.cik}:{m.last_evidence_at[:10]}"  # a new cycle after each 'keep'
        reason = (f"{m.ticker}: no new theme evidence since {m.last_evidence_at[:10]} "
                  f"(tracked since {m.added_at[:10]})")  # fmt: skip
        payload = {"ticker": m.ticker, "theme_key": m.theme_key, "since": m.last_evidence_at}
        if propose(engine, "m02_still_track", key, reason, payload, now, cik=m.cik) != "suppressed":
            n += 1
    return n


def suggest_promotion(
    engine: sqlite3.Connection, cik: str, evidence: str, kind_of_evidence: str, now: datetime
) -> str:
    """Called by later parts when a tracked name gains hard evidence (D-M02-11)."""
    m = tiers.member(engine, cik)
    if m is None or m.tier != "tracked":
        return "suppressed"
    tiers.touch_evidence(engine, cik, now)
    payload = {"ticker": m.ticker, "evidence": evidence, "type": kind_of_evidence}
    return propose(engine, "m02_promote", f"{cik}:{kind_of_evidence}",
                   f"{m.ticker}: {evidence}", payload, now, cik=cik)  # fmt: skip
