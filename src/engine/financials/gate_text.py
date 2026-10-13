"""Survival gate: going-concern and covenant text (M04 Part 4b-lite; D-M04-34, -71, -95…98).

Stored text only (0 SEC requests): every stored document of the company's periodic
filings (10-K, 10-Q, 10-KT, 10-QT, 20-F, 40-F, their amendments) and 6-Ks — the main
document, EX-99 (a 6-K's report) and EX-10 (credit agreements and amendments). Each
document is scanned once per classifier version (`SCAN_VERSION`, recorded with the
document's sha256 in `refresh_state` `m04_gate_text:<cik>`); a changed document is scanned
again. Quotes are cut from the stored text by offsets and kept with the passage id (D21).

Classes (D-M04-34; sentence classifier, tense and modality decide, not the section):

- **fail** — `auditor_gc` (the auditor's going-concern paragraph), `management_exists`
  ("substantial doubt exists", "there is substantial doubt", "these conditions raise
  substantial doubt", also in risk factors in the present tense), `breach_unwaived`,
  `forbearance`, `reclass_covenant` (debt classified as current for a breach or default),
  `acceleration` ("immediately due and payable"), `delisting`;
- **warn + review** — `alleviated` (also a "raise" conclusion with an alleviation sentence
  within 1,500 characters), `auditor_cam` (a critical audit matter without a going-concern
  paragraph), `ifrs_material_uncertainty`, `breach_waived` (a waiver in the sentence, or in
  the next one referring back: "this violation", "such default"), `reset` (covenant relief
  period, amended financial covenants), `listing_deficiency` (cure-period notice);
- **hypothetical** ("could raise substantial doubt") — `m04_gc_text` review only while the
  runway is below 8 quarters (or unknown), else information;
- **no trigger** — `boilerplate` (the ASC 205-40 evaluation, going-concern basis),
  `negated`, `compliant` ("in compliance with … covenants"), `no_default`;
- **excluded** — any class in a `spac_shell` period (model tag keyed on period end, else
  the shell boundary in `entity_link`, else an untagged blank-check report before the
  company's 8-K 2.01 close; S4.5).

Exhibits (EX-10) count only for `reset`: credit agreements define "Event of Default" and
"forbearance" as terms. Hypothetical covenant sentences ("could result in an event of
default") are counted, not stored.

Which rows act on the gate is decided at read time (D-M04-96): the company's **current
report** as of the gate's date = the latest scanned periodic filing filed by then, plus the
6-Ks filed after it. Older rows are history: shown, never gate inputs.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from engine.financials import models as models_mod
from engine.financials.text import clean, docs_for, passages_for, sentences
from engine.sec.asof import PERIODIC_FORMS
from engine.sec.client import iso
from engine.sec.identity import entity_links, normalize_cik
from engine.signals import Source

SCAN_VERSION = "gate-text-1"
STATE_KEY = "m04_gate_text:{cik}"
FOREIGN_CURRENT = frozenset({"6-K", "6-K/A"})
SCAN_FORMS = PERIODIC_FORMS | FOREIGN_CURRENT
HYPO_RUNWAY_Q = 8.0  # D-M04-34: hypothetical wording is reviewed only below 8 quarters
ALLEVIATION_WINDOW = 1500  # characters around a "raise" conclusion (D-M04-95)
SIX_K_ONLY_DAYS = 400  # a company with only 6-Ks: those filed in this window are current

# class → (family, base effect, label)
CLASSES: dict[str, tuple[str, str, str]] = {
    "auditor_gc": ("going_concern", "fail", "auditor going-concern paragraph"),
    "management_exists": ("going_concern", "fail", 'management: "substantial doubt exists"'),
    "alleviated": ("going_concern", "warn", "substantial doubt alleviated"),
    "auditor_cam": ("going_concern", "warn", "auditor critical audit matter only"),
    "ifrs_material_uncertainty": ("going_concern", "warn", 'IFRS "material uncertainty"'),
    "hypothetical": ("going_concern", "hypothetical",
                     'hypothetical ("could raise substantial doubt")'),
    "boilerplate": ("going_concern", "none", "ASC 205-40 evaluation or going-concern basis"),
    "negated": ("going_concern", "none", "negated (no substantial doubt)"),
    "breach_unwaived": ("covenant", "fail", "covenant breach or event of default, not waived"),
    "forbearance": ("covenant", "fail", "forbearance"),
    "reclass_covenant": ("covenant", "fail", "debt classified as current (breach or default)"),
    "acceleration": ("covenant", "fail", "debt accelerated (immediately due and payable)"),
    "delisting": ("covenant", "fail", "delisting or trading suspension"),
    "breach_waived": ("covenant", "warn", "covenant breach waived"),
    "reset": ("covenant", "warn", "covenants reset (relief period, amended covenants)"),
    "listing_deficiency": ("covenant", "warn", "listing-standard deficiency (cure period)"),
    "compliant": ("covenant", "none", '"in compliance" with covenants'),
    "no_default": ("covenant", "none", "no default (negated)"),
}  # fmt: skip
SEVERITY = {"fail": 3, "warn": 2, "hypothetical": 1, "none": 0, "excluded": -1}
KIND_OF_FAMILY = {"going_concern": "m04_gc_text", "covenant": "m04_covenant"}
SIGNAL_OF_FAMILY = {"going_concern": "gc_language", "covenant": "covenant_status"}
OWNER_OUTCOMES = ("noted", "treat_as_fail", "misread")

TRIGGER = re.compile(
    r"substantial doubt|going concern|material uncertaint|significant doubt|covenant|"
    r"waive|forbear|events? of default|cross[- ]default|as (?:a )?current|delist|"
    r"immediately due and payable|in default|in compliance|regain compliance|relief period",
    re.I,
)
SD = re.compile(r"substantial doubt", re.I)
MU = re.compile(r"material uncertaint(?:y|ies)|significant doubt", re.I)
GC = re.compile(r"going concern", re.I)
HYPO = re.compile(
    r"\b(?:could|may|might|would|if|unless|in the event|no assurance|cannot assure|"
    r"can be no assurance|should|potential(?:ly)?|possib(?:le|ly|ility)|risk that|whether)\b",
    re.I,
)
ALLEV = re.compile(r"alleviat", re.I)
NOT_ALLEV = re.compile(
    r"\b(?:not|no longer|cannot|unable to)\s+(?:\w+\s+){0,3}alleviat|"
    r"\bnot\s+(?:been\s+)?alleviated",
    re.I,
)
NEG_GC = re.compile(
    r"\b(?:no|not|never|nor|without)\s+(?:\w+\s+){0,6}(?:substantial doubt|material "
    r"uncertaint|significant doubt)|substantial doubt[^.;]{0,60}\b(?:does|did|do) not exist|"
    r"substantial doubt[^.;]{0,40}\bno longer\b|\bnot aware of any material uncertaint",
    re.I,
)
CONCLUDED = re.compile(
    r"\b(?:concluded|concludes|determined|determines)\b[^.;]{0,80}substantial doubt", re.I
)
EXISTS = re.compile(
    r"substantial doubt (?:exists|existed|remains)|there (?:is|was|remains) (?:a )?substantial "
    r"doubt|\braise[sd]? substantial doubt|substantial doubt (?:about|regarding|as to|"
    r"concerning)[^.;]{0,100}(?:ability|continue)",
    re.I,
)
EVAL = re.compile(
    r"\bevaluat\w*\b[^.;]{0,160}\bwhether\b|\brequired to (?:evaluate|assess)\b|"
    r"\bassess\w*\b[^.;]{0,80}\bwhether\b|\b205-40\b[^.;]{0,200}\bevaluat|"
    r"\bevaluat\w*[^.;]{0,200}\b205-40\b",
    re.I,
)
BASIS = re.compile(
    r"going concern basis|basis of (?:a )?going concern|assum\w* (?:that )?the \w+ will "
    r"continue as a going concern|(?:prepared|presented) on a going concern",
    re.I,
)
AUDITOR = re.compile(
    r"registered public accounting firm|we have audited|\bour audits?\b|in our opinion|"
    r"basis for (?:the )?opinion",
    re.I,
)
GC_PARAGRAPH = re.compile(
    r"(?:prepared|presented) assuming that the \w+ will continue as a going concern|"
    r"substantial doubt about the \w+['’]s ability to continue as a going concern\s*\n",
    re.I,
)
CAM = re.compile(r"critical audit matter", re.I)
# The auditor's report ends where the statements' notes or the next item begin
SECTION_END = re.compile(
    r"\n\s*(?:note\s+\d+\b|notes to (?:the )?(?:condensed )?(?:consolidated )?financial|"
    r"item\s+\d+[a-z]?\b)",
    re.I,
)


def _auditor_context(before: str, rx: re.Pattern, n: int) -> bool:
    """`rx` (auditor or CAM wording) within `n` characters before, with no notes heading or
    item heading after its last occurrence (the sentence is still inside the report)."""
    window = before[-n:]
    last = None
    for m in rx.finditer(window):
        last = m
    return last is not None and not SECTION_END.search(window, last.end())


def is_heading(sent: str) -> bool:
    """A heading line ("Substantial Doubt About the Company's Ability to Continue as a Going
    Concern"): no closing punctuation and at most 16 words. Headings are not conclusions."""
    s = sent.strip()
    return bool(s) and s[-1] not in '.;:!?”")' and len(s.split()) <= 16


COV_CTX = re.compile(
    r"covenant|credit agreement|credit facilit|loan agreement|term loan|revolv|indenture|"
    r"\bnotes?\b|debenture|lender|borrowing|facility|\bdebt\b",
    re.I,
)
FORBEAR = re.compile(r"forbearance|agreed to forbear|forbear from", re.I)
RESET_TERM = re.compile(r"covenant relief|relief period", re.I)
RESET = re.compile(
    r"amend\w*[^.;]{0,100}financial covenants?|financial covenants?[^.;]{0,100}amend\w*|"
    r"(?:increase|raise)[sd]? the (?:maximum|permitted)[^.;]{0,40}(?:leverage|debt)[^.;]{0,20}"
    r"ratio|(?:reset|relax|suspend)\w*[^.;]{0,40}covenants?",
    re.I,
)
WAIVER = re.compile(r"\bwaive[rd]?s?\b|\bwaiving\b", re.I)
REFER = re.compile(
    r"\b(?:such|this|these|that|the foregoing|the)\s+(?:covenant\s+)?(?:breach(?:es)?|"
    r"defaults?|non-?compliance|violations?|events? of default|failure)\b",
    re.I,
)
BREACH = re.compile(
    r"not in compliance with[^.;]{0,160}(?:covenant|credit agreement|credit facilit|loan "
    r"agreement|indenture|facility)|(?:breach(?:ed)?|violat\w*|default(?:ed)?)\b[^.;]{0,80}"
    r"(?:covenant|credit agreement|credit facilit|indenture|loan agreement)|covenant "
    r"(?:default|breach|violation)s?|(?:did|does|do) not (?:meet|satisfy|comply with)"
    r"[^.;]{0,100}(?:covenant|ratio)|failed to (?:meet|satisfy|comply with)[^.;]{0,100}covenant|"
    r"events? of default\b[^.;]{0,60}(?:has|have|had) occurred|events? of default\b[^.;]{0,40}"
    r"(?:is|are) continuing|\bin default (?:under|of|on)\b",
    re.I,
)
NEG_COV = re.compile(
    r"\bno (?:event of default|events of default|default|breach|covenant (?:breach|violation)|"
    r"violation)s?\b|\bnot in default\b|\b(?:has|have|had) not occurred\b|\bwithout (?:default|"
    r"breach)|\bthere (?:were|was|are|is) no\b",
    re.I,
)
RECLASS = re.compile(
    r"(?:classified|reclassified|presented|recorded)\s+(?:\w+\s+){0,6}as (?:a )?current", re.I
)
RECLASS_WHY = re.compile(r"covenant|default|waiver|demand|callable|breach", re.I)
ACCEL = re.compile(
    r"(?:declared|became|become|been|are now|is now)\s+(?:\w+\s+){0,8}immediately due and payable|"
    r"accelerated (?:the )?(?:maturity|repayment|payment)",
    re.I,
)
DELIST = re.compile(
    r"(?:determined|decided|determination) to delist|(?:has|have|was|were) (?:been )?"
    r"(?:suspended and )?delisted|trading[^.;]{0,60}(?:was|has been|have been) suspended|"
    r"filed (?:a )?Form 25",
    re.I,
)
LISTING = re.compile(
    r"not in compliance with[^.;]{0,120}(?:listing|minimum bid|bid price|Nasdaq|NYSE|"
    r"stockholders['’] equity requirement|market value)|\bregain(?:ed)? compliance\b|"
    r"deficiency (?:letter|notice)",
    re.I,
)
COMPLIANT = re.compile(r"\bin compliance with\b", re.I)
NOT_COMPLIANT = re.compile(r"\bnot in compliance\b", re.I)
SPAC_TEXT = re.compile(r"blank check company|initial business combination|trust account", re.I)


def _before(sent: str, m: re.Match, n: int = 140) -> str:
    return sent[max(0, m.start() - n) : m.start()]


def _hypo_before(sent: str, m: re.Match, n: int = 140) -> bool:
    return bool(HYPO.search(_before(sent, m, n)))


def _hypo_around(sent: str, m: re.Match, n: int = 140, after: int = 80) -> bool:
    """A modal before the covenant phrase or right after it ("Any breach … could result in
    an event of default")."""
    return _hypo_before(sent, m, n) or bool(HYPO.search(sent[m.start() : m.end() + after]))


# --- Sentence classes ---------------------------------------------------------------------


def classify_gc(sent: str, before: str, around: str) -> tuple[str | None, str]:
    """Going-concern class of one sentence → (class or None, note). `before` = the text up
    to 6,000 characters before the sentence (auditor context); `around` = the sentences
    within 1,500 characters (an alleviation nearby)."""
    sd, mu = SD.search(sent), MU.search(sent)
    if not sd and not mu:
        if GC.search(sent) and BASIS.search(sent):
            return "boilerplate", ""
        return None, ""
    if not sd and mu:  # IFRS wording (IAS 1.25 / IAS 8.6K)
        if NEG_GC.search(sent):
            return "negated", ""
        if _hypo_before(sent, mu, 80):
            return "hypothetical", ""
        return "ifrs_material_uncertainty", ""
    near_before = before[-1500:]
    if _auditor_context(before, AUDITOR, 6000):
        paragraph = GC_PARAGRAPH.search(near_before + "\n" + sent) and not NEG_GC.search(sent)
        if (
            paragraph
            and EXISTS.search(sent)
            and not ALLEV.search(sent)
            and not _hypo_before(sent, sd)
        ):
            return "auditor_gc", "auditor's report"
        if _auditor_context(before, CAM, 4000):
            return "auditor_cam", "critical audit matter (no going-concern paragraph)"
    if ALLEV.search(sent):
        if NOT_ALLEV.search(sent):
            return "management_exists", "plans do not alleviate the doubt"
        return "alleviated", ""
    if CONCLUDED.search(sent) and not NEG_GC.search(sent):
        return _alleviated_nearby("management_exists", around)
    if EVAL.search(sent):
        return "boilerplate", "ASC 205-40 evaluation"
    if NEG_GC.search(sent):
        return "negated", ""
    if _hypo_before(sent, sd):
        return "hypothetical", ""
    if EXISTS.search(sent):
        return _alleviated_nearby("management_exists", around)
    return None, ""


def _alleviated_nearby(klass: str, around: str) -> tuple[str, str]:
    for s in re.split(r"(?<=[.;])\s+", around):
        if ALLEV.search(s) and SD.search(s) and not NOT_ALLEV.search(s):
            return "alleviated", f"alleviated nearby: “{clean(s)[:240]}”"
    return klass, ""


def classify_cov(sent: str, nxt: str, exhibit: bool) -> tuple[str | None, str]:
    """Covenant / listing class of one sentence → (class, note) or (None, "hypothetical")
    for a counted, unstored hypothetical. `nxt` = the next sentence (a waiver referring
    back). Exhibits count only for `reset`."""
    term = RESET_TERM.search(sent)
    if exhibit:
        if term or (RESET.search(sent) and not HYPO.search(sent)):
            return "reset", "exhibit"
        return None, ""
    lst = LISTING.search(sent)
    if lst and not DELIST.search(sent):
        if _hypo_before(sent, lst):
            return None, "hypothetical"
        return "listing_deficiency", ""
    d = DELIST.search(sent)
    if d:
        return (None, "hypothetical") if _hypo_around(sent, d) else ("delisting", "")
    f = FORBEAR.search(sent)
    if f:
        if _hypo_around(sent, f) or NEG_COV.search(sent):
            return None, "hypothetical"
        return "forbearance", ""
    if term:
        return "reset", ""
    r = RESET.search(sent)
    if r and not _hypo_before(sent, r):
        return "reset", ""
    if not COV_CTX.search(sent):
        return None, ""
    rc = RECLASS.search(sent)
    if rc and RECLASS_WHY.search(sent):
        if _hypo_around(sent, rc) or NEG_COV.search(sent):
            return None, "hypothetical"
        return "reclass_covenant", ""
    a = ACCEL.search(sent)
    if a:
        if _hypo_around(sent, a) or NEG_COV.search(sent):
            return None, "hypothetical"
        return "acceleration", ""
    b = BREACH.search(sent)
    if b:
        if _hypo_around(sent, b):
            return None, "hypothetical"
        if NEG_COV.search(sent):
            return "no_default", ""
        if WAIVER.search(sent):
            return "breach_waived", ""
        if WAIVER.search(nxt) and REFER.search(nxt):
            return "breach_waived", f"waiver in the next sentence: “{clean(nxt)[:240]}”"
        return "breach_unwaived", ""
    if COMPLIANT.search(sent) and not NOT_COMPLIANT.search(sent):
        c = COMPLIANT.search(sent)
        return (None, "hypothetical") if _hypo_before(sent, c) else ("compliant", "")
    if NEG_COV.search(sent) and re.search(r"default|breach|violation", sent, re.I):
        return "no_default", ""
    return None, ""


@dataclass
class Hit:
    start: int
    end: int
    klass: str
    note: str
    quote: str

    @property
    def family(self) -> str:
        return CLASSES[self.klass][0]

    @property
    def effect(self) -> str:
        return CLASSES[self.klass][1]


@dataclass
class DocScan:
    hits: list[Hit] = field(default_factory=list)
    hypothetical_cov: int = 0  # covenant hypotheticals counted, not stored
    sentences: int = 0


def scan_text(text: str, *, exhibit: bool = False) -> DocScan:
    """Classify every sentence of a document that carries a trigger word."""
    out = DocScan()
    seen: set[tuple[str, str]] = set()
    last_end = -1
    for m in TRIGGER.finditer(text):
        if m.start() < last_end:
            continue  # same sentence as the previous trigger word
        s, e = _sentence(text, m.start())
        last_end = max(e, m.end())
        out.sentences += 1
        sent = text[s:e]
        if is_heading(sent):
            continue
        nxt = _next_sentence(text, e)
        cg, ng = (None, "") if exhibit else classify_gc(
            sent, text[max(0, s - 6000) : s],
            text[max(0, s - ALLEVIATION_WINDOW) : min(len(text), e + ALLEVIATION_WINDOW)],
        )  # fmt: skip
        cc, nc = classify_cov(sent, nxt, exhibit)
        if cc is None and nc == "hypothetical":
            out.hypothetical_cov += 1
        best = max(
            ((k, n) for k, n in ((cg, ng), (cc, nc)) if k),
            key=lambda kn: SEVERITY[CLASSES[kn[0]][1]],
            default=None,
        )
        if best is None:
            continue
        quote = clean(sent)
        if (best[0], quote) in seen:
            continue  # the same sentence repeated (MD&A and notes)
        seen.add((best[0], quote))
        out.hits.append(Hit(s, e, best[0], best[1], quote))
    return out


def _sentence(text: str, pos: int) -> tuple[int, int]:
    """The sentence around `pos`: from the last sentence end (or a blank line) before it to
    the next one, bounded to 1,500 characters each side."""
    lo = max(0, pos - 1500)
    hi = min(len(text), pos + 1500)
    best = (lo, hi)
    for s, e in sentences(text, lo, hi):
        if s <= pos < e:
            return s, e
        if s <= pos:
            best = (s, e)
    return best


def _next_sentence(text: str, end: int) -> str:
    nxt = next(iter(sentences(text, end, min(len(text), end + 1500))), None)
    return text[nxt[0] : nxt[1]] if nxt else ""


# --- Filings, documents and the SPAC exclusion ----------------------------------------------


@dataclass(frozen=True)
class Filing:
    accession: str
    form: str
    filed: str
    period_end: str | None


def filings(engine: sqlite3.Connection, cik: str) -> list[Filing]:
    """Periodic filings and 6-Ks of the company (filing index), newest first."""
    marks = ",".join("?" * len(SCAN_FORMS))
    out = []
    for r in engine.execute(
        f"SELECT f.accession, f.form, f.filed, f.report_date FROM filing f JOIN filing_cik c "
        f"ON c.accession = f.accession WHERE c.cik = ? AND f.form IN ({marks}) "
        "ORDER BY f.filed DESC, f.accession DESC",
        (cik, *sorted(SCAN_FORMS)),
    ):
        end = r["report_date"]
        if not end:
            got = engine.execute(
                "SELECT max(period_end) FROM fact WHERE accession = ?", (r["accession"],)
            ).fetchone()
            end = got[0] if got else None
        out.append(Filing(r["accession"], r["form"], r["filed"], end))
    return out


def readable(doc_type: str | None, filename: str, form: str) -> tuple[bool, bool]:
    """(scan it, is an exhibit). Main documents, EX-99 (a 6-K's report) and EX-10."""
    t = (doc_type or "").upper()
    if not t or t == form.upper() or t in SCAN_FORMS:
        return True, False
    if t.startswith("EX-99"):
        return True, form not in FOREIGN_CURRENT  # a 6-K's EX-99 is the report itself
    if t.startswith("EX-10"):
        return True, True
    return False, False


def spac_close(engine: sqlite3.Connection, cik: str) -> tuple[str | None, str]:
    """The de-SPAC closing: the shell boundary in `entity_link`, else the 8-K 2.01 event."""
    links = [lk.boundary_date for lk in entity_links(engine, cik) if lk.kind == "spac_shell"]
    if links:
        return max(links), "shell boundary (entity_link)"
    r = engine.execute(
        "SELECT coalesce(report_date, filed) AS d, filed FROM event WHERE cik = ? AND "
        "item = '2.01' ORDER BY filed LIMIT 1",
        (cik,),
    ).fetchone()
    if r is not None:
        return r["d"], f"8-K 2.01 filed {r['filed']}"
    return None, ""


def excluded(
    engine: sqlite3.Connection,
    mf: models_mod.ModelFile,
    cik: str,
    ticker: str | None,
    period_end: str | None,
    text: str,
) -> str:
    """Why a report's text is out (a `spac_shell` period, keyed on period end), or ""."""
    if period_end is None:
        return ""
    t = mf.for_company(cik, ticker, period_end)
    if t is not None and t.tag == "spac_shell":
        return f"spac_shell period (model tag, periods before {t.before or 'the close'})"
    close, how = spac_close(engine, cik)
    shell = bool(entity_links(engine, cik)) or bool(SPAC_TEXT.search(text[:400_000]))
    if close and period_end < close and shell:
        return f"pre-merger SPAC period (period {period_end} before the close {close}; {how})"
    return ""


# --- Scan and store -------------------------------------------------------------------------


def load_state(engine: sqlite3.Connection, cik: str) -> dict | None:
    row = engine.execute(
        "SELECT detail FROM refresh_state WHERE name = ?", (STATE_KEY.format(cik=cik),)
    ).fetchone()
    try:
        return json.loads(row["detail"]) if row and row["detail"] else None
    except json.JSONDecodeError:
        return None


def save_state(engine: sqlite3.Connection, cik: str, st: dict, now: datetime) -> None:
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
        "detail = excluded.detail",
        (STATE_KEY.format(cik=cik), "M04 Part 4b", iso(now), json.dumps(st, sort_keys=True)),
    )


