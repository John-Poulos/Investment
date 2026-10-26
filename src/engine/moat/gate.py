"""M06 gate: `moat_gate` for a first MY entry (rule 4; R1, A3; D-M06-5, -6; D-M01-9).

- met = verdict NARROW or WIDE **and** the catch-up band's low end ≥ the MY horizon
  (`config/moat.toml`, 5 years global, D-M06-6): NARROW 3–5 years is not met (A3);
- UNRATED → `unrated` (not met); NONE → `not_met`, shown; N_A (model tag or SIC) →
  `not_applicable`, never "fail";
- no owner verdict yet → missing ("no owner verdict yet"), so a first MY entry stays blocked
  until one is entered;
- an owner override (met / not_met) wins, logged with its reason and shown as "override"
  (D12); the computed state stays in the method;
- a verdict older than the newest 10-K reads "stale since <date>" (D-M06-8); it still
  applies.

The survival gate is not repeated here (M01 rule 1 already requires it, D-M01-6). Grade =
the verdict's grade. PT and ST are information (any band above 3 years exceeds them).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from engine.moat import verdict as verdict_mod
from engine.sec.identity import normalize_cik

STATES = ("met", "not_met", "unrated", "not_applicable")


@dataclass(frozen=True)
class Gate:
    state: str | None  # one of STATES; None = missing
    why: str
    computed: str | None = None  # the state before an override
    override: bool = False
    stale: str = ""  # "stale since <date>" or ""


def stale_text(v: sqlite3.Row | None, newest_filed: str | None) -> str:
    if v is None or not newest_filed:
        return ""
    return f"stale since {newest_filed}" if v["as_of"] < newest_filed[:10] else ""


def compute(
    v: sqlite3.Row | None, quant_state: str | None, horizon: int, newest_filed: str | None = None
) -> Gate:
    if quant_state == "not_applicable":
        return Gate("not_applicable", "N_A by model tag or SIC: not applicable, never a fail "
                    "(rule 4)")  # fmt: skip
    if v is None:
        return Gate(None, "no owner verdict yet")
    stale = stale_text(v, newest_filed)
    verdict, band = v["verdict"], v["band"]
    low = verdict_mod.band_low(band)
    if verdict in ("NARROW", "WIDE"):
        if low is not None and low >= horizon:
            state = "met"
            why = (f"{verdict}, catch-up band {verdict_mod.band_text(band)}: low end {low} ≥ "
                   f"the {horizon}-year MY horizon (A3)")  # fmt: skip
        else:
            state = "not_met"
            why = (
                f"{verdict}, catch-up band {verdict_mod.band_text(band)}: low end "
                f"{low if low is not None else '—'} < the {horizon}-year MY horizon (A3)"
            )
    elif verdict == "UNRATED":
        state, why = "unrated", "UNRATED: not met until a verdict is entered (D-M06-5)"
    else:
        state, why = "not_met", f"NONE (catch-up band {verdict_mod.band_text(band)}): no moat (R1)"
    if v["override"]:
        why = (f"override {v['override']} by the owner: {v['override_reason']} (computed: "
               f"{state} — {why}; D-M06-5, D12)")  # fmt: skip
        return Gate(v["override"], why, state, True, stale)
    return Gate(state, why, state, False, stale)


def latest_gate(engine: sqlite3.Connection, cik: str) -> sqlite3.Row | None:
    """The stored MY `moat_gate` row (for M01 rule 1 / M11's size cap, D-M01-9)."""
    return engine.execute(
        "SELECT * FROM signal WHERE cik = ? AND module_id = 'M06' AND signal = 'moat_gate' "
        "AND timeframe = 'MY' ORDER BY as_of DESC LIMIT 1",
        (normalize_cik(cik) or cik,),
    ).fetchone()
