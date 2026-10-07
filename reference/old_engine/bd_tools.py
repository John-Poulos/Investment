"""
bd_tools.py — BD&L Intelligence Data Sources
Three new tool modules for the pharma CI runner:

  Step 11 → deal_tracker        (SEC EDGAR 8-K + EFTS full-text search)
  Step 12 → conference_calendar (BioMedCentral Conference Alerts + hardcoded authoritative calendar)
  Step 13 → biosimilar_watch    (FDA Drugs@FDA ANDA/BLA submissions + Orange/Purple Book)

All functions are free, no API key required.
Rate limits and User-Agent handling follow the same pattern as sec_edgar.py.
"""

import os
import re
import time
import json
import html as _html
import requests
import threading
from datetime import datetime, timedelta, date
from typing import Optional

from infra.engine_errors import SourceFetchFailed
from tools.deal_extraction import extract_deal_economics
from utils.text import sanitize_source_text, normalize_company_key
from tools.deal_funnel import (
    DealFunnel, STAGE_DEDUPE, STAGE_FETCH, STAGE_CLASSIFY, STAGE_EMIT,
    REASON_DUPLICATE, REASON_CAP_DEFERRED, REASON_CONFIRMED_NON_DEAL, REASON_NON_BD,
    REASON_NO_DEAL_LANGUAGE, REASON_6K_HOUSEKEEPING,)

# ── Console verbosity ────────────────────────────────────────────────────────
# The per-query EFTS diagnostics and the per-filing [DIAG] blocks are invaluable
# when debugging retrieval, and overwhelming otherwise: a single run emits
# hundreds of lines and pushes the coverage funnel out of scrollback. They are
# now OFF by default and re-enabled with BD_VERBOSE=1. Errors, warnings, drops,
# and the funnel table always print. Generic: no drug/profile knowledge.
BD_VERBOSE = os.getenv("BD_VERBOSE", "0").lower() in ("1", "true", "yes")

# Where the coverage funnel is persisted so it survives console scrollback.
BD_FUNNEL_LOG_DIR = os.getenv("BD_FUNNEL_LOG_DIR", "logs")


def _vprint(*args, **kwargs) -> None:
    """Verbose-only print. Silent unless BD_VERBOSE=1."""
    if BD_VERBOSE:
        print(*args, **kwargs)


def _persist_funnel(funnel: "DealFunnel") -> Optional[str]:
    """
    Write the coverage funnel to disk (text + JSON) so it can be read after the
    run regardless of console scrollback. Never raises: instrumentation must not
    be able to break the pipeline it measures.
    """
    try:
        os.makedirs(BD_FUNNEL_LOG_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        txt = os.path.join(BD_FUNNEL_LOG_DIR, f"deal_funnel_{stamp}.txt")
        js  = os.path.join(BD_FUNNEL_LOG_DIR, f"deal_funnel_{stamp}.json")
        with open(txt, "w", encoding="utf-8") as fh:
            fh.write(funnel.render() + "\n")
        with open(js, "w", encoding="utf-8") as fh:
            json.dump(funnel.to_meta(), fh, indent=2)
        # Stable "latest" pointers for scripted checks.
        for src, dst in ((txt, "deal_funnel_latest.txt"), (js, "deal_funnel_latest.json")):
            latest = os.path.join(BD_FUNNEL_LOG_DIR, dst)
            with open(src, encoding="utf-8") as a, open(latest, "w", encoding="utf-8") as b:
                b.write(a.read())
        return txt
    except Exception as e:                      # pragma: no cover - best effort
        print(f"  [FUNNEL] could not persist funnel log: {e}")
        return None
from tools.deal_parties import extract_deal_parties
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── Shared HTTP config ──────────────────────────────────────────────────────

USER_AGENT   = os.getenv("SEC_USER_AGENT", "PharmaAgent contact@pharmaagent.com")
HEADERS_SEC  = {"User-Agent": USER_AGENT}
HEADERS_JSON = {"User-Agent": USER_AGENT, "Accept": "application/json"}
REQUEST_DELAY = 0.35   # SEC EFTS: conservative baseline between requests.
                        # At max_workers=3, effective rate is ~3 req/sec — well under
                        # the 10 req/sec limit and avoids the 500s caused by burst load.

_sec_rate_lock = threading.Semaphore(3)  # max 3 concurrent EFTS requests.
                                          # 8 workers caused cascade 500s; 3 keeps
                                          # burst load low enough for EFTS to handle.


class DealTrackerResult:
    """
    Return type for get_deal_tracker().
    Behaves like a list (iterable, len, index) for backwards compatibility,
    but also exposes a .meta dict and .deals list separately.

    Runner usage:
        result = get_deal_tracker(...)
        deals  = result.deals
        scope  = result.meta["search_scope_days"]

    Backwards-compatible usage (treats result as plain list):
        for d in result: ...
        len(result)
    """
    def __init__(self, deals: list, meta: dict):
        self.deals = deals
        self.meta  = meta

    # ── list-like interface ──────────────────────────────────────────────────
    def __iter__(self):         return iter(self.deals)
    def __len__(self):          return len(self.deals)
    def __getitem__(self, idx): return self.deals[idx]
    def __bool__(self):         return bool(self.deals)

EFTS_URL         = "https://efts.sec.gov/LATEST/search-index"
# EFTS_URL_ALT is the same endpoint — kept for reference during debugging
# Confirmed working format: ?q=%22term%22+%22phrase%22&forms=8-K&dateRange=custom&startdt=...&enddt=...
ARCHIVES_URL     = "https://www.sec.gov/Archives/edgar/data"
SUBMISSIONS_URL  = "https://data.sec.gov/submissions"
FDA_DRUGSFDA_URL = "https://api.fda.gov/drug/drugsfda.json"
FDA_NDC_URL      = "https://api.fda.gov/drug/ndc.json"
ORANGE_BOOK_URL  = "https://www.accessdata.fda.gov/cder/ob/results_product.cfm"

# ─── Shared helpers ──────────────────────────────────────────────────────────

def _get_json(url: str, params: dict = None,
              headers: dict = None, max_retries: int = 3) -> dict:
    """Robust GET→JSON with exponential backoff on 5xx."""
    import random
    hdrs = headers or HEADERS_SEC
    for attempt in range(max_retries):
        time.sleep(REQUEST_DELAY)
        try:
            resp = requests.get(url, params=params, headers=hdrs, timeout=20)
            if resp.status_code >= 500:
                wait = (2 ** attempt) + random.uniform(0, 0.5)
                print(f"  {url[:60]} HTTP {resp.status_code} — retry {attempt+1}/{max_retries} in {wait:.1f}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            print(f"  HTTP error: {e}")
            return {}
        except (requests.RequestException, ValueError) as e:
            if attempt < max_retries - 1:
                wait = (2 ** attempt) + random.uniform(0, 0.5)
                print(f"  Error — retry in {wait:.1f}s: {e}")
                time.sleep(wait)
            else:
                print(f"  Gave up after {max_retries} attempts: {e}")
                return {}
    return {}


def _today_str() -> str:
    return date.today().isoformat()


# ─── Week-over-week deal tracking ────────────────────────────────────────────
# Persists the set of deal accessions seen in each run to a local JSON file so
# the next run can detect deals that disappeared (silently dropped due to EFTS
# query non-determinism, transient 500s, or dedup ordering) vs deals that are
# genuinely new.
#
# State file location: configurable via DEAL_TRACKER_STATE_PATH env var,
# defaults to a local file next to this module. In a containerized/ephemeral
# runner environment, set this env var to a persistent volume path or the
# diff will simply report "no prior state" every run (harmless — diff is
# best-effort, not required for the report to function).

_STATE_PATH = os.getenv("DEAL_TRACKER_STATE_PATH", "deal_tracker_state.json")


def _load_prior_deal_state() -> dict:
    """Return {"run_date": str, "accessions": {accession: company_name}} or {}."""
    try:
        with open(_STATE_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_deal_state(results: list[dict]) -> None:
    """Persist this run's deal accessions for next run's diff."""
    state = {
        "run_date": _today_str(),
        "accessions": {
            d["accession"]: d.get("company", "")
            for d in results
            if d.get("accession")
        },
    }
    try:
        with open(_STATE_PATH, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        print(f"  DealTracker: could not save state file ({e}) — diff will be unavailable next run")


def _diff_against_prior_run(results: list[dict], days_back: int) -> list[dict]:
    """
    Compare this run's accessions against the prior run's saved state.

    Returns a list of "vanished" deal stubs — accessions present in the prior
    run but missing from this run, AND whose filing date would still fall
    within the current search window (i.e. they should still be findable but
    aren't, suggesting a query/dedup issue rather than the deal aging out).

    Each vanished entry has minimal fields so the runner/LLM can surface a
    "previously flagged, now missing — verify" note without re-fetching.
    """
    prior = _load_prior_deal_state()
    if not prior or not prior.get("accessions"):
        return []  # no prior state — first run or state file unavailable

    prior_accessions = set(prior["accessions"].keys())
    current_accessions = {d["accession"] for d in results if d.get("accession")}

    vanished_acc = prior_accessions - current_accessions
    if not vanished_acc:
        return []

    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    vanished = []
    for acc in vanished_acc:
        company = prior["accessions"][acc]
        # Best-effort: accession numbers encode filing year (first 10 digits
        # are CIK, next 2 are year) — we don't have the exact filing date here
        # since prior state only stores accession→company. Surface all
        # vanished accessions; the runner can decide relevance based on the
        # prior run_date being recent.
        vanished.append({
            "accession":   acc,
            "company":     company,
            "prior_run_date": prior.get("run_date", "unknown"),
            "note": (
                f"This deal appeared in the {prior.get('run_date','prior')} run "
                f"but is missing from this run's results. If it should still be "
                f"within the {days_back}-day window, this may indicate a transient "
                f"EFTS query failure or deduplication issue — verify manually."
            ),
        })

    if vanished:
        print(f"  DealTracker: {len(vanished)} deal(s) from prior run vanished — "
              f"{[v['company'] for v in vanished]}")

    return vanished


def _days_from_now(iso_date_str: str) -> Optional[int]:
    try:
        target = datetime.strptime(iso_date_str[:10], "%Y-%m-%d").date()
        return (target - date.today()).days
    except (ValueError, TypeError):
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 11 — DEAL TRACKER
# Sources:
#   Primary:   SEC EDGAR EFTS full-text search (8-K filings)
#              https://efts.sec.gov/LATEST/search-index
#   Secondary: SEC EDGAR submissions API (company-level 8-K metadata)
#              https://data.sec.gov/submissions/CIK{cik}.json
#
# Why 8-K?  Item 1.01 "Entry into a Material Definitive Agreement" is the
# mandatory disclosure event for M&A, licensing, option, and collaboration
# deals.  Full-text search on deal-specific phrase clusters surfaces these
# within minutes of filing.  No third-party data vendor required.
#
# Free?  Yes — SEC EDGAR is public.  Rate limit: 10 req/sec (enforced by
# REQUEST_DELAY).  No API key.  Requires descriptive User-Agent header.
# ═══════════════════════════════════════════════════════════════════════════════

# Phrase clusters that together characterize a BD deal disclosure in an 8-K.
# We run multiple targeted queries and deduplicate by accession number so that
# a single filing is never counted twice even if it matches several clusters.

# Phrase clusters for EFTS focused search.
# KEY DESIGN PRINCIPLE: each entry is a SINGLE quoted phrase.
# Combining multiple quoted phrases in one EFTS query (e.g. "license agreement" "milestone")
# requires BOTH to appear verbatim in the same document — this kills recall.
# Instead we run one query per anchor and deduplicate by accession number.
# The confirmation step (DEAL_CONFIRM_PATTERNS) handles precision.

DEAL_QUERY_CLUSTERS = [
    # Tier 1 — highest-signal deal anchors (single phrase each)
    '"license agreement"',
    '"collaboration agreement"',
    '"merger agreement"',
    '"definitive agreement"',
    '"option agreement"',
    '"strategic collaboration"',
    '"exclusive license"',
    '"asset purchase agreement"',
    '"co-development agreement"',
    '"development and commercialization"',
    # Tier 2 — deal payment/structure anchors
    '"milestone payment"',
    '"upfront payment"',
    '"royalty agreement"',
    '"sublicense agreement"',
    '"co-promote"',
    '"exclusive worldwide license"',
    # Tier 3 — supply/clinical-trial collaboration anchors. Pharma BD deals
    # involving large companies (e.g. Novo Nordisk supplying drug product to
    # a smaller biotech for a combination trial) are often filed as "Clinical
    # Supply Agreement" or "Supply and Collaboration Agreement" rather than
    # the generic clusters above — without these, such deals are only caught
    # by the broad single-word fallback, which is non-deterministic under
    # EFTS retry/timeout conditions.
    '"supply agreement"',
    '"clinical supply agreement"',
    '"manufacturing and supply agreement"',
]

# Broad single-word fallback — used in the per-term broad sweep only.
# These are high-recall but lower precision; the confirm step filters junk.
DEAL_BROAD_CLUSTERS = [
    '"license"',
    '"acquisition"',
    '"merger"',
    '"collaboration"',
    '"partnership"',
]

# # Alias map: when focus_terms contains a key, also search its aliases.
# # This ensures brand names and mechanism names are searched alongside INNs.
# FOCUS_TERM_ALIASES: dict[str, list[str]] = {
#     "semaglutide":   ["Ozempic", "Wegovy", "Rybelsus"],
#     "tirzepatide":   ["Mounjaro", "Zepbound"],
#     "liraglutide":   ["Victoza", "Saxenda"],
#     "orforglipron":  ["orforglipron"],           # oral GLP-1 — no brand yet
#     "retatrutide":   ["retatrutide"],
#     "danuglipron":   ["danuglipron"],
#     "GLP-1":         ["GLP-1", "glucagon-like peptide", "GLP1"],
#     "GIP":           ["GIP", "glucose-dependent insulinotropic"],
#     "obesity":       ["obesity", "weight loss", "anti-obesity"],
# }

# 8-K deal confirmation — any one of these in the fetched text confirms deal filing.
# Kept broad: we'd rather over-include and let the LLM filter than under-include.
DEAL_CONFIRM_PATTERNS = [
    r"item\s*1[\.\u00b7]?\s*01",                         # Item 1.01 header
    r"entry into.*(?:material|definitive)",              # standard 8-K opener
    r"license\s+agreement",
    r"collaboration\s+agreement",
    r"merger\s+agreement",
    r"acquisition\s+agreement",
    r"option\s+agreement",
    r"definitive\s+agreement",
    r"strategic\s+(?:alliance|collaboration|partnership)",
    r"co\s*-\s*develop",
    r"co\s*-\s*promot",
    r"sublicense",
    r"exclusive\s+license",
    r"material\s+definitive",
    r"(?:first|second|third)\s+amendment.*(?:license|collaboration|agreement)",
    r"upfront\s+(?:payment|fee)",
    r"milestone\s+payment",
    r"royalt",
    r"worldwide\s+(?:exclusive\s+)?(?:license|rights)",
    r"commercialization\s+rights",
    r"asset\s+purchase\s+agreement",
]

# Dollar-figure extraction — looks for values like $1.2 billion, $500 million, €300M
DOLLAR_RE = re.compile(
    r"\$\s*[\d,]+(?:\.\d+)?\s*(?:billion|million|B|M)\b"
    r"|(?:USD|EUR|GBP)\s*[\d,]+(?:\.\d+)?\s*(?:billion|million|B|M)\b",
    re.IGNORECASE,
)

# Royalty / revenue-interest FINANCING: structured as a "purchase agreement",
# but no company or asset changes hands — must be caught before the M&A block,
# whose "purchase price" / "sale and purchase" signals it would otherwise trip.
_ROYALTY_FIN_SIGNALS = (
    "royalty note purchase", "royalty purchase agreement", "royalty financing",
    "revenue interest financing", "revenue interest purchase", "synthetic royalty",
    "royalty interest",
)
# License/collaboration context. When present WITHOUT a strong entity-acquisition
# signal, the weak M&A verbs ("acquire", "purchase price") describe rights, not a
# company purchase — divert to the licence branches below.
_LICENSE_CONTEXT_SIGNALS = (
    "license agreement", "licensing agreement", "exclusive license", "worldwide license",
    "in-license", "in-licensed", "out-license", "sublicense", "collaboration agreement",
    "license and collaboration", "commercialization rights", "worldwide rights",
    "ex-china rights", "acquire rights", "acquiring rights", "rights to develop",
    "right to license",
)
# Unambiguous entity acquisition — these are NEVER a licence, so they override the
# divert guard and stay M&A.
_STRONG_MA_SIGNALS = (
    "merger", "tender offer", "wholly owned subsidiary", "stock purchase agreement",
    "acquire all", "all outstanding shares", "agreement and plan of merger",
)

# Deal type classifier
def _classify_deal(text: str, full_text: str = "") -> str:
    """
    Classify a deal from extracted filing text.

    Args:
        text:      primary excerpt used for classification (e.g. item_101[:3000])
        full_text: optional larger excerpt (e.g. rich_text[:8000]) used ONLY to
                   disambiguate "Agreement Termination" vs "M&A" — an M&A filing
                   (sale/purchase deed, tender offer, merger) commonly contains
                   boilerplate "termination of the Agreement" clauses that would
                   otherwise misfire the termination branch if those clauses
                   happen to fall within `text` but the M&A language ("merger",
                   "acquisition", "purchase price", "tender offer") falls outside
                   the truncated `text` window. Checking full_text for M&A
                   signals before committing to "Agreement Termination" prevents
                   that misclassification.

    IMPORTANT — read order matters (most specific first):
      1. Non-BD financial instruments must be caught BEFORE generic "license" match
         to prevent misclassification of loan agreements, ATM facilities, etc.
      2. Amendment check before base type — an amended license is "License Amendment",
         not just "Licensing".
      3. M&A check is widened to include "purchase price", "sale and purchase",
         and "shares tendered" — acquisitions are often described without the
         literal word "acquisition" in the indexed excerpt.
    """
    text_l = text.lower()
    full_l = (full_text or text).lower()

    # Royalty / revenue-interest financing — precedes every other branch, since
    # it contains both "purchase" (→ would hit M&A) and "royalt" (→ would hit
    # Royalty/Out-License) but is neither.
    if any(s in full_l for s in _ROYALTY_FIN_SIGNALS):
        return "Royalty Financing"

    # ── Explicit non-BD filings — caller should filter these out ──────────────
    # Loan / credit / debt instruments
    if any(t in text_l for t in ("loan agreement", "credit agreement", "credit facility",
                                  "term loan", "revolving credit", "promissory note",
                                  "security agreement", "borrowing capacity")):
        if "license" not in text_l and "collaboration" not in text_l:
            return "Non-BD: Debt/Financing"

    # Equity / capital markets
    if any(t in text_l for t in ("at-the-market", "atm offering", "sales agreement",
                                  "equity distribution", "aggregate offering")):
        if "license" not in text_l and "collaboration" not in text_l:
            return "Non-BD: Capital Markets"

    # Employment / executive compensation
    # Position-based check: classify as Non-BD: Employment only if an
    # employment signal appears EARLIER in the text than any BD deal signal.
    # A header-window approach (checking only the first N chars) failed
    # because employment-agreement 8-Ks routinely mention an unrelated
    # "License Agreement" (e.g. background university IP) within the same
    # short window. Position-ordering is more robust: the actual SUBJECT of
    # an Item 1.01 filing is described first, so whichever signal type
    # (employment vs. BD deal) is mentioned first reflects the true subject.
    EMPLOYMENT_SIGNALS = ("employment agreement", "base salary", "severance",
                          "chief executive officer", "chief financial officer",
                          "chief operating officer", "chief business officer",
                          "chief medical officer", "equity incentive",
                          "stock option grant", "offer letter")
    BD_DEAL_SIGNALS = ("license agreement", "collaboration agreement",
                       "merger", "acquisition", "asset purchase agreement",
                       "royalty agreement", "exclusive license",
                       "strategic collaboration", "tender offer")

    def _first_pos(signals):
        positions = [text_l.find(s) for s in signals]
        positions = [p for p in positions if p != -1]
        return min(positions) if positions else None

    emp_pos = _first_pos(EMPLOYMENT_SIGNALS)
    bd_pos  = _first_pos(BD_DEAL_SIGNALS)

    if emp_pos is not None and (bd_pos is None or emp_pos < bd_pos):
        return "Non-BD: Employment"

    # ── M&A signals — widened beyond literal "merger"/"acquisition" ───────────
    # Checked against full_l so M&A language outside the primary excerpt window
    # is still caught (this is the fix for the Prestige/LaCorium misclassification,
    # where "termination" appeared in the first 3000 chars but "purchase price" /
    # "Sale and Purchase Deed" appeared later in the document).
    M_AND_A_SIGNALS = (
        "merger", "acquisition", "tender offer",
        "purchase price", "sale and purchase", "shares tendered",
        "wholly owned subsidiary", "stock purchase agreement",
    )
    has_ma_signal = any(t in full_l for t in M_AND_A_SIGNALS)

    # Divert weak M&A verbs when licence context is present but no STRONG
    # entity-acquisition signal is — "acquire rights", "purchase price" inside a
    # licence, "Royalty Note Purchase" (already handled above) are not M&A.
    _license_ctx = any(s in full_l for s in _LICENSE_CONTEXT_SIGNALS)
    _strong_ma   = any(s in full_l for s in _STRONG_MA_SIGNALS)
    _divert      = _license_ctx and not _strong_ma

    if any(t in text_l for t in ("merger", "acquisition", "acquire", "tender offer")):
        if "asset purchase" in text_l:
            return "Asset Purchase"
        if not _divert:
            return "M&A"
        # else: fall through to the licence/royalty branches below

    if has_ma_signal:
        if "asset purchase" in text_l:
            return "Asset Purchase"
        if not _divert:
            return "M&A"
        # else: fall through

    # Amendment check MUST come before exclusive/license checks
    # Catches both "amendment to" and "amended [agreement]"
    if any(t in text_l for t in ("amendment", "amended")) and any(t in text_l for t in
                                      ("license", "collaboration", "agreement")):
        return "License Amendment"

    # Agreement Termination — only fires if NO M&A signal exists anywhere in
    # full_text. A genuine termination 8-K (e.g. "Termination of License
    # Agreement") will not contain merger/purchase/tender language at all.
    if "termination" in text_l and "agreement" in text_l and not has_ma_signal:
        return "Agreement Termination"

    if "option agreement" in text_l or "right to license" in text_l:
        return "Option / Right-to-License"

    if any(t in text_l for t in ("co-develop", "co-promotion", "co-commerciali",
                                  "strategic collaboration", "collaboration agreement",
                                  "joint development", "collaboration with",
                                  "collaborate with")):
        return "Collaboration / Co-Development"

    if "asset purchase" in text_l:
        return "Asset Purchase"

    # Royalty: check for royalty language BEFORE plain "license" fallback
    if "royalt" in text_l:
        return "Royalty / Out-License"

    if "exclusive license" in text_l or "worldwide license" in text_l:
        return "Exclusive License"

    if "license" in text_l:
        return "Licensing"

    return "Other BD Transaction"

# _sec_rate_lock is defined at module level above (Semaphore(3))

def _fetch_deal_8ks(
    query: str,
    days_back: int,
    max_results: int,
    sic_codes: Optional[list[str]] = None,
) -> list[dict]:
    """
    Run one EFTS full-text query against 8-K filings and return raw hits.

    CONFIRMED EFTS behavior (from working queries in production):
    - Endpoint: https://efts.sec.gov/LATEST/search-index
    - Params passed via standard urllib.parse.urlencode (spaces → '+', quotes → %22)
    - Quoted phrases work: "license agreement" → %22license+agreement%22
    - OR groups with parentheses DO NOT reliably work — EFTS rejects or ignores them
    - Solution: pass one term/phrase per query, run multiple queries, deduplicate
    - SIC filtering done post-fetch (no server-side SIC param)
    """

    start_dt = (date.today() - timedelta(days=days_back)).isoformat()
    end_dt   = _today_str()

    # CONFIRMED from echoed query JSON analysis:
    # - forms=8-K               → correct root_forms filter, includes 8-K/A ✓
    # - dateRange+startdt+enddt → applied as range filter on file_date ✓
    # - q param: plain quoted phrases ONLY.
    #   Do NOT add "AND file_date:[...]" to q — EFTS treats everything in q as
    #   match_phrase against doc_text, so field syntax becomes literal phrase
    #   searches ("AND", "file_date:[2026-04-10", "TO", "2026-06-09]") that
    #   require those exact strings to appear in the document, killing all recall.
    import urllib.parse
    url = f"{EFTS_URL}?" + urllib.parse.urlencode({
        "q":         query,
        "forms":     "8-K",
        "dateRange": "custom",
        "startdt":   start_dt,
        "enddt":     end_dt,
    })

    _diag = getattr(_fetch_deal_8ks, '_diag_count', 0)
    if _diag == 0:
        _vprint(f"  [EFTS DIAG] First URL: {url}")
    with _sec_rate_lock:
        time.sleep(REQUEST_DELAY)
        import random
        resp = None
        for attempt in range(3):
            try:
                resp = requests.get(url, headers=HEADERS_SEC, timeout=20)
                if resp.status_code >= 500:
                    # Longer backoff for 500s — EFTS is under load, not a transient blip.
                    # 2s, 5s, 11s — gives the server time to recover between retries.
                    wait = (2 ** (attempt + 1)) + random.uniform(0.5, 1.5)
                    print(f"  {EFTS_URL} HTTP {resp.status_code} — retry {attempt+1}/3 in {wait:.1f}s")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
            except (requests.RequestException, ValueError) as e:
                if attempt < 2:
                    wait = (2 ** attempt) + random.uniform(0, 0.5)
                    time.sleep(wait)
                else:
                    return []
        else:
            return []

        # ── Diagnostic: print raw response on first call ──────────────────────────
        if _diag == 0:
            _fetch_deal_8ks._diag_count = 1
            total_raw  = data.get("hits", {}).get("total", "?")
            echoed_q   = data.get("query", {}).get("query", {})
            filters    = echoed_q.get("bool", {}).get("filter", [])
            must       = echoed_q.get("bool", {}).get("must", [])
            _vprint(f"  [EFTS DIAG] status={resp.status_code}  total={total_raw}")
            _vprint(f"  [EFTS DIAG] echoed must clauses: {[list(m.values())[0] for m in must]}")
            _vprint(f"  [EFTS DIAG] echoed filter clauses ({len(filters)}): {filters}")
            date_in_filter = any('range' in str(f) or 'file_date' in str(f) for f in filters)
            date_in_must   = any('file_date' in str(m) for m in must)
            _vprint(f"  [EFTS DIAG] date applied in filter={date_in_filter}  in must={date_in_must}")

        hits = data.get("hits", {}).get("hits", [])
        total = data.get("hits", {}).get("total", {})
        total_n = total.get("value", 0) if isinstance(total, dict) else int(total or 0)

        if total_n:
            _vprint(f"         → {total_n} total hits, processing up to {max_results}")
            if _diag > 0:  # print full response on first actual hit
                _vprint(f"  [EFTS HIT] query={query[:60]}  hit_sample={str(hits[0])[:200]}")

        results = []
        for hit in hits[:max_results]:
            src       = hit.get("_source", {})
            sics      = src.get("sics", [])

            # Post-fetch SIC filter (pharma = 2830-2836, biotech = 8731-8734)
            if sic_codes and sics:
                if not any(s in sic_codes for s in sics):
                    continue

            names     = src.get("display_names", [])
            accession = src.get("adsh", "")
            ciks      = src.get("ciks", ["0"])
            cik_num   = str(ciks[0]).lstrip("0") if ciks else "0"
            acc_clean = accession.replace("-", "")

            results.append({
                "entity":       names[0].split("(")[0].strip() if names else "Unknown",
                "file_date":    src.get("file_date", ""),
                "accession":    accession,
                "description":  src.get("file_description", ""),
                "sic_codes":    sics,
                "filing_index": f"{ARCHIVES_URL}/{cik_num}/{acc_clean}/{accession}-index.htm",
                "cik":          str(ciks[0]) if ciks else "",
            })

        return results

def _fetch_deal_8ks_batch(queries: list[str], days_back: int, max_results: int,
                          sic_filter: Optional[list[str]] = None, max_workers: int = 3) -> list[dict]:
    """
    Run multiple EFTS queries with bounded concurrency.

    max_workers=3 (default) matches _sec_rate_lock Semaphore(3). Raising this
    above 3 without also raising the semaphore causes threads to queue behind
    the lock but still burst when the semaphore releases, which is what was
    causing the cascade of HTTP 500s from EFTS. Keep both values in sync.
    """
    import random
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_fetch_deal_8ks, q, days_back, max_results, sic_filter): q
            for q in queries
        }
        for future in as_completed(futures):
            try:
                results.extend(future.result())
            except Exception as e:
                print(f"  Batch query failed: {e}")
            # Small jitter between completions to prevent burst on rapid futures
            time.sleep(random.uniform(0.05, 0.15))
    return results

# Cached CIK lookup — populated once per process from SEC company_tickers.json
_CIK_CACHE: dict[str, str] = {}


# ── Foreign-issuer 6-K housekeeping filter ───────────────────────────────────
# Foreign private issuers (AstraZeneca, Roche, Sanofi, Novartis) file MANY 6-Ks
# per window — most are routine UK/EU regulatory notices, not deals. Left
# unfiltered they flood the fetch budget (a single issuer's ~20 6-Ks can exhaust
# the submissions cap and DEFER a real deal 6-K, which is then never fetched).
# These subjects are purely administrative and NEVER carry a BD deal, so they can
# be dropped early. IMPORTANT: earnings/interim-results 6-Ks are deliberately NOT
# listed — a foreign issuer can disclose a deal inside a quarterly report's
# "subsequent events" note, so those must still be read/classified. Generic
# regulatory vocabulary → lives in the engine.
_HOUSEKEEPING_6K_RE = re.compile(
    r"repurchase of (?:ordinary )?shares|share repurchase|share buy[\s-]?back|"
    r"buy[\s-]?back program|transaction in own shares|"
    r"person[s]? discharging managerial responsibilit|\bPDMR\b|"
    r"manager[s'’]+ transactions|director/pdmr shareholding|directorate change|"
    r"total voting rights|voting rights and capital|transparency directive|"
    r"notification of major (?:holdings|interest)|holding\(s\) in company|\bTR-1\b|"
    r"block[\s-]?listing|"
    r"form 8\.3|rule 8\.3|opening position disclosure|dealing disclosure|"
    r"net asset value|grant of (?:options|awards)|vesting of|exercise of options|"
    r"admission of shares|result of (?:agm|annual general meeting)|"
    r"notice of (?:agm|annual general meeting)",
    re.IGNORECASE,
)


def _is_housekeeping_6k(text: str) -> bool:
    """True if a 6-K's subject/opening text is a purely administrative notice
    (share repurchase, PDMR dealing, voting-rights, block listing, etc.) that can
    never be a BD deal. Used to drop foreign-issuer 6-K noise before it consumes
    the fetch budget. Deliberately does NOT match earnings/results, which can
    carry deal news in subsequent-events notes."""
    return bool(_HOUSEKEEPING_6K_RE.search(text or ""))


def _resolve_ticker_ciks(tickers: list[str],
                         name_hints: Optional[dict[str, str]] = None) -> dict[str, str]:
    """
    Resolve a list of exchange tickers to zero-padded 10-digit SEC CIK strings.

    PRIMARY source (unchanged, fast, free, ~10,000 exchange-listed companies):
        https://www.sec.gov/files/company_tickers.json

    FALLBACK CHAIN (fires ONLY for tickers the primary map misses — typically
    foreign/OTC ADRs like RHHBY that are absent from the exchange-listed file):
        1. company_tickers_exchange.json — a richer SEC file (adds an exchange
           column and some tickers the primary file omits).
        2. EDGAR browse-edgar atom name-search (reused from tools.sec_edgar) keyed
           on the caller-supplied company-name hint (e.g. RHHBY -> "Roche"). The
           bare ticker rarely resolves a foreign ADR, so the NAME hint is what
           actually surfaces the CIK; without a hint this step is skipped.

    The fallback is strictly additive: the primary path is untouched, fallbacks
    fire only on a miss, and results are cached so the cost is paid once. Keeping
    the drug/company-specific hint in the profile (name_hints, sourced from
    profile["competitor_company_names"]) keeps this engine generic.

    NOTE: resolving a foreign issuer's CIK is necessary but not sufficient for
    coverage — foreign private issuers file 6-K (not 8-K), so the submissions
    enumeration must also accept 6-K for their deals to surface. See the form
    filter in get_deal_tracker().

    Returns:
        Dict mapping UPPER-CASE ticker -> zero-padded CIK string e.g. "0000072971"
        Missing tickers are absent from the dict (caller should skip them).
    """
    global _CIK_CACHE
    name_hints = {k.upper(): v for k, v in (name_hints or {}).items()}
    upper_tickers = {t.upper() for t in tickers}

    # Return from cache if all tickers already resolved
    if upper_tickers.issubset(_CIK_CACHE.keys()):
        return {t: _CIK_CACHE[t] for t in upper_tickers if t in _CIK_CACHE}

    print("  Fetching SEC ticker→CIK index...")
    data = _get_json(
        "https://www.sec.gov/files/company_tickers.json",
        headers=HEADERS_SEC,
    )
    if data:
        # Response format: {"0": {"cik_str": 72971, "ticker": "NVO", "title": "..."}, ...}
        for entry in data.values():
            tkr = str(entry.get("ticker", "")).upper()
            cik = str(entry.get("cik_str", "")).zfill(10)
            _CIK_CACHE[tkr] = cik
    else:
        print("  WARNING: Could not fetch primary ticker index — will rely on fallbacks")

    resolved = {t: _CIK_CACHE[t] for t in upper_tickers if t in _CIK_CACHE}
    missing  = upper_tickers - resolved.keys()

    # ── Fallback 1: richer company_tickers_exchange.json (covers some OTC/ADR) ──
    if missing:
        exch = _get_json(
            "https://www.sec.gov/files/company_tickers_exchange.json",
            headers=HEADERS_SEC,
        )
        # Format: {"fields": ["cik","name","ticker","exchange"], "data": [[...], ...]}
        rows = (exch or {}).get("data") or []
        fields = (exch or {}).get("fields") or []
        try:
            ci, ti = fields.index("cik"), fields.index("ticker")
            for row in rows:
                tkr = str(row[ti]).upper()
                if tkr in missing and tkr not in _CIK_CACHE:
                    _CIK_CACHE[tkr] = str(row[ci]).zfill(10)
        except (ValueError, IndexError):
            pass
        resolved = {t: _CIK_CACHE[t] for t in upper_tickers if t in _CIK_CACHE}
        missing  = upper_tickers - resolved.keys()

    # ── Fallback 2: EDGAR atom name-search via a company-name hint ──────────────
    if missing:
        try:
            from tools.sec_edgar import resolve_cik as _edgar_resolve_cik  # lazy: no circular import
        except Exception as _e:
            _edgar_resolve_cik = None
            print(f"  Name-search fallback unavailable ({_e})")
        if _edgar_resolve_cik:
            for tkr in sorted(missing):
                hint = name_hints.get(tkr)
                if not hint:
                    # Without a name, a foreign ADR ticker almost never resolves;
                    # skip rather than spend a doomed request.
                    continue
                try:
                    cik = _edgar_resolve_cik(hint)
                except Exception as _e:
                    cik = None
                    print(f"  Name-search fallback failed for {tkr} ({hint!r}): {_e}")
                if cik:
                    _CIK_CACHE[tkr] = str(cik).zfill(10)
                    print(f"  CIK fallback: {tkr} → {_CIK_CACHE[tkr]} (via name-search '{hint}')")
        resolved = {t: _CIK_CACHE[t] for t in upper_tickers if t in _CIK_CACHE}
        missing  = upper_tickers - resolved.keys()

    if missing:
        print(f"  WARNING: No CIK found for tickers: {sorted(missing)}")
    return resolved

def _resolve_primary_document_url(index_url: str) -> Optional[str]:
    """
    Fetch the filing index page and return the URL of the primary 8-K document.
    Falls back to the first .htm document if primaryDocument isn't labelled.
    """
    time.sleep(REQUEST_DELAY)
    try:
        resp = requests.get(index_url, headers=HEADERS_SEC, timeout=15)
        resp.raise_for_status()
        text = resp.text

        # The index lists documents in a table; primary doc is typically first .htm
        # Look for the JSON-ified index first (faster parse)
        matches = re.findall(
            r'href="(/Archives/edgar/data/[^"]+\.htm)"', text, re.IGNORECASE
        )
        if matches:
            return "https://www.sec.gov" + matches[0]
    except Exception as e:
        print(f"  _resolve_primary_document_url error: {e}")
    return None


def _extract_item_101(text: str) -> str:
    """Extract Item 1.01 block. Falls back to deal-language anchored extraction."""

    # Pattern 1: explicit Item 1.01 header.
    # F-113-a (deal-1a): the previous pattern required a literal newline after
    # the header. The R4 source-text sanitiser in utils.text collapses ALL whitespace
    # to single spaces at the filing-text ingress, so on sanitised text this
    # branch could never match and every filing fell through to the anchor
    # fallbacks below. Newline-agnostic now: the header is "Item 1.01", an
    # optional title ("Entry into a Material Definitive Agreement"), optional
    # punctuation, then the body up to the next Item header. The first match is
    # frequently the cover-page items LIST (a header with no body), so take the
    # first match whose body is substantive rather than the first match.
    pattern = re.compile(
        r'item\s*1[\.\u00b7\u2022]?\s*01\b\s*[\.:\-\u2013\u2014]?\s*'
        r'(?:entry\s+into\s+a\s+material\s+definitive\s+agreement)?\s*[\.:\-\u2013\u2014]?\s*'
        r'(.*?)(?=\bitem\s*[1-9][\.\u00b7\u2022]?\s*\d\d\b|$)',
        re.IGNORECASE | re.DOTALL
    )
    for m in pattern.finditer(text):
        body = m.group(1).strip()
        if len(body) > 100:
            return body[:3000]

    # Pattern 2: "Entry into a Material Definitive Agreement" anchor
    idx = text.lower().find("entry into a material definitive agreement")
    if idx != -1:
        return text[idx:idx + 3000]

    # Pattern 3: deal-language anchor — grab surrounding context
    for anchor in [
        "license agreement", "collaboration agreement",
        "merger agreement", "acquisition agreement",
        "option agreement", "first amendment", "second amendment",
    ]:
        idx = text.lower().find(anchor)
        if idx != -1:
            start = max(0, idx - 200)
            return text[start:start + 3000]

    return ""


# Asset codes: 2-5 uppercase letters + optional dash + 3-5 digits (APG777, NXP-100).
_ASSET_CODE_RE = re.compile(r"\b([A-Z]{2,5}-?\d{3,5})\b")
# INN drug names by class suffix (zumilokibart, risankizumab, deucravacitinib).
_INN_SUFFIX = ("mab", "tinib", "ciclib", "degib", "parib", "lisib", "kibart",
               "gene", "cel", "tide", "sen", "vec", "ximab", "zumab", "umab",
               "citinib", "kinra", "kizumab")
_INN_RE = re.compile(r"\b([a-z]{5,}(?:" + "|".join(_INN_SUFFIX) + r"))\b")
# Code-shaped tokens that are NOT assets (statute/citation boilerplate).
_ASSET_STOPWORDS = {"CFR", "USC", "SEC", "GAAP", "EBITDA"}

# Generic MODALITY / descriptor words that are not asset identifiers. If treated
# as assets they collide with unrelated trials ("biologic" matched a Chronic
# Sinusitis study at an unaffiliated university). Filtered from assets_mentioned
# AND never used as a trial-matching token. Lowercase, matched case-insensitively.
GENERIC_ASSET_TERMS = frozenset({
    "biologic", "biologics", "biological", "biologicals", "small molecule",
    "small-molecule", "antibody",
    "monoclonal antibody", "monoclonal", "mab", "gene therapy", "cell therapy",
    "car-t", "car t", "peptide", "vaccine", "fusion protein", "protein",
    "inhibitor", "agonist", "antagonist", "oligonucleotide", "sirna", "mrna",
    "adc", "antibody-drug conjugate", "antibody drug conjugate", "bispecific",
    "enzyme", "compound", "drug", "therapy", "therapeutic", "treatment",
    "placebo", "molecule", "conjugate", "degrader", "agent", "product",
    "candidate", "asset", "biosimilar",
})


def _is_generic_asset(token: str) -> bool:
    """True if a token is a modality/descriptor word rather than an asset ID."""
    return (token or "").strip().lower() in GENERIC_ASSET_TERMS


def _extract_drug_names(text: str, keywords: list[str]) -> list[str]:
    """
    Discover deal assets from filing text DETERMINISTICALLY, without needing them
    pre-listed in the profile keywords:
      - alphanumeric program codes (APG777, NXP100, BNT327)
      - INN drug names by recognised class suffix (zumilokibart, risankizumab)
      - any profile keyword that appears (back-compatible with prior behaviour)

    The previous version returned only pre-listed keywords, so novel program codes
    in a filing were never surfaced (assets_mentioned came back empty). This finds
    them while staying fully sourced — every returned token is a literal substring
    of the filing. Order-preserving, de-duplicated, capped. Generic modality words
    (see GENERIC_ASSET_TERMS) are excluded — they are descriptors, not identifiers,
    and cause catastrophic false trial matches.
    """
    if not text:
        return []
    found, seen = [], set()

    def _add(x: str) -> None:
        k = x.lower()
        if k not in seen and not _is_generic_asset(x):
            seen.add(k)
            found.append(x)

    for m in _ASSET_CODE_RE.finditer(text):
        code = m.group(1)
        if code.split("-")[0] not in _ASSET_STOPWORDS:
            _add(code)
    for m in _INN_RE.finditer(text):
        _add(m.group(1))
    for kw in (keywords or []):
        if kw.lower() in text.lower():
            _add(kw)
    return found[:8]


def compute_pipeline_crossref(deal_text: str, profile: Optional[dict]) -> Optional[dict]:
    """
    Deterministically match a deal against the customer's grounding data (the
    profile's target/drug vocabulary and, when populated, the customer portfolio),
    producing a STRUCTURED, auditable overlap fact — never prose, never inference:

        {"overlap_type": "target"|"drug"|"portfolio",
         "matched_on":   "IL-13",
         "customer_ref": "your IL-13 focus area",
         "source":       "profile.focus_term_aliases"}

    Returns None when nothing matches — silence over speculation. This is the
    SOURCED substrate for any 'why it matters' note: it says only that a named
    target/drug from the deal literally co-occurs with the customer's tracked
    vocabulary, with the matched token and its source recorded for audit.
    """
    if not deal_text or not profile:
        return None
    hay = deal_text.lower()
    aliases   = profile.get("focus_term_aliases", {}) or {}
    portfolio = profile.get("default_customer_portfolio", []) or []

    def _tok(t: str) -> bool:
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(t.lower()) + r"(?![a-z0-9])", hay))

    # 1) strongest signal: a shared TARGET / mechanism (IL-13, TL1A, TYK2 ...)
    for term in aliases:
        if term and (term.isupper() or re.search(r"[0-9/]", term)) and _tok(term):
            return {"overlap_type": "target", "matched_on": term,
                    "customer_ref": f"your {term} focus area",
                    "source": "profile.focus_term_aliases"}
    # 2) a tracked competitor DRUG name appears in the deal
    for term in aliases:
        if term and not (term.isupper() or re.search(r"[0-9/]", term)) and _tok(term):
            return {"overlap_type": "drug", "matched_on": term,
                    "customer_ref": f"tracked competitor asset {term}",
                    "source": "profile.focus_term_aliases"}
    # 3) explicit customer-portfolio overlap (only when portfolio is populated)
    for item in portfolio:
        name = item if isinstance(item, str) else (item.get("name") or "")
        if name and name.lower() in hay:
            return {"overlap_type": "portfolio", "matched_on": name,
                    "customer_ref": f"your portfolio asset {name}",
                    "source": "profile.default_customer_portfolio"}
    return None


