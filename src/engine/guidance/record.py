"""Guidance record: one outcome per metric, basis and period (D-M04-10, D-M04-79; S1.7).

Shared scorer for M04's Q2 guidance row and M11's R19 ledger (M11 owns scoring weights
and may extend it). Built in M04 Part 1b; stored in `guidance_outcome`, recomputed by the
local pass of every refresh (0 SEC requests).

**Score** (kind 'score'), for a period that has ended:
- the guide scored is the latest given before the period end (newest first; on the same
  day an owner-corrected row beats a release, a release beats a call; D-M02-24, -28);
- a range or ± guide is scored on its low end; a floor ("more than $25B") is a low end;
  ceilings, direction-only, point and "approximately" guides are **unscored** (no
  tolerance yet); rows flagged `not_meaningful` or with an open `guidance_implausible` /
  `guidance_conflict` item are unscored until resolved (D-M04-79);
- direction (D-M04-84): revenue, margin, EPS, income and capex **miss** when below the low
  end (or floor); cost metrics (operating expenses, total expenses, cost of revenue) miss
  when **above** the high end (a ceiling is their high end, a floor is unscored); tax rate
  and other income are **unscored: not a performance target** (still shown);
- capex is scored only on an exact M02 recipe; an approximate recipe or an unmapped clause
  reads **unscored: capex recipe approximate (<clause>)** (Microsoft FY2026 Q4);
- otherwise **hit**; the actual is on the guide's own
  basis: GAAP (and "unspecified", labelled) from first-filed facts via `facts_as_of`;
  non-GAAP needs the stated reconciliation, not stored yet → missing; capex from M02's
  `moneyflow/guided.py` path (`actual_for`, recipe of the guide's clause, shown-actual
  rule; D-M02-29, -33), so one guided-vs-actual result is shared by M02, M04 and M11;
- the outcome takes the guide's grade (call = B, D-M02-21); downward and upward
  revisions before the period end are counted separately (`changes.py`).
- A period not yet ended is **pending**, with M02's freshness state for its metric.

**Removal** (kind 'removal'): for each earnings release, a metric guided at the same
fiscal position a year earlier (same metric, same horizon: next quarter, this fiscal year
…) and absent from this release and its call is checked with M02's freshness states,
extended from capex to every metric family (D-M02-30): only **not restated** (release and
stored call both silent) can be a removal; "call not stored yet", "call unavailable — not
checked" and "latest results not read yet" give **missing** with that state. A stated
reason (a "no outlook" refusal stored in `guidance_skip`, or a withdrawal sentence in this
or the prior release and call) makes it **unscored: reason stated**, with the quote. A
removal whose period has ended reads **expired**. Only the core families (revenue, gross
margin, EPS, operating income, net income, capex, FCF) count as removed or expired and
feed `guidance_removed` / M01 rule 4; any other family's is **dropped** ("dropped
(information)"), stored and shown, never in the signal (D-M04-85).

`guidance_hit_rate` = hits ÷ scored guides; "repeated" = 2† misses in the last 4 guided
quarters. A company whose scanned releases (and stored calls) never guide reads "missing
(DS1): release-silent guider". Guidance is a forecast, not a commitment (D-M02-21).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from engine.calls.transcripts import last_quarter
from engine.guidance.changes import changes_for
from engine.guidance.parse import CAPEX_WORDS
from engine.moneyflow.actuals import Book, actual_for, overrides_by_cik, recipe_for
from engine.moneyflow.guided import NO_OUTLOOK, RESULTS_MIN_DAYS, freshness
from engine.moneyflow.periods import fiscal_year_end, span_of
from engine.moneyflow.stated import stated_for
from engine.sec.asof import facts_as_of
from engine.sec.identity import normalize_cik
from engine.signals import Source, write_signal

MODULE = "M04"
NEAR_DAYS = 10
REPEATED_MISSES, REPEATED_WINDOW = 2, 4  # starting values (D-M04-10)
DOWN = frozenset({"lowered", "lowered low end", "lowered high end"})
UP = frozenset({"raised", "raised low end", "raised high end"})
PER_SHARE = frozenset({"eps_diluted"})
# Metric → how its GAAP actual is read (concept, or a ratio of two concepts in percent).
DIRECT = {
    "revenue": "revenue",
    "eps_diluted": "eps_diluted",
    "net_income": "net_income",
    "operating_income": "operating_income",
}
RATIOS = {
    "gross_margin": ("gross_profit", "revenue"),
    "operating_margin": ("operating_income", "revenue"),
    "tax_rate": ("income_tax", "pretax_income"),
}
# Direction of a miss (D-M04-84): performance metrics miss below the low end, cost metrics
# above the high end; a tax rate or other income is not a performance target (unscored).
COST = frozenset({"operating_expenses", "total_expenses", "cost_of_revenue"})
NOT_TARGET = frozenset({"tax_rate", "other_income"})
# Removals that count (D-M04-85): only these families feed `guidance_removed` / M01 rule 4;
# any other family's removal is stored and shown as "dropped (information)".
CORE = frozenset({"revenue", "gross_margin", "eps_diluted", "operating_income", "net_income",
                  "capex", "fcf"})  # fmt: skip
# Withdrawal wording that states why a guide was dropped (reason search, S1.7).
_DROP_REASON = re.compile(
    r"\b(?:(?:not|no longer|won't|will not|do not|don't|are not)\s+(?:be\s+)?"
    r"(?:provid|giv|issu|offer|updat)\w*\s+(?:a\s+|an\s+|our\s+|any\s+)?"
    r"(?:full[- ]year\s+|annual\s+|fiscal[- ]year\s+|long[- ]term\s+)?"
    r"(?:financial\s+)?(?:guidance|outlook|forecast)"
    r"|(?:suspend|withdr[ae]w|withdrawing|withdrawn|discontinu|paus)\w*\s+(?:our\s+|its\s+|the\s+)?"
    r"(?:full[- ]year\s+|annual\s+|fiscal[- ]year\s+)?(?:financial\s+)?(?:guidance|outlook)"
    r"|(?:mov|shift)\w*\s+to\s+(?:a\s+)?quarterly\s+(?:guidance|outlook))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Release:
    accession: str
    filed: str
    fy: int
    q: int

    @property
    def event(self) -> dict:
        return {"accession": self.accession, "filed": self.filed}


@dataclass
class Outcome:
    kind: str  # score | removal
    metric: str
    basis: str
    period: str
    outcome: str  # hit | miss | unscored | removed | expired | missing | pending
    state: str = ""
    guidance_id: int | None = None
    accession: str = ""  # the guide's document
    guide_text: str = ""
    stated_on: str | None = None
    origin: str | None = None
    grade: str | None = None
    actual: float | None = None
    actual_ref: str = ""
    actual_filed: str = ""
    revisions_down: int = 0
    revisions_up: int = 0
    note: str = ""
    reason: tuple[str, str, str] | None = None  # accession, filename, quote
    end: str = ""  # period end date (sorting)
    release: str = ""  # removal: the release checked
    release_filed: str = ""


@dataclass
class Record:
    cik: str
    outcomes: list[Outcome] = field(default_factory=list)
    hits: int = 0
    misses: int = 0
    repeated: bool = False
    missing: str | None = None  # why there is no hit rate
    scanned: int = 0  # earnings releases scanned

    @property
    def scored(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float | None:
        return self.hits / self.scored if self.scored else None


# --- Small helpers -------------------------------------------------------------------------


def money(x: float, metric: str, unit: str) -> str:
    if unit == "%":
        return f"{x:.1f}%".replace("-", "−")
    if metric in PER_SHARE:
        return f"−${abs(x):.2f}" if x < 0 else f"${x:.2f}"
    if unit == "count":
        return f"{x:,.0f}"
    sign = "−" if x < 0 else ""
    x = abs(x)
    return f"{sign}${x / 1e9:,.2f}B" if x >= 1e9 else f"{sign}${x / 1e6:,.0f}M"


def guide_text(r: sqlite3.Row) -> str:
    if r["kind"] == "direction":
        return {"up": "↑", "down": "↓", "flat": "→"}.get(r["direction"] or "", "?") + " no figure"
    lo, hi = float(r["low"]), float(r["high"])
    a, b = money(lo, r["metric"], r["unit"]), money(hi, r["metric"], r["unit"])
    if r["bound"] == "floor":
        return f"≥ {a}"
    if r["bound"] == "ceiling":
        return f"≤ {b}"
    if lo == hi:
        return ("≈ " if r["kind"] == "approx" else "") + a
    return f"{a} to {b}"


def releases(engine: sqlite3.Connection, cik: str) -> list[Release]:
    """Earnings releases (8-K Item 2.02), oldest first, with the fiscal quarter each reports;
    one filed within 10 days of a quarter end is an operating update (D-M02-23)."""
    fye = fiscal_year_end(engine, cik)
    out = []
    for r in engine.execute(
        "SELECT accession, filed, items FROM filing WHERE cik = ? AND form = '8-K' ORDER BY filed",
        (cik,),
    ):
        if not (r["items"] and "2.02" in r["items"].split(",")):
            continue
        filed = date.fromisoformat(r["filed"][:10])
        last = last_quarter(filed, fye)
        if last is None or (filed - last[2]).days < RESULTS_MIN_DAYS:
            continue
        out.append(Release(r["accession"], r["filed"][:10], last[0], last[1]))
    return out


def documents(engine: sqlite3.Connection, release: Release) -> list[str]:
    """The release and its stored call documents."""
    calls = [
        r[0]
        for r in engine.execute(
            "SELECT accession FROM call_document WHERE release_accession = ?", (release.accession,)
        )
    ]
    return [release.accession, *calls]


def horizon(period: str, fy: int, q: int) -> str | None:
    """Fiscal position relative to the reported quarter: 'FY Q+1', 'FY+0', 'CY+1'."""
    m = re.fullmatch(r"(FY|CY)(\d{4})(?: Q([1-4]))?", period)
    if not m:
        return None
    y = int(m[2])
    if m[3]:
        return f"{m[1]} Q{(y * 4 + int(m[3])) - (fy * 4 + q):+d}"
    return f"{m[1]}{y - fy:+d}"


def next_year(period: str) -> str:
    m = re.fullmatch(r"(FY|CY)(\d{4})(.*)", period)
    return f"{m[1]}{int(m[2]) + 1}{m[3]}" if m else period


def _open_review(engine: sqlite3.Connection, r: sqlite3.Row) -> str | None:
    for it in engine.execute(
        "SELECT kind, payload FROM review_queue WHERE resolved_at IS NULL AND cik = ? "
        "AND kind IN ('guidance_implausible', 'guidance_conflict')",
        (r["cik"],),
    ):
        p = json.loads(it["payload"] or "{}")
        if p.get("accession") != r["accession"]:
            continue
        if it["kind"] == "guidance_implausible" and (
            p.get("guidance_id") == r["guidance_id"]
            or (p.get("offsets") or [None])[0] == r["quote_start"]
        ):
            return "open guidance_implausible review"
        if it["kind"] == "guidance_conflict" and p.get("key") == [
            r["metric"],
            r["basis"],
            r["period"],
        ]:
            return "open guidance_conflict review"
    return None


# --- Actuals -------------------------------------------------------------------------------


@dataclass(frozen=True)
class ActualValue:
    value: float | None
    ref: str = ""
    filed: str = ""
    why: str = ""  # reason when missing; label when present


def _point(engine, cik, concept, ptype, end: date, as_of: str, cache: dict | None = None):
    """The point of `concept` ending within ten days of `end`; `cache` keeps one as-of read
    per concept and period type for a company's whole record."""
    key = (cik, concept, ptype, as_of)
    if cache is not None and key in cache:
        points = cache[key]
    else:
        points = facts_as_of(engine, cik, concept, as_of, ptype=ptype).points
        if cache is not None:
            cache[key] = points
    for p in points:
        if abs((date.fromisoformat(p.end) - end).days) <= NEAR_DAYS:
            return p
    return None


