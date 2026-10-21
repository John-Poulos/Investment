"""M08 Part 1 inside the refresh and the `value` script (D-M08-1…12; 0 requests).

`valuation_pass` (local; the refresh hooks it after the M07 steps and before M09, MVP_PLAN
local-step order, so closes, the gate, filing status and `cvd_state` are current):

- **Row cadence (D-M08-8):** one row set per completed week — the close of the newest
  completed week (`technicals.bars.Calendar`, M09's week) — plus one at the newest stored
  close when a periodic report was filed after that week's close. A rerun in the same week
  updates the same rows; the Valuation tab computes today's line live (nothing written).
- Per covered name (watchlist, promoted and tracked): every standard row (D32), the
  cyclical flag, the headline (`route`), own-history percentiles from calendar quarter-ends
  on first-filed values (D-M08-2), the peer percentile of the headline (shown only), and the
  "value-trap risk" note (rule 9). One short write transaction per name (LESSONS).
- A missing row never overwrites a stored value of the same `as_of`.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from engine import m01_rules
from engine.calls import calendar
from engine.financials import distress, peers, shares
from engine.financials import models as models_mod
from engine.financials import nep as nep_mod
from engine.financials import stage as stage_mod
from engine.moneyflow.periods import fiscal_year_end
from engine.prices.store import BENCHMARK
from engine.sec.identity import normalize_cik
from engine.signals import Source, write_signal
from engine.technicals import bars
from engine.valuation import cyclical, estimates, pctile, route
from engine.valuation import peg as peg_mod
from engine.valuation.asof import Known, latest_close_day
from engine.valuation.measures import (
    FWD,
    LABELS,
    MODULE,
    ROW_KEYS,
    STANDARD_KEYS,
    Measure,
    Snapshot,
    fmt,
    snapshot,
)
from engine.valuation.params import Params

HISTORY_FROM = "2009-01-01"  # XBRL starts 2009–2011 (M04 failure modes)
INFO_ALL = ("MY", "PT", "ST")
PERIODIC = (
    "10-K",
    "10-Q",
    "10-KT",
    "10-QT",
    "20-F",
    "40-F",
    "10-K/A",
    "10-Q/A",
    "20-F/A",
    "40-F/A",
)
TRAP_STATES = ("STRUCTURAL_DECLINE", "CYCLE_PLUS_DAMAGE")


@dataclass
class OutRow:
    signal: str
    as_of: str
    method: str
    value: float | None = None
    text: str | None = None
    missing: str | None = None
    sources: list[Source] = field(default_factory=list)
    info: tuple[str, ...] = INFO_ALL


@dataclass
class NameResult:
    ticker: str
    cik: str
    day: str  # requested date
    as_of: str  # the close date used
    snap: Snapshot
    flag: cyclical.Flag | None = None
    route: route.Route | None = None
    headline: route.Headline | None = None
    pctiles: dict[str, pctile.Pctile] = field(default_factory=dict)
    peer: pctile.Peer | None = None
    history: pctile.History | None = None
    m04: m01_rules.M04Rows | None = None
    trap: str = ""
    notes: list[str] = field(default_factory=list)  # labels added to every row
    rows: list[OutRow] = field(default_factory=list)
    # Part 2: estimates, forward P/E, PEG, the walk-down window
    est: estimates.Reading | None = None
    next_report: calendar.NextReport | None = None
    walk: tuple[bool | None, str] = (None, "")
    peg: peg_mod.Peg | None = None
    cagr: str = ""
    blocked: str = ""

    @property
    def headline_pctile(self) -> pctile.Pctile | None:
        if self.headline is None or self.headline.measure is None:
            return None
        return self.pctiles.get(self.headline.measure)


def _blocked(tag: models_mod.ModelTag | None) -> str:
    if tag is None:
        return ""
    if tag.tag == "fund":
        return "not applicable (fund, D-M04-8)"
    if tag.tag == "spac_shell":
        return f"shell period (before {tag.before})" if tag.before else "shell (spac_shell tag)"
    return ""


def first_bar(engine: sqlite3.Connection, cik: str) -> str | None:
    syms = shares.price_symbols(engine, cik)
    if not syms:
        return None
    marks = ",".join("?" * len(syms))
    r = engine.execute(
        f"SELECT min(date) FROM price_bar WHERE symbol IN ({marks}) AND close IS NOT NULL", syms
    ).fetchone()
    return r[0] if r else None


def history(k: Known, before: str, p: Params, *, fye, mf, ticker, asset_treasury) -> pctile.History:
    """Own-history quarter-end values on first-filed facts (D-M08-2)."""
    h = pctile.History()
    start = first_bar(k.engine, k.cik)
    if start is None:
        return h
    for q in pctile.quarter_ends(max(start, HISTORY_FROM), before):
        blocked = _blocked(mf.for_company(k.cik, ticker, q))
        if blocked:
            continue
        s = snapshot(
            k,
            q,
            first=True,
            fye=fye,
            asset_treasury=asset_treasury,
            nep_swing=p.nep_swing_pp,
            nep_min_years=p.nep_min_years,
            tol=p.close_tolerance_days,
        )
        if s.missing:
            continue
        h.quarters += 1
        for key, m in s.measures.items():
            h.add(key, q, m.value, m.text)
    return h


def peer_values(engine, cik: str, key: str, day: str, today: str, p: Params) -> tuple[list, int]:
    """[(name, value)] of `key` at `day` for confirmed SEC peers with stored prices."""
    vals, confirmed = [], 0
    for r in peers.confirmed_peers(engine, cik):
        if not r["cik"]:
            continue
        confirmed += 1
        if not shares.has_prices(engine, r["cik"]):
            continue
        pk = Known(engine, r["cik"], today)
        s = snapshot(
            pk,
            day,
            fye=fiscal_year_end(engine, r["cik"]),
            nep_swing=p.nep_swing_pp,
            nep_min_years=p.nep_min_years,
            tol=p.close_tolerance_days,
        )
        if not s.missing and s.m(key).value is not None:
            vals.append((r["name"], s.m(key).value))
    return vals, confirmed


def evaluate(
    engine: sqlite3.Connection,
    ticker: str,
    cik: str,
    day: str,
    today: str,
    p: Params,
    mf: models_mod.ModelFile,
    *,
    with_history: bool = True,
    with_peers: bool = True,
    est_upto: str | None = None,
) -> NameResult:
    """Every M08 reading for one company at the close on or before `day`. Estimates are the
    newest snapshot fetched by the close date (rule 1), or by `est_upto` (the live tab)."""
    norm = normalize_cik(cik) or cik
    k = Known(engine, norm, today)
    fye = fiscal_year_end(engine, norm)
    tag_now, tag_text = models_mod.route(engine, mf, norm, ticker)
    tag_day = mf.for_company(norm, ticker, day)
    blocked = _blocked(tag_day)
    treasury = tag_now == "asset_treasury"
    snap = snapshot(
        k,
        day,
        fye=fye,
        blocked=blocked,
        asset_treasury=treasury,
        nep_swing=p.nep_swing_pp,
        nep_min_years=p.nep_min_years,
        tol=p.close_tolerance_days,
    )
    as_of = snap.close.day if snap.close is not None else day
    r = NameResult(ticker, norm, day, as_of, snap)
    r.m04 = m01_rules.read_m04(engine, norm)
    ov = p.override(norm, ticker)
    ys = nep_mod.years(k.view(as_of), fye)
    r.flag = cyclical.flag(ys, p, ov)
    conf = stage_mod.confirmed(engine, norm)
    stage_text = distress.stage_label(engine, norm)[0]
    r.route = route.choose(
        stage=conf["confirmed"] if conf else None,
        stage_text=stage_text,
        cyclical=r.flag.cyclical,
        tag=tag_now,
        tag_text=tag_text,
        override_headline=ov.headline if ov else None,
        override_reason=ov.reason if ov else "",
    )
    r.headline = route.headline(r.route, snap)
    if with_history and not snap.missing:
        r.history = history(k, as_of, p, fye=fye, mf=mf, ticker=ticker, asset_treasury=treasury)
    h = r.history or pctile.History()
    for key, m in snap.measures.items():
        r.pctiles[key] = h.pctile(key, m.value, p.own_min_points)
    hk = r.headline.measure
    if hk and with_peers and r.headline.value is not None:
        vals, n = peer_values(engine, norm, hk, as_of, today, p)
        r.peer = pctile.peer(r.headline.value, vals, p.peer_min, n)
    # labels (rules 5, 9, 10)
    hp = r.headline_pctile
    if hp is not None and hp.value is not None and hp.value <= p.value_trap_pctile:
        why = []
        if r.m04.gate_state == "fail":
            why.append("survival gate fail")
        if r.m04.cvd_state in TRAP_STATES:
            why.append(f"CvD {r.m04.cvd_state}")
        if why:
            r.trap = (
                f"value-trap risk: headline own pctile {hp.value:.0f} ≤ "
                f"{p.value_trap_pctile:g}† with {' and '.join(why)} (cheap is not a buy; "
                "rule 9, D-M08-11)"
            )
    f = r.m04.filing
    if f is not None and f.text in ("stale", "overdue"):
        r.notes.append(f"as of {snap.twelve or 'the last report'}; M04 filing_status {f.text}")
    part2(r, engine, k, p, blocked=blocked, treasury=treasury, est_upto=est_upto)
    r.rows = build_rows(r, p)
    return r


def part2(r: NameResult, engine, k: Known, p: Params, *, blocked, treasury, est_upto) -> None:
    """Estimates, forward P/E, PEG and the walk-down window (Part 2; D-M08-4…7, -14…17)."""
    s = r.snap
    r.blocked = blocked
    if s.missing:
        s.measures[FWD] = Measure(FWD, missing=s.missing)
    if blocked:
        return
    pts = k.view(r.as_of)
    fy_ends = pts("net_income", "FY")
    reported = max(fy_ends) if fy_ends else None
    r.est = estimates.reading(engine, r.cik, r.as_of, p, upto=est_upto or r.as_of,
                              reported_fy_end=reported)  # fmt: skip
    r.next_report = calendar.next_report(engine, r.cik, r.as_of)
    r.walk = calendar.walk_down(r.next_report, r.as_of, p.walk_down_days)
    fy1, fy2 = r.est.fy1, r.est.fy2
    if not s.missing:
        base = list(getattr(s.cap, "sources", None) or [])
        fwd = peg_mod.forward_pe(s.close.value, fy1, treasury=treasury,
                                 sources=[*base, *r.est.sources])  # fmt: skip
        if r.est.missing:
            fwd.missing = r.est.missing
        s.measures[FWD] = fwd
    dates = estimates.snapshot_dates(engine, r.cik)
    since = f"own snapshots since {dates[0]}" if dates else "no snapshots yet"
    r.pctiles[FWD] = pctile.Pctile(
        None, 0, missing=f"no quarter-end history of forward EPS ({since}; deferred)"
    )
    if s.missing:
        return
    r.peg = peg_mod.peg(
        fwd=s.m(FWD),
        fy1=fy1,
        fy2=fy2,
        ttm_pe=s.m("val_pe_ttm"),
        cyclical=bool(r.flag and r.flag.cyclical),
        treasury=treasury,
        cap_pct=p.peg_growth_cap_pct,
        have_snapshot=r.est.snap is not None,
    )
    r.cagr = peg_mod.trailing_cagr(k, pts, r.as_of)


def _pe_note(r: NameResult) -> str:
    if not r.flag or not r.flag.cyclical:
        return ""
    note = "trailing P/E inverts at cycle extremes (cyclical flag, rule 5)"
    if r.m04 and r.m04.cvd_state == "CYCLICAL_TROUGH":
        note += "; CvD CYCLICAL_TROUGH: a high trailing P/E reads trough earnings, not expensive"
    return note


def build_rows(r: NameResult, p: Params) -> list[OutRow]:
    s, ver = r.snap, f"M08 {p.version}"
    common = [x for x in (*r.notes, ver) if x]
    out = []
    for key in ROW_KEYS:
        m = s.m(key)
        pc = r.pctiles.get(key)
        bits = [f"{LABELS[key]} {m.shown}"]
        if m.detail:
            bits.append(m.detail)
        if key == "val_pe_ttm" and (note := _pe_note(r)):
            bits.append(note)
        if key == FWD and r.est is not None:
            bits += [*r.est.notes, r.walk[1]] if r.walk[1] else list(r.est.notes)
        if key in ("val_ev_nebit", "val_p_neps") and s.nep is not None:
            bits.append(s.nep.text())
        if pc is not None:
            bits.append(pc.text())
        if r.headline and r.headline.measure == key:
            bits.append("the headline: its weight is carried by valuation_multiple")
        bits += common
        method = "; ".join(bits)
        if m.missing:
            out.append(OutRow(key, r.as_of, method, missing=m.missing, sources=m.sources))
        else:
            out.append(OutRow(key, r.as_of, method, m.value, m.text, sources=m.sources))
    # the headline
    hl, rt = r.headline, r.route
    others = " · ".join(f"{LABELS[k_].split(' (')[0]} {s.m(k_).shown}" for k_ in STANDARD_KEYS)
    bits = [hl.method]
    if rt.beside and rt.beside in s.measures:
        bits.append(f"beside: {LABELS[rt.beside]} {s.m(rt.beside).shown}")
    bits.append(f"all measures: {others}")
    if r.flag:
        bits.append(r.flag.text())
    if hl.measure in ("val_ev_nebit", "val_p_neps") and s.nep is not None:
        bits.append(s.nep.text())
    if s.cap is not None and getattr(s.cap, "text", ""):
        bits.append(s.cap.text)
    if s.ev_text:
        bits.append(s.ev_text)
    elif s.ev_missing:
        bits.append(f"EV incomplete: {s.ev_missing}")
    if r.trap:
        bits.append(r.trap)
    bits += common
    info = INFO_ALL if not rt.scored else ("ST",)
    srcs = s.m(hl.measure).sources if hl.measure else []
    method = "; ".join(bits)
    if hl.missing:
        out.append(
            OutRow(
                "valuation_multiple", r.as_of, method, missing=hl.missing, sources=srcs, info=info
            )
        )
    elif hl.value is not None or srcs:
        out.append(
            OutRow(
                "valuation_multiple", r.as_of, method, hl.value, hl.text, sources=srcs, info=info
            )
        )
    else:
        # a code with no deciding number (stage_unconfirmed, not_applicable): the inputs read
        # are the close and shares, or the owner's model tag (grade B, D14)
        src = list(getattr(s.cap, "sources", None) or [])
        if not src and rt.code == "not_applicable":
            src = [Source("config/company_models.toml", r.as_of, "B", "model tag")]
        if src:
            out.append(
                OutRow("valuation_multiple", r.as_of, method, None, hl.text, sources=src, info=info)
            )
        else:
            out.append(
                OutRow(
                    "valuation_multiple",
                    r.as_of,
                    method,
                    missing=s.missing or f"{hl.text}: no close or shares",
                    info=info,
                )
            )
    # its percentile
    hp = r.headline_pctile
    pbits = [f"headline {LABELS[hl.measure]}" if hl.measure else "no headline measure"]
    if hp is not None:
        pbits.append(hp.text())
    if r.peer is not None:
        pbits.append(r.peer.text())
    if r.trap:
        pbits.append(r.trap)
    pbits.append("a high percentile is context, never a sell signal (D16)")
    pbits += common
    pm = "; ".join(pbits)
    if hp is not None and hp.value is not None:
        out.append(
            OutRow(
                "valuation_pctile", r.as_of, pm, round(hp.value, 1), None, sources=srcs, info=info
            )
        )
    else:
        why = hp.missing if hp is not None else (hl.text or hl.missing or "no headline measure")
        if hp is not None and hp.missing.startswith("no current value"):
            why = f"headline {hl.text or hl.missing or 'has no value'}"
        out.append(OutRow("valuation_pctile", r.as_of, pm, missing=why, sources=srcs, info=info))
    out += part2_rows(r, p, common)
    return out


def est_line(r: NameResult) -> list[str]:
    """The revision detail of FY1 and FY2 (shared by `est_revision` and the script)."""
    e = r.est
    if e is None:
        return []
    bits = [h.text() for h in (e.fy1, e.fy2) if h is not None]
    if e.snap is not None and e.fy1 is None:
        bits.append("no fiscal-year estimate after the newest reported fiscal year")
    return [*bits, e.coverage(), *e.notes]


def part2_rows(r: NameResult, p: Params, common: list[str]) -> list[OutRow]:
    """`peg` and `est_revision` (Part 2). Grade B: vendor consensus (D14)."""
    out: list[OutRow] = []
    s, walk = r.snap, r.walk[1]
    if r.blocked:
        for sig in ("peg", "est_revision"):
            out.append(OutRow(sig, r.as_of, "; ".join(common), missing=r.blocked))
        return out
    e = r.est
    # PEG (rule 6)
    pg = r.peg
    if pg is None:
        out.append(OutRow("peg", r.as_of, "; ".join(common), missing=s.missing or "no close"))
    else:
        bits = [f"PEG {pg.shown}", *pg.detail]
        if r.cagr:
            bits.append(r.cagr)
        if pg.codes and "cyclical" in pg.codes and r.flag is not None:
            bits.append(r.flag.text())
        if not pg.scored:
            ev_s, pc = s.m("val_ev_sales"), r.pctiles.get("val_ev_sales")
            bits.append(
                f"R6 sales fallback: EV/Sales {ev_s.shown}" + (f" ({pc.text()})" if pc else "")
            )
        bits += ["vendor basis (non-GAAP consensus)", "rough ranking only (S-new-M08-6)"]
        if walk:
            bits.append(walk)
        bits += common
        srcs = [*(getattr(s.cap, "sources", None) or []), *(e.sources if e else [])]
        info = ("ST",) if pg.scored else INFO_ALL
        method = "; ".join(bits)
        if pg.missing:
            out.append(OutRow("peg", r.as_of, method, missing=pg.missing, sources=srcs))
        elif not srcs:
            out.append(OutRow("peg", r.as_of, method, missing=f"{pg.text}: no inputs stored"))
        else:
            out.append(OutRow("peg", r.as_of, method, pg.value, pg.text, sources=srcs, info=info))
    # est_revision (R15; rule 7): FY1 30-day revision, every timeframe (MY weight low, M01)
    bits = [
        f"FY1 30-day revision (R15); up ≥ +{p.flat_band_pct:g}%, down ≤ −{p.flat_band_pct:g}%, "
        "flat between† (D-M08-15)",
        *est_line(r),
        "vendor basis",
    ]
    if walk:
        bits.append(walk)
    bits += ["MY weight low (M01)", *common]
    method = "; ".join(bits)
    if e is None or e.missing:
        why = e.missing if e is not None else "no estimate reading"
        out.append(OutRow("est_revision", r.as_of, method, missing=why, info=()))
    elif e.fy1 is None:
        out.append(
            OutRow(
                "est_revision",
                r.as_of,
                method,
                missing="no FY1 estimate in the snapshot "
                f"{e.snap.snapshot_date} (no coverage of the coming fiscal year)",
                sources=e.sources,
                info=(),
            )  # fmt: skip
        )
    else:
        rev = e.fy1.rev30
        if rev.missing:
            out.append(
                OutRow(
                    "est_revision",
                    r.as_of,
                    method,
                    missing=f"FY1 30-day revision: {rev.missing}",
                    sources=e.sources,
                    info=(),
                )  # fmt: skip
            )
        elif rev.value is None:
            out.append(
                OutRow(
                    "est_revision", r.as_of, method, None, estimates.NM, sources=e.sources, info=()
                )  # fmt: skip
            )
        else:
            out.append(
                OutRow(
                    "est_revision",
                    r.as_of,
                    method,
                    round(rev.value, 4),
                    estimates.band(rev, p),
                    sources=e.sources,
                    info=(),
                )  # fmt: skip
            )
    return out


# --- the pass ----------------------------------------------------------------------------------


@dataclass
class ValPass:
    results: dict[str, list[NameResult]]
    week: str
    written: int = 0
    kept: int = 0
    errors: dict[str, str] = field(default_factory=dict)
    params_note: str = ""


def _has_value(engine: sqlite3.Connection, cik: str, signal: str, as_of: str) -> bool:
    return (
        engine.execute(
            "SELECT 1 FROM signal WHERE cik = ? AND module_id = 'M08' AND signal = ? AND as_of = ? "
            "AND (value IS NOT NULL OR value_text IS NOT NULL) LIMIT 1",
            (cik, signal, as_of),
        ).fetchone()
        is not None
    )


def write_rows(engine: sqlite3.Connection, r: NameResult) -> tuple[int, int]:
    """(rows written, missing rows kept back). Caller owns the transaction."""
    n = kept = 0
    for o in r.rows:
        common = dict(
            engine=engine,
            cik=r.cik,
            ticker=r.ticker,
            module_id=MODULE,
            signal=o.signal,
            as_of=o.as_of,
            info=o.info,
            sources=o.sources,
        )
        if o.missing is not None:
            # only a stale price store keeps a stored value (M09's rule, D-M09-13); a missing
            # row computed from stored facts replaces it (live check 2: AVGO's stale P/E and
            # GFS's EV rows from the earlier rules were kept)
            if o.missing.startswith("no close within") and _has_value(
                engine, r.cik, o.signal, o.as_of
            ):
                kept += 1
                continue
            n += write_signal(**common, method=o.method, missing=o.missing)
        else:
            n += write_signal(**common, method=o.method, value=o.value, value_text=o.text)
    return n, kept


def row_days(engine: sqlite3.Connection, cik: str, week: str, today: str) -> list[str]:
    """The completed week's close date, plus the newest close when a periodic report was
    filed after it (D-M08-8)."""
    days = [week]
    marks = ",".join("?" * len(PERIODIC))
    f = engine.execute(
        f"SELECT max(filed) FROM filing WHERE cik = ? AND form IN ({marks})", (cik, *PERIODIC)
    ).fetchone()[0]
    if f and f > week:
        last = latest_close_day(engine, cik, today)
        if last and last >= f:
            days.append(last)
    return days


def valuation_pass(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    params: Params | None = None,
    mf: models_mod.ModelFile | None = None,
    with_peers: bool = True,
) -> ValPass:
    """M08 for every covered name (0 requests); one name's error does not stop the others."""
    p = params or Params()
    mf = mf if mf is not None else models_mod.load_safe()
    today = bars.eastern_today(now)
    week = bars.Calendar.load(engine, today).expected_as_of()
    vp = ValPass({}, week)
    for ticker, cik in sorted(companies.items()):
        if not cik or ticker.upper() == BENCHMARK:
            continue
        norm = normalize_cik(cik) or cik
        try:
            results = [
                evaluate(engine, ticker, norm, d, today.isoformat(), p, mf, with_peers=with_peers)
                for d in row_days(engine, norm, week, today.isoformat())
            ]
            engine.execute("BEGIN")
            try:
                for r in results:
                    n, kept = write_rows(engine, r)
                    vp.written += n
                    vp.kept += kept
                engine.execute("COMMIT")
            except Exception:
                engine.execute("ROLLBACK")
                raise
            vp.results[ticker] = results
        except Exception as e:
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            vp.errors[ticker] = f"{type(e).__name__}: {e}"
    return vp


