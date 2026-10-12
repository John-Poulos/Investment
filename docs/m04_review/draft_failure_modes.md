# M04 failure modes — draft for the redrafted doc

Draft 2026-10-12 for the M04_FINANCIALS.md "Failure modes" section (D9: how could this data mislead?). Sources: the current table, the pack's "Failure modes (rows to add)" sections, the round briefs and PROBE_RESULTS.md. Rows for rejected options are dropped and duplicates merged. S-numbers are accepted suggestions (texts in the round briefs). Build and operations rows (lock, logon load, fixtures, DB growth) belong in M04_BUILD_LOG.md.

## Data layer
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Point-in-time values and tag switches | Recasts rewrite what was known (Rite Aid FY2017 32,845 → 22,928; WDC FY2023 12.3B → 6.3B); 8-K and DEF 14A facts become "latest"; a tag switch (ASC 606 contract tags) reads as a change | `facts_as_of`, periodic forms only, first-filed values in backtests (S1.1, S6.1); switch inside a window = "definition changed", not scored (D-M04-3; S2.2) |
| Extension-only, wrong-meaning and mis-mapped tags | Values only under extensions, absent from companyfacts (NVDA capex before FY2022, NVDA marketable securities 51,951; MRVL has no issuance tag); GE FY2016 contract assets double-tagged as `CommodityContractAssetNoncurrent` (a derivative concept); nonproduction D&A read as total (INTC $200M vs $9,204M) | Instance read or "missing", never zero; per-company alias (GE only), that concept never mapped generally; `Depreciation` added, fallbacks marked (D-M04-3, -42; S1.3, S1.4, SB.18) |
| Shares | Cover and period-end dates mixed; multi-class counts missing (GOOG, META, MSTR, SPCX); splits | Four series; class-summed cover count from R1; split guard on every series; pre-2011 history on basic weighted average, labelled (D-M04-2) |
| Capex definition and split | Broader fallback tag (+15.8% Amazon FY2016) mixed into peer z; Greenwald out of range (MU 6 of 8 years, INTC 4 of 4) or calls a build-out maintenance (MSFT 65–79%); depreciation moves with useful lives (INTC 2023 −29.5%) | Company definition with "≈ broader tag" marker; peers on PP&E tag only (NVDA, AMZN out); depreciation default capped at capex, Greenwald only as in-range cross-check; method tag on every value; consumers use total capex (D-M04-3, -6; S2.7) |
| History depth and breaks | XBRL starts 2009–2011, later for some concepts; bankruptcy emergence leaves no 12-month period (Peabody 2017) | Depth per concept; "insufficient history", never "first deep decline"; stubs never summed (D-M04-54) |
| De-SPAC and same-CIK history | Shell and target histories under one CIK read as restatement or issuance (INFQ FY2025 loss 52% smaller; SPCX +100%, INFQ +1,310%) | Boundary at the closing 8-K (2.01 + 5.06); `predecessor` label; `spac_shell` keyed on period end (D-M04-8, -22) |
| Filer status and deadlines | Status must carry year to year: Invitae's FY2022 float $569.8M is above the $560M exit line, so it stayed large accelerated; an entry-line ($700M) reading misdates its deadline | Rule 12b-2 entry and exit lines from stored float, carried yearly; longest deadline when float is missing; Invitae as regression case (S1.6; D-M04-36, -61) |
| Foreign filers | 6-K XBRL stops (GFS); IFRS wording; 6-Ks carry no item codes, so default and delisting notices go undetected; a filer can slide a year unseen | IFRS phrases; annual burn up to 16 months, then incomplete; "as of <date>" labels; 6-K events a known omission (D-M04-36) |
| Tickers and prices | Recycled tickers attach another company (BBBY, RAD, SHLD); spliced series (BTU 2017, CHK 2021); stale bars after cancellation (RADCQ, NVTAQ to 2026-10-09) | `cik` on every signal; Tiingo symbol only when name and dates match the SEC company; last real trade found first; else "missing: no prices" (D-M04-72, -74) |
| Signal record | Text in numeric `value` sorts above numbers; missing stored as 0; transcript or owner-entry rows look like filing evidence | `value_text`; missing = "missing: <reason>"; grade = weakest deciding input, inputs listed in `method` (D-M04-9) |
| Segment data | Segment figures read as consolidated (the Rivian "recast" mistake); segment definitions restated | `fact_dim` with axis and member on every value; breaks flagged, not merged (D-M04-42) |

