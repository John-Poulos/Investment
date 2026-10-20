# M05 fixtures (Part 1)

Hand-built, not recorded: Claude may not call SEC or read `data\` (CLAUDE.md). Byte-exact once
written (D24). SEC companyfacts JSON layout (only the tags used). MU's worked example uses the
M04 Part 1b file `tests/fixtures/m04/mu_companyfacts_trimmed_20261012.json` (capex and
`Depreciation` FY2012–26); its contract liabilities, Microsoft's RPO and revenue, and the ROIC
inputs are entered in `tests/test_future_spend.py`. Real INTC/MSFT histories and MU's
`ContractWithCustomerLiability` can be exported by the owner with
`uv run python scripts/run_m05.py export` (0 requests) and replace the synthetic cases later.

| File | Figures and their source | Placeholders |
|---|---|---|
| utility_synthetic_companyfacts_20261020.json | D32 case: a regulated-utility shape, capex 1.78–1.90× depreciation in every year 2014–2025 (rate-base growth), depreciation +4% and revenue +3% a year; FY2025 1.82 vs prior-8-FY median 1.835 → STEADY, never AHEAD_OF_DEMAND | **all figures synthetic**; CIK 0009000001; accessions; filed dates (Feb 15 after the year) |
| assetlight_synthetic_companyfacts_20261020.json | D32 case: asset-light software, capex 1.0–1.2% of revenue, revenue +20% a year 2018–2025, no depreciation or D&A tag → `capex_demand` "missing: no depreciation or D&A (not split)" | **all figures synthetic**; CIK 0009000002 |
| decliner_synthetic_companyfacts_20261020.json | Intel-shaped decliner 2017–2023 ($B): revenue 62.8, 70.8, 72.0, 77.9, 79.0, 63.1, 54.2 and capex 11.8, 15.2, 16.2, 14.4, 18.7, 24.8, 25.75 (rounded from Intel's reported totals and the brief: capex ÷ revenue 23.7% → 39.4% → 47.5%); 2020 capex set to 14.4 so 2023's intensity is 1.75× its prior-3-FY average (the brief's reading, M04_BUILD_LOG Part 8a) → AHEAD_OF_DEMAND | **synthetic**: not Intel's filings (CIK 0009000003); depreciation values illustrative; accessions; filed dates |
