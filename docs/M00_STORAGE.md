# M00 — Storage & refresh (SQLite)

Status: approved (D25) · Updated: 2026-10-13 · Serves: all modules · Sources: S39, S42, S48–S53

## Purpose
Hold everything the engine knows in SQLite so lookups read locally first and SEC is called only for what changed.

## Files (local disk, outside OneDrive-synced folders)
| File | Contents | Backup |
|---|---|---|
| data/engine.db | Entities, tickers, peer groups, filing index, XBRL facts, normalized series, insider trades, signals, guidance ledger, review queue, positions/lots, decisions | Nightly online backup; the one to protect |
| data/corpus.db | Documents, sections, passages, FTS5 indexes, raw HTTP cache | Rebuildable from SEC |

Settings: WAL mode, `busy_timeout` 5 s, foreign keys on, `synchronous=NORMAL`. WAL needs every process on the same machine (no network drives); readers and one writer run concurrently.

## Core tables (engine.db)
| Table | Key | Notes |
|---|---|---|
| entity | cik | name, SIC, fiscal year end, exchange, filer category (submissions `category`) |
| ticker | ticker, valid_from | maps to cik; keeps ticker history |
| peer_group / peer_member | group_id, cik | source = SIC or owner (D19) |
| filing | accession | cik (first lister), form, filed, accepted_at, report_date, 8-K items, primary_doc, is_xbrl, is_inline_xbrl, size, ingested_at |
| filing_cik | accession, cik | every CIK whose submissions list the accession |
| fact | cik, taxonomy, tag, unit, start, end, accession | every reported value with filed date (point-in-time) |
| series | cik, concept, period_end, period_type | first and latest value + accessions, method, parser_version |
| frame_value | taxonomy, tag, unit, frame, cik | peer-median source |
| insider_txn | accession, line | issuer, owner, role, code, shares, price, shares_after, 10b5-1 flag, ownership nature, derivative terms, referenced footnotes, `replaced_by` (the Form 4/A that replaces the row, M07 rule 7) |
| form4_doc | accession | one row per parsed Form 4: issuer, doc type, period, all reporting owners (JSON), 10b5-1 checkbox, parser version |
| form4_holding | accession, line | holding lines without a transaction (form4-2): table kind, title, shares owned, D/I, nature, footnotes (D-SEC-27; D-STO-30) |
| insider_class | owner_cik, issuer_cik, year | M07 Cohen-Malloy-Pomorski class (routine / opportunistic / unclassified), years used, months seen, reason; derived, replaced per issuer (D-M07-9; D-STO-30) |
| signal | cik, module_id, signal, timeframe, as_of | D13 record; ticker for display; `value` numbers only, `value_text` states; missing = both empty + "missing: <reason>" (D-M04-9, -74; D-STO-19) |
| entity_link | predecessor_cik, successor_cik, kind | predecessor CIKs and de-SPAC shell periods with their boundary date (D-STO-19) |
| cover_shares | accession, class_label | per-class cover counts from R1 pages, cover date, error-correction flag (D-M04-2) |
| capex_split | cik, period_end | total capex (own-history tag), definition-changed flag, maintenance, growth, method and rung, Greenwald net/gross in range only, marks (D-M04-6; D-STO-20) |
| guidance_outcome | cik, kind, metric, basis, period | score or removal outcome, state, actual and reference, grade, revisions, reason passage (D-M04-10, -79, -84, -85; D-STO-20, -21) |
| company_stage | cik, period_end | life-cycle stage per latest fiscal year: computed Dickinson stage (2 of 3 on core investing), per-year signs (JSON), revenue CAGR 3y, review reasons, the owner's confirmation (stage, by, at, item) (D-M04-7, -12; D-STO-22) |
| m04_proposal | prop_key | M04 review proposals: kind, payload, D-M04-71 priority group, capped, baseline, status queued / overflow / baseline (D-STO-22) |
| peer_candidate | target_cik + candidate_cik or name | ranked SIC shortlist and owner-added peers (CIK or non-SEC name), active form and date, ranking revenue, status proposed / struck / confirmed (D-M04-4; D-STO-22) |
| sic_listing / sic_browse | sic, cik, browsed; sic, browsed | browse-by-SIC listings and the pages read, one browse per SIC (`browsed` = 10-K; older per-form rows are replaced on the next browse), partial when the page cap was reached on a full page (D-STO-22) |
| fact_dim | accession, concept, dims, period, unit | dimensional facts from filing instances on the kept axes (customers, segments, products or services, classes of stock), as filed (D-M04-42; D-STO-25) |
| unit_metric | cik, metric, line, period_label, accession | unit KPIs, credits (kept separate) and company-stated non-GAAP rows with quote and extractor (D-M04-42; D-STO-25) |
| credit_line | line_id (cik, status, as_of indexed) | undrawn committed credit for the survival-gate runway: facility, undrawn amount, maturity, the balance-sheet date it was stated for, source sentence or URL, accession, passage (Part 4b), origin owner / finder, status proposed / confirmed / rejected / withdrawn, grade, confirmer and dates; never deleted (D-M04-32, -86; D-STO-26) |
| gate_text | accession, filename, start_offset (cik, filed indexed) | going-concern and covenant sentences of stored periodic text: form, period end, family, class, base effect (fail / warn / hypothetical / none / excluded), verified quote, passage, exhibit flag, note, baseline, item link, owner answer; which rows act on the gate is decided at read time (current report); per-document scan record in `refresh_state` (D-M04-34, -95…98; D-STO-28) |
| estimate_change | cik, accession, start_offset | estimate-change sentences by filing version: amount, basis, denominator, share, band, quote, owner answer (D-M04-17, -92; D-STO-27) |
| special_item | cik, period_end, source, what, accession | recurring "one-time" charges per fiscal year: tag amount or wording sentence (D-M04-19, -93; D-STO-27) |
| market_share | share_id (cik, market, period_end indexed) | owner-entered market share: period, share %, market, optional market size, source and URL, grade A (share of a filing-stated industry total) or B (third party), status active / withdrawn, who and when (D-M04-68, -105; D-STO-29) |
| filing_status | cik, period_end, form | category carried and its source, deadline, due date, NT, filed, current/stale/overdue, note (D-M04-36, -61) |
| llm_call / llm_observation / llm_citation | ids | every owner-initiated LLM call (model, prompt version, tokens, cost, raw reply); its observations (verified or rejected with reason); citations by accession, file, offsets, quote, doc sha256 (M00_SEARCH D-SRCH-19). The 0001 `extraction` table is unused. |
| guidance / guidance_scan | id; accession, filename | R19 ledger parsed by code: metric, basis, period, value (low/high/point/spread), prior, stated_on, exact quote + offsets, period source, doc sha256, parser version; one scan row per release (parsed/none/review) |
| event | accession, item, cik | one row per 8-K item: category, severity, title, consuming modules, amended flag, catalog version |
| fulltext_query / fulltext_hit | query_id; query_id, accession, filename | each EFTS query run (phrase, variant, forms, window, total, capped) and the filings it matched |
| review_queue | id | D8 items awaiting owner |
| position / lot / decision | ids | owner portfolio, tax lots, profile of record (D12) |
| fetch_log | id | every call (SEC and Tiingo; never a key): url, outcome (ok/not_found/failed/throttled), detail, at — also the shared Tiingo request budget |
| refresh_run / refresh_day | run_id; day | each nightly run (trigger, status, report) and each daily-index day (processed / no_index / pending) |
| ticker_refresh_log | id | each ticker-map refresh: counts (stored, listed, added, changed, dropped), applied/held/forced |
| refresh_state | name | last refresh of reference files (e.g. ticker map) for read-path freshness |
| price_bar / price_fetch | symbol, date; symbol | daily bars from Tiingo (raw + adjusted OHLCV, dividend, split) and per-symbol fetch state (D-UI-8) |
| schema_version | version | ordered migrations |

