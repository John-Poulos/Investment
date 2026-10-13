"""Restatements: the walk, the dei flag, little-r text and non-reliance (M04 Part 3).

Sources (D-M04-15): 8-K Item 4.02 events; the dei `DocumentFinStmtErrorCorrectionFlag` on
annual covers filed from 2023-12-01 (R1 pages, `sec/cover.py`; a missing flag earlier means
"not required", never false); little-r wording in stored 10-K/10-Q text; and the walk below.

**Walk (D-M04-16).** For each walked concept (revenue, net income, operating cash flow and
its continuing-operations variant, pretax income), each fiscal year and each reported
quarter, the values filed on periodic forms are put in filing order (one value per filing:
the concept's highest-priority tag; point-in-time rules as `sec/asof.py`: 8-Ks and proxies
never count, predecessor CIKs to their boundary, `spac_shell` periods out). Every change
between consecutive versions is a **step**. Labels are applied in this order:

1. standards (ASU/ASC/Topic adoption, change in accounting principle, LIFO → FIFO), from
   the changing filing's text;
2. discontinued operations — a revenue, cash-flow or pretax step with net income for the
   same period unchanged in the same two filings and the phrase in the text is a whole
   reclassification (GE FY2017 revenue −18,964; Rite Aid FY2017);
3. segments (recast wording);
4. splits — not reached: only dollar concepts are walked;
5. tag switch (the two versions sit under different tags; no amount);
6. rounding (both values whole millions, or thousands, and the change is one unit);
7. NCI share (net income: what is left equals the change in the non-controlling share);
8. restricted cash (cash-flow concepts, text);
9. de-SPAC / entity boundary (the old version predates a predecessor or shell boundary
   and the new one follows it): whole step.

Text amounts: numbers in passages of the changing filing that carry a label phrase, the
family taken from the nearest phrase; at most two amounts (either sign) are fitted to the
step; a fit is kept only when it leaves at most 5%† of the step (else the labels stay as
"mentioned" and explain nothing). Numbers equal to either version are never used (they
come from the recast table itself). Also recorded: `error` (little r wording beside
"previously issued/reported": a cause, explains nothing) and `cf_shift_up` (a cash-flow
step up: watch; down: note).

**Tolerance (D-M04-16):** a residual above both 0.5%† of the old value and $0.1M† opens an
`m04_restate` review (group 4); the first walk of a company is a baseline (D-M04-71).
**Non-reliance (D-M04-21):** an open 4.02 marks every M04 row reading periods that end on or
before its filing date "inputs under non-reliance" and warns; adds are not blocked.
"""

from __future__ import annotations

import itertools
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from engine.financials import queue
from engine.financials.text import (
    Doc,
    clean,
    doc_scale,
    docs_for,
    numbers,
    passages_for,
    quote_at,
    sentence_at,
    sentences,
)
from engine.search.query import search
from engine.sec.asof import (
    FOREIGN_INTERIM_FORMS,
    PERIODIC_FORMS,
    _document_period_ends,
    is_foreign_filer,
)
from engine.sec.client import iso
from engine.sec.identity import entity_links, normalize_cik
from engine.sec.xbrl_facts import ALL_CONCEPTS, Concept, _gaap, classify, concept_for, concept_rows

MODULE = "M04"
TOL_PCT = 0.005  # D-M04-16 starting values
TOL_USD = 100_000.0
FIT_LEFT = 0.05  # a text fit may leave at most 5%† of the step
DEI_FROM = "2023-12-01"  # the dei error-correction flag is required on 10-Ks filed from here
WINDOW_YEARS = 3

