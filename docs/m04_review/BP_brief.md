# M04 Build parts (proposal) — brief

Updated for Round 1 answers (D-M04-2…13): Part 1 split into 1a data, 1b capex and trends, 1c tags, stage and peer proposals; B.5 and B.8 settled (D-M04-11, D-M04-2); one-off total ~2,700 requests; first stages form a 15-item setup batch (D-M04-12); gate routing per D-M04-13.

**Decides:** ten parts (1a–1c, 2–8), one owner live check each, and questions B.1–B.4, B.6, B.7 (B.5, B.8 settled).
**Outline items:** the parts build Analyze 1–4 and 6 (lines 65–74), Red Flags 1–6 (78–83), Capex 3–5 (92–95). Also D-M02-12, D6, D8, D10, D13 (extended by D-M04-9), D24.

## What the research says
- M02: one conversation and one owner live check per part; 2–4 live rounds each, kept cheap by `--no-sec` re-runs; screens mocked up first (D-UI-4).
- Limiter is per process: two SEC processes reach 10/s (S121); `run_script` holds `data/refresh.lock`. Logon task stops at 3 h; refreshes take 1.5–6.7 min; SEC pace ~265 a minute.
- Companyfacts 0.2–6.1 MB per company; companyconcept ~29 KB per tag. One R1 page gives per-class shares (1a) and the error-correction flag (3).
- Surprises: `ffd` fee facts only from 2026-04-08, none for MSTR; GFS files 6-K in `ifrs-full`; MSTR's SIC 6199; history under other CIKs (Google Inc., Marvell Technology Group, INFQ's SPAC); BBBY recycled 2025-08-29; Tiingo keeps delisted data only for unrecycled tickers (S-new-bp-1…5).

## Worked example
**Parts and live-check budget** (pack 3247–3258 and 3326–3337, corrected; Part 8 from Round 6 S6.3; estimates marked):

| Part | Contents | SEC requests | Time |
|---|---|---|---|
| 1a Data foundation | `facts_as_of`, form list (SB.11); predecessor CIKs; share series, `sbc`, R1 cover counts, implied float (D-M04-2); migration 0029 (`value_text` D-M04-9, `cik` B.7); signal writer; `filing_status` | ~40 R1 (GOOG, META, MSTR, SPCX) + 2 WDC; +17 companyfacts if the parser changes | < 1 min |
| 1b Capex and trends | capex display with "≈ broader tag" marker, own-history and peer tag rules (D-M04-3); `capex_split` (D-M04-6); ROIC concepts; trend rows on own history (D-M04-11); guidance outcomes in shared `guidance/` (D-M04-10) | 0 (local report) | < 1 min |
| 1c Company profile | `config/company_models.toml` loader (D-M04-8); stage (D-M04-7) and 15 `m04_stage` setup items (D-M04-12); SIC peer proposals as `m04_peer` items (D-M04-4) | ~5 browse-by-SIC pages + ~1 per candidate (~50, estimate) | < 1 min |
| 2 Peers | confirmed peers' facts; offsets ±45/±40 d (D-M04-5); small-n stats; peer z for trend rows; 53-week flags | 40–50 companyfacts, ~150–185 MB (estimate) | 1–2 min |
| 3 Flags | events, restatement walk, dei flag from R1 | ~24 R1 + 44 + 8 | ~1 min |
| 4 Gate | runway, maturity wall, Z, distress finders; liquidity-only gate for `asset_treasury` and `reit` only (D-M04-13) | 215 | 1–2 min |
| 5 Dilution | issuance, 424Bs; `issuance_funded` keeps the normal gate, `financing_pressure` warns in the warn band or on failure (D-M04-13) | 220 | ~1 min |
| 6 / 7 | earnings quality / unit economics | 16 / 249 | 1–2 min each |
| 8 CvD | grid, calibration, proposed trend-row votes (D-M04-11) | ~1,750 companyconcept (70 × 25 tags), 30–60 MB, ~200 fixture files; Tiingo ≤ 34 | 8–9 min |
| **Total** | | **~2,700** (pack 1,130–1,190) | ~10–11 min |

**First-run review queue** (baselines: 101 walk steps, 136 EFTS filing hits):

| Option | Weekly queue at first run | Setup batch | INFQ FY2025 10-K "substantial doubt" | CvD AMBIGUOUS, stage changes |
|---|---|---|---|---|
| B.3a revised | hits filed in the last 12 months + gate fail or incomplete | 15 first stages (D-M04-12), peer sets (D-M04-4) | queued, priority 1; period before 2026-02-13, so read under `spac_shell` (D-M04-8) | priority 2 |
| B.3d pack draft | none | peer sets | baseline, never queued | priority 7 |
| B.3c queue all | 237 items ≈ 47 weeks at 5 a week | — | buried | buried |