@dataclass
class CompanyScan:
    cik: str
    first: bool = False
    docs_read: int = 0
    docs_skipped: int = 0  # already scanned at this version
    sentences: int = 0
    hypothetical_cov: int = 0
    rows_new: int = 0
    rows_kept: int = 0  # answered or reviewed rows kept across a re-scan
    no_text: list[str] = field(default_factory=list)  # periodic filings without stored text
    notes: list[str] = field(default_factory=list)


def _passage(passages: list[tuple[int, int, int]], pos: int) -> int | None:
    for pid, a, b in passages:
        if a <= pos < b:
            return pid
    return None


def scan_company(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    cik: str,
    ticker: str | None,
    now: datetime,
    *,
    mf: models_mod.ModelFile | None = None,
) -> CompanyScan:
    """Scan the company's not-yet-scanned documents and store their rows (0 requests).
    Caller owns no transaction."""
    norm = normalize_cik(cik) or cik
    mf = mf if mf is not None else models_mod.load_safe()
    st = load_state(engine, norm) or {}
    cs = CompanyScan(norm, first="first_scan_at" not in st)
    docs_state: dict[str, list] = st.get("docs", {})
    fil_state: dict[str, dict] = st.get("filings", {})
    ts = iso(now)
    engine.execute("BEGIN")
    try:
        for f in filings(engine, norm):
            docs = docs_for(corpus, f.accession)
            if not docs:
                if f.form not in FOREIGN_CURRENT:
                    cs.no_text.append(f"{f.form} {f.accession} filed {f.filed}")
                continue
            any_read = False
            for d in docs:
                scan, exhibit = readable(d.doc_type, d.filename, f.form)
                if not scan:
                    continue
                any_read = True
                sha = corpus.execute(
                    "SELECT sha256 FROM document WHERE doc_id = ?", (d.doc_id,)
                ).fetchone()[0]
                key = f"{d.accession}/{d.filename}"
                if docs_state.get(key) == [SCAN_VERSION, sha]:
                    cs.docs_skipped += 1
                    continue
                cs.docs_read += 1
                res = scan_text(d.text, exhibit=exhibit)
                cs.sentences += res.sentences
                cs.hypothetical_cov += res.hypothetical_cov
                why = excluded(engine, mf, norm, ticker, f.period_end, d.text)
                cs.rows_kept += _replace_rows(engine, d.accession, d.filename)
                spans = passages_for(corpus, d.doc_id)
                for h in res.hits:
                    if not verified(d.text, h):
                        continue  # never store an unverified quote (D21)
                    effect = "excluded" if why else h.effect
                    note = "; ".join(x for x in (why, h.note) if x)
                    cur = engine.execute(
                        "INSERT INTO gate_text (accession, filename, start_offset, end_offset, "
                        "cik, form, doc_type, filed, period_end, family, class, effect, quote, "
                        "passage_id, doc_id, exhibit, note, baseline, first_seen_at, "
                        "computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                        "?, ?, ?) ON CONFLICT (accession, filename, start_offset) DO NOTHING",
                        (d.accession, d.filename, h.start, h.end, norm, f.form, d.doc_type,
                         f.filed, f.period_end, h.family, h.klass, effect, h.quote,
                         _passage(spans, h.start), d.doc_id, int(exhibit), note,
                         int(cs.first), ts, ts),
                    )  # fmt: skip
                    cs.rows_new += cur.rowcount
                docs_state[key] = [SCAN_VERSION, sha]
            if any_read:
                fil_state[f.accession] = {
                    "form": f.form,
                    "filed": f.filed,
                    "period_end": f.period_end,
                }
        st.update(docs=docs_state, filings=fil_state, version=SCAN_VERSION, at=ts)
        st.setdefault("first_scan_at", ts)
        save_state(engine, norm, st, now)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return cs


