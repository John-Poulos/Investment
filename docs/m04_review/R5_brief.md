# M04 Round 5 — Unit economics and margin collapse (stage-aware, R2) — brief

Updated for Round 1 answers (D-M04-2…13): 5.1 settled (D-M04-7, D-M04-12); 5.2e dropped, R12 runs at every stage (D-M04-7); 5.8 routes unconfirmed stages per D-M04-7; S5.9 uses `value_text` and "missing" rows (D-M04-9); 5.10 narrowed to the basis of D-M04-11's trend rows; `m04_stage` 15 at first run, on the setup page (D-M04-12).

**Decides:** the R12 trigger, the cause and what it does (5.2, 5.3, 5.6, 5.7); unit-economics flags by stage (5.8, 5.9); the positive rows' basis (5.10); data reach (5.4); the D-M04-1 customer row (5.5, 5.11, 5.12).
**Outline:** Analyze 3, 4, 6 (l. 69, 70, 74–75); ALAB/MRVL margin expansion (l. 56); Red Flags 1, 3, 5 (l. 78, 80, 82). Approved: R2, R11, R12, D-M04-1, D-M04-7…11.

## What the research says
- Filings must state causes, price versus volume included (Reg S-K 303(b), S-new-49); every test case does (S-new-50, S-new-51, S-new-r5-4).
- Falling gross margin predicts lower earnings; evidence mixed (S-new-52). A margin falling while revenue rises needs a cause at any stage (sticky costs, S-new-54).
- Profitability reverts about 38% a year, except in decline (S-new-55/56). Young firms' unit cost should fall with cumulative output (S-new-57).
- Inventory ahead of sales predicts EPS for retailers only (S-new-53); the 15 pp gap is unsourced. Contribution margin is non-GAAP; credits carry no units (S-new-59).
- Customers are often anonymous (S16); concentration matters more when high (S45, HHI). RPO matters for contracted names only.

## Worked example
**R12 trigger options on real quarters** (S-new-r5-2/3/7; Invitae and Intel 2021 from Gaps)