def gaap_actual(
    engine: sqlite3.Connection, cik: str, metric: str, span, as_of: str, cache: dict | None = None
) -> ActualValue:
    if span.ptype not in ("Q", "FY"):
        return ActualValue(None, why="calendar-year guide on a non-calendar fiscal year")
    if metric in DIRECT:
        p = _point(engine, cik, DIRECT[metric], span.ptype, span.end, as_of, cache)
        if p is None:
            return ActualValue(None, why=f"no {DIRECT[metric]} fact for the period yet")
        return ActualValue(float(p.first_value), f"{p.first_accession} ({DIRECT[metric]}, "
                           "first filed)", p.first_filed)  # fmt: skip
    if metric in RATIOS:
        num_c, den_c = RATIOS[metric]
        den = _point(engine, cik, den_c, span.ptype, span.end, as_of, cache)
        num = _point(engine, cik, num_c, span.ptype, span.end, as_of, cache)
        how = f"{num_c} ÷ {den_c}"
        if num is None and metric == "gross_margin" and den is not None:
            cost = _point(engine, cik, "cost_of_revenue", span.ptype, span.end, as_of, cache)
            if cost is not None:
                g = float(den.first_value) - float(cost.first_value)
                return ActualValue(
                    g / float(den.first_value) * 100,
                    f"{den.first_accession} (revenue − cost of revenue, derived; first filed)",
                    max(den.first_filed, cost.first_filed),
                )
        if num is None or den is None:
            return ActualValue(None, why=f"no {num_c if num is None else den_c} fact yet")
        if float(den.first_value) <= 0:
            return ActualValue(None, why=f"not meaningful: {den_c} ≤ 0")
        return ActualValue(
            float(num.first_value) / float(den.first_value) * 100,
            f"{den.first_accession} ({how}, first filed)",
            max(num.first_filed, den.first_filed),
        )
    return ActualValue(None, why=f"no actual mapped for {metric}")


