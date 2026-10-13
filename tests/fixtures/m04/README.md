# M04 fixtures (Parts 1a–1b)

Hand-built, not recorded: Claude may not call SEC (CLAUDE.md, M04_BUILD_LOG "Workflow").
Byte-exact once written (D24). Companyconcept files follow SEC's companyconcept JSON layout
(one tag per file, fetch-date suffix per SB.6; the date is the build date). R1 pages follow
EDGAR's R-page HTML layout (`table.report`, `th.tl` title, `td.pl` labels).

| File | Figures and their source | Placeholders |
|---|---|---|
| mu_us-gaap_Revenues_20261012.json | MU FY2018 revenue 30,391 ($M) first filed 2018-10-15 under `Revenues` (M04_DESIGN_PACK lines 49, 3574, 3588); FY2017 20,322 | accession numbers |
| mu_us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax_20261012.json | FY2018 30,391 re-filed 2019-10-17 under the ASC 606 tag; FY2019 23,406 | accession numbers |
| wdc_us-gaap_Revenues_20261012.json | WDC FY2023 revenue 12,318 in the FY2023 and FY2024 10-Ks (M04_DESIGN_PACK 401, 2629) | accessions; filed dates approximate; tag split chosen to exercise "time before tag priority" |
| wdc_us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax_20261012.json | FY2023 recast to 6,255 after the SanDisk separation (pack 2629) | accession; filed date approximate |
| googl_us-gaap_NetIncomeLoss_20261012.json | Alphabet 2023 net income in a DEF 14A, accession 0001308179-26-000342 filed 2026-04-24 (pack line 53) | 10-K accessions and filed dates; the value 73,795 is Alphabet's reported 2023 net income |
| nvta_dei_EntityPublicFloat_20261012.json | Invitae float $6.8B at 2021-06-30, $569.8M at 2022-06-30; FY2022 10-K filed 2023-02-28 (PROBE_RESULTS S2) | accessions; FY2021 10-K filed date |
| nvta_dei_EntityCommonStockSharesOutstanding_20261012.json | Cover shares 260,674,728 (2023-05-05) and 267,014,064 (2023-08-04) (PROBE_RESULTS S2) | accessions; filed dates approximate |
| meta_10k_fy2025_R1.htm | META FY2025 10-K cover: Class A 2,187,177,748 + Class B 342,377,716 = 2,529,555,464 at 2026-01-23, error-correction flag false (M04_BUILD_LOG Part 1a) | layout: classes as row groups |
| mstr_10q_2011q2_R1.htm | MSTR Q2 2011 10-Q cover: Class A 8,217,394 + Class B 2,492,830 at 2011-07-27 (M04_BUILD_LOG Part 1a; probe verified the format to 2011) | layout: classes as column headers |
| spcx_10q_2026q2_R1.htm | SPCX 10-Q cover has per-class "Entity Common Stock, Shares Outstanding" rows, Class A and Class B (PROBE_RESULTS S3; only labels were printed) | **share counts and cover date are illustrative**; the live check captures the real ones |
| goog_inc_10q_2009q2_R1.htm | Google Inc. Q2 2009: R1 is the balance sheet, not a cover (PROBE_RESULTS S3) | **all amounts illustrative**; only "not a cover" is tested |

Split guard: MSTR's 10-for-1 split (trading split-adjusted from 2024-08-08) is entered in the
tests as a price-bar split factor, not as a fixture file.

## Part 1b

Trimmed companyfacts files (SEC companyfacts JSON layout, only the tags used; D-M04-75 form).
Values in $M from docs/m04_review/R1_brief.md (worked example), the probe log
logs/probe_m04_20261012-132155.txt (L1 Greenwald inputs, S4 NVIDIA instances) and
M04_BUILD_LOG Part 1b. Placeholders everywhere: accession numbers (`<cik>-<yy>-9nnnnn`),
filed dates (period end + 45 days), fiscal-year end dates where not stated (each company's
usual 52/53-week or calendar year end).