## Read path (every lookup)
1. Read the stored copy with `fetched_at` and the newest filing known for that company.
2. Fresh if it reflects every known filing and is within its backstop age → serve; no SEC call.
3. Otherwise call SEC via the shared client; on `Ok`, write raw + parsed in one transaction, then serve.
4. On `Failed`, serve the stored copy flagged stale (never a blank); on `Empty`, record the checked negative.

Freshness is event-driven (SEC data changes only when a company files); backstops catch the rest.

| Data | Backstop age |
|---|---|
| Filing index (submissions) | 1 day |
| Company facts | 7 days, or immediately after a new 10-K/10-Q/10-KT/20-F/40-F, an XBRL 6-K or an 8-K Item 2.02 |
| R1 cover page | Never (one read per filing; outcome kept in `refresh_state` r1:<accession>) |
| Filing status | Recomputed from the calendar on every run (local) |
| Frames (peer medians) | 30 days; refresh in earnings season |
| Documents | Never (immutable; amendments are new accessions) |
| Ticker map | 1 day |

## Refresh jobs (Windows Task Scheduler)
- **Backfill (once, or when companies are added):** per-company API calls for watchlist + peers. Bulk ZIPs only if the universe grows into the thousands (submissions.zip alone ≈ 2 GB).
- **Nightly (e.g. 02:00 ET):** daily index for prior business days → diff against stored accessions → fetch new filings for the universe → re-parse affected facts/series → index new documents → recompute signals → run report (counts, failures, throttles). Late-filed ownership forms land in the next day's index, so each run rechecks the prior day.
- Documents stored for watchlist + owner-chosen peers; other peers get facts only.

