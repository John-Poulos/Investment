# M00 — SEC data layer (core service)

Status: approved 2026-10-06 (storage condition met by M00_STORAGE.md) · Serves: M02, M04, M05, M07, M11 · Reuses: owner's sec_edgar.py, bd_tools.py, financial_intelligence.py, ir_feeds.py · Sources: S23, S24, S39–S43, S46, S56

## Purpose
One client for all SEC data — identity, filings, documents, full-text search, XBRL facts, peer frames, insider forms — where every result says whether it is data, a checked negative, or a failure.

## Rules
1. One HTTP client and one rate limiter for all SEC calls across threads; paced at 5 req/s (SEC limit: 10/s per user, regardless of machines; D-SEC-18).
2. `SEC_USER_AGENT` (name + email) required at startup; no placeholder.
3. Typed results: `Ok(data)`, `Empty(paths_checked)`, `NotFound(url)`, `Failed(reason)`. A failure never becomes empty data. `NotFound` (HTTP 404) means no file at that URL — a wrong or broken link, not proof of no data; only a source parser that has tried every known path may report `Empty`, listing each path.
4. Throttle (429, or SEC's block page — "Request Rate Threshold Exceeded" / "Undeclared Automated Tool" — under any status) trips a breaker that pauses all SEC calls ≥ 10 min. A bare 403 is a failure (Archives return 403 for unpublished files); 3 in a row trip the breaker (D-SEC-16).
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

## Event severity defaults (approved by owner 2026-10-07, D-SEC-12)
Defaults for alerting only (M01 rule 6); weights adjustable later; the owner decides (D8, D16).

| Severity | 8-K items |
|---|---|
| high | 1.03 bankruptcy · 2.04 debt acceleration · 3.01 delisting notice · 4.02 non-reliance · 5.01 change in control |
| medium | 1.01 / 1.02 material agreement entered / ended · 1.05 cybersecurity incident · 2.01 acquisition or disposal · 2.02 earnings · 2.05 exit costs · 2.06 impairment · 3.02 unregistered equity sales · 3.03 holder-rights change · 4.01 auditor change · 5.02 officer/director change · 5.06 shell status |
| low | 1.04 mine safety · 2.03 new debt · 5.03–5.05, 5.07, 5.08 governance · 7.01 Reg FD · 8.01 other events · 6-K · unknown codes |
| none | 6.xx asset-backed · 9.01 exhibits |
## Decisions
- D-SEC-1 (2026-10-06): Plan approved by owner, conditional on database storage (addressed in M00_STORAGE.md).
- D-SEC-2 (2026-10-07): Built `client.py` (`sec/client.py`) and `identity.py`. HTTP 404 = `NotFound` (D-SEC-4); other 4xx fail without retry. While the throttle breaker is open, calls fail fast as `Failed(throttled)` rather than block, so the nightly job logs and moves on; `Retry-After` above 10 min extends it.
- D-SEC-3 (2026-10-07): identity reads both ticker files daily into ticker history; a ticker under two CIKs keeps the first seen and is reported as a conflict; large changes are held for review (D-SEC-5). EDGAR company-name search fallback deferred until its atom output is checked live; old pharma name scoring dropped.
- D-SEC-4 (2026-10-07): 404 is `NotFound` ("no file or active link at this URL"), logged and cached as `not_found` for ≤ 6 h; never read as "no data" by the client (owner).
- D-SEC-5 (2026-10-07): The daily ticker refresh compares the full SEC ticker files with the stored map. It is held — stored map stays in use, lookups flagged stale, diff (added/dropped/changed) sent to the review queue — when more than 1% of stored tickers would drop or the count changes more than 10% either way. Owner approves with `force=True`. Dropped tickers only get an end date; history is kept. Every refresh is logged in `ticker_refresh_log` to calibrate the thresholds (owner).
- D-SEC-6 (2026-10-07): Built `submissions.py`. Reads `filings.recent` and every older page in `filings.files`; a page ingested once is skipped (closed date range). A page that fails or is not found leaves the sync incomplete with the page named, keeps the rows that loaded, and is retried next sync; mismatched or missing arrays are a failure, never fewer filings. One accession may be listed under several CIKs (Form 4 issuer + owner), so `filing_cik` links them. Earnings releases = 8-K with Item 2.02. Live 2026-10-07: AAPL 2,264 filings back to 1994 (1 older page); 94 of 233 8-Ks carry Item 2.02.
- D-SEC-7 (2026-10-07): Built `documents.py`. Reads the "Document Format Files" table of `{accession}-index.htm` (falls back to `-index.html`; both 404 → `Empty` listing both URLs), strips the `/ix?doc=` viewer prefix. Default ingest: primary document (type = form), plus EX-99.1 for 8-Ks. Raw bytes kept in the HTTP cache (10-year TTL, filings immutable); text extracted by a versioned stdlib HTML parser (drops script/style/`ix:header`, decodes entities, tab-separates table cells), stored whole with one "whole" FTS5 section until the section splitter exists. Wanted types not in the index are reported, not silently skipped.
- D-SEC-8 (2026-10-07): Built `xbrl_facts.py` (parser facts-1). Every companyfacts fact is stored in `fact` with filed date and accession; repeated values keep every version. Concept map (26 concepts) with ordered us-gaap/ifrs-full/dei tags; per period the highest-priority tag wins, so tag switches merge; tags within a concept must mean the same thing (no broader fallback, e.g. `LongTermDebt` is not a fallback for the noncurrent concept). Units: USD preferred, else the company's main currency; other units skipped and reported. Periods classified by length (Q 80–105 days, 6M, 9M, FY 350–380, instant). Missing quarters derived from year-to-date facts sharing a start; direct quarters win. TTM only from four contiguous quarters. Per-share and share counts are non-additive: never derived or summed. `series` stores Q, FY, TTM, I with first and latest version; derived values use the later component's accession and the later filed date. Refresh when 7 days old or a newer 10-K/10-Q/20-F/40-F or Item 2.02 8-K is in the filing index.
- D-SEC-9 (2026-10-07): Built `frames.py`. Frames (one value per company per calendar period, all filers) are fetched per candidate tag; each company gets its highest-priority tag's value (same order as xbrl_facts) with the tag kept. 404 = tag unused that period (remembered 30 days); fetch failures mark the result incomplete. Frames stored whole and refreshed after 30 days (earnings-season refresh by `force`). Peer stats: median, quartiles, robust z = (x − median) ÷ (IQR ÷ 1.35); peers without a value listed, never zero; < 5 peers flagged low confidence; zero IQR → z undefined. Frame TTM = four calendar-quarter frames, only for companies with all four. Live 2026-10-07: calendar-Q4 frames are sparse (CY2024Q4 85 KB vs ~400 KB for other quarters; most companies report Q4 only inside the annual figure), so frame TTM covered almost no semis. Decision: peer TTM, quarterly flows and YoY come from each peer's own xbrl_facts series (`series_values`, `series_yoy`: closest period within 45 days, so off-calendar fiscal years compare; YoY only when the earlier value is positive). Frames stay the source for instants, annual values and market-wide breadth; AAPL frame values matched its own series exactly. Live re-run: frame TTM covered 257 of 4,227 companies (no semis); own-series TTM YoY for 8 semis to ~2025-06-30: median +21.5%, NVDA +71.6% (z +2.30), INTC −3.7% (z −1.16); NVDA TTM equals the sum of its four reported quarters. Peer period ends spanned 2025-05-29 (MU) to 2025-08-03 (AVGO): each value carries its end date; how much offset M04 tolerates is for M04 (set by D-M04-5). SIC peer discovery (frames carry no SIC): D-M04-4.
- D-SEC-10 (2026-10-07): Built `insiders.py` (parser form4-1). Source is raw Form 4 XML (structured since 2003; the issuer's submissions list every Form 4), so raw filings cover the full history (R13); the Insider Transactions Data Sets backfill is deferred until its layout is checked live. XML = primary document without the rendering folder (`xslF345X05/`), falling back to the filing index; raw bytes go to the parser so the declared encoding is honoured. Every non-derivative and derivative transaction is a row (holdings are not); joint filings keep every owner in `form4_doc.owners`, rows carry the first owner and role. 10b5-1 is judged per row (live 2026-10-07: the 2023+ `aff10b5One` checkbox is per form, so copying it to every row marked a gift and an RSU conversion as plan trades). Yes = a row footnote says the trade was under a 10b5-1 plan; no = a row footnote says it was not, or the checkbox is explicitly unset; NULL = checkbox set but row not identified (form flag kept on `form4_doc`), or nothing disclosed; `plan_basis` records which. Codes G (gift), A (grant), M (exercise/conversion), F (tax withholding) are reported with the filer's price (gifts often 0); M07 must exclude them from $ sale totals (R22). Live re-run (AAPL, 60 Form 4s, 170 rows): 43 of 48 sales flagged yes from row footnotes; 5 sales from forms with the checkbox unset (not plan trades); no G/A/M/F row flagged yes without row evidence. Missing prices stay NULL. Sync parses each Form 4 once per parser version, newest first, with an optional cap; a throttle stops the run.
- D-SEC-11 (2026-10-07): Built `events.py` (catalog items-2026-10). One event per 8-K / 8-K/A item from the stored filing index (no extra SEC calls); 6-K = one foreign-report event. Every Form 8-K item is catalogued with a category and default severity; codes outside the catalog (pre-2004 numbering, 8-Ks without items) are kept as "unknown", never dropped. `ingest_event_documents` stores the filing text so sections like "8-K Item 4.02" can be read later. The old engine's per-company EDGAR Atom feed is not reimplemented: the nightly daily index (refresh.py) detects new filings for every company at once.
- D-SEC-12 (2026-10-07): Event severity defaults approved as proposed (owner); weights can be adjusted later. Live (AAPL): 413 events from 236 current reports; 94 earnings events = Item 2.02 filings; 37 events "unknown" are pre-August-2004 item numbers (1–12, e.g. old Item 12 = earnings).
- D-SEC-13 (2026-10-07): Pre-2004 8-K items mapped onto current items for backtesting (owner): old 1→5.01, 2→2.01, 3→1.03, 4→4.01, 5→8.01, 6→5.02, 7→9.01, 8→5.03, 9→7.01, 10→5.05, 11→5.04, 12→2.02, applied only to filings before 2004-08-23; the event keeps the original code and the title shows the mapping (catalog items-2026-10.1). Plain numbers after that date stay "unknown".
- D-SEC-14 (2026-10-07): Built `fulltext.py`, the one EFTS client, carrying over bd_tools' confirmed rules: one quoted phrase per query (merge by accession across phrases), no field syntax / operators / groups in `q` (rejected before any call), forms and dates as parameters, SIC filter after the fetch (hits without SIC kept), at most 3 queries in flight. Totals at EFTS's 10,000 limit are flagged `capped`. A quoted phrase that gets an HTTP 5xx falls back to its unquoted terms, labeled `terms (fallback)`; trend counts never fall back, so every window counts the same thing. Queries and matched filings are stored (`fulltext_query`, `fulltext_hit`); failed windows stay missing, not zero. Raw responses cached 6 h for windows touching the last week, 30 days for older ones. Live 2026-10-07: EFTS counts documents, not filings (a Micron 10-Q matched in two exhibits), so window counts also give distinct filings and companies when every hit was fetched (else missing). "high bandwidth memory" 10-K documents 2019→2025: 4, 5, 6, 4, 6, 10, 12. `earnings_releases` now includes pre-2004 Item 12 so it matches the earnings events (AAPL 98). Re-run: yearly 10-K documents = distinct filings = distinct companies (4, 5, 6, 4, 6, 10, 12), so no exhibit double-counting in that series; the guard matters for 10-Q/8-K windows where exhibits match.
- D-SEC-15 (2026-10-07): Built `refresh.py` (nightly job; M00_STORAGE "Nightly refresh as built"). Watchlist (owner): AAPL, TSLA, MU, MSTR, SPCX (SpaceX), MSFT, AMZN, GOOG, BA, NVDA, ETV (closed-end fund, no 10-K), GFS, INTC, META, MRVL, INFQ; M02 may later recommend additions (owner decides). Missed runs: the job catches up all missed days; at logon the owner is asked before a catch-up (owner choice). The client gained `fresh=True` to bypass a cached copy when the daily index shows a new filing.
- D-SEC-16 (2026-10-07): First live refresh stopped on a false throttle. Two fixes: (1) market dates are US Eastern (`MARKET_TZ`), so an evening run asks for yesterday's index, not the day still in progress (21:32 ET is already the next day in UTC); (2) a bare HTTP 403 is a failure, not a throttle: SEC Archives answer 403 for files not yet published. A throttle is now 429 or SEC's block page ("Request Rate Threshold Exceeded" / "Undeclared Automated Tool"); 3 bare 403s in a row still trip the breaker as a safeguard; 403/throttle bodies are logged. A 403 daily index is treated like a missing one (pending, or holiday when old). Runs stopped by a throttle or error do not count as done for the missed-run check.
- D-SEC-17 (2026-10-07): Second live refresh crashed on a duplicate series key: a watchlist company reported the same fiscal period with start dates a day apart. `xbrl_facts` now keeps one point per (type, end) — newest filing wins, ties go to the longer period — and names the alternative in the method ("also reported as …"). The refresh now records an unexpected error as that company's failure (with file:line) and continues; only a throttle stops a run; a failed backfill is retried next run. Backfill completed 2026-10-07 (run 4 ok); `scripts/check_tickers.py` confirmed SPCX = SPACE EXPLORATION TECHNOLOGIES CORP.
- D-SEC-18 (2026-10-07): Pace lowered from 8/s to 5/s. fetch_stats on the backfill: ~4,000 requests in ~15 min, peaks 81 per 10 s and 451 per 60 s (7.5–8/s) — within our target and SEC's published 10/s, yet the next run's first request got a 429 block page. Sustained bulk near the limit is not tolerated; 5/s keeps the 16-company backfill to ~15 min. `scripts/fetch_stats.py` summarises request rates from fetch_log for future throttle diagnosis.

## Open questions
- Rate limiter is per process: a second process calling SEC (e.g. UI during the nightly job) would add to the rate. Keep bulk fetching in the nightly job; revisit with a cross-process limiter if needed.
- Fallback tags (owner 2026-10-07): when a value comes from a lower-priority tag (e.g. capex from `PaymentsToAcquireProductiveAssets`, which can include intangibles), the tag name must reach the user so they know it is not a like-for-like comparison. The tag is already carried on every value (`series.method`, `FrameValue.tag`); UI display and whether such values are excluded from comparisons → full discussion at M04.
- Shares outstanding (owner 2026-10-07): cover-page (dei, near filing date) and balance-sheet (period end) counts differ in timing; variance likely small. Recommendation: separate concepts — period-end count (book value per share), cover-page count (market cap, float, R22 % of float), and weighted-average diluted shares (per-share metrics) — rather than one mixed series. Raise at M04/M07.
- SIC peer discovery: frames carry no SIC. Options: EDGAR company browse by SIC (check output live) or the bulk submissions file. Decide when building peer groups (D19).
- Insider Transactions Data Sets (2006→): add as a bulk backfill only if per-filing Form 4 fetching proves too slow; verify file layout and 10b5-1 field live first.
- EdgarTools: adopt only as a parser of content fetched by our client (keeps Rule 1's single limiter) — evaluate for XBRL dimensions and Form 4.