| File | Figures and their source | Placeholders |
|---|---|---|
| mu_companyfacts_trimmed_20261012.json | MU FY2012–FY2026 revenue (SalesRevenueNet / Revenues / ASC 606 tags as in L1), PP&E payments, Depreciation, PP&E net and gross (plain tags to FY2019, finance-lease-inclusive tags from FY2019) — L1. OCF FY2022 15,181 and FY2023 1,559 (R1 brief); FY2025 17,525 and FY2026 89,675 = the brief's FCF on total capex + capex (1,668 + 15,857; 58,963 + 30,712); FY2024 8,507 (Micron FY2024 10-K). FY2022–23 cost of goods sold 16,860 / 16,956 and gross profit 13,898 / −1,416 (GM 45.2% / −9.1%, brief). Q3 FY2023 (2023-03-03..06-01): revenue 3,752, cost 4,420, gross profit −668, diluted EPS −1.73 (brief's guidance case) | accessions; filed dates; fiscal year ends approximate (Thursday nearest Aug 31) |
| intc_companyfacts_trimmed_20261012.json | INTC FY2017–FY2025 revenue, PP&E net and gross (plain tags to 2022, finance-lease tags 2022–25), capex FY2022–25 (24,844 / 25,750 / 23,944 / 14,646), Depreciation FY2021–25 (FY2023 7,847: −29.5%) — L1 | accessions; filed dates; year ends (last Saturday of December) approximate; capex kept to FY2022–25 so the window is the brief's 4 years |
| msft_companyfacts_trimmed_20261012.json | MSFT FY2019–FY2026 revenue, PP&E net and gross FY2020–26, capex FY2025–26 (64,551 / 115,948), Depreciation FY2025–26 (22,000 / 34,300) — L1; Greenwald FY2026 78.7% (net) / 65.1% (gross) recomputed from them | accessions; filed dates |
| amzn_companyfacts_trimmed_20261012.json | AMZN purchases of property and equipment (PaymentsToAcquireProductiveAssets) FY2015 4,589, FY2016 7,804, FY2017 11,955 (Amazon 10-Ks); PP&E-tag FY2016 6,737 = 7,804 ÷ 1.158, the brief's "+15.8% on the fallback tag" | the PP&E-tag value is derived from the brief's gap, not read from a filing |
| nvda_companyfacts_trimmed_20261012.json | NVDA FY2022 PaymentsToAcquireProductiveAssets 976 (NVIDIA FY2022 10-K) | **FY2012 PP&E-tag value 100.0 is illustrative** (only the "definition changed" year is tested) |
| nvda_10k_fy2013_instance_trimmed.xml, nvda_10k_fy2021_instance_trimmed.xml | `nvda:PurchasesOfPropertyAndEquipmentAndIntangibleAssets` FY2013 183.3M (183,300,000 to the probe's printed precision) and FY2021 1,128.0M — probe S4; one us-gaap fact kept in the FY2013 file to show the extension-only reader | one context and unit each; namespaces as in the filings' prefixes |
| nvda_10k_fy2013_index.htm, nvda_10k_fy2021_index.htm | EDGAR filing index pages of 0001045810-13-000008 and 0001045810-21-000010 with the instance hrefs probe S4 read (nvda-20130127.xml, nvda-20210131_htm.xml) | trimmed to the two tables; sizes illustrative |

Guidance rows, releases, calls and corpus sentences in `tests/test_financials_1b.py` are
entered in the test: MU Q3 FY2023 ($3.70B ± 0.20, (23.0)% ± 2.5, ($1.79) ± 0.07) and Intel
FY2022 ($76.0B → $65–68B → $63–64B; actual $63,054M) from the R1 brief; Intel's January and
April 2022/2023 release patterns from the brief's guidance table; the withdrawal sentence
in the January 2023 call is **illustrative** (the brief says the call "reportedly" gave a
reason); the ROIC, gross-profit-derivation and scoring-rule companies are illustrative.

## Part 1c

| File | Figures and their source | Placeholders |
|---|---|---|
| stage_cases_20261012.json | Per company ($M): operating, investing (total) and financing cash flow, PP&E payments, acquisitions, business sale proceeds for the last 3 fiscal years, and revenue for 4 years. The Dickinson signs and 3-year revenue CAGRs follow docs/m04_review/R1_brief.md "Sitting 2": AAPL shake-out ×3 on total, mature ×3 on core, +1.8%; INTC growth ×3, −5.7%; TSLA growth ×3, +5.2%; NVDA mature ×3, +100.0%; MU mature, mature, growth, +104.6%; BA mature, introduction, shake-out, +10.3%; MRVL mature, mature, shake-out (divestiture), +11.4%; META mature, +19.9%; MSTR growth, introduction ×2, −1.5%; SPCX one fiscal year; INFQ none after the de-SPAC. Some values are near the companies' reported figures (e.g. AAPL FY2023 operating cash flow 110,543; MU FY2024–26 operating cash flow and FY2025–26 capex as in the Part 1b fixture) | **most amounts illustrative**, chosen to give the brief's signs and CAGRs; MSFT, AMZN, GOOG and GFS (plain mature) added to make the 15 setup items; fiscal year ends rounded to month ends |
| browse_sic3674_page_trimmed.htm | EDGAR browse-by-SIC result layout (`table.tableFile2`, CIK link then company name), five real SIC 3674 names incl. "KULICKE &amp; SOFFA INDUSTRIES INC" (probe S1 printed the escaped name) | trimmed to five rows; the 505-name list, form-index rows and revenue frames of the 505/82 test are generated in `tests/test_financials_1c.py` (counts from PROBE_RESULTS S1) |

## Part 2

Trimmed companyfacts files (SEC companyfacts JSON layout; D-M04-75). Revenue figures ($M) from M04_DESIGN_PACK worked example A (Intel 2022 vs AMD, NVDA, TXN, MU; the n = 4 and n = 5 z values). Placeholders everywhere: accession numbers (`<cik>-<yy>-900nnn`), filed dates (period end + 50 days for 10-Ks, + 40 for 10-Qs).

| File | Figures and their source | Placeholders |
|---|---|---|
| amd_companyfacts_trimmed_20261012.json | AMD revenue FY2020-23 9,763 / 16,434 / 23,601 / 22,680 (pack: +43.6% in 2022, -3.9% in 2023); FY2022 = 53 weeks (2021-12-26..2022-12-31); goodwill 289 -> 24,177 (Xilinx, AMD FY2022 10-K) | capex 301 / 450 and OCF 3,521 / 3,565 near the reported figures; one IncreaseDecreaseInAccountsPayable fact (illustrative) to test the trim |
| txn_companyfacts_trimmed_20261012.json | TXN revenue 2020-23 14,461 / 18,344 / 20,028 / 17,519 (pack: +9.2%, -12.5%) | capex 2,462 / 2,797 and OCF 8,756 / 8,720 near the reported figures |
| nvda_peer_companyfacts_trimmed_20261012.json | NVDA revenue FY2021-24 16,675 / 26,914 / 26,974 / 60,922 (pack: +0.2%, +125.9%); capex on PaymentsToAcquireProductiveAssets FY2022 976 | **FY2023 PP&E-tag value 1,800 is illustrative** (shows NVDA stays excluded in every year); FY2023 productive-assets 1,833 and OCF approximate |
| mu_peer_companyfacts_trimmed_20261012.json | Micron discrete quarters Q1 FY2021 - Q1 FY2023 (TTM to 2021-12-02 = 29,619 and to 2022-12-01 = 27,156, pack) and FY2021-22 27,705 / 30,758 | quarter dates approximate (Thursday ends); Q4 entered as a discrete 10-K fact |
| wdc_companyfacts_trimmed_20261012.json | Western Digital quarters 2021-01-02 .. 2022-12-30 (Friday ends, a month after Micron's: offset +29 d at 2022-12-30, -62 d before its filing; pack "WDC 62 days off until 2023-11-07" pattern) | **quarterly revenue values approximate** (only the offsets and the YoY arithmetic are tested) |
## Part 3

GE companyconcept files (SEC companyconcept JSON layout, one tag per file) and two short text
excerpts, hand-built from Round 2's worked walk (docs/m04_review/R2_brief.md "Worked example";
$M). Placeholders: accessions of the FY2018 and FY2019 10-Ks (`0000040545-19-900010`,
`-20-900010`; the FY2016 and FY2017 accessions are the real ones from the probe log S5), filed
dates approximate, and **every level value is illustrative**: only the steps between versions
are Round 2's figures. The excerpt texts are written for the fixture (not quoted from GE's
filings) and carry the amounts Round 2 attributes to each cause.

