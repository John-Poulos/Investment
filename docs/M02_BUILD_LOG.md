# M02 — Build log (running)

Updated: 2026-10-08 · Companion to M02_THEMES.md (decisions live there; this file holds what each build conversation needs) · Cross-module lessons: LESSONS.md

## How to use
- A build conversation reads M02_THEMES.md, then its part below, then LESSONS.md.
- Each part records: agreed spec (decision IDs), what to reuse, live-test labels, open items, and notes written during the build.
- Lessons that would help another module go to LESSONS.md, not here.

## Design review (2026-10-08 conversation)
One section per proposed amendment, discussed with the owner in order. Outcome lines are filled in as each is settled.

| # | Amendment | Outcome | Decision |
|---|---|---|---|
| 1 | Forward money flow from the guidance ledger | accepted, modified: positive for spender and suppliers; definition tags; stale flag; quoted theme link; call guidance from IR documents | D-M02-5, D-M02-6 |
| 2 | Gemini roles | modified: code mines phrases, Gemini names; phrase tests; code finds links, Gemini labels, owner confirms; use case 5b approved | D-M02-8, D-M02-9, D-SRCH-21 |
| 3 | Digest delivery | accepted, extended: weekly events + seasonal pass; per-item, grouped, cap 10/week; 5 item kinds; crowding flag | D-M02-10 |
| 4 | Tracked tier in the UI | accepted, extended: toml core + DB promoted; promotion suggestions; 12-month still-track review | D-M02-11 |
| 5 | Price budget for the tracked tier | dropped (premise wrong: cap counts unique symbols); revised for logon-only runs: watchlist daily, tracked 3-day rotation, 8 req/h kept for the app | D-M02-12 |
| 6 | News sources | modified: Tiingo News dropped; IR RSS polled; Finnhub + Massive; 11 trade-press feeds; arXiv, USAspending, Federal Register, Congress.gov | D-M02-13 |
| 7 | Search inputs | modified: 5/s pace; form.idx denominator; 10-page cap with lower bound; section + quantified rule; queued drill-down | D-M02-14 |
| 8 | Failure modes | approved: 12 rows + capex-funding row added; ★ guards are build requirements | D-M02-15 |

## Build parts (owner approved order 2026-10-09; one conversation each, Medium effort)
| Part | Covers | Decisions | Depends on | Live checks (owner runs) | Status |
|---|---|---|---|---|---|
| 1 Theme core | `config/themes.toml` seeds + DB themes/phrases with `discovered_at`; EFTS breadth with `form.idx` denominator, 10-page cap, lower bound; Themes tab v1 (share of filers, same window YoY) | D-M02-1, -14, -16 | M00 | EFTS probe (aggregations, NEAR/OR, 10-K/A); breadth for seed phrases | next |
| 2 Plumbing | Review kinds m02_theme/phrase/candidate/link/input/ir_download; weekly header, cap 10, suppression; guide panel; tracked tier tables + side panel core/promoted/tracked; promotion suggestion + 12-month review; price rotation (tracked 3-day) + 8/h app reserve; end-of-run summary box | D-M02-10, -11, -12 | 1 | one logon catch-up with tracked names | — |
| 3 Money flow | Capex components (clause tag, "definition changed", stale flag, own-definition actuals incl. finance-lease principal, funding coverage); new XBRL concepts; spender→theme quote link; per-spender view | D-M02-5, -15 | 1, 2 | guidance re-scan; MSFT/META checks | — |
| 4 Call guidance | Alpha Vantage adapter (probe done 2026-10-09: works, fiscal labels); allowed-site IR fetch (MSFT, MRVL, GFS, MU paced); Downloads pickup + m02_ir_download; PDF/DOCX/PPTX text; parser; grade B → A on match | D-M02-6 | 2, 3 | probe done 2026-10-09 | — |
| 5 Suppliers L0–L3 | Reverse lookup with alias table; L1 passages; Exhibit 10 ingest for Item 1.01; Gemini 5/5b; labelled precision set (~30); m02_link/m02_input | D-M02-7, -9, -15 | 1, 2 | NVDA reverse lookup; Gemini labels on the labelled set | — |
| 6 Seasonal pass | Corpus phrase mining; phrase tests (hits, ≥ N companies, industry spread, samples); Gemini 4 naming; candidate proposals (section + quantified rule); crowding flag; first-mention flags | D-M02-8, -10, -14, -15 | 1, 2, 5 | one seasonal run | — |
| 7 News & feeds | IR RSS; Finnhub + Massive; 11 trade-press feeds; arXiv, USAspending, Federal Register, Congress.gov; dedupe; weekly event digest content | D-M02-13, -15 | 2 | one weekly digest | — |