def _replace_rows(engine: sqlite3.Connection, accession: str, filename: str) -> int:
    """Before a re-scan: drop the document's rows that nobody answered or reviewed; the
    others are kept (and keep their offsets). Returns the number kept."""
    engine.execute(
        "DELETE FROM gate_text WHERE accession = ? AND filename = ? AND owner_outcome IS NULL "
        "AND item_id IS NULL",
        (accession, filename),
    )
    return engine.execute(
        "SELECT count(*) FROM gate_text WHERE accession = ? AND filename = ?",
        (accession, filename),
    ).fetchone()[0]


def verified(text: str, h: Hit) -> bool:
    return 0 <= h.start < h.end <= len(text) and clean(text[h.start : h.end]) == h.quote


def verify_rows(corpus: sqlite3.Connection, rows: list[sqlite3.Row]) -> tuple[int, int]:
    """(verified, checked): each stored quote against the stored document (D21)."""
    ok = 0
    for r in rows:
        got = corpus.execute(
            "SELECT substr(text, ?, ?) FROM document WHERE accession = ? AND filename = ?",
            (r["start_offset"] + 1, r["end_offset"] - r["start_offset"], r["accession"],
             r["filename"]),
        ).fetchone()  # fmt: skip
        ok += int(bool(got and got[0] is not None and clean(got[0]) == r["quote"]))
    return ok, len(rows)


