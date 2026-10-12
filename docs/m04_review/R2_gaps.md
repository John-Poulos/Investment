# Round 2 — Known gaps check (earnings quality)

Read 2026-10-12. Scope: the 10 "Round 2" bullets in `docs/M04_DESIGN_PACK.md` Known gaps (lines 3501–3510) and the "Beneish (1999) ACCR definition" item from the "New sources" bullet (line 3560). No SEC host was requested. Non-SEC hosts used: GE's own annual-report PDFs, retrieved from the Internet Archive copy of ge.com/investor-relations; Amazon's IR CDN; NVIDIA's IR CDN; abc.xyz; Cornell LII; Audit Analytics; and the press (secondary).

**GE sources used below** (company-published PDFs, Internet Archive captures of ge.com; read 2026-10-12):
- **GE-AR17**: the 2017 Annual Report with the FY2017 10-K. https://web.archive.org/web/20180412212038/https://www.ge.com/investor-relations/sites/default/files/GE_AR17.pdf. Caveat: this print carries "DRAFT" in the 10-K page headers, but its figures match the XBRL values in the pack (CFO 10,426 / −244; NI −5,786 / 8,831). Re-check each quoted sentence against the EDGAR text at build.
- **GE-AR18**: the FY2018 10-K, filed 2019-02-26. https://web.archive.org/web/20190407004205/https://www.ge.com/investor-relations/sites/default/files/GE_AR18_10k.pdf
- **GE-AR19**: the FY2019 10-K, filed 2020-02-24. https://web.archive.org/web/20200324031828/https://www.ge.com/investor-relations/sites/default/files/GE_AR19_10-K.pdf

## Summary
| # | Gap | Status | Changes pack? |
|---|---|---|---|
| 1 | Alphabet 2023: NI +$3.0B and the prior 4-year life | closed | wording only |
| 2 | GE NI residuals: what the amounts are measured on; LIFO→FIFO | closed | **yes** |
| 3 | Causes of GE's CFO shifts; −152 vs restricted cash; cause of the revenue recast | partly closed | **yes** |
| 4 | Tag GE used for its 2015 contract assets | needs live probe | no |
| 5 | Did GE's own 10-Ks quantify the estimate changes? | closed (re-check at build) | **yes** |
| 6 | Scratch M-score/Dechow mapping; Tesla, GFS, SPCX; NVDA/MRVL F | needs owner data | no |
| 7 | ASU attribution of the 2016–18 CFO shifts; how many steps the text will explain | partly closed | no |
| 8a | m04_estimate volume | partly closed | no |
| 8b | Part 3 download time | needs live probe | no |
| 8c | "SPCX has no prior 10-K" | partly closed | no |
| 9a | 21% tax approximation | partly closed | **yes** (rule by year) |
| 9b | $0.1M floor, 25% non-operating share, 24-month baseline, 5-a-week cap | stays open | no |
| 10 | Pack-level critique parts 15, 16, 19, 20 | stays open (pack consolidation) | no |
| 11 | Beneish (1999) ACCR definition | stays open | no |

## Findings

**1. Alphabet 2023: closed.** The pack's own "New sources" entry S-new-22 (line 3665) already records that Note 1 was read through R10 on 2026-10-12: servers went from 4 to 6 years and certain network equipment from 5 to 6 years, effective with fiscal 2023. The 2023 effect was depreciation −$3.9B and net income +$3.0B ($0.24 per share). Alphabet's Q4 2023 release reports the same effects, and also the quarter alone (−$983M depreciation, +$765M net income). That release was seen through a search-engine summary, not fetched. The Fly/TipRanks (secondary) agrees. Alphabet's IR FAQ (abc.xyz/investor/faqs-and-general-information) confirms the January 2023 change to six years but gives no amounts. Action: drop "re-confirm" from Round 2 item 6, from the Alphabet cash-conversion table and from the Known gaps. The share stays 3.0 ÷ 73.795 = 4.1% → note.

**2. GE net-income residuals: closed. Both residuals fall to zero once the change in the noncontrolling-interest (NCI) share is accounted for.**
- What the amounts are measured on: GE-AR18 Note 1 (PDF p.108) states the ASC 606 effect as a decrease to "revenues and earnings (loss) from continuing operations": 2017 −2,224 / −2,668; 2016 −220 / −1,182. These are the same amounts as the 8-K, and they are before NCI.
- LIFO→FIFO (GE-AR18 Note 1, p.111): continuing operations fell by $147M (2016) and $124M (2017). The note states there was no cash-flow effect.
- NCI. The 2017 10-K shows net earnings 8,540 / −6,056 with NCI −291 / −270. GE-AR18 shows 7,211 / −8,849 with NCI −289 / −365 (cash-flow statements, GE-AR17 p.138, GE-AR18 p.100).

