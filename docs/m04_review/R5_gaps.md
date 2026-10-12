# Round 5 known gaps: closure report

Pack section: `docs/M04_DESIGN_PACK.md` lines 1980–2590 (Round 5). Gaps: the "**Round 5:**" bullets in Known gaps (lines 3485–3565), plus the New sources bullet on the Lev & Thiagarajan / Abarbanell & Bushee constructions. All reads were on 2026-10-12. No SEC request was made, and `.env` and `data\` were not read. "Search-index excerpt" means a web-search tool summarised a sec.gov page; this report did not fetch that page.

## Summary

| # | Gap | Status | Changes pack? |
|---|---|---|---|
| 1 | Dickinson (2011) primary: sign table and US transition rates | needs_owner_data | no |
| 2 | Lev & Thiagarajan / Abarbanell & Bushee gross-margin signal construction (also the New sources bullet) | partly_closed | no (wording of research item 3) |
| 3 | Kesavan & Mani operations benchmark | stays_open | no |
| 4 | Critique 19: Q5.1 placement; model-tag vocabulary | stays_open (bookkeeping) | no |
| 5 | Critique 27a: 5.2d assumes no stated cost-of-revenue items for Tesla and Target | closed (release level) | no (confirms) |
| 6 | Critique 27b: Invitae quarterly ex-items margin | partly_closed | no |
| 7 | Critique 27c: Intel 2021Q1 under 5.2b (needs 2019 quarters) | closed | **yes** |
| 8 | Critique 27c: Invitae quarters before 2020Q4 (needs 2018 quarters) | partly_closed | **yes** |
| 9 | Microsoft ~45% OpenAI share of commercial RPO | closed | **yes** |
| 10 | 8-K 1.02 co-filed with 2.03 (Tesla ×2, Rivian) | partly_closed | no |
| 11 | Invitae FY2022 stated per-unit amounts; Rivian credits | partly_closed | **yes** |
| 12 | Patatoukas (2012) via a summary; Asgharian & Liu via the abstract only | partly_closed | no (adds a candidate measure) |
| 13 | m04_customer review volume; live-check minutes | needs_owner_data / Part 7 | no |
| 14 | Pack-wide consolidation (critique 6, 15, 16, 17) | stays_open (bookkeeping) | no |

## Gap by gap

**1. Dickinson (2011) primary.** Status: needs_owner_data.
- Tried: TAR (paywalled); SSRN abstract 755804 (HTTP 403); a web search for a free copy. Only third-party Scribd uploads were found, and they were not used.
- The sign table still rests on the two matching secondaries (S-new-r5-1, S-new-56). Dickinson's US transition rates stay unknown.
- Owner action: obtain the TAR article (doi 10.2308/accr-10130), or accept 5.1a on the labelled secondaries. No SEC call is needed.

**2. Gross-margin signal construction (Lev & Thiagarajan 1993; Abarbanell & Bushee 1997).** Status: partly_closed. Neither primary is free (JAR; the Penn repository returned 403).
- **Secondary read in full:** Seng & Hancock (2012), "Fundamental Analysis and the Prediction of Earnings", *Int. J. Business and Management* 7(3):32, Table 1 (open access, doi:10.5539/ijbm.v7n3p32). It reproduces the LT/AB signals:
  - GM signal = %ΔSales − %ΔGross margin.
  - For every variable, %Δx = (x_t − E[x_t]) / E[x_t], where E[x_t] is the mean of the two prior years.
  - "Gross margin" is gross profit in dollars (Sales − COGS), not the margin rate.
  - Signals are signed so that a positive value is bad news for future earnings. The data are annual.
- **A second secondary differs.** Gupta, Pevzner & Seethamraju (2005 WP, assets.csom.umn.edu/assets/50765.pdf) write the LT inventory signal as a plain annual % change. The expectation base therefore still needs the primary.
- **Mixed evidence.** Seng & Hancock (global sample, 1990–2000) found the GM signal insignificant in several models.
- **Worked on Invitae** (pack figures; FY2018 gross profit $67.6M is secondary, Motley Fool):

  | Year | %ΔSales | %ΔGross profit | Signal |
  |---|---|---|---|
  | 2020 | +53.4% | −2.2% | +55.6 |
  | 2021 | +85.5% | +24.1% | +61.4 |
  | 2022 | +39.5% | +2.6% | +36.9 |

  All three are bad news. For Rivian the signal is not meaningful, because gross profit is ≤ 0.
- **Effect on the pack.** Research item 3 should say: % change in gross *profit dollars* against the mean of the two prior years, annual. That is a different construction from 5.2a, which uses pp of the rate, quarterly year over year. The recommended option is unchanged. The signal could be shown as MY information only.

**3. Kesavan & Mani (2013) operations benchmark.** Status: stays_open.
- The abstract (Penn State Pure page) says only that the authors used benchmarking metrics from the operations management literature.
- The likely base is the Gaur, Fisher & Raman (2005) adjusted inventory turnover (gross margin, capital intensity, sales surprise). That link is an inference only.
- Tried: INFORMS (paywall), the UVM replication thesis (403), the LSU repository (403).
- S5.6's 15 pp inventory gap stays an unsourced starting value, as the pack already says.

**4. Critique 19 (partial).** Status: stays_open (bookkeeping).
- Q5.1 is presented with Round 1 under the owner's sequencing, so the Round 1 brief owns its text.
- The model-tag vocabulary belongs to Q3.4 (Round 3 brief).

**5. 5.2d: no stated cost-of-revenue items for Tesla and Target.** Status: closed at release level.
- **Tesla Q1 2023 Update** (digitalassets.tesla.com/tesla-contents/image/upload/IR/TSLA-Q1-2023-Update):
  - No dollar charge sits in cost of revenues for Q4 2022 or Q1 2023.
  - The only one-off line is "Restructuring and other", which is in operating expenses.
  - The operating-income drivers are stated qualitatively: lower ASP, higher raw material, commodity, logistics and warranty costs, the 4680 ramp, lower credit revenue and factory under-utilisation.
- **Target Q1 2022 release** (corporate.target.com/press/release/2022/05/target-corporation-reports-first-quarter-earnings):
  - Markdowns are "driven largely by inventory impairments", with no amount given.
  - The adjusted-EPS "Other" item is $20M pretax. It is described as unrelated to current-period operations, and its line is not stated.
  - The rate went 30.0% → 25.7%: −4.3 pp on the rounded rates. The pack's −4.4 uses unrounded rates, so no change is needed.
- **Target Q2 2022 release** (…/2022/08/target-corporation-reports-second-quarter-earnings): no impairment amount, and no reconciling items. The rate went 30.4% → 21.5%.
- So 5.2d = 5.2a for both companies is confirmed. The residual is that the 10-Q text was not read.

**6. Invitae quarterly ex-items margin.** Status: partly_closed.
- Invitae's earnings releases state a non-GAAP gross profit that excludes amortization of acquired intangibles. That is a quarterly, company-stated ex-items figure.
- Found (press-release reprints and search-index excerpts):

  | Quarter | Non-GAAP gross profit | Margin |
  |---|---|---|
  | Q1 2020 | $26.5M | 41.3% |
  | Q2 2020 | $8.0M | 17.3% |
  | Q3 2020 | $26.8M | 39.0% (company says 39%) |

- The 2019 comparatives were not found, so 5.2d's year-over-year values are still not computed. Q2 2020 collapses on either basis.
- Design note: EX-99.1 non-GAAP reconciliations are a quarterly source of stated items for 5.2d and S5.4.
- Probe P2 (optional).

**7. Intel 2021Q1 under 5.2b.** Status: closed (primary, intc.com releases).

| Quarter | Revenue $M | GAAP GM | YoY pp | TTM revenue YoY |
|---|---|---|---|---|
| 2019Q1 | 16,061 | 56.6% | | |
| 2020Q1 | 19,828 | 60.6% | | 75,732 |
| 2020Q2 | 19,728 | 53.3% | | |
| 2020Q4 | 19,978 | 56.8% | −2.0 | |
| 2021Q1 | 19,673 | 55.2% | **−5.4** | 77,712 (**+2.6%**) |
| 2021Q2 | 19,631 | 57.1% | +3.8 | |

- Basis: FY2019 = 71,965 and FY2020 = 77,867, so TTM = FY − Q1 + Q1.
- **5.2b fires at 2021Q1.** The pack's "probably" becomes confirmed.
- **5.2a stays silent**, because the quarters before and after do not qualify.
- Q2 2021 also has falling TTM revenue (77,615 against 78,955).
- Sources: intc.com press releases 1086 (Q1 2020), 1439 (Q4/FY2020), 1460 (Q1 2021) and 1485 (Q2 2021).
- Pack change: in the 5.2 table notes and in Q5.2(b)'s "Gets wrong", replace "probably" with "fires at 2021Q1 (−5.4 pp; TTM +2.6%)".

**8. Invitae quarters before 2020Q4.** Status: partly_closed. **R12 fires a year earlier than the pack says.**

| Quarter | Revenue $M | Gross profit $M | GM | YoY pp | TTM revenue YoY |
|---|---|---|---|---|---|
| 2018Q1 | 27.7 | 9.6 | 34.7% | | |
| 2018Q2 | 37.3 | 16.9 | 45.3% | | |
| 2018Q3 | 37.4 | 16.9 | 45.2% | | |
| 2018Q4 | 45.4 | 24.2 (FY − 9M) | 53.3% | | |
| 2019Q1 | 40.6 | 19.3 | 47.5% | +12.8 | |
| 2019Q2 | 53.5 | 25.5 | 47.7% | +2.4 | |
| 2019Q3 | 56.5 | 24.4 | 43.2% | −2.0 | |
| 2019Q4 | 66.2 (FY − 9M; reported 66.3) | 29.5 (FY − 9M) | 44.5% | **−8.8** | +46.8% |
| 2020Q1 | 64.2 | 23.8 | 37.1% | **−10.4** | +49.7% |
| 2020Q2 | 46.2 | 3.2 | 6.9% | −40.7 | +31.8% |
| 2020Q3 | 68.7 | 22.1 | 32.2% | −11.0 | +25.2% |
| 2020Q4 | 100.5 (FY − 9M) | 32.2 (FY − 9M) | 32.0% | −12.5 | +29.0% |

- **Cross-check.** The derived 2020Q4 row reproduces the pack's 32.0% and +29.0%.
- **5.2a** opens at 2019Q4 and **fires at 2020Q1** (10-Q, about May 2020), not at 2021Q1.
- **5.2b fires at 2019Q4** (FY2019 10-K, early 2020), so it is still one quarter earlier than 5.2a.
- **Robustness.** Excluding Q4 2018's one-time Medicare payment (about $1.9M, GenomeWeb), 2018Q4 is 51.3% and the drop is still −6.7 pp.
- **New case.** In 2020Q2, quarterly revenue fell 13.6% (COVID) while TTM revenue rose 31.8%. The TTM test therefore lets R12 run on what is an under-absorption cause (volume). The cause finder must allow "volume/scale" when the quarter's own revenue fell.
- **Sources.** Company releases, via BioSpace, StockTitan and 1stOncology reprints and search-index excerpts of the 8-K exhibits. The FY2018 gross profit of $67.6M and the 2018Q4 revenue come from Motley Fool and GenomeWeb (secondary).
- **Pack changes:**
  - Worked example: "R12 opens by 2021Q1" becomes "fires at 2020Q1", about 2.5 years before the FY2022 survival-gate failure.
  - S5.11: the regression case fires at 2020Q1.
  - The 5.2 table: add the 2019Q4 and 2020Q1 rows.
  - The "Result" line: (b) is one quarter earlier (2019Q4).
- Probe P1 confirms the figures from XBRL.

**9. Microsoft's OpenAI share of commercial RPO.** Status: closed. Microsoft's own wording, from the FY26 Q2 call (2026-01-28; microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q2):
- Commercial RPO was $625B, +110%, with a weighted average duration of about 2.5 years.
- Amy Hood: "Approximately 45% of our commercial RPO balance is from OpenAI."
- In Q&A, about 55% (roughly $350B) relates to the rest of the portfolio. The OpenAI share is therefore about $281B (computed).
- **FY26 Q4 call** (…/earnings-fy-2026-q4):
  - Commercial RPO was $678B (+84%), +25% excluding OpenAI, with a weighted average duration of 2.3 years.
  - "All sequential commercial RPO growth" came from customers outside frontier-model companies.
  - No OpenAI share was given. If the OpenAI balance did not grow, its share at 2026-06-30 is at most about 41% (281/678; a derived bound).
- **Pack changes:**
  - S-new-r5-9: replace Silicon UK with the Microsoft IR pages.
  - The note becomes company-stated text (call remarks; D14 grade A), not grade B. Keep it a text note, never XBRL.
  - Failure-mode row "RPO": "grade-B note" becomes "company-stated note, dated".

**10. 8-K 1.02 co-filed with 2.03.** Status: partly_closed.
- **Tesla 2023-01-25** (accession 0001564590-23-000799). Read from ir.tesla.com's copy (`_flysystem/s3/sec/000156459023000799/tsla-8k_20230120-gen.pdf`):
  - Item 1.01: a new $5.0B senior unsecured revolving credit facility (Citibank as agent).
  - Item 1.02: the ABL Credit Agreement (Deutsche Bank as agent) was terminated, with no borrowings outstanding and no penalty.
  - Item 2.03 incorporates Item 1.01.
  - So this one is financing, confirmed.
- **Tesla 2026-09-29** (search-index excerpt only): the existing revolving credit agreement was terminated on entry into new Credit Agreements. Likely financing; not verified.
- **Rivian 2025-06-12** (search-index excerpt only): green notes closed to redeem the $1.25B floating-rate senior secured notes due 2026. The 1.02 is probably that discharged indenture; the items are not confirmed.
- Probe P5.

**11. Invitae FY2022 per-unit; Rivian credits.** Status: partly_closed (search-index excerpts of the 10-Ks).
- **Invitae FY2022 10-K:**
  - Stated revenue per unit was **$388** (2021: $380), "changes in payer and product mix".
  - Stated cost per unit was **$323** (2021: $298).
  - So stated gross profit per unit was $65, against $77 computed. The stated base is again narrower: $388 against $400 computed.
- **Rivian FY2025 10-K/ARS revenue disaggregation:**
  - New EVs $3,639M, regulatory credits **$197M** (2024: **$333M**), software and services $1,551M. These sum to the $5,387M total.
  - New EVs plus credits = $3,836M, against $3,830M of automotive revenue. So credits do sit inside automotive revenue, within $6M.
- **Revised ex-credit automotive gross profit per unit:**
  - FY2025: −$14.9k (was −$14.7k, derived from 191).
  - FY2024 on 333: −$29.9k (was −$29.7k on 325).
  - The flags are unchanged.
- **New KPI-definition case:** FY2024 credits are $325M in the Q4 2024 letter but $333M in the FY2025 10-K.
- Q4 2025's $270M decrease is confirmed by Electrek (secondary).
- Probe P3 and P4.

**12. Patatoukas (2012); Asgharian & Liu (2017).** Status: partly_closed.
- **Asgharian & Liu full text read** (41 pp, May 2017; swlb1.aeaweb.org/conference/2018/preliminary/paper/dGQ3hGSZ):
  - Customer concentration = Σ_j (sales to major customer j ÷ total sales)², which is the Patatoukas (2012) HHI.
  - Uniqueness = inverse Hoberg–Phillips product similarity.
  - The major-customer effect is larger with higher concentration and with less unique products.
  - Concentration matters mainly when customers suffer adverse shocks.
  - The customers' own product uniqueness does not matter.
- **NVIDIA customer HHI:** FY2024 0.017, FY2025 0.039, FY2026 0.068.
- **Candidate refinement** (not a change in option): show `customer_hhi` beside revenue at stake, and weigh negative customer news more than positive.
- Patatoukas (2012) itself is still read only through summaries (Haas newsroom; Alpha Architect). The paywalled TAR primary is unread.

**13. m04_customer volume; live-check minutes.** Status: needs_owner_data / Part 7.
- The volume can be measured without SEC calls from the owner's `event` table (migration 0006):
  `SELECT item, COUNT(*), COUNT(DISTINCT cik) FROM event WHERE item IN ('1.01','1.02','2.03') AND filed >= '2023-10-01' GROUP BY item;`
  Then count the 1.02 accessions that also carry 2.03.
- The minutes depend on instance sizes and are measured in the Part 7 live check.

**14. Pack-wide consolidation.** Status: stays_open (bookkeeping).
- Owned by the step-4 drafting and critic pass: the D-M04-1 change table, all review kinds, enum encoding and the signals-out table.
- Round 5 supplies its own rows. It also lists for owner confirmation the stage-neutral reading of R12 and the customer-row implementing rules.

## Combined probe (owner runs)

No existing script does these reads. `run_live.py` only runs `pytest -m live`, and `fetch_stats.py` reads `fetch_log`. A small one-off live test or `scripts/probe_m04_r5.py` on the engine's SEC client (it takes `refresh.lock`) is needed.

| ID | Endpoint | Target | Requests |
|---|---|---|---|
| P1 | companyconcept | NVTA (CIK0001501134): `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues` (pre-2018 fallback), `CostOfRevenue`; rows for fp Q1–Q3/FY, FY2018–FY2020 | 3 |
| P2 (optional) | Archives EX-99.1 | NVTA earnings releases 2019Q4–2022Q3: non-GAAP gross profit and the prior-year column | about 11 |
| P3 | Archives document | NVTA FY2022 10-K (0001501134-23-000024): the per-unit sentences | 1 |
| P4 | Archives R page | RIVN FY2025 10-K (0001874178-26-000008): revenue disaggregation note | 1–2 |
| P5 | Archives document | TSLA 8-K 0001628280-26-063820 `tsla-20260929.htm`; RIVN 8-K filed 2025-06-12 (accession from the stored submissions) | 2 |

Total: about 8 required requests, plus about 11 optional.

Owner data (no SEC call): the `event` query in item 13. Owner reading: the Dickinson (2011) TAR article.
