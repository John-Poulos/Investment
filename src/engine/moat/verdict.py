"""M06 owner verdicts and the `m06_verdict` review items (rules 2, 6; D-M06-3…5, -8).

The engine proposes, the owner decides (D8):

- proposal: persistent or through_cycle (no challenger warning; challengers arrive in
  Part 2) → "NARROW candidate"; weak → NONE; short_history → UNRATED; not_meaningful →
  UNRATED (book ROIC cannot read it); not_applicable → N_A (no item, written by the pass).
- entry: verdict WIDE / NARROW / NONE / UNRATED, source label(s) (Morningstar's five plus
  vertical integration, D-M06-4), the outline's catch-up band (≤ 3 / 3–5 / 5–10 / > 10 years,
  D-M06-3) and a reason. The band decides the verdict: ≤ 3 = NONE, 3–10 = NARROW, > 10 =
  WIDE; an entry whose verdict and band disagree is refused. UNRATED takes no band (a young
  name may instead get a qualitative verdict, grade B, D-M06-5). An optional quote from a
  stored filing is verified mechanically (D21): found → grade A; not found → the entry is
  stored as `rejected` and never applies. An optional gate override (met / not_met) needs
  its reason (D-M06-5, D12).
- items (kind `m06_verdict`, module M06, outside M04's weekly cap): one setup item per
  covered company that is not N_A and has no verdict (D-M06-8: 15 at the start); later a
  verdict re-opens only when a new 10-K changes the quant class (key `<cik>:reopen:<FY>:
  <class>`) — a challenger warning re-opens it from Part 2. Entering a verdict closes the
  company's open item.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from engine.financials.text import docs_for, passages_for
from engine.llm.verify import MIN_QUOTE, normalize, quote_found
from engine.moat.quant import Quant
from engine.sec.client import iso
from engine.sec.identity import normalize_cik

MODULE = "M06"
KIND = "m06_verdict"
KIND_LABELS = {KIND: "M06: moat verdict to enter (setup batch or quant class changed)"}
ACTIONS = {KIND: ("enter_verdict",)}  # answered on the M06 setup page, never by a button here
VERDICTS = ("WIDE", "NARROW", "NONE", "UNRATED")
SOURCES = {
    "intangibles": "intangibles",
    "switching_costs": "switching costs",
    "network": "network",
    "cost_advantage": "cost advantage",
    "efficient_scale": "efficient scale",
    "vertical_integration": "vertical integration",
}
# band key → (label, low years, high years or None)
BANDS = {
    "le3": ("≤ 3 years", 0, 3),
    "3to5": ("3–5 years", 3, 5),
    "5to10": ("5–10 years", 5, 10),
    "gt10": ("> 10 years", 10, None),
}
BAND_VERDICT = {"le3": "NONE", "3to5": "NARROW", "5to10": "NARROW", "gt10": "WIDE"}
OVERRIDES = ("met", "not_met")


class VerdictError(ValueError):
    """The entry is refused before anything is stored (missing reason, band mismatch)."""


class VerdictRejected(ValueError):
    """The cited quote was not found: the entry is stored as `rejected` and never applies."""

    def __init__(self, message: str, verdict_id: int) -> None:
        super().__init__(message)
        self.verdict_id = verdict_id


@dataclass(frozen=True)
class Proposal:
    verdict: str  # "NARROW candidate" | NONE | UNRATED | N_A | "—"
    why: str

    @property
    def needs_item(self) -> bool:
        return self.verdict not in ("N_A", "—")


def propose(q: Quant) -> Proposal:
    s = q.state
    if s in ("persistent", "through_cycle"):
        return Proposal("NARROW candidate", f"{q.headline()}; no challenger warning (challenger "
                        "tracking arrives in M06 Part 2); you choose NARROW or WIDE by the "
                        "catch-up band")  # fmt: skip
    if s == "weak":
        return Proposal("NONE", f"{q.headline()}: the record shows no durable excess return")
    if s == "short_history":
        return Proposal("UNRATED", f"{q.headline()}: fewer than {q.params.min_years} fiscal "
                        "years with a computable ROIC; a qualitative verdict is grade B "
                        "(D-M06-5)")  # fmt: skip
    if s == "not_meaningful":
        return Proposal("UNRATED", "book ROIC not meaningful (invested capital ≤ 0 in most "
                        "years): judge on other evidence")  # fmt: skip
    if s == "not_applicable":
        return Proposal("N_A", q.headline())
    return Proposal("—", f"no proposal: {q.missing}")


@dataclass(frozen=True)
class Entry:
    verdict: str
    sources: tuple[str, ...] = ()
    band: str = ""
    reason: str = ""
    accession: str = ""
    quote: str = ""
    override: str = ""
    override_reason: str = ""


def band_low(band: str | None) -> int | None:
    return BANDS[band][1] if band in BANDS else None


def band_text(band: str | None) -> str:
    return BANDS[band][0] if band in BANDS else "—"


def source_text(sources: str | None) -> str:
    keys = [s for s in (sources or "").split(",") if s]
    return ", ".join(SOURCES.get(s, s) for s in keys) or "—"


def validate(e: Entry) -> Entry:
    v = (e.verdict or "").strip().upper()
    if v == "N_A":
        raise VerdictError("N_A comes from the model tags (config/company_models.toml) or the "
                           "SEC industry code, not from an entry.")  # fmt: skip
    if v not in VERDICTS:
        raise VerdictError(f"Choose a verdict: {', '.join(VERDICTS)}.")
    if not e.reason.strip():
        raise VerdictError("A reason is required.")
    band = (e.band or "").strip()
    sources = tuple(dict.fromkeys(s.strip() for s in e.sources if s.strip()))
    unknown = [s for s in sources if s not in SOURCES]
    if unknown:
        raise VerdictError(f"Unknown source label {unknown[0]!r}.")
    if v == "UNRATED":
        if band:
            raise VerdictError("UNRATED takes no catch-up band; choose a verdict to give one.")
    else:
        if band not in BANDS:
            raise VerdictError("Choose the catch-up band (outline Moat 5: can a competitor "
                               "catch up in 3 years or less?).")  # fmt: skip
        if BAND_VERDICT[band] != v:
            raise VerdictError(f"A catch-up band of {BANDS[band][0]} reads "
                               f"{BAND_VERDICT[band]}, not {v} (≤ 3 = NONE, 3–10 = NARROW, "
                               "> 10 = WIDE; D-M06-3).")  # fmt: skip
    if v in ("WIDE", "NARROW") and not sources:
        raise VerdictError("Name at least one moat source for WIDE or NARROW (D-M06-4).")
    ov = (e.override or "").strip()
    if ov and ov not in OVERRIDES:
        raise VerdictError("A gate override is met or not_met.")
    if ov and not e.override_reason.strip():
        raise VerdictError("A gate override needs its reason (logged, D-M06-5).")
    acc, quote = e.accession.strip(), " ".join(e.quote.split())
    if quote and not acc:
        raise VerdictError("Give the accession of the filing the quote comes from.")
    if acc and not quote:
        raise VerdictError("Give the quote from that filing, or leave the accession empty.")
    if quote and len(normalize(quote).strip(" .…\"'")) < MIN_QUOTE:
        raise VerdictError(f"The quote is too short to verify (at least {MIN_QUOTE} characters).")
    return Entry(v, sources, band, e.reason.strip(), acc, quote, ov, e.override_reason.strip())


def verify_quote(corpus: sqlite3.Connection, cik: str, accession: str, quote: str) -> str | None:
    """`<accession>/<filename>[#p<passage>]` when the quote is in a stored document of the
    company's own SEC filing (not a transcript `AV-` or IR document `IR-`), else None."""
    if accession.upper().startswith(("AV-", "IR-")):
        return None
    for d in docs_for(corpus, accession):
        row = corpus.execute("SELECT cik FROM document WHERE doc_id = ?", (d.doc_id,)).fetchone()
        if row is None or row[0] != cik or not quote_found(quote, d.text):
            continue
        for pid, a, b in passages_for(corpus, d.doc_id):
            if quote_found(quote, d.text[a:b]):
                return f"{d.ref}#p{pid}"
        return d.ref
    return None