def _extract_counterparty(text: str, exclude_name: str = "") -> Optional[str]:
    """
    Heuristic extraction of counterparty from Item 1.01 text.
    exclude_name: the filing company's own name — prevents self-match.

    NOTE: SEC filing text typically capitalizes "Agreement", "Transaction",
    "License", etc. (Title Case legal drafting convention) — e.g.
    "entered into an Amended and Restated Exclusive License Agreement with
    MIRALOGX, LLC". The previous patterns required lowercase "agreement"/
    "transaction"/"entered into"/"executed", which never matched Title Case
    filing text and caused counterparty to silently return None for the
    majority of real filings. All anchor words are now matched case-
    insensitively via (?i:...) inline groups, while the captured company
    name itself still requires a leading capital letter (real entity names
    are always capitalized, so this avoids capturing lowercase boilerplate).
    """
    # Entity suffixes — comma before suffix is optional (e.g. "MIRALOGX, LLC"
    # or "MIRALOGX LLC"; "Care Pharmaceuticals Pty Limited"; "Novo Nordisk A/S")
    SUFFIX = r'(?:Inc\.?|LLC|L\.L\.C\.|Ltd\.?|Corp\.?|Corporation|GmbH|plc|PLC|AG|A/S|AB|NV|N\.V\.|SA|S\.A\.|Pty\.?\s+Ltd\.?|Pty\.?\s+Limited|Limited|Holdings?|Co\.?)'

    patterns = [
        # "...entered into an Amended and Restated Exclusive License Agreement
        #  with MIRALOGX, LLC" / "...Asset Purchase Agreement with Janssen
        #  Pharmaceuticals, Inc." — anchor words case-insensitive, captured
        #  name still must start with a capital letter.
        rf'(?i:agreement|transaction)\s+with\s+([A-Z][A-Za-z0-9\s,\.&\-]+?,?\s*{SUFFIX})',
        # "...entered into a [Type] Agreement with [Name]" without a suffix
        # (foreign entities, university names, etc.)
        rf'(?i:entered into|executed)\s+(?:an?\s+)?[\w\s]{{0,40}}?(?i:agreement|arrangement)\s+with\s+([A-Z][A-Za-z0-9\s,\.&\-]{{2,60}})',
        # "...Company and [Counterparty Name]" where counterparty has a
        # recognizable pharma/biotech name pattern
        r'and\s+([A-Z][A-Za-z0-9\s]+(?:Therapeutics|Pharma|Pharmaceuticals|Biosciences|Biologics|Sciences|Labs|Laboratories|Holdings))',
    ]
    exclude_tokens = set(exclude_name.lower().split()) - {"inc", "llc", "ltd", "corp", "the"}

    for pat in patterns:
        for m in re.finditer(pat, text):
            name = m.group(1).strip().rstrip(",.")
            # Trim trailing connector words a greedy match might pick up
            name = re.sub(r'\s+(?:to|for|in|under|pursuant|regarding)$', '', name, flags=re.IGNORECASE)
            if not (3 < len(name) < 80):
                continue
            # Skip if name shares most tokens with the filer
            name_tokens = set(name.lower().split()) - {"inc", "llc", "ltd", "corp", "the"}
            overlap = name_tokens & exclude_tokens
            if exclude_tokens and len(overlap) / max(len(exclude_tokens), 1) > 0.5:
                continue
            return name
    return None


# def _resolve_document_urls_html(index_url: str) -> dict:
#     """
#     Fetch the filing index and return URLs for both the primary 8-K document
#     and Exhibit 99.1 (press release) if present.
#     Returns: {"primary": url_or_None, "exhibit_99": url_or_None}
#     """
#     time.sleep(REQUEST_DELAY)
#     try:
#         resp = requests.get(index_url, headers=HEADERS_SEC, timeout=15)
#         resp.raise_for_status()
#         text = resp.text

#         primary   = None
#         ex99      = None

#         # Parse all href + description pairs from the index table
#         rows = re.findall(
#             r'href="(/Archives/edgar/data/[^"]+)"[^>]*>.*?<td[^>]*>([^<]*)</td>',
#             text, re.IGNORECASE | re.DOTALL
#         )
#         for path, description in rows:
#             url  = "https://www.sec.gov" + path
#             desc = description.strip().lower()
#             if not primary and path.endswith(".htm"):
#                 primary = url
#             if "ex" in desc and "99" in desc and ex99 is None:
#                 ex99 = url

#         # Fallback: grab first .htm as primary
#         if not primary:
#             matches = re.findall(
#                 r'href="(/Archives/edgar/data/[^"]+\.htm)"', text, re.IGNORECASE
#             )
#             if matches:
#                 primary = "https://www.sec.gov" + matches[0]

#         return {"primary": primary, "exhibit_99": ex99}

#     except Exception as e:
#         print(f"  _resolve_document_urls error: {e}")
#         return {"primary": None, "exhibit_99": None}

_TAG_RE  = re.compile(r"<[^>]+>")
_ROW_RE  = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_HREF_RE = re.compile(r'href="(/Archives/edgar/data/[^"]+)"', re.IGNORECASE)
_DOC_EXT = (".htm", ".html", ".txt")


def _clean_cell(cell: str) -> str:
    # R4b: was tags -> "" plus the literal "&nbsp;" only — the same named-only
    # class as the F9b ingress, so a numeric &#160; in an index cell survived
    # into the Type label. The ONE sanitiser decodes every entity form. A tag
    # now becomes a space rather than nothing; the sole consumer compares with
    # label.replace(" ", ""), so "EX-<br>99.1" resolves the same way.
    return sanitize_source_text(cell)


def _parse_index_rows(text: str) -> list[tuple[str, str, str]]:
    """
    Row-scoped parse of the EDGAR filing-index table.
    Returns [(href_path, type_label_upper, filename_lower)].

    Scoped PER <tr> so a cell can never be read from a neighbouring row. The
    previous implementation used one regex with a repeated capture group —
    Python keeps only the LAST repetition, and `.*?` under DOTALL crossed
    </tr>, so the "type" it read was the next row's Seq number. Result:
    exhibit_99 was None for every filing ever processed.
    """
    out: list[tuple[str, str, str]] = []
    for m in _ROW_RE.finditer(text):
        row = m.group(1)
        h = _HREF_RE.search(row)
        if not h:
            continue
        path = h.group(1)
        if not path.lower().endswith(_DOC_EXT):      # skip .jpg/.gif graphics
            continue
        raw_cells = _CELL_RE.findall(row)
        cells = [_clean_cell(c) for c in raw_cells]
        # EDGAR column order: Seq | Description | Document | Type | Size.
        # The Type label is the cell immediately AFTER the anchor's cell.
        anchor_i = next((i for i, c in enumerate(raw_cells) if "href=" in c.lower()), None)
        type_label = cells[anchor_i + 1] if (anchor_i is not None and anchor_i + 1 < len(cells)) else ""
        out.append((path, type_label.upper(), path.rsplit("/", 1)[-1].lower()))
    return out


def _pick_exhibit_99(rows: list[tuple[str, str, str]]) -> Optional[str]:
    """
    Prefer EX-99.1 (the press release, which states deal totals and guidance)
    over EX-99.2 (typically an investor slide deck). Falls back to filename
    convention when the Type column is absent or non-standard.
    """
    def _url(p: str) -> str:
        return "https://www.sec.gov" + p
    for path, label, _ in rows:
        if label.replace(" ", "").startswith("EX-99.1"):
            return _url(path)
    for path, _, fname in rows:
        if re.match(r"^ex-?99[-_.]?1\b", fname) or re.match(r"^ex991\b", fname):
            return _url(path)
    for path, label, fname in rows:
        if label.replace(" ", "").startswith("EX-99") or fname.startswith(("ex99", "ex-99")):
            return _url(path)
    return None

def _index_json_url(index_htm_url: str) -> Optional[str]:
    """The structured index.json sits beside {accession}-index.htm."""
    m = re.search(r'/edgar/data/(\d+)/(\d+)/([0-9\-]+)-index\.htm', index_htm_url)
    if not m:
        return None
    cik, accnodash, acc = m.groups()
    return f"{ARCHIVES_URL}/{cik}/{accnodash}/{acc}-index.json"


def _pick_from_index_json(payload: dict, base_url: str) -> dict:
    """
    Resolve {primary, exhibit_99} from an EDGAR index.json payload.

    index.json.directory.item[] lists every file with a reliable `type` field
    (e.g. "8-K", "EX-99.1", "GRAPHIC"), so no HTML table reconstruction is
    needed — the source of the earlier fragility. Prefers EX-99.1 (press
    release) over EX-99.2 (slides); filename fallback when the type is blank.
    """
    items = (payload.get("directory") or {}).get("item") or []
    primary = ex99 = ex99_alt = None
    for it in items:
        name = it.get("name") or ""
        low  = name.lower()
        typ  = (it.get("type") or "").upper().replace(" ", "")
        if not low.endswith((".htm", ".html", ".txt")):
            continue                                   # skip graphics/xbrl/etc.
        url = f"{base_url}/{name}"
        if typ in ("8-K", "8-K/A") and not primary:
            primary = url
        if typ.startswith("EX-99.1") and not ex99:
            ex99 = url
        elif (typ.startswith("EX-99") or low.startswith(("ex99", "ex-99"))) and not ex99_alt:
            ex99_alt = url
    if not ex99:                                        # filename fallback for .1
        for it in items:
            low = (it.get("name") or "").lower()
            if re.match(r"^ex-?99[-_.]?1", low):
                ex99 = f"{base_url}/{it['name']}"
                break
    return {"primary": primary, "exhibit_99": ex99 or ex99_alt}


