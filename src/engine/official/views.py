"""Official feeds for the UI (D-M02-13, D-M02-60): theme page sections and the company
page's federal awards (Money flow tab).

Labels follow D-M02-15: arXiv = research momentum, never money flow; bills "introduced"
unless enacted; USAspending amounts are obligations (not cash paid), DoD 90-day delay,
recipients mapped to the parent only on exact name or parent matches.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from engine.official.arxiv import months_due

AWARD_NOTE = (
    "Amounts are obligations — the government's commitment, not cash paid — as the "
    "award's total obligated to date; new awards only (first obligation in the window). "
    "Department of Defense awards appear with a 90-day delay. Recipients count for a "
    "company only when the stated name or the recipient's USAspending parent equals one of "
    'its names (case, punctuation, "The" and legal suffix aside).'
)


def usd(x: float | None) -> str:
    if x is None:
        return "—"
    sign = "−" if x < 0 else ""
    x = abs(x)
    if x >= 1e9:
        return f"{sign}${x / 1e9:,.2f}B"
    if x >= 1e6:
        return f"{sign}${x / 1e6:,.1f}M"
    if x >= 1e3:
        return f"{sign}${x / 1e3:,.0f}K"
    return f"{sign}${x:,.0f}"


@dataclass
class ArxivTable:
    months: list[str]  # oldest → newest
    rows: list[dict[str, Any]]  # {phrase, cells: [n | None], last12, prior12}


def arxiv_table(engine: sqlite3.Connection, theme_id: int, today: date, n: int = 12) -> ArxivTable:
    all_months = months_due(today, 24)  # newest first
    months = list(reversed(all_months[:n]))
    phrases = [r["phrase"].strip().strip('"') for r in engine.execute(
        "SELECT phrase FROM theme_phrase WHERE theme_id = ? AND status = 'active' "
        "ORDER BY phrase_id", (theme_id,))]  # fmt: skip
    rows = []
    for p in phrases:
        got = {r["month"]: r["n"] for r in engine.execute(
            "SELECT month, n FROM arxiv_count WHERE phrase = ?", (p.lower(),))}  # fmt: skip
        last = [got.get(m) for m in all_months[:12]]
        prior = [got.get(m) for m in all_months[12:24]]
        rows.append({
            "phrase": p,
            "cells": [got.get(m) for m in months],
            "last12": sum(last) if all(v is not None for v in last) else None,
            "prior12": sum(prior) if all(v is not None for v in prior) else None,
        })  # fmt: skip
    return ArxivTable(months, rows)


@dataclass
class ThemeOfficial:
    arxiv: ArxivTable
    fedreg: list[dict[str, Any]] = field(default_factory=list)
    bills: list[dict[str, Any]] = field(default_factory=list)
    awards: list[dict[str, Any]] = field(default_factory=list)  # per linked company
    days: int = 365


def theme_view(engine: sqlite3.Connection, theme_id: int, today: date,
               days: int = 365) -> ThemeOfficial:  # fmt: skip
    since = (today - timedelta(days=days)).isoformat()
    fed = [dict(r) for r in engine.execute(
        "SELECT d.*, o.phrase FROM fedreg_doc d JOIN official_theme o "
        "ON o.source = 'fedreg' AND o.ref = d.document_number "
        "WHERE o.theme_id = ? AND d.publication_date >= ? "
        "ORDER BY d.publication_date DESC LIMIT 40", (theme_id, since))]  # fmt: skip
    bills = [dict(r) for r in engine.execute(
        "SELECT b.*, o.phrase FROM congress_bill b JOIN official_theme o "
        "ON o.source = 'congress' AND o.ref = b.bill_id WHERE o.theme_id = ? "
        "ORDER BY b.status = 'enacted' DESC, coalesce(b.latest_action_date, b.first_seen_at) "
        "DESC LIMIT 40", (theme_id,))]  # fmt: skip
    awards = []
    for r in engine.execute(
        "SELECT tc.ticker, t.cik FROM theme_company tc LEFT JOIN ticker t "
        "ON t.ticker = tc.ticker AND t.valid_to IS NULL "
        "WHERE tc.theme_id = ? AND tc.status = 'active' ORDER BY tc.rowid", (theme_id,)
    ):  # fmt: skip
        if not r["cik"]:
            continue
        s = engine.execute(
            "SELECT count(*) n, sum(a.amount) total, count(a.amount) priced, max(a.base_date) "
            "latest FROM usa_award a JOIN usa_recipient p USING (recipient_id) "
            "WHERE p.cik = ? AND a.base_date >= ?", (r["cik"], since)
        ).fetchone()  # fmt: skip
        checked = engine.execute("SELECT fetched_at FROM refresh_state WHERE name = ?",
                                 (f"official:usaspending:{r['cik']}",)).fetchone()  # fmt: skip
        awards.append({"ticker": r["ticker"], "n": s["n"],
                       "total": s["total"] if s["priced"] else None, "latest": s["latest"],
                       "checked": checked[0][:10] if checked else None})  # fmt: skip
    return ThemeOfficial(arxiv_table(engine, theme_id, today), fed, bills, awards, days)


@dataclass
class CompanyAwards:
    checked: str | None
    detail: str | None
    mapped: list[dict[str, Any]]
    unmapped: list[dict[str, Any]]  # found by this company's search, recipient not mapped
    total_365: float | None


def company_awards(engine: sqlite3.Connection, cik: str, today: date) -> CompanyAwards:
    st = engine.execute("SELECT fetched_at, detail FROM refresh_state WHERE name = ?",
                        (f"official:usaspending:{cik}",)).fetchone()  # fmt: skip
    mapped = [dict(r) for r in engine.execute(
        "SELECT a.*, p.how, p.parent_name FROM usa_award a JOIN usa_recipient p "
        "USING (recipient_id) WHERE p.cik = ? "
        "ORDER BY coalesce(a.base_date, a.first_seen_at) DESC LIMIT 60", (cik,))]  # fmt: skip
    unmapped = [dict(r) for r in engine.execute(
        "SELECT a.*, p.how, p.parent_name, p.profile_at FROM usa_award a "
        "LEFT JOIN usa_recipient p USING (recipient_id) "
        "WHERE a.searched_cik = ? AND (p.cik IS NULL OR p.cik != ?) "
        "ORDER BY a.amount DESC LIMIT 30", (cik, cik))]  # fmt: skip
    since = (today - timedelta(days=365)).isoformat()
    s = engine.execute(
        "SELECT sum(a.amount) total, count(a.amount) priced FROM usa_award a "
        "JOIN usa_recipient p USING (recipient_id) WHERE p.cik = ? AND a.base_date >= ?",
        (cik, since),
    ).fetchone()
    total = s["total"] if s["priced"] else None
    return CompanyAwards(st[0][:10] if st else None, st[1] if st else None, mapped, unmapped,
                         total)  # fmt: skip
