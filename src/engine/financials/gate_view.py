"""Survival-gate panel on the Financials tab, the owner's credit-line entry and the Part 4a
review actions (M04 Part 4a; D-UI-28, D-M04-86).

- `company_view`: the gate tests for one company (computed live as of today, as the tab
  does for capex and trends), the credit lines, the distress / debt / FCF rows, the open
  Part 4a items, the one-line Profile badge, and the all-companies table read from the
  stored `survival_gate` and `runway_q` signals (the last local pass).
- `add_credit_line` / `withdraw_credit_line` (owner only): "Add confirmed credit line" writes
  a `credit_line` row with the owner as confirmer (origin 'owner'); Part 4b's finder will
  propose rows into the same table (D-M04-86). The caller recomputes the gate.
- `apply_action`: the data side of the four Part 4a kinds (`queue.apply` calls it).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime

from engine.financials import debt, distress, gate, gate_step, gate_text
from engine.financials import models as models_mod
from engine.financials.queue import QueueError
from engine.sec.client import iso
from engine.sec.identity import normalize_cik

TAG_RX = re.compile(r"^(us-gaap|ifrs-full|dei|[a-z]{2,10}):[A-Za-z][A-Za-z0-9]*$")
ACCESSION = re.compile(r"\b\d{10}-\d{2}-\d{6}\b")
INPUTS = ("cash", "operating_cash_flow", "capex")


class CreditLineError(ValueError):
    """The credit-line entry breaks a rule (amount, dates, source)."""


@dataclass
class Row:
    test: str
    result: str
    inputs: str
    rule: str
    strong: bool = False


@dataclass
class GateView:
    ticker: str | None
    gate: gate.Gate
    rows: list[Row]
    score: distress.Score | None
    score_rows: list[Row]
    credit: list[sqlite3.Row]
    credit_judged: list[gate.Credit]
    default_as_of: str
    badge: str
    items: list[tuple[int, str]]
    everyone: list[dict] = field(default_factory=list)
    note: str = ""
    text_rows: list = field(default_factory=list)  # Part 4b-lite: the Gate text block
    text_more: int = 0
    text_classes: list = field(default_factory=list)  # the class-rule table


def _items(engine: sqlite3.Connection, cik: str) -> list[tuple[int, str]]:
    return [
        (r["item_id"], r["kind"])
        for r in engine.execute(
            "SELECT item_id, kind FROM review_queue WHERE cik = ? AND kind IN ('m04_gate_fail', "
            "'m04_runway', 'm04_gate_input', 'm04_score_gap', 'm04_credit_line', "
            "'m04_gc_text', 'm04_covenant') "
            "AND resolved_at IS NULL ORDER BY item_id",
            (cik,),
        )
    ]


def badge(g: gate.Gate, items: list[tuple[int, str]]) -> str:
    bits = [f"gate: {g.state}"]
    if g.scope != "full":
        bits.append(g.scope_name)
    if g.tier == "self_funding":
        bits.append("runway: self-funding")
    elif g.runway is not None:
        bits.append(f"runway {g.runway:.1f} q ({g.tier_text})")
    if items:
        bits.append("review open")
    return " · ".join(bits)


def everyone(engine: sqlite3.Connection, companies: dict[str, str]) -> list[dict]:
    """One line per covered company from the stored signals (the last local pass)."""
    out = []
    for ticker, cik in sorted(companies.items()):
        row = {"ticker": ticker}
        for sig in ("survival_gate", "runway_q", "maturity_wall", "distress_score"):
            r = engine.execute(
                "SELECT value, value_text, method, as_of FROM signal WHERE cik = ? AND "
                "module_id = 'M04' AND signal = ? AND timeframe = 'MY' ORDER BY as_of DESC "
                "LIMIT 1",
                (cik, sig),
            ).fetchone()
            row[sig] = r
        g = row["survival_gate"]
        if g is None:
            row["state"], row["trigger"], row["scope"] = "—", "not computed yet", ""
        else:
            m = g["method"] or ""
            row["state"] = g["value_text"] or "missing"
            head = m.split("; scope: ", 1)[0]
            row["trigger"] = "" if head == "no trigger" else head
            row["scope"] = m.split("scope: ", 1)[1].split(" (", 1)[0] if "scope: " in m else ""
            row["as_of"] = g["as_of"]
        r = row["runway_q"]
        row["runway"] = (
            "—"
            if r is None
            else r["value_text"]
            if r["value_text"]
            else f"{float(r['value']):.1f}"
            if r["value"] is not None
            else "missing"
        )
        w = row["maturity_wall"]
        row["wall"] = f"{float(w['value']):.2f}" if w and w["value"] is not None else "—"
        d = row["distress_score"]
        row["distress"] = (
            "—"
            if d is None
            else (
                f"{float(d['value']):.2f} {d['value_text']}"
                if d["value"] is not None
                else d["value_text"] or "missing"
            )
        )
        out.append(row)
    return out


def _rows(g: gate.Gate) -> list[Row]:
    rows = [
        Row(
            "Gate",
            g.state
            + (
                " (counts as pass for M01)"
                if g.state == "warn"
                else " (read by M01 as not-pass)"
                if g.state == "not_applicable"
                else ""
            ),
            (f"balance sheet {g.balance_date}" + (f"; {g.input_age}" if g.input_age else ""))
            if g.balance_date
            else "—",
            f"worst test below; scope: {g.scope_text}",
            strong=True,
        )
    ]
    if g.scope == "not_applicable":
        return rows
    liq = g.liquidity_parts() if g.liquidity is not None else "; ".join(g.missing) or "—"
    if g.scope != "trust_only":
        rb = " · ".join(
            f"{v:.1f} q ({k})" if v is not None else f"no burn ({k})"
            for k, v in g.runway_by_basis.items()
        )
        rows.append(
            Row(
                "Runway",
                (g.runway_text() + (f" — {rb}" if rb else "")) if g.bases else "—",
                liq,
                g.runway_test[1]
                or "cash burner: fail < 6, warn < 8; capex-funded: warn "
                "< 8, m04_runway review < 6, never fails (D-M04-32, -38)",
            )
        )
        nog = _without_growth(g)
        if nog:
            rows.append(
                Row(
                    "Runway without growth capex",
                    nog,
                    "maintenance capex = the Part 1b split (D-M04-6)",
                    "information",
                )
            )
        rows.append(
            Row(
                "Maturity wall, 12 months",
                g.wall_test[0] if g.wall_test[0] != "n/a" else "not tested",
                g.debt12_text or "—",
                g.wall_test[1]
                or "fail if 12-month debt > liquidity; warn if + 4 × burn > liquidity (D-M04-33)",
            )
        )
        rows.append(
            Row(
                "Maturity wall, 24 months",
                g.debt24_text or "—",
                "maturity schedule tags",
                "shown only",
            )
        )
    else:
        rows.append(Row("Trust account", liq, "AssetsHeldInTrust…", g.runway_test[1]))
    if g.raised:
        rows.append(
            Row(
                "Raised in last 4 quarters",
                g.raised,
                "M02 allocation block",
                "information for Part 5 (S4.13)",
            )
        )
    rows.append(
        Row(
            "8-K triggers (Part 3)",
            "; ".join(g.events) or "none open",
            ("other open events: " + "; ".join(g.other_events))
            if g.other_events
            else "3-year event list",
            "1.03 / 2.04 / 3.01 delisting or missed cure fail; cure-period deficiency "
            "warns (D-M04-37)",
        )
    )
    rows.append(
        Row(
            "Going-concern and covenant text (Part 4b)",
            g.text_summary or "—",
            (f"current report {g.text_report}" if g.text_report else "no stored periodic text")
            + (f"; {g.text_note}" if g.text_note else ""),
            "fail class → trigger; warn class → warns + review; hypothetical → review only "
            "below 8 quarters; spac_shell periods excluded (D-M04-34, -96)",
        )
    )
    rows.append(
        Row(
            "Filing status",
            g.filing_status or "—",
            "Part 1a",
            "overdue → incomplete + exit warning (D-M04-61); foreign annual filer > 16 "
            "months → incomplete (D-M04-36)",
        )
    )
    rows.append(
        Row(
            "Non-reliance",
            g.non_reliance or "none",
            "Part 3 lookup",
            'open 4.02 → "inputs under non-reliance", warns (D-M04-21)',
        )
    )
    return rows


def _without_growth(g: gate.Gate) -> str:
    return g.runway_no_growth


def _score_rows(s: distress.Score | None, cg: gate_step.CompanyGate) -> list[Row]:
    out = []
    if s is not None:
        label = f"distress_score {s.variant or ''}".strip()
        reading = (
            (("warning" if s.warning else "no warning") + f" — {s.zone}")
            if s.zone
            else (s.not_meaningful or f"missing: {s.missing}")
        )
        out.append(
            Row(
                label,
                f"{s.value:.2f}" if s.value is not None else "—",
                reading,
                s.method(),
                strong=s.warning,
            )
        )
        if s.o_p is not None:
            out.append(
                Row(
                    "Ohlson O (information)",
                    f"P {s.o_p:.3f}",
                    f"{'above' if s.o_p > distress.O_CUTOFF else 'below'} the "
                    f"{distress.O_CUTOFF} cut-off",
                    "Model 1; OCF as the FUTL proxy",
                )
            )
    f = cg.fcf
    if f is not None:
        out.append(
            Row(
                "fcf_burn",
                f"{f.value:+.1%} of revenue" if f.value is not None else "—",
                (
                    f"{f.to_liquidity:+.2f} of cash and investments; "
                    if f.to_liquidity is not None
                    else ""
                )
                + f.tier,
                f"{f.basis} FCF on total capex"
                + (f"; {f.context}" if f.context else "")
                + (f"; missing: {f.missing}" if f.missing else ""),
            )
        )
    d = cg.debt
    if d is not None and d.latest is not None:
        lp = d.latest
        out.append(
            Row(
                "debt_to_revenue",
                f"{lp.ratio:.2f}" if lp.ratio is not None else "—",
                d.range_text("ratio") + (f"; {d.peer_note}" if d.peer_note else ""),
                lp.debt_text + " ÷ 12-month revenue",
            )
        )
        out.append(
            Row(
                "net_debt_ebitda",
                f"{lp.nd_ebitda:.2f}×" if lp.nd_ebitda is not None else (lp.nd_text or "—"),
                d.range_text("nd_ebitda"),
                "EBITDA = operating income + D&A",
            )
        )
    n = cg.neg
    if n is not None:
        out.append(
            Row(
                "negative_equity",
                n.state,
                "; ".join(n.reasons) or "—",
                f"equity {gate.money(n.equity)}" + (f" at {n.end}" if n.end else ""),
                strong=n.state == "warn",
            )
        )
    return out


def company_view(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str | None,
    today: date,
    companies: dict[str, str] | None = None,
) -> GateView:
    norm = normalize_cik(cik) or cik
    mf = models_mod.load_safe()
    t = today.isoformat()
    g = gate.evaluate(engine, norm, ticker, t, models=mf, today=t)
    cg = gate_step.CompanyGate(ticker or norm, norm, g)
    if g.scope != "not_applicable":
        cg.score = distress.score(engine, norm, ticker, t, models=mf, close_day=t)
        cg.debt = debt.debt_rows(engine, norm, t, g.balance_date)
        cg.fcf = debt.fcf_burn(engine, g, t)
        cg.neg = debt.negative_equity(engine, norm, t)
        g.raised = gate.raised_share(engine, g)
    items = _items(engine, norm)
    review_hypo, _ = gate_text.runway_reviews(g.runway, g.tier, g.scope)
    text_rows, more, _cur = gate_text.view_rows(engine, norm, t, review_hypo)
    return GateView(
        ticker,
        g,
        _rows(g),
        cg.score,
        _score_rows(cg.score, cg),
        gate.credit_lines(engine, norm),
        list(g.credits),
        g.balance_date or t,
        badge(g, items),
        items,
        everyone(engine, companies) if companies else [],
        text_rows=text_rows,
        text_more=more,
        text_classes=CLASS_RULES,
    )


# The class-rule table under the Gate text block (D-M04-34; owner's mock-up 2026-10-13)
CLASS_RULES = (
    (
        "Auditor going-concern paragraph; management “substantial doubt exists”; unwaived "
        "covenant breach; forbearance; covenant-driven debt reclassification; acceleration; "
        "delisting",
        "fail + alert (m04_gate_fail)",
        "Fisker FY2023; Invitae Q3 2023; Proterra FY2022",
    ),
    (
        "Doubt alleviated; audit-matter only; IFRS “material uncertainty”; waived or reset "
        "covenant; listing deficiency",
        "warn + m04_gc_text / m04_covenant review",
        "Microvast “alleviate”; UTI waiver; Albemarle relief period",
    ),
    (
        "Hypothetical (“could raise substantial doubt”)",
        "review only when runway < 8 q; else information",
        "Riot FY2025",
    ),
    (
        "“in compliance with … covenants”; ASC 205-40 evaluation; going-concern basis; negated",
        "no trigger",
        "Boeing FY2023; Invitae Q2 2023",
    ),
    (
        "spac_shell periods (keyed on period end; untagged: the 8-K 2.01 close)",
        "excluded",
        "INFQ FY2025 10-K “alleviated” (shell year)",
    ),
)


# --- Owner credit-line entry (D-M04-86) -----------------------------------------------------


def _date(s: str, what: str) -> str:
    try:
        return date.fromisoformat(s.strip()).isoformat()
    except ValueError as e:
        raise CreditLineError(f"{what} must be a date (YYYY-MM-DD)") from e


def add_credit_line(
    engine: sqlite3.Connection,
    cik: str,
    facility: str,
    amount_m: str,
    maturity: str,
    as_of: str,
    source: str,
    by: str,
    now: datetime,
    note: str = "",
) -> int:
    """Owner entry: undrawn available amount in $M. Grade A when the source names a filing
    (sec.gov archive URL or an accession), else B (D-M04-9). Caller owns no transaction."""
    norm = normalize_cik(cik) or cik
    facility = facility.strip()
    source = source.strip()
    if not facility:
        raise CreditLineError('Name the facility (e.g. "five-year revolver").')
    if not source:
        raise CreditLineError("Give the source: the sentence or the filing URL.")
    try:
        amount = float(amount_m.replace(",", "").strip()) * 1e6
    except ValueError as e:
        raise CreditLineError("Amount must be a number in $M (undrawn available).") from e
    if amount <= 0:
        raise CreditLineError("Amount must be above 0.")
    mat, at = _date(maturity, "Maturity"), _date(as_of, "As of")
    if mat <= at:
        raise CreditLineError("Maturity must be after the as-of date.")
    url = source if source.startswith(("http://", "https://")) else None
    acc = ACCESSION.search(source)
    grade = "A" if (url and "sec.gov/Archives" in url) or acc else "B"
    ts = iso(now)
    engine.execute("BEGIN")
    try:
        lid = engine.execute(
            "INSERT INTO credit_line (cik, facility, amount, maturity, as_of, source_text, "
            "source_url, accession, origin, status, grade, proposed_at, confirmed_by, "
            "confirmed_at, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'owner', 'confirmed', "
            "?, ?, ?, ?, ?)",
            (
                norm,
                facility,
                amount,
                mat,
                at,
                source,
                url,
                acc.group(0) if acc else None,
                grade,
                ts,
                by,
                ts,
                note.strip() or None,
            ),
        ).lastrowid
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return lid


def withdraw_credit_line(
    engine: sqlite3.Connection, cik: str, line_id: int, by: str, now: datetime
) -> bool:
    engine.execute("BEGIN")
    try:
        cur = engine.execute(
            "UPDATE credit_line SET status = 'withdrawn', closed_by = ?, closed_at = ? "
            "WHERE line_id = ? AND cik = ? AND status IN ('confirmed', 'proposed')",
            (by, iso(now), line_id, normalize_cik(cik) or cik),
        )
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return bool(cur.rowcount)


# --- Review actions (Part 4a kinds) ---------------------------------------------------------


def _set_state(engine: sqlite3.Connection, name: str, detail: dict, now: datetime) -> None:
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
        "detail = excluded.detail",
        (name, "owner", iso(now), json.dumps(detail, sort_keys=True)),
    )


def apply_action(
    engine: sqlite3.Connection,
    kind: str,
    action: str,
    payload: dict,
    cik: str | None,
    by: str,
    now: datetime,
    *,
    target: str = "",
    note: str = "",
) -> str:
    """Inside `review.m04_action`'s transaction. Returns the resolution text."""
    if not cik:
        raise QueueError("This item names no company.")
    if kind == "m04_gate_fail":
        if action == "inputs_wrong":
            if not note.strip():
                raise QueueError("Say what is wrong with the inputs (note).")
            return (
                f"inputs_wrong: {note.strip()} (gate state unchanged; fix the input or map a tag)"
            )
        return "noted (gate state unchanged)"
    if kind == "m04_score_gap":
        if action == "look_closer":
            return "look_closer: " + (note.strip() or "the owner reads the balance sheet")
        return "noted (score is a warning only, D-M04-31)"
    if kind == "m04_runway":
        st = gate_step._state(engine, cik) or {}
        st["runway_answer"] = {
            "answer": action,
            "since": st.get("runway"),
            "by": by,
            "at": iso(now),
        }
        gate_step._save_state(engine, cik, st, now)
        if action == "allow_strength":
            return (
                "allow_strength: capex can be cut; rule-7 strength allowed while the runway "
                "stays below 6 quarters in this band (D-M04-38)"
            )
        return "keep_blocked: rule-7 strength stays blocked until the runway is ≥ 6 quarters"
    if kind == "m04_gate_input":
        inp = payload.get("input")
        if inp not in INPUTS:
            raise QueueError(f"Unknown gate input {inp!r}.")
        name = f"m04_gate_map:{cik}:{inp}"
        if action == "map_tag":
            tag = target.strip()
            if not TAG_RX.match(tag):
                raise QueueError(
                    "Give the tag as taxonomy:Tag (e.g. us-gaap:PaymentsToAcquireProductiveAssets)."
                )
            tax, name_ = tag.split(":", 1)
            if (
                engine.execute(
                    "SELECT 1 FROM fact WHERE cik = ? AND taxonomy = ? AND tag = ? LIMIT 1",
                    (cik, tax, name_),
                ).fetchone()
                is None
            ):
                raise QueueError(f"No stored fact for {tag} for this company.")
            _set_state(engine, name, {"tag": tag, "by": by, "at": iso(now)}, now)
            return f"map_tag: {inp} ← {tag} (the gate reads it from the next recompute)"
        _set_state(engine, name, {"not_reported": True, "by": by, "at": iso(now)}, now)
        return f"not_reported: {inp} not reported by the company (runway stays labelled)"
    raise QueueError(f"'{action}' is not an action for {kind}.")
