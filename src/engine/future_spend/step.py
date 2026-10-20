"""M05 Part 1 inside the refresh and the `demand` script (D-M05-1…13).

`future_spend_pass` (local, 0 requests): the refresh hooks it after the M04 local passes
(`financials_local_step` stored `capex_split`; the CvD pass wrote `cvd_state`) and before
M07 (MVP_PLAN local-step order). Per covered name (watchlist, promoted, tracked): the
channel (`config/m05_channels.toml`), the M04 model tag, the capex series, the three rows
`capex_demand`, `growth_capex_roic`, `bookings_cover`, written in one short transaction per
name (LESSONS: the app writes too). Rows carry `as_of` = the newest input's filing date, so a
rerun on unchanged facts updates the same rows; missing rows with no input use today.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from engine import m01_rules
from engine.financials import models as models_mod
from engine.future_spend import channels as channels_mod
from engine.future_spend import demand
from engine.moneyflow import views as mf_views
from engine.sec.identity import normalize_cik
from engine.signals import Source, write_signal

MODULE = "M05"
SIGNALS = ("capex_demand", "growth_capex_roic", "bookings_cover")
# Model tags that make M05 not applicable (D-M04-8 routing; rule 8): no operating capex read.
NOT_APPLICABLE_TAGS = ("fund", "financial", "asset_treasury", "spac_shell")
ALL = ("MY", "PT", "ST")
# Signals-out table: ✓ timeframes carry weight once D13 weights exist; the rest are info.
INFO = {"capex_demand": ("ST",), "growth_capex_roic": ("PT", "ST"), "bookings_cover": ("ST",)}


@dataclass
class Out:
    signal: str
    as_of: str
    method: str
    value: float | None = None
    text: str | None = None
    missing: str | None = None
    sources: list[Source] = field(default_factory=list)
    info: tuple[str, ...] = ()


@dataclass
class NameResult:
    ticker: str
    cik: str
    channel: channels_mod.Channel
    rows: list[Out]
    not_applicable: str | None = None
    series: demand.Series | None = None
    demand: demand.Demand | None = None
    growth: demand.GrowthRoic | None = None
    rpo: mf_views.Rpo | None = None
    deposits: demand.DepositsLine | None = None
    vote: demand.Vote | None = None
    guide: str = ""

    def row(self, signal: str) -> Out | None:
        return next((o for o in self.rows if o.signal == signal), None)


def _as_of(sources: list[Source], today: str) -> str:
    return max((s.date for s in sources if s.date), default=today)


def _info(signal: str, ch: channels_mod.Channel) -> tuple[str, ...]:
    if ch.commitments_lead and signal in ("capex_demand", "growth_capex_roic"):
        return ALL  # R9: capex is info for fabless and outsourced
    return INFO[signal]


def current_guide(engine: sqlite3.Connection, cik: str, today: date) -> str:
    """M02's current-year capex guide, shown in the method, never scored (rule 1)."""
    try:
        from engine.moneyflow.actuals import overrides_by_cik
        from engine.moneyflow.guided import guided_lines

        for g in guided_lines(engine, cik, today, None, overrides_by_cik(engine).get(cik)):
            if not g.ended and " Q" not in g.period:
                return (f"current-year guide {g.period} {g.value_text} ({g.origin}, "
                        f"{g.stated_on}; shown, not scored)")  # fmt: skip
    except Exception as e:  # noqa: BLE001 — a guidance read must not stop the M05 rows
        return f"current-year guide not read ({type(e).__name__})"
    return "no current-year capex guide"


def name_result(
    engine: sqlite3.Connection,
    ticker: str,
    cik: str,
    today: date,
    *,
    chf: channels_mod.ChannelFile,
    mf: models_mod.ModelFile,
) -> NameResult:
    norm = normalize_cik(cik) or cik
    day = today.isoformat()
    ch = chf.for_company(norm, ticker)
    s = demand.build_series(engine, norm, day)
    latest = s.years[-1] if s.years else None
    tag, how = models_mod.route(engine, mf, norm, ticker, latest.end if latest else None)
    r = NameResult(ticker, norm, ch, [], series=s)
    na = None
    if ch.not_applicable:
        na = "not applicable (channel n/a" + (f"; M04 tag {tag}" if tag else "") + ")"
    elif tag in NOT_APPLICABLE_TAGS:
        na = f"not applicable ({tag})"
    if na is not None:
        r.not_applicable = na
        for sig in SIGNALS:
            r.rows.append(Out(sig, day, f"{how}; {ch.text()}", missing=na, info=ALL))
        return r
    tail = f"{ch.text()}; {demand.LABEL}" + (f"; M04 tag {tag}" if tag else "")
    r.rows.append(_capex_demand(engine, r, s, today, tail))
    r.rows.append(_growth(engine, r, norm, day, tail))
    r.rows.append(_bookings(engine, r, s, day, tail))
    return r