| Case | Facts | 5.2a: 2 qtrs ≥ 3 pp, TTM rev up | 5.2b: 1 qtr ≥ 5 pp | 5.2d: (a) excl. stated items |
|---|---|---|---|---|
| Tesla | 2022Q4 −3.6, 2023Q1 −9.8 pp; TTM +38% | fires 2023Q1 | fires 2023Q1 | as (a) |
| Target | 2022Q1 −4.4, Q2 −8.9 pp; TTM +7.5% | fires Q2 2022 with instance read | fires Q2 2022 | as (a) |
| Invitae | 2019Q4 −8.8, 2020Q1 −10.4, 2020Q2 −40.7 pp; TTM +32% to +50% | **fires 2020Q1** | fires 2019Q4 | not computable |
| Intel 2021Q1 | −5.4 pp, TTM +2.6% | silent | **fires** | silent |
| Intel 2024Q3 | −27.5 pp (≈ −4.1 excl. stated $3.1B) | silent | **fires** | silent |
| Intel 2022Q1 | TTM −0.01% | no (CvD's case) | no | no |

5.2c (peer gap) is silent on shared squeezes and has no peers for Invitae or Rivian. 5.2a flags Invitae about 2.5 years before its FY2022 survival-gate failure.

**Unit economics and customers** (S-new-r5-4, S-new-47, S-new-r5-6, S-new-50, S-new-r5-8)

| Name | Units | Per unit | Reading |
|---|---|---|---|
| Invitae 2019→22 | 469k → 1,290k | GP $210 → $77; cost $252 → $323 | all young-firm flags; cause price/mix |
| Rivian auto FY2024→25 | 51,579 → 42,247 (−18%) | GP −$23.4k → −$10.2k | no per-unit flag; credits $299M vs GP $170M (Q4 2024); burning with falling units |
| Tesla 2022→23 | +38% | GP $13.4k → $7.4k | bridge: volume +$6.6B, price −$14.0B, cost +$3.2B; cause price |
| NVIDIA FY2025→26 | ≥10% customers 3 → 2 | at stake 34% → 36% (≈ $77.7B) | shorter list, no loss |

Stage (D-M04-7): Invitae and Rivian introduction; Tesla and Intel go to owner confirmation (D-M04-12), Intel from FY2023 as "growth with falling revenue". Open: a confirmed price cause gives no signal yet (5.6); Rivian, R11's case, gets no per-unit flag (5.9).

## All cases
| Group | Cases (pack numbers) |
|---|---|
| R12 fires, cause needed | 1 any stage; 6 volume bought with price; 16 two-level cause |
| R12 silent by design | 2 revenue and margin down (CvD); 3 knife-edge TTM; 4 one-quarter charge |
| Early warnings | 5 inventory ahead of sales; 12 production above deliveries |
| Young unit economics | 7 improving (Rivian); 8 not improving (Invitae); 9–11 GP from credits, ex-credit diverges, credit share not meaningful |
| Scope and data | 13–15 units missing, scope mismatch, category break; 17–25 zeros, recasts, restatements, no GP tag, definitions, late lines, contribution margin, waterfall sums |
| Stage and tags | 26–30 settled by D-M04-7/8: tag first (fund, financial, spac_shell → no rows); short history → review, both sets labelled, uncounted (INFQ after its 2026-02-13 closing) |
| Customers | 31–40 |
| **Added** | 41 quarter revenue falls while TTM rises (Invitae 2020Q2); 42 stated items equal the whole change (Invitae 2022, $68.6M); 43 burning with units falling (Rivian 2025); 44 per-unit decline at a growth or mature name (Tesla 2023); 45 cause names a competitor (no test case); 46 expansion that is reversion (Target FY2023 23.6% → 26.5%) |

**Completeness:** complete for the test names and the 15 operating watchlist names. Known omissions: segment collapse inside consolidated margin (needs 5.4a), channel inventory, churn, text-only backlog (BA, SPCX), FX from text, market share (Round 6).

## Suggestions
- **S5.1** *Changed:* stage per D-M04-7/12, tag first per D-M04-8; `fund`, `financial`, `spac_shell` get "missing: not applicable (<tag>)" rows; other tags run unchanged.
- **S5.2** R12 per 5.2; one `m04_margin_cause` item per episode; TTM revenue from `rev_yoy` (D-M04-11); 3 pp an unsourced starting value.
- **S5.3** Cause finder with a `competition` class (competitor wording, falling share, M06 challenger); stated items checked against the bridge, never added across levels.
- **S5.4** Stated items beside reported margin; they feed Round 2's recurrence count; EX-99.1 reconciliations quarterly.
- **S5.5–S5.8** `unit_metric` table (credits separate; 50% and 10% starting values); flag sets per 5.8, per-unit decline shown at every stage; `fact_dim` from instances, recasts flagged; contribution margins company-stated only.
- **S5.9** *Changed:* D-M04-9 encoding: `margin_cause`, `r12_episode`, `customer_signal` states in `value_text`, `value` NULL, stated $M in `method`; "missing: <reason>" rows (no unit metric, no peers); one row per timeframe; weakest-input grade (cause from a transcript → B). Rows also: `r12_warning`, `unit_gp_trend`, `unit_cost_vs_cumulative`, `rev_per_unit_vs_cost`, `production_gap`, `sga_vs_revenue`, `gm_delta_pp_ex_items`, `customer_hhi`.
- **S5.10–S5.13** Reversion prior shown ("not used" in decline); regression cases from the tables; comparability markers (Amazon, Target), peer gap on D-M04-5 offsets; RPO per 5.11, weight per 5.12, build part to be set.
- **S5.14** *Changed:* `m04_stage` 15 at first run on the setup page, then 4–5 a year (D-M04-12); `m04_margin_cause` under 1 a quarter; `m04_customer` 1–3 a quarter (cap 3 a week); `m04_unit_kpi` about 1 a year.
- **S5.15–S5.16** Calibration per 5.7; `run_m04.py` under `refresh.lock`, live check about 70–80 requests.

## Check flags
- Settled by Round 1: 5.1 duplicate, encoding, tag names, first-run stage volume, positive trend rows (D-M04-7…12).
- Answered by 5.6–5.12: outcome after a cause, information-only drift, growth mapping, Rivian/R11, Red Flag 1, RPO ratio, weighting.
- Invitae 2022's items sum to the whole change, hiding double counting. Fix: S5.3.

## Gaps
**Closed:** Intel 2021Q1 GM 60.6% → 55.2%, TTM +2.6% (intc.com). Invitae 5.2a fires 2020Q1 (2020Q2 if the secondary FY2018 figure is off). Microsoft's "approximately 45%" OpenAI share of RPO is from the FY26 Q2 call: grade B (D-M04-9), A if found in a filing. Tesla and Target state no cost items, so 5.2d = 5.2a. Tesla's 2023 Item 1.02 is a financing replacement.
**Open, no SEC:** Dickinson, Lev & Thiagarajan, Abarbanell & Bushee, Kesavan & Mani, Patatoukas primaries.
**Owner's probe** (`scripts/probe_m04_r5.py`, about 8 requests plus 11 optional): P1 NVTA revenue and cost FY2018–20 · P2 (optional) NVTA non-GAAP GP · P3 NVTA FY2022 per-unit text · P4 RIVN FY2025 credits · P5 two 8-K Item 1.02 texts. No-SEC query: 8-K 1.01/1.02/2.03 counts in `event`.

## Questions
**5.1** Settled by D-M04-7 and D-M04-12.

**5.2 R12 trigger**
- (a) (recommended) TTM revenue up and gross margin down ≥ 3 pp year over year in 2 straight quarters (reported; excluding stated items beside); closes after 2 non-qualifying quarters; every stage (D-M04-7). Why: fires on all three real squeezes, silent on Intel. Gets wrong: Target without 5.4a.
- (b) One quarter ≥ 5 pp. Gets wrong: Intel 2021Q1 and 2024Q3.
- (c) Peer gap only. Gets wrong: Invitae, Rivian (no peers).
- (d) (a) excluding stated items. Gets wrong: recurring "one-offs" always excluded.
- Old (e), mature and growth only: removed, D-M04-7 runs R12 at every stage.

**5.3 Who names the cause**
- (a) (recommended) Code tags sentences, owner confirms, Gemini on request. Why: D28. Gets wrong: management framing (the bridge check helps).
- (b) Arithmetic only. Gets wrong: Invitae amortization versus write-downs.
- (c) Gemini by default. Gets wrong: a paid request where code suffices.

**5.4 Unit KPIs, segments, customer axes**
- (a) (recommended) Tesla DS2 extractor, EX-99.2, RIVN tracked, instance reads into `fact_dim`. Why: Target fires on time. Gets wrong: about 180 backfill requests.
- (b) Bulk data sets. Gets wrong: Target and NVIDIA values arrive late.
- (c) Margins only. Gets wrong: NVIDIA 36%, Rivian scope.
- (d) EdgarTools first. Gets wrong: needs `uv add`.

**5.5 Customer signal**
- (a) (recommended) Engine proposes the class, owner confirms; instance axes, else sentences; customer-named 8-Ks only; weakening owner-confirmed. Why: implements the approved row. Gets wrong: anonymous matching is inference.
- (b) Text only. Gets wrong: table-only disclosures.
- (c) Defer to M05/M06. Gets wrong: NVIDIA's 36% invisible.

**5.6 What a confirmed cause does**
- (a) (recommended) Price, mix or competition → `r12_warning` plus a CvD Q2 "weakening" vote; volume, input cost or FX → watch; one-off, accounting, segment or credits → cleared but fed to Round 2. Why: the outline says "avoid". Gets wrong: Target 2022 warns, then reverts.
- (b) Every episode warns. Gets wrong: Invitae's COVID volume quarter.
- (c) Cause shown only. Gets wrong: Tesla and Invitae never warn.

**5.7 Do Round 5 flags count?**
- (a) (recommended) Confirmed R12 warnings and young-firm per-unit flags count, not while the stage is unconfirmed (D-M04-7); unsourced thresholds stay information until Part 8 calibration on at least 20 owner-labelled episodes (starting value). Why: R11 and R12 are approved red flags. Gets wrong: unconfirmed episodes wait.
- (b) All information-only. Gets wrong: Invitae never counts.
- (c) All count now. Gets wrong: uncalibrated cut-offs vote.

**5.8 Stage → flag set**
- (a) (recommended) Introduction → young; growth → young plus SG&A rule; mature → mature; decline → mature, reversion unused; confirmed shake-out → all-stage flags only. Never confirmed → both sets labelled "stage unconfirmed", uncounted; later ambiguity → last confirmed stage (D-M04-7). Why: growth firms have units and cash flow. Gets wrong: more flags for growth names.
- (b) Growth → young only. Gets wrong: no leverage check for growth names.
- (c) Growth → mature only. Gets wrong: Tesla 2023's per-car fall unflagged.

**5.9 Rivian: burn with falling units** (feeds 3.9)
- (a) (recommended) Young-firm warning when TTM units fall while FCF (total capex, D-M04-6) < 0; Rivian otherwise a negative control. Why: deliveries −18% while burning. Gets wrong: planned changeovers warn.
- (b) Credit warnings only. Gets wrong: Rivian 2025 unflagged.
- (c) Negative unit GP for 4 quarters. Gets wrong: ignores Rivian's halved loss per car.

**5.10 Basis of the positive margin rows** (changed: D-M04-11 already adds `gm_trend_pp` and `opex_vs_sales`, information until Part 8)
- (a) (recommended) Add an "excluding stated items and credits" basis beside reported, reversion prior shown. Why: Rivian's credit-built margin and Target's FY2023 rebound otherwise read as pricing power. Gets wrong: management chooses which items are stated.
- (b) Reported only. Gets wrong: Rivian's credits read as pricing power.
- Old (b) "count now" and (c) "leave to M03/M06": removed, settled by D-M04-11.

**5.11 Contracted RPO test**
- (a) (recommended) Weakening when the RPO level is below its 3-year minimum for 2 quarters; ratio-only breaks open review. Why: the approved test. Gets wrong: flat RPO with soaring revenue only reviewed.
- (b) Ratio only. Gets wrong: fast growers read weakening (illustrative).
- (c) Both fail. Gets wrong: a shrinking order book with faster-falling revenue (illustrative).

**5.12 Revenue-at-stake weight**
- (a) (recommended) Design-in vote = min(1, at-stake ÷ 0.25); contracted 1; transactional 0; missing excluded (NVIDIA 1; a single 12% customer 0.48). Why: implements D-M04-1's weighting. Gets wrong: 0.25 unsourced.
- (b) One full vote. Gets wrong: a 10% customer equals NVIDIA's 36%.
- (c) Leave to Round 6. Gets wrong: never built.
