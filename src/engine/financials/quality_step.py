"""M04 Part 6 inside the refresh and the `quality` script (D-M04-14, -17…21, -60, -71, -90…93).

`quality_pass` (local, 0 requests) computes for every covered company the earnings-quality
scores from stored facts (`quality.py`), the estimate-change sentences of its last three
annual reports (`estimates.py`) and its recurring "one-time" charges (`special.py`); stores
`estimate_change` and `special_item`; writes the signals `eq_cash`, `eq_accruals`,
`contract_asset_gap`, `deferred_rev_gap`, `mscore`, `mscore_sgi1`, `misstate_f`,
`estimate_share`, `special_items`; and opens `m04_mscore` and `m04_estimate` items (group
7, inside the weekly cap of 5) for core and promoted names only (tracked: rows, no items,
D-M04-80). A company's first scan is a baseline: items found then queue only when their
annual report was filed in the last 12 months (D-M04-71). A finding that no longer holds is
withdrawn (closed `withdrawn` by "engine"; answered items kept).

Hooked into `scripts/run_refresh.py` after the Part 7a local pass (`financials_quality_local_step`);
there is no SEC part: new annual reports arrive with the refresh's own document step, and
the GE and Lockheed reference files are owner-run (`run_financials.py quality`).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from engine.financials import estimates, models, quality, queue, restate, special, stage
from engine.financials.profile import full_scope
from engine.sec.client import iso
from engine.signals import Source, write_signal

MODULE = "M04"
BASELINE_STATE = "m04_quality_baseline:{cik}"


@dataclass
class CompanyQuality:
    ticker: str
    cik: str
    q: quality.Quality | None = None
    findings: list[estimates.Finding] = field(default_factory=list)
    recurrence: str = ""
    special: special.Special | None = None
    signals: dict[str, str] = field(default_factory=dict)
    proposals: dict[str, int] = field(default_factory=dict)
    error: str = ""


@dataclass
class QualityPass:
    companies: dict[str, CompanyQuality]
    flushed: int = 0


def first_scan(engine: sqlite3.Connection, cik: str) -> bool:
    return (
        engine.execute(
            "SELECT 1 FROM refresh_state WHERE name = ?", (BASELINE_STATE.format(cik=cik),)
        ).fetchone()
        is None
    )


def _src(v: quality.Val, what: str = "") -> Source:
    return Source(v.accession, v.filed, "A", what or v.tag)


def _stage(engine: sqlite3.Connection, cik: str) -> tuple[str | None, str]:
    row = stage.confirmed(engine, cik)
    if row is None:
        return None, "stage unconfirmed (D-M04-7): both readings shown, not counted"
    return row[
        "confirmed"
    ], f"stage {stage.STAGE_NAMES.get(row['confirmed'], row['confirmed'])} (confirmed)"


def cash_text(cc: quality.CashConversion, stage_label: str) -> str:
    """What `eq_cash` says (state and routing)."""
    if cc.state == "ok":
        return f"3-year CFO/NI ≥ {quality.CFO_NI_WARN} — no flag"
    if cc.state == "warn":
        return f"< {quality.CFO_NI_WARN} with {stage_label}: persistence warning (D-M04-20)"
    if cc.state == "note":
        return f"< {quality.CFO_NI_WARN} with {stage_label}: a note, not a warning (D-M04-20)"
    if cc.state == "warn_or_note":
        return (
            f"< {quality.CFO_NI_WARN}; {stage_label} — warning if mature or decline, a note "
            "if introduction, growth or shake-out; not counted"
        )
    return cc.why


def write_signals(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str | None,
    q: quality.Quality,
    findings: list[estimates.Finding],
    recurrence: str,
    sp: special.Special | None,
    today: str,
    tracked: bool = False,
) -> dict[str, str]:
    """The nine Part 6 signals; caller owns the transaction. Returns signal → state."""
    out: dict[str, str] = {}
    common = dict(engine=engine, cik=cik, ticker=ticker, module_id=MODULE)
    fx = quality.Facts(engine, cik)
    latest = q.ends[-1] if q.ends else None
    f = fx.filing_of(latest) if latest else None
    base_src = [Source(f[0], f[1], "A", "annual report")] if f else []
    as_of = f[1] if f else today
    nr = restate.non_reliance(engine, cik, latest) if latest else None
    mark = f"; {nr.mark}" if nr else ""

    def missing(name: str, why: str, info=("ST",)) -> None:
        write_signal(
            **common,
            signal=name,
            as_of=as_of,
            method=mark.lstrip("; "),
            missing=why,
            info=info,
            sources=base_src,
        )
        out[name] = f"missing: {why}"

    if q.excluded:
        for name, info in (
            ("eq_cash", ("ST",)),
            ("eq_accruals", ("ST",)),
            ("contract_asset_gap", ("ST",)),
            ("deferred_rev_gap", ("ST",)),
            ("mscore", ("MY", "PT", "ST")),
            ("mscore_sgi1", ("MY", "PT", "ST")),
            ("misstate_f", ("MY", "PT", "ST")),
            ("estimate_share", ("ST",)),
            ("special_items", ("ST",)),
        ):
            missing(name, q.excluded, info)
        return out
    if not q.ends:
        for name in (
            "eq_cash",
            "eq_accruals",
            "contract_asset_gap",
            "deferred_rev_gap",
            "mscore",
            "mscore_sgi1",
            "misstate_f",
            "estimate_share",
            "special_items",
        ):
            missing(name, "no fiscal year of revenue or net income stored")
        return out

    # eq_cash and eq_accruals (D-M04-20)
    cc = q.cash
    srcs = [_src(v) for v in cc.sources] or base_src
    basis = (
        "; ".join(
            f"{y.label} NI {quality.money(y.ni.value)}M → operating {quality.money(y.basis_ni)}M "
            f"({', '.join(w for w, _ in y.items)})"
            for y in cc.years
            if y.operating
        )
        or "reported net income (no identified non-operating item above 25% of |NI|)"
    )
    years = ", ".join(
        f"{y.label} CFO {quality.money(y.cfo.value)}M / NI {quality.money(y.basis_ni)}M"
        for y in cc.years
        if y.cfo
    )
    method = f"3-year sums {years}; basis: {basis}; {cash_text(cc, q.stage_label)}{mark}"
    if cc.state == "missing":
        missing("eq_cash", cc.why)
    elif cc.state == "not_meaningful":
        write_signal(
            **common,
            signal="eq_cash",
            as_of=as_of,
            value_text="not_meaningful",
            method=f"{cc.why}; {method}",
            sources=srcs,
            info=("ST",),
        )
        out["eq_cash"] = "not_meaningful"
    else:
        write_signal(
            **common,
            signal="eq_cash",
            as_of=as_of,
            value=round(cc.ratio3, 4),
            value_text=cc.state,
            method=method,
            sources=srcs,
            info=("ST",),
        )
        out["eq_cash"] = f"{cc.ratio3:.2f} {cc.state}"
    if cc.accruals is not None:
        hist = ", ".join(f"{lb} {v:+.3f}" for lb, v in cc.accruals_hist)
        write_signal(
            **common,
            signal="eq_accruals",
            as_of=as_of,
            value=round(cc.accruals, 5),
            value_text=cc.accruals_text,
            sources=srcs,
            info=("ST",),
            method=f"(net income − CFO) ÷ average total assets, same basis as eq_cash; "
            f"own history {hist}; shown, no warning (D-M04-20){mark}",
        )
        out["eq_accruals"] = f"{cc.accruals:+.3f} {cc.accruals_text}"
    else:
        missing(
            "eq_accruals",
            cc.why
            if cc.state in ("missing", "not_meaningful")
            else "total assets missing for the accrual years",
        )

    # contract_asset_gap and deferred_rev_gap (S2.2)
    for name, g in (("contract_asset_gap", q.contract), ("deferred_rev_gap", q.deferred)):
        if g.state == "missing" or g.latest is None:
            missing(name, g.why or "no tag")
            continue
        r = g.latest
        text = "definition_changed" if r.state == "definition_changed" else g.state
        rs = "; ".join(
            f"{x.label} line {x.line_growth:+.1%} ({x.prior.tag} → {x.line.tag}), revenue "
            + (f"{x.revenue_growth:+.1%}" if x.revenue_growth is not None else "missing")
            + (f", gap {x.gap_pp:+.1f} pp" if x.gap_pp is not None else "")
            + ("" if x.state == "scored" else f" [{x.state.replace('_', ' ')}, not scored]")
            for x in g.readings[-3:]
        )
        kw = dict(value=round(r.gap_pp, 2)) if r.gap_pp is not None else {}
        write_signal(
            **common,
            signal=name,
            as_of=as_of,
            value_text=text,
            info=("ST",),
            sources=[_src(r.line), _src(r.prior)],
            method=f"fiscal-year readings: {rs}; {g.why or 'no flag'}{mark}",
            **kw,
        )
        out[name] = text

    # mscore, mscore_sgi1, misstate_f (screens, information in every timeframe)
    ms = q.latest_m
    every = ("MY", "PT", "ST")
    if ms is None or (ms.state == "incomplete"):
        missing("mscore", "incomplete: " + (ms.why if ms else "no fiscal year"), every)
        missing("mscore_sgi1", "incomplete: " + (ms.why if ms else "no fiscal year"), every)
    else:
        msrc = [_src(v) for v in ms.inputs.used] or base_src
        comp = ", ".join(f"{k} {v:.3f}" for k, v in ms.components.items())
        subs = ms.inputs.method()
        m_method = (
            f"Beneish M {ms.label} (ACCR from cash flow); {comp}"
            + (f"; {subs}" if subs else "")
            + f"; review only when SGI = 1 above "
            f"{quality.M_CUT} (D-M04-14){mark}"
        )
        if ms.state == "not_meaningful":
            write_signal(
                **common,
                signal="mscore",
                as_of=as_of,
                value_text="not_meaningful",
                method=f"{ms.why}; {m_method}",
                sources=msrc,
                info=every,
            )
            write_signal(
                **common,
                signal="mscore_sgi1",
                as_of=as_of,
                value_text="not_meaningful",
                method=ms.why,
                sources=msrc,
                info=every,
            )
            out["mscore"] = out["mscore_sgi1"] = "not_meaningful"
        else:
            write_signal(
                **common,
                signal="mscore",
                as_of=as_of,
                value=round(ms.m, 4),
                value_text=ms.reading,
                method=m_method,
                sources=msrc,
                info=every,
            )
            write_signal(
                **common,
                signal="mscore_sgi1",
                as_of=as_of,
                value=round(ms.m_sgi1, 4),
                value_text="above_cut" if ms.m_sgi1 > quality.M_CUT else "below_cut",
                method=f"M with SGI = 1 (SGI {ms.components['SGI']:.3f}); {ms.label}{mark}",
                sources=msrc,
                info=every,
            )
            out["mscore"] = f"{ms.m:.2f} {ms.reading}"
            out["mscore_sgi1"] = f"{ms.m_sgi1:.2f}"
    fs = q.latest_f
    if fs is None or fs.state == "incomplete":
        missing("misstate_f", "incomplete: " + (fs.why if fs else "no fiscal year"), every)
    else:
        fsrc = [_src(v) for v in fs.inputs.used] or base_src
        if fs.state == "not_meaningful":
            write_signal(
                **common,
                signal="misstate_f",
                as_of=as_of,
                value_text="not_meaningful",
                method=fs.why,
                sources=fsrc,
                info=every,
            )
            out["misstate_f"] = "not_meaningful"
        else:
            comp = ", ".join(f"{k} {v:.3f}" for k, v in fs.components.items())
            subs = fs.inputs.method()
            write_signal(
                **common,
                signal="misstate_f",
                as_of=as_of,
                value=round(fs.score, 4),
                value_text=fs.band,
                sources=fsrc,
                info=every,
                method=(
                    f"approximation: Dechow et al. (2011) Model 1, Compustat "
                    f"coefficients; {fs.label}; {comp}"
                    + (f"; {subs}" if subs else "")
                    + f"; bands > 1.00 and > 2.45 shown, never a trigger "
                    f"(D-M04-14){mark}"
                ),
            )
            out["misstate_f"] = f"{fs.score:.2f} {fs.band}"

    # estimate_share (D-M04-17, -18)
    if tracked:
        missing("estimate_share", "tracked tier, no documents (D-M04-80)")
    else:
        mine = [x for x in findings if f is not None and x.accession == f[0]]
        if mine:
            acc = mine[0].accession
            top = max(mine, key=lambda x: abs(x.share or 0))
            text = top.band + ("+recurring" if recurrence else "")
            kw = dict(value=round(top.share * 100, 3)) if top.share is not None else {}
            write_signal(
                **common,
                signal="estimate_share",
                as_of=top.filed,
                value_text=text,
                info=("ST",),
                sources=[Source(x.accession, x.filed, "A", "estimate sentence") for x in mine],
                method=(
                    f"{len(mine)} estimate sentence(s) in {top.form} {acc}; largest "
                    f"{quality.money(top.amount)}M {top.basis.replace('_', '-')} for "
                    f"{top.fiscal_label} ÷ {top.denominator_what or top.why}"
                    + (
                        f"; recurrence: {recurrence} in 3 disclosures (D-M04-17)"
                        if recurrence
                        else ""
                    )
                    + f"; bands < 10% note, 10–25% watch, "
                    f"≥ 25% elevated (D-M04-17){mark}"
                ),
                **kw,
            )
            out["estimate_share"] = text
        elif f is not None and _text_stored(engine, f[0]):
            write_signal(
                **common,
                signal="estimate_share",
                as_of=as_of,
                value_text="none",
                method=f"no estimate-change sentence with an amount in the latest annual "
                f"report {f[0]}{mark}",
                sources=base_src,
                info=("ST",),
            )
            out["estimate_share"] = "none"
        else:
            missing(
                "estimate_share",
                "latest annual report text not stored"
                + (
                    f" ({len(findings)} sentence(s) in earlier reports, on the tab)"
                    if findings
                    else ""
                ),
            )

    # special_items (D-M04-19, -94): value = cumulative counted charges ÷ cumulative
    # operating income; text warn | none | not_meaningful (short history as stated)
    if sp is None or sp.state == "missing":
        missing("special_items", sp.why if sp else "not computed")
    else:
        yrs = "; ".join(f"{y.label}: {y.source}" for y in sp.years)
        ssrc = [
            Source(a, d, "A", w)
            for y in sp.years
            for w, a in [(w, a) for w, _, a in y.tags] + [(p, a) for p, _, a, _ in y.stated]
            if (d := _filed(engine, a))
        ] or base_src
        kw = dict(value=round(sp.ratio, 4)) if sp.ratio is not None else {}
        write_signal(
            **common,
            signal="special_items",
            as_of=as_of,
            value_text=sp.state,
            info=("ST",),
            sources=ssrc,
            method=(
                f"years counted {sp.count} of {len(sp.years)} (an amount needed: tag or stated "
                f"$; warn ≥ {special.WARN_YEARS} and ≥ {special.SIZE_MIN:.0%} of operating "
                f"income, D-M04-94); {yrs}; cumulative ÷ operating income "
                + (
                    f"{sp.ratio:.1%}"
                    if sp.ratio is not None
                    else f"{sp.ratio_why} (tagged years {sp.tagged_years})"
                )
                + ("; non-GAAP gap quoted on the tab" if sp.non_gaap else "")
                + f"{mark}"
            ),
            **kw,
        )
        out["special_items"] = sp.state
    return out


def _filed(engine: sqlite3.Connection, accession: str) -> str | None:
    r = engine.execute(
        "SELECT filed FROM fact WHERE accession = ? LIMIT 1", (accession,)
    ).fetchone()
    return r[0] if r else None


def _text_stored(engine: sqlite3.Connection, accession: str) -> bool:
    """The annual report's text was in the corpus at this pass (`_mark_text`)."""
    return bool(
        engine.execute(
            "SELECT 1 FROM refresh_state WHERE name = ?", (f"m04_quality_text:{accession}",)
        ).fetchone()
    )