def current(engine: sqlite3.Connection, cik: str) -> sqlite3.Row | None:
    """The company's verdict in force: its newest active entry."""
    return engine.execute(
        "SELECT * FROM m06_verdict WHERE cik = ? AND status = 'active' "
        "ORDER BY decided_at DESC, verdict_id DESC LIMIT 1",
        (normalize_cik(cik) or cik,),
    ).fetchone()


def history(engine: sqlite3.Connection, cik: str, limit: int = 20) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT * FROM m06_verdict WHERE cik = ? ORDER BY decided_at DESC, verdict_id DESC LIMIT ?",
        (normalize_cik(cik) or cik, limit),
    ).fetchall()


def open_item(engine: sqlite3.Connection, cik: str) -> sqlite3.Row | None:
    return engine.execute(
        "SELECT * FROM review_queue WHERE kind = ? AND cik = ? AND resolved_at IS NULL "
        "ORDER BY item_id DESC LIMIT 1",
        (KIND, normalize_cik(cik) or cik),
    ).fetchone()


def enter(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    cik: str,
    entry: Entry,
    q: Quant,
    by: str,
    now: datetime,
) -> int:
    """Store an owner verdict and close the open item; returns the verdict id. Refused
    entries raise VerdictError (nothing stored); an unverified quote stores the entry as
    `rejected` and raises VerdictRejected. Caller owns no transaction (one is opened here)."""
    norm = normalize_cik(cik) or cik
    e = validate(entry)
    if q.state == "not_applicable":
        raise VerdictError(f"{q.ticker} reads N_A ({q.headline()}): edit the model tag "
                           "file to rate it.")  # fmt: skip
    ref, status, grade = None, "active", "B"
    if e.quote:
        ref = verify_quote(corpus, norm, e.accession, e.quote)
        status, grade = ("active", "A") if ref else ("rejected", "B")
    item = open_item(engine, norm)
    prop = propose(q)
    ts = iso(now)
    engine.execute("BEGIN")
    try:
        vid = engine.execute(
            "INSERT INTO m06_verdict (cik, verdict, sources, band, reason, passage_ref, quote, "
            "quote_status, grade, override, override_reason, quant_class, quant_fy, proposal, "
            "item_id, status, decided_by, decided_at, as_of) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (norm, e.verdict, ",".join(e.sources) or None, e.band or None, e.reason,
             ref or (f"{e.accession} (quote not found)" if e.quote else None), e.quote or None,
             ("verified" if ref else "rejected") if e.quote else None, grade, e.override or None,
             e.override_reason or None, q.state, q.newest_fy, prop.verdict,
             item["item_id"] if item and status == "active" else None, status, by, ts,
             now.date().isoformat()),
        ).lastrowid  # fmt: skip
        if item is not None and status == "active":
            res = f"verdict {e.verdict}" + (f" ({band_text(e.band)})" if e.band else "")
            engine.execute(
                "UPDATE review_queue SET resolved_at = ?, resolution = ?, resolved_by = ?, "
                "note = ? WHERE item_id = ? AND resolved_at IS NULL",
                (ts, res, by, e.reason, item["item_id"]),
            )
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    if status == "rejected":
        raise VerdictRejected(
            f"The quote was not found in the stored text of {e.accession} for this company "
            f"(D21): the entry is stored as rejected (id {vid}) and does not apply.",
            vid,
        )
    return vid