# --- Reading rows: the current report, effects, gate lines ----------------------------------


def label(klass: str) -> str:
    return CLASSES.get(klass, ("", "", klass))[2]


def effective(r: sqlite3.Row | dict) -> str:
    """The row's effect after the owner's answer (misread → none, treat as fail → fail)."""
    if r["effect"] == "excluded":
        return "excluded"
    if r["owner_outcome"] == "misread":
        return "none"
    if r["owner_outcome"] == "treat_as_fail":
        return "fail"
    return r["effect"]


@dataclass
class Current:
    accessions: set[str]
    report: dict | None  # the latest scanned periodic filing (accession, form, filed, period)
    note: str = ""


def current(engine: sqlite3.Connection, cik: str, as_of: str) -> Current:
    """The current report as of `as_of` (D-M04-96): the latest scanned periodic filing filed
    by then, plus the 6-Ks filed after it; with only 6-Ks, those of the last 400 days."""
    norm = normalize_cik(cik) or cik
    st = load_state(engine, norm) or {}
    fil = st.get("filings", {})
    seen = [(v["filed"], acc, v) for acc, v in fil.items() if v["filed"] <= as_of]
    periodic = sorted((x for x in seen if x[2]["form"] not in FOREIGN_CURRENT), reverse=True)
    sixk = [x for x in seen if x[2]["form"] in FOREIGN_CURRENT]
    if periodic:
        filed, acc, v = periodic[0]
        accs = {acc} | {a for f, a, _ in sixk if f > filed}
        report = {"accession": acc, **v}
    else:
        floor = (date.fromisoformat(as_of[:10]) - timedelta(days=SIX_K_ONLY_DAYS)).isoformat()
        accs = {a for f, a, _ in sixk if f >= floor}
        report = None
    note = ""
    newer = engine.execute(
        "SELECT f.accession, f.form, f.filed FROM filing f JOIN filing_cik c ON c.accession = "
        f"f.accession WHERE c.cik = ? AND f.form IN ({','.join('?' * len(PERIODIC_FORMS))}) "
        "AND f.filed <= ? AND f.filed > ? ORDER BY f.filed DESC LIMIT 1",
        (norm, *sorted(PERIODIC_FORMS), as_of, report["filed"] if report else "0000"),
    ).fetchone()
    if newer is not None and newer["accession"] not in fil:
        note = (
            f"newer {newer['form']} {newer['accession']} (filed {newer['filed']}) has no stored "
            "text; the latest stored report is read"
        )
    return Current(accs, report, note)