## Peers
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Peer set | Coarse or stale SIC (solar in 3674; AMZN's SIC peers are mail-order retailers); product peers outside SIC (QCOM, WDC); 505 names in 3674; a 10-K-only "active" filter drops 20-F filers (GFS); non-SEC peers (SK hynix, Samsung) missing; acquired revenue reads as growth (AMD +43.6% 2022) | Ranked shortlist, active = 10-K/20-F/40-F; owner confirms and adds product peers; non-SEC peers stored as "missing"; acquisition years flagged (R1 case list) (D-M04-4; S6.2) |
| Period offset and peer lag | The cycle turns inside a 1–2 month offset; 53-week years add about 2%; the peer quarter arrives weeks later (WDC 32 days after Micron) | TTM ±45 days, quarters ±40; end dates shown; 53-week flag; outside = "no comparable period" (D-M04-5) |
| Robust z | The method flips the label with few peers (Intel 2022 at n = 4: −0.82 to −1.92); one outlier puts everyone "in the pack" (NVDA 2023 z +8.97); high dispersion hides a large gap (Intel 2025 −34.8 pp at z −0.91) | Fixed gap below 5; MAD × 1.4826 × b_n for 5–9; drop \|z\| > 3 once; method and n shown; gap in pp always shown; neutral zone between cycle and company-specific (D-M04-52, -55) |
| Margin comparisons | One unlike peer gives a fake gap (Micron vs WDC −33.5 pp); no gross-profit tag; cost of sales differs (Amazon fulfillment; Target rate on Sales) | Margin gap votes only with ≥ 3 comparable peers (S6.10); method `derived`, base stated, "not like-for-like" (D-M04-3, -40, -54) |

## CvD profile
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Activation | TTM lags: MU read NO_SLOWDOWN at its 2022-10-07 10-K; one lumpy quarter can switch CvD on | Revenue, gross margin (≥ 3 pp) or operating income (≥ 25%) falls, or latest quarter ≥ 10% below a year earlier (starting values) (D-M04-55, -67) |
| Missing rows | Unbuilt rows read as disagreement (all AMBIGUOUS) or vanish unseen; a state can rest on few rows (MU trough on 3 of 7) | Missing rows leave the denominator; ≥ 2 present; coverage shown beside confidence (D-M04-56) |
| Filing lag, stale and overdue | The price trigger fires before the filing that confirms the state (Micron's low came while filings showed growth); a dead company keeps its last state (Invitae, RadioShack) | "stale" once a period ends unfiled, later tranches wait (pauses up to 40–50 days); `overdue` → gate incomplete and exit warning; 8-K 1.03 and 3.01 fail the gate first (D-M04-37, -61) |
| Inventory days | Write-downs understate days (Micron 153 vs 235); ending vs average inventory gives other figures (151/213) | One labelled definition (average inventory); write-down added back to inventory and COGS (R1 brief; probe L9) |
| Capex and intensity rows | One cut drives both Q1 supply response and Q2 weakening; a surge into falling revenue reads intact; a planned counter-cyclical build reads neutral | Q2 on total capex intensity and R&D level; surge > 1.5× own average → neutral, pointer to M05 (D-M04-54, -64) |
| Troughs and ROIC | 1–4 pp wiggles count as cycles (Intel 2013–17); write-downs fake lower lows; invested capital ≤ 0 after buybacks; goodwill jumps | 5 pp turning points, write-down adjusted; ROIC `not_meaningful` when ≤ 0 and "intact" only with gross margin (D-M04-54) |
| Health scores | 4 of 9 F signals are cycle-driven (MU FY2016 F = 3); G penalises acceleration (NVDA FY2024) and needs peer medians; F-quality's CFO point holds for a decliner (Intel 2025 intact) | F-quality 0–5 is the only health vote; Piotroski F and Mohanram G shown, not voted (D-M04-53, -59) |
| Equity point | Plan issuance every year reads as dilution; INTC 2024 (+2.1%) stays intact | Round 3 measure, lost only on extreme or serial issuance; unconfirmed stage → missing (D-M04-65) |
| Normalized earnings power | Assumes the next cycle resembles the last; decliners keep old margins; repeated "one-time" items inflate it; two unrelated one-offs both stay in | Current and cycle-average revenue bases; reported and ex-items shown; an item excluded only if nothing similar in 10 years (D-M04-54, -66) |
| Overreaction gauge | Mismatched windows fake an overreaction; clears near the low (MU Q2 FY23); a trough without overreaction still gets strength | Same 4 quarters for price and earnings; informs, never overrides (D-M04-57, -62) |
| Market share and the Intel case | Most names rest on owner entries (grade B); "no gains" line is illustrative; without share and moat rows CvD never says "damage" alone (Intel) | Grade shown; else "missing: no share data"; Intel AMBIGUOUS → owner review, the owner's answer is the expected state (D-M04-63, -68) |
| Guidance record | Seasonal guides read as removals (Intel January); Intel FY2022 a "hit" despite two cuts; release-silent guiders | Same fiscal position a year earlier; ended = "expired"; revisions counted separately; "missing (DS1)" (D-M04-10) |
| M01 reading of CvD | A NO_SLOWDOWN name at a gate warn (Rivian) still gets tranches | Only CYCLICAL_TROUGH + gate pass adds rule-7 strength; gate state shown beside (D-M04-58) |

## Survival gate
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Distress scores (Z, Z'', O) | Young firms read "distress" with years of cash (Rivian Z'' −5.37 with $5.3B); Type II error 15–20%; bubble prices inflate X4; O-score units flip results; BA 1.53 at FY2025 | Out of the gate; stage-labelled `distress_score` warning; variant, version, cut-off and units stored and tested (D-M04-31) |
| Burn and runway | One-quarter swings and seasonal Q1 OCF (AMZN); one 10-Q gives no TTM (SPCX); growth capex makes cash-rich firms look short (AMZN 9.1, Intel FY2024 5.6); capex that cannot be cut only warns | Worse of TTM ÷ 4 and last two quarters; one quarter → incomplete; capex-funded names warn below 8, review below 6, never fail; rule-7 blocked while in review (D-M04-32, -38) |
| Undrawn credit | Revolvers mostly untagged; borrowing base and springing covenants cut availability; facilities expiring inside the horizon (Boeing FY2019: $3.2B 364-day ends Oct 2020 → 5.9 quarters, fail, not warn) | Confirmed credit only (tag, verified text or owner entry, with expiry) maturing beyond the horizon; Boeing 5.9 and 5.5 regression cases (D-M04-32; SB.18) |
| Debt maturities | `DebtCurrent` already holds commercial paper (Boeing FY2019 13,449 summed vs 7,340); roll-down looks like reclassification; 7 quarters' runway with 3.5 quarters' debt only warns | Commercial paper never added twice; 12-month debt > liquidity fails, + 4 × burn warns, 24-month wall shown; only text fails a reclassification (D-M04-33, -34) |
| Going-concern and covenant text | Hypotheticals, negations, alleviated cases, audit matters, boilerplate (Invitae Q2 2023) and SPAC-era sentences match; "in compliance" dominates; breaches are often waived; text leads by only 62–144 days | Sentence classes; only "exists", unwaived breach, forbearance or covenant reclassification fail; alleviated, waived or reset → warn + review; `spac_shell` periods out (INFQ) (D-M04-34, -8) |
| 8-K events | Cure notices usually end in compliance; a deficiency ending in delisting only warns until the final notice; listing transfers | 1.03 fails, never auto-clears; 2.04 fails until a clean periodic filing and owner resolution; transfer = information (D-M04-37; S1.11) |
| Gate scope | MSTR's assets and income swing with bitcoin; banks, funds and ETV never get tranche adds | Model tag → liquidity-only gate for `asset_treasury`, `reit`; "not applicable" reads as not-pass until a sector gate exists (D-M04-8, -35) |

## Earnings quality
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Cash conversion and accruals | Growth inflates accruals; CFO/NI meaningless near zero NI or with a sign flip; finance arms and discontinued ops (GE 2016); factoring pulls cash forward; a growth firm with real collection problems gets only a note | Cash-flow version vs own history, no return claim; `not_meaningful` when NI ≤ 0 or < 1% of revenue; 3-year sums; < 0.8 warns only for mature and decline (D-M04-14, -20) |
| Operating basis | Fair-value, crypto and valuation-allowance swings move NI without cash (Tesla 2023, MSTR 2025); the 21% / 35% tax approximation misses foreign and capital-loss rates | Operating basis; stated rate when given; model tag → `not_meaningful` (D-M04-8, -14; S2.1) |
| M-score and misstatement score | SGI penalises growers; old cut-offs; > 100 false positives per true one; GMI breaks on negative margins; misstatement `issue` ≈ 1 for large caps and soft assets lift most above 1.00 (Apple 1.30); a growth-based manipulator gets only a note | Screens only; review only when the SGI = 1 M-score > −1.78; misstatement score labelled "approximation", both bands, never a trigger; `issue` unknown → missing (D-M04-14; S2.3, S2.4) |
| Restatement events | No 8-K for little r; no history before 2004-08-23; dei error flag only on annual reports from 2023 and missed by out-of-period corrections (AVGO's Dec 2023 10-K needs its R1); a 4.01 after a de-SPAC is routine | 4.02 + dei flag + text + one-off old-filing fetch; flag never positive evidence; a 4.01 within 12 months escalates, post-de-SPAC 4.01 without disagreement = information (D-M04-15; S1.11) |
| Restatement walk | Recasts, adoptions, tag switches, rounding, cash-flow reclassifications and de-SPAC look like errors; a dollar floor hides small corrections; tiny residuals queue (GE +$4M on −$244M) | Ordered labels, then residual > 0.5% and $0.1M → review; first-run baseline (D-M04-16, -71) |
| Open 4.02 | CvD, gate and scores read disowned figures; an M01 add can still trigger | Rows marked "inputs under non-reliance" and warn; adds not blocked (D16) (D-M04-21) |
| Estimate changes | Disclosed only when material; income-decreasing ones exist; GE Power's 29% segment share hidden behind 15.5% company share | Bands in both directions on the amount's own tax basis; segment share only when stored or quoted (D-M04-17, -18) |
| Recurring "one-time" charges | A genuine multi-year restructuring reads as recurrence; a computed non-GAAP gap misstates the company's own | ≥ 3 of 4 years (starting value), shown with its plan; gap quoted, never computed (D-M04-19) |

## Dilution
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Share measure | Diluted counts move with the profit sign; splits read as 10× growth; escrowed shares sit in basic EPS but not the cover count (INTC 71M); counts filed in USD (INFQ warrants) | Basic weighted average, same-filing pairs; split guard; cause label on the cover cross-check; unit check → data defect (D-M04-2, -22) |
| Weighted-average lag | Late ATM sales show only partly (MSTR +28.1% weighted vs +35.5% cover); a raise repairs the gate before the shares show (BA 2024–25) | Cover-count cross-check; gate condition looks back 4 quarterly filings (D-M04-22, -26) |
| Legacy-share pairs | One filing mixes bases: INFQ's comparatives are unrecast legacy shares (× 0.3474 exchange ratio) beside recast figures | Not meaningful across a de-SPAC once the close is linked; a pair at the exchange ratio → data defect (D-M04-22) |
| Issuance bands | All-filer breakpoints set by microcaps; SPACs pass a float filter (95 SIC-6770 filers ≥ $75M) and the "blank check" phrase is no test (101 non-6770 hits); about 1,400 small firms read "extreme" | Float ≥ $700M with SIC 6770 excluded explicitly; yearly percentiles of same-filing pairs (D-M04-23) |
| Shelves, 424Bs, ATMs | A shelf is capacity, not a raise; 21 of 41 424Bs carry no fee exhibit; GOOG's June 2026 424B5s were equity, not debt; resales add no shares | Fee exhibit per 424B, else paired final supplement or cover; class by form and security; resale = supply, never dilution (D-M04-24) |
| Causes | Value-creating issuance warns (Intel 2025 strategic buyers); 8-K 3.02 absent below 1% (5% small filers) | Only non-cash causes become information; cash raises warn while the gate fails or warns, cause shown; share counts stay the measure (D-M04-28) |
| Warning routing | Issuance is MSTR's strategy; a funded plan in a brief warn band warns; a raise from strength after a brief warn warns; a growth firm with a sliding runway is only reviewed; an incomplete gate gives no warning | Model tag and gate state route it; cause shown; gate fail warns at every stage; incomplete shown as a data gap (D-M04-13, -25, -26, -27) |
| Convertibles, warrants, preferred, Up-C | As-converted only when dilutive; capped calls; stale or contingent warrants; preferred series missed (MSTR STRE, ~10–11 series); Up-C class A understates the share base | Text with quote → review; in the money only, gross and net; "missing: exchangeable units" (D-M04-25) |

## Unit economics and margins (R11, R12)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Life-cycle stage | Securities flows (AAPL shake-out); partner financing mimics growth (INTC, Tesla FY2024); one-year flips; acquirers look like growth; MRVL's latest-year shake-out not reviewed | Core investing, 2 of 3 years; CAGR conflict → review; owner confirms first stage and every change; unconfirmed → both flag sets, uncounted (D-M04-7, -12, -46) |
| R12 trigger | Stage-gated, Invitae would never be checked; a one-quarter charge fires it (Intel 2024Q3); companyfacts lacks Target's 10-Q cost of revenue for a year, so it fires late or never | Every stage; 2 straight quarters; ex-items basis beside; 10-Q instance read into `fact_dim`, else "missing: dimensional" (D-M04-40, -42) |
| Margin causes | Management framing, buried offsets, mis-signed summaries; Target 2022 warns, then reverts | Arithmetic check of stated components; quote stored; owner confirms; Gemini on request only; price, mix, competition warn, the rest watch or clear (D-M04-41, -44) |
| Stated items and credits | Management chooses what is "stated"; regulatory credits lift margin with no unit cost (Rivian Q4 2025); Target FY2023's rebound is reversion | Reported and ex-items-and-credits both shown; reversion prior shown, "not used" for decline (D-M04-46, -48) |
| Per-unit figures and KPIs | Revenue scope ≠ units (leases, credits, services); stated vs computed differ (Invitae $380 vs $394); production above deliveries flatters cost; KPI categories change; huge margins on tiny revenue | Stated figure first with quote, computed beside on matching scope; gap > 10% flagged; breaks flagged, not merged; `not_meaningful` below a revenue floor (D-M04-42) |
| Burning with falling units | Planned model changeovers warn | Young-firm warning only (D-M04-47); its D13 weight is disputed between D-M04-45 and -60 (Open questions) |

## Customers
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| ≥ 10% customer list and weight | Customers anonymous; matching across years is inference; a shorter list read as a loss (NVIDIA FY2026); a customer may have shrunk below the line; the 0.25 at-stake divisor is unsourced (a single 12% customer weighs 0.48) | Revenue at stake and total revenue shown; loss only with text or 8-K evidence and owner confirmation; weight a starting value, missing excluded (D-M04-43, -50) |
| RPO | Tiny for design-in suppliers (NVIDIA ≈ 1%); one counterparty dominates; flat RPO with soaring revenue only reviewed | RPO test for the contracted class only; ratio-only breaks → review; counterparty share as a dated company-stated note (D-M04-49) |
| 8-K 1.01 / 1.02 | Mostly financing (all four 1.02 + 2.03 co-filings on the watchlist) | Customer event only when the text names a customer or supply agreement; 1.02 co-filed with 2.03 = financing (D-M04-43) |

## Calibration and starting values
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Unsourced thresholds | Starting values (±40 days, 2 misses in 4, 3 pp, 25%, 10%, 8-quarter warn band, −25 pp) read as tested rules; names sit near lines (SPCX 7.997, AMZN 9.1) | Labelled starting values; tuned only at Part 8 (D-M04-45, -51) |
| Small, hindsight-prone labels | 24 + 4 CvD episodes and 20–30 red-flag cases are small; labels that know the outcome fit hindsight; J.C. Penney has no prices for the gauge | Blind labelling, split before and after FY2018; tune only activation, z cut, majority and gauge (D-M04-51, -72, -73) |
| Unweighted and information rows | A serial diluter with a passing gate can reach confluence; `debt_to_revenue`, net debt ÷ EBITDA, `fcf_burn` and core trend rows give no warning until calibrated (AMZN) | Red flags shown and reviewed with no D13 weight until ≥ 20 labelled episodes; information rows against own range and peer z (D-M04-11, -29, -39, -60) |
| Backtest results | Invite threshold edits inside a build | Changes proposed with sources at a High review (D6; D-M04-73) |
| First runs and backfill | Baselines flood the queue (101 walk steps, 136 EFTS hits); history exists only after the owner's backfill | Baseline recorded, not queued, except items filed in the last 12 months and current gate fails; weekly cap 5; missing until backfilled (D-M04-70, -71) |

## Owner entries and overrides
No decision in this review overrode a research recommendation. These rows cover owner-entered inputs and the owner's changes in D-M04-1.

| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Model tags | An untagged treasury company routes by SIC (MSTR 6199 excluded as a financial); a wrong tag removes tests | Hand-edited file with reason and source; unknown tag rejected; engine may propose `reit`, owner edits (D-M04-8) |
| Stage override | The owner's last confirmed stage keeps routing after the company changes | Computed changes and ambiguous cases reopen `m04_stage` (D-M04-7, -12) |
| Peer curation | Hand-picked peers can fake a shared or company-specific reading | Engine shortlist and each peer's end date shown; non-SEC peers listed as missing (D-M04-4, -5) |
| Owner-entered facts | Share, revolver and stickiness entries age and carry no filing | Grade B; expiry on credit entries; class proposed by engine, owner confirms (D-M04-9, -32, -43, -68) |
| D-M04-1 owner changes | IQR-based robust z is unstable with few peers; no research threshold exists for customer loss, so the owner's class decides the vote | z amended to MAD × b_n with fixed-gap fallback; "weakening" owner-confirmed (D-M04-43, -50, -52) |
