# M04 Build parts (proposal) — brief

Updated for Rounds 1–5 answers (D-M04-2…50) and the probe (2026-10-12): 13 parts (4, 7, 8 split; restatement walk and both old-filing fetches in Part 3); requests recounted from measured rates (~2,850 one-off, ~1,170 under new B.9a); full peer companyfacts would add up to 1.0–1.25 GB to engine.db → B.9; B.3, B.6 narrowed (cap 5, D-M04-34, -45); B.4 uses Tiingo's delisted symbols; INFQ's going-concern sentence is a `spac_shell` period, excluded.

**Decides:** 13 parts, one owner live check each; questions B.1–B.4, B.6, B.7, B.9 (B.5, B.8 settled).
**Outline items:** Analyze 1–4 and 6 (lines 65–74), Red Flags 1–6 (78–83), Capex 3–5 (92–95). Also D-M02-12, D6, D8, D10, D13 (extended by D-M04-9), D24.

## What the research says
- M02: one conversation and one live check per part, 2–4 live rounds kept cheap by `--no-sec`; mock-ups first (D-UI-4).
- Pace 5/s per process (S121; `run_script` holds the lock). Probe: 4–4.6 requests/s with downloads, ~4 MB/s on large files. Logon task limit 3 h; refreshes 1.5–6.7 min.
- Sizes (probe L10): engine.db 352.2 MB, 351,351 fact rows over 18 CIKs (≤ ~1.0 KB a row); corpus.db 891.6 MB, ~442 MB http_cache (companyfacts median 3.40 MB). Documents: 10-K 2.3–4.9 MB, 10-Q 1.6–2.0, 8-K < 0.1, instances 2.2–13.5, SPCX 424B4 12.0.
- 14 watchlist 10-Ks were filed in 2023; 13 before 2023-12-01 (no dei error flag required), AVGO's on 2023-12-14.

## Worked example
**Parts and live-check budget** (estimate = depends on peer or episode choices):

| Part | Contents | SEC requests | Check |
|---|---|---|---|
| 1a Data | `facts_as_of`, form list (SB.11); predecessor CIKs; share series, R1 reader, implied float (D-M04-2); migration `value_text` (D-M04-9), `cik` (B.7); signal writer; `filing_status`, category carried yearly (D-M04-36) | ~37 R1 + 2 WDC | < 1 min |
| 1b Capex, trends | capex tags (D-M04-3; NVDA FY2013–21 extension from instances); `capex_split` (D-M04-6); ROIC; trend rows (D-M04-11); guidance record (D-M04-10) | ~18 | < 1 min |
| 1c Profile | model tags (D-M04-8); stage, 15 setup items (D-M04-7, -12); ranked SIC peer shortlist, active = 10-K/20-F/40-F (D-M04-4) | ≤ 90 browse pages (3674 = 6) + 2–4 frames | ~1 min |
| 2 Peers | peer facts (B.9); offsets (D-M04-5); small-n stats; peer z | 40–50 companyfacts, 116–170 MB (estimate) | ~1 min |
| 3 Restatements, events | 8-K triggers (D-M04-37); walk (D-M04-16); dei flag; ≤ 35 old filings (D-M04-15) and 2 prior 10-Ks each (D-M04-17), stored for Part 6; non-reliance (D-M04-21) | ~26 R1 + ≤ 35 + ≤ 28 + 8 ≈ 97 | 1–2 min |
| 4a Gate numbers | runway, wall (D-M04-32, -33); `distress_score` (-31); input age, not applicable (-35, -36); review below 6 (-38); debt and `fcf_burn` rows (-29, -39) | ~24 (Rivian, Invitae) | < 1 min |
| 4b Gate text | going-concern and covenant classes, EFTS history baseline (D-M04-34); undrawn-credit finder | ~200 | 2–3 min |
| 5 Dilution | issuance and de-SPAC guard (D-M04-22); bands, SIC 6770 out (-23); 424B fee exhibits (-24); `financing_pressure` (-25…-28); overhang; lock-ups | 4 frames + 5 EFTS + ~250 | 1–2 min |
| 6 Earnings quality | M/F scores, accruals (D-M04-14, -20); estimate bands (-17, -18); `special_items` (-19) | ~10 | < 1 min |
| 7a Units data | `fact_dim` (D-M04-42); Tesla DS2 extractor; EX-99.2; RIVN; Invitae EX-99.1 | ~300; ~0.5 GB downloaded | 2–3 min |
| 7b R12, customers | D-M04-40, -41, -43…-50 | ~6 | < 1 min |
| 8a CvD, tab | grid and scores per Round 6; Red Flag 1 row (D-M04-30); M04 tab | 0 | < 1 min |
| 8b Calibration | backtest on owner labels (B.6); episode prices (B.4) | ~1,750 concept or ~70 companyfacts (B.9a); Tiingo ≤ 34 | 6–7 min (B.9a ~1) |
| **Total** | | **~2,850; ~1,170 under B.9a** | |