def _has_item(engine: sqlite3.Connection, cik: str, key: str) -> bool:
    return (
        engine.execute(
            "SELECT 1 FROM review_queue WHERE kind = ? AND cik = ? AND "
            "json_extract(payload, '$.key') = ?",
            (KIND, cik, key),
        ).fetchone()
        is not None
    )


def propose_item(engine: sqlite3.Connection, q: Quant, now: datetime) -> str:
    """Queue the setup item or a re-open item when due → 'queued' | 'none'. Caller owns the
    transaction. Outside M04's cap (D-M06-8: its own setup batch)."""
    prop = propose(q)
    if not prop.needs_item or q.state is None:
        return "none"
    v = current(engine, q.cik)
    if v is None:
        key = f"{q.cik}:setup"
        reason = f"{q.ticker}: moat verdict to enter (setup batch); proposal {prop.verdict}"
    else:
        changed = v["quant_class"] != q.state and (v["quant_fy"] or "") != (q.newest_fy or "")
        if not changed:
            return "none"
        key = f"{q.cik}:reopen:{q.newest_fy}:{q.state}"
        reason = (f"{q.ticker}: quant class changed {v['quant_class']} → {q.state} at "
                  f"{q.newest_fy} (verdict {v['verdict']} of {v['as_of']}); proposal "
                  f"{prop.verdict}")  # fmt: skip
    if _has_item(engine, q.cik, key) or open_item(engine, q.cik) is not None:
        return "none"
    payload = {"key": key, "ticker": q.ticker, "proposal": prop.verdict, "why": prop.why,
               "quant_state": q.state, "share": q.value, "fy": q.newest_fy}  # fmt: skip
    engine.execute(
        "INSERT INTO review_queue (module_id, kind, cik, reason, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (MODULE, KIND, q.cik, reason, json.dumps(payload), iso(now)),
    )
    return "queued"