def line(r: NameResult) -> str:
    """One line per name for the script and the run report."""
    s, hl = r.snap, r.headline
    if hl.value is not None:
        head = f"{LABELS[hl.measure].split(' (')[0]} {fmt(hl.measure, hl.value)}"
        if hl.measure == "val_ps" and r.route.measure != "val_ps":
            head += " (EV incomplete → P/S)"
    else:
        head = hl.text or f"missing: {hl.missing}"
    hp = r.headline_pctile
    pc = (
        f", own pctile {hp.value:.0f}/{hp.n}"
        if hp and hp.value is not None
        else (f", pctile missing ({hp.missing})" if hp else "")
    )
    flag = "cyclical" if r.flag and r.flag.cyclical else ""
    std = " · ".join(
        f"{k.replace('val_', '')} {s.m(k).shown}"
        for k in ("val_pe_ttm", FWD, "val_ev_ebit", "val_ev_sales", "val_ps", "val_pb")
    )
    bits = [f"{r.ticker} {r.as_of}: headline {head}{pc} [{r.route.basis}]", std, part2_short(r)]
    if flag:
        bits.append(flag)
    if r.trap:
        bits.append("VALUE-TRAP RISK")
    if s.missing:
        bits = [f"{r.ticker} {r.as_of}: all rows missing: {s.missing}"]
    return " · ".join(bits)


