"""Review queue actions (D8; M00_UI screen 3, D-UI-12).

Every action closes the item with who, when, the action and the owner's note
(U3). Nothing here calls SEC, Tiingo or Gemini.

- guidance_unparsed: enter the guidance by hand (stored as source 'owner' with the
  same sentence as its quote; survives re-scans) or dismiss.
- guidance_conflict: keep the stored value, keep the other one (re-parsed from the
  stored document), or dismiss.
- llm_rejected: acknowledge (rejected output never becomes fact).
- ticker_map_hold: approve (the next nightly run applies SEC's ticker files with
  force; approval valid 7 days) or keep the stored map.
- m02_*: M02 proposals (engine/themes/proposals.py); data changes in `m02_action`.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from engine.guidance.calls import anchor_of, management_turns
from engine.guidance.ledger import TAX_RATE_SANE, Release, _insert
from engine.guidance.parse import METRICS, parse_call, parse_release
from engine.guidance.sources import default_grade, origin_of
from engine.llm.verify import numbers, scaled_forms
from engine.sec.client import iso
from engine.sec.identity import APPROVAL_STATE
from engine.themes import proposals, tiers

KIND_LABELS = {
    "guidance_unparsed": "Guidance sentence not parsed",
    "guidance_conflict": "Guidance stated twice with different values",
    "llm_rejected": "Gemini output rejected by the verifier",
    "ticker_map_hold": "Ticker map update held",
    **proposals.KIND_LABELS,
}
ACTIONS = {
    "guidance_unparsed": ("enter", "dismiss"),
    "guidance_conflict": ("keep_stored", "keep_other", "dismiss"),
    "llm_rejected": ("acknowledge",),
    "ticker_map_hold": ("approve", "keep_map"),
    **proposals.ACTIONS,
}
METRIC_NAMES = tuple(dict.fromkeys(name for _, name in METRICS))
PERIOD = re.compile(r"^(?:FY\d{4}( Q[1-4]| remaining)?|CY\d{4})$")


class ReviewError(ValueError):
    """The action cannot be applied (already resolved, wrong kind, bad input)."""


@dataclass(frozen=True)
class ReviewItem:
    item_id: int
    module_id: str
    kind: str
    cik: str | None
    ticker: str | None
    reason: str
    payload: dict[str, Any]
    created_at: str
    resolved_at: str | None
    resolution: str | None
    resolved_by: str | None
    note: str | None

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)

    @property
    def actions(self) -> tuple[str, ...]:
        return ACTIONS.get(self.kind, ("dismiss",))

    @property
    def week(self) -> str:
        """Monday of the week an M02 item was queued (digest grouping, D-M02-10)."""
        if self.module_id != proposals.MODULE:
            return ""
        return proposals.week_start(datetime.fromisoformat(self.created_at)).date().isoformat()


def _item(engine: sqlite3.Connection, r: sqlite3.Row) -> ReviewItem:
    ticker = None
    if r["cik"]:
        t = engine.execute(
            "SELECT ticker FROM ticker WHERE cik = ? AND valid_to IS NULL ORDER BY valid_from "
            "DESC LIMIT 1",
            (r["cik"],),
        ).fetchone()
        ticker = t[0] if t else None
    return ReviewItem(
        r["item_id"], r["module_id"], r["kind"], r["cik"], ticker, r["reason"],
        json.loads(r["payload"]) if r["payload"] else {}, r["created_at"], r["resolved_at"],
        r["resolution"], r["resolved_by"], r["note"],
    )  # fmt: skip


def items(
    engine: sqlite3.Connection,
    *,
    open_only: bool = True,
    kind: str | None = None,
    cik: str | None = None,
    limit: int = 500,
) -> list[ReviewItem]:
    where, params = [], []
    if open_only:
        where.append("resolved_at IS NULL")
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if cik:
        where.append("cik = ?")
        params.append(cik)
    sql = "SELECT * FROM review_queue"
    if where:
        sql += " WHERE " + " AND ".join(where)
    order = "created_at DESC, item_id DESC" if open_only else "resolved_at DESC, item_id DESC"
    rows = engine.execute(f"{sql} ORDER BY {order} LIMIT ?", (*params, limit)).fetchall()
    return [_item(engine, r) for r in rows]


def get(engine: sqlite3.Connection, item_id: int) -> ReviewItem | None:
    r = engine.execute("SELECT * FROM review_queue WHERE item_id = ?", (item_id,)).fetchone()
    return _item(engine, r) if r else None


def counts(engine: sqlite3.Connection) -> dict[str, int]:
    return {
        r[0]: r[1]
        for r in engine.execute(
            "SELECT kind, count(*) FROM review_queue WHERE resolved_at IS NULL GROUP BY kind"
        )
    }


def _open(engine: sqlite3.Connection, item_id: int, kinds: tuple[str, ...] | None) -> ReviewItem:
    it = get(engine, item_id)
    if it is None:
        raise ReviewError(f"No review item {item_id}.")
    if it.resolved_at:
        raise ReviewError("This item is already resolved.")
    if kinds and it.kind not in kinds:
        raise ReviewError(f"That action does not apply to {it.label.lower()}.")
    return it


def _close(
    engine: sqlite3.Connection, item_id: int, resolution: str, note: str, by: str, now: datetime
) -> None:
    engine.execute(
        "UPDATE review_queue SET resolved_at = ?, resolution = ?, resolved_by = ?, note = ? "
        "WHERE item_id = ? AND resolved_at IS NULL",
        (iso(now), resolution, by, note.strip() or None, item_id),
    )


def resolve(
    engine: sqlite3.Connection, item_id: int, action: str, note: str, by: str, now: datetime
) -> None:
    """Close an item without changing data: dismiss, acknowledge, keep_stored, keep_map."""
    it = _open(engine, item_id, None)
    if action not in it.actions or action in ("enter", "keep_other", "approve"):
        raise ReviewError(f"'{action}' is not a closing action for {it.label.lower()}.")
    _close(engine, item_id, action, note, by, now)


def m02_action(
    engine: sqlite3.Connection,
    item_id: int,
    action: str,
    note: str,
    by: str,
    now: datetime,
    core: set[str] = frozenset(),
) -> None:
    """M02 proposal actions: apply the data change (tracked tier, theme status), then close."""
    it = _open(engine, item_id, tuple(proposals.ACTIONS))
    if action not in it.actions:
        raise ReviewError(f"'{action}' is not an action for {it.label.lower()}.")
    engine.execute("BEGIN")
    try:
        proposals.apply(engine, it.kind, action, it.payload, it.cik, by, now, core)
        _close(engine, item_id, action, note, by, now)
        engine.execute("COMMIT")
    except tiers.TierError as e:
        engine.execute("ROLLBACK")
        raise ReviewError(str(e)) from e
    except Exception:
        engine.execute("ROLLBACK")
        raise


# --- guidance_unparsed: owner entry ------------------------------------------------------


@dataclass(frozen=True)
class ManualGuidance:
    metric: str
    basis: str
    period: str
    unit: str  # USD | % | count
    low: str
    high: str = ""  # empty = same as low
    scale: str = "1"  # 1 | 1e6 | 1e9 (USD and count)


def _dec(s: str, what: str) -> Decimal:
    try:
        return Decimal(s.replace(",", "").replace("$", "").strip())
    except InvalidOperation as e:
        raise ReviewError(f"{what} is not a number: {s!r}") from e


def enter_guidance(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    item_id: int,
    g: ManualGuidance,
    note: str,
    by: str,
    now: datetime,
) -> list[str]:
    """Store owner-entered guidance for an unparsed sentence. Returns warnings
    (e.g. a number not found in the sentence); the entry is stored regardless."""
    it = _open(engine, item_id, ("guidance_unparsed",))
    if g.metric not in METRIC_NAMES:
        raise ReviewError(f"Unknown metric {g.metric!r}.")
    if g.basis not in ("GAAP", "non-GAAP", "unspecified"):
        raise ReviewError(f"Unknown basis {g.basis!r}.")
    period = " ".join(g.period.split())
    if not PERIOD.match(period):
        raise ReviewError("Period must look like FY2026, FY2026 Q3, FY2026 remaining or CY2026.")
    if g.unit not in ("USD", "%", "count"):
        raise ReviewError(f"Unknown unit {g.unit!r}.")
    scale = Decimal(1) if g.unit == "%" else _dec(g.scale, "Scale")
    low = _dec(g.low, "Low") * scale
    high = _dec(g.high or g.low, "High") * scale
    if low > high:
        raise ReviewError("Low is above high.")
    p = it.payload
    start, end = p["offsets"]
    doc = corpus.execute(
        "SELECT text, sha256 FROM document WHERE accession = ? AND filename = ?",
        (p["accession"], p["filename"]),
    ).fetchone()
    if doc is None:
        raise ReviewError("The source document is no longer stored.")
    quote = doc["text"][start:end]
    filed = engine.execute(
        "SELECT filed FROM guidance_scan WHERE accession = ? AND filename = ?",
        (p["accession"], p["filename"]),
    ).fetchone()
    in_quote = numbers(quote)
    warnings = [
        f"{v.normalize():f} does not appear in the sentence (in raw, millions or billions form)"
        for v in sorted({low, high})
        if not (scaled_forms([v]) & in_quote)
    ]
    flag = reason = None
    lo, hi = TAX_RATE_SANE
    if g.metric == "tax_rate" and (low < lo or high > hi):
        flag, reason = "not_meaningful", f"tax rate outside {lo}-{hi}% (owner entry)"
    try:
        engine.execute("BEGIN")
        engine.execute(
            "INSERT INTO guidance (cik, accession, filename, metric, basis, period, unit, kind, "
            "low, high, point, stated_on, source, quote, quote_start, quote_end, period_quote, "
            "period_start, period_end, doc_sha256, parser_version, created_at, flag, flag_reason, "
            "origin, grade) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'owner', ?, ?, ?, ?, ?, ?, ?, 'owner', ?, "
            "?, ?, ?, ?)",
            (
                it.cik,
                p["accession"],
                p["filename"],
                g.metric,
                g.basis,
                period,
                g.unit,
                "point" if low == high else "range",
                format(low, "f"),
                format(high, "f"),
                format(low, "f") if low == high else None,
                filed[0] if filed else iso(now)[:10],
                quote,
                start,
                end,
                quote,
                start,
                end,
                doc["sha256"],
                iso(now),
                flag,
                reason,
                origin_of(p["accession"]),
                default_grade(origin_of(p["accession"])),
            ),  # fmt: skip
        )
        _close(engine, item_id, "entered", note, by, now)
        engine.execute("COMMIT")
    except sqlite3.IntegrityError as e:
        engine.execute("ROLLBACK")
        raise ReviewError(
            f"{g.metric} {g.basis} {period} is already in the ledger for this release."
        ) from e
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return warnings


# --- guidance_conflict: keep the other value ---------------------------------------------


def _conflict_key(it: ReviewItem) -> tuple[str, str, str]:
    if "key" in it.payload:
        m, b, per = it.payload["key"]
        return m, b, per
    head = it.reason.split(":")[0].split()  # "<metric> <basis> <period ...>: two different values"
    return head[0], head[1], " ".join(head[2:])


def keep_other(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    item_id: int,
    note: str,
    by: str,
    now: datetime,
) -> None:
    it = _open(engine, item_id, ("guidance_conflict",))
    p = it.payload
    if p.get("cross"):
        raise ReviewError("The release value stands when a call differs (D-M02-20); dismiss "
                          "this item, or note why the call should win.")  # fmt: skip
    key = _conflict_key(it)
    doc = corpus.execute(
        "SELECT doc_id, text, sha256 FROM document WHERE accession = ? AND filename = ?",
        (p["accession"], p["filename"]),
    ).fetchone()
    if doc is None:
        raise ReviewError("The source document is no longer stored.")
    other_start = p["other_offsets"][0]
    if origin_of(p["accession"]) == "release":
        parsed = parse_release(doc["text"])
    else:
        cd = engine.execute("SELECT quarter FROM call_document WHERE accession = ? AND "
                            "filename = ?", (p["accession"], p["filename"])).fetchone()  # fmt: skip
        turns = management_turns(corpus, doc["doc_id"], doc["text"])
        parsed = parse_call(doc["text"], turns, anchor_of(cd["quarter"]) if cd else None)
    match = [
        i
        for i in parsed.items
        if i.quote_start == other_start and (i.metric, i.basis, i.period) == key
    ]
    if not match:
        raise ReviewError("The other value could not be found again in the stored document.")
    filed = engine.execute(
        "SELECT filed FROM guidance_scan WHERE accession = ? AND filename = ?",
        (p["accession"], p["filename"]),
    ).fetchone()
    release = Release(it.cik or "", p["accession"], p["filename"],
                      filed[0] if filed else "", doc["doc_id"])  # fmt: skip
    engine.execute("BEGIN")
    try:
        engine.execute(
            "DELETE FROM guidance WHERE accession = ? AND filename = ? AND metric = ? AND "
            "basis = ? AND period = ?",
            (p["accession"], p["filename"], *key),
        )
        _insert(engine, release, doc["text"], doc["sha256"], match[0], iso(now))
        _close(engine, item_id, "keep_other", note, by, now)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise


# --- ticker_map_hold ---------------------------------------------------------------------


def approve_ticker_hold(
    engine: sqlite3.Connection, item_id: int, note: str, by: str, now: datetime
) -> None:
    _open(engine, item_id, ("ticker_map_hold",))
    engine.execute("BEGIN")
    try:
        engine.execute(
            "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) "
            "VALUES (?, 'owner', ?, ?) ON CONFLICT (name) DO UPDATE SET "
            "fetched_at = excluded.fetched_at, detail = excluded.detail",
            (APPROVAL_STATE, iso(now), f"item {item_id}"),
        )
        _close(engine, item_id, "approved; applies at the next nightly run", note, by, now)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise


# --- undo ----------------------------------------------------------------------------


REOPENABLE = ("entered", "dismiss", "acknowledge", "keep_stored", "keep_map")


def reopen(engine: sqlite3.Connection, item_id: int, by: str, now: datetime) -> str:
    """Return a resolved item to the queue. An 'entered' item also loses the
    owner-entered guidance row it created (matched by release and sentence)."""
    it = get(engine, item_id)
    if it is None:
        raise ReviewError(f"No review item {item_id}.")
    if not it.resolved_at:
        raise ReviewError("This item is already open.")
    if it.resolution not in REOPENABLE:
        raise ReviewError(f"Items resolved with '{it.resolution}' cannot be reopened here.")
    removed = 0
    engine.execute("BEGIN")
    try:
        if it.resolution == "entered":
            p = it.payload
            removed = engine.execute(
                "DELETE FROM guidance WHERE source = 'owner' AND accession = ? AND filename = ? "
                "AND quote_start = ?",
                (p["accession"], p["filename"], p["offsets"][0]),
            ).rowcount
        engine.execute(
            "UPDATE review_queue SET resolved_at = NULL, resolution = NULL, resolved_by = NULL, "
            "note = coalesce(note, '') || ? WHERE item_id = ?",
            (f" [reopened by {by} {iso(now)[:16]}]", item_id),
        )
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return f"reopened; {removed} owner-entered row removed" if removed else "reopened"