## Nightly refresh as built (D-SEC-15)
- `scripts/run_refresh.py` → `engine.refresh.run_refresh`; watchlist in `config/watchlist.toml` (owner list 2026-10-07; unresolved tickers reported every run and kept).
- Reads `daily-index/{year}/QTR{q}/master.{YYYYMMDD}.idx` for every business day after the last finished one, plus the previous day again; days are `processed`, `no_index` (missing and older than 3 days = holiday) or `pending` (retried next run). A missed night is caught up by the next run.
- For each watchlist company that filed, and each company seen the first time (backfill: Form 4s for `form4_years` = 4 years since D-M07-1 (3 before), latest 10-K and 10-Q, last 4 earnings 8-Ks): filing index (fresh fetch), events, Form 4s, facts (forced when a 10-K/10-Q/20-F/40-F filed), documents of new 10-K/10-Q/8-K/20-F/6-K filings.
- Run report in `logs/refresh_<timestamp>.txt` and `refresh_run`; a throttle stops the run with days left pending. One run at a time (`data/refresh.lock`).
- Scheduling (`scripts/register_tasks.ps1`, owner runs it): task 1 daily 02:00 local, wakes from sleep, runs only while logged on (locked is fine). Task 2 at logon: if the 02:00 run was missed, a Windows prompt asks before catching up (owner choice 2026-10-07); "No" is remembered for that night.

## Windows notes
- Repo and data under a local path such as `C:\dev\...`, not OneDrive-synced Documents/Desktop.
- Declare `tzdata` as a dependency (no IANA time zone database on Windows).
- No per-ticker filenames: keys live in SQLite; any file is named by CIK (reserved names like CON/PRN and colons fail on Windows).
- Open text files with `encoding="utf-8"`.
- Verified on owner's machine 2026-10-06: FTS5 present, tzdata installed. Re-run the check under uv's Python after `uv sync`.
- FTS5 check: `python -c "import sqlite3; print([r for r in sqlite3.connect(':memory:').execute('pragma compile_options') if 'FTS5' in r[0]])"` must print `('ENABLE_FTS5',)`.

## Failure modes
| Risk | Guard |
|---|---|
| Sync tool copies DB mid-write | Local path outside OneDrive |
| Writers contend | Nightly job is the only bulk writer; UI writes small transactions; busy_timeout |
| Stale data served silently | Stale flag + fetched_at shown in UI |
| Schema drift | schema_version + ordered migrations; tests migrate an empty DB |