def _capex_demand(engine, r: NameResult, s: demand.Series, today: date, tail: str) -> Out:
    day = today.isoformat()
    info = _info("capex_demand", r.channel)
    if not s.years:
        return Out("capex_demand", day, tail, missing="no total capex stored", info=info)
    d = demand.classify(s, len(s.years) - 1)
    r.demand = d
    y = d.year
    srcs = [Source(y.capex.accession, y.capex.filed, "A", f"capex {y.capex.tag}")]
    if y.dep_point is not None:
        srcs.append(Source(y.dep_point.accession, y.dep_point.filed, "A", s.rung))
    if y.revenue is not None:
        srcs.append(Source(y.revenue.accession, y.revenue.filed, "A", "revenue"))
    b = d.bookings
    if b is not None and b.rpo_now is not None:
        srcs.append(Source(b.rpo_now.accession, b.rpo_now.filed, "A", "RPO"))
    if b is not None and b.deposits.now is not None:
        srcs.append(Source(b.deposits.now.accession, b.deposits.now.filed, "A", "deposits"))
    m04 = m01_rules.read_m04(engine, r.cik)
    cover, cover_how = demand.ocf_cover(engine, s, y)
    r.vote = demand.vote(d.state, cover, cover_how, m04.cvd_state, m04.cvd_missing)
    r.guide = current_guide(engine, r.cik, today)
    beside = []
    for name, row in (("runway_q", m04.runway), ("survival_gate", m04.gate)):
        beside.append(f"{name} {row.text or 'missing'}" if row else f"{name} missing")
    rung = demand.RUNG_NAME.get(s.rung, "not split")
    parts = [f"{d.label}: {d.why or d.missing}"] + d.notes + [
        b.text() if b else "", r.vote.text, "beside: " + ", ".join(beside), r.guide,
        f"rung: {rung}; capex on {y.capex.tag}" + (f" [{y.capex.mark}]" if y.capex.mark else ""),
        tail,
    ]  # fmt: skip
    method = "; ".join(p for p in parts if p)
    as_of = _as_of(srcs, day)
    if d.state is None:
        return Out("capex_demand", as_of, method, missing=d.missing, sources=srcs, info=info)
    val = round(d.ratio, 4) if d.ratio is not None else None
    return Out("capex_demand", as_of, method, value=val, text=d.state, sources=srcs, info=info)


def _growth(engine, r: NameResult, cik: str, day: str, tail: str) -> Out:
    g = demand.growth_roic(engine, cik, day)
    r.growth = g
    info = _info("growth_capex_roic", r.channel)
    srcs = [Source(a, f, "A", w) for a, f, w in g.sources if a]
    method = "; ".join(p for p in (g.why, tail) if p)
    as_of = _as_of(srcs, day)
    if g.state is None or not srcs:
        return Out("growth_capex_roic", as_of, method, missing=g.missing or "no source accession",
                   sources=srcs, info=info)  # fmt: skip
    val = round(g.value, 6) if g.value is not None else None
    return Out("growth_capex_roic", as_of, method, value=val, text=g.state, sources=srcs,
               info=info)  # fmt: skip


def _bookings(engine, r: NameResult, s: demand.Series, day: str, tail: str) -> Out:
    rp = mf_views.rpo(engine, r.cik)
    r.rpo = rp
    r.deposits = demand.deposits_line(s)
    info = _info("bookings_cover", r.channel)
    dep = r.deposits.text()
    cust = customers_text(engine, r.cik)
    if not rp.reported:
        return Out("bookings_cover", day, f"{dep}; {cust}; {tail}", missing="RPO not tagged",
                   info=info)  # fmt: skip
    last = rp.rows[-1]
    srcs = [Source(last.accession, last.filed, "A", "RPO")] if last.accession else []
    if last.revenue_ref[0]:
        srcs.append(Source(last.revenue_ref[0], last.revenue_ref[1], "A", "TTM revenue"))
    if last.cover is None:
        return Out("bookings_cover", _as_of(srcs, day), f"RPO {demand._m(last.value)} at "
                   f"{last.end}; {dep}; {cust}; {tail}", missing="no TTM revenue at the RPO date",
                   sources=srcs, info=info)  # fmt: skip
    head = (f"RPO {demand._m(last.value)} ÷ TTM revenue {demand._m(last.revenue_ttm)} at "
            f"{last.end} = {last.cover:.2f} years")  # fmt: skip
    p = rp.cover_prior
    if p is None:
        cmp_ = "no cover a year earlier (short_history)"
    else:
        cmp_ = (f"a year earlier {p.cover:.2f} ({p.end}): {demand._pct(rp.cover_change)} → "
                f"{rp.cover_state} (±{mf_views.COVER_STEP:.0%}†)")  # fmt: skip
    method = (f"{head}; {cmp_}; own history only (expedients differ, S79); {dep}; {cust}; "
              f"{tail}")  # fmt: skip
    if not srcs:
        return Out("bookings_cover", day, method, missing="no source accession", info=info)
    return Out("bookings_cover", _as_of(srcs, day), method, value=round(last.cover, 4),
               text=rp.cover_state, sources=srcs, info=info)  # fmt: skip