def capex_actual(book: Book, period: str, clause, override, stated) -> ActualValue:
    """M02's guided-vs-actual capex; scored only when the recipe is exact (D-M04-3): an
    approximate recipe or an unmapped clause gives "capex recipe approximate (<clause>)"."""
    recipe = recipe_for(clause, override)
    a = actual_for(book, period, clause, override, stated)
    rv = a.recipe
    if recipe.approximate or (rv is not None and rv.approximate):
        what = clause or recipe.label
        if rv is not None and rv.note and not recipe.approximate:
            what = rv.note.removeprefix("approximate: ")
        return ActualValue(
            float(a.shown) if a.shown is not None else None,
            f"{a.label} (M02 guided-vs-actual)",
            "",
            f"capex recipe approximate ({what})",
        )
    if a.shown is None:
        return ActualValue(None, why="no capex actual for the period yet (M02 recipe)")
    ref = a.recipe.how if a.recipe and a.source == "recipe" else (
        f"stated {a.stated.accession}" if a.stated else ""
    )  # fmt: skip
    return ActualValue(float(a.shown), f"{ref} · {a.label} (M02 guided-vs-actual)", "")


# --- Scoring -------------------------------------------------------------------------------


def _latest_before(rows: list[sqlite3.Row], end: date) -> sqlite3.Row | None:
    before = [r for r in rows if date.fromisoformat(r["stated_on"][:10]) <= end]
    if not before:
        return None
    before.sort(
        key=lambda r: (r["stated_on"], r["source"] == "owner", r["origin"] == "release",
                       r["guidance_id"]),
        reverse=True,
    )  # fmt: skip
    return before[0]