| File | Figures and their source | Placeholders |
|---|---|---|
| ge_us-gaap_Revenues_20261012.json | Revenue FY2016 −4,224 and FY2017 −3,849 (ASC 606) in the FY2018 10-K; FY2017 −18,964 in the FY2019 10-K (discontinued operations) | levels illustrative |
| ge_us-gaap_NetIncomeLoss_20261012.json | NI FY2016 −1,331, FY2017 −2,698 (FY2018 10-K); FY2017 unchanged in the FY2019 10-K | levels illustrative |
| ge_us-gaap_NetIncomeLossAttributableToNoncontrollingInterest_20261012.json | NCI FY2017 change +94 (Round 2: the residual is the NCI share) | levels illustrative |
| ge_us-gaap_NetCashProvidedByUsedInOperatingActivities_20261012.json | CFO FY2017 −4,394 (FY2018 10-K) | levels illustrative |
| ge_us-gaap_NetCashProvidedByUsedInOperatingActivitiesContinuingOperations_20261012.json | CFO FY2016 −244 → +1,160 (+1,404, the "−244 base") | level after the step illustrative |
| ge_us-gaap_IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest_20261012.json | pretax FY2016 unchanged across two 10-Ks (walked, no step) | value illustrative |
| ge_10k_fy2018_excerpt.txt | ASC 606 revenue −4,225 / −3,849, NI −1,182 / −2,668; LIFO→FIFO −147 / −124; ASU 2016-15 +1,400 (2016) / −4,411 (2017); restricted cash 153 (R2 brief rows 1–7) | wording written for the fixture; 4,225 chosen to leave Round 2's +1 |
| ge_10k_fy2019_excerpt.txt | FY2017 recast for discontinued operations, NI unchanged (R2 row 3) | wording written for the fixture |

