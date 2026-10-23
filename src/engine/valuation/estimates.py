"""Analyst estimates: the weekly snapshot rotation and the revision readings (M08 Part 2).

D-M08-6 (budget), D-M08-14 (mapping and snapshot use), D-M08-15 (flat band), rule 7.

- **Rotation.** One Alpha Vantage `EARNINGS_ESTIMATES` call per company a week for the core
  and promoted names (a `fund` such as ETV is not asked), at most 3 a day in the logon run,
  after the transcripts (`calls.alpha_vantage`, its share of the shared `fetch_log`). Never
  asked first, then the oldest; a no-coverage reply is asked again after 4 weeks, a failure
  the next day. A budget stop ends the batch, names the companies left for the next run and
  is reported, never silent (LESSONS). The last attempt per company lives in `refresh_state`
  `m08_estimates:<cik>`.
- **Storage.** Every vendor row and field from the first snapshot (`estimate_snapshot`,
  migration 0041): fiscal years and quarters, past quarters included; a vendor null stays
  NULL (missing, never 0). Same Eastern date → that date's rows are replaced.
- **Reading at a date.** The newest snapshot fetched on or before the date (rule 1: what was
  known then), at most 28 days old. FY1 / FY2 are mapped by the vendor's period-end `date`,
  not its label: FY1 = the first fiscal-year row ending after the newest fiscal year the
  company has reported by the date (else after the date), FY2 the next (MU, NVDA, MSFT are
  off-calendar). A vendor label that disagrees is named.
- **Revisions** (R15): (average ÷ average N days ago − 1) for N = 30, 90; `not_meaningful`
  when either |average| < $0.10 or the sign changes; breadth = (up − down) ÷ count over 30
  days (null counts → missing); dispersion = (high − low) ÷ |average| only when count ≥ 3
  (range-based: the vendor gives no standard deviation).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime

from engine.calls.alpha_vantage import ESTIMATES_BUDGET, AlphaVantageClient
from engine.financials import models as models_mod
from engine.sec.client import iso
from engine.sec.results import Failed
from engine.signals import Source
from engine.technicals.bars import eastern_today
from engine.valuation.params import Params

STATE = "m08_estimates:"
FIELDS = {
    "eps_estimate_average": "eps_avg",
    "eps_estimate_high": "eps_high",
    "eps_estimate_low": "eps_low",
    "eps_estimate_analyst_count": "eps_count",
    "eps_estimate_average_7_days_ago": "eps_avg_7d",
    "eps_estimate_average_30_days_ago": "eps_avg_30d",
    "eps_estimate_average_60_days_ago": "eps_avg_60d",
    "eps_estimate_average_90_days_ago": "eps_avg_90d",
    "eps_estimate_revision_up_trailing_7_days": "rev_up_7d",
    "eps_estimate_revision_down_trailing_7_days": "rev_down_7d",
    "eps_estimate_revision_up_trailing_30_days": "rev_up_30d",
    "eps_estimate_revision_down_trailing_30_days": "rev_down_30d",
    "revenue_estimate_average": "revenue_avg",
    "revenue_estimate_high": "revenue_high",
    "revenue_estimate_low": "revenue_low",
    "revenue_estimate_analyst_count": "revenue_count",
}
COLUMNS = tuple(FIELDS.values())
KNOWN = frozenset({"date", "horizon", *FIELDS})
GRADE = "B"  # third-party data (D14)
NM = "not_meaningful"


def num(v: object) -> float | None:
    """A vendor number, or None for null, "None", "" or text."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def source_id(ticker: str, snapshot_date: str) -> str:
    """A non-SEC identifier (LESSONS: mark non-SEC documents in their identifier)."""
    return f"AV-EST-{ticker.upper()}-{snapshot_date}"


# --- storage and rotation ----------------------------------------------------------------


