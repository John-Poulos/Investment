# Round 1 — Known gaps check (data and what is buildable now)

Read 2026-10-12. Scope: the 12 "Round 1" bullets in `docs/M04_DESIGN_PACK.md` Known gaps (lines 3488–3500), plus the "New sources" bullets on the Dickinson (2011) stage table (shared with Round 5) and Micron's 153/235 inventory days (lines 3560, 3562). No SEC host was requested. Non-SEC hosts used: Micron's and Intel's own IR sites (micron.gcs-web.com, intc.com), Infleqtion's IR site (ir.infleqtion.com, company copies of its 8-Ks), Cornell LII (17 CFR 240.12b-2), the Eurostat glossary, Tiingo documentation, Semantic Scholar, and secondary pages named in each row. Some facts come from web-search summaries of sec.gov pages that were never fetched; these are marked "search relay". Repo files read: `src/engine/sec/events.py`, `src/engine/prices/{tiingo,store}.py`, `scripts/` (run_prices, guidance_samples, run_guidance, fetch_stats, check_tickers, probe_financing, run_money), `src/engine/moneyflow/instance.py` (header), and `logs/guidance_20261008-011457.txt` (a log, not `data\`).

## Summary
| # | Gap | Status | Changes pack? |
|---|---|---|---|
| 1 | Greenwald rule: gross or net PP&E; 5-year window | partly closed | **yes** (method reading; figures to recompute) |
| 2 | Dickinson (2011) Table 1 (with Round 5) | stays open | no (one attribution fix) |
| 3 | EDGAR browse-by-SIC 3674 not fetched | needs live probe | no |
| 4 | 31 guidance-ledger rows unreadable in `data\` | partly closed | **yes** (1.9a scoring rules) |
| 5 | Intel July 2022 release not read | closed | **yes** (worked example) |
| 6 | Tiingo coverage of delisted tickers | needs live probe | no |
| 7 | Invitae FY2023 filer status unknown | partly closed | **yes** (due date; S1.6 backtest rule) |
| 8 | R1 cover pages: pre-2011 format; ~165 count | partly closed | **yes** (fetch-plan figure) |
| 9 | NVIDIA FY2013–FY2021 capex extension tag | needs live probe | no |
| 10 | GE `UnbilledContractsReceivable` line label | partly closed | no |
| 11 | SPCX per-class cover count | needs live probe | no |
| 12 | INFQ 8-K 3.01 and 4.01 causes | closed | **yes** (event routing; red-flag count) |
| 13a | ±40-day quarter/instant tolerance unsourced | stays open | no |
| 13b | 25% revenue-CAGR stage conflict unsourced | partly closed | **yes** (sourced anchor 20%; same first-run result) |
| 13c | "2 misses in 4 quarters" unsourced | stays open | no |
| 13d | Depreciation cap rule unsourced | stays open | no |
| 14 | Critique items owned by other rounds | stays open (owners named) | no |
| 15 | Micron 153/235 inventory days, no written source | closed | **yes** (definition; Round 6 display) |

## Findings

**1. Greenwald (partly closed; changes the pack's reading).**
- A secondary page reproduces the book's steps and cites page 96 of *Value Investing: From Graham to Buffett and Beyond*: compute PP&E ÷ sales "for each of the five prior years and find the average" (einvestingforbeginners.com, read 2026-10-12). The book itself was not read; the Old School Value pages still return 404.
- Settled by that passage: the window is the **five prior years** (the current year is excluded, as the pack assumed), and it is an **average of yearly ratios**, not the pack's ratio of sums.
- Still open: gross or net. The passage says only "PPE". The same page's own paraphrase says gross, but that is the author's wording, not Greenwald's.
- Effect on the pack: item 11 and the A2 worked example say "(sums)". They should switch to the average of yearly ratios and show net and gross side by side. The Micron, Intel and Microsoft Greenwald columns need recomputing from stored facts (local, no SEC).
- Recommendation 1.5a still holds. The algebra shows why:
  - Greenwald maintenance = capex − r × Δrevenue, with r > 0. When revenue falls, maintenance is above capex under **any** reading. That covers Micron FY2019, FY2020 and FY2023, and Intel in all 4 years.
  - Maintenance turns negative when r > capex ÷ Δrevenue. The cut-offs are: MU FY2024 0.876, FY2025 1.293, FY2026 0.321. The pack's net, ratio-of-sums r is 1.422, 1.497 and 1.436. Gross PP&E only raises r. The average of yearly ratios is pulled up by FY2023's low revenue. So "6 of 8 Micron years out of range" should survive; confirm FY2025 in the recompute.
  - Microsoft FY2026: Greenwald stays above depreciation ($34,300M) while r < 1.63. It stays inside 0…capex while r < 2.31. The net reading gives r = 0.516. Check the gross reading in the recompute.
- Probe L1 (local).

**2. Dickinson (2011) Table 1 (stays open).**
- Tried 2026-10-12. Semantic Scholar lists the paper as `CLOSED` (no open PDF). SSRN 755804 returns 403. The NTU thesis that applies the method is an encrypted PDF with no text layer. No free primary copy was found.
- The sign table still rests on two matching secondaries (S-new-56 Brazilian paper; S-new-r5-1).
- Attribution fix for Round 1: item 12 (line 147) still states "62% stayed mature … 30% moved back to growth" as a general fact. Round 5 corrected it to the Brazilian sample (313 firms, 2005–12). Round 1 should carry that label.
- To close: the owner obtains the TAR article (library or AAA), or the round runs on the two secondaries, labelled.

**3. Browse-by-SIC (needs live probe).**
- This note is stale: the Build-parts research did fetch page 1 of the 3674 list (S-new-bp-6). The list is alphabetical and includes inactive filers. So the problem was the user agent, not a block.
- The active-filer filter can use the quarterly form indexes already stored by `themes/universe.py`, with no new request (Build parts item 5).
- Probe P1.

**4. Guidance ledger (partly closed).**
- `logs/guidance_20261008-011457.txt` lists every parsed row (53 releases: 31 parsed, 20 none, 2 review). It reflects the DB as of 2026-10-08.
- Parsed releases: INTC 4, META 4, AMZN 4, NVDA 4, MRVL 4, MU 4, INFQ 4, GOOG 2, MSTR 1. Releases with no guidance: MSFT 4, AAPL 4, TSLA 4, BA 3, GOOG 2, MSTR 2, SPCX 1.
- What this changes in 1.9a:
  - (a) **Release-silent companies.** For MSFT, AAPL, TSLA, BA and SPCX, `guidance_hit_rate` would read "missing: no guidance in releases (calls: DS1)", never 0.
  - (b) **Duplicate rows.** Intel's rows come in up to three bases for one metric: GAAP and non-GAAP from the table, plus "unspecified" from the sentence. The hit rate must count one outcome per metric and period, on the guide's own basis.
  - (c) **Forms of guide.** The ledger holds four forms: `range`, `plusminus`, `point` (Intel GM 41%, EPS $0.31) and `approx` (Micron GM about 81%, NVIDIA opex about $6.7B). A strict "below a point guide" rule makes a 0.1 pp shortfall a miss. A tolerance for point and approx guides is needed (no published source found), or those forms are shown unscored.
  - (d) **"Removed" needs more history.** The rows span releases filed 2025-10-23 to 2026-10-02, one year. Comparisons with the same fiscal position a year earlier start with the next quarter's releases.
  - (e) **Revisions are already captured.** Meta's rows carry `prior` ranges, e.g. FY2025 capex $66–72B → $70–72B.
- Actuals are not in the log. Pairing rows with first-filed actuals is a local query in the S1.7 build (L2).

**5. Intel July 2022 release (closed).**
- Intel's IR site, release of 2022-07-28, read 2026-10-12: https://www.intc.com/news-events/press-releases/detail/1563/intel-reports-second-quarter-2022-financial-results
- The release revised FY2022 revenue to $65–68B, GAAP and non-GAAP. It kept net capital spending at $27B (GAAP) and adjusted FCF at ($1–2)B. Its headline says "revising" and "reiterating".
- Worked-example change (1.9a). Intel FY2022 revenue went $76.0B (2022-04-28) → $65–68B (2022-07-28) → $63–64B (2022-10-27). Actual: $63,054M.
  - That is **two** downward revisions, not "at least one".
  - Under 1.9a it is a hit on the latest guide.
  - It was below the July range, by 3.0% against the low end.
  - It was 17.0% below the first guide.

**6. Tiingo delisted coverage (needs live probe).**
- Tiingo's symbology page (S-new-bp-1) says delisted data is supported only for tickers not yet recycled.
- Its end-of-day docs (read 2026-10-12) say two things:
  - The meta endpoint `/tiingo/daily/<ticker>` returns `startDate` and `endDate`.
  - The public file https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip "includes current coverage as well as symbol reservations". Its columns are not listed there.
- Per-episode coverage still needs the owner's key. Probe P2.

**7. Invitae filer status (partly closed).**
- Rule 12b-2 (Cornell LII, read 2026-10-12): status is set at fiscal year-end from public float on the last business day of the second fiscal quarter. A large accelerated filer leaves that status when float is below $560M. It becomes an accelerated filer if float is at least $60M and it fails the SRC revenue test (revenue under $100M).
- Invitae at 2023-06-30:
  - Shares: 267,014,064 on the Q2 2023 10-Q cover, as of 2023-08-04 (search relay of the sec.gov page, not fetched).
  - Price: about $1.13 for June 2023 (digrin, secondary); a $1.38 insider sale on 2023-06-13.
  - Float: at most about $430M even at $1.60 a share. FY2022 revenue was about $0.5B, far above the SRC test.
- Result: **accelerated filer** for FY2023. The FY2023 10-K was due 75 days after year-end, on **2024-03-15**; with an NT 10-K it would have been 2024-04-01. Replace the range in S1.6. The conclusion (8-K 3.01, then bankruptcy, then Form 25 all came first) is unchanged.
- **Rule change for S1.6 backtests.** Historical status can be derived from `dei:EntityPublicFloat`, which is stored in `fact` from each 10-K cover. Apply the 12b-2 entry and exit thresholds ($700M / $560M; $75M / $60M) and the SRC revenue test. Use the longest deadline only when the float is missing. Invitae is that case: its FY2023 10-K was never filed, so the float is estimated from Q2 cover shares × close, labelled.
- Probe P3 (optional confirmation).

**8. R1 cover pages (partly closed).**
- The Build-parts section (lines 3242–3249) measured the count: **162** XBRL 10-K/10-Q accessions (GOOG 44, META 57, MSTR 61), plus SPCX 1 = **163**. That replaces "about 165, estimate".
- 61 = Q2 2011 to Q2 2026, so MSTR's earliest in-scope filing is its Q2 2011 10-Q. Its R1 was read (S-new-bp-5): Class A 8,217,394 + Class B 2,492,830. So the format is verified back to 2011.
- Only Google Inc.'s predecessor CIK (0001288776, 10-Qs from 2009) falls before 2011. It is outside the 162. That makes it a scope choice. It adds about 25 pages if wanted, and its 2009–2010 R1 format is unverified (P4, optional).
- Apply the split guard to cover counts (MSTR 10-for-1 in 2024).

**9. NVIDIA capex tag (needs live probe).**
- No non-SEC source shows the tag.
- One search hit for `PurchasesRelatedToPropertyAndEquipmentAndIntangibleAssets` pointed at NVIDIA's FY2013 10-K. Its cash-flow caption, "purchases related to property and equipment and intangible assets", suggests a company extension tag. Unconfirmed.
- If confirmed, the line includes intangibles before FY2022 too. NVIDIA's own history would then be one consistent broad definition. That matches the 1.2a peer exclusion. Probe P5.

**10. GE contract-assets label (partly closed).**
- Search relays of GE's FY2017 10-K (sec.gov, not fetched) say the GE column of the Statement of Financial Position shows **"Contract assets"**: $28,861M (2017) and $25,162M (2016), with a note reference. Those are exactly the values tagged `UnbilledContractsReceivable`.
- The schedule components include deferred inventory costs and nonrecurring engineering costs. So the line is broader than unbilled receivables.
- A non-SEC mirror (finboard) was truncated before the balance sheet.
- Keep the alias marked, with the label "Contract assets (GE, pre-ASC 606)". Confirm in P6.

**11. SPCX per-class cover count (needs live probe).** Nothing non-SEC shows its 10-Q cover. Probe P4.

**12. INFQ 8-K 3.01 and 4.01 (closed).**
- Both read 2026-10-12 from Infleqtion's IR copies of its 8-Ks:
  - 3.01: https://ir.infleqtion.com/sec-filings/all-sec-filings/content/0001193125-26-035805/d71149d8k.htm
  - 4.01: https://ir.infleqtion.com/sec-filings/all-sec-filings/content/0001193125-26-126442/d35442d8k.htm
- **3.01 (2026-02-03)** is a voluntary **transfer of listing**. Churchill X told Nasdaq it would move to the NYSE once the Infleqtion combination closed. Nasdaq trading was to end 2026-02-13 and NYSE trading (INFQ) to start 2026-02-17. No deficiency.
- **4.01 (event 2026-03-20, filed 2026-03-26; 8-K/A 2026-03-31).**
  - Withum, the SPAC's auditor, was dismissed effective once it finished the FY2025 audit. KPMG, Legacy Infleqtion's auditor, was engaged for FY2026.
  - The 8-K states no disagreements and no reportable events. It says Withum's report on the SPAC's statements carried no adverse opinion or disclaimer and was not modified for uncertainty.
  - "Going concern", "substantial doubt" and "explanatory paragraph" do not appear in the 8-K.
- **Effect.**
  - `events.py` stores 3.01 as `red_flag`/high and 4.01 as `red_flag`/medium. Both are routine de-SPAC mechanics here.
  - So 2 of the 6 "red-flag" events in 3 years (Build parts count) are false positives.
  - Add text sub-classes: 3.01 "transfer of listing" → info. A 4.01 within about 90 days of a 2.01 + 5.06 closing that states no disagreements → info.
  - R4_gaps item 10 makes the same 3.01 point for S4.1. This adds the 4.01 case and a real example.

**13a. ±40 days (stays open).** No published alignment tolerance was found. Compustat's documentation reached (2003 user's guide, p. 66) defines data year and data quarter but not a calendar-quarter offset. It stays a labelled starting value, set from MU–WDC 29/36 days and D-SEC-9's −32/+34.

**13b. 25% CAGR stage conflict (partly closed).**
- A published high-growth line exists. The Eurostat glossary (read 2026-10-12) gives average annualised growth above 10% a year over three years (t−3 to t) as the main definition. It names 20% as an alternative threshold and allows turnover as the measure. 20% is the OECD-Eurostat (2007) manual's figure, per UK government and Statistics Denmark pages (secondary).
- Using **20%** instead of 25% gives the same first run: NVDA (+100.0%) and MU (+104.6%) are flagged. META (+19.9%) stays just below, a borderline the owner should see. MSFT 16.1%, GOOG 12.5% and AMZN 11.7% are not flagged.
- 10% would flag six mature names, too many for a review queue.
- Recommend 20% (OECD-Eurostat), labelled "high-growth definition, firm-statistics context, not stage-specific".

**13c. "2 misses in 4" (stays open).** No source found. It stays a starting value for M11/R19 calibration.

**13d. Depreciation cap (stays open).** The cap (maintenance = min(depreciation, capex), growth ≥ 0) is a modelling bound, not a calibrated threshold. Search relays attribute "net capex = capex − depreciation", which can be negative, to Damodaran's NYU course slides. The slide PDF had no readable text layer here, so this is unverified. If the owner prefers no cap, "capex below depreciation" can be shown as its own flag instead of being capped.

**14. Critique items owned elsewhere (stays open).**
- Customer signal (2) → Round 5.
- `cvd_confidence` for missing rows (4) and CvD grid gaps (5) → Round 6.
- Consolidated D-M04-1 change table (6) → consolidation at merge, fed by Round 1's list at line 627.
- M01 interaction (7) → Round 6 and the final critic pass.
- Review-kind caps (15) → Round 4 (weekly cap) and the pack-wide review-kind list.

**15. Micron 153 / 235 days (closed).**
- Micron's figures reproduce exactly from primary figures, using **average** inventory over the 91-day quarter:
  - Q1 FY2023 inventories: $8,359M at 2022-12-01 (from Micron's Q1 FY2023 release, read via a verbatim reprint on thetechoutlook.com). The same table's $6,663M at 2022-09-01 matches `InventoryNet`.
  - Q2 FY2023 inventories $8,129M, COGS $4,899M and write-downs $1.43B come from the S-new-5 release.
  - (8,359 + 8,129) ÷ 2 ÷ 4,899 × 91 = **153.1 days**.
  - Excluding the write-down, take it out of COGS and add it back to closing inventory: (8,359 + 9,559) ÷ 2 ÷ 3,469 × 91 = **235.0 days**.
  - Adjusting COGS only gives 216.3. The pack's 151 / 213 use closing inventory only.
- A call summary (longportapp, secondary) says "average days of inventory", which matches.
- **Effect.** The company basis is no longer unstated. The engine can compute Micron's own basis (average inventory, write-down added back) as grade A from filings. The oral 153 / 235 stay grade B, as checks. Round 6 should show the engine's own-basis figure, not "151 / 213 beside the oral figures".
- Round 1's worked-example row ("inventory ÷ COGS × 365", closing inventory: 144.2 → 180.5) should name its basis. On average inventory FY2023 reads 162.0 days, (6,663 + 8,387) ÷ 2 ÷ 16,956 × 365.

## Probes (owner runs one combined probe)
| ID | What | Endpoint type | Requests | Existing script |
|---|---|---|---|---|
| P1 | Browse-by-SIC 3674 (and the other watchlist SICs if wanted): all pages, `type=10-K`, `count=100`; then filter to active filers with the stored form indexes | www.sec.gov `cgi-bin/browse-edgar?action=getcompany&SIC=3674` | about 5–10 for 3674 | none (proposed Part 2 `run_financials.py peers`) |
| P2 | Delisted coverage: NVTA, RAD, JCP, SHLD, FIT. Compare each `last_date` with the delisting date; a recent `last_date` means the ticker was recycled. For `not_found`, look the name up in the public `supported_tickers.zip` (no key). Note: this writes `price_bar` rows for those symbols | Tiingo daily prices (key) | 5 Tiingo, 0 SEC | `uv run python scripts/run_prices.py --symbols NVTA,RAD,JCP,SHLD,FIT` |
| P3 | Invitae (CIK 0001501134) `dei:EntityCommonStockSharesOutstanding` and `dei:EntityPublicFloat` history; NVTA close on 2023-06-30 from P2 | companyconcept (dei) | 2 | none (one-off) |
| P4 | Cover pages: SPCX Q2 2026 10-Q `R1.htm` (accession from `filing`); optional: Google Inc. (CIK 0001288776) Q2 2009 10-Q `R1.htm` | Archives R page | 1 (+1 optional) | none (proposed Part 1 probe) |
| P5 | NVIDIA capex tag: the FY2021 10-K inline instance (`nvda-20210131_htm.xml`, accession from `filing`) and one pre-2019 instance (FY2013 10-K `.xml`). List cash-flow investing tags with `moneyflow.instance.parse_instance`; note that `instance_url` handles only `_htm.xml` | Archives instance | 2 (+2 index pages if accessions are unknown) | `run_money.py` reads instances, but not ad hoc; small one-off |
| P6 | GE FY2017 10-K (0000040545-18-000014) balance-sheet R page: confirm the "Contract assets" label and note number | Archives R page | 1–2 (FilingSummary + R page) | none |
| L1 | Local, no network: Greenwald as the average of yearly ratios, net and gross PP&E (`PropertyPlantAndEquipmentGross` and its finance-lease counterpart from `fact`), for MU FY2019–26, INTC 2022–25, MSFT FY2026 | `fact` table | 0 | none (Part 1 fixture) |
| L2 | Local, no network: pair the parsed ledger rows whose period has ended with first-filed actuals (per basis) | `guidance`, `fact` | 0 | none (S1.7 build) |

SEC total: about 11–17 requests, under a minute at the client's pace.
