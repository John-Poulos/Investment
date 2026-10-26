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

## Part 2: commitments (`commitments/*.txt`)

Synthetic files start with "SYNTHETIC FIXTURE (M05 Part 2"; real files (`*_real.txt`) start with "REAL EXCERPTS (M05 Part 2): " and name the filing (a test checks both). Real files: the owner's `uv run python scripts/run_m05.py export-text` of 2026-10-26 (0 requests), excerpts verbatim in document order joined by blank lines, text between them omitted (D-M05-27). Synthetic files stay for set-aside and D32 cases the real excerpts do not contain.

| File | Figures and their source | Placeholders |
|---|---|---|
| nvda_10k_fy2026_note12_synthetic.txt | NVIDIA FY2026 10-K Note 12: supply and capacity $95.2B (cancelable / rescheduled / adjustable wording in the next sentence), cloud $27.0B, investments $11.4B, other $3.4B (brief, D-M05-3) | wording; the $60.1B schedule line and the table row (set-aside cases) |
| nvda_10q_q2_fy2027_synthetic.txt | NVIDIA Q2 FY2027 10-Q: $279B, $92B rest of FY2027, $87B FY2028 (brief) | wording; the comparative, the "increased by" and the "could" sentences (set-aside cases) |
| meta_10q_q2_2026_synthetic.txt | Meta Q2 2026: $349.31B contractual commitments, July 2026 leases about $68B (brief cases 12–13) | wording; the $41.2B lease amount |
| mu_10k_fy2026_deposits_synthetic.txt | Micron FY2026: $12.75B customer prepayments (failure modes) | wording; the $9.1B PP&E commitment |
| nvda_10k_fy2026_real.txt | **real**, NVDA 10-K 0001045810-26-000021: $95.2B supply and capacity (CAM and Note), $11.4B investment and $3.4B other commitments, $160M customer advances; $21.4B inventories balance set aside | none |
| nvda_10q_q2_fy2027_real.txt | **real**, NVDA 10-Q 0001045810-26-000075: $279B supply and capacity (from $119B), $25B equity investment commitments, $2.8B customer advances; $99B equity investments held, charges, provisions set aside | none (replaces the live-check-1 file) |
| meta_10k_fy2025_real.txt | **real**, META 10-K 0001628280-26-003942: $131.05B contractual commitments (scope not split), $103.77B leases not yet commenced | none |
| meta_10q_q3_2026_real.txt | **real**, META 10-Q 0001628280-26-066773: $454.52B (scope not split), $355.73B leases not yet commenced, $1.53B letters of credit set aside | none (replaces the total-only file) |
| mu_10k_fy2026_real.txt | **real**, MU 10-K 0000723125-26-000023: $4.18B PP&E, $10.8B purchase obligations; deposits not read from text | none |
| mu_10q_q3_fy2026_real.txt | **real**, MU 10-Q 0000723125-26-000015: $2.93B PP&E ("As of May 28") | none |
| airline_10k_fy2024/2025_synthetic.txt | D32: invented airline, aircraft commitments $12.0B / $14.6B, fuel $1.2B | **all figures synthetic** (CIK 0009000011) |
| retailer_10k_fy2025_synthetic.txt | D32: invented outsourced apparel retailer, merchandise obligations $3.5B, cancellable | **all figures synthetic** (CIK 0009000012) |