def _mark_text(engine: sqlite3.Connection, corpus, cik: str, now_iso: str) -> None:
    if corpus is None:
        return
    for a in estimates.annual_reports(engine, corpus, cik):
        if corpus.execute(
            "SELECT 1 FROM document WHERE accession = ? LIMIT 1", (a.accession,)
        ).fetchone():
            engine.execute(
                "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, "
                "NULL) ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at",
                (f"m04_quality_text:{a.accession}", "estimates.scan", now_iso),
            )


def _n(x: float) -> str:
    """Two decimals with a true minus sign (as the docs write scores: −1.75)."""
    return f"{x:.2f}".replace("-", "−")


def mscore_payload(ticker: str | None, ms: quality.MScore) -> dict:
    return {
        "ticker": ticker,
        "fiscal_label": ms.label,
        "period_end": ms.end,
        "accession": ms.accession,
        "filed": ms.filed,
        "m": round(ms.m, 3),
        "m_sgi1": round(ms.m_sgi1, 3),
        "components": {k: round(v, 3) for k, v in ms.components.items()},
        "inputs": quality.inputs_text(ms.inputs.used),
        "substitutions": ms.inputs.method(),
    }


def estimate_payload(ticker: str | None, f: estimates.Finding, recurrence: str) -> dict:
    return {
        "ticker": ticker,
        "accession": f.accession,
        "form": f.form,
        "filed": f.filed,
        "doc": f.doc_ref,
        "fiscal_label": f.fiscal_label,
        "kind": f.kind,
        "amount": f.amount,
        "basis": f.basis,
        "denominator": f.denominator,
        "denominator_what": f.denominator_what,
        "share": f.share,
        "band": f.band,
        "quote": f.quote,
        "recurrence": recurrence,
    }