def store(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str,
    rows: Iterable[dict],
    *,
    snapshot_date: str,
    fetched_at: str,
    source_ref: str,
) -> int:
    """Store one reply's rows (caller owns the transaction). Rows without a `date` or a
    `horizon` are skipped (counted by the caller via the return value)."""
    engine.execute(
        "DELETE FROM estimate_snapshot WHERE cik = ? AND snapshot_date = ?", (cik, snapshot_date)
    )
    n = 0
    for r in rows:
        end, horizon = str(r.get("date") or "").strip(), str(r.get("horizon") or "").strip()
        if not end or not horizon:
            continue
        vals = [num(r.get(k)) for k in FIELDS]
        engine.execute(
            f"INSERT OR REPLACE INTO estimate_snapshot (cik, ticker, snapshot_date, horizon, "
            f"period_end, {', '.join(COLUMNS)}, raw, source_ref, fetched_at) VALUES "
            f"(?, ?, ?, ?, ?, {', '.join('?' * len(COLUMNS))}, ?, ?, ?)",
            (cik, ticker, snapshot_date, horizon, end[:10], *vals,
             json.dumps(r, sort_keys=True), source_ref, fetched_at),
        )  # fmt: skip
        n += 1
    return n


def record(
    engine: sqlite3.Connection, cik: str, ticker: str, outcome: str, at: str, detail: str, ref: str
) -> None:
    engine.execute(
        "INSERT OR REPLACE INTO refresh_state (name, source_ref, fetched_at, detail) "
        "VALUES (?, ?, ?, ?)",
        (STATE + cik, ref, at,
         json.dumps({"ticker": ticker, "outcome": outcome, "detail": detail})),
    )  # fmt: skip


def last_attempt(engine: sqlite3.Connection, cik: str) -> dict | None:
    r = engine.execute(
        "SELECT fetched_at, detail FROM refresh_state WHERE name = ?", (STATE + cik,)
    ).fetchone()
    if r is None:
        return None
    try:
        d = json.loads(r["detail"] or "{}")
    except ValueError:
        d = {}
    return {"at": r["fetched_at"], **d}


@dataclass(frozen=True)
class Due:
    ticker: str
    cik: str
    last_at: str = ""  # "" = never asked
    last_outcome: str = ""


def due(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    p: Params | None = None,
    mf: models_mod.ModelFile | None = None,
) -> tuple[list[Due], list[str]]:
    """(companies due now, never asked first then the oldest; names not asked with why)."""
    p = p or Params()
    mf = mf if mf is not None else models_mod.load_safe()
    today = eastern_today(now)
    out, skipped = [], []
    for ticker, cik in sorted(companies.items()):
        tag = mf.for_company(cik, ticker, today.isoformat())
        if tag is not None and tag.tag == "fund":
            skipped.append(f"{ticker}: not asked (fund, D-M04-8)")
            continue
        last = last_attempt(engine, cik)
        if last is None:
            out.append(Due(ticker, cik))
            continue
        age = (today - date.fromisoformat(last["at"][:10])).days
        outcome = last.get("outcome", "")
        wait = {"ok": p.snapshot_every_days, "no_coverage": p.no_coverage_retry_days}.get(
            outcome, 1
        )
        if age >= wait:
            out.append(Due(ticker, cik, last["at"], outcome))
    out.sort(key=lambda d: (d.last_at != "", d.last_at, d.ticker))
    return out, skipped


@dataclass
class FetchRun:
    asked: int = 0
    stored: list[str] = field(default_factory=list)  # "TICKER (n rows)"
    no_coverage: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    stopped: str = ""
    left: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [
            f"estimates: {self.asked} request(s); stored {len(self.stored)}"
            + (f" ({', '.join(self.stored)})" if self.stored else "")
            + f"; no coverage {len(self.no_coverage)}"
            + (f" ({', '.join(self.no_coverage)})" if self.no_coverage else "")
            + f"; failed {len(self.failed)}"
        ]
        out += [f"  failed: {f}" for f in self.failed]
        if self.stopped:
            out.append(
                f"  BUDGET STOP: {self.stopped}; left for the next run: "
                + (", ".join(self.left) or "none")
                + " (their rows read the older snapshot or missing)"
            )
        elif self.left:
            out.append(f"  not asked this run (limit): {', '.join(self.left)}")
        out += [f"  {s}" for s in self.skipped]
        return out