**Peer and episode storage** (40–50 peers + ~17 episode companies):

| Option | Requests | engine.db (352 MB now) |
|---|---|---|
| B.9a companyfacts, M04 tags kept | ~70 (~200–240 MB downloaded) | ≤ ~0.3 GB more (estimate) |
| B.9b companyconcept per tag | ~1,750 | similar rows; 30–60 MB files |
| B.9c full companyfacts rows | ~70 | +1.0–1.25 GB for peers alone |

Reading: every check is minutes; only 4b, 7a and 8b pass two. Boeing regression: FY2019 runway (10,030 + 6,400) ÷ ~2,750–2,785 = 5.9 quarters, fail; Q2 2024 5.5, fail; the wall passes in both.

## All cases
- **Runs:** logon-only (1); killed at 3 h, resumable (2); lock contention (3); SEC 429 or block (4); Tiingo cap (5).
- **Findings:** baselines, 101 walk steps and EFTS history (6); new wording (7); calibration → High review (20); stage unconfirmed → both flag sets, uncounted.
- **Companies:** fixtures (8); recycled BBBY, RAD, SHLD, uncovered J.C. Penney, bars past cancellation (RADCQ, NVTAQ) (9); GFS `ifrs-full`, 20-F peers (10); ETV (11); MSTR (12); predecessor CIKs, INFQ keyed on period end, its legacy-share pair `not_meaningful` (13); 21 of 41 424Bs without fee exhibit (14); extension-only tags (NVDA, GE) (21); 95 SIC-6770 filers ≥ $75M float (22); category carried (Invitae FY2022 $569.8M large accelerated, FY2023 accelerated) (23); recast first-filed values (Rite Aid FY2017 32,845 → 22,928) (24).
- **Process:** answer shrinks a part (15); new package (16); branch switched (17); DB growth (18, B.9); new filings mid-check (19); peers confirmed between 1c and 2; stale prices (SB.5); Round 6 unanswered at 8a (25).

Complete for the 13 parts once B.9 is answered. Unmeasured: owner bandwidth, Gemini spend (D-UI-11), rows per peer (Part 2 check).

## Suggestions
SB.1–SB.15 as before, except:
- SB.1 S-new IDs → S122 onward; open `M04_BUILD_LOG.md`; update the DESIGN code map.
- SB.3 Parts 1a–8b; one branch each.
- SB.6 Add the Part 8 set (~200 files under B.9b, one trimmed file per company under B.9a), NVDA instances (1b), GE FY2016 tags (6), Invitae EX-99.1 (7a).
- SB.8 Migrations from 0029; D13 and M00_STORAGE gain `value_text` and `cik`; `fact_dim` in 7a.
- SB.9 Add `m04_dilution`, `m04_overhang` (MSTR baseline ~10–11 with STRE), `m04_margin_cause`, `m04_estimate`; `m04_peer` only from the shortlist.
- SB.14 Round 3's 3.8 and 3.9 are D-M04-29 (4a) and D-M04-30 (8a).
- **SB.16 (new)** Files over ~2 MB (instances, 424Bs, 10-Ks) are parsed, then dropped from http_cache; rows and passages stay.
- **SB.17 (new)** Open re-probes ride on their part: S1 (1c, 6 requests), S6 and S7 (5, 3–5), S14 (7b, 1–2), S17 and T2 (8b, 1 + 4–6 Tiingo).
- **SB.18 (new)** Probe regression cases: Boeing 5.9 and 5.5 fail; BA Z 1.53 a `distress_score` warning, GFS 2.07 no `m04_score_gap`; Invitae R12 at 2020Q1; NVDA out of peer capex in every year; GE alias for GE only, never `CommodityContractAssetNoncurrent`.

## Check flags
- 1c's "~5 pages + ~50 candidates" was low: SIC 3674 lists 505, 82 active on 10-K only → ranked shortlist, cap per SIC.
- Part 2's 150–185 MB counted downloads only → B.9.
- Part 3 R1: 48 10-Ks since 2023, less 13 before the line, less ~9 read in 1a ≈ 26 (recount at build).
- The old brief queued INFQ's "substantial doubt"; it reads "alleviated", period ending 2025-12-31, before the close → excluded (D-M04-34).
- R3 case 12 ("GOOG 424Bs are debt") is wrong: 4 equity 424B5s in June 2026.
- Invitae's EX-99.1 pass took 37 requests, not ~25.

