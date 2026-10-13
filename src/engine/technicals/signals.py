"""The five M09 rows for one name (M09 Part 1; docs/M09_TECHNICALS.md "Signals out", rules).

Computes from completed weekly bars (`bars.weekly`) and returns the rows to write; the step
writes them (`step.py`). Every row: `module_id` M09, grade A (Tiingo closes, D-M04-82),
`source_ref` "Tiingo adj_close <date>", `as_of` = the last completed week's final session,
parameters version in `method` (`config/technicals.toml`).

| Signal | value / value_text | MY | PT | ST |
|---|---|---|---|---|
| `band_z` | z of ln close / `below_2` … `above_2` | ✓ | info | info |
| `price_band` | 20-week mean of the close (levels in `method`) | info | info | info |
| `trend_state` | +1 / 0 / −1 / `up`, `flat`, `down` | ✓ | ✓ | info |
| `mom_12_1` | return / `positive`, `negative` | info | ✓ | info |
| `rev_1m` | z / `extended_up`, `extended_down`, `normal`, `news_move` | info | info | ✓ |
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from engine import m01_rules
from engine.signals import Source
from engine.technicals import bands
from engine.technicals.bars import Weekly
from engine.technicals.earnings import Catalyst
from engine.technicals.params import Params

MODULE = "M09"
SIGNALS = ("band_z", "price_band", "trend_state", "mom_12_1", "rev_1m")
INFO = {
    "band_z": ("PT", "ST"),
    "price_band": ("MY", "PT", "ST"),
    "trend_state": ("ST",),
    "mom_12_1": ("MY", "ST"),
    "rev_1m": ("MY", "PT"),
}
R17_NOTE = (
    "decline risk: about 40% of Russell 3000 stocks since 1980 suffered a permanent fall of "
    "70% or more from peak (57% in IT; JPM 2014); 58% trailed T-bills (Bessembinder) — a "
    "population base rate, not a forecast for this stock (R17, D-M09-7)"
)
UPPER_NOTE = "upper extreme — information (D-M09-3); never a sell signal (D16)"
KNIFE_NOTE = "falling-knife context: 12-1 momentum negative and trend down (D-M09-5)"
BAND_NOTE = "normal-model band; hit rates uncalibrated (Cont 2001, S-new-M09-10)"
TURNOVER_NOTE = "turnover not checked (deferred)"
NEWS_NOTE = "news_move: drift expected, not a reversal candidate (Chan 2003, S-new-M09-3)"


# --- Indicators (pure) ---------------------------------------------------------------------


@dataclass(frozen=True)
class Trend:
    state: str  # up | flat | down
    position: str  # above | below (confirmed after `flip_closes` closes)
    raw: str  # this week's side
    pending: bool  # one close on the other side, not yet flipped
    ma: float
    slope: float  # MA change over `slope_weeks`
    ma_distance: float  # close ÷ MA − 1

    @property
    def value(self) -> int:
        return {"up": 1, "flat": 0, "down": -1}[self.state]

    def text(self) -> str:
        pend = f"; pending flip: 1 close {self.raw} the MA (flips after 2)" if self.pending else ""
        return (
            f"40-week MA {self.ma:.2f}, ma_distance {self.ma_distance:+.1%}, slope "
            f"{self.slope:+.2%} over 4 weeks; position {self.position}{pend}"
        )


def trend_at(closes: Sequence[float], p: Params) -> Trend | None:
    """Close vs the MA plus its slope; the position flips after `flip_closes` closes."""
    n = len(closes)
    if n < max(p.trend_min_bars, p.ma_weeks + p.slope_weeks):
        return None
    ma = {k: sum(closes[k - p.ma_weeks + 1 : k + 1]) / p.ma_weeks
          for k in range(p.ma_weeks - 1, n)}  # fmt: skip
    first = p.ma_weeks - 1
    sides = {k: "above" if closes[k] > ma[k] else "below" for k in ma}
    pos = sides[first]
    run = 1
    for k in range(first + 1, n):
        run = run + 1 if sides[k] == sides[k - 1] else 1
        if sides[k] != pos and run >= p.flip_closes:
            pos = sides[k]
    t = n - 1
    slope = ma[t] / ma[t - p.slope_weeks] - 1
    if pos == "above" and slope > p.slope_tolerance:
        state = "up"
    elif pos == "below" and slope < -p.slope_tolerance:
        state = "down"
    else:
        state = "flat"
    return Trend(state, pos, sides[t], sides[t] != pos, ma[t], slope, closes[t] / ma[t] - 1)


def mom_12_1(closes: Sequence[float], p: Params) -> float | None:
    if len(closes) < p.mom_min_bars:
        return None
    return closes[-1 - p.skip_weeks] / closes[-1 - p.lookback_weeks] - 1


@dataclass(frozen=True)
class Reversal:
    z: float
    ret: float  # 4-week log return
    sigma_w: float


def rev_at(closes: Sequence[float], p: Params) -> Reversal | None:
    if len(closes) < p.rev_min_bars:
        return None
    t = len(closes) - 1
    ret = math.log(closes[t] / closes[t - p.rev_weeks])
    seg = closes[t - p.rev_weeks - p.rev_sigma_weeks : t - p.rev_weeks + 1]
    _, sw = bands.mean_sd(bands.log_returns(seg))
    if sw == 0:
        return None
    return Reversal(ret / (math.sqrt(p.rev_weeks) * sw), ret, sw)


def high_52w(daily: Sequence[tuple[str, float]], as_of: str) -> tuple[float, str] | None:
    """Highest daily adjusted close in the 52 weeks to `as_of` (inclusive)."""
    lo = (date.fromisoformat(as_of) - timedelta(days=364)).isoformat()
    inside = [(c, d) for d, c in daily if lo < d <= as_of]
    return max(inside) if inside else None


# --- Benchmark (SPY, D-M09-6) ----------------------------------------------------------------


def benchmark_text(spy: Weekly | None, as_of: str, p: Params, what: str) -> str:
    """SPY's 12-1 or trend at the name's week, for `method`; never a row of its own."""
    if spy is None or not spy.bars:
        return "SPY: missing: SPY not stored"
    closes = [b.close for b in spy.bars if b.date <= as_of]
    if not closes:
        return "SPY: missing: SPY not stored"
    week = next(b.date for b in reversed(spy.bars) if b.date <= as_of)
    if what == "mom":
        m = mom_12_1(closes, p)
        return (
            f"SPY 12-1 {m:+.1%} ({week}, labelled proxy)"
            if m is not None
            else f"SPY 12-1 missing: insufficient_history ({len(closes)}/{p.mom_min_bars})"
        )
    tr = trend_at(closes, p)
    if tr is None:
        return f"SPY trend missing: insufficient_history ({len(closes)}/{p.trend_min_bars})"
    return (f"SPY trend {tr.state} ({week}: MA {tr.ma:.2f}, {tr.ma_distance:+.1%}, slope "
            f"{tr.slope:+.2%}{', pending flip' if tr.pending else ''})")  # fmt: skip


# --- Rows ------------------------------------------------------------------------------------


@dataclass
class Out:
    signal: str
    as_of: str
    method: str
    value: float | int | None = None
    text: str | None = None
    missing: str | None = None
    sources: list[Source] = field(default_factory=list)

    @property
    def info(self) -> tuple[str, ...]:
        return INFO[self.signal]


@dataclass
class NameResult:
    ticker: str
    cik: str
    weekly: Weekly
    as_of: str
    rows: list[Out] = field(default_factory=list)
    band: bands.Band | None = None
    trend: Trend | None = None
    mom: float | None = None
    rev: Reversal | None = None
    news: list[Catalyst] = field(default_factory=list)
    qual: m01_rules.Reading | None = None
    m04: m01_rules.M04Rows | None = None
    missing: str = ""  # one reason for every row (stale, no prices)
    lag: str = ""  # as_of older than the calendar's newest completed week, and why


def _insufficient(w: Weekly, have: int, need: int) -> tuple[str, str]:
    """(missing reason, method note)."""
    if w.cut_off and w.cut_bars:
        return (f"shell period (before {w.cut_off})",
                f"{have}/{need} completed weeks after the shell cut-off ({w.cut_bars} daily "
                "bars of the spac_shell period excluded, D-M04-8)")  # fmt: skip
    return f"insufficient_history ({have}/{need})", ""


def compute(
    ticker: str,
    cik: str,
    w: Weekly,
    p: Params,
    *,
    expected_as_of: str,
    m04: m01_rules.M04Rows | None,
    find_news: Callable[[str, str], tuple[list[Catalyst], list[Catalyst]]] | None = None,
    spy: Weekly | None = None,
) -> NameResult:
    """The five rows for one name (missing rows carry their reason, never zero).

    `find_news(start, end)` returns (earnings 8-Ks, 6-Ks) in the rev_1m window (start, end]."""
    res = NameResult(ticker, cik, w, w.as_of or expected_as_of, m04=m04)
    version = p.version
    if w.last_daily is None:
        res.missing = "no stored prices"
    elif w.stale:
        res.missing = "stale bars"
    if res.missing:
        res.as_of = expected_as_of
        note = (f"last stored bar {w.last_daily}, {w.stale_days} days old (over 5)"
                if w.last_daily else "no Tiingo bars stored for this symbol")  # fmt: skip
        for s in SIGNALS:
            res.rows.append(Out(s, expected_as_of, f"{s} {version}; {note}",
                                missing=res.missing))  # fmt: skip
        return res
    closes = w.closes()
    n = len(closes)
    as_of = res.as_of
    src = [Source(f"Tiingo adj_close {as_of}", as_of, "A", f"{w.symbol} weekly close")]
    basis = f"; basis: {w.basis}" if w.basis else ""
    lag = ""
    if as_of < expected_as_of:
        res.lag = f"as_of older than {expected_as_of}" + (
            f": {'; '.join(w.dropped)}" if w.dropped else ""
        )
        lag = f"; {res.lag}"
    tail = f"{basis}{lag}"
    week = w.bars[-1].monday if w.bars else ""

    # qualification (R3, D-M09-4) — context, never a deciding input of the grade
    if m04 is not None:
        res.qual = m01_rules.rule1(m04)
        qual = f"{res.qual.text}; M04 reading: {m01_rules.m04_line(m04)}"
    else:
        qual = "qualification incomplete (M04 rows not read)"

    res.trend = trend_at(closes, p)
    res.mom = mom_12_1(closes, p)
    knife = res.mom is not None and res.mom < 0 and res.trend is not None and \
        res.trend.state == "down"  # fmt: skip

    def add(signal: str, method: str, **kw) -> None:
        if kw.get("missing") is None:
            kw.setdefault("sources", list(src))
        res.rows.append(Out(signal, as_of, method, **kw))

    # band_z and price_band (D27, D-M09-2)
    res.band = bands.band_at(closes, window=p.band_window, returns=p.pullback_returns)
    b = res.band
    if b is None:
        why, extra = _insufficient(w, n, p.band_window)
        for s in ("band_z", "price_band"):
            add(s, f"{s} {version}" + (f"; {extra}" if extra else "") + tail, missing=why)
    else:
        pb = (f"pullback_sigma {b.pullback_sigma:+.2f} (σ_w {b.sigma_w:.1%} a week, "
              f"{p.pullback_returns} weekly returns)" if b.pullback_sigma is not None
              else f"pullback_sigma n/a ({n}/{p.pullback_returns + 1} closes)")  # fmt: skip
        zp = f"{b.z_price:+.2f}" if b.z_price is not None else "n/a (σ = 0)"
        if b.z is None:
            add("band_z", f"band_z {version}; σ of ln close = 0{tail}",
                missing="flat prices (σ = 0)")  # fmt: skip
        else:
            z = b.z
            zn = bands.zone(z, p.zone_1, p.zone_2)
            notes = []
            if zn == "below_2":
                notes.append(m01_rules.rule7(m04).text if m04 is not None
                             else "beyond 2σ: warning, no added strength (D27)")  # fmt: skip
            if zn.startswith("below"):
                notes.append(R17_NOTE)
            if zn.startswith("above"):
                notes.append(UPPER_NOTE)
            if knife:
                notes.append(KNIFE_NOTE)
            method = (
                f"band_z {version}: z of ln(close) vs the {p.band_window}-week mean of ln(close) "
                f"(geometric mean {b.geo_mean:.2f}, σ of ln close {b.sd_log:.4f}); close "
                f"{b.close:.2f} (week of {week}); {pb}; {p.band_window}-week high {b.high:.2f} "
                f"({b.from_high:+.1%}); z of price {zp}; {qual}"
                + "".join(f"; {x}" for x in notes)
                + f"; {BAND_NOTE}{tail}"
            )
            add("band_z", method, value=round(z, 4), text=zn)
        lv = b.levels()
        add(
            "price_band",
            f"price_band {version} (display only: never a trigger, never a vote; D-M09-2 "
            f"amendment): {p.band_window}-week mean of the close {lv['mean']:.2f}, σ of the "
            f"close {b.price_sd:.2f}; −2σ {lv['-2']:.2f}, −1σ {lv['-1']:.2f}, +1σ "
            f"{lv['+1']:.2f}, +2σ {lv['+2']:.2f}; close {b.close:.2f}, z of price {zp}{tail}",
            value=round(lv["mean"], 4),
        )

    # trend_state (D-M09-5)
    if res.trend is None:
        why, extra = _insufficient(w, n, p.trend_min_bars)
        add("trend_state", f"trend_state {version}" + (f"; {extra}" if extra else "")
            + f"; {benchmark_text(spy, as_of, p, 'trend')}{tail}", missing=why)  # fmt: skip
    else:
        tr = res.trend
        add(
            "trend_state",
            f"trend_state {version}: close {closes[-1]:.2f} vs {tr.text()}; up = above a rising "
            f"MA, down = below a falling MA (slope tolerance ±{p.slope_tolerance:.2%}), else "
            f"flat"
            + (f"; {KNIFE_NOTE}" if knife else "")
            + f"; {benchmark_text(spy, as_of, p, 'trend')}; context and warning only, never "
            f"blocks (D-M09-5){tail}",
            value=tr.value,
            text=tr.state,
        )

    # mom_12_1 (A4: PT lead)
    if res.mom is None:
        why, extra = _insufficient(w, n, p.mom_min_bars)
        add("mom_12_1", f"mom_12_1 {version}" + (f"; {extra}" if extra else "")
            + f"; {benchmark_text(spy, as_of, p, 'mom')}{tail}", missing=why)  # fmt: skip
    else:
        c4, c52 = w.bars[-1 - p.skip_weeks], w.bars[-1 - p.lookback_weeks]
        hi = high_52w(w.daily, as_of)
        hi_txt = (f"52-week high ratio {closes[-1] / hi[0]:.3f} (daily adjusted closes; high "
                  f"{hi[0]:.2f} on {hi[1]}; momentum context, never a target)" if hi
                  else "52-week high ratio n/a")  # fmt: skip
        add(
            "mom_12_1",
            f"mom_12_1 {version}: close {p.skip_weeks} weeks ago {c4.close:.2f} ({c4.date}) ÷ "
            f"close {p.lookback_weeks} weeks ago {c52.close:.2f} ({c52.date}) − 1; {hi_txt}; "
            f"{benchmark_text(spy, as_of, p, 'mom')}"
            + (f"; {KNIFE_NOTE}" if knife else "")
            + f"; literature effect, not a forecast (S12){tail}",
            value=round(res.mom, 4),
            text="positive" if res.mom > 0 else "negative",
        )

    # rev_1m (A4: ST lead; rule 7 news moves)
    res.rev = rev_at(closes, p)
    if res.rev is None:
        if n >= p.rev_min_bars:
            add("rev_1m", f"rev_1m {version}; σ_w = 0{tail}", missing="flat prices (σ = 0)")
        else:
            why, extra = _insufficient(w, n, p.rev_min_bars)
            add("rev_1m", f"rev_1m {version}" + (f"; {extra}" if extra else "") + tail,
                missing=why)  # fmt: skip
    else:
        rv = res.rev
        base = w.bars[-1 - p.rev_weeks].date
        news, foreign = find_news(base, as_of) if find_news else ([], [])
        res.news = list(news)
        if res.news:
            zn = "news_move"
        elif rv.z >= p.extended_z:
            zn = "extended_up"
        elif rv.z <= -p.extended_z:
            zn = "extended_down"
        else:
            zn = "normal"
        bits = [
            f"rev_1m {version}: {p.rev_weeks}-week log return {rv.ret:+.4f} "
            f"({math.exp(rv.ret) - 1:+.1%}) from {base} to {as_of} ÷ (2 × σ_w {rv.sigma_w:.1%}, "
            f"{p.rev_sigma_weeks} weekly returns before the window); |z| ≥ {p.extended_z:g} → "
            "extended"
        ]
        if res.news:
            bits.append(NEWS_NOTE + ": " + "; ".join(c.text() for c in res.news))
        if foreign:
            bits.append("6-K in the window (not classified; may be results): "
                        + "; ".join(c.text() for c in foreign))  # fmt: skip
        bits += [TURNOVER_NOTE, qual]
        srcs = list(src) + [Source(c.accession, c.filed, "A", f"8-K item {c.item}")
                            for c in res.news]  # fmt: skip
        add("rev_1m", "; ".join(bits) + tail, value=round(rv.z, 4), text=zn, sources=srcs)
    return res


def line(r: NameResult) -> str:
    """One line per name for the log (values, zones, price_band levels, as_of, missing)."""
    if r.missing:
        return f"{r.ticker}: missing: {r.missing} (as_of {r.as_of}; last bar {r.weekly.last_daily})"
    parts = []
    by = {o.signal: o for o in r.rows}
    for s in SIGNALS:
        o = by.get(s)
        if o is None:
            continue
        if o.missing:
            parts.append(f"{s} missing: {o.missing}")
        elif s == "band_z":
            b = r.band
            pb = f", pullback_sigma {b.pullback_sigma:+.2f}" if b and b.pullback_sigma is not \
                None else ""  # fmt: skip
            zp = f", z price {b.z_price:+.2f}" if b and b.z_price is not None else ""
            parts.append(f"band_z {o.value:+.2f} {o.text}{pb}{zp}")
        elif s == "price_band":
            lv = r.band.levels()
            parts.append(f"price_band {lv['mean']:.2f} [−2σ {lv['-2']:.2f} · −1σ {lv['-1']:.2f} · "
                         f"+1σ {lv['+1']:.2f} · +2σ {lv['+2']:.2f}]")  # fmt: skip
        elif s == "trend_state":
            t = r.trend
            parts.append(f"trend {o.text} (MA {t.ma:.2f}, {t.ma_distance:+.1%}, slope "
                         f"{t.slope:+.2%}{', pending flip' if t.pending else ''})")  # fmt: skip
        elif s == "mom_12_1":
            parts.append(f"mom_12_1 {o.value:+.1%} {o.text}")
        elif s == "rev_1m":
            parts.append(f"rev_1m {o.value:+.2f} {o.text}")
    q = r.qual.text if r.qual else ""
    lag = f" [{r.lag}]" if r.lag else ""
    close = f" close {r.weekly.bars[-1].close:.2f}" if r.weekly.bars else ""
    return f"{r.ticker} {r.as_of}{close}: " + " · ".join(parts) + (f" · {q}" if q else "") + lag