def fetch(
    engine: sqlite3.Connection,
    client: AlphaVantageClient,
    dues: list[Due],
    now: datetime,
    *,
    budget: int = ESTIMATES_BUDGET,
    limit: int | None = None,
) -> FetchRun:
    """Ask each due company in order; a budget stop ends the batch (reported)."""
    run = FetchRun()
    snap_day = eastern_today(now).isoformat()
    todo = dues if limit is None else dues[:limit]
    run.left = [d.ticker for d in dues[len(todo) :]]
    for i, d in enumerate(todo):
        res = client.estimates(d.ticker, budget=budget)
        if isinstance(res, Failed) and res.throttled and "daily budget" in res.reason:
            run.stopped = res.reason
            run.left = [x.ticker for x in todo[i:]] + run.left
            break
        run.asked += 1
        at = iso(now)
        engine.execute("BEGIN")
        try:
            if isinstance(res, Failed):
                record(engine, d.cik, d.ticker, "failed", at, res.reason, res.url or "")
                run.failed.append(f"{d.ticker}: {res.reason}")
                if res.throttled:
                    run.stopped = res.reason
            else:
                reply = res.data
                n = 0
                if reply.rows:
                    n = store(engine, d.cik, d.ticker, reply.rows, snapshot_date=snap_day,
                              fetched_at=res.fetched_at or at,
                              source_ref=res.source_ref or "")  # fmt: skip
                if n:
                    record(engine, d.cik, d.ticker, "ok", at, f"{n} rows", res.source_ref or "")
                    run.stored.append(f"{d.ticker} ({n} rows)")
                else:
                    why = reply.note or "no usable rows (no date or horizon)"
                    record(engine, d.cik, d.ticker, "no_coverage", at, why, res.source_ref or "")
                    run.no_coverage.append(d.ticker)
            engine.execute("COMMIT")
        except Exception:
            engine.execute("ROLLBACK")
            raise
        if run.stopped:  # a vendor rate-limit reply also ends the batch
            run.left = [x.ticker for x in todo[i + 1 :]] + run.left
            break
    return run


# --- reading -------------------------------------------------------------------------------


@dataclass(frozen=True)
class EstRow:
    horizon: str
    period_end: str
    v: dict[str, float | None]
    raw: dict

    @property
    def is_year(self) -> bool:
        return "year" in self.horizon.lower()

    def extra_fields(self) -> list[str]:
        return sorted(set(self.raw) - KNOWN)

    def nulls(self) -> list[str]:
        return [k for k in FIELDS if num(self.raw.get(k)) is None]


@dataclass(frozen=True)
class Snap:
    ticker: str
    snapshot_date: str
    source_ref: str
    rows: tuple[EstRow, ...]

    @property
    def source(self) -> Source:
        return Source(source_id(self.ticker, self.snapshot_date), self.snapshot_date, GRADE,
                      "Alpha Vantage EARNINGS_ESTIMATES snapshot")  # fmt: skip


def snapshot_dates(engine: sqlite3.Connection, cik: str) -> list[str]:
    return [
        r[0]
        for r in engine.execute(
            "SELECT DISTINCT snapshot_date FROM estimate_snapshot WHERE cik = ? ORDER BY 1",
            (cik,),
        )
    ]


def latest(engine: sqlite3.Connection, cik: str, upto: str) -> Snap | None:
    """The newest snapshot fetched on or before `upto`."""
    r = engine.execute(
        "SELECT max(snapshot_date) FROM estimate_snapshot WHERE cik = ? AND snapshot_date <= ?",
        (cik, upto),
    ).fetchone()
    if r is None or r[0] is None:
        return None
    day = r[0]
    rows = engine.execute(
        f"SELECT ticker, horizon, period_end, source_ref, raw, {', '.join(COLUMNS)} FROM "
        "estimate_snapshot WHERE cik = ? AND snapshot_date = ? ORDER BY period_end, horizon",
        (cik, day),
    ).fetchall()
    out = tuple(
        EstRow(x["horizon"], x["period_end"], {c: x[c] for c in COLUMNS}, json.loads(x["raw"]))
        for x in rows
    )
    return Snap(rows[0]["ticker"], day, rows[0]["source_ref"], out)