def _score_one(r: sqlite3.Row, actual: ActualValue) -> tuple[str, str]:
    """(outcome, state) for a guide row whose period has ended (direction per D-M04-84)."""
    if r["flag"]:
        return "unscored", f"flagged {r['flag']}: {r['flag_reason'] or ''}".strip()
    if r["metric"] in NOT_TARGET:
        return "unscored", "not a performance target (D-M04-84)"
    if r["kind"] == "direction":
        return "unscored", "direction only"
    if actual.why.startswith("capex recipe approximate"):
        return "unscored", actual.why
    if r["metric"] in COST:
        return _score_cost(r, actual)
    if r["bound"] == "ceiling":
        return "unscored", "ceiling (not scored, D-M04-79)"
    if r["bound"] != "floor" and r["kind"] in ("point", "approx"):
        return "unscored", f"{r['kind']} guide: no tolerance yet (D-M04-10)"
    if actual.value is None:
        return "missing", actual.why
    low = float(r["low"])
    if actual.value < low:
        return "miss", "below the floor" if r["bound"] == "floor" else "below the low end"
    if r["bound"] != "floor" and actual.value > float(r["high"]):
        return "hit", "above the range"
    return "hit", "at or above the floor" if r["bound"] == "floor" else "within the range"


def _score_cost(r: sqlite3.Row, actual: ActualValue) -> tuple[str, str]:
    """A cost metric misses above the high end; a ceiling is its high end, a floor is not
    scored (the mirror of D-M04-79; D-M04-84)."""
    if r["bound"] == "floor":
        return "unscored", "floor on a cost metric (not scored, D-M04-84)"
    if r["bound"] != "ceiling" and r["kind"] in ("point", "approx"):
        return "unscored", f"{r['kind']} guide: no tolerance yet (D-M04-10)"
    if actual.value is None:
        return "missing", actual.why
    if actual.value > float(r["high"]):
        return "miss", "above the ceiling" if r["bound"] == "ceiling" else "above the high end"
    if r["bound"] != "ceiling" and actual.value < float(r["low"]):
        return "hit", "below the range"
    return "hit", "at or below the ceiling" if r["bound"] == "ceiling" else "within the range"