Entered in `tests/test_financials_3.py`: Infleqtion Q1 2026 little r (revenue +$446K, net loss
−$544K; M04_BUILD_LOG Part 3; levels 9.1M / −30.2M illustrative); Rite Aid FY2017 revenue
32,845 first filed 2017-05-03 → 22,928 filed 2019-04-25 (probe S17; NI and accessions
illustrative); Invitae 3.01 2024-02-06 and 1.03 + 2.04 2024-02-14 (PROBE_RESULTS); INFQ 3.01
2026-02-03 and 4.01 2026-03-26 (M04_BUILD_LOG); the 1.02 + 2.03 co-filings AMZN 2023-11-01,
MU 2025-01-21 and 2025-03-12, TSLA 2026-09-29 (PROBE_RESULTS L8); AVGO's 10-K of 2023-12-14
(accession illustrative; its R1 is served from the META fixture page, flag false); Intel's
rating action BBB+ → BBB (August 2025; sentence written for the test). All 8-K texts are
written for the tests.

## Part 7a

Trimmed XBRL instances (SEC extracted-instance layout: `xbrli:context` with `xbrldi:explicitMember` dims), companyconcept files and release snippets (HTML as EDGAR serves exhibits; stored through the document parser in the tests). Placeholders: accession numbers not quoted from a log (`<cik>-<yy>-9nnnnn` or a plausible number), filed dates, company prefixes' namespace URIs.