def _resolve_via_index_json(index_url: str) -> Optional[dict]:
    """
    Structured resolver: fetch {accession}-index.json and pick primary + EX-99.1.
    Returns a dict on success, or None if the JSON couldn't be fetched/parsed
    (caller then falls back to the HTML parser). Reuses the same HTTP contract
    (headers, delay) as the rest of the SEC layer.
    """
    js_url = _index_json_url(index_url)
    if not js_url:
        return None
    time.sleep(REQUEST_DELAY)
    try:
        resp = requests.get(js_url, headers=HEADERS_SEC, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        base_url = js_url.rsplit("/", 1)[0]
        return _pick_from_index_json(payload, base_url)
    except Exception as e:
        _vprint(f"  [RESOLVE] index.json unavailable ({e}); falling back to HTML: {index_url}")
        return None


def _resolve_document_urls(index_url: str) -> dict:
    """
    Identify, for an 8-K filing:
    - primary:    the 8-K body document (contains Item 1.01)
    - exhibit_99: the Exhibit 99.1 press release (deal totals / guidance)

    Strategy: try the STRUCTURED index.json first (reliable per-document `type`
    field), and fall back to HTML-table parsing only if the JSON is unavailable.
    The HTML path was fragile across EDGAR's format variants, which left
    exhibit_99 empty for filings that in fact carry a press release.
    """
    # 1) structured index.json (primary strategy)
    resolved = _resolve_via_index_json(index_url)
    if resolved and (resolved.get("primary") or resolved.get("exhibit_99")):
        if not resolved.get("primary"):
            resolved["primary"] = _resolve_primary_via_submissions(index_url)
        if not resolved.get("exhibit_99"):
            print(f"  [RESOLVE] no EX-99 in index.json: {index_url}")
        return resolved

    # 2) HTML fallback (legacy path, kept for robustness)
    time.sleep(REQUEST_DELAY)
    try:
        resp = requests.get(index_url, headers=HEADERS_SEC, timeout=15)
        resp.raise_for_status()
        text = resp.text

        rows    = _parse_index_rows(text)
        primary = next(("https://www.sec.gov" + p for p, label, _ in rows
                        if label in ("8-K", "8-K/A")), None)
        ex99    = _pick_exhibit_99(rows)

        if not primary:
            primary = _resolve_primary_via_submissions(index_url)
        if not ex99:
            print(f"  [RESOLVE] no EX-99 found (html, {len(rows)} rows): {index_url}")
        return {"primary": primary, "exhibit_99": ex99}

    except Exception as e:
        print(f"  _resolve_document_urls error ({index_url}): {e}")
        return {"primary": None, "exhibit_99": None}

def resolve_filing_documents(index_url: str) -> dict:
    """
    Public wrapper around _resolve_document_urls — used by
    tools.financial_intelligence to fetch a competitor's most recent
    earnings filing (primary doc + Exhibit 99.1 press release) for
    guidance / product-revenue extraction, independent of the deal-tracker
    workflow this was originally written for.
    Returns {"primary": url_or_None, "exhibit_99": url_or_None}.
    """
    return _resolve_document_urls(index_url)

def _resolve_primary_via_submissions(index_url: str) -> Optional[str]:
    """
    Fallback: derive the 8-K body URL from the accession number directly.
    The SEC submissions API returns document lists with reliable type fields.

    Accession is embedded in the index URL:
    .../edgar/data/{cik}/{accession_nodash}/{accession}-index.htm
    """
    # Extract CIK and accession from URL
    m = re.search(
        r'/edgar/data/(\d+)/(\d+)/([0-9\-]+)-index\.htm',
        index_url
    )
    if not m:
        return None

    cik_raw, _, accession = m.groups()
    cik_padded = cik_raw.zfill(10)

    time.sleep(REQUEST_DELAY)
    try:
        url  = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
        resp = requests.get(url, headers=HEADERS_SEC, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Find this accession in recent filings
        filings   = data.get("filings", {}).get("recent", {})
        acc_list  = filings.get("accessionNumber", [])
        doc_list  = filings.get("primaryDocument", [])

        for acc, doc in zip(acc_list, doc_list):
            if acc == accession and doc:
                acc_clean = acc.replace("-", "")
                cik_num   = cik_raw.lstrip("0")
                return f"{ARCHIVES_URL}/{cik_num}/{acc_clean}/{doc}"

    except Exception as e:
        print(f"  _resolve_primary_via_submissions error: {e}")

    return None

def _build_deal_analyst_note(deal: dict) -> str:
    """
    Customer-facing one-line explanation of a deal row.

    Built ONLY from validated, engine-extracted fields (deal_type, counterparty,
    sanitized deal_direction, is_high_value, assets, disclosure status) — never
    free-generated text — so it cannot introduce a claim the source filing does
    not support. It explains WHAT KIND of deal and WHO, and flags significance;
    it does NOT repeat the Value column's figures (shown alongside), does NOT dump
    the raw "all values mentioned" list, and carries NO engineering/provenance
    meta (that is stated once at the section level in the renderer).
    """
    dtype     = deal.get("deal_type") or "BD transaction"
    cp        = deal.get("counterparty")
    assets    = deal.get("assets_mentioned") or []
    hv        = deal.get("is_high_value")
    direction = deal.get("deal_direction")            # sanitized upstream; may be None
    val_disclosed = bool(deal.get("deal_value_usd"))

    # 1) What happened. Prefer the validated direction phrase; suppress a phrase
    #    that leaked a null counterparty ("... to acquire the target").
    if direction and "the target" not in direction.lower():
        lead = direction.rstrip(".")
    elif cp:
        lead = f"{dtype} with {cp}"
    else:
        lead = dtype

    parts = [lead]

    # 2) Significance + disclosure status (categorical, not numeric — the Value
    #    column carries the numbers).
    flags = []
    # Sourced competitive relevance: only present when the engine deterministically
    # matched a deal target/drug against the customer's tracked vocabulary. The
    # matched token is literal filing text, so this is a fact, not an inference.
    xref = deal.get("pipeline_crossref")
    if isinstance(xref, dict) and xref.get("matched_on"):
        flags.append(f"relevant to {xref.get('customer_ref') or xref['matched_on']} "
                     f"(matched on {xref['matched_on']})")
    elif isinstance(xref, str) and xref.strip():
        flags.append(xref.strip())
    # Sourced clinical context from ClinicalTrials.gov (phase / indication /
    # mechanism), resolved deterministically. Rendered only when present; every
    # token is a literal registry field. Type-guarded: trial_facts is a dict or
    # None, and format_trial_context returns "" for anything empty.
    tf = deal.get("trial_facts")
    if isinstance(tf, dict):
        tclause = _format_trial_clause(tf)
        if tclause:
            flags.append(tclause)
    if hv:
        flags.append("high-value for this portfolio")
    if not val_disclosed and dtype != "Agreement Termination":
        flags.append("deal economics not disclosed in the filing")
    if dtype == "License Amendment":
        flags.append("amends an existing agreement")
    if assets:
        # Surface the profiled asset first so the program list is consistent with
        # the "clinical profile (<asset>)" label — otherwise the matched molecule
        # (e.g. Nuvectis's NXP900) can be absent from a truncated program list
        # while its profile is shown, reading as a mismatch.
        ordered = list(assets)
        prof_asset = tf.get("profiled_asset") if isinstance(tf, dict) else None
        if prof_asset and prof_asset in ordered:
            ordered.remove(prof_asset)
            ordered.insert(0, prof_asset)
        flags.append("program(s): " + ", ".join(ordered[:3]))
    if flags:
        parts.append("; ".join(flags))

    return ". ".join(p.rstrip(".") for p in parts) + "."


def _format_trial_clause(facts: dict) -> str:
    """Compact sourced clause from resolved CT.gov facts. Provenance-aware: a
    mechanism sourced FROM the trial text is co-located under the CT.gov citation,
    while a mechanism from the filing crossref or the profile drug-target map
    carries its OWN attribution — so a non-registry mechanism is never
    misattributed to ClinicalTrials.gov.

    The clinical profile is labelled with the SPECIFIC asset it describes
    (facts['profiled_asset']) whenever a particular molecule was matched — this
    prevents a deal that also lists an unrelated program (e.g. C4's CFT8919 next
    to the matched elranatamab, or Nuvectis's NXP900 profile vs an NXP100 program
    list) from implying the profile belongs to the wrong drug. An efficacy
    endpoint is surfaced when available (safety endpoints are suppressed upstream).

    Defensive against any None field (the resolver's type contract permits
    phase/indication/mechanism/endpoint to be None). Returns '' when nothing
    renderable."""
    if not isinstance(facts, dict) or not facts.get("ncts"):
        return ""
    nct = facts["ncts"][0]
    mech = facts.get("mechanism")
    mech_src = facts.get("mechanism_source") or ""
    # A mechanism read from the trial record shares the trial's CT.gov citation;
    # anything else (crossref, profile map) must footnote its own source.
    mech_from_trial = bool(mech) and mech_src.startswith("ClinicalTrials.gov")

    bits = []
    if mech and mech_from_trial:
        bits.append(str(mech))
    ind = facts.get("indication")
    if ind:
        bits.append(str(ind))
    phase = facts.get("phase")
    if phase and str(phase).upper() not in ("NA", "N/A"):
        bits.append(str(phase).replace("PHASE", "Phase "))

    # Name the asset the profile describes, so the reader can't misattribute the
    # profile to another program listed for the same deal.
    prof_asset = facts.get("profiled_asset")
    label = f"clinical profile ({prof_asset})" if prof_asset else "clinical profile"

    clause = ""
    if bits:
        clause = f"{label}: " + ", ".join(bits) + f" (per ClinicalTrials.gov {nct})"
    if mech and not mech_from_trial:
        seg = f"mechanism: {mech} (per {mech_src or 'curated reference'})"
        clause = clause + "; " + seg if clause else seg
    # Efficacy endpoint (safety endpoints suppressed upstream) — the primary
    # readout that will move the asset; sourced to the same NCT.
    ep = facts.get("lead_endpoint")
    if ep:
        clause = clause + f"; primary endpoint: {ep}" if clause else \
                 f"primary endpoint: {ep} (per ClinicalTrials.gov {nct})"
    return clause


# Whole-token-ish boundary: the term must be flanked by non-alphanumerics so
# "GIP" does not match inside "equipment" while "GLP-1" still matches in
# "GLP-1 receptor agonist".
_THESIS_TERM_BOUNDARY = r"(?<![a-z0-9]){term}(?![a-z0-9])"


def _deal_searchable_text(deal: dict) -> str:
    """
    Concatenate the SOURCE text fields of a deal for term matching (lowercased).

    NOTE: pipeline_crossref is deliberately excluded — it is DERIVED output
    (a dict produced by compute_pipeline_crossref from this very text), not source
    filing text. Including it would (a) create a feedback loop and (b) raise a
    TypeError once it is populated as a dict, since this joins only strings.
    """
    parts = [
        deal.get("company") or "",
        deal.get("counterparty") or "",
        deal.get("headline") or "",
        deal.get("deal_type") or "",
        deal.get("item_101_excerpt") or "",
        deal.get("exhibit_99_excerpt") or "",
        deal.get("analyst_note") or "",
    ]
    assets = deal.get("assets_mentioned") or []
    if isinstance(assets, list):
        parts.extend(str(a) for a in assets)
    # Defensive: coerce anything non-string so a future dict/None field can never
    # break term matching or empty the whole deal-tracker section.
    return " \n ".join(str(p) for p in parts if p).lower()


def _expand_focus_variants(
    focus_terms: Optional[list[str]],
    focus_term_aliases: Optional[dict[str, list[str]]],
) -> dict[str, list[str]]:
    """term -> [term + aliases], deduplicated and lowercased. Generic."""
    focus_term_aliases = focus_term_aliases or {}
    out: dict[str, list[str]] = {}
    for term in focus_terms or []:
        variants: list[str] = []
        seen: set[str] = set()
        for v in [term] + list(focus_term_aliases.get(term, [])):
            vl = (v or "").strip().lower()
            if vl and vl not in seen:
                seen.add(vl)
                variants.append(vl)
        if variants:
            out[term] = variants
    return out


# ── deal-1a: filing SUBSTANCE — what the document says it is about ───────────
# THE DEFECT (TRACK §6.34g, CI review 2026-08-31). A deal's `headline` is the
# EDGAR index description of the hit document, which for an exhibit hit is the
# bare label "EX-99.1". One report printed `summary: "EX-99.1 (value: $381M
# upfront)"` — a filename standing in for a $381M transaction — and, because
# the press release itself is excluded from thesis scoring (T111, correctly:
# issuer "about us" boilerplate scored 11 of 13 unrelated deals on-thesis),
# the scorer had almost nothing to read and routed the deal off-thesis.
#
# THE FIX. Read the narrowest surface on which a press release states what it
# is announcing: its TITLE and its ANNOUNCEMENT SENTENCE, and of that sentence
# only the part FROM THE DEAL VERB ONWARD ("...today announced | a license
# agreement with X to develop Y for Z"). The clause before the verb is the
# filer's self-description ("a clinical-stage company developing therapies
# for <the profile's indication>") — the T111 boilerplate one paragraph
# earlier — and is excluded.
#
# MODULARITY. Strategies are keyed by DOCUMENT KIND, not SEC form: an 8-K
# alone arrives as a press-release exhibit, an Item 1.01 body, or an Item
# 7.01/8.01 body, and a 6-K body is a fourth. Each strategy owns its one-line
# METHOD sentence (rule 2: the datum's footnote travels with the datum). A new
# document kind (10-Q MD&A, 13D) is a new registry entry, never a new branch
# in the scorer, which reads `substance` and knows no strategy.
#
# ENGINE/PROFILE LINE (rules 1/10): press-release grammar only — exhibit
# labels, newswire datelines, announcement verbs. No drug, company, class, or
# indication term appears here; those arrive from the profile via the scorer.
#
# CACHE. exhibit_99_excerpt / item_101_excerpt are already on every cached
# deal record, so this runs POST-cache in the runner's deterministic tagging
# tier — no TOOL_OUTPUT_VERSIONS bump; cached filings re-score on the next run.

# The stored excerpt clamp. MEASURED on 29 cached press-release excerpts
# (session 113 probe, tree cache): at 2,000 chars 4 of 20 announcement
# sentences were cut by the clamp, the sentence began as late as char 1,530,
# and p90 of "chars needed" WAS the clamp. 4,000 gives 2x headroom for long
# highlight-bullet preambles at +2 KB per deal. The clamp is now RECORDED on
# the record (rule 2) instead of silent; deal_tracker's 6-hour TTL means old
# 2,000-char rows age out without a TOOL_OUTPUT_VERSIONS bump.
DEAL_EXCERPT_CHARS = 4000
DEAL_EXCERPT_METHOD = (
    "Excerpt is the first {kept:,} characters of the {total:,}-character source "
    "document as flattened by the source-text sanitiser; the substance reader and "
    "thesis scorer see only this excerpt (deal-1a).")


def _excerpt_with_basis(text: str, limit: int = DEAL_EXCERPT_CHARS):
    """(excerpt, basis) — the clamp and its footnote, or (None, None)."""
    if not text:
        return None, None
    total = len(text)
    kept = min(total, limit)
    return text[:kept], {"kept": kept, "total": total, "clamped": total > kept,
                         "limit": limit,
                         "method": DEAL_EXCERPT_METHOD.format(kept=kept, total=total)}


# EDGAR's document-table header rides at the head of a fetched exhibit as
# flattened text — "EX-99.1 2 d102781dex991.htm EX-99.1 EX-99.1 Exhibit 99.1
# Press Release <title>" (type, sequence, filename, type, type, label). Strip
# those tokens repeatedly until the first real word. MEASURED: with only the
# first label stripped, 10 of 25 read releases yielded a title.
# Alternation order matters: the FILENAME must be tried before the LABEL,
# because filenames such as "mira-ex99_1.htm" begin with "ex99" and the label
# alternative would eat "ex99-1" and strand ".htm" (measured: 4 of 8 titles).
_SUBSTANCE_EDGAR_HEADER_TOKEN_RE = re.compile(
    r"^\s*(?:[\w\-.]+\.(?:htm|html|txt|pdf|xml)|(?:exhibit|ex)[\s\-\.]*\d+(?:\.\d+)?"
    r"|\d{1,3}|graphic|document)"
    r"\b[\s:\-\u2013\u2014,]*", re.IGNORECASE)
# Sub-headline separators a release places between its title and its dateline
# ("Title • Approval based on ... -- U.S. launch ..."). The title is the first
# segment; the rest is kept on the record as `subhead`, never discarded.
_SUBSTANCE_SUBHEAD_SPLIT_RE = re.compile(r"\s*(?:\u2022|\s--\s|\s\u2013\s|\s\u2014\s|\s\|\s)\s*")


def _strip_edgar_header(text: str) -> str:
    for _ in range(12):
        m = _SUBSTANCE_EDGAR_HEADER_TOKEN_RE.match(text)
        if not m or m.end() == 0:
            break
        text = text[m.end():]
    return text


_SUBSTANCE_EXHIBIT_LABEL_RE = re.compile(
    r"^\s*(?:exhibit|ex)[\s\-\.]*\d+(?:\.\d+)?\s*[:\-\u2013\u2014]?\s*", re.IGNORECASE)
_SUBSTANCE_HEADLINE_IS_LABEL_RE = re.compile(
    r"^\s*(?:exhibit|ex)[\s\-\.]*\d+(?:\.\d+)?\s*$", re.IGNORECASE)
_SUBSTANCE_RELEASE_NOISE_RE = re.compile(
    r"\b(?:for\s+immediate\s+release|press\s+release|news\s+release|media\s+release)\b"
    r"[:\s\-\u2013\u2014]*", re.IGNORECASE)
# A newswire dateline in flattened text: "RICHMOND, Calif., Jan. 6, 2025
# (GLOBE NEWSWIRE) -- ", "INDIANAPOLIS, Sept. 4, 2026 /PRNewswire/ -- ",
# "Copenhagen, Denmark, 4 September 2026 – ". Anchored on the DATE; the city
# fragment before it is trimmed separately by _SUBSTANCE_DATELINE_CITY_RE.
_SUBSTANCE_MONTHS = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
                     r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
_SUBSTANCE_DATE_RE = re.compile(
    r"(?:" + _SUBSTANCE_MONTHS + r"\.?\s+\d{1,2},?\s+\d{4}"          # Sept. 4, 2026
    r"|\d{1,2}\s+" + _SUBSTANCE_MONTHS + r"\.?,?\s+\d{4})",           # 4 September 2026
    re.IGNORECASE)
_SUBSTANCE_WIRE_RE = re.compile(
    r"[\(\-\u2013\u2014/]*\s*(?:GLOBE\s*NEWSWIRE|BUSINESS\s*WIRE|PR\s*Newswire|PRNewswire|"
    r"ACCESSWIRE|Newsfile|Cision|EQS)[^)\-\u2013\u2014/]*[\)\-\u2013\u2014/]*\s*", re.IGNORECASE)
# The city fragment of a dateline, trimmed off the title's tail. US wire style
# sets the city in CAPITALS ("SAN FRANCISCO", "RICHMOND, Calif.,"), so a
# capitalised title word ("Billion") is never mistaken for it. European style
# is mixed case with the country following ("Copenhagen, Denmark,"); there the
# city is ONE word unless it opens with a geographic prefix ("New York",
# "San Diego", "Palo Alto"). Geography grammar, not class knowledge.
_SUBSTANCE_CITY_PREFIXES = (
    "New", "San", "Los", "Las", "St.", "Saint", "Fort", "Palo", "Salt", "Santa",
    "South", "North", "East", "West", "Mountain", "Menlo", "Redwood", "Foster",
    "Hong", "Tel", "Cape", "Port", "Rio", "Sao", "S\u00e3o", "Buenos", "Kuala",
    "Abu", "Long", "Little", "Grand", "Lake", "Oklahoma", "Kansas", "Jersey")
_SUBSTANCE_DATELINE_CITY_RE = re.compile(
    r"\s*(?:[\-\u2013\u2014]{1,2}\s*)?"
    r"(?:"
    r"[A-Z][A-Z.'\-]+(?:\s+[A-Z][A-Z.'\-]+){0,3}"                                    # CAPS city ...
    r"(?:(?:,\s*[A-Za-z.]{2,20}){1,2}|\s*,"                                          #   , State, | ,
    r"|(?=\s*[\-\u2013\u2014]{1,2}\s*\(?[A-Za-z ]*(?:WIRE|NEWSWIRE|ACCESSWIRE|Newsfile)))"  #   --(WIRE)
    # A bare run of capitals before the date with no comma or wire marker is
    # TITLE text ("VERTEX ... ACQUISITION OF ..."), not a city — measured.
    r"|(?:(?:" + "|".join(re.escape(x) for x in _SUBSTANCE_CITY_PREFIXES) + r")\s+)?"
    r"[A-Z][a-z.'\-]+(?:,\s*[A-Za-z.]{2,20}){1,2}"                                # City, Country
    r"|(?:(?:" + "|".join(re.escape(x) for x in _SUBSTANCE_CITY_PREFIXES) + r")\s+)?"
    r"[A-Z][a-z.'\-]+\s*,"                                                          # City, <date>
    r")"
    r"[\s,]*(?:[\-\u2013\u2014]{1,2}\s*\(?[A-Za-z ]*(?:WIRE|NEWSWIRE|ACCESSWIRE|Newsfile)\)?\s*[\-\u2013\u2014]*)?"
    r"\s*$")
# The deal verb. "today announced" is the press-release norm; the agreement
# verbs cover Item 1.01 bodies, which open "On <date>, X entered into ...".
_SUBSTANCE_CUE_RE = re.compile(
    r"\b(?:announced|announces|announcing|entered\s+into|has\s+entered\s+into|"
    r"have\s+entered\s+into|agreed\s+to|has\s+agreed\s+to|signed|has\s+signed|"
    r"executed|completed|has\s+completed|closed|has\s+closed|acquired|has\s+acquired|"
    r"to\s+acquire|will\s+acquire|licensed|has\s+licensed|amended|has\s+amended|"
    r"expanded|has\s+expanded|extended|has\s+extended|to\s+merge|will\s+merge|"
    r"unveiled|has\s+unveiled)\b", re.IGNORECASE)
# Sentence end in flattened text: terminal punctuation, whitespace, a capital.
# Abbreviations that end with a period and a capital follows are protected.
_SUBSTANCE_ABBREV = ("inc", "corp", "ltd", "co", "plc", "llc", "lp", "s.a", "ag", "n.v",
                     "dr", "mr", "ms", "mrs", "jr", "sr", "st", "no", "vs", "u.s", "u.k",
                     "calif", "mass", "conn", "fla", "ill", "ind", "mich", "minn", "wash",
                     "penn", "tenn", "wis", "colo", "nev", "ariz", "ore", "okla", "ph.d",
                     "approx", "et al", "e.g", "i.e", "jan", "feb", "mar", "apr", "jun",
                     "jul", "aug", "sep", "sept", "oct", "nov", "dec")
_SUBSTANCE_SENT_END_RE = re.compile(r"[.!?]+(?=\s+[A-Z\u201c\"])")
_SUBSTANCE_TITLE_MAX_WORDS = 60
_SUBSTANCE_LEAD_MAX_CHARS = 700

SUBSTANCE_METHOD_PRESS_RELEASE = (
    "Substance read from the press-release exhibit (EX-99.x) as flattened by the "
    "source-text sanitiser: the TITLE is the text between the exhibit label and the "
    "newswire dateline (release-label noise removed); the ANNOUNCEMENT SENTENCE is the "
    "first sentence after the dateline containing an announcement verb, and the "
    "scorable lead is that sentence FROM THE VERB ONWARD — the filer's "
    "self-description before the verb and all later release text are excluded "
    "(deal-1a; T111 boilerplate rule).")
SUBSTANCE_METHOD_ITEM_BODY = (
    "Substance read from the filing's Item body (Item 1.01 or the anchor-phrase "
    "fallback): no title; the ANNOUNCEMENT SENTENCE is the first sentence containing "
    "an agreement verb (else the body's first sentence), and the scorable lead is that "
    "sentence from the verb onward (deal-1a).")
SUBSTANCE_HEADLINE_REPAIR_METHOD = (
    "Headline replaced: the EDGAR index description of the hit document was a bare "
    "exhibit label (or empty), so the press-release exhibit's own title is shown; the "
    "original label is retained in headline_basis.original (deal-1a).")


def _substance_sentence_bounds(text: str, pos: int) -> tuple[int, int]:
    """(start, end) of the sentence containing `pos` in flattened text.
    Abbreviation periods (Inc., Calif., U.S.) do not end a sentence."""
    def _is_end(m) -> bool:
        pre = text[max(0, m.start() - 12):m.start()].lower()
        tok = re.split(r"[\s(]", pre)[-1] if pre else ""
        tok = tok.rstrip(".")
        return tok not in _SUBSTANCE_ABBREV
    start = 0
    for m in _SUBSTANCE_SENT_END_RE.finditer(text, 0, pos):
        if _is_end(m):
            start = m.end()
    end = len(text)
    for m in _SUBSTANCE_SENT_END_RE.finditer(text, pos):
        if _is_end(m):
            end = m.end()
            break
    return start, end


def _substance_lead(text: str, from_pos: int, window: Optional[int] = None) -> Optional[dict]:
    """First announcement sentence at/after from_pos; None when no cue is found
    (within `window` chars when given, else to the end of the excerpt — the
    excerpt is already the clamp). Returns {sentence, lead_from_cue, cue}."""
    seg_end = len(text) if window is None else min(len(text), from_pos + window)
    m = _SUBSTANCE_CUE_RE.search(text, from_pos, seg_end)
    if not m:
        return None
    s, e = _substance_sentence_bounds(text, m.start())
    s = max(s, from_pos)                 # the sentence begins after the dateline
    sentence = text[s:e].strip(" -\u2013\u2014")
    _w = _SUBSTANCE_WIRE_RE.match(sentence)     # "(GLOBE NEWSWIRE) -- " after the date
    if _w and _w.end() > 0:
        sentence = sentence[_w.end():].strip(" -\u2013\u2014")
    lead = text[m.start():e].strip()
    if len(lead) > _SUBSTANCE_LEAD_MAX_CHARS:
        cut = lead.rfind(" ", 0, _SUBSTANCE_LEAD_MAX_CHARS)
        lead = lead[:cut if cut > 0 else _SUBSTANCE_LEAD_MAX_CHARS].rstrip() + " [...]"
    return {"sentence": sentence, "lead_from_cue": lead, "cue": m.group(0)}


def _substance_from_press_release(text: str) -> Optional[dict]:
    """Strategy: press-release exhibit. Title = text before the dateline;
    lead = announcement sentence after it, from the verb onward."""
    text = (text or "").strip()
    if not text:
        return None
    body = _strip_edgar_header(text)
    body = _SUBSTANCE_EXHIBIT_LABEL_RE.sub("", body, count=1)
    body = _SUBSTANCE_RELEASE_NOISE_RE.sub("", body)
    # The first month-day-year date in a release is its dateline; search the
    # whole excerpt, since highlight bullets before the dateline can run long.
    # A body-text date that wins instead yields a >60-word "title", which the
    # cap below rejects — degradation is to no title, never to a wrong one.
    dm = _SUBSTANCE_DATE_RE.search(body)
    title = None
    subhead = None
    lead_from = 0
    if dm:
        head = body[:dm.start()]
        # City first — its pattern needs to SEE a trailing wire marker
        # ("SAN FRANCISCO--(BUSINESS WIRE)--") to know the capitals are a city.
        head = _SUBSTANCE_DATELINE_CITY_RE.sub("", head)
        head = _SUBSTANCE_WIRE_RE.sub(" ", head).strip(" -\u2013\u2014,;:|\u2022")
        segs = [x.strip() for x in _SUBSTANCE_SUBHEAD_SPLIT_RE.split(head) if x.strip()]
        first = segs[0] if segs else ""
        words = first.split()
        if 3 <= len(words) <= _SUBSTANCE_TITLE_MAX_WORDS:
            title = " ".join(words)
            rest = " ".join(segs[1:]).strip()
            subhead = rest[:300] if rest else None
        lead_from = dm.end()
    lead = _substance_lead(body, lead_from)
    if lead is None and lead_from:
        lead = _substance_lead(body, 0)            # dateline found, verb before it
    if title is None and lead is None:
        return None
    return {"title": title, "subhead": subhead,
            "lead_sentence": lead["sentence"] if lead else None,
            "lead_from_cue": lead["lead_from_cue"] if lead else None,
            "cue": lead["cue"] if lead else None,
            "dateline_found": bool(dm)}


def _substance_from_item_body(text: str) -> Optional[dict]:
    """Strategy: 8-K/6-K Item body. No title. Lead = first agreement sentence
    from the verb onward, else the body's first sentence."""
    text = (text or "").strip()
    if not text:
        return None
    lead = _substance_lead(text, 0, window=len(text))
    if lead is None:
        s, e = _substance_sentence_bounds(text, 0)
        first = text[s:e].strip()
        if not first:
            return None
        lead = {"sentence": first, "lead_from_cue": first, "cue": None}
    return {"title": None, "subhead": None, "lead_sentence": lead["sentence"],
            "lead_from_cue": lead["lead_from_cue"], "cue": lead["cue"],
            "dateline_found": False}


# Registry: document kind -> (strategy, method sentence). Extend here only.
SUBSTANCE_STRATEGIES: dict[str, tuple] = {
    "press_release": (_substance_from_press_release, SUBSTANCE_METHOD_PRESS_RELEASE),
    "item_body":     (_substance_from_item_body,     SUBSTANCE_METHOD_ITEM_BODY),
}


def extract_filing_substance(text: str, doc_kind: str) -> Optional[dict]:
    """Dispatch on document kind. Returns None when the strategy finds no title
    and no announcement sentence, else the strategy's dict plus `strategy` and
    `method` — the method sentence IS the footnote for every downstream use."""
    entry = SUBSTANCE_STRATEGIES.get(doc_kind)
    if entry is None:
        raise KeyError(f"unknown substance document kind {doc_kind!r}; "
                       f"registered: {sorted(SUBSTANCE_STRATEGIES)}")
    fn, method = entry
    # Cached excerpts written before the R4 sanitiser still carry numeric
    # entities (&#8217;). Decoding here is idempotent on clean text.
    out = fn(_html.unescape(text or ""))
    if not out:
        return None
    out["strategy"] = doc_kind
    out["method"] = method
    return out


def apply_deal_substance(deal: dict) -> dict:
    """Post-cache, deterministic, idempotent: set deal["substance"] from the
    press-release exhibit when present (else the Item body), and repair a
    headline that is a bare exhibit label (or empty) with the exhibit's title,
    recording the repair in deal["headline_basis"]. Returns the deal."""
    if not isinstance(deal, dict):
        return deal
    sub = None
    if deal.get("exhibit_99_excerpt"):
        sub = extract_filing_substance(deal["exhibit_99_excerpt"], "press_release")
        if sub:
            sub["source_field"] = "exhibit_99_excerpt"
            sub["excerpt_basis"] = deal.get("exhibit_99_excerpt_basis")   # None on pre-deal-1a rows
    if sub is None and deal.get("item_101_excerpt"):
        sub = extract_filing_substance(deal["item_101_excerpt"], "item_body")
        if sub:
            sub["source_field"] = "item_101_excerpt"
            sub["excerpt_basis"] = deal.get("item_101_excerpt_basis")
    deal["substance"] = sub
    # Why substance is absent, when it is — the export never carries a silent
    # empty field (rule 2). None when substance was read.
    if sub is None:
        deal["substance_note"] = (
            "exhibit/Item text present but no title or announcement sentence was "
            "recognised (no newswire dateline and no deal verb); the deal scores on "
            "its T111 surfaces exactly as before deal-1a"
            if (deal.get("exhibit_99_excerpt") or deal.get("item_101_excerpt"))
            else "no press-release exhibit or Item text was fetched for this filing")
    else:
        deal["substance_note"] = None

    hb = deal.get("headline_basis")
    original = (hb or {}).get("original") if isinstance(hb, dict) else None
    current = deal.get("headline") or ""
    label_like = (not current.strip()) or bool(_SUBSTANCE_HEADLINE_IS_LABEL_RE.match(current))
    if original is None:
        original = current
    if sub and sub.get("title") and (label_like or (isinstance(hb, dict) and hb.get("source") == "exhibit_title")):
        deal["headline"] = sub["title"]
        deal["headline_basis"] = {"source": "exhibit_title", "original": original,
                                  "method": SUBSTANCE_HEADLINE_REPAIR_METHOD}
    else:
        deal["headline_basis"] = {"source": "edgar_file_description", "original": original,
                                  "method": ("Headline is the EDGAR index description of the "
                                             "hit document, unchanged.")}
    return deal


def _deal_substance_text(deal: dict) -> str:
    """deal-1a — the exhibit's SUBSTANCE surface: the press-release title and
    the announcement sentence from the deal verb onward (never the filer's
    self-description before the verb). Lowercased for the word-bounded matcher."""
    sub = deal.get("substance")
    if not isinstance(sub, dict):
        return ""
    parts = [sub.get("title") or "", sub.get("lead_from_cue") or ""]
    return " \n ".join(str(x) for x in parts if x).lower()


def _deal_subject_text(deal: dict) -> str:
    """
    T111(c) — the deal's STATED SUBJECT, the only prose surface thesis terms
    may match: the EDGAR filing headline/description, the classified deal
    type, the Item 1.01 excerpt (the agreement's own description of itself),
    and the directional-cue sentence deal_parties extracted. Deliberately
    EXCLUDES party names, the full Exhibit 99.1 press release, and
    analyst_note: "about us" issuer boilerplate ("...developing treatments
    for <the profile's indication>...") inside an unrelated-disease press
    release scored 11 of 13 deals on-thesis for one class's report
    (CI review 2026-07-30 p40). Lowercased for the word-bounded matcher.
    deal-1a: a headline REPAIRED from an exhibit label carries the exhibit
    title here; the substance surface proper is _deal_substance_text.
    """
    p = deal.get("deal_parties") or {}
    parts = [
        deal.get("headline") or "",
        deal.get("deal_type") or "",
        deal.get("item_101_excerpt") or "",
        (p.get("snippet") or "") if isinstance(p, dict) else "",
    ]
    return " \n ".join(str(x) for x in parts if x).lower()


def _deal_asset_surface_text(deal: dict) -> str:
    """T111(c) — the TARGET-side pipeline surface: extracted asset names and
    the pipeline_crossref match token. Asset vocabulary may match here (an
    asset named in the target's pipeline is on-thesis evidence even when the
    subject sentence omits it). Lowercased for the word-bounded matcher."""
    parts = []
    assets = deal.get("assets_mentioned") or []
    if isinstance(assets, list):
        parts.extend(str(a) for a in assets)
    xref = deal.get("pipeline_crossref")
    if isinstance(xref, dict) and xref.get("matched_on"):
        parts.append(str(xref["matched_on"]))
    return " \n ".join(p for p in parts if p).lower()


def score_deal_thesis_relevance(
    deal: dict,
    focus_terms: Optional[list[str]],
    focus_term_aliases: Optional[dict[str, list[str]]] = None,
    thesis_vocab: Optional[dict[str, list[str]]] = None,
) -> dict:
    """
    Classify one EDGAR deal as on-thesis or adjacent for the active profile.

    Generic — no drug-class knowledge; all specificity comes from the
    profile-supplied vocabulary. T111(c) REPLACED loose whole-filing term
    matching: a term now counts only where its KIND is allowed to match —
      • asset terms (vocab key "assets"):     the target's extracted pipeline
        (assets_mentioned, pipeline_crossref) OR the deal's stated subject;
      • every other vocab key:                the deal's stated subject ONLY
        (headline, deal type, Item 1.01 excerpt, directional-cue sentence —
        see _deal_subject_text) and, deal-1a, the exhibit's SUBSTANCE (its
        title and its announcement sentence from the deal verb onward — see
        _deal_substance_text); press-release boilerplate never scores.
    `thesis_vocab` comes from profiles.defaults.get_deal_thesis_vocab; when
    None it is composed from `focus_terms` under the key "deal_focus_terms"
    (back-compat — the restricted surfaces still apply, and the emitted
    basis discloses the ungrouped list was in use). Aliases expand through
    focus_term_aliases exactly as before.

    Returns:
        {"on_thesis": bool, "confidence": str, "matched_terms": [str],
         "rationale": str, "basis": dict}
    `basis` (field_basis doctrine — an auditable record beside the verdict):
        {"matched": [{"term","vocab_key","surface"}],
         "surfaces_searched": [...], "method": <one methodology sentence>,
         "substance_method": <the substance strategy's sentence, or None>}
    `surface` is one of subject_text / exhibit_substance / asset_surface.
    confidence is one of:
      • "high"        — a vocabulary term/alias matched an allowed surface.
      • "provisional" — the filing matched the FOCUSED EFTS query AND no
                        scorable surface was extracted (no Item 1.01 text,
                        no cue sentence, no assets) — kept on-thesis, flagged
                        for verification. T111 NARROWED this path: when a
                        scorable subject EXISTS and no term matches, the
                        focused-query hit no longer keeps the deal on-thesis
                        (that is exactly the boilerplate false-positive).
      • "adjacent"    — no term matched an allowed surface.
      • "unfiltered"  — no vocabulary configured; cannot filter.
    """
    _METHOD_SENTENCE = (
        "Terms from the profile's deal-thesis vocabulary (aliases expanded) "
        "matched word-bounded against the target's extracted pipeline "
        "(assets_mentioned, pipeline_crossref) for asset terms and, for all "
        "terms, the deal's stated subject (EDGAR headline, deal type, Item 1.01 "
        "excerpt, directional-cue sentence) plus the exhibit's substance (its "
        "title and its announcement sentence from the deal verb onward); the "
        "filer's self-description and all remaining press-release/boilerplate "
        "text are excluded from scoring (T111; deal-1a)."
    )
    vocab = dict(thesis_vocab) if thesis_vocab else {}
    if not vocab and focus_terms:
        vocab = {"deal_focus_terms": list(focus_terms)}
    if not vocab:
        return {
            "on_thesis": True, "confidence": "unfiltered", "matched_terms": [],
            "rationale": (
                "No deal-thesis vocabulary (deal_thesis / deal_focus_terms) "
                "configured for this profile — thesis filtering skipped; all "
                "EDGAR deals shown."
            ),
            "basis": {"matched": [], "surfaces_searched": [],
                      "method": "no vocabulary configured; scoring skipped",
                      "substance_method": None},
        }

    subject_text   = _deal_subject_text(deal)
    substance_text = _deal_substance_text(deal)
    asset_text     = _deal_asset_surface_text(deal)
    surfaces_searched = (["subject_text"]
                         + (["exhibit_substance"] if substance_text else [])
                         + (["asset_surface"] if asset_text else []))
    _sub = deal.get("substance") if isinstance(deal.get("substance"), dict) else None

    matched: list[str] = []
    matched_detail: list[dict] = []
    for vkey, terms in vocab.items():
        allow_asset_surface = (vkey == "assets")
        variants = _expand_focus_variants(terms, focus_term_aliases)
        for term, vlist in variants.items():
            hit_surface = None
            for v in vlist:
                pat = _THESIS_TERM_BOUNDARY.format(term=re.escape(v))
                if allow_asset_surface and asset_text and re.search(pat, asset_text):
                    hit_surface = "asset_surface"
                    break
                if subject_text and re.search(pat, subject_text):
                    hit_surface = "subject_text"
                    break
                if substance_text and re.search(pat, substance_text):
                    hit_surface = "exhibit_substance"
                    break
            if hit_surface and term not in matched:
                matched.append(term)
                matched_detail.append({"term": term, "vocab_key": vkey,
                                       "surface": hit_surface})

    basis = {"matched": matched_detail, "surfaces_searched": surfaces_searched,
             "method": _METHOD_SENTENCE,
             "substance_method": (_sub or {}).get("method")}

    if matched:
        _keys = sorted({m["vocab_key"] for m in matched_detail})
        return {
            "on_thesis": True, "confidence": "high", "matched_terms": matched,
            "rationale": (
                f"On-thesis: profile deal-thesis term(s) {', '.join(matched)} "
                f"(vocab: {', '.join(_keys)}) matched the "
                f"{' and '.join(sorted({m['surface'] for m in matched_detail}))} "
                f"(SEC {deal.get('filing_form', '8-K')} accession "
                f"{deal.get('accession', '?')})."
            ),
            "basis": basis,
        }

    # deal-1a: the exhibit's substance is ADDITIVE only. It may score a term;
    # it never counts as the "scorable subject" whose silence demotes a focused
    # hit from provisional to adjacent — one announcement sentence cannot tell
    # a boilerplate match from a term in the release's second paragraph, and
    # the T111 demotion was calibrated on the agreement's own Item 1.01 text.
    subject_available = bool(subject_text.strip() and (
        deal.get("item_101_excerpt")
        or (deal.get("deal_parties") or {}).get("snippet")
        if isinstance(deal.get("deal_parties") or {}, dict)
        else deal.get("item_101_excerpt"))) or bool(asset_text)

    if deal.get("_hit_source") == "efts_focused" and not subject_available:
        _sub_clause = (
            " The press-release exhibit's title/announcement sentence WAS read "
            "and did not carry the term either (deal-1a), so the match sits "
            "deeper in the filing — verify"
            if substance_text else
            " No scorable subject surface (Item 1.01 text, directional-cue "
            "sentence, exhibit substance, extracted assets) was available to "
            "confirm or refute it — verify")
        return {
            "on_thesis": True, "confidence": "provisional", "matched_terms": [],
            "rationale": (
                "On-thesis (provisional): the 8-K matched a FOCUSED SEC EFTS "
                "full-text query built from this profile's deal_focus_terms."
                + _sub_clause
                + " against the source filing "
                f"(accession {deal.get('accession', '?')})."
            ),
            "basis": basis,
        }

    is_ticker = bool(deal.get("_ticker_match"))
    _via = ("the tracked-competitor submissions enumeration" if is_ticker
            else "a FOCUSED EFTS query whose term did not appear in the "
                 "deal's stated subject — likely issuer boilerplate elsewhere "
                 "in the filing (T111)"
            if deal.get("_hit_source") == "efts_focused"
            else "the broad EDGAR deal sweep")
    return {
        "on_thesis": False, "confidence": "adjacent", "matched_terms": [],
        "rationale": (
            "Adjacent: no profile deal-thesis term/alias matched the target's "
            "extracted pipeline, the deal's stated subject or the exhibit's "
            "substance; surfaced via "
            + _via
            + ". Routed to Adjacent BD Radar for situational awareness rather "
            "than the on-thesis Deal Tracker."
        ),
        "basis": basis,
    }


def deal_counterparty_resolved(deal: dict) -> bool:
    """T111(b) — SINGLE OWNER of "is the other side of this deal known?".

    True iff the row carries a non-empty extracted counterparty, or its
    deal_parties parse resolved BOTH sides of an acquisition (acquirer AND
    target) or a license (licensor AND licensee). Engine: pure deal grammar —
    no drug, company, class, or threshold knowledge.

    Consumers (keep this list current — it is why the test lives in ONE
    place): the URGENT-promotion gate in
    agents.report_pipeline.ensure_high_value_deal_flags, and the WATCH
    nomination producer in utils.nominations._nominate_deal_gaps. A row this
    function rejects must never reach actionable_flags.urgent through the
    deterministic floor: the live 2026-07-30 report's #1 URGENT flag was a
    high-value M&A half whose counterparty was unresolved — an alert the
    reader could not act on or verify against a named party.
    """
    if (deal.get("counterparty") or "").strip():
        return True
    p = deal.get("deal_parties") or {}
    if isinstance(p, dict):
        if (p.get("acquirer") or "").strip() and (p.get("target") or "").strip():
            return True
        if (p.get("licensor") or "").strip() and (p.get("licensee") or "").strip():
            return True
    return False


# ── deal-1b: OWN RECORDS — the run already knows these companies and assets ──
# THE DEFECT (TRACK §6.34g). A report tracked a company's asset as a
# combination partner in Section 9 and, in the same run, scored that company's
# $381M deal "no profile focus-term match". The scorer knew only the profile
# vocabulary; it never consulted what the run itself had already established
# from ClinicalTrials.gov and the profile's own declarations.
#
# THE FIX, in two tiers (ruling D3-113, option C):
#   asset tier   — the deal names, or its counterparty sponsors, an ASSET the
#                  run tracks (a trial_summary asset, a combination partner,
#                  a watchlist asset). Evidence about the DEAL: the vocabulary
#                  verdict is overturned to on-thesis, confidence "own_records",
#                  and the promotion is a structured, human-overturnable record.
#   company tier — only a COMPANY NAME matches (trial industry sponsor, profile
#                  asset_company_map, private/small-cap watchlist). Evidence
#                  about the COMPANY, not the deal: the vocabulary verdict
#                  STANDS, and the silence is refused — a conflict record is
#                  raised so an analyst rules (register below).
# Tracked competitors (competitor_company_names) are EXCLUDED from the index
# (ruling D5-113): the deal already carries _ticker_match and the radar already
# names them as tracked competitors deploying capital off-thesis.
#
# THE REGISTER (ruling D4-113, R1+R2). Analyst rulings live in the PROFILE
# (profile["deal_thesis_rulings"], read through profiles.defaults.
# get_deal_thesis_rulings): keyed by company, optionally narrowed to one
# accession; each carries verdict, reason, as_of and source_url. A ruling
# overrides both the vocabulary and the own-records verdicts and prints its
# reason, date and source on the page. Corrections never land in engine code.
#
# F-90-4 SHAPE (ruling D5-111): every judgement here is a record —
# {record_kind, code, decided, was, evidence, profile, accession, company,
# method} — collating on (code, section) with the f90-4a finding codes.
#
# ENGINE/PROFILE LINE (rules 1/10): name matching and list algebra only. No
# drug, company, class or indication term appears here; every name arrives
# from the run's trial records or the profile.

OWN_RECORDS_INDEX_METHOD = (
    "Own-records index built from this run: assets = the trial summary's asset keys, "
    "their combination partners (trial co-interventions, profile exclusions applied) "
    "and the profile's known_assets_watchlist / asset_company_map keys; companies = "
    "INDUSTRY lead sponsors of those assets' registered trials, asset_company_map "
    "values, and the private/small-cap watchlists (tickers resolved through the "
    "profile's ticker→name map, unresolved tickers listed); tracked competitors "
    "(competitor_company_names) are excluded because the deal record already marks "
    "them. Each entry keeps its source (NCT ids / profile key) and its admission basis "
    "(admitted_by) for the footnote (deal-1b); harvested names that cannot be shown to "
    "be assets are quarantined with a reason under assets_quarantined (F-115-e).")
OWN_RECORDS_CROSSCHECK_METHOD = (
    "Own-records cross-check: index asset names (profile aliases expanded; F-115-e "
    "hygiene gate applied, each with its admission basis) matched word-bounded against "
    "the deal's extracted assets, exhibit substance and stated subject (asset tier), a "
    "term that is a whole token of the deal's own party names being rejected as "
    "party_name; the deal's filer, counterparty and parsed parties matched "
    "by normalised company key against index companies (company tier). Asset tier "
    "overturns an adjacent vocabulary verdict to on-thesis (confidence own_records); "
    "company tier leaves the verdict and raises a conflict record for analyst ruling "
    "(deal-1b).")
DEAL_RULING_METHOD = (
    "Routing set by an analyst ruling in the profile's deal_thesis_rulings register "
    "(company-keyed, optionally narrowed to one accession); the ruling's reason, as_of "
    "and source_url are printed with the row, and the engine's own verdict is kept "
    "beside it as `was` (deal-1b).")

# ── F-115-e: THE ASSET HYGIENE GATE (TRACK §6.44b; T52 class) ─────────────────
# THE DEFECT. Index asset names were harvested from trial_summary keys and
# combo_partners with no check that the string IS a drug: the registry's
# fallback key ("Unknown"), an activity used as a trial comparator, and a
# fragment of a sponsor's corporate name all entered as "assets" and were
# matched word-bounded against filing text. Three of three reviewed deals were
# promoted on such a term — one on THE FILER'S OWN NAME, one on a word that
# appears in share-option boilerplate in every merger filing.
#
# THE RULE (ruling F-115-e/A, session 116: strict). A registry-harvested name
# is an asset only when this run can SHOW it is one:
#   registry_mesh        the registry's own interventionBrowseModule normalised
#                        it to a MeSH intervention term on >=1 trial of this run
#   coded_name           it carries a development-code shape (letters+digits:
#                        the shape of every pre-INN candidate)
#   profile_declaration  the profile names it (known_assets_watchlist,
#                        asset_company_map, focus_term_aliases) — always admitted
# Everything else is QUARANTINED, never deleted (R13a pattern: a visible
# non-credit with its reason): trial_grammar (arm vocabulary — placebo/
# comparator/activity words, which are registry grammar, not class knowledge),
# company_name (its normalised key is a sponsor / index company / tracked
# competitor of this run, or a single token of one — the filer's-own-name case),
# too_short, unattested_single_word / unattested_name. A quarantined name is
# promoted by the profile's existing known_assets_watchlist; no new profile key.
# ENGINE/PROFILE LINE holds: no drug, company, class or indication term below.

# Trial grammar, not class knowledge: arm labels that are never an asset.
_OWN_RECORDS_TRIAL_GRAMMAR = {"placebo", "saline", "standard of care", "no intervention",
                              "sham", "vehicle", "usual care", "best supportive care"}
# Single arm-vocabulary tokens (whole-word) that mark a registry string as a
# comparator, control or activity rather than a drug. English trial grammar.
_OWN_RECORDS_GRAMMAR_TOKENS = frozenset({
    "placebo", "saline", "sham", "vehicle", "control", "comparator", "unknown",
    "care", "exercise", "diet", "dietary", "lifestyle", "counseling",
    "counselling", "education", "educational", "training", "surgery",
    "surgical", "monitoring", "questionnaire", "survey", "program", "programme",
    "intervention", "observation", "supplement", "supplements",
})
# Development-code shape: a short letter prefix joined to a digit run
# (a hyphen or space allowed), optionally one trailing letter. Pharma
# nomenclature, not any company's scheme; dose fragments ("2.4 mg") do not
# match because the prefix must be letters and the digits must follow it.
_OWN_RECORDS_CODED_NAME_RE = re.compile(r"(?<![a-z0-9])[a-z]{1,6}[- ]?\d{2,8}[a-z]?(?![a-z0-9])")
# f115-e2: the letters-only development-code shape ("ZQ-VXPL"): a short
# all-caps prefix, a hyphen, an all-caps token, tested on the name in its RAW
# casing (the registry writes codes capitalised; a lower-case or mixed-case
# hyphenated string is a word pair, not a code). A class abbreviation whose
# suffix begins with a digit ("XYZ-1RA") does not match: the token after the
# hyphen must be letters. Measured at 116 against the run of record's
# quarantine list: fires on the two alphabetic codes, on nothing else.
_OWN_RECORDS_ALPHA_CODE_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,5}-[A-Z]{2,10}\d{0,4}(?![A-Za-z0-9])")
_OWN_RECORDS_COMPANY_KEY_STOP = {"and", "the", "of", "a", "s"}
# f115-e2 — THE REDUCED FORM. Registry strings decorate a drug name with dose,
# form and route ("Quorvane (10mg Tab)", "quorvane multidose pen"); the MeSH
# lookup compared the whole string and held real drugs as unattested. The gate
# now takes an ORDER-PRESERVING stripper from its caller (`name_core`, supplied
# by the runner from the single owner tools.clinicaltrials._asset_core_name —
# nothing is declared here) and:
#   * looks the reduced form up against the registry MeSH terms and the
#     profile declarations, both reduced the same way (core to core; the exact
#     form is tried first);
#   * keys the index entry by the reduced form on BOTH sides of the gate, so
#     every raw string of one drug folds onto one entry (the plain form is the
#     display name whenever the run saw one; every raw string folded in is kept
#     under harvested_as) and the footnote's matched_as states the reduced form;
#   * applies the profile's partner exclusions and too_short to the reduced
#     form as well.
# The grammar and company checks still run on the RAW string first. Without a
# stripper the gate behaves exactly as at 116.
#
# F-116-a — WHAT A REGISTRY MAPPING CAN ATTEST. The registry maps a study to
# MeSH terms by reading the sponsor's intervention names AND descriptions, and
# MeSH is one tree for drugs, drug classes and biological targets alike. Two
# shapes therefore passed as `registry_mesh` and one promoted a filing: a
# protein TARGET named in an antibody's description (a leaf term no sponsor
# ever typed as an intervention), and CLASS terms the registry itself lists as
# parents of other mappings ("... receptor agonists", form and activity words).
# Ruling C/118: a mapped term attests a name only when
#   * the registry does NOT list it under `intervention_mesh_ancestors` on any
#     trial of the run (a term the registry uses as a parent is a class node,
#     whatever a sponsor typed) — else refused as registry_class_term; and
#   * the registry ALSO names it as an intervention on some trial of the run:
#     the term's reduced form is a whole-token phrase inside an intervention
#     name's reduced form, or that name (>= 4 chars, not grammar) is a whole-
#     token phrase inside the term (the registry's salt/ester suffixes on a
#     name the sponsor wrote plain) — else refused as registry_unnamed.
# Both sides are reduced by the caller's stripper (f115-e2 rule). A harvested
# name whose only attestation was a refused term is HELD under the refusal's
# reason, so the reader of the held list sees which happened; a code-shaped
# name is still a coded_name asset (the code is evidence in itself). Reads two
# record keys the registry wrote; declares no term. Records from before the
# key existed carry no ancestors, so the class refusal is silent on them —
# counts.mesh_ancestor_terms makes that vintage visible.

ASSET_HYGIENE_METHOD = (
    "Asset hygiene gate (F-115-e): a name harvested from the run's trial records enters "
    "the own-records asset index only if the registry normalised it to a MeSH intervention "
    "term on at least one trial of this run (registry_mesh), or it carries a development-"
    "code shape (coded_name); names the profile declares are always admitted "
    "(profile_declaration). Every other harvested name is quarantined with its reason "
    "(trial_grammar, company_name, too_short, unattested_single_word, unattested_name) and "
    "listed, not deleted; a quarantined name is admitted by adding it to the profile's "
    "known_assets_watchlist. Dose, form and route words are removed from a harvested name "
    "before the lookups, every registry string of one drug is kept under one entry, and the "
    "reduced form is the term matched against the deal (the footnote states it); a "
    "development code may also be letters only (capitalised prefix, hyphen, capitalised "
    "token). A registry term attests a name only if the registry also names it as an "
    "intervention on some trial of the run and does not list it as a parent (class) term "
    "on any; a name whose only registry attestation fails those tests is held "
    "(registry_unnamed, registry_class_term). At match time a term that is a whole token "
    "of the deal's own party names is rejected (party_name) and listed under "
    "rejected_matches.")


def _own_asset_tokens(k: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", k) if t]


def _own_asset_admission(k: str, *, declared: bool, mesh_terms: set,
                         company_keys: set, company_tokens: set,
                         partner_filter=None, raw: str = "", core: str = "",
                         declared_cores=frozenset(),
                         mesh_cores=frozenset(),
                         mesh_refused=None) -> tuple[bool, str, str]:
    """(admitted, basis, key) for one normalised asset key under the F-115-e
    gate; `key` is the form the decision was made on — `k`, or the reduced form
    `core` when the name was attested (or held) only after dose/form/route
    stripping (f115-e2), so the caller keys the entry by it.
    `declared` = the profile named it. `mesh_terms` = the intervention_mesh
    terms of this run's trials that ATTEST (normalised; F-116-a: the caller has
    already removed the terms the registry lists as parents or never names as
    an intervention). `company_keys` / `company_tokens`
    = the run's sponsor and index company keys and their tokens. `partner_filter`
    = the universal registry-grammar filter supplied by the caller
    (tools.clinicaltrials.is_meaningful_combo_partner); None applies only the
    local grammar sets. `raw` = the name as the registry wrote it (the
    letters-only code shape is read in that casing). `core` = the reduced form
    from the caller's stripper (empty: no stripping); `declared_cores` /
    `mesh_cores` = the declarations and attesting MeSH terms reduced the same
    way. `mesh_refused` = {term or reduced term: refusal reason} for the mapped
    terms that do NOT attest (F-116-a); a name whose only registry attestation
    is such a term is held under that reason. Holds no drug, class or company
    vocabulary."""
    if not k:
        return False, "too_short", k
    reduced = bool(core) and core != k
    if declared:
        return True, "profile_declaration", k
    if reduced and core in declared_cores:
        return True, "profile_declaration", core
    toks = _own_asset_tokens(k)
    if any(t in _OWN_RECORDS_GRAMMAR_TOKENS for t in toks) or any(
            re.search(_THESIS_TERM_BOUNDARY.format(term=re.escape(g)), k)
            for g in _OWN_RECORDS_TRIAL_GRAMMAR):
        return False, "trial_grammar", k
    if callable(partner_filter):
        try:
            if not partner_filter(k):
                return False, "trial_grammar", k
        except Exception:
            pass
    if len(k) < 4 and not any(ch.isdigit() for ch in k):
        return False, "too_short", k
    ck = _own_company_key(k)
    if ck and ck in company_keys:
        return False, "company_name", k
    # A corporate designator (Inc, plc, Pharma, Therapeutics...) was stripped
    # by the company normaliser: the string is company-shaped.
    if set(toks) - set(ck.split()) - _OWN_RECORDS_COMPANY_KEY_STOP:
        return False, "company_name", k
    if len(toks) == 1 and toks[0] in company_tokens:
        return False, "company_name", k
    # Attestation: the exact form first, then the reduced form (core to core).
    if k in mesh_terms:
        return True, "registry_mesh", k
    if reduced and (core in mesh_terms or core in mesh_cores):
        return True, "registry_mesh", core
    if _OWN_RECORDS_CODED_NAME_RE.search(k) or (raw and _OWN_RECORDS_ALPHA_CODE_RE.search(raw)):
        return True, "coded_name", k
    # F-116-a: the registry mapped this name but the mapping does not attest
    # it; the hold names the refusal, filed under the form that was refused.
    refused = mesh_refused if isinstance(mesh_refused, dict) else {}
    if k in refused:
        return False, refused[k], k
    if reduced and core in refused:
        return False, refused[core], core
    # Not attested: the reason (and the key the hold is filed under) read the
    # reduced form when there is one, so "Quorvane 10 mg" is a held single word.
    basis_key = core if reduced else k
    if reduced and len(core) < 4 and not any(ch.isdigit() for ch in core):
        return False, "too_short", core
    alpha = [t for t in _own_asset_tokens(basis_key) if not any(ch.isdigit() for ch in t)]
    return False, ("unattested_single_word" if len(alpha) <= 1 else "unattested_name"), basis_key


def _own_asset_key(name) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _own_company_key(name, ticker_map=None) -> str:
    try:
        return normalize_company_key(str(name or ""), ticker_map=ticker_map,
                                     strip_descriptors=True)
    except Exception:
        return str(name or "").strip().lower()


def build_own_records_index(trial_summary, clinical_trials, *,
                            asset_company_map=None, known_assets=None,
                            private_companies=None, small_cap_tickers=None,
                            ticker_names=None, excluded_company_names=None,
                            partner_exclusions=None, focus_term_aliases=None,
                            partner_filter=None, name_core=None) -> dict:
    """The run's own records, indexed for the cross-check. Generic: every name
    arrives as an argument; nothing is declared here. Returns
    {"assets": {key: {"name", "sources": [...], "admitted_by": str,
                      "nct_ids": [...], "harvested_as": [...]}},
     "assets_quarantined": {key: {"name", "sources": [...], "reason": str,
                                  "nct_ids": [...], "harvested_as": [...]}},
     "companies": {key: {...}}, "excluded_companies": [...],
     "unresolved_tickers": [...], "method": str, "hygiene_method": str,
     "counts": {...}} (F-115-e: harvested names pass _own_asset_admission;
    focus_term_aliases and partner_filter feed that gate). f115-e2: `name_core`
    (callable str -> str, the caller's dose/form/route stripper) reduces every
    harvested name; the entry is keyed by the reduced form, raw strings of one
    drug fold onto it (harvested_as, present only when a folded string differs
    from the key), counts.assets_collapsed counts the folded ones so that
    assets + quarantined + collapsed = distinct harvested names; NCT ids are
    attached to quarantined entries too. None: no stripping (116 behaviour).
    F-116-a: "mesh_refused" {mapped term: reason} lists the registry mappings
    that do not attest (see the block above _own_asset_admission), and counts
    gains mesh_terms / mesh_ancestor_terms / mesh_terms_refused."""
    ts = trial_summary if isinstance(trial_summary, dict) else {}
    trials = clinical_trials if isinstance(clinical_trials, list) else []
    acm = asset_company_map if isinstance(asset_company_map, dict) else {}
    tmap = ticker_names if isinstance(ticker_names, dict) else {}
    excl_assets = {_own_asset_key(x) for x in (partner_exclusions or [])} | _OWN_RECORDS_TRIAL_GRAMMAR
    excl_companies = {_own_company_key(v) for v in (excluded_company_names or []) if v}

    assets: dict[str, dict] = {}
    quarantined: dict[str, dict] = {}
    companies: dict[str, dict] = {}

    # F-115-e: what this run can show. Declared names (the profile's), the
    # registry's MeSH intervention terms, and every company name the run
    # carries (sponsors of ALL scanned trials, profile company declarations,
    # tracked competitors) — the gate reads these and declares nothing itself.
    declared = {_own_asset_key(a) for a in (known_assets or [])} \
        | {_own_asset_key(a) for a in acm} \
        | {_own_asset_key(a) for a in (focus_term_aliases or {}) if isinstance(a, str)} \
        | {_own_asset_key(v) for vl in (focus_term_aliases or {}).values()
           for v in (vl if isinstance(vl, list) else []) if isinstance(v, str)}
    declared.discard("")
    mesh_mapped = {_own_asset_key(m) for rec in trials if isinstance(rec, dict)
                   for m in (rec.get("intervention_mesh") or []) if m}
    run_company_names = [rec.get("sponsor") for rec in trials
                         if isinstance(rec, dict) and rec.get("sponsor")] \
        + list(acm.values()) + list(private_companies or []) \
        + list(excluded_company_names or []) + list(tmap.values())
    company_keys = {_own_company_key(c, tmap) for c in run_company_names if c}
    company_keys.discard("")
    company_tokens = {t for ck in company_keys for t in ck.split() if len(t) >= 4}

    # f115-e2: the caller's stripper, applied to BOTH sides of every lookup.
    def _reduce(s) -> str:
        if not callable(name_core):
            return ""
        try:
            return str(name_core(str(s or "")) or "").strip()
        except Exception:
            return ""

    # F-116-a: which of the registry's mappings attest. Two registry-written
    # record keys, read the same way as intervention_mesh; nothing declared.
    ancestor_terms = {_own_asset_key(a) for rec in trials if isinstance(rec, dict)
                      for a in (rec.get("intervention_mesh_ancestors") or []) if a}
    named_forms: set = set()      # every intervention name the registry wrote, reduced
    for rec in trials:
        if not isinstance(rec, dict):
            continue
        for iv_key in ("interventions", "interventions_non_countable"):   # both keys (R13a)
            for iv in (rec.get(iv_key) or []):
                nm = iv.get("name") if isinstance(iv, dict) else iv
                if nm:
                    named_forms.add(_reduce(nm) or _own_asset_key(nm))
    named_forms.discard("")
    named_tokens = {n: _own_asset_tokens(n) for n in named_forms}

    def _phrase_in(needle: list, hay: list) -> bool:
        n = len(needle)
        return 0 < n <= len(hay) and any(hay[i:i + n] == needle for i in range(len(hay) - n + 1))

    def _registry_names(m: str) -> bool:
        """The registry wrote this mapped term as an intervention somewhere in
        the run: the term inside a name, or the name (a real word, not grammar)
        inside the term — the salt/ester suffix shape."""
        mt = _own_asset_tokens(_reduce(m) or m)
        if not mt:
            return False
        for n, nt in named_tokens.items():
            if _phrase_in(mt, nt):
                return True
            if len(n) >= 4 and not (set(nt) & _OWN_RECORDS_GRAMMAR_TOKENS) and _phrase_in(nt, mt):
                return True
        return False

    mesh_refused: dict[str, str] = {}
    for m in sorted(mesh_mapped):
        if m in ancestor_terms:
            mesh_refused[m] = "registry_class_term"
        elif not _registry_names(m):
            mesh_refused[m] = "registry_unnamed"
    mesh_terms = mesh_mapped - set(mesh_refused)
    declared_cores = {_reduce(d) for d in declared} - {""}
    mesh_cores = {_reduce(m) for m in mesh_terms} - {""}
    for m, why in list(mesh_refused.items()):        # the reduced forms carry the reason too,
        mc = _reduce(m)                              # unless an attesting term reduces there
        if mc and mc not in mesh_refused and mc not in mesh_terms and mc not in mesh_cores:
            mesh_refused[mc] = why
    seen_keys: set = set()          # every distinct harvested key that reached the gate
    collapsed = [0]                 # of those, the ones that folded onto another entry

    def _fold(ent, raw, src, key):
        """One more registry string for an entry that exists: keep its source;
        the plain form (whose own key IS the entry key) becomes the display
        name, every other raw string is kept under harvested_as."""
        ent["sources"].append(src)
        if _own_asset_key(raw) == key:
            if _own_asset_key(ent["name"]) != key:
                ent.setdefault("harvested_as", [])
                if ent["name"] not in ent["harvested_as"]:
                    ent["harvested_as"].append(ent["name"])
                ent["name"] = raw
        elif raw not in ent.get("harvested_as", []):
            ent.setdefault("harvested_as", []).append(raw)

    def _add_asset(name, src):
        raw = str(name).strip()
        k = _own_asset_key(name)
        if not k or k in excl_assets:
            return
        core = _reduce(raw)
        if core and core in excl_assets:
            return
        target = k if (k in assets or k in quarantined) else (
            core if core and core != k and (core in assets or core in quarantined) else None)
        if target is not None:
            _fold(assets.get(target) or quarantined[target], raw, src, target)
            if k not in seen_keys:
                seen_keys.add(k)
                collapsed[0] += 1
            return
        ok, basis, key = _own_asset_admission(
            k, declared=k in declared, mesh_terms=mesh_terms, company_keys=company_keys,
            company_tokens=company_tokens, partner_filter=partner_filter, raw=raw,
            core=core, declared_cores=declared_cores, mesh_cores=mesh_cores,
            mesh_refused=mesh_refused)
        ent = {"name": raw, "sources": [src]}
        if key != k:
            ent["harvested_as"] = [raw]
        seen_keys.add(k)
        if ok:
            ent["admitted_by"] = basis
            assets[key] = ent
        else:
            ent["reason"] = basis
            quarantined[key] = ent

    def _add_company(name, src):
        k = _own_company_key(name, tmap)
        if not k:
            return
        if k in excl_companies:
            return
        companies.setdefault(k, {"name": str(name).strip(), "sources": []})["sources"].append(src)

    # 1. trial summary: assets, their partners, their industry sponsors
    for asset, entry in ts.items():
        if not isinstance(entry, dict):
            continue
        _add_asset(asset, {"kind": "trial_summary", "ref": asset})
        for cp in (entry.get("combo_partners") or []):
            _add_asset(cp, {"kind": "combo_partner", "ref": asset})
        for sp in (entry.get("industry_sponsors") or []):
            _add_company(sp, {"kind": "trial_industry_sponsor", "ref": asset})

    # 2. profile declarations
    for a in (known_assets or []):
        _add_asset(a, {"kind": "profile:known_assets_watchlist", "ref": a})
    for a, c in acm.items():
        _add_asset(a, {"kind": "profile:asset_company_map", "ref": c})
        _add_company(c, {"kind": "profile:asset_company_map", "ref": a})
    for c in (private_companies or []):
        _add_company(c, {"kind": "profile:private_company_watchlist", "ref": c})
    unresolved = []
    for t in (small_cap_tickers or []):
        nm = tmap.get(t) if isinstance(t, str) else None
        if nm:
            _add_company(nm, {"kind": "profile:small_cap_watchlist", "ref": t})
        else:
            unresolved.append(t)

    # 3. NCT evidence: which registered trials name each asset / sponsor
    for rec in trials:
        if not isinstance(rec, dict):
            continue
        nct = rec.get("nct_id")
        names = set()
        for iv in (rec.get("interventions") or []):
            nm = iv.get("name") if isinstance(iv, dict) else iv
            if nm:
                names.add(_own_asset_key(nm))
        for nm in (rec.get("intervention_mesh") or []) + (rec.get("combo_partners") or []):
            if nm:
                names.add(_own_asset_key(nm))
        # f115-e2: quarantined entries are sourced to a trial as well, so the
        # held list can be read against the NCT record.
        for k, ent in list(assets.items()) + list(quarantined.items()):
            if k in names or any(k in n for n in names if len(k) >= 6):
                ent.setdefault("nct_ids", [])
                if nct and nct not in ent["nct_ids"]:
                    ent["nct_ids"].append(nct)
        if rec.get("sponsor_class") == "INDUSTRY" and rec.get("sponsor"):
            ck = _own_company_key(rec["sponsor"], tmap)
            if ck in companies:
                companies[ck].setdefault("nct_ids", [])
                if nct and nct not in companies[ck]["nct_ids"]:
                    companies[ck]["nct_ids"].append(nct)

    return {"assets": assets, "assets_quarantined": quarantined, "companies": companies,
            "excluded_companies": sorted(x for x in excl_companies if x),
            "unresolved_tickers": unresolved,
            # F-116-a: the registry's mappings the gate refused, with the reason,
            # and the three counts that make the rule's reach (and the record
            # vintage) visible: a run whose records carry no ancestors reads
            # mesh_ancestor_terms = 0 beside a non-zero mesh_terms.
            "mesh_refused": {m: why for m, why in mesh_refused.items() if m in mesh_mapped},
            "counts": {"assets": len(assets), "assets_quarantined": len(quarantined),
                       "assets_collapsed": collapsed[0],
                       "companies": len(companies), "trials_scanned": len(trials),
                       "mesh_terms": len(mesh_mapped), "mesh_ancestor_terms": len(ancestor_terms),
                       "mesh_terms_refused": sum(1 for m in mesh_refused if m in mesh_mapped)},
            "method": OWN_RECORDS_INDEX_METHOD, "hygiene_method": ASSET_HYGIENE_METHOD}


def _deal_party_names(deal: dict) -> list[tuple[str, str]]:
    """(field, name) for every company name the deal record carries."""
    out = []
    for f in ("company", "counterparty"):
        if (deal.get(f) or "").strip():
            out.append((f, deal[f].strip()))
    p = deal.get("deal_parties") or {}
    if isinstance(p, dict):
        for f in ("acquirer", "target", "licensor", "licensee"):
            v = (p.get(f) or "").strip() if isinstance(p.get(f), str) else ""
            if v:
                out.append((f"deal_parties.{f}", v))
    return out


def cross_check_deal_own_records(deal: dict, index: Optional[dict],
                                 focus_term_aliases: Optional[dict] = None) -> dict:
    """Two-tier match of one deal against the own-records index.
    Returns {"asset_matches": [...], "rejected_matches": [...], "company_matches": [...],
             "tier": str|None, "method": str}. Each match carries the record's
    sources/NCT ids and admission basis; F-115-e: a term that is a whole token
    of the deal's own party names is a rejected match (reason party_name)."""
    empty = {"asset_matches": [], "rejected_matches": [], "company_matches": [],
             "tier": None, "method": OWN_RECORDS_CROSSCHECK_METHOD}
    if not isinstance(index, dict) or not (index.get("assets") or index.get("companies")):
        return empty
    aliases = focus_term_aliases or {}
    text = " \n ".join(x for x in (
        _deal_asset_surface_text(deal), _deal_substance_text(deal), _deal_subject_text(deal)) if x)
    party_tokens = {t for _f, n in _deal_party_names(deal)
                    for t in _own_asset_tokens(_own_asset_key(n))}
    # f115-e2: an entry's display name may be the registry's decorated string,
    # so alias expansion is looked up by the entry KEY as well as by name.
    alias_by_key = {_own_asset_key(a): vl for a, vl in aliases.items()
                    if isinstance(a, str) and _own_asset_key(a)}
    asset_matches = []
    rejected_matches = []
    for k, ent in (index.get("assets") or {}).items():
        variants = [k]
        for a in list(aliases.get(ent.get("name"), []) or []) + list(alias_by_key.get(k, []) or []):
            av = _own_asset_key(a)
            if av and av not in variants:
                variants.append(av)
        for v in variants:
            if text and re.search(_THESIS_TERM_BOUNDARY.format(term=re.escape(v)), text):
                m = {"tier": "asset", "asset": ent.get("name"), "matched_as": v,
                     "sources": ent.get("sources", []), "nct_ids": ent.get("nct_ids", []),
                     "admitted_by": ent.get("admitted_by")}
                if v in party_tokens:
                    rejected_matches.append(dict(m, reason="party_name"))
                else:
                    asset_matches.append(m)
                break
    company_matches = []
    comp_idx = index.get("companies") or {}
    for field, name in _deal_party_names(deal):
        ck = _own_company_key(name)
        if ck and ck in comp_idx:
            ent = comp_idx[ck]
            company_matches.append({"tier": "company", "deal_field": field,
                                    "deal_name": name, "record_name": ent.get("name"),
                                    "sources": ent.get("sources", []),
                                    "nct_ids": ent.get("nct_ids", [])})
    tier = "asset" if asset_matches else ("company" if company_matches else None)
    return {"asset_matches": asset_matches, "rejected_matches": rejected_matches,
            "company_matches": company_matches,
            "tier": tier, "method": OWN_RECORDS_CROSSCHECK_METHOD}


def _find_deal_ruling(deal: dict, rulings) -> Optional[dict]:
    """Accession-narrowed ruling first, then a standing company ruling."""
    if not isinstance(rulings, list) or not rulings:
        return None
    acc = (deal.get("accession") or "").strip()
    names = {_own_company_key(n) for _f, n in _deal_party_names(deal)}
    by_acc = [r for r in rulings if isinstance(r, dict) and r.get("accession")
              and str(r["accession"]).strip() == acc]
    if by_acc:
        return by_acc[0]
    for r in rulings:
        if isinstance(r, dict) and not r.get("accession") \
                and _own_company_key(r.get("company")) in names:
            return r
    return None


def _evidence_labels(matches: list[dict]) -> list[str]:
    out = []
    for m in matches:
        srcs = sorted({s.get("kind", "?") for s in m.get("sources", []) if isinstance(s, dict)})
        ncts = m.get("nct_ids") or []
        who = m.get("asset") or m.get("record_name") or "?"
        lab = f"{who} ({', '.join(srcs)}"
        if ncts:
            lab += "; " + ", ".join(ncts[:3]) + (f" +{len(ncts) - 3}" if len(ncts) > 3 else "")
        if m.get("admitted_by"):
            lab += "; admitted: " + str(m["admitted_by"]).replace("_", " ")
            # f115-e2: the term actually matched, when it is not the name as
            # written (a reduced dose/form/route-stripped form, or an alias).
            if m.get("matched_as") and _own_asset_key(who) != m["matched_as"]:
                lab += f" (as {m['matched_as']})"
        out.append(lab + ")")
    return out


def _review_record(code: str, decided: str, was: str, evidence, deal: dict,
                   profile_ident: Optional[dict], method: str) -> dict:
    return {"record_kind": "deal_thesis_review", "code": code, "decided": decided,
            "was": was, "evidence": evidence, "profile": dict(profile_ident or {}),
            "accession": deal.get("accession"), "company": deal.get("company"),
            "method": method}


def _vocab_terms_lower(thesis_vocab, focus_term_aliases) -> set[str]:
    out = set()
    for _k, terms in (thesis_vocab or {}).items():
        for t, vl in _expand_focus_variants(terms, focus_term_aliases).items():
            out.update(vl)
    return out


def resolve_deal_thesis(deal: dict, focus_terms, focus_term_aliases=None,
                        thesis_vocab=None, own_records: Optional[dict] = None,
                        rulings=None, profile_ident: Optional[dict] = None) -> dict:
    """The routing decision with every override recorded. Order:
    analyst ruling > own-records asset tier > vocabulary scorer; company-tier
    own-records matches never change the verdict but always leave a record.
    Returns the scorer's dict plus "review": [records], "own_records": xc."""
    vocab_v = score_deal_thesis_relevance(deal, focus_terms, focus_term_aliases,
                                          thesis_vocab=thesis_vocab)
    review: list[dict] = []
    xc = cross_check_deal_own_records(deal, own_records, focus_term_aliases)
    vocab_set = _vocab_terms_lower(thesis_vocab, focus_term_aliases)

    ruling = _find_deal_ruling(deal, rulings)
    if ruling:
        on = ruling.get("verdict") == "on_thesis"
        decided = "on_thesis" if on else "adjacent"
        rationale = (
            f"{'On-thesis' if on else 'Adjacent'} per analyst ruling "
            f"({ruling.get('as_of')}; {ruling.get('source_url')}): {ruling.get('reason')} "
            f"[engine verdict was {vocab_v['confidence']}"
            + (f"; own records: {xc['tier']} tier" if xc.get("tier") else "") + "].")
        review.append(_review_record("deal.thesis_ruling_applied", decided,
                                     vocab_v["confidence"], [dict(ruling)], deal,
                                     profile_ident, DEAL_RULING_METHOD))
        return {"on_thesis": on, "confidence": "analyst_ruling",
                "matched_terms": vocab_v["matched_terms"], "rationale": rationale,
                "basis": dict(vocab_v["basis"], ruling=dict(ruling),
                              ruling_method=DEAL_RULING_METHOD),
                "review": review, "own_records": xc}

    if xc.get("tier") == "asset" and vocab_v["confidence"] in ("adjacent", "provisional"):
        labels = _evidence_labels(xc["asset_matches"])
        review.append(_review_record("deal.thesis_promoted_by_own_records", "on_thesis",
                                     vocab_v["confidence"], xc["asset_matches"], deal,
                                     profile_ident, OWN_RECORDS_CROSSCHECK_METHOD))
        gaps = [m for m in xc["asset_matches"]
                if _own_asset_key(m.get("matched_as")) not in vocab_set]
        if gaps:
            review.append(_review_record("deal.thesis_vocab_gap", "on_thesis",
                                         vocab_v["confidence"], gaps, deal, profile_ident,
                                         "An asset this run tracks through its own trial "
                                         "records or profile declarations carried the deal "
                                         "on-thesis but is absent from the profile's "
                                         "deal_thesis vocabulary (aliases expanded); the "
                                         "analyst decides whether the vocabulary should "
                                         "name it (deal-1b)."))
        return {"on_thesis": True, "confidence": "own_records",
                "matched_terms": vocab_v["matched_terms"],
                "rationale": (
                    "On-thesis (own records): the deal names or its parties sponsor an "
                    "asset this run already tracks — " + "; ".join(labels)
                    + f" — while no profile vocabulary term matched (engine verdict was "
                      f"{vocab_v['confidence']}). Human-overturnable; see deal_thesis_rulings."),
                "basis": dict(vocab_v["basis"], own_records=xc),
                "review": review, "own_records": xc}

    if xc.get("tier") == "company" and not vocab_v["on_thesis"]:
        review.append(_review_record("deal.thesis_own_records_conflict", "adjacent",
                                     vocab_v["confidence"], xc["company_matches"], deal,
                                     profile_ident, OWN_RECORDS_CROSSCHECK_METHOD))
        out = dict(vocab_v)
        out["rationale"] = (vocab_v["rationale"] + " NOTE: "
                            + "; ".join(_evidence_labels(xc["company_matches"]))
                            + " appears in this run's own records — adjacency is a "
                              "vocabulary verdict only; an analyst ruling in "
                              "deal_thesis_rulings can promote it (deal-1b).")
        out["basis"] = dict(vocab_v["basis"], own_records=xc)
        out["review"] = review
        out["own_records"] = xc
        return out

    out = dict(vocab_v)
    out["review"] = review
    out["own_records"] = xc
    return out


def partition_deals_by_thesis(
    deals: list[dict],
    focus_terms: Optional[list[str]],
    focus_term_aliases: Optional[dict[str, list[str]]] = None,
    thesis_vocab: Optional[dict[str, list[str]]] = None,
    own_records: Optional[dict] = None,
    rulings: Optional[list] = None,
    profile_ident: Optional[dict] = None,
) -> tuple[list[dict], list[dict]]:
    """
    Split deals into (on_thesis, adjacent), tagging each deal in place with
    thesis_on / thesis_confidence / thesis_matched_terms / thesis_rationale /
    thesis_basis (T111(c): the auditable matched-vocabulary record) and, deal-1b,
    thesis_review (the list of structured override records — empty when the
    vocabulary verdict stood unchallenged). Generic; input order is preserved
    within each bucket. own_records / rulings / profile_ident are optional: a
    caller passing none of them gets the T111 behaviour exactly.
    """
    on_thesis: list[dict] = []
    adjacent:  list[dict] = []
    for d in deals:
        verdict = resolve_deal_thesis(d, focus_terms, focus_term_aliases,
                                      thesis_vocab=thesis_vocab,
                                      own_records=own_records, rulings=rulings,
                                      profile_ident=profile_ident)
        d["thesis_on"]            = verdict["on_thesis"]
        d["thesis_confidence"]    = verdict["confidence"]
        d["thesis_matched_terms"] = verdict["matched_terms"]
        d["thesis_rationale"]     = verdict["rationale"]
        d["thesis_basis"]         = verdict.get("basis")
        d["thesis_review"]        = verdict.get("review") or []
        (on_thesis if verdict["on_thesis"] else adjacent).append(d)
    return on_thesis, adjacent


def deal_to_adjacent_radar_item(deal: dict) -> dict:
    """
    Convert an off-thesis deal into an Adjacent BD Radar CANDIDATE item
    (title / summary / why_adjacent / source_url / source_label). The Group-4
    relevance gate then decides whether the candidate is BD-relevant enough to
    surface — nothing is dropped here. Generic.
    """
    company = deal.get("company") or "Unknown filer"
    cp      = deal.get("counterparty")
    dtype   = deal.get("deal_type") or "BD filing"
    title   = f"{company} — {dtype}" + (f" / {cp}" if cp else "")
    val     = deal.get("deal_value_usd")
    summary = deal.get("headline") or deal.get("analyst_note") or f"SEC 8-K {dtype}"
    if val:
        summary = f"{summary} (value: {val})"
    is_ticker = bool(deal.get("_ticker_match"))
    why = (
        f"Tracked competitor {company} deployed capital via {dtype} outside this "
        f"report's therapeutic thesis — assess for competitor capital-allocation "
        f"read-through."
        if is_ticker else
        "Surfaced by the SEC deal sweep with no profile focus-term match; include "
        "only if an indirect link to the core class exists."
    )
    # deal-1a: a headline repaired from a bare exhibit label discloses the
    # repair beside the datum (rule 2) — the reader sees the release title and
    # the footnote says where it came from and what EDGAR had said.
    _hb = deal.get("headline_basis") if isinstance(deal.get("headline_basis"), dict) else {}
    _hl_note = (f"; headline is the EX-99 press-release title (EDGAR index "
                f"description was {_hb.get('original') or 'empty'!r})"
                if _hb.get("source") == "exhibit_title" else "")
    return {
        "title":        title,
        "summary":      summary,
        "why_adjacent": why,
        "source_url":   deal.get("filing_index_url"),
        "source_label": (
            f"SEC EDGAR {deal.get('filing_form', '8-K')}, accession {deal.get('accession', '?')}; "
            f"thesis-classified ADJACENT — {deal.get('thesis_rationale', '')}{_hl_note}"
        ),
        # Marks a SOURCED, validated deal (vs a soft preprint/industry candidate)
        # so downstream reconciliation can guarantee it renders rather than
        # leaving its inclusion to an LLM relevance gate.
        "_source_kind": "sec_deal",
        "_accession":   deal.get("accession"),
    }


def get_deal_tracker(
    competitor_tickers: list[str],
    days_back:          int = 30,
    max_per_query:      int = 20,
    pharma_sic_only:    bool = True,
    # NEW: inject the two sec_edgar functions to avoid circular import
    filing_text_fn=None,       # get_filing_text from sec_edgar.py
    extract_fn=None,           # extract_relevant_paragraphs from wherever it lives
    keywords:           Optional[list[str]] = None,
    focus_terms:        Optional[list[str]] = None,   
    focus_term_aliases: Optional[dict[str, list[str]]] = None,
    # Ticker → company-name hints (from profile["competitor_company_names"]),
    # used ONLY to resolve foreign/OTC tickers the primary CIK map misses.
    company_name_hints: Optional[dict[str, str]] = None,
) -> list[dict]:
    """
    Pull BD deals from SEC 8-K filings filed in the last `days_back` days.

    Strategy:
      1. Run each DEAL_QUERY_CLUSTER phrase search against 8-K filings.
      2. Optionally also search by specific competitor tickers using
         the submissions API (reliable company-level 8-K enumeration).
      3. Deduplicate by accession number.
      4. For each unique accession, extract deal metadata from the filing
         index page (deal type, dollar value, counterparties).

    Args:
        competitor_tickers: e.g. ["NVO", "LLY", "AZN", "PFE"]
        days_back:          Look-back window in days. Default: 30.
        max_per_query:      Max EFTS hits per phrase cluster. Default: 20.
        pharma_sic_only:    Filter to SIC 2830-2836 + 8731-8734. Default: True.

    Returns:
        List of deal dicts, newest first.
    """
    PHARMA_SICS = [str(s) for s in range(2830, 2837)] + \
                  [str(s) for s in range(8731, 8735)]
    sic_filter = PHARMA_SICS if pharma_sic_only else None

    focus_term_aliases = focus_term_aliases or {}

    if focus_terms:
        def _expand_term(term: str) -> list[str]:
            aliases = focus_term_aliases.get(term, [])
            seen: set[str] = set()
            result = []
            for t in [term] + aliases:
                if t.lower() not in seen:
                    seen.add(t.lower())
                    result.append(t)
            return result

    print(f"  DealTracker: window={days_back}d  focus_terms={focus_terms}  tickers={competitor_tickers}")

    # ── 1. Phrase-cluster full-text search ───────────────────────────────
    seen_accessions: set[str] = set()
    raw_hits: list[dict]      = []

    # Coverage instrumentation. MUST be created before _add_hit() is defined:
    # that nested function closes over `funnel` and runs during acquisition
    # (stage 1), long before the results/counters block further down.
    funnel = DealFunnel()

    # Index for O(1) promotion of broad hits to efts_focused
    accession_to_hit: dict[str, dict] = {}

    # ── 1a. Broad phrase-cluster search ──────────────────────────────────────
    # Skip broad search when focus_terms are provided — the focused queries
    # (1b) are strict supersets of the broad clusters AND require the
    # therapeutic keyword, so they are both more relevant and more targeted.
    # Running 1a first poisons seen_accessions with unrelated pharma filings
    # that then can never be upgraded to efts_focused, causing the runner's
    # focus-term pre-filter to drop them.  When focus_terms is empty we still
    # want the broad sweep as a fallback.
    run_broad = not bool(focus_terms)
    if run_broad:
        hits = _fetch_deal_8ks_batch(DEAL_QUERY_CLUSTERS, days_back, max_per_query, sic_filter)
        for h in hits:
            if h["accession"] not in seen_accessions:
                seen_accessions.add(h["accession"])
                h["hit_source"] = "efts"
                accession_to_hit[h["accession"]] = h
                raw_hits.append(h)
                funnel.hit("efts")

    # ── 1b. Focused therapeutic-area search ──────────────────────────────────
    # KEY: No OR groups or parentheses — EFTS standard urlencode path does not
    # support them. Run each term/alias as its own query and deduplicate.
    # This matches the pattern that produced real hits in run 1 (broad queries).
    if focus_terms:
        def _expand_term(term: str) -> list[str]:
            """Return term + all known brand/alias variants, deduplicated."""
            aliases = focus_term_aliases.get(term, [])
            seen: set[str] = set()
            result = []
            for t in [term] + aliases:
                if t.lower() not in seen:
                    seen.add(t.lower())
                    result.append(t)
            return result

        def _add_hit(h: dict) -> None:
            """Add hit if new; upgrade efts→efts_focused if already seen."""
            acc = h["accession"]
            if acc not in seen_accessions:
                seen_accessions.add(acc)
                h["hit_source"] = "efts_focused"
                accession_to_hit[acc] = h
                raw_hits.append(h)
                funnel.hit("efts_focused")
            else:
                existing = accession_to_hit.get(acc)
                if existing and existing.get("hit_source") == "efts":
                    existing["hit_source"] = "efts_focused"
                    # Re-tiering an existing hit is NOT a new candidate. Move the
                    # tally across sources so `1_acquire` stays an exact count.
                    funnel.hits_by_source["efts"] = max(
                        0, funnel.hits_by_source.get("efts", 0) - 1)
                    funnel.hits_by_source["efts_focused"] = (
                        funnel.hits_by_source.get("efts_focused", 0) + 1)

        for term in focus_terms:
            for variant in _expand_term(term):
                # Build all queries for this variant at once
                tier1_queries = [f'"{variant}" {cluster}' for cluster in DEAL_QUERY_CLUSTERS]
                tier2_queries = [f'"{variant}" {broad}' for broad in DEAL_BROAD_CLUSTERS]
                all_queries = tier1_queries + tier2_queries

                _vprint(f"  DealTracker focused batch for '{variant}': {len(all_queries)} queries")
                hits = _fetch_deal_8ks_batch(all_queries, days_back, max_per_query, sic_filter)
                for h in hits:
                    _add_hit(h)

        efts_unique = len([h for h in raw_hits if h.get("hit_source") == "efts_focused"])
        print(f"  DealTracker EFTS phase complete: {efts_unique} unique focused hits")

    # ── 2. Company-level 8-K enumeration (submissions API) ──────────────
    # The submissions API requires zero-padded 10-digit CIK numbers, NOT tickers.
    start_cutoff = date.today() - timedelta(days=days_back)
    ticker_to_cik = _resolve_ticker_ciks(competitor_tickers, name_hints=company_name_hints)
    ticker_entity_names: set[str] = set()


    for ticker in competitor_tickers:
        cik_padded = ticker_to_cik.get(ticker.upper())
        if not cik_padded:
            print(f"  DealTracker submissions: {ticker} — CIK not resolved, skipping")
            continue
        print(f"  DealTracker submissions: {ticker} (CIK {cik_padded})")
        data = _get_json(
            f"{SUBMISSIONS_URL}/CIK{cik_padded}.json",
            headers=HEADERS_SEC,
        )
        if not data:
            continue

        company_name = data.get("name", ticker)
        ticker_entity_names.add(company_name.lower())
        filings      = data.get("filings", {}).get("recent", {})
        forms        = filings.get("form", [])
        dates        = filings.get("filingDate", [])
        accessions   = filings.get("accessionNumber", [])
        descriptions = filings.get("primaryDocument", [])
        doc_descs    = filings.get("primaryDocDescription", [])

        items_list = filings.get("items", [])

        for i, (form, fdate, acc, desc) in enumerate(zip(forms, dates, accessions, descriptions)):
            # 8-K/8-K-A: US domestic issuers' current reports.
            # 6-K/6-K-A: the foreign-private-issuer equivalent (Roche, Novartis,
            #   etc. do NOT file 8-K) — required for their deals to surface at all.
            #   This is naturally bounded: domestic issuers file no 6-K and foreign
            #   issuers file no 8-K, so adding 6-K only pulls foreign-issuer rows,
            #   which the downstream deal classifier/prefilter still vets for noise.
            if form not in ("8-K", "8-K/A", "6-K", "6-K/A"):
                continue
            try:
                filing_date = datetime.strptime(fdate, "%Y-%m-%d").date()
            except ValueError:
                continue
            if filing_date < start_cutoff:
                continue
            # Count the candidate BEFORE the dedupe test: EDGAR returned it, so it
            # entered the funnel. Dropping it first made dropped_total exceed
            # (acquired − emitted) by exactly the number of duplicates.
            funnel.hit("submissions")
            if acc in seen_accessions:
                funnel.drop(STAGE_DEDUPE, REASON_DUPLICATE,
                            {"entity": company_name, "accession": acc, "file_date": fdate})
                continue

            seen_accessions.add(acc)
            cik_num    = data.get("cik", "0").lstrip("0")
            acc_clean  = acc.replace("-", "")
            item_code  = items_list[i] if i < len(items_list) else ""
            item_str   = str(item_code)
            doc_desc   = doc_descs[i] if i < len(doc_descs) else ""

            # 6-K PRE-FETCH housekeeping drop: if the submissions-index subject is
            # a purely administrative notice (share repurchase, PDMR dealing,
            # voting rights, block listing…), drop it now so it never consumes the
            # fetch budget and crowd out a real deal 6-K. Best-effort — when the
            # description is uninformative the fetch-stage backstop still catches
            # it. Only 6-Ks are gated (8-K items are handled below).
            if form in ("6-K", "6-K/A") and _is_housekeeping_6k(doc_desc):
                funnel.drop(STAGE_FETCH, REASON_6K_HOUSEKEEPING,
                            {"entity": company_name, "accession": acc, "file_date": fdate},
                            detail=f"6-K administrative notice: {doc_desc[:60]}")
                continue

            # has_101: Item 1.01 "Entry into Material Definitive Agreement"
            has_101 = "1.01" in item_str
            # has_801: Item 8.01 "Other Events" — sometimes used for deal press releases
            has_801 = "8.01" in item_str
            # Items field may be empty for large filers; don't skip solely on that
            items_empty = not item_str.strip() or item_str in ("", "nan", "None", "[]")

            # For tracked competitors: fetch if 1.01 present, items empty, or 8.01 present.
            # Only skip if items explicitly lists non-deal items (2.02 earnings, 5.02 officer, etc.)
            NON_DEAL_ONLY_ITEMS = {"2.02", "5.02", "5.03", "7.01", "9.01"}
            explicit_items = set(re.findall(r"\d+\.\d+", item_str))
            is_non_deal_only = bool(explicit_items) and explicit_items.issubset(NON_DEAL_ONLY_ITEMS)

            should_skip = is_non_deal_only and not has_101 and not has_801

            raw_hits.append({
                "entity":       company_name,
                "file_date":    fdate,
                "accession":    acc,
                "description":  desc,
                "doc_description": doc_desc,
                "form":         form,
                "sic_codes":    [],
                "filing_index": f"{ARCHIVES_URL}/{cik_num}/{acc_clean}/{acc}-index.htm",
                "cik":          data.get("cik", ""),
                "hit_source":   "submissions",
                "skip_fetch":   should_skip,
                "has_101":      has_101,
            })
            
    # Prioritise: ticker matches first, then by date
    def _hit_sort_key(h):
        is_ticker = h["entity"].lower() in ticker_entity_names
        return (0 if is_ticker else 1, h["file_date"])

    # ── 3. Enrich each hit ────────────────────────────────────────────────────
    # Build from competitor company names resolved via submissions API
    # These are populated in the submissions loop above
    # ticker_entity_names: set[str] = set()
    # for ticker in competitor_tickers:
    #     cik_padded = ticker_to_cik.get(ticker.upper())
    #     if not cik_padded:
    #         continue
    #     data = _get_json(
    #         f"{SUBMISSIONS_URL}/CIK{cik_padded}.json",
    #         headers=HEADERS_SEC,
    #     )
        # if data:
        #     ticker_entity_names.add(data.get("name", "").lower())

    results: list[dict]  = []
    efts_fetched         = 0   # counts efts + efts_focused fetches
    submissions_fetched  = 0

    # Sort: efts_focused first (most targeted), then ticker submissions, then broad efts
    sorted_hits = sorted(
        raw_hits,
        key=lambda h: (
            2 if h.get("hit_source") == "efts_focused" else
            1 if h["entity"].lower() in ticker_entity_names else
            0,
            h["file_date"]
        ),
        reverse=True
    )

    for hit in sorted_hits:
        desc      = hit.get("description", "")
        deal_type = _classify_deal(desc) if desc else None

        deal = {
            "source":             "SEC_EDGAR_8K",
            "company":            hit["entity"],
            "filed_date":         hit["file_date"],
            "days_since_filed":   (
                date.today() - datetime.strptime(hit["file_date"], "%Y-%m-%d").date()
            ).days if hit["file_date"] else None,
            "is_new_this_week":   (
                (date.today() - datetime.strptime(hit["file_date"], "%Y-%m-%d").date()).days <= 7
            ) if hit["file_date"] else False,
            "accession":          hit["accession"],
            "filing_index_url":   hit["filing_index"],
            # Actual EDGAR form type. Submissions hits carry it (8-K vs a foreign
            # issuer's 6-K); EFTS full-text hits target 8-Ks, so default to 8-K.
            "filing_form":        hit.get("form") or "8-K",
            "deal_type":          deal_type,
            "counterparty":       None,
            "deal_value_usd":       None,
            "deal_direction":       None,
            "deal_direction_kind":  None,
            "filer_role":           None,
            "counterparty_role":    None,
            "deal_parties":         None,
            "deal_direction_note":  None,
            "deal_economics":       None,
            "deal_economics_note":  None,
            "assets_mentioned":   [],
            "item_101_excerpt":   None,
            "exhibit_99_excerpt": None,
            "headline":           desc,
            "pipeline_crossref":  None,
            "analyst_note":       None,
        }

        hit_source      = hit.get("hit_source", "efts")
        is_ticker_match = hit["entity"].lower() in ticker_entity_names

        # ── skip_fetch override ───────────────────────────────────────────────
        # submissions hits only set skip_fetch=True when the items field showed
        # no 1.01 — but for tracked tickers we ALWAYS want to fetch and confirm,
        # because large companies (LLY, AMGN) sometimes file 8-Ks where the
        # items list is incomplete or absent in the submissions JSON.
        skip_fetch = hit.get("skip_fetch", False) and not is_ticker_match

        # ── fetch cap ────────────────────────────────────────────────────────
        # efts_focused hits are never capped — they are the most targeted signal.
        # Broad efts and submissions hits share separate caps.
        over_cap = (
            (hit_source == "efts"        and efts_fetched        >= 10) or
            (hit_source == "submissions" and submissions_fetched >= 15)
        )
        # efts_focused: not capped, counts against efts_fetched for diagnostics only

        deal["_ticker_match"]  = is_ticker_match   # runner can use this to relax filter
        deal["_hit_source"]    = hit_source         # thesis scorer: efts_focused = strong on-thesis signal

        if over_cap or skip_fetch:
            funnel.defer(STAGE_FETCH, REASON_CAP_DEFERRED, hit,
                         detail=f"hit_source={hit_source}, over_cap={over_cap}, skip_fetch={skip_fetch}")

        if filing_text_fn and not over_cap and not skip_fetch:
            urls = _resolve_document_urls(hit["filing_index"])

            _vprint(f"  [DIAG] {hit['entity'][:40]}")
            _vprint(f"         index:   {hit['filing_index']}")
            _vprint(f"         primary: {urls['primary']}")
            _vprint(f"         ex99:    {urls['exhibit_99']}")

            raw      = ""
            ex99_text = ""
            item_101  = ""

            if urls["primary"]:
                raw = filing_text_fn(urls["primary"], max_chars=100000)
                if hit_source == "submissions":
                    submissions_fetched += 1
                else:
                    efts_fetched += 1

            if urls["exhibit_99"]:
                ex99_text = filing_text_fn(urls["exhibit_99"], max_chars=60000)
                deal["exhibit_99_excerpt"], deal["exhibit_99_excerpt_basis"] = \
                    _excerpt_with_basis(ex99_text)

            rich_text = ex99_text or raw

            _vprint(f"         raw len:  {len(raw)}")
            _vprint(f"         ex99 len: {len(ex99_text)}")

            if raw:
                item_101 = _extract_item_101(raw)
                deal["item_101_excerpt"], deal["item_101_excerpt_basis"] = \
                    _excerpt_with_basis(item_101)
                _vprint(f"         item_101: {len(item_101)} chars")

            is_deal = any(
                re.search(p, (raw + " " + ex99_text)[:8000], re.IGNORECASE)
                for p in DEAL_CONFIRM_PATTERNS
            )

            # Explicit non-deal signals — suppress even ticker matches for these
            NON_DEAL_PATTERNS = [
                r"item\s*2\.02",                            # earnings release
                r"results of operations",
                r"quarterly.*earnings",
                r"item\s*5\.02.*director|officer",          # personnel change
            ]
            is_confirmed_non_deal = any(
                re.search(p, raw[:4000], re.IGNORECASE) for p in NON_DEAL_PATTERNS
            ) and not is_deal

            _vprint(f"         is_deal: {is_deal}  ticker_match: {is_ticker_match}  non_deal: {is_confirmed_non_deal}")

            # 6-K FETCH-STAGE housekeeping backstop: catches administrative 6-Ks
            # whose submissions-index description was blank/uninformative (so the
            # pre-fetch drop missed them). Guarded by `not is_deal` so a 6-K that
            # also announces a deal is never discarded.
            if (hit.get("form") in ("6-K", "6-K/A") and not is_deal
                    and _is_housekeeping_6k((raw or "")[:3000])):
                _vprint(f"         *** DROPPED — 6-K administrative notice (housekeeping) ***")
                funnel.drop(STAGE_FETCH, REASON_6K_HOUSEKEEPING, hit,
                            detail="6-K administrative notice (post-fetch)")
                continue

            if is_confirmed_non_deal:
                _vprint(f"         *** DROPPED — confirmed non-deal filing (earnings/personnel) ***")
                funnel.drop(STAGE_CLASSIFY, REASON_CONFIRMED_NON_DEAL, hit)
                continue

            if not is_deal and not is_ticker_match:
                _vprint(f"         *** DROPPED — not confirmed as deal filing ***")
                funnel.drop(STAGE_CLASSIFY, REASON_NO_DEAL_LANGUAGE, hit,
                            detail="no deal language in extracted text; not a tracked ticker")
                continue

            if not is_deal and is_ticker_match:
                # Tracked ticker, not confirmed deal but not a confirmed non-deal either —
                # keep as low-confidence, runner can decide
                deal["analyst_note"] = (
                    "8-K filed by tracked competitor; deal language not confirmed "
                    f"in extracted text. Review manually: {hit['filing_index']}"
                )
                deal["_confidence"] = "low"
                results.append(deal)
                continue

            # ── Enrichment from confirmed deal text ──────────────────────────
            # full_text is the larger window — used to disambiguate M&A vs
            # Agreement Termination when M&A language falls outside item_101[:3000]
            full_text_for_class = (raw + " " + ex99_text)[:8000]
            deal["deal_type"] = _classify_deal(
                item_101 or rich_text[:3000],
                full_text=full_text_for_class,
            )

            # Drop non-BD filings caught by the classifier (debt, ATM, employment)
            if deal["deal_type"] and deal["deal_type"].startswith("Non-BD:"):
                _vprint(f"         *** DROPPED — {deal['deal_type']} (not a pharma BD event) ***")
                funnel.drop(STAGE_CLASSIFY, REASON_NON_BD, deal, detail=deal["deal_type"])
                continue

            # ── Structured deal-economics extraction ──────────────────────────
            # Replaces positional `DOLLAR_RE.findall(...)[0]` (which grabbed the
            # first dollar figure — often a par value or prior-year revenue) with
            # cue-anchored, scale-normalized parsing that classifies each amount
            # as upfront / milestone / total / equity / royalty. Objective and
            # cacheable — no profile policy here; the runner applies the
            # (profile-tunable) high-value threshold downstream of the cache.
            econ = extract_deal_economics(rich_text)
            deal["deal_economics"]            = econ
            deal["deal_value_upfront_usd"]    = econ["upfront_usd"]
            deal["deal_value_milestones_usd"] = econ["milestones_usd"]
            deal["deal_value_total_usd"]      = econ["total_usd"]
            deal["deal_value_equity_usd"]     = econ["equity_usd"]
            deal["deal_value_headline_usd"]   = econ["headline_usd"]
            deal["deal_value_royalty"]        = econ["royalty"]
            deal["deal_economics_note"]       = econ["extraction_note"]
            # Back-compat: the LLM schema, renderer, and _build_deal_analyst_note
            # already read the STRING field deal_value_usd — now populate it with
            # the structured human display instead of a lone positional match.
            deal["deal_value_usd"] = econ["value_display"]
            if len(econ["all_amounts"]) > 1:
                deal["all_values_mentioned"] = [a["raw"] for a in econ["all_amounts"]]

            deal["counterparty"] = _extract_counterparty(
                rich_text[:4000],
                exclude_name=hit["entity"]
            )

            # ── Counterparty sanity check ─────────────────────────────────────
            # _extract_counterparty uses regex heuristics that can latch onto
            # subsidiary names, law firms, or other entities mentioned in
            # boilerplate rather than the actual deal counterparty. As a
            # cross-check, verify the extracted name (or a significant token
            # from it) actually appears in the broader filing text near deal
            # language. If it doesn't, mark low-confidence rather than display
            # a name that may be wrong — this directly addresses the
            # Prestige/"Tailor Investments / Standive" misextraction.
            if deal["counterparty"]:
                cp = deal["counterparty"]
                cp_tokens = [t for t in re.findall(r"[A-Za-z]+", cp) if len(t) > 3]
                # Require at least one significant token to recur in full_text
                # outside the immediate match window — i.e. the name is
                # mentioned more than once, suggesting it's a real party to
                # the agreement rather than a one-off boilerplate reference.
                recurrence = sum(full_text_for_class.lower().count(t.lower()) for t in cp_tokens)
                if recurrence < 2:
                    deal["_counterparty_unverified"] = True
                    deal["analyst_note_prefix"] = (
                        f"[UNVERIFIED COUNTERPARTY: '{cp}' appears only once in "
                        f"filing text — confirm against source before citing] "
                    )

            # ── Deal direction (deterministic; tools.deal_parties) ────────────
            # Stands alone; composes with the economics step when present. For an
            # acquisition the per-share price is bound to the TARGET in the note
            # below, so no total can be synthesised from the wrong entity's float.
            parties = extract_deal_parties(
                rich_text,
                filer_name=hit["entity"],
                counterparty_hint=deal.get("counterparty"),
            )
            deal["deal_direction"]      = parties["direction"]
            deal["deal_direction_kind"] = parties["direction_kind"]
            deal["filer_role"]          = parties["filer_role"]
            deal["counterparty_role"]   = parties["counterparty_role"]
            deal["deal_parties"]        = parties
            deal["deal_direction_note"] = parties["parties_note"]       

            # Asset discovery runs on the FULL press-release/body text (rich_text
            # prefers the EX-99.1 press release, where program codes like APG777
            # appear). _extract_drug_names discovers novel codes/INN names by
            # pattern, so it must NOT be pre-filtered through extract_fn's
            # keyword-relevance gate — that gate discards any text not already
            # matching a profile keyword, which is exactly why assets_mentioned
            # came back empty for every deal.
            _asset_text = rich_text or ""
            if _asset_text:
                deal["assets_mentioned"] = _extract_drug_names(_asset_text, keywords or [])

            deal["analyst_note"] = _build_deal_analyst_note(deal)

        elif hit_source == "submissions" and is_ticker_match and skip_fetch:
            # Ticker hit where items list showed no 1.01 — low-priority keep
            # The runner pre-filter will use item101=False to rank this lower.
            deal["analyst_note"] = (
                "8-K from tracked ticker; items list indicates no Item 1.01 — "
                f"likely operational filing. Spot-check: {hit['filing_index']}"
            )
            results.append(deal)
            continue

        else:
            # filing_text_fn not provided, cap reached, or unrecoverable skip
            deal["analyst_note"] = (
                "Text extraction deferred (cap reached or fetcher not provided). "
                f"Review: {hit['filing_index']}"
            )

        results.append(deal)

    # Stamp every result with the actual search window so the runner/renderer
    # can display "EDGAR EFTS search scope: N days" correctly regardless of
    # what default the caller compiled against.
    #
    # RUNNER FILTER GUIDANCE — replace the current runner pre-filter with:
    #
    #   tool_results["deal_tracker"] = [
    #       d for d in tool_results["deal_tracker"]
    #       if (
    #           d.get("item_101_excerpt")
    #           or d.get("exhibit_99_excerpt")
    #           or d.get("deal_value_usd")
    #           or d.get("counterparty")          # ← ADD THIS
    #       )
    #       and d.get("_confidence") != "low"     # ← ADD THIS (exclude unconfirmed ticker hits)
    #   ]
    #
    # This passes confirmed deals through even when item_101 extraction returns
    # empty (common for inline 8-Ks where content is in Exhibit 99.1).
    for r in results:
        r["search_scope_days"] = days_back
    funnel.keep(STAGE_EMIT, len(results))

    # ── Week-over-week diff: detect deals that vanished since last run ────────
    vanished_deals = _diff_against_prior_run(results, days_back)
    _save_deal_state(results)

    meta = {
        "search_scope_days": days_back,
        "search_start":      (date.today() - timedelta(days=days_back)).isoformat(),
        "search_end":        date.today().isoformat(),
        "focus_terms":       focus_terms or [],
        "tickers_searched":  competitor_tickers,
        "deals_found":       len(results),
        "vanished_deals":    vanished_deals,
        "funnel":            funnel.to_meta(),   # cache-safe plain JSON
    }
    print(
        f"  DealTracker: {len(results)} deals — "
        f"{efts_fetched} EFTS + {submissions_fetched} submissions fetched "
        f"(window: {days_back}d, {date.today() - timedelta(days=days_back)} → {date.today()})"
    )

    # Coverage funnel LAST so it is the final thing on screen, and persisted to
    # disk so it survives console scrollback. Set BD_VERBOSE=1 for per-query and
    # per-filing diagnostics (off by default — they bury this table).
    print(funnel.render())
    _log_path = _persist_funnel(funnel)
    if _log_path:
        print(f"  [FUNNEL] written to {_log_path} (and {BD_FUNNEL_LOG_DIR}/deal_funnel_latest.txt)")
    if not BD_VERBOSE:
        print("  [FUNNEL] set BD_VERBOSE=1 for per-query EFTS + per-filing diagnostics")

    # Return a DealTrackerResult so the runner can access meta separately
    # from the deal list without risk of iterating over a sentinel dict.
    #
    # RUNNER USAGE:
    #   result = get_deal_tracker(...)
    #   deals  = result.deals          # list of deal dicts
    #   scope  = result.meta["search_scope_days"]
    #   # or for backwards compat (result is also directly iterable as deals):
    #   deals  = list(result)
    #
    # RUNNER PRE-FILTER (replace existing):
    #   deals = [
    #       d for d in result.deals
    #       if (d.get("item_101_excerpt") or d.get("exhibit_99_excerpt")
    #           or d.get("deal_value_usd") or d.get("counterparty"))
    #       and d.get("_confidence") != "low"
    #   ]
    return DealTrackerResult(deals=results, meta=meta)


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 12 — CONFERENCE CALENDAR
# Source: Dynamic — Wikipedia "List of medical conferences" + society homepages,
#          with a versioned static fallback for guaranteed offline operation.
#
# Strategy: get_conference_calendar() first attempts to resolve current-year
# dates via _fetch_live_conference_dates().  That function queries Wikipedia's
# structured event tables (free, no key, stable API) and supplements with
# direct society page fetches for the six highest-signal meetings.
# On any network or parse failure it falls back to CONFERENCE_CALENDAR_FALLBACK,
# a versioned static list that covers the nearest 2 conference years.
#
# The static list is intentionally NOT the sole source of truth.  The runner
# should log a warning whenever the fallback is used so that the static list
# can be refreshed.
#
# For live abstract submission tracking, the optional secondary source is
# the WHO ICTRP search portal API (free, no key) which captures data
# presentations registered as secondary publications.
# ═══════════════════════════════════════════════════════════════════════════════

# ── Static fallback calendar ─────────────────────────────────────────────────
# Used when live fetch fails.  Covers 2025-2027.
# Sources: ASCO.org, ASH.org, diabetes.org (ADA), ESMO.org, AACR.org,
#          EASD.org, EHA.io, heart.org (ACC), escardio.org (ESC)
# Last verified: June 2026.
#
# Structure per entry:
#   name           — official conference full name
#   abbreviation   — ticker-style (used in pipeline_map.milestone_dates.event)
#   society        — organising body
#   location        — city, country
#   conference_start / conference_end — ISO dates
#   abstract_deadline — submission close date (None = not yet announced)
#   late_breaking_deadline — LB abstract deadline (often 4-6 wks before meeting)
#   data_readout_window — narrative for analyst ("Day 1 plenary", etc.)
#   therapeutic_focus   — list of relevant therapy areas
#   bd_relevance        — why this meeting matters for BD decisions

CONFERENCE_CALENDAR_FALLBACK: list[dict] = [
    # ── Oncology ────────────────────────────────────────────────────────────
    {
        "name":                   "American Society of Clinical Oncology Annual Meeting",
        "abbreviation":           "ASCO 2026",
        "society":                "ASCO",
        "location":               "Chicago, IL, USA",
        "conference_start":       "2026-05-29",
        "conference_end":         "2026-06-02",
        "abstract_deadline":      "2026-02-06",
        "late_breaking_deadline": "2026-04-09",
        "data_readout_window":    "Plenary session May 31; Late-breaking clinical trials June 1-2",
        "therapeutic_focus":      ["oncology", "hematology", "immunotherapy", "ADC"],
        "bd_relevance":           (
            "Highest-impact oncology readouts of the year. Phase III OS/PFS data "
            "presented here drive licensing valuations and partnership decisions. "
            "Monitor for any asset in your pipeline_map with 'Conference readout (ASCO 2026)' milestone."
        ),
    },
    {
        "name":                   "American Association for Cancer Research Annual Meeting",
        "abbreviation":           "AACR 2026",
        "society":                "AACR",
        "location":               "San Diego, CA, USA",
        "conference_start":       "2026-04-25",
        "conference_end":         "2026-04-29",
        "abstract_deadline":      "2025-12-12",
        "late_breaking_deadline": "2026-03-06",
        "data_readout_window":    "Late-breaking sessions April 27-29; Phase I dose-escalation data common",
        "therapeutic_focus":      ["oncology", "immuno-oncology", "targeted therapy", "biomarkers"],
        "bd_relevance":           (
            "Key preclinical and early-clinical (Phase I/II) readouts. "
            "First-in-human data and novel mechanism presentations drive early-stage licensing interest."
        ),
    },
    {
        "name":                   "European Society for Medical Oncology Congress",
        "abbreviation":           "ESMO 2026",
        "society":                "ESMO",
        "location":               "Berlin, Germany",
        "conference_start":       "2026-09-11",
        "conference_end":         "2026-09-15",
        "abstract_deadline":      "2026-05-28",
        "late_breaking_deadline": "2026-07-16",
        "data_readout_window":    "Presidential symposia Sept 11-12; Late-breaking Sept 13-14",
        "therapeutic_focus":      ["oncology", "precision medicine", "IO", "rare cancers"],
        "bd_relevance":           (
            "European counterpart to ASCO. EU regulatory path data and ex-US "
            "partnering signals. Major European pharma (AZN, Roche, Novartis) "
            "use ESMO for global launch-readout strategy."
        ),
    },
    {
        "name":                   "American Society of Hematology Annual Meeting",
        "abbreviation":           "ASH 2026",
        "society":                "ASH",
        "location":               "New Orleans, LA, USA",
        "conference_start":       "2026-12-05",
        "conference_end":         "2026-12-08",
        "abstract_deadline":      "2026-08-06",
        "late_breaking_deadline": "2026-10-08",
        "data_readout_window":    "Plenary Dec 6; Oral sessions Dec 6-8",
        "therapeutic_focus":      [
            "hematology", "AML", "MDS", "myeloma", "lymphoma",
            "CAR-T", "bispecifics", "gene therapy"
        ],
        "bd_relevance":           (
            "Defining meeting for blood cancer assets. CAR-T, bispecific antibody, "
            "and gene therapy data here set BD valuations for hematology platforms. "
            "Abstract deadline is a BD intelligence trigger — watch competitor submissions."
        ),
    },
    # ── Metabolic / Diabetes / Obesity ──────────────────────────────────────
    {
        "name":                   "American Diabetes Association Scientific Sessions",
        "abbreviation":           "ADA 2026",
        "society":                "ADA",
        "location":               "San Francisco, CA, USA",
        "conference_start":       "2026-06-19",
        "conference_end":         "2026-06-22",
        "abstract_deadline":      "2026-02-13",
        "late_breaking_deadline": "2026-04-17",
        "data_readout_window":    "Presidential plenary June 20; Late-breaking clinical trials June 22",
        "therapeutic_focus":      [
            "diabetes", "obesity", "GLP-1", "SGLT2", "cardiometabolic",
            "non-alcoholic steatohepatitis", "NASH", "MASH"
        ],
        "bd_relevance":           (
            "Primary readout venue for GLP-1 RA, SGLT2, dual/triple agonist, "
            "and NASH/MASH data. Any Phase III cardiometabolic trial with "
            "completion in Q1-Q2 2026 will likely publish here. Critical for GLP-1 space BD."
        ),
    },
    {
        "name":                   "European Association for the Study of Diabetes",
        "abbreviation":           "EASD 2026",
        "society":                "EASD",
        "location":               "Stockholm, Sweden",
        "conference_start":       "2026-09-14",
        "conference_end":         "2026-09-18",
        "abstract_deadline":      "2026-05-07",
        "late_breaking_deadline": "2026-07-16",
        "data_readout_window":    "Hot topic sessions Sept 14-15; Symposia Sept 16-18",
        "therapeutic_focus":      ["diabetes", "obesity", "MASH", "cardiometabolic", "renal"],
        "bd_relevance":           (
            "European equivalent of ADA. Novo Nordisk and Lilly use EASD for "
            "EU-strategy data releases. Important for ex-US partnership valuations."
        ),
    },
    # ── Cardiovascular ──────────────────────────────────────────────────────
    {
        "name":                   "European Society of Cardiology Congress",
        "abbreviation":           "ESC 2026",
        "society":                "ESC",
        "location":               "Barcelona, Spain",
        "conference_start":       "2026-08-28",
        "conference_end":         "2026-09-01",
        "abstract_deadline":      "2026-02-07",
        "late_breaking_deadline": "2026-06-05",
        "data_readout_window":    "Hot Line sessions Aug 29-Sept 1; LBCT throughout",
        "therapeutic_focus":      [
            "heart failure", "atrial fibrillation", "atherosclerosis",
            "lipid-lowering", "PCSK9", "cardiometabolic"
        ],
        "bd_relevance":           (
            "Largest cardiovascular meeting globally. CVOT readouts, heart failure "
            "data, and PCSK9/lipid-lowering results drive major BD decisions. "
            "ESC Hot Line is equivalent to NEJM simultaneous publication."
        ),
    },
    {
        "name":                   "American College of Cardiology Scientific Sessions",
        "abbreviation":           "ACC 2027",
        "society":                "ACC",
        "location":               "Washington DC, USA",
        "conference_start":       "2027-03-27",
        "conference_end":         "2027-03-29",
        "abstract_deadline":      "2026-10-02",
        "late_breaking_deadline": "2027-01-08",
        "data_readout_window":    "Late-breaking clinical trials all 3 days",
        "therapeutic_focus":      [
            "cardiology", "heart failure", "interventional", "CVOT", "lipids"
        ],
        "bd_relevance":           (
            "Major US cardiology readout. Watch for CVOT primary endpoints "
            "and any GLP-1/SGLT2 cardiovascular outcome data presented here."
        ),
    },
    # ── Rare Disease / Gene Therapy ─────────────────────────────────────────
    {
        "name":                   "European Hematology Association Congress",
        "abbreviation":           "EHA 2026",
        "society":                "EHA",
        "location":               "Milan, Italy",
        "conference_start":       "2026-06-11",
        "conference_end":         "2026-06-14",
        "abstract_deadline":      "2026-02-05",
        "late_breaking_deadline": "2026-04-09",
        "data_readout_window":    "Late-breaking oral sessions June 12-13",
        "therapeutic_focus":      ["hematology", "sickle cell", "thalassemia", "MPN", "gene therapy"],
        "bd_relevance":           (
            "European hematology counterpart to ASH. Gene therapy and cell therapy "
            "readouts common. Watch for ex-US rights deals announced alongside data."
        ),
    },
    # ── Neurology ───────────────────────────────────────────────────────────
    {
        "name":                   "American Academy of Neurology Annual Meeting",
        "abbreviation":           "AAN 2026",
        "society":                "AAN",
        "location":               "Philadelphia, PA, USA",
        "conference_start":       "2026-04-05",
        "conference_end":         "2026-04-09",
        "abstract_deadline":      "2025-10-30",
        "late_breaking_deadline": "2026-02-12",
        "data_readout_window":    "Plenary April 6; Science sessions April 5-9",
        "therapeutic_focus":      ["neurology", "MS", "Alzheimer's", "Parkinson's", "rare neurological"],
        "bd_relevance":           (
            "Key venue for AD/PD/MS disease-modifying therapy data. "
            "CNS BD targets commonly surfaced here before Phase III initiation."
        ),
    },
]


# ── Dynamic conference date resolution ───────────────────────────────────────
# Maps society abbreviation → (URL, CSS/text anchor hints for date extraction)
# Wikipedia's "List of medical conferences" is the most reliable structured
# free source; individual society pages are used as supplementary checks.

_SOCIETY_PAGES: dict[str, dict] = {
    "ASCO":  {"wiki_key": "American Society of Clinical Oncology",
              "home": "https://www.asco.org/meetings-education/asco-meetings/asco-annual-meeting"},
    "ASH":   {"wiki_key": "American Society of Hematology",
              "home": "https://www.hematology.org/meetings/annual-meeting"},
    "ADA":   {"wiki_key": "American Diabetes Association",
              "home": "https://professional.diabetes.org/scientific-sessions"},
    "ESMO":  {"wiki_key": "European Society for Medical Oncology",
              "home": "https://www.esmo.org/meeting-calendar/esmo-congress"},
    "AACR":  {"wiki_key": "American Association for Cancer Research",
              "home": "https://www.aacr.org/meeting/aacr-annual-meeting/"},
    "EASD":  {"wiki_key": "European Association for the Study of Diabetes",
              "home": "https://www.easd.org/annual-meeting.html"},
    "ESC":   {"wiki_key": "European Society of Cardiology",
              "home": "https://www.escardio.org/Congresses-&-Events/ESC-Congress"},
    "ACC":   {"wiki_key": "American College of Cardiology",
              "home": "https://www.acc.org/Education-and-Meetings/Meetings/Meeting-Items/2027/ACC-27"},
    "EHA":   {"wiki_key": "European Hematology Association",
              "home": "https://ehaweb.org/congress/"},
    "AAN":   {"wiki_key": "American Academy of Neurology",
              "home": "https://www.aan.com/conferences/annual-meeting"},
}

# ISO date pattern — matches YYYY-MM-DD anywhere in text
_ISO_DATE_RE = re.compile(r"\b(20\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01]))\b")
# "Month D/DD, YYYY" pattern (e.g. "June 7, 2027" or "May 30–June 3, 2027")
_PROSE_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2})(?:[–\-](?:\w+\s+)?(\d{1,2}))?,?\s+(20\d{2})\b",
    re.IGNORECASE,
)
_MONTH_MAP = {m: i+1 for i, m in enumerate(
    ["january","february","march","april","may","june",
     "july","august","september","october","november","december"]
)}


