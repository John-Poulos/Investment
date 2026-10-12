# M04 Round 2 — Earnings quality — brief

**Decides:** which earnings-quality scores M04 shows and when they reach review (2.1); how restatements are detected and how first-vs-latest deltas are labelled and queued (2.2–2.3); how estimate changes are measured (2.4–2.5). New 2.6–2.9 cover outline items and approved rules the pack leaves open.
**Outline items:** Red Flag 3 "accounting manipulations and 'one-time' adjustments" (GE, Rivian; l. 80), the main item. Analyze 2 "FCF growth … golden indicator" (l. 66–68) in part (cash conversion only). R2 (stage-aware red flags), R11 (Rivian = unit economics, GE = earnings quality), D8 (review queue), D21/D28 (code finds text, Gemini only on request).

## What the research says
- Accruals, the M-score and the misstatement score have lost most of their return power; they remain screens with many false alarms (S-new-6…12). Use cash-flow accruals (S-new-13).
- M-score: investigate above −1.78 (38–76% caught, 3.5–17.5% of clean firms flagged); SGI pushes growers toward "manipulator" (S-new-14). Only the M-score and the misstatement score at high cut-offs gave investors a net benefit (S-new-15).
- Misstatement score: > 1.00 catches 68.6%, flags 36.3% of clean firm-years; > 2.45 catches 18.8%, flags 5% (S-new-16).
- Restatements: 4.02 is waived when already reported in a 10-K/10-Q (S-new-r2-1); little r is now about 76% of restatements and predicts later errors (S-new-17, -18); the checkbox marks annual error corrections only (S-new-r2-2).
- Most first-vs-latest deltas are recasts, not errors. Tests: NI unchanged (revenue); CFO + CFI + CFF unchanged (cash). Shifts that raise CFO are a manipulation channel (S-new-r2-3).
- About 500 material estimate changes a year, mostly income-increasing (S-new-21); GE booked over $1.4B in 2016 (S-new-20).
- Cash conversion is the most robust large-cap measure, but factoring and non-cash items distort it (Tesla 2023 valuation allowance, 39.8% of NI; S-new-r2-8).
- Rivian (R11): unit economics in Round 5; its write-downs ($920M 2022, $107M 2023) fall under new 2.6.

## Worked example
GE restatement walk (S-new-1, S-new-r2-8, S-new-r2-9; GE FY2018/FY2019 10-Ks read for the gaps; $M). Columns (a)–(c) are the 2.3 tolerance options applied to what is left after labelling.

| # | Step (first → latest version) | Label after text | Left over | 2.3 (a) 0.5% and $0.1M | (b) min(1%, 5% pretax) | (c) 2% |
|---|---|---|---|---|---|---|
| 1–2 | Revenue FY2016 −4,224; FY2017 −3,849 | ASC 606 + other income out of revenue (8-K 2018-04-13) | +1, 0 | — | — | — |
| 3 | Revenue FY2017 −18,964, NI unchanged | `reclass`; cause: Baker Hughes + Transportation to discontinued ops (passage attached) | — | — | — | — |
| 4 | NI FY2016 −1,331 | ASC 606 −1,182 + LIFO→FIFO −147 | −2 | — | — | — |
| 5 | NI FY2017 −2,698 | ASC 606 −2,668 + LIFO→FIFO −124 | +94 = NCI share (+95) | review **unless** the NCI rule (S2.6) applies | review unless NCI rule | — |
| 6 | CFO FY2016 +1,404 | `cf_shift_up` 1,400 (watch; no cause stated) | +4 on a −244 base | **review** (tol. 1.2) | review (2.4) | — (4.9) |
| 7 | CFO FY2017 −4,394 | ASU 2016-15 −4,411; total −152 = restricted cash −153 | +17 | — (52) | — | — |
| 8 | CFO FY2017 +522 | `cf_shift_up` 523; cause suggested, no amount | — | flag | flag | flag |
| — | Infleqtion Q1 2026 revenue +$446K / net loss −$544K (little r) | `error` (10-Q text) | — | both created | both created | net loss **missed** |

- With the two new mechanical labels (NCI share, restricted cash), GE queues one item under (a): step 6, the near-zero-base case. (c) queues nothing for GE but misses Infleqtion's net-loss correction and Boeing's 0.66–1.78% revenue revisions.
- GE's estimate changes on its own first-reported 10-K amount ($2.2B, 2016; provisional, see Gaps): 2,200 ÷ 9,030 = 24.4% → watch, against 15.5% from the SEC order's lower bound. Same band under 2.5(a).

