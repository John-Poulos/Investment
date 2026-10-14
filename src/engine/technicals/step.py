"""M09 Part 1 inside the refresh and the `signals` script (D-M09-1…9).

`technicals_pass` (local, 0 requests; the refresh hooks it after `prices_step` and the M04
local passes, so the closes, the gate, filing status and `cvd_state` are current):

- one session calendar for the pass (`bars.Calendar`), SPY's completed weeks once (the
  benchmark: no CIK, no D13 rows, D-M09-6, D-UI-33);
- per covered name (watchlist, promoted and tracked; ticker → CIK): completed weekly bars
  (shell cut-off from the `spac_shell` tag), the M04 rows M01 reads (`m01_rules`), the
  earnings 8-Ks in the `rev_1m` window, the five rows (`signals.compute`), written in one
  short transaction per name (LESSONS: the app writes too);
- one row set per completed week from the first run; no history backfill (the chart computes
  history on the fly, `bands.band_history`). A rerun in the same week updates the same rows.
- A missing row never overwrites a stored value of the same week (a stale symbol whose last
  week was computed earlier keeps it).
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from engine import m01_rules
from engine.financials import models as models_mod
from engine.financials.profile import full_scope
from engine.prices.store import BENCHMARK
from engine.sec.identity import normalize_cik
from engine.signals import write_signal
from engine.technicals import bars, earnings, signals
from engine.technicals.params import Params


@dataclass
class TechPass:
    results: dict[str, signals.NameResult]
    spy: bars.Weekly | None
    expected_as_of: str
    written: int = 0
    kept: int = 0  # missing rows not written over a stored value
    errors: dict[str, str] = field(default_factory=dict)
    params_note: str = ""


def _has_value(engine: sqlite3.Connection, cik: str, signal: str, as_of: str) -> bool:
    return (
        engine.execute(
            "SELECT 1 FROM signal WHERE cik = ? AND module_id = 'M09' AND signal = ? AND as_of = ? "
            "AND (value IS NOT NULL OR value_text IS NOT NULL) LIMIT 1",
            (cik, signal, as_of),
        ).fetchone()
        is not None
    )


def write_rows(engine: sqlite3.Connection, r: signals.NameResult) -> tuple[int, int]:
    """(rows written, missing rows kept back). Caller owns the transaction."""
    n = kept = 0
    for o in r.rows:
        common = dict(engine=engine, cik=r.cik, ticker=r.ticker, module_id=signals.MODULE,
                      signal=o.signal, as_of=o.as_of, info=o.info)  # fmt: skip
        if o.missing is not None:
            if _has_value(engine, r.cik, o.signal, o.as_of):
                kept += 1
                continue
            n += write_signal(**common, method=o.method, missing=o.missing, sources=o.sources)
        else:
            n += write_signal(**common, method=o.method, value=o.value, value_text=o.text,
                              sources=o.sources)  # fmt: skip
    return n, kept


def name_result(
    engine: sqlite3.Connection,
    ticker: str,
    cik: str,
    today,
    cal: bars.Calendar,
    p: Params,
    *,
    covered: bool,
    mf: models_mod.ModelFile,
    spy: bars.Weekly | None,
    expected: str,
    corpus: sqlite3.Connection | None = None,
) -> signals.NameResult:
    norm = normalize_cik(cik) or cik
    cut = bars.shell_cut_off(mf, norm, ticker)
    w = bars.weekly(engine, ticker, today, cal, cut_off=cut)
    m04 = m01_rules.read_m04(engine, norm, covered=covered)

    def find(start: str, end: str):
        return (earnings.earnings_in_window(engine, norm, start, end, corpus),
                earnings.foreign_reports_in_window(engine, norm, start, end, corpus))  # fmt: skip

    return signals.compute(ticker, norm, w, p, expected_as_of=expected, m04=m04,
                           find_news=find, spy=spy)  # fmt: skip


def technicals_pass(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    params: Params | None = None,
    mf: models_mod.ModelFile | None = None,
    corpus: sqlite3.Connection | None = None,
) -> TechPass:
    """M09 for every covered name (0 requests); one name's error does not stop the others.
    `corpus` (read only) classifies 6-K exhibits as earnings releases (D-M09-16)."""
    p = params or Params()
    mf = mf if mf is not None else models_mod.load_safe()
    today = bars.eastern_today(now)
    cal = bars.Calendar.load(engine, today)
    expected = cal.expected_as_of()
    spy = bars.weekly(engine, BENCHMARK, today, cal)
    spy = spy if spy.bars else None
    covered = set(full_scope(engine, companies).values())
    tp = TechPass({}, spy, expected)
    for ticker, cik in sorted(companies.items()):
        if not cik or ticker.upper() == BENCHMARK:  # no CIK → no D13 rows (D-M09-6)
            continue
        try:
            r = name_result(engine, ticker, cik, today, cal, p, covered=cik in covered, mf=mf,
                            spy=spy, expected=expected, corpus=corpus)  # fmt: skip
            engine.execute("BEGIN")
            try:
                n, kept = write_rows(engine, r)
                engine.execute("COMMIT")
            except Exception:
                engine.execute("ROLLBACK")
                raise
            tp.results[ticker] = r
            tp.written += n
            tp.kept += kept
        except Exception as e:
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            tp.errors[ticker] = f"{type(e).__name__}: {e}"
    return tp


def spy_line(tp: TechPass, p: Params) -> str:
    if tp.spy is None:
        return f"{BENCHMARK} (benchmark, no rows): missing: SPY not stored"
    w = tp.spy
    a = w.as_of or ""
    stale = f"; stale: last bar {w.last_daily}" if w.stale else ""
    return (f"{BENCHMARK} (benchmark, no rows) {a} close {w.bars[-1].close:.2f}: "
            f"{signals.benchmark_text(w, a, p, 'trend')} · "
            f"{signals.benchmark_text(w, a, p, 'mom')}{stale}")  # fmt: skip


def summary_lines(tp: TechPass, p: Params) -> list[str]:
    zones: dict[str, int] = {}
    missing = 0
    for r in tp.results.values():
        for o in r.rows:
            if o.missing:
                missing += 1
            elif o.signal in ("band_z", "trend_state", "rev_1m"):
                key = f"{o.signal} {o.text}"
                zones[key] = zones.get(key, 0) + 1
    out = [
        f"M09 technicals: {len(tp.results)} names, as_of {tp.expected_as_of} (newest completed "
        f"week); {tp.written} rows written, {missing} missing rows"
        + (f", {tp.kept} missing rows kept back over stored values" if tp.kept else ""),
        "  " + ", ".join(f"{k} {v}" for k, v in sorted(zones.items())) if zones else "  —",
        "  " + spy_line(tp, p),
    ]
    if tp.params_note:
        out.append(f"  parameters: {tp.params_note}")
    out += [f"  {t}: error — {e}" for t, e in sorted(tp.errors.items())]
    return out


def run_local_part(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    params: Params | None = None,
    params_note: str = "",
    clock: Callable[[], float] = time.monotonic,
    corpus: sqlite3.Connection | None = None,
) -> list[str]:
    """The refresh hook (after prices and the M04 local passes). Never fails."""
    t0 = clock()
    p = params or Params()
    try:
        tp = technicals_pass(engine, companies, now, params=p, corpus=corpus)
        tp.params_note = params_note
        lines = summary_lines(tp, p)
    except Exception as e:
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        lines = [f"  M09: error — {type(e).__name__}: {e}"]
    return [f"M09 technicals — local pass (Part 1, 0 requests) ({clock() - t0:.1f} s):", *lines]