def score(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    cik: str,
    today: date,
) -> list[Outcome]:
    fye = fiscal_year_end(engine, cik)
    as_of = today.isoformat()
    rows = engine.execute(
        "SELECT * FROM guidance WHERE cik = ? ORDER BY metric, basis, period", (cik,)
    ).fetchall()
    groups: dict[tuple[str, str, str], list[sqlite3.Row]] = {}
    for r in rows:
        groups.setdefault((r["metric"], r["basis"], r["period"]), []).append(r)
    changes = changes_for(engine, cik)
    book = override = stated = None
    cache: dict = {}
    out: list[Outcome] = []
    for (metric, basis, period), group in sorted(groups.items()):
        span = span_of(period, fye)
        if span is None:
            continue  # "FY2026 remaining" and similar spans are not scored
        r = _latest_before(group, span.end)
        if r is None:
            continue  # stated only after the period ended: a reported actual, not a guide
        o = Outcome("score", metric, basis, period, "pending", guidance_id=r["guidance_id"],
                    accession=r["accession"], guide_text=guide_text(r), stated_on=r["stated_on"],
                    origin="owner" if r["source"] == "owner" else r["origin"], grade=r["grade"],
                    end=span.end.isoformat())  # fmt: skip
        for c in changes:
            if (c.metric, c.basis, c.period) == (metric, basis, period) and date.fromisoformat(
                c.stated_on[:10]
            ) <= span.end:
                o.revisions_down += c.kind in DOWN
                o.revisions_up += c.kind in UP
        if span.end >= today:
            o.state = freshness(engine, cik, period, today, corpus, metric=metric).state
            out.append(o)
            continue
        review = _open_review(engine, r)
        if review:
            o.outcome, o.state = "unscored", review
            out.append(o)
            continue
        if metric == "capex":
            if book is None:
                book, stated = Book(engine, cik), stated_for(engine, cik)
                override = overrides_by_cik(engine).get(cik)
            act = capex_actual(book, period, r["clause"], override, stated)
        elif basis == "non-GAAP":
            act = ActualValue(None, why="non-GAAP: the stated reconciliation is not stored yet")
        else:
            act = gaap_actual(engine, cik, metric, span, as_of, cache)
            if basis == "unspecified" and act.value is not None:
                o.note = "basis unspecified: scored on GAAP"
        o.outcome, o.state = _score_one(r, act)
        o.actual, o.actual_ref, o.actual_filed = act.value, act.ref, act.filed
        out.append(o)
    return out