@dataclass(frozen=True)
class Figure:
    """One computed figure: a value (percent or ratio), or a code, or missing."""

    value: float | None = None
    text: str | None = None
    missing: str = ""

    def shown(self, unit: str = "%", digits: int = 2) -> str:
        if self.missing:
            return f"missing ({self.missing})"
        if self.value is None:
            return "n/m" if self.text == NM else (self.text or "—")
        return f"{self.value:+.{digits}f}%" if unit == "%" else f"{self.value:+.{digits}f}"


def revision(now: float | None, then: float | None, min_abs: float) -> Figure:
    """(now ÷ then − 1) in percent; n/m on a small base or a sign change (rule 7)."""
    if now is None or then is None:
        return Figure(missing="vendor average not stated")
    if abs(now) < min_abs or abs(then) < min_abs:
        return Figure(text=NM, missing="")
    if (now > 0) != (then > 0):
        return Figure(text=NM)
    return Figure(value=(now / then - 1) * 100)


def nm_reason(now: float | None, then: float | None, min_abs: float) -> str:
    if now is None or then is None:
        return ""
    if abs(now) < min_abs or abs(then) < min_abs:
        return f"|average| below ${min_abs:.2f}"
    if (now > 0) != (then > 0):
        return "sign change"
    return ""


@dataclass
class Horizon:
    name: str  # FY1, FY2
    row: EstRow
    rev30: Figure
    rev90: Figure
    breadth30: Figure
    dispersion: Figure
    count: float | None
    nm30: str = ""
    nm90: str = ""

    @property
    def avg(self) -> float | None:
        return self.row.v["eps_avg"]

    def text(self) -> str:
        r = self.row
        bits = [
            f"{self.name} {r.period_end} ('{r.horizon}'): avg EPS "
            + (f"{self.avg:.4f}" if self.avg is not None else "not stated"),
            "30-day revision " + self.rev30.shown() + (f" [{self.nm30}]" if self.nm30 else ""),
            "90-day revision " + self.rev90.shown() + (f" [{self.nm90}]" if self.nm90 else ""),
            "breadth 30 d " + self.breadth30.shown("ratio"),
            "dispersion " + self.dispersion.shown(digits=1).lstrip("+"),
            "count " + (f"{self.count:g}" if self.count is not None else "not stated (missing)"),
        ]
        return ", ".join(bits)


def horizon(name: str, row: EstRow, p: Params) -> Horizon:
    v = row.v
    avg, count = v["eps_avg"], v["eps_count"]
    up, down = v["rev_up_30d"], v["rev_down_30d"]
    if up is None or down is None:
        breadth = Figure(missing="vendor revision counts null (never read as 0)")
    elif not count:
        breadth = Figure(missing="analyst count not stated")
    else:
        breadth = Figure(value=(up - down) / count)
    hi, lo = v["eps_high"], v["eps_low"]
    if count is None:
        disp = Figure(missing="analyst count not stated")
    elif count < p.min_count_dispersion:
        disp = Figure(text=f"not computed (count {count:g} < {p.min_count_dispersion})")
    elif hi is None or lo is None or avg is None:
        disp = Figure(missing="high or low not stated")
    elif abs(avg) < p.min_abs_eps:
        disp = Figure(text=NM)
    else:
        disp = Figure(value=(hi - lo) / abs(avg) * 100)
    return Horizon(
        name,
        row,
        revision(avg, v["eps_avg_30d"], p.min_abs_eps),
        revision(avg, v["eps_avg_90d"], p.min_abs_eps),
        breadth,
        disp,
        count,
        nm_reason(avg, v["eps_avg_30d"], p.min_abs_eps),
        nm_reason(avg, v["eps_avg_90d"], p.min_abs_eps),
    )


@dataclass
class Reading:
    snap: Snap | None
    fy1: Horizon | None = None
    fy2: Horizon | None = None
    missing: str = ""  # no snapshot to read
    notes: list[str] = field(default_factory=list)

    @property
    def sources(self) -> list[Source]:
        return [self.snap.source] if self.snap is not None else []

    def coverage(self) -> str:
        """Analysts behind FY1 (outline Analysts item 4: low coverage shown)."""
        if self.fy1 is None or self.fy1.count is None:
            return "coverage: analyst count not stated"
        c = self.fy1.count
        return f"coverage: {c:g} analyst(s)" + (" (low coverage)" if c < 3 else "")


