"""Financials tab, M04 Part 7a sections (owner's mock-up; M00_UI D-UI-27). Plain data for
`tabs/_m04_units.html`:

- **Major customers (≥ 10% of revenue)** per fiscal year from the 10-K instance
  (`srt:MajorCustomersAxis`): count, revenue at stake (sum of the stated percentages, in $
  on the year's revenue), each customer's share. Customers are anonymous ("Customer A");
  matching them across years is inference, and a shorter list is not a loss (a customer
  can fall below the 10% line; NVIDIA FY2026), so this table never votes.
- **Segments** from the latest annual instance, each value as filed; a value another
  filing reports differently is marked "recast" (first value on hover), and a change in
  the set of segments is a break, never merged (D-M04-42).
- **Unit KPIs**: latest period per metric and model line against a year earlier; credits
  in their own table; company-stated non-GAAP gross margin year over year on each
  release's own columns; reference episodes (Invitae, Target) that are not covered.
- **Share classes**: per-class cover counts from the instance against Part 1a's R1 counts.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from engine.financials import exhibits, units
from engine.financials.capex import fiscal_label
from engine.sec.instance_dim import local, recasts, rows

INVITAE_CIK = "0001501134"
TARGET_CIK = "0000027419"
RIVN_CIK = "0001874178"
TARGET_QUARTERS = (("2022Q1", "2022-04-30", "2021-05-01"), ("2022Q2", "2022-07-30", "2021-07-31"))
PCT_TAGS = ("ConcentrationRiskPercentage1", "ConcentrationRiskPercentage")
SEGMENT_TAGS = units.REVENUE_TAGS + ("OperatingIncomeLoss",)
ANNUAL_FORMS = ("10-K", "10-KT", "20-F", "40-F", "10-K/A")


def _days(start: str | None, end: str) -> int:
    if not start:
        return 0
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _annual(r: sqlite3.Row) -> bool:
    return 300 <= _days(r["period_start"], r["period_end"]) <= 380


@dataclass(frozen=True)
class CustomerYear:
    label: str
    end: str
    count: int
    customers: list[tuple[str, float]]
    at_stake: float  # share of revenue
    at_stake_usd: float | None
    revenue: float | None
    accession: str
    basis: str
    # facts of the same year and filing left out of the sum: (member, value, reason)
    excluded: tuple[tuple[str, float, str], ...] = ()


def _year_revenue(engine: sqlite3.Connection, cik: str, end: str) -> float | None:
    for tag in units.REVENUE_TAGS:
        r = engine.execute(
            "SELECT value FROM fact WHERE cik = ? AND tag = ? AND period_end = ? AND "
            "period_start IS NOT NULL AND julianday(period_end) - julianday(period_start) "
            "BETWEEN 300 AND 380 ORDER BY filed LIMIT 1",
            (cik, tag, end),
        ).fetchone()
        if r is not None:
            return float(r[0])
    return None


CUSTOMER_AXES = (
    "MajorCustomersAxis",
    "ConcentrationRiskByBenchmarkAxis",
    "ConcentrationRiskByTypeAxis",
)
# A member that stands for several customers ("ThreeLargestCustomers", "TopTen…"): its
# percentage repeats the named customers' (live check 1: INTC FY2025 "4 at 86%").
_AGGREGATE = re.compile(
    r"customers$|^top(?:\d|one|two|three|four|five|ten)|largest|combined|aggregate|^total"
    r"|^all(?:other)?customers",
    re.I,
)


def _dims(dims: str) -> dict[str, str]:
    return {
        a.split(":")[-1]: m.split(":")[-1]
        for a, m in (p.split("=", 1) for p in dims.split(";") if "=" in p)
    }


def customer_reason(concept: str, dims: str) -> str:
    """'' when the fact is a consolidated customer share of revenue, else why it is left
    out: only `ConcentrationRiskByBenchmarkAxis` = revenue or sales with
    `ConcentrationRiskByTypeAxis` = customer concentration, and no other axis (a segment,
    product or geography split is not the company's share) (D-M04-43)."""
    d = _dims(dims)
    other = sorted(a for a in d if a not in CUSTOMER_AXES)
    if other:
        return f"not consolidated ({', '.join(other)})"
    tag = concept.split(":")[-1]
    bench = d.get("ConcentrationRiskByBenchmarkAxis", "").lower()
    typ = d.get("ConcentrationRiskByTypeAxis", "").lower()
    if tag in units.REVENUE_TAGS:
        return "" if not bench and not typ else "revenue fact with a concentration axis"
    if not bench:
        return "no benchmark axis"
    if not ("revenue" in bench or "sales" in bench) or any(
        w in bench for w in ("cost", "receivable", "purchase", "payable", "inventor")
    ):
        return f"benchmark {d['ConcentrationRiskByBenchmarkAxis']}"
    if "customer" not in typ:
        return f"risk type {d['ConcentrationRiskByTypeAxis']}" if typ else "no risk-type axis"
    return ""


def _own_year(rs: list[sqlite3.Row]) -> dict[str, str]:
    """accession → the fiscal year end its annual report covers (its latest annual period)."""
    out: dict[str, str] = {}
    for r in rs:
        out[r["accession"]] = max(out.get(r["accession"], ""), r["period_end"])
    return out


def major_customers(engine: sqlite3.Connection, cik: str) -> list[CustomerYear]:
    """≥ 10% customers per fiscal year: consolidated customer shares of revenue only
    (`customer_reason`), one value per customer, all from one filing — the year's own
    annual report (its latest amendment wins). A later 10-K repeats a past year only for
    the customers still above 10% and re-letters them ("Customer A" is not the same
    customer each year), so mixing filings would double-count or undercount. Aggregate
    members (a "three largest customers" total) are left out, with the reason kept."""
    kept: list[sqlite3.Row] = []
    for r in rows(engine, cik, role="customer"):
        if r["concept"].split(":")[-1] not in PCT_TAGS + units.REVENUE_TAGS or not _annual(r):
            continue
        if r["form"] not in ANNUAL_FORMS:
            continue
        kept.append(r)
    own = _own_year(kept)
    by_end: dict[str, list[sqlite3.Row]] = {}
    for r in kept:
        by_end.setdefault(r["period_end"], []).append(r)
    out = []
    for end, rs in sorted(by_end.items()):
        mine = [r for r in rs if own.get(r["accession"]) == end]
        pool = mine or rs
        pick = (
            max(pool, key=lambda r: (r["filed"], r["accession"]))
            if mine
            else min(pool, key=lambda r: (r["filed"], r["accession"]))
        )["accession"]
        rs = [r for r in rs if r["accession"] == pick]
        excluded: list[tuple[str, float, str]] = []
        pct: dict[str, float] = {}
        usd: dict[str, float] = {}
        for r in rs:
            tag = r["concept"].split(":")[-1]
            why = customer_reason(r["concept"], r["dims"])
            if why:
                excluded.append((local(r["member"]), float(r["value"]), why))
                continue
            (pct if tag in PCT_TAGS else usd).setdefault(r["member"], float(r["value"]))
        rev = _year_revenue(engine, cik, end)
        basis = "stated percentages"
        if pct and max(pct.values()) > 1:  # tagged as 12 rather than 0.12
            pct = {k: v / 100 for k, v in pct.items()}
            basis += " (tagged in percent, scaled)"
        for k in list(pct):
            others = [v for o, v in pct.items() if o != k]
            if _AGGREGATE.search(local(k)) or (
                len(others) >= 3 and abs(pct[k] - sum(others)) <= 0.006
            ):
                excluded.append((local(k), pct.pop(k), "aggregate of several customers"))
                usd.pop(k, None)
        for k in [k for k in usd if _AGGREGATE.search(local(k))]:
            excluded.append((local(k), usd.pop(k), "aggregate of several customers"))
        if not pct and usd and rev:
            pct = {k: v / rev for k, v in usd.items()}
            basis = "stated revenue ÷ total revenue"
        if not pct:
            continue
        stake = sum(pct.values())
        stake_usd = sum(usd.values()) if usd else (stake * rev if rev else None)
        out.append(
            CustomerYear(
                fiscal_label(end),
                end,
                len(pct),
                sorted(((local(k), v) for k, v in pct.items()), key=lambda kv: -kv[1]),
                stake,
                stake_usd,
                rev,
                pick,
                basis + ("" if mine else "; from the first filing that reports the year"),
                tuple(excluded),
            )
        )
    return out


@dataclass
class SegmentTable:
    title: str
    accession: str
    labels: list[str]
    rows: list[tuple[str, list[tuple[str, str]]]]  # label, [(text, title)]
    notes: list[str] = field(default_factory=list)


def _only_role(dims: str, role_axis: str) -> bool:
    for p in dims.split(";"):
        axis, member = p.split("=", 1)
        a = axis.split(":")[-1]
        if a == role_axis:
            continue
        if a == "ConsolidationItemsAxis" and "OperatingSegments" in member:
            continue
        return False
    return True


RENAME_TOL = 0.01


def renames(
    old_rows: list[sqlite3.Row], new_rows: list[sqlite3.Row], gone: set[str], new: set[str]
) -> dict[str, str]:
    """Old member → new member where both filings report the same concepts for the
    overlapping periods and every overlapping value agrees within 1% (a renamed member,
    e.g. Boeing's BoeingDefenseSpaceSecuritySegment → DefenseSpaceAndSecuritySegment);
    each old member pairs with exactly one new member, else it stays a break."""

    def values(rs, member):
        return {
            (r["concept"], r["period_start"], r["period_end"]): float(r["value"])
            for r in rs
            if r["member"] == member
        }

    out: dict[str, str] = {}
    for o in sorted(gone):
        ov = values(old_rows, o)
        hits = []
        for n in sorted(new - set(out.values())):
            nv = values(new_rows, n)
            keys = set(ov) & set(nv)
            if keys and all(
                abs(ov[k] - nv[k]) <= RENAME_TOL * max(abs(ov[k]), abs(nv[k]), 1.0) for k in keys
            ):
                hits.append(n)
        if len(hits) == 1:
            out[o] = hits[0]
    return out


def segment_table(engine: sqlite3.Connection, cik: str) -> SegmentTable | None:
    """Segment revenue and operating income from the latest annual instance; recasts marked;
    a changed set of segments is a break. Product or service revenue when no segments."""
    for role, axis, title in (
        ("segment", "StatementBusinessSegmentsAxis", "Segments"),
        ("product", "ProductOrServiceAxis", "Revenue by product or service (no segment facts)"),
    ):
        rs = [
            r
            for r in rows(engine, cik, role=role)
            if r["concept"].split(":")[-1] in SEGMENT_TAGS
            and _annual(r)
            and r["form"] in ANNUAL_FORMS
            and _only_role(r["dims"], axis)
        ]
        if role == "product":
            rs = [r for r in rs if r["concept"].split(":")[-1] in units.REVENUE_TAGS]
        if not rs:
            continue
        accs = sorted({(r["filed"], r["accession"]) for r in rs})
        latest = accs[-1][1]
        cur = [r for r in rs if r["accession"] == latest]
        ends = sorted({r["period_end"] for r in cur})[-3:]
        recast = {(x.concept, x.dims, x.end): x for x in recasts(engine, cik, role=role)}
        table_rows = []
        keys = sorted(
            {(r["member"], r["concept"], r["dims"]) for r in cur}, key=lambda k: (local(k[0]), k[1])
        )
        for member, concept, dims in keys:
            cells = []
            for end in ends:
                hit = next(
                    (
                        r
                        for r in cur
                        if r["member"] == member
                        and r["concept"] == concept
                        and r["dims"] == dims
                        and r["period_end"] == end
                    ),
                    None,
                )
                if hit is None:
                    cells.append(("—", "not reported in this filing"))
                    continue
                v = float(hit["value"]) / 1e6
                rc = recast.get((concept, dims, end))
                text = f"{v:,.0f}".replace("-", "−")
                tip = f"{concept} · {latest}"
                if rc:
                    text += " recast"
                    tip += (
                        f" · first filed {rc.first[0] / 1e6:,.0f} ({rc.first[1]}, "
                        f"{rc.first[2]}); latest {rc.latest[0] / 1e6:,.0f} ({rc.latest[1]})"
                    )
                cells.append((text, tip))
            name = "operating income" if concept.endswith("OperatingIncomeLoss") else "revenue"
            table_rows.append((f"{local(member)} · {name}", cells))
        notes = []
        if len(accs) > 1:
            prev = accs[-2][1]
            before = {r["member"] for r in rs if r["accession"] == prev}
            now_ = {r["member"] for r in cur}
            if before != now_:
                renamed = renames(
                    [r for r in rs if r["accession"] == prev], cur, before - now_, now_ - before
                )
                if renamed:
                    notes.append(
                        "Renamed member: "
                        + ", ".join(f"{local(o)} → {local(n)}" for o, n in sorted(renamed.items()))
                        + " (both filings report the overlapping years and the values agree "
                        "within 1%); series continued."
                    )
                gone_set = before - now_ - set(renamed)
                new_set = now_ - before - set(renamed.values())
                if gone_set or new_set:
                    gone = ", ".join(sorted(local(m) for m in gone_set)) or "none"
                    new = ", ".join(sorted(local(m) for m in new_set)) or "none"
                    notes.append(
                        f"Break: the set of {role}s changed from {prev} to {latest} "
                        f"(no longer reported: {gone}; new: {new}); not merged (D-M04-42)."
                    )
        n_recast = sum(1 for k in recast if k[2] in ends)
        if n_recast:
            notes.append(
                f"{n_recast} value(s) in these years were reported differently by "
                "another filing (recast; hover for both)."
            )
        return SegmentTable(title, latest, [fiscal_label(e) for e in ends], table_rows, notes)
    return None


@dataclass(frozen=True)
class ClassCheck:
    accession: str
    form: str | None
    filed: str
    instance: list[tuple[str, float]]
    instance_total: float
    r1_total: float | None
    agree: str


def class_checks(engine: sqlite3.Connection, cik: str, limit: int = 4) -> list[ClassCheck]:
    """Per filing: cover counts by class from the instance vs Part 1a's R1 counts."""
    by: dict[str, list[sqlite3.Row]] = {}
    for r in rows(engine, cik, role="class"):
        if r["concept"].endswith("EntityCommonStockSharesOutstanding"):
            by.setdefault(r["accession"], []).append(r)
    out = []
    for acc, rs in sorted(by.items(), key=lambda kv: kv[1][0]["filed"], reverse=True)[:limit]:
        inst = [(local(r["member"]), float(r["value"])) for r in rs]
        total = sum(v for _, v in inst)
        r1 = engine.execute(
            "SELECT sum(shares), count(*) FROM cover_shares WHERE accession = ?", (acc,)
        ).fetchone()
        r1_total = float(r1[0]) if r1 and r1[1] else None
        if r1_total is None:
            agree = "R1 not read for this filing"
        elif abs(r1_total - total) < 0.5:
            agree = "agree"
        else:
            agree = f"differ by {total - r1_total:+,.0f}"
        out.append(ClassCheck(acc, rs[0]["form"], rs[0]["filed"], inst, total, r1_total, agree))
    return out


@dataclass(frozen=True)
class KpiLine:
    company: str
    metric: str
    earlier: str
    later: str
    change: str
    source: str
    title: str = ""


def _fmt_value(v: float, unit: str) -> str:
    if unit == "USD":
        return f"${v / 1e6:,.1f}M"
    if unit in ("MWh", "GWh"):
        return f"{v:,.0f} {unit}"
    return f"{v:,.0f}"


def _metric_name(r: units.KpiRow) -> str:
    name = r.metric.replace("_", " ")
    return f"{name} · {r.line}" if r.line else name


def kpi_lines(
    engine: sqlite3.Connection, cik: str, company: str
) -> tuple[list[KpiLine], list[KpiLine]]:
    """(unit KPIs, credits) for one company."""
    kpis, credits = [], []
    for r in units.kpi_rows(engine, cik):
        if r.kind == "non_gaap" or r.metric == "revenue_stated":
            continue
        earlier = f"{r.earlier[0]}: {_fmt_value(r.earlier[1], r.unit)}" if r.earlier else "—"
        later = f"{r.later[0]}: {_fmt_value(r.later[1], r.unit)}"
        change = f"{r.change:+.1%}".replace("-", "−") if r.change is not None else "—"
        line = KpiLine(
            company,
            _metric_name(r),
            earlier,
            later,
            change,
            f"{r.source} ({r.basis})",
            r.quote[:300],
        )
        (credits if r.kind == "credit" else kpis).append(line)
    for m in exhibits.non_gaap_margin_yoy(engine, cik)[-4:]:
        kpis.append(
            KpiLine(
                company,
                "non-GAAP gross margin (company-stated; YoY on the release's own columns)",
                f"{m.prior:.1%}",
                f"{m.label}: {m.margin:.1%}",
                f"{m.pp:+.1f} pp".replace("-", "−"),
                m.accession,
            )
        )
    return kpis, credits


def reference_lines(engine: sqlite3.Connection) -> list[KpiLine]:
    """Episode companies outside the watchlist (Part 8b names): Invitae, Target."""
    out: list[KpiLine] = []
    for m in exhibits.non_gaap_margin_yoy(engine, INVITAE_CIK):
        out.append(
            KpiLine(
                "Invitae",
                "non-GAAP gross margin YoY (company-stated)",
                f"{m.prior:.1%}",
                f"{m.label}: {m.margin:.1%}",
                f"{m.pp:+.1f} pp".replace("-", "−"),
                m.accession,
            )
        )
    for r in units.kpi_rows(engine, INVITAE_CIK):
        if r.metric == "billable_units":
            out.append(
                KpiLine(
                    "Invitae",
                    "billable units",
                    f"{r.earlier[0]}: {r.earlier[1]:,.0f}" if r.earlier else "—",
                    f"{r.later[0]}: {r.later[1]:,.0f}",
                    f"{r.change:+.1%}".replace("-", "−") if r.change is not None else "—",
                    f"{r.source} ({r.basis})",
                    r.quote[:300],
                )
            )
    for label, end, prior in TARGET_QUARTERS:
        pp, cur, old = units.gm_yoy_pp(engine, TARGET_CIK, end, prior)
        if cur.revenue is None and old.revenue is None:
            continue
        out.append(
            KpiLine(
                "Target",
                f"gross margin {label} vs a year earlier",
                f"{old.gm:.1%}" if old.gm is not None else old.basis,
                f"{cur.gm:.1%}" if cur.gm is not None else cur.basis,
                f"{pp:+.1f} pp".replace("-", "−") if pp is not None else "—",
                cur.basis,
            )
        )
    return out


@dataclass
class UnitsView:
    customers: list[CustomerYear]
    segments: SegmentTable | None
    kpis: list[KpiLine]
    credits: list[KpiLine]
    reference: list[KpiLine]
    classes: list[ClassCheck]
    dim_rows: int
    instances_read: int
    breaks: list[units.Break]
    rivn: str


def rivn_note(engine: sqlite3.Connection) -> str:
    row = engine.execute(
        "SELECT tier FROM tier_member WHERE cik = ? AND status = 'active'", (RIVN_CIK,)
    ).fetchone()
    if row is None:
        return (
            "RIVN enters as a promoted company through the UI (D-M04-81, D-M02-11): open "
            "/c/RIVN, Themes tab, Track, then Promote; then run "
            "scripts/run_financials.py units. Not covered yet."
        )
    if row["tier"] != "promoted":
        return (
            "RIVN is tracked, not promoted: promote it on /c/RIVN (Themes tab) for "
            "documents and instance reads (D-M04-80, -81)."
        )
    return "RIVN is promoted (D-M04-81): covered like the core watchlist."


def company_view(engine: sqlite3.Connection, cik: str, ticker: str | None = None) -> UnitsView:
    n_dim = engine.execute("SELECT count(*) FROM fact_dim WHERE cik = ?", (cik,)).fetchone()[0]
    n_read = engine.execute(
        "SELECT count(DISTINCT accession) FROM fact_dim WHERE cik = ?", (cik,)
    ).fetchone()[0]
    kpis, credits = kpi_lines(engine, cik, ticker or cik)
    return UnitsView(
        customers=major_customers(engine, cik),
        segments=segment_table(engine, cik),
        kpis=kpis,
        credits=credits,
        reference=reference_lines(engine),
        classes=class_checks(engine, cik),
        dim_rows=n_dim,
        instances_read=n_read,
        breaks=units.breaks(engine, cik),
        rivn=rivn_note(engine),
    )