# --- Removals ------------------------------------------------------------------------------


def _doc_texts(corpus: sqlite3.Connection, accessions: list[str]):
    marks = ",".join("?" * len(accessions))
    return corpus.execute(
        f"SELECT accession, filename, text FROM document WHERE accession IN ({marks})", accessions
    ).fetchall()


def _sentence(text: str, start: int, end: int) -> str:
    a = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    stops = [i for i in (text.find(".", end), text.find("\n", end)) if i != -1]
    b = min(stops) + 1 if stops else len(text)
    return " ".join(text[a:b].split())


def _fits_metric(sentence: str, metric: str) -> bool:
    """A capex refusal explains a dropped capex guide only; a generic one explains any."""
    return metric == "capex" or not CAPEX_WORDS.search(sentence)


def stated_reason(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    accessions: list[str],
    metric: str,
) -> tuple[str, str, str] | None:
    """A stored "no outlook" refusal or a withdrawal sentence in these documents that fits
    the metric (a "no 2027 capex outlook" sentence does not explain a dropped tax rate)."""
    if corpus is None or not accessions:
        return None
    marks = ",".join("?" * len(accessions))
    for s in engine.execute(
        f"SELECT accession, filename, start_offset, end_offset FROM guidance_skip "
        f"WHERE accession IN ({marks}) AND reason = ?",
        (*accessions, NO_OUTLOOK),
    ):
        row = corpus.execute(
            "SELECT substr(text, ? + 1, ? - ?) FROM document WHERE accession = ? AND filename = ?",
            (s["start_offset"], s["end_offset"], s["start_offset"], s["accession"], s["filename"]),
        ).fetchone()
        if row and row[0] and _fits_metric(row[0], metric):
            return s["accession"], s["filename"], " ".join(row[0].split())
    for d in _doc_texts(corpus, accessions):
        text = d["text"] or ""
        for m in _DROP_REASON.finditer(text):
            sent = _sentence(text, m.start(), m.end())
            if _fits_metric(sent, metric):
                return d["accession"], d["filename"], sent
    return None


def removals(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    cik: str,
    today: date,
) -> list[Outcome]:
    fye = fiscal_year_end(engine, cik)
    rel = releases(engine, cik)
    out: list[Outcome] = []
    for i, cur in enumerate(rel):
        earlier = next((e for e in rel if (e.fy, e.q) == (cur.fy - 1, cur.q)), None)
        if earlier is None:
            continue
        prior = rel[i - 1] if i > 0 else None

        def families(r: Release) -> dict[tuple[str, str], sqlite3.Row]:
            docs = documents(engine, r)
            marks = ",".join("?" * len(docs))
            fam: dict[tuple[str, str], sqlite3.Row] = {}
            for g in engine.execute(
                f"SELECT * FROM guidance WHERE cik = ? AND accession IN ({marks}) "
                "ORDER BY origin = 'release' DESC, guidance_id",
                (cik, *docs),
            ):
                h = horizon(g["period"], r.fy, r.q)
                if h is not None:
                    fam.setdefault((g["metric"], h), g)
            return fam

        before, now = families(earlier), families(cur)
        for (metric, h), g in sorted(before.items()):
            if (metric, h) in now:
                continue
            expected = next_year(g["period"])
            span = span_of(expected, fye)
            text = f"{guide_text(g)} for {g['period']} (stated {g['stated_on'][:10]})"
            o = Outcome("removal", metric, "any", expected, "removed", guidance_id=g["guidance_id"],
                        accession=g["accession"], guide_text=text,
                        stated_on=g["stated_on"], origin=g["origin"], grade=g["grade"],
                        end=span.end.isoformat() if span else "", release=cur.accession,
                        release_filed=cur.filed)  # fmt: skip
            if span is not None and span.end < today:
                o.outcome, o.state = (
                    "expired",
                    f"period ended {span.end}; not guided at {cur.filed}",
                )
                out.append(_information(o))
                continue
            st = freshness(engine, cik, expected, today, corpus, metric=metric, event=cur.event)
            if st.state == "company gives no outlook yet":
                o.outcome, o.state = "unscored", "reason stated"
                o.reason = stated_reason(engine, corpus, documents(engine, cur), metric)
                o.note = st.why
            elif st.state != "not restated":
                o.outcome, o.state = "missing", st.state
                o.note = st.why
            else:
                docs = documents(engine, cur) + (documents(engine, prior) if prior else [])
                reason = stated_reason(engine, corpus, docs, metric)
                if reason is not None:
                    o.outcome, o.state, o.reason = "unscored", "reason stated", reason
                else:
                    o.state = "not restated: release and call silent, no reason stated"
                    if corpus is None:
                        o.note = "reason not searched (no corpus)"
            out.append(_information(o))
    return out