def _prose_to_iso(month: str, day: str, year: str) -> str:
    """Convert 'June 7 2027' components to '2027-06-07'."""
    m = _MONTH_MAP.get(month.lower(), 0)
    return f"{year}-{m:02d}-{int(day):02d}" if m else ""


# Why a refresh did not produce a date, per meeting, for this run.
#
# The refresh path has FOUR ways out and only one of them used to print. An
# unmapped society, a non-200 response and a page carrying no future date all
# returned silently, so a run in which every stale meeting failed to refresh
# produced a log containing nothing at all about it — and the calendar then
# served the stale entries as though they were current. Absence of a log line
# was being read as evidence the step had worked.
#
# Cleared at the start of each run: reports are generated in-process, so a list
# left here would accumulate across reports and attribute one run's failures to
# the next.
_CONFERENCE_REFRESH_OUTCOMES: list[dict] = []


def reset_conference_calendar_state() -> None:
    """Forget the previous run's refresh outcomes. Called once per run."""
    _CONFERENCE_REFRESH_OUTCOMES.clear()


# ONE STRING, ONE MEANING — how a meeting is identified across both routes.
#
# The ledger records a meeting under the society token the refresh pass was
# given ("ESC"). The returned row carries the ticker-style label ("ESC 2026").
# The union below used to join those two, so it compared a stable string
# against a volatile one — volatile because the SUCCESSFUL refresh branch in
# _build_live_calendar REWRITES that label to a new year. They never matched.
#
# Invisible until 2026-09-01. Every meeting past its stored dates had also
# ended more than 30 days ago, so the window filters dropped it before it could
# reach the payload and the two key spaces never met. ESC ending 2026-09-01 put
# a stale meeting inside the 30-day back window for the first time; on
# 2026-09-02 the union returned SEVEN entries for six meetings, named ESC twice
# under two spellings, and stated a method — both routes — that had not run.
# Measured forward: 9-for-7 once ESMO rolls on 09-16, 11-for-8 once EASD rolls
# on 09-19. The overcount is the number of stale meetings inside the back
# window, so it grows and shrinks with the calendar.
#
# Every calendar entry already DECLARES `society`, and the rebuild in
# get_conference_calendar carries it onto every returned row on every vintage.
# The identity is therefore read, not parsed (rule 2). Parsing survives only as
# a named fallback for a row that declares nothing — which the curated list
# never does and a profile-supplied list might, once the list moves out of the
# engine.
CONFERENCE_IDENTITY_METHOD = (
    "meetings are matched across the two disclosure routes by the society each "
    "entry declares, not by parsing its printed label")