def fiscal_years(
    snap: Snap, reported_fy_end: str | None, day: str
) -> tuple[EstRow | None, EstRow | None, str]:
    """(FY1, FY2, note) mapped by the vendor's period-end dates (D-M08-14)."""
    years = sorted((r for r in snap.rows if r.is_year), key=lambda r: r.period_end)
    after = reported_fy_end or day
    ahead = [r for r in years if r.period_end > after]
    fy1 = ahead[0] if ahead else None
    fy2 = ahead[1] if len(ahead) > 1 else None
    basis = (
        f"after the newest reported fiscal year ({reported_fy_end})"
        if reported_fy_end
        else f"after {day} (no reported fiscal year stored)"
    )
    note = f"FY1/FY2 by vendor period end, {basis}"
    for name, r, label in (("FY1", fy1, "current fiscal year"), ("FY2", fy2, "next fiscal year")):
        if r is not None and r.horizon.lower() != label:
            note += f"; {name} {r.period_end} is labelled '{r.horizon}' by the vendor"
    return fy1, fy2, note


def reading(
    engine: sqlite3.Connection,
    cik: str,
    day: str,
    p: Params,
    *,
    upto: str | None = None,
    reported_fy_end: str | None = None,
) -> Reading:
    """The estimates known at `upto` (default `day`) for a row dated `day`."""
    upto = upto or day
    snap = latest(engine, cik, upto)
    if snap is None:
        first = snapshot_dates(engine, cik)
        why = (
            f"no estimate snapshot on or before {upto} (first {first[0]})"
            if first
            else "no estimate snapshot (budget / no coverage)"
        )
        last = last_attempt(engine, cik)
        if not first and last is not None and last.get("outcome") == "no_coverage":
            why = (
                f"no estimate snapshot: no coverage ({last.get('detail', '')}, asked "
                f"{last['at'][:10]})"
            )
        return Reading(None, missing=why)
    age = (date.fromisoformat(upto) - date.fromisoformat(snap.snapshot_date)).days
    if age > p.snapshot_max_age_days:
        return Reading(
            None,
            missing=f"estimate snapshot {snap.snapshot_date} is {age} days old "
            f"(> {p.snapshot_max_age_days})",
        )
    r = Reading(snap)
    fy1, fy2, note = fiscal_years(snap, reported_fy_end, day)
    r.notes.append(note)
    r.notes.append(f"snapshot {snap.snapshot_date} (vendor basis, non-GAAP; grade B)")
    if fy1 is not None:
        r.fy1 = horizon("FY1", fy1, p)
    if fy2 is not None:
        r.fy2 = horizon("FY2", fy2, p)
    return r


def band(rev: Figure, p: Params) -> str:
    if rev.value is None:
        return NM
    if rev.value >= p.flat_band_pct:
        return "up"
    if rev.value <= -p.flat_band_pct:
        return "down"
    return "flat"


# --- the refresh hook ---------------------------------------------------------------------


def run_fetch_part(
    engine: sqlite3.Connection,
    client: AlphaVantageClient | None,
    companies: dict[str, str],
    now: datetime,
    *,
    params: Params | None = None,
    mf: models_mod.ModelFile | None = None,
    no_client_reason: str = "no client",
) -> list[str]:
    """The weekly rotation inside the refresh, after the transcripts (≤ 3 a day; core and
    promoted names). A budget stop is reported with the names left; never fails the run."""
    head = "M08 estimates — Alpha Vantage EARNINGS_ESTIMATES (≤ 3 a day, after transcripts):"
    try:
        dues, skipped = due(engine, companies, now, params, mf)
        if client is None:
            return [head, f"  skipped — {no_client_reason}; due: "
                    + (", ".join(d.ticker for d in dues) or "none")]  # fmt: skip
        if not dues:
            return [head, "  nothing due (one snapshot per company a week)", *skipped]
        run = fetch(engine, client, dues, now)
        run.skipped = skipped
        return [head, *("  " + x if not x.startswith("  ") else x for x in run.lines())]
    except Exception as e:
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        return [head, f"  error — {type(e).__name__}: {e}"]
