"""M01 rule readers from stored M04 rows (rules 1, 3, 4, 7; D27, D-M01-5, D-M01-6).

One place for "how M01 reads M04" (docs/M04_FINANCIALS.md, the table of that name), read
from the D13 `signal` rows M04 writes, so every module reads the same answer: M09's
qualification label (R3, D-M09-4), M11's no-add gate and exit warning, M12's blocked thesis
(MVP_PLAN item 3). Labels only: nothing here blocks or sizes a position (D16).

Rows read (module M04, timeframe MY, the newest row, optionally as of a date):
`survival_gate` (pass, warn, fail, incomplete, not_applicable; Part 4a), `filing_status`
(current, stale, overdue; Part 1a), `cvd_state` (Part 8a; the effective state, an owner
answer applied), `runway_q` (its method says "capex-funded review open … rule-7 strength
blocked" while an `m04_runway` review is open, and "owner: capex can be cut" once
answered), `guidance_removed` (value `removed`, last 12 months; rule 4).

- Rule 1 / R3 "qualified" (D-M01-6): gate pass or warn, no overdue filing, CvD not
  STRUCTURAL_DECLINE or CYCLE_PLUS_DAMAGE. Gate fail, incomplete or not applicable (ETV
  `fund`, D-M04-35) → not qualified; `cvd_state` missing → "qualification incomplete"
  (D-M09-4); tracked names → "not covered by M04" (D-M04-80). MSTR: no special rule (D-M04-8).
- Rule 7 (D27, D-M01-5): strength beyond 2σ only with gate pass or warn, no overdue filing,
  CvD = CYCLICAL_TROUGH and no open capex-funded runway review (D-M04-38).
- Rule 3 (tranches) and rule 4 (exit warnings) per the M04 table.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

from engine.sec.identity import normalize_cik

PASS = ("pass", "warn")
DAMAGE = ("STRUCTURAL_DECLINE", "CYCLE_PLUS_DAMAGE")
NO_CVD = "Part 8a not built"  # the reason while no `cvd_state` row exists


@dataclass(frozen=True)
class Row:
    text: str | None  # value_text
    as_of: str
    method: str

    @property
    def missing(self) -> str | None:
        """The missing reason of a missing row, else None."""
        if self.text is not None:
            return None
        m = self.method or ""
        return m[len("missing: ") :].split(";")[0] if m.startswith("missing: ") else "no value"


@dataclass
class M04Rows:
    cik: str
    covered: bool = True  # core or promoted (tracked names: facts-only rows, D-M04-80)
    gate: Row | None = None
    filing: Row | None = None
    cvd: Row | None = None
    runway: Row | None = None
    guidance_removed: str | None = None  # as_of of a `removed` row in the last 12 months

    @property
    def gate_state(self) -> str | None:
        return self.gate.text if self.gate else None

    @property
    def overdue(self) -> bool:
        return bool(self.filing and self.filing.text == "overdue")

    @property
    def cvd_state(self) -> str | None:
        return self.cvd.text if self.cvd else None

    @property
    def cvd_missing(self) -> str | None:
        if self.cvd is None:
            return NO_CVD
        return self.cvd.missing

    @property
    def runway_blocked(self) -> bool:
        m = self.runway.method if self.runway else ""
        return "capex-funded review open" in m and "owner: capex can be cut" not in m

    @property
    def stumble_answered(self) -> bool:
        return bool(self.cvd and "owner answer STUMBLE" in (self.cvd.method or ""))


@dataclass(frozen=True)
class Reading:
    state: str
    text: str
    reasons: list[str] = field(default_factory=list)


def _latest(engine: sqlite3.Connection, cik: str, signal: str, as_of: str | None) -> Row | None:
    sql = (
        "SELECT value_text, as_of, method FROM signal WHERE cik = ? AND module_id = 'M04' "
        "AND signal = ? AND timeframe = 'MY'"
    )
    params: tuple = (cik, signal)
    if as_of:
        sql += " AND as_of <= ?"
        params += (as_of,)
    r = engine.execute(sql + " ORDER BY as_of DESC LIMIT 1", params).fetchone()
    return Row(r[0], r[1], r[2] or "") if r else None


def read_m04(
    engine: sqlite3.Connection, cik: str, *, covered: bool = True, as_of: str | None = None
) -> M04Rows:
    """The M04 rows M01 reads, newest first (as of a date when given)."""
    norm = normalize_cik(cik) or cik
    out = M04Rows(norm, covered)
    out.gate = _latest(engine, norm, "survival_gate", as_of)
    out.filing = _latest(engine, norm, "filing_status", as_of)
    out.cvd = _latest(engine, norm, "cvd_state", as_of)
    out.runway = _latest(engine, norm, "runway_q", as_of)
    day = date.fromisoformat(as_of) if as_of else date.today()
    rem = engine.execute(
        "SELECT as_of FROM signal WHERE cik = ? AND module_id = 'M04' AND signal = "
        "'guidance_removed' AND timeframe = 'MY' AND value_text = 'removed' AND as_of <= ? "
        "AND as_of >= ? ORDER BY as_of DESC LIMIT 1",
        (norm, day.isoformat(), (day - timedelta(days=365)).isoformat()),
    ).fetchone()
    out.guidance_removed = rem[0] if rem else None
    return out


def m04_line(r: M04Rows) -> str:
    """ "gate warn (2026-08-01), filing current, cvd_state missing: Part 8a not built"."""
    parts = []
    if r.gate is None:
        parts.append("gate missing")
    elif r.gate.text is None:
        parts.append(f"gate missing: {r.gate.missing}")
    else:
        parts.append(f"gate {r.gate.text} ({r.gate.as_of})")
    parts.append(f"filing {r.filing.text or 'missing'}" if r.filing else "filing missing")
    if r.cvd_state:
        parts.append(f"cvd_state {r.cvd_state} ({r.cvd.as_of})")
    else:
        parts.append(f"cvd_state missing: {r.cvd_missing}")
    if r.runway_blocked:
        parts.append("capex-funded runway review open")
    return ", ".join(parts)


def rule1(r: M04Rows) -> Reading:
    """R3 "fundamentally qualified" for a first entry (D-M01-6, D-M09-4)."""
    if not r.covered:
        extra = f"; tracked tier, facts-only gate {r.gate_state}" if r.gate_state else ""
        return Reading("not_covered", f"qualification: not covered by M04 (D-M04-80){extra}")
    g = r.gate_state
    if g is None:
        why = r.gate.missing if r.gate else "no survival_gate row"
        return Reading("incomplete", f"qualification incomplete (survival_gate missing: {why})")
    if g not in PASS:
        return Reading("not_qualified", f"not qualified: gate {g} (D-M01-6, D-M04-35)", [g])
    if r.filing is None or r.filing.text is None:
        return Reading("incomplete", "qualification incomplete (filing_status missing)")
    if r.overdue:
        return Reading("not_qualified", "not qualified: filing overdue (D-M01-6, D-M04-61)",
                       ["overdue"])  # fmt: skip
    cvd = r.cvd_state
    if cvd is None:
        return Reading("incomplete", f"qualification incomplete (cvd_state missing: "
                       f"{r.cvd_missing}; gate {g}, filing {r.filing.text}; D-M09-4)")  # fmt: skip
    if cvd in DAMAGE:
        return Reading("not_qualified", f"not qualified: CvD {cvd} (D-M01-6)", [cvd])
    return Reading("qualified", f"qualified (gate {g}, filing {r.filing.text}, CvD {cvd})")


def rule7(r: M04Rows) -> Reading:
    """Strength beyond 2σ (D27, D-M01-5): `stronger` or `warning`."""
    no = "beyond 2σ: warning, no added strength (D27, D-M01-5)"
    if not r.covered:
        return Reading("warning", f"{no}: not covered by M04 (D-M04-80)")
    g = r.gate_state
    if g not in PASS:
        return Reading("warning", f"{no}: gate {g or 'missing'}")
    if r.overdue:
        return Reading("warning", f"{no}: filing overdue")
    if r.cvd_state is None:
        return Reading("warning", f"{no}: cvd_state missing ({r.cvd_missing})")
    if r.cvd_state != "CYCLICAL_TROUGH":
        return Reading("warning", f"{no}: CvD {r.cvd_state}")
    if r.runway_blocked:
        return Reading("warning", f"{no}: capex-funded runway review open (D-M04-38)")
    return Reading("stronger", f"beyond 2σ: stronger (CYCLICAL_TROUGH, gate {g}; D27, D-M01-5)")


def rule3(r: M04Rows) -> Reading:
    """Later tranches (M01 rule 3; the M04 table): `allowed` or `blocked`."""
    if not r.covered:
        return Reading("blocked", "blocked: not covered by M04 (D-M04-80)")
    g = r.gate_state
    if g == "fail":
        return Reading("blocked", "blocked: survival gate fail (D-M04-31)")
    if g not in PASS:
        return Reading("blocked", f"blocked: gate {g or 'missing'} (D-M04-35)")
    if r.overdue:
        return Reading("blocked", "blocked: filing overdue (D-M04-58, -61)")
    cvd = r.cvd_state
    if cvd is None:
        return Reading("blocked", f"blocked: cvd_state missing ({r.cvd_missing})")
    if cvd in DAMAGE:
        return Reading("blocked", f"blocked: CvD {cvd} (D-M04-58)")
    if cvd == "AMBIGUOUS" or (cvd == "STUMBLE" and not r.stumble_answered):
        return Reading("blocked", f"blocked: CvD {cvd} until the owner answers the m04_cvd item "
                       "(D-M04-56, -58)")  # fmt: skip
    if cvd not in ("CYCLICAL_TROUGH", "NO_SLOWDOWN", "STUMBLE"):
        return Reading("blocked", f"blocked: unknown CvD state {cvd}")
    stale = "; stale filing: later tranches wait (D-M04-61)" if r.filing and \
        r.filing.text == "stale" else ""  # fmt: skip
    return Reading("blocked" if stale else "allowed",
                   f"{'allowed' if not stale else 'first tranche only'}: CvD {cvd}, gate {g}"
                   + stale)  # fmt: skip


def rule4(r: M04Rows) -> list[str]:
    """Exit-warning reasons (warnings only, D16)."""
    out = []
    if r.gate_state == "fail":
        out.append("survival gate fail (S6.14)")
    if r.overdue:
        out.append("filing overdue (D-M04-61)")
    if r.cvd_state in DAMAGE:
        out.append(f"CvD {r.cvd_state} (M01 rule 4, S6.14)")
    if r.guidance_removed:
        out.append(f"guidance_removed {r.guidance_removed} (quietly removed targets, S1.7)")
    return out