| Step | Δ NetIncomeLoss | ASC 606 | LIFO→FIFO | Residual (attributable to GE) | Δ NCI share | Residual on net income incl. NCI (`ProfitLoss`) |
|---|---|---|---|---|---|---|
| 4: FY2016 | −1,331 | −1,182 | −147 | **−2** (was −149) | +2 | **0** |
| 5: FY2017 | −2,698 | −2,668 | −124 | **+94** (was −30) | +95 | **−1** |

- Effect on question 2.3: step 4 is no longer queued under any option. Step 5 is queued under (a) (tolerance 28.9) and (b) (57.9) **only if** the engine tests NetIncomeLoss without allowing for NCI. Recommendation (new S2.6 rule): when a stated amount is "earnings from continuing operations", match it against the measure that includes NCI (`ProfitLoss`), or label the NCI change mechanically. GE then queues no net-income residual.
- Fixture rows 4–5 change: labels `accounting_change` (ASC 606 + LIFO→FIFO), residual 0 / −1. The text needed is the later 10-K itself (GE-AR18). The 8-K is not needed for net income.

**3. Causes of GE's cash-flow shifts: partly closed.**
- **Step 7 (CFO FY2017 −4,394; total −152): closed.** GE-AR18 Note 1 (p.110) on ASU 2016-15: GE moved $553M of the Deferred Purchase Price receipts from operating to investing cash for 2017, plus an *incremental $3,858M* for 2017 after a daily-computation interpretation. Together that is −4,411 against the CFO step of −4,394, so the CFO residual is **+17**, below the (a) tolerance of 52. The −152 total residual is restricted cash under ASU 2016-18. Cash at year-end rose by 673 between the two versions (44,724 − 44,051) and at the start of the year by 826 (50,384 − 49,558). The difference, −153, matches −152 within rounding. The 668/654 in the note is continuing operations only; the discontinued-operations parts are 5 and 172. The pack's "553 quantified … amount does not match → review" is replaced: step 7 is fully explained.
- **Step 6 (CFO FY2016 +1,404): cause still unstated.** Line by line (GE-AR17 p.138 against GE-AR18 p.100): continuing CFO 6,099 → 7,503 (+1,404); "All other financing activities" −1,274 → −2,607 (−1,333); CFI −67. The +4 total residual is restricted cash (beginning-of-year cash +819, end +826 → +7, within ±3 rounding). GE-AR18 gives only the generic "We have reclassified certain prior-year amounts to conform to the current-year's presentation" (Note 1, p.102), and ASU 2016-15 is applied to 2017–2018 only. So the `cf_shift_up` +1,400 stays a concern with no cause, as the pack says. Only its +4 residual is now explained.
- **Step 8 (CFO FY2017 +522 in the 2019 10-K): suggested cause, no amount.** GE-AR19 (p.66) shows discontinued-operations CFO −968 → +714 and continuing 7,000 → 5,840. This coincides with the reclassification of Baker Hughes and Transportation to discontinued operations (Note 2, p.76). No amount is stated, so the step stays a mechanical `cf_shift_up` with the passage attached as the suggested cause.
- **Revenue step 3 (FY2017 −18,964, NI unchanged): cause found, amount does not tie.** GE-AR19 Note 2: "Discontinued operations include our Baker Hughes and Transportation segments". 2017 sales of the discontinued operations were Baker Hughes 17,180 and Transportation 3,935, total 21,115. That leaves 2,151 unexplained, possibly sales between GE and those businesses that were eliminated before (inference). The label stays `reclass` (mechanical). The passage is attached as the cause.
- **New mechanical rule suggested (S2.6):** when CFO + CFI + CFF changes between versions and the beginning and ending cash balances changed by amounts whose difference equals that change, label it `restricted_cash` (ASU 2016-18). A switch to `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents` is the tag-level sign. With this rule and the NCI rule, GE's four residuals all close. The remaining items are the step 6 shift (watch flag) and the attached causes for steps 3 and 8.
- **Effect on 2.3:** option (a) keeps its main reason (Infleqtion's two steps). Its "Why … still queues GE's four residuals" must be rewritten: with the rules above, GE queues none. Option (b)'s drawback "lets GE's FY2017 net-income residual (−30) pass" no longer applies. Option (c)'s "misses all four GE residuals" no longer applies either. The tolerance table rows for steps 4–7 change accordingly.

**4. GE's 2015 contract-asset tag: needs live probe.** The value 21,156 sits only in the 2016 10-K (pack, S-new-r2-6). No GE annual report PDF for 2016 was captured: the Internet Archive holds only `GE_AR16_ISR.pdf` and an HTML stub for `GE_AR16.pdf`. A tag name needs the instance anyway. Probe: 1 Archives request for the FY2016 10-K XBRL instance (accession 0000040545-17-000010), then find the element whose 2015-12-31 value is 21,156. It is already in the pack's Part 6 live check (S2.9), so it adds no request.

**5. Did GE's own 10-Ks quantify the estimate changes? Closed. They did, at company level, and the amount was later restated.**
- GE-AR17, critical accounting estimates (p.94): revisions to the estimated profitability of long-term service agreements "increased earnings by $2.1 billion, $2.2 billion and $1.4 billion in 2017, 2016 and 2015". GE-AR17 Note 9 (p.161): 2017 contract assets rose by $3,699M, mainly from a $2,131M change in estimated profitability (Power $1,301M, Transportation $361M, Aviation $250M, Oil & Gas $219M).
- GE-AR18 (p.57), after ASC 606: the same revisions "decreased earnings by $(0.2) billion in 2018 and increased earnings by $0.5 billion and $0.7 billion in 2017 and 2016". **The estimate-change amount was itself restated** (2016: $2.2B → $0.7B).
- Effect on the S2.7 worked example. A company-figure share from GE's own filing, first-reported, treated as pre-tax: **2016: 2,200 ÷ 9,030 = 24.4% → watch** (just under 25%), against 15.5% from the SEC order's lower bound. FY2017 stays `not_meaningful` (pretax loss). The nine-month 2017 figure (28.9%) still rests on the order, because the 10-Ks give annual amounts only.
- Recommendations:
  1. The fixture uses GE's own grade-A amount, with the order's amount shown beside it.
  2. S2.7 stores each estimate amount by filing version and uses the as-of version, because the amount can be restated.
  3. Add "estimated profitability" and "adjustment of earnings" to the S2.7 FTS5 phrase list. GE's sentences do not contain "change in estimate". "Cumulative catch up" without a hyphen already matches, because the `porter unicode61` tokenizer splits hyphens (`src/engine/search/query.py`).
- Whether GE called this amount pre-tax is not stated ("adjustment of earnings"). Mark the basis as assumed.
- Re-check probe: 1 Archives request for the primary document of the FY2017 10-K (filed 2018-02-23), to confirm the quoted sentences in the filed text, given the "DRAFT" headers in the print.

**6. Scratch mapping; Tesla, GFS, SPCX; NVDA/MRVL F: needs owner data (0 SEC requests).**
- `src/engine/sec/xbrl_facts.py` `store_facts` stores *every* companyfacts fact (all taxonomies and forms, with filed date and accession) in `fact`. So recomputing M and F, the Tesla aliases, GFS on `ifrs-full` and the restatement walk all run locally.
- NVIDIA FY2026: NVIDIA's CFO commentary (IR CDN, https://s201.q4cdn.com/141608511/files/doc_financials/2026/Q426/Q4FY26-CFO-Commentary.pdf) states that cash, cash equivalents and marketable securities were $62.6B. A third-party extraction (sec-api.io, secondary) splits this into 10,605 cash and 51,951 marketable securities under a different element. So the input exists under a new tag, and the `short_term_investments` alias list needs that tag.
- SPCX: M and F need annual statements, so they are not computable until its first 10-K (FY2026, due about Q1 2027).
- Probe (owner, read-only local script; no existing script does this; `check_tickers.py` shows only the entity):
  - For NVDA, MRVL, TSLA and GFS, list the `fact` tags at each fiscal year-end;
  - for NVDA FY2026, list balance-sheet instant tags with values near 51,951;
  - for MRVL FY2026, list `Proceeds*` tags;
  - for TSLA FY2022–23, list `LongTermDebt*` and `Proceeds*`;
  - then recompute the Round 2 score table from `fact`.

**7. ASU attribution of the CFO shifts: partly closed.**
- Amazon's FY2017 10-K (Amazon IR annual-report PDF, https://s2.q4cdn.com/299287126/files/doc_financials/annual/Amazon_AR.PDF, PDF pp.28 and 59) confirms ASU 2016-09, adopted in Q1 2017. Excess tax benefits of $119M (2015) and $829M (2016) were moved from financing to operating cash, and the selected data adds $78M (2013) and $6M (2014). That is a stated amount, so the text label will apply.
- GE (not in the 21) confirms ASU 2016-15 and 2016-18 with amounts (gap 3).
- Apple (4), Alphabet (3), Meta (2), Boeing (1) and Intel 2023 are not read.
- Early yield evidence: in both later filings read, the text states amounts, so the labels apply. The overall yield is still unknown until the Part 3 dry run, which measures it; no separate probe is needed.

**8a. m04_estimate volume: partly closed.**
- Audit Analytics (S-new-21, re-read): an average of 500.6 material estimate changes a year (2000–2018) across SEC registrants; the number of filers is not stated.
- Watchlist evidence from the press (secondary: Bloomberg Tax/Accounting Today on Meta; Interface Media/SiliconANGLE on Amazon and Microsoft) shows about one useful-life change a year among the hyperscalers:
  - Meta 2025: depreciation −$2.92B, NI +$2.59B;
  - Amazon 2024: 5 → 6 years, about +$3.2B operating income;
  - Microsoft FY2023: 4 → 6 years, a $3.7B forecast.
- Each is roughly 3–5% of profit (inference from approximate profit levels). So the *note* volume is about 2–4 a year, while the *review* kind (share ≥ 10%) stays rare. The 1–2 a year estimate is reasonable as a ceiling.
- Verify these shares from `fact` at Part 6.

**8b. Part 3 download time: needs live probe.** No size was measured: the GE PDFs are prints, not EDGAR HTML. Measure it in the Part 3 live check itself. `fetch_log` already records each request (`scripts/fetch_stats.py` summarises request rates). Add bytes per document to that run's log. No separate probe.

**8c. "SPCX has no prior 10-K": partly closed.** Evidence in the repo:
- prices start 2026-06-12 (DESIGN.md);
- pack Round 1 case 21 says "no TTM until the first 10-K";
- Round 4 annualizes H1 because a TTM is unavailable.

The "about 14" count in 2.4a already excludes SPCX (16 − ETV − SPCX), so no figure changes. Confirm with 0 SEC requests: the owner runs a local query of the stored filing index for SPCX's CIK, `form IN ('10-K','10-K/A')`. Otherwise, 1 submissions request.

**9a. 21% tax: partly closed.** 26 U.S.C. §11(b) sets the corporate rate at 21%, for taxable years beginning after 2017-12-31 (Pub. L. 115-97 §13001(c)(1)); Cornell LII, https://www.law.cornell.edu/uscode/text/26/11. The top rate before 2018 was 35% (the former §11(b)). Recommendation: tax the non-operating items at the filer's own statutory rate from the tax reconciliation (`EffectiveIncomeTaxRateReconciliationAtFederalStatutoryIncomeTaxRate`) when that is tagged. Otherwise use 21% for 2018 and later and 35% before 2018. Label it an approximation either way. Today's examples are 2023–2025, so no figure changes.

**9b. $0.1M floor, 25% non-operating share, 24-month baseline, 5-a-week cap: stay open.** No published source was found. These are labelled starting values. The cap has a project precedent: M02's owner-approved 10/week (D-M02-10) and the rank–cap–flush lesson (LESSONS.md, D-M02-51).

**10. Critique parts 15, 16, 19, 20: stay open.** These are pack bookkeeping, owned by the pack consolidation step (the consolidated review-kind table, the signal enum encoding, moving 5.1 into Round 1, and aligning S1.1's form list). Note for 19: the S2.1 CFO/NI warning still needs the stage.

**11. Beneish (1999) ACCR definition: stays open.**
- The FAJ paper (55(5):24–36, doi:10.2469/faj.v55.n5.2296) is members-only at CFA Institute. IDEAS lists it as subscriber-only. The author's Kelley page returned 401, and ResearchGate returned 403. The Scribd and Academia copies were not used (uncertain rights).
- Secondary sources split: several describe the 1999 TATA as working-capital accruals (Δcurrent assets − Δcash − Δcurrent liabilities + Δcurrent maturities of LTD + Δincome tax payable − depreciation and amortization, all ÷ total assets). The teaching note (S-new-14) and Wikipedia use (income from continuing operations − CFO) ÷ total assets.
- No change to S2.3: it already names the ACCR variant in the method. Keep the cash-flow form, which is consistent with S-new-13, and label it "cash-flow variant; the 1999 original reportedly uses working-capital accruals (secondary, unverified)". The owner can obtain the paper through the DOI if wanted.

## Combined probe (for the owner's one run)
- Archives: GE FY2016 10-K instance (already in Part 6) and the GE FY2017 10-K primary document (1, re-check).
- Local, read-only, 0 SEC requests: `fact` tag listings and score recompute (gap 6), and the SPCX 10-K query (8c).
- Measured in the Part 3 run: download sizes and times (8b), and the text-label yield (7).
