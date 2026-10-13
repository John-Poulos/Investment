"""Financials tab, M04 sections (M00_UI D-UI-22, D-UI-23; M04 Parts 1a–1b). Plain data for
the template.

A Profile block at the top (Part 1c: stage and flag set, model tag, peers confirmed).
Sections below the existing quarterly and balance-sheet tables (owner's mock-ups): Filing
status, Share counts (Part 1a); Capex, Core trends, Guidance record (Part 1b); Marker
legend; and "M04 rows still to come" (one row per later build part, each "missing: not
built, Part n"; D10: never hidden).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date

from engine.financials import capex as capex_mod
from engine.financials import models as models_mod
from engine.financials import profile as profile_mod
from engine.financials import trends as trends_mod
from engine.financials.shares import ShareRow, share_rows
from engine.financials.status import stored_status
from engine.guidance import record as record_mod
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
        "definition changed",
        "Total capex switches between the PP&E tag and the broader productive-assets tag "
        "inside the window: that year is shown but not scored (D-M04-3).",
    ),
    (
        "useful-life change?",
        "Depreciation fell ≥ 20%† while gross PP&E grew: the depreciation rung of the capex "
        "split may move with an accounting estimate, not with spending (S2.7; Intel 2023).",
    ),
    (
        "n/m",
        "Not meaningful: a growth rate on a base ≤ 0 or below 1% of revenue, or ROIC on "
        "invested capital ≤ 0 (S2.1, S6.5). Hover for the reason.",
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
    ("Peer statistics and peer z (core trends, capex peers)", "2"),
    ("Restatements, 8-K filing events, ratings", "3"),
    ("Survival gate: runway, maturity wall, distress score", "4a"),
    ("Survival gate: going-concern and covenant text", "4b"),
    ("Dilution and financing pressure", "5"),
    ("Earnings quality: cash conversion, M-score, estimates", "6"),
    ("Unit and dimensional data", "7a"),
    ("Margin collapse (R12), unit economics, customers", "7b"),
    ("Cycle vs decline, health vote, overreaction gauge", "8a"),
)


@dataclass(frozen=True)
class Cell:
    text: str
    title: str = ""
    muted: bool = False


@dataclass
class TableRow:
    label: str
    cells: list[Cell]
    note: str = ""
    sub: bool = False


@dataclass
class Table:
    labels: list[str]
    rows: list[TableRow]
    lines: list[str] = field(default_factory=list)


@dataclass
class GuidanceSection:
    headline: str
    repeated: bool
    scored: list[record_mod.Outcome]
    pending: list[record_mod.Outcome]
    removals: list[record_mod.Outcome]


@dataclass
class M04View:
    status: list[sqlite3.Row]
    record: sqlite3.Row | None
    days_to_due: int | None
    shares: list[ShareRow]
    capex: Table | None = None
    trends: Table | None = None
    signals: list[tuple[str, str, str]] = field(default_factory=list)  # name, value, method
    guidance: GuidanceSection | None = None
    legend: tuple[tuple[str, str], ...] = LEGEND
    todo: list[tuple[str, str]] = field(default_factory=list)
    profile: profile_mod.Profile | None = None


def m(x: float | None) -> str:
    """$M with commas; missing stays a dash."""
    if x is None:
        return "—"
    return f"{x / 1e6:,.0f}".replace("-", "−")


def pct(x: float | None, scale: float = 100) -> str:
    return "—" if x is None else f"{x * scale:+.1f}%".replace("-", "−")


def _missing(reason: str) -> Cell:
    if reason.startswith(trends_mod.NM):
        return Cell("n/m", reason, True)
    return Cell("—", reason or "missing", True)


def capex_table(v: capex_mod.CapexView) -> Table:
    labels = [y.label for y in v.years]

    def row(label: str, fn, note: str = "", sub: bool = False) -> TableRow:
        return TableRow(label, [fn(y) for y in v.years], note, sub)

    def display(y: capex_mod.CapexYear) -> Cell:
        if y.display is None:
            return Cell("—", "missing: no company-definition value (M02 recipe or statement)", True)
        return Cell(m(y.display.shown), y.display_label)

    def total(y: capex_mod.CapexYear) -> Cell:
        t = y.total
        if t is None:
            return Cell("—", "missing: no capex tag this year", True)
        mark = " ≈" if t.mark else ""
        title = f"{t.tag}{f' [{t.mark}]' if t.mark else ''} · {t.accession} · filed {t.filed}"
        return Cell(m(t.value) + mark + (" ‡" if t.definition_changed else ""),
                    title + (f" · {t.note}" if t.note else ""))  # fmt: skip

    def dep(y: capex_mod.CapexYear) -> Cell:
        if y.depreciation is None:
            return Cell("—", "missing: no depreciation fact", True)
        return Cell(m(y.depreciation), y.depreciation_ref)

    def money_attr(attr: str):
        def f(y: capex_mod.CapexYear) -> Cell:
            val = getattr(y, attr)
            if val is None:
                return Cell("—", f"missing: {y.missing(attr)}", True)
            mark = " †" if attr == "maintenance" and y.marks and "useful-life" in y.marks[0] else ""
            return Cell(
                m(val) + mark, f"{y.method}" + (f" · {'; '.join(y.marks)}" if y.marks else "")
            )

        return f

    def gw(which: str):
        def f(y: capex_mod.CapexYear) -> Cell:
            val = y.greenwald_net if which == "net" else y.greenwald_gross
            ok = y.gw_net_in if which == "net" else y.gw_gross_in
            note = y.greenwald_net_note if which == "net" else y.greenwald_gross_note
            if val is not None and ok:
                share = (
                    f" ({val / y.total.value:.1%} of total)" if y.total and y.total.value else ""
                )
                return Cell(m(val), f"Greenwald maintenance on {which} PP&E{share}")
            return Cell("—", note or "not computable", True)

        return f

    rung = capex_mod.RUNG_METHOD.get(v.rung, v.rung)
    rows = [
        row(
            "Capex, company definition (as the Money flow tab)",
            display,
            note=f"recipe: {v.recipe_label}",
        ),  # fmt: skip
        row(
            "Capex, standard tag (own history = total capex)",
            total,
            note=f"{v.definition}" + (f"; {v.definition_mark}" if v.definition_mark else ""),
        ),  # fmt: skip
        row("Depreciation", dep),
        row(f"Maintenance capex ({rung})", money_attr("maintenance")),
        row("Growth capex (total − maintenance)", money_attr("growth")),
    ]
    for which in ("net", "gross"):
        ins = [y for y in v.years if (y.gw_net_in if which == "net" else y.gw_gross_in)]
        if ins:
            rows.append(row(f"Greenwald maintenance, {which} PP&E (cross-check, in range only)",
                            gw(which), sub=True))  # fmt: skip
    rows += [
        row("FCF on total capex (OCF − total capex)", money_attr("fcf_total")),
        row("FCF on maintenance capex (OCF − maintenance)", money_attr("fcf_maintenance")),
        row("Owner earnings (OCF − maintenance − SBC; information)", money_attr("owner_earnings")),
    ]
    lines = [v.gw_line("net"), v.gw_line("gross")]
    if v.changed_years:
        lines.append(f"definition changed (‡, not scored): {', '.join(v.changed_years)} (D-M04-3)")
    for y in v.years:
        for mk in y.marks:
            if mk.startswith("useful-life"):
                lines.append(f"{y.label} maintenance (†): {mk}")
    return Table(labels, rows, lines)


def trends_table(t: trends_mod.TrendsView) -> Table:
    rows = []
    for r in t.rows:
        cells = []
        for lbl in t.labels:
            c = r.cells.get(lbl)
            if c is None:
                cells.append(Cell("", ""))
            elif c.value is None:
                cells.append(_missing(c.text))
            elif r.unit == "usd":
                cells.append(Cell(m(c.value), c.text))
            elif r.unit == "pp":
                cells.append(Cell(f"{c.value:+.1f} pp".replace("-", "−"), c.text))
            elif r.key == "gm":
                cells.append(Cell(f"{c.value:.1f}%".replace("-", "−"), c.text))
            else:
                cells.append(Cell(pct(c.value), c.text))
        rows.append(TableRow(r.label, cells, r.note))
    return Table(t.labels, rows)


def _signal_rows(t: trends_mod.TrendsView) -> list[tuple[str, str, str]]:
    out = []
    for s in t.signals:
        if s.missing is not None:
            out.append((s.name, f"missing: {s.missing}", s.method))
        elif s.text:
            out.append((s.name, "n/m", s.method))
        elif s.name in ("gm_trend_pp", "opex_vs_sales"):
            out.append((s.name, f"{s.value:+.1f} pp".replace("-", "−"), s.method))
        else:
            out.append((s.name, pct(s.value), s.method))
    return out


def guidance_section(rec: record_mod.Record) -> GuidanceSection:
    if rec.scored:
        head = (
            f"Hit rate {100 * rec.hits / rec.scored:.0f}% ({rec.hits} of {rec.scored} scored "
            f"guides; {rec.misses} miss{'es' if rec.misses != 1 else ''})"
        )
    else:
        head = f"Hit rate: missing {rec.missing}"
    scored = sorted(
        (o for o in rec.outcomes if o.kind == "score" and o.outcome != "pending"),
        key=lambda o: (o.end, o.metric),
        reverse=True,
    )
    pending = sorted(
        (o for o in rec.outcomes if o.kind == "score" and o.outcome == "pending"),
        key=lambda o: (o.end, o.metric),
    )
    removals = sorted(
        (o for o in rec.outcomes if o.kind == "removal"),
        key=lambda o: o.release_filed,
        reverse=True,
    )
    return GuidanceSection(head, rec.repeated, scored, pending, removals)


def company_view(
    engine: sqlite3.Connection,
    cik: str,
    today: date,
    corpus: sqlite3.Connection | None = None,
    ticker: str | None = None,
) -> M04View:
    norm = normalize_cik(cik) or cik
    rows = stored_status(engine, norm)
    unfiled = [r for r in rows if r["filed"] is None]
    record = unfiled[0] if unfiled else (rows[0] if rows else None)
    days = None
    if record is not None:
        days = (date.fromisoformat(record["due_date"]) - today).days
    cv = capex_mod.capex_view(engine, norm, today.isoformat())
    tv = trends_mod.trends_view(engine, norm, today.isoformat(), cv)
    rec = record_mod.record_for(engine, corpus, norm, today)
    return M04View(
        status=rows[:6],
        record=record,
        days_to_due=days,
        shares=share_rows(engine, norm),
        capex=capex_table(cv) if cv.years else None,
        trends=trends_table(tv) if tv.labels else None,
        signals=_signal_rows(tv),
        guidance=guidance_section(rec),
        todo=[(what, f"missing: not built, Part {part}") for what, part in STILL_TO_COME],
        profile=profile_mod.company_profile(engine, models_mod.load_safe(), norm, ticker),
    )
