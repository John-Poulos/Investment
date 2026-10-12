# M04 review — combined owner probe

One owner run settles every `needs_live_probe` / `needs_owner_data` row in `R1_gaps.md` … `R6_gaps.md` and `BP_gaps.md`. Script: `scripts/probe_m04.py` (tests: `tests/test_probe_m04.py`, no network).

## Commands (owner)
- Full run, about 4–6 minutes: `uv run python scripts/probe_m04.py` → log `logs/probe_m04_<time>.txt`. Send that file back.
- Part of it: `uv run python scripts/probe_m04.py --only S5,T2,L7` (IDs below). Local only: `--no-sec --no-tiingo`. Probe table without running: `--list`.
- No redirect: the script writes its own UTF-8 log as it goes, one probe at a time (PowerShell 5.1 `>`/`*>` writes UTF-16). If it stops before printing "log written to", copy the console text instead.
- It takes `refresh.lock` like every SEC-calling script: during a running refresh it refuses to start (exit code 2); run it again afterwards.

## Read-only
- SEC: the engine's `SecClient` (5/s pacing, `SEC_USER_AGENT` from `.env`, Ok/Empty/NotFound/Failed). Responses already in `http_cache` are read from it; nothing new is written to `http_cache`, `document`, `fact`, `filing` or `price_bar`. Documents already in `corpus.db` are read locally instead of fetched.
- The only rows written are `fetch_log` entries, one per request (the request log; Tiingo's hourly/daily budget counts them).
- Each probe prints a few lines (sentences or table lines around matches, capped); a failing probe prints `ERROR …` and the run continues.

## Tiingo: why not `run_prices.py --symbols`
`run_prices.py --symbols NVTA,RAD,…` writes `price_bar` and `price_fetch` rows, and a recycled ticker would store another company's bars under the old symbol (BP #3, R6 #3). It also has no metadata call, so it cannot show the name behind a ticker. The probe instead uses the engine's `TiingoClient` read-only: T2 calls the meta endpoint `/tiingo/daily/<SYM>` (name, exchange, start/end dates) with the client's key header, spacing, budget check and `fetch_log` entry, and one `daily()` window for NVTA's 2023-06-30 close (returned, not stored). T1 reads Tiingo's public `supported_tickers.zip` in memory (no key, no API quota).

## Probes
Duplicates merged: Tiingo delisted coverage (R1 #6, R6 #3, BP #3) → T1 + T2; GE contract-assets label (R1 #10, BP #6) with GE's 2015 tag and estimate sentences (R2 #4, #5) → S5; Invitae concepts (R1 #7 P3, R5 P1, R6 #5 Invitae part) → S2; Boeing covenant sentence (R4 #3) inside S10.

| ID | Settles | Round / gap | Requests | How |
|---|---|---|---|---|
| L1 | Greenwald as average of yearly ratios, net vs gross PP&E | R1 #1 (L1) | 0 | `fact`: PP&E net/gross (incl. finance-lease variants), revenue, capex, depreciation by FY for MU, INTC, MSFT, first filed |
| L2 | Tags behind M/F-score gaps | R2 #6 | 0 | `fact`: NVDA instants near 51,951M / 10,605M / 62.6B; MRVL FY2026 `Proceeds*`; TSLA FY2022–23 `LongTermDebt*`, `Proceeds*`; GFS taxonomy counts and input tags |
| L3 | "SPCX has no prior 10-K" | R2 #8c | 0 | stored filing index: SPCX 10-K/10-Q/424B/S-1 rows |
| L4 | SPCX preferred-to-common count | R3 #2 (P2) | 0 | stored SPCX 10-Q text ("conversion of", "convertible preferred", "6,728") and conversion facts |
| L5 | INFQ CY2025/CY2024 frame pair | R3 #5 (P3) | 0 | stored INFQ text ("46,186", "39,808"); `WeightedAverageNumberOfSharesOutstandingBasic` rows with accn/form/fp/frame |
| L6 | MSTR instrument count | R3 #6 (P4) | 0 | latest stored MSTR 10-Q: convertible-notes, ATM and STRK/F/D/C lines |
| L7 | Manufacturer Z (GFS etc.) | R4 #4 (P3) | 0 | SIC 2000–3999 watchlist names: latest annual balance sheet, stored close on/before it, dei shares, X1–X5 and Z |
| L8 | `m04_customer` volume | R5 #13 | 0 | `event`: Items 1.01/1.02/2.03 since 2023-10-01; 1.02 accessions co-filed with 2.03 |
| L9 | MU/NVDA closes vs Yahoo; Micron 153/235 base | R6 #4, #15 | 0 | `price_bar` closes on the pack's dates, MU max/min 2021-09..2022-12; MU `InventoryNet` near 2022-12-01 |
| L10 | Bandwidth/size inputs; 2023 dei flag scope | BP #1, #4, #7, #8 (probe A) | 0 | DB and WAL sizes; fact rows per company; `http_cache` sizes by kind; 10-Ks filed in 2023 |
| S1 | Browse-by-SIC 3674 list and active filers | R1 #3 (P1) | 2–10 | `cgi-bin/browse-edgar` SIC 3674, 100 a page; active = 10-K in the stored form indexes in the last 12 months |
| S2 | Invitae filer status; R12 quarters; FY2021–22 revenue | R1 #7 (P3), R5 #8 (P1), R6 #5 | 5 | companyconcept: dei shares and float; revenue (two tags) and `CostOfRevenue`, quarters and years 2017Q4–2023 |
| S3 | Per-class cover counts; pre-2011 R1 format | R1 #8, #11 (P4) | 4–6 | FilingSummary + cover R page: SPCX latest 10-Q; Google Inc. (CIK 1288776) Q2 2009 10-Q (via submissions) |
| S4 | NVIDIA capex extension tag | R1 #9 (P5) | 4–6 | filing index + XBRL instance of the FY2021 and FY2013 10-Ks; investing tags for the fiscal year |
| S5 | GE "Contract assets (Note 9)" label; 2015 contract-asset tag; LTSA estimate sentences | R1 #10 (P6), R2 #4, #5, BP #6 | 4–5 | FY2017 10-K (0000040545-18-000014) text; FY2016 10-K (0000040545-17-000010) instance: element = 21,156M at 2015-12-31 |
| S6 | SPCX lock-up release schedule | R3 #1 (P1) | 1 (> 10 MB) | 424B4 of 2026-06-12: "lock-up" sentences (up to 24) and heading offsets |
| S7 | Up-C example | R3 #7 (P5) | 4–6 | EFTS phrase "exchangeable for shares of Class A common stock", 10-K Jan–Apr 2026; companyconcept NCI % for RYAN, BROS, FLNC |
| S8 | Blank checks by EFTS SIC | R3 #8 (P6) | 5–20 | EFTS "blank check company", 10-K Jan–Apr 2026, all pages; SIC-6770 filers vs stored CY2025 frames (float ≥ $75M count) |
| S9 | GOOG/AMZN 424Bs are debt | R3 #9 (P7) | about 80 | stored 424B list since 2023-10-12; per filing: index + fee exhibit → Debt/Equity and security titles |
| S10 | Class example sentences verbatim; Boeing compliant sentence | R4 #1, #3 (P1) | 9 | the 8 S4.10 documents (pack URLs) + Boeing FY2023 10-K; sentences with offsets |
| S11 | Boeing revolver maturity split | R4 #11 (P4, optional) | 0–2 | Boeing FY2019 10-K and Q2 2024 10-Q (stored text first): credit-facility expiry sentences |
| S12 | INFQ "substantial doubt" class; period vs close date | R4 #2 (P2) | 0–1 | stored INFQ text first, else the FY2025 10-K (0001193125-26-134544); 8-K 2.01 close date from the index |
| S13 | Invitae FY2022 per-unit amounts | R5 #11 (P3) | 1 | FY2022 10-K (0001501134-23-000024): per-test sentences |
| S14 | Rivian regulatory credits in automotive revenue | R5 #11 (P4) | 2 | FY2025 10-K (0001874178-26-000008): FilingSummary + revenue disaggregation R page |
| S15 | 8-K 1.02 co-filed with 2.03 | R5 #10 (P5) | 2–3 | TSLA 8-K 0001628280-26-063820; Rivian submissions → 8-K of 2025-06-12 (items, termination sentences) |
| S16 | Invitae quarterly non-GAAP gross profit | R5 #6 (P2, optional) | about 25 | Invitae submissions → earnings 8-Ks 2020-01..2022-11 → EX-99.1 lines |
| S17 | BBBY / Rite Aid episodes in XBRL; Boeing FY2018–20 | R6 #5 | 8 | companyconcept (3 revenue tags each), submissions (last 10-K, 8-K 1.03); Boeing revenue from stored facts |
| T1 | Delisted symbols in Tiingo's coverage file | R1 #6, R6 #3, BP #3 | 1 public file | `supported_tickers.zip` in memory; rows for the 18 symbols |
| T2 | Ticker recycling (name and date range per symbol); NVTA 2023-06-30 close | R1 #6, #7, R6 #3, BP #3 | 19 Tiingo | meta endpoint for BBBY(Q), RAD(CQ), JCP(NQ), SHLD(Q), RSH(CQ), FIT, NVTA(Q), BTU(UQ), CHK(AQ), GPRO; NVTA daily window |

Totals: about 170–210 SEC requests (about 40 s of pacing at 5/s, plus downloads of roughly 100 MB and text extraction), 19 Tiingo requests at 3 s spacing (about 1 minute; under the 48/hour budget unless a refresh just used it), one public file. Estimated 4–6 minutes in all; local probes take seconds.

## Not in the probe
- R1 L2 (pair ledger rows with first-filed actuals) and the R2 #6 score recompute: build work (S1.7, Part 2/6); L1 and L2 print the inputs.
- R2 #8b download times and R2 #7 text-label yield, BP #2 peer counts, R6 #8 Part 8 storage: measured in their build parts' own live checks.
- Paywalled papers (Dickinson 2011, Beneish 1999, Mohanram 2005, Patatoukas 2012): owner reading, no probe.
