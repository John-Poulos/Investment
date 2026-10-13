"""Financials tab, Part 3 sections (owner's mock-up, 2026-10-12): Filing events (3 years),
Restatement walk, Credit ratings, and the label-file note. Plain data for
`tabs/_m04_flags.html`; computed from the stored rows (the refresh's local pass and
`scripts/run_financials.py flags` write them)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from engine.financials import events, labels, ratings, restate
from engine.sec.identity import normalize_cik
from engine.signals import latest_signal

SHOW_STEPS = 40

EVENTS_NOTE = (
    "Classes (D-M04-37, -15; S1.11): 1.03 bankruptcy fails and never clears by itself; 2.04 "
    "acceleration fails until a later clean periodic filing and your resolution; 3.01 fails on "
    "delisting or a missed cure, warns + review on a cure-period deficiency, is information on "
    "a listing transfer; 4.01 auditor change is information, information within ~90 days after "
    "a de-SPAC closing with no disagreements, and escalates (warn + review) within 12 months of "
    "a restatement; 4.02 non-reliance warns until the restated filing and marks rows reading "
    'the affected periods "inputs under non-reliance" (adds not blocked, D-M04-21); 2.06 '
    "impairment is information with a review; 1.02 co-filed with 2.03 is financing, not a "
    "customer loss (read in Part 7b); NT 10-K/10-Q warns until the late report. Every event is "
    "an uncapped alert line here and in the end-of-run box (D-M04-77); only the review item "
    "counts against the weekly cap of 5 (D-M04-71). The survival gate reads fail and warn "
    "events in Part 4a."
)
WALK_NOTE = (
    "Each step = a change between consecutive filed versions of a value on periodic forms "
    "(revenue, net income, operating cash flow and its continuing-operations variant, pretax "
    "income; fiscal years and reported quarters; 8-Ks and proxies never count). Labels in "
    "order (D-M04-16): standard adoption, discontinued operations, segment recast, split, tag "
    "switch, rounding, NCI share, restricted cash, de-SPAC / predecessor; amounts come from the "
    "changing filing's text (at most two quoted amounts, kept only when they explain all but "
    "5%† of the step). Left over above both 0.5%† of the old value and $0.1M† → review "
    "(`m04_restate`, group 4). A cash-flow step up is `cf_shift_up` (watch). Sources "
    "(D-M04-15): 8-K 4.02, the dei error-correction flag on annual covers filed from "
    "2023-12-01 (earlier: not required, never false), little-r wording in stored 10-K/10-Q "
    "text, and old filings fetched once to label pre-corpus steps (≤ 35). The first walk of a "
    "company is a baseline: shown, queued only when filed in the last 12 months (D-M04-71). "
    "Expected at the first run: about 101 steps on the watchlist (Round 2 counted 102), ≤ 4 "
    "queued."
)
RATINGS_NOTE = (
    "Sentences in stored 8-Ks and earnings releases stating a rating action (downgraded, "
    "lowered, outlook negative, watch, upgraded, affirmed); no agency name needed; "
    "hypothetical wording skipped (S3.7, DS17: text only, no agency feed). Downgrades, "
    "negative outlooks and watches open an `m04_rating` review (group 3); information row, no "
    "weight."
)


@dataclass
class EventLine:
    filed: str
    item: str
    klass: str
    state: str
    clears_when: str
    note: str
    quote: str
    accession: str
    cleared: str


@dataclass
class StepLine:
    filed: str
    concept: str
    period: str
    change: str  # "from → to (Δ)"
    first_latest: str
    labels: str
    labels_title: str
    left: str
    outcome: str
    baseline: bool
    accession: str
    owner: str


@dataclass
class FlagsView:
    events: list[EventLine]
    events_note: str
    steps: list[StepLine]
    steps_hidden: int
    walk_counts: str
    sources: list[str]
    walk_note: str
    ratings: list[sqlite3.Row]
    ratings_note: str
    labels_note: str
    signals: list[tuple[str, str, str]] = field(default_factory=list)


def _m(v) -> str:
    return restate.money(float(v)) if v is not None else "—"


def _plain(v) -> str:
    x = float(v)
    s = f"{x / 1e6:,.1f}M" if abs(x) >= 1e6 else f"{x / 1e3:,.0f}K"
    return s.replace("-", "−")


def flags_view(
    engine: sqlite3.Connection, corpus: sqlite3.Connection | None, cik: str, today: date
) -> FlagsView:
    norm = normalize_cik(cik) or cik
    since = restate.window_start(today)
    evs = [
        EventLine(
            r["filed"],
            r["item"] if r["item"].startswith("NT") else f"8-K {r['item']}",
            r["class"].replace("_", " "),
            r["state"],
            r["clears_when"],
            r["note"],
            r["quote"] or "",
            r["accession"],
            f"{r['cleared_at'][:10]} ({r['cleared_by']})" if r["cleared_at"] else "",
        )
        for r in events.stored_events(engine, norm, since)
    ]
    rows = restate.stored_steps(engine, norm)
    shown = [r for r in rows if r["outcome"] != "explained" or r["to_filed"] >= since]
    hidden = len(rows) - len(shown[:SHOW_STEPS])
    steps = []
    for r in shown[:SHOW_STEPS]:
        labs = json.loads(r["labels"])
        text = (
            "; ".join(
                lb["name"] + (f" {_m(lb['amount'])}" if lb["amount"] is not None else "")
                for lb in labs
            )
            or "none"
        )
        title = " | ".join(
            f"{lb['name']}: “{lb['quote'][:300]}” ({lb['doc']})" for lb in labs if lb.get("quote")
        )
        pct = f" ({float(r['residual_pct']) * 100:.2f}%)" if r["residual_pct"] is not None else ""
        steps.append(
            StepLine(
                r["to_filed"],
                r["concept"].replace("_", " "),
                f"{r['period_type']} {r['period_start']}..{r['period_end']}",
                f"{_plain(r['from_value'])} → {_plain(r['to_value'])} ({_m(r['delta'])})",
                f"{_plain(r['first_value'])} → {_plain(r['latest_value'])}",
                text,
                title + (f" | {r['text_state']}" if r["text_state"] else ""),
                _m(r["residual"]) + pct,
                r["outcome"],
                bool(r["baseline"]) and not r["item_id"],
                r["to_accession"],
                r["owner_outcome"] or "",
            )
        )
    n_rev = sum(1 for r in rows if r["outcome"] == "review")
    n_watch = sum(1 for r in rows if r["outcome"] == "watch")
    filings_n = len({r["to_accession"] for r in rows})
    n_base = sum(1 for r in rows if r["outcome"] == "review" and r["baseline"] and not r["item_id"])
    counts = (
        f"{len(rows)} steps from {filings_n} changing filings: {len(rows) - n_rev - n_watch}"
        f" explained, {n_watch} watch, {n_rev} over tolerance ({n_base} baseline, not queued)"
    )
    if hidden > 0:
        counts += (
            f"; {hidden} step(s) not listed (explained steps filed before {since}, "
            f"and any beyond the first {SHOW_STEPS})"
        )
    sources = []
    flags = restate.dei_flags(engine, norm, "2023-01-01")
    if flags:
        sources.append(
            "dei error-correction flag: "
            + " · ".join(f"{f.form} {f.filed} {f.state}" for f in flags[:8])
        )
    else:
        sources.append("dei error-correction flag: no annual report filed since 2023")
    hits = restate.little_r_text(engine, corpus, norm, since)
    sources.append(
        f"little-r wording in stored 10-K/10-Q text since {since}: "
        + ("; ".join(f"{h.form} {h.filed} “{h.quote[:200]}”" for h in hits[:3]) or "none")
    )
    nr = restate.non_reliance(engine, norm)
    sources.append(nr.mark if nr else "non-reliance: no open 8-K 4.02")
    sig = []
    for name in ("restatement", "non_reliance", "restate_delta"):
        s = latest_signal(engine, norm, "M04", name)
        if s is None:
            sig.append(
                (
                    name,
                    "not computed yet",
                    "the refresh's local pass or `run_financials.py flags` writes it",
                )
            )
        else:
            val = s["value_text"] or ("" if s["value"] is None else f"{s['value']}")
            if s["value"] is not None and s["value_text"]:
                val = f"{s['value_text']} ({float(s['value']):.2f}%)"
            sig.append((name, val or s["method"].split(";")[0], s["method"]))
    lf = labels.read()
    return FlagsView(
        evs,
        EVENTS_NOTE,
        steps,
        max(hidden, 0),
        counts,
        sources,
        WALK_NOTE,
        ratings.stored(engine, norm),
        RATINGS_NOTE,
        "config/m04_labels.toml holds the 24 CvD episodes and 4 controls and the "
        "red-flag rows by family, labels blank; you fill it during Parts 3–7, "
        "blind; the app never edits it (D-M04-51, -73). " + lf.line(),
        sig,
    )
