"""Financials tab, M04 sections (M00_UI D-UI-22; M04 Part 1a). Plain data for the template.

Sections below the existing quarterly and balance-sheet tables (owner's mock-up, option a):
Filing status, Share counts, Marker legend, and "M04 rows still to come" (one row per
later build part, each "missing: not built, Part n"; D10: never hidden).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date

from engine.financials.shares import ShareRow, share_rows
from engine.financials.status import stored_status
from engine.sec.identity import normalize_cik

LEGEND = (
    (
        "≈ broader tag: <what it adds>",
        "The value comes from a tag that includes more than the "
        "row's concept (e.g. capex on PaymentsToAcquireProductiveAssets includes software and "
        'intangibles); kept apart from M02\'s "≈, gap X%" recipe mark (D-M04-3).',
    ),
    (
        "≈ narrower tag / alias",
        "A tag that covers less (depreciation without amortization) or a "
        "per-company alias (GE, NVDA only; SB.18).",
    ),
    (
        "first filed / latest",
        "Hover a value: its tag, accession, and the dates it was first "
        "and last filed (a later filing may restate it).",
    ),
    (
        "implied",
        "Float shares = public float ÷ the close on the float date; not a reported "
        "count (D-M04-2; M07 owns R22).",
    ),
    (
        "split-adjusted ×n",
        "Share counts scaled by the splits in the price history after the "
        "count's date (split guard).",
    ),
    ("missing: <reason>", "No value, and why. Missing is never zero (D-M04-9)."),
)

STILL_TO_COME = (
    ("Capex split, ROIC, core trends, guidance record", "1b"),
    ("Life-cycle stage, model tag, peer shortlist", "1c"),
    ("Peer statistics and peer z", "2"),
    ("Restatements, 8-K filing events, ratings", "3"),
    ("Survival gate: runway, maturity wall, distress score", "4a"),
    ("Survival gate: going-concern and covenant text", "4b"),
    ("Dilution and financing pressure", "5"),
    ("Earnings quality: cash conversion, M-score, estimates", "6"),
    ("Unit and dimensional data", "7a"),
    ("Margin collapse (R12), unit economics, customers", "7b"),
    ("Cycle vs decline, health vote, overreaction gauge", "8a"),
)


@dataclass
class M04View:
    status: list[sqlite3.Row]
    record: sqlite3.Row | None
    days_to_due: int | None
    shares: list[ShareRow]
    legend: tuple[tuple[str, str], ...] = LEGEND
    todo: list[tuple[str, str]] = field(default_factory=list)


def company_view(engine: sqlite3.Connection, cik: str, today: date) -> M04View:
    norm = normalize_cik(cik) or cik
    rows = stored_status(engine, norm)
    unfiled = [r for r in rows if r["filed"] is None]
    record = unfiled[0] if unfiled else (rows[0] if rows else None)
    days = None
    if record is not None:
        days = (date.fromisoformat(record["due_date"]) - today).days
    return M04View(
        status=rows[:6],
        record=record,
        days_to_due=days,
        shares=share_rows(engine, norm),
        todo=[(what, f"missing: not built, Part {part}") for what, part in STILL_TO_COME],
    )
