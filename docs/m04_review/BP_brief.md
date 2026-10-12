# M04 Build parts (proposal) — brief

**Decides:** how M04 is built: eight parts with one owner live check each, one run script and lock (B.1), what the logon refresh fetches (B.2), review caps and first-run baselines (B.3), delisted and recycled names (B.4). New B.5–B.8 cover checker gaps. The pack numbers these questions B.1–B.4, so the brief keeps B.n.
**Outline items:** none directly; the parts are where "Analyze the financials" 1–4 and 6 (lines 65–74), Red Flags 1–6 (78–83) and Capex 3–5 (92–95) get built. Also D-M02-12 (PC off overnight), D8, D10, D13, D24, D6.

## What the research says
- M02 pattern: one conversation and one owner live check per part; every log found new wording, so 2–4 live rounds, kept cheap by local re-runs (140 requests in 47 s); screens mocked up on real data first (M02_BUILD_LOG, D-UI-4).
- The rate limiter is per process: two SEC processes at 5/s reach SEC's 10/s (S121). `run_script` holds `data/refresh.lock` (D-M02-51).
- Time: logon task stops at 3 h (D-M02-12, S120); last refreshes took 1.5–6.7 min; SEC pace about 265 requests a minute (D-SEC-18); 48 EFTS queries took 43 s (S-new-bp-4); M02 read 113 instances in about 1 min.
- Sizes: companyfacts 0.2–6.1 MB per company, median 3.7 MB; companyconcept about 29 KB per tag (S-new-bp-3, S-new-1).
- Surprises: `ffd` fee facts exist only from 2026-04-08 and not for MSTR; GFS files 6-K/20-F in `ifrs-full`; MSTR's SIC is 6199; history sits under other CIKs (Google Inc., Marvell Technology Group, INFQ's SPAC shell) (S-new-bp-3). The `signal` key uses ticker, and BBBY was recycled on 2025-08-29 (S-new-bp-2); Tiingo keeps delisted data only for tickers not yet recycled (S-new-bp-1).
- One R1 cover page gives both per-class shares (Part 1) and the error-correction flag (Part 3) (S-new-bp-5).

## Worked example
**Live-check budget, corrected** (pack 3247–3258; Part 8 rewritten from Round 6 S6.3; time at 265 a minute):

| Part | Pack | Corrected | Time |
|---|---|---|---|
| 1 Data foundation | 162 R1 + 2 + 17 optional | ~40 + 17 optional (B.8a) | < 1 min |
| 2 Peers | 90 browse + 40–50 companyfacts | + ~1 per candidate; two owner runs (propose, fetch) | 1–2 min |
| 3 Flags | 36 R1 + 44 + 8 | ~24 R1 + 44 + 8 | ~1 min |
| 4–7 | 215 / 220 / 16 / 249 | unchanged | 1–2 min each |
| 8 CvD | 50–80 companyfacts (185–300 MB); Tiingo ≤ 22 | **~1,750 companyconcept** (70 × 25 tags), 30–60 MB in `data/`, ~200 fixture files; Tiingo ≤ 34 | **8–9 min** |
| **Total** | 1,130–1,190 | **~2,800–2,900** (~2,700 with B.8a) | ~11 min pacing |

**First-run review queue** (baselines: 101 walk steps, 136 EFTS filing hits):

| Option | First-run queue | INFQ FY2025 10-K "substantial doubt" (filed 2026, unread) | CvD AMBIGUOUS |
|---|---|---|---|
| B.3a revised | hits from the last 12 months + gate fail/incomplete | queued, priority 1 | priority 2 |
| B.3d pack draft | none | baseline, never queued | priority 7 |
| B.3c queue all | 237 items ≈ 47 weeks at 5/week | buried | buried |

Reading: Round 6's plan more than doubles the one-off total, yet it is still minutes. The draft baseline rule would file away the watchlist's only current going-concern hit.

## All cases
- **Runs:** logon-only (1); killed at 3 h, resumable (2); lock contention (3); SEC 429/block, budget stop (4); Tiingo cap (5).
- **Findings:** first-run baseline (6) with the B.3a exception; new wording, `--no-sec` re-runs (7); calibration → High review (20); red flags with no labelled set (new, B.6).
- **Companies:** non-watchlist fixtures (8); delisted and recycled (9); GFS 6-K (10); fund without XBRL (11); misleading SIC (12); predecessor CIK or SPAC shell (13); missing fee facts (14).
- **Process:** an answer shrinks a part (15); new package (16); branch switched (17); DB growth (18); new filings mid-check (19); owner confirmation mid-check in Part 2 (new); price rows computed before the day's prices (new).