def rows_for(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT * FROM gate_text WHERE cik = ? ORDER BY filed DESC, accession, start_offset",
        (normalize_cik(cik) or cik,),
    ).fetchall()


def line(r: sqlite3.Row | dict) -> str:
    q = r["quote"]
    q = q if len(q) <= 220 else q[:217] + "…"
    fam = "going-concern" if r["family"] == "going_concern" else "covenant"
    return (
        f"{fam} text: {label(r['class'])} — {r['form']} filed {r['filed']} "
        f"({r['accession']}): “{q}”"
    )


@dataclass
class TextGate:
    fails: list[tuple[str, Source]] = field(default_factory=list)
    warns: list[tuple[str, Source]] = field(default_factory=list)
    hypotheticals: list[sqlite3.Row] = field(default_factory=list)
    current: Current | None = None
    rows: list[sqlite3.Row] = field(default_factory=list)  # current rows

    def summary(self) -> str:
        if self.current is None or (not self.current.accessions):
            return "no stored periodic text"
        if self.fails:
            return "fail: " + "; ".join(sorted({x.split(" — ")[0] for x, _ in self.fails}))
        if self.warns:
            return "warn: " + "; ".join(sorted({x.split(" — ")[0] for x, _ in self.warns}))
        if self.hypotheticals:
            return "hypothetical wording only (review while runway < 8 q)"
        return "no trigger in the current report"