Reading: Part 8 more than doubles the one-off total, yet every check is minutes. INFQ has under 3 operating fiscal years, so its stage is a review item; both flag sets show "stage unconfirmed", uncounted (D-M04-7).

## All cases
- **Runs:** logon-only (1); killed at 3 h (2); lock contention (3); SEC 429 or block (4); Tiingo cap (5).
- **Findings:** first-run baseline (6, B.3a exception); new wording (7); calibration → High review (20); red flags unlabelled (B.6); setup batch unconfirmed at Part 3 → "stage unconfirmed", uncounted (D-M04-7).
- **Companies:** fixtures (8); delisted, recycled (9); GFS 6-K (10); ETV `fund` (11); MSTR `asset_treasury` over SIC (12); predecessor CIK, INFQ `spac_shell` to 2026-02-13 (13); missing fee facts (14).
- **Process:** answer shrinks a part (15); new package (16); branch switched (17); DB growth (18); new filings mid-check (19); peers confirmed between 1c and 2; stale prices (SB.5).

Complete once B.6 and B.7 are answered. Unmeasured: owner bandwidth, engine.db size, Gemini spend (D-UI-11).

## Suggestions
SB.1–SB.12 as in the pack, with these changes:
- SB.1 Map the 131 S-new IDs to S122 onward (17 duplicate URLs merged); update the DESIGN code map.
- SB.3 Parts 1a–1c replace Part 1; Part 2 has one owner run.
- SB.5 Price-dependent rows (Z's X4, overreaction gauge) run after the price step or show the close date.
- SB.6 Add the Part 8 fixture set (~200 files, ~6 MB).
- SB.8 DS12–DS17; migrations from 0029; M00_STORAGE and D13 text gain `value_text` (D-M04-9).
- SB.9 Add kinds `m04_gc_text`, `m04_covenant`, `m04_score_gap`, `m04_customer`, `m04_unit_kpi`, `m04_mscore`, `m04_peer` (setup); `m04_restate` 2–3 a year; `m04_stage` 15 once, then 4–5 a year (D-M04-12).
- SB.10 Enum encoding settled by D-M04-9; CIK is B.7.
- SB.13 Committed, not "if adopted": `capex_split` (D-M04-6), ROIC, trend rows (D-M04-11) and guidance record (D-M04-10, M11 scores R19) in 1b; float shares (D-M04-2) in 1a; D-M04-1 customer row in 1a, 3, 7, 8 per 5.5.
- SB.14 Round 3's 3.8 and 3.9 rows, if adopted, land in Parts 4 and 8.
- SB.15 The setup page shows D-M04-8 tags read-only; edits go to the toml.

## Check flags
- Part 1 after Round 1 holds ten pieces, too many for one conversation → split 1a–1c.
- Part 8 row never updated from S6.3, whose "4 minutes at 8 per second" breaks the 5/s pace → ~6–7 min SEC time.
- Pack Part 2's `lifecycle_stage` (5.1), Round 3's `asset_holding`, and the liquidity-only gate for issuance-funded names (3.4a, Round 6 change 19) are superseded by D-M04-7, -8 and -13 → Parts 1c, 4, 5 above.
- Red flags weightless "until a labelled set exists", which nothing builds → B.6.
- Draft B.3 put AMBIGUOUS (blocks M01 tranches) and stage last and baselined current filings → B.3a revised.
- INFQ's "substantial doubt" sits in a SPAC-period filing; possibly SPAC deadline wording (inference, unread). B.3a still queues it once.
- Part 3's dei fetch cap differs from 2.2a (44 vs ≤ 35) → follow 2.2. Use Round 6's `filing_status`; recount walk steps (101 vs 102) at Part 3.
- Logon R1: per filing only for 4 multi-class filers, plus annual covers (D-M04-2) → ~30 a year, not 70.
- Settled by Round 1: Analyze 1–4 home (D-M04-11); 4× R1 pages (D-M04-2).

## Gaps
**Closed now**
- GE's `UnbilledContractsReceivable` = "Contract assets (Note 9)": 28,861 (2017), 25,162 (2016); ~23% is not unbilled revenue. Note for Round 2.
- dei checkboxes not expected before ~2023-12-01 (C&DI 121H.01, secondary): missing then means "not required"; Part 3 needs ~24 R1 pages.
- Review volume 25–55 a year (0.5–1.1 a week), stage included. Three citation fixes remain (Rounds 2, 3, 6). Gzip makes MB and minutes upper bounds.

**Needs the owner's probe**
- Probe A, local, 0 requests (`BP_gaps.md`): DB sizes, fact rows per CIK, document sizes, 2023 10-K dates.
- Probe B, Tiingo metadata, 6–12 requests (NVTA, RAD, JCP, SHLD, FIT, BBBY); needs a small script; can wait for Part 8.
- Peer counts: set by 1c proposals and owner confirmations.

## Questions
B.1 Run script and lock
- (a) (recommended) One `run_financials.py`: a subcommand per part, `--no-sec`, lock via `run_script`, log of requests, MB and seconds per fetch type. Why: every part reads `fact`. Gets wrong: one larger script.
- (b) One script per part. Gets wrong: ten copies of lock and log code.
- (c) Pytest live tests only. Gets wrong: no walk report or gate printout to read.

B.2 What runs in the logon refresh
- (a) (recommended) Per-new-filing work only (R1, peer companyfacts on a new 10-K/10-Q, instance, EX-99.2, missing fee exhibits; stage, trends and finders local): ~340–380 requests a year, ~40 on a heavy day; backfills from B.1's script. Why: adds seconds to 1.5–6.7 min runs. Gets wrong: history exists only after the owner's backfill.
- (b) Backfill on first sight. Gets wrong: Part 8's ~1,750 requests run unattended; new wording lands in a background log; a kill leaves half a baseline.
- (c) Weekly owner update only. Gets wrong: a 4.02 8-K waits a week while M01 reads the old gate.

B.3 Review caps and baselines (recommendation changed: order, baseline exception, setup batch)
- (a) (recommended) M04 cap of 5 a week (starting value), Round 5's per-kind caps inside it. Order: survival; CvD AMBIGUOUS and stage changes; events; restatement; dilution; margin, customer, unit KPI; estimate and M-score. First runs are baselines except hits filed in the last 12 months and gate fail or incomplete. First stages (15, D-M04-12) and peer sets form a setup batch outside the cap, due before Part 3. Why: blocking items first; steady state 0.5–1.1 a week. Gets wrong: full queues mean ~23 items a week (M02 10, guidance ~8, M04 5).
- (b) Share M02's cap of 10. Gets wrong: survival items compete with M02's overflow of 104.
- (c) Queue everything. Gets wrong: 237 items, ~47 weeks.
- (d) Pack draft. Gets wrong: INFQ's hit never queued; AMBIGUOUS waits behind information-only items.

B.4 Delisted and recycled names (counts corrected)
- (a) (recommended) Probe Tiingo for ≤ 17 episode companies (34 requests), match by date range; no match → EDGAR-only labels, "missing: no prices" row (D-M04-9). Why: BBBY was recycled. Gets wrong: those names lose price checks.
- (b) Drop them. Gets wrong: calibration loses Invitae, Bed Bath & Beyond, Rite Aid, J.C. Penney.
- (c) Buy delisted data (EODHD). Gets wrong: breaks S2.

B.5 Outline financial rows — settled by D-M04-11 (1.10a): information rows built in 1b (own history) and 2 (peer z); votes proposed at Part 8.

B.6 Red flags before a labelled set
- (a) (recommended) Information-only, plus a Part 8 step: owner blind-labels GE, Invitae, RadioShack, Sears, Rivian, MSTR, Target, Tesla (controls Lockheed, Alphabet) during Parts 3–7; weights at the High review. Why: "until" gets an end. Gets wrong: ten cases is small.
- (b) No scheduled labelling. Gets wrong: "avoid" flags may never carry weight.
- (c) Weight now. Gets wrong: unsourced thresholds vote.

B.7 CIK on signal rows
- (a) (recommended) `cik` on `signal` for all modules, in the `value_text` migration (D-M04-9); keyed with module, signal, timeframe, as_of; ticker for display; D13 gains `cik`. Why: recycled tickers; that migration already touches every module. Gets wrong: backfills other modules' rows.
- (b) M04 only. Gets wrong: modules key one company differently under a shared record.
- (c) None. Gets wrong: old Bed Bath & Beyond and Beyond, Inc. share BBBY rows.

B.8 R1 history depth — settled by D-M04-2 (1.1a): 3 years of R1 for GOOG, META, MSTR, SPCX (~40 pages); older history from basic weighted average, labelled.