Complete once B.5–B.8 are answered. Unmeasured: owner bandwidth, engine.db size, Gemini spend (estimated before each call, D-UI-11).

## Suggestions
SB.1–SB.12 as in the pack, with these changes:
- SB.1 Map all 131 S-new IDs to S122 onward, merging 17 duplicate URLs; update the DESIGN code map.
- SB.3 Part 2 has two owner runs.
- SB.5 Price-dependent rows (Z's X4, overreaction gauge) run after the price step or show the close date used.
- SB.6 Add the Part 8 fixture set (~200 files, about 6 MB).
- SB.8 Part 1 lists DS12–DS17 and migrations from 0029 (0027–0028 are taken).
- SB.9 Review-kind table merged from Rounds 2, 4, 5: add `m04_gc_text`, `m04_covenant`, `m04_score_gap`, `m04_customer`, `m04_unit_kpi`, `m04_mscore`; `m04_restate` at 2–3 a year.
- SB.13 (new) Approved items are committed, not "if adopted": A2 `capex_split` and ROIC concepts in Part 1; the D-M04-1 customer row in Parts 1, 3, 7, 8 per 5.5 (a deferral goes in the change table).
- SB.14 (new) Round 3's 3.8 and 3.9 rows (debt ÷ revenue; burn without share gains), if adopted, land in Parts 4 and 8.
- SB.15 (new) The Part 2 setup page shows stage and model tags read-only, in the 1.7 vocabulary, edited in the toml (1.7a).

## Check flags
- Part 8 row never updated from Round 6 S6.3; S6.3's "4 minutes at 8 per second" breaks the 5/s pace → about 6–7 min.
- Outline Analyze 1–4 and Red Flag 4 have no build home → B.5.
- Red flags weightless "until a labelled set exists", which nothing builds → B.6.
- Draft B.3 put CvD AMBIGUOUS (blocks M01 tranches) and stage (routes R2) last, and baselined current filings → B.3a revised.
- Part 1 fetches 4× the R1 pages 1.1a recommends and omits SPCX → B.8.
- Part 3's dei source and fetch cap differ from 2.2a (44 vs ≤ 35 filings) → follow the 2.2 answer.
- Overdue state: use Round 6's `filing_status`; walk count 101 vs Round 2's 102 → recount at Part 3.
- Logon table counts an R1 page per 10-Q; only multi-class filers need them → ~30 a year, not 70.

## Gaps
**Closed now**
- GE's `UnbilledContractsReceivable` is the line "Contract assets (Note 9)": 28,861 (2017), 25,162 (2016), matching the fixture; about 23% is not unbilled revenue (GE 2017 Annual Report, company-hosted). Note for Round 2.
- dei flag: staff did not expect the checkboxes before a recovery policy was required, about 2023-12-01 (C&DI 121H.01 via TheCorporateCounsel.net, secondary). Missing before then means "not required", never "false". Part 3 needs about 24 R1 pages, not 36; probe A confirms the 2023 filing dates.
- Merged review volume: 25–55 items a year (0.5–1.1 a week).
- No source-ID collisions; three citation fixes remain for Rounds 2, 3 and 6 (Round 2 line 736; HXZ at 674 vs 1064; Round 6's 151/213).
- The SEC client requests gzip, so the pack's MB and minutes are upper bounds.

**Needs the owner's probe**
- Probe A, local read-only, 0 requests (script in `BP_gaps.md`): DB sizes, fact rows per CIK, cached document sizes, 2023 10-K dates → `logs\m04_local_probe.txt`.
- Probe B, Tiingo metadata, 6–12 requests: NVTA, RAD, JCP, SHLD, FIT, BBBY. Needs a small new script; `run_prices.py --symbols` would store a recycled ticker's bars. Can wait for Part 8.
- Peer counts: set by the owner's Part 2 confirmations.

## Questions
**B.1 Run script and lock**
- (a) (recommended) One `run_financials.py`: a subcommand per part, `--no-sec`, lock via `run_script`, log of requests, MB and seconds per fetch type. Why: every part reads `fact`. Gets wrong: one larger script.
- (b) One script per part. Gets wrong: eight copies of lock and log code; the R1 reader split across two.
- (c) Pytest live tests only. Gets wrong: no walk report or gate printout to read.

**B.2 What runs in the logon refresh**
- (a) (recommended) Per-new-filing work only (R1, peer companyfacts on a new 10-K/10-Q, instance, EX-99.2, missing fee exhibits, local finders): ~340–420 requests a year, ~40 on a heavy day; backfills from B.1's script. Why: seconds added to 1.5–6.7 min runs. Gets wrong: history exists only after the owner's backfill.
- (b) Backfill on first sight. Gets wrong: Part 8's ~1,750 requests run unattended; new wording lands in a background log; a kill leaves half a baseline.
- (c) Weekly owner update only. Gets wrong: a 4.02 8-K waits a week while M01 reads the old gate.

**B.3 Review caps and baselines** (recommendation changed: order and baseline exception)
- (a) (recommended) M04 cap of 5 a week (starting value), Round 5's per-kind caps inside it. Order: survival; CvD AMBIGUOUS and stage; events; restatement; dilution; margin, customer, unit KPI; estimate and M-score. First runs are baselines except hits filed in the last 12 months and gate fail or incomplete. Why: blocking items first; steady state 0.5–1.1 a week. Gets wrong: full queues mean ~23 items a week (M02 10, guidance ~8, M04 5).
- (b) Share M02's cap of 10. Gets wrong: survival items compete with M02's overflow of 104.
- (c) Queue everything. Gets wrong: 237 items, ~47 weeks.
- (d) Pack draft. Gets wrong: INFQ's hit never queued; AMBIGUOUS waits behind information-only items.

**B.4 Delisted and recycled names** (counts corrected)
- (a) (recommended) Probe Tiingo metadata for ≤ 17 episode companies (34 requests), match by date range; no match → EDGAR-only labels, "missing: no prices". Why: BBBY was recycled. Gets wrong: those names lose price checks.
- (b) Drop them. Gets wrong: calibration loses Invitae, Bed Bath & Beyond, Rite Aid, J.C. Penney.
- (c) Buy delisted data (EODHD). Gets wrong: breaks S2.

**B.5 Outline financial rows** (new; answer once if Round 1 asks too)
- (a) (recommended) Part 1 builds information rows: revenue YoY and 3-yr CAGR; FCF (CFO − total capex) and its growth, with FCF after SBC and FCF margin; gross-margin change (pp, 4 quarters and 3 years); opex vs revenue growth. Own history and peer z, stage-aware, method-tagged; Part 8 proposes votes. Why: outline 65–70 and 81 have no home. Gets wrong: the "golden indicator" is unweighted until Part 8.
- (b) Signals now on starting values (illustrative: FCF growth > 0 three years). Gets wrong: MU at its FY2023 trough votes against CvD.
- (c) Raw series only. Gets wrong: Analyze 1–4 never computed.

**B.6 Red flags before a labelled set** (new)
- (a) (recommended) Information-only, plus a Part 8 step: owner blind-labels GE, Invitae, RadioShack, Sears, Rivian, MSTR, Target, Tesla (controls Lockheed, Alphabet) during Parts 3–7; weights proposed at the High review. Why: "until" gets an end. Gets wrong: ten cases is small.
- (b) No scheduled labelling. Gets wrong: "avoid" flags may never carry weight.
- (c) Weight now. Gets wrong: unsourced thresholds vote.

**B.7 CIK on signal rows** (new; or under 1.8)
- (a) (recommended) `cik` on `signal` for all modules, in the key with module, signal, timeframe, as_of; ticker for display; D13 gains `cik`. Why: recycled tickers. Gets wrong: migration touches other modules' rows.
- (b) M04 only. Gets wrong: modules key the same company differently.
- (c) None. Gets wrong: old Bed Bath & Beyond and Beyond, Inc. share BBBY rows.

**B.8 R1 history depth** (new; sub-option of 1.1)
- (a) (recommended) Per 1.1a: last 3 years for GOOG, META, MSTR plus SPCX (~37 + SPCX); older from basic weighted average, labelled. Why: avoids the unverified pre-2011 format. Gets wrong: older per-class history approximated.
- (b) Full history, 162 pages. Gets wrong: unverified pre-2011 pages; MSTR 2011 counts predate its split.