def _conference_identity(row) -> tuple[str, str, str]:
    """(join key, society as written, how it was arrived at) for one row.

    Accepts a ledger outcome, a returned calendar row, a curated entry or a
    bare string, because all four reach this function and a join that works on
    three of them is the defect this replaced.

    The join key is upper-cased so a declared token and a parsed one cannot
    disagree on case alone; the society is returned AS WRITTEN so nothing
    downstream has to un-normalise it for display.
    """
    if isinstance(row, dict):
        declared = str(row.get("society") or "").strip()
        if declared:
            return declared.upper(), declared, "declared"
        label = str(row.get("abbreviation") or row.get("name") or "").strip()
    else:
        label = str(row or "").strip()
    parts = label.split()
    token = parts[0] if parts else ""
    if not token:
        return "?", "", "unidentified"
    return token.upper(), token, "parsed"


def _record_refresh_outcome(abbreviation: str, reason: str) -> None:
    """Record one meeting whose refresh did not produce a usable date.

    The one identifier the refresh pass holds is the society token it was
    called with, so it is stored under BOTH names: `abbreviation` unchanged for
    every existing reader, and `society` as the identity the union joins on.
    Storing it once and letting the consumer re-derive the other spelling is
    exactly what let the two routes disagree about the same meeting.

    The signature is deliberately unchanged. test_t41_band2 extracts
    _fetch_society_dates and exec's it against four two-argument stand-ins, and
    counts its four call sites; a third parameter here breaks all five checks.
    """
    society = str(abbreviation or "").strip()
    _CONFERENCE_REFRESH_OUTCOMES.append(
        {"abbreviation": society, "society": society, "reason": reason})