Effort: High only if a part raises a new design question; otherwise Medium. Each part: branch → fixture tests → owner live check → PR → merge (DESIGN.md workflow).

## Notes per part
(filled during the review and the builds)

### Money flow — capex guidance (D-M02-5)
- Reuse: `guidance/ledger.py` (metric `capex`), `guidance/changes.py` (raised/lowered…), `sec/xbrl_facts.py` concepts `capex` (`PaymentsToAcquirePropertyPlantAndEquipment`, fallback `PaymentsToAcquireProductiveAssets` — the fallback tag must be shown, M00_SEC_DATA open item) and `rpo`.
- Needed: concept for finance-lease principal (`FinanceLeasePrincipalPayments`) so Meta-style "capex incl. finance-lease principal" can be rebuilt for guided-vs-actual; parser keeps the "including/excluding …" clause per capex row; `changes.py` gains "definition changed" when clauses differ.
- 2026 reference values for tests and sanity checks (S80): Meta CY2026 $130–145B (release, incl. finance-lease principal; was $125–145B); Alphabet $195–205B (call; was $180–190B); Amazon ~$220B (call; was ~$200B); Microsoft ~$175B CY2026 (call; drop from ~$190B is the lease reclassification); Oracle FY27 $90–95B (secondary).
- Owner note: weighting of capex as a buy signal for the spender is revisited later (D-M02-5).
- Purchase obligations are not in the XBRL concept map yet; ≥10% customers are dimensional (not in company facts) → text only.

- Capex funding component (owner): capex vs operating cash flow, and debt/share issuance in the same period (XBRL concepts to add: operating cash flow, debt proceeds, share issuance proceeds — check the concept map).

### Supplier discovery L0–L3 (D-M02-7)
- L2 is the main free method: EFTS phrase = the customer's name (one quoted phrase per query, D-SEC-14), forms 10-K/10-Q, then fetch hit documents and find the sentence with FTS NEAR(name, customer / "accounted for" / "% of"). EFTS returns no text (S56), so each hit needs a document fetch (budget it).
- L1: customer's own Item 1 / 1A passages naming suppliers (check NVIDIA's 10-K wording in the stored corpus at build).
- L3: 8-K Item 1.01 events already catalogued (`events.py`); Exhibit 10 documents are not ingested by default (D-SEC-7 ingests primary + EX-99.1) → add EX-10.* for Item 1.01 filings of linked companies.
- Each link = review item until the owner confirms; rung + grade + quote stored; direction (who supplies whom) shown explicitly.
- Later rungs L4–L8 listed in D-M02-7.

### Phrase mining and tests (D-M02-8)
- Corpus n-gram counts per year over stored passages (`search/passages.py` output); flag rising 2–3-grams; drop stop-phrases and boilerplate (forward-looking-statement text, D-SRCH-20).
- EFTS breadth per phrase via `fulltext.count_by_window` (distinct companies need all hits fetched; EFTS aggregations return only top ~30 entities — live probe at build).
- Industry spread from hit SICs (`fulltext_hit.sics`).
- Gemini use case 4: prompt gets the mined cluster + sample passages; output = name + variants, each variant re-tested.

### Link labelling (D-M02-9)
- Hand-label ~30 passages first (fixture), measure Gemini precision + direction accuracy; record in this log.
- Real example for tests: NVIDIA FY2026 10-K names foundries TSMC, Samsung; memory SK Hynix, Micron, Samsung; assembly/test Hon Hai, Wistron, Fabrinet; CoWoS vendor unnamed. Commitments 2026-01-25 $95.2B manufacturing/supply/capacity; Q2 FY27 CFO commentary: supply commitments $119B → $279B, mostly memory (L4 example).
- Use case 5b prompt: Item 1/1A passages of one company → input categories with quotes.

### Digest and review items (D-M02-10)
- Reuse: `review_queue` table (module_id 'M02', kind, payload JSON), `engine/review.py` actions pattern, `/review` filters, guide panel (D-UI-15). New kinds: m02_theme, m02_phrase, m02_candidate, m02_link, m02_input.
- Suppression key per proposal (theme/phrase/company/link) + last shown components → re-raise only on material change (distinct filers doubled, new hard money-flow evidence).
- Weekly header = a grouping label on the queue page (no separate item); cap 10/week, overflow listed in the Themes tab.
- Seasonal schedule: ~Apr 15; ~50 days after Mar 31, Jun 30, Sep 30 (i.e. ~May 20, Aug 19, Nov 19). Denominator = distinct filers of the form family in the same window (EFTS total for a near-universal phrase, or SEC filing-count data; decide at build — S88).
- Crowding: EFTS forms N-1A, 485APOS (+ 485BPOS?) with the theme phrase, per window.