Scores (question 2.1; scratch mapping, recompute from `fact` at build): NVIDIA FY2025 M −0.96 / SGI = 1 −1.98 / F 3.11 · NVIDIA FY2026 −1.17 / **−1.75** / F not computed · Marvell FY2026 −1.60 / −1.98 · Apple FY2025 −2.29 / −2.35 / F 1.30 · Microsoft −2.54 / −2.67 / 1.15 · Boeing FY2024 incomplete / F 1.63 · Strategy F 3.28 (`asset_treasury` → not meaningful) · Micron FY2023 M −7.01 (negative gross margin → not meaningful).

## All cases
| Outcome | Cases (pack numbers; added ones marked +) |
|---|---|
| Error events | 1 4.02(a)/(b); 2 Big R in a 10-K/10-Q only (B.3); 3 little r (Infleqtion, interim-only, text is the only route); 4 out-of-period correction; 21 auditor change within 12 months (escalates; de-SPAC as context); 22 before 2004-08-23 → no 4.02 history |
| Mechanical labels, no flag | 5 standard adoption; 6 discontinued-ops recast (GE −16%, WDC); 7 segment recast; 8 split; 9 tag switch; 10 rounding/unit; 11 8-K or DEF 14A value (excluded); 28 de-SPAC `predecessor`; +NCI share inside a "continuing operations" amount (GE FY2017); +restricted cash brought into totals (ASU 2016-18, GE FY2017) |
| Watch or note | 23 CFO shift (`cf_shift_up` watch, `cf_shift_down` note); 18 factoring; 13–14 estimate change, recurring same direction; 15 catch-up revenue (own history); 16 contract assets outgrowing revenue / deferred revenue falling; 29 fair-value swings; 30 valuation allowance → operating basis; +Intel 2023 useful-life change (machinery 5 → 8 years, depreciation −29.5%) → estimate note and A2 tag |
| Review | 12 mixed step with a residual; 24 shift plus residual; 25 near-zero base; 26 cause in an intervening filing; 27 cause without an amount (passage attached) |
| Not meaningful / incomplete | 17 NI near zero, **or negative** (+); 19 growth inflating SGI and accruals; 20 missing inputs (no SG&A line, no total liabilities, tag switch → probe, never zero); 31 negative gross margin; 32 unclassified balance sheet (GE); `asset_treasury` (Strategy) |
| Excluded | +`financial`, `reit`, `fund`, `spac_shell` tags (1.7a), or SIC 6000–6799 without a tag; 33 foreign filer: walk on 20-F/6-K and `ifrs-full`, 4.02 detector silent |
| Pending new questions | +recurring "one-time" charges and the non-GAAP gap (2.6); +stage unassigned or ambiguous (2.7); +open 4.02 non-reliance while other rows read those periods (2.8); +estimate amount later restated (GE $2.2B → $0.7B in the FY2018 10-K) → store by filing version |

**Completeness:** complete for revenue, NI and CFO on the watchlist once the added cases are in. Not seen on real data, listed from the rules: 4.02(b), Big R via B.3, 10-K/A error correction. Other concepts are not walked. SPCX has no annual history yet.

## Suggestions
- **S2.1** `eq_cash` (CFO/NI, cash-flow accruals, operating basis). *Changed:* not meaningful when NI ≤ 0 or |NI| < 1% of revenue; tax at the filer's statutory rate, else 21% (2018 on) / 35%; tags per 1.7, stage per 1.6 and 2.7.
- **S2.2** `credit.dso()` plus `contract_asset_gap`, `deferred_rev_gap`. *Added:* alias-to-standard tag switch → window not scored.
- **S2.3** `mscore`, SGI = 1 decides review; ACCR variant named (cash-flow; 1999 original unverified).
- **S2.4** `misstate_f`, "approximation", bands > 1.00 / > 2.45, `issue` unknown never 0.
- **S2.5** `restatement` (4.02, dei flag, text, 4.01 escalation). *Changed:* dei flag from R1 pages, one count (36) pack-wide.
- **S2.6** `restate_delta` walk, ordered labels, first-run baseline. *Added:* NCI-share and `restricted_cash` labels.
- **S2.7** `estimate_share`. *Added:* two phrases; amounts by filing version; useful-life change tags A2 maintenance capex; Intel 2023.
- **S2.8** Information only until D13 weights. *Added:* `eq_cash` and Piotroski's CFO > NI test count the same evidence.
- **S2.9** Fixtures and live checks. *Changed:* GE rows 4–7 as above; GE estimate on its own amount, order beside it.
- **S2.10** Review kinds. *Changed:* inside the one M04 cap and B.3a order; baseline count reconciled (101 vs 102/135).
- **S2.11** *New, if 2.6a:* `special_items`.