def conference_refresh_outcomes() -> list[dict]:
    """Refresh attempts that produced no date this run, in order."""
    return [dict(o) for o in _CONFERENCE_REFRESH_OUTCOMES]


def stale_conference_entries(payload: Optional[list] = None) -> list[dict]:
    """Meetings whose stored dates could not be confirmed current on this run.

    TWO ROUTES, UNIONED, because neither covers the other's case and in its own
    case each is the only evidence that exists:

      LEDGER  — _CONFERENCE_REFRESH_OUTCOMES, written by the refresh pass. This
                is the only route that survives the horizon and therapeutic-area
                filters, which drop a meeting whose stored dates have already
                gone past before it can reach the returned payload. Measured on
                a forced-failure run: 5 in the ledger, 0 in the payload.
      PAYLOAD — the _stale_fallback marker on a returned row. This is the only
                route that survives a CACHE HIT, where the refresh pass never
                executes and reset_conference_calendar_state() has emptied the
                ledger before the cached rows are handed back. Measured on the
                same probe after reset: ledger 0.

    Reading either alone loses a whole class of run, which is why the previous
    payload-only scan reported nothing on the very run that had five failures.

    PROVENANCE (rule 2). Each entry names the route that produced it in
    `detected_via`, so a caller quoting the count can state how it was arrived
    at instead of asserting it.

    De-duplicated by DECLARED SOCIETY, ledger first, so a meeting seen on both
    routes is counted once and keeps the ledger's more specific reason. It was
    de-duplicated by abbreviation until 2026-09-02, which is the same string on
    neither route — see CONFERENCE_IDENTITY_METHOD above for what that cost and
    when it starts costing it.

    A meeting the payload CORROBORATES rather than adds is recorded as such in
    `also_on_payload` instead of vanishing into the ledger entry. A count that
    silently absorbs its own duplicates cannot state how it was reached, and
    stale_conference_method below is the reader that needs it.
    """
    found: dict[str, dict] = {}
    for outcome in conference_refresh_outcomes():
        key, society, basis = _conference_identity(outcome)
        found[key] = {
            "abbreviation": str(outcome.get("abbreviation") or society or key),
            "society": society or key,
            "identity_basis": basis,
            "reason": outcome.get("reason") or "refresh produced no usable date",
            "detected_via": "refresh ledger",
            "also_on_payload": False,
        }
    for conf in (payload or []):
        if not isinstance(conf, dict) or not conf.get("_stale_fallback"):
            continue
        key, society, basis = _conference_identity(conf)
        if key in found:
            found[key]["also_on_payload"] = True
            continue
        found[key] = {
            "abbreviation": str(conf.get("abbreviation") or conf.get("name")
                                or society or key),
            "society": society or key,
            "identity_basis": basis,
            "reason": ("stored dates are past and this entry was served from "
                       "cache, so no refresh was attempted on this run"),
            "detected_via": "cached payload marker",
            "also_on_payload": True,
        }
    return list(found.values())


