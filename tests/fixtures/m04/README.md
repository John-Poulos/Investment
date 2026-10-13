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