| File | Figures and their source | Placeholders |
|---|---|---|
| nvda_10k_fy2025_instance_trimmed.xml | NVIDIA FY2025: 3 customers ≥ 10%, 34% at stake (M04_BUILD_LOG Part 7a); revenue 130,497M; segment revenue 116,193 / 14,304 (NVIDIA FY2025 10-K) | **per-customer split 12/11/11%, the 17% receivables share, segment operating income and the extension fact are illustrative**; the equity-component and typed-member contexts test the skip rules |
| nvda_10k_fy2026_instance_trimmed.xml | NVIDIA FY2026: 2 customers, 36% at stake ≈ $77.7B (Part 7a spec) | **22/14% split, FY2026 segment values and the FY2025 recast (115,186 / 15,311) are illustrative**; revenue 215,938M is entered in the test so 36% gives $77.7B |
| meta_10k_fy2025_instance_trimmed.xml | Meta cover counts Class A 2,187,177,748 + Class B 342,377,716 at 2026-01-23 (Part 1a) | equity-statement fact illustrative (skip rule) |
| mstr_10q_2011q2_instance_trimmed.xml | MSTR Q2 2011 Class A 8,217,394 + Class B 2,492,830 at 2011-07-27 (Part 1a) | pre-inline layout assumed |
| spcx_10q_2026q2_instance_trimmed.xml | matches the illustrative R1 fixture (3,612,000,000 + 2,388,000,000 at 2026-08-10) | **all counts illustrative** |
| goog_10q_2026q2_instance_trimmed.xml | total 12,230,000,000 at 2026-07-15 (Part 1a live check 1) | **split by class illustrative** |
| tgt_us-gaap_Revenues_20261012.json, tgt_us-gaap_CostOfGoodsAndServicesSold_20261012.json | Target FY2021–22 Q1–Q2 quarter dates; cost line only for FY2021 quarters (the review found companyfacts lacks the 10-Q cost line, R5 failure modes) | **values illustrative**, chosen so the rates reproduce the pack's unrounded −4.4 and −8.9 pp (30.0% → 25.6%, 30.4% → 21.5%, R5_gaps #5) |
| tgt_10q_fy2022q1_instance_trimmed.xml, tgt_10q_fy2022q2_instance_trimmed.xml | FY2022 Q1/Q2 revenue and cost on one product-or-service member | **tagging layout assumed** (the live check shows Target's real one); values as above |
| tsla_update_q4_2023_ex991_trimmed.htm, tsla_update_q4_2022_ex991_trimmed.htm | Tesla operational summaries Q4-2021 … Q4-2023: production and deliveries by model line as Tesla published them (2022 deliveries 1,313,851, 2023 1,808,581: +38%, Part 7a spec) | **storage deployed and regulatory-credit values illustrative**; accessions 0000950170-23-001409 (probe log) and a placeholder |
| tsla_pd_q3_2022_ex991_trimmed.htm | Q3 2022 production 365,923 / deliveries 343,830 in the older "Model S/X" categories | category label is the case under test; accession placeholder |
| rivn_q4_2024_ex991_trimmed.htm, rivn_q4_2025_ex991_trimmed.htm | Rivian deliveries 51,579 (2024) → 42,247 (2025), −18% (Part 7a spec) | **production figures, Q4 2025 quarter figures and wording illustrative**; accessions placeholders |
| nvta_q1…q4_2020_ex991_trimmed.htm | Invitae non-GAAP gross profit per quarter with prior-year columns as printed in the probe log (S16: 26,500/19,595; 7,996/26,158; 26,793/25,803; 45,506/31,600; year 106,794/103,156); accessions from the probe log | **revenues illustrative**: 2020 quarters from R5_gaps margins (41.3%, 17.3%, 39.0%; Q4 = FY 279.6M − Q1–Q3), 2019 quarters solved so each release's own columns give PROBE_RESULTS S16's −7.0 / −31.6 / −6.7 / −2.3 pp (they sum to 216.9M vs the reported 216.8M) |
| nvta_q4_2019_ex991_trimmed.htm, nvta_q4_2022_ex991_trimmed.htm | billable units 469,000 (2019) and 1,290,000 (2022) (M04_DESIGN_PACK worked example, R5 brief) | **sentence wording illustrative**; 2022 accession placeholder |
| tsla_update_q4_2023_ex991_divcells_trimmed.htm | the Q4 2023 operational summary figures above in the one-div-per-cell layout of filer-generated HTML (Part 7a live check 1) | **layout assumed** (a footnote mark, `%` in its own cell, a dash for Q2-2023 storage); storage values illustrative |