def gate_lines(engine: sqlite3.Connection, cik: str, as_of: str) -> TextGate:
    """The text findings that act on the gate as of `as_of` (current report only)."""
    norm = normalize_cik(cik) or cik
    tg = TextGate(current=current(engine, norm, as_of))
    if not tg.current.accessions:
        return tg
    for r in rows_for(engine, norm):
        if r["accession"] not in tg.current.accessions:
            continue
        tg.rows.append(r)
        eff = effective(r)
        src = Source(r["accession"], r["filed"], "A", f"{r['form']} text ({r['class']})")
        if eff == "fail":
            tg.fails.append((line(r), src))
        elif eff == "warn":
            tg.warns.append((line(r), src))
        elif eff == "hypothetical":
            tg.hypotheticals.append(r)
    return tg


def runway_reviews(runway: float | None, tier: str | None, scope: str) -> tuple[bool, str]:
    """Is hypothetical wording reviewed? (D-M04-34: only while the runway is below 8
    quarters; an unknown runway on a tested gate is reviewed too, the conservative reading)."""
    if tier == "self_funding":
        return False, "self-funding"
    if runway is not None:
        return runway < HYPO_RUNWAY_Q, f"runway {runway:.1f} q"
    if scope in ("full", "liquidity_only"):
        return True, "runway unknown"
    return False, f"runway not tested ({scope})"