def customers_text(engine: sqlite3.Connection, cik: str) -> str:
    """M04's ≥ 10% customers of the latest year, shown beside the bookings (never added)."""
    try:
        from engine.financials.units_view import major_customers

        years = major_customers(engine, cik)
    except Exception as e:  # noqa: BLE001
        return f"≥ 10% customers not read ({type(e).__name__})"
    if not years:
        return "≥ 10% customers: none tagged"
    y = years[-1]
    names = ", ".join(f"{n} {v:.0%}" for n, v in y.customers)
    return f"≥ 10% customers {y.label}: {names} (M04 store, shown beside)"


def write_rows(engine: sqlite3.Connection, r: NameResult) -> int:
    """Rows written. Caller owns the transaction."""
    n = 0
    for o in r.rows:
        common = dict(engine=engine, cik=r.cik, ticker=r.ticker, module_id=MODULE,
                      signal=o.signal, as_of=o.as_of, info=o.info)  # fmt: skip
        if o.missing is not None:
            n += write_signal(**common, method=o.method, missing=o.missing, sources=o.sources)
        else:
            n += write_signal(**common, method=o.method, value=o.value, value_text=o.text,
                              sources=o.sources)  # fmt: skip
    return n


@dataclass
class FutureSpendPass:
    results: dict[str, NameResult]
    written: int = 0
    errors: dict[str, str] = field(default_factory=dict)
    channel_error: str = ""


def future_spend_pass(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    chf: channels_mod.ChannelFile | None = None,
    mf: models_mod.ModelFile | None = None,
) -> FutureSpendPass:
    """M05 for every covered name (0 requests); one name's error does not stop the others."""
    chf = chf if chf is not None else channels_mod.load_safe()
    mf = mf if mf is not None else models_mod.load_safe()
    today = now.date()
    fp = FutureSpendPass({}, channel_error=chf.error)
    for ticker, cik in sorted(companies.items()):
        if not cik:
            continue
        try:
            r = name_result(engine, ticker, cik, today, chf=chf, mf=mf)
            engine.execute("BEGIN")
            try:
                n = write_rows(engine, r)
                engine.execute("COMMIT")
            except Exception:
                engine.execute("ROLLBACK")
                raise
            fp.results[ticker] = r
            fp.written += n
        except Exception as e:
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            fp.errors[ticker] = f"{type(e).__name__}: {e}"
    return fp


def line(r: NameResult) -> str:
    """One line per name for the log."""
    if r.not_applicable:
        return f"{r.ticker}: {r.not_applicable}"
    bits = []
    for o in r.rows:
        if o.missing is not None:
            bits.append(f"{o.signal} missing: {o.missing}")
            continue
        v = ""
        if o.value is not None:
            v = f" {o.value:.1%}" if o.signal == "growth_capex_roic" else f" {o.value:.2f}"
        extra = ""
        if o.signal == "capex_demand" and r.demand is not None:
            d = r.demand
            if d.median is not None:
                extra = f" (median {d.median:.2f}, {d.label})"
            elif d.label:
                extra = f" ({d.label})"
        bits.append(f"{o.signal} {o.text}{v}{extra}")
    out = f"{r.ticker} [{r.channel.channel}]: " + " · ".join(bits)
    if r.vote is not None:
        out += f" · {r.vote.text}"
    return out


def summary_lines(fp: FutureSpendPass) -> list[str]:
    states: dict[str, int] = {}
    missing = 0
    ahead, positive = [], []
    for r in fp.results.values():
        for o in r.rows:
            if o.missing is not None:
                missing += 1
            else:
                key = f"{o.signal} {o.text}"
                states[key] = states.get(key, 0) + 1
        o = r.row("capex_demand")
        if o is not None and o.text == "AHEAD_OF_DEMAND":
            ahead.append(r.ticker)
        if r.vote is not None and r.vote.positive:
            positive.append(r.ticker)
    out = [
        f"M05 future spend: {len(fp.results)} names; {fp.written} rows written, {missing} "
        "missing rows",
        "  " + ", ".join(f"{k} {v}" for k, v in sorted(states.items())) if states else "  —",
        f"  capex vote positive (rule 4): {', '.join(positive) or 'none'}; AHEAD_OF_DEMAND "
        f"(M01 rule-4 exit warning, D-M01-7): {', '.join(ahead) or 'none'}",
    ]
    if fp.channel_error:
        out.append(f"  channel file rejected, every company read as unset: {fp.channel_error}")
    out += [f"  {t}: error — {e}" for t, e in sorted(fp.errors.items())]
    return out


def run_local_part(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    """The refresh hook (after the M04 local passes, before M07). Never fails."""
    t0 = clock()
    try:
        lines = summary_lines(future_spend_pass(engine, companies, now))
    except Exception as e:
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        lines = [f"  M05: error — {type(e).__name__}: {e}"]
    return [f"M05 future spend — local pass (Part 1, 0 requests) ({clock() - t0:.1f} s):", *lines]
