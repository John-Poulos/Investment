# M00 — SEC data layer (core service)

Status: approved 2026-10-06 (storage condition met by M00_STORAGE.md) · Serves: M02, M04, M05, M07, M11 · Reuses: owner's sec_edgar.py, bd_tools.py, financial_intelligence.py, ir_feeds.py · Sources: S23, S24, S39–S43, S46, S56

## Purpose
One client for all SEC data — identity, filings, documents, full-text search, XBRL facts, peer frames, insider forms — where every result says whether it is data, a checked negative, or a failure.

## Rules
1. One HTTP client and one rate limiter for all SEC calls across threads; target ≤ 8 req/s (SEC limit: 10/s per user, regardless of machines).
2. `SEC_USER_AGENT` (name + email) required at startup; no placeholder.
3. Typed results: `Ok(data)`, `Empty(paths_checked)`, `NotFound(url)`, `Failed(reason)`. A failure never becomes empty data. `NotFound` (HTTP 404) means no file at that URL — a wrong or broken link, not proof of no data; only a source parser that has tried every known path may report `Empty`, listing each path.
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
- ~~`{accession}-index.json` exists and carries document types~~ — checked live 2026-10-07: it does not exist (404); `index.json` is a folder listing (type = icon name); `{accession}-index.htm` carries document types → documents.py parses the HTML index.
- bd_tools' EFTS behaviors still hold.
- Throttle detection fires on a recorded block page (never by exceeding the limit).

## Decisions
- D-SEC-1 (2026-10-06): Plan approved by owner, conditional on database storage (addressed in M00_STORAGE.md).
- D-SEC-2 (2026-10-07): Built `client.py` (`sec/client.py`) and `identity.py`. HTTP 404 = `NotFound` (D-SEC-4); other 4xx fail without retry. While the throttle breaker is open, calls fail fast as `Failed(throttled)` rather than block, so the nightly job logs and moves on; `Retry-After` above 10 min extends it.
- D-SEC-3 (2026-10-07): identity reads both ticker files daily into ticker history; a ticker under two CIKs keeps the first seen and is reported as a conflict; large changes are held for review (D-SEC-5). EDGAR company-name search fallback deferred until its atom output is checked live; old pharma name scoring dropped.
- D-SEC-4 (2026-10-07): 404 is `NotFound` ("no file or active link at this URL"), logged and cached as `not_found` for ≤ 6 h; never read as "no data" by the client (owner).
- D-SEC-5 (2026-10-07): The daily ticker refresh compares the full SEC ticker files with the stored map. It is held — stored map stays in use, lookups flagged stale, diff (added/dropped/changed) sent to the review queue — when more than 1% of stored tickers would drop or the count changes more than 10% either way. Owner approves with `force=True`. Dropped tickers only get an end date; history is kept. Every refresh is logged in `ticker_refresh_log` to calibrate the thresholds (owner).
- D-SEC-6 (2026-10-07): Built `submissions.py`. Reads `filings.recent` and every older page in `filings.files`; a page ingested once is skipped (closed date range). A page that fails or is not found leaves the sync incomplete with the page named, keeps the rows that loaded, and is retried next sync; mismatched or missing arrays are a failure, never fewer filings. One accession may be listed under several CIKs (Form 4 issuer + owner), so `filing_cik` links them. Earnings releases = 8-K with Item 2.02. Live 2026-10-07: AAPL 2,264 filings back to 1994 (1 older page); 94 of 233 8-Ks carry Item 2.02.
- D-SEC-7 (2026-10-07): Built `documents.py`. Reads the "Document Format Files" table of `{accession}-index.htm` (falls back to `-index.html`; both 404 → `Empty` listing both URLs), strips the `/ix?doc=` viewer prefix. Default ingest: primary document (type = form), plus EX-99.1 for 8-Ks. Raw bytes kept in the HTTP cache (10-year TTL, filings immutable); text extracted by a versioned stdlib HTML parser (drops script/style/`ix:header`, decodes entities, tab-separates table cells), stored whole with one "whole" FTS5 section until the section splitter exists. Wanted types not in the index are reported, not silently skipped.
- D-SEC-8 (2026-10-07): Built `xbrl_facts.py` (parser facts-1). Every companyfacts fact is stored in `fact` with filed date and accession; repeated values keep every version. Concept map (26 concepts) with ordered us-gaap/ifrs-full/dei tags; per period the highest-priority tag wins, so tag switches merge; tags within a concept must mean the same thing (no broader fallback, e.g. `LongTermDebt` is not a fallback for the noncurrent concept). Units: USD preferred, else the company's main currency; other units skipped and reported. Periods classified by length (Q 80–105 days, 6M, 9M, FY 350–380, instant). Missing quarters derived from year-to-date facts sharing a start; direct quarters win. TTM only from four contiguous quarters. Per-share and share counts are non-additive: never derived or summed. `series` stores Q, FY, TTM, I with first and latest version; derived values use the later component's accession and the later filed date. Refresh when 7 days old or a newer 10-K/10-Q/20-F/40-F or Item 2.02 8-K is in the filing index.
- D-SEC-9 (2026-10-07): Built `frames.py`. Frames (one value per company per calendar period, all filers) are fetched per candidate tag; each company gets its highest-priority tag's value (same order as xbrl_facts) with the tag kept. 404 = tag unused that period (remembered 30 days); fetch failures mark the result incomplete. Frames stored whole and refreshed after 30 days (earnings-season refresh by `force`). Peer stats: median, quartiles, robust z = (x − median) ÷ (IQR ÷ 1.35); peers without a value listed, never zero; < 5 peers flagged low confidence; zero IQR → z undefined. Frame TTM = four calendar-quarter frames, only for companies with all four. Live 2026-10-07: calendar-Q4 frames are sparse (CY2024Q4 85 KB vs ~400 KB for other quarters; most companies report Q4 only inside the annual figure), so frame TTM covered almost no semis. Decision: peer TTM, quarterly flows and YoY come from each peer's own xbrl_facts series (`series_values`, `series_yoy`: closest period within 45 days, so off-calendar fiscal years compare; YoY only when the earlier value is positive). Frames stay the source for instants, annual values and market-wide breadth; AAPL frame values matched its own series exactly. SIC peer discovery (frames carry no SIC) is open.

## Open questions
- Rate limiter is per process: a second process calling SEC (e.g. UI during the nightly job) would add to the rate. Keep bulk fetching in the nightly job; revisit with a cross-process limiter if needed.
- Fallback tags (owner 2026-10-07): when a value comes from a lower-priority tag (e.g. capex from `PaymentsToAcquireProductiveAssets`, which can include intangibles), the tag name must reach the user so they know it is not a like-for-like comparison. The tag is already carried on every value (`series.method`, `FrameValue.tag`); UI display and whether such values are excluded from comparisons → full discussion at M04.
- Shares outstanding (owner 2026-10-07): cover-page (dei, near filing date) and balance-sheet (period end) counts differ in timing; variance likely small. Recommendation: separate concepts — period-end count (book value per share), cover-page count (market cap, float, R22 % of float), and weighted-average diluted shares (per-share metrics) — rather than one mixed series. Raise at M04/M07.
- SIC peer discovery: frames carry no SIC. Options: EDGAR company browse by SIC (check output live) or the bulk submissions file. Decide when building peer groups (D19).
- EdgarTools: adopt only as a parser of content fetched by our client (keeps Rule 1's single limiter) — evaluate for XBRL dimensions and Form 4.