### Tracked tier (D-M02-11, D-M02-12)
- Tables: tier membership (cik, ticker, tier tracked/promoted, theme ids, reason, added_at, added_by, last_evidence_at) — owner id per U3 where personal.
- Refresh (runs at logon, PC off overnight): universe = toml core ∪ promoted (full jobs) and tracked (filing index + XBRL facts on new filings); prices: core + promoted daily, tracked in a 3-day rotation (by cik mod 3 or oldest-bar-first), soft cap ~150 tracked; price step ≤ 40 req/h so the app keeps 8/h (`prices/tiingo.py` budget check reads `fetch_log`); `scripts/run_refresh.py` `prices_step` today takes the resolved watchlist only.
- Keep refresh write transactions short (app writes during the run; busy_timeout 5 s). Task limit 3 h (`register_tasks.ps1`).
- End-of-run summary box (ctypes MessageBox already used by `ask_yes_no`) when downloads or review items are waiting.
- Side panel already reserves "Tracked" (M00_UI); add core/promoted labels.
- Review kinds: m02_candidate (accept → tracked), promotion suggestion, still-track review (12 months without new evidence).

### News and official feeds (D-M02-13)
- Reuse ideas (not code) from `reference/old_engine/ir_feeds.py`: feedparser-based fetch, entry cleaning, recency filter, keyword match. Adds a dependency (feedparser) → `uv add` asks the owner.
- IR RSS URLs (checked 2026-10-08): Q4 Inc `/rss/pressrelease.aspx` — investors.micron.com, investor.nvidia.com, investor.atmeta.com, investors.boeing.com (headline/link/date, no description); Notified `investors.gf.com/rss/news-releases.xml` (snippets); Intel `www.intc.com/news-events/press-releases/rss`; NVIDIA newsroom `nvidianews.nvidia.com/releases.xml`. Discovery rule: `<link type=rss>` on the press page, then vendor patterns. Store per company in config with date checked.
- Trade-press feed URLs: semiengineering.com/feed/, eetimes.com/feed/, servethehome.com/feed/, tomshardware.com/feeds.xml, datacenterdynamics.com/en/rss/, datacenterfrontier.com (`__rss/website-scheduled-content.xml?input={"sectionAlias":"home"}`), spacenews.com/feed/, nasaspaceflight.com/feed/, quantumcomputingreport.com/feed/, thequantuminsider.com/feed/, therobotreport.com/feed/.
- Finnhub `/company-news?symbol=&from=&to=` (key header), Massive `/v2/reference/news?ticker=` (5/min). Grade map by source domain in config.
- Official: arXiv API (1 req/3 s, one connection; count new preprints per phrase per month), USAspending `/api/v2/search/spending_by_award/` (recipient filter; POST JSON), Federal Register `/api/v1/documents.json?conditions[term]=`, Congress.gov (`CONGRESS_API_KEY`).
- Each feed behind one adapter (U7), its licence in DATA_SOURCES.md; tests use recorded fixtures only.

### Search inputs (D-M02-14)
- Live probe (owner runs, `scripts/run_live.py` label to add): EFTS aggregations (`entity_filter` bucket count, `sum_other_doc_count`?), `NEAR(n)` and OR through the API, `forms=10-K` vs 10-K/A, page size 100, `from` > 10,000 error.
- `fulltext.count_by_window` gains `max_pages` (10) and a lower-bound flag; companies from `entity_filter` when capped.
- Denominator: `full-index/{year}/QTR{n}/form.idx` (fixed-width; form, company, CIK, date, file) → distinct CIKs per form family per window; form families: 10-K (+10-K405 pre-2003, 10-KT?), 10-Q (+10-S if adopted, S88), 8-K, 20-F/40-F, N-1A/485APOS (crowding).
- Section tagging uses stored sections (`sec/sections.py`, items-1) and FTS5 NEAR over passages; "quantified" = a number, $, % or money word (revenue, capex, orders, backlog, million, billion) within ~10 words.
- Fetch queue table (accession, reason, queued_by, queued_at, fetched_at); `scripts/fetch_queued.py`; refresh drains it.

### Build requirements from the failure-mode table (D-M02-15)
- Store `discovered_at` on every phrase, theme, link and candidate (point-in-time backtests).
- First-mention flags: 8-K Item 5.03 (name change), S-1/S-3/424B* within ±90 days, reverse merger (8-K Items 2.01 + 5.01/5.06 shell), market cap below a micro-cap line (from prices × shares; line set at build).
- Per-spender contributions in every money-flow view.
- L2 alias table per customer (legal name, short name, ticker-free aliases) + nearby customer/revenue wording.
- News dedupe key (normalized URL; else title + date + company).