C, F = "currency", "flow"
WALK_ONLY = {
    "operating_cash_flow_cont": Concept(
        "operating_cash_flow_cont",
        _gaap("NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
        C,
        F,
    ),
    "nci_income": Concept(
        "nci_income", _gaap("NetIncomeLossAttributableToNoncontrollingInterest"), C, F
    ),
}
WALK_CONCEPTS = (
    "revenue",
    "net_income",
    "operating_cash_flow",
    "operating_cash_flow_cont",
    "pretax_income",
)
ROUND2_CONCEPTS = ("revenue", "net_income", "operating_cash_flow")  # Round 2's 102 count
CASH_CONCEPTS = ("operating_cash_flow", "operating_cash_flow_cont")
RECLASS_CONCEPTS = ("revenue", "operating_cash_flow", "operating_cash_flow_cont", "pretax_income")

ORDER = (
    "standards",
    "discontinued",
    "segments",
    "split",
    "tag_switch",
    "rounding",
    "nci_share",
    "restricted_cash",
    "entity_boundary",
)
LABEL_NAMES = {
    "standards": "standard adoption",
    "discontinued": "discontinued operations",
    "segments": "segment recast",
    "split": "split",
    "tag_switch": "tag switch",
    "rounding": "rounding",
    "nci_share": "NCI share",
    "restricted_cash": "restricted cash",
    "entity_boundary": "de-SPAC / predecessor",
    "error": "error (little r)",
    "cf_shift_up": "cf_shift_up (watch)",
    "cf_shift_down": "cash-flow shift down (note)",
}

FAMILY = {
    "standards": re.compile(
        r"\bASU\s?(?:No\.\s?)?\d{4}-\d{2}\b|\bASC\s(?:606|842|326|715|740)\b|\bTopic\s"
        r"(?:606|842|326)\b|adoption of (?:the )?new (?:accounting )?(?:standard|guidance)|"
        r"retrospective(?:ly)? (?:adopt|appl|basis)|change in accounting principle|"
        r"LIFO\)? to (?:the )?(?:FIFO|first-in)",
        re.I,
    ),
    "discontinued": re.compile(r"discontinued operations?", re.I),
    "segments": re.compile(
        r"(?:recast|reclassif\w*|revised)[^.]{0,80}\bsegments?\b|\bsegments?\b[^.]{0,80}"
        r"(?:recast|reclassif\w*)",
        re.I,
    ),
    "restricted_cash": re.compile(r"restricted cash", re.I),
}
# A quoted amount counts for a step only when its sentence names the step's line item.
CONCEPT_WORDS = {
    "revenue": re.compile(r"revenues?|sales", re.I),
    "net_income": re.compile(r"net (?:earnings|income|loss)|earnings attributable", re.I),
    "operating_cash_flow": re.compile(
        r"operating activities|cash from operat|operating cash", re.I
    ),
    "operating_cash_flow_cont": re.compile(
        r"operating activities|cash from operat|operating cash", re.I
    ),
    "pretax_income": re.compile(r"pre-?tax|before income taxes", re.I),
}
ERROR_WORD = re.compile(
    r"\berrors?\b|misstatements?|out-of-period|\brevision\b|\brevised\b|"
    r"immaterial correction",
    re.I,
)
PRIOR_WORD = re.compile(r"previously (?:issued|reported)|prior[- ]periods?", re.I)
HYPOTHETICAL = re.compile(r"\b(?:if|may|could|would|might|should)\b", re.I)


# --- Facts ----------------------------------------------------------------------------------


def walk_concept(name: str) -> Concept:
    return WALK_ONLY.get(name) or ALL_CONCEPTS[name]


def _rows(engine: sqlite3.Connection, cik: str, con: Concept) -> list[dict]:
    """Periodic-form USD facts of the concept, point-in-time rules as `facts_as_of`."""
    links = entity_links(engine, cik)
    preds = {lk.predecessor_cik: lk for lk in links if lk.kind == "predecessor"}
    shells = [lk for lk in links if lk.kind == "spac_shell"]
    allowed = set(PERIODIC_FORMS)
    if is_foreign_filer(engine, cik):
        allowed |= FOREIGN_INTERIM_FORMS
    doc_end = _document_period_ends(engine, cik) if shells else {}
    out = []
    for r in concept_rows(engine, [cik, *preds], concept_for(cik, con)):
        if r["form"] not in allowed or r["unit"] != "USD" or r["period_start"] is None:
            continue
        if r["cik"] != cik and r["filed"] > preds[r["cik"]].boundary_date:
            continue
        if shells and r["cik"] == cik:
            end = doc_end.get(r["accession"], r["period_end"])
            if any(end < lk.boundary_date for lk in shells):
                continue
        out.append(dict(r))
    return out


@dataclass(frozen=True)
class Version:
    value: float
    tag: str
    accession: str
    form: str
    filed: str


def chains(
    engine: sqlite3.Connection, cik: str, con: Concept
) -> dict[tuple[str, str, str], list[Version]]:
    """(start, end, FY|Q) → versions in filing order, one per filing (top-priority tag)."""
    rank = {t: i for i, t in enumerate(concept_for(cik, con).tags)}
    groups: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for r in _rows(engine, cik, con):
        key = (r["period_start"], r["period_end"])
        cur = groups[key].get(r["accession"])
        if cur is None or rank[(r["taxonomy"], r["tag"])] < rank[(cur["taxonomy"], cur["tag"])]:
            groups[key][r["accession"]] = r
    out = {}
    for (start, end), by_acc in groups.items():
        ptype = classify(start, end)
        if ptype not in ("FY", "Q"):
            continue
        vs = sorted(by_acc.values(), key=lambda r: (r["filed"], r["accession"]))
        out[(start, end, ptype)] = [
            Version(
                float(r["value"]),
                f"{r['taxonomy']}:{r['tag']}",
                r["accession"],
                r["form"] or "",
                r["filed"],
            )
            for r in vs
        ]
    return out


def value_at(chain: list[Version] | None, accession: str) -> float | None:
    if not chain:
        return None
    return next((v.value for v in chain if v.accession == accession), None)


# --- Text labels -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    value: float
    family: str
    passage_id: int | None
    doc: str  # accession/filename
    quote: str


@dataclass
class TextScan:
    """What the changing filing's stored text says (read once per accession)."""

    stored: bool
    families: dict[str, tuple[int | None, str, str]] = field(default_factory=dict)  # first hit
    candidates: list[Candidate] = field(default_factory=list)
    error: tuple[int | None, str, str] | None = None  # (passage, doc ref, quote)


def is_error_sentence(s: str) -> bool:
    return bool(ERROR_WORD.search(s) and PRIOR_WORD.search(s) and not HYPOTHETICAL.search(s))


def scan_docs(docs: list[Doc], corpus: sqlite3.Connection) -> TextScan:
    scan = TextScan(stored=bool(docs))
    for d in docs:
        scale = doc_scale(d.text)
        spans = passages_for(corpus, d.doc_id) or [(None, 0, len(d.text))]
        for pid, s, e in spans:
            body = d.text[s:e]
            hits = [(fam, m.start() + s) for fam, rx in FAMILY.items() for m in rx.finditer(body)]
            for m in ERROR_WORD.finditer(body):
                if scan.error is None:
                    a, b = sentence_at(d.text, m.start() + s)
                    if is_error_sentence(d.text[a:b]):
                        scan.error = (pid, d.ref, quote_at(d.text, m.start() + s))
            if not hits:
                continue
            for fam, at in hits:
                if fam not in scan.families:
                    scan.families[fam] = (pid, d.ref, quote_at(d.text, at))
            for n in numbers(d.text, s, e, scale):
                fam, at = min(hits, key=lambda h: abs(h[1] - n.start))
                a, b = sentence_at(d.text, n.start)
                scan.candidates.append(Candidate(n.value, fam, pid, d.ref, clean(d.text[a:b])))
    return scan


# --- Steps -------------------------------------------------------------------------------------


@dataclass
class Label:
    family: str
    amount: float | None = None
    passage_id: int | None = None
    doc: str = ""
    quote: str = ""

    def as_dict(self) -> dict:
        return {
            "family": self.family,
            "name": LABEL_NAMES.get(self.family, self.family),
            "amount": self.amount,
            "passage_id": self.passage_id,
            "doc": self.doc,
            "quote": self.quote,
        }


@dataclass
class Step:
    cik: str
    concept: str
    start: str
    end: str
    ptype: str
    old: Version
    new: Version
    first_value: float
    latest_value: float
    labels: list[Label] = field(default_factory=list)
    residual: float = 0.0
    outcome: str = "explained"
    text_state: str = "not needed"

    @property
    def delta(self) -> float:
        return self.new.value - self.old.value

    @property
    def residual_pct(self) -> float | None:
        return abs(self.residual) / abs(self.old.value) if self.old.value else None

    @property
    def key(self) -> str:
        return f"{self.cik}:{self.concept}:{self.start}:{self.end}:{self.new.accession}"

    @property
    def period(self) -> str:
        return f"{self.ptype} {self.start}..{self.end}"

    def has(self, family: str) -> bool:
        return any(lb.family == family for lb in self.labels)


def over_tolerance(residual: float, base: float) -> bool:
    if abs(residual) <= TOL_USD:
        return False
    return base == 0 or abs(residual) > TOL_PCT * abs(base)


def _rounding(a: float, b: float) -> bool:
    for unit in (1e6, 1e3):
        if a % unit == 0 and b % unit == 0 and abs(a - b) <= unit:
            return True
    return False


def _boundary(engine: sqlite3.Connection, cik: str, old: Version, new: Version) -> str | None:
    for lk in entity_links(engine, cik):
        if old.filed <= lk.boundary_date < new.filed:
            return f"{lk.name or lk.predecessor_cik} → boundary {lk.boundary_date} ({lk.kind})"
    return None


def fit(
    delta: float, cands: list[Candidate], old: float, new: float, nci: float | None
) -> tuple[list[Candidate], float, float | None]:
    """Best ≤ 2 text amounts (either sign) and the NCI share for a step.
    Returns (amounts used, residual, NCI amount used)."""
    pool, seen = [], set()
    for c in cands:
        v = abs(c.value)
        if v == 0 or v > 2 * abs(delta) or v < 0.01 * abs(delta):
            continue
        if _close(v, abs(old)) or _close(v, abs(new)) or round(v) in seen:
            continue
        seen.add(round(v))
        pool.append(c)
    pool = pool[:40]

    def with_nci(r: float) -> tuple[float, float | None]:
        if nci:
            for s in (nci, -nci):
                if abs(r - s) <= max(1e6, 0.001 * abs(delta)) and abs(s) <= abs(r) * 2:
                    return r - s, s
        return r, None

    best: tuple[float, list[Candidate], float, float | None] = (abs(delta), [], delta, None)
    r0, n0 = with_nci(delta)
    if abs(r0) < best[0]:
        best = (abs(r0), [], r0, n0)
    combos: list[tuple[Candidate, ...]] = [(c,) for c in pool] + list(
        itertools.combinations(pool, 2)
    )
    for combo in combos:
        for signs in itertools.product((1, -1), repeat=len(combo)):
            used = sum(s * abs(c.value) for s, c in zip(signs, combo, strict=True))
            r_text = delta - used
            r, n = with_nci(r_text)
            if abs(r_text) > FIT_LEFT * abs(delta) and n is None:
                continue
            if abs(r) < best[0] - 1e-6:
                signed = [
                    Candidate(s * abs(c.value), c.family, c.passage_id, c.doc, c.quote)
                    for s, c in zip(signs, combo, strict=True)
                ]
                best = (abs(r), signed, r, n)
    return best[1], best[2], best[3]


def _close(a: float, b: float) -> bool:
    return b != 0 and abs(a - b) <= max(1.0, 0.0005 * abs(b))


def label_step(
    engine: sqlite3.Connection,
    step: Step,
    scan: TextScan | None,
    ni_chain: list[Version] | None,
    nci_chain: list[Version] | None,
) -> None:
    """Apply the D-M04-16 labels in order; set residual and outcome."""
    old, new, delta = step.old, step.new, step.delta
    labels: list[Label] = []
    whole: Label | None = None
    if step.concept in RECLASS_CONCEPTS and scan and "discontinued" in scan.families:
        a, b = value_at(ni_chain, old.accession), value_at(ni_chain, new.accession)
        if a is not None and b is not None and a == b:
            pid, ref, q = scan.families["discontinued"]
            whole = Label("discontinued", delta, pid, ref, q)
    if old.tag != new.tag:
        labels.append(Label("tag_switch", None, None, new.accession, f"{old.tag} → {new.tag}"))
    if whole is None and _rounding(old.value, new.value):
        whole = Label("rounding", delta)
    if whole is None and (why := _boundary(engine, step.cik, old, new)):
        whole = Label("entity_boundary", delta, None, "", why)
    residual = delta
    if whole is not None:
        labels.append(whole)
        residual = 0.0
    else:
        words = CONCEPT_WORDS[step.concept]
        cands = [
            c
            for c in (scan.candidates if scan else [])
            if (c.family != "restricted_cash" and words.search(c.quote))
            or (c.family == "restricted_cash" and step.concept in CASH_CONCEPTS)
        ]
        nci = None
        if step.concept == "net_income":
            a, b = value_at(nci_chain, old.accession), value_at(nci_chain, new.accession)
            nci = (b - a) if a is not None and b is not None else None
        used, residual, nci_used = fit(delta, cands, old.value, new.value, nci)
        for c in used:
            labels.append(Label(c.family, c.value, c.passage_id, c.doc, c.quote))
        if nci_used is not None:
            labels.append(
                Label(
                    "nci_share",
                    nci_used,
                    None,
                    new.accession,
                    f"change in net income attributable to non-controlling "
                    f"interests {nci_used / 1e6:+,.0f}M",
                )
            )
        used_fams = {lb.family for lb in labels}
        for fam, (pid, ref, q) in scan.families.items() if scan else ():
            if fam not in used_fams and (fam != "restricted_cash" or step.concept in CASH_CONCEPTS):
                labels.append(Label(fam, None, pid, ref, q))
    if scan and scan.error:
        pid, ref, q = scan.error
        labels.append(Label("error", None, pid, ref, q))
    if step.concept in CASH_CONCEPTS and delta != 0:
        labels.append(Label("cf_shift_up" if delta > 0 else "cf_shift_down"))
    labels.sort(key=lambda lb: ORDER.index(lb.family) if lb.family in ORDER else len(ORDER))
    step.labels, step.residual = labels, residual
    if over_tolerance(residual, old.value):
        step.outcome = "review"
    elif step.has("cf_shift_up"):
        step.outcome = "watch"
    else:
        step.outcome = "explained"
    if whole is not None and whole.family != "discontinued" or scan is None:
        step.text_state = "not needed"
    else:
        step.text_state = "text read" if scan.stored else "text not stored"


def walk(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    cik: str,
    concepts: tuple[str, ...] = WALK_CONCEPTS,
) -> list[Step]:
    """Every step of the company's walked concepts, labelled."""
    norm = normalize_cik(cik) or cik
    by_concept = {name: chains(engine, norm, walk_concept(name)) for name in concepts}
    ni = by_concept.get("net_income") or chains(engine, norm, walk_concept("net_income"))
    nci = chains(engine, norm, walk_concept("nci_income"))
    scans: dict[str, TextScan] = {}
    steps: list[Step] = []
    for name in concepts:
        for (start, end, ptype), chain in sorted(by_concept[name].items()):
            distinct = [chain[0]]
            for v in chain[1:]:
                if v.value != distinct[-1].value:
                    distinct.append(v)
            for old, new in zip(distinct, distinct[1:], strict=False):
                st = Step(norm, name, start, end, ptype, old, new, chain[0].value, chain[-1].value)
                needs_text = not _rounding(old.value, new.value)
                scan = None
                if needs_text and corpus is not None:
                    if new.accession not in scans:
                        scans[new.accession] = scan_docs(docs_for(corpus, new.accession), corpus)
                    scan = scans[new.accession]
                elif needs_text:
                    scan = TextScan(stored=False)
                label_step(
                    engine, st, scan, ni.get((start, end, ptype)), nci.get((start, end, ptype))
                )
                steps.append(st)
    return steps


def old_filing_targets(steps: list[Step]) -> list[str]:
    """Changing filings whose text is not stored, for steps the labels could not explain
    (most steps first, then newest)."""
    count: dict[str, int] = defaultdict(int)
    filed: dict[str, str] = {}
    for s in steps:
        if s.outcome == "review" and s.text_state == "text not stored":
            count[s.new.accession] += 1
            filed[s.new.accession] = s.new.filed
    return sorted(count, key=lambda a: (count[a], filed[a]), reverse=True)


# --- Storage and review ---------------------------------------------------------------------


BASELINE_STATE = "m04_walk_baseline:{cik}"


def first_walk(engine: sqlite3.Connection, cik: str) -> bool:
    return (
        engine.execute(
            "SELECT 1 FROM refresh_state WHERE name = ?", (BASELINE_STATE.format(cik=cik),)
        ).fetchone()
        is None
    )


def store(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str | None,
    steps: list[Step],
    now: datetime,
    *,
    queue_items: bool = True,
) -> dict[str, int]:
    """Upsert the steps (owner answers kept), queue `m04_restate` for review steps; the
    company's first walk is a baseline (D-M04-71). Caller owns the transaction."""
    at = iso(now)
    first = first_walk(engine, cik)
    counts = {
        "steps": len(steps),
        "review": 0,
        "queued": 0,
        "overflow": 0,
        "baseline": 0,
        "suppressed": 0,
    }
    keys = set()
    for s in steps:
        keys.add((s.concept, s.start, s.end, s.new.accession))
        engine.execute(
            "INSERT INTO restate_step (cik, concept, period_start, period_end, period_type, "
            "from_value, from_tag, from_accession, from_filed, to_value, to_tag, to_accession, "
            "to_form, to_filed, first_value, latest_value, delta, labels, residual, residual_pct, "
            "outcome, text_state, baseline, first_seen_at, computed_at) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (cik, concept, period_start, period_end, to_accession) DO UPDATE SET "
            "from_value = excluded.from_value, from_tag = excluded.from_tag, "
            "from_accession = excluded.from_accession, from_filed = excluded.from_filed, "
            "to_value = excluded.to_value, to_tag = excluded.to_tag, to_form = excluded.to_form, "
            "to_filed = excluded.to_filed, first_value = excluded.first_value, "
            "latest_value = excluded.latest_value, delta = excluded.delta, "
            "labels = excluded.labels, residual = excluded.residual, "
            "residual_pct = excluded.residual_pct, outcome = excluded.outcome, "
            "text_state = excluded.text_state, computed_at = excluded.computed_at",
            (
                cik,
                s.concept,
                s.start,
                s.end,
                s.ptype,
                s.old.value,
                s.old.tag,
                s.old.accession,
                s.old.filed,
                s.new.value,
                s.new.tag,
                s.new.accession,
                s.new.form,
                s.new.filed,
                s.first_value,
                s.latest_value,
                s.delta,
                json.dumps([lb.as_dict() for lb in s.labels]),
                s.residual,
                s.residual_pct,
                s.outcome,
                s.text_state,
                int(first),
                at,
                at,
            ),
        )
        if s.outcome != "review":
            continue
        counts["review"] += 1
        row = engine.execute(
            "SELECT owner_outcome FROM restate_step WHERE cik = ? AND concept = ? AND "
            "period_start = ? AND period_end = ? AND to_accession = ?",
            (cik, s.concept, s.start, s.end, s.new.accession),
        ).fetchone()
        if not queue_items or (row and row["owner_outcome"]):
            continue
        status = queue.propose(
            engine,
            "m04_restate",
            s.key,
            restate_reason(ticker or cik, s),
            restate_payload(ticker, s),
            now,
            cik=cik,
            baseline=first,
            filed=s.new.filed,
        )
        counts[status] = counts.get(status, 0) + 1
        item = engine.execute(
            "SELECT item_id FROM m04_proposal WHERE prop_key = ?", (f"m04_restate:{s.key}",)
        ).fetchone()
        if item and item["item_id"]:
            engine.execute(
                "UPDATE restate_step SET item_id = ? WHERE cik = ? AND concept = ? AND "
                "period_start = ? AND period_end = ? AND to_accession = ?",
                (item["item_id"], cik, s.concept, s.start, s.end, s.new.accession),
            )
    for r in engine.execute(
        "SELECT concept, period_start, period_end, to_accession FROM "
        "restate_step WHERE cik = ? AND owner_outcome IS NULL",
        (cik,),
    ).fetchall():
        if tuple(r) not in keys:
            engine.execute(
                "DELETE FROM restate_step WHERE cik = ? AND concept = ? AND period_start = ? AND "
                "period_end = ? AND to_accession = ?",
                (cik, *tuple(r)),
            )
    if first:
        engine.execute(
            "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (name) DO NOTHING",
            (BASELINE_STATE.format(cik=cik), "restate.walk", at, json.dumps({"steps": len(steps)})),
        )
    return counts


def money(v: float | None) -> str:
    if v is None:
        return "—"
    if abs(v) >= 100e6:
        return f"{v / 1e6:+,.0f}M".replace("-", "−")
    if abs(v) >= 1e6:
        return f"{v / 1e6:+,.1f}M".replace("-", "−")
    return f"{v / 1e3:+,.0f}K".replace("-", "−")


def restate_reason(who: str, s: Step) -> str:
    return (
        f"{who}: {s.concept} {s.period} changed {money(s.delta)} in {s.new.form} "
        f"{s.new.filed}; {money(s.residual)} unexplained after labels "
        f"({(s.residual_pct or 0) * 100:.2f}% of {money(s.old.value)})"
    )


def restate_payload(ticker: str | None, s: Step) -> dict:
    return {
        "ticker": ticker,
        "concept": s.concept,
        "period": s.period,
        "from_value": s.old.value,
        "from_accession": s.old.accession,
        "from_filed": s.old.filed,
        "to_value": s.new.value,
        "accession": s.new.accession,
        "to_filed": s.new.filed,
        "delta": s.delta,
        "residual": s.residual,
        "residual_pct": s.residual_pct,
        "text_state": s.text_state,
        "labels": [lb.as_dict() for lb in s.labels],
        "from_text": money(s.old.value).lstrip("+"),
        "to_text": money(s.new.value).lstrip("+"),
        "residual_text": money(s.residual),
        "label_texts": [
            lb["name"] + (f" {money(lb['amount'])}" if lb["amount"] is not None else "")
            for lb in (x.as_dict() for x in s.labels)
        ],
    }


def stored_steps(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT * FROM restate_step WHERE cik = ? ORDER BY to_filed DESC, concept, period_end DESC",
        (normalize_cik(cik) or cik,),
    ).fetchall()


# --- dei flag, little r, non-reliance ----------------------------------------------------------


@dataclass(frozen=True)
class DeiFlag:
    accession: str
    form: str
    filed: str
    state: str  # true | false | not on cover | not required | not read


def dei_flags(engine: sqlite3.Connection, cik: str, since: str = "2023-01-01") -> list[DeiFlag]:
    """The error-correction flag per annual report filed since `since` (D-M04-15)."""
    out = []
    for r in engine.execute(
        "SELECT f.accession, f.form, f.filed FROM filing f JOIN filing_cik c ON c.accession = "
        "f.accession WHERE c.cik = ? AND f.form IN ('10-K', '10-K/A', '10-KT', '20-F', '20-F/A', "
        "'40-F') AND f.filed >= ? ORDER BY f.filed DESC",
        (cik, since),
    ):
        if r["filed"] < DEI_FROM:
            out.append(DeiFlag(r["accession"], r["form"], r["filed"], "not required"))
            continue
        st = engine.execute(
            "SELECT detail FROM refresh_state WHERE name = ?", (f"r1:{r['accession']}",)
        ).fetchone()
        if st is None:
            out.append(DeiFlag(r["accession"], r["form"], r["filed"], "not read"))
            continue
        detail = json.loads(st["detail"] or "{}")
        if "error_correction_flag" in detail:
            flag = detail["error_correction_flag"]
        else:
            row = engine.execute(
                "SELECT error_correction_flag FROM cover_shares WHERE accession = ? LIMIT 1",
                (r["accession"],),
            ).fetchone()
            flag = None if row is None or row[0] is None else bool(row[0])
        if detail.get("outcome") not in ("cover",) and flag is None:
            state = f"not on cover ({detail.get('outcome', 'not read')})"
        else:
            state = {True: "true", False: "false", None: "not on cover"}[flag]
        out.append(DeiFlag(r["accession"], r["form"], r["filed"], state))
    return out


@dataclass(frozen=True)
class TextHit:
    accession: str
    filed: str
    form: str
    doc: str
    passage_id: int | None
    quote: str


LITTLE_R_QUERY = (
    '(error OR errors OR misstatement OR misstatements OR "out-of-period" OR '
    'revision OR revised) AND ("previously issued" OR "previously reported" OR '
    '"prior period" OR "prior periods")'
)


def little_r_text(
    engine: sqlite3.Connection, corpus: sqlite3.Connection | None, cik: str, since: str
) -> list[TextHit]:
    """Little-r wording in stored 10-K/10-Q text filed since `since` (sentence-level check:
    an error word beside "previously issued/reported" or "prior period", no hypothetical)."""
    if corpus is None:
        return []
    out, seen = [], set()
    for h in search(
        corpus,
        LITTLE_R_QUERY,
        ciks=[cik],
        doc_types=["10-K", "10-K/A", "10-Q", "10-Q/A"],
        limit=200,
    ):
        f = engine.execute(
            "SELECT form, filed FROM filing WHERE accession = ?", (h.accession,)
        ).fetchone()
        if f is None or f["filed"] < since or h.accession in seen:
            continue
        text = corpus.execute(
            "SELECT substr(text, ?, ?) FROM document WHERE doc_id = ?",
            (h.start + 1, h.end - h.start, h.doc_id),
        ).fetchone()[0]
        for a, b in sentences(text):
            s = text[a:b]
            if is_error_sentence(s):
                seen.add(h.accession)
                out.append(
                    TextHit(
                        h.accession,
                        f["filed"],
                        f["form"],
                        f"{h.accession}/{h.filename}",
                        h.passage_id,
                        quote_at(text, a),
                    )
                )
                break
    return sorted(out, key=lambda t: t.filed, reverse=True)


@dataclass(frozen=True)
class NonReliance:
    accession: str
    filed: str
    mark: str


def non_reliance(
    engine: sqlite3.Connection, cik: str, period_end: str | None = None
) -> NonReliance | None:
    """The open 4.02 that covers `period_end` (any period when None), else None (D-M04-21).
    Later parts call this for every row they compute and show `mark` beside it."""
    row = engine.execute(
        "SELECT accession, filed FROM m04_event WHERE cik = ? AND item = '4.02' AND state IN "
        "('warn', 'fail') AND (? IS NULL OR ? <= filed) ORDER BY filed DESC LIMIT 1",
        (normalize_cik(cik) or cik, period_end, period_end),
    ).fetchone()
    if row is None:
        return None
    return NonReliance(
        row["accession"],
        row["filed"],
        f"inputs under non-reliance (8-K 4.02 filed {row['filed']}, "
        f"{row['accession']}; periods ending on or before that date)",
    )


def evidence_dates(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    cik: str,
    steps_rows: list | None = None,
    since: str = "1990-01-01",
) -> list[tuple[str, str]]:
    """(date, what) for every restatement found: 4.02 events, dei flag true, little-r text,
    walk steps labelled `error`. Used for the 4.01 escalation (D-M04-15)."""
    out = [
        (r["filed"], f"8-K 4.02 {r['accession']}")
        for r in engine.execute(
            "SELECT accession, filed FROM event WHERE cik = ? AND item = '4.02' AND filed >= ?",
            (cik, since),
        )
    ]
    out += [
        (f.filed, f"dei error flag true {f.accession}")
        for f in dei_flags(engine, cik, since)
        if f.state == "true"
    ]
    out += [
        (h.filed, f"little r in {h.form} {h.accession}")
        for h in little_r_text(engine, corpus, cik, since)
    ]
    for r in steps_rows if steps_rows is not None else stored_steps(engine, cik):
        if (
            any(lb["family"] == "error" for lb in json.loads(r["labels"]))
            and r["to_filed"] >= since
        ):
            out.append((r["to_filed"], f"little r in the walk {r['to_accession']}"))
    return sorted(set(out), reverse=True)


def window_start(today: date) -> str:
    return (today - timedelta(days=365 * WINDOW_YEARS)).isoformat()
