"""Financials tab, Part 6 sections (owner's mock-up, 2026-10-13): earnings-quality scores,
contract assets and deferred revenue, estimate changes, recurring "one-time" charges and
non-operating swings, plus the GE and Lockheed reference rows when stored. Plain data for
`tabs/_m04_quality.html`. Scores are computed live from stored facts (as the Part 1b rows
are); estimate sentences and special items come from the tables the refresh's local pass
and `scripts/run_financials.py quality` write."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from engine.financials import estimates, quality, restate, special, stage
from engine.sec.identity import normalize_cik
from engine.signals import latest_signal

GE_CIK = "0000040545"
LMT_CIK = "0000936468"
SIGNALS = (
    "eq_cash",
    "eq_accruals",
    "contract_asset_gap",
    "deferred_rev_gap",
    "mscore",
    "mscore_sgi1",
    "misstate_f",
    "estimate_share",
    "special_items",
)

SCORES_NOTE = (
    "CFO/NI on the operating basis: net income less identified non-cash, non-operating items "
    "(securities and digital-asset fair-value changes taxed at 21% from 2018, 35% before; the "
    "valuation-allowance change as reported) when they exceed 25% of |net income| (S2.1); "
    "not meaningful when 3-year net income is ≤ 0 or below 1% of revenue. Below 0.8 warns for a "
    "confirmed mature or decline stage and is a note for introduction, growth and shake-out; "
    "with no confirmed stage both readings are shown and not counted (D-M04-20, -7). Accruals "
    "= (net income − CFO) ÷ average assets against the company's own 5 prior years, shown, "
    "never a warning. M-score: Beneish with the cash-flow ACCR, and with SGI = 1; the "
    "m04_mscore review opens only when the SGI = 1 version is above −1.78, otherwise a raw M "
    "above −1.78 is a growth-driven note (D-M04-14). Misstatement F: Dechow et al. (2011) "
    "Model 1, an approximation on Compustat coefficients; bands > 1.00 (flags about 36% of "
    "clean firm-years) and > 2.45 (5%) shown, never a trigger; `issue` with no proceeds tag "
    "is unknown, never 0. All values as first reported; hover a score for its inputs, tags "
    "and accessions. No D13 weight until ≥ 20 owner labels (D-M04-60)."
)
GAPS_NOTE = (
    "Fiscal-year readings, values as first reported (S2.2): contract assets growing more than "
    "10 pp faster than revenue in the last 2 readings, or deferred revenue falling while "
    "revenue grows in the last 2 readings → watch. A reading whose line changed tag (an alias "
    "→ a standard tag, or one standard tag → another) reads “definition changed” and is not "
    "scored (D-M04-3 rule). GE's `ge:ContractAsset` and `CommodityContractAssetNoncurrent` are "
    "read for GE only (SB.18)."
)
ESTIMATES_NOTE = (
    "Sentences in the current and two prior annual reports that state the effect of a change "
    "in estimate with an amount (D-M04-17): one amount per sentence, after-tax first, then "
    "pre-tax, then an expense line (its income effect). Denominator on the amount's own basis "
    "and year, as known on the report's filing date: after-tax ÷ net income; pre-tax ÷ "
    "operating income, else pretax income from continuing operations; not meaningful when ≤ 0 "
    "or below 1% of revenue; a segment share only when stored or quoted (D-M04-18). Bands < 10% "
    "note, 10–25% watch, ≥ 25% elevated, both directions; ≥ 10% opens m04_estimate (group 7). "
    "The same direction in all three disclosures adds a recurrence flag. Amounts are kept by "
    "filing version (a later report's restated amount is its own row). Hover a sentence for "
    "its verified quote."
)
SPECIAL_NOTE = (
    "Per fiscal year of the last 4: restructuring, impairment or write-down tags, or "
    "“non-recurring” / “one-time” wording in that year's stored annual report (D-M04-19). "
    "Items in ≥ 3 of 4 years warn (starting value, all stages); a genuine multi-year "
    "restructuring reads as recurrence too, so read the plan. The company-stated non-GAAP vs "
    "GAAP gap is quoted from its own release, never computed."
)
SWINGS_NOTE = (
    "Non-cash, non-operating items by tag with their after-tax effect and share of net income "
    "(SB.12): shown, not scored; they decide the operating basis of CFO/NI. A model tag "
    "(`asset_treasury`, MSTR) makes CFO/NI, accruals and both scores not meaningful (D-M04-8)."
)


@dataclass
class ScoreRow:
    label: str
    cfo_ni: str
    accruals: str
    m: str
    m1: str
    f: str
    reading: str
    title_m: str = ""
    title_f: str = ""
    bold: bool = False


@dataclass
class QualityView:
    ticker: str | None
    excluded: str
    stage_label: str
    tag_how: str
    rows: list[ScoreRow]
    cash_line: str
    dso: str
    non_reliance: str
    gaps: list[dict]
    estimates: list[dict]
    recurrence: str
    catch_up: list[dict]
    special: dict | None
    swings: list[dict]
    reference: dict = field(default_factory=dict)
    signals: list[tuple[str, str, str]] = field(default_factory=list)
    notes: dict = field(
        default_factory=lambda: {
            "scores": SCORES_NOTE,
            "gaps": GAPS_NOTE,
            "estimates": ESTIMATES_NOTE,
            "special": SPECIAL_NOTE,
            "swings": SWINGS_NOTE,
        }
    )


def _m(ms: quality.MScore) -> tuple[str, str, str, str]:
    """(M, M with SGI = 1, reading, hover)."""
    hover = quality.inputs_text(ms.inputs.used)
    if ms.components:
        hover = ", ".join(f"{k} {v:.3f}" for k, v in ms.components.items()) + " · " + hover
    if ms.inputs.method():
        hover += " · " + ms.inputs.method()
    if ms.state == "incomplete":
        return ms.why.replace("missing: ", "incomplete (missing: ") + ")", "", "—", hover
    if ms.state == "not_meaningful":
        return f"not meaningful ({ms.why})", "", "—", hover
    reading = {
        "review": "m04_mscore (SGI = 1 above −1.78)",
        "growth_driven": "“growth-driven” note (raw M above −1.78 only)",
        "below": "—",
    }[ms.reading]
    return f"{ms.m:.2f}".replace("-", "−"), f"{ms.m_sgi1:.2f}".replace("-", "−"), reading, hover


def _f(fs: quality.FScore) -> tuple[str, str]:
    hover = quality.inputs_text(fs.inputs.used)
    if fs.components:
        hover = ", ".join(f"{k} {v:.3f}" for k, v in fs.components.items()) + " · " + hover
    if fs.inputs.method():
        hover += " · " + fs.inputs.method()
    if fs.score is None:
        return (
            fs.why.replace("missing: ", "incomplete (missing: ") + ")"
            if fs.state == "incomplete"
            else f"not meaningful ({fs.why})"
        ), hover
    b = " (> 2.45)" if fs.score > 2.45 else " (> 1.00)" if fs.score > 1.0 else ""
    return f"{fs.score:.2f}{b}", hover


def _gap_rows(g: quality.Gap, line: str, ticker: str | None) -> list[dict]:
    out = []
    for r in g.readings[-3:]:
        reading = (
            "definition changed — not scored"
            if r.state == "definition_changed"
            else "revenue missing — not scored"
            if r.state == "no_revenue"
            else ""
        )
        out.append(
            {
                "company": ticker,
                "line": line,
                "label": r.label,
                "tags": r.prior.tag + ("" if r.prior.tag == r.line.tag else f" → {r.line.tag}"),
                "earlier": quality.money(r.prior.value),
                "later": quality.money(r.line.value),
                "growth": f"{r.line_growth:+.1%} line; revenue "
                + (f"{r.revenue_growth:+.1%}" if r.revenue_growth is not None else "—")
                + (f"; gap {r.gap_pp:+.1f} pp" if r.gap_pp is not None else ""),
                "reading": reading,
                "title": f"{r.prior.tag} {r.prior.accession} → {r.line.tag} {r.line.accession}",
            }
        )
    if out and g.state == "watch":
        out[-1]["reading"] = "watch (2 readings)"
    elif out and not out[-1]["reading"]:
        out[-1]["reading"] = g.why or "no flag"
    return out


def _estimate_rows(rows: list[sqlite3.Row], ticker: str | None) -> list[dict]:
    out = []
    for r in rows:
        share = f"{float(r['share']):+.1%}" if r["share"] is not None else "—"
        out.append(
            {
                "company": ticker,
                "form": r["form"],
                "filed": r["filed"],
                "label": r["fiscal_label"],
                "kind": r["kind"].replace("_", " "),
                "quote": r["quote"],
                "doc": r["doc_ref"],
                "amount": quality.money(float(r["amount"])),
                "basis": r["basis"].replace("_", "-"),
                "denominator": (
                    quality.money(float(r["denominator"])) if r["denominator"] is not None else "—"
                ),
                "denominator_what": r["denominator_what"] or "",
                "share": share,
                "band": r["band"],
                "baseline": bool(r["baseline"]),
                "owner": r["owner_outcome"] or "",
            }
        )
    return out


def _special(sp: special.Special) -> dict:
    return {
        "state": sp.state,
        "count": sp.count,
        "of": len(sp.years),
        "ratio": f"{sp.ratio:.1%}" if sp.ratio is not None else sp.ratio_why or "—",
        "years": [
            {
                "label": y.label,
                "tags": ", ".join(f"{w} {quality.money(v)}M" for w, v, _ in y.tags) or "—",
                "text": [(p, q) for p, q, _ in y.text],
                "text_state": y.text_state,
                "has": y.has,
            }
            for y in sp.years
        ],
        "non_gaap": sp.non_gaap,
        "non_gaap_ref": sp.non_gaap_ref,
    }


def _dso(engine: sqlite3.Connection, cik: str) -> str:
    try:
        from engine.financing.credit import dso

        s = dso(engine, cik)
    except Exception as e:  # context only; never breaks the tab
        return f"DSO: not available ({type(e).__name__})"
    if not s.obs:
        return "DSO (M02, context): missing: no receivables and quarterly revenue pair"
    o = s.obs[-1]
    ch = f", {o.change:+.0%} vs a year earlier" if o.change is not None else ""
    alert = f"; M02 alert: {s.alert}" if s.alert else ""
    return (
        f"DSO (M02, context only): {o.value:.0f} days at {o.end}{ch}{alert} — the alert "
        "stays M02's (m02_fin_alert, D-M02-47); no second item here"
    )


def company_view(
    engine: sqlite3.Connection, corpus: sqlite3.Connection | None, cik: str, ticker: str | None
) -> QualityView:
    norm = normalize_cik(cik) or cik
    row = stage.confirmed(engine, norm)
    st = row["confirmed"] if row else None
    st_label = (
        f"stage {stage.STAGE_NAMES.get(st, st)} (confirmed)"
        if st
        else "stage unconfirmed: both readings, not counted (D-M04-7)"
    )
    q = quality.compute(engine, norm, ticker, stage=st, stage_label=st_label)
    latest = q.ends[-1] if q.ends else None
    nr = restate.non_reliance(engine, norm, latest) if latest else None
    view = QualityView(
        ticker,
        q.excluded,
        st_label,
        q.tag_how,
        [],
        "",
        "",
        nr.mark if nr else "",
        [],
        [],
        "",
        [],
        None,
        [],
    )
    if not q.excluded:
        cc = q.cash
        for i, (ms, fs) in enumerate(zip(q.mscores, q.fscores, strict=True)):
            m, m1, reading, hm = _m(ms)
            f, hf = _f(fs)
            last = i == len(q.mscores) - 1
            cfo = acc = ""
            if last:
                if cc.ratio3 is not None:
                    cfo = f"{cc.ratio3:.2f}" + (f" ({cc.state})" if cc.state != "ok" else "")
                else:
                    cfo = cc.state.replace("_", " ") + (f" ({cc.why})" if cc.why else "")
                if cc.accruals is not None:
                    acc = f"{cc.accruals:+.3f} ({cc.accruals_text.replace('_', ' ')})"
            view.rows.append(
                ScoreRow(ms.label, cfo, acc, m, m1, f, reading, hm, hf, ms.reading == "review")
            )
        from engine.financials.quality_step import cash_text

        yrs = ", ".join(
            f"{y.label} CFO {quality.money(y.cfo.value)}M / NI "
            f"{quality.money(y.basis_ni)}M"
            + (
                " (operating basis: " + ", ".join(w for w, _ in y.items) + ")"
                if y.operating
                else ""
            )
            for y in cc.years
            if y.cfo
        )
        view.cash_line = f"{yrs}. {cash_text(cc, st_label)}" if yrs else cash_text(cc, st_label)
        view.dso = _dso(engine, norm)
        view.gaps = _gap_rows(q.contract, "contract assets", ticker) + _gap_rows(
            q.deferred, "deferred revenue", ticker
        )
        if not view.gaps:
            view.gaps = [
                {
                    "company": ticker,
                    "line": "contract assets / deferred revenue",
                    "label": "—",
                    "tags": "",
                    "earlier": "",
                    "later": "",
                    "growth": "",
                    "reading": f"missing: {q.contract.why}; {q.deferred.why}",
                    "title": "",
                }
            ]
        view.estimates = _estimate_rows(estimates.stored(engine, norm), ticker)
        cu = estimates.catch_up(engine, norm)
        if cu:
            view.catch_up = [{"company": ticker, "years": cu.years, "flag": cu.flag}]
        view.special = _special(special.compute(engine, corpus, norm))
        view.swings = [
            {
                "label": lb,
                "what": w,
                "tag": v.tag,
                "amount": quality.money(v.value),
                "effect": quality.money(e),
                "share": f"{s:.1%}" if s is not None else "—",
                "accession": v.accession,
            }
            for lb, w, v, e, s in q.swings
        ]
    # reference cases (not covered; shown when stored, as Part 7a's reference episodes)
    if (
        norm != GE_CIK
        and engine.execute("SELECT 1 FROM fact WHERE cik = ? LIMIT 1", (GE_CIK,)).fetchone()
    ):
        ge = quality.Facts(engine, GE_CIK)
        g = quality.contract_asset_gap(ge)
        view.reference["gaps"] = _gap_rows(g, "contract assets", "GE (reference)")
        view.reference["estimates"] = _estimate_rows(
            estimates.stored(engine, GE_CIK), "GE (reference)"
        )
    if norm != LMT_CIK:
        cu = estimates.catch_up(engine, LMT_CIK)
        if cu:
            view.reference["catch_up"] = [
                {"company": "LMT (reference)", "years": cu.years, "flag": cu.flag}
            ]
    for name in SIGNALS:
        s = latest_signal(engine, norm, "M04", name)
        if s is None:
            view.signals.append((name, "not computed yet", ""))
            continue
        if s["value"] is not None:
            val = f"{float(s['value']):,.3f}" + (f" ({s['value_text']})" if s["value_text"] else "")
        else:
            val = s["value_text"] or "missing"
        view.signals.append((name, val, s["method"]))
    view.recurrence = estimates.recurrence_rows(estimates.stored(engine, norm))
    return view
