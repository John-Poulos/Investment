"""Survival gate: numbers (M04 Part 4a; D-M04-8, -13, -21, -31…33, -35…38, -61, -86).

Liquidity and legal facts only; runs at every stage; scope by model tag. Altman Z, Z''
and Ohlson O are out of the gate (`distress.py`).

- **Liquidity** = cash + short-term investments (restricted cash excluded) + undrawn
  committed credit that is confirmed, stated for this balance sheet and matures more than
  12 months after it (`credit_line`, D-M04-32, -86). Tagged capacity without a maturity is
  shown, never counted. The balance sheet is the latest one filed by the as-of date
  (cash, total or current assets); cash is read at that date, with labelled fallbacks, and
  never at an older balance sheet (live check 1). Short-term investments: the shared
  concept with its aliases, two fallback tags, then cash-and-investments minus cash
  (labelled); none found → the candidate tags with facts are named.
- **Burn** = −(OCF − total capex) per quarter, the worse of TTM ÷ 4 and the last two
  quarters (D-M04-32); total capex on the company's own-history definition (Part 1b,
  D-M04-3). One quarter only → incomplete; fewer than four → last two only ("short
  history"). Foreign annual filers: fiscal year ÷ 4 up to 16 months, then incomplete
  (D-M04-36). Capex untagged → OCF-only runway, labelled, plus an `m04_gate_input` item.
- **Tiers:** cash burner (OCF < 0 on TTM or the last two quarters; `issuance_funded`
  included): fail < 6 quarters, warn < 8. Capex-funded (OCF > 0, FCF < 0): warn < 8,
  `m04_runway` review < 6, never fails (D-M04-38). Self-funding (FCF ≥ 0 on both): pass.
- **Wall** (D-M04-33): 12-month debt > liquidity fails; + 4 × burn > liquidity warns;
  the 24-month wall is shown. 12-month debt = `DebtCurrent` (commercial paper inside,
  never added twice), else `LongTermDebtCurrent` + `ShortTermBorrowings`; at a fiscal year
  end the larger of that and the year-1 maturity tag.
- **Legal facts:** open 8-K 1.03 / 2.04 / 3.01 states from Part 3 (D-M04-37); an overdue
  filing → incomplete plus an exit warning (D-M04-61); an open 4.02 marks the inputs
  "under non-reliance" and warns (D-M04-21).
- **States** (`value_text`): pass, warn (a pass for M01), fail, incomplete, not_applicable
  (D-M04-31, -35; S4.1). `method` names the trigger or the missing inputs.
- **Scope by tag** (D-M04-8, -13, -35): full gate (untagged, `issuance_funded`);
  liquidity-only (`asset_treasury`, `reit`): the wall, legal facts and filing status are
  tested, the runway is shown only; trust only (`spac_shell` periods, keyed on period
  end): the trust account plus legal facts; not applicable (`fund`, `financial`, untagged
  FF12 group 11), read by M01 as not-pass. The two partial scopes are the build's
  reading of an open design point (M04_FINANCIALS "Open questions").
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from engine.financials import capex as capex_mod
from engine.financials import models as models_mod
from engine.financials import restate
from engine.sec.asof import PERIODIC_FORMS, AsOfPoint, facts_as_of, is_foreign_filer
from engine.sec.identity import normalize_cik
from engine.sec.xbrl_facts import ALL_CONCEPTS, Concept, concept_for
from engine.signals import Source

FAIL_Q = 6.0  # D-M04-32
WARN_Q = 8.0  # starting value †
HORIZON_DAYS = 365  # credit must mature beyond 12 months after the balance sheet
CREDIT_ASOF_DAYS = 45  # a confirmed line counts for the balance sheet it was stated for
FOREIGN_MONTHS = 16  # D-M04-36
NEAR = 10
GATE_ITEMS = ("1.03", "2.04", "3.01")  # D-M04-37
STATES = ("pass", "warn", "fail", "incomplete", "not_applicable")
SEVERITY = {"pass": 0, "warn": 1, "incomplete": 2, "fail": 3}
SCOPES = {
    "full": "full gate",
    "liquidity_only": "liquidity-only",
    "trust_only": "trust only",
    "not_applicable": "not applicable",
}
TIER_NAMES = {
    "self_funding": "self-funding",
    "cash_burner": "cash burner",
    "capex_funded": "capex-funded",
}

_g = lambda *t: tuple(("us-gaap", x) for x in t)  # noqa: E731
TRUST = Concept(
    "trust_account",
    _g("AssetsHeldInTrustNoncurrent", "AssetsHeldInTrust", "AssetsHeldInTrustCurrent"),
    "currency",
    "instant",
)
UNDRAWN_TAGGED = Concept(
    "credit_tagged",
    _g("LineOfCreditFacilityRemainingBorrowingCapacity")
    + (("ifrs-full", "UndrawnBorrowingFacilities"),),
    "currency",
    "instant",
)
DEBT_CURRENT = Concept(
    "debt_current_only",
    _g("DebtCurrent")
    + (("ifrs-full", "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"),),
    "currency",
    "instant",
)
LTD_CURRENT = Concept("ltd_current", _g("LongTermDebtCurrent"), "currency", "instant")
# Cash fallbacks at the balance-sheet date (live check 1: a company whose cash line sits
# under another tag for some years must not fall back to an older balance sheet). The
# cash-flow total includes restricted cash: restricted cash tagged at the date is taken
# out; untagged, the label says so. Always labelled in `method`.
CASH_WITH_RESTRICTED = Concept(
    "cash_with_restricted",
    _g("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "currency",
    "instant",
)
CASH_ONLY = Concept("cash_only", _g("Cash"), "currency", "instant")
# Short-term investments: the shared concept (tag priority, per-company aliases such as
# NVDA's extension tag, read through `facts_as_of`) plus two older or narrower tags; the
# combined cash-and-investments total minus cash is the last, labelled fallback.
STI_MORE = _g("AvailableForSaleSecuritiesCurrent", "OtherShortTermInvestments")
CASH_AND_STI = Concept(
    "cash_and_sti", _g("CashCashEquivalentsAndShortTermInvestments"), "currency", "instant"
)


def sti_concept() -> Concept:
    """`short_term_investments` with the gate's fallback tags after its own (marked); the
    name is kept so `concept_for` still appends the company aliases (lowest priority)."""
    base = ALL_CONCEPTS["short_term_investments"]
    return replace(
        base,
        tags=base.tags + STI_MORE,
        marks=base.marks + tuple((t, g, "≈ fallback tag (M04 gate)") for t, g in STI_MORE),
    )


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def _near(a: str, b: str, days: int = NEAR) -> bool:
    return abs((_d(a) - _d(b)).days) <= days


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return date(year, month, 28)


def money(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v / 1e6:,.0f}M" if abs(v) >= 1e6 else f"{v:,.0f}"


@dataclass
class Credit:
    line_id: int | None
    facility: str
    amount: float
    maturity: str
    as_of: str
    grade: str
    source: str
    counted: bool
    why: str
    beyond_24m: bool = False


@dataclass
class Basis:
    name: str  # "last two quarters" | "TTM ÷ 4" | "fiscal year ÷ 4"
    end: str
    ocf: float  # total over the basis
    capex: float | None  # total over the basis; None = untagged (OCF-only)
    quarters: float  # 2, 4 or 4 (annual)

    @property
    def fcf(self) -> float:
        return self.ocf - (self.capex or 0.0)

    @property
    def per_q(self) -> float:
        return self.fcf / self.quarters

    @property
    def burn(self) -> float:
        return max(0.0, -self.per_q)


@dataclass
class Gate:
    cik: str
    ticker: str | None
    as_of: str
    scope: str = "full"
    scope_text: str = ""
    tag: str | None = None
    state: str = "pass"
    triggers: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    balance_date: str | None = None
    input_age: str = ""
    cash: float | None = None
    sti: float | None = None
    restricted: float | None = None
    trust: float | None = None
    credits: list[Credit] = field(default_factory=list)
    tagged_capacity: float | None = None
    liquidity_cash: float | None = None
    liquidity: float | None = None
    bases: list[Basis] = field(default_factory=list)
    basis_note: str = ""
    tier: str | None = None
    burn: float | None = None
    burn_basis: str = ""
    runway: float | None = None  # with counted credit, worse basis
    runway_cash: float | None = None  # cash only, worse basis
    runway_by_basis: dict[str, float | None] = field(default_factory=dict)
    capex_mark: str = ""
    ocf_only: bool = False
    runway_test: tuple[str, str] = ("n/a", "")
    debt12: float | None = None
    debt12_text: str = ""
    debt24: float | None = None
    debt24_text: str = ""
    wall_ratio: float | None = None
    wall_test: tuple[str, str] = ("n/a", "")
    events: list[str] = field(default_factory=list)
    other_events: list[str] = field(default_factory=list)
    non_reliance: str = ""
    filing_status: str = ""
    overdue: bool = False
    overdue_due: str = ""
    exit_warning: list[str] = field(default_factory=list)
    runway_review: bool = False  # capex-funded runway < 6 (m04_runway)
    gate_inputs: list[tuple[str, str]] = field(default_factory=list)  # (input, why)
    total_assets: float | None = None
    runway_no_growth: str = ""  # information (D-M04-6)
    raised: str = ""  # share of liquidity raised in the last 4 quarters (S4.13, for Part 5)
    sources: list[Source] = field(default_factory=list)
    signal_as_of: str = ""

    @property
    def scope_name(self) -> str:
        return SCOPES.get(self.scope, self.scope)

    @property
    def tier_text(self) -> str:
        return TIER_NAMES.get(self.tier or "", "—")

    def runway_text(self) -> str:
        if self.tier == "self_funding":
            return "self-funding"
        if self.runway is None:
            return "—"
        out = f"{self.runway:.1f} q"
        if self.credits and self.runway_cash is not None and self.runway_cash != self.runway:
            out += f" ({self.runway_cash:.1f} cash-only)"
        return out

    def method(self) -> str:
        """The trigger or the missing inputs first (S4.1), then the parts."""
        head = []
        if self.triggers:
            head.append("trigger: " + "; ".join(self.triggers))
        if self.missing:
            head.append("missing: " + "; ".join(self.missing))
        if self.warnings:
            head.append("warn: " + "; ".join(self.warnings))
        if not head:
            head.append("no trigger")
        parts = [f"scope: {self.scope_text or self.scope_name}"]
        if self.balance_date:
            parts.append(
                f"balance sheet {self.balance_date}"
                + (f" ({self.input_age})" if self.input_age else "")
            )
        if self.liquidity is not None:
            parts.append(f"liquidity {money(self.liquidity)} = {self.liquidity_parts()}")
        if self.tier:
            parts.append(f"tier {self.tier_text}")
        if self.runway is not None or self.tier == "self_funding":
            parts.append(
                f"runway {self.runway_text()}"
                + (f" on {self.burn_basis}" if self.burn_basis else "")
            )
        if self.runway_test[1]:
            parts.append(f"runway test: {self.runway_test[1]}")
        if self.wall_test[1]:
            parts.append(f"wall: {self.wall_test[1]}")
        if self.debt24_text:
            parts.append(f"24-month wall: {self.debt24_text}")
        if self.non_reliance:
            parts.append(self.non_reliance)
        if self.filing_status:
            parts.append(f"filing status {self.filing_status}")
        if self.exit_warning:
            parts.append("exit warning: " + "; ".join(self.exit_warning))
        parts += self.notes
        return "; ".join(head + parts)

    def liquidity_parts(self) -> str:
        if self.scope == "trust_only":
            return f"trust {money(self.trust)}"
        bits = [f"cash {money(self.cash)}"]
        bits.append(
            f"ST investments {money(self.sti)}"
            if self.sti is not None
            else "ST investments none tagged"
        )
        counted = [c for c in self.credits if c.counted]
        if counted:
            bits.append(
                "credit "
                + " + ".join(f"{money(c.amount)} {c.facility} (to {c.maturity})" for c in counted)
            )
        else:
            bits.append("credit: none confirmed (cash-only)")
        return " + ".join(bits)


# --- Reading inputs ------------------------------------------------------------------------


def _points(
    engine: sqlite3.Connection,
    cik: str,
    concept: str | Concept,
    as_of: str,
    ptype: str,
    shell: bool = False,
) -> dict[str, AsOfPoint]:
    return {
        p.end: p
        for p in facts_as_of(engine, cik, concept, as_of, ptype=ptype, include_shell=shell).points
    }


def _at(points: dict[str, AsOfPoint], end: str | None, days: int = NEAR) -> AsOfPoint | None:
    if end is None:
        return None
    if end in points:
        return points[end]
    return next((p for e, p in sorted(points.items(), reverse=True) if _near(e, end, days)), None)


def _latest(points: dict[str, AsOfPoint], on_or_before: str | None = None) -> AsOfPoint | None:
    ends = [e for e in points if on_or_before is None or e <= on_or_before]
    return points[max(ends)] if ends else None


def balance_anchor(
    engine: sqlite3.Connection, cik: str, as_of: str, cash_pts: dict[str, AsOfPoint]
) -> str | None:
    """The latest balance sheet filed on or before `as_of`: the newest instant among cash,
    total assets and current assets. Cash is then read at this date, never at an older one
    (live check 1: Intel FY2024 read a 2021 balance sheet when its cash tag was absent)."""
    ends = list(cash_pts)
    for name in ("total_assets", "current_assets"):
        ends += list(_points(engine, cik, name, as_of, "I"))
    return max(ends, default=None)


def _periodic_marks() -> tuple[str, list[str]]:
    forms = sorted(PERIODIC_FORMS)
    return ",".join("?" * len(forms)), forms


def tags_at(
    engine: sqlite3.Connection, cik: str, end: str, as_of: str, like: str = "%Cash%"
) -> list[str]:
    """Instant tags (name LIKE `like`) the company filed for `end` by `as_of`, with values:
    the log shows them when an input is missing at the balance sheet."""
    marks, forms = _periodic_marks()
    lo = (_d(end) - timedelta(days=NEAR)).isoformat()
    hi = (_d(end) + timedelta(days=NEAR)).isoformat()
    rows = engine.execute(
        "SELECT taxonomy, tag, max(value) AS v FROM fact WHERE cik = ? AND period_start IS NULL "
        "AND period_end BETWEEN ? AND ? AND filed <= ? AND tag LIKE ? AND unit = 'USD' "
        f"AND form IN ({marks}) GROUP BY taxonomy, tag ORDER BY tag",
        (cik, lo, hi, as_of, like, *forms),
    ).fetchall()
    return [f"{r['taxonomy']}:{r['tag']} {money(float(r['v']))}" for r in rows]


def tags_present(
    engine: sqlite3.Connection, cik: str, tags: tuple[tuple[str, str], ...], as_of: str
) -> tuple[list[str], list[str]]:
    """(tags with any instant facts by `as_of`, "tag (latest end)"; tags with none)."""
    have, none = [], []
    for tax, tag in tags:
        row = engine.execute(
            "SELECT max(period_end) FROM fact WHERE cik = ? AND taxonomy = ? AND tag = ? "
            "AND period_start IS NULL AND filed <= ?",
            (cik, tax, tag, as_of),
        ).fetchone()
        if row and row[0]:
            have.append(f"{tax}:{tag} (latest {row[0]})")
        else:
            none.append(f"{tax}:{tag}")
    return have, none


def owner_maps(engine: sqlite3.Connection, cik: str) -> dict[str, dict]:
    """The owner's answers on `m04_gate_input` items: input → {"tag": "us-gaap:X"} or
    {"not_reported": true} (refresh_state `m04_gate_map:<cik>:<input>`)."""
    out = {}
    for r in engine.execute(
        "SELECT name, detail FROM refresh_state WHERE name LIKE ?", (f"m04_gate_map:{cik}:%",)
    ):
        try:
            out[r["name"].rsplit(":", 1)[1]] = json.loads(r["detail"] or "{}")
        except json.JSONDecodeError:
            continue
    return out


def _with_map(base: Concept, mapping: dict | None) -> Concept:
    tag = (mapping or {}).get("tag")
    if not tag or ":" not in tag:
        return base
    tax, name = tag.split(":", 1)
    return Concept(
        base.name,
        base.tags + ((tax, name),),
        base.unit,
        base.kind,
        base.additive,
        base.marks + ((tax, name, "owner-mapped tag (m04_gate_input)"),),
    )


def capex_concept(engine: sqlite3.Connection, cik: str, as_of: str) -> tuple[Concept, str]:
    """Quarterly total capex on the definition Part 1b uses for the company's own history
    (D-M04-3), the other definition's tags after it as the fallback (a company with no
    fiscal-year capex yet, e.g. one 10-Q): (concept, the main definition's mark or "")."""
    ppe, prod = capex_mod.definitions(cik)
    years = capex_mod.total_capex(engine, cik, as_of)
    main = years[-1].definition if years else "ppe"
    first, second = (prod, ppe) if main == "productive" else (ppe, prod)
    tags = tuple((t, g) for t, g, _ in first.tags + second.tags)
    marks = tuple((t, g, m) for t, g, m in first.tags + second.tags if m)
    mark = next((m for _, _, m in first.tags if m), "")
    return Concept("gate_capex", tags, "currency", "flow", marks=marks), mark


def credit_lines(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT * FROM credit_line WHERE cik = ? ORDER BY as_of DESC, maturity, line_id",
        (cik,),
    ).fetchall()


def _credits(
    engine: sqlite3.Connection, cik: str, balance: str, extra: tuple[Credit, ...] = ()
) -> list[Credit]:
    """Confirmed lines (and `extra`, e.g. a regression case's stated lines) judged against
    this balance sheet."""
    horizon = (_d(balance) + timedelta(days=HORIZON_DAYS)).isoformat()
    beyond24 = (_d(balance) + timedelta(days=2 * HORIZON_DAYS)).isoformat()
    lo = (_d(balance) - timedelta(days=CREDIT_ASOF_DAYS)).isoformat()
    rows = [
        Credit(
            r["line_id"],
            r["facility"],
            float(r["amount"]),
            r["maturity"],
            r["as_of"],
            r["grade"],
            r["source_url"] or r["source_text"],
            False,
            "",
        )
        for r in credit_lines(engine, cik)
        if r["status"] == "confirmed"
    ]
    out = []
    for c in [*rows, *extra]:
        c = Credit(**c.__dict__)
        if c.as_of > balance:  # stated for a later balance sheet (a historical as-of read)
            continue
        if c.as_of < lo:
            c.why = f"stated for {c.as_of}, not this balance sheet ({balance}): confirm again"
            out.append(c)
            continue
        if c.maturity <= horizon:
            c.why = f"matures {c.maturity}, inside 12 months: not counted"
        else:
            c.counted = True
            c.why = f"matures {c.maturity}, beyond 12 months"
            c.beyond_24m = c.maturity > beyond24
        out.append(c)
    return out


def _debt12(
    engine: sqlite3.Connection, cik: str, as_of: str, balance: str, shell: bool
) -> tuple[float | None, str, list[AsOfPoint]]:
    dc = _at(_points(engine, cik, DEBT_CURRENT, as_of, "I", shell), balance)
    ltdc = _at(_points(engine, cik, LTD_CURRENT, as_of, "I", shell), balance)
    stb = _at(_points(engine, cik, "short_term_borrowings", as_of, "I", shell), balance)
    cp = _at(_points(engine, cik, "commercial_paper", as_of, "I", shell), balance)
    y1s = _points(engine, cik, "debt_due_y1", as_of, "I", shell)
    used: list[AsOfPoint] = []
    base, text = None, ""
    if dc is not None:
        base, text = float(dc.value), f"DebtCurrent {money(dc.value)}"
        used.append(dc)
        if cp is not None:
            text += f" (commercial paper {money(cp.value)} inside, not added twice)"
    elif ltdc is not None:
        base = float(ltdc.value) + (float(stb.value) if stb is not None else 0.0)
        text = f"LongTermDebtCurrent {money(ltdc.value)}" + (
            f" + ShortTermBorrowings {money(stb.value)}" if stb is not None else ""
        )
        used += [p for p in (ltdc, stb) if p is not None]
        if cp is not None:
            text += " (commercial paper not added)"
    elif stb is not None:
        base, text = float(stb.value), f"ShortTermBorrowings {money(stb.value)}"
        used.append(stb)
    elif cp is not None:
        base, text = float(cp.value), f"CommercialPaper {money(cp.value)}"
        used.append(cp)
    y1 = _at(y1s, balance)
    if y1 is not None:
        used.append(y1)
        if base is None or float(y1.value) > base:
            text = f"year-1 maturities {money(y1.value)}" + (
                f" (larger than {text})" if base is not None else ""
            )
            base = float(y1.value)
        else:
            text += f" (year-1 maturities {money(y1.value)})"
    elif base is None:
        old = _latest(y1s, balance)
        if old is not None and (_d(balance) - _d(old.end)).days <= 366:
            base = float(old.value)
            text = f"year-1 maturities {money(old.value)} of the {old.end} schedule"
            used.append(old)
    return base, text, used


def _debt24(
    engine: sqlite3.Connection, cik: str, as_of: str, balance: str, d12: float | None, shell: bool
) -> tuple[float | None, str, AsOfPoint | None]:
    y2 = _latest(_points(engine, cik, "debt_due_y2", as_of, "I", shell), balance)
    if y2 is None or (_d(balance) - _d(y2.end)).days > 366:
        return None, "no maturity schedule tagged", None
    total = (d12 or 0.0) + float(y2.value)
    return (
        total,
        (
            f"12-month {money(d12) if d12 is not None else 'none'} + year-2 "
            f"{money(y2.value)} (schedule {y2.end}) = {money(total)}"
        ),
        y2,
    )


def _quarter_chain(q: dict[str, AsOfPoint], end: str) -> list[AsOfPoint]:
    """The quarter ending at `end` and the one before it, if contiguous."""
    last = _at(q, end)
    if last is None:
        return []
    out = [last]
    prev = [
        p for e, p in q.items() if p.end < last.end and 60 <= (_d(last.end) - _d(e)).days <= 120
    ]
    if prev:
        out.insert(0, max(prev, key=lambda p: p.end))
    return out


def _src(p: AsOfPoint | None, what: str) -> list[Source]:
    return [Source(p.accession, p.filed, "A", what)] if p is not None else []


def scope_of(
    engine: sqlite3.Connection,
    mf: models_mod.ModelFile,
    cik: str,
    ticker: str | None,
    period_end: str | None,
) -> tuple[str, str | None, str]:
    """(scope, tag, how) by tag first, then SIC (D-M04-8, -13, -35)."""
    tag, how = models_mod.route(engine, mf, cik, ticker, period_end)
    if tag in ("fund", "financial"):
        return "not_applicable", tag, how
    if tag in ("asset_treasury", "reit"):
        return "liquidity_only", tag, how
    if tag == "spac_shell":
        return "trust_only", tag, how
    return "full", tag, how


# --- The gate ------------------------------------------------------------------------------


def evaluate(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str | None,
    as_of: str,
    *,
    models: models_mod.ModelFile | None = None,
    today: str | None = None,
    extra_credit: tuple[Credit, ...] = (),
    calendar: bool = True,
) -> Gate:
    """The gate as known on `as_of` (facts filed by then). `calendar=False` skips the
    filing-status test (historical regression cases); `today` (default `as_of`) dates the
    16-month foreign-filer rule."""
    norm = normalize_cik(cik) or cik
    mf = models if models is not None else models_mod.load_safe()
    g = Gate(norm, ticker, as_of)
    today = today or as_of
    cash_any = _points(engine, norm, "cash", as_of, "I", shell=True)
    trust_any = _points(engine, norm, TRUST, as_of, "I", shell=True)
    b_any = max([*cash_any, *trust_any], default=None)
    g.scope, g.tag, how = scope_of(engine, mf, norm, ticker, b_any)
    g.scope_text = f"{g.scope_name} ({how})"
    if mf.error:
        g.notes.append(f"model tag file rejected, no tags applied: {mf.error}")
    if g.scope == "not_applicable":
        g.state = "not_applicable"
        g.notes.append("no gate without a test: read by M01 as not-pass (D-M04-35)")
        g.signal_as_of = as_of
        return g
    shell = g.scope == "trust_only"
    if shell:
        _trust_only(engine, g, as_of, trust_any, cash_any)
    else:
        _liquidity_and_burn(engine, g, as_of, today, extra_credit)
        if g.balance_date and g.liquidity is not None:
            _wall(engine, g, as_of)
    _legal(engine, g, as_of, calendar)
    _combine(g)
    dates = [s.date for s in g.sources]
    g.signal_as_of = max(dates) if dates else as_of
    if g.overdue_due:
        g.signal_as_of = max(g.signal_as_of, g.overdue_due)
    return g


def _trust_only(engine, g: Gate, as_of: str, trust_any, cash_any) -> None:
    t = _latest(trust_any)
    if t is None:
        g.missing.append("trust account not tagged (AssetsHeldInTrust…)")
        g.balance_date = max(cash_any, default=None)
        return
    g.balance_date, g.trust = t.end, float(t.value)
    g.liquidity = g.trust
    g.sources += _src(t, "trust account")
    g.runway_test = (
        "n/a",
        "not tested: trust only (spac_shell), the shell's cash is the "
        "trust held for redemptions (D-M04-8)",
    )


def _liquidity_and_burn(
    engine, g: Gate, as_of: str, today: str, extra: tuple[Credit, ...] = ()
) -> None:
    cik = g.cik
    maps = owner_maps(engine, cik)
    cash_pts = _points(engine, cik, _with_map(ALL_CONCEPTS["cash"], maps.get("cash")), as_of, "I")
    b = balance_anchor(engine, cik, as_of, cash_pts)
    if b is None:
        g.missing.append("cash at the latest balance sheet")
        g.gate_inputs.append(("cash", "no cash tag found"))
        return
    g.balance_date = b
    rc = _at(_points(engine, cik, "restricted_cash", as_of, "I"), b)
    cash = _at(cash_pts, b)
    if cash is not None:
        g.cash = float(cash.value)
    elif (cr := _at(_points(engine, cik, CASH_WITH_RESTRICTED, as_of, "I"), b)) is not None:
        cash = cr
        if rc is not None:
            g.cash = float(cr.value) - float(rc.value)
            g.notes.append(
                f"cash = CashCashEquivalentsRestrictedCash… {money(cr.value)} − restricted "
                f"{money(rc.value)} (fallback: no cash-and-equivalents tag at {b})"
            )
        else:
            g.cash = float(cr.value)
            g.notes.append(
                f"cash = CashCashEquivalentsRestrictedCash… {money(cr.value)} (fallback: no "
                f"cash-and-equivalents tag at {b}; restricted cash, if any, inside)"
            )
    elif (co := _at(_points(engine, cik, CASH_ONLY, as_of, "I"), b)) is not None:
        cash = co
        g.cash = float(co.value)
        g.notes.append(
            f"cash = us-gaap:Cash {money(co.value)} (fallback: no equivalents tag at {b})"
        )
    if cash is None:
        seen = tags_at(engine, cik, b, as_of)
        g.missing.append(f"cash at the latest balance sheet ({b}): no cash tag at that date")
        g.notes.append(
            f"tags with 'Cash' in the name at {b}: " + ("; ".join(seen) if seen else "none")
        )
        g.gate_inputs.append(("cash", f"no cash tag at the balance sheet of {b}"))
        return
    g.sources += _src(cash, "cash")
    sti_con = sti_concept()
    sti = _at(_points(engine, cik, sti_con, as_of, "I"), b)
    if sti is not None:
        g.sti = float(sti.value)
        g.sources += _src(sti, "short-term investments")
        if "alias" in sti.method or "fallback tag" in sti.method:
            g.notes.append(f"ST investments {sti.method.split(';')[0]}")
    elif (cs := _at(_points(engine, cik, CASH_AND_STI, as_of, "I"), b)) is not None:
        if float(cs.value) > g.cash:
            g.sti = float(cs.value) - g.cash
            g.sources += _src(cs, "cash and short-term investments")
            g.notes.append(
                f"ST investments = CashCashEquivalentsAndShortTermInvestments {money(cs.value)} "
                f"− cash {money(g.cash)} (fallback, labelled)"
            )
    if g.sti is None:
        have, none = tags_present(engine, cik, concept_for(cik, sti_con).tags + CASH_AND_STI.tags,
                                  as_of)  # fmt: skip
        g.notes.append(
            f"ST investments none at {b}: tags with facts "
            + ("; ".join(have) if have else "none")
            + (f"; no facts for {', '.join(none)}" if none else "")
        )
    if rc is not None:
        g.restricted = float(rc.value)
        g.notes.append(f"restricted cash {money(rc.value)} excluded")
    ta = _at(_points(engine, cik, "total_assets", as_of, "I"), b)
    g.total_assets = float(ta.value) if ta is not None else None
    tagged = _at(_points(engine, cik, UNDRAWN_TAGGED, as_of, "I"), b)
    if tagged is not None:
        g.tagged_capacity = float(tagged.value)
        g.notes.append(
            f"undrawn credit tagged {money(tagged.value)}: not counted (no maturity; "
            "confirm it with its maturity, D-M04-32)"
        )
    g.liquidity_cash = g.cash + (g.sti or 0.0)
    g.credits = _credits(engine, cik, b, extra)
    g.liquidity = g.liquidity_cash + sum(c.amount for c in g.credits if c.counted)
    for c in g.credits:
        if c.counted and c.line_id is not None:
            g.sources.append(Source(f"credit_line {c.line_id}", c.as_of, c.grade, c.facility))
    if g.total_assets is not None and g.liquidity_cash > g.total_assets * 1.001:
        g.missing.append(
            f"withheld: cash and investments {money(g.liquidity_cash)} exceed "
            f"total assets {money(g.total_assets)} (inconsistent inputs)"
        )

    # Burn bases (D-M04-32)
    ocf_q = _points(
        engine,
        cik,
        _with_map(ALL_CONCEPTS["operating_cash_flow"], maps.get("operating_cash_flow")),
        as_of,
        "Q",
    )
    ocf_ttm = _points(engine, cik, "operating_cash_flow", as_of, "TTM")
    ocf_fy = _points(engine, cik, "operating_cash_flow", as_of, "FY")
    cx_con, g.capex_mark = capex_concept(engine, cik, as_of)
    cx_con = _with_map(cx_con, maps.get("capex"))
    cx_q = _points(engine, cik, cx_con, as_of, "Q")
    cx_ttm = _points(engine, cik, cx_con, as_of, "TTM")
    cx_fy = _points(engine, cik, cx_con, as_of, "FY")
    capex_any = bool(cx_q or cx_fy)
    last_q = _latest(ocf_q, (_d(b) + timedelta(days=NEAR)).isoformat())
    last_fy = _latest(ocf_fy, (_d(b) + timedelta(days=NEAR)).isoformat())
    foreign = is_foreign_filer(engine, cik)
    annual = foreign and last_fy is not None and (last_q is None or last_q.end < last_fy.end)
    if annual:
        fy = last_fy
        age_limit = _add_months(_d(fy.end), FOREIGN_MONTHS)
        g.input_age = f"annual inputs as of {fy.end}"
        if _d(today) > age_limit:
            g.missing.append(
                f"foreign annual filer: inputs older than {FOREIGN_MONTHS} months "
                f"(fiscal year {fy.end}, limit {age_limit}; D-M04-36)"
            )
            return
        cx = _at(cx_fy, fy.end)
        g.bases.append(
            Basis(
                "fiscal year ÷ 4",
                fy.end,
                float(fy.value),
                float(cx.value) if cx is not None else None,
                4.0,
            )
        )
        g.sources += _src(fy, "OCF fiscal year") + _src(cx, "capex fiscal year")
        g.basis_note = "foreign annual filer: fiscal year ÷ 4 (up to 16 months, D-M04-36)"
    else:
        if last_q is None:
            g.missing.append("operating cash flow for the last two quarters")
            g.gate_inputs.append(("operating_cash_flow", "no quarterly OCF found"))
            return
        if not _near(last_q.end, b, 100):
            g.input_age = f"cash flows as of {last_q.end}"
        chain = _quarter_chain(ocf_q, last_q.end)
        if len(chain) < 2:
            g.missing.append(
                f"one quarter of cash flows only ({last_q.end}): no last-two-quarter burn"
            )
            return
        cx2 = [_at(cx_q, p.end) for p in chain]
        capex2 = sum(float(p.value) for p in cx2) if all(cx2) else None
        g.bases.append(
            Basis(
                "last two quarters", chain[-1].end, sum(float(p.value) for p in chain), capex2, 2.0
            )
        )
        for p in chain:
            g.sources += _src(p, "OCF quarter")
        for p in cx2:
            g.sources += _src(p, "capex quarter")
        t = _at(ocf_ttm, last_q.end)
        if t is not None:
            tc = _at(cx_ttm, last_q.end)
            g.bases.append(
                Basis(
                    "TTM ÷ 4",
                    t.end,
                    float(t.value),
                    float(tc.value) if tc is not None else None,
                    4.0,
                )
            )
        else:
            g.basis_note = "short history: fewer than 4 quarters, last two quarters only"
    if any(bs.capex is None for bs in g.bases):
        g.ocf_only = True
        for bs in g.bases:
            bs.capex = None
        why = "capex untagged" if not capex_any else "capex not tagged for these periods"
        if maps.get("capex", {}).get("not_reported"):
            why = "capex not reported (owner)"
        else:
            g.gate_inputs.append(("capex", why))
        g.notes.append(f"{why}: OCF-only runway (labelled)")
    used = [
        p
        for p in (*cx_q.values(), *cx_ttm.values(), *cx_fy.values())
        if g.bases and _near(p.end, g.bases[0].end, 120)
    ]
    broader = next(
        (
            m.split("[", 1)[1].split("]", 1)[0]
            for p in used
            for m in [p.method]
            if "broader tag" in m and "[" in m
        ),
        "",
    )
    g.capex_mark = g.capex_mark or broader
    if g.capex_mark and not g.ocf_only:
        g.notes.append(f"total capex on the [{g.capex_mark}] definition (D-M04-3)")
    _tiers(g)
    g.runway_no_growth = runway_without_growth(engine, g)
    if g.runway_no_growth:
        g.notes.append(f"runway without growth capex: {g.runway_no_growth} (information, D-M04-6)")


def _tiers(g: Gate) -> None:
    if not g.bases:
        return
    ocf_neg = any(bs.ocf < 0 for bs in g.bases)
    fcf_neg = any(bs.fcf < 0 for bs in g.bases)
    g.tier = "cash_burner" if ocf_neg else ("capex_funded" if fcf_neg else "self_funding")
    if g.tag == "issuance_funded":
        g.notes.append("issuance_funded: normal gate (D-M04-13)")
    for bs in g.bases:
        g.runway_by_basis[bs.name] = (g.liquidity / bs.burn) if bs.burn > 0 else None
    worst = max(g.bases, key=lambda bs: bs.burn)
    if worst.burn <= 0:
        g.burn = 0.0
        g.runway_test = (
            "pass",
            "self-funding (FCF ≥ 0 on " + " and ".join(bs.name for bs in g.bases) + ")",
        )
        if g.ocf_only:
            g.runway_test = ("pass", "OCF ≥ 0 (capex untagged)")
        return
    g.burn, g.burn_basis = worst.burn, worst.name
    g.runway = g.liquidity / g.burn
    g.runway_cash = g.liquidity_cash / g.burn
    q = g.runway
    if g.scope == "liquidity_only":
        g.runway_test = ("shown", f"{q:.1f} q shown, not tested (liquidity-only, D-M04-8)")
        return
    if g.tier == "cash_burner":
        if q < FAIL_Q:
            g.runway_test = ("fail", f"cash burner, runway {q:.1f} q < {FAIL_Q:g}")
        elif q < WARN_Q:
            g.runway_test = ("warn", f"cash burner, runway {q:.1f} q < {WARN_Q:g}†")
        else:
            g.runway_test = ("pass", f"cash burner, runway {q:.1f} q ≥ {WARN_Q:g}")
    else:  # capex-funded: never fails (D-M04-38)
        if q < FAIL_Q:
            g.runway_review = True
            g.runway_test = (
                "warn",
                f"capex-funded, runway {q:.1f} q < {FAIL_Q:g}: m04_runway "
                "review (rule-3 adds allowed, rule-7 strength blocked "
                "while open, D-M04-38)",
            )
        elif q < WARN_Q:
            g.runway_test = ("warn", f"capex-funded, runway {q:.1f} q < {WARN_Q:g}†")
        else:
            g.runway_test = ("pass", f"capex-funded, runway {q:.1f} q ≥ {WARN_Q:g}")


def _wall(engine, g: Gate, as_of: str) -> None:
    b = g.balance_date
    d12, text, used = _debt12(engine, g.cik, as_of, b, False)
    for p in used:
        g.sources += _src(p, "12-month debt")
    g.debt24, g.debt24_text, y2 = _debt24(engine, g.cik, as_of, b, d12, False)
    g.sources += _src(y2, "year-2 maturities")
    if g.debt24 is not None:
        g.debt24_text += f" vs liquidity {money(g.liquidity)}"
    if d12 is None:
        g.wall_test = ("n/a", "not tested: no current-debt or maturity tags (optional input)")
        return
    g.debt12, g.debt12_text = d12, text
    burn4 = 4 * (g.burn or 0.0)
    g.wall_ratio = (d12 + burn4) / g.liquidity if g.liquidity else None
    if d12 > g.liquidity:
        g.wall_test = (
            "fail",
            f"12-month debt {money(d12)} > liquidity {money(g.liquidity)} ({text})",
        )
    elif d12 + burn4 > g.liquidity:
        g.wall_test = (
            "warn",
            f"12-month debt {money(d12)} + 4 × burn {money(burn4)} > "
            f"liquidity {money(g.liquidity)}",
        )
    else:
        g.wall_test = (
            "pass",
            f"12-month debt {money(d12)} + 4 × burn {money(burn4)} ≤ "
            f"liquidity {money(g.liquidity)} ({text})",
        )


def _legal(engine, g: Gate, as_of: str, calendar: bool) -> None:
    for r in engine.execute(
        "SELECT * FROM m04_event WHERE cik = ? AND state IN ('fail', 'warn') AND filed <= ? "
        "ORDER BY filed DESC",
        (g.cik, as_of),
    ):
        line = f"8-K {r['item']} {r['class']} filed {r['filed']} ({r['accession']}): {r['state']}"
        if r["item"] in GATE_ITEMS:
            g.events.append(line)
            g.sources.append(Source(r["accession"], r["filed"], "A", f"8-K {r['item']}"))
            (g.triggers if r["state"] == "fail" else g.warnings).append(line)
        elif r["item"] != "4.02":
            g.other_events.append(line + " (not a gate trigger)")
    nr = restate.non_reliance(engine, g.cik, g.balance_date)
    if nr is not None:
        g.non_reliance = nr.mark
        g.warnings.append("inputs under non-reliance (open 4.02, D-M04-21)")
        g.sources.append(Source(nr.accession, nr.filed, "A", "8-K 4.02"))
    if not calendar:
        g.filing_status = "not evaluated (historical as-of)"
        return
    rows = engine.execute(
        "SELECT * FROM filing_status WHERE cik = ? ORDER BY period_end DESC", (g.cik,)
    ).fetchall()
    if not rows:
        g.filing_status = "not evaluated (no periodic reports)"
        return
    over = [r for r in rows if r["status"] == "overdue" and r["filed"] is None]
    if over:
        r = over[0]
        g.overdue, g.overdue_due = True, r["due_date"]
        g.filing_status = f"overdue: {r['form']} period {r['period_end']}, due {r['due_date']}"
        g.missing.append(
            f"overdue filing ({r['form']} period {r['period_end']}, due {r['due_date']}; D-M04-61)"
        )
        g.exit_warning.append("overdue filing (D-M04-61)")
    else:
        stale = [r for r in rows if r["status"] == "stale"]
        g.filing_status = (
            (
                "stale: " + f"{stale[0]['form']} period {stale[0]['period_end']} not "
                f"yet due ({stale[0]['due_date']})"
            )
            if stale
            else "current"
        )


def _combine(g: Gate) -> None:
    sev = 0
    if g.runway_test[0] == "fail":
        g.triggers.append(g.runway_test[1])
    elif g.runway_test[0] == "warn":
        g.warnings.append(g.runway_test[1])
    if g.wall_test[0] == "fail":
        g.triggers.append(g.wall_test[1])
    elif g.wall_test[0] == "warn":
        g.warnings.append(g.wall_test[1])
    if g.warnings:
        sev = SEVERITY["warn"]
    if g.missing:
        sev = SEVERITY["incomplete"]
    if g.triggers:
        sev = SEVERITY["fail"]
        g.exit_warning.append("gate fail (S6.14)")
    g.state = next(k for k, v in SEVERITY.items() if v == sev)


def runway_without_growth(engine: sqlite3.Connection, g: Gate) -> str:
    """Information (D-M04-6): the burn with the latest fiscal year's maintenance share of
    total capex (Part 1b's `capex_split`)."""
    if not g.bases or g.ocf_only or not g.liquidity:
        return ""
    row = engine.execute(
        "SELECT fiscal_label, total, maintenance FROM capex_split WHERE cik = ? AND maintenance "
        "IS NOT NULL AND total > 0 ORDER BY period_end DESC LIMIT 1",
        (g.cik,),
    ).fetchone()
    if row is None:
        return "missing: no capex split stored (Part 1b)"
    share = float(row["maintenance"]) / float(row["total"])
    worst = max(max(0.0, -(b.ocf - (b.capex or 0.0) * share) / b.quarters) for b in g.bases)
    what = f"maintenance {share:.0%} of capex, {row['fiscal_label']}"
    if worst <= 0:
        return f"self-funding ({what})"
    return f"{g.liquidity / worst:.1f} q ({what})"


def raised_share(engine: sqlite3.Connection, g: Gate) -> str:
    """Share of liquidity raised in the trailing four quarters (S4.13, read by Part 5):
    equity issued + net debt raised, from M02's allocation block, its coverage label kept
    (D-M02-31). Today's evaluation only."""
    if not g.liquidity_cash:
        return ""
    from engine.moneyflow.actuals import latest_clause, overrides_by_cik
    from engine.moneyflow.allocation import allocation

    try:
        windows = allocation(
            engine, g.cik, latest_clause(engine, g.cik), overrides_by_cik(engine).get(g.cik)
        )
    except Exception as e:  # the allocation block must not break the gate
        return f"missing: allocation block error ({type(e).__name__})"
    w = next((x for x in windows if x.ptype == "TTM"), None)
    if w is None:
        return "missing: no TTM financing window"
    eq = w.lines.get("equity_issued")
    if (eq is None or eq.value is None) and w.net_debt is None:
        return f"missing: no equity or debt financing lines mapped ({w.label}; {w.coverage_text})"
    raised = (eq.value if eq and eq.value else 0.0) + max(0.0, w.net_debt or 0.0)
    return (
        f"{raised / g.liquidity_cash:.0%} of cash and investments ({money(raised)}: equity "
        f"issued {money(eq.value if eq else None)}, net debt {money(w.net_debt)}; "
        f"{w.label}; {w.coverage_text})"
    )
