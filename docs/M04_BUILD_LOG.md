# M04 — Build log (running)

Updated: 2026-10-12 · Companion to M04_FINANCIALS.md (decisions D-M04-1…75 live there; this file holds what each build conversation needs) · Cross-module lessons: LESSONS.md · Outputs are research signals, not advice.

## How to use
- A build conversation reads M04_FINANCIALS.md, then its part below, then LESSONS.md. The round briefs (`docs/m04_review/R1…R6_brief.md`, `BP_brief.md`) hold the full texts of the accepted suggestions S1.x–S6.x and SB.x; `PROBE_RESULTS.md` holds the measured figures. Read the pack (`M04_DESIGN_PACK.md`) only for a section a part names.
- Each part records: goal, decisions (D-M04-n), code, tables and migrations, config, review kinds, fixture tests, the owner's live check, docs to update in the same commit, re-probes, dependencies. Notes go under "Notes per part" during the build.
- Lessons that would help another module go to LESSONS.md, not here.
- Every rule cites its D-M04-n. Missing data stays missing, never zero (D-M04-9). Thresholds marked "starting value" are not tuned inside a build (D6; results go to the High review after Part 8b).

## Workflow
- **One branch per part** from main: `m04-part1a`, `m04-part1b`, … `m04-part8b` (SB.2, SB.3). Check `git branch --show-current` and `git status` before starting and before every commit (the owner may merge or switch mid-session).
- **Effort:** Medium for every part. High only if a part raises a new design question (ask first, D7), and for the results review after Part 8b (D-M04-73).
- **Order inside a part:** mock-up on real stored data, owner approves (D-UI-4, SB.7) → build with fixture tests → owner live check → local re-runs with `--no-sec` until the log is clean (expect 2–4 rounds; every M02 live log found new wording) → PR via `gh` → owner merges with "Create a merge commit" → `git switch main`, `git pull`, `git branch -d <branch>`.
- **One script:** `scripts/run_financials.py <subcommand>` (D-M04-69). One subcommand per part, `--no-sec` for local re-runs, the lock through `engine.store.lock.run_script` (one SEC process at a time; the limiter is per process, S121), and a log `logs/financials_<subcommand>_<timestamp>.txt` with requests, MB and seconds per fetch type, rows added per table, and the engine.db size before and after. The script catches and logs its own tracebacks, so the log file is all the owner sends back. Subcommands: `data` (1a), `capex` (1b), `profile` (1c), `peers` (2), `flags` (3), `gate` (4a), `gate-text` (4b), `issuance` (5), `quality` (6), `units` (7a), `margins` (7b), `cvd` (8a), `backtest` (8b).
- **Live checks:** Claude cannot call SEC or Tiingo, and may not read `.env` or `data\`. The owner runs one combined check per part (minutes, not tens of minutes) and sends the log. Fixture tests cover the rest. Tests never call live endpoints unless marked `live`.
- **Fixtures:** companyconcept files per tag, fetch date in the file name (SB.6); for peers and episodes one trimmed companyfacts file per company (D-M04-75). `tests/fixtures/` stays byte-exact (D24). Large documents (10-Ks, instances, 424Bs over ~2 MB) are trimmed to the needed block.
- **Large files:** files over ~2 MB (instances, 424Bs, 10-Ks) are parsed, then dropped from `http_cache`; rows and passages stay (SB.16).
- **Packages:** none expected. EdgarTools is not adopted (D-M04-42 chose instance reads); any `uv add` needs owner approval (D24).
- **Every part also:** adds its rows to the Financials tab (a row a rule does not use shows its reason and is never hidden, D10); adds its signals to "Signals out" in M04_FINANCIALS.md, whose MY/PT/ST columns carry the timeframe weights (SB.3); adds its per-new-filing work to `financials_step` (below); adds review-guide rows with a worked example for each new `m04_` kind (D-UI-15, as M02 does, e.g. D-M02-53); updates this file, LESSONS.md when a lesson generalises, and DESIGN.md "Resume here".

## Logon-refresh constraints (D-M02-12, D-M04-70)
- The owner's PC is never on overnight. Every scheduled run is the logon catch-up, in the background of the owner's session, killed at 3 hours. Recent refreshes took 1.5–6.7 minutes.
- `financials_step` has two hooks in `scripts/run_refresh.py` (order today: calls → money → supply → financing → news → official → seasonal → prices), both inside the refresh lock and timed in the run report (SB.5):
  - **SEC part, after `official_step`.** It does **per-new-filing work only**: R1 pages for annual covers and multi-class 10-Qs (~30 a year), a peer's companyfacts when the daily index shows its 10-K/10-Q/20-F/40-F (160–200), instances (~70), EX-99.2 (≤ 60), fee exhibits where `ffd` facts are missing (~30), frames (2): about 350–390 SEC requests a year; the heaviest earnings-season day is about 40 requests, under a minute. Finders run on stored text.
  - **Local pass, after `prices_step`** (0 SEC requests; also runs when prices are skipped): re-evaluates `filing_status`, the stale mark and the gate state for every covered company, because overdue and stale come from the calendar, not from a new filing (D-M04-61; the Invitae and RadioShack cases); recomputes the price-dependent rows (Z's market value, implied float, the overreaction gauge) and labels each with the close date used (BP check 21). Tracked-tier closes can be up to 3 days old (D-M02-18).
- **Alerts:** `m04_gate_fail` items and exit warnings are listed in the existing end-of-run summary box, shown after the lock is released (D-M02-18, -53, -57), and on the M04 tab.
- **Backfills are owner-run** through `run_financials.py`, never on first sight inside the refresh (D-M04-70).
- Every step is idempotent and resumable: a kill at 3 hours or a 429/block page leaves pending items pending, and the budget stop is reported (D-SEC-18, D-UI-8).

## Review order and cap (D-M04-71)
- **M04 weekly cap: 5** per Monday–Sunday week (UTC), as D-M02-18 (starting value, S4.8), separate from M02's 10; overflow flushed by priority, oldest first within a tie (as D-M02-53). Flush order: 1 survival (`m04_gate_fail` for a gate fail or incomplete, `m04_runway`, `m04_gc_text`, `m04_covenant`, `m04_score_gap`) · 2 CvD review (`m04_cvd`: AMBIGUOUS, STUMBLE, CYCLE_PLUS_DAMAGE) and stage changes · 3 filing events · 4 restatement · 5 dilution and overhang · 6 margin cause, customer, unit KPI · 7 estimate and M-score. One cap and one order replace the per-kind caps in Rounds 2, 4 and 5. Gate fails are alerts (`m04_gate_fail`, uncapped); operational items (`m04_credit_line`, `m04_gate_input`) are uncapped (S4.8).
- **Baselines:** the first run of every history scan (walk steps, EFTS history, overhang list) is recorded and shown, never queued, except items filed in the last 12 months and a current gate fail or incomplete, which queue at priority 1.
- **Setup batch, outside the cap and before Part 3:** 15 first stages (`m04_stage`, D-M04-12) and the ranked peer shortlists (`m04_peer`, ~13). Also outside the cap: `m04_credit_line` confirmations (~2) and the stickiness-class proposals (see "Open points for the build").
- **Owner load:** steady state 0.5–1.1 M04 items a week; with every queue full, M04 5 + M02 10 + ~8 guidance audits ≈ 23 a week. A skipped week rolls over in priority order; survival items never wait behind lower kinds.

## Label schedule (D-M04-51, D-M04-73)
- **When:** during Parts 3–7, so labels exist before Part 8b fetches episode data. Blind: the owner labels before seeing any engine output for that episode.
- **CvD episodes (D-M04-51):** 24 episodes (15 up to FY2017, 9 from 2018) plus 4 no-slowdown controls, from S6.3: troughs MU FY2012, MU FY2016, Halliburton, Nucor, Caterpillar, Deere (2015–16); damage Peabody, Chesapeake, Freeport-McMoRan; stumbles AMD 2012–15, J.C. Penney FY2012, GoPro 2016; declines Sears 2012–17, RadioShack 2012–14, Fitbit 2017; test MU FY2019–20, MU FY2023, WDC FY2023, INTC 2022–25, Invitae 2022–23, Bed Bath & Beyond 2019–23, Rite Aid 2021–23, J.C. Penney 2017–20, Boeing 2019–20; controls NVDA FY2024, MU FY2018, Caterpillar 2018, Nucor 2021.
- **Red flags (D-M04-73):** the same episodes plus GE 2016–17, Invitae 2021–23, RadioShack, Sears, Rivian 2022–26, MSTR 2025–26, Target FY2022, Tesla 2023; controls Lockheed and Alphabet.
- **Form:** Part 3 adds a label template (`config/m04_labels.toml`: episode, window, company CIK, label, label date, note; red-flag rows by flag family). The owner fills it in batches alongside Parts 3–7; the build never edits it.
- **Use:** Part 8b scores against it (confusion matrix, label stability, walk-forward: calibrate ≤ FY2017, test 2018+). Red-flag weights stay 0 until ≥ 20 owner-labelled episodes exist (D-M04-45, D-M04-60); weights are set at a High-effort review after Part 8b.

## Design review (2026-10-12)
One round per section; the owner chose the recommended option everywhere. Texts: `docs/m04_review/<round>_brief.md`.

| Round | Subject | Decisions | Suggestions |
|---|---|---|---|
| 1 | Data and what is buildable now; company profile and records | D-M04-2…13 | S1.1–S1.12 |
| 2 | Earnings quality | D-M04-14…21 | S2.1–S2.11 |
| 3 | Dilution and financing pressure; Red Flags 6 and 1 | D-M04-22…30 | S3.1–S3.10 |
| 4 | Survival gate and distress language; Red Flag 4 | D-M04-31…39 | S4.1–S4.13 |
| 5 | Unit economics, margin collapse, customer row | D-M04-40…50 | S5.1–S5.16 |
| 6 | CvD calibration and health scores; M01 reading (D-M01-5) | D-M04-51…68 | S6.1–S6.15 |
| Build parts | Script, refresh, review order, delisted names, labels, CIK, peer storage | D-M04-69…75 | SB.1–SB.18 |

## Build parts
| Part | Covers | Decisions | Depends on | Live check (owner) | Status |
|---|---|---|---|---|---|
| 0 Docs | SOURCES S122+, DS12–DS17, M04 doc redraft, this log, DESIGN code map | SB.1, S1.8, S1.9 | — | none | — |
| 1a Data | `facts_as_of`, form list, predecessor CIKs, share series, R1 cover reader, implied float, `filing_status`, signal migration (`value_text`, `cik`) and writer | D-M04-2, -9, -36, -61, -74 | 0 | `data` (~39 requests, < 1 min) | built 2026-10-12; live check pending |
| 1b Capex, trends | capex definitions and NVDA extension tag, `capex_split`, ROIC, trend rows, guidance record | D-M04-3, -6, -10, -11 | 1a | `capex` (~18, < 1 min) | built 2026-10-12; live check pending |
| 1c Profile | model tags, stage, M04 queue, ranked SIC peer shortlist, setup page | D-M04-4, -7, -8, -12, -71 | 1b | `profile` (≤ 90 pages + 2–4 frames, ~1 min) | — |
| Setup | owner confirms 15 stages and the peer shortlists | D-M04-12, -71 | 1c | — | — |
| 2 Peers | trimmed peer companyfacts, offsets, small-n statistics, peer z | D-M04-3, -5, -52, -75 | 1c + setup | `peers` (40–50 companyfacts, ~1 min) | — |
| 3 Restatements, events | 8-K triggers and sub-classes, walk, dei flag, old filings, prior 10-Ks, non-reliance, ratings, label template | D-M04-15…17, -21, -37, -71, -73 | 1a + setup | `flags` (~97, 1–2 min) | — |
| 4a Gate numbers | runway, wall, `distress_score`, gate states and scope, input age, debt and FCF rows | D-M04-8, -13, -29, -31…33, -35, -36, -38, -39, -61 | 1b, 1c, 3 | `gate` (~24, < 1 min) | — |
| 4b Gate text | going-concern and covenant classes, EFTS baseline, undrawn-credit finder | D-M04-34, -71 | 4a | `gate-text` (~200, 2–3 min) | — |
| 5 Dilution | issuance, bands, 424B fee exhibits, `financing_pressure`, overhang, lock-ups | D-M04-13, -22…28 | 1c, 4a, 4b | `issuance` (~260, 1–2 min) | — |
| 6 Earnings quality | `eq_cash`, M-score, misstatement score, estimate bands, `special_items`, contract gaps | D-M04-14, -17…20 | 1c, 3 | `quality` (~10, < 1 min) | — |
| 7a Units data | `fact_dim`, Tesla DS2 extractor, EX-99.2, RIVN tracked, Invitae EX-99.1 | D-M04-42 | 1a | `units` (~300, ~0.5 GB downloaded, 2–3 min) | — |
| 7b R12, customers | R12 trigger, cause finder, unit flags, customer row, RPO | D-M04-40, -41, -43…50 | 4a, 6, 7a | `margins` (~6–8, < 1 min) | — |
| 8a CvD, tab | grid, classification, health vote, gauge, Red Flag 1 row, market share, M01 reading, M04 tab | D-M04-1, -30, -52…68 | 1a–7b | `cvd --no-sec` (0 SEC, < 1 min) | — |
| 8b Calibration | episode facts and prices, backtest on owner labels, red-flag label report | D-M04-51, -72, -73, -75 | 8a + labels | `backtest` (~71 SEC + ≤ 40 Tiingo, ~3 min) | — |

Order: 0 → 1a → 1b → 1c → setup batch → 2 → 3 → 4a → 4b → 5 → 6 → 7a → 7b → 8a → 8b → High review. 7a reads only Part 1a and may move earlier if a later part stalls. One-off SEC requests ≈ 1,170 in all (B.9a plan, D-M04-75).

## Migrations (engine 0029 onward)
Numbers are planned (0028_official_followup is the latest on main); take the next free number at build if another branch lands first. No corpus migration is expected: old filings and prior 10-Ks use the existing document and passage tables.

| Part | Migration | Adds |
|---|---|---|
| 1a | 0029_m04_data | `signal` rebuilt with `cik` (key: cik, module_id, signal, timeframe, as_of) and `value_text`; ticker kept for display; existing rows backfilled from `ticker` (D-M04-9, -74) · `entity_link` (predecessor or shell CIK, successor, boundary date, kind) · `cover_shares` (accession, class, shares, cover date, `error_correction_flag`) · `filing_status` (cik, period, form, category carried, due date, status) |
| 1b | 0030_m04_capex | `capex_split` (cik, period, total, maintenance, method, rung) · `guidance_outcome` (guide row, actual, outcome: hit / miss / unscored / revised / removed / expired, reason passage) |
| 1c | 0031_m04_profile | `company_stage` (cik, fiscal year, computed, confirmed, by, at) · `m04_proposal` (as `m02_proposal`, plus priority group and `baseline`) · `peer_candidate` (target cik, candidate cik or name, SIC, rank, active forms) |
| 2 | 0032_m04_peers | `peer_fetch` (cik, fetched_at, tags kept, rows, MB); `peer_group` / `peer_member` (0001) now written |
| 3 | 0033_m04_flags | `restate_step` (cik, concept, period, first and latest value and accession, label, residual, baseline) · `m04_event` (accession, item, class, state, clears_at, owner resolution) · `rating_action` |
| 4a | 0034_m04_gate | `credit_line` (cik, facility, amount, maturity, source passage, confirmed by) |
| 4b | 0035_m04_gate_text | `gate_text` (accession, period end, class, quote, passage id, baseline) |
| 5 | 0036_m04_issuance | `issuance_band` (year, universe, cuts) · `offering` (424B accession, security type, amount, fee source, paired final supplement) · `overhang_item` · `lockup_release` |
| 6 | 0037_m04_quality | `estimate_change` (accession, amount, basis, denominator, band, filing version) · `special_item` |
| 7a | 0038_fact_dim | `fact_dim` (cik, accession, concept, axis, member, period, value, unit) · `unit_metric` (cik, period, metric, value, source) |
| 7b | 0039_m04_margins | `r12_episode` · `margin_cause` (class, quote, arithmetic check) · `customer_class` (cik, class, proposed, confirmed) |
| 8a | 0040_m04_cvd | `market_share` (owner entries: cik, period, share, market, source, grade) |
| 8b | 0041_m04_backtest | `episode` (cik, window, label key) · `episode_symbol` (cik, Tiingo symbol, start, end, last real trade, match result) · `backtest_run` |

## Review kinds
Names and plumbing follow the M02 proposal pattern (D-M02-18; priority flush D-M02-53). Group = D-M04-71 priority. Volumes are for the watchlist in steady state after baselines (BP gaps #5, S5.14); all are estimates until the first logs.

| Kind | Part | Group | Expected volume | Notes |
|---|---|---|---|---|
| `m04_stage` | 1c | setup, then 2 | 15 once, then 4–5 a year | owner override; last confirmed stage routes (D-M04-7, -12) |
| `m04_peer` | 1c | setup | ~13 once | ranked shortlist only (SB.9) |
| `m04_event` | 3 | 3 | ~2 a year | 4.02, 4.01 within 12 months, 2.04, 3.01, 1.03, 2.06, NT |
| `m04_rating` | 3 | 3 | ~1 a year (INTC) | text only (DS17) |
| `m04_restate` | 3 | 4 | ≤ 4 at first run, then 2–3 a year | baseline: 101 walk steps (recount vs Round 2's 102) |
| `m04_gate_fail` | 4a, 4b | 1 (alert, uncapped) | 0 now; rare | gate turns fail or incomplete (D-M04-71); fail-class text (4b) |
| `m04_runway` (proposed name) | 4a | 1 | 0–1 now; rare | capex-funded runway below 6 quarters (D-M04-38) |
| `m04_gate_input` | 4a | operational (uncapped) | 1 now (INFQ) | non-financing tag to map; missing gate inputs; financing tags via M02's `fin_tag_map` (D-M02-31) |
| `m04_score_gap` | 4a | 1 | 0–1 at first run | GFS 2.07 raises none (SB.18) |
| `m04_credit_line` | 4b | operational (uncapped) | ~2 now; then per 10-Q for names with runway < 12 or the capex-funded warning | confirms undrawn credit and its maturity |
| `m04_gc_text` | 4b | 1 | < 1 a quarter | alleviated, audit-matter only, IFRS uncertainty, hypothetical with runway < 8 |
| `m04_covenant` | 4b | 1 | < 1 a month | waived or reset covenants; current-debt jump (sub-class `m04_current_jump`) |
| `m04_dilution` | 5 | 5 | 1 now (MSTR); 4–8 a year with overhang | per D-M04-25, -27 |
| `m04_overhang` | 5 | 5 | baseline ~10–11 (MSTR incl. STRE) | |
| `m04_financing_doc` | 5 | 5 | a few now; then 0–1 | ATM or resale found without fee exhibit or count |
| `m04_estimate` | 6 | 7 | ~1–2 a year (inference) | bands per D-M04-17 |
| `m04_mscore` | 6 | 7 | ~1 now (NVDA FY2026) | SGI = 1 version above −1.78 |
| `m04_margin_cause` | 7b | 6 | 1–3 a year | one per R12 episode |
| `m04_customer` | 7b | 6 | 1–3 a quarter | weakening needs owner confirmation |
| `m04_unit_kpi` | 7a, 7b | 6 | ~1 a year | |
| `m04_cvd` | 8a | 2 | ~2–4 a year (estimate) | opens on AMBIGUOUS, STUMBLE or CYCLE_PLUS_DAMAGE (the grid's "review", D-M04-1); blocks tranches until resolved; the owner's answer becomes the state (D-M04-56, -58) |

## Part 0 — docs (on `m04-review`, before its PR)
Do the bookkeeping once, before any code cites it (SB.1, S1.8, S1.9). No code, no live check.
- **SOURCES.md** (done 2026-10-12): S122 = McConnell & Muscarella (fixes the duplicate S101). All 131 provisional IDs mapped to S123–S225 in order of first definition; 43 IDs sharing a URL or work merged into 15 S-numbers (BP gaps #10). The mapping table (provisional → S-number) is at the end of the pack's "New sources" so the briefs stay readable. The peer rule cites S162 (browse-by-SIC).
- **DATA_SOURCES.md:** register DS12 dimensional facts (segments, `srt:MajorCustomersAxis`, multi-class cover shares), DS13 industry price and volume series (gap), DS14 unit KPIs beyond Tesla, DS15 historical 4.02 texts, DS16 market share (owner entry with source, grade B), DS17 credit-rating actions (text only). Update DS2 (extractor in Part 7a), DS7 (two prior 10-Ks, D-M04-17, Part 3), DS8 (delisted symbols by name-and-date match, D-M04-72).
- **M04_FINANCIALS.md redraft** (done 2026-10-12 on `m04-review`; check only): fold the D-M04-1 change table (R6 brief) into the profile; rewrite the survival gate per D-M04-31…38 and drop the superseded text; consolidated "Signals out" (S1.5 list plus Round 6 additions, MY/PT/ST columns, "info" = weight 0); failure modes from all rounds; close the answered open questions; Sources line in S-numbers.
- **`docs/M04_BUILD_LOG.md`** opened from the review draft (done 2026-10-12).
- **DESIGN.md:** "Resume here" (phase 4, M04 build; next action Part 1a); code map migrations 0001–0028; docs list and CLAUDE.md module-doc list add M04_BUILD_LOG.md; workflow line: M04 live checks use `run_financials.py <subcommand>` (D-M04-69); open items closed by decisions, here only (build parts do not close them again): separate shares concepts (D-M04-2), SIC peer discovery (D-M04-4), peer offset (D-M04-5), capex fallback marker (D-M04-3), EdgarTools evaluation (not adopted, D-M04-42), M04 red flags (Rounds 2–5); DS7 noted "partly, D-M04-17". D13: add "evidence_grade = weakest deciding input; source_ref = newest accession, +N; inputs in method (D-M04-9)". D14: add "B also covers transcripts, third-party data and owner entries without a filing (D-M04-9)". D27: append "read per D-M01-5". Approved revisions, M05: append "Capex split owned by M04 (D-M04-6, amends A2; default depreciation); M05 owns growth capex × ROIC."
- **M01_TIMEFRAMES.md** (rows M04 now feeds): rule 4 and D-M01-5 add exit warnings on an overdue filing (D-M04-61) and a survival-gate fail (S6.14), red-flag warnings listed in the `exit_warning` reasons and never blocking (D-M04-21), and `guidance_removed` (S1.7) as the input to "quietly removed targets"; D-M01-5's STUMBLE reads "blocked until the owner resolves the `m04_cvd` review"; Inputs refresh for CvD and gate "On filing and on each refresh (due dates)"; "Fundamental windows" row annotated "M04 windows fixed per D-M04-29, -49, -64; the 5-year average applies to display"; rule 7's "(the M04 overreaction setup)" → "(gauge shown, not required, D-M04-62; read per D-M01-5)".
- **M02_THEMES.md:** open question "Weighting of capex as a buy signal" gains "weigh together with M04's capex-funded runway and `fcf_burn` (D-M04-32, -38, -39)"; note that M04 reads the DSO series and alert as context (D-M02-47), ownership revisited when D13 weights are set.
- **Optional:** the three pack citation fixes still open (BP gaps #9: fixes 4, 5, 8b). The pack is a research record; skip if not cited elsewhere.

## Part 1a — Data foundation
**Goal.** One point-in-time read path and one signal writer that every later part uses: as-of facts with the right forms, share series that work for multi-class filers, filer status and deadlines, and `signal` rows keyed by CIK with text states.

**Decisions.** D-M04-2 (share series, R1 reader, implied float), D-M04-9 (encoding), D-M04-74 (cik), D-M04-36 and D-M04-61 (filing status; consumers in 4a and 8a); S1.1 (`facts_as_of`), S1.3 (concept fixes), S1.4 (tag and accession on every value), S1.5 (M04 first writer of D13), S1.6 (`filing_status`), SB.11 (form list), SB.18 (GE alias for GE only).

**Code.**
- `src/engine/sec/asof.py` — `facts_as_of(engine, cik, concept, as_of)`: periodic forms only (10-K, 10-Q, 10-KT, 20-F, 40-F, XBRL 6-K and amendments; 8-K, DEF 14A, S-1, S-4 values never "latest"); tag priority applied after time (fixes MU FY2018 revenue shown as first filed 2019-10-17); predecessor and de-SPAC boundaries from `entity_link`. Live and backtest signals read it; `series` stays display-only (S1.1).
- `src/engine/refresh.py` — `FACT_FORMS` gains 10-KT and XBRL 6-K, so a GFS 6-K forces a facts sync (SB.11).
- `src/engine/sec/xbrl_facts.py` — concepts `shares_period_end`, `shares_cover`, `shares_basic_wavg`, `shares_diluted_wavg`, `sbc`; `da` adds `Depreciation` and drops the nonproduction tag; `ppe_net` marked fallback; the S1.3 extra-tag list; per-company aliases (GE contract assets; NVDA `nvda:MarketableSecuritiesAndEquitySecuritiesFVNI`, L2), never `CommodityContractAssetNoncurrent` in general (SB.18). Bump the parser version only if stored rows must change.
- `src/engine/sec/cover.py` — R1 cover reader: per-class "Entity Common Stock, Shares Outstanding" rows summed, cover date, `DocumentFinStmtErrorCorrectionFlag` (Part 3 reuses it); split guard on cover counts (MSTR 2011 counts predate the 2024 10-for-1 split); an R1 page that is not a cover (Google Inc. 2009) → fallback to basic weighted average, labelled.
- `src/engine/sec/identity.py` + `entity_link` — predecessor CIKs: Google Inc. 0001288776 (to 2016-02-11), Marvell Technology Group 0001058057 (to 2021-03-16); INFQ's shell years (Churchill Capital Corp X) before the 2026-02-13 close, keyed on period end.
- `src/engine/financials/shares.py` — the four series plus `sbc`; implied float = `dei:EntityPublicFloat` ÷ close on its date, yearly, labelled "implied" (M07 owns R22).
- `src/engine/financials/status.py` — `filing_status` (current / stale / overdue): due date = period end + deadline by filer status (10-K 60/75/90, 10-Q 40/40/45, 20-F four months; NT +15/+5); category carried year to year with Rule 12b-2 exit thresholds; backtests derive status from stored float, longest deadline only when float is missing (S1.6, D-M04-36). Foreign annual filers: annual inputs usable up to 16 months.
- `src/engine/signals.py` (shared, all modules) — `write_signal`: enums and states in `value_text` with `value` NULL; numbers in `value`; a missing signal = both empty, `method` = "missing: <reason>"; one row per timeframe, ST "info" rows weight 0; `evidence_grade` = weakest deciding input; `source_ref` = newest accession, "+N" when more, full input list in `method` (D-M04-9).
- `scripts/run_financials.py` — skeleton (subcommand table, `--no-sec`, `run_script` lock, log format) and subcommand `data`.
- UI: Financials tab rows for share series (per class), implied float, filing status, and the marker legend.

**Tables.** Migration 0029_m04_data (see Migrations). **Config.** None. **Review kinds.** None.

**Mock-up first (SB.7).** The Financials tab with every planned M04 row (empty rows show "missing: not built, Part n"), on scratch data from the briefs' real figures (Claude may not read `data\`): MU FY2022–23, META cover shares by class, AMZN's capex fallback marker. The owner sees it on real data in the live check.

**Fixtures and tests.**
- WDC FY2023 revenue 12,318 as of 2024 (2 companyconcept files, revenue tags).
- MU FY2018 revenue first filed 2018-10-15 (tag switch); Alphabet 2023 net income never from a DEF 14A.
- META FY2025 10-K R1: Class A 2,187,177,748 + Class B 342,377,716 = 2,529,555,464 at 2026-01-23, flag false. MSTR Q2 2011 R1: A 8,217,394 + B 2,492,830 at 2011-07-27, split-adjusted. SPCX 10-Q R1 per-class rows. Google Inc. Q2 2009 R1 = balance sheet → fallback, labelled.
- Invitae status: FY2022 float $569.8M > $560M exit line → still large accelerated, due 2023-03-01, filed 2023-02-28 (current); FY2023 float ~$295–302M → accelerated, due 2024-03-15, never filed → overdue.
- GFS: a 6-K with XBRL triggers a facts sync; a 6-K without XBRL does not.
- Signals: text never stored in `value`; a missing row; two CIKs that shared BBBY keep separate rows.

**Live check (owner).** `uv run python scripts/run_financials.py data` — ~37 R1 pages (3 years of GOOG, META, MSTR, SPCX filings) + 2 WDC companyconcept files ≈ 39 SEC requests, under a minute (plus 18 companyfacts, ~52 MB, only if the parser version is bumped). The owner looks for: per-class and summed cover counts with cover dates (META 2,529,555,464); any R1 page read as "not a cover"; split-guard hits; `filing_status` for all 18 companies (all current expected); the extra-tag report (tags M04 needs that a company lacks); GFS 6-K sync line; rows added and engine.db MB.

**Docs (same commit).** M00_SEC_DATA (as-of reads, form list, R1 reader, predecessor CIKs, concept fixes and aliases) · M00_STORAGE (0029) · M00_UI (Financials rows, marker legend; new D-UI-n) · DATA_SOURCES DS12 (multi-class cover counts via R1) · M04_FINANCIALS (Signals out: share series, `filing_status`) · DESIGN code map (`signals.py`, `sec/asof.py`, `sec/cover.py`, `financials/`, `run_financials.py`) · CLAUDE.md commands (`run_financials.py`).

**Re-probes.** None (S3's SPCX values are captured here).

**Depends on.** Part 0 merged.

## Part 1b — Capex, trends, guidance record
**Goal.** Capex the way each use needs it, the maintenance/growth split, ROIC, the outline's core trend rows, and the guidance record the Q2 row reads.

**Decisions.** D-M04-3, D-M04-6, D-M04-10, D-M04-11; S1.7, S2.1 (near-zero base), S2.7 (useful-life mark); SB.12 (ROIC in Part 1).

**Code.**
- `src/engine/financials/capex.py` — three definitions (D-M04-3): display = M02's recipe from `moneyflow/actuals.py` (derived from the guidance clause, `config/capex_definitions.toml` overrides only, approximate label and shown-actual rule; D-M02-29, -32, -34), so the Money flow and Financials tabs show one value, with the standard-tag value beside it and the marker worded "broader tag: <what it adds>" (e.g. "includes intangibles"), distinct from M02's "≈, gap X%"; own history = the longest consistent tag series, a switch inside the window reads "definition changed", not scored; peers = PP&E tag only, AMZN (fallback only) and NVDA (no PP&E-only tag in any year) "not like-for-like" and excluded (applied in Part 2). NVDA FY2013–21 own history from instances via `nvda:PurchasesOfPropertyAndEquipmentAndIntangibleAssets`; one definition across the switch (same caption).
- `capex_split` (D-M04-6): disclosed → project-level → depreciation (default, capped at total capex) → D&A (marked last rung) → "not split"; Greenwald beside it only inside 0…total capex, on Greenwald's average of yearly ratios over five prior years, net and gross both shown (L1); one method per company per displayed window, tagged on every value; a useful-life change marks that year's depreciation rung (Intel 2023). Owner earnings = OCF − maintenance capex − SBC and "runway without growth capex" are information. Consumers (runway, FCF after SBC, Q2 capex row) use total capex.
- `src/engine/financials/trends.py` — `rev_yoy`, `rev_cagr3`, `fcf_growth` (on total capex and on owner earnings; not meaningful on a near-zero or negative base), `gm_trend_pp` (4-quarter and 3-year change; gross profit derived where untagged, labelled: AMZN, GOOG, META, SPCX, INFQ), `opex_vs_sales`; ROIC per S6.5 (NOPAT ÷ average invested capital; NOPAT = operating income × (1 − tax ÷ pretax, bounded 0–35%), or operating income alone when pretax ≤ 0; invested capital = equity + long-term debt + current debt − cash − short-term investments; `not_meaningful` when ≤ 0), method-tagged, consumed by D-M04-54 in 8a. Own history now; peer robust z in Part 2. Information rows, no vote until Part 8 (D-M04-11).
- `src/engine/guidance/record.py` (shared with M11) — per metric and period one outcome: miss = actual below the low end of the latest range given before period end (or below a point guide) on the guide's own basis (GAAP from first-filed facts via `facts_as_of`; non-GAAP from the stated reconciliation); point and "approximately" guides unscored; repeated = 2 misses in the last 4 guided quarters; downward revisions counted separately; removed vs the same fiscal position a year earlier, reason searched in the current and prior release and call, period not yet ended (ended = "expired"); `guidance_hit_rate` row; release-silent guiders "missing (DS1)"; a `guidance_removed` event (information) for M01 rule 4.
  - Capex actuals come from M02's `moneyflow/guided.py` (recipe in force at the guide date, shown-actual rule; D-M02-29, -33), so "own basis" for capex means D-M02-29 and each row has one guided-vs-actual result, shared by M02, M04 and M11.
  - "Removed" fires only when M02's freshness state is "not restated" (release and stored call both silent, D-M02-30); "call not stored yet", "call unavailable" and "latest results not read yet" give "missing: <state>"; a stored `guidance_skip` refusal counts as the stated reason. M02's six freshness states are extended from capex to every metric family M04 scores.
  - Part 1b builds the shared scorer (outcome per row, `guidance_outcome`); M11's review owns R19 scoring and weighting and may extend it (D-M04-10).
- `run_financials.py capex`. UI: capex rows with marker and legend, split rung, trend rows, guidance outcomes.

**Tables.** 0030_m04_capex. **Config.** Reads `config/capex_definitions.toml`. **Review kinds.** None.

**Fixtures and tests.**
- MU FY2022 → FY2023: revenue 30,758 → 15,540; GM 45.2% → −9.1%; OCF 15,181 → 1,559; capex tag 12,067 → 7,676 vs stated net capex 7,010; depreciation 7,030 → 7,670. FCF on total capex FY2023 −6,117, FY2025 1,668, FY2026 58,963 (depreciation basis −6,111, 9,245, 80,255).
- Split: MU FY2023 total 7,676, depreciation 7,670, Greenwald out of range; MU FY2026 30,712 / 9,420; INTC 2022 24,844 / 11,128; MSFT FY2026 115,948 / 34,300, Greenwald beside at 78.7% (net) or 65.1% (gross). Out-of-range counts: MU 6 of 8 (net), 7 of 8 (gross); INTC 4 of 4.
- AMZN FY2016: fallback tag 15.8% above the PP&E tag → "broader tag" marker. NVDA FY2021 1,128.0 and FY2013 183.3 from trimmed instances.
- Guidance: MU Q3 FY2023 revenue, GAAP GM, EPS → 3 hits; INTC FY2022 ($76.0B → $65–68B → $63–64B; actual $63,054M) → hit with 2 downward revisions; INTC January 2023 → not removed; INTC April 2023 → removed unless a reason is found (the January 2023 call reportedly gave one).

**Live check (owner).** `uv run python scripts/run_financials.py capex` — ~18 SEC requests (NVDA FY2013–21 instances), under a minute. The owner looks for: the definition used per company and its marker; "definition changed" windows; split rung and whether Greenwald is in range; trend rows for 18 companies (missing ones with reasons); guidance outcomes and hit rates; NVDA's pre-FY2022 values.

**Docs.** M04_FINANCIALS (capex rules, split, trend rows, guidance record; Signals out: `rev_yoy`, `rev_cagr3`, `fcf_growth`, `fcf_growth_oe`, `gm_trend_pp`, `opex_vs_sales`, `capex_maint`, `capex_growth`, `owner_earnings`, `guidance_hit_rate`, `guidance_removed`) · M00_SEC_DATA (NVDA extension via instances) · M00_STORAGE (0030) · M00_UI (capex markers) · M02_THEMES (freshness states extended to M04's metric families; `guided.py` shared with `guidance/record.py`).

**Re-probes.** None. **Depends on.** 1a.

## Part 1c — Company profile, queue and peer shortlist
**Goal.** Everything later rules route on: model tags, life-cycle stage, the M04 review queue, and a ranked peer shortlist for the owner to confirm in one setup batch.

**Decisions.** D-M04-4, D-M04-7, D-M04-8, D-M04-12, D-M04-46 (stage → flag-set map, consumed in 6 and 7b), D-M04-71; S1.10, S6.2.

**Code.**
- `config/company_models.toml` + `src/engine/financials/models.py` — six fixed tags (`issuance_funded`, `asset_treasury`, `reit`, `fund`, `financial`, `spac_shell`), hand-edited, one-line reason and source each, unknown tag rejected at load, the app never edits it. Initial entries: MSTR `asset_treasury`, ETV `fund`, INFQ `spac_shell` for periods ending before 2026-02-13 (none after). Routing per the R1 brief table; a tag overrides SIC (MSTR SIC 6199) and applies before stage; untagged FF12 group 11 → "not applicable"; the engine may propose `reit` for SIC 6798 (proposal only).
- `src/engine/financials/stage.py` — Dickinson signs with core investing (capex + acquisitions − asset and business sale proceeds); a stage holds when 2 of the last 3 fiscal years agree; `m04_stage` when none holds, when shake-out holds, or on a CAGR conflict (introduction/growth with `rev_cagr3` < 0; mature/decline > 20%); under 3 fiscal years → review, both flag sets computed, labelled "stage unconfirmed", not counted; the owner's last confirmed stage keeps routing; owner override. Stage → flag set (D-M04-46). Stage routes flags only.
- `src/engine/financials/queue.py` — M04 proposals on the M02 pattern: weekly cap 5, D-M04-71 priority, baseline marker with the 12-month and current-fail exceptions, setup kinds outside the cap. M02's `themes/proposals.py` and its cap of 10 stay unchanged (shared helpers may move to `engine/proposals.py`).
- `src/engine/sec/browse.py` + `src/engine/financials/peers.py` — browse-by-SIC pages per watchlist SIC (capped per SIC; SIC 3674 = 6 pages, 505 listed), active = a 10-K, 20-F or 40-F in the last 12 months from stored form indexes (0 requests), ranked by revenue closeness from 2–4 frames; `m04_peer` items from the shortlist only; owner adds product-market peers (QCOM, WDC); non-SEC peers stored by name as "missing" (SK hynix, Samsung).
- UI: setup page (`m04_setup.html`): stage confirmations and overrides, peer shortlists, model tags read-only (edits go to the toml).
- `run_financials.py profile`.

**Tables.** 0031_m04_profile. **Config.** `config/company_models.toml` (new). **Review kinds.** `m04_stage` (15 at setup), `m04_peer` (~13 at setup).

**Fixtures and tests.**
- Stage: AAPL mature on core investing (shake-out on total); INTC growth with CAGR −5.7% → review; TSLA growth → owner confirms; NVDA (+100.0%) and MU (+104.6%) mature with CAGR > 20% → review; BA no 2 of 3 → review; MRVL mature; META +19.9% stays under 20%; MSTR tag first, then review; SPCX, INFQ under 3 years → review, both sets labelled. First run: 15 setup items.
- Tags: unknown tag rejected; INFQ periods before 2026-02-13 are `spac_shell`, keyed on period end.
- Peers: SIC 3674 browse fixture (505 listed, 82 active on 10-K; a 20-F filer such as GFS counted active).

**Live check (owner).** `uv run python scripts/run_financials.py profile` — up to ~90 browse pages (cap per SIC; includes the S1 re-probe) + 2–4 frames, about a minute. The owner looks for: the 15 computed stages and which go to review; shortlist size per SIC (listed / active incl. 20-F and 40-F) and any company with no usable peers; the tag file loaded with 3 entries.

**After merge — setup batch (owner).** Confirm the 15 stages and the peer shortlists on the setup page, adding product-market peers. Peers must be confirmed before Part 2's fetch; the whole batch before Part 3 (D-M04-71).

**Docs.** M04_FINANCIALS (tags and routing table, stage rule, peer rule; Signals out: `lifecycle_stage`) · M00_SEC_DATA (browse-by-SIC) · M00_STORAGE (0031) · M00_UI (setup page) · DESIGN config list (`company_models.toml`).

**Re-probes.** S1 (6 requests): active filter with 20-F/40-F counted, full list written to the log (SB.17). **Depends on.** 1b (capex for core investing, CAGR).

## Part 2 — Peer facts and statistics
**Goal.** Comparable peer values for the confirmed peer sets, matched in time, with statistics that hold up at 5–9 peers.

**Decisions.** D-M04-3 (peer capex leg), D-M04-5, D-M04-52, D-M04-75; D-M04-11 and D-M04-29 (peer z for information rows); SB.16, SB.18.

**Code.**
- `src/engine/financials/peer_facts.py` — one companyfacts download per confirmed peer; keep only the tags M04 reads (concept map from 1a/1b), store them in `fact` under the peer's CIK, drop the cache file (D-M04-75, SB.16); `peer_fetch` records rows and MB. IFRS filers (`ifrs-full`, 20-F/6-K, e.g. GFS) use mapped IFRS tags where they exist, else "missing".
- `src/engine/financials/stats.py` — robust z: MAD × 1.4826 × the small-sample factor b_n for 5–9 peers, IQR ÷ 1.35 for ≥ 10, fixed-gap fallback (low confidence) below 5; drop |z| > 3 once before scoring (D-M04-52).
- `src/engine/financials/peers.py` — offsets: TTM ±45 days, quarters and instants ±40 days; outside → "no comparable period", counted toward the < 5 fallback; each peer's end date shown; 53-week years flagged (D-M04-5); acquisition years (AMD 2022) flagged (R1 case list). Peer capex statistics on the PP&E tag only; AMZN and NVDA excluded in every year (D-M04-3, SB.18).
- Peer robust z added to the 1b trend rows. `financials_step`: refetch a peer's companyfacts when the daily index shows its periodic filing (D-M04-70).
- `run_financials.py peers`. UI: peer columns with end dates and n; "no comparable period" shown.

**Tables.** 0032_m04_peers; `peer_group` / `peer_member` written from the confirmed setup. **Review kinds.** None new.

**Fixtures and tests.** One trimmed companyfacts file per chip peer (B.9a). WDC against MU at 29–36 days → kept at ±40; a two-month gap → "no comparable period". Intel 2022 with n = 4 → fixed-gap fallback (methods spread −0.82 to −1.92). b_n cases at n = 5…9; |z| > 3 dropped once. NVDA out of peer capex in every year; AMZN fallback excluded.

**Live check (owner).** `uv run python scripts/run_financials.py peers` — 40–50 companyfacts (116–170 MB downloaded at the 3.40 MB median), about a minute; engine.db up to ~0.3 GB more (estimate). The owner looks for: rows and MB per peer (closes the "rows per peer" gap) and the engine.db size after; n per peer group and any group below 5; peers with "no comparable period"; peer z on MU and INTC revenue rows. If growth is larger than expected, the owner decides before Part 8b repeats the pattern (failure-mode row "Engine DB growth").

**Docs.** M00_STORAGE (peer writes, trimmed peer facts) · M00_SEC_DATA (companyfacts trim; M04 offsets tighten D-SEC-9's 45 days for quarters and instants) · M04_FINANCIALS.

**Re-probes.** None. **Depends on.** 1c and the confirmed peer sets.

## Part 3 — Restatements, filing events, prior filings
**Goal.** Every filing event and restatement M04 reads, classified once and stored for the gate and the scores; the restatement walk with labels and a baseline; the old filings later parts need; the label template.

**Decisions.** D-M04-15, D-M04-16, D-M04-17, D-M04-21, D-M04-37, D-M04-71, D-M04-73; S1.11, S2.5, S2.6, S3.7, S2.10.

**Code.**
- `src/engine/financials/events.py` — 8-K classes from the stored `event` table (D-M04-37): 1.03 fails and never clears by itself; 2.04 fails until a later clean periodic filing and owner resolution; 3.01 fails on delisting or a missed cure, a cure-period deficiency warns + review, a listing transfer is information (S1.11); 4.01 within ~90 days of a de-SPAC close with no disagreements is information (S1.11), and any 4.01 within 12 months of a restatement escalates (D-M04-15); 4.02; 2.06; NT 10-K/10-Q. 1.02 co-filed with 2.03 → financing, not customer (L8; read in 7b). Stored in `m04_event` with state; the gate reads them in 4a.
- `src/engine/financials/restate.py` — sources (D-M04-15): 4.02 events; the dei error-correction flag from R1 pages (1a reader) for 10-Ks filed from 2023-12-01 (a missing flag earlier means "not required", never false); little-r wording in 10-K/10-Q text (FTS5 on stored text). Walk (D-M04-16): fiscal-year and discrete-quarter values per concept, first vs latest, ordered labels (standards, discontinued operations, segments, splits, tag switches, rounding, NCI share, restricted cash, de-SPAC); a residual above both 0.5% and $0.1M opens `m04_restate`; first run is a baseline (D-M04-71). One-off fetch of at most ~35 older filings to label pre-corpus steps.
- Non-reliance (D-M04-21): an open 4.02 marks every M04 row reading the affected periods "inputs under non-reliance" and warns; adds are not blocked. A lookup here; each later part applies it.
- Prior filings (D-M04-17): two prior 10-Ks per company (≤ ~28; ETV and INFQ shell years skipped), stored as documents and passages for Part 6; large files parsed then dropped from the cache (SB.16).
- `src/engine/financials/ratings.py` — credit-rating sentences in stored 8-Ks and releases, no agency name needed; old-engine severity words kept, bare "covenant"/"waiver of" dropped (S3.7); `m04_rating`.
- `config/m04_labels.toml` — label template (episodes and red-flag families per D-M04-51, -73); the owner fills it during Parts 3–7.
- `run_financials.py flags`. UI: event rows with state and clearing; walk report; review-guide rows.

**Tables.** 0033_m04_flags. **Config.** `config/m04_labels.toml` (template). **Review kinds.** `m04_event`, `m04_restate`, `m04_rating`.

**Fixtures and tests.**
- GE walk (about 8 companyconcept files: net income, revenues, CFO and its continuing-operations variant, pretax): 142 steps from 45 filings; Round 2 rows: revenue FY2017 −18,964 with NI unchanged → discontinued operations; NI FY2017 residual +94 → NCI share; CFO FY2017 −4,394 → ASU 2016-15 −4,411 and restricted cash −153; CFO FY2016 +1,404 → `cf_shift_up`, residual +4 on a −244 base → review.
- Infleqtion Q1 2026 little r (revenue +$446K, net loss −$544K) → both steps created.
- Rite Aid FY2017 32,845 first filed → 22,928 recast → discontinued operations label.
- Watchlist walk: 101 steps from 44 filings (the log reconciles Round 2's 102).
- Events: INFQ 3.01 (2026-02-03, NYSE transfer) → information; INFQ 4.01 (2026-03-26) within 90 days of the close → information; Invitae 3.01 (2024-02-06), 1.03 + 2.04 (2024-02-14) → fail inputs; 1.02 + 2.03 co-filings AMZN 2023-11-01, MU 2025-01-21 and 2025-03-12, TSLA 2026-09-29 → financing.
- dei flag: AVGO's 10-K of 2023-12-14 requires it; the 13 earlier 2023 10-Ks read "not required".
- Rating: INTC BBB+ → BBB (August 2025).

**Live check (owner).** `uv run python scripts/run_financials.py flags` — ~26 R1 pages (10-Ks filed from 2023-12-01 across the 18 companies, less those read in 1a; recount at build) + ≤ 35 old filings + ≤ 28 prior 10-Ks + ~8 GE companyconcept ≈ 97 SEC requests, 1–2 minutes. The owner looks for: the walk report per company (steps, labels, residuals; baseline count against 101); queued `m04_restate` items (≤ 4 expected) with their passages; dei flags (false expected); event classes over 3 years (6 red-flag-list events plus INFQ's NT 10-Q); rating sentences; old-filing and prior-10-K counts against the caps.

**Docs.** M00_STORAGE (0033, baseline marker) · M00_SEC_DATA (dei flag via R1, historical document fetch) · M00_UI (event rows, review guide) · DATA_SOURCES DS7 (prior 10-Ks), DS15, DS17 · M04_FINANCIALS (Signals out: `restatement`, `restate_delta`, `non_reliance`).

**Re-probes.** None. **Depends on.** 1a (R1 reader, `facts_as_of`), the setup batch (D-M04-71).

## Part 4a — Survival gate: numbers
**Goal.** The gate from liquidity and legal facts, its states and scope by tag, and the distress, debt and FCF rows beside it.

**Decisions.** D-M04-8 and D-M04-13 (scope), D-M04-29, D-M04-31, D-M04-32, D-M04-33, D-M04-35, D-M04-36, D-M04-37 (consumed), D-M04-38, D-M04-39, D-M04-61; D-M04-21 applied; S4.1–S4.4, S4.9, S4.11, S4.13, SB.18.

**Code.**
- `src/engine/financials/gate.py`:
  - Runway (D-M04-32): burn = OCF − total capex, the worse of TTM ÷ 4 and the last two quarters; liquidity = cash and marketable securities (company aliases, e.g. NVDA) + confirmed undrawn credit maturing beyond the horizon. Cash burners (incl. `issuance_funded`) fail below 6 quarters, warn below 8; capex-funded names (OCF > 0) warn below 8, go to `m04_runway` review below 6, never fail; while that review is open, rule-3 adds are allowed and rule-7 strength is blocked (D-M04-38). "Runway without growth capex" information (D-M04-6); share of liquidity raised in the last 4 quarters for Part 5 (S4.13), with equity issued and debt raised or repaid read from M02's allocation block (`moneyflow/allocation.py`, `fin_tag_map`, "partial: X% mapped" label kept; D-M02-31).
  - Wall (D-M04-33): debt due within 12 months above liquidity fails every gated name, commercial paper never added twice (`DebtCurrent` already holds it); 12-month debt + 4 × burn above liquidity warns; the 24-month wall shown.
  - States in `value_text`: pass, warn (a pass for M01, D-M04-31), fail, incomplete, not_applicable; `method` names the trigger or the missing inputs (S4.1). A turn to fail or incomplete opens `m04_gate_fail` (D-M04-71). Scope by tag: `asset_treasury`, `reit` liquidity-only; `spac_shell` trust only; `fund`, `financial`, untagged FF12 group 11 not applicable, read by M01 as not-pass (D-M04-35); "withheld" → incomplete.
  - Triggers from Part 3 events (D-M04-37); overdue → incomplete plus an exit warning (D-M04-61); input age labelled "as of <date>", foreign annual filers incomplete after 16 months (D-M04-36); non-reliance marker (D-M04-21). Gate states and `filing_status` are recomputed for every covered company in `financials_step`'s local pass on each logon run, not only on a new filing (D-M04-61).
  - `m04_gate_input` covers non-financing gate inputs only; financing tags are mapped once, in M02's `fin_tag_map` (D-M02-31).
- `src/engine/financials/distress.py` — `distress_score` (D-M04-31): Altman Z for manufacturers (incl. GFS), Z'' otherwise, Ohlson O; stage-labelled; market value from class-summed `shares_cover` × close; never a gate input; not meaningful for `asset_treasury`; `m04_score_gap` per S4.8.
- `src/engine/financials/debt.py` — `debt_to_revenue` (total debt incl. current ÷ TTM revenue) and net debt ÷ EBITDA against own 3-year range and peer z (D-M04-29); `fcf_burn` (TTM FCF ÷ revenue and ÷ liquidity, operating vs capex-funded, `capex_split` context) beside `fcf_growth` (D-M04-39). Information rows. `negative_equity`: equity < 0 with an accumulated deficit, TTM operating loss or negative TTM OCF warns; buyback-funded → note (S4.8).
- `credit_line` rows come from owner confirmations; until one exists the runway is cash-only and labelled (the finder lands in 4b).
- M01 reading (D-M04-31): rule-3 adds and rule-7 strength open only on pass (warn counts as pass).
- `run_financials.py gate`; price-dependent Z rows recomputed in the local pass after `prices_step`, labelled with the close date used.

**Tables.** 0034_m04_gate. **Review kinds.** `m04_gate_fail`, `m04_runway`, `m04_gate_input`, `m04_score_gap`.

**Fixtures and tests** (Rivian ~12 and Invitae ~12 companyconcept files; SB.18):
- Boeing FY2019: (10,030 + 6,400 credit beyond 12 months) ÷ ~2,750–2,785 = 5.9 quarters → fail; wall passes; CP 6,109 inside `DebtCurrent` 7,340 not double counted.
- Boeing Q2 2024: 5.5 → fail; wall passes; $7.0B of credit beyond 24 months. Boeing Q2 2022: pass, 7.8–9.5 with credit.
- Rivian Q2 2026: runway 5.5 cash-only → fail until the ABL is confirmed past 12 months (6.1 with it); Z'' −5.37 → `distress_score` warning only.
- Invitae FY2021: runway 5.6 (last two quarters) / 6.8 (TTM) → fail, 715 days before its 8-K 1.03; Z'' 1.31 grey.
- Intel FY2024: runway 5.6, OCF +8,288 → capex-funded, warn + `m04_runway`. AMZN Q2 2026: 9.1 → pass; `fcf_burn` information; "broader tag" marker.
- MSTR: liquidity-only; 24-month wall 4,550 vs 2,448 shown. ETV: not applicable → not-pass. INFQ: trust-only before 2026-02-13; after, OCF-only runway 93.6 (capex untagged) → pass + `m04_gate_input`.
- BA Z 1.53 → `distress_score` warning, gate unchanged; GFS 2.07 and INTC 2.00 grey → no `m04_score_gap`. GFS after 16 months without annual inputs → incomplete.

**Live check (owner).** `uv run python scripts/run_financials.py gate` — ~24 SEC requests (Rivian and Invitae fixture files; the watchlist gate is local), under a minute. The owner looks for: one line per company with state, trigger, runway on both burn bases, liquidity parts with as-of dates, the 12- and 24-month walls, distress variant and zone, `fcf_burn`, debt rows; that no fail appears without its trigger; BA, INTC, AMZN, MSTR, INFQ and GFS against the fixtures above.

**Docs.** M01_TIMEFRAMES (gate values incl. incomplete; not applicable = not pass; the D27 reading; D-M04-38) · M00_STORAGE (0034) · M00_UI (gate panel) · M04_FINANCIALS (gate section; Signals out: `survival_gate`, `runway_q`, `maturity_wall`, `distress_score`, `fcf_burn`, `debt_to_revenue`, `net_debt_ebitda`, `negative_equity`).

**Re-probes.** Optional L7 local re-run for AVGO's Z (0 requests). **Depends on.** 1b (total capex), 1c (tags, stage), 3 (8-K triggers, non-reliance).

## Part 4b — Survival gate: text
**Goal.** Going-concern and covenant language classed into fail, warn or review, with a 25-year baseline, and the undrawn-credit finder that feeds the runway.

**Decisions.** D-M04-34, D-M04-71; S4.5–S4.8.

**Code.**
- `src/engine/financials/gate_text.py` — classes (D-M04-34): fail on an auditor going-concern paragraph, a management "substantial doubt exists" conclusion, an unwaived covenant breach, forbearance or covenant-driven debt reclassification; warn + `m04_gc_text`/`m04_covenant` review on alleviated doubt, audit-matter-only mentions, waived or reset covenants; hypothetical wording → review only when runway < 8 quarters; `spac_shell` periods excluded, keyed on period end; untagged SPACs fall back to the 2.01 close date (S4.5); 6-K text, IFRS "material uncertainty", "event of default", "delist" (S4.6).
- One-off EFTS history pass (S4.7): the three phrases × the watchlist CIKs and the predecessor CIKs, 10-K/10-Q, 2001 to date, plus hit documents not yet stored; recorded as baseline except filings in the last 12 months and a current gate fail (D-M04-71).
- `src/engine/financials/credit_lines.py` — quote-verified facility sentences (amount, maturity) → `m04_credit_line` setup items → `credit_line` on confirmation; the gate recomputes.
- `run_financials.py gate-text`. UI: quote view on gate rows.

**Tables.** 0035_m04_gate_text. **Review kinds.** `m04_gc_text`, `m04_covenant` (incl. the `m04_current_jump` sub-class), `m04_credit_line`; fail-class text opens `m04_gate_fail`.

**Fixtures and tests** (S10's nine documents, trimmed to the sentences): Fisker → fail; Invitae Q3 2023 "substantial doubt exists" → fail; Invitae Q2 2023 ASC 205-40 boilerplate → no trigger; Proterra; Microvast "alleviate" → warn + review; Riot "could raise" → hypothetical; UTI; Albemarle EX-10.1 (relief period, buybacks barred, "Permitted Common Dividend Payments"); Boeing FY2023 "in compliance" → no trigger. INFQ FY2025 10-K "alleviated", period 2025-12-31, before the close → excluded. Boeing credit: FY2019 $9.6B = 3 × $3.2B maturing October 2020, 2022, 2024; Q2 2024 $4.0B (May 2029), $3.0B (August 2025), $3.0B (August 2028).

**Live check (owner).** `uv run python scripts/run_financials.py gate-text` — about 200 SEC requests (48+ EFTS queries, up to ~143 hit documents less those stored, predecessor CIKs), 2–3 minutes. The owner looks for: hits per phrase and company with their class (most are other uses: "not in compliance" 124 documents); the baseline count; any queued item with its quote; credit facilities proposed per company; Boeing's gate after confirming its credit lines.

**Docs.** M00_SEC_DATA (EFTS history pass incl. predecessor CIKs) · M00_STORAGE (0035) · M00_UI · M04_FINANCIALS (text classes; Signals out: `gc_language`, `covenant_status`; failure mode: text leads Chapter 11 by only 62–144 days) · LESSONS if new wording appears.

**Re-probes.** None. **Depends on.** 4a (runway for the hypothetical rule).

## Part 5 — Dilution and financing pressure
**Goal.** Measure issuance split-safely, band it against a sized universe, read what was actually sold, and warn only when shares are sold to survive (outline Red Flag 2).

**Decisions.** D-M04-13, D-M04-22…28; D-M04-65 (equity-point input for 8a); S3.1–S3.10.

**Code.**
- `src/engine/financials/issuance.py` — `net_issuance_yoy` = log change in basic weighted-average shares, same quarter a year apart, both values from one filing; checked against `shares_cover`; `not_meaningful` across an IPO, de-SPAC or recast, and when a pair's ratio to the same filing's recast series is about the exchange ratio (INFQ 0.34740312; data defect) (D-M04-22). Bands (D-M04-23): yearly percentiles of same-filing pairs from frames (basic weighted shares, `EntityPublicFloat`), float ≥ $700M, SIC 6770 out (EFTS SIC path); top quintile = "extreme"; 12-month window with the 5-year composite beside it. Serial = extreme in ≥ 2 of 3 years or a top-quintile composite (D-M04-26).
- `src/engine/financials/offerings.py` — 424B classes (D-M04-24): `ffd` filing-fee facts first, then the fee exhibit; a 424B without an exhibit is paired with the deal's final supplement or its cover is read; a shelf is capacity, not a raise; 424B3/424B7 resales add no shares; text read only for 424B4 lock-ups (release schedule) and resale counts. 8-K 3.02 placements and 3.03 recaps (MSTR preferred designations) as causes. An ATM or resale found by phrase with no fee exhibit or count to confirm it → `m04_financing_doc`.
- `src/engine/financials/pressure.py` — `financing_pressure` (D-M04-25…28): untagged and `issuance_funded` names warn when issuance is extreme or serial and the gate is fail or warn, now or in any of the 4 quarterly filings before the share jump, cover counts tested too; `issuance_funded` with a passing gate outside the warn band → `m04_dilution` (D-M04-13); `asset_treasury`, `reit` → review; `fund`, `financial` excluded; `spac_shell` not meaningful; routed on the confirmed stage (fail warns at every stage; warn warns for mature, shake-out, decline, review for introduction and growth; under 3 years both readings, uncounted; D-M04-27); only non-cash causes (share-paid acquisition, IPO/de-SPAC recast, split, 3.03 recap) make it information (D-M04-28), cash raises keep the warning with the cause shown. No D13 weight until ≥ 20 labels (D-M04-60).
- `src/engine/financials/overhang.py` — gross and net overhang ÷ `shares_cover`: convertibles, warrants, mandatory convertibles, contingent warrants, escrowed shares (S3.6); `m04_overhang`, baseline on first run.
- SBC block (S3.4): SBC ÷ revenue and ÷ OCF, buyback offset, FCF after SBC on total capex; owner earnings information. Buybacks (withholding separate), equity issued and debt flows for the buyback offset and `financing_capacity` are read from M02's `moneyflow/allocation.py` and `fin_tag_map`, keeping the "partial: X% mapped" label (D-M02-31); no second tag mapping.
- `run_financials.py issuance`. UI: issuance with band and cause, offerings table, overhang, lock-up schedule.

**Tables.** 0036_m04_issuance. **Review kinds.** `m04_dilution`, `m04_overhang`, `m04_financing_doc`.

**Fixtures and tests.**
- BA: gate fail Q2 2024, October 2024 raise (129.4M common + 115M mandatory units), CY2025 +17.5% (top quintile on ≥ $700M) with the gate passing → warns via the 4-quarter look-back. BA mandatory: 115M × 0.2914–0.3497 = 33.5–40.2M shares = 4.24–5.09% of 790,370,020.
- MSTR CY2025 +44.2% (Q2 2026 +28.1%, cover +35.5%) → `m04_dilution` review (`asset_treasury`); overhang baseline ~10–11: six convertible series, five preferred (STRF, STRC, STRE, STRK, STRD).
- INTC Q2 2026 +16.8% (cover +15.2%), three 3.02 placements (735.1M shares) → cash cause shown, warns only if the gate warns; 71M escrowed shares beside the 240.5M contingent warrant.
- META −0.5% → information. SPCX +100.2% (IPO) and INFQ +1,310% (de-SPAC) → `not_meaningful`; INFQ legacy pair 46,186,000 × 0.3474 = 16.0M → `not_meaningful`, data defect.
- 424Bs: Intel 424B5 0001193125-26-345221 `ffd` offering $22,999,999,890, fee $3,176,299.98; GOOG's four June 2026 424B5s → equity, a cash raise (information while the gate passes); AMZN's all debt; Intel 424B7 Commerce resale → no new shares; a preliminary supplement without exhibit → paired.
- Band: CY2025 cut +12.1% on ≥ $700M; 95 SIC-6770 filers with float ≥ $75M removed by SIC, not by float.

**Live check (owner).** `uv run python scripts/run_financials.py issuance` — 4 frames (2.8 MB) + 5 EFTS + ~250 fee-exhibit requests (~1.5 a filing) + 3–5 re-probe requests ≈ 260, 1–2 minutes. The owner looks for: band cuts per year and the count of blank checks removed; issuance and band per company; `financing_pressure` states with reasons; the 424B table (security, amount, source: `ffd` / exhibit / paired / cover); MSTR's overhang list; SPCX's lock-up releases; the Up-C candidate's tags.

**Docs.** M00_SEC_DATA (`ffd` facts, fee exhibits, frames cross-section, EFTS SIC path) · M00_STORAGE (0036) · M00_UI · M04_FINANCIALS (Signals out: `net_issuance_yoy`, `issuance_pct`, `composite_issuance_5y`, `sbc_offset`, `financing_capacity`, `overhang_gross_pct`, `overhang_net_pct`, `financing_pressure`).

**Re-probes** (SB.17). S6: SPCX 424B4 "Shares Eligible for Future Sale" block with line breaks joined (1 request, 12 MB, dropped after parse). S7: Up-C tags and members for 1–2 EFTS hits (e.g. Bumble, Perella Weinberg), dimensional included (2–4 requests); its result becomes the Up-C fixture.

**Depends on.** 1c (tags, stage), 4a and 4b (gate state history).

## Part 6 — Earnings quality
**Goal.** Earnings-quality screens as persistence warnings and review items, the estimate-change test across three disclosures, and recurring "one-time" charges (outline Red Flag 3).

**Decisions.** D-M04-14, D-M04-17, D-M04-18, D-M04-19, D-M04-20, D-M04-21 (applied), D-M04-60; S2.1–S2.4, S2.7–S2.9, S2.11; SB.12 (non-operating swings), SB.18 (GE alias).

**Code.**
- `src/engine/financials/quality.py` — `eq_cash` (CFO/NI, cash-flow accruals, operating basis; not meaningful when NI ≤ 0 or |NI| < 1% of revenue; sign-flip guard; tax 21% from 2018, 35% before, unless stated); `mscore` with and without SGI = 1, `m04_mscore` only when the SGI = 1 version is above −1.78, else a "growth-driven" note; `misstate_f` labelled "approximation", both bands (> 1.00, > 2.45), never a trigger, unknown `issue` → missing (D-M04-14). Contract-asset and deferred-revenue gaps; DSO from M02's `financing/credit.dso` shown as context only: the DSO alert stays M02's (`m02_fin_alert`, D-M02-47) and M04 raises no second item for it; an alias-to-standard tag switch reads "definition changed", not scored (S2.2). Stage routing (D-M04-20): 3-year CFO/NI < 0.8 warns for mature and decline, a note for introduction, growth and shake-out; accruals vs own history, no warning; the rest stage-neutral. Non-operating swings by tag (MSTR bitcoin fair value, unrealized gains, valuation-allowance releases).
- `src/engine/financials/estimates.py` — estimate-change sentences from the current and two prior 10-Ks (Part 3): bands < 10% / 10–25% / ≥ 25% of the denominator, both directions, recurrence across three disclosures (D-M04-17); denominator on the amount's own tax basis and period, not meaningful when ≤ 0 or below 1% of revenue, segment share only when stored or quoted (D-M04-18); amounts by filing version.
- `src/engine/financials/special.py` — `special_items`: restructuring, impairment and write-down tags plus FTS5 "non-recurring"/"one-time" wording in ≥ 3 of the last 4 years; cumulative size vs operating income; the company-stated non-GAAP vs GAAP gap quoted, never computed (D-M04-19). No D13 weight until ≥ 20 labels (D-M04-60).
- `run_financials.py quality`. UI: score table with both M-score versions and bands; estimate sentences with band.

**Tables.** 0037_m04_quality. **Review kinds.** `m04_estimate`, `m04_mscore`.

**Fixtures and tests** (scores were computed on scratch data; the build recomputes them and records the values):
- NVDA FY2025 M −0.96 / SGI = 1 −1.98, `misstate_f` 3.11 → "growth-driven" note; NVDA FY2026 −1.17 / −1.75 → `m04_mscore`; MRVL FY2026 −1.60 / −1.98 → note; AAPL FY2025 −2.29 / −2.35, F 1.30; MSFT −2.54 / −2.67, F 1.15; BA FY2024 incomplete, F 1.63; MSTR not meaningful (`asset_treasury`); MU FY2023 M −7.01 not meaningful (negative gross margin).
- GE 2016 estimate change 2,200 ÷ 9,030 = 24.4% → 10–25% band; amount later restated $2.2B → $0.7B kept by filing version.
- GE contract assets (2 companyconcept files): `ge:ContractAsset` FY2016 (25,162) → `UnbilledContractsReceivable` FY2017 (28,861): +14.7% on the line, +18.8% on revenue in excess of billings; GE alias only; `CommodityContractAssetNoncurrent` never mapped.
- Lockheed catch-up revenue (1 file). Alphabet 2023 useful lives 4 → 6 years, NI +$3.0B; Amazon 2025 NI −$1.0B (income-decreasing kept).

**Live check (owner).** `uv run python scripts/run_financials.py quality` — ~10 SEC requests (GE and Lockheed fixture files), under a minute. The owner looks for: the score table per company; queued items (1 expected: NVDA FY2026); estimate sentences per company with band and denominator; `special_items` counts; non-operating swings for MSTR.

**Docs.** M00_STORAGE (0037) · M00_UI · DATA_SOURCES DS7 (partly closed) · M04_FINANCIALS (Signals out: `eq_cash`, `eq_accruals`, `contract_asset_gap`, `deferred_rev_gap`, `mscore`, `mscore_sgi1`, `misstate_f`, `estimate_share`, `special_items`).

**Re-probes.** None. **Depends on.** 1c (stage, tags), 3 (prior 10-Ks, events, non-reliance).

## Part 7a — Unit and dimensional data
**Goal.** The data Rounds 5 and 6 need that companyfacts lacks: dimensional facts (segments, major customers, share classes), unit KPIs, and earnings-release exhibits.

**Decisions.** D-M04-42; S5.5–S5.7; SB.16.

**Code.**
- `src/engine/sec/instance_dim.py` — generalises `moneyflow/instance.py`'s parser to keep dimensional facts on the one instance read: `srt:MajorCustomersAxis`, segment and product axes, class-of-stock axes; recasts flagged; instance files dropped after parse (SB.16). About 180 backfill reads (3 years × 4 filings for the XBRL filers), then one per new periodic filing in `financials_step`.
- `src/engine/financials/units.py` — Tesla DS2 extractor (production, deliveries, storage by model line from stored 8-K EX-99.1; prior quarter and year ago); `unit_metric` with credits kept separate; contribution margins company-stated only.
- `src/engine/financials/exhibits.py` — EX-99.2 letters (≤ 60 a year: 4 releases × configured companies); Invitae EX-99.1 non-GAAP gross-profit reconciliations (S16).
- `config/watchlist.toml` — RIVN tracked (D-M04-42), backfilled with the usual facts and filings.
- `run_financials.py units`. UI: segment and customer tables; unit KPI rows.

**Tables.** 0038_fact_dim. **Review kinds.** `m04_unit_kpi` (KPI definition breaks).

**Fixtures and tests.** NVDA customers ≥ 10%: 3 → 2 (FY2025 → FY2026), revenue at stake 34% → 36% (≈ $77.7B). Target 2022Q1 and Q2 gross margins (−4.4, −8.9 pp; ~4 companyconcept files + trimmed instance). Tesla deliveries 2022 → 2023 (+38%). Rivian deliveries 51,579 → 42,247 (−18%). Invitae non-GAAP gross margin YoY 2020Q1 −7.0 pp, Q2 −31.6, Q3 −6.7, Q4 −2.3; units 469k → 1,290k. Multi-class counts from `fact_dim` agree with Part 1a's R1 counts (GOOG, META, MSTR, SPCX).

**Live check (owner).** `uv run python scripts/run_financials.py units` — ~180 instances + ≤ 60 EX-99.2 + ~25 RIVN backfill + 37 Invitae EX-99.1 + ~4 Target ≈ 300 SEC requests, ~0.5 GB downloaded (instances 2.2–13.5 MB, dropped after parse), 2–3 minutes. The owner looks for: instances read, MB and parse failures; dimensional rows per company and axis; NVDA's customer percentages; the Tesla KPI table; RIVN's backfill; EX-99.2 found per company; cover-count agreement with 1a.

**Docs.** M00_SEC_DATA (instance dimensions, EX-99.2) · M00_STORAGE (0038: `fact_dim`, `unit_metric`) · M00_UI · DATA_SOURCES DS2 (built), DS12 (covered for these axes), DS14 · watchlist config (RIVN) · DESIGN open items: close "Tesla delivery KPIs (DS2)" (EdgarTools is closed in Part 0).

**Re-probes.** None. **Depends on.** 1a. Independent of 2–6; may move earlier.

## Part 7b — R12, unit economics and customers
**Goal.** Revenue up with margins collapsing (R12) found, its cause named and confirmed; young-firm unit-economics flags by stage (R11); the D-M04-1 customer row.

**Decisions.** D-M04-40, D-M04-41, D-M04-43…50; D-M04-30 input (D-M04-47 feeds the Red Flag 1 row in 8a); S5.1–S5.14.

**Code.**
- `src/engine/financials/margins.py` — R12 (D-M04-40): TTM revenue up (from `rev_yoy`) and gross margin down ≥ 3 pp year over year in 2 straight quarters, reported basis with the excluding-stated-items margin beside it; the episode closes after 2 non-qualifying quarters; every stage; one `m04_margin_cause` per episode. Cause finder (D-M04-41): code tags cause sentences ("primarily due to", "driven by", …) into price, mix, competition, volume, input cost, FX, one-off, accounting, segment, credits, with an arithmetic check of stated components, never added across levels; owner confirms; Gemini only on request (D28). Outcome (D-M04-44): price, mix or competition → `r12_warning` plus a CvD Q2 "weakening" vote; volume, input cost or FX → watch; one-off, accounting, segment or credits → cleared, fed to the `special_items` recurrence count. Counting (D-M04-45): confirmed R12 warnings and young-firm per-unit flags count, not while the stage is unconfirmed; the rest information until ≥ 20 labels.
- `src/engine/financials/unit_flags.py` — flag sets by confirmed stage (D-M04-46): `unit_gp_trend`, `unit_cost_vs_cumulative`, `rev_per_unit_vs_cost`, `production_gap`, `credit_share_of_gp`, `inventory_sales_gap`; the SG&A rule for growth; per-unit decline shown at every stage. Burning with falling units `units_falling_burn` (D-M04-47): TTM units fall while FCF on total capex < 0 → young-firm warning (D13 weight: open question in M04_FINANCIALS.md). Positive margin rows get the excluding-stated-items-and-credits basis with the reversion prior shown (unused in decline) (D-M04-48).
- `src/engine/financials/customers.py` — stickiness class proposed by the engine, confirmed by the owner (D-M04-43); data from `fact_dim` axes, else sentences, with M02's `supply_link` read as a dated sentence source (L2 revenue shares, L3 Item 1.01 counterparties, confirmed direction; D-M02-36, -40) and M02's RPO series reused (D-M02-19 (4)); M04 keeps only the loss rules and class logic; only customer-named 8-Ks count (1.02 + 2.03 → financing, Part 3); "weakening" needs owner confirmation; contracted RPO weakening when below its 3-year minimum for 2 quarters, a ratio break alone opens review (D-M04-49); weight = min(1, revenue at stake ÷ 0.25) for design-in, 1 contracted, 0 transactional, missing excluded (D-M04-50); `customer_hhi`.
- `run_financials.py margins`. UI: episode view with cause quotes and the arithmetic check; customer row.

**Tables.** 0039_m04_margins. **Review kinds.** `m04_margin_cause`, `m04_customer`, `m04_unit_kpi`.

**Fixtures and tests.**
- Tesla: 2022Q4 −3.6, 2023Q1 −9.8 pp, TTM +38% → fires 2023Q1; bridge volume +$6.6B, price −$14.0B, cost +$3.2B → price → `r12_warning`; GP per car $13.4k → $7.4k.
- Target: 2022Q1 −4.4, Q2 −8.9 pp, TTM +7.5% → fires Q2 2022; FY2023 23.6% → 26.5% shown as reversion.
- Invitae: 2019Q4 −8.9, 2020Q1 −10.5 pp, TTM +46.8%, +49.7% → fires 2020Q1; excluding-items basis qualifies 2020Q1–Q3 (SB.18); FY2022 revenue per unit $388 (2021 $380), cost per unit $323 ($298); stated items $68.6M equal the whole change → no double counting.
- Intel: 2021Q1 −5.4 pp, TTM +2.6% → silent; 2024Q3 −27.5 pp (≈ −4.1 excluding $3.1B stated) → silent; 2022Q1 TTM −0.01% → no.
- Rivian: units −18% with FCF < 0 → D-M04-47 warning; GP per unit −$23.4k → −$10.2k; credits $299M vs GP $170M (Q4 2024).
- Customers: NVIDIA 2 customers, 36% at stake → weight 1, no loss; a single 12% design-in customer → 0.48; MSFT's ~45% OpenAI RPO share from the call → grade B.

**Live check (owner).** `uv run python scripts/run_financials.py margins` — ~6–8 SEC requests (S14 re-probe, a few releases), under a minute. The owner looks for: R12 episodes per company with quarters and margins; cause sentences, classes and the arithmetic check; proposed stickiness classes; RPO tests; unit flags by stage; Rivian's credit values.

**Docs.** M00_STORAGE (0039) · M00_UI (cause review layout) · M04_FINANCIALS (Signals out: `margin_cause`, `r12_episode`, `r12_warning`, `gm_delta_pp`, `gm_delta_pp_ex_items`, `inventory_sales_gap`, unit rows incl. `units_falling_burn`, `production_gap`, `credit_share_of_gp`, `sga_vs_revenue`, `customer_signal`, `customer_at_stake`, `customer_hhi`) · DATA_SOURCES DS14.

**Re-probes.** S14: Rivian R49 value cells for FY2025 and FY2024 (credits $197M / $333M, $3,639M / $1,551M lines; 1–2 requests). **Depends on.** 4a (FCF, runway), 6 (`special_items`), 7a (units, axes), 1c (stage).

## Part 8a — CvD assembly, health vote and the M04 tab
**Goal.** The Cycle vs Decline grid as amended in Round 6, its classification and confidence, the overreaction gauge, the Red Flag 1 row, M01's reading, and the M04 tab. No new fetches.

**Decisions.** D-M04-1 as amended by D-M04-52…68; D-M04-10 (guidance row), D-M04-30, D-M04-43/-49/-50 (customer row), D-M04-44 (R12 vote), D-M04-21 and D-M04-61 (applied), D-M04-60; D-M01-5.

**Code.**
- `src/engine/financials/cvd.py`:
  - Activation (D-M04-55, -67): TTM revenue falls, gross margin falls ≥ 3 pp, operating income falls ≥ 25%, or the latest quarter's revenue is ≥ 10% below a year earlier; otherwise NO_SLOWDOWN.
  - Q1 rows: revenue growth vs peers (robust z per D-M04-52; fixed-gap fallback below 5; "shared" needs peers falling too; open-ended zones, between = neutral, D-M04-55); industry pricing "missing (DS13)"; inventory days on the own basis (average inventory, write-downs added back); supply response; cycle history from XBRL ("first deep decline").
  - Q2 rows: market share (D-M04-68: owner-entered third-party share, grade B, or computed from a stated industry total, grade A; "falling" = down ≥ 1 pp over 4 quarters in a flat or growing market; else "missing: no share data"); gross-margin gap; trough vs prior trough on 5 pp turning points, write-down adjusted, ROIC agreeing with gross margin for "intact" (D-M04-54); R&D level and total capex intensity, a surge > 1.5× the own 3-year average into falling revenue → neutral with a pointer to M05 (D-M04-54, -64); moat "not applicable until M06"; customer row; guidance row (`guidance_hit_rate`); health vote = F-quality 0–5 (≥ 4 intact, 3 neutral, ≤ 2 weakening; D-M04-53, -59) with the equity point per D-M04-65; R12 vote only when it fires (D-M04-44). Piotroski F and Mohanram G shown, not voted.
  - Resolution (D-M04-56): missing rows leave the denominator; ≥ 2 rows present; 2/3 majority of present weight; `cvd_confidence` = the lower of the two winning shares; coverage shown. Classification table; AMBIGUOUS, STUMBLE and CYCLE_PLUS_DAMAGE → `m04_cvd`, the owner's answer becomes the state (D-M04-56). Stale mark once a period has ended unfiled; overdue blocks (D-M04-61); non-reliance marker (D-M04-21). Intel's expected state is AMBIGUOUS → owner review (D-M04-63).
- `src/engine/financials/gauge.py` — normalized earnings power on current revenue and on cycle-average revenue (D-M04-54); one-time items excluded only if nothing similar occurred in the prior 10 years, reported and ex-items both shown (D-M04-66); overreaction gap = 4-quarter price change − change in NEP on current revenue, same 4 quarters, flagged at ≤ −25 pp, cycle-average base beside it (D-M04-57); never needed for rule-7 strength (D-M04-62). Runs after the price step, or labels the close date used.
- `src/engine/financials/red_flag1.py` — Red Flag 1 joint row `burn_no_share_gain` (D-M04-30): burn (runway warn or fail, or FCF on total capex < 0) together with market share up < 1 pp (D-M04-68), D-M04-47's falling-units warning feeding it; never a gate input; "missing" without share data. No D13 weight until ≥ 20 labels (D-M04-60).
- M01 reading (D-M04-58 / D-M01-5): only CYCLICAL_TROUGH with a gate pass adds rule-7 (D27) strength; NO_SLOWDOWN allows tranches; AMBIGUOUS, STUMBLE, CYCLE_PLUS_DAMAGE, STRUCTURAL_DECLINE and overdue block tranches. Exit warnings (rule 4) on CYCLE_PLUS_DAMAGE, STRUCTURAL_DECLINE, overdue, gate fail and `guidance_removed`; red-flag warnings listed in the reasons, never blocking (M04_FINANCIALS.md "How M01 reads M04").
- UI: M04 tab (`tabs/m04.html`), mock-up first with MU and INTC grids from Round 6 values (SB.7); market-share entry form (owner, with source). `run_financials.py cvd` (`--no-sec`).

**Tables.** 0040_m04_cvd (`market_share`). **Review kinds.** `m04_cvd`.

**Fixtures and tests** (Micron closes equal stored Tiingo closes, L9; F-quality values recomputed on the 0–5 scale of D-M04-59):
- MU Q4 FY22 (10-K 2022-10-07): TTM +11.0%, quarter ≈ −19.7% → active by D-M04-67; gap −45.1 (flagged). Q1 FY23 −34.3; Q2 FY23 −18.4 (cycle-average −60.5); Q3 FY23 +29.7; Q4 FY23 (10-K 2023-10-06) → CYCLICAL_TROUGH, confidence 1.00, Q2 on 3 of 7 rows present. The $48.88 low (2022-09-26) sits in a stale window (Q4 FY22 unfiled).
- Inventory days Q2 FY23 153.1 / 235.0 (write-down added back; `InventoryNet` 8,359 / 8,129).
- INTC 2023 → AMBIGUOUS 0.25 → `m04_cvd`; capex 1.75× its 3-year average with falling revenue → neutral. INTC 2024 +2.1% issuance, not extreme → equity point kept.
- MU FY2023 capex 1.30× → intact. NVDA FY2023 activates on margin only (GM −8.0 pp). MU FY2016 F-quality neutral, not weakening. NVDA G 3 of 7 in a +125.9% year → shown, not voted. Invitae: gate fail overrides the grid.

**Live check (owner).** `uv run python scripts/run_financials.py cvd --no-sec` — 0 SEC requests, under a minute, after a normal refresh with prices. The owner looks for: one grid per company (state, confidence, coverage, each row with its value or "missing: <reason>", the gauge on both bases); MU and INTC against the fixtures; queued `m04_cvd` items; the M04 tab on real data.

**Docs.** M01_TIMEFRAMES (CvD states read by rules 3, 4 and 7 as built; D-M01-5) · M00_UI (M04 tab, share entry) · M00_STORAGE (0040) · DATA_SOURCES DS13 (still a gap), DS16 (owner entries built) · M04_FINANCIALS (final Signals out: `cvd_state`, `cvd_confidence`, `cvd_coverage_q1`, `cvd_coverage_q2`, `deeper_than_peers`, `f_quality`, `f_score`, `g_score`, `normalized_ep_cur`, `normalized_ep_cyc`, `overreaction_gap`, `market_share_chg_pp`, `burn_no_share_gain` (Red Flag 1 row)) · DESIGN phase.

**Re-probes.** None. **Depends on.** 1a–7b.

## Part 8b — Calibration
**Goal.** Score the engine against the owner's blind labels on real episodes, with first-filed facts and name-matched prices, and hand the results to a High-effort review. No threshold is changed inside this part (D6).

**Decisions.** D-M04-51, D-M04-72, D-M04-73, D-M04-75; S6.1, S6.3, S6.15.

**Code.**
- `src/engine/financials/episodes.py` — the ~70 episode and peer companies (17 non-watchlist episode companies plus ~5 peers in each of ~12 industries, after overlaps): one trimmed companyfacts each (D-M04-75); all reads through `facts_as_of` with first-filed values (S6.1; Rite Aid FY2017 recast 32,845 → 22,928).
- `src/engine/prices/episodes.py` + a metadata call in `prices/tiingo.py` — a Tiingo symbol is used only when its name and date range match the SEC company over the episode window: BBBYQ, RADCQ, NVTAQ, SHLDQ, RSH/RSHCQ, FIT, BTUUQ, GPRO (BA stored); bars stored under the episode symbol in `episode_symbol` keyed by CIK, never under a recycled bare ticker (BBBY, RAD, SHLD); last real trade found first (RADCQ, NVTAQ end 2026-10-09); BTU and CHK checked for splices; J.C. Penney "missing: no prices" (gauge and Z's X4 missing). ≤ 34 Tiingo requests; 8 an hour stay reserved for the app; budget stop reported (D-M04-72).
- `src/engine/financials/backtest.py` — tunes only activation, the z cut, the majority rule and the gauge threshold; information rows reported, not tuned (D-M04-51); walk-forward (calibrate ≤ FY2017, test 2018+); confusion matrix, label stability, every variant logged. Red-flag report: each flag family against the owner's red-flag labels, no weights (D-M04-73).
- `run_financials.py backtest`.

**Tables.** 0041_m04_backtest. **Config.** Reads `config/m04_labels.toml` (filled by the owner). **Review kinds.** None.

**Fixtures and tests.** Trimmed companyfacts for MU, INTC, WDC and the chip peers (one file per company, SB.6). Tiingo metadata: BBBY (no data), RAD (Radiopharm, ASX), SHLD (Global X ETF) → rejected; BBBYQ (1992-06-05 … 2023-09-29) → accepted; JCP, JCPNQ absent → "missing: no prices"; NVTA meta 404 → NVTAQ used. Episode facts: BBBY revenue FY2016–FY2023 12,104 → 5,345 (tag switch at FY2019); BA 101,127 / 76,559 / 58,158 (FY2018–20); Invitae FY2021 460.4, FY2022 516.3. A stale repeated bar after cancellation is not a trade.

**Live check (owner).** `uv run python scripts/run_financials.py backtest` — ~70 companyfacts (~200–240 MB downloaded; engine.db ≤ ~0.3 GB more, estimate) + 1 (S17) SEC requests, about a minute; Tiingo ≤ 34 + 4–6 (T2) at 3 s spacing, about 2 minutes. Labels must be complete first. The owner looks for: the symbol table (accepted / rejected with reason, last real trade, splice verdicts); per-episode state path against the label; the confusion matrix for each window and label stability; red-flag hit rates against labels; rows, MB and Tiingo requests used; BBBY's pre-FY2016 revenue tag.

**After the part.** A High-effort review with sources (D6) proposes thresholds and red-flag weights; accepted items become D-M04-76 onward. Until then every starting value stands.

**Docs.** M04_FINANCIALS (calibration results recorded as a proposal, not as edits) · DATA_SOURCES DS8 (delisted symbols) · M00_STORAGE (0041) · SOURCES · DESIGN phase ("M04 built; calibration review next").

**Re-probes** (SB.17). S17: Rite Aid's "last 10-K" submissions row (form, report date, primary document; 1 request). T2: `daily()` windows around the RADCQ and NVTAQ cancellations and their last 30 days; BTU for 2016; CHK for 2020-07 (4–6 Tiingo requests, no storage). **Depends on.** 8a; labels complete.

## Failure modes (build)
| Input or step | How it can mislead | Guard |
|---|---|---|
| Live-check estimates | Peer and episode counts are estimates; large downloads dominate time | Each log prints requests, MB and seconds per fetch type; runs resumable |
| Lock | Two SEC processes reach 10/s (S121) | `run_script` in the script; `financials_step` inside the refresh lock |
| Logon refresh | M04 work makes the background run heavy in the owner's session | Per-new-filing SEC work only, plus a local pass (0 requests) for filing status, gate state and price rows; step timed in the run report; backfills owner-run (D-M04-70) |
| First runs | Baselines flood the queue (101 walk steps, 136 EFTS hits, ~10 overhang items) | Baseline recorded, not queued, with the 12-month and current-fail exceptions; cap 5 and priority (D-M04-71) |
| Fixtures | Companyfacts files bloat `tests/fixtures/`; later filings change files | Companyconcept per tag or trimmed files; fetch date in the name; tests pin values |
| Tickers | A recycled ticker attaches another company's rows or prices (BBBY 2025) | `signal` keyed by CIK (D-M04-74); Tiingo symbol matched by name and dates (D-M04-72) |
| Delisted prices | Tiingo keeps delisted data only for tickers not yet recycled; stale bars after cancellation | Metadata check; last real trade first; "missing: no prices" |
| Form filter | GFS's quarterly facts arrive on XBRL 6-K in `ifrs-full` | Form list plus XBRL 6-K; facts sync on 6-K (SB.11) |
| SIC exclusions | MSTR (6199) sits among financials | Model tag before any score (D-M04-8) |
| Fee facts | `ffd` facts only from 2026-04, none for MSTR; 21 of 41 424Bs lack an exhibit | Exhibit fetch; pairing with the final supplement or cover read |
| Instance reads | M02's reader kept no dimensional facts | `fact_dim` stored on the one read (Part 7a) |
| EFTS company filter | Predecessor CIKs are not searched by default | Predecessor list from 1a queried with the same phrases |
| Engine DB growth | Peer and episode facts lengthen backups and as-of reads | M04 tags only (D-M04-75); row counts and DB size in every log; the owner decides on any split |
| Calibration | Backtest results invite threshold edits inside a build | Changes proposed with sources in a High review (D6) |
| Missing vs zero | A missing input read as 0 passes or fails a rule silently | "missing: <reason>" rows (D-M04-9); tests assert no zero fill |

## Open points for the build
- **R1 depth:** S1.12 says "R1 full history 163 filings"; D-M04-2 says ~37 requests for 3 years, older history on basic weighted average. This log follows D-M04-2 (binding); full history only if the owner asks.
- **Missing rows and `evidence_grade`:** settled in Part 1a — NULL is allowed only on missing rows (CHECK in 0029); a missing row that names inputs still records their weakest grade.
- **ROIC formula:** defined by S6.5 (accepted with Round 6; see Part 1b), not by a D-M04 line. Part 1b builds it as written.
- **Stickiness-class proposals (D-M04-43):** ~15 at first run; D-M04-71's setup batch names only stages and peers. Proposed: treat them as setup items outside the cap in 7b.
- **Label file:** `config/m04_labels.toml` is committed and readable by Claude; if the owner wants labels private, they go under `data\` and only the backtest reads them.
- **RIVN:** "tracked" in D-M04-42 could mean the M02 tracked tier (facts and filing index only) or the core watchlist; instance and EX-99.2 reads need the filing list either way. Confirm in 7a.
- **Per-kind caps:** Round 5's per-kind caps (e.g. customers 3 a week) are read as superseded by D-M04-71's single cap of 5 (open question in M04_FINANCIALS.md).
- **Review-kind names:** Round 4's S4.8 names govern over the pack's single `m04_gate` (the pack allowed rounds to rename kinds); `m04_runway` and the starred signal names in M04_FINANCIALS.md are proposed and confirmed at build.
- **Recounts at build:** walk steps 101 vs 102 (Part 3); Part 3's R1 page count; migration numbers if another branch lands first.

## Notes per part
(filled during each build: live-check log names and findings, fixes with D-M04-n, what was deferred)

### Part 0 — docs
- 2026-10-12, branch `m04-part0`: SOURCES S122 (McConnell & Muscarella, was the duplicate S101) and S123–S225 (131 provisional IDs; 43 merged into 15 numbers; map at the end of the pack's "New sources"); five one-clause findings (S139, S163, S199, S220, S223) marked "verify before citing". DATA_SOURCES DS12–DS17 registered; DS2, DS7, DS8 updated. DESIGN (open items closed, D13/D14/D27/M05 notes, workflow, code map, Resume here), M01 (rule 4 exit warnings, rule 7, D-M01-5 STUMBLE, inputs refresh, windows) and M02 (capex-weighting question, DSO) edits applied. M05/M09 packs now number their provisional IDs from S226. No code; no live check.
### Part 1a — Data foundation
- 2026-10-12, branch `m04-part1a` (built; awaiting the owner's live check). Mock-up approved by the owner (option a: M04 sections below the quarterly and balance-sheet tables; D-UI-22).
- **Built.** Migration 0029_m04_data: `signal` rebuilt (key cik, module, signal, timeframe, as_of; `value_text`; ticker for display; CHECKs: no text in `value`, an empty row needs "missing: …", grade and source may be NULL only on missing rows — closes the open point above), old rows moved by the ticker span covering `as_of`; `entity_link` seeded (Google Inc. → Alphabet to 2016-02-11, Marvell Technology Group → Marvell Technology to 2021-03-16, Churchill Capital Corp X shell to 2026-02-13); `cover_shares`; `filing_status`; `entity.category`. Code: `sec/asof.py` (`facts_as_of`), `sec/cover.py` (R1 reader, both layouts: classes as row groups or as column headers, XML R pages), `financials/shares.py`, `financials/status.py`, `financials/step.py`, `financials/views.py`, `signals.py` (`write_signal`), `scripts/run_financials.py` (subcommand table; `data`), refresh hooks (`financials_sec_step` after official, `financials_local_step` after prices, both timed), `refresh.FACT_FORMS` = `xbrl_facts.REFRESH_FORMS` (+10-KT/10-QT/40-F/A) and a 6-K forces a facts sync only when `filing.is_xbrl = 1`.
- **Concepts (xbrl_facts).** New series: `shares_period_end`, `shares_cover`, `shares_basic_wavg`, `shares_diluted_wavg`, `sbc`, `public_float`. `da` drops `DepreciationAndAmortization` and ends with `Depreciation` marked "≈ narrower tag"; `ppe_net` ends with the finance-lease-inclusive tag marked "≈ broader tag"; capex's `PaymentsToAcquireProductiveAssets` marked "≈ broader tag: includes software and intangibles" (the legend's D-M04-3 wording; the capex rows themselves are Part 1b). S1.3 extra list = `EXTRA_CONCEPTS` (41, read through `facts_as_of`, never in `series`). Aliases per CIK only: GE `contract_assets` ← `CommodityContractAssetNoncurrent` and `ge:ContractAsset`; NVDA `short_term_investments` ← `nvda:MarketableSecuritiesAndEquitySecuritiesFVNI` (extension facts exist only where M02's instance reader stored them).
- **PARSER_VERSION → facts-2.** Stored `series` rows change (new concepts, `da` tags, method marks), so the label changes. It costs **no** companyfacts download: `series` is rebuilt from the stored `fact` rows (`rebuild_series`), which `data` does for every covered company (0 requests); the refresh rebuilds a company whenever it syncs it.
- **Decided at build.** (1) `facts_as_of` first value = earliest filed under any tag, value = highest-priority tag among facts filed by the as-of date. (2) Predecessor facts are read when filed on or before the boundary; shell facts are dropped when their document's period (filing `report_date`, else its latest fact period) ends before the closing; `include_shell=True` shows them. (3) The submissions category governs the latest 10-K and later periods; older periods use the Rule 12b-2 chain from stored float; a missing float is estimated as cover count × close at the Q2 end (labelled), else carried, else the longest deadline (labelled). Weekend due dates roll to Monday (holidays not checked). (4) Next expected period: same position a year earlier shifted by a year (52/53-week safe), else month-end +3 months, else +91 days; 20-F filers annual only. (5) `filing_status` signal as_of = filed date (current), period end (stale) or due date (overdue), so rows do not repeat daily; `shares_cover` and `implied_float_shares` are written as info rows (weight 0). (6) Refresh R1 reads = annual covers of every covered company plus 10-Qs of multi-class filers, filed in the last 30 days and not read yet; older filings only through `data`. (7) Multi-class = the latest 10-K/10-Q with stored facts has no non-dimensional dei cover count (GOOG, META, MSTR, SPCX today).
- **Fixtures** (`tests/fixtures/m04/`, hand-built, README lists sources and placeholders): MU and WDC revenue and Alphabet net income as companyconcept files; Invitae dei float and cover counts; META, MSTR 2011, SPCX (illustrative counts) and Google Inc. 2009 R1 pages. 31 new tests (573 in all).
- **Live check (owner):** `uv run python scripts/run_financials.py data` → `logs/financials_data_<time>.txt`. About 39 SEC requests (≈37 R1 pages: GOOG 12, META 12, MSTR 12, SPCX 1, plus `R1.xml` only where `R1.htm` is 404; 2 WDC companyconcept files), well under a minute; no companyfacts downloads. Re-runs: `… data --no-sec`.
- **The owner looks for:** per-class and summed cover counts with cover dates (META FY2025 10-K 2,187,177,748 + 342,377,716 = 2,529,555,464 at 2026-01-23, flag false); "R1 read as not a cover" lines; split-guard hits (MSTR counts before 2024-08-08 ×10); WDC FY2023 revenue 12,318M as of 2024-12-31 and 6,255M today; `filing_status` for every covered company — none overdue expected; calendar-quarter filers read **stale** until their Q3 2026 10-Q arrives (a period has ended unfiled, not yet due, D-M04-61); the extra-tag report; the GFS 6-K lines (XBRL → sync, none → backstop); rows added per table and engine.db MB before and after.
- Live check 1 (2026-10-12, `logs/financials_data_20261012-174457.txt`): 39 SEC requests (37 R1 pages, 2 WDC companyconcept), 0 failures; 37/37 R1 pages read as covers (GOOG 12,230,000,000 at 2026-07-15; META 2,529,555,464 at 2026-01-23 as expected; MSTR pre-split counts ×10 by the guard; SPCX 13,181,779,945 at 2026-07-28); filing status current 6, stale 11, overdue 0, ETV not evaluated; WDC FY2023 revenue as of 2024-12-31 = 12,318M, as of today 6,255M (recast after the SanDisk separation) — the as-of read works; series rebuilt from stored facts (facts-2, 0 requests); engine.db 352.3 → 358.6 MB. Fixes: GOOG's Class C member label "Class C share repurchases" cut to "Class C" (stored GOOG rows keep the old label until their next read); INFQ's non-accelerated category now names the SRC revenue test; split-guard hits (236, mostly AAPL dei history) summarised per company in the log.

### Part 1b — Capex, trends, guidance record
- 2026-10-12, branch `m04-part1b` (built; awaiting the owner's live check). Mock-up approved by the owner (sections below the Part 1a ones: Capex, Core trends, Guidance record; D-UI-23).
- **Built.** Migration 0030_m04_capex: `capex_split` (cik, fiscal year end, total and its tag, definition-changed flag, maintenance, growth, method, rung, uncapped rung value, Greenwald net/gross kept only in range, note, marks) and `guidance_outcome` (kind `score` or `removal`; outcome hit / miss / unscored / removed / expired / missing / pending, `revised` reserved for M11; state, revisions down/up, actual and its reference, grade, reason passage). Code: `financials/capex.py` (definitions, own-history series, split, Greenwald cross-check, FCF rows), `financials/trends.py` (trend rows, ROIC), `guidance/record.py` (shared scorer, removals, hit rate, signals), `financials/step.py` local pass (`part1b`: recompute, store, signal), `financials/views.py` + template, `run_financials.py capex`. Shared changes: `moneyflow/guided.freshness` takes `metric` (the six states for every metric family) and `event` (states at an earlier release); a capex refusal no longer counts for another metric and vice versa; `moneyflow/instance.py` gains `instance_href`, `instance_facts` (moved from `scripts/probe_m04.py`, which now imports them), `find_instance` (raw index page: the instance sits in the data-files table that `parse_filing_index` skips) and a `url=` on `store_instance`; NVIDIA's `nvda:PurchasesOfPropertyAndEquipmentAndIntangibleAssets` is a per-CIK `capex` alias (marked "≈ broader tag: includes intangibles"). `tests/conftest.py` blocks every `requests` call in fixture tests (see below).
- **Decided at build.** (1) Own history: two definitions — PP&E payments (us-gaap or IFRS PP&E tag) and productive assets (the broader us-gaap tag plus per-company extension aliases; NVIDIA's extension and later `PaymentsToAcquireProductiveAssets` share a caption, so one definition); the one with more fiscal years is the series (tie → PP&E); a year only the other has is filled, marked "definition changed" and not scored in FCF growth. A broader series carries "broader tag: <what it adds>" and, where the PP&E tag also exists, the gap ("+15.8% vs the PP&E tag", AMZN FY2016). (2) Fiscal-year points must end within 10 days of the company's fiscal year end (Amazon's 10-Q trailing-twelve-month cash flows are not fiscal years, D-M02-34 (3)). (3) Window = the last 8 fiscal years with total capex; the split rung is the highest rung with a value in the latest year; a year without that rung's fact reads "not split" (no mixing). The disclosed and project-level rungs have no finder yet, so depreciation is the rung in practice, D&A where `Depreciation` is untagged. (4) Greenwald on latest-known revenue and PP&E (`ppe_net`, `ppe_gross`, finance-lease-inclusive tags as their marked fallbacks), average of the five prior yearly ratios × revenue change; in range = 0 ≤ maintenance ≤ total capex; real MU data gives 6 of 8 (net) and 7 of 8 (gross); real INTC shows 4 of 8 in an 8-year window (its four revenue-falling years 2022–25; the fixture's 4-year capex window gives 4 of 4). (5) "useful-life change?" is a numeric mark: depreciation down ≥ 20%† while gross PP&E grows (INTC 2023 −29.5% / +11.7%); text evidence is Part 6's estimate finder. (6) A row "FCF on maintenance capex" (the R1 brief's depreciation-basis FCF: MU −6,111 / 9,245 / 80,255) sits beside owner earnings, which also subtracts SBC. (7) Trend signals use TTM when a TTM a year earlier exists (rev_yoy, gm_trend_pp 4-quarter, opex_vs_sales), else fiscal years; near-zero base = below 1% of the base year's revenue; opex = gross profit − operating income; "not meaningful" is `value_text` `not_meaningful`. (8) ROIC: equity and cash required; long-term debt, current debt and short-term investments without a fact are taken as none on the balance sheet and named in the method; average invested capital ≤ 0 → not meaningful; display only (no ROIC signal in the Signals-out list; Part 8a reads `trends.roic`). (9) Guidance actuals: first-filed values via `facts_as_of`; ratios (gross and operating margin, tax rate) from first-filed parts, gross margin derived from cost of revenue when untagged; basis "unspecified" scored on GAAP and labelled; non-GAAP → missing until a reconciliation store exists; metrics with no mapped actual (operating expenses, other income) → missing; ± guides are ranges; "hit" includes above the range (state says so). (10) Not-ended periods are stored as `pending` with M02's freshness state. (11) Removal = per earnings release against the release reporting the same fiscal quarter a year earlier; family = metric + horizon (next quarter, this or next fiscal year), any basis; states evaluated at that release; one row per metric and expected period (removed or expired first, then reason stated, then missing; earliest release). Reason = a stored `guidance_skip` refusal or a withdrawal sentence ("not providing full-year guidance", "withdraw/suspend … guidance", "move to quarterly guidance") in this and the prior release and their calls; with a reason the row is `unscored`, state "reason stated", quote stored. (12) `guidance_removed` is one signal per release date (the signal key has no metric), `removed` if any guide was dropped for a period not yet ended, else `expired`, metrics in the method; `guidance_hit_rate` in percent with n, misses, revisions and "repeated" in the method, as_of = the newest actual's filing date; missing reasons "(DS1) release-silent guider", "no earnings release scanned", "no scored guide yet (…)". (13) Signal `as_of` = the newest input's filing date, so rows do not repeat daily. (14) The tab computes capex, trends and the record live (as the Money flow tab does); the local pass stores `capex_split`, `guidance_outcome` and the signals — about 1 s per company.
- **Fixtures** (`tests/fixtures/m04/`, README lists sources): trimmed companyfacts files for MU, INTC, MSFT, AMZN, NVDA (R1 brief, probe log L1); NVIDIA FY2013 and FY2021 trimmed instances and filing index pages (probe S4). 21 new tests (596 in all).
- **Incident (2026-10-12, during the build):** the Part 1a script test called `run_financials.py capex` to check "not built"; once `capex` was built, that test ran the real subcommand: 9 SEC requests (NVIDIA filing index pages, now cached), Part 1b tables and signals written to `data\engine.db` (migration 0030 applied there) and `logs/financials_capex_20261012-190919.txt` written. Fixed: the test uses an unbuilt subcommand, and `tests/conftest.py` now fails any `requests` call in a test not marked `live` (LESSONS). Because 0030 is applied to the real database, its schema must not change on this branch.
- **Live check (owner):** `uv run python scripts/run_financials.py capex` → `logs/financials_capex_<time>.txt`. About 18 SEC requests (9 NVIDIA filing index pages — now cache hits — and 9 instances of ~2–3 MB, each parsed, its extension facts stored and the file dropped from http_cache), well under a minute; then 0 requests for the recomputation. Re-runs: `… capex --no-sec`.
- **The owner looks for:** per company the total-capex definition and marker (AMZN and NVDA "broader tag"), "definition changed" years (NVDA FY2010–12 on the PP&E tag expected), the company-definition value beside it (MU FY2023 stated net capex 7,010 vs tag 7,676); split rung and Greenwald in range (MU 6/8 net, 7/8 gross; INTC FY2023 "useful-life change?"); FCF and owner earnings; trend rows for all covered companies with missing reasons; guidance hit rates, misses, removals with their state or reason; NVIDIA FY2013–FY2021 capex from instances (FY2013 183.3M, FY2021 1,128.0M); requests, MB, rows added and engine.db size.
- Live check 1 (2026-10-12, `logs/financials_capex_20261012-193656.txt`): 9 SEC requests (9 NVIDIA XBRL instances, 23.8 MB, each parsed and dropped from the cache; the 9 index pages were cache hits), 0 failures; NVIDIA series rebuilt from stored facts; the NVIDIA FY2010–22 capex series matches (FY2013 183.3M, FY2021 1,128.0M); Greenwald out of range MU 6/8 net, 7/8 gross, INTC 4/8; INTC FY2023 "useful-life change?" mark (depreciation −29.5%, gross PP&E +11.7%); recomputation for 18 companies at 0 requests (11.7 s); engine.db 354.5 → 359.0 MB. Fixes: (1) own-history definition = the one covering the displayed 8-year window, tie → PP&E tag (D-M04-3): AMZN was on the PP&E tag (more years over its whole history) with FY2018–25 all "definition changed" and FCF growth missing; now the broader tag for the window, FCF growth computed, older PP&E-only years still marked. (2) Capex guides scored only on an exact M02 recipe; MSFT FY2026 Q4 (≥ $40B vs PP&E-only $35.8B, clause "including the lease reclassification impact from the useful life update" not mapped) is now "unscored: capex recipe approximate (…)", not a miss (D-M04-84). (3) Direction-aware scoring: cost metrics miss above the high end; tax rate and other income unscored, "not a performance target" — NVIDIA's four and Meta's one tax-rate misses become unscored (D-M04-84). (4) Only core families (revenue, gross margin, EPS, operating income, net income, capex, FCF) count as removed / feed `guidance_removed`; INTC, NVDA operating-expense and META, NVDA tax-rate / other-income removals read "dropped (information)" (D-M04-85; migration 0031_guidance_dropped rebuilds the derived `guidance_outcome` table with outcome `dropped`, since 0030 is applied to the real database). `capex --no-sec` also rebuilds NVIDIA's series from stored facts and prints "SEC requests: 0". Re-run: `uv run python scripts/run_financials.py capex --no-sec`.
### Part 1c — Company profile, queue and peer shortlist
### Part 2 — Peer facts and statistics
### Part 3 — Restatements, filing events, prior filings
### Part 4a — Survival gate: numbers
### Part 4b — Survival gate: text
### Part 5 — Dilution and financing pressure
### Part 6 — Earnings quality
### Part 7a — Unit and dimensional data
### Part 7b — R12, unit economics and customers
### Part 8a — CvD assembly, health vote and the M04 tab
### Part 8b — Calibration

## Notes for other modules' reviews
Questions in other design packs that M04 now settles (read before that module's review; M04 decisions bind).
- **M03:** the segment store is `fact_dim` (cik, accession, concept, axis, member, period, value, unit; D-M04-42), not `segment_fact`, with no first/latest-filed or external columns and watchlist only. SIC peer discovery (D-M04-4), peer offset (D-M04-5), small-n statistics (D-M04-52), firm stage (D-M04-7, owner-confirmed, D-M04-12) and shares (D-M04-2) are decided. Narrow S1.1 to one choice: extend `fact_dim` to the tracked tier, or add first/latest-filed columns.
- **M05:** the capex split is M04's with a depreciation default (D-M04-6, amends A2); M04 builds the customer store (axes, sentences, `customer_class`; D-M04-42, -43), so drop the A2 and customer-store questions. M04's tag file takes only its six tags (D-M04-8), so a spend-channel field needs a separate key or file that M04's loader ignores. M04 computes the Q1 supply and Q2 capex/R&D rows (D-M04-54, -64): S4.3 narrows to "M05 reads M04's rows and supplies only the D-M04-64 pointer view". `commitment_risk` is not adopted by any M04 decision; put it to the owner as an M04 addition.
- **M07:** the shares split and implied float are decided (D-M04-2; four series, class-summed cover count, M07 owns R22). Read `shares_cover`, `shares_period_end` and the implied float; drop the shares-split question; renumber M07's provisional DS entries after DS17 (M04 uses DS12–DS17, Part 0).
- **M08:** stage comes from Part 1c (`lifecycle_stage`, owner-confirmed; D-M04-7, -12), not "part 2"; `shares_diluted_wavg` exists (D-M04-2); NEP has two bases plus ex-items (D-M04-54, -66); peers per D-M04-4 (Parts 1c, 2); dividends paid come from M02's allocation block (D-M02-31). Drop the "unless M04 adds them" items.
- **M09:** MSTR's gate (`asset_treasury`, liquidity-only, CvD runs; D-M04-8) and the share series (D-M04-2) are decided. Q4.1's `qualified` reads `survival_gate` and `cvd_state` per D-M01-5; its "R3 screen" waits on the owner's first-entry (rule 1) decision, which M04 does not define.
- **M10:** `financing_pressure` (D-M04-25…28), the maturity wall (D-M04-33) and `fact_dim` axes (segment, product, customer, class; D-M04-42) are decided, not proposals. Narrow 3.3 to: store all axes on Part 7a's instance read (geography at no extra request) and floating-rate debt as a Part 4a addition for the owner.
- **M11:** M04 Part 1b builds the shared guidance scorer (`guidance/record.py`, `guidance_outcome`: hit, miss, unscored, revised, removed, expired; D-M04-10); M11 owns R19 scoring and weighting and extends that scorer rather than building its own. M11's planned `withdrawn` detection is M04's `guidance_removed` (S1.7, fired only in M02's "not restated" state). NO_SLOWDOWN is defined by D-M04-55.