def _row(r: NameResult, signal: str) -> OutRow | None:
    return next((o for o in r.rows if o.signal == signal), None)


def part2_short(r: NameResult) -> str:
    """PEG and est_revision in a few words (the script's per-name line)."""
    out = []
    for sig in ("peg", "est_revision"):
        o = _row(r, sig)
        if o is None:
            continue
        if o.missing:
            shown = f"missing ({o.missing[:60]})"
        elif o.value is not None:
            shown = (
                f"{o.value:.2f}"
                + ("%" if sig == "est_revision" else "")
                + (f" {o.text}" if o.text else "")
            )
        else:
            shown = o.text or "—"
        out.append(f"{sig} {shown}")
    if r.walk[0]:
        out.append("walk-down window")
    return " · ".join(out)


def summary_lines(vp: ValPass) -> list[str]:
    heads: dict[str, int] = {}
    missing = 0
    for rs in vp.results.values():
        for r in rs:
            key = r.headline.measure or r.headline.text or "missing"
            heads[key] = heads.get(key, 0) + 1
            missing += sum(1 for o in r.rows if o.missing)
    flagged = sorted(t for t, rs in vp.results.items() if rs and rs[0].flag and rs[0].flag.cyclical)
    traps = sorted(t for t, rs in vp.results.items() if any(r.trap for r in rs))
    out = [
        f"M08 valuation: {len(vp.results)} names, week close {vp.week}; {vp.written} rows "
        f"written, {missing} missing rows"
        + (f", {vp.kept} missing rows kept back over stored values" if vp.kept else ""),
        "  headlines: " + (", ".join(f"{k} {v}" for k, v in sorted(heads.items())) or "—"),
        "  cyclical: "
        + (", ".join(flagged) or "none")
        + (" · value-trap risk: " + ", ".join(traps) if traps else ""),
    ]
    est: dict[str, int] = {}
    pegs: dict[str, int] = {}
    no_snap = []
    for t, rs in sorted(vp.results.items()):
        if not rs:
            continue
        for sig, tally in (("est_revision", est), ("peg", pegs)):
            o = _row(rs[0], sig)
            if o is None:
                continue
            key = "missing" if o.missing else (o.text or "value")
            tally[key] = tally.get(key, 0) + 1
            if sig == "est_revision" and o.missing and "snapshot" in o.missing:
                no_snap.append(t)
    out.append(
        "  est_revision: " + (", ".join(f"{k} {v}" for k, v in sorted(est.items())) or "—")
        + " · peg: " + (", ".join(f"{k} {v}" for k, v in sorted(pegs.items())) or "—")
    )  # fmt: skip
    if no_snap:
        out.append("  no usable estimate snapshot (missed, budget or no coverage): "
                   + ", ".join(no_snap))  # fmt: skip
    if vp.params_note:
        out.append(f"  parameters: {vp.params_note}")
    out += [f"  {t}: error — {e}" for t, e in sorted(vp.errors.items())]
    return out


def run_local_part(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    params: Params | None = None,
    params_note: str = "",
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    """The refresh hook (after the M07 steps, before M09). Never fails."""
    t0 = clock()
    try:
        vp = valuation_pass(engine, companies, now, params=params)
        vp.params_note = params_note
        lines = summary_lines(vp)
    except Exception as e:
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        lines = [f"  M08: error — {type(e).__name__}: {e}"]
    return [f"M08 valuation — local pass (Parts 1–2, 0 requests) ({clock() - t0:.1f} s):", *lines]
