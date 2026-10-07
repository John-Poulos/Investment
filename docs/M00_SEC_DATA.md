# M00 — SEC data layer (core service)

Status: approved 2026-10-06 (storage condition met by M00_STORAGE.md) · Serves: M02, M04, M05, M07, M11 · Reuses: owner's sec_edgar.py, bd_tools.py, financial_intelligence.py, ir_feeds.py · Sources: S23, S24, S39–S43, S46, S56

## Purpose
One client for all SEC data — identity, filings, documents, full-text search, XBRL facts, peer frames, insider forms — where every result says whether it is data, a checked negative, or a failure.

## Rules
1. One HTTP client and one rate limiter for all SEC calls across threads; target ≤ 8 req/s (SEC limit: 10/s per user, regardless of machines).
2. `SEC_USER_AGENT` (name + email) required at startup; no placeholder.
3. Typed results: `Ok(data)`, `Empty(paths_checked)`, `Failed(reason)`. A failure never becomes empty data.
4. Throttle (403/429, or the "Request Rate Threshold Exceeded" page even under a 200) trips a breaker that pauses all SEC calls ≥ 10 min.
5. Cache raw responses by URL + params with per-endpoint TTL; parsers are versioned and re-run on cached raw; failures never cached; checked negatives cached briefly and labeled.
6. Missing stays missing — never coerced to zero.
7. Documents stored untruncated; consumers request sections (MD&A, segment note, earnings exhibit) (D22).
8. Every derived number carries `source_ref`, `method`, `as_of` (D13).

## Components
| File | Job | Reuses |
|---|---|---|
| client.py | HTTP, limiter, 5xx backoff, throttle breaker, typed results, raw cache | `_get_json` backoff; `SourceFetchFailed` |
| identity.py | Ticker↔CIK, name, SIC, fiscal year end; daily refresh | bd_tools `_resolve_ticker_ciks`; "paths tried" record. Drop pharma scoring |
| submissions.py | Filing index incl. older pages (`filings.files`); 8-K item codes | `get_company_filings` + paging |
| documents.py | Primary doc + EX-99.1; full text; section extraction | `resolve_filing_documents`; `get_filing_text` minus truncation |
| fulltext.py | The one EFTS client; tags the query variant used | `search_filings_text` + bd_tools EFTS rules (one phrase per query; no field syntax in q; forms/dates as params; SIC post-filter; ≤ 3 concurrent) |
| xbrl_facts.py | Concept reader: tag maps, unit checks, period normalizer, point-in-time | `get_rd_spend` merge/USD/form/staleness pattern, generalized |
| frames.py | One value per company per calendar period → peer medians (R24, CvD, G-score) | new |
| insiders.py | Form 4 XML parser; Insider Transactions Data Sets backfill (2006→; 10b5-1 flag) | new |
| events.py | 8-K items: 2.02 earnings (R19), 4.02 non-reliance, 1.01 agreements, 5.02 officers | ir_feeds EDGAR feeds as fallback |
| refresh.py | Backfill + nightly daily-index incremental (M00_STORAGE.md) | new |

## Period normalizer
- Classify durations (~90/180/270/365 days) and instants.
- 10-Q cash flows are year-to-date (Reg S-X 10-01(c)(3)): Q2 = 6M − Q1, Q3 = 9M − 6M, Q4 = FY − 9M; same derivation for income-statement Q4.
- TTM = last four discrete quarters (flows) or latest instant (balances).
- Label periods from start/end dates, not `fy`/`fp` (those describe the filing).

## Point-in-time store
Per (concept, period): first-reported value + filed date, and latest value + filed date (tables `fact`, `series` in M00_STORAGE.md). Backtests read as of a date; live views read latest; restatement deltas feed M04 earnings quality.

## Concept map (initial)
Revenue, cost of revenue, gross profit, operating income, net income, diluted EPS, R&D, SG&A, D&A, capex, PP&E net, inventory, receivables, cash, short-term investments, total assets, current assets and liabilities, total liabilities, long-term debt, retained earnings, equity, shares outstanding, operating cash flow, interest expense, RPO. Each: ordered us-gaap/ifrs-full candidate tags, merged across tag switches, unit-checked, method-tagged. Unmapped concepts are reported, never guessed by substring.

## Gaps outside this layer
- Segment/product/geographic data is dimensional → FSN data sets (DIM table) or per-filing XBRL. Evaluate EdgarTools first.
- Market prices → separate free source, TBD.

## Defects addressed
| Defect (source) | Fix |
|---|---|
| Fetch failure reads as "no data" (owner) | Rule 3 |
| Cache keys bypass TTLs; outages cached as zeros (owner) | Rule 5 |
| Filing text loses its middle (owner) | Rule 7 |
| Duplicate EFTS producer (owner) | fulltext.py |
| Separate delays per module, no shared limit (review) | Rule 1 |
| Throttle treated as non-retryable "no data" (review) | Rule 4 |
| "Quarterly" cash-flow window only matches Q1 year-to-date (review) | Period normalizer |
| Missing cash → 0 → runway 0 → "distressed" (review) | Rule 6 |
| Instant values picked across units (review) | Unit checks |
| Latest-filed dedupe leaks restatements into backtests (review) | Point-in-time store |
| Submissions read `recent` only (review) | Page `filings.files` |
| Earnings text = newest 8-K of any kind (review) | Filter Item 2.02 |
| EFTS unquoted fallback unlabeled (review) | Tag the variant |
| Substring tag guessing (review) | Concept map |
| Pharma CIK scoring penalizes "Inc" names (review) | Ticker file primary |

## Verify in first integration test
- `{accession}-index.json` exists and carries document types; else the resolver silently uses HTML.
- bd_tools' EFTS behaviors still hold.
- Throttle detection fires on a recorded block page (never by exceeding the limit).

## Decisions
- D-SEC-1 (2026-10-06): Plan approved by owner, conditional on database storage (addressed in M00_STORAGE.md).
- D-SEC-2 (2026-10-07): Built `client.py` (`sec/client.py`) and `identity.py`. HTTP 404 = `Empty` (checked negative); other 4xx fail without retry. While the throttle breaker is open, calls fail fast as `Failed(throttled)` rather than block, so the nightly job logs and moves on; `Retry-After` above 10 min extends it.
- D-SEC-3 (2026-10-07): identity reads both ticker files daily into ticker history; a ticker under two CIKs keeps the first seen and is reported as a conflict; a refresh listing under half the stored tickers is refused. EDGAR company-name search fallback deferred until its atom output is checked live; old pharma name scoring dropped.

## Open questions
- Rate limiter is per process: a second process calling SEC (e.g. UI during the nightly job) would add to the rate. Keep bulk fetching in the nightly job; revisit with a cross-process limiter if needed.
- EdgarTools: adopt only as a parser of content fetched by our client (keeps Rule 1's single limiter) — evaluate for XBRL dimensions and Form 4.
