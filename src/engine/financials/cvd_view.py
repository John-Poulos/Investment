"""The M04 tab: Cycle vs Decline verdict, grid, health scores, market-share entry and the
watchlist summary (M04 Part 8a; D-UI-31; owner's mock-up 2026-10-13).

- `company_view`: the CvD grid for one company computed live as of today (as the
  Financials tab computes its rows), its open `m04_cvd` item, the owner's market-share
  entries and the all-companies table read from the last local pass
  (`cvd_step.stored_lines`).
- `add_share` / `withdraw_share` (owner only): "Add market share" writes `market_share`
  (grade B, or A for a share of an industry total stated in a filing; D-M04-68, -105);
  the caller recomputes the company's CvD rows.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime

from engine.financials import cvd, cvd_step, market_share
from engine.financials import models as models_mod
from engine.financials import stage as stage_mod
from engine.sec.identity import normalize_cik

READING = {
    "shared": "shared (cycle)",
    "company_specific": "company-specific",
    "intact": "intact",
    "weakening": "weakening",
    "neutral": "neutral",
    "missing": "—",
    "not_applicable": "not applicable",
}
QUESTIONS = {"Q1": "Q1 — Is the slump shared?", "Q2": "Q2 — Is the franchise intact?"}
LINKS = (  # (label, anchor on the Financials tab)
    ("Survival gate", "#gate"),
    ("Capex, core trends, peers and the guidance record", ""),
    ("Restatements, filing events and earnings quality", ""),
)


@dataclass
class Tab:
    ticker: str
    c: cvd.CvD
    q1: list[cvd.Row]
    q2: list[cvd.Row]
    stage_text: str
    items: list[tuple[int, str]]
    shares: list[sqlite3.Row]
    everyone: list[dict] = field(default_factory=list)
    today: str = ""

    @property
    def conf(self) -> str:
        return f"{self.c.confidence:.2f}" if self.c.confidence is not None else "—"


def _items(engine: sqlite3.Connection, cik: str) -> list[tuple[int, str]]:
    return [
        (r["item_id"], r["reason"])
        for r in engine.execute(
            "SELECT item_id, reason FROM review_queue WHERE kind = 'm04_cvd' AND cik = ? AND "
            "resolved_at IS NULL ORDER BY item_id",
            (cik,),
        )
    ]


def stage_text(engine: sqlite3.Connection, cik: str) -> str:
    row = stage_mod.confirmed(engine, cik)
    if row is None:
        return "stage unconfirmed (equity point missing, D-M04-65; confirm on M04 setup)"
    return f"{stage_mod.STAGE_NAMES.get(row['confirmed'], row['confirmed'])} (confirmed)"


def company_view(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str,
    today: date,
    companies: dict[str, str] | None = None,
) -> Tab:
    norm = normalize_cik(cik) or cik
    t = today.isoformat()
    ent = engine.execute("SELECT category FROM entity WHERE cik = ?", (norm,)).fetchone()
    c = cvd.evaluate(
        engine,
        norm,
        ticker,
        t,
        models=models_mod.load_safe(),
        live_category=ent["category"] if ent and ent["category"] else None,
    )
    return Tab(
        ticker,
        c,
        [r for r in c.rows if r.q == "Q1"],
        [r for r in c.rows if r.q == "Q2"],
        stage_text(engine, norm),
        _items(engine, norm),
        market_share.entries(engine, norm),
        cvd_step.stored_lines(engine, companies) if companies else [],
        t,
    )


def add_share(engine: sqlite3.Connection, cik: str, form: dict, by: str, now: datetime) -> int:
    engine.execute("BEGIN")
    try:
        sid = market_share.add(
            engine,
            cik,
            form.get("period_end", ""),
            form.get("share_pct", ""),
            form.get("market", ""),
            form.get("source", ""),
            by=by,
            now=now,
            market_size=form.get("market_size") or None,
            url=form.get("source_url", ""),
            filing_total=form.get("kind") == "industry_total",
            note=form.get("note", ""),
        )
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return sid


def withdraw_share(
    engine: sqlite3.Connection, cik: str, share_id: int, by: str, now: datetime
) -> bool:
    engine.execute("BEGIN")
    try:
        ok = market_share.withdraw(engine, share_id, cik, by, now)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return ok