def effect_text(r: sqlite3.Row, is_current: bool, review_hypo: bool) -> str:
    eff = effective(r)
    owner = f" (owner: {r['owner_outcome'].replace('_', ' ')})" if r["owner_outcome"] else ""
    if eff == "excluded":
        return "excluded" + owner
    if not is_current:
        return {"fail": "history (fail class)", "warn": "history (warn class)"}.get(
            eff, "history"
        ) + owner
    if eff == "fail":
        return "fail → m04_gate_fail" + owner
    if eff == "warn":
        return f"warn + {KIND_OF_FAMILY[r['family']]} review" + owner
    if eff == "hypothetical":
        return ("review (m04_gc_text)" if review_hypo else "information") + owner
    return "no trigger" + owner


@dataclass
class ViewRow:
    filed: str
    form: str
    period: str
    klass: str
    label: str
    effect: str
    quote: str
    title: str
    item_id: int | None
    strong: bool


def view_rows(
    engine: sqlite3.Connection, cik: str, as_of: str, review_hypo: bool, limit: int = 40
) -> tuple[list[ViewRow], int, Current]:
    """Rows for the Gate text block: current-report rows first, then history (newest first)."""
    norm = normalize_cik(cik) or cik
    cur = current(engine, norm, as_of)
    rows = sorted(rows_for(engine, norm), key=lambda r: r["filed"], reverse=True)
    # current report first, most severe first; newest first within (stable sort)
    rows.sort(key=lambda r: (r["accession"] not in cur.accessions, -SEVERITY[effective(r)]))
    out = []
    for r in rows[:limit]:
        is_cur = r["accession"] in cur.accessions
        out.append(
            ViewRow(
                r["filed"],
                r["form"] + (f" · {r['doc_type']}" if r["exhibit"] else ""),
                r["period_end"] or "—",
                r["class"],
                label(r["class"]),
                effect_text(r, is_cur, review_hypo),
                r["quote"],
                f"passage {r['passage_id'] or '—'} · {r['accession']}/{r['filename']} · "
                f"offset {r['start_offset']}" + (f" · {r['note']}" if r["note"] else ""),
                r["item_id"],
                is_cur and effective(r) in ("fail", "warn"),
            )
        )
    return out, max(0, len(rows) - limit), cur


