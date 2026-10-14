"""The Technicals tab, the chart overlays and the Overview line (M09 Part 2, D-UI-35).

Everything is computed from stored bars by the same functions the refresh uses
(`step.name_result`, `signals.compute`, `bands.band_history`), so the newest completed week
equals the stored D13 rows; the tab also shows whether the stored row matches. No writes, no
requests, no review kinds (information only).

- **Signals:** the five rows for the newest completed week with value, zone or state, as_of,
  the full `method` on hover, missing reasons, the qualification label with its M04 line and
  the R17 note under any `below_*` zone; each signal's role in MY / PT / ST.
- **History:** the last 12 completed weeks, recomputed week by week (no stored history: one
  row set per week is written from the first run on, D-M09-13).
- **Overlays:** the price-level σ band (20-week mean of the weekly close ± 1σ / ± 2σ, display
  only, D-M09-2 amendment) and the 40-week MA of completed weekly closes. Weekly bars: the
  value at each completed week (the partial week has none). Daily bars: stepped — each
  session shows the newest week completed on or before it (a week completes with its last
  session), so the current partial week shows the last completed week's value (D-M09-17).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from datetime import datetime

from engine import m01_rules
from engine.financials import models as models_mod
from engine.prices import store as prices
from engine.sec.identity import normalize_cik
from engine.signals import latest_signal
from engine.technicals import bands, bars, earnings, signals, step
from engine.technicals.params import Params

HISTORY_WEEKS = 12
LABELS = {
    "band_z": "Band depth (band_z)",
    "price_band": "Price-level σ band (price_band)",
    "trend_state": "Trend vs 40-week MA (trend_state)",
    "mom_12_1": "12-1 momentum (mom_12_1)",
    "rev_1m": "1-month reversal (rev_1m)",
}
# Role per profile (docs/M09_TECHNICALS.md "Signals out"; D-M09-1)
ROLES = {
    "band_z": ("✓ lead (timing)", "info", "info"),
    "price_band": ("info (display)", "info (display)", "info (display)"),
    "trend_state": ("✓ context", "✓", "info"),
    "mom_12_1": ("info", "✓ lead", "info"),
    "rev_1m": ("info", "info", "✓ lead"),
}
OVERLAY_NOTE = (
    "σ bands: 20-week mean of the weekly close ± 1σ / ± 2σ of the close (display only, never "
    "a trigger, D-M09-2); 40-week MA of completed weekly closes. Daily bars step: each "
    "session shows the newest completed week (D-M09-17)."
)


@dataclass
class SigRow:
    signal: str
    label: str
    roles: tuple[str, str, str]
    as_of: str
    value: str = ""
    state: str | None = None
    details: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    filings: list[tuple[str, str]] = field(default_factory=list)  # (accession, text)
    method: str = ""
    missing: str | None = None
    stored: str = ""
    stored_ok: bool = False


@dataclass
class HistRow:
    as_of: str
    close: float | None
    cells: dict[str, str]  # signal → short text
    zone: str | None = None
    missing: dict[str, str] = field(default_factory=dict)


@dataclass
class TechView:
    ticker: str
    cik: str
    as_of: str
    expected_as_of: str
    version: str
    rows: list[SigRow] = field(default_factory=list)
    history: list[HistRow] = field(default_factory=list)
    qual: str = ""
    qual_state: str = ""
    m04_line: str = ""
    covered: bool = True
    missing: str = ""  # one reason for every row (no prices, stale)
    lag: str = ""
    zone: str | None = None
    r17: bool = False
    knife: bool = False
    rule7: str = ""
    spy: str = ""
    last_bar: str | None = None

    @property
    def r17_note(self) -> str:
        return signals.R17_NOTE


def _tracked(engine: sqlite3.Connection) -> set[str]:
    from engine.themes import tiers

    return {m.cik for m in tiers.members(engine, "tracked")}


def _fmt(x: float | None, spec: str) -> str:
    return "—" if x is None else format(x, spec)


def _stored(engine: sqlite3.Connection, cik: str, o: signals.Out) -> tuple[str, bool]:
    s = latest_signal(engine, cik, signals.MODULE, o.signal, "MY")
    if s is None:
        return "not stored yet (the next logon refresh writes it)", False
    shown = s["value_text"] or (_fmt(s["value"], ".4g") if s["value"] is not None else "missing")
    if s["as_of"] != o.as_of:
        return f"stored row {s['as_of']}: {shown} (this week not written yet)", False
    if o.missing is not None:
        same = s["value"] is None and s["value_text"] is None
    else:
        same = (s["value_text"] == o.text) and (
            s["value"] is None
            if o.value is None
            else s["value"] is not None and abs(float(s["value"]) - float(o.value)) < 5e-4
        )
    if same:
        return f"stored row {s['as_of']} matches", True
    return (f"stored row {s['as_of']}: {shown} — differs from the bars now (refetched or "
            "recomputed since; the next refresh rewrites it)", False)  # fmt: skip


def _sig_rows(
    engine, r: signals.NameResult, p: Params, spy, rule7: str, knife: bool
) -> list[SigRow]:
    out = []
    w = r.weekly
    by = {o.signal: o for o in r.rows}
    for s in signals.SIGNALS:
        o = by.get(s)
        if o is None:
            continue
        row = SigRow(s, LABELS[s], ROLES[s], o.as_of, method=o.method, missing=o.missing)
        row.stored, row.stored_ok = _stored(engine, r.cik, o)
        if o.missing is not None:
            out.append(row)
            continue
        b, tr, rv = r.band, r.trend, r.rev
        if s == "band_z" and b is not None:
            row.value, row.state = f"{b.z:+.2f}", o.text
            row.details = [
                (f"pullback_sigma {b.pullback_sigma:+.2f} (σ_w {b.sigma_w:.1%} a week)"
                 if b.pullback_sigma is not None else "pullback_sigma n/a"),
                f"{p.band_window}-week high {b.high:.2f} ({b.from_high:+.1%})",
                f"z of price {_fmt(b.z_price, '+.2f')}",
                f"geometric mean {b.geo_mean:.2f}, close {b.close:.2f}",
            ]  # fmt: skip
            if o.text == "below_2":
                row.notes.append(rule7)
            if o.text and o.text.startswith("above"):
                row.notes.append(signals.UPPER_NOTE)
        elif s == "price_band" and b is not None:
            lv = b.levels()
            row.value = f"{lv['mean']:.2f}"
            row.details = [
                f"−2σ {lv['-2']:.2f} · −1σ {lv['-1']:.2f} · +1σ {lv['+1']:.2f} · "
                f"+2σ {lv['+2']:.2f}",
                f"σ of the close {b.price_sd:.2f}; close {b.close:.2f}, z of price "
                f"{_fmt(b.z_price, '+.2f')}",
                "display only: never a trigger, never a vote (D-M09-2 amendment)",
            ]
        elif s == "trend_state" and tr is not None:
            row.value, row.state = (f"{tr.value:+d}" if tr.value else "0"), o.text
            row.details = [
                f"40-week MA {tr.ma:.2f}, ma_distance {tr.ma_distance:+.1%}",
                f"slope {tr.slope:+.2%} over {p.slope_weeks} weeks; position {tr.position}"
                + (f"; pending flip: 1 close {tr.raw} the MA" if tr.pending else ""),
                signals.benchmark_text(spy, o.as_of, p, "trend"),
            ]
        elif s == "mom_12_1" and r.mom is not None:
            row.value, row.state = f"{r.mom:+.1%}", o.text
            c4, c52 = w.bars[-1 - p.skip_weeks], w.bars[-1 - p.lookback_weeks]
            hi = signals.high_52w(w.daily, o.as_of)
            row.details = [
                f"close {c4.close:.2f} ({c4.date}) ÷ close {c52.close:.2f} ({c52.date}) − 1",
                (f"52-week high ratio {w.bars[-1].close / hi[0]:.3f} (high {hi[0]:.2f} on "
                 f"{hi[1]}; context, never a target)" if hi else "52-week high ratio n/a"),
                signals.benchmark_text(spy, o.as_of, p, "mom"),
            ]  # fmt: skip
        elif s == "rev_1m" and rv is not None:
            row.value, row.state = f"{rv.z:+.2f}", o.text
            base = w.bars[-1 - p.rev_weeks].date
            row.details = [
                f"{p.rev_weeks}-week log return {rv.ret:+.4f} from {base} to {o.as_of}; σ_w "
                f"{rv.sigma_w:.1%} ({p.rev_sigma_weeks} weeks before the window)",
                signals.TURNOVER_NOTE,
            ]
            if r.news:
                row.notes.append(signals.NEWS_NOTE)
            row.filings = [(c.accession, c.text()) for c in r.news]
            row.filings += [(c.accession, "listed only, not classified: " + c.text())
                            for c in r.foreign]  # fmt: skip
        if s in ("band_z", "trend_state", "mom_12_1") and knife:
            row.notes.append(signals.KNIFE_NOTE)
        out.append(row)
    return out


def _history(r: signals.NameResult, p: Params, find_news) -> list[HistRow]:
    w = r.weekly
    n = len(w.bars)
    out = []
    for k in range(max(0, n - HISTORY_WEEKS), n):
        b = w.bars[k]
        wk = replace(w, bars=w.bars[: k + 1], daily=[x for x in w.daily if x[0] <= b.date],
                     last_daily=b.date, stale=False, stale_days=0, dropped=[])  # fmt: skip
        h = signals.compute(r.ticker, r.cik, wk, p, expected_as_of=b.date, m04=None,
                            find_news=find_news)  # fmt: skip
        by = {o.signal: o for o in h.rows}
        row = HistRow(b.date, b.close, {})
        for s, o in by.items():
            if o.missing is not None:
                row.missing[s] = o.missing
        if h.band is not None and h.band.z is not None:
            row.zone = by["band_z"].text
            row.cells["band_z"] = f"{h.band.z:+.2f} {row.zone}"
            row.cells["pullback"] = _fmt(h.band.pullback_sigma, "+.2f")
        if h.band is not None:
            lv = h.band.levels()
            row.cells["price_band"] = f"{lv['-2']:.2f} · {lv['mean']:.2f} · {lv['+2']:.2f}"
        if h.trend is not None:
            pend = ", pending flip" if h.trend.pending else ""
            row.cells["trend_state"] = (f"{h.trend.state} (MA {h.trend.ma:.2f}, "
                                        f"{h.trend.ma_distance:+.1%}){pend}")  # fmt: skip
        if h.mom is not None:
            row.cells["mom_12_1"] = f"{h.mom:+.1%}"
        if h.rev is not None:
            row.cells["rev_1m"] = f"{h.rev.z:+.2f} {by['rev_1m'].text}"
        out.append(row)
    return list(reversed(out))  # newest first


def company_view(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    cik: str,
    ticker: str,
    now: datetime,
    p: Params,
    mf: models_mod.ModelFile,
) -> TechView:
    norm = normalize_cik(cik) or cik
    today = bars.eastern_today(now)
    cal = bars.Calendar.load(engine, today)
    expected = cal.expected_as_of()
    spy = bars.weekly(engine, prices.BENCHMARK, today, cal)
    spy = spy if spy.bars else None
    covered = norm not in _tracked(engine)
    r = step.name_result(engine, ticker, norm, today, cal, p, covered=covered, mf=mf, spy=spy,
                         expected=expected, corpus=corpus)  # fmt: skip
    v = TechView(ticker, norm, r.as_of, expected, p.version, covered=covered, missing=r.missing,
                 lag=r.lag, spy=signals.benchmark_text(spy, r.as_of, p, "mom"),
                 last_bar=r.weekly.last_daily)  # fmt: skip
    if r.m04 is not None:
        q = m01_rules.rule1(r.m04)
        v.qual, v.qual_state, v.m04_line = q.text, q.state, m01_rules.m04_line(r.m04)
        rule7 = m01_rules.rule7(r.m04).text
    else:
        rule7 = "beyond 2σ: warning, no added strength (D27)"
    v.knife = r.mom is not None and r.mom < 0 and r.trend is not None and \
        r.trend.state == "down"  # fmt: skip
    v.rows = _sig_rows(engine, r, p, spy, rule7, v.knife)
    bz = next((x for x in v.rows if x.signal == "band_z"), None)
    v.zone = bz.state if bz and bz.missing is None else None
    v.r17 = bool(v.zone and v.zone.startswith("below"))
    v.rule7 = rule7 if v.zone == "below_2" else ""
    if r.weekly.bars:

        def find(start: str, end: str):
            ins = earnings.earnings_in_window(engine, norm, start, end, corpus)
            return ins, earnings.foreign_reports_in_window(engine, norm, start, end, corpus)

        v.history = _history(r, p, find)
    return v


# --- chart overlays ----------------------------------------------------------------------------


def overlay(
    engine: sqlite3.Connection,
    ticker: str,
    cik: str | None,
    bar: str,
    now: datetime,
    p: Params,
    mf: models_mod.ModelFile,
) -> dict:
    """{"series": {mean, p1, m1, p2, m2, ma: [{time, value}]}, …} on the chart's own bar times
    (`prices.bars`), so every point sits on a candle."""
    today = bars.eastern_today(now)
    norm = normalize_cik(cik) if cik else None
    cut = bars.shell_cut_off(mf, norm, ticker)
    w = bars.weekly(engine, ticker, today, cut_off=cut)
    closes = w.closes()
    hist = bands.band_history(closes, window=p.band_window, returns=p.pullback_returns)
    ma: list[float | None] = [None] * len(closes)
    run = 0.0
    for i, c in enumerate(closes):
        run += c
        if i >= p.ma_weeks:
            run -= closes[i - p.ma_weeks]
        if i >= p.ma_weeks - 1:
            ma[i] = run / p.ma_weeks
    keys = ("m2", "m1", "mean", "p1", "p2")
    level = {"m2": "-2", "m1": "-1", "mean": "mean", "p1": "+1", "p2": "+2"}

    def values(i: int) -> dict[str, float | None]:
        b = hist[i]
        lv = b.levels() if b is not None else None
        out = {k: (round(lv[level[k]], 4) if lv else None) for k in keys}
        out["ma"] = round(ma[i], 4) if ma[i] is not None else None
        return out

    chart = prices.bars(engine, ticker, "W" if bar == "W" else "D", today)
    series: dict[str, list[dict]] = {k: [] for k in (*keys, "ma")}
    if bar == "W":
        by_monday = {b.monday: i for i, b in enumerate(w.bars)}
        pick = [(c["time"], by_monday.get(c["time"])) for c in chart.bars]
    else:
        pick, j = [], -1
        for c in chart.bars:  # stepped: the newest week completed on or before the session
            while j + 1 < len(w.bars) and w.bars[j + 1].date <= c["time"]:
                j += 1
            pick.append((c["time"], j if j >= 0 else None))
    for t, i in pick:
        if i is None:
            continue
        for k, x in values(i).items():
            if x is not None:
                series[k].append({"time": t, "value": x})
    last = values(len(w.bars) - 1) if w.bars else {}
    return {
        "symbol": ticker.upper(),
        "bar": "W" if bar == "W" else "D",
        "as_of": w.as_of,
        "version": p.version,
        "window": p.band_window,
        "ma_weeks": p.ma_weeks,
        "cut_off": cut,
        "last": last,
        "series": series,
        "note": OVERLAY_NOTE,
    }


# --- Overview line -----------------------------------------------------------------------------


def overview_row(engine: sqlite3.Connection, cik: str) -> dict | None:
    """The newest stored M09 rows (MY) for the Overview signal list; None before any run."""
    got = {}
    for s in ("band_z", "trend_state", "mom_12_1", "rev_1m"):
        r = latest_signal(engine, cik, signals.MODULE, s, "MY")
        if r is not None:
            missing = None
            if r["value"] is None and r["value_text"] is None:
                missing = (r["method"] or "")[len("missing: ") :].split(";")[0]
            got[s] = {"as_of": r["as_of"], "value": r["value"], "text": r["value_text"],
                      "missing": missing}  # fmt: skip
    if not got:
        return None
    return {"as_of": max(x["as_of"] for x in got.values()), **got}