## Check flags
- Red Flag 3 "one-time adjustments": no signal; the S1.3 charge tags are unused → 2.6. R2 applied silently, unassigned stage undefined → 2.7. Open 4.02 not linked to CvD or the gate → 2.8. FCF growth has no home → 2.9.
- CFO/NI with a loss flips sign (NI −100, CFO −50 reads 0.5 and warns) → S2.1 changed.
- Stage cited as "5.1" (now 1.6); tag "bitcoin treasury" is `asset_treasury` (1.7; Round 3 too).
- 2.1 said "the M-score alone" had a net benefit; the misstatement score at high cut-offs did too → reworded, (d) added. 2.4a's one prior 10-K cannot test 3-year recurrence → two.
- Add failure-mode rows: alias-to-standard tag switch (contract gaps); tax-rate approximation. Engine row: `value_text`, `source_ref` (1.8a, D13).
- No conflict with D16, D27 or M01 rules 3 and 7: Round 2 feeds neither CvD nor the gate unless 2.8(b).

## Gaps
**Closed now**
- Alphabet 2023: servers 4 → 6 years, NI +$3.0B (S-new-22, Note 1); 4.1% → note.
- GE NI residuals: ASC 606 amounts are continuing operations before NCI; LIFO→FIFO −147 / −124; residuals −2 and +94 (= NCI share), 0 and −1 on `ProfitLoss` (GE FY2018 10-K pp. 108, 111). Changes 2.3's reasoning.
- GE CFO FY2017: ASU 2016-15 moved −4,411 (residual +17); total −152 = restricted cash −153 (p. 110).
- GE revenue FY2017 recast: discontinued operations, 21,115 of 2017 sales (FY2019 10-K Note 2); 2,151 does not tie, so the passage is attached.
- GE's own estimate amount: $2.2B (2016), restated to $0.7B (FY2017 annual report p. 94; FY2018 10-K p. 57). Provisional: "DRAFT" print, all service agreements not Power alone, basis assumed pre-tax.
- Amazon ASU 2016-09 shifts are stated with amounts ($119M, $829M), so text labels apply. Tax: 21% from 2018, 35% before (26 U.S.C. §11(b)). Estimate notes about 2–4 a year (press, secondary); reviews rare.

**Needs the owner's probe**
- GE FY2017 10-K primary document (1 request): confirm the $2.2B sentences. GE 2015 contract-asset tag: already in the Part 6 instance read.
- Local, 0 SEC requests: `fact` tags at year-ends for NVDA (instant near 51,951), MRVL (`Proceeds*`), TSLA (`LongTermDebt*`, `Proceeds*`), GFS; recompute the score table; SPCX 10-K count.
- Measured in the Part 3 run: download sizes, text-label yield. Stay open: Beneish 1999 ACCR; unsourced thresholds.

## Questions
**2.1 Score set and role** (reworded; recommendation kept)
- (a) (recommended) Cash conversion and accruals as persistence warnings, no return weight. M-score with M and M with SGI = 1 side by side; review only when SGI = 1 is above −1.78. Misstatement score with percentile and both bands, no review trigger. Why: screens, not signals; the SGI-neutral test removes growth alarms. Today: NVIDIA FY2026 (−1.75) is the one review; NVIDIA FY2025 and Marvell get a "growth-driven" note. Gets wrong: a manipulator whose score rests on sales growth gets only that note (illustrative).
- (b) Both scores at the published cut-offs. Gets wrong: flags NVIDIA (both years) and Marvell on growth; Apple 1.30, Microsoft 1.15 and Boeing 1.63 sit in the > 1.00 band that holds 36.3% of clean firm-years.
- (c) Cash conversion only. Gets wrong: drops both screens that showed a net investor benefit; misses NVIDIA FY2026's asset-quality jump (AQI 1.52).
- (d) As (a), plus `misstate_f` > 2.45 as a review trigger. Gets wrong: queues NVIDIA FY2025 (3.11, driven by growth and issuance; 1.12 with `issue` = 0).

**2.2 Restatement sources and escalation**
- (a) (recommended) 4.02 + dei flag + 10-K/10-Q text + one-off fetch of at most 35 historical filings (8-K 8.01 second pass after a dry-run count); a 4.01 within 12 months escalates. Why: catches B.3 and little r (Infleqtion ticks no box) and labels GE from its 8-K and later 10-Ks. Gets wrong: causes stated without amounts stay review items.
- (b) 4.02 only. Gets wrong: misses Infleqtion's little r, GE's recast causes and Tesla's ASU 2023-08 change.
- (c) As (a) without escalation. Gets wrong: drops the auditor-change signal (29% of Big R vs 11% base).
- (d) As (a) without the historical fetch. Gets wrong: about 102 pre-corpus steps stay `unexplained`, including GE's steps the filings explain to the dollar.