# --- Owner answers ----------------------------------------------------------------------------


def apply_action(
    engine: sqlite3.Connection, item_id: int, kind: str, action: str, payload: dict,
    cik: str | None, now: datetime, note: str = "",
) -> str:  # fmt: skip
    """The owner's reading of a text finding (inside `review.m04_action`'s transaction):
    `noted` keeps the class; `treat_as_fail` makes it a fail trigger while its report is
    current; `misread` removes its effect (the class is wrong). Stored on every row of the
    item's report and class. A gate-fail text alert takes `noted` and `inputs_wrong`
    (= misread)."""
    from engine.financials.queue import QueueError

    acc, klass = payload.get("accession"), payload.get("class")
    if not acc or not klass:
        raise QueueError("This item names no text finding.")
    outcome = {"inputs_wrong": "misread"}.get(action, action)
    if outcome not in OWNER_OUTCOMES:
        raise QueueError(f"'{action}' is not an action for {kind}.")
    if outcome == "misread" and not note.strip():
        raise QueueError("Say what the code misread (note).")
    cur = engine.execute(
        "UPDATE gate_text SET owner_outcome = ?, owner_at = ? WHERE accession = ? AND class = ? "
        "AND cik = ?",
        (outcome, iso(now), acc, klass, normalize_cik(cik or "") or cik or ""),
    )
    if not cur.rowcount:
        cur = engine.execute(
            "UPDATE gate_text SET owner_outcome = ?, owner_at = ? WHERE item_id = ?",
            (outcome, iso(now), item_id),
        )
    if not cur.rowcount:
        raise QueueError("The sentence behind this item is no longer stored.")
    return {
        "noted": "noted (class kept; acts on the gate while its report is current)",
        "treat_as_fail": "treat_as_fail: a fail trigger while its report is current",
        "misread": f"misread: {note.strip()} (no effect on the gate from now on)",
    }[outcome]