def _information(o: Outcome) -> Outcome:
    """A removal (or expiry) outside the core families is "dropped (information)", never in
    the `guidance_removed` signal (D-M04-85)."""
    if o.outcome in ("removed", "expired") and o.metric not in CORE:
        o.state = f"dropped (information): {o.outcome}; {o.state}"
        o.outcome = "dropped"
    return o


# --- Record, storage, signals --------------------------------------------------------------


_RANK = {"removed": 0, "expired": 0, "dropped": 0, "unscored": 1, "missing": 2}


def _first_findings(found: list[Outcome]) -> list[Outcome]:
    """One removal row per metric and expected period: a removal (or expiry) over a stated
    reason over a missing state; among equals, the earliest release (the event's date)."""
    best: dict[tuple[str, str], Outcome] = {}
    for o in found:  # oldest release first
        k = (o.metric, o.period)
        if k not in best or _RANK[o.outcome] < _RANK[best[k].outcome]:
            best[k] = o
    return list(best.values())


def _repeated(outcomes: list[Outcome]) -> bool:
    quarters: dict[str, list[str]] = {}
    for o in outcomes:
        if o.kind == "score" and o.outcome in ("hit", "miss") and " Q" in o.period:
            quarters.setdefault(o.period, []).append(o.outcome)
    last = sorted(quarters, key=lambda p: next(o.end for o in outcomes if o.period == p))[
        -REPEATED_WINDOW:
    ]
    return sum(1 for p in last if "miss" in quarters[p]) >= REPEATED_MISSES


def record_for(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    cik: str,
    today: date,
) -> Record:
    norm = normalize_cik(cik) or cik
    rec = Record(norm)
    rec.outcomes = score(engine, corpus, norm, today) + _first_findings(
        removals(engine, corpus, norm, today)
    )
    rec.hits = sum(1 for o in rec.outcomes if o.kind == "score" and o.outcome == "hit")
    rec.misses = sum(1 for o in rec.outcomes if o.kind == "score" and o.outcome == "miss")
    rec.repeated = _repeated(rec.outcomes)
    rec.scanned = engine.execute(
        "SELECT count(*) FROM guidance_scan WHERE cik = ?", (norm,)
    ).fetchone()[0]
    any_guide = engine.execute("SELECT 1 FROM guidance WHERE cik = ? LIMIT 1", (norm,)).fetchone()
    if not rec.scored:
        if any_guide is None and rec.scanned:
            rec.missing = (
                f"(DS1) release-silent guider: no guidance in {rec.scanned} scanned earnings "
                "release(s) or stored calls"
            )
        elif any_guide is None:
            rec.missing = "no earnings release scanned"
        else:
            counts: dict[str, int] = {}
            for o in rec.outcomes:
                if o.kind == "score":
                    counts[o.outcome] = counts.get(o.outcome, 0) + 1
            rec.missing = (
                "no scored guide yet ("
                + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
                + ")"
            )
    return rec