def propose(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str | None,
    q: quality.Quality,
    findings: list[estimates.Finding],
    recurrence: str,
    now: datetime,
    first: bool,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    live = set()
    for ms in q.mscores:
        if ms.reading != "review":
            continue
        key = f"{cik}:{ms.end}"
        live.add(key)
        status = queue.propose(
            engine,
            "m04_mscore",
            key,
            f"{ticker or cik} {ms.label}: Beneish M with SGI = 1 is {_n(ms.m_sgi1)}, above "
            f"{_n(quality.M_CUT)} (raw M {_n(ms.m)}; screen, D-M04-14)",
            mscore_payload(ticker, ms),
            now,
            cik=cik,
            baseline=first,
            filed=ms.filed,
        )
        counts[f"m04_mscore {status}"] = counts.get(f"m04_mscore {status}", 0) + 1
    counts["m04_mscore withdrawn"] = queue.withdraw_stale(
        engine, "m04_mscore", cik, live, now, "recomputed: M with SGI = 1 no longer above −1.78"
    )
    live = set()
    answered = {
        (r["accession"], r["start_offset"])
        for r in engine.execute(
            "SELECT accession, start_offset FROM estimate_change WHERE cik = ? AND owner_outcome "
            "IS NOT NULL",
            (cik,),
        )
    }
    for f in findings:
        if f.band not in ("watch", "elevated") or (f.accession, f.start) in answered:
            continue
        live.add(f.key)
        status = queue.propose(
            engine,
            "m04_estimate",
            f.key,
            f"{ticker or cik} {f.form} filed {f.filed}: estimate change "
            f"{quality.money(f.amount)}M ({f.basis.replace('_', '-')}) = {f.share:+.1%} of "
            f"{f.fiscal_label} "
            + ("net income" if f.basis == "after_tax" else "operating or pretax income")
            + f" → {f.band} (D-M04-17)",
            estimate_payload(ticker, f, recurrence),
            now,
            cik=cik,
            baseline=first,
            filed=f.filed,
        )
        counts[f"m04_estimate {status}"] = counts.get(f"m04_estimate {status}", 0) + 1
        row = engine.execute(
            "SELECT item_id FROM m04_proposal WHERE prop_key = ?", (f"m04_estimate:{f.key}",)
        ).fetchone()
        if row and row["item_id"]:
            engine.execute(
                "UPDATE estimate_change SET item_id = ? WHERE cik = ? AND accession = ? AND "
                "start_offset = ?",
                (row["item_id"], cik, f.accession, f.start),
            )
    counts["m04_estimate withdrawn"] = queue.withdraw_stale(
        engine,
        "m04_estimate",
        cik,
        live,
        now,
        "recomputed: the sentence is no longer found or its share is below 10%",
    )
    return {k: v for k, v in counts.items() if v}


def _tx(engine: sqlite3.Connection, fn: Callable, *args, **kw):
    engine.execute("BEGIN")
    try:
        out = fn(*args, **kw)
        engine.execute("COMMIT")
        return out
    except Exception:
        engine.execute("ROLLBACK")
        raise


def company_quality(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    ticker: str,
    cik: str,
    now: datetime,
    *,
    mf: models.ModelFile | None = None,
    queue_items: bool = True,
    tracked: bool = False,
    signals: bool = True,
) -> CompanyQuality:
    cq = CompanyQuality(ticker, cik)
    st, st_label = _stage(engine, cik)
    cq.q = quality.compute(engine, cik, ticker, models=mf, stage=st, stage_label=st_label)
    if not cq.q.excluded and not tracked:
        cq.findings = estimates.scan(engine, corpus, cik)
        cq.recurrence = estimates.recurrence(cq.findings)
    if not cq.q.excluded:
        cq.special = special.compute(engine, None if tracked else corpus, cik)
    first = first_scan(engine, cik)
    at = iso(now)

    def work():
        estimates.store(engine, cq.findings, cik, at, first)
        if cq.special is not None:
            special.store(engine, cik, cq.special, at)
        _mark_text(engine, None if tracked else corpus, cik, at)
        if signals:
            cq.signals = write_signals(
                engine,
                cik,
                ticker,
                cq.q,
                cq.findings,
                cq.recurrence,
                cq.special,
                now.date().isoformat(),
                tracked,
            )
        if queue_items and not cq.q.excluded:
            cq.proposals = propose(
                engine, cik, ticker, cq.q, cq.findings, cq.recurrence, now, first
            )
        if first:
            engine.execute(
                "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES "
                "(?, 'quality_step', ?, ?) ON CONFLICT (name) DO NOTHING",
                (BASELINE_STATE.format(cik=cik), at, json.dumps({"estimates": len(cq.findings)})),
            )

    _tx(engine, work)
    return cq


def quality_pass(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    companies: dict[str, str],
    now: datetime,
) -> QualityPass:
    """Part 6 for every covered company (0 requests). One company's error does not stop the
    others."""
    scope = set(full_scope(engine, companies).values())
    mf = models.load_safe()
    out: dict[str, CompanyQuality] = {}
    for ticker, cik in sorted(companies.items()):
        try:
            out[ticker] = company_quality(
                engine,
                corpus,
                ticker,
                cik,
                now,
                mf=mf,
                queue_items=cik in scope,
                tracked=cik not in scope,
            )
        except Exception as e:
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            out[ticker] = CompanyQuality(ticker, cik, error=f"{type(e).__name__}: {e}")
    flushed = _tx(engine, queue.flush_overflow, engine, now)
    return QualityPass(out, flushed)


def run_local_part(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    companies: dict[str, str],
    now: datetime,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    t0 = clock()
    qp = quality_pass(engine, corpus, companies, now)
    return local_lines(qp, clock() - t0)


def local_lines(qp: QualityPass, seconds: float = 0.0) -> list[str]:
    props: dict[str, int] = {}
    for c in qp.companies.values():
        for k, v in c.proposals.items():
            props[k] = props.get(k, 0) + v
    est = sum(len(c.findings) for c in qp.companies.values())
    lines = [
        f"M04 earnings quality — local pass (Part 6, 0 SEC requests) ({seconds:.1f} s): "
        f"{len(qp.companies)} companies, {est} estimate sentence(s); items: "
        + (", ".join(f"{k} {v}" for k, v in sorted(props.items())) or "none")
        + f"; {qp.flushed} overflow item(s) flushed"
    ]
    lines += [f"  {c.ticker}: error — {c.error}" for c in qp.companies.values() if c.error]
    return lines