## Decisions
- D-STO-1 (2026-10-06): SQLite (owner). Nightly incremental from the daily index replaces nightly full bulk.
- D-STO-2 (2026-10-07): Design approved by owner (D25, was P8).
- D-STO-3 (2026-10-07): Schema 0001 built (`engine/store/migrations/`). corpus.db: `document` holds full text, `section` holds offsets, `section_fts` is a self-contained FTS5 table (porter unicode61) so snippet()/highlight() work; `http_cache` holds raw responses. Instant facts have NULL period_start; uniqueness via an expression index. Each migration runs in one transaction with its schema_version row.
- D-STO-4 (2026-10-07): Migration 0002 rebuilds `fetch_log` and `http_cache` for the `not_found` outcome (D-SEC-4) and adds `ticker_refresh_log` (D-SEC-5).
- D-STO-5 (2026-10-07): Migration 0003 adds `filing_cik` and filing `is_inline_xbrl`, `size` (D-SEC-6).
- D-STO-6 (2026-10-07): corpus migration 0003 adds document `parser_version`, `encoding`, `raw_size`, `description` (D-SEC-7).
- D-STO-7 (2026-10-07): corpus migration 0004 adds section `title`, `splitter_version` and `split_log` (one row per document: outcome split/fallback/single, sections found, required items missing) (D-SRCH-4).
- D-STO-8 (2026-10-07): engine migration 0004 adds `frame_value.period_start` (D-SEC-9).
- D-STO-9 (2026-10-07): engine migration 0005 adds `form4_doc` and Form 4 detail columns on `insider_txn` (D-SEC-10).
- D-STO-10 (2026-10-07): engine migration 0006 adds `event` (D-SEC-11).
- D-STO-11 (2026-10-07): engine migration 0007 adds `fulltext_query` and `fulltext_hit` (D-SEC-14).
- D-STO-12 (2026-10-07): engine migration 0008 adds `refresh_run` and `refresh_day` (D-SEC-15).
- D-STO-13 (2026-10-08): corpus migration 0005 adds `passage` (section, seq, offsets, chunker version) and self-contained `passage_fts` (D-SRCH-10).
- D-STO-14 (2026-10-08): engine migration 0009 rebuilds `guidance` (never written before) with provenance columns and adds `guidance_scan` (D-SRCH-11).
- D-STO-15 (2026-10-08): engine migration 0010 adds guidance `flag` / `flag_reason` (D-SRCH-15).
- D-STO-16 (2026-10-08): engine migration 0011 adds `llm_call`, `llm_observation`, `llm_citation` (D-SRCH-19).
- D-STO-17 (2026-10-08): engine migration 0012 adds `price_bar` and `price_fetch` (M00_UI D-UI-8).
- D-STO-18 (2026-10-08): engine migration 0013 adds review_queue `resolved_by`, `note` and rebuilds `guidance` to allow source 'owner' (owner-entered rows, D-UI-12).
- D-STO-19 (2026-10-12, M04 Part 1a): engine migration 0029_m04_data rebuilds `signal` keyed by CIK (D-M04-74) with `value_text` and CHECKs (no text in `value`; an empty row needs "missing: …"; grade and source NULL only on missing rows; D-M04-9); existing rows get the CIK of the ticker span covering their `as_of` (else the latest span, else 0000000000 with a note) and text in `value` moves to `value_text`. Adds `entity_link` (three seeded links), `cover_shares`, `filing_status` and `entity.category`.
- D-STO-20 (2026-10-12, M04 Part 1b): engine migration 0030_m04_capex adds `capex_split` (per company and fiscal year end) and `guidance_outcome` (kind `score` | `removal`; outcome hit, miss, unscored, removed, expired, missing, pending; `revised` reserved for M11). Both are derived tables: the refresh's local pass replaces a company's rows on every run (0 SEC requests), so they need no backfill and no migration of old rows.
- D-STO-21 (2026-10-12, M04 Part 1b live check 1): engine migration 0031_guidance_dropped rebuilds `guidance_outcome` empty with outcome `dropped` added ("dropped (information)": a non-core removal, D-M04-85); SQLite cannot alter a CHECK, and the table is derived, so the next local pass (or `run_financials.py capex --no-sec`) refills it.
- D-STO-22 (2026-10-12, M04 Part 1c): engine migration 0032_m04_profile adds `company_stage` (computed rows replaced by the local pass; the owner's confirmation columns kept), `m04_proposal` (as `m02_proposal` plus priority group, capped and baseline), `peer_candidate`, and `sic_listing` / `sic_browse` (not in the Migrations plan: the setup page needs the listed counts and the S1 re-probe's list, replaced per SIC on each `run_financials.py profile`). Confirmed peer sets are written to the existing `peer_group` / `peer_member` (0001), one group per target named "M04 peers <cik>". 0031 was taken by `guidance_dropped`, so later M04 migrations shift by one (M04_BUILD_LOG Migrations).
- D-STO-23 (2026-10-12, M04 Part 2; D-M04-75, SB.16): engine migration 0033_m04_peers adds `peer_fetch` (one row per peer: last attempt and outcome, last success, tags in the file and tags kept, fact rows kept and new, MB downloaded, fiscal year end inferred, latest period and filed date, and a due filing seen in the daily index). Peer facts are stored in `fact` under the peer's CIK, trimmed to M04's tags (the 1a/1b concept map incl. IFRS and dei, the capex-definition and D&A tags, goodwill); no `series` rows for peers; the companyfacts file is never cached. A peer without an `entity` row gets one (companyfacts name, fiscal year end from its latest annual fact). `peer_group` / `peer_member` stay written by the setup page (Part 1c), including an empty confirmed set; a re-confirmed set replaces the members, and removed peers keep their stored facts. Growth estimate for the live check: up to ~0.3 GB for 40–50 peers (measured in the `peers` log).
- D-STO-24 (2026-10-12, M04 Part 3; D-M04-15, -16, -37, -71): engine migration 0034_m04_flags adds `restate_step` (one row per change between consecutive filed versions of a walked value: old and new value, tag, accession and filed date, first and latest version, delta, labels JSON with amounts and quotes, residual and its share of the old value, outcome explained / watch / review, text state, `baseline` marker, the owner's answer, review item), `m04_event` (one row per M04 8-K item or NT filing: class, base state and current state fail / warn / info / cleared / resolved, review flag, clears-when text, cleared date and by, deciding quote, owner resolution kept across recomputation) and `rating_action` (one row per rating sentence: action, from/to rating, agency if named, quote and offsets, review flag). The first scan of a company is recorded in `refresh_state` (`m04_walk_baseline:<cik>`, `m04_events_baseline:<cik>`, `m04_ratings_baseline:<cik>`): items found then are baseline (shown, queued only when filed in the last 12 months or a current fail). Old filings and prior 10-Ks use the existing corpus tables (no corpus migration).
- D-STO-25 (2026-10-12, M04 Part 7a; D-M04-42, SB.16): engine migration 0035_fact_dim (0034 is Part 3's; later numbers are taken in merge order because the runner requires 1..n with no gaps) adds `fact_dim` (one row per dimensional fact on a kept axis — customers, segments, products or services, classes of stock — with its axis, member, all dims of its context, period, value and unit, as filed; unique per accession, concept, dims, period and unit; recasts compared at read time, never merged) and `unit_metric` (unit KPIs, credits and company-stated non-GAAP rows: metric, model line, period label as stated and its mapped dates, value, unit, kind `kpi` | `credit` | `non_gaap`, basis, source exhibit, accession, verbatim quote, extractor; key cik, metric, line, period label, accession, so a Q4 and its fiscal year never collide). Instance files are never cached; `refresh_state` `fact_dim:<accession>` marks an instance read (M02's `xbrl_instance:` marker is set on the same read), `unit_scan:<version>:<doc_id>` a scanned document, `ex992:<accession>` an earnings 8-K checked for EX-99.2.
- D-STO-26 (2026-10-13, M04 Part 4a; D-M04-32, -86): engine migration 0036_m04_gate adds `credit_line` (one row per stated undrawn committed facility: amount, maturity, `as_of` = the balance sheet it was stated for, source text / URL / accession, `passage_id` for Part 4b's verified sentences, origin `owner` | `finder`, status `proposed` | `confirmed` | `rejected` | `withdrawn`, grade A with a filing source else B, confirmer and closer with dates, review item; a confirmed row needs its confirmer, rows are never deleted). Part 4a writes owner entries from the gate panel; Part 4b's finder will propose rows into the same table. The gate's states and figures are D13 signals (`survival_gate`, `runway_q`, `maturity_wall`, `distress_score`, `fcf_burn`, `debt_to_revenue`, `net_debt_ebitda`, `negative_equity`); turn bookkeeping lives in `refresh_state` (`m04_gate:<cik>`: the state, the balance sheet, when a fail / incomplete / capex-funded review / score gap started, the owner's runway answer) and the owner's gate-input maps in `m04_gate_map:<cik>:<input>`.
- D-STO-27 (2026-10-13, M04 Part 6; D-M04-17, -19, -71, -92, -93): engine migration 0037_m04_quality (wave B: 0036 is Part 4a's; the Part 6 branch carried a no-op `0036_placeholder_part4a.sql` until the rebase) adds `estimate_change` (one row per estimate-change sentence of a stored annual report, keyed by cik, accession and sentence offset — the filing version, so a restated amount in a later report is a new row; signed amount, basis after-tax / pre-tax / expense, denominator with its concept, tag and accession, share, band note / watch / elevated / not_meaningful / missing, verbatim quote, passage, baseline marker, review item, the owner's answer kept across rescans) and `special_item` (one row per fiscal year and finding: a restructuring, impairment or write-down tag with its amount, or "non-recurring" / "one-time" wording with its sentence; replaced per company on every pass). Scores (CFO/NI, accruals, M-score, misstatement score, contract gaps) are not stored: they are recomputed from `fact` on every pass and written as signals. `refresh_state` `m04_quality_baseline:<cik>` marks a company's first scan and `m04_quality_text:<accession>` an annual report whose text was in the corpus at the last pass.
- D-STO-28 (2026-10-13, M04 Part 4b-lite; D-M04-34, -95…98): engine migration 0038_m04_gate_text adds `gate_text` (one row per classified sentence of a stored periodic filing or 6-K and its EX-10 / EX-99 exhibits, keyed by accession, filename and sentence start offset: form, doc type, filed, period end, family going_concern | covenant, class, base effect fail | warn | hypothetical | none | excluded, the quote cut from the stored text and verified, passage and document ids, exhibit flag, note, baseline flag, review item, owner answer noted | treat_as_fail | misread). The effect on the gate is decided at read time (the current report as of the gate's date), so the table holds history too. Each document is scanned once per classifier version; the scan record (document sha256 and version, scanned filings with form, filed date and period end, first-scan time) lives in `refresh_state` `m04_gate_text:<cik>`, so no second table is needed. A re-scan replaces the document's rows unless they carry an owner answer (amended at Part 4b live check 1, code only, schema unchanged: a row with only a review item is reclassified too, and its item is withdrawn when the finding no longer holds; the migration's comment still reads "or a review item"). A new row for a sentence the owner answered in another report (same company, class and quote) carries that answer. No corpus migration.
- D-STO-29 (2026-10-13, M04 Part 8a MVP; D-M04-56, -68, -105): engine migration 0039_m04_cvd adds `market_share` (owner entries; never deleted, withdrawn with who and when). The CvD grid, state, confidence, coverage and health scores are recomputed from stored facts on every pass and written as D13 signals; the owner's `m04_cvd` answers and the last pass's one-line summary per company live in `refresh_state` (`m04_cvd:<cik>`, `m04_cvd_line:<cik>`), so no other table. Built in parallel with Part 4b-lite (0038): the branch carried a no-op `0038_placeholder_part4b.sql` (`SELECT 1;`) to keep the chain 1..39; it is removed at the rebase on main, before any live check.
- D-STO-30 (2026-10-13, M07 Part 1; D-M07-1…12, D-SEC-27): engine migration 0040_m07_insiders (wave W2: 0039 is M04 Part 8a's; this branch carried a no-op `0039_placeholder_part8a.sql` until the rebase) adds `form4_holding` (holding lines of a Form 4 without a transaction, parser form4-2: accession, line, table kind, title, shares owned, D/I, nature, footnotes; replaced with the form's rows on every parse), `insider_class` (one row per owner CIK, issuer CIK and calendar year: class routine / opportunistic / unclassified, the 3 years used, months seen per year, reason, computed at; derived, replaced per issuer on each M07 recompute) and `insider_txn.replaced_by` (the Form 4/A accession whose row replaces this one, matched on owner, transaction date and shares; set from scratch by the M07 pass). Bookkeeping in `refresh_state`: `form4_since:<cik>` (covered Form 4 start), `m07_pass:<cik>` (recompute fingerprint), `m07_baseline:<cik>` (first pass), `m07_alert:<cik>:<filing day>` (one insider-buy alert per company and day; "baseline: …" on the first pass). The three M07 signals are D13 rows in `signal`.

## Open questions
- Backfill universe: watchlist size and peers per group.