### Call guidance from IR documents (D-M02-6, DS1)
- Main spenders first: Alphabet, Amazon, Microsoft, Oracle (Meta's capex is in its release).
- Step 1: owner runs `uv run python scripts/probe_alpha_vantage.py` (7 requests; summary in logs/probe_av_*.txt, raw JSON in data/probe/alpha_vantage/). Answers: free-key access, coverage (AMZN, MSFT, ORCL, AAPL, TSLA), calendar vs fiscal `quarter`, capex wording present.
- **Result (logs/probe_av_20261009-000758.txt):** 7/7 HTTP 200, no premium/limit messages. Response `{symbol, quarter, transcript: [{speaker, title, content, sentiment}]}`; 24–61 turns, 35–57k characters per call. `quarter` = company fiscal label: MSFT 2026Q2 → FY26 Q2 call ("Capital expenditures were $37.5 billion in this quarter…"), MSFT 2026Q4 → July 2026 call ($41 billion), ORCL 2026Q3 → March 2026 call (analyst asks about FY2027 capex). ORCL 2027Q1 (Sept 2026 call) → `transcript: []` (empty = not available yet; missing, never "no guidance"). AAPL 2026Q3: no capex wording (Apple gives none). Raw JSON in data/probe/alpha_vantage/ (owner's machine only).
- Build notes from the probe:
  - Map ledger periods directly: company label FY2026 Q4 ↔ `2026Q4` (no calendar conversion).
  - Parse **management turns only** (title is an officer/IR role; skip Operator and analysts — analysts' questions carry capex numbers too).
  - Spoken guidance is often directional ("heavy CapEx the next few years", "FY27 capex to grow") → part-4 design question (direction-only row vs review queue; see M02_THEMES open questions). Expect new parser wording → review queue first.
  - `sentiment` per turn is a vendor score: stored, never used as a signal (unverifiable).
  - Empty transcript → retry on later runs for ~30 days, then queue `m02_ir_download`.
  - Budget: 25 requests/day → backfill 16 companies × 4 quarters ≈ 3 days; ongoing ≈ 16 per quarter. Key `ALPHA_VANTAGE_API_KEY` goes in the query string (Alpha Vantage requires it): never log URLs.
  - Fixtures: synthetic JSON in the same shape (vendor transcripts stay off GitHub).
- If Alpha Vantage fails: IR documents. Checked 2026-10-08 — transcripts: MSFT (DOCX, cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/TranscriptFY26Q4.docx), GOOGL (PDF, s206.q4cdn.com/479360582/files/doc_events/…), META (PDF, s21.q4cdn.com/399680738/files/doc_financials/<yr>/q<n>/), NVDA and BA (FactSet ©); prepared remarks with capex: MU (s25.q4cdn.com/621799436/…/Q4-FY26-Prepared-Remarks.pdf), INTC; CFO commentary: NVDA; Amazon audio only (DS9); Oracle/Apple none. Q4 Inc runs 10 of 13 sites and builds file links with JavaScript (needs a rendered page or the owner's download).
- Terms (not legal advice): NVDA, AAPL, INTC, BA, ORCL, AMZN bar robots; MU only above human pace; Google via robots.txt; MSFT, MRVL, GFS allow personal copies. Owner decision (2026-10-08): honour the terms — automatic fetch only for MSFT, MRVL, GFS (MU at human pace); all others via the **browser-download inbox**.
- Inbox design (build): folder from settings (default `data/inbox/ir/`, U5); the owner saves a file there; an ingest step (script and a UI page) asks or infers ticker, document type (transcript / prepared_remarks / cfo_commentary / slides), company period label and optional source URL; stores sha256, original filename, downloaded_at; moves the file to the store; text extracted, split into sections/passages, guidance parser run. Formats seen: PDF, DOCX, PPTX, HTML → text extraction needs new dependencies (e.g. pypdf, python-docx; `uv add` asks the owner).
- "I downloaded it" button: newest matching PDF/DOCX/PPTX in the Downloads folder (path from settings), name shown, ingest on confirm.
- Download checklist: when the nightly run sees an Item 2.02 8-K from a restricted-site spender, it queues `m02_ir_download` with the IR events page link and the expected documents; resolved when the file is ingested (or dismissed).
- Terms per site are recorded once (config, with the date checked) and drive auto-fetch vs inbox; re-check terms yearly.
- Grade B for third-party transcripts; A when the figure matches a company document or later filing (D-M02-6).
- Store whole in corpus.db as a company document type; same section/passage/FTS path; same guidance parser (expect new wording → review queue).
- One adapter (U7); record licence/terms in DATA_SOURCES.md.
