"""Credit-quality and investment-book series per company (D-M02-45 (3)), from stored XBRL.

Series (quarter ends, the company's own history; no thresholds across companies):
- days sales in receivables = receivables ÷ quarterly revenue × days in the quarter
  (Beneish DSRI, S105) — every company tags both;
- trade-receivable allowance ÷ gross receivables (allowance ÷ (net + allowance));
- financing receivables ÷ TTM revenue and their allowance ÷ financing receivables
  (only where tagged: Boeing Capital, Tesla);
- guarantees, maximum exposure ÷ TTM revenue;
- equity investment book = marketable + non-marketable + equity-method stakes (each part
  shown; a missing part stays missing), ÷ total assets.
A tag the company stopped using shows "not tagged since <date>". Alerts (weekly digest,
"noted"): allowance, financing-allowance or guarantee ratio rising two quarters in a
row; DSO rising two quarters in a row by more than 10% in total — against the same
quarter a year earlier when revenue is seasonal (latest four quarters' max ÷ min ≥ 1.3).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from engine.sec.xbrl_facts import Concept, Point, build_concept, get_series

TOL = 10  # days: a quarter end matched across tags
QUARTERS = 8
DSO_RISE = 0.10
SEASONAL = 1.3
RECENT_DAYS = 200  # alerts only on a quarter that ended in the last ~two quarters


def _instant(name: str, *tags: str) -> Concept:
    return Concept(name, tuple(("us-gaap", t) for t in tags), "currency", "instant")


ALLOWANCE = _instant(
    "ar_allowance",
    "AllowanceForDoubtfulAccountsReceivableCurrent",
    "AccountsReceivableAllowanceForCreditLossCurrent",
    "AllowanceForDoubtfulAccountsReceivable",
)
FIN_RECEIVABLES = _instant(
    "financing_receivables",
    "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLoss",
    "FinancingReceivableBeforeAllowanceForCreditLoss",
    "NotesReceivableGross",
    "FinancingReceivable",
)
FIN_ALLOWANCE = _instant(
    "financing_allowance",
    "FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest",
    "FinancingReceivableAllowanceForCreditLosses",
)
GUARANTEES = _instant("guarantees", "GuaranteeObligationsMaximumExposure")
MARKETABLE = _instant("equity_marketable", "EquitySecuritiesFvNi", "EquitySecuritiesFVNINoncurrent")
NONMARKETABLE = _instant(
    "equity_nonmarketable",
    "EquitySecuritiesWithoutReadilyDeterminableFairValueAmount",
    "NonmarketableEquitySecuritiesCarryingValue",
)
EQUITY_METHOD = _instant("equity_method", "EquityMethodInvestments")


@dataclass(frozen=True)
class Obs:
    end: str
    value: float  # the ratio or amount shown
    parts: str = ""  # what it is made of, for the row's note


@dataclass
class Series:
    key: str
    label: str
    unit: str  # days | ratio | usd
    obs: list[Obs] = field(default_factory=list)
    last_tagged: str | None = None  # last quarter end any input tag was reported
    tags: str = ""
    alert: str | None = None
    alerting: bool = True

    @property
    def latest(self) -> Obs | None:
        return self.obs[-1] if self.obs else None

    def stale(self, today: date) -> bool:
        return self.last_tagged is not None and (
            not self.obs
            or date.fromisoformat(self.last_tagged) < today - timedelta(days=RECENT_DAYS)
        )


def _points(engine: sqlite3.Connection, cik: str, c: Concept) -> tuple[list[Point], str]:
    res = build_concept(engine, cik, c)
    if res is None:
        return [], ""
    pts = [p for p in res.points if p.ptype == "I" and p.latest.value is not None]
    return sorted(pts, key=lambda p: p.end), ", ".join(t.split(":")[-1] for t in res.tags_used)


def _near(a: str, b: str) -> bool:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days) <= TOL


def _at(points, end: str):
    return next((p for p in points if _near(p.end, end)), None)


def _quarters(engine, cik) -> list:
    return [r for r in get_series(engine, cik, "revenue", "Q") if r.latest.value]


def _ttm(engine, cik) -> list:
    return [r for r in get_series(engine, cik, "revenue", "TTM") if r.latest.value]


def _rising(vals: list[float]) -> bool:
    return len(vals) >= 3 and vals[-3] < vals[-2] < vals[-1]


def dso(engine: sqlite3.Connection, cik: str) -> Series:
    s = Series("dso", "Days sales in receivables", "days", tags="receivables ÷ quarterly revenue")
    ar = [r for r in get_series(engine, cik, "receivables", "I") if r.latest.value is not None]
    rev = _quarters(engine, cik)
    s.last_tagged = ar[-1].end if ar else None
    for q in rev:
        a = _at(ar, q.end)
        if a is None or not q.start:
            continue
        days = (date.fromisoformat(q.end) - date.fromisoformat(q.start)).days + 1
        s.obs.append(Obs(q.end, float(a.latest.value) / float(q.latest.value) * days))
    s.obs = s.obs[-QUARTERS:]
    vals = [o.value for o in s.obs]
    seasonal = len(rev) >= 4 and (
        max(float(r.latest.value) for r in rev[-4:]) / min(float(r.latest.value) for r in rev[-4:])
        >= SEASONAL
    )
    if seasonal and len(s.obs) >= 6:
        yoy = [s.obs[i].value / s.obs[i - 4].value - 1 for i in range(len(s.obs) - 2, len(s.obs))]
        if all(y > 0 for y in yoy) and yoy[-1] > DSO_RISE:
            s.alert = (
                f"above the same quarter a year earlier twice in a row (latest {yoy[-1]:+.0%})"
            )
    elif _rising(vals) and vals[-1] / vals[-3] - 1 > DSO_RISE:
        s.alert = (
            f"rose two quarters in a row: {vals[-3]:.0f} → {vals[-2]:.0f} → {vals[-1]:.0f} days "
            f"({vals[-1] / vals[-3] - 1:+.0%})"
        )
    return s


def _ratio_series(key, label, num_pts, den_fn, tags, alerting=True) -> Series:
    s = Series(key, label, "ratio", tags=tags, alerting=alerting)
    s.last_tagged = num_pts[-1].end if num_pts else None
    for p in num_pts:
        den = den_fn(p)
        if den:
            s.obs.append(Obs(p.end, float(p.latest.value) / den, f"${float(p.latest.value):,.0f}"))
    s.obs = s.obs[-QUARTERS:]
    vals = [o.value for o in s.obs]
    if alerting and _rising(vals):
        s.alert = f"rose two quarters in a row: {vals[-3]:.2%} → {vals[-2]:.2%} → {vals[-1]:.2%}"
    return s


def allowance(engine: sqlite3.Connection, cik: str) -> Series:
    allow, tags = _points(engine, cik, ALLOWANCE)
    ar = [r for r in get_series(engine, cik, "receivables", "I") if r.latest.value is not None]

    def gross(p):
        a = _at(ar, p.end)
        return float(a.latest.value) + float(p.latest.value) if a else None

    return _ratio_series(
        "allowance", "Trade-receivable allowance ÷ gross receivables", allow, gross, tags
    )


def financing(engine: sqlite3.Connection, cik: str) -> list[Series]:
    rec, rtags = _points(engine, cik, FIN_RECEIVABLES)
    allow, atags = _points(engine, cik, FIN_ALLOWANCE)
    ttm = _ttm(engine, cik)

    def rev(p):
        t = _at(ttm, p.end)
        return float(t.latest.value) if t else None

    def base(p):
        r = _at(rec, p.end)
        return float(r.latest.value) if r else None

    return [
        _ratio_series(
            "fin_receivables",
            "Financing receivables ÷ TTM revenue",
            rec,
            rev,
            rtags,
            alerting=False,
        ),
        _ratio_series(
            "fin_allowance",
            "Financing-receivable allowance ÷ financing receivables",
            allow,
            base,
            atags,
        ),
    ]


def guarantees(engine: sqlite3.Connection, cik: str) -> Series:
    pts, tags = _points(engine, cik, GUARANTEES)
    ttm = _ttm(engine, cik)

    def rev(p):
        t = _at(ttm, p.end)
        return float(t.latest.value) if t else None

    s = _ratio_series("guarantees", "Guarantees, maximum exposure ÷ TTM revenue", pts, rev, tags)
    if pts and not s.obs:  # exposure stated but no TTM revenue at that date: show the amount
        s.unit = "usd"
        s.obs = [Obs(p.end, float(p.latest.value)) for p in pts[-QUARTERS:]]
    return s


def equity_book(engine: sqlite3.Connection, cik: str) -> Series:
    parts = [
        (lbl, *_points(engine, cik, c))
        for lbl, c in (
            ("marketable", MARKETABLE),
            ("non-marketable", NONMARKETABLE),
            ("equity-method", EQUITY_METHOD),
        )
    ]
    assets = [r for r in get_series(engine, cik, "total_assets", "I") if r.latest.value]
    ends = sorted({p.end for _, pts, _ in parts for p in pts})
    s = Series(
        "equity_book",
        "Equity investment book ÷ total assets",
        "ratio",
        tags=", ".join(t for _, _, t in parts if t),
        alerting=False,
    )
    s.last_tagged = ends[-1] if ends else None
    seen: list[str] = []
    for end in ends:
        if any(_near(end, e) for e in seen):
            continue
        seen.append(end)
        got = [(lbl, _at(pts, end)) for lbl, pts, _ in parts]
        got = [(lbl, p) for lbl, p in got if p is not None]
        a = _at(assets, end)
        if not got or a is None:
            continue
        total = sum(float(p.latest.value) for _, p in got)
        desc = " + ".join(f"{lbl} ${float(p.latest.value) / 1e9:,.1f}B" for lbl, p in got)
        s.obs.append(Obs(end, total / float(a.latest.value), f"${total / 1e9:,.1f}B = {desc}"))
    s.obs = s.obs[-QUARTERS:]
    return s


def company_series(engine: sqlite3.Connection, cik: str) -> list[Series]:
    return [
        dso(engine, cik),
        allowance(engine, cik),
        *financing(engine, cik),
        guarantees(engine, cik),
        equity_book(engine, cik),
    ]


def queue_alerts(engine: sqlite3.Connection, ciks: dict[str, str], now: datetime) -> int:
    """One weekly-digest item per company, series and quarter that triggers (D-M02-43)."""
    from engine.themes.proposals import propose

    n = 0
    cutoff = (now.date() - timedelta(days=RECENT_DAYS)).isoformat()
    for ticker, cik in sorted(ciks.items()):
        for s in company_series(engine, cik):
            if not s.alert or not s.latest or s.latest.end < cutoff:
                continue
            payload = {
                "ticker": ticker,
                "series": s.label,
                "quarter_end": s.latest.end,
                "change": s.alert,
                "tags": s.tags,
                "why": f"{ticker}: {s.label[0].lower() + s.label[1:]} {s.alert}",
            }
            res = propose(
                engine,
                "m02_fin_alert",
                f"{cik}:{s.key}:{s.latest.end}",
                f"{ticker}: {s.label[0].lower() + s.label[1:]} {s.alert}",
                payload,
                now,
                cik=cik,
            )
            n += res in ("queued", "overflow", "requeued")
    return n