def stale_conference_method(entries: Optional[list] = None) -> str:
    """How a stale-meeting count was reached, for the AUDIT record only.

    NOT for the page. The two routes, the de-duplication and the identity rule
    are engine mechanics: a reader needs the meetings and the caveat, and an
    analyst auditing the figure needs how it was arrived at (rule 2). The runner
    puts this on the degradation record, which report_metadata carries whole and
    the renderer never prints.

    Composed HERE, beside the data it describes, rather than in the runner. The
    conference step's disclosure has to fit inside the 2600-character slice
    test_t41_band2 asserts over, and that slice had 41 characters of headroom
    when this was written. A sentence of this length composed inline would have
    pushed the note's closing clause out of the window and failed three checks
    in a suite that is not about identity — the same trap the T63 scope record
    sprang once already, recorded in the runner beside that step.

    Empty string when there is nothing to describe, so a caller can put it on a
    record unconditionally without asserting a method for an absence.
    """
    rows = [e for e in (entries or []) if isinstance(e, dict)]
    if not rows:
        return ""
    ledger = [e for e in rows if e.get("detected_via") == "refresh ledger"]
    cached = [e for e in rows if e.get("detected_via") == "cached payload marker"]
    both = [e for e in ledger if e.get("also_on_payload")]
    declared = [e for e in rows if e.get("identity_basis") == "declared"]
    parsed = [e for e in rows if e.get("identity_basis") == "parsed"]
    return (
        f"Counted from {len(ledger)} meeting(s) recorded by this run's refresh "
        f"pass and {len(cached)} carrying a stale marker on a returned row with "
        f"no refresh recorded this run, de-duplicated to {len(rows)}: "
        f"{len(both)} appeared on both routes and were counted once, keeping "
        f"the refresh pass's more specific reason. Identity method: "
        f"{CONFERENCE_IDENTITY_METHOD}; {len(declared)} declared, "
        f"{len(parsed)} parsed.")


def _fetch_society_dates(abbreviation: str) -> Optional[dict]:
    """
    Attempt to scrape start/end dates for the next occurrence of `abbreviation`
    from the society's own homepage.  Returns a minimal dict with
    {"conference_start": ISO, "conference_end": ISO} or None on failure.

    Strategy: fetch the society home page → search for ISO and prose date
    patterns → pick the soonest future start date and the immediately
    following date pair as end.
    """
    info = _SOCIETY_PAGES.get(abbreviation)
    if not info:
        _record_refresh_outcome(abbreviation, "no society page is mapped for it")
        return None
    url = info["home"]
    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        }, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            _record_refresh_outcome(
                abbreviation, f"the society page returned HTTP {resp.status_code}")
            return None
        text = resp.text

        today = date.today()
        candidates: list[date] = []

        # ISO dates
        for m in _ISO_DATE_RE.finditer(text):
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
                if d >= today:
                    candidates.append(d)
            except ValueError:
                pass

        # Prose dates ("June 7, 2027")
        for m in _PROSE_DATE_RE.finditer(text):
            month, day_start, day_end, year = m.group(1), m.group(2), m.group(3), m.group(4)
            iso_s = _prose_to_iso(month, day_start, year)
            if iso_s:
                try:
                    d = datetime.strptime(iso_s, "%Y-%m-%d").date()
                    if d >= today:
                        candidates.append(d)
                    if day_end:
                        iso_e = _prose_to_iso(month, day_end, year)
                        if iso_e:
                            d_end = datetime.strptime(iso_e, "%Y-%m-%d").date()
                            # The SAME forward-looking filter the start date gets
                            # two lines above. Without it the end of a date range
                            # that has already happened — the shape every society
                            # archive page carries, e.g. "April 24-29, 2020" —
                            # was appended unconditionally. candidates.sort()
                            # then made it the EARLIEST entry, so it was selected
                            # as the next occurrence and published: observed on
                            # 2026-08-03 as "patched AACR -> 2020-04-29", which
                            # also rewrote that entry's abbreviation to
                            # "AACR 2020" and cleared its two deadline fields.
                            # Only the start date was ever guarded; a range whose
                            # start is past and whose end is past is exactly the
                            # case the guard existed to reject.
                            if d_end >= today:
                                candidates.append(d_end)
                except ValueError:
                    pass

        if not candidates:
            _record_refresh_outcome(
                abbreviation,
                "the society page carried no date at or after today, so no "
                "future occurrence could be read from it")
            return None

        candidates.sort()
        start = candidates[0]
        # Best guess for end: first candidate at least 1 day after start, within 14 days
        end_candidates = [c for c in candidates if start < c <= start + timedelta(days=14)]
        end = end_candidates[0] if end_candidates else start + timedelta(days=3)

        return {
            "conference_start": start.isoformat(),
            "conference_end":   end.isoformat(),
        }

    except Exception as e:
        _record_refresh_outcome(abbreviation, f"the society page could not be fetched: {e}")
        return None


