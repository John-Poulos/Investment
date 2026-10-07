import os
import re
import time
import requests
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv
from utils.text import sanitize_source_text

load_dotenv()

# SEC requires a descriptive User-Agent or they will block you
# Set SEC_USER_AGENT in your .env: "Your Name your@email.com"
USER_AGENT = os.getenv("SEC_USER_AGENT", "PharmaAgent contact@pharmaagent.com")

SUBMISSIONS_URL  = "https://data.sec.gov/submissions"
EFTS_URL         = "https://efts.sec.gov/LATEST/search-index"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts"
ARCHIVES_URL     = "https://www.sec.gov/Archives/edgar/data"

HEADERS = {"User-Agent": USER_AGENT}

REQUEST_DELAY = 0.15  # SEC rate limit: 10 req/sec

DOMESTIC_FORMS  = ["10-K", "10-Q", "8-K"]
FOREIGN_FORMS   = ["20-F", "6-K", "40-F"]
ALL_PHARMA_FORMS = DOMESTIC_FORMS + FOREIGN_FORMS


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------

def _get_json(url: str, params: dict = None, max_retries: int = 3) -> dict:
    """
    GET expecting JSON response. Returns {} on unrecoverable error.

    Retries on 5xx server errors with exponential backoff — the EFTS
    full-text search endpoint occasionally returns 500 for valid queries
    due to transient Elasticsearch backend issues.
    """
    import random
    for attempt in range(max_retries):
        time.sleep(REQUEST_DELAY)
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)

            # 5xx = transient server error — retry with backoff
            if resp.status_code >= 500:
                wait = (2 ** attempt) + random.uniform(0, 0.5)
                print(f"  SEC EDGAR {resp.status_code} — retrying in {wait:.1f}s "
                      f"(attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.HTTPError as e:
            # 4xx errors are not retryable
            print(f"SEC EDGAR HTTP error: {e}")
            return {}
        except (requests.RequestException, ValueError) as e:
            if attempt < max_retries - 1:
                wait = (2 ** attempt) + random.uniform(0, 0.5)
                print(f"  SEC EDGAR error — retrying in {wait:.1f}s: {e}")
                time.sleep(wait)
            else:
                print(f"SEC EDGAR error (gave up after {max_retries} attempts): {e}")
                return {}

    return {}


def _get_text(url: str, params: dict = None) -> str:
    """GET expecting text/XML/HTML response. Returns '' on any error."""
    time.sleep(REQUEST_DELAY)
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except (requests.RequestException, Exception) as e:
        print(f"SEC EDGAR fetch error: {e}")
        return ""


def _extract_cik_from_atom(text: str) -> Optional[str]:
    """Parse CIK value from SEC atom/XML response text."""
    start = text.find("<cik>")
    end   = text.find("</cik>")
    if start != -1 and end != -1:
        return text[start + 5:end].strip().zfill(10)
    return None


# ── T110 — CIK resolution records the paths it tried ────────────────────────
# THE DEFECT (CI review 2026-07-30 §3.7). "GPCR — Private co. Could not
# resolve a CIK for 'GPCR'" for Structure Therapeutics, a listed company whose
# Phase III asset the same report tracks. Two causes, both here: the name
# fallback below was handed the TICKER as a company name (EDGAR was asked for a
# company called "GPCR"), and the failure was reported as a bare sentence, so
# a reader could not tell an exhausted lookup from an unattempted one.
#
# The fix is not a new matcher. The run's resolver (utils.text) already knows
# the declared name behind a ticker; it is passed IN as name_hint. What this
# module adds is the extra lookup and an honest record of every path tried —
# the T104 checked-negative doctrine applied to entity resolution.
#
# Cost control: at most ONE additional request per identifier (the declared
# name), and results are memoised for the process so a repeated ticker costs
# nothing.
CIK_LOOKUP_METHOD = (
    "CIK resolved against SEC EDGAR company search: numeric CIK, then the "
    "identifier as a ticker, then the identifier as a company name, then the "
    "profile-declared company name for that identifier; every path attempted "
    "is recorded with its result, so a negative states what was checked")

_CIK_CACHE: dict = {}


def _cik_probe(path: str, query: str, result: str) -> dict:
    """One attempted lookup, named. Carried into the report so 'no CIK' is a
    checked negative rather than an assertion."""
    return {"path": path, "query": query, "result": result}


def resolve_cik_with_paths(identifier: str, name_hint: str = "") -> tuple:
    """(cik_or_None, paths) — the resolution and the trail that produced it.

    `name_hint` is the company name the run's entity resolver holds for this
    identifier (profiles supply the declaration; utils.text resolves it). It is
    tried ONLY after the identifier's own paths have failed, so a hint can add
    a resolution but can never override one EDGAR made on the identifier
    itself.
    """
    ident = str(identifier or "").strip()
    hint = " ".join(str(name_hint or "").split())
    cached = _CIK_CACHE.get((ident, hint))
    if cached is not None:
        return cached

    paths: list = []
    if not ident:
        result = (None, paths + [_cik_probe("identifier", "", "empty identifier")])
        _CIK_CACHE[(ident, hint)] = result
        return result

    if ident.isdigit():
        cik = ident.zfill(10)
        result = (cik, [_cik_probe("numeric CIK", ident, f"used as-is: {cik}")])
        _CIK_CACHE[(ident, hint)] = result
        return result

    if len(ident) <= 6 and " " not in ident:
        text = _get_text(
            "https://www.sec.gov/cgi-bin/browse-edgar",
            params={"action": "getcompany", "CIK": ident.upper(),
                    "output": "atom"})
        cik = _extract_best_cik(text, hint=ident)
        paths.append(_cik_probe("EDGAR ticker lookup", ident.upper(),
                                f"CIK {cik}" if cik else "no match"))
        if cik:
            _CIK_CACHE[(ident, hint)] = (cik, paths)
            return cik, paths

    text = _get_text(
        "https://www.sec.gov/cgi-bin/browse-edgar",
        params={"action": "getcompany", "company": ident, "output": "atom"})
    cik = _extract_best_cik(text, hint=ident)
    paths.append(_cik_probe("EDGAR company-name search", ident,
                            f"CIK {cik}" if cik else "no match"))
    if cik:
        _CIK_CACHE[(ident, hint)] = (cik, paths)
        return cik, paths

    # The declared name — the path that was missing before T110.
    if hint and hint.lower() != ident.lower():
        text = _get_text(
            "https://www.sec.gov/cgi-bin/browse-edgar",
            params={"action": "getcompany", "company": hint, "output": "atom"})
        cik = _extract_best_cik(text, hint=hint)
        paths.append(_cik_probe("EDGAR company-name search (declared name)",
                                hint, f"CIK {cik}" if cik else "no match"))

    _CIK_CACHE[(ident, hint)] = (cik, paths)
    return cik, paths


def _resolve_cik(identifier: str) -> Optional[str]:
    return resolve_cik_with_paths(identifier)[0]


def resolve_cik(identifier: str, name_hint: str = "") -> Optional[str]:
    """
    Public wrapper around resolve_cik_with_paths. Used by
    tools.financial_intelligence to distinguish public companies (CIK
    resolves) from private companies (returns None). Callers that need to
    DISCLOSE a negative should call resolve_cik_with_paths and carry the
    paths — a bare None cannot say what was checked.
    """
    return resolve_cik_with_paths(identifier, name_hint)[0]

def _extract_best_cik(atom_text: str, hint: str = "") -> Optional[str]:
    """
    Parse all (CIK, name) pairs from an SEC atom response and return the CIK
    whose company name is most plausible for the given ticker/name hint.

    Scoring (higher = better match):
      +3  name contains a pharma/biotech signal word
      +2  name contains the hint string itself
      +1  name contains a token from the hint (for multi-word hints)
      -2  name contains a financial-advisor/fund signal word
    """
    import re

    if not atom_text:
        return None

    # Extract all CIK + company-name pairs from atom XML
    pairs = re.findall(
        r'<company-info>.*?<cik>(\d+)</cik>.*?<conformed-name>(.*?)</conformed-name>',
        atom_text, re.DOTALL
    )
    if not pairs:
        # Fallback: grab the first bare CIK if structure differs
        m = re.search(r'<cik>(\d+)</cik>', atom_text)
        return m.group(1).zfill(10) if m else None

    PHARMA_SIGNALS    = {"pharma", "bioscience", "therapeutics", "biotech",
                         "laboratories", "lab", "healthcare", "medical",
                         "plc", " ag", " ab", " sa", " nv", " se",
                         "biologics", "oncology", "genomics"}
    FINANCIAL_SIGNALS = {"advisor", "advisors", "financial", "fund", "capital",
                         "investment", "partners", "holdings", "management",
                         "securities", "asset", "trust", "llc", "inc"}

    hint_lower  = hint.lower()
    hint_tokens = set(hint_lower.split())

    def score(pair):
        cik, name = pair
        name_lower = name.lower()
        s = 0
        if any(sig in name_lower for sig in PHARMA_SIGNALS):
            s += 3
        if hint_lower in name_lower or name_lower in hint_lower:
            s += 2
        if hint_tokens & set(name_lower.split()):
            s += 1
        if any(sig in name_lower for sig in FINANCIAL_SIGNALS):
            s -= 2
        return s

    pairs.sort(key=score, reverse=True)
    best_cik, best_name = pairs[0]
    print(f"  Resolved '{hint}' → CIK {best_cik.zfill(10)} ({best_name})")
    return best_cik.zfill(10)


def _accession_to_url(cik: str, accession: str) -> str:
    """Build EDGAR filing index URL from CIK and accession number."""
    acc_clean = accession.replace("-", "")
    return f"{ARCHIVES_URL}/{int(cik)}/{acc_clean}/{accession}-index.htm"


def _document_url(cik: str, accession: str, filename: str) -> str:
    """Build direct document URL from CIK, accession, and filename."""
    acc_clean = accession.replace("-", "")
    return f"{ARCHIVES_URL}/{int(cik)}/{acc_clean}/{filename}"


# ---------------------------------------------------------------------------
# PUBLIC FUNCTION 1 — Recent Filings for a Company
# ---------------------------------------------------------------------------

def get_company_filings(
    identifier: str,
    form_types: Optional[list[str]] = None,
    days_back: int = 90,
    include_foreign: bool = True
) -> list[dict]:
    """
    Get recent SEC filings for a company by ticker, CIK, or name fragment.

    Args:
        identifier:      Ticker ("NVO"), CIK number, or name ("Novo Nordisk")
        form_types:      Form types to include e.g. ["10-K", "8-K"]
                         Default: all pharma-relevant forms
        days_back:       How far back to search. Default: 90 days
        include_foreign: Include 20-F and 6-K for foreign filers. Default: True

    Returns:
        List of filing metadata dicts, newest first.
    """
    if form_types is None:
        form_types = ALL_PHARMA_FORMS if include_foreign else DOMESTIC_FORMS

    cik = _resolve_cik(identifier)
    if not cik:
        print(f"Could not resolve CIK for '{identifier}'")
        return []

    print(f"  Resolved '{identifier}' → CIK {cik}")

    data = _get_json(f"{SUBMISSIONS_URL}/CIK{cik}.json")
    if not data:
        return []

    company_name = data.get("name", "Unknown")
    recent       = data.get("filings", {}).get("recent", {})

    # Submissions API returns parallel arrays — access by index
    acc_list  = recent.get("accessionNumber", [])
    date_list = recent.get("filingDate", [])
    form_list = recent.get("form", [])          # "form" not "form_type"
    doc_list  = recent.get("primaryDocument", [])
    desc_list = recent.get("primaryDocDescription", [])
    rep_list  = recent.get("reportDate", [])
    item_list = recent.get("items", [])

    cutoff  = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    filings = []

    for i in range(len(acc_list)):
        form = form_list[i]
        date = date_list[i]

        if form not in form_types:
            continue
        if date < cutoff:
            continue

        acc = acc_list[i]
        doc = doc_list[i]

        filings.append({
            "source":        "SEC_EDGAR",
            "company":       company_name,
            "cik":           cik,
            "form_type":     form,
            "filed_date":    date,
            "report_date":   rep_list[i],
            "accession":     acc,
            "description":   desc_list[i],
            "items":         item_list[i],
            "filing_index":  _accession_to_url(cik, acc),
            "document_url":  _document_url(cik, acc, doc) if doc else "",
        })

    print(f"  Found {len(filings)} filings for {company_name} (last {days_back} days)")
    return filings


# ---------------------------------------------------------------------------
# PUBLIC FUNCTION 2 — Full Text Search Across All Filings
# ---------------------------------------------------------------------------

def search_filings_text(
    query: str,
    form_types: Optional[str] = None,
    days_back: Optional[int] = 90,
    max_results: int = 100
) -> list[dict]:
    """
    Search full text of all SEC filings for a keyword or phrase.

    Useful for:
      - Every company mentioning a drug: '"semaglutide"'
      - Deal language: '"license agreement" "GLP-1"'
      - Pipeline disclosures: '"Phase 3" "obesity"'
      - Risk factor monitoring: '"GLP-1" "competition"'

    Args:
        query:       Keyword/phrase. Use quotes for exact: '"GLP-1"'
        form_types:  Comma-separated form types. Default: all pharma forms
        days_back:   Search window. Default: 90 days
        max_results: Max results to return. Default: 100

    Returns:
        List of filing metadata dicts with document URLs.
    """
    if form_types is None:
        form_types = ",".join(ALL_PHARMA_FORMS)

    params: dict = {
        "q":     query,
        "forms": form_types,
        "size":  min(100, max_results),
        "from":  0,
    }

    if days_back:
        cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        today  = datetime.now().strftime("%Y-%m-%d")
        params["dateRange"] = "custom"
        params["startdt"]   = cutoff
        params["enddt"]     = today

    all_hits = []
    offset   = 0

    # Build list of query variants to try in order:
    #   1. Original query (exact phrase if quoted)
    #   2. Unquoted fallback — some terms cause 500s when quoted
    #      e.g. '"lecanemab"' → 'lecanemab'
    query_variants = [query]
    if query.startswith('"') and query.endswith('"'):
        query_variants.append(query.strip('"'))

    active_query = query_variants[0]

    while len(all_hits) < max_results:
        params["q"]    = active_query
        params["from"] = offset
        data = _get_json(EFTS_URL, params=params)

        # If primary query failed and we have a fallback, try it once
        if not data and len(query_variants) > 1 and active_query == query_variants[0]:
            active_query = query_variants[1]
            print(f"  EFTS fallback: retrying without quotes → '{active_query}'")
            params["q"]    = active_query
            params["from"] = 0
            offset         = 0
            data = _get_json(EFTS_URL, params=params)

        if not data:
            print(f"  Full-text search failed for '{query[:40]}' — skipping")
            break

        hits  = data.get("hits", {}).get("hits", [])
        total = data.get("hits", {}).get("total", {}).get("value", 0)

        if not hits:
            break

        all_hits.extend(hits)
        offset += len(hits)

        print(
            f"  Full-text '{active_query[:40]}': "
            f"{min(offset, max_results)}/{min(total, max_results)}"
        )

        if offset >= total:
            break

    results = []
    for hit in all_hits[:max_results]:
        src    = hit.get("_source", {})
        hit_id = hit.get("_id", "")

        # Verified field names from actual API response
        display_names = src.get("display_names", [])
        entity        = display_names[0].split("(")[0].strip() if display_names else "N/A"
        form_type     = src.get("form", src.get("file_type", "N/A"))
        filed         = src.get("file_date", "N/A")
        accession     = src.get("adsh", "")
        ciks          = src.get("ciks", ["0"])
        cik_num       = ciks[0].lstrip("0") if ciks else "0"
        acc_clean     = accession.replace("-", "")
        _, _, filename = hit_id.partition(":")

        doc_url = (
            f"{ARCHIVES_URL}/{cik_num}/{acc_clean}/{filename}"
            if filename and cik_num else ""
        )

        results.append({
            "source":        "SEC_EDGAR_FULLTEXT",
            "entity":        entity,
            "form_type":     form_type,
            "filed_date":    filed,
            "report_period": src.get("period_ending", "N/A"),
            "description":   src.get("file_description", "N/A"),
            "accession":     accession,
            "filename":      filename,
            "cik":           ciks[0] if ciks else "N/A",
            "sic_code":      src.get("sics", []),
            "document_url":  doc_url,
            "filing_index":  (
                f"{ARCHIVES_URL}/{cik_num}/{acc_clean}/{accession}-index.htm"
            ),
        })

    return results


# ---------------------------------------------------------------------------
# PUBLIC FUNCTION 3 — R&D Spend History (XBRL)
# ---------------------------------------------------------------------------

def get_rd_spend(identifier: str) -> list[dict]:
    cik = _resolve_cik(identifier)
    if not cik:
        print(f"  Could not resolve CIK for '{identifier}'")
        return []

    print(f"  Fetching R&D spend for '{identifier}' (CIK {cik})")
    data = _get_json(f"{COMPANYFACTS_URL}/CIK{cik}.json")
    if not data:
        return []

    company_name = data.get("entityName", "Unknown")
    facts_root   = data.get("facts", {})

    # Try US-GAAP first, then IFRS (foreign filers: AZN, NVS, SNY, etc.)
    gaap = facts_root.get("us-gaap", {})
    ifrs = facts_root.get("ifrs-full", {})

    # ── Candidate R&D tags ───────────────────────────────────────────────────
    # IMPORTANT: companies sometimes switch XBRL tags between filings (e.g.
    # Lilly used "ResearchAndDevelopmentExpense" in older filings and
    # "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost" in newer
    # ones). Taking the first non-empty tag via `or` silently locks onto
    # whichever tag has ANY data — even if it's years stale — and never looks
    # at a newer tag that has the current quarters. To fix this we collect ALL
    # matching tags and MERGE their facts, deduplicating by period below.
    CANDIDATE_TAGS = [
        ("us-gaap", "ResearchAndDevelopmentExpense"),
        ("us-gaap", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"),
        ("ifrs-full", "ResearchAndDevelopmentExpense"),
        ("ifrs-full", "ExpenditureOnResearchAndDevelopmentRecognisedAsExpense"),
    ]

    taxonomies = {"us-gaap": gaap, "ifrs-full": ifrs}
    matched_tags: list[tuple[str, str, dict]] = []  # (taxonomy, tag, rd_data)

    for taxonomy_name, tag in CANDIDATE_TAGS:
        taxonomy = taxonomies.get(taxonomy_name, {})
        if tag in taxonomy:
            matched_tags.append((taxonomy_name, tag, taxonomy[tag]))

    if not matched_tags:
        # Last resort: scan all available fact keys for anything R&D-like
        for taxonomy_name, taxonomy in taxonomies.items():
            for key in taxonomy:
                if "research" in key.lower() and "development" in key.lower():
                    matched_tags.append((taxonomy_name, key, taxonomy[key]))
                    print(f"  Found R&D data under non-standard key: {taxonomy_name}:{key}")

    if not matched_tags:
        print(f"  No R&D XBRL data found for {company_name}")
        return []

    print(f"  R&D tags found for {company_name}: "
          f"{[f'{t}:{k}' for t, k, _ in matched_tags]}")

    # ── Merge raw facts across all matched tags ─────────────────────────────
    # Each fact is tagged with its source so duplicates (same period reported
    # under two tags) can be deduplicated below while preferring whichever
    # source has the most recent `filed` date for that period.
    currency  = None
    raw_facts: list[dict] = []

    for taxonomy_name, tag, rd_data in matched_tags:
        units_dict = rd_data.get("units", {})

        tag_currency  = None
        tag_facts     = []
        if "USD" in units_dict:
            tag_currency = "USD"
            tag_facts    = units_dict["USD"]
        else:
            for key, val in units_dict.items():
                if isinstance(val, list) and val:
                    tag_currency = key.replace("iso4217:", "")
                    tag_facts    = val
                    break

        print(f"    {taxonomy_name}:{tag} → {len(tag_facts)} facts, currency={tag_currency}")

        if currency is None:
            currency = tag_currency
        elif tag_currency and tag_currency != currency:
            print(f"    WARNING: currency mismatch across tags "
                  f"({currency} vs {tag_currency}) — keeping {currency}, "
                  f"skipping facts from {taxonomy_name}:{tag}")
            continue

        for f in tag_facts:
            f = dict(f)  # don't mutate the source dict
            f["_source_tag"] = f"{taxonomy_name}:{tag}"
            raw_facts.append(f)

    print(f"  currency: {currency}, merged facts count: {len(raw_facts)}")

    if not raw_facts:
        print(f"  No R&D facts found for {company_name}")
        return []

    seen: dict[tuple, dict] = {}
    for fact in raw_facts:
        form = fact.get("form", "")
        if form not in ("10-K", "10-K/A", "10-Q", "20-F", "20-F/A", "6-K"):
            continue
        start_str = fact.get("start", "")
        end_str   = fact.get("end",   "")
        filed     = fact.get("filed", "")
        key       = (start_str, end_str, form)

        if start_str and end_str:
            try:
                days = (
                    datetime.strptime(end_str,   "%Y-%m-%d") -
                    datetime.strptime(start_str, "%Y-%m-%d")
                ).days
            except ValueError:
                days = 0
        else:
            days = 0

        period_type = (
            "annual"      if days > 300 else
            "semi-annual" if days > 150 else
            "quarterly"
        )

        if key not in seen or filed > seen[key]["filed_date"]:
            seen[key] = {
                "source":       "SEC_EDGAR_XBRL",
                "company":      company_name,
                "cik":          cik,
                "period_start": start_str,
                "period_end":   end_str,
                "period_type":  period_type,
                "value":        fact.get("val", 0),
                "currency":     currency,
                "form_type":    form,
                "filed_date":   filed,
                "accession":    fact.get("accn", "N/A"),
                "_source_tag":  fact.get("_source_tag", ""),
            }

    records = sorted(seen.values(), key=lambda x: x["period_end"], reverse=True)
    print(f"  Found {len(records)} unique R&D periods for {company_name} ({currency})")

    # ── Staleness check ──────────────────────────────────────────────────────
    # If the most recent period_end is more than ~9 months old, the merged
    # tag set still doesn't cover current filings — surface this loudly rather
    # than silently shipping stale figures into the report. (9 months, not 6,
    # to avoid false positives in the gap between a fiscal year close and the
    # next 10-Q being filed/indexed.)
    if records:
        try:
            latest_end = datetime.strptime(records[0]["period_end"], "%Y-%m-%d")
            age_days   = (datetime.now() - latest_end).days
            if age_days > 274:  # ~9 months
                print(
                    f"  WARNING: latest R&D period for {company_name} ends "
                    f"{records[0]['period_end']} ({age_days} days ago, tag="
                    f"{records[0].get('_source_tag','?')}) — figures may be "
                    f"STALE. Check for a newer/renamed XBRL tag for this filer."
                )
        except ValueError:
            pass

    return records

# ---------------------------------------------------------------------------
# PUBLIC FUNCTION 4 — Fetch Filing Text for LLM Analysis
# ---------------------------------------------------------------------------

def get_filing_text(document_url: str, max_chars: int = 80000) -> str:
    text = _get_text(document_url)
    if not text:
        return ""

    # R4: the ONE source-text sanitiser (utils.text), applied at the ingress so
    # every filing-text consumer (runner extracts, financial pressure signals,
    # deal-document reads via filing_text_fn) receives readable text. The
    # previous inline regexes stripped NAMED entities only, so numeric forms
    # such as &#160; survived into rendered cells (review F9b). Applied to
    # plain-text documents too: SEC .txt renderings carry the same entities.
    text = sanitize_source_text(text)
    if not text:
        return ""

    if len(text) <= max_chars:
        return text

    print(f"  Filing truncated: {len(text):,} → {max_chars:,} chars")

    # NEW: for 8-Ks, bias toward the middle/back where Item 1.01 lives.
    # For 10-K/10-Q, the front matters more (MD&A, financials come early).
    # Simple heuristic: keep first 20k (cover page + items list) +
    # last (max_chars - 20k) chars (actual item content).
    front = text[:20000]
    back  = text[-(max_chars - 20000):]
    return front + "\n[...TRUNCATED...]\n" + back