## Gaps
**Closed by the probe:** DB, cache and document sizes; 2023 10-Ks; Tiingo delisted coverage; fee-exhibit rate (~1.5 requests a filing); EFTS SIC path.
**Still open:** rows per peer; S1 with 20-F/40-F; stale bars and BTU/CHK splices; Rite Aid "last 10-K" row; S6, S7, S14 values; Round 6 answers.

## Questions
B.1 Run script and lock
- (a) (recommended) One `run_financials.py`: subcommand per part, `--no-sec`, lock via `run_script`, log of requests, MB and seconds per fetch type. Why: every part reads `fact`. Gets wrong: one larger script.
- (b) One script per part. Gets wrong: 13 copies of lock and log code.
- (c) Pytest live tests only. Gets wrong: no walk report or gate printout to read.

B.2 What runs in the logon refresh
- (a) (recommended) Per-new-filing work only: R1 for annual covers and multi-class 10-Qs (~30 a year), peer companyfacts on a new peer filing (160–200), instances (~70), EX-99.2 (≤ 60), fee exhibits (~30), frames (2) ≈ 350–390 a year; finders run on stored text. Heaviest day ~40 requests, under a minute. Why: adds seconds to 1.5–6.7 min runs. Gets wrong: history exists only after the owner's backfill.
- (b) Backfill on first sight. Gets wrong: 8b's requests or 7a's ~0.5 GB run unattended in the owner's session.
- (c) Weekly owner update. Gets wrong: a 4.02 or 1.03 8-K waits a week while M01 reads the old gate.

B.3 Review order and baselines (narrowed: cap 5 accepted in Round 4; EFTS history is a baseline by D-M04-34)
- (a) (recommended) Order: survival; CvD AMBIGUOUS and stage changes; events; restatement; dilution; margin, customer, unit KPI; estimate and M-score. Baselines except items filed in the last 12 months and a current gate fail or incomplete. Setup batch (15 stages, peer shortlists) outside the cap, before Part 3. Why: blocking items first; steady state 0.5–1.1 a week. Gets wrong: ~23 items a week when all queues are full.
- (d) Pack draft, all baselined, AMBIGUOUS last. Gets wrong: AMBIGUOUS blocks M01 tranches yet waits; a fresh hit is never queued.
- (b), (c) settled by the cap of 5.

B.4 Delisted and recycled names (changed by the probe)
- (a) (recommended) Use a Tiingo symbol only when meta name and date range match the SEC company: BBBYQ, RADCQ, NVTAQ, SHLDQ, RSH/RSHCQ, FIT, BTUUQ, GPRO; bars stored under that symbol; last real trade found first; BTU and CHK checked for splices; J.C. Penney "missing: no prices". ≤ 34 requests. Why: BBBY, RAD, SHLD are recycled. Gets wrong: J.C. Penney loses price checks.
- (b) Drop delisted episodes. Gets wrong: calibration loses Invitae, Bed Bath & Beyond, Rite Aid, Sears, RadioShack.
- (c) Buy delisted data. Gets wrong: breaks S2.

B.5 Outline financial rows — settled by D-M04-11.

B.6 Red-flag labels (narrowed by D-M04-45: information until ≥ 20 owner-labelled episodes)
- (a) (recommended) Owner blind-labels red flags on Round 6's episodes plus GE, Invitae, RadioShack, Sears, Rivian, MSTR, Target, Tesla (controls Lockheed, Alphabet) during Parts 3–7; weights at the High review after 8b. Why: gives "until" an end in one session. Gets wrong: 20–30 cases is small.
- (b) No schedule. Gets wrong: counted flags may never carry weight.
- (c) Weight now — settled out by D-M04-45.

B.7 CIK on signal rows
- (a) (recommended) `cik` on `signal` for all modules, in the `value_text` migration; ticker for display; D13 gains `cik`. Why: three recycled tickers (probe T2); that migration touches every module anyway. Gets wrong: backfills other modules' rows.
- (b) M04 only. Gets wrong: modules key one company differently.
- (c) None. Gets wrong: old Bed Bath & Beyond and Beyond, Inc. share BBBY rows.

B.8 R1 history depth — settled by D-M04-2.

B.9 Peer and episode fact storage (new; Parts 2, 8b)
- (a) (recommended) One companyfacts download per company, keep only M04's tags, drop the cache file. Why: per-tag values in 1/25 of the requests and a fraction of full rows. Gets wrong: a tag added later needs a re-download (~1 min).
- (b) Companyconcept per tag (Round 6 S6.3). Gets wrong: ~1,750 requests, 6–7 min, for the same values.
- (c) Full rows. Gets wrong: engine.db grows to ~1.4–1.6 GB; slower backups and as-of reads.
