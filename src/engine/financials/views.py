"""Financials tab, M04 sections (M00_UI D-UI-22, D-UI-23; M04 Parts 1a–1b). Plain data for
the template.

A Profile block at the top (Part 1c: stage and flag set, model tag, peers confirmed).
Sections below the existing quarterly and balance-sheet tables (owner's mock-ups): Filing
status, Share counts (Part 1a); Capex, Core trends, Guidance record (Part 1b); peer
columns on the Core trends rows and a "Peers — <ticker>" table (Part 2, D-UI-25); Marker
legend; and "M04 rows still to come" (one row per later build part, each "missing: not
built, Part n"; D10: never hidden).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date

from engine.financials import capex as capex_mod
from engine.financials import models as models_mod
from engine.financials import peer_facts as peer_facts_mod
from engine.financials import peer_z as peer_z_mod
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
    (
        "peer z",
        "(company − peer median) ÷ scale: MAD × 1.4826 × b_n for 5–9 peers, IQR ÷ 1.35 for "
        "10 or more; any peer beyond |z| > 3 dropped once; the gap to the median always shown "
        "(D-M04-52). Information rows: no vote until Part 8 (D-M04-11).",
    ),
    (
        "fixed-gap fallback",
        "Fewer than 5 comparable peers: the gap to the median decides, z is information only "
        "(low confidence), with the spread of four z methods (Intel 2022 at n = 4: −0.82 to "
        "−1.92).",
    ),
    (
        "no comparable period",
        "The peer's period ends outside ±45 days (12-month flows) or ±40 days (quarters, "
        "instants) of the company's; counted toward the < 5 fallback. \"Awaiting peer "
        'filing" = its next quarter would fall inside (D-M04-5).',
    ),
    (
        "53-week year / acquisition year",
        "Peer flags: a 12-month period of 370 days or more (adds about 2%); cash for "
        "businesses or a goodwill rise ≥ 10%† of revenue (AMD FY2022: Xilinx). The peer stays "
        "in the comparison.",
    ),
    ("missing: <reason>", "No value, and why. Missing is never zero (D-M04-9)."),
)

STILL_TO_COME = (
    ("Survival gate: 25-year EDGAR text history and undrawn-credit finder (MVP: deferred)", "4b"),
    ("Dilution and financing pressure", "5"),
    ("Margin collapse (R12), unit economics, customers", "7b"),
    # Part 8a built the CvD grid and health vote on the M04 tab; deferred by the owner (D31):
    ("Normalized earnings power, overreaction gauge, Red Flag 1 row", "8a (deferred, MVP)"),
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
    extra: list[Cell] = field(default_factory=list)  # peer columns (Part 2)


@dataclass
class Table:
    labels: list[str]
    rows: list[TableRow]
    lines: list[str] = field(default_factory=list)
    extra_heads: list[str] = field(default_factory=list)


@dataclass
class PeersSection:
    title: str
    status: str  # "" or "peers not confirmed on the M04 setup page"
    ref: str  # "company's latest 12-month period ends 2026-08-27"
    lines: list[peer_z_mod.PeerLine]
    note: str


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
    peers: PeersSection | None = None


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


PEER_HEADS = ["Peer median", "Robust z", "n", "Peer method"]


def _fmt(key: str, unit: str, v: float | None) -> str:
    if v is None:
        return "—"
    if key == "gm":
        return f"{v:.1f}%".replace("-", "−")
    if unit == "pp":
        return f"{v:+.1f} pp".replace("-", "−")
    return pct(v)


def peer_cells(key: str, unit: str, comp: peer_z_mod.Comparison | None) -> list[Cell]:
    """Peer median, robust z, n and method for one core trend row (Part 2)."""
    if comp is None:
        return [Cell("—", "no peer comparison", True)] * 3 + [
            Cell("missing: no comparison", "", True)
        ]
    if comp.status:
        return [Cell("—", comp.status, True)] * 3 + [Cell(f"missing: {comp.status}", "", True)]
    row = comp.rows.get(key)
    if row is None:
        return [Cell("—", "not compared", True)] * 3 + [Cell("not compared", "", True)]
    if row.missing:
        text = (
            f"missing: {row.missing}" if not row.missing.startswith("not compared") else row.missing
        )
        if row.note:
            text += f" · {row.note}"
        return [Cell("—", row.missing, True)] * 3 + [Cell(text, row.basis, True)]
    r = row.result
    members = "; ".join(
        f"{m.name} {_fmt(key, unit, m.value)} ({m.end}, {m.offset:+d} d)"
        + (f" [{'; '.join(m.flags)}]" if m.flags else "")
        if m.included else f"{m.name}: {m.why}"
        for m in row.members
    )  # fmt: skip
    company = f"company {_fmt(key, unit, row.company.value)}"
    gap = f"gap {r.gap * row.scale:+.1f} pp".replace("-", "−") if r.gap is not None else ""
    if r.median is None:
        med = Cell("—", f"{company}; {r.note}; {members}", True)
    else:
        med = Cell(_fmt(key, unit, r.median), f"{company}; {gap}; {members}")
    if r.z is None:
        z = Cell("—", r.note or "no z", True)
    else:
        z = Cell(f"{r.z:+.2f}".replace("-", "−") + (" (info)" if r.z_info else ""),
                 "information only (fewer than 5 peers)" if r.z_info else r.method)  # fmt: skip
    n = Cell(f"{r.n}" + (f" of {r.n_in}" if r.n_in != r.n else ""), f"{r.n_in} comparable")
    method = "; ".join(x for x in (gap, r.method_text(), row.basis, row.note) if x)
    return [med, z, n, Cell(method, members, r.fallback)]


def trends_table(t: trends_mod.TrendsView, comp: peer_z_mod.Comparison | None = None) -> Table:
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
        rows.append(TableRow(r.label, cells, r.note, extra=peer_cells(r.key, r.unit, comp)))
    return Table(t.labels, rows, extra_heads=list(PEER_HEADS))


PEERS_NOTE = (
    "Peer facts: one companyfacts download per confirmed SEC peer (scripts/run_financials.py "
    "peers), trimmed to M04's tags and stored as facts; the file is not kept (D-M04-75, "
    "SB.16). The refresh re-fetches a peer when the daily index shows its new 10-K, 10-Q, "
    "20-F or 40-F (D-M04-70); a peer that is a covered company uses its own refreshed facts. "
    "Offsets: 12-month periods ±45 days, quarters and instants ±40 (D-M04-5); outside = no "
    "comparable period, counted toward the < 5 fallback."
)


def peers_section(
    comp: peer_z_mod.Comparison, ticker: str, engine: sqlite3.Connection
) -> PeersSection:
    ref = (f"company's latest 12-month period ends {comp.ref_end}" if comp.ref_end
           else "company has no 12-month revenue")  # fmt: skip
    last = engine.execute(
        "SELECT max(ok_at) FROM peer_fetch WHERE cik IN (SELECT m.cik FROM peer_member m JOIN "
        "peer_group g ON g.group_id = m.group_id WHERE g.name = ?)",
        (peer_facts_mod.GROUP.format(cik=comp.cik),),
    ).fetchone()[0]
    note = PEERS_NOTE + (f" Last peer download: {last[:10]}." if last else "")
    return PeersSection(f"Peers — {ticker}", comp.status, ref, comp.lines, note)


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
    comp = peer_z_mod.compare(engine, ticker or norm, norm, today.isoformat())
    peer_z_mod.annotate(tv, comp)
    rec = record_mod.record_for(engine, corpus, norm, today)
    return M04View(
        status=rows[:6],
        record=record,
        days_to_due=days,
        shares=share_rows(engine, norm),
        capex=capex_table(cv) if cv.years else None,
        trends=trends_table(tv, comp) if tv.labels else None,
        peers=peers_section(comp, ticker or norm, engine),
        signals=_signal_rows(tv),
        guidance=guidance_section(rec),
        todo=[(what, f"missing: not built, Part {part}") for what, part in STILL_TO_COME],
        profile=profile_mod.company_profile(engine, models_mod.load_safe(), norm, ticker),
    )