def store(engine: sqlite3.Connection, rec: Record, now: str) -> int:
    """Replace the company's `guidance_outcome` rows. Caller owns the transaction."""
    engine.execute("DELETE FROM guidance_outcome WHERE cik = ?", (rec.cik,))
    rows = []
    for o in rec.outcomes:
        acc, fn, quote = o.reason or (None, None, None)
        rows.append((
            rec.cik, o.kind, o.metric, o.basis, o.period, o.guidance_id, o.guide_text,
            o.stated_on, o.origin, o.grade, o.actual, o.actual_ref or None, o.outcome,
            o.state or None, o.revisions_down, o.revisions_up,
            "; ".join(x for x in (o.note, f"release {o.release_filed}" if o.release else "") if x)
            or None, acc, fn, quote, now,
        ))  # fmt: skip
    engine.executemany(
        "INSERT INTO guidance_outcome (cik, kind, metric, basis, period, guidance_id, guide_text, "
        "stated_on, origin, grade, actual, actual_ref, outcome, state, revisions_down, "
        "revisions_up, note, reason_accession, reason_filename, reason_quote, computed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def write_signals(engine: sqlite3.Connection, rec: Record, ticker: str | None, today: date) -> int:
    """`guidance_hit_rate` (MY, PT; ST info) and `guidance_removed` events (info)."""
    n = 0
    scored = [o for o in rec.outcomes if o.kind == "score" and o.outcome in ("hit", "miss")]
    if scored:
        down = sum(o.revisions_down for o in scored)
        method = (
            f"hit rate over n = {rec.scored} scored guides ({rec.hits} hits, {rec.misses} "
            f"misses; miss = below the low end of the latest guide before period end, "
            f"D-M04-10, -79); repeated: {'yes' if rec.repeated else 'no'} "
            f"({REPEATED_MISSES}† misses in the last {REPEATED_WINDOW} guided quarters); "
            f"downward revisions {down}"
        )
        sources = [Source(o.accession, (o.stated_on or "")[:10], o.grade or "A",
                          f"{o.metric} {o.period}") for o in scored]  # fmt: skip
        as_of = max((o.actual_filed or o.end) for o in scored)
        n += write_signal(
            engine, cik=rec.cik, ticker=ticker, module_id=MODULE, signal="guidance_hit_rate",
            as_of=as_of, value=round(100 * rec.hits / rec.scored, 1), method=method,
            sources=sources, info=("ST",),
        )  # fmt: skip
    else:
        n += write_signal(
            engine, cik=rec.cik, ticker=ticker, module_id=MODULE, signal="guidance_hit_rate",
            as_of=today.isoformat(), method="guidance record (D-M04-10)",
            missing=rec.missing or "no scored guide", info=("ST",),
        )  # fmt: skip
    events: dict[str, list[Outcome]] = {}
    for o in rec.outcomes:
        if o.kind == "removal" and o.outcome in ("removed", "expired"):
            events.setdefault(o.release_filed, []).append(o)
    for filed, found in sorted(events.items()):
        # One event per release (the signal key has no metric): "removed" when any guide was
        # dropped for a period not yet ended, else "expired"; every metric in the method.
        state = "removed" if any(o.outcome == "removed" for o in found) else "expired"
        what = "; ".join(
            f"{o.metric} {o.period} {o.outcome} (guided a year earlier: {o.guide_text})"
            for o in sorted(found, key=lambda o: o.metric)
        )
        sources = [Source(found[0].release, filed, "A", "release")] + [
            Source(o.accession, (o.stated_on or "")[:10], o.grade or "A", "guide a year earlier")
            for o in found
        ]
        n += write_signal(
            engine, cik=rec.cik, ticker=ticker, module_id=MODULE, signal="guidance_removed",
            as_of=filed, value_text=state,
            method=f"absent from the release of {filed} and its call, release and call silent, "
                   f"no reason stated (S1.7): {what}",
            sources=sources, info=("MY", "PT", "ST"),
        )  # fmt: skip
    return n