def _build_live_calendar() -> list[dict]:
    """
    Build a conference calendar by merging the static fallback list with
    any fresher dates retrieved from society homepages.

    For each entry in the fallback list:
      - If the hardcoded conference_end has already passed, attempt to fetch
        a future occurrence from the society homepage and patch the dates.
      - If the fetch fails or the hardcoded dates are still future, use the
        fallback entry as-is.

    Returns the merged list (same schema as CONFERENCE_CALENDAR_FALLBACK).
    """
    today    = date.today()
    results  = []
    patched  = 0

    for entry in CONFERENCE_CALENDAR_FALLBACK:
        conf = dict(entry)  # shallow copy — don't mutate the module-level constant
        try:
            conf_end = datetime.strptime(conf["conference_end"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            results.append(conf)
            continue

        if conf_end >= today:
            # Still in the future — use as-is
            results.append(conf)
            continue

        # Stale — attempt live refresh.
        # The society is DECLARED by the entry and is read, not parsed. It was
        # taken from the printed label here — the same label the success branch
        # below REWRITES to a new year — so the identity the ledger recorded and
        # the identity the returned row carries were derived two different ways
        # from two different strings, and the union could not compare them.
        # _conference_identity falls back to the old parse for an entry that
        # declares no society, so a profile-supplied list still resolves once
        # this calendar leaves the engine.
        abbrev = _conference_identity(conf)[1]  # declared society, e.g. "ASCO"
        live   = _fetch_society_dates(abbrev)
        if live:
            conf["conference_start"]  = live["conference_start"]
            conf["conference_end"]    = live["conference_end"]
            # Clear stale deadline fields — we don't have live values for these
            conf["abstract_deadline"]      = None
            conf["late_breaking_deadline"] = None
            # Update abbreviation year to match new dates
            new_year = live["conference_start"][:4]
            conf["abbreviation"] = f"{abbrev} {new_year}"
            # Provenance (rule 2). A date read off a society's own web page and
            # a date curated into this list are not the same kind of fact: the
            # scraped one is the earliest future date anywhere on that page,
            # which may be a registration or submission date rather than the
            # meeting itself. They were previously indistinguishable once
            # written, on the page and in the payload alike.
            conf["date_provenance"] = "scraped"
            conf["date_source_url"] = (_SOCIETY_PAGES.get(abbrev) or {}).get("home", "")
            conf["date_method"] = (
                "earliest date at or after today found on the society's own "
                "page; not confirmed to be the meeting date itself")
            patched += 1
            print(f"  ConferenceCalendar: patched {abbrev} → {live['conference_start']} "
                  f"(scraped from the society page, not curated)")
        else:
            # Refresh produced no date, for one of four reasons — each now
            # recorded rather than three of them returning silently. The stale
            # entry is kept so the calendar is not empty, and the flag below is
            # READ by the runner, which it previously was not: across every
            # module, profile and test in the tree its only occurrences were the
            # line that set it and the comment describing it.
            conf["_stale_fallback"] = True
            conf["date_provenance"] = "stale"

        results.append(conf)

    stale = [c for c in results if c.get("_stale_fallback")]
    if patched:
        print(f"  ConferenceCalendar: {patched} entries refreshed from society pages")
    if stale:
        # Announced once, here, inside the step that decides it happened —
        # not once per meeting and not again by the caller.
        print(f"  ConferenceCalendar: {len(stale)} meeting(s) are past their stored "
              f"dates and could not be refreshed, so stored dates are being served: "
              + "; ".join(f"{o['abbreviation']} — {o['reason']}"
                          for o in conference_refresh_outcomes()))
    return results


def get_conference_calendar(
    days_horizon: int = 180,
    therapeutic_areas: Optional[list[str]] = None,
    include_past_30d: bool = True,
    custom_conferences: Optional[list[dict]] = None,
    live_refresh: bool = True,
) -> list[dict]:
    """
    Return upcoming (and optionally recently-completed) conference events
    with BD-relevant deadlines and data windows.

    Args:
        days_horizon:         How many days ahead to include. Default: 180.
        therapeutic_areas:    Filter to specific areas e.g. ["oncology", "diabetes"].
                              None = all areas.
        include_past_30d:     Include conferences that ended within last 30 days
                              (for post-conference deal tracking). Default: True.
        custom_conferences:   Optional list of additional conference dicts in the
                              same schema as CONFERENCE_CALENDAR_FALLBACK.
        live_refresh:         If True (default), attempt to refresh stale dates
                              from society homepages before filtering.  Set False
                              to force static-only mode (faster, offline-safe).

    Returns:
        List of conference dicts enriched with:
          days_to_conference_start  — int (negative = already started/past)
          days_to_abstract_deadline — int or None
          days_to_lb_deadline       — int or None
          status                    — "Upcoming" | "Ongoing" | "Completed (30d)" | "Abstract Window Open"
          _stale_fallback           — True if live refresh failed for this entry
          date_provenance           — "curated" | "scraped" | "stale"
          date_source_url           — page a scraped date was read from, else ""
          date_method               — how the date was arrived at, and its limit

    The last four survive the rebuild below and are readable by the caller.
    They previously did not: every one of them was written and then dropped.
    """
    calendar = _build_live_calendar() if live_refresh else list(CONFERENCE_CALENDAR_FALLBACK)
    if custom_conferences:
        calendar.extend(custom_conferences)

    today    = date.today()
    cutoff   = today + timedelta(days=days_horizon)
    past_cut = today - timedelta(days=30)

    results = []
    for conf in calendar:
        try:
            conf_start = datetime.strptime(conf["conference_start"], "%Y-%m-%d").date()
            conf_end   = datetime.strptime(conf["conference_end"],   "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue

        # Date-range filter
        if conf_start > cutoff:
            continue
        if conf_end < past_cut and not include_past_30d:
            continue
        if conf_end < past_cut and include_past_30d and conf_end < today - timedelta(days=30):
            continue

        # Therapeutic area filter
        if therapeutic_areas:
            focus = [f.lower() for f in conf.get("therapeutic_focus", [])]
            if not any(ta.lower() in " ".join(focus) for ta in therapeutic_areas):
                continue

        # Compute day deltas
        days_to_start = (conf_start - today).days
        days_to_end   = (conf_end   - today).days

        abstract_deadline = conf.get("abstract_deadline")
        days_to_abstract  = _days_from_now(abstract_deadline) if abstract_deadline else None

        lb_deadline    = conf.get("late_breaking_deadline")
        days_to_lb     = _days_from_now(lb_deadline) if lb_deadline else None

        # Status
        if days_to_start > 0:
            if days_to_abstract is not None and 0 < days_to_abstract <= 30:
                status = "Abstract Window Open — closing soon"
            elif days_to_abstract is not None and days_to_abstract <= 0:
                status = "Upcoming — abstracts closed"
            else:
                status = "Upcoming"
        elif days_to_start <= 0 <= days_to_end:
            status = "Ongoing"
        else:
            status = "Completed (within 30 days)"

        # Action items for BD team
        action_items = []
        if days_to_abstract is not None:
            if 0 < days_to_abstract <= 14:
                action_items.append(
                    f"URGENT: Abstract deadline {abstract_deadline} — "
                    f"{days_to_abstract} days remaining"
                )
            elif days_to_abstract <= 0:
                action_items.append(f"Abstracts submitted (deadline was {abstract_deadline})")
        if days_to_lb is not None and 0 < days_to_lb <= 30:
            action_items.append(
                f"Late-breaking deadline {lb_deadline} — {days_to_lb} days"
            )
        if days_to_start <= 7 and days_to_start > 0:
            action_items.append(
                f"Conference starts in {days_to_start} days — monitor abstract list"
            )
        if status == "Ongoing":
            action_items.append(
                "Conference ONGOING — watch for data releases and deal announcements"
            )

        results.append({
            # ── identity fields (always present, guaranteed by static calendar) ──
            "name":                      conf["name"],
            "abbreviation":              conf["abbreviation"],
            "society":                   conf.get("society", ""),
            "location":                  conf.get("location", ""),
            "conference_start":          conf["conference_start"],
            "conference_end":            conf["conference_end"],
            "therapeutic_focus":         conf.get("therapeutic_focus", []),
            "bd_relevance":              conf.get("bd_relevance", ""),
            "data_readout_window":       conf.get("data_readout_window", ""),
            # ── deadline fields ──────────────────────────────────────────────
            "abstract_deadline":         conf.get("abstract_deadline"),
            "late_breaking_deadline":    conf.get("late_breaking_deadline"),
            # ── computed fields (prompt schema names, used by LLM + renderer) ─
            "days_to_start":             days_to_start,           # prompt: days_to_start
            "days_to_abstract_deadline": days_to_abstract,
            "days_to_lb_deadline":       days_to_lb,
            "status":                    status,
            "action_items":              action_items,
            # ── LLM-populated field (stub; LLM fills from trial data) ─────────
            "pipeline_trials_aligned":   [],   # LLM cross-references clinical_trials
            # ── provenance and staleness (rule 2, rule 25) ───────────────────
            # These four are written by the refresh pass above and used to die
            # exactly here: the return is REBUILT from named keys, so a key not
            # named is dropped however carefully it was set. _stale_fallback had
            # no surviving consumer anywhere in the tree, and the three date
            # fields had none at all — 5 rows carried provenance before this
            # boundary and 0 after it.
            #
            # They are carried now because the payload is the ONLY route that
            # can disclose a stale date on a cache hit, where the refresh pass
            # never runs and the ledger is empty. Every row states where its
            # date came from, so a curated date and a scraped one are no longer
            # indistinguishable once written.
            "_stale_fallback":           bool(conf.get("_stale_fallback")),
            "date_provenance":           conf.get("date_provenance", "curated"),
            "date_source_url":           conf.get("date_source_url", ""),
            "date_method":               conf.get(
                "date_method",
                "curated entry from the maintained conference list; not "
                "re-read from the society's page on this run"),
        })

    # Sort: ongoing first, then by start date ascending
    results.sort(key=lambda x: (
        x["status"] != "Ongoing",
        x["days_to_start"]
    ))

    print(f"  ConferenceCalendar: {len(results)} events in {days_horizon}d window")
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 13 — BIOSIMILAR WATCH
# Sources:
#   Primary:   FDA Drugs@FDA API — ANDA/BLA submissions
#              https://api.fda.gov/drug/drugsfda.json
#   Secondary: FDA Orange Book (reference listed drugs, patent/exclusivity data)
#              https://www.accessdata.fda.gov/scripts/cder/ob/ (parseable HTML)
#              Direct download: https://www.fda.gov/media/76860/download (ZIP)
#   Tertiary:  ClinicalTrials.gov — biosimilar Phase III trials
#              https://clinicaltrials.gov/api/v2/studies (already in runner)
#
# Why?  The FDA makes ANDA (small molecule) and 351(k) BLA (biosimilar)
# applications public via the Drugs@FDA API.  Cross-referencing competitor
# assets in your pipeline_map against these records surfaces IP cliff risk
# and entry timing windows — directly informing BD valuation models.
#
# Free?  Yes.  FDA APIs are public, no key required.  Rate limit: ~240 req/min
# for api.fda.gov.  Orange Book CSV is a free monthly download.
# ═══════════════════════════════════════════════════════════════════════════════

# Application types to flag as biosimilar-related.
# 4b (rules 1/10): the ORDER tuple is the composition source for the GROUP2
# schema literal in agents/report_pipeline.py (" | ".join) — the schema no
# longer re-declares these strings, and a set cannot be rendered into a prompt
# deterministically. The set, which every membership check uses, is derived
# from the tuple so the two cannot drift.
BIOSIMILAR_APP_TYPE_ORDER = ("ANDA", "BLA")  # BLA 351(k) = biosimilar; ANDA = generic
BIOSIMILAR_APP_TYPES = set(BIOSIMILAR_APP_TYPE_ORDER)

# Status codes that indicate an active / pending submission.
# Same 4b composition contract as BIOSIMILAR_APP_TYPE_ORDER above; tuple order
# is lifecycle order, exactly the order the pre-4b schema literal taught, so
# the composed schema is byte-identical to it.
ACTIVE_SUBMISSION_STATUS_ORDER = (
    "Pending",
    "Filed",
    "Tentatively Approved",
    "Approved",  # Include approved generics/biosimilars — they affect exclusivity
)
ACTIVE_SUBMISSION_STATUSES = set(ACTIVE_SUBMISSION_STATUS_ORDER)

# Remembered outage for the Drugs@FDA application endpoint.
#
# The unit of failure here is the HOST, not the drug. One unreachable endpoint
# was asked 24 times on the 2026-08-03 forced-failure run (4 drugs x 2
# application types x 3 name fields) to learn the same thing once.
#
# Module-level state outlives the run: reports are generated in-process, so a
# value left here would make one bad minute into a dead source for every later
# report until the process restarted. It is therefore bounded in time AND
# cleared at the start of each run, because either alone is insufficient.
_FDA_APP_FAILURE: Optional[tuple] = None
_FDA_APP_FAILURE_TTL_SECONDS = 15 * 60


def reset_biosimilar_watch_state() -> None:
    """Forget any remembered Drugs@FDA outage. Called once per run."""
    global _FDA_APP_FAILURE
    _FDA_APP_FAILURE = None


def _remembered_fda_app_failure() -> Optional[SourceFetchFailed]:
    """The recent outage, if one was recorded and has not aged out."""
    global _FDA_APP_FAILURE
    if not _FDA_APP_FAILURE:
        return None
    recorded_at, failure = _FDA_APP_FAILURE
    if (time.time() - recorded_at) > _FDA_APP_FAILURE_TTL_SECONDS:
        _FDA_APP_FAILURE = None
        return None
    return failure


def _remember_fda_app_failure(failure: SourceFetchFailed) -> None:
    global _FDA_APP_FAILURE
    _FDA_APP_FAILURE = (time.time(), failure)


def _fetch_fda_applications(drug_name: str, app_type: str = "ANDA") -> list[dict]:
    """
    Query FDA Drugs@FDA API for applications matching a drug name.

    Key FDA API facts that drove this implementation:
      1. ANDA = small-molecule generics only. Biologics (peptides, mAbs) use BLA.
      2. 351(k) biosimilars are BLA submissions with submission_type "BLA" under
         a BLA application. The correct search is:
           application_type:BLA AND products.active_ingredients.name:"semaglutide"
      3. Quotes around field values: ONLY for text/phrase fields. Enum/keyword
         fields (application_type) must be unquoted.
      4. Boolean spaces: use literal space " AND " — requests encodes it to "+"
         which FDA Lucene accepts. Never embed "+" in the Python string (becomes %2B).
      5. FDA returns HTTP 404 (not 400/200-empty) for zero-result queries.
         Treat 404 as empty list.
      6. Broad unconstrained queries (no drug name, limit=100) also 404 because
         the result set is too large. Always include a drug name constraint.
    """
    import requests as _req

    drug_lower = drug_name.strip().lower()

    def fda_get(search: str, limit: int = 20) -> list[dict]:
        """GET with 404-as-empty and fast-fail (no retry on query errors).

        A 404 is a real answer from this endpoint and still returns []. Every
        other failure now raises instead of returning [], because an empty list
        here was indistinguishable from "this drug has no such applications" —
        and that is a claim about the regulatory record, published on the page
        as a finding.
        """
        remembered = _remembered_fda_app_failure()
        if remembered is not None:
            # The host is already known to be unreachable on this run. Re-raise
            # the original rather than asking again; the caller sees one outage,
            # not one per drug per application type per name field.
            raise remembered

        operation = f'{app_type} applications for "{drug_name}"'
        time.sleep(REQUEST_DELAY)
        try:
            resp = _req.get(
                FDA_DRUGSFDA_URL,
                params={"search": search, "limit": limit},
                headers=HEADERS_JSON,
                timeout=20,
            )
        except Exception as e:
            failure = SourceFetchFailed(
                source="FDA Drugs@FDA", operation=operation, reason=str(e))
            _remember_fda_app_failure(failure)
            raise failure

        if resp.status_code == 404:
            return []   # zero results — not an error; this endpoint's real empty

        if resp.status_code >= 400:
            # Not retried: a malformed query does not improve on retry. But it
            # is not an empty result either, and returning [] said it was.
            failure = SourceFetchFailed(
                source="FDA Drugs@FDA", operation=operation,
                reason=f"HTTP {resp.status_code}", status_code=resp.status_code)
            if failure.retryable:
                # A throttle or a server fault is about the HOST and will affect
                # every following query; a 400-class query error is about this
                # one request and must not suppress the others.
                _remember_fda_app_failure(failure)
            raise failure

        try:
            return resp.json().get("results", [])
        except Exception as e:
            raise SourceFetchFailed(
                source="FDA Drugs@FDA", operation=operation,
                reason=f"response could not be parsed: {e}",
                status_code=resp.status_code)

    # openFDA drugsfda has NO server-side `application_type` field: the ANDA/NDA/
    # BLA distinction lives only in the application_number prefix and MUST be
    # filtered client-side. The previous queries used `application_type:{app_type}`,
    # a non-existent field, so FDA Lucene 404'd and every drug returned 0 records
    # (the root of biosimilar_watch's persistent "0 ANDA/BLA records retrieved").
    # We now search by name and keep only records whose application_number carries
    # the requested prefix.
    want = app_type.strip().upper()

    def _matches_type(rec: dict) -> bool:
        appnum = (rec.get("application_number") or "").upper()
        return appnum.startswith(want)

    for field in ("products.active_ingredients.name",
                  "products.brand_name", "sponsor_name"):
        raw = fda_get(f'{field}:"{drug_name}"', limit=100)
        matched = [r for r in raw if _matches_type(r)]
        if raw:
            # Diagnostic: distinguishes "name search matched nothing" (raw=0) from
            # "records exist but none are this application type" (raw>0, matched=0).
            print(f"    FDA[{want}] {drug_name} via {field}: "
                  f"{len(raw)} raw -> {len(matched)} {want}")
        if matched:
            return matched
    return []


def _is_biologic(drug_name: str, molecule_type_map: Optional[dict] = None) -> bool:
    """
    Return True only if the drug uses the BLA (biologic) regulatory pathway — i.e.
    its follow-ons are 351(k) biosimilars (Purple Book), not ANDA generics (Orange
    Book).

    Driven by the profile's asset_molecule_type map when supplied: 'biologic' ->
    True; 'peptide' / 'small_molecule' -> False. Peptides of <=40 amino acids are
    regulated as DRUGS under an NDA (ANDA generics), so they are NOT biologics —
    the previous hardcoded list wrongly flagged the GLP-1 peptides (semaglutide,
    liraglutide, exenatide, tirzepatide), which skipped their ANDA generic search
    entirely and produced "0 records" for assets that in fact face generics.

    Assets absent from the map fall back to a minimal set of unambiguous biologics
    (insulins, fusion proteins, mAbs) and otherwise default to the NDA/generic
    pathway — never misrouted to BLA-only.
    """
    name = (drug_name or "").strip().lower()
    if molecule_type_map:
        for asset, mtype in molecule_type_map.items():
            if (asset or "").strip().lower() == name:
                return str(mtype).strip().lower() == "biologic"
    # Fallback for assets not in the profile map: only unambiguous biologics.
    # NOTE: the GLP-1/GIP PEPTIDES are deliberately absent — they are NDA drugs.
    FALLBACK_BIOLOGIC = {
        "insulin glargine", "insulin degludec", "insulin lispro",
        "insulin aspart", "insulin glulisine",
        "dulaglutide", "albiglutide",            # Fc-/albumin-fusion proteins (BLA)
        "evolocumab", "alirocumab",              # PCSK9 mAbs
        "adalimumab", "etanercept", "infliximab", "rituximab",
        "trastuzumab", "bevacizumab", "pembrolizumab", "nivolumab",
    }
    return name in FALLBACK_BIOLOGIC


# ─────────────────────────────────────────────────────────────────────────────
# Application-status vocabulary — ONE OWNER, ONE COPY
# ─────────────────────────────────────────────────────────────────────────────
# The submission_status values below are the ones this module reads back from
# the openFDA Drugs@FDA application endpoint (FDA_DRUGSFDA_URL); they are the
# source's own strings, read verbatim from the records parsed here, not an
# editorial list. The mapping to a class is the only judgement, and it is stated
# once so every reader shares it.
#
# WHY IT IS EXPORTED. The three booleans this module writes onto each record
# (is_approved / is_tentative / is_pending) are DERIVED from current_status by
# the equality test below — they are a restatement of a field that travels with
# the record, not an independent observation. Consumers that received a record
# whose booleans did not survive its journey therefore need the vocabulary, not
# the booleans; without it they had to either re-declare the strings (a second
# copy, free to drift) or read a missing key and publish the resulting silence
# as a finding. The 2026-08-08 report did the latter. Callers classify through
# these functions; nobody re-declares the strings.
#
# TOOL_OUTPUT_VERSIONS: no bump is due for this change. The record shape and
# every value in it are unchanged — the same three booleans are computed from
# the same field by the same rule, through a named function instead of three
# inline comparisons — so a cached payload written before this change is still
# exactly what this code would write today.
APPLICATION_STATUS_CLASSES = ("approved", "tentative", "pending", "other")

_APPLICATION_STATUS_TEXT_TO_CLASS = {
    "approved":             "approved",
    "tentatively approved": "tentative",
    "pending":              "pending",
    "filed":                "pending",
}

APPLICATION_STATUS_METHOD = (
    "application status classified from the record's own Drugs@FDA "
    "submission_status field (approved / tentatively approved / pending / "
    "filed); any other value is classified 'other' and asserts nothing"
)


def classify_application_status(status_text) -> str:
    """Map one Drugs@FDA submission_status string to its class.

    Returns one of APPLICATION_STATUS_CLASSES. An unrecognised or empty status
    returns "other" — never a guess, and never one of the three actionable
    classes."""
    return _APPLICATION_STATUS_TEXT_TO_CLASS.get(
        str(status_text or "").strip().lower(), "other")


def classify_application_record(rec: dict) -> tuple[str, str]:
    """Classify one application record WHATEVER SHAPE IT ARRIVED IN.

    Returns (class, basis) where class is one of APPLICATION_STATUS_CLASSES and
    basis is one of:
      "flags"  — the pre-computed booleans were present and were used
      "status" — no usable booleans; classified from current_status here
      "none"   — neither present; class is "other" and the caller must treat
                 this as UNREADABLE rather than as a negative finding

    The booleans win when present because they were computed at the record's
    source from that record's own status, and a consumer that recomputes over a
    producer's explicit value can only introduce disagreement. A null is not a
    value: only a real bool counts as present, so a shape that carried the key
    with nothing in it falls through to the status text rather than being read
    as False."""
    if not isinstance(rec, dict):
        return "other", "none"
    flags = {
        "approved":  rec.get("is_approved"),
        "tentative": rec.get("is_tentative"),
        "pending":   rec.get("is_pending"),
    }
    if any(isinstance(v, bool) for v in flags.values()):
        for cls, val in flags.items():
            if val is True:
                return cls, "flags"
        return "other", "flags"
    status = rec.get("current_status")
    if isinstance(status, str) and status.strip():
        return classify_application_status(status), "status"
    return "other", "none"


def _parse_fda_record(rec: dict, reference_drug: str) -> dict:
    """Extract BD-relevant fields from a raw FDA Drugs@FDA record."""
    openfda = rec.get("openfda", {})
    subs    = rec.get("submissions", [{}])
    latest  = subs[-1] if subs else {}

    # Submission history to find earliest ANDA/BLA submission date
    submission_dates = [
        s.get("submission_status_date", "")
        for s in subs
        if s.get("submission_status_date")
    ]
    earliest_submission = min(submission_dates) if submission_dates else None
    latest_action       = max(submission_dates) if submission_dates else None

    # Days since earliest submission (proxy for regulatory timeline)
    days_pending = None
    if earliest_submission:
        try:
            days_pending = (
                date.today() -
                datetime.strptime(earliest_submission[:8], "%Y%m%d").date()
            ).days
        except ValueError:
            pass

    app_type       = rec.get("application_type", "")
    app_number     = rec.get("application_number", "")
    current_status = latest.get("submission_status", "Unknown")
    # Classified ONCE, here, and reused by every branch below (note text and the
    # three booleans alike). Previously each site re-declared the status strings
    # inline; identical rule, four copies.
    _status_class = classify_application_status(current_status)

    # BD implication
    if _status_class == "approved":
        bd_note = (
            f"Approved {app_type} {app_number} — market entry risk for "
            f"{reference_drug}. Review remaining exclusivity / patent protection."
        )
    elif _status_class == "pending":
        bd_note = (
            f"Active {app_type} {app_number} pending — anticipate potential "
            f"market entry for {reference_drug}. Flag for IP cliff analysis."
        )
    elif _status_class == "tentative":
        bd_note = (
            f"Tentative approval received — entry pending exclusivity expiry. "
            f"Monitor 180-day exclusivity clock for {reference_drug}."
        )
    else:
        bd_note = f"{app_type} {app_number} status: {current_status}."

    # is_new_this_week — true if earliest submission within last 7 days
    is_new_this_week = False
    if earliest_submission:
        try:
            sub_date = datetime.strptime(earliest_submission[:8], "%Y%m%d").date()
            is_new_this_week = (date.today() - sub_date).days <= 7
        except ValueError:
            pass

    # Same three booleans as before, from the same field by the same rule —
    # but through the one exported classifier, so the vocabulary has a single
    # owner and a consumer holding a record without these keys can reach the
    # same answer instead of reading the absence as a negative.
    is_approved  = _status_class == "approved"
    is_tentative = _status_class == "tentative"
    is_pending   = _status_class == "pending"

    # analyst_note — pre-populated guidance; LLM enriches with IP/pipeline context
    if is_pending:
        analyst_note = (
            f"Entry risk ACTIVE — cross-reference patent_intelligence.ip_cliff_watch "
            f"for {reference_drug} to estimate earliest realistic market entry date. "
            f"Days pending: {days_pending or 'unknown'}."
        )
    elif is_tentative:
        analyst_note = (
            f"Tentative approval granted — entry held pending 180-day exclusivity "
            f"or patent expiry for {reference_drug}. Monitor Orange Book for exclusivity codes."
        )
    elif is_approved:
        analyst_note = (
            f"Approved {app_type} on market. Assess remaining patent protection for "
            f"{reference_drug} and flag any continuation filings in patent_intelligence."
        )
    else:
        analyst_note = f"Status '{current_status}' — monitor for future action."

    return {
        # core identity (always populated)
        "reference_drug":      reference_drug,
        "applicant":           rec.get("sponsor_name", "Unknown"),
        "application_number":  app_number,
        "application_type":    app_type,
        "current_status":      current_status,
        # timeline fields
        "earliest_submission": earliest_submission,
        "days_pending":        days_pending,
        # boolean flags (used by prompt escalation rules)
        "is_new_this_week":    is_new_this_week,
        "is_approved":         is_approved,
        "is_tentative":        is_tentative,
        "is_pending":          is_pending,
        # cross-reference stubs (LLM fills from pipeline_map + patent data)
        "pipeline_crossref":   None,
        "patent_crossref":     None,
        # narrative fields
        "bd_implication":      bd_note,
        "analyst_note":        analyst_note,
        # supplementary detail (kept for LLM context)
        "product_name":        (
            openfda.get("brand_name", [None])[0] or
            openfda.get("generic_name", [None])[0] or "Unknown"
        ),
        "active_ingredient":   openfda.get("substance_name", []),
        "latest_action_date":  latest_action,
        "submission_count":    len(subs),
        "source":              "FDA_DRUGSFDA",
    }


def get_biosimilar_watch(
    pipeline_drugs: list[str],
    include_generics: bool = True,
    include_biosimilars: bool = True,
    approved_lookback_days: int = 365,
    asset_molecule_type: Optional[dict] = None,
) -> list[dict]:
    """
    Check for ANDA (generic) and BLA 351(k) (biosimilar) applications filed
    against drugs in your pipeline_map or competitor asset list.

    Args:
        pipeline_drugs:       List of INN drug names to check e.g.
                              ["semaglutide", "tirzepatide", "retatrutide"]
        include_generics:     Include ANDA filings. Default: True.
        include_biosimilars:  Include BLA 351(k) biosimilar filings. Default: True.
        approved_lookback_days: Only include approved ANDAs/BLAs filed within
                              this window. Default: 365 days.

    Returns:
        List of biosimilar/generic application records, sorted by BD priority:
          1. Pending/Filed (highest risk — entry imminent)
          2. Tentatively Approved
          3. Recently Approved

    Raises:
        SourceFetchFailed: when the application endpoint could not be reached.

    This payload is a LIST, so infra.engine_errors.mark_degraded cannot attach a
    failure record to it and is_degraded() would be False for anything returned
    here — meaning a swallowed failure would be written to the cache and served
    as fact for a full week. Raising is therefore the only contract available at
    this boundary, and the run records the reason before re-raising.
    """
    results: list[dict] = []
    seen_apps: set[str] = set()

    for drug in pipeline_drugs:
        # Biologics (peptides, mAbs) use BLA 351(k), not ANDA.
        # Skipping ANDA for biologics avoids guaranteed-empty API calls.
        drug_is_biologic = _is_biologic(drug, asset_molecule_type)
        app_types_for_drug = []
        if include_generics and not drug_is_biologic:
            app_types_for_drug.append("ANDA")
        if include_biosimilars:
            app_types_for_drug.append("BLA")  # covers innovator BLA + 351(k) biosimilar

        for app_type in app_types_for_drug:
            route = "351(k) biosimilar" if drug_is_biologic and app_type == "BLA" else app_type
            print(f"  BiosimilarWatch: {drug} [{route}]")
            records = _fetch_fda_applications(drug, app_type)

            for rec in records:
                app_num = rec.get("application_number", "")
                if app_num in seen_apps:
                    continue

                parsed = _parse_fda_record(rec, drug)
                # Approved follow-ons represent ACTUAL market entry and matter for
                # the earliest-entry reconciliation regardless of age — only drop
                # by recency when a window is explicitly set (the 2024 liraglutide
                # generics are >365d old and were being dropped, showing 0 records).
                if (parsed["is_approved"] and parsed["latest_action_date"]
                        and approved_lookback_days is not None):
                    try:
                        action_date = datetime.strptime(
                            parsed["latest_action_date"][:8], "%Y%m%d"
                        ).date()
                        if (date.today() - action_date).days > approved_lookback_days:
                            continue
                    except ValueError:
                        pass

                seen_apps.add(app_num)
                results.append(parsed)

    # Priority sort: pending > tentative > approved > other
    def priority(r: dict) -> int:
        if r["is_pending"]:   return 0
        if r["is_tentative"]: return 1
        if r["is_approved"]:  return 2
        return 3

    results.sort(key=priority)

    # Summary stats
    n_pending  = sum(1 for r in results if r["is_pending"])
    n_approved = sum(1 for r in results if r["is_approved"])
    print(
        f"  BiosimilarWatch: {len(results)} records — "
        f"{n_pending} pending, {n_approved} approved"
    )

    return results