**2.3 Tolerance for unexplained deltas** (reasoning updated by the gap closures)
- (a) (recommended) Review a step or residual above both 0.5% and $0.1M, after the S2.6 labels including NCI share and restricted cash. Why: creates both Infleqtion correction steps the $1M floor missed. Gets wrong: queues GE FY2016's +$4M CFO residual on a −$244M base.
- (b) Above min(1%, 5% of pretax income). Gets wrong: shrinks with profit (Intel FY2023: $38M vs $271M); undefined when pretax ≤ 0 (GE FY2017, Infleqtion).
- (c) Above 2%. Gets wrong: misses Infleqtion's net-loss correction (1.8%) and Boeing's 0.66–1.78% revisions.

**2.4 Estimate changes and prior filings** (recommendation changed: two prior 10-Ks)
- (a) (recommended) Bands < 10% / 10–25% / ≥ 25% of the 2.5 denominator, both directions; fetch two prior 10-Ks per company (about 28 requests), which also closes DS7. Why: the 3-year recurrence test needs three annual disclosures. Gets wrong: SPCX (no prior 10-K) and ETV (N-CSR) get no recurrence test.
- (b) Any quantified change is a note; prior 10-Ks wait for M06/M11. Gets wrong: Alphabet 2023 and Intel 2023 are judged alone.
- (c) Income-increasing changes only. Gets wrong: hides Amazon 2025 (NI −$1.0B).

**2.5 Estimate-share denominator**
- (a) (recommended) Company figures matched to the amount's tax basis and period; not meaningful when ≤ 0 or below 1% of revenue; segment share beside it only when stored or quoted. Why: always available; GE reads watch (2016) on either amount. Gets wrong: GE Power's 29%/45% segment view is hidden until segment profit is stored.
- (b) Segment profit when attributed. Gets wrong: missing for most names until 5.4; GE's 29%/45% exist only in the SEC order.
- (c) Company net income only. Gets wrong: divides pre-tax amounts by after-tax income; GE's bands do not change, but the error grows with the tax rate (illustrative: 35% rate, 1.54× overstatement).

**2.6 Recurring "one-time" charges** (new; outline Red Flag 3)
- (a) (recommended) `special_items`: restructuring, impairment, goodwill and inventory write-down tags plus FTS5 "non-recurring"/"one-time" in ≥ 3 of the last 4 fiscal years (starting value), their cumulative size against operating income, and the company-stated non-GAAP vs GAAP gap from stored releases, quoted, never computed (S5.8, D-M02-29). Why: the outline's named pattern; excluded "one-time" costs predict lower cash flows (Doyle et al. 2003; McVay 2006, to add as S-new-r2-10/11). Gets wrong: a genuine multi-year restructuring reads as recurrence (shown with its stated plan).
- (b) Leave it to Round 5's "excluding stated items" margin. Gets wrong: covers gross margin only; Rivian's write-downs show, but repeated charges below gross profit and the non-GAAP gap do not.
- (c) No signal. Gets wrong: GE's and Rivian's named pattern is never measured.

**2.7 How R2 applies in this round** (new; confirmation)
- (a) (recommended) Events, the M-score (via SGI = 1), `misstate_f` and the contract and deferred-revenue gaps are stage-neutral. The CFO/NI < 0.8 warning applies to mature, shake-out and decline; introduction, growth and unassigned or ambiguous stages get a note until the stage is confirmed. Accruals are shown against own history, with no warning. Why: the gaps are already relative to revenue growth; only cash conversion is mainly a growth effect. Gets wrong: a growth firm with real collection problems gets a note, not a warning (illustrative).
- (b) Everything stage-neutral. Gets wrong: young firms building receivables warn on growth.
- (c) All Round 2 flags become notes for introduction and growth. Gets wrong: a young firm's 4.02 or little r is only a note.

**2.8 Open 4.02 and other M04 outputs** (new)
- (a) (recommended) While a 4.02 is open (until the restated filing), every row reading the affected periods (CvD, gate, F/G/Z, guidance record) is marked "inputs under non-reliance" and shown as a warning; adds are not blocked (D16). Why: the owner sees the doubt without the engine overruling M01. Gets wrong: an M01 add can still trigger on figures the company disowns.
- (b) As (a), and the gate reads "incomplete" (no adds, as a gate fail). Gets wrong: a small, quickly restated error (illustrative: one quarter's revenue) stops adds for months.
- (c) No link. Gets wrong: M01 reads non-reliance figures with no mark.

**2.9 Where FCF growth lives** (new; outline l. 66–68)
- (a) (recommended) M04 `fcf_growth`: 3-year FCF growth and FCF margin, with A2 growth capex shown beside it, so FCF growing while building out reads as the outline's strong signal; information until D13 weights. Why: the outline calls it golden; no round measures it. Gets wrong: FCF growth off a near-zero base (not meaningful rule needed, as S2.1).
- (b) In M05 with capex. Gets wrong: the outline lists it under "Analyze the financials", and M05 is not built yet.
- (c) Not measured. Gets wrong: the outline's golden indicator is missing.
