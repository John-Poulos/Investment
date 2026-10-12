# M04 fixtures (Part 1a)

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
