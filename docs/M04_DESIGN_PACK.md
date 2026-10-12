# M04 — Design review pack (draft for the owner)

**Status:** research only. Nothing is decided until the owner answers (D7). · **Date:** 2026-10-12 · **Effort:** High for this review; each build part Medium.

**Scope.** This pack covers the M04 items still open:
- The DESIGN.md open items: show the capex fallback tag to the user, separate the shares concepts, set a peer period-end offset tolerance, discover SIC peers, and M04 red flags.
- The red flags listed as "still to design" in M04_FINANCIALS.md: earnings quality, dilution, going-concern and covenant language, and unit economics.
- Calibration of the approved CvD profile (D-M04-1). That profile changes only where a question says so.

Outputs are research signals, not financial advice.

## How this review runs
- **Order.** One round per section, in the order below. Each round's answers are recorded before the next round starts.
- **What each round contains:**
  - What the research says. Every claim is cited: S-numbers from docs/SOURCES.md, or provisional S-new-n IDs listed under "New sources". Codebase facts cite the file.
  - A worked example. Figures are real and sourced; invented rows are marked illustrative.
  - All cases the rule must handle.
  - Numbered suggestions (S1.1, S1.2, …).
  - Failure-mode rows for the M04 table (D9).
  - 2–4 questions. Each has lettered options with the recommended option first and one line of why.
- **How to answer.** Plain text, e.g. "1.1a 1.2b 1.3a 1.4a".
  - Suggestions stand or fall with your answers. Strike any you reject by number ("S2.6 no"), or reply "rest ok".
  - Answers become decisions D-M04-2 onward.
  - Every threshold below is a starting value, calibrated in Round 6.

---

## Round 1 — Data and what is buildable now

**Read before this round is presented** (owner rule: primaries before the round, not before build):
- Greenwald's own maintenance-capex rule (S13 is secondary: the Wikipedia "Owner earnings" summary, re-read 2026-10-12; the Old School Value page now returns 404). Open points: gross or net PP&E, and whether the 5-year window includes the current year. Question 1.5 depends on it.
- Dickinson (2011), Table 1 (S-new-56; the stage mapping below comes from a secondary paper). Question 1.6 depends on it.
- The sources added in this revision (S-new-r1-2 to S-new-r1-9) were read at the cited passages.

### What the research says
1. **Most M04 numeric inputs are already stored.**
   - The `fact` table keeps every companyfacts value from us-gaap, ifrs-full, dei and srt, each with its accession, form and filed date.
   - `series` holds 26 concepts (Q, FY, TTM, instant), including `rd`, `da`, `ppe_net` and `rpo`. Each has a first and a latest value and a `method` that names the tag used.
   - Any other standard tag can become a series on demand. The pattern is in `financing/credit.py` (`build_concept`, `_instant`).
   - Limits:
     - `moneyflow/periods.tag_points` assumes currency, so share-unit concepts need their own `Concept`.
     - Company extension tags are only available from the filing instance (LESSONS, D-M02-32).
     - Companyfacts carries no dimensional facts (S40, S41).
     - Interim cash flows are year-to-date, so quarters are derived (S43).
   - Result: Piotroski F, Altman Z″, Beneish ratios, accruals and inventory days need no new SEC fetch for the company itself.
   - Code: `src/engine/sec/xbrl_facts.py`, `store/migrations/engine/0001_initial.sql`, `moneyflow/instance.py`.
2. **There are two point-in-time defects.**
   - **(a) Tag priority is applied before time.** `build_concept` picks the highest-priority tag for a period, then takes first and latest *within that tag*.
     - Real case: Micron's FY2018 revenue was first filed 2018-10-15 under `Revenues`. `series` records it as first filed 2019-10-17, under `RevenueFromContractWithCustomerExcludingAssessedTax`.
     - So a query as of 2018-11 finds nothing, and first-vs-latest deltas are wrong after any tag switch (S-new-1).
   - **(b) No form filter on "latest".** XBRL facts also arrive in 8-Ks and proxy statements (S-new-1):
     - GE's 2015 operating cash flow appears in an 8-K filed 2016-06-03.
     - Alphabet's 2023 net income appears in a DEF 14A filed 2026-04-24 (accession 0001308179-26-000342).
   - Frames return the value "last filed" that "most closely fits" the calendar period (S39), so they cannot serve as historical peer values.
   - `SeriesRow.restated` exists but only tests use it. Nothing writes the D13 `signal` table yet.
3. **Share counts are one mixed series.**
   - `shares_outstanding` merges `CommonStockSharesOutstanding` (balance-sheet date) with `dei:EntityCommonStockSharesOutstanding` (cover date, weeks later). Both survive as separate points in one series.
   - Checked 2026-10-12 (S-new-1, S-new-r1-1):
     - META and Strategy have neither non-dimensional tag (404).
     - Alphabet has no dei count (404).
     - SpaceX (SPCX) has no dei facts at all in companyfacts; its cover count is probably reported per class (to confirm from its R1 page).
     - Apple's dei count is dated at the cover date: 2025-10-17 for a 2025-09-27 year end.
   - Weighted-average basic and diluted shares exist for all of them.
   - No concept maps weighted-average shares or stock-based compensation (SBC).
   - Your 2026-10-07 note recommends separate concepts and names R22 "% of float" (M07) as a consumer of the cover count (M00_SEC_DATA.md line 104).
   - Float in shares is not tagged. `dei:EntityPublicFloat` is a dollar value of non-affiliate equity "as of the last business day of the registrant's most recently completed second fiscal quarter" (Form 10-K cover, S-new-r1-3). Float shares can therefore be implied once a year as float ÷ the close on that date.
4. **The capex fallback reaches the user only on hover, and two watchlist names depend on it.**
   - `capex` falls back to `PaymentsToAcquireProductiveAssets`, which is broader: it includes software and intangibles (S100).
     - Amazon: the PP&E tag ends with FY2016 (S100 dates the switch to 2017). The broader tag carries every year from FY2016, first filed in the FY2018 10-K (2019-02-01). Its FY2017 10-K carries no standard capex tag at all, so an as-of read in 2018 finds no FY2017 capex.
     - For the overlap year FY2016 the two tags differ by 15.8%: $6,737M under the PP&E tag (FY2016 10-K) against $7,804M under the broader tag (FY2018 10-K) (S-new-r1-1).
     - NVIDIA uses it from FY2022. Between FY2013 and FY2021 no standard capex tag exists in its companyfacts, probably because of a company extension tag (to confirm from one instance) (S-new-r1-1).
   - `tabs/financials.html` shows `method` only in a tooltip.
   - M02's money view labels the fallback in text (`moneyflow/actuals.py:153`).
   - Company-stated definitions already exist for display: `config/capex_definitions.toml` (Amazon "cash capex" = productive assets − `amzn:ProceedsFromPropertyPlantAndEquipmentSalesAndIncentives`) and the D-M02-29 recipes (Meta: PP&E + finance-lease principal, Q2 2026 $30.116B + $0.962B = $31.08B). They are reconciled to stated figures (D-M02-32).
   - `FrameValue.tag` carries the tag, but no peer statistic flags or excludes fallback values.
5. **The peer machinery exists, but no peers are stored.**
   - `frames.py` has `peer_stats`, `robust_z`, `MIN_PEERS = 5`, and a closest-period match within ±45 days.
   - Nothing writes the `peer_group` and `peer_member` tables.
   - SIC codes exist only in `entity`, for resolved companies, and in EFTS hits. Frames carry none (D-SEC-9). The submissions JSON gives `sic`, `fiscalYearEnd` and the filer `category` at one request per company (S-new-r1-1).
   - GICS explains return co-movement and key ratios better than SIC, NAICS or Fama-French, most of all for large firms, but it is not free (S-new-2). Text-based industries: S109.
   - SIC codes checked 2026-10-12 (S-new-r1-1) show how coarse they are:
     - In 3674: MU, INTC, NVDA, AMD, TXN, AVGO, MRVL, GFS and ON, but also the solar companies First Solar and Enphase (S110: 3674 includes solar cells).
     - Not in 3674: Qualcomm (3663), Western Digital and Seagate (3572).
     - Watchlist oddities: Amazon 5961 (catalog and mail-order retail); Strategy 6199 (finance services, inside the 6000–6799 financials range); Alphabet, Meta and SpaceX 7370; Infleqtion 7374.
6. **One offset tolerance for all period types misleads.**
   - Overlap arithmetic: a 45-day offset leaves about 88% overlap for a TTM window but about 51% for a quarter.
   - Observed offsets:
     - D-SEC-9: Micron ended 2025-05-29 and AVGO 2025-08-03 against a 2025-06-30 target (−32 and +34 days).
     - Micron's TTM ending 2022-12-01 is 30 days before calendar year-end.
     - Micron vs Western Digital quarter ends (eight discrete quarters, 2023-11 to 2026-02): 29 days in six of them. The other two run 36 days, because they fall in WDC's 53-week FY2026, whose first quarter ended 2025-10-03 rather than late September (S-new-r1-1).
   - Effect on the Q1 test: comparing Micron's fiscal year ending 2022-09-01 (121 days off) with Intel's calendar 2022 gives Intel z −3.35. The offset-respecting Micron TTM gives −1.71 (Round 6).
   - 53-week years add about 2% to that year's growth. Intel's FY2022 ran 2021-12-26 to 2022-12-31 (S-new-1). Micron's FY2026 ran 370 days (2025-08-29 to 2026-09-03).
   - Research data align fiscal years by convention (S-new-3):
     - Compustat assigns year-ends from January to May to the prior year.
     - Fama-French lag fiscal year-ends by at least 6 months.
7. **Red-flag events are already typed.**
   - `events.py` routes these 8-K items to M04:
     - `red_flag`: 1.03, 1.05, 2.04, 2.05, 2.06, 3.01, 4.01, 4.02;
     - `capital`: 2.03, 3.02 and 3.03 (3.03, a material modification to holders' rights, also goes to M07 and feeds Round 3);
     - `agreement`: 1.02 (termination of a material agreement, also M02/M06, for the customer row) and 2.01;
     - `governance`: 5.03 (including a change in fiscal year), 5.05, 5.06 (change in shell company status, which marks a de-SPAC closing).
   - Pre-2004 items are mapped through `LEGACY_ITEMS`. The item list is Form 8-K's (S-new-r1-2). The full submissions history is covered (S39).
   - `filing` holds every form: NT 10-K, NT 10-Q, 10-K/A, S-1, S-3, S-3ASR, 424B*, S-8.
   - Documents are fetched only for 10-K, 10-Q, 8-K and their amendments, 20-F and 6-K (`config/watchlist.toml`).
   - Counts of late filings, amendments and shelves are therefore buildable from metadata now.
   - Not stored: 424B and S-3 text, prior-year 10-Ks (DS7) and EX-99.2 letters.
8. **XBRL history starts 2009–2011**, depending on filer size (S-new-4).
   - Micron's XBRL starts with the 10-Q filed 2010-01-12, which carries a comparative quarter ending 2008-12-04.
   - Micron's `GrossProfit` first appears in the FY2011 10-K (S-new-1).
   - So history depth must be set per concept, not per company.
9. **The old engine** (`reference/old_engine/financial_intelligence.py`):
   - Has no share-count logic.
   - Computes runway as (cash + short-term investments) ÷ operating cash-flow burn.
   - Gives shelf filings severity "none".
   - Matches substrings in 3 filings truncated to 60,000 characters.
   - Reports unknown signal types as "unknown", never a default.

   What to keep, change or drop is settled in Rounds 3–4.
10. **Two mapped concepts are wrong or stale for several watchlist names** (S-new-r1-1).
    - **`da`** maps `DepreciationDepletionAndAmortization`, `DepreciationAmortizationAndAccretionNet` and `DepreciationAndAmortization`. Two problems:
      - The standard label of `DepreciationAndAmortization` is "Depreciation, Depletion and Amortization, Nonproduction", a narrower meaning. Intel's only values under it are $177–294M a year (FY2015–FY2019). Its `Depreciation` for FY2019 was $9,204M, so `da` reports about 2% of the real figure, then nothing after FY2019.
      - Microsoft and Alphabet tag only `Depreciation`, so `da` is empty for both.
    - **`ppe_net`** (`PropertyPlantAndEquipmentNet`) stops for five names. Each moved to `PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization`, which also includes finance-lease right-of-use assets:
      - Micron: last net value 2020-05-28;
      - Intel: 2022-12-31;
      - Meta: 2020-09-30;
      - Alphabet: 2025-03-31;
      - Tesla: 2025-09-30.
11. **Capex split (A2) cannot rely on Greenwald alone** (S13, S25; S-new-r1-1; worked example below).
    - A2 (approved) orders the sources: disclosed, then project-level, then Greenwald (default), then D&A, every value method-tagged.
    - Disclosed splits exist mainly in midstream filers (S25).
    - Greenwald, per the summary: growth capex = the PP&E-to-sales ratio of the past 5 years (sums) × the year's change in sales; maintenance = total capex − growth capex. A fall in sales makes growth capex negative (S13).
    - Micron's FY2023 10-K gives no maintenance split. It names projects (Boise and Clay fabs, Gujarat assembly and test) without amounts, and guides FY2024 capex "net of partner contributions" at slightly above $7 billion (S-new-5, read in full 2026-10-12). So for Micron the ladder falls to Greenwald.
    - On real data Greenwald fails in both directions:
      - Micron: out of the range 0 to total capex in 6 of 8 years (FY2019–FY2026);
      - Intel: out of range in all 4 years FY2022–FY2025;
      - Microsoft FY2026 (inside the range): 77.7% of capex comes out as "maintenance", against depreciation of 29.6% of capex, because capex runs ahead of revenue.
    - Depreciation is the stable proxy, but it moves with useful-life changes. Intel lengthened certain machinery lives from 5 to 8 years in 2023 (about +$2.5B to gross margin; S-new-61, S-new-r1-8), and its depreciation fell 29.5%.
    - Nothing in `src/` implements A2 today.
12. **Life-cycle stage from cash-flow signs misroutes large caps** (moved here from Round 5, item 7, because Rounds 2–4 route on it; S-new-56).
    - Dickinson's signs (operating, investing, financing):
      - introduction (−, −, +);
      - growth (+, −, +);
      - mature (+, −, −);
      - shake-out (−,−,−), (+,+,+) or (+,+,−);
      - decline (−,+,+) or (−,+,−).
    - Stages are not sequential: of mature firms, 62% stayed mature the next year and 30% moved back to growth.
    - On watchlist data (worked example):
      - Apple reads shake-out three years running, because maturing securities make investing cash flow positive;
      - Intel reads growth three years running while its revenue fell, because partner and government financing flowed in;
      - Strategy reads introduction, because its operating cash flow is slightly negative while equity funds bitcoin purchases in investing cash flow.
13. **The D13 `signal` table cannot hold enums cleanly** (migration 0001).
    - `value` is NUMERIC; `timeframe` (MY/PT/ST), `evidence_grade` (A/B/C), `source_ref` and `method` are NOT NULL; the key is (ticker, module_id, signal, timeframe, as_of).
    - SQLite stores non-numeric text in a NUMERIC column as TEXT, and any TEXT value sorts above every number (S-new-r1-7). Tested here: `max()` over 'CYCLICAL_TROUGH' and 1.5 returns the text.
    - `cvd_state`, `survival_gate`, `lifecycle_stage` and `margin_cause` are enums or text.
14. **Filing deadlines are rules, not a fixed lag.**
    - 10-K: 60, 75 or 90 days after year end for large accelerated, accelerated and other filers (Form 10-K General Instruction A(2), S-new-r1-3).
    - 10-Q: 40 days for accelerated and large accelerated filers, 45 for the rest (FRM 1330.1, S88).
    - 20-F: within four months (Form 20-F General Instruction A(b), S-new-r1-5).
    - Form NT (12b-25) is filed no later than one business day after the due date, and extends the deadline by 15 calendar days for annual and 5 for quarterly reports (Rule 12b-25, S-new-r1-4).
    - Filer status today comes from the submissions `category`. Every watchlist operating company checked is "Large accelerated filer", except SpaceX ("Non-accelerated filer") and Infleqtion, which lists only "Emerging growth company"; ETV was not checked. Historical status is not in companyfacts.
15. **Foreign, de-SPAC and newly listed filers break the 10-K/10-Q assumptions** (S-new-r1-1).
    - **GlobalFoundries (GFS):**
      - It has filed a 20-F every year 2022–2026 and quarterly 6-Ks, with no switch to 10-K/10-Q. Its facts are ifrs-full in USD, from the 20-F and from 6-Ks.
      - Its 2024 Q1 and Q2 6-Ks carry no XBRL. Those income-statement quarters arrive a year later as comparatives (6-Ks of 2025-05-06 and 2025-08-05). Total assets at 2024-03-31 and 2024-06-30 never arrive; only cash does, through cash-flow comparatives. The Q3 6-K (2024-11-05) is complete.
      - 6-K is not a fact-refresh trigger (`FACT_FORMS`), so new 6-K facts arrive through the 7-day backstop (`xbrl_facts.FACTS_BACKSTOP`).
      - 6-Ks carry no item codes, so the 8-K red-flag map is silent for them.
      - IFRS going-concern notes disclose "material uncertainties" that "may cast significant doubt": IAS 1.25, which becomes IAS 8.6K for periods from 2027-01-01 (S-new-r1-6). This wording differs from AS 2415's "substantial doubt".
    - **Infleqtion (INFQ)** files under the CIK of Churchill Capital Corp X, the SPAC it merged with. The name changed 2026-02-18; the closing 8-K was filed 2026-02-17 with items 2.01 and 5.06.
      - Its FY2025 net income is −$66,931,068 in the 10-K filed 2026-03-31, which presents the SPAC.
      - The same year is −$32,228,000 in the 10-Q filed 2026-08-18, which presents Infleqtion.
      - Total assets at 2025-12-31 are $424.9M (the trust) against $115.3M.
      - The merger window also carries an 8-K 3.01 (2026-02-03) and a 4.01 (2026-03-26). Their causes have not been read.
    - **SpaceX (SPCX)** priced its IPO on 2026-06-12 (424B4).
      - The S-1 financials are not in companyfacts, which holds only fee facts from it.
      - XBRL history is the first 10-Q: H1 and Q2 of 2026 and 2025, plus balance sheets at 2025-12-31 and 2026-06-30. There is no FY2025 total, so there is no TTM until the FY2026 10-K.
      - Basic weighted shares are 5,864M for Q2 2026 against 2,929M for Q2 2025 (+100.2%). That mix of pre- and post-IPO counts is Round 3's case.
16. **Customer-signal inputs (D-M04-1) are partly stored.**
    - `rpo` (`RevenueRemainingPerformanceObligation`) is already mapped. 10 of the 14 US-GAAP watchlist filers checked tag it (not AAPL, META, MRVL or INFQ; GFS reports under IFRS and was not checked). Micron's was $134,000M at 2026-09-03.
    - Major-customer percentages are dimensional only: none of the 15 companyfacts files carries `ConcentrationRiskPercentage1`. They sit on `srt:MajorCustomersAxis` in the instance (DS12).
    - 8-K 1.02 is typed and routed to M04.
    - M02 already keeps supplier and customer links (`supply/`; `config/aliases.toml` `customer = true`).
    - The customer-link return evidence (S44, S45) and the design belong to Round 5.
17. **Guidance-record examples need care at the edges** (S-new-5, S-new-r1-9).
    - Micron hit its Q3 FY2023 guide given in the Q2 release of 2023-03-28 (10-Q filed 2023-06-29):
      - revenue $3,752M against $3.70B ± $0.20B;
      - GAAP gross margin −17.8% against (23.0%) ± 2.5%, above the range;
      - GAAP diluted EPS −$1.73 against ($1.79) ± $0.07.
    - Intel guided FY2022 revenue at $76.0B (2022-04-28), then revised it to "$63 billion to $64 billion" (2022-10-27). Actual: $63,054M.
    - Intel's April 2022 release guided full-year revenue, non-GAAP EPS ($3.60), net capital spending ($27B) and adjusted free cash flow. Its April 2023 release guided Q2 only.
    - Its January releases guided Q1 only in both 2022 and 2023: the full-year 2022 outlook came at the 2022-02-17 investor meeting. Comparing consecutive releases (October 2022 → January 2023) would therefore report a "removal" that is only seasonal.

**What is buildable now**

| Need | Status | Gap or new work |
|---|---|---|
| Piotroski F, Altman Z″, Beneish, accruals, inventory days | Buildable from `fact` and `series` | Shares split first (F's equity signal) |
| Altman Z (manufacturers) | Needs cover shares × Tiingo price | Watchlist and tracked names only (DS8) |
| Dechow misstatement score | Needs 6–7 extra concepts | S1.3 |
| ROIC (approved Q2 trough row) | Operating income, equity, long-term debt, cash, short-term investments mapped | Tax rate and current-debt tags (S1.3); definition and use in Round 6 |
| R&D and capex intensity (approved Q2 row) | `rd`, `capex`, revenue mapped | Which capex definition: question 1.2 |
| Capex split (A2) | Revenue and `capex` mapped | `ppe_net` and `da` tag fixes (S1.3, item 10); method per question 1.5 |
| Peer z (Q1/Q2) | Code ready (`frames.py`) | No stored peers; one companyfacts request per peer |
| Restatement deltas | Data in `fact` | Walk across tags (defect 2a); de-SPAC boundary (item 15) |
| 8-K red flags | Typed in `event`, full history | 4.02 text only for filings fetched since backfill; 6-K filers have no items |
| Late filings, amendments, shelves, 424B, S-8 | `filing` metadata; filer status in submissions `category` | Documents not fetched; due dates per S1.6 |
| Going-concern and covenant text | FTS5 over latest 10-K/10-Q and new 8-Ks | Prior years (DS7): about 1 request per document. One prior 10-K each = 16; a full 10-K/10-Q history since XBRL is about 960 requests, about 4 minutes at the measured pace (D-SEC-18, about 4,000 requests in 15 minutes); storage size not measured. IFRS wording for 20-F filers |
| Dilution | Buybacks and equity proceeds mapped (`moneyflow/allocation.py`) | Basic/diluted weighted-average and SBC concepts; 424B security class |
| Runway and maturities | Cash, short-term investments, OCF, capex mapped; maturity, revolver and current-debt tags in `fact` where non-dimensional | Revolver capacity often dimensional |
| Customer base (D-M04-1) | `rpo` mapped (10 of 14 US-GAAP filers); 8-K 1.01/1.02 typed; M02 supplier/customer links | Major-customer % dimensional only (DS12); design in Round 5 (S44, S45) |
| Market share (approved Q2 row) | — | No free structured source. Grade-B press figures (S36, S-new-69) or owner entry with source → DS16. "Missing" until then (how missing rows count: Round 6) |
| Moat and challengers (approved Q2 row) | — | M06 not built → "missing (M06)" |
| Segment revenue, customer concentration %, multi-class cover shares | — | Dimensional: missing from companyfacts and from `instance.py` (DS12) |
| Non-operating and fair-value swings | Tags in `fact`, for example: GOOG FY2025 `NonoperatingIncomeExpense` $29,787M = 18.8% of pretax $158,826M (equity-security gains $24,080M); MSTR FY2025 `CryptoAssetUnrealizedLossOperating` $5,403M inside a $5,444M operating loss; INTC FY2025 valuation-allowance change $2,629M | Routing in Round 2. MSTR's swing sits inside operating income, so only the model tag (1.7) catches it |
| Gross profit | `gross_profit` mapped | Not tagged by AMZN (none since FY2009), GOOG, META, SPCX, INFQ → derived revenue − cost of revenue, labelled. Amazon's cost of sales excludes fulfillment (S-new-22), so it is not like-for-like with peers |
| Contract assets before ASC 606 (Round 2 GE fixture) | GE tagged `UnbilledContractsReceivable`: $25,162M (2016-12-31) → $28,861M (2017-12-31), with quarters between; `ContractWithCustomerAssetNetCurrent` only from 2019-12-31 | Pre-2018 alias in the concept, marked; GE's line label to confirm in the 10-K |
| Credit-rating actions | — | No free structured source; text in stored 8-Ks and releases only (old engine's "Credit Rating Action", severity elevated; keep or drop in Rounds 3–4) → DS17 |
| Unit KPIs | Tesla EX-99.1 stored (DS2) | Not parsed; EX-99.2 not fetched |
| Industry pricing and volume | — | DS13 |
| Guidance record (R19) | Ledger built; guided-vs-actual for capex only | Revenue, EPS and gross-margin hit rate; "removed" kind (S1.7, question 1.9) |
| Cycle history | XBRL from 2009–2011 | Pre-2009 troughs missing |
| Delisted companies' prices (Round 6 backtests) | Tiingo coverage of delisted tickers unverified (DS8) | Probe in Part 8's live check; fallback: EDGAR-only labels with no overreaction gauge |

**Fetch plan for this round's items**

| Fetch | Scope | One-off | Ongoing | Runs in |
|---|---|---|---|---|
| R1 cover page (class-summed cover count) | Multi-class filers: GOOG, META, MSTR, SPCX | About 37 (last 3 years); full history about 165 (estimate at 4 filings a year; the R-page format of filings before about 2011 is unverified) | 1 per new 10-K/10-Q, about 13 a year | Logon refresh, after facts |
| Submissions JSON (SIC, fiscal year end, filer status) | Each proposed peer not yet in `entity` | 1 per peer | Weekly with facts | Part 2 owner script |
| EDGAR browse-by-SIC | One per SIC in use (3674, 3572, 3663, 7370 …) | About 5 | — | Part 2 owner script (not fetched in this research: SEC refused it without the engine's declared user agent) |
| Peer facts | Confirmed peers | About 1 per peer | 7-day backstop | Logon refresh |

At the measured pace each row takes under a minute, far inside the 3-hour task limit (D-M02-12). Owner scripts take `refresh.lock` (D-M02-53).

### Worked example — Micron FY2022 → FY2023 (CvD case "expect CYCLICAL_TROUGH")
Sources: companyfacts as filed (S-new-1, S-new-r1-1). The first-filed and latest values are equal for every row. Release figure: S-new-5.

| Concept (engine) | FY2022 | FY2023 | Change | Source |
|---|---|---|---|---|
| revenue | $30,758M | $15,540M | −49.5% | 10-K (XBRL), release |
| cost_of_revenue | $16,860M | $16,956M | +0.6% | 10-K (XBRL) |
| gross_profit | $13,898M | $(1,416)M | GM 45.2% → −9.1% | 10-K (XBRL) |
| operating_income | $9,702M | $(5,745)M | margin 31.5% → −37.0% | 10-K (XBRL) |
| operating_cash_flow | $15,181M | $1,559M | −89.7% | 10-K (XBRL), release |
| capex (PP&E payments, first tag) | $12,067M | $7,676M | −36.4% | 10-K (XBRL) |
| Micron's own "net capex" | — | $7.01B | about $0.67B below the tag | release (company definition) |
| depreciation (`Depreciation`) | $7,030M | $7,670M | +9.1% | 10-K (XBRL) |
| inventory (`InventoryNet`) | $6,663M | $8,387M | +25.9% | 10-K (XBRL) |
| inventory write-down (`InventoryWriteDown`) | 0 | $1,831M | — | 10-K (XBRL) |
| inventory days (inventory ÷ COGS × 365) | 144.2 | 180.5 | +36 days | computed |

Point-in-time rows (real, S-new-1, S-new-r1-1):

| Case | What the filings hold | What `series` does today |
|---|---|---|
| Tag switch | MU FY2018 revenue first filed 2018-10-15 under `Revenues` | first_filed 2019-10-17 under the new tag; an as-of-2018-11 read finds nothing |
| Split | MSTR Q3 2023 diluted shares first 14,221,000 (filed 2023-11-01), re-reported 142,214,000 (filed 2024-10-31) | first vs latest reads as +900% dilution, or as a "restatement" |
| Multi-class | META and MSTR: no non-dimensional period-end or cover count (404); GOOG: no dei count; SPCX: no dei facts | share metrics silently missing |
| Non-periodic source | Alphabet 2023 net income in a DEF 14A (2026-04-24) | can become "latest" |
| Wrong-meaning tag | INTC FY2019 `DepreciationAndAmortization` (nonproduction) $200M; `Depreciation` $9,204M | `da` = $200M |
| Tag stops when the filer moves to a broader tag | MU `PropertyPlantAndEquipmentNet` last 2020-05-28; finance-lease-inclusive tag to 2026-09-03 | `ppe_net` empty after FY2019 |
| De-SPAC entity change, same CIK | INFQ FY2025 net income −$66.9M (SPAC, 10-K 2026-03-31) vs −$32.2M (Infleqtion, 10-Q 2026-08-18) | reads as a restatement (the loss 52% smaller) |
| Missing interim XBRL | GFS 2024 Q1–Q2 6-Ks without XBRL; total assets at 2024-03-31 and 2024-06-30 absent | instants missing; the quarters are unknown to as-of reads until a year later |

How M04 reads Micron:
- **Q2 (franchise):** gross margin collapsed, but the 10-K attributes it to lower DRAM and NAND prices, inventory write-downs and $382M of underutilization cost (S-new-5). The peer gross-margin gap must confirm.
- **Q1 (shared?):** WDC files with the SEC but sits in SIC 3572, so a 3674 proposal misses it (question 1.4). SK hynix and Samsung do not file with the SEC, so they are "missing peers" (R24).
- **Supply response:** capex was cut 36%, consistent with the coordinated supply cuts in S37. The depreciation-based split below shows the cut fell on growth capex (FY2022 $5,037M → FY2023 $6M) while maintenance held.
- **Capex definition:** the company states $7.01B and the tag gives $7,676M. This is exactly the case where the user must see which definition a value uses.

### Worked example — capex split (A2) on Micron, Intel and Microsoft (S-new-r1-1; $M)
Method used here: Greenwald's growth capex = (Σ PP&E ÷ Σ revenue over the five prior fiscal years) × the year's revenue change, and maintenance = total capex − growth. PP&E is net, and from FY2020 the finance-lease-inclusive tag (item 10). Depreciation = the `Depreciation` tag. Capex = the PP&E payments tag.

**Micron**

| FY (end) | Revenue | Δ revenue | Total capex | PP&E ÷ sales, 5 prior years | Greenwald maintenance | Inside 0…capex? | Depreciation | Growth capex on depreciation |
|---|---|---|---|---|---|---|---|---|
| FY2019 (2019-08-29) | 23,406 | −6,985 | 9,780 | 0.805 | 15,404 | no (above) | 5,340 | 4,440 |
| FY2020 | 21,435 | −1,971 | 8,223 | 0.940 | 10,076 | no (above) | 5,570 | 2,653 |
| FY2021 | 27,705 | +6,270 | 10,030 | 1.084 | 3,231 | yes | 6,130 | 3,900 |
| FY2022 | 30,758 | +3,053 | 12,067 | 1.100 | 8,709 | yes | 7,030 | 5,037 |
| FY2023 | 15,540 | −15,218 | 7,676 | 1.157 | 25,285 (3.3× capex) | no (above) | 7,670 | 6 |
| FY2024 | 25,111 | +9,571 | 8,386 | 1.422 | −5,221 | no (negative) | 7,700 | 686 |
| FY2025 | 37,378 | +12,267 | 15,857 | 1.497 | −2,508 | no (negative) | 8,280 | 7,577 |
| FY2026 (53 weeks, 2026-09-03) | 133,188 | +95,810 | 30,712 | 1.436 | −106,890 | no (negative) | 9,420 | 21,292 |

**Intel** (revenue fell every year; Greenwald above total capex in all four years)

| FY | Revenue | Total capex | Greenwald maintenance | Depreciation | Growth capex on depreciation |
|---|---|---|---|---|---|
| 2022 | 63,054 | 24,844 | 36,533 | 11,128 | 13,716 |
| 2023 | 54,228 | 25,750 | 33,172 | 7,847 (−29.5%: useful life 5 → 8 years) | 17,903 |
| 2024 | 53,101 | 23,944 | 25,092 | 9,951 | 13,993 |
| 2025 | 52,853 | 14,646 | 14,953 | 10,757 | 3,889 |

**Microsoft FY2026** (capex ahead of revenue):
- Revenue $331,839M (+$50,115M); capex $115,948M.
- Greenwald maintenance is $90,086M (77.7% of capex), inside the range. Depreciation is $34,300M (29.6%).
- Greenwald therefore calls most of the build-out "maintenance".

What the split changes downstream (Micron):
- Free cash flow on total capex: FY2023 −$6,117M; FY2025 $1,668M; FY2026 $58,963M.
- The same on depreciation as maintenance: −$6,111M; $9,245M; $80,255M.
- The choice matters in build-out years, not in the trough.

### Worked example — stage and model tags on the watchlist (S-new-r1-1; last three fiscal years with all three cash-flow totals)

| Company | Years | Stage on total investing cash flow (5.1a as drafted) | Stage on core investing (capex + acquisitions − asset and business sale proceeds) | Revenue CAGR, 3 years | Under 1.6a / 1.7a |
|---|---|---|---|---|---|
| AAPL | FY2023–25 | Shake-out ×3 (investing +$3,705M, +$2,935M, +$15,195M) | Mature ×3 | +1.8% | mature |
| MSFT | FY2024–26 | Mature ×3 | Mature ×3 | +16.1% | mature |
| AMZN | 2023–25 | Mature, mature, growth | same | +11.7% | mature |
| GOOG | 2023–25 | Mature ×3 | same | +12.5% | mature |
| META | 2023–25 | Mature ×3 | same | +19.9% | mature |
| GFS | 2023–25 | Mature ×3 (IFRS) | same | −5.7% | mature |
| MRVL | FY2024–26 | Mature, mature, shake-out (investing +$2,098M) | same (divestiture proceeds $2,479M) | +11.4% | mature (2 of 3) |
| TSLA | 2023–25 | Growth ×3 | same | +5.2% | growth |
| NVDA | FY2024–26 | Mature ×3 | same | +100.0% | review: mature with revenue CAGR > 25% |
| MU | FY2024–26 | Mature, mature, growth | same | +104.6% | review: mature with revenue CAGR > 25% |
| INTC | 2023–25 | Growth ×3 (financing +$8,505M, +$11,138M, +$11,587M) | same | −5.7% | review: growth with falling revenue |
| BA | 2023–25 | Mature, introduction, shake-out | same | +10.3% | review: no stage holds 2 of 3 |
| MSTR | 2023–25 | Growth, introduction, introduction | same | −1.5% | tag `asset_treasury` routes it; stage review |
| INFQ | — | SPAC-era flows only (2024: 0 / 0 / 0) | — | — | unassigned (one post-merger year) |
| SPCX | — | no fiscal year in XBRL | — | — | unassigned |
| ETV | — | fund (N-CSR) | — | — | tag `fund` |

First run under 1.6a: 8 stages assigned, 5 review items (NVDA, MU, INTC, BA, MSTR), 2 unassigned. Under 5.1a as drafted, Apple would be routed as shake-out, and Intel as a growth name (M-score without SGI, Z as a warning only) in the years CvD expects decline.

### Worked example — guidance record (S-new-5, S-new-r1-9)

| Case | Guide | Actual | Under 1.9a |
|---|---|---|---|
| MU Q3 FY2023 revenue | $3.70B ± $0.20B (release 2023-03-28) | $3,752M (10-Q 2023-06-29) | hit |
| MU Q3 FY2023 GAAP gross margin | (23.0%) ± 2.5% | −17.8% | hit (above range) |
| MU Q3 FY2023 GAAP diluted EPS | ($1.79) ± $0.07 | −$1.73 | hit |
| INTC FY2022 revenue | $76.0B (2022-04-28) → $63–64B (2022-10-27) | $63,054M | hit on the latest guide; at least one downward revision (−17.0% against the first; the July 2022 release was not read) |
| INTC April 2023 release | April 2022 release guided FY revenue, non-GAAP EPS, net capex and adjusted FCF; April 2023 guided Q2 only | — | `removed` (4 metrics, no stated reason) |
| INTC January 2023 release | Q1 only; January 2022 was Q1 only too | — | not flagged (a consecutive-release diff would flag it falsely) |

### All cases (data layer)
1. Tag present and stable → use it.
2. Tag switch, same or different value → walk all of the concept's tags in filed order. Amazon's capex switch also changed the value by 15.8%.
3. Fallback tag broader than the concept → visible marker. Cases:
   - capex productive assets (AMZN from FY2016, NVDA from FY2022);
   - Micron's long-term debt, reported only as `LongTermDebtAndCapitalLeaseObligations` after `LongTermDebtNoncurrent` stops at 2013-05-30;
   - net PP&E including finance-lease right-of-use assets (MU, INTC, META, GOOG, TSLA).
4. Company extension tag only → instance read where a recipe needs it (D-M02-32). Example: NVDA capex FY2013–FY2021, to confirm.
5. Dimensional only → "missing: dimensional". Examples: multi-class cover shares, segments, customer-concentration %, many revolvers.
6. Tag absent → missing, never zero. A reported zero is kept (Rivian's pre-revenue gross profit of 0). Gross profit not tagged (AMZN, GOOG, META, SPCX, INFQ) → derived, labelled.
7. Period before XBRL, or before the tag's first use → "insufficient history".
8. Value revised:
   - Big R restatement or little r revision;
   - recast (discontinued operations, new standard, segment change);
   - split.
9. Value arriving in an 8-K, DEF 14A, S-1 or S-4 → not "latest" for periodic analysis.
10. Year-to-date-derived quarters, including filers with no discrete Q4 facts (Rivian).
11. Instants at the balance-sheet date vs the cover date.
12. 52/53-week years and off-calendar fiscal years (MU FY2026: 370 days; WDC FY2026 quarters shift by a week).
13. Peers:
    - in tolerance;
    - out of tolerance;
    - non-SEC (SK hynix, Samsung);
    - outside the subject's SIC (QCOM 3663, WDC 3572);
    - inside the SIC but another business (solar in 3674);
    - an acquisition year (AMD 2022 includes Xilinx);
    - fallback-tag values;
    - fewer than 5 peers.
14. Financials (SIC 6000–6799) and funds (ETV files N-CSR) → excluded from scores, unless a model tag says otherwise. Strategy is SIC 6199; its `asset_treasury` tag keeps the liquidity gate running (1.7).
15. Company not on the watchlist → no stored facts; owner-run fetch.
16. Bankrupt or delisted company → `filing_overdue` once the due date passes (S1.6); the last state is kept and labelled with its as-of date (Invitae never filed an FY2023 10-K).
17. Wrong-meaning tag inside a concept (INTC `DepreciationAndAmortization`) → removed from the concept; the probe report compares overlapping tags.
18. Foreign private issuer (GFS):
    - 20-F annual plus 6-K interim XBRL in ifrs-full;
    - 6-K XBRL may be missing (GFS 2024 Q1–Q2);
    - no 8-K items;
    - IFRS going-concern wording;
    - semiannual reporters elsewhere have no TTM until two halves exist;
    - non-USD units kept apart (none on the watchlist).
19. Switch from 20-F/6-K to 10-K/10-Q → both form families accepted, switch date flagged. GFS has not switched as of its 2026-02 20-F.
20. De-SPAC under the SPAC's CIK (INFQ) → the closing 8-K (2.01 + 5.06) is a boundary: values for earlier periods are read only from filings for periods ending after it. Differences across the boundary are not restatements.
21. Recent IPO (SPCX) → no XBRL before the first 10-Q, no TTM until the first 10-K, no dei cover facts; pre-IPO share counts go to Round 3.
22. Transition reports (10-KT, 10-QT; 8-K 5.03 change in fiscal year) → odd-length periods kept as reported, never annualized.

Complete for the watchlist, its named peers and the pack's fixtures as of 2026-10-12. Known omissions: banks and insurers (excluded); ADRs filing 40-F (none on the watchlist); filers with restated XBRL from before 2011 (not checked).

### Suggestions
- **S1.1 As-of reads first.** Add `facts_as_of(cik, concept, as_of)` built from `fact`:
  - use facts filed on or before `as_of`, from periodic forms only:
    - 10-K, 10-K/A, 10-Q, 10-Q/A, 10-KT, 10-KT/A, 10-QT, 10-QT/A, 20-F, 20-F/A, 40-F, 40-F/A;
    - 6-K and 6-K/A for filers whose annual report is a 20-F or 40-F.

    This aligns with `refresh.FACT_FORMS` and `xbrl_facts.REFRESH_FORMS`, which gain the transition forms. 6-K joins the refresh trigger for 20-F filers;
  - apply tag priority *after* the time filter;
  - apply the de-SPAC boundary (case 20);
  - derive quarters and TTM from those facts.

  `series` stays for live views. The restatement walk (Round 2), the guidance record (S1.7) and backtests (Round 6) use `fact`.

  Fixtures are stored as companyconcept files per tag, not whole companyfacts files: GE's `NetIncomeLoss` is 66 KB against 6.1 MB for GE's companyfacts and 4.2 MB for Micron's. Fixture cases:
  - Micron FY2018 revenue known as of 2018-10-15;
  - WDC FY2023 revenue = $12,318M as of 2024 (S-new-1);
  - INFQ FY2025 net income across the boundary;
  - GFS 2024 6-K gap;
  - INTC `da` FY2019.
- **S1.2 Shares split** per question 1.1.
- **S1.3 One M04 extra-concept list, plus three concept fixes.** It reuses `Concept`, needs no new fetch, and reports a missing tag as a probe, never as zero.
  - **Fixes:**
    - `da`: add `Depreciation`; drop `DepreciationAndAmortization` (nonproduction); keep depreciation as its own concept for A2.
    - `ppe_net`: add the finance-lease-inclusive tag as a marked broader fallback.
    - Contract assets: add `UnbilledContractsReceivable` as a marked pre-2018 alias.
  - **Already mapped, not repeated here:** `rpo`, `rd`, `ppe_net`, `da`.
  - **Extra tags:**
    - `IncomeTaxExpenseBenefit`, pretax income, `IncomeLossFromContinuingOperations` (with operating income, these give ROIC's NOPAT);
    - `DebtCurrent` / `LongTermDebtCurrent`, `ShortTermBorrowings`, `CommercialPaper` (with equity and cash, these give ROIC's invested capital);
    - maturities year 1–5 and after year 5, `LineOfCreditFacilityRemainingBorrowingCapacity`, restricted cash;
    - `ContractWithCustomerLiabilityCurrent` (with `DeferredRevenueCurrent` before 2018), `ContractWithCustomerAssetNetCurrent`, `ContractWithCustomerPerformanceObligationSatisfiedInPreviousPeriod`;
    - `ShareBasedCompensation`, `ProceedsFromIssuanceOfCommonStock`, plan-issuance proceeds, `ProceedsFromIssuanceOfLongTermDebt`;
    - `LongTermInvestments`, `PreferredStockValue`, `AccruedIncomeTaxesCurrent`;
    - investing and financing cash-flow totals, `PaymentsToAcquireBusinessesNetOfCashAcquired`, divestiture and asset-sale proceeds (stage, 1.6);
    - `InventoryWriteDown`, `AssetImpairmentCharges`, `GoodwillImpairmentLoss`, `RestructuringCharges`, `AdvertisingExpense`;
    - `NonoperatingIncomeExpense`, `EquitySecuritiesFvNiGainLoss`, `IncomeTaxReconciliationChangeInDeferredTaxAssetsValuationAllowance`, `CryptoAssetUnrealizedLossOperating`, `CryptoAssetFairValue` (Round 2 routing);
    - `PropertyPlantAndEquipmentGross` and its finance-lease-inclusive counterpart (Greenwald variant check).
- **S1.4 Method visible.** Every M04 value carries its tag and accession, and fallback values are marked (question 1.2).
- **S1.5 Signal record and names fixed now** (question 1.8).
  - M04 becomes the first writer of the D13 `signal` table. Dechow's score is named `misstate_f`; Piotroski keeps `f_score`.
  - No signal is hidden. A value that a rule does not use is shown with its reason (D10).
  - Signals out, consolidated across Rounds 1–6:
    - "✓" = may carry weight in that timeframe once D13 weights exist;
    - "info" = shown with weight 0;
    - "*" = name proposed here, where a round gave none.

  | Signal | Type | Round | MY | PT | ST |
  |---|---|---|---|---|---|
  | `cvd_state` | enum | 6 (approved) | ✓ | ✓ | info |
  | `cvd_confidence` | 0–1 | 6 (approved) | ✓ | ✓ | info |
  | `survival_gate` | pass / fail / incomplete | 4 (approved; third value new) | ✓ | ✓ | ✓ |
  | `overreaction_gap` | % | 6 (approved) | ✓ | ✓ | info |
  | `f_score`, `g_score`, `z_score` | int, int, float | 6 (approved) | ✓ | ✓ | info |
  | `f_quality`* | 0–4 | 6 | ✓ | ✓ | info |
  | `norm_earnings`* | $ (two bases) | 6 | info | info | info |
  | `distress_score` | float + variant | 4 | ✓ | ✓ | info |
  | `runway_q`*, `maturity_wall`* | quarters; $ vs liquidity | 4 | ✓ | ✓ | ✓ |
  | `going_concern`*, `covenant_status`* | enum class + quote | 4 | ✓ | ✓ | ✓ |
  | `eq_cash`, `contract_asset_gap`, `deferred_rev_gap` | ratio; flags | 2 | ✓ | ✓ | info |
  | `mscore`, `misstate_f` | float | 2 | ✓ | ✓ | info |
  | `restatement` | event | 2 | ✓ | ✓ | ✓ |
  | `restate_delta`, `estimate_share` | % + label | 2 | ✓ | ✓ | info |
  | `net_issuance_yoy`, `issuance_band`* | log change; enum | 3 | ✓ | ✓ | info |
  | `composite_issuance`*, `sbc_block`*, `financing_capacity`* | log; ratios; $ and % | 3 | info | info | info |
  | `overhang_pct`* | % | 3 | ✓ | ✓ | info |
  | `financing_pressure` | warning | 3 | ✓ | ✓ | ✓ |
  | `margin_cause` | enum + quote | 5 | ✓ | ✓ | info |
  | `gm_delta_pp`, `credit_share_of_gp`, `inventory_sales_gap` | pp; % | 5 | ✓ | ✓ | info |
  | `unit_gp`, `unit_gp_ex_credits` | $ per unit | 5 | info | info | info |
  | `lifecycle_stage` | enum (routing, not a vote) | 1 (moved from 5) | info | info | info |
  | `capex_maint`*, `capex_growth`* | $ + method | 1 | info | info | info |
  | `guidance_hit_rate`* | % + n | 1 | ✓ | ✓ | info |
  | `filing_overdue`* | flag + days | 1 | ✓ | ✓ | ✓ |

  - **Timeframe parameters (module template).** M04's inputs are filings, so one computation serves all three timeframes. What differs by timeframe lives in the M01 profiles (D12): the weights (info = 0) and, later, any persistence window. Each row is written once per timeframe with the profile's parameters recorded in `method`.
- **S1.6 `filing_overdue`** (renamed from `stale`; "stale" keeps its M04_FINANCIALS.md meaning: the last known CvD state between filings, shown with its as-of date).
  - **Due date** = period end + the form's deadline for the filer's status:
    - 10-K: 60/75/90 days;
    - 10-Q: 40/40/45 days;
    - 20-F: four months.

    An NT filing extends it by 15 days (annual) or 5 days (quarterly). Sources: S-new-r1-3, S88, S-new-r1-4, S-new-r1-5.
  - **Status:** the submissions `category` for live use. In backtests, where historical status is unknown, use the longest deadline so nothing is flagged early.
  - **Flag:** from the first refresh after the due date. This is a backstop, not the first signal.
  - Invitae: submissions show "Large accelerated filer", its last reported status. Its FY2023 10-K was due between 2024-02-29 (60 days) and about 2024-04-01 (90 days), depending on its status then. No NT 10-K was filed. The 8-K 3.01 (2024-02-06), 1.03 + 2.04 (2024-02-14) and Form 25-NSE (2024-02-21) all came first. The draft rule (expected date + 45 days) would have waited until about mid-April.
  - Round 6's failure-mode row "Stale last filing" takes this rule and name.
- **S1.7 Guidance record (Q2)** (question 1.9).
  - Revenue, EPS and gross-margin hit rate per company, on the guide's own basis:
    - GAAP actuals from the first-filed periodic facts (`facts_as_of`);
    - non-GAAP actuals from the company's own stated reconciliation (the D-M02-29 stated-actuals pattern).
  - Add a "removed" change kind, for the profile's "quiet target removals", plus an "expired" kind for guided periods that have ended.
  - The functions live in `guidance/` and are shared with M11.
- **S1.8 Register entries in DATA_SOURCES.md:**
  - DS12 dimensional facts: segments, customer concentration (`srt:MajorCustomersAxis`), multi-class cover shares. The open EdgarTools evaluation (S41) bears on reading them and is decided with question 5.4;
  - DS13 industry price and volume series (free FRED producer prices; SIA/WSTS monthly at grade B; to check);
  - DS14 unit KPIs beyond Tesla (generalise DS2, including EX-99.2 letters);
  - DS15 historical 4.02 8-K texts;
  - DS16 market share: grade-B third-party figures or owner entry with source;
  - DS17 credit-rating actions: text only;
  - DS7 gains the request counts above; DS8 gains "delisted-ticker coverage unverified; probe before Part 8".
- **S1.9 Housekeeping.**
  - SOURCES.md uses S101 twice. Renumber one when the S-new IDs are assigned.
  - Part 1 also updates M00_SEC_DATA.md (concept fixes, forms), M00_STORAGE.md (signal migration, entity boundary) and M00_UI.md (capex marker and legend) in the same commit.
- **S1.10 Review kinds from this round:**
  - `m04_peer`: one per operating watchlist company at setup (about 13, a one-off batch), then only for new names;
  - `m04_stage`: 5 at first run (worked example), then on change, about yearly.

  After setup, both kinds enter the M04 weekly cap set with the full review-kind list. Overdue filings are digest warnings, not review items.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| `series` first vs latest | A tag switch makes "first" a later comparative; 8-K or DEF 14A facts become "latest" | As-of reads from `fact`, periodic forms only |
| Shares | Cover and period-end dates mixed; multi-class counts missing; splits | Separate concepts; "missing: multi-class" label; split guard |
| Capex fallback | Broader tag (+15.8% for Amazon FY2016); peer z mixes definitions | Visible marker; excluded from peer statistics; own history on one tag |
| `da` concept | Nonproduction D&A read as total (INTC $200M vs $9,204M); empty for MSFT, GOOG | `Depreciation` added, nonproduction tag dropped; probe compares overlapping tags |
| `ppe_net` concept | Stops for five names that moved to the finance-lease-inclusive tag | Finance-lease-inclusive tag as a marked fallback |
| Greenwald maintenance capex | Out of range in busts and booms (MU FY2023 3.3× capex; FY2026 negative); calls a build-out "maintenance" (MSFT 77.7%) | Range test; depreciation default (1.5a); method tag on every value |
| Depreciation as maintenance | Useful-life changes move it (INTC 2023 −29.5%); lags replacement cost | Method tag; useful-life changes flagged by the estimate-change finder (Round 2) |
| Life-cycle stage | Securities flows (AAPL shake-out ×3); partner financing (INTC growth ×3); treasury assets (MSTR) | Core investing sign; revenue-trend check → review; model tags |
| SIC routing | MSTR (6199) excluded as a financial; AMZN peers by SIC are mail-order retailers | Model tag overrides SIC; owner-curated peers |
| Peer offset | The cycle turns inside a 1–2-month offset; 53-week years (WDC 36 days) | Per-type tolerance; each peer's end date shown; 53-week flag |
| SIC peers | Coarse or stale codes; solar in 3674; QCOM and WDC outside 3674; key peers abroad | Owner curation (R24); non-SEC peers stored by name and flagged missing |
| Peer acquisitions | AMD +43.6% in 2022 includes Xilinx | Flag acquisition years (8-K 2.01, `BusinessAcquisition*` tags) |
| History depth | XBRL starts 2009–2011 and later for some concepts | "Insufficient history", never "first deep decline" |
| Frames in backtests | Last-filed values | Live breadth only |
| De-SPAC history | SPAC facts under the same CIK read as a restatement (INFQ FY2025 loss 52% smaller) | Boundary at the closing 8-K (2.01 + 5.06) |
| Foreign filers | 6-K XBRL gaps; no item codes; IFRS wording | Gaps shown; IFRS phrase in the finder; 6-K text scan (Round 4) |
| Filing overdue | Deadlines differ by status and NT extensions | Rule-based due date; longest deadline when status unknown |
| Signal encoding | Text in the NUMERIC `value` sorts above every number | `value_text` column (1.8a) |
| Guidance "removed" | Seasonal guidance patterns read as removals (Intel January releases) | Compare with the release at the same fiscal position a year earlier; ended periods are "expired" |

### Questions
This round carries nine questions, because the critique moved the stage, model-tag, capex-split, signal-record and guidance decisions ahead of Round 2. They can be answered in two sittings: 1.1–1.5 (data), then 1.6–1.9 (company profile and records). Each option names the case it gets wrong.

**1.1 Shares concepts**
- (a) *Recommended.* Four series: `shares_period_end`, `shares_cover` (kept on its own cover date), `shares_basic_wavg` and `shares_diluted_wavg`, plus `sbc`.
  - For multi-class filers with no non-dimensional count (GOOG, META, MSTR, SPCX), read the class-summed cover count from the filing's R1 page: about 37 requests for the last 3 years, then 1 per new filing in the logon refresh. Older history uses the basic weighted average, labelled.
  - Float shares for R22 = `dei:EntityPublicFloat` ÷ the close on its date (last business day of Q2), once a year, labelled "implied". M07 owns R22.

  Why: it matches your 2026-10-07 note, fixes four silent gaps and gives M07 a float in shares.
- (b) The four series; multi-class names use the basic weighted average only, labelled "lagging". Gets wrong: fast issuers. MSTR's cover count rose 35.5% while its weighted average rose 28.1% (Round 3); SPCX's post-IPO count is understated by period weighting.
- (c) Keep one series and add the diluted weighted average. Gets wrong: Apple's cover count stays mixed with period-end counts (dated 2025-10-17 for a 2025-09-27 year end), GOOG, META, MSTR and SPCX still have no count, and diluted moves with the profit sign (MSTR Q2 2025: 306.8M diluted vs 275.2M basic).

**1.2 Capex definitions: display, own history, peers** (closes the 2026-10-07 fallback item)
- (a) *Recommended.* One definition per use:
  - **Display:** the company's own definition (`config/capex_definitions.toml` and the D-M02-29 recipes, reconciled to stated figures per D-M02-32), with the standard-tag value beside it. Any fallback value carries a visible "≈ broader tag" marker and a legend; the tooltip stays.
  - **Own-history rows** (Q2 intensity vs own 3-year average, A2 split, free cash flow): the company's longest consistent tag series. A switch inside the window reads "definition changed" and that window is not scored. Amazon (productive assets FY2016–FY2025) is therefore scored on its own history.
  - **Peer statistics:** PP&E tag only. Fallback-only peers (AMZN, NVDA from FY2022) are listed as "not like-for-like" and excluded. A subject on the fallback keeps its own-history leg; its peer leg reads "not like-for-like".

  Why: the same Amazon year differs by 15.8% between the tags, too much to mix into a peer z, yet Amazon's own series is consistent.
- (b) Marker shown; fallback values included in peer statistics, flagged. Gets wrong: an AMZN or NVDA value sits about 16% high in the peer median.
- (c) A separate row per tag. Gets wrong: Amazon's PP&E-tag row is empty after FY2016, so its Q2 capex row goes missing.
- (d) Tooltip only (today). Gets wrong: the owner cannot see that Amazon's and NVIDIA's capex is broader; the open item stays open.

**1.3 Peer discovery**
- (a) *Recommended.* The engine proposes peers from 4-digit SIC: `entity.sic` and submissions `sic` (1 request per candidate), plus one owner-run EDGAR browse-by-SIC probe per SIC (about 5 requests). The owner confirms or edits them in `peer_group` (`m04_peer` items). Product-market peers beyond SIC are added by the owner (Intel: AMD, NVIDIA, Qualcomm; Micron: WDC). Non-SEC peers are stored by name as "missing".
  - Sample (S-new-r1-1): a 3674 proposal for MU or INTC brings MU, INTC, NVDA, AMD, TXN, AVGO, MRVL, GFS and ON, plus solar names (FSLR, ENPH) that the owner removes. It misses QCOM (3663) and WDC/STX (3572), which the owner adds.

  Why: follows R24 and avoids the 2 GB bulk file (S50).
- (b) Proposals from 3-digit SIC. Gets wrong: 367 adds printed circuit boards, passive and other components (3672, 3675–3679; S110) and still misses QCOM (366) and WDC (357).
- (c) The owner lists peers by hand only. Gets wrong: nothing new surfaces when an SEC filer enters the industry.
- (d) Bulk submissions.zip. Gets wrong: nothing on coverage, but about 2 GB per refresh (S50) for the same `sic` field.

**1.4 Peer period offset**
- (a) *Recommended.* TTM ±45 days; quarters and instants ±40 days. These are starting values, set from observed offsets: MU vs WDC 29 days (36 in WDC's 53-week FY2026), and D-SEC-9's −32/+34. The minimum quarter overlap is then 56%. Peers outside the tolerance show as "no comparable period" and count toward the fewer-than-5 fallback. Each peer's end date is shown and 53-week years are flagged. Why: WDC, Micron's only SEC memory peer, stays comparable while two-month mismatches are stopped.
- (b) TTM ±45; quarters and instants ±35. Gets wrong: WDC drops out for two quarters of its 53-week FY2026 (36 days).
- (c) Quarters and instants ±16, with a calendar-quarter fallback labelled "offset N days". Gets wrong: MU–WDC (29–36 days) never matches directly; every comparison goes through the fallback.
- (d) ±45 for everything (today). Gets wrong: a quarter can overlap only 51%, enough for the cycle to turn inside the gap.

**1.5 Capex split (A2): owner, method and consumers**
- (a) *Recommended.*
  - M04 owns `capex_split` in the data layer (Part 1); M05 reuses it.
  - Ladder: disclosed → project-level → **depreciation** (default, capped at total capex) → Greenwald shown beside it as a cross-check when inside the range of 0 to total capex.
  - One method per company for the whole displayed window, tagged on every value.
  - Inputs: revenue, `ppe_net` with the finance-lease fallback, `Depreciation`, capex per 1.2, five prior fiscal years for Greenwald.
  - Consumers: runway burn (S4.2), free cash flow after SBC (S3.4) and the Q2 capex row (S6.4) all use **total** capex. Maintenance capex is information only: "owner earnings" = OCF − maintenance capex − SBC, and "runway without growth capex".

  Changes A2's default from Greenwald to depreciation. Why: Greenwald is out of range in 6 of 8 Micron years and 4 of 4 Intel years, and inside the range it calls 77.7% of Microsoft's FY2026 build-out maintenance.
- (b) The approved ladder, with Greenwald used only when inside the range in every year of the window, else depreciation. Gets wrong: Microsoft FY2026 maintenance of $90,086M against $34,300M of depreciation, which understates owner earnings by about $56B.
- (c) The approved ladder as written (Greenwald each year, no range test). Gets wrong: Micron FY2023 maintenance at 3.3× total capex; FY2026 at −$106,890M.
- (d) M05 owns A2; M04 shows total capex only until M05 is built. Gets wrong: no M04 signal changes, but owner earnings and the Micron reading "the cut fell on growth capex" are unavailable until M05.

**1.6 Life-cycle stage** (replaces 5.1; Rounds 2–4 route on it)
- (a) *Recommended.*
  - Dickinson signs on operating cash flow, **core** investing (capex + acquisitions − asset and business sale proceeds) and financing.
  - A stage holds when 2 of the last 3 fiscal years agree.
  - "Ambiguous" when:
    - no stage holds 2 of 3;
    - the stage is shake-out;
    - the stage disagrees with the 3-year revenue CAGR: introduction or growth with a CAGR < 0, or mature or decline with a CAGR > 25% (starting values, unsourced).
  - Ambiguous → an `m04_stage` review item. Until confirmed, routing uses the owner's last confirmed stage, else "unassigned" (no stage-specific routing).
  - Owner override. Fewer than 3 fiscal years in XBRL → unassigned.

  Why: total investing cash flow reads Apple as shake-out three years running and Intel as growth while revenue falls. First run: 8 assigned, 5 reviews, 2 unassigned.
- (b) Dickinson on total investing cash flow, 2-of-3 persistence (5.1a as drafted). Gets wrong: AAPL shake-out FY2023–25; INTC routed as a growth name.
- (c) The owner sets every stage by hand. Gets wrong: stage changes such as BA (mature → introduction → shake-out, 2023–25) go unnoticed between owner reviews.
- (d) Rules on growth and cash flow (e.g. TTM revenue growth > 25% or 3-year cumulative CFO < 0 → young). Gets wrong: NVDA (+100% CAGR) and MU FY2026 (+104.6%) read "young"; Intel is never flagged.

**1.7 Owner model tags** (the vocabulary 3.4a and Round 4 rely on)
- (a) *Recommended.* Six tags with fixed routing in a hand-edited `config/company_models.toml` (the app never edits it, as with `capex_definitions.toml`). Each entry carries a one-line reason and source. A tag overrides SIC routing; an unknown tag is rejected at load. Initial entries: MSTR `asset_treasury`, ETV `fund`; the owner decides INFQ.

  | Tag | Meaning | Earnings quality (R2) | Dilution (R3) | Survival gate (R4) | Health scores |
  |---|---|---|---|---|---|
  | `issuance_funded` | Equity raises are the funding plan (early growth; RIVN when tracked) | normal | review, not warning | normal | normal |
  | `asset_treasury` | Main asset is a volatile holding at fair value (MSTR, 846,000 bitcoin at 2026-06-30) | NI, accruals, M-score `not_meaningful` | review | liquidity facts only | Z `not_meaningful` |
  | `reit` | Real estate investment trust | excluded | review | liquidity facts only | excluded |
  | `fund` | Registered or closed-end fund (ETV, N-CSR) | excluded | excluded | excluded | excluded |
  | `financial` | Bank, insurer, broker | excluded | excluded | excluded | excluded |
  | `spac_shell` | Blank check before closing (INFQ's CIK until 2026-02-13) | excluded | excluded | trust only | excluded |

  Why: MSTR's SIC (6199) would exclude it as a financial, yet its FY2025 operating loss of $5,444M is almost all a $5,403M unrealized bitcoin loss. Only a tag routes both.
- (b) Free-text tags, with routing set per company in code. Gets wrong: every new name needs code, and the same situation routes differently across companies.
- (c) Two tags (issuance-funded, asset-holding) and SIC for the rest. Gets wrong: MSTR is excluded by SIC before the tag applies unless precedence is defined, and SPAC-era facts (INFQ 2025) pass as an operating company.

**1.8 Signal record encoding and timeframe rows**
- (a) *Recommended.*
  - A migration adds `value_text TEXT` to `signal`. Enums and states go there with `value` NULL; numbers stay in `value`.
  - A missing signal is a row with both empty and `method` = "missing: <reason>" (D10, never zero).
  - One row per timeframe, as in the table in S1.5. ST "info" rows carry weight 0 in the profile.
  - `evidence_grade` = the weakest input that decided the value: A for filings and verified quotes; B for call transcripts, third-party share or trade data (DS13, DS16) and owner entries without a filing source.
  - `source_ref` = the accession of the newest filing used, with "+N" when more; the full input list is in `method`.

  Extends the D13 record. Why: readable enums without code tables, and no mixed types in one column.
- (b) Integer codes in `value`, with a code table in the M04 doc. Gets wrong: a code change silently changes the meaning of stored history, and rows are unreadable in SQL.
- (c) Text in the NUMERIC column (SQLite accepts it). Gets wrong: `max()` and sorting put 'CYCLICAL_TROUGH' above every number (tested), so mixed queries return text.
- (d) MY rows only; PT and ST read MY. Gets wrong: there is no row to hold a PT-specific parameter once M01 profiles differ (D12).

**1.9 Guidance record (approved Q2 row)**
- (a) *Recommended.*
  - **Miss:** the actual is below the low end of the latest range given before the period ended, or below a point guide. The comparison uses the guide's own basis: GAAP from first-filed facts, non-GAAP from the company's stated reconciliation.
  - **Repeated:** 2 misses in the last 4 guided quarters (starting value, unsourced). Downward revisions are counted separately.
  - **Removed:** a metric family guided in the release at the same fiscal position a year earlier is absent now, with no stated reason, for a period not yet ended. Ended periods are "expired".
  - **Ownership:** shared `guidance/` functions; M11 owns R19 scoring; M04's Q2 row reads `guidance_hit_rate`.
  - Outcomes: MU Q3 FY2023 3 of 3 hits; INTC FY2022 revenue a hit after at least one downward revision; INTC's April 2023 release `removed`; its January 2023 release not flagged.

  Why: near-term, verifiable targets (R19), without seasonal false removals.
- (b) Miss against the midpoint; "removed" = absent from the previous release. Gets wrong: it flags Intel's January 2023 release (FY2022 had expired and January releases carry no full-year guide), and it counts in-range results below the midpoint as misses.
- (c) Score against the first guide for the period. Gets wrong: Intel FY2022 reads as a 17.0% miss although Intel cut the guide to $63–64B in October.
- (d) Defer to M11. Gets wrong: the approved Q2 row stays "missing" for every company until M11 is built.

Changes to approved decisions in this round, for the consolidated D-M04-1 change table:
- 1.5a changes A2's default (Greenwald → depreciation);
- 1.8a extends the D13 record with `value_text`;
- 1.6a defines R2's "ambiguous stage" rule.

### New sources added in this section
- **S-new-r1-1** SEC data APIs checked 2026-10-12 (additions to S-new-1):
  - companyfacts (`https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`) for MU, INTC, MSFT, AMZN, GOOG, META, NVDA, AAPL, TSLA, BA, MSTR, MRVL, GFS, INFQ, SPCX and GE. Tags read: revenue, cost, gross profit, operating income, cash-flow totals, capex tags, `Depreciation`, `DepreciationDepletionAndAmortization`, `DepreciationAndAmortization`, PP&E net, gross and finance-lease-inclusive tags, `InventoryNet`, `InventoryWriteDown`, `RevenueRemainingPerformanceObligation`, non-operating, crypto and valuation-allowance tags, `UnbilledContractsReceivable`, weighted-average shares;
  - companyconcept WDC revenue — https://data.sec.gov/api/xbrl/companyconcept/CIK0000106040/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json ;
  - submissions (`https://data.sec.gov/submissions/CIK##########.json`: `sic`, `fiscalYearEnd`, `category`, 8-K items) for the watchlist, AMD, QCOM, TXN, AVGO, WDC, STX, FSLR, ENPH, ON and Invitae (CIK0001501134).
- **S-new-r1-2** SEC, Form 8-K, General Instructions and item list — https://www.sec.gov/files/form8-k.pdf
- **S-new-r1-3** SEC, Form 10-K, General Instruction A(2) (60/75/90 days) and the cover-page instruction on non-affiliate market value — https://www.sec.gov/files/form10-k.pdf
- **S-new-r1-4** Exchange Act Rule 12b-25, 17 CFR 240.12b-25 (Form NT; 15 and 5 calendar-day extensions) — https://www.law.cornell.edu/cfr/text/17/240.12b-25
- **S-new-r1-5** SEC, Form 20-F, General Instruction A(b) (four months) — https://www.sec.gov/files/form20-f.pdf
- **S-new-r1-6** IFRS Foundation (republished May 2025), "Going Concern—A focus on disclosure", educational material (IAS 1.25 → IAS 8.6K; IFRS 18 effective for periods from 2027-01-01) — https://www.ifrs.org/content/dam/ifrs/supporting-implementation/educational-materials/going-concern-2025.pdf
- **S-new-r1-7** SQLite, "Datatypes In SQLite" (NUMERIC affinity; sort order of TEXT vs numbers) — https://www.sqlite.org/datatype3.html
- **S-new-r1-8** Intel FY2024 10-K, Note 1 "Basis of Presentation", useful life of production machinery from 5 to 8 years (company rendering of the XBRL note; supports S-new-61) — https://www.intc.com/filings-reports/all-sec-filings/xbrl_doc_only/3810
- **S-new-r1-9** Intel earnings releases (8-K Ex. 99.1):
  - Q4 2021 (2022-01-26) — https://www.sec.gov/Archives/edgar/data/50863/000005086322000006/q421_earningsrelease.htm
  - Q1 2022 (2022-04-28) — https://www.sec.gov/Archives/edgar/data/50863/000005086322000019/q122_earningsrelease.htm
  - Q3 2022 (2022-10-27) — https://www.sec.gov/Archives/edgar/data/50863/000005086322000037/q322_earningsrelease.htm
  - Q4 2022 (2023-01-26) — https://www.sec.gov/Archives/edgar/data/50863/000005086323000005/q422_earningsrelease.htm
  - Q1 2023 (2023-04-27) — https://www.sec.gov/Archives/edgar/data/50863/000005086323000027/q123_earningsrelease.htm

Links re-found for existing IDs (no new ID):
- S13: Wikipedia "Owner earnings" — https://en.wikipedia.org/wiki/Owner_earnings (re-read 2026-10-12; the Old School Value pages returned 404).
- S88: FRM Topic 1, paragraph 1330.1, read 2026-10-12 for the 10-Q deadlines.

---

## Round 2 — Earnings quality

### What the research says
**Verdict for large caps:**
- Accruals, the Beneish M-score and the Dechow misstatement score have lost most of their power to predict returns. They remain screens for low-persistence earnings and misstatement risk, with many false alarms.
- Signals that hold up:
  - event and disclosure flags: 8-K 4.02, the 10-K error-correction checkbox, and estimate changes measured against profit;
  - cash conversion;
  - receivables, deferred-revenue and contract-asset trends against the company's own history.

1. **Accruals.**
   - The cash part of earnings persists more than the accrual part, and high-accrual firms earned lower returns (S-new-6).
   - Harder-to-verify accruals persist even less (S-new-7, Richardson et al.).
   - Much of the effect is growth in net operating assets (S-new-7, Fairfield et al.; summaries only). That matters for young growth firms (R2).
   - **Decay:**
     - Accrual hedge returns are "no longer reliably positive" in the US (S-new-8).
     - Across 97 predictors, returns were 26% lower out of sample and 58% lower after publication (S-new-9).
     - With NYSE breakpoints and value weights, 65% of 452 anomalies fail t = 1.96 (S-new-10).
     - Cash-based operating profitability subsumes accruals (S-new-12).
     - Fama & French (1963–2005) found accrual returns in all size groups, with weaker regression evidence (S-new-11).
   - **Measurement:** use the cash-flow statement (net income − CFO), not balance-sheet changes, which acquisitions and FX distort (S-new-13).
2. **Beneish M-score.**
   - M = −4.84 + 0.920·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI − 0.172·SGAI + 4.679·ACCR − 0.327·LEVI. The teaching note defines ACCR from cash flow; the 1999 original may differ (S-new-14; original S105).
   - Investigate above about −1.78. Depending on the cut-off, it catches 38–76% of manipulators and wrongly flags 3.5–17.5% of clean firms (S-new-14).
   - It predicts returns out of sample within every size, book-to-market, momentum, accrual and short-interest decile (S-new-14, Beneish, Lee & Nichols).
   - Across seven fraud models, even the best trade more than 100 false positives per true one. Only the M-score, and the misstatement score at high cut-offs, gave investors a net benefit (S-new-15).
   - SGI mechanically pushes fast growers toward "manipulator". Setting SGI to 1 removes that push: NVIDIA FY2025 reads −0.96 with SGI and −1.98 without it (worked example).
   - GMI is a ratio of gross margins, so it loses meaning when either year's gross margin is zero or negative: Micron FY2023 (gross margin −9.1%) gets GMI −4.96, which pulls M down to −7.01 (worked example).
3. **Dechow et al. misstatement score** (S-new-16, primary read).
   - Built from SEC enforcement releases (AAERs) 1982–2005 covering 676 misstating firms.
   - Model 1: −7.893 + 0.790·rsst_acc + 2.518·ch_rec + 1.191·ch_inv + 1.979·soft_assets + 0.171·ch_cs − 0.932·ch_roa + 1.029·issue, logistic. Score = probability ÷ 0.0037.
   - Score > 1.00 catches 68.6% of misstaters and wrongly flags 36.3% of clean firm-years. Score > 2.45 catches 18.8% and wrongly flags 5%.
   - Out of sample (Model 3, 1999–2002): 73.8% caught, 38.3% false flags.
   - Marginal effects are largest for soft assets (0.595) and issuance (0.559), against 0.099 for ch_rec.
   - Large firms are over-represented among misstaters, partly because of scrutiny. 82.5% of sample firms issue in a given year, so for large caps `issue` = 1 discriminates little (inference). Apple FY2025 scores 1.30, inside the > 1.00 band, mainly from soft assets (0.76) and a $4.5B debt issue (worked example).
4. **Restatements.**
   - **What triggers a 4.02:** Item 4.02(a) applies when the company concludes prior statements "should no longer be relied upon"; 4.02(b) when the auditor gives that notice. The 8-K is due within 4 business days (S-new-r2-1, Form 8-K General Instruction B.1 and Item 4.02).
   - **Gap:** General Instruction B.3 waives the 8-K when substantially the same information was already reported, for example in a 10-K or 10-Q (S-new-r2-1).
   - **Little r** (immaterial corrections, no 4.02):
     - Little r rose from about 35% of restatements in 2005 to nearly 76% in 2020, and SEC staff see some materiality analyses biased toward "immaterial" (S-new-17, Munter).
     - Little r corrections predict later errors, material weaknesses and comment letters, with modestly negative returns (S-new-18).
     - Errors must be separated from irregularities (S-new-18, Hennes et al.).
     - Watchlist case: Infleqtion's Q2 2026 10-Q (filed 2026-08-18) corrects "immaterial errors" in Q1 2026: revenue $9,461K → $9,907K (+4.7%), net loss $(30,263)K → $(29,719)K, from revenue recognition and the expected-loss provision (S-new-r2-7). There was no 4.02 8-K; the same day it amended its Q2 earnings 8-K (Item 2.02).
   - **Big R base rates:**
     - About 3% of companies a year (2005–2024).
     - 29% followed an auditor change in the prior year, against an 11% base rate (S-new-17, PCAOB).
   - **Price reaction:** the 4.02 abnormal return vs SPY is about −1.1% at 1 day and −2.0% at 20 days (S-new-17, vendor).
   - **The cover checkbox** has been in force since 2023 on Forms 10-K, 20-F and 40-F and is tagged `dei:DocumentFinStmtErrorCorrectionFlag` (S-new-19). The staff interpretations were read on 2026-10-12 (S-new-r2-2):
     - C&DI 104.20 (2025-04-11): the box is marked whenever previously issued statements were revised for an error, "regardless of whether those restatements are required or not", so little r counts. An immaterial prior-period error corrected in the current year (an out-of-period adjustment) does not mark it.
     - C&DI 104.24: a restatement first reported elsewhere (for example in an 8-K or a registration statement) is marked on the next annual report that presents the restated period.
     - C&DI 104.25: a restatement of interim periods only does not mark the box. C&DI 104.22: the box may stay unmarked the following year if there is no new restatement. So Infleqtion's Q1 2026 correction will not mark its FY2026 10-K.
     - The C&DIs say nothing about changes in accounting principle, reclassifications or discontinued-operations recasts. These are not error corrections, so the box stays unmarked (inference). A false flag therefore rules out an error correction but does not explain a change.
     - C&DIs 104.18 and 104.19 (transition timing) were withdrawn on 2026-09-25.
     - The flag is not in companyfacts, which holds numeric facts only. Reading it costs one instance fetch per annual report from 2023: 54 annual reports for the 14 XBRL filers on the watchlist (S-new-r2-8). It costs nothing if the stored 10-K HTML keeps its inline XBRL tags (check at build).
5. **Most first-vs-latest deltas are not errors.**
   - Common causes: ASC 606 retrospective adoption, discontinued-operations recasts and 8-K recasts (worked example, S-new-1).
   - **Revenue test:** a reclassification leaves net income unchanged while revenue moves. It must be applied step by step between consecutive versions.
   - **Cash-flow test:** a recast that moves cash between operating, investing and financing leaves CFO + CFI + CFF unchanged while CFO moves. Net income says nothing about this, so the revenue test does not apply to CFO.
   - **Cash-flow classification is also a manipulation channel.** Firms with financial distress, ratings near the investment-grade line, analyst cash-flow forecasts or a strong return–CFO link inflate CFO by moving items between categories, sometimes beyond GAAP, and by timing payments and collections (S-new-r2-3). A shift that raises CFO is therefore a concern of its own, even when the total is unchanged.
   - **Walk run on the watchlist** (companyfacts fetched 2026-10-12; 13 us-gaap filers, revenue, net income and CFO, 10-K/10-Q versions; GFS reports in `ifrs-full` and was not walked; S-new-r2-8):
     - 150 steps exceed the recommended tolerance (2.3a) over the full XBRL history. Most sit in 2013 and 2017–2018 filings.
     - 48 get a mechanical label: 21 CFO-increasing and 8 CFO-decreasing classification shifts, 9 revenue reclasses, 9 de-SPAC predecessor steps and 1 change of rounding unit.
     - 102 need text. They sit in at most 35 later filings, and almost none of those filings are stored (DS7).
     - Filings from 2022 on carry 12 steps outside Infleqtion's de-SPAC switch (Intel 6, Tesla 4, Infleqtion 2), about 2–3 a year.
     - 20 of the 21 CFO-increasing shifts are in 2016–2018 filings (Amazon 10, Apple 4, Alphabet 3, Meta 2, Boeing 1); Intel's is in 2023. That fits the cash-flow standards adopted then (ASU 2016-09, 2016-15, 2016-18; inference, causes not read).
   - **The cause is often in another filing.**
     - GE's 8-K of 2018-04-13 (Item 8.01) quantifies both causes of the FY2017 revenue step. ASC 606 accounts for −$2,224M and other income moved out of revenue for −$1,625M, which together equal the XBRL step of −$3,849M exactly (S-new-r2-9).
     - Tesla's 2024 quarters changed in its 2025 10-Qs (Q1 2024 net income $1,129M → $1,390M). The cause, ASU 2023-08 adopted effective 2024-01-01, is stated in its FY2024 10-K, filed between the two versions (S-new-r2-5, S-new-r2-8).
6. **The GE pattern** (S03, primary S-new-20, ¶5–8, ¶13–14).
   - Cost-estimate reductions gave GE Power Services more than $1.4B of revenue and earnings in 2016, and more than $1.1B in the first three quarters of 2017. That was 29% and 45% of GE Power *segment* profit.
   - Measured on company figures, the same amounts are 15.5% of GE's 2016 pretax income from continuing operations ($9,030M) and 28.9% of its nine-month 2017 pretax income ($3,812M). Full-year 2017 was a pretax loss of $8,791M (S-new-r2-8). Which denominator applies is question 2.5.
   - A $5B deferred balance within contract assets rose with them. GE's balance-sheet contract assets were $21,156M (2015), $25,162M (2016) and $28,861M (2017) (S-new-r2-6).
     - The 2017 10-K tags the 2016–17 values `UnbilledContractsReceivable`, which is in companyfacts.
     - The 2015 value appears only in the 2016 10-K, under a tag that is not in companyfacts (probably an extension; not checked). It needs one instance read (D-M02-32).
   - Factoring added more than $1.4B (2016) and more than $500M (first three quarters of 2017) to Industrial Cash Flow, about 12% and 33% of the total. It pulled forward $878M from 2018, $585M from 2019, $407M from 2020 and $400M from later years.
   - Penalty $200M; no restatement.
   - Estimate changes on average make earnings more useful, with limited support for widespread manipulation (S-new-21, Albrecht et al.).
   - About 500 material estimate changes occur a year (2000–2018). Income-increasing changes outnumber decreasing ones almost every year. Depreciation and amortization come first, percentage-of-completion second (S-new-21, Audit Analytics).
   - Watchlist cases (S-new-22):
     - Alphabet 2023 extended server lives to 6 years: depreciation −$3.9B (confirmed in Item 7 on 2026-10-12); net income +$3.0B and the prior 4-year life are still to re-confirm in Note 1.
     - Amazon 2025 shortened a subset from 6 to 5 years: D&A +$1.4B, net income −$1.0B.
   - No standard numeric tag exists for estimate changes (frames for `ChangeInAccountingEstimateFinancialEffect` CY2024 → 404, S-new-24), so they need text extraction.
7. **Revenue recognition.**
   - Improper revenue recognition was the most common technique, in 61% of 347 SEC fraud cases from 1998–2007 (S-new-23, COSO via BDO).
   - Revenue-based models detect manipulation better than accrual models (S-new-23, Stubben).
   - The ASC 606 catch-up footprint is `ContractWithCustomerPerformanceObligationSatisfiedInPreviousPeriod`, tagged by 126 filers in CY2024 (Lockheed $1.2B, Northrop $396M, RTX −$144M) (S-new-24).
   - Contract assets: 579 filers, none found on the watchlist. Before ASC 606, filers used other tags; GE used `UnbilledContractsReceivable` (item 6).
   - Contract liabilities: 2,034 filers, including BA, MSFT, AAPL, AMZN, NVDA, MU and MSTR.
   - DSO is already built (`financing/credit.dso`, D-M02-47).
8. **Cash conversion** is the most robust large-cap measure (S-new-6, S-new-12). But CFO can be engineered (GE factoring; classification shifting, S-new-r2-3) and distorted on a consolidated basis: GE's 2016 CFO was −$244M against net income of $8.83B, cause not decomposed (S-new-1).
   - **Non-cash, non-operating items move net income without moving cash** (S-new-r2-8):
     - Tesla 2023: the valuation-allowance change in the tax-rate reconciliation was −$5,962M, 39.8% of net income of $14,997M.
     - Alphabet 2025: gains on debt and equity securities were $24,620M pre-tax. Non-operating income was 18.8% of pretax income.
     - Strategy: bitcoin has been carried at fair value since 2025-01-01 (ASU 2023-08, adopted prospectively, with a cumulative effect of +$12,746M to retained earnings; S-new-r2-4). Its 2025 fair-value loss of $5,403M sits inside operating income, against net income of −$3,848M and CFO of −$67M.
     - Intel 2024: the valuation allowance rose by $10.9B and net income was −$18,756M (not meaningful in any case).
9. **Staging.** For young growth firms, accrual size, SGI and Δreceivables partly measure growth (S-new-7), so use own-history, growth-adjusted comparisons. Event flags are stage-neutral. The M-score's growth handling (S2.3) now keys on SGI itself, so it does not wait for the stage decision (5.1). The CFO/NI warning still uses stage.

### Worked example — GE restatement walk under the corrected rule (S-new-1, S-new-r2-8, S-new-r2-9; companyconcept JSON fetched 2026-10-12; $M)

| # | Concept, period: step (filed → filed) | Δ | Mechanical test | Label without text (pre-corpus) | Label with GE's 2018-04-13 8-K text |
|---|---|---|---|---|---|
| 1 | Revenues FY2016: 123,693 (2018-02-23) → 119,469 (2019-02-26) | −4,224 (−3.4%) | Net income moved (8,831 → 7,500), so not `reclass` | `unexplained` | `accounting_change` −220 (ASC 606) + `reclass` −4,005 (other income moved out of revenue); residual +1 is below tolerance |
| 2 | Revenues FY2017: 122,092 (2018-02-23) → 118,243 (2019-02-26) | −3,849 (−3.2%) | Net income moved | `unexplained` | `accounting_change` −2,224 + `reclass` −1,625; residual 0 |
| 3 | Revenues FY2017: 118,243 → 99,279 (2020-02-24) | −18,964 (−16.0%) | Net income unchanged at −8,484 | `reclass` ("recast, not an error"; cause in the 2020 10-K, likely discontinued operations, not read) | same |
| 4 | Net income FY2016: 8,831 → 7,500 (2019-02-26) | −1,331 (−15.1%) | — | `unexplained` | ASC 606 −1,182 (stated for earnings from continuing operations) + residual −149 → review. The 8-K's other changes, such as LIFO to FIFO, are not quantified in what was read |
| 5 | Net income FY2017: −5,786 → −8,484 (2019-02-26) | −2,698 | — | `unexplained` | ASC 606 −2,668 (−1,558 before, and −1,110 from, U.S. tax reform) + residual −30. The basis (continuing operations vs net income) is to be checked at build |
| 6 | CFO FY2016: −244 → 1,160 (2019-02-26) | +1,404 | CFI −67, CFF −1,333; CFO + CFI + CFF −40,173 → −40,169 (+4) | `cf_shift_up` 1,400 + residual +4 | No cause found (the 8-K applies ASU 2016-15 to 2017 only), so the shift remains a concern |
| 7 | CFO FY2017: 10,426 → 6,032 (2019-02-26) | −4,394 (−42.1%) | CFI +4,242, CFF 0; total −6,398 → −6,550 (−152) | `cf_shift_down` 4,242 + residual −152 | 553 of the shift quantified (ASU 2016-15: securitization receipts moved from operating to investing). Restricted cash now counted as cash (ASU 2016-18) is a likely cause of the residual, but the amount does not match → review |
| 8 | CFO FY2017: 6,032 → 6,554 (2020-02-24) | +522 (+8.7%) | CFI −1,185, CFF +662; total −6,550 → −6,551 (−1) | `cf_shift_up` 523 | not read |
| 9 | CFO FY2015: 19,891 (10-K, 2016-02-26), same value in an 8-K filed 2016-06-03 | 0 | 8-K version excluded | no step | Shows that 8-K recasts carry XBRL |

- **What the correction changes.** Under the draft rule, step 8 would have read `reclass` because net income was unchanged. Any step in a 10-K with the error flag false would have read `accounting_change`, which hides residuals like those in steps 4–7.
- **What the text adds.** GE's 8-K labels steps 1–2 exactly and shrinks steps 4–5 to small residuals. It sits *between* the two versions, so the evidence search must cover every document filed in that window, not only the later 10-K (S2.6).

**Tolerance options on these steps** (question 2.3; residual tested after labels; $M):

| Residual or step | (a) > 0.5% and > $0.1M | (b) > min(1%, 5% of pretax income) | (c) > 2% |
|---|---|---|---|
| Steps 1–2 residuals (+1, 0) | not queued | not queued | not queued |
| Step 4 residual −149 (base 8,831) | review (tolerance 44) | review (88) | not queued (177) |
| Step 5 residual −30 (base −5,786) | review (28.9) | not queued (57.9) | not queued (115.7) |
| Step 6 residual +4 (base −244) | review (1.2) | review (2.4) | not queued (4.9) |
| Step 7 residual −152 (base 10,426) | review (52) | review (104) | not queued (209) |
| Step 8 shift +523 | `cf_shift_up` flag | flag | flag |
| Infleqtion Q1 2026 revenue +$446K (4.7%) | step created (tolerance $100K) | created ($95K) | created ($189K) |
| Infleqtion Q1 2026 net loss −$544K (1.8%) | created ($151K) | created ($303K) | missed ($605K) |
| Same two Infleqtion steps under the draft's $1M floor | both missed | — | — |

Watchlist totals over the full history: 150 steps under (a), 141 under the draft's $1M floor, 142 under (b) and 121 under (c). From 2022 on: 21, 19, 20 and 16.

**Scores on real filings** (question 2.1). Computed 2026-10-12 from companyfacts, using the first 10-K value filed on or before the as-of date (S-new-r2-8). This is a scratch mapping, so treat the scores as approximations and recompute them from `fact` at build.

| Company, fiscal year | M | M with SGI = 1 | Misstatement score F | What drives it |
|---|---|---|---|---|
| NVIDIA FY2025 | −0.96 | −1.98 | 3.11 (1.12 with `issue` = 0) | SGI 2.14; rsst_acc 0.40; ch_cs 1.15 (growth) |
| NVIDIA FY2026 | −1.17 | −1.75 | not computed: `MarketableSecuritiesCurrent` is absent in the FY2026 10-K (tag switch) | AQI 1.52: assets outside current assets and PP&E rose from 22.6% to 34.2% of total assets, including $22.3B of non-marketable equity securities |
| Marvell FY2026 | −1.60 | −1.98 | not computed: no equity- or debt-proceeds tag for the year, so `issue` is unknown | SGI 1.42; DSRI 1.50 |
| Apple FY2025 | −2.29 | −2.35 | 1.30 (0.47) | soft assets 0.76; `issue` from $4.48B of debt |
| Microsoft FY2025 | −2.54 (SG&A = S&M + G&A) | −2.67 | 1.15 | — |
| Alphabet FY2025 | −2.64 (S&M + G&A) | −2.78 | 0.97 | — |
| Meta FY2025 | −3.02 (S&M + G&A) | −3.22 | 0.80 | — |
| Micron FY2025 | −2.75 | −3.18 | 0.61 | — |
| Micron FY2023 | −7.01 → not meaningful | — | 0.48 | GMI −4.96 from a negative gross margin |
| Boeing FY2024 | incomplete (no SG&A tag); GMI −3.32 | — | 1.63 | gross margin negative; $18.2B of equity raised |
| Intel FY2024 | −3.11 | −3.09 | incomplete: no `Liabilities` total (derivable as 196,485 − 105,032 = 91,453) | — |
| Amazon FY2025 | incomplete (neither an SG&A tag nor S&M + G&A tags) | — | incomplete (no `Liabilities` total) | — |
| Strategy FY2025 | −2.45 (S&M + G&A) | −2.48 | 3.28 | bitcoin: rsst_acc 0.70 and soft assets 0.96 from fair-valued holdings → `not_meaningful` by model tag |
| GE FY2016 / FY2017 | incomplete | — | incomplete | unclassified balance sheet: no current assets or current liabilities, so AQI and LEVI fail; ACCR 0.026 / −0.043 |

Tag gaps that a naive mapping would turn into silent zeros include Tesla FY2023. It reports `LongTermDebt` instead of `LongTermDebtNoncurrent`, and its equity proceeds sit under `ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlans` ($700M). These belong in the S1.3 probe and are not scored here.

**What each 2.1 option shows on this table:**
- (a) gives one review item: NVIDIA FY2026, where M with SGI = 1 is −1.75. NVIDIA FY2025 and Marvell FY2026 get a "growth-driven" note.
- (b) flags NVIDIA (both years), Marvell, Apple, Microsoft, Boeing and Strategy.
- (c) shows none of these.

**GE estimate share** (question 2.5; amounts are lower bounds from the SEC order, S-new-20; denominators from S-new-r2-8):

| Basis | 2016 | First nine months of 2017 | FY2017 |
|---|---|---|---|
| Company pretax income from continuing operations (GE tags no operating income) | 1,400 ÷ 9,030 = 15.5% → watch | 1,100 ÷ 3,812 = 28.9% → elevated | pretax −8,791 → `not_meaningful` |
| GE Power segment profit (order's figures; dimensional, DS12) | 29% → elevated | 45% → elevated | — |

Whether GE's own filings quantified these amounts is not checked. The fixture feeds the order's amounts as inputs.

**GE contract assets vs revenue** (S2.2; S-new-r2-6, S-new-1; revenue as first reported):

| Year | Contract assets | Growth | Revenue | Growth | Gap |
|---|---|---|---|---|---|
| 2015 | 21,156 | — | 117,386 | — | — |
| 2016 | 25,162 | +18.9% | 123,693 | +5.4% | 13.6 pp |
| 2017 | 28,861 | +14.7% | 122,092 | −1.3% | 16.0 pp |

The gap exceeds 10 pp in two consecutive annual readings, so `contract_asset_gap` fires. Quarterly readings would need GE's 2016 10-Q instances (3 reads), because those values sit under the same non-companyfacts tag.

**Alphabet cash conversion** (S-new-1, S-new-22, S-new-r2-8):

| Year | Net income | CFO | CFO / NI | Item | Share of NI |
|---|---|---|---|---|---|
| 2022 | 59,972 | 91,495 | 1.53 | — | — |
| 2023 | 73,795 | 101,746 | 1.38 | Server lives to 6 years: depreciation −3.9B (confirmed); NI +3.0B (re-confirm) | ≈ 4.1% → note |
| 2024 | 100,118 | 125,299 | 1.25 | — | — |
| 2025 | 132,170 | 164,713 | 1.25 | Gains on debt and equity securities 24,620 pre-tax (≈ 19,450 after tax at 21%) | ≈ 14.7% → note; operating basis CFO / NI 1.46 |

**Tesla cash conversion and a valuation-allowance release** (S-new-r2-8):

| Year | Net income | CFO | CFO / NI | Non-operating item | Operating basis |
|---|---|---|---|---|---|
| 2022 | 12,556 | 14,724 | 1.17 | — | — |
| 2023 | 14,997 | 13,256 | 0.88 | Valuation-allowance change −5,962 (39.8% of NI) | NI 9,035; CFO / NI 1.47; accruals (NI − CFO) flip from +1,741 to −4,221 |
| 2024 | 7,091 | 14,923 | 2.10 | — | — |

The 3-year CFO/NI (2022–2024) is 1.24.

**Strategy 2025** (S-new-r2-4, S-new-r2-8): fair-value loss 5,403 inside an operating loss of 5,444; net income −3,848; CFO −67; revenue 477. Even after removing the fair-value loss, both CFO and net income are tiny next to the holdings, so CFO/NI, accruals, the M-score and `misstate_f` are `not_meaningful` (model tag).

**Lockheed Martin** catch-up revenue tag (S-new-1): $2.2B (2019), $2.0B, $2.2B, $2.0B, $1.6B, $1.2B (2024). These are revenue, not profit, so they are shown against own history only.

**Engine row (illustrative):** `{ticker:"GE", module_id:"M04", signal:"restate_delta", value:-0.160, method:"Revenues FY2017, step 10-K 2019-02-26 → 10-K 2020-02-24; cause=reclass (NI unchanged)", evidence_grade:"A", …}`

### All cases
1. 8-K 4.02(a), company-driven, or 4.02(b), auditor-driven and rarer.
2. Big R disclosed only in a 10-K or 10-Q (B.3, no 8-K).
3. Little r revision: dei flag true from 2023; text "revision", "immaterial error". Interim-only corrections do not tick the box (C&DI 104.25), so text is the only route: Infleqtion Q1 2026.
4. Out-of-period correction booked in the current period: no prior revision, box not ticked (C&DI 104.20).
5. Retrospective accounting change (ASC 606) → not an error.
6. Discontinued-operations or spin recast: GE FY2017 revenue −16% with net income unchanged; WDC FY2023 revenue $12.3B → $6.3B.
7. Segment recast.
8. Stock split (MSTR 10×).
9. Tag switch with an unchanged value.
10. Rounding noise, including a change of reporting unit: Tesla FY2017 CFO −$60.654M → −$61.0M; Marvell $832.279M → $832.3M → `rounding`.
11. Value from an 8-K or DEF 14A.
12. Mixed step: quantified causes plus a residual (GE FY2017 revenue: ASC 606 −2,224 and other income −1,625; GE FY2016 net income: ASC 606 −1,182, residual −149).
13. Estimate change, income-increasing or income-decreasing; company-level only, no segment.
14. Recurring estimate changes in the same direction.
15. Catch-up revenue tagged or untagged; pre-2018 periods have no ASC 606 tags.
16. Contract assets outgrowing revenue (GE, under the pre-ASC 606 tag `UnbilledContractsReceivable` and an earlier non-companyfacts tag); deferred revenue falling while revenue grows.
17. Net income near zero or negative (CFO/NI not meaningful); finance arm or discontinued operations inside CFO.
18. Factoring or supplier finance pulling cash forward.
19. Growth company: SGI and accruals inflated (NVIDIA FY2025: M −0.96, −1.98 with SGI = 1).
20. Missing input:
    - no single SG&A line: Microsoft, Alphabet, Meta and Strategy → S&M + G&A, method-tagged; Amazon and Boeing → incomplete;
    - D&A instead of depreciation alone;
    - no total liabilities (Intel, Amazon) → derived as liabilities-and-equity minus equity including NCI, method-tagged;
    - a tag switch inside the inputs (NVIDIA FY2026 short-term investments; Tesla debt and equity proceeds) → probe, never zero.
21. Auditor change (4.01) within 12 months of an error. When the change follows a de-SPAC (Infleqtion: 5.06 on 2026-02-17, 4.01 on 2026-03-26, little r filed 2026-08-18), it still escalates, and the de-SPAC is shown as context.
22. Period before 2004-08-23 → no Item 4.02 history.
23. Cash moved between CFO, CFI and CFF with the total unchanged: GE FY2016 +1,404 and FY2017 +523 (`cf_shift_up`); GE FY2017 −4,242 (`cf_shift_down`); 21 CFO-increasing shifts in the watchlist history.
24. Shift plus residual: GE FY2017 residual −152 after ASU 2016-18 brought restricted cash into the totals.
25. Near-zero base: GE FY2016 CFO −244, where a percentage tolerance collapses to the dollar floor.
26. Cause stated in a filing between the two versions: GE's 8-K Item 8.01 recast; Tesla's FY2024 10-K for 2024 quarters changed in 2025 10-Qs.
27. Cause found but not quantified → stays `unexplained`, with the passage attached as the suggested cause.
28. De-SPAC predecessor switch: Infleqtion's 2025 periods replaced after the 8-K Item 5.06 of 2026-02-17 → `predecessor`.
29. Fair-value swings in net income: Strategy's bitcoin (ASU 2023-08 from 2025-01-01, loss inside operating income) → `not_meaningful` by model tag; Alphabet's 2025 securities gains (14.7% of NI) → note.
30. Valuation-allowance release or charge: Tesla 2023 release (39.8% of NI) → operating basis; Intel 2024 charge with negative NI → `not_meaningful`.
31. Negative gross margin in either year (Micron FY2023, Boeing FY2024) → GMI and M not meaningful.
32. Unclassified balance sheet (GE) → M and F incomplete.
33. Foreign filer (GFS: `ifrs-full`, 20-F and 6-K with XBRL): the walk reads 20-F/6-K versions and IFRS tags; 6-Ks carry no item codes, so the 4.02 detector is silent; the 20-F carries the same checkbox (S-new-19). The form list follows S1.1 (Round 1).

**Complete / known omissions.** The walk covers revenue, net income and CFO only. These cases were not seen on real data and are listed from the rules: 4.02(b), a Big R via B.3, and a 10-K/A error correction on the watchlist. Not checked: SPCX (no stored history checked) and ETV (fund; excluded).

### Suggestions
- **S2.1 `eq_cash`.**
  - TTM and 3-year CFO/NI, and cash-flow accruals ÷ average assets, against own 5-year range plus peer robust z.
  - `not_meaningful` when |NI| < 1% of revenue (D-SRCH-15 pattern).
  - **Operating basis.** Net income less identified non-cash, non-operating items:
    - gains or losses on debt and equity securities, and fair-value changes on crypto assets, taxed at 21% (labelled approximation);
    - the valuation-allowance change from the tax-rate reconciliation, as reported.
  - When those items exceed 25% of |NI| (starting value, unsourced), the ratios use the operating basis and name the items. Tesla 2023 switches; Alphabet 2025 shows a note.
  - Model tag "bitcoin treasury" (and other asset-holding tags from 3.4) → `not_meaningful`, reason shown.
  - Warning when 3-year CFO/NI < 0.8 (starting value, unsourced) for a company not in an introduction or growth stage. Stage comes from 5.1, which the pack moves ahead of this round.
- **S2.2 Reuse `credit.dso()`** and add:
  - `contract_asset_gap`: contract assets growing more than 10 pp faster than revenue in 2 consecutive readings (the GE pattern);
  - `deferred_rev_gap`: deferred revenue falling year over year while revenue grows.

  Readings compare the same quarter a year earlier (D-M02-47), or fiscal years where quarters are missing. Pre-2018 aliases (`UnbilledContractsReceivable`; `DeferredRevenueCurrent`) are method-tagged; an extension tag needs an instance read (D-M02-32). Thresholds are starting values, unsourced.
- **S2.3 `mscore`.**
  - Annual, components shown, built from mapped concepts.
  - M and M with SGI = 1 are shown side by side, so growth handling does not depend on the stage decision.
  - "Investigate" only when M with SGI = 1 is above −1.78. When only M is above it, the note reads "growth-driven". −1.78 is shown beside the own-history and peer percentile.
  - "Incomplete" when a required input is missing.
  - "Not meaningful" when gross margin is ≤ 0 in either year (GMI) or a model tag applies.
  - The method names the ACCR variant and any substitution: S&M + G&A for SG&A, D&A for depreciation, derived total liabilities.
- **S2.4 `misstate_f`.** Dechow Model 1, built after the S1.3 concepts.
  - Labelled "approximation", because the coefficients were estimated on Compustat items.
  - Shows the score, its own-history percentile, and bands > 1.00 and > 2.45.
  - Required inputs missing → incomplete. Optional balance-sheet items that are absent (long-term investments, preferred stock) are named in the method. `issue` with no proceeds tag is "unknown", never 0.
- **S2.5 `restatement` event signal.**
  - Inputs:
    - 4.02 (tagged a or b) as a grade-A warning;
    - the dei flag;
    - FTS5 phrases in stored 10-K/10-Q ("as restated", "revision of previously issued", "immaterial error", "correction of immaterial errors", "out-of-period adjustment").
  - Little r → note.
  - A 4.01 in the prior 12 months escalates the signal; a preceding 5.06 is shown as context.
  - The dei flag is read as C&DIs 104.20–104.25 describe: it marks error corrections in annual periods only, and a false flag never counts as evidence of an accounting change.
- **S2.6 `restate_delta` from the S1.1 walk.** Periodic forms per S1.1's list. One row per (concept, period), with each step between consecutive versions labelled in this order:
  - below tolerance → shown as a minor change, no flag (question 2.3);
  - `rounding`: the later value is a round multiple of a larger unit and the step is under half that unit;
  - `split`: share or per-share concepts, checked against Tiingo `split_factor`;
  - `predecessor`: the period ended before an 8-K Item 5.06 date and the later version was filed after it (de-SPAC);
  - `reclass` (revenue only): net income unchanged within tolerance;
  - `cf_shift_up` / `cf_shift_down` (CFO only): CFO + CFI + CFF unchanged within tolerance. When the total moved by more than the tolerance but less than CFO did, the offsetting part is the shift and the change in the total is the residual (GE FY2017: shift −4,242, residual −152). `cf_shift_up` is a watch flag (S-new-r2-3); `cf_shift_down` is a note;
  - `error`: a 4.02 between the versions, the dei flag true, or an error passage ("restated", "revision", "immaterial error");
  - `accounting_change` / `reclass` from text: a passage in any document filed between the two versions (later periodic filing, 8-K Item 8.01, intervening 10-K) that names a standard or reclassification *and states an amount*. The amount is subtracted and the residual is tested again;
  - otherwise `unexplained` → review (D8). A cause passage without an amount is attached to the review item as the suggested cause.

  A step only partly explained keeps the residual as `unexplained`. "dei flag false" is not evidence of anything.
  - **Historical text.** A one-off fetch of the primary document of each later filing that still has an unlabelled step, at most 35 for the watchlist (one request each). If no cause is found, a second pass fetches the 8-Ks with Item 8.01 and the 10-Ks filed in the window; their number is counted in a dry run before fetching.
  - **First-run baseline.** Steps whose later filing is more than 24 months old (starting value, unsourced) are labelled and shown on the Financials tab as history, never queued (LESSONS: a first scan is a baseline). Newer `unexplained` steps and residuals are queued under S2.10.
  - On today's data the baseline is 135 steps, and 15 steps are newer:
    - Infleqtion 11: 9 `predecessor` and 2 little r;
    - Tesla 4, which the intervening FY2024 10-K labels `accounting_change`.

    At most 4 are queued, and only if that 10-K is not found.
- **S2.7 `estimate_share`.**
  - Code finds ASC 250 and catch-up passages by FTS5 ("change in estimate", "estimated useful life", "cumulative catch-up", "profit booking rate"). Gemini runs only on request, with verified quotes (D21, D28).
  - Denominator per question 2.5. Basis and period are matched to the disclosed amount: after-tax ÷ net income; pre-tax ÷ operating income; pre-tax ÷ pretax income from continuing operations where operating income is not tagged; year-to-date against year-to-date. A denominator ≤ 0, or below 1% of revenue → `not_meaningful`.
  - Bands: < 10% note, 10–25% watch, ≥ 25% elevated (starting values, unsourced). GE reads watch for 2016 and elevated for the first nine months of 2017 on company figures.
  - Three years of same-direction changes add a flag. Changes in both directions are shown.
- **S2.8 Information only** until D13 weights exist. No return claim is made for these ratios (the decay evidence above). Round 6 calibrates CvD only, so this round's thresholds stay starting values until a labelled red-flag case set exists. That set is a pack-level item.
- **S2.9 Regression fixtures and live checks.** GE is not on the watchlist, so it appears in fixtures only. Non-watchlist fixtures are companyconcept files per tag, not whole companyfacts.
  - **Part 3 live check.**
    - GE: companyconcept for NetIncomeLoss, Revenues, CFO, CFI, CFF and pretax income (6 requests), plus 3 documents: the 2018-04-13 8-K and the 2019-02-26 and 2020-02-24 10-Ks.
    - WDC: revenue and net income (2 requests).
    - Watchlist: historical documents (at most 35) and dei flags (about 54, or 0 if read from stored HTML).
    - About 100 requests in all: under 30 s of request time at the 5/s pacing. Downloading about 40 large documents dominates the run (a few minutes; estimate).
    - The script takes `refresh.lock` (D-M02-51).
  - **Part 6 live check.**
    - GE: `UnbilledContractsReceivable` (1 request) and the FY2016 10-K instance (1).
    - Lockheed: catch-up tag (1).
    - Prior 10-Ks if 2.4a (about 14).
  - **Fixture expectations:**
    - GE 2016–17 walk: rows 1–9 as in the table, with and without the 8-K text.
    - GE `contract_asset_gap` fires on 2016 and 2017 (13.6 and 16.0 pp).
    - GE `estimate_share` reads 15.5% watch (2016), 28.9% elevated (first nine months of 2017) and `not_meaningful` (FY2017).
    - GE M-score and `misstate_f` read "incomplete".
    - Alphabet 2023: estimate note (4.1%). Alphabet 2025: non-operating note (14.7%).
    - Tesla 2023: operating basis. Tesla's 2024 quarters: `accounting_change` from the FY2024 10-K.
    - Strategy 2025: `not_meaningful`.
    - Infleqtion: `predecessor` for 2025 periods; `error` (little r) for Q1 2026 from the stored 10-Q; dei flag stays false.
    - NVIDIA: FY2025 growth-driven note; FY2026 review.
    - Micron FY2023: M not meaningful.
- **S2.10 Review kinds from this round** (they join the pack-level M04 review table; D-M02-51 pattern: rank, cap per pass, flush in priority order):

| Kind | Queued when | Expected volume (watchlist) | Priority |
|---|---|---|---|
| `m04_restate` | An `unexplained` step or residual above tolerance, later filing within 24 months | First run: at most 4. Then about 2–3 steps a year reach the walk, most labelled mechanically (12 in filings from 2022 on, outside the de-SPAC switch) | 1, ranked by residual ÷ tolerance |
| `m04_estimate` | An estimate-change passage with share ≥ 10%, to confirm amount and sign | Unknown until the Part 6 scan. The base rate of about 500 material changes a year across all filers (S-new-21) suggests about 1–2 a year for 14 filers (inference) | 2, elevated before watch |
| `m04_mscore` | M with SGI = 1 above −1.78 (one per 10-K) | 1 now (NVIDIA FY2026) of 13 watchlist company-years scored | 3 |

  Shared cap: 5 items a week across these kinds (starting value, unsourced). `cf_shift_up`, the operating-basis switch, the growth-driven note and little r are flags or notes, not review items.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Accruals | Growth inflates them; the return edge has decayed; balance-sheet versions are distorted by M&A | Cash-flow-statement version; own history; no return claim; stage-aware |
| CFO / NI | Meaningless near zero NI; finance arms and discontinued operations (GE 2016 −$244M); factoring pulls cash forward | `not_meaningful`; 3-year sums; shown beside DSO and receivables-sale text |
| Non-operating swings | Fair-value gains, crypto remeasurement and valuation-allowance changes move NI without cash (Tesla 2023, Strategy 2025) | Operating basis above 25% of NI; model tag → `not_meaningful` |
| M-score | SGI penalizes growers; cut-off from 1980s–90s data; more than 100 false positives per true one; ACCR variants; GMI breaks on negative gross margins; unclassified balance sheets; no SG&A line | Components shown; M with SGI = 1 decides the review; screen only; method tag; "incomplete" or "not meaningful" with reason |
| Misstatement score | Compustat coefficients; `issue` ≈ always 1 for large caps; soft assets lift most large caps above 1.00 (Apple 1.30); name clash with Piotroski | "Approximation"; percentile; signal named `misstate_f`; `issue` unknown, never 0 |
| 4.02 events | B.3 cases have no 8-K; no history before 2004-08-23; foreign filers' 6-Ks carry no items | dei flag plus text; "missing" before Aug 2004 |
| Error-correction checkbox | Annual reports from 2023 only; out-of-period and interim-only corrections, and the following year, do not tick it; a false flag does not mean "accounting change" | Combine with text; never used as positive evidence |
| Cash-flow classification | Recasts move cash between sections; firms shift items to inflate CFO (S-new-r2-3) | Sum test; `cf_shift_up` watch flag; residual to review |
| Text evidence | The cause sits in a filing not stored, or in an 8-K or 10-K between the versions; a cause without an amount explains nothing | One-off historical fetch; 8-K 8.01 second pass; amount required for a label |
| De-SPAC history | The shell's values are replaced by the accounting acquirer's (Infleqtion) | `predecessor` label from 8-K Item 5.06 |
| Estimate changes | Disclosed only when material, often company-level only; income-decreasing changes exist; segment shares look larger than company shares (GE 29% vs 15.5%) | Sign and size vs profit; recurrence; both directions; denominator named (2.5) |
| Catch-up revenue tag | Revenue, not profit; only 126 filers | Own history only |
| Restatement delta | Recasts, standard adoptions, tag switches, 8-K/DEF 14A facts, unit rounding and de-SPAC switches look like errors; a dollar floor hides small-company corrections (Infleqtion) | Step labels; periodic forms only; tolerance with a $0.1M floor (question 2.3); first-run baseline |

### Questions
**2.1 Score set and role**
- (a) *Recommended.* Cash conversion and accruals as earnings-persistence warnings, with no return weight. M-score now: components shown, M and M with SGI = 1 side by side, own-history and peer percentile, and the published cut-off displayed. Review only when M with SGI = 1 is above −1.78: today that is NVIDIA FY2026, while NVIDIA FY2025 and Marvell FY2026 get a "growth-driven" note. Misstatement score after the extra concepts, with its percentile. Why: the decay evidence says these are screens, not signals; the M-score alone showed a net investor benefit (S-new-15); and the SGI-neutral test removes growth alarms without waiting for the stage decision.
- (b) Both scores now, same display at the published cut-offs. Gets wrong: flags NVIDIA (both years) and Marvell on growth, and puts Apple (1.30), Microsoft (1.15), Boeing (1.63) and Strategy (3.28) above the misstatement score's 1.00 line, a band that also holds 36.3% of clean firm-years.
- (c) Cash conversion only, no scores. Gets wrong: drops the one screen with a net investor benefit, and would not show NVIDIA FY2026's asset-quality jump (AQI 1.52).

**2.2 Restatement sources and escalation**
- (a) *Recommended.* 4.02, plus the dei error flag (about 54 instance reads, or none from stored HTML), plus 10-K/10-Q text, plus a one-off fetch of at most 35 historical filings (8-K 8.01 second pass after a dry-run count). An auditor change within the prior 12 months escalates, with a de-SPAC shown as context. Why: it catches the B.3 and little r cases an 8-K-only detector misses (Infleqtion's interim-only correction ticks no box), and it labels GE's steps from its 2018 8-K.
- (b) 4.02 events only. Gets wrong: misses Infleqtion's little r (no 8-K, no checkbox), GE's recast causes and Tesla's ASU 2023-08 change.
- (c) As (a) without the escalation. Gets wrong: drops the auditor-change signal (29% of Big R after a change, against an 11% base).
- (d) As (a) without the historical fetch. Gets wrong: about 102 pre-corpus steps stay `unexplained` baseline, including GE's revenue steps that the 8-K explains to the dollar.

**2.3 Tolerance for unexplained deltas** (revenue, net income, CFO; all options use the S2.6 labels and first-run baseline)
- (a) *Recommended.* Review a step or residual larger than both 0.5% of the value and $0.1M (starting values, unsourced). Recasts are shown as "recast, not an error", with no flag. Why: it creates both of Infleqtion's Q1 2026 correction steps, which the draft's $1M floor missed, and it still queues GE's four residuals after the 8-K text. Gets wrong: queues GE's +$4M CFO residual on a −$244M base (near-zero base).
- (b) Review above the smaller of 1% of the value or 5% of pretax income. The 5% figure is the rule of thumb SAB 99 discusses and warns against using alone (S-new-25). Gets wrong: the tolerance shrinks with pretax income, so in a near-break-even year revenue steps are judged against 5% of profit (Intel FY2023: $38M instead of $271M under (a)). It also lets GE's FY2017 net-income residual (−30) pass.
- (c) Above 2% only. Gets wrong: misses Infleqtion's net-loss correction (1.8%), Boeing's 2016–17 revenue revisions of 0.66–1.78%, and all four GE residuals.

**2.4 Estimate changes and prior filings**
- (a) *Recommended.* Bands < 10% / 10–25% / ≥ 25% of the 2.5 denominator, both directions shown. Fetch one prior 10-K per watchlist company now (about 14 requests: ETV files N-CSR, and SPCX, listed in June 2026, likely has no prior 10-K; not checked), which also closes DS7 for risk-factor diffs. Why: the 3-year recurrence test needs history, and DS7 is already an open gap.
- (b) Any quantified change is a note; the prior 10-K waits for M06/M11. Gets wrong: Alphabet's 2023 change is judged alone, because there is no history for the recurrence test.
- (c) Flag income-increasing changes only. Gets wrong: hides Amazon's 2025 income-decreasing change (net income −$1.0B), which the bands should show.

**2.5 Estimate-share denominator** (new; GE worked example)
- (a) *Recommended.* Company figures matched to the amount's tax basis and period (S2.7), with `not_meaningful` for a denominator ≤ 0 or below 1% of revenue. A segment share is shown beside it only when segment profit is stored (5.4, DS12) or quoted in a verified passage. Why: company denominators are non-dimensional and always available; GE still reads watch (2016) and elevated (first nine months of 2017).
- (b) Segment profit when the change is attributed to a segment, company otherwise. Gets wrong: segment profit is dimensional and missing for most names until 5.4, and GE's 29% and 45% exist only in the SEC order, so the fixture could not be built from filings.
- (c) Company net income only. Gets wrong: it divides pre-tax amounts by after-tax income (GE 2016: 15.9% against 15.5% on a pre-tax base; first nine months of 2017: 28.5% against 28.9%), a mismatch that grows with the tax rate, and it gives no segment view at all.

### New sources added in this section
- **S-new-r2-1** SEC Form 8-K and General Instructions (OMB 3235-0060, expires 2027-11-30): General Instructions B.1 (four business days) and B.3 (previously reported information), Items 4.01, 4.02 and 5.06 — https://www.sec.gov/files/form8-k.pdf (replaces the S98 citation for these points; S98 is the safe-harbor/Reg FD entry).
- **S-new-r2-2** SEC, Exchange Act Forms Compliance and Disclosure Interpretations 104.20–104.25 (2025-04-11; 104.18–104.19 withdrawn 2026-09-25), read 2026-10-12 — https://www.sec.gov/rules-regulations/staff-guidance/compliance-disclosure-interpretations/exchange-act-forms
- **S-new-r2-3** Lee, L. F. (2012), "Incentives to Inflate Reported Cash from Operations Using Classification and Timing", The Accounting Review 87(1):1–33, doi:10.2308/accr-10156 — https://academicnewsletter.sufe.edu.cn/info/415854
- **S-new-r2-4** Strategy Inc. Q1 2025 10-Q, R24 (ASU 2023-08 adoption table: effective 2025-01-01, prospective; digital assets 23,909,373 → 41,790,421; retained earnings effect 12,746,378, in $ thousands) — https://www.sec.gov/Archives/edgar/data/1050446/000095017025063536/R24.htm
- **S-new-r2-5** Tesla FY2024 10-K (ASU 2023-08 effective 2024-01-01; $236M prior-period adjustment to retained earnings) — https://www.sec.gov/Archives/edgar/data/1318605/000162828025003063/tsla-20241231.htm (also the "URL to add" in S-new-50).
- **S-new-r2-6** GE statements of financial position: FY2017 10-K R4 (contract assets 28,861 / 25,162) — https://www.sec.gov/Archives/edgar/data/40545/000004054518000014/R4.htm ; FY2016 10-K R5 (25,162 / 21,156) — https://www.sec.gov/Archives/edgar/data/40545/000004054517000010/R5.htm
- **S-new-r2-7** Infleqtion, Inc.: Q2 2026 10-Q, "Correction of Immaterial Errors" — https://www.sec.gov/Archives/edgar/data/2007825/000162828026057508/infq-20260630.htm ; submissions (former name Churchill Capital Corp X/Cayman; 8-K 2026-02-17 with items 2.01 and 5.06; 8-K 2026-03-26 with item 4.01) — https://data.sec.gov/submissions/CIK0002007825.json
- **S-new-r2-8** SEC XBRL companyfacts and companyconcept data fetched 2026-10-12 — patterns https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json and https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/<Tag>.json:
  - GE (CIK0000040545): NetCashProvidedByUsedInInvestingActivities, NetCashProvidedByUsedInFinancingActivities, IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest, UnbilledContractsReceivable, AssetsCurrent (absent);
  - Alphabet (CIK0001652044): DebtAndEquitySecuritiesGainLoss, NonoperatingIncomeExpense, OperatingIncomeLoss, IncomeTaxExpenseBenefit, Depreciation, SellingAndMarketingExpense, GeneralAndAdministrativeExpense;
  - Tesla (CIK0001318605): IncomeTaxReconciliationChangeInDeferredTaxAssetsValuationAllowance, IncomeTaxExpenseBenefit, LongTermDebt, ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlans, quarterly NetIncomeLoss 2024;
  - Strategy (CIK0001050446): CryptoAssetUnrealizedLossOperating, OperatingIncomeLoss, NetIncomeLoss, NetCashProvidedByUsedInOperatingActivities;
  - Intel (CIK0000050863): ValuationAllowanceDeferredTaxAssetChangeInAmount, LiabilitiesAndStockholdersEquity, StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest, revenue FY2023, pretax income FY2023;
  - Infleqtion (CIK0002007825): revenue, net income, CFO by filing;
  - M-score and Dechow inputs for NVIDIA (CIK0001045810), Marvell (CIK0001835632), Apple (CIK0000320193), Microsoft (CIK0000789019), Meta (CIK0001326801), Micron (CIK0000723125), Boeing (CIK0000012927), Amazon (CIK0001018724);
  - restatement-walk counts across the 13 us-gaap filers on the watchlist (GFS, in `ifrs-full`, not walked).
- **S-new-r2-9** General Electric 8-K filed 2018-04-13 (Item 8.01: recast of 2016–2017 for ASC 606, other-income presentation, ASU 2016-15, ASU 2016-18, ASU 2017-07 and LIFO to FIFO) — https://www.sec.gov/Archives/edgar/data/40545/000004054518000021/a8-kbodyandnarrative.htm

---

## Round 3 — Dilution and financing pressure

### What the research says
1. **Net issuance predicts lower returns, mainly at the extreme.**
   - After 1970, share issuance predicts returns more significantly than size, book-to-market or momentum individually (S-new-26, Pontiff & Woodgate). The effect holds in 41 non-US countries (S-new-26, McLean, Pontiff & Watanabe).
   - **Fama & French (1963–2005)** (S-new-11):
     - Negative abnormal returns are limited to the top quintile of net issuers: −0.27% a month, t −2.55, equal-weighted.
     - Average net issuance is about 24% in the top quintile, 4.5% in quintile 4 and 0.1–1.5% in quintiles 1–3.
     - Small issues (options, grants) earn positive abnormal returns, and repurchases above the median are followed by positive returns.
   - **Hou, Xue & Zhang** (S-new-10):
     - The issuance anomaly survives NYSE breakpoints and value weights: −0.66% a month, t −4.45, where 64% of 447 anomalies fail.
     - Its q-factor alpha is −0.29% (t −2.19).
   - Expect a weaker edge after publication (S-new-9).
   - Fama-French publish net-issuance portfolios with NYSE breakpoints (S-new-27).
   - The result to calibrate against is the one that survives NYSE breakpoints and value weights (S-new-10). An all-filer cross-section is set by microcaps instead (worked example: top quintile from +60% unfiltered, +12% with float ≥ $700M).
2. **Composite issuance** (S-new-28) = log(market-value growth) − log stock return, over 5 years.
   - It rises with equity issues, option plans and share-paid acquisitions, and falls with buybacks and dividends. Splits are neutral.
   - A 20% issue raises it by about 0.18.
3. **Issuers underperform afterwards** (S-new-29):
   - seasoned equity offerings by about 7% a year over 5 years (Loughran & Ritter);
   - debt issuers in high-volume periods, worse for small, young and speculative issuers (Spiess & Affleck-Graves);
   - floating-price convertibles (Hillion & Vermaelen);
   - total external financing (S103).
4. **SBC is a real cost** (S-new-30).
   - Investors price it as an expense (Aboody, Barth & Kasznik).
   - High-SBC firms have higher valuation ratios and lower later returns, and analysts exclude more of it from street EPS (Mohanram, White & Zhao).
   - Buybacks rise with options exercisable by all employees (Kahle), so buybacks should be shown net of SBC. Post-buyback drift: S81.
5. **A shelf is capacity, not a raise** (S-new-31).
   - Form S-3 I.B.1 requires at least $75M of non-affiliate float. Below that, I.B.6 (the "baby shelf") caps sales at one-third of float per 12 months.
   - A WKSI has $700M of float, or $1B of non-convertible debt issued in 3 years (Rule 405).
   - An ATM sells "into an existing trading market" (Rule 415(a)(4)); shelves last 3 years (415(a)(5)).
   - Staff interpretations (law-firm summary):
     - CFI 116.26 (2026-03-19) lets an ATM continue after float falls below $75M.
     - CFI 116.23 counts the full ATM amount toward the one-third cap.
   - A proposal reported June 2026 would remove the cap; it is not final.
   - The old engine's comment is right: treating a shelf as distress would fire on every small cap (`financial_intelligence.py:1260-1263`).
   - **The 424B form type says what kind of supplement it is** (Rule 424, S-new-r3-2): 424(b)(2) is a primary shelf takedown; 424(b)(3) covers other changes and is also what resale prospectuses use (INFQ below); 424(b)(5) combines the two; 424(b)(7) names selling security holders and their amounts. A 424B7, or a resale 424B3, adds no shares.
6. **ATM programs** (S-new-32).
   - 682 programs, more than $62B announced, 2008–2016. The sample excludes financials, so REITs are left out.
   - Users are smaller and less profitable, and hold more cash.
   - Firms take down 43% of the announced program on average (median 27%), and about a third complete 100%. Takedowns rise with the quarter's stock return.
   - Actual sales are disclosed only in aggregate in the 10-Q/10-K.
   - When access was eased, small firms' annual chance of raising equity rose 5.7 pp (+49%) (Gustafson & Iliev).
7. **Filing-fee exhibits are Inline XBRL**: large accelerated filers from 2024-07-31, all filers from 2025-07-31 (S-new-33).
   - A 424B carries one only when fees are paid with it.
   - Strategy's 424B5 (0001193125-24-247536) states a maximum of $21,000,000,000 of Class A common, fee $3,215,100.
8. **Diluted shares move with the profit sign.** ASC 260 excludes antidilutive securities, and ASU 2020-06 requires the if-converted method (S-new-34).
   - Strategy: Q2 2025 diluted 306.8M vs basic 275.2M (+11.5%); FY2025 diluted = basic = 277.7M (S-new-1).
   - So diluted shares cannot measure issuance.
9. **Same-filing comparatives are already split-adjusted.**
   - Strategy's Q2 2025 basic count is 275,244,000 in accession …26-000044 (S-new-1).
   - First-reported vs latest shows splits as 10× (Round 1 table).
   - This fails across an IPO, a de-SPAC close or a common-control recast: the earlier period belongs to another capital structure or another entity, even inside one filing (SPCX and INFQ below).
10. **8-K Items 3.02 and 3.03** (Form 8-K instructions, S-new-r3-3).
    - 3.02 (unregistered sales) need not be filed while sales since the last report stay below 1% of the class outstanding, or 5% for a smaller reporting company. A missing 3.02 is therefore not proof of no issuance; share counts remain the measure.
    - 3.03 covers material modifications to holders' rights, including a new class that limits them, and working-capital or dividend restrictions. It names a cause (split, recap, senior class), not an amount.
    - `events.py` already tags both as `capital` for M04 and M07. Intel's three 2025 placements each came under 3.02, and SPCX's and INFQ's event weeks both carry 3.02 and 3.03 (worked example).
11. **Rating downgrades are followed by lower returns; upgrades are not** (S-new-r3-1, Dichev & Piotroski).
    - All Moody's changes 1970–1997: abnormal returns of about −10% to −14% in the first year after downgrades, strongest for small, low-credit-quality firms; no reliable effect after upgrades.
    - No free rating feed exists in our sources. Companies state actual actions in 10-K/10-Q liquidity text, next to hypotheticals: Boeing's Q3 2024 10-Q reports Moody's April 2024 downgrade to Baa3/P-3 and, in the same note, the risk of further downgrades (S-new-r3-9).
12. **Data.**
    - Available now:
      - Every S-3, S-3ASR, S-1, S-8, F-3 and 424B2/3/4/5/7 is in `filing` (`sec/submissions.py`), with no new calls needed.
      - 8-K 3.02 and 3.03 are typed.
      - Annual CY frames of basic weighted-average shares, plus four quarterly-instant `dei:EntityPublicFloat` frames for the size filter, give the universe cross-section in about 6 requests a year (annual, because Q4 is sparse in quarterly frames: D-SEC-9). CY2025: 5,031 same-filing pairs (worked example).
      - `dei:EntityPublicFloat` is already read (`themes/flags.py`, D-M02-50).
      - Watchlist activity since 2023-10-12 (submissions JSON, S-new-r3-4): 125 424Bs (75 424B5, 24 424B2, 13 424B3, 11 424B7, 2 424B4), 13 S-3ASR, 3 F-3ASR, 1 S-3. META's list reaches back only to 2024-06-18. GOOG alone filed 28 while its share count fell (−1.6% in CY2025), so counting 424Bs as dilution would fire on debt programs.
    - Gaps and complications:
      - Documents for these forms are not stored.
      - Strategy's 21 424B5s in 2025 include preferred-stock offerings, so each supplement needs its security class before it counts.
      - ATM agreements usually come under 8-K 1.01 or 8.01 and need text phrases (old `bd_tools.py:446`).
      - Share bridges are mostly dimensional: META's `StockRepurchasedDuringPeriodShares` returns 404.
      - Warrant exercise prices are often untagged: INFQ has no `ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights` fact (404); the $11.50 sits on the 10-Q cover.
      - Up-C exchangeable units have no usable non-dimensional tag: the `MinorityInterestOwnershipPercentageByNoncontrollingOwners` frame holds 2 filers at CY2025Q4I.
      - IFRS filers report `ifrs-full:WeightedAverageShares`, with quarters in 6-Ks (GFS), so they are absent from the us-gaap frames.
13. **Old-engine defects:**
    - S-1/A is counted as a shelf, but it is often an IPO or resale.
    - "covenant" and "waiver of" match almost every 10-K.
    - No amounts are read.
    - "Credit Rating Action" fires on the substrings "credit rating", "downgrade" and "negative outlook" at severity "elevated" (`financial_intelligence.py:122`, `:1282`). Among 10-K documents filed 2025-03-01 to 2025-03-15, EFTS finds "credit rating" in 428 and "downgrade" in 325, against 1,183 containing "Item 1A" (roughly 36% and 27%; document counts, exhibits included), but the actual-event phrasing "downgraded our" in only 7 (S-new-r3-4). The substrings mostly catch risk-factor hypotheticals.

### Worked example
**CY2025 issuance cross-section** (S-new-r3-4; frames fetched 2026-10-12; log change in basic weighted-average shares, CY2025 vs CY2024, both values from the same filing)

| Universe | Firms (repurchasers / zero / positive) | Repurchaser median | Positive issuers: 20th / 40th / 60th / 80th percentile (80th = top-quintile start) | MSTR +44.2% | BA +17.5% | INTC +5.8% |
|---|---|---|---|---|---|---|
| A All filers | 5,031 (1,336 / 227 / 3,468) | −2.2% | +1.0 / +3.7 / +13.3 / +60.1% | Q4 (77th pct) | Q4 (64th) | Q3 (47th) |
| B Float ≥ $75M | 2,972 (1,119 / 42 / 1,811) | −2.2% | +0.6 / +1.9 / +5.7 / +19.0% | top (90th) | Q4 (79th) | Q4 (60th) |
| C Float ≥ $700M | 1,882 (880 / 32 / 970) | −2.2% | +0.5 / +1.5 / +4.1 / +12.1% | top (94th) | top (85th) | Q4 (67th) |

- Coverage: 5,204 CY2025 and 5,667 CY2024 values; 5,138 pairs, of which 5,031 (98%) come from one filing.
- Float is the latest `dei:EntityPublicFloat` across the CY2024Q2I, CY2024Q4I, CY2025Q1I, CY2025Q2I and CY2025Q3I frames, because each filer measures it at the end of its own second fiscal quarter. 641 firms have none and fall out of B and C.
- Universe A's top quintile holds 694 firms: 563 have float under $75M or none, and 38 have $700M or more.
- Nine names match a blank-check pattern ("Acquisition", "Merger Corp", …). None has float of $75M or more, so the float filter already removes them.
- The $75M and $700M lines are the S-3 primary-eligibility and WKSI thresholds (S-new-31), so neither is invented.
- Quarter-over-year placed on universe C: MSTR Q2 2026 +28.1% top (91st); INTC Q2 2026 +16.8% top (84th); BA Q2 2026 +4.5% Q4; SPCX +100.2% and INFQ +1,310% top, both artefacts (below). The bands are annual-average changes and the quarter figure is a 12-month change on quarterly averages: same horizon, not identical.
- **Reading.** On all filers MSTR is not even "extreme", because microcaps set the bar at +60%. On C the watchlist's three real issuers reach the top quintile for three different causes: a stated strategy (MSTR), a 2024 capital raise (BA) and strategic stakes (INTC).

**Strategy (MSTR): extreme issuer funded by ATM programs** (S-new-1, S-new-33, S-new-35)

| Row | Value | Source |
|---|---|---|
| Cover shares 2025-07-31 | Class A 263,912,697 + Class B 19,640,250 = 283,552,947 | Q2 2025 10-Q R1 |
| Cover shares 2026-07-24 | Class A 364,585,501 + Class B 19,640,250 = 384,225,751 | Q2 2026 10-Q R1 |
| Cover-to-cover change | +35.5% (log 0.304) in 358 days | computed |
| Basic weighted average, Q2 2026 vs Q2 2025 (one accession) | 352,534,000 vs 275,244,000 → +28.1% (log 0.247) | companyconcept |
| Basic weighted average, CY2025 vs CY2024 (one accession) | 277,660,000 vs 192,549,000 → +44.2% (log 0.366) | frames (S-new-r3-4) |
| Equity proceeds | FY2025 $16,271,959,000; H1 2026 $8,245,330,000 | companyconcept |
| Preferred proceeds (senior claims, not common dilution) | FY2025 $7,036,110,000; H1 2026 $7,534,966,000; preferred cash dividends H1 2026 $758,224,000 | companyconcept (S-new-r3-5) |
| SBC | FY2025 $53,369,000; H1 2026 $27,441,000 (not the driver) | companyconcept |
| ATM capacity (424B5, 2024-10-30) | $21.0B against 183,003,980 Class A shares at $255.34 → about 44.9% of Class A value | 424B5 + fee exhibit; computed |
| 424B5 count | 21 in 2025, 4 in 2026 to date; includes preferred offerings and program supplements | EDGAR list |
| Engine reading | Universe C: +28.1% is the 91st percentile of positive issuers and CY2025's +44.2% the 94th; the top quintile starts at +12.1% → "extreme". With the owner's issuance-funded tag (the tag is illustrative) → `m04_dilution` review, not a warning | computed |

**Meta (META) FY2025: buybacks more than offset SBC** (S-new-1)

| Row | Value |
|---|---|
| SBC | $20,427M (FY2024 $16,690M) = 10.2% of revenue ($200,966M), 17.6% of OCF ($115,800M) |
| Buybacks / RSU tax withholding | $26,248M / $18,400M |
| Basic weighted shares | 2,534M → 2,521M (−0.5%); diluted 2,614M → 2,574M (−1.5%) |
| Buyback offset (computed) | (26,248 + 18,400) ÷ 20,427 = 2.19×: about $44.6B of cash to cut basic shares 0.5% |

**Intel (INTC) 2025–26: strategic stakes, each under 8-K 3.02** (S-new-r3-6, S-new-r3-5)

| Row | Value | Source |
|---|---|---|
| US Department of Commerce | 274,583,000 shares at closing (a $20.74 price if all released funds arrive) + 158,740,000 into escrow ($20.00); $8,869.8M of CHIPS disbursements; blended $20.47 | 8-K 2025-08-25 (1.01, 3.02) |
| Government warrants | 240,516,150 shares at $20.00, exercisable only if Intel ceases to own at least 51% of its foundry business; 5-year term; 4.8% of cover shares, contingent | same 8-K |
| SoftBank | 86,956,522 shares at $23.00 = $2.0B | 8-K 2025-08-21 (3.02) |
| NVIDIA | 214,776,632 shares at $23.28 = $5.0B, subject to HSR clearance | 8-K 2025-09-18 (3.02) |
| Total placed | 735,056,154 shares = 16.8% of the 2025-07-18 cover count (4,377M) | computed |
| Cover shares | 4,377M (2025-07-18) → 4,770M (2025-10-17) → 4,995M (2026-01-16) → 5,044M (2026-07-17): +15.2% | dei |
| Basic weighted average | Q2 2026 5,104M vs Q2 2025 4,369M: +16.8% (log 0.155), top quintile on C. CY2025 shows only +5.8%: the late-year placements lag in the annual average | companyconcept |
| Check | The Q2 2026 weighted average exceeds the 2026-07-17 cover count by 60M; cause not checked (the escrowed shares are a candidate) | computed |
| Resale | A 424B7 (selling-holder form) followed on 2025-09-05; no new shares | submissions |
| Engine reading | Extreme band, cause linked to three 3.02 filings → information with a cause label, not `m04_dilution` | — |

**Infleqtion (INFQ): de-SPAC recast, warrants and resale overhang** (S-new-1, S-new-r3-5, S-new-r3-7)
- **Same CIK, two companies.** CIK 2007825 was Churchill Capital Corp X until 2026-02-18. The business combination closed 2026-02-13 at an exchange ratio of 0.34740312 (Q2 2026 10-Q).
  - Q1 2025 basic weighted average: 9,000,000 in the SPAC's 10-Q (filed 2025-06-13) and 14,737,927 in Infleqtion's Q1 2026 10-Q (filed 2026-05-15). Same CIK, same period, different entity: an as-of walk would call it a +63.8% restatement.
  - Q2 2026 vs Q2 2025 basic: 219,743,810 vs 15,586,999 = +1,310% (log 2.65). Legacy preferred converted 1:1 into 133,240,425 shares at the close (`ConvertiblePreferredStockSharesIssuedUponConversion`), and the SPAC's shares joined.
  - The CY2025/CY2024 frame pair (46,186,000 vs 39,808,027, +16.0%) comes from the Q2 2026 10-Q but does not reconcile with that filing's own H1 2025 figure of 15,164,809. It puts INFQ in universe C's top quintile by accident.
- **Warrants.** 10,350,000 public + 75,000 private = 10,425,000 (424B3, 2026-08-26). XBRL `ClassOfWarrantOrRightOutstanding` is 10,424,967, dated 2026-02-13 and repeated in the 2026-08-18 10-Q. `WarrantsAndRightsOutstanding` carries the count in a USD unit (10,412,167 at 2026-06-30).
- **Strike and price.** Exercise price $11.50 (10-Q cover). Last sale $13.83 on 2026-08-25 (424B3): in the money by $2.33.
- **Overhang.**
  - Gross: 10,425,000 ÷ 225,357,052 cover shares = 4.63%.
  - Net by treasury-stock arithmetic: 10,425,000 × 2.33 ÷ 13.83 = 1,756,345 shares = 0.78%.
  - Exercise cash if all are exercised: $119.9M.
- **Resale supply.** The 424B3 registers resale of up to 121,829,432 shares by selling securityholders = 54.1% of cover shares. That adds no shares, but it is the post-lock-up supply.
- Cover shares: 216,471,927 (2026-03-20) → 225,357,052 (2026-08-14), +4.1%; H1 2026 option exercises were 9,322,163 shares.

**SpaceX (SPCX): IPO year** (S-new-r3-5, S-new-r3-8)
- IPO in June 2026: 638.9M Class A shares at $135.00, net proceeds $85,675M (10-Q Note 1); 424B4 filed 2026-06-12.
- A 5-for-1 split in May 2026 (`StockholdersEquityNoteStockSplitConversionRatio1` = 5). The X and xAI mergers were share exchanges (10-Q Note 1).
- Convertible preferred (temporary-equity) shares: 2,046M (2025-12-31) → 135M (2026-03-31) → 0 (2026-06-30).
- Basic weighted average, Q2 2026 vs Q2 2025: 5,864M vs 2,929M = +100.2% (log 0.69), top quintile on every universe.
- Cover 2026-07-28: Class A 7,696,293,669 + Class B 5,485,486,276 = 13,181,779,945, which is 2.25× the Q2 weighted average. The year-over-year figure will jump again next quarter.
- New money: the 638.9M IPO shares are 4.85% of the cover count. The preferred conversion moves existing claims into the common count.
- Engine reading: IPO year → `not_meaningful` until four post-IPO quarters exist (starting value, unsourced). Cover-to-cover runs from the first post-IPO cover. The lock-up end comes from the 424B4 (over 10 MB; not read here).

**Boeing (BA): 2024 raise and a mandatory convertible** (S-new-r3-5, S-new-r3-9)
- October 2024: 112,500,000 common shares at $143.00, and 100,000,000 depositary shares of 6.00% Series A Mandatory Convertible Preferred (term sheet). FY2024 proceeds: common $18,200M, convertible preferred $5,657M. The proceeds suggest the over-allotment was also sold; not checked.
- Basic weighted average CY2025 vs CY2024: +17.5%, top quintile on C. Q2 2026 vs Q2 2025: +4.5% (Q4). The raise came late in 2024, so it shows mainly in the 2025 figure.
- Scheduled dilution: each depositary share converts into 0.2914–0.3497 common shares around 2027-10-15. On the term-sheet count that is 29.1M–35.0M shares, or 3.7–4.4% of the 790,370,020 cover shares (2026-07-21).
- Rating text: the Q3 2024 10-Q states an actual action (Moody's to Baa3/P-3 in April 2024) next to a hypothetical about further downgrades. Only the first is a rating event.
- Engine reading: extreme on C for 2025, cause linked (Oct 2024 424B5s) → information. `financing_pressure` depends on the survival gate (Round 4).

### All cases
1. Routine employee issuance (small positive issuance, which Fama-French find earns positive returns).
2. Buybacks that only offset SBC (META).
3. Net buyback.
4. Extreme ATM issuer (MSTR).
5. Issuance-funded model: bitcoin treasury, REIT, early growth (R2).
6. Share-paid acquisition (8-K 2.01, S-4), including common-control share exchanges inside an IPO year (SPCX's X and xAI mergers).
7. Strategic placements: Intel sold 735.1M shares in three 3.02 placements in 2025, 16.8% of its shares (S-new-r3-6).
8. Split or reverse split; 8-K 3.03 as the cause label.
9. Profit-sign flip moving the diluted count.
10. Multi-class filer with no non-dimensional count.
11. ATM set up (424B5) vs actual sales.
12. Preferred or debt supplements (not common dilution): MSTR preferred; GOOG's 28 424Bs since 2023-10-12.
13. Shelf only; WKSI routine automatic shelf.
14. Baby-shelf company near the one-third cap.
15. Convertibles: dilutive or antidilutive; capped calls; net-share settlement.
16. Warrants in or out of the money; SPAC redemptions; stale XBRL dates (INFQ: in the money, 0.78% net, 4.63% gross).
17. 8-K 3.02 unregistered sales and PIPEs, and sales below the 1% / 5% threshold that need no 8-K.
18. Weighted-average lag after a late-quarter ATM or a late-year raise (MSTR, BA, INTC).
19. Issuance with long runway vs with short runway.
20. Rule change (baby-shelf cap removed).
21. IPO year: pre-IPO weighted averages, preferred conversion and IPO shares in one comparison (SPCX +100%, more next quarter).
22. Lock-up expiry and resale registrations: supply, not new shares (INFQ 424B3 for 54.1% of cover shares; GFS and INTC 424B7s).
23. De-SPAC: the SPAC's own history and the recast target's history under one CIK; exchange-ratio recast (INFQ 0.34740312; Q1 2025 reads 9.0M and 14.7M).
24. Up-C or exchangeable units outside the Class A count (none known on the watchlist; no usable tag).
25. Mandatory convertible: scheduled dilution over a conversion-rate range (BA, 3.7–4.4% around 2027-10-15).
26. Contingent warrants (INTC: 240.5M, exercisable only if the 51% foundry condition breaks).
27. IFRS filer: `ifrs-full:WeightedAverageShares` (GFS 555M vs 553M, +0.4%) with quarters in 6-Ks, placed against the us-gaap breakpoints.
28. Unit mis-tags (INFQ's warrant count filed in USD).
29. Internally inconsistent frame pair (INFQ CY2025).
30. Credit-rating text: actual action / placed on review for downgrade / hypothetical / analyst "downgrade" of the stock / upgrade.

**Complete / known omissions.** This list covers every situation found on the 15 operating watchlist names on 2026-10-12 (ETV is a fund and excluded). Known omissions, with no watchlist case today: rights offerings, tracking stocks, spin-offs (share count unchanged while the company shrinks), share lending, and Up-C beyond a text finder.

### Suggestions
- **S3.1 `net_issuance_yoy`.**
  - Log change in basic weighted-average shares: current quarter vs the same quarter a year earlier, both from the latest filing (split-safe).
  - The cover-to-cover change is shown beside it where both covers exist.
  - Method tag `wavg_basic_same_filing`.
  - A comparison that crosses an IPO, a de-SPAC close (8-K 2.01 plus a former-name change in submissions) or a common-control recast is `not_meaningful`. The measure restarts with the first pair of post-event filings; cover-to-cover runs from the first post-event cover.
  - IFRS filers use `ifrs-full:WeightedAverageShares`.
- **S3.2 Issuance band** from yearly CY-frame breakpoints over a defined universe:
  - pairs whose two values come from the same filing;
  - public float of $700M or more (latest `dei:EntityPublicFloat` from four quarterly-instant frames), the WKSI line in Rule 405 (S-new-31);
  - blank checks out: SIC 6770 where `entity.sic` knows it, a name pattern otherwise;
  - the breakpoints apply to every company, smaller ones included, as NYSE breakpoints do (S-new-10, S-new-27).

  Zero issuers are kept apart. Labels: repurchaser (above or below median) / flat / positive quintiles 1–4 / top quintile "extreme issuer (S-new-11, S-new-10)". The stored value is the percentile (0–100) with the year's breakpoints, so the label can be rebuilt. About 6 requests a year (2 weighted-average frames + 4 float frames), fetched once a year after the spring 10-K season as a one-off under `refresh.lock`, not in the logon refresh. Informational until D13 weights exist and a labelled dilution case set exists (Round 6 calibrates CvD only).
- **S3.3 Composite issuance** (5 years) from `price_bar` and shares, shown beside net issuance.
- **S3.4 SBC block** (new `sbc` concept):
  - SBC ÷ revenue and ÷ OCF;
  - FCF after SBC (OCF − capex − SBC);
  - buyback offset = (buybacks + RSU withholding) ÷ SBC, shown beside the net share change.

  Compared with the company's own 3-year range. No universe threshold, because none with evidence was found.
- **S3.5 Financing capacity:**
  - active shelf (S-3, S-3ASR or F-3 within 3 years);
  - 424B supplements in the last 12 months, by form type and security class, never counted as sales:
    - 424B2 and 424B5: primary (common, preferred or debt, from the fee exhibit);
    - 424B3 and 424B7: resale or update, adding no shares; the resale count is read from text as supply;
    - 424B4: IPO, with the lock-up end read from text;
  - ATM capacity from the fee-exhibit XML where present, as a percentage of market cap;
  - actual sales from `ProceedsFromIssuanceOfCommonStock` and the share-count change;
  - baby-shelf headroom (one-third of float).

  Regulatory caps live in config, sourced and dated. Fetch plan: about 2 requests per 424B (filing index + fee exhibit). The watchlist's 125 424Bs since 2023-10-12 come to about 250 requests one-off, under a minute at 5/s. New 424Bs, about 3–4 a month at the observed rate, join the logon refresh. Both run under `refresh.lock`.
- **S3.6 Convertible and warrant overhang.**
  - Note-text phrases: "conversion rate", "initial conversion price", "warrants to purchase … exercise price", "mandatory conversion".
  - Numbers are verified against the stored passage and go to review (`m04_overhang`).
  - Shown at the current price as gross shares and as net shares by treasury-stock arithmetic, both ÷ basic shares. `ClassOfWarrantOrRightOutstanding` is used where present, with its date.
  - Contingent warrants are listed apart (INTC). Mandatory convertibles show their share range and date (BA).
  - Unit check: a share count in a currency unit is reported as a data defect (INFQ).
  - Fixture: INFQ at $13.83 → gross 4.63%, net 0.78%.
- **S3.7 Old engine.**
  - **Keep:** the severity vocabulary with "unknown" reported, and the ATM 8-K phrases.
  - **Drop:** the bare "covenant" and "waiver of" substrings, and S-1/A counted as a shelf.
  - **Change "Credit Rating Action":**
    - drop the bare substrings, which match roughly 36% and 27% of 10-K documents;
    - use a sentence classifier over `NEAR(downgrad* rating*, 10)`, "review for downgrade" and "negative outlook", with classes actual / review / hypothetical / analyst / upgrade;
    - only actual and review emit, at the old severity "elevated", as information beside `financing_pressure`, never as a gate input (S-new-r3-1);
    - one `m04_rating` review item per new actual action.
  - **8-K 3.02 and 3.03 feed Round 3 as cause labels:** placement, split, recap or senior class. They are linked to share-count jumps and never counted as amounts.
- **S3.8 Regression cases:**
  - MSTR 2025–26: extreme and model-tagged → review; preferred 424B5s are not common dilution.
  - META 2025: offset 2.19× → informational.
  - INFQ 2026: de-SPAC → `not_meaningful`; warrants in the money (gross 4.63%, net 0.78%); resale supply 54.1%.
  - INTC 2026: extreme on C, cause linked to three 3.02 placements → information; contingent warrants listed apart.
  - SPCX 2026: IPO year → `not_meaningful`; IPO shares 4.85% of cover.
  - BA 2025: extreme on C, cause linked; mandatory convertible 3.7–4.4%.
  - GFS: IFRS tags, +0.4%.
  - Universe fixture: the CY2025 breakpoints above, from stored frame files.
- **S3.9 Review items from this round** (D8; follows the D-M02-51 pattern; volumes are estimates):

  | Kind | Raised when | First-scan baseline (watchlist) | Weekly after baseline | Priority |
  |---|---|---|---|---|
  | `m04_dilution` | Extreme band and an owner model tag; or extreme band with no linked cause (no 3.02, 2.01/S-4, 424B5, IPO or de-SPAC link) | 1 (MSTR); INTC and BA cause-linked; SPCX and INFQ `not_meaningful` | 0–1, in earnings weeks | 1 |
  | `m04_overhang` | Convertible, warrant or mandatory-convertible terms read from text with a verified quote | About 4 companies (MSTR, INFQ, INTC, BA), one item per instrument | 0–1 (new 8-K 1.01/3.02 or 424B) | 2 |
  | `m04_financing_doc` | ATM agreement or resale registration found by phrase, with no fee exhibit or count to confirm it | A few (MSTR programs, INFQ resale) | 0–1 | 3 |
  | `m04_rating` | Rating sentence classified actual or review | At most 1 from the latest-filing corpus: INTC's FY2025 10-K contains "downgraded" (not yet classified); BA's latest filings do not | 0–1 | 4 |

  Cap: at most 5 Round 3 items a week inside the M04 cap (starting value, unsourced). The baseline flushes in priority order over 2–3 weeks, and waiting items are listed on the M04 tab.
- **S3.10 Signals from this round** (for the consolidated signals-out table; the PT/ST columns are proposals):

  | Signal | Type / range | Meaning | MY | PT | ST |
  |---|---|---|---|---|---|
  | `net_issuance_yoy` | log change | Basic weighted shares, quarter vs same quarter a year earlier, one filing | ✓ | ✓ | info |
  | `issuance_pct` | 0–100 | Percentile in the year's frames universe; band label rebuilt from stored breakpoints | ✓ | ✓ | info |
  | `composite_issuance_5y` | log | Daniel–Titman, 5 years | ✓ | info | info |
  | `sbc_offset` | ratio | (buybacks + RSU withholding) ÷ SBC | ✓ | info | info |
  | `overhang_gross_pct`, `overhang_net_pct` | % of basic shares | In-the-money warrants and convertibles at the current price | ✓ | ✓ | ✓ |
  | `financing_pressure` | 1 on, 0 off, absent when inputs are missing | Warning per question 3.4 | ✓ | ✓ | ✓ |

  All values are numeric, so they fit the NUMERIC `signal.value`. Evidence grade A (filings). Text-derived numbers are written only after the quote check (D21).

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Diluted weighted shares | Move with the profit sign | Issuance measured on basic shares; diluted–basic gap shown in profit periods only |
| Splits | 10× "growth" or "restatements" | Same-filing pairs; `split_factor` cross-check |
| Multi-class | Metric silently missing | "Missing: multi-class" label or class-summed cover count (1.1) |
| Weighted-average lag | Late-quarter ATM sales or late-year raises show only partly | Cover-count cross-check (MSTR: +35.5% cover vs +28.1% weighted; INTC CY2025 +5.8% vs Q2 2026 +16.8%) |
| Share-paid acquisitions; strategic stakes | Large issuance that may create value | Cause linked (8-K 2.01, 3.02, S-4); label |
| Issuance-funded models | Issuance is the strategy | Owner model tag → review, not warning |
| Shelf, 424B counts | Capacity, not dilution; preferred, debt and resale supplements | Classify by form type and security class; sales from proceeds and share counts |
| ATM capacity | Firms use 43% on average, median 27% | Capacity and actual sales shown separately |
| SBC vs buybacks | Buybacks only offset SBC; withholding sits in financing cash flow | Offset ratio beside net share change |
| Paper thresholds | 1963–2005 equal-weighted; edge halves after publication | Own cross-section percentiles (float ≥ $700M universe); informational |
| Frames universe | All-filer breakpoints set by microcaps (top quintile from +60%) | Same-filing pairs, float ≥ $700M, blank checks out |
| Convertibles and warrants | As-converted shares only when dilutive; capped calls; stale warrant counts | Text with quote → review; gross and net shown; in the money only |
| Mandatory and contingent instruments | Scheduled dilution missed; conditional warrants counted as live | Range and date for mandatories; contingent warrants listed apart |
| IPO, de-SPAC and recast years | Pre-event counts or another entity's history read as issuance (SPCX +100%, INFQ +1,310%) | `not_meaningful` until post-event pairs exist; 8-K 2.01 and former-name check |
| Same CIK, two entities | SPAC history and the recast target's history under one CIK (INFQ Q1 2025: 9.0M vs 14.7M) | Predecessor-break flag; the as-of walk stops at the close |
| Frame pairs | A de-SPAC pair can be internally inconsistent (INFQ CY2025) | The company's own quarterly series checked before banding |
| Resale registrations and lock-ups | Read as new issuance, or the supply is missed | Form-type class; resale count shown as supply, never inside dilution |
| 8-K 3.02 | Absent below 1% (5% for smaller reporting companies) | Share counts remain the measure; 3.02 only names the cause |
| Unit mis-tags | A count filed in USD (INFQ warrants) | Unit check; reported as a data defect |
| Up-C units | Class A count understates the economic share base | Text finder → review; "missing: exchangeable units" |
| Credit-rating text | Risk-factor hypotheticals and analyst "downgrades" match | Sentence classifier; actual and review only |
| Rule changes | Baby-shelf cap may go | Caps in config with source and date |

### Questions
**3.1 Issuance measure**
- (a) *Recommended.* Basic weighted average, same quarter year over year from one filing, with a cover-to-cover cross-check and S3.1's `not_meaningful` rule across IPO, de-SPAC and recast events. Why: split-safe, present for every filer, and not moved by the profit sign. Gets wrong: it lags late-quarter sales (MSTR +28.1% weighted vs +35.5% cover), which the cross-check shows.
- (b) Period-end count (the Fama-French definition). Gets wrong: META, MSTR and GOOG have no non-dimensional count (404) and go missing, and balance-sheet and cover dates get mixed.
- (c) Diluted weighted average. Gets wrong: MSTR swings 11.5% with the profit sign (Q2 2025 diluted 306.8M vs basic 275.2M; FY2025 equal).

**3.2 Bands, universe and window**
- (a) *Recommended.* Yearly percentile bands from the CY frames over same-filing pairs with float ≥ $700M, blank checks excluded; the top quintile is labelled "extreme" (+12.1% for CY2025). A 12-month window, with the 5-year composite beside it. Why: it matches the large-firm breakpoints behind the evidence (S-new-10, S-new-27), and the watchlist's three real issuers (MSTR, BA, INTC 2026) land in the top quintile. Gets wrong: small companies are judged against large-firm breakpoints, so more of them read "extreme"; that is intended, as with NYSE breakpoints.
- (b) Float ≥ $75M (the S-3 primary line). Top quintile from +19.0%. Gets wrong: BA's 2025 +17.5% and INTC's Q2 2026 +16.8% drop to quintile 4, although both added about 17% to their share counts in a year.
- (c) All SEC filers (the earlier draft). Top quintile from +60.1%, set by microcaps (563 of its 694 names have float under $75M or none). Gets wrong: MSTR's +44.2% reads only quintile 4.
- (d) Fixed cut-offs such as 5%, 10% and 20% a year (no evidence supports these numbers). Gets wrong: at 20%, BA and INTC are missed; at any level, the label ignores how the market's issuance moves.
- (e) Number and percentile only, no bands. Gets wrong: question 3.4 has no "extreme" condition to test.

**3.3 Shelves and ATM programs**
- (a) *Recommended.* Detect from stored metadata, classify each 424B by form type and security class, and fetch the fee exhibit for capacity where one exists (about 2 requests per 424B: about 250 one-off for the watchlist, then the logon refresh). Read text only for 424B4 lock-ups and resale counts. Sales are measured from proceeds and share counts. Why: real amounts without reading prospectuses. Gets wrong: capacity stays unknown where fees were paid with the shelf instead of the 424B; it is shown as "capacity unknown".
- (b) Also fetch and read all 424B text. Gets wrong: nothing that (a) gets right, but it costs one multi-megabyte document per 424B (MSTR: 30 since 2023-10-12), and SpaceX's 424B4 alone exceeds 10 MB.
- (c) Shelf metadata only (old engine). Gets wrong: MSTR's preferred 424B5s count as common, GOOG's 28 debt-program 424Bs count as financing, INFQ's resale 424B3s count as issuance, and no amounts are read.

**3.4 When it warns** (company model tag)
- (a) *Recommended.* `financing_pressure` warns only when three conditions all hold:
  - the issuance band is "extreme";
  - the survival gate fails, or runway sits in the warn band (6–8 quarters under 4.2a; the approved D-M04-1 gate already fails below 6);
  - the company is not owner-tagged with an issuance-funded or asset-holding model.

  Any one of these alone is information. Model-tagged names become `m04_dilution` review items.
  - **Tag vocabulary** (the owner sets it; the engine proposes from SIC and 10-K text): `issuance_funded` (equity-funded growth, R2), `asset_holding` (balance-sheet asset strategy, such as MSTR's bitcoin treasury), `reit` (SIC 6798, payout funded by issuance), `none`. Rounds 2 and 4 read the same tag. If the owner moves the tag question ahead of Round 2, this list is the proposal.
  - **Change to D-M04-1:** the same tag gives MSTR-like names a liquidity-only survival gate (Round 4). This belongs in the consolidated table of D-M04-1 changes.
  - **M01:** `financing_pressure` is a warning to the owner. It does not change M01 rules 3 or 7, which read only `survival_gate` and `cvd_state`.

  Why: issuance or shelves alone would fire on every small cap and on MSTR's stated strategy. Gets wrong: a gate that is "incomplete" gives no warning (shown as incomplete, not as safe).
- (b) Warn on "extreme" issuance alone. Gets wrong: it warns on INTC 2026 (strategic stakes), BA 2025 (funded by the raise) and MSTR every quarter, and on SPCX and INFQ wherever the IPO rule is missed.
- (c) No model tag; all companies treated alike. Gets wrong: MSTR's stated strategy becomes a warning whenever its gate fails or warns, and its gate reads bitcoin swings (Round 4 failure-mode row).

### New sources added in this section
- **S-new-r3-1** Dichev & Piotroski (2001), "The Long-Run Stock Returns following Bond Ratings Changes", J. Finance 56(1):173–203, doi 10.1111/0022-1082.00322 — https://ideas.repec.org/a/bla/jfinan/v56y2001i1p173-203.html
- **S-new-r3-2** SEC Rule 424, 17 CFR 230.424 (prospectus filing types (b)(2), (b)(3), (b)(5), (b)(7)) — https://www.law.cornell.edu/cfr/text/17/230.424
- **S-new-r3-3** SEC Form 8-K and General Instructions (OMB 3235-0060), Items 3.02(b) and 3.03, pp. 23–24 — https://www.sec.gov/files/form8-k.pdf (can replace S98 wherever 8-K item rules are cited)
- **S-new-r3-4** SEC data APIs, fetched 2026-10-12:
  - Frames: https://data.sec.gov/api/xbrl/frames/us-gaap/WeightedAverageNumberOfSharesOutstandingBasic/shares/CY2025.json and …/CY2024.json; https://data.sec.gov/api/xbrl/frames/dei/EntityPublicFloat/USD/CY2025Q2I.json (also CY2024Q2I, CY2024Q4I, CY2025Q1I, CY2025Q3I); https://data.sec.gov/api/xbrl/frames/us-gaap/MinorityInterestOwnershipPercentageByNoncontrollingOwners/pure/CY2025Q4I.json
  - Submissions (424B and shelf counts since 2023-10-12): https://data.sec.gov/submissions/CIK##########.json for the 15 operating watchlist companies
  - EFTS full-text counts, 10-K documents filed 2025-03-01 to 2025-03-15, for "Item 1A", "credit rating", "downgrade", "negative outlook" and "downgraded our" — e.g. https://efts.sec.gov/LATEST/search-index?q=%22credit%20rating%22&forms=10-K&dateRange=custom&startdt=2025-03-01&enddt=2025-03-15 ; per-company "downgraded" and "credit rating" queries for INTC (CIK 50863) and BA (CIK 12927), 10-K/10-Q, 2024-01-01 to 2026-10-11
- **S-new-r3-5** SEC XBRL companyconcept/companyfacts data, fetched 2026-10-12 (additions to S-new-1). Pattern: `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/<taxonomy>/<Tag>.json`
  - Intel (CIK0000050863): WeightedAverageNumberOfSharesOutstandingBasic; dei EntityCommonStockSharesOutstanding.
  - Boeing (CIK0000012927): WeightedAverageNumberOfSharesOutstandingBasic, ProceedsFromIssuanceOfCommonStock, ProceedsFromIssuanceOfConvertiblePreferredStock; dei EntityCommonStockSharesOutstanding.
  - SpaceX (CIK0001181412): WeightedAverageNumberOfSharesOutstandingBasic, TemporaryEquitySharesOutstanding, StockholdersEquityNoteStockSplitConversionRatio1, ProceedsFromIssuanceInitialPublicOffering.
  - Infleqtion (CIK0002007825): WeightedAverageNumberOfSharesOutstandingBasic, ConvertiblePreferredStockSharesIssuedUponConversion, PreferredStockConvertibleConversionRatio, WarrantsAndRightsOutstanding, ClassOfWarrantOrRightOutstanding, StockIssuedDuringPeriodSharesStockOptionsExercised; dei EntityCommonStockSharesOutstanding, EntityPublicFloat; ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights (404).
  - Strategy (CIK0001050446): ProceedsFromIssuanceOfPreferredStockAndPreferenceStock, DividendsPreferredStockCash.
  - GlobalFoundries (CIK0001709048): ifrs-full WeightedAverageShares.
- **S-new-r3-6** Intel Form 8-Ks (replace the secondary S-new-68 in this round):
  - 2025-08-25, Items 1.01/3.02 (US Department of Commerce shares and warrants), accession 0000050863-25-000129 — https://www.sec.gov/Archives/edgar/data/50863/000005086325000129/intc-20250822.htm
  - 2025-08-21, Item 3.02 (SoftBank), accession 0000050863-25-000126 — https://www.sec.gov/Archives/edgar/data/50863/000005086325000126/intc-20250818.htm
  - 2025-09-18, Item 3.02 (NVIDIA), accession 0000050863-25-000155 — https://www.sec.gov/Archives/edgar/data/50863/000005086325000155/intc-20250915.htm
- **S-new-r3-7** Infleqtion:
  - Q2 2026 10-Q (cover: warrants at $11.50; Note 1: exchange ratio 0.34740312), accession 0001628280-26-057508 — https://www.sec.gov/Archives/edgar/data/2007825/000162828026057508/infq-20260630.htm
  - 424B3 of 2026-08-26 (last sale $13.83 on 2026-08-25; 10,350,000 public and 75,000 private warrants; resale of up to 121,829,432 shares), accession 0001193125-26-368786 — https://www.sec.gov/Archives/edgar/data/2007825/000119312526368786/d25094d424b3.htm
- **S-new-r3-8** SpaceX:
  - Q2 2026 10-Q (Note 1: IPO 638.9M Class A at $135.00, net $85,675M; X and xAI mergers by share exchange; cover counts at 2026-07-28), accession 0001628280-26-052535 — https://www.sec.gov/Archives/edgar/data/1181412/000162828026052535/spcx-20260630.htm
  - 424B4 of 2026-06-12 (lock-up terms; over 10 MB, not read) — https://www.sec.gov/Archives/edgar/data/1181412/000162828026042639/spaceexplorationtechnologi.htm
- **S-new-r3-9** Boeing:
  - Mandatory convertible and common offering term sheet (FWP, 2024-10-29) — https://www.sec.gov/Archives/edgar/data/12927/000119312524246135/d825843dfwp.htm
  - Q3 2024 10-Q, Note 1 liquidity (Moody's downgrade to Baa3/P-3, April 2024) — https://www.sec.gov/Archives/edgar/data/12927/000001292724000082/ba-20240930.htm

---

## Round 4 — Survival gate and distress language

### What the research says
1. **Altman Z** (S-new-36, primary; S-new-r4-1, Altman's own 2017 slides).
   - Built on 33 bankrupt and 33 paired manufacturers (1946–65).
   - One year before failure, at the 2.67 cut-off (1.81 in brackets), accuracy was 82% (75%) for 1969–75, 85% (78%) for 1976–95 and 94% (84%) for 1997–99. Two years out: 68–80%. Three to five years out on the original sample: 29–48%.
   - Type II error (healthy firms scored as distressed) has risen:
     - 15–20% of all firms and 10% of the largest scored below 1.81;
     - in 1999 more than 20% of Compustat industrials did.
   - Altman advocates 1.81.
   - The average Z rose to almost 10 in 1999, mostly through market value (X4).
   - Z″ = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4, with X4 = book equity ÷ total liabilities (S-new-36).
   - **Zones, now confirmed in a primary source.** Altman (2000) adds the +3.25 constant in the emerging-market version. His 2017 slides apply the same constant to "manufacturers, non-manufacturer industrials; developed and emerging market credits", with zones of 4.35 and 5.85 (S-new-r4-1, slide 27). Those are the 1.10 / 2.60 zones (S34) plus 3.25. So the two forms agree, and only mixing them misleads.
   - Slide 28 maps Z″ (with the constant) to bond ratings. The 2013 medians are 4.03 for B, 2.57 for CCC and 0.05 for 94 Chapter 11 filers (2010–13).
2. **Market-based measures beat accounting-only scores** (S-new-37):
   - about half of the accounting ratios in earlier models are not significant, while market size, past returns and idiosyncratic volatility predict (Shumway);
   - a Black-Scholes-Merton probability carries more information than Z or O (Hillegeist et al.);
   - about 0.75 accuracy across countries (Altman et al., abstract).
3. **Ohlson O-score** (S-new-38). The original was read on 2026-10-12 (S-new-r4-2).
   - Sample: 105 industrial firms that failed in 1970–76 (8 NYSE, 43 AMEX, 54 OTC or regional) and 2,058 that did not. The mean lead from the last fiscal year-end to failure is about 13 months (p. 115).
   - Model 1 predicts failure within one year. Its coefficients match the S-new-38 formula (Table 4, p. 121).
   - SIZE = log(total assets in dollars ÷ GNP price-level index), with the index at 100 for 1968 and taken for the year before the balance-sheet date (p. 118).
     - Entering assets in $ millions shifts O by 0.407 × ln 10⁶ ≈ 5.6.
     - An index scaled to 1.0 instead of 100 shifts O by 0.407 × ln 100 ≈ 1.9.
     - The index comes from FRED GNPDEF (2017 = 100). Its 1968 average is 18.24, which puts 2020 at about 577, 2021 at 603 and 2025 at 706 on a 1968 = 100 base (S-new-r4-2).
   - A cut-off of 0.038 minimizes the sum of error rates. At that cut-off, 17.4% of non-failed firms and 12.4% of failed firms are misclassified (p. 126).
   - FUTL uses "funds provided by operations", a funds-statement measure from before the cash-flow statement existed. OCF is a proxy and must be labelled as one.
4. **CHS** (S-new-39), a monthly logit on CRSP/Compustat, 1963–2003.
   - Pseudo-R² falls from 0.312 next month to 0.114 at 12 months and 0.044 at 36 months.
   - It needs a market cross-section to winsorize, plus total S&P 500 value for RSIZE, which our sources lack.
   - Distressed stocks earned anomalously low returns from 1981 to 2003 (CHS; Dichev with Z and O). Persistence after 2003 was not checked.
5. **Young firms read as distress by construction.**
   - The share of industrial firms with negative retained earnings rose from 11.8% (1978) to 50.2% (2002) (S-new-40).
   - No published false-positive rate exists for Rivian-type firms.
6. **Going-concern opinions are weak predictors in both directions** (S-new-41, S-new-42).
   - About half of bankruptcies are preceded by one, and about 10% of recipients file within a year. These come from pre-ASU 2014-15 studies cited by Blay, Moon & Paterson.
   - After ASU 2014-15, opinions rose for stressed survivors, and a larger share of bankruptcies were preceded by one (Bakarich & Baranek, abstract).
   - First-time opinions are followed by about −14% drift over a year, with limited profit after costs (Kausar, Taffler & Tan).
   - FY2025 rates: 19.6% overall, 36% for non-accelerated filers and smaller reporting companies, 0.3% for large accelerated filers; over 70% are repeats (Audit Analytics).
   - Invitae shows how late the text comes. EFTS finds "substantial doubt" in its 10-K and 10-Q filings only in 2015–18 and in the Q2 and Q3 2023 10-Qs. Its first "exists" conclusion was filed 98 days before its 8-K Item 1.03 (S-new-r4-5, S-new-r4-6).
7. **The rules fix the wording we can search for** (S-new-43, S-new-r4-3).
   - ASC 205-40: management evaluates every period. Substantial doubt exists when it is "probable" the entity cannot meet obligations within one year. Disclosure is required even when management's plans alleviate the doubt.
   - AS 2415: the auditor's paragraph must say "substantial doubt" and "going concern", without conditional language. Absence of the paragraph is not assurance.
   - 10-Qs carry management's evaluation only.
   - IFRS filers (GFS files 20-F and 6-K) use IAS 1.25 wording: "material uncertainties" that "may cast significant doubt". IFRS 18 moves this text unchanged to IAS 8.6K, effective 2027 (S-new-r4-3).
   - 6-Ks carry no 8-K item codes, so the 1.03, 2.04 and 3.01 detectors are silent for foreign filers.
8. **Covenant violations are common and usually not distress** (S-new-44).
   - 10–20% of US non-financial firms report a violation in any year (1996–2008).
   - Violations are followed by cuts to acquisitions, capex, leverage and payouts and by more CEO turnover; performance then improves (Nini, Smith & Sufi).
   - Their method was text search followed by manual reading, with financials excluded (Becher, Griffin & Nini).
   - Covenants are set tight as "trip wires" (Dichev & Skinner), and investment drops sharply after a violation (Chava & Roberts).
9. **Breaches are disclosable** (S-new-45).
   - Reg S-X 4-08(c): the notes state uncured defaults and waiver periods.
   - ASC 470-10-45-11: callable debt is classified as current unless waived for more than a year or a cure is probable. That reclassification is a text event. The yearly roll-down of scheduled maturities into current debt is not.
   - 8-K 2.04 is already typed as high-severity.
10. **Maturities** (S-new-46, S-new-r4-4).
    - `LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths` plus the year-2 to after-year-5 tags sit on the annual schedule. The taxonomy excludes rolling interim schedules from the year-1 tag. Extension-tagged buckets are missing from companyfacts.
    - Release 33-10890 removed the contractual-obligations table, so cash requirements now sit in narrative text.
    - **Current-debt tags overlap.** `DebtCurrent` is defined as short-term debt plus current maturities, and `LongTermDebtCurrent` "includes … commercial paper". Adding `CommercialPaper` to either can double count. Boeing's FY2019 10-K tags `DebtCurrent` 7,340 and `CommercialPaper` 6,109 ($M). Their sum, 13,449, exceeds Boeing's liquidity of 10,030; `DebtCurrent` alone does not.
    - **Scheduled roll-down looks like a reclassification.** Boeing's current debt went from 1,278 (2024-12-31) to 7,930 (2025-03-31). Its FY2024 10-K had already scheduled 1,173 for 2025 and 8,022 for 2026 (S-new-r4-4).
11. **Runway** has no standard definition or peer-reviewed threshold. ASC 205-40's one year is the legal anchor (S-new-43).
    - The old engine's ladder: < 12 months distressed, < 24 moderate, for small caps only.
    - Its integrity gate withheld a verdict when inputs disagreed (the false "Distressed" call on Viking Therapeutics; `financial_intelligence.py:78-86`).
    - **Undrawn credit is almost never tagged** (S-new-r4-4, checked 2026-10-12).
      - None of the 15 operating watchlist names tags `LineOfCreditFacilityRemainingBorrowingCapacity` for a current period; Tesla's last value is from 2016.
      - GFS tags the IFRS equivalent, `UndrawnBorrowingFacilities` (1,116 at 2025-12-31).
      - Rivian returns 404 for both line-of-credit tags.
12. **Financials are excluded.** Altman's samples are manufacturers; Nini et al. drop SIC 6000–6999; FF12 group 11 is already coded (`themes/industries.py`, S112).
13. **Data.**
    - All Z″ inputs are mapped.
    - Debt and revolver tags are in `fact` where non-dimensional.
    - Going-concern booleans are not in companyfacts, so text is needed.
    - The corpus holds the latest 10-K and 10-Q only (DS7).
    - Porter stemming widens matches (S47).
    - EFTS takes one phrase per query and no NEAR (D-M02-17, S97).
    - **Watchlist EFTS counts** (10-K/10-Q, plus 20-F/6-K for GFS, 2001 to 2026-10-12; S-new-r4-5). The queries cover 16 CIKs: the 15 operating names and Marvell's pre-2021 CIK 1058057, which holds MRVL's older history. They return 11 documents for "substantial doubt", 12 for "forbearance" and 130 for "not in compliance". NVIDIA alone has 68 for "not in compliance", mostly unrelated to covenants.
    - Some hits are exhibits: Micron's 2012–13 EX-99.1 and Tesla's FY2016 EX-99.1.
    - Rivian has 0 hits for all three phrases since 2021.
14. **Capex is the lever, and total capex moves the runway** (S-new-r4-4).
    - Intel's gross capex fell from 23,944 (FY2024) to 14,646 (FY2025), −39%. Micron's fell 36% in FY2023 (Round 1).
    - On total capex, two watchlist names with positive OCF sit near the warn band today: AMZN at 9.1 quarters and SPCX at 8.0.
    - Maintenance capex (A2) is not built, so for now the gate can use only total capex.

### Worked example — Rivian Q2 2026 (not on the watchlist; R11 case; S-new-47, S-new-r4-4; $M)
| Row | Value |
|---|---|
| Current assets / current liabilities (2026-06-30) | 7,618 / 3,620 |
| Total assets / total liabilities | 15,140 / 10,013 |
| Accumulated deficit / equity | (28,200) / 5,127 |
| Cash + short-term investments / total liquidity including ABL | 5,310 / 5,846 (ABL 536, derived) |
| Undrawn-credit tags (`LineOfCreditFacilityRemaining…`, `…MaximumBorrowingCapacity`) | 404, not tagged (companyconcept, 2026-10-12) |
| Pro forma after the July 2026 follow-on (about 1,317 net) | 7,163 |
| TTM loss from operations / OCF / capex / FCF | −3,533 / −1,845 / −1,644 / −3,489 |
| TTM net income / prior-year TTM | −3,233 / −3,506 (companyconcept) |
| FCF Q1 2026 / Q2 2026 | −1,075 / −849 |

- **Z″** (operating income as the EBIT proxy):
  - X1 0.264, X2 −1.863, X3 −0.233, X4 0.512.
  - Z″ = 1.732 − 6.072 − 1.568 + 0.538 = **−5.37**: distress under the 1.10 cut-off.
  - Without the X2 term it is 0.70, still below 1.10.
  - With the +3.25 constant it is −2.12 against Altman's 4.35 distress line. That is below the 2013 median of 94 Chapter 11 filers (0.05; S-new-r4-1), while Rivian holds 5.3B of cash.
- **O-score** (Model 1; OCF as the FUTL proxy; index 706 for 2025):
  - SIZE 16.88. O = −3.44, so P = 0.031, just below the 0.038 cut-off.
  - SIZE alone contributes −6.87.
  - With total assets entered in $ millions, P becomes 0.90 (the unit trap in research item 3).
- **Runway (quarters):**

| Burn definition | Burn per quarter | Cash only | + ABL | Pro forma |
|---|---|---|---|---|
| FCF TTM ÷ 4 | 872 | 6.1 | 6.7 | 8.2 |
| FCF, last-2-quarter average | 962 | **5.5** | 6.1 | 7.5 |
| OCF TTM ÷ 4 | 461 | 11.5 | 12.7 | 15.5 |

- **Reading.**
  - The score says distress; the facts say borderline.
  - Under 4.1a and 4.2a the gate fails at 5.5 quarters on cash only, because the ABL is untagged. It passes with a warning at 6.1 once a text-found ABL figure is confirmed (S4.2).
  - On today's burn, the Q3 2026 10-Q, which will include the July raise, would read about 7.5 quarters.
  - Under the approved profile, Z″ keeps the gate failed regardless of cash (question 4.1).
  - The DOE loan and the Volkswagen funds are conditional, so they are a note, not liquidity.
  - EFTS confirms no going-concern or covenant language in Rivian's 10-K or 10-Q filings since 2021 (research item 13).
  - Maturities are unread, because RIVN is not in `fact`.

**Invitae under the recommended runway rule (4.2a), with Z″ and O** (S02, S-new-r4-4; companyfacts first-filed values from 10-K and 10-Q only; $M). Liquidity = cash + current available-for-sale securities, with restricted cash (about 10) excluded.

| As of (filed) | Liquidity | Burn/q: TTM ÷ 4 / last-2 | 4.2a runway → state | TTM ÷ 4 only | Z″ (TTM OI) | O-score P | Going-concern text in the filing |
|---|---|---|---|---|---|---|---|
| FY2020 (2021-02-26) | 354.0 | 80.3 / 93.9 | 3.8 → fail | 4.4 | −0.51 | — | none |
| Q2 2021 (2021-08-09), after the 2021 raises | 1,530.2 | 106.7 / 119.5 | 12.8 → pass | 14.3 | 1.78 | — | none |
| Q3 2021 (2021-11-09) | 1,242.1 | 135.5 / 161.7 | 7.7 → warn | 9.2 | 1.58 | — | none |
| FY2021 (2022-03-01) | 1,045.4 | 153.6 / 187.8 | **5.6 → fail** | 6.8 (pass) | 1.31 (grey) | 0.008 | none |
| Q1 2022 (2022-05-03) | 874.7 | 171.7 / 181.7 | 4.8 → fail | 5.1 | 0.74 (distress) | — | none |
| FY2022 (2023-02-28) | 547.1 | 136.6 / 113.5 | 4.0 → fail | 4.0 | −16.76 | 0.944 | none |
| Q2 2023 (2023-08-08) | 325.1 | 79.8 / 46.0 | 4.1 → fail | 4.1 | −13.49 | — | evaluation described, no doubt concluded; boilerplate |
| Q3 2023 (2023-11-08) | 254.6 | 62.0 / 62.6 | 4.1 → fail | 4.1 | −54.14 | — | management: substantial doubt exists |

- **Afterwards:** an 8-K with Items 1.03 and 2.04 on 2024-02-14 (S-new-r4-6). No FY2023 10-K was filed.
- **Z″ caveat:** from Q2 2022 on, Z″ includes the 2022 goodwill and asset impairments (2,318 in Q2 2022).
- **Lead time before the 8-K Item 1.03, by signal:**
  - 4.2a: continuous fail from the FY2021 10-K, 715 days ahead.
  - TTM ÷ 4 alone (the draft's measure): first fail at Q1 2022, 652 days ahead.
  - Z″ < 1.10: from Q1 2022.
  - O > 0.038: by the FY2022 10-K, 351 days ahead.
  - Going-concern "exists": 98 days ahead.
- **The gate tracks financing.** It failed at FY2020, passed after the 2021 raises and failed again from FY2021 on.
- **Company-stated burn** (S-new-48; release liquidity includes restricted cash): FY2021 849.2 → 5.0 quarters on 1,060; FY2022 509.6 → 4.4. FY2023 guidance of 250–275 → 8.5 quarters, which would pass. That is why guidance never feeds the gate.

**Boeing maturity wall (question 4.3)** (S-new-r4-4; $M). Next-12-month debt = `DebtCurrent` (never plus `CommercialPaper`); at a 10-K, the larger of that and the year-1 tag.

| As of (filed) | Liquidity | Burn/q (4.2a) | Runway | 12-month debt | 4.3a: debt + 4 × burn | 4.3a | 4.3b: debt > liquidity |
|---|---|---|---|---|---|---|---|
| 2019-12-31 (2020-01-31) | 10,030 | 2,778 | 3.6 fail | 7,340 (CP 6,109 inside; the naive sum is 13,449) | 18,450 | fail | pass (fail if CP is double counted) |
| 2022-06-30 (2022-07-27) | 11,448 | 1,874 | 6.1 warn | 5,406 | 12,900 | **fail** | pass |
| 2022-09-30 (2022-10-26) | 14,257 | 87 | 164 pass | 5,431 | 5,778 | pass | pass |
| 2024-06-30 (2024-07-31) | 12,621 | 4,128 | 3.1 fail | 4,765 | 21,277 | fail | pass |
| 2024-12-31 (2025-02-03) | 26,282 | 3,578 | 7.3 warn | 1,278 (scheduled: 1,173 in 2025, 8,022 in 2026) | 15,588 | pass | pass |
| 2025-03-31 (2025-04-23) | 23,674 | 3,194 | 7.4 warn | 7,930 (roll-down, within 9,195 scheduled) | 20,706 | pass | pass |
| 2026-06-30 (2026-07-28) | 20,022 | 412 | 48.7 pass | 4,565 | 6,211 | pass | pass |

- In seven years of Boeing data, Q2 2022 is the only point where 4.3a changes the verdict on its own (the runway only warns).
  - Its last-2 burn includes a one-quarter OCF of −3,216 (Q1 2022).
  - Boeing passed the next quarter.
  - Its revolvers are untagged.
- 24-month wall at FY2025: 8,351 + 4,403 = 12,754 against 29,400 + TTM OCF 1,065 = 30,465 → pass.
- **Intel, capex-funded case.** At FY2024 (filed 2025-01-31): liquidity 22,062; burn 3,914 (TTM ÷ 4); runway 5.6; OCF +8,288.
  - 4.3a: 3,750 + 15,656 = 19,406 → pass.
  - At 2025-06-28: 7.2 quarters. `DebtCurrent` is 6,731 with commercial paper of 2,000 inside it.
  - From 2025-09-27: 14.7 quarters, then self-funding.

**Watchlist gate today under the recommended options** (companyfacts fetched 2026-10-12; S-new-r4-4; $M)

| Names | Data as of | Burn tier (4.2a) | Runway | Undrawn credit tagged | 12-month debt source | Verdict |
|---|---|---|---|---|---|---|
| AAPL, MSFT, GOOG, META, NVDA, MU, MRVL, TSLA, INTC | latest 10-Q/10-K, 2026 | self-funding (FCF ≥ 0, TTM and last 2) | — | no | year-1 tag or `DebtCurrent` (NVDA has no year-1 tag) | pass |
| BA | 2026-06-30 | capex-funded (TTM OCF 3,639) | 48.7 | no | `DebtCurrent` 4,565 | pass |
| AMZN | 2026-06-30 | capex-funded (capex tag = fallback) | 9.1 (122,988 ÷ 13,496) | no | `LongTermDebtCurrent` 3,330 + short-term borrowings 325 | pass |
| SPCX | 2026-06-30, one 10-Q | capex-funded, short history (H1 ÷ 2) | 7.997 (100,009 ÷ 12,505) | no | year-1 2,402; current 2,525 | pass with warning |
| GFS | 2025-12-31 (20-F; its 2026 6-Ks carry no XBRL facts) | self-funding (OCF 1,731, capex 722) | — | yes, IFRS 1,116 | no maturity or current-debt tags found | pass, labelled "as of last 20-F" |
| MSTR | 2026-06-30 | model tag → liquidity-only gate (3.4a) | 374 | no | year-1 40; year-2 4,510 | pass; 24-month wall 4,550 vs 2,448 shown |
| INFQ | 2026-06-30 | capex untagged → OCF-only | 93.6 (477 ÷ 5.1) | no | no debt tags | pass; tag-mapping item |
| ETV | — | fund (N-CSR) | — | — | — | not applicable |

- None of the 15 operating names is "incomplete" under the S4.1 input split. If undrawn credit were a required input, 14 of 15 would be incomplete.

**Negative equity: buybacks vs losses (S4.8)** (S-new-r4-4; $M)

| Company, date | Equity | Retained earnings | Treasury stock | Operating result | Reading |
|---|---|---|---|---|---|
| McDonald's FY2025 (10-K 2026-02-24) | −1,791 | +70,282 | 79,316 | OI +12,393; OCF +10,551 | buyback-funded → note |
| Boeing 2024-09-30 (10-Q 2024-10-23) | −23,552 | **+19,299** | 48,564 (AOCI −10,273) | 9-month operating loss −6,937 | operating loss → warning |
| Boeing 2025-12-31 (10-K 2026-01-30) | +5,454 | +17,252 | 28,029 | — | positive again after the late-2024 equity raise |
| Invitae 2023-03-31 | −36.7 | −5,021 | — | losses | warning (the gate already fails) |

- A retained-earnings sign test alone would call Boeing's 2024 deficit "buyback-driven". The operating-result test catches it.

**Going-concern and covenant classes on real filings (question 4.4)** (S-new-r4-5, S-new-r4-6). Key words are the matched terms; full sentences and offsets become fixtures at build (D-SRCH-19).

| Class (engine label) | Real filing | Matched words | Gate under 4.4a | What followed |
|---|---|---|---|---|
| auditor_gc | Fisker FY2023 10-K, filed 2024-04-23. The auditor's report (PwC) has a paragraph headed on substantial doubt, citing a missed March 2024 interest payment. | `raises substantial doubt` under a going-concern heading | fail | 8-K Items 1.03 and 2.04 on 2024-06-24 (62 days) |
| management_exists | Invitae Q3 2023 10-Q (2023-11-08), Note 1 | `substantial doubt exists` | fail | 8-K Items 1.03 and 2.04 on 2024-02-14 (98 days) |
| management_exists, in risk factors | Fisker FY2023 10-K risk-factor summary, in the present tense | `There is substantial doubt` | fail; tense decides, not section | as above |
| alleviated (auditor CAM) | Microvast FY2025 10-K (2026-03-16). Plans are judged probable to alleviate the doubt; the auditor treats it as a critical audit matter with no going-concern paragraph. | `alleviate substantial doubt` | warning + review | still filing |
| hypothetical | Riot Platforms FY2025 10-K (2026-03-02) | exact phrase "could raise substantial doubt about our ability to continue as a going concern" | review only if runway < 8 quarters | — |
| negated (evaluation only) | Invitae Q2 2023 10-Q (2023-08-08). The note describes the required evaluation and states resources for the next 12 months. | `evaluate whether there is substantial doubt` | none (note) | "exists" one quarter later |
| boilerplate | Invitae Q2 and Q3 2023 10-Qs | going-concern basis wording | none | — |
| ifrs_material_uncertainty | IAS 1.25 / IAS 8.6K wording; GFS has 0 EFTS hits | `material uncertainty` … `significant doubt` | as management_exists | — |
| breach_unwaived | Proterra FY2022 10-K (2023-03-17). In covenant default under its senior credit facility; waivers obtained only on its convertible notes. | `covenant default` | fail | 8-K Items 1.03 and 2.04 on 2023-08-08 (144 days) |
| forbearance | Fisker FY2023 10-K: a forbearance agreement expiring 2024-05-01 | `forbearance agreement` | fail | 8-K Items 1.03 and 2.04 on 2024-06-24 |
| breach_waived | Universal Technical Institute Q3 FY2025 10-Q (2025-08-07). Quick ratio 0.62 against 0.65 required; waiver obtained; its other covenants were met. | `obtained a waiver` | warning + review | — |
| reset | Albemarle Second Amendment to its credit agreement (2024-10-31; EX-10.1 to its Q3 2024 10-Q). Covenant relief runs to the Q2 2026 compliance certificate: maximum leverage 5.75× at 2025-06-30, minimum interest cover 1.00×, buybacks barred. | `Covenant Relief Period` | warning + review | — |
| compliant | Same UTI note (term loan, fixed-charge coverage and leverage met) | `in compliance` | baseline | — |
| acceleration (8-K 2.04) | Invitae 2024-02-14; Proterra 2023-08-08; Fisker 2024-06-24 | item code | fail | Item 1.03 in the same 8-K |

- Every "fail" text case came 2–5 months before Chapter 11. The runway rule carries the long lead time.
- 20 of the 25 hits on the first EFTS page for "substantial doubt has been alleviated" (2022–25) are SPAC 10-Qs.

### All cases
1. Healthy mature company → pass.
2. Young firm with a deficit, operating loss and years of cash (Rivian) → score distress; gate decided by runway.
3. Self-funding (burn ≤ 0) → "self-funding", never ∞.
4. One-quarter burn spike from a year-to-date-derived working-capital swing (Boeing Q1 2022 OCF −3,216).
5. Runway near the threshold, flipping by definition (Rivian 5.5 vs 6.1; SPCX 7.997 vs the 8-quarter warn line).
6. Guided burn lower than trailing (Invitae 8.5 vs 4.1).
7. Revolver tagged (GFS, IFRS) / untagged (every other watchlist name; Rivian) / borrowing-base limited; conditional facilities (DOE).
8. Restricted cash.
9. Pro forma raise after period end.
10. Maturity wall within 12 months; convertible with a holder put; commercial paper inside `DebtCurrent` (Boeing FY2019, Intel 2025); missing extension buckets; between 10-Ks.
11. Going-concern sentence: auditor paragraph / management "exists" (in notes or stated in risk factors) / alleviated / auditor critical audit matter without a paragraph / hypothetical risk factor / negated or evaluation only / "going concern basis" boilerplate.
12. No going-concern language, then bankruptcy (about half of cases).
13. Covenant: compliant / breach waived / breach unwaived / forbearance / reset amendment / cross default / acceleration (2.04).
14. 8-K 1.03 bankruptcy; 3.01 delisting notice.
15. Bank, fund (ETV N-CSR), crypto treasury (MSTR assets swing with bitcoin).
16. Equity below zero: from buybacks (McDonald's) or from losses with positive retained earnings (Boeing 2024).
17. Not on the watchlist (no facts).
18. Filing overdue (S1.6's state) → gate "incomplete".
19. Missing required inputs → gate "incomplete", never pass.
20. Capex-funded burn: OCF positive, FCF negative (AMZN 9.1, SPCX 8.0, Intel FY2024 5.6).
21. Seasonal working capital (Amazon's Q1 OCF is its weakest quarter).
22. Short history: fewer than 4 quarters of periodic data (SPCX has one 10-Q; S-1 data is not in companyfacts).
23. Capex tag missing (INFQ).
24. Scheduled roll-down of maturities vs covenant-driven reclassification to current (Boeing 1,278 → 7,930 is roll-down).
25. 24-month wall above liquidity for a model-tagged name (MSTR: 4,550 vs 2,448, bitcoin not counted).
26. Foreign filer: 20-F/6-K, `ifrs-full` tags, IFRS wording, no item codes, 6-K XBRL that stops (GFS).
27. Text in a pre-merger SPAC filing under the same CIK (INFQ's FY2025 10-K carries the SPAC's statements and has one hit); history under a predecessor CIK (MRVL before 2021).
28. EFTS hits in exhibits (MU EX-99.1, TSLA FY2016 EX-99.1) and unrelated "not in compliance" uses (NVDA, 68).

Complete for the gate as designed. Known omissions:
- covenant terms in credit agreements that were never filed;
- headroom figures, which are rarely disclosed;
- purchase commitments and lease obligations beyond debt maturities;
- parent or subsidiary guarantees;
- cash trapped abroad;
- crypto holdings as liquidity (only model-tagged names are handled, and only by exclusion).

### Suggestions
- **S4.1 Facts first.** The gate fails on any of:
  - going concern "exists" (auditor paragraph, or management's conclusion in any section);
  - unwaived breach, forbearance, 8-K 2.04, or a covenant-driven reclassification to current (text, per S4.3);
  - 8-K 1.03 or 3.01;
  - runway below threshold for a cash-burning company (S4.2);
  - the maturity test (S4.3).

  Further rules:
  - **Three values.** The `survival_gate` signal gains a third value, "incomplete", for missing required inputs.
  - **Required inputs** (missing → incomplete):
    - cash at the latest balance-sheet date (any mapped cash tag, IFRS included);
    - OCF for at least the last two quarters;
    - a latest periodic filing that is not overdue (S1.6);
    - for text triggers, the latest 10-K and 10-Q (or 20-F and 6-K) in the corpus.
  - **Substitutable inputs** (missing → method changes and is labelled):
    - capex: missing → OCF-only runway, plus an operational tag item (INFQ);
    - TTM: fewer than 4 quarters → the last-2 average only, labelled "short history" (SPCX). One quarter only → incomplete.
  - **Optional inputs** (missing → left out; they can only shorten the runway or mark a test "partial"):
    - short-term investments;
    - undrawn credit (S4.2);
    - maturity buckets;
    - restricted cash, which is excluded anyway.
  - **Today's effect:** 0 of the 15 operating watchlist names are incomplete under this split (worked example).
  - **Not applicable:** FF12 group 11 and funds (ETV) get no gate, shown as "not applicable: fund/financial" with the reason (D10). Model-tagged names (MSTR) get a liquidity-only gate (3.4a).
  - The absence of an opinion is never a pass (AS 2415).
  - Scores become a `distress_score` warning, with the stage flag from `lifecycle_stage` (question 4.1).
  - **Encoding in `signal`:**
    - value 1 = pass, 0 = fail, NULL = incomplete;
    - `method` lists the trigger or the missing inputs;
    - rows are written for MY, PT and ST, as approved;
    - evidence grade A for filing-based inputs.
- **S4.2 Runway** (question 4.2).
  - **Liquidity** = cash + short-term investments (restricted cash excluded) + confirmed undrawn committed credit, from one of:
    - a tag: `LineOfCreditFacilityRemainingBorrowingCapacity`, or IFRS `UndrawnBorrowingFacilities`, non-dimensional;
    - a text finder: FTS5 phrases ("available for borrowing", "remaining borrowing capacity", "undrawn", "availability under") NEAR "credit facility", "revolving" or "ABL" in the latest 10-K or 10-Q. Code extracts the amount and date from the verified sentence (D-SRCH-19), and the owner confirms it (`m04_credit_line`);
    - an owner entry with a source note.
  - **Credit rules:**
    - Only stated availability counts, never facility size.
    - A confirmed value expires at the next 10-Q or 10-K and is found again.
    - Until confirmed, credit is excluded and the runway is shown both ways (Rivian 5.5 / 6.1).
    - Conditional facilities appear as a note.
  - **Burn** = −(OCF − total capex), the worse of TTM ÷ 4 and the last-2-quarter average. Total capex uses all mapped capex tags, with fallbacks labelled. When A2 maintenance capex exists, its runway is shown as information.
  - **Tiers:**
    - Cash-burning operations (TTM or last-2 OCF < 0): fail below 6 quarters (the D-M04-1 value); warn below 8 (starting value, unsourced).
    - Capex-funded (OCF ≥ 0 on both, FCF < 0): no fail. Warning below 8 and review below 6 (starting values, unsourced; motivated by the Intel and Micron capex cuts in research item 14).
    - Self-funding: FCF ≥ 0 on both measures.
  - **Also shown:**
    - the OCF-only runway;
    - the runway net of next-12-month maturities;
    - a pro forma raise, as a note.
  - Trailing only, never guidance.
  - Old engine's integrity gate kept: the verdict is withheld when inputs are inconsistent, e.g. a derived quarter crossing a restatement.
- **S4.3 Maturity wall** (question 4.3).
  - **Next-12-month debt:**
    - At a 10-Q: `DebtCurrent`, or, if it is absent, `LongTermDebtCurrent` + `ShortTermBorrowings`.
    - `CommercialPaper` is shown but never added, because both definitions can contain it (Boeing FY2019).
    - At a 10-K: the larger of that figure and the year-1 tag.
  - A 24-month wall (years 1 + 2) is shown against liquidity + max(0, TTM OCF).
  - **Roll-down screen.** Current debt at a 10-Q is expected to stay at or below the last 10-K's year-1 + year-2 buckets plus tagged commercial paper or short-term borrowings.
    - Above that → `m04_current_jump` review plus a text search for a covenant-driven reclassification (ASC 470-10-45-11).
    - Only the text fails the gate.
    - Boeing 2025-03-31 (7,930 ≤ 9,195) and Intel 2025-06-28 (6,731 ≤ 6,250 + 2,000) are roll-down.
  - "Maturities partial" when buckets are missing.
  - Convertibles are counted at the earliest holder put, read from text where tags lack it.
- **S4.4 Score family** (`distress_score`, question 4.1).
  - Z for SIC 2000–3999 (S110), cut-off 1.81 (S-new-36).
  - Z″ for other non-financials:
    - stored without the constant against 1.10 / 2.60 (equal to Altman's 4.35 / 5.85 with it, S-new-r4-1);
    - the bond-rating-equivalent row from slide 28 shown as context.
  - Z shown with and without X4. Formula version stored on every value.
  - **O-score** (Model 1), now verified, built as information:
    - total assets in dollars;
    - the FRED GNPDEF index rebased to 1968 = 100, taken for the prior year;
    - OCF labelled as the FUTL proxy;
    - P shown beside the 0.038 reference and the paper's error rates.
    - Unit test: Rivian P 0.031, and 0.90 with assets in $ millions.
  - Skip FF12 group 11 and N-CSR filers.
  - CHS-12m as information only (no RSIZE; SPY as a labelled market proxy).
- **S4.5 Going-concern finder (local FTS5).**
  - **Queries:**
    - `NEAR("substantial doubt" "going concern", 25)`;
    - `"continue as a going concern"`;
    - for IFRS: `NEAR("material uncertainty" "going concern", 25)` and `"significant doubt"`.
  - **Sections:** 10-K Item 8, 10-K Item 7, 10-K risk factors, 10-Q Part I Items 1–2, and the 20-F financial statements. Exhibits are labelled and never fail the gate on their own.
  - **Classifier.** A raw-text sentence classifier labels each hit:
    - labels: `auditor_gc` / `management_exists` / `alleviated` / `auditor_cam` / `hypothetical` / `negated` / `boilerplate` / `ifrs_material_uncertainty` / `spac_pre_merger`;
    - tense and modality decide, not the section (Fisker's present-tense risk factor counts as "exists");
    - `auditor_gc` needs a going-concern paragraph heading in the auditor's report; a mention inside a critical audit matter alone is `auditor_cam` (Microvast);
    - hits in filings dated before a de-SPAC close (8-K 2.01) are `spac_pre_merger` and ignored (INFQ).
  - The quote and offsets are stored (D-SRCH-19).
- **S4.6 Covenant finder.**
  - **Phrases:**
    - `"not in compliance"`, `"covenant default"`, `"obtained a waiver"`, `NEAR(waiv* covenant, 10)`;
    - `forbearance`, "event of default" near occurred or continuing, `"cross default"`;
    - `NEAR(amend* "financial covenant", 10)`, `"covenant relief"`;
    - `NEAR("classified as current" covenant OR default OR waiver OR demand, 15)`.
  - The baseline `"in compliance with all"` is recorded, so silence is distinguishable from compliance.
  - Classes: breach_unwaived / breach_waived / forbearance / reset / reclass_covenant / acceleration (2.04) / compliant / silent.
- **S4.7 History via EFTS** (question 4.4).
  - One phrase per query ("substantial doubt", "forbearance", "not in compliance"), on 10-K and 10-Q (plus 20-F and 6-K for GFS) since 2001, filtered by CIK. MRVL's predecessor CIK 1058057 is included.
  - Hits are fetched and run through the same classifiers.
  - **Size today:** 48 queries return 153 documents (11 + 12 + 130). With every hit fetched, that is about 200 requests: about 40 seconds at the client's 5 per second, plus download time, so a few minutes (S-new-r4-5).
  - A first-scan baseline is recorded before any alert (D-M02-58). History hits are shown on the company page and never queued. Only hits in each company's latest 10-K or 10-Q can create review items.
  - It is a one-off backfill owner-run through `scripts/run_survival.py --history` (S4.10).
- **S4.8 Review items (D8), following the D-M02-10 / D-M02-51 pattern.**
  - Equity below zero is a warning only with an accumulated deficit, a TTM operating loss or a negative TTM OCF. Buyback-funded negative equity is a note (McDonald's vs Boeing 2024).
  - Kinds, with expected volume on the 16-name watchlist (about 60 10-K/10-Q filings a year, about 1.2 a week):

| Kind | Trigger | Expected volume | Priority | Cap |
|---|---|---|---|---|
| `m04_gate_fail` | gate turns fail, or a fail-class text is found | 0 today; rare | 1 | uncapped (alert) |
| `m04_gc_text` | alleviated / auditor_cam / IFRS uncertainty; hypothetical only when runway < 8 quarters or the capex-funded warning is on | history: 11 documents in 25 years; going forward under 1 a quarter | 2 | M04 weekly cap |
| `m04_covenant` | breach_waived, reset, `m04_current_jump` | under 1 a month after classification | 2 | M04 weekly cap |
| `m04_score_gap` | `distress_score` in distress while the gate passes | first run 0–1. Of the deficit names, SPCX Z″ 4.1 (annualized H1) and INFQ 10.8 read safe; GFS's book Z″ of 1.87 is grey; MSTR is model-tagged. | 3 | M04 weekly cap |
| `m04_credit_line` | text-found undrawn credit to confirm; only for names with runway < 12 quarters or the capex-funded warning | first run about 2 (SPCX, AMZN); then per 10-Q for those names | operational | uncapped |
| `m04_gate_input` | tag to map (capex untagged) | first run 1 (INFQ) | operational | uncapped |

  - M04 weekly cap: 5 judgment items (starting value, unsourced). Overflow is shown on the M04 tab and flushed by priority, oldest first.
- **S4.9 Regression cases and survival set:**
  - Rivian Q2 2026 (fixture): score distress; cash-only fail 5.5; 6.1 with confirmed ABL.
  - Invitae quarterly 2021–23: fail from the FY2021 10-K (715 days ahead of the 8-K 1.03).
  - Boeing:
    - FY2019: CP double count → 4.3b must pass;
    - Q2 2022: 4.3a fails while the runway warns;
    - Q2 2024: runway fail;
    - 2025-03-31: roll-down, not a reclassification;
    - 2024-09-30: negative equity warning.
  - Intel FY2024: capex-funded warning. AMZN Q2 2026: pass at 9.1. SPCX Q2 2026: short-history warning. McDonald's FY2025: negative-equity note.
  - Text fixtures: Fisker, Invitae Q2 and Q3 2023, Proterra, Microvast, Riot, UTI and the Albemarle amendment.
  - A mature non-manufacturer: pass.
  - Each quarter, report the watchlist count of score-distress vs gate-fail.
  - **Calibration.** The 6-quarter fail is the approved D-M04-1 value. The 8-quarter warn band, the capex-funded tier, 4.3a and the classifier rules are starting values. They are checked in Part 8 against this labelled survival set:
    - failures, with 8-K 1.03 dates: Invitae 2024-02-14, Fisker 2024-06-24, Proterra 2023-08-08;
    - survivors: Boeing 2019–25, Intel 2024–25, Rivian, AMZN, SPCX.
  - `distress_score` stays information-only until that set exists.
- **S4.10 Part 4 build notes.**
  - **Script:** `scripts/run_survival.py`:
    - `--history`: the EFTS pass; resumable, with a dry-run estimate;
    - `--fixtures`: the owner capture.
    - Like every SEC-calling script, it takes `refresh.lock`.
  - **Refresh:** the logon refresh adds no SEC requests. Facts and 10-K/10-Q text are already fetched, and the classifiers run locally after the refresh, inside the 3-hour task (D-M02-12).
  - **Live check:** the EFTS pass (about 200 requests) plus fixtures, about 45 requests:
    - Invitae and Rivian companyconcept tags (about 14 each);
    - McDonald's equity tags (6);
    - submissions for Invitae, Fisker and Proterra (3);
    - the 8 text-fixture documents.
    - Total: about 245 requests, a few minutes.
  - **Fixture size:** companyconcept per tag, not whole companyfacts files, keeps `tests/fixtures/` small.
  - **Docs in the same commit:**
    - M04_FINANCIALS.md;
    - M00_STORAGE.md: new tables `m04_text_hit` (class, quote, offsets) and `m04_credit_line` (amount, as-of, source, confirmed);
    - M00_SEC_DATA.md: EFTS history pass and the predecessor-CIK map;
    - M00_UI.md: the gate panel with its reasons;
    - DATA_SOURCES.md: FRED GNPDEF.
  - A mock-up with real data comes before the gate panel is built (D-UI-4).
- **S4.11 Signals out (this round).** PT and ST profiles come later (M01); "info" = shown, no weight.

| Signal | Type | Meaning | MY | PT | ST |
|---|---|---|---|---|---|
| survival_gate | pass / fail / incomplete (1 / 0 / NULL) | Gate verdict; `method` names the trigger or the missing inputs | ✓ | ✓ | ✓ |
| runway_q | float or "self-funding"; tier | Quarters of liquidity at the 4.2 burn | ✓ | ✓ | info |
| maturity_wall | ratio | (12-month debt + 4 × burn) ÷ liquidity; 24-month wall shown | ✓ | ✓ | info |
| distress_score | float + variant (Z, Z″, O) | Accounting score; warning only (4.1a) | ✓ | ✓ | info |
| gc_language | enum (S4.5 labels) | Latest going-concern class, with quote | ✓ | ✓ | ✓ |
| covenant_status | enum (S4.6 classes) | Latest covenant class, with quote | ✓ | ✓ | ✓ |

- **S4.12 Changes to the approved profile (D-M04-1) from this round.**

| Approved text | Change if the recommended options pass | Question |
|---|---|---|
| "Altman Z in the distress zone … → no adds" | Z, Z″ and O leave the gate and become a `distress_score` warning | 4.1a |
| "runway (cash + undrawn credit ÷ quarterly burn) < 6 quarters" | Liquidity adds short-term investments, excludes restricted cash and counts only confirmed undrawn credit. Burn = total-capex FCF, worse of TTM ÷ 4 and last 2. Fail < 6 unchanged; new warn band < 8. Capex-funded companies warn, never fail. | 4.2a |
| "next-12-month debt maturities > liquidity" | Next-12-month debt + 4 × burn > liquidity; `DebtCurrent` without commercial paper on top; 24-month wall shown | 4.3a |
| (none) | New fail triggers: going concern "exists", unwaived breach, forbearance, 8-K 2.04, covenant-driven reclassification, 8-K 1.03 and 3.01 | 4.4a |
| survival_gate "pass/fail" | Adds "incomplete" with the required-input split | S4.1 |
| "not for financials" (Z only) | Whole gate not applicable for FF12 group 11 and funds; model-tagged names get a liquidity-only gate | S4.1, 3.4a |
| Failure-mode row "Altman Z … pair with runway" | Replaced by the rows below | — |

  M01 rules 3 and 7 are not reworded, but their outcomes change (question 4.1).

### Failure modes (rows to add)
| Input | How it can mislead | Guard |
|---|---|---|
| Z / Z″ / O on young firms | Deficit and operating loss read "distress" while years of cash remain (Rivian Z″ −5.37 with 5.3B of cash) | Stage flag; warning only, never a gate fail on its own |
| Z cut-offs and variant | 1946–65 manufacturers; Type II error 15–20%; the +3.25 constant mixed with the 1.10 / 2.60 zones turns distress into "safe" (Altman's own zones with the constant are 4.35 / 5.85) | Variant, version and cut-off stored; 1.81; unit test on fixtures |
| Z X4 | Bubble prices inflate Z (1999 average near 10); crashes cut it just as M01 triggers | Show with and without X4 |
| O-score units | Assets in $ millions flip Rivian from P 0.031 to 0.90; an index of 1.0 instead of 100 shifts O by about 1.9 | Dollars and a 1968 = 100 index, both unit-tested; FUTL proxy labelled |
| CHS | CHS power at 12 months is about a third of next-month | Information only |
| Burn | One-quarter swings; YTD derivation; seasonal Q1 OCF (AMZN) | Two-period rule; trailing only; three definitions shown |
| Capex in the burn | Discretionary growth capex makes cash-rich firms look short (AMZN 9.1, SPCX 8.0, Intel FY2024 5.6) | Capex-funded tier warns, never fails; OCF-only runway shown |
| Short history | One 10-Q gives no TTM (SPCX) | Last-2 only, labelled; one quarter → incomplete |
| Revolver | Untagged at every watchlist name but GFS; Rivian flips 5.5 / 6.1 on the ABL; borrowing base or springing covenant cuts availability; conditional loans | Tag, verified text or owner entry, with expiry; stated availability only; conditional loans as a note |
| Current-debt tags | `DebtCurrent` already holds commercial paper (Boeing FY2019: 13,449 summed vs 7,340); roll-down looks like a reclassification (Boeing 1,278 → 7,930) | No commercial paper on top; roll-down screen; only text fails |
| Maturity tags | Annual schedule; missing extension buckets; holder puts vary | Larger of the year-1 tag and current debt; "partial" flag |
| Going-concern text | Hypotheticals, negations, alleviated cases, critical audit matters, boilerplate, SPAC-era and exhibit hits all match; stemming widens matches | Sentence classifier on raw text with tense and section rules; only "exists" fails |
| Going-concern as predictor | About half of bankruptcies had no opinion; about 90% of recipients do not file within a year; text came 62–144 days ahead in the fixtures | Gate input, never a forecast or a pass; runway carries the lead time |
| Covenant text | "In compliance" dominates; violations are common and often waived (UTI); "not in compliance" has unrelated uses (NVDA 68) | Unwaived, forbearance, 2.04 or covenant reclassification only |
| Negative equity | Buyback-funded deficits (McDonald's) look like distress; Boeing 2024 had positive retained earnings | Equity sign plus operating loss, OCF or accumulated deficit |
| Foreign filers | IFRS wording, no 8-K item codes, 6-K XBRL that stops (GFS) | IFRS phrases; "as of last 20-F" label |
| Financials, funds, crypto treasuries | Z is meaningless for banks and funds; MSTR's assets swing with bitcoin | FF12 group 11 and funds not applicable; model tag → liquidity facts only |
| Warn band and capex tier | 8 quarters and the tier are unsourced; SPCX (7.997) and AMZN (9.1) sit near the line | Labelled starting values; Part 8 survival set |

### Questions
**4.1 Role of distress scores, and how M01 reads the gate**
- (a) *Recommended.* Z, Z″ and O become a `distress_score` warning (stage-flagged), and the gate uses liquidity and legal facts. CHS-12m stays information.
  - M01 reading:
    - only `pass` (including the warn band) opens rule-3 tranche adds and rule-7 beyond-2σ strength;
    - `incomplete` blocks adds as a named data gap, not a warning;
    - `distress_score` and `financing_pressure` are shown and never block.
  - **Confirm:** this makes young firms add-eligible. Rivian (Z″ −5.37) passes once a confirmed runway reaches 6 quarters (6.1 with the ABL), so tranche adds can follow an M01 trigger whenever CvD allows.
  - Why: Type II error of 15–20%, and young firms read as distress by construction. On Invitae, the runway failed 2 months before Z″ and a year before O did.
  - Gets wrong: lets a firm with deep accounting distress but cash through (Rivian), and leans on runway inputs such as undrawn credit.
- (b) Scores block only rule 7's beyond-2σ strength; rule-3 adds are decided by facts.
  - Gets wrong: Rivian gets adds but never the stronger signal however much cash it holds, and the owner has two gates to read.
- (c) Score stays in the gate unless retained earnings < 0 and runway ≥ 6 quarters.
  - Gets wrong: a mature firm with positive retained earnings and a one-off loss still fails on a 1946–65 score. Boeing 2024 had positive retained earnings, so its result would hinge on the price-based manufacturer Z.
- (d) As now (score in the gate).
  - Gets wrong: Rivian fails for years whatever its cash. Invitae's FY2021 10-K passes (Z″ 1.31 grey, TTM ÷ 4 runway 6.8), so the first fail comes at Q1 2022.

**4.2 Runway rule**
- (a) *Recommended.* As in S4.2:
  - Burn = OCF − total capex, the worse of TTM ÷ 4 and the last-2-quarter average.
  - Cash-burning operations fail below 6 quarters and warn below 8 (starting value, unsourced).
  - Capex-funded companies (OCF ≥ 0, FCF < 0) warn below 8 and get a review below 6, but never fail.
  - Liquidity counts only confirmed undrawn credit.
  - Cases:
    - Invitae fails from the FY2021 10-K (5.6);
    - Rivian: 5.5 on cash only (fail), 6.1 with the confirmed ABL (pass with warning);
    - Boeing Q2 2024: 3.1 (fail);
    - Intel FY2024: 5.6, warning and review;
    - SPCX: 7.997 (warning);
    - AMZN: 9.1 (pass).
  - Why: it catches Invitae about two years ahead and reacts within two quarters, while capex, the lever Intel and Micron pulled, does not decide survival alone.
  - Gets wrong: a capex-funded firm with capex it cannot actually cut only warns.
- (b) Same window, but total-capex burn fails every company below 6.
  - Gets wrong: Intel fails at its FY2024 10-K although its operations made +8,288 of cash and it cut capex 39% the next year.
- (c) Worse of TTM ÷ 4 and the latest quarter.
  - Rivian: 6.1 cash-only (warn). Invitae FY2021: 5.4 (fail).
  - Gets wrong: one quarter decides. Boeing Q1 2022 fails at 3.4 on a single −3,216 OCF quarter; (a) gives 8.0 (just under 8, a warning).
- (d) OCF only, with the old engine's 12/24 months.
  - Gets wrong: Invitae's FY2022 10-K reads 13.3 months ("moderate") 50 weeks before Chapter 11, and the class flips between distressed and moderate through 2023.
- (e) Fail below 4 quarters (the ASC 205-40 horizon).
  - Gets wrong: Invitae passes at its FY2022 10-K (4.0) and in Q2–Q3 2023 (4.1).

**4.3 Maturity wall test**
- (a) *Recommended.* Next-12-month debt + 4 × quarterly burn > liquidity, with 4 quarters matching the ASC 205-40 year.
  - Next-12-month debt as in S4.3, with no commercial paper on top.
  - Capex-funded companies warn instead of failing.
  - Roll-down screen; 24-month wall shown.
  - Cases:
    - Boeing fails at FY2019, Q2 2022 and Q2 2024, and passes 2025–26;
    - Intel passes;
    - MSTR's 24-month wall is shown.
  - Why: a cash-burning company facing a wall fails earlier.
  - Gets wrong: Boeing Q2 2022 fails on one bad quarter (Q1 2022 OCF −3,216) with its revolvers untagged, and passes the next quarter.
- (b) Next-12-month maturities > liquidity (as now).
  - Gets wrong: misses Boeing Q2 2022 entirely. It fails Boeing FY2019 only if commercial paper is double counted (13,449 vs 10,030). Otherwise 7,340 passes, and only the runway (3.6) catches FY2019.

**4.4 Going-concern and covenant triggers, and history**
- (a) *Recommended.* The gate fails on:
  - an auditor paragraph (Fisker) or a management "exists" conclusion in any section (Invitae Q3 2023; Fisker's risk factors);
  - an unwaived breach (Proterra);
  - forbearance (Fisker);
  - an 8-K 2.04;
  - a covenant-driven reclassification read from text.

  Alleviated (Microvast), critical-audit-matter-only, waived (UTI) and reset (Albemarle) cases become a warning plus a review item. Hypothetical sentences (Riot) go to review only when runway < 8 quarters.

  History: one owner-run EFTS pass back to 2001 for the watchlist, about 200 requests and a few minutes, kept as a baseline.
  - Why: matches the AS 2415 wording, and violations alone are common (10–20% a year). UTI's waived quick-ratio breach is a trip wire at a healthy firm.
  - Gets wrong: text fails only 62–144 days ahead in these cases, so the runway carries the lead time. A reset at a weakening firm (Albemarle) stays a warning.
- (b) Any going-concern sentence or any breach fails the gate.
  - Gets wrong: Riot's hypothetical risk factor, Microvast's alleviated doubt, UTI's waived breach and Invitae's Q2 2023 boilerplate all fail. 20 of 25 sampled "alleviated" hits are SPAC 10-Qs.
- (c) As (a), without the EFTS history (latest filings only).
  - Gets wrong: no baseline to tell new language from repeats (over 70% of opinions are repeats), and no visible history. MSTR's 2001 and 2009 forbearance exhibits and MRVL's 2007 hits under its old CIK stay unseen.

---

### New sources added in this section
- **S-new-r4-1** Altman, E. I. (2017), "The Evolution & Applications of the Altman Z-Score Family of Models & Global Credit Markets Commentary", Global Finance Conference, Hofstra University, 5 May 2017 (slides 25, 27, 28: Z″ with the +3.25 constant; zones 4.35 / 5.85; US bond-rating equivalents) — https://www.hofstra.edu/pdf/community/bdc/breslin/breslin-evolution-of-altman-z-score.pdf
- **S-new-r4-2** Ohlson (1980) original, read 2026-10-12: Ohlson, J. A., "Financial Ratios and the Probabilistic Prediction of Bankruptcy", J. Accounting Research 18(1):109–131. JSTOR scan via an Internet Archive copy (pp. 115, 118–121, 126) — https://web.archive.org/web/2015id_/http://www.math.ryerson.ca/ramlab/projects/crd/ohlson1980.pdf ; FRED GNP implicit price deflator (GNPDEF, 2017 = 100) — https://fred.stlouisfed.org/series/GNPDEF
- **S-new-r4-3** IFRS Foundation (2025), "Going Concern—A focus on disclosure", educational material, revised May 2025 (IAS 1.25 moved unchanged to IAS 8.6K by IFRS 18, effective 2027) — https://www.ifrs.org/content/dam/ifrs/supporting-implementation/educational-materials/going-concern-2025.pdf
- **S-new-r4-4** SEC XBRL and submissions data checked 2026-10-12:
  - companyfacts for Invitae (CIK 1501134), McDonald's (63908) and the watchlist: BA 12927, INTC 50863, AAPL 320193, MU 723125, MSFT 789019, AMZN 1018724, NVDA 1045810, MSTR 1050446, TSLA 1318605, META 1326801, GOOG 1652044, GFS 1709048, MRVL 1835632, INFQ 2007825, SPCX 1181412;
  - Rivian (1874178) companyconcept for `NetIncomeLoss` and `NetCashProvidedByUsedInOperatingActivities`, and 404s for the two line-of-credit tags;
  - submissions for Invitae, Fisker (1720990) and Proterra (1820630), giving the 8-K 1.03 dates;
  - taxonomy element descriptions as carried in companyfacts (`DebtCurrent`, `LongTermDebtCurrent`, `CommercialPaper`, year-1 maturity, `LineOfCreditFacilityRemainingBorrowingCapacity`).
  - Patterns: https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json ; https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/<Tag>.json ; https://data.sec.gov/submissions/CIK##########.json
- **S-new-r4-5** EDGAR full-text search queries run 2026-10-12 (watchlist counts; phrase searches for class examples). Pattern: https://efts.sec.gov/LATEST/search-index?q=%22substantial%20doubt%22&forms=10-K,10-Q&dateRange=custom&startdt=2001-01-01&enddt=2026-10-12&ciks=0001501134 ; UI: https://www.sec.gov/edgar/search/
- **S-new-r4-6** Going-concern and covenant text examples:
  - Fisker FY2023 10-K (0001720990-24-000045) — https://www.sec.gov/Archives/edgar/data/1720990/000172099024000045/fsr-20231231.htm ; Fisker 8-K, Items 1.03 and 2.04 (0001193125-24-167032) — https://www.sec.gov/Archives/edgar/data/1720990/000119312524167032/
  - Invitae Q2 2023 10-Q — https://www.sec.gov/Archives/edgar/data/1501134/000150113423000068/nvta-20230630.htm ; Q3 2023 10-Q — https://www.sec.gov/Archives/edgar/data/1501134/000150113423000104/nvta-20230930.htm ; 8-K, Items 1.03 and 2.04 (0001501134-24-000016) — https://www.sec.gov/Archives/edgar/data/1501134/000150113424000016/
  - Microvast FY2025 10-K (0001628280-26-018264) — https://www.sec.gov/Archives/edgar/data/1760689/000162828026018264/mvst-20251231.htm
  - Riot Platforms FY2025 10-K (0001104659-26-022322) — https://www.sec.gov/Archives/edgar/data/1167419/000110465926022322/riot-20251231x10k.htm
  - Proterra FY2022 10-K (0001628280-23-008519) — https://www.sec.gov/Archives/edgar/data/1820630/000162828023008519/ptra-20221231.htm ; 8-K, Items 1.03 and 2.04 (0001628280-23-027865) — https://www.sec.gov/Archives/edgar/data/1820630/000162828023027865/
  - Universal Technical Institute Q3 FY2025 10-Q (0001261654-25-000019) — https://www.sec.gov/Archives/edgar/data/1261654/000126165425000019/uti-20250630.htm
  - Albemarle Second Amendment to Credit Agreement, EX-10.1 to the Q3 2024 10-Q (0000915913-24-000158) — https://www.sec.gov/Archives/edgar/data/915913/000091591324000158/exhibit1010930202410-q.htm
  - Infleqtion FY2025 10-K (pre-merger SPAC statements; 0001193125-26-134544) — https://www.sec.gov/Archives/edgar/data/2007825/000119312526134544/d94946d10k.htm

## Round 5 — Unit economics and margin collapse (stage-aware, R2)

**What this round covers.**
- Margin collapse while revenue rises (R12) and unit economics (R11). Invitae is the R12 regression case listed in M04_FINANCIALS.md, and Rivian is the R11 case. Both are worked below.
- The D-M04-1 customer signal ("by stickiness class and own history, weighted by revenue at stake"). No other round designs it, so it is folded in here: research items 16–19, the NVIDIA example, cases 31–40, S5.13 and question 5.5.
- **Question 5.1 (stage) is presented with Round 1.** Rounds 2–4 already route on `lifecycle_stage` (S2.3, S4.1, S4.9). Its research and worked example stay here. The owner model-tag vocabulary belongs with question 3.4, not here.

### What the research says
1. **Filings must state the cause** (S-new-49).
   - Reg S-K 303(b) requires the reasons behind material line-item changes, in quantitative and qualitative terms, including offsetting changes.
   - 303(b)(2)(iii) asks how far a revenue increase comes from price, volume or new products.
   - 303(b)(2)(ii) covers known events that change the relationship between costs and revenues.
   - Examples:
     - Tesla's FY2023 10-K says total automotive gross margin (28.5% → 19.4%) fell "primarily due to a lower average selling price" (S-new-50). Its FY2024 10-K gives 19.4% → 18.4%, attributed to lower selling prices and the Cybertruck ramp, partly offset by lower cost per unit and higher credit and FSD revenue (S-new-r5-5).
     - Target publishes a gross-margin waterfall in percentage points (S-new-51).
     - Rivian's Q4 2023 letter splits its "~$81k" per-vehicle gain into about 45% fixed cost, 40% variable cost and 15% revenue per unit (S-new-47).
     - Invitae's FY2022 10-K attributes a $68.6M rise in cost of revenue to volume. It attributes the rise in cost per unit to these items, which sum exactly to $68.6M (S-new-r5-4):
       - amortization of acquired intangibles, +$50.6M;
       - inventory and prepaid write-downs, +$18.2M, "principally related to the exit of certain product offerings and geographies";
       - shipping, +$6.4M;
       - lower lab materials, −$5.2M;
       - other, −$1.4M.
2. **Per-unit bridge.** Gross-profit change = volume effect + price effect + cost effect. The arithmetic is standard; no peer-reviewed definition was found. Tesla 2022→2023 reconciles exactly to the reported change (worked example).
3. **Falling gross margin predicts lower earnings.**
   - Lev & Thiagarajan and Abarbanell & Bushee both use a gross-margin signal: % change in sales − % change in gross margin. Their full texts were not opened, so the construction needs checking (S-new-52).
   - A UK extension found margin and cost signals the most informative, with effects that depend on the macro state and the industry (S-new-52).
4. **Inventory ahead of sales.**
   - For US retailers, abnormal inventory growth (measured against an operations benchmark) has an inverted-U relation to next-year EPS, and analysts do not fully price it (S-new-53).
   - Target: inventory rose 30.5% at January 2022 against +13.2% sales, and 43% year over year at April 2022. The FY2022 gross-margin rate then fell 4.7 pp (S-new-1, S-new-51).
5. **Operating leverage and sticky costs.**
   - SG&A rises 0.55% per 1% sales increase but falls only 0.35% per 1% decrease (S-new-54). Operating leverage: S-new-54.
   - So falling margins on falling revenue can be scale. Margins that collapse while revenue rises cannot be: the cause must be price, mix, input cost, a one-off, credits or under-absorption. That is R12's diagnostic logic.
   - The logic does not depend on stage. Invitae was "introduction" by cash-flow signs in every year from 2019 to 2022 (item 7), yet its margin fell while revenue rose. So R12 opens a cause review at any stage, and stage only changes which follow-up flags apply (S5.6).
6. **Reversion.**
   - Profitability reverts about 38% a year, faster below the mean (S-new-55).
   - Life-cycle grouping improves forecasts most in the introduction and decline stages (S-new-56, Vorst & Yohn).
   - Return on net operating assets does not revert across stages: a gap of about 7 pp between mature and decline firms remains after 5 years (S-new-56, Dickinson abstract).
   - Target's gross-margin rate went from 23.6% to 26.5% in FY2023: Sales $105,803M and cost of sales $77,736M in the FY2023 10-K (S-new-r5-3; replaces the trade-press citation).
7. **Stage from cash-flow signs** (Dickinson 2011, S-new-56), as (operating, investing, financing):

   | Stage | Signs |
   |---|---|
   | Introduction | (−, −, +) |
   | Growth | (+, −, +) |
   | Mature | (+, −, −) |
   | Shake-out | (−,−,−), (+,+,+) or (+,+,−) |
   | Decline | (−,+,+) or (−,+,−) |

   - Two secondary sources match this table:
     - Prędkiewicz & Machnik (2025) reproduce it in full, with stage labels, sourced to Dickinson (2011) (S-new-r5-1);
     - the Brazilian paper already cited lists the same eight patterns in the same order (S-new-56).
   - Dickinson's own table is still unread. The journal is paywalled, and SSRN refused the fetch (403). See the checklist below.
   - **Correction:** "62% of mature firms stayed mature and 30% moved back to growth" is the Brazilian paper's own sample (313 listed companies, 2005–12), not Dickinson's US data (S-new-56). The US filings in the worked example show the same kind of non-sequential moves:
     - Tesla: mature 2021–22, growth 2023–25.
     - Intel: mature 2018–21, growth 2022–25. Positive financing flows (debt and partner funding) produce the "growth" signs while revenue fell 33% from 2021 to 2024. Those flows are reported in the cash-flow statement, but their purpose was not checked.
8. **Young firms.**
   - Non-financial growth metrics were value-relevant where earnings were not (S-new-57, Amir & Lev).
   - Unit cost falls as a power of cumulative production; Wright's law forecast best across 62 technologies (S-new-57, Nagy et al.).
   - So the red flag is per-unit cost that does not fall as cumulative units grow. Invitae is a real case: cost per billable unit was $252 → $301 → $298 → $323 (2019–22) while units grew 2.75× (worked example).
9. **Negative gross margin.**
   - No peer-reviewed base rate was found.
   - Lordstown, Proterra, Fisker, Canoo and Nikola failed, but that list is outcome-selected (S-new-58).
   - The survival gate is the primary guard.
10. **Contribution margin is non-GAAP.**
    - C&DI 100.01 warns that excluding normal, recurring cash operating expenses can mislead. Aterian's 2021 letter moved its reconciliation to gross profit (S-new-59).
    - Design choice: show company-stated figures, labelled, and never compute them.
11. **KPI definition risk** (S-new-59, Release 33-10751 summary).
    - KPIs need definitions and disclosure of method changes, yet Rivian's per-vehicle gross profit is undefined.
    - Revenue scope often differs from the unit count:
      - Tesla's deliveries include leased cars, but leasing revenue is a separate line.
      - Regulatory credits have no units: Tesla $1,790M in 2023 and $2,763M in 2024 (S-new-r5-5); Rivian $299M in Q4 2024 and $325M for FY2024 (S-new-47).
      - Invitae states revenue per billable unit of $413 (2020) and $380 (2021). Total revenue ÷ units gives $424 and $394, 3–4% higher, so the stated figure uses a narrower revenue base. Its stated cost per unit ($299, $298) matches the computed one (S-new-r5-4).
    - Category labels change. Tesla's delivery releases say "Model S/X" in the 2022 release and "Other Models" in the 2023 and 2024 releases, the line that now includes Cybertruck (S-new-r5-5).
12. **Segments.**
    - ASU 2023-07 adds significant segment expenses, retrospectively (S-new-60).
    - Segment values sit on XBRL axes and are not in companyfacts (S41).
    - Warning case: a search engine called Rivian's automotive-segment cost (6,150 / 5,693) a "recast" of consolidated cost (6,464 / 6,170). Consolidated FY2022 gross profit is −3,123, unchanged in three 10-Ks (S-new-1).
13. **One-offs and credits inside gross profit:**
    - Intel 2024: $3.3B of impairment and accelerated depreciation plus $922M of Gaudi inventory charges (S-new-61). The Q3 2024 10-Q puts "$3.1 billion of charges, substantially all" in cost of sales (S-new-r5-7).
    - Rivian write-downs: $920M (2022) → $107M (2023).
    - Rivian Q4 2024: gross profit $170M against credits of $299M.
    - Rivian 2023: produced 57,232, delivered 50,122 (S-new-47).
14. **Data.**
    - Margin concepts are mapped, and Q4 is derived (Rivian has no discrete Q4 facts).
    - MD&A is split by section, with tables tab-separated (D-SRCH-12).
    - Unit counts are not in XBRL:
      - Tesla's delivery EX-99.1 is stored but not parsed (DS2);
      - Invitae's billable units appear only in 10-K MD&A text.
    - EX-99.2 is not fetched (`documents.py` `DEFAULT_EXTRA_TYPES`).
    - RIVN is not on the watchlist.
    - `instance.py` keeps non-dimensional contexts only. It stores facts, not the raw instance file, so widening it later means fetching each instance it has already read once more.
    - The `fact` unique key (`cik, taxonomy, tag, unit, period, accession`) has no dimension. Two segment members for the same tag and period would collide, so dimensional values need their own table (S5.7).
    - Gaps checked 2026-10-12 (S-new-r5-2):
      - Invitae has no `GrossProfit` tag (404).
      - NVIDIA's `ConcentrationRiskPercentage1` is absent from companyfacts (404); its customer percentages exist only on dimensional contexts.
      - Target's 10-Qs before Q3 2022 have no cost-of-sales fact in companyfacts under any mapped tag (`CostOfGoodsAndServicesSold`; `CostOfRevenue` and `CostOfGoodsSold` return 404). Their statements of operations show the line, under a "Sales" heading. The Q1 2022 value first reaches companyfacts on 2023-05-26 and the Q2 2022 value on 2023-08-25, as comparatives a year later. Target's 10-Ks are tagged normally.
    - `rpo` (`RevenueRemainingPerformanceObligation`) is already a mapped series (`xbrl_facts.py`).
15. **Gross margin is not defined the same way everywhere.**
    - Amazon (watchlist) has no gross-profit line. It says operating income is "more meaningful" because its product categories and services are so diverse. Its cost of sales covers product cost, shipping and digital content; fulfillment-center, store and customer-service costs are a separate line (S-new-22, FY2025 10-K).
    - Target states its rate on Sales, not on total revenue. FY2022: 23.6% on Sales against 24.6% on total revenue. FY2021: 28.3% against 29.3% (S-new-r5-3).
    - Invitae's cost of revenue includes amortization of acquired intangibles (S-new-r5-4). An acquisition therefore lowers its gross margin without any change in operations.
    - Suppliers with more concentrated customers report lower gross margins, but also lower SG&A and inventory (S-new-r5-10, summary). So a shift in customer mix is itself a margin cause.
16. **Customer disclosure rules.**
    - ASC 280 requires the amount of revenue from any single customer at 10% or more of revenue, but not the customer's name (S16).
    - Reg S-K adds the name only when losing the customer would be material (D-M02-35 note).
    - So customers are often anonymous. NVIDIA writes "one direct customer" (S-new-r5-8).
    - The 10% line is a disclosure rule, not a significance test (M04_FINANCIALS.md).
17. **What customer links predict.**
    - Customers' returns lead their suppliers' returns. Cohen & Frazzini built their links from these ≥10% disclosures (S44).
    - A supplier's returns are more sensitive to its major customers when it depends on them for a larger share of sales and its products are less unique (S45: Asgharian & Liu 2017, "Stock Return Dependence and Product Market Linkages"). That supports weighting by revenue at stake and by stickiness class, as D-M04-1 already approved.
    - Concentration is not bad in itself. Higher customer concentration went with better supplier performance overall: gross margins were lower, but SG&A and inventory were lower too (S-new-r5-10, Patatoukas 2012, via a summary). So the comparison is against the company's own history, not a universal threshold.
18. **RPO separates contracted names from the rest** (ASC 606, S16).
    - NVIDIA's RPO is $2.3B against $215.9B of FY2026 revenue (about 1%).
    - Microsoft's RPO is $684B against $331.8B of FY2026 revenue (2.06×). It jumped from $398B to $631B (+$233B) in the quarter to 2025-12-31 (S-new-r5-2).
    - Press reports say about 45% of Microsoft's commercial RPO is tied to OpenAI. That is grade B, from Silicon UK; Microsoft's own wording is still to be read (S-new-r5-9).
    - So RPO measures contracted names only, and it can hide a single-customer concentration.
19. **Customer data the engine already has.**
    - Percentages are dimensional (item 14). Sentences such as "accounted for X% of revenue" can be found with M02's L2 revenue-share patterns (`supply/find.py`, D-M02-35).
    - `events.py` types 8-K 1.01 and 1.02; 1.02 (termination of a material agreement) is routed to M02, M04 and M06.
    - In the 8-K lists checked, 1.02 arrived alongside 2.03 (a new financial obligation) every time, consistent with a financing replacement rather than a lost customer: Tesla 2023-01-25 and 2026-09-29, Rivian 2025-06-12. Only item numbers were read, not the texts (S-new-r5-5, S-new-r5-6).
    - M02's confirmed supplier/customer links (`supply/links.py`, rungs L1–L3) name the customers of watchlist suppliers. `aliases.toml` flags the watchlist names and large spenders as `customer = true`.

**Read before this round is presented** (pre-review checklist):
- Dickinson (2011): the sign table and the US transition rates (question 5.1a). The primary is not reachable from here. Either the owner obtains The Accounting Review article, or the round goes ahead on the two matching secondaries, labelled as such.
- How Lev & Thiagarajan and Abarbanell & Bushee construct the gross-margin signal (item 3).
- Kesavan & Mani's operations benchmark (the S5.6 inventory gap).

### Worked example
**Invitae 2019–22: the R12 regression case, a young firm by cash-flow signs** (S-new-r5-2, S-new-r5-4)

There is no `GrossProfit` tag, so gross profit = revenue − cost of revenue.

| Year | Revenue $M | Cost of revenue $M | Gross margin | Billable units | Revenue / unit (stated; computed) | Cost / unit (stated; computed) | Gross profit / unit (computed) |
|---|---|---|---|---|---|---|---|
| 2019 | 216.8 | 118.1 | 45.5% | 469,000 | —; $462 | —; $252 | $210 |
| 2020 | 279.6 | 198.3 | 29.1% | 659,000 | $413; $424 | $299; $301 | $123 |
| 2021 | 460.4 | 348.7 | 24.3% | 1,169,000 | $380; $394 | $298; $298 | $96 |
| 2022 | 516.3 | 417.3 | 19.2% | 1,290,000 | "higher" (amount not read); $400 | higher; $323 | $77 |

- **Revenue rose in every year while margin fell 26 pp.** This is R12.
- **2021 cause, as stated:**
  - revenue per unit fell $413 → $380 "primarily due to changes in payer and product mix, as well as reductions in pricing for some payers";
  - cost per unit was flat;
  - offsetting increases: amortization of acquired intangibles +$28.0M, SBC +$10.1M, inventory write-downs +$9.7M.

  That makes 2021 case 6 below: volume bought with price.
- **2022 cause:** the research item 1 list, which sums to the stated $68.6M.
- **Cash-flow signs:** (−,−,+), introduction, in every year 2019–22. 2018 was (−,+,+), decline, on +$36M of investing inflows. 2022 financing was only +$1.8M, so a near-zero flow decided the sign.
- **Engine reading (illustrative):**
  - R12 opens by 2021Q1 under 5.2a (table below) and stays open to 2022Q3.
  - Cause classes: price/mix (2021), accounting (acquisition amortization), one-off (write-downs) and input cost (shipping).
  - Young-firm flags all fire:
    - per-unit gross profit fell while units rose 2.75×;
    - unit cost did not fall with cumulative units;
    - revenue per unit fell while cost per unit stayed flat (2021).
  - The survival gate fails at the FY2022 10-K (Round 4).
  - Invitae therefore ties R11's pattern to R12's trigger. Rivian (below) is the counter-case: per-unit economics improve.

**Rivian: young firm, negative margin, improving per unit (R11 case)** (S-new-1, S-new-47, S-new-r5-6). Consolidated rows include software and services.

| Period | Revenue $M | Gross profit $M | Deliveries | Revenue / unit | Cost / unit | Gross profit / unit | Gross margin |
|---|---|---|---|---|---|---|---|
| FY2022 | 1,658 | −3,123 | 20,332 | $81.5k | $235.1k | −$153.6k | −188% |
| FY2023 | 4,434 | −2,030 | 50,122 | $88.5k | $129.0k | −$40.5k | −46% |
| FY2024 | 4,970 | −1,200 | 51,579 | $96.4k | $119.6k | −$23.3k | −24% |
| Q4 2024 | 1,734 | +170 (automotive +110) | 14,183 | — | — | see automotive table | — |
| FY2025 | 5,387 | +144 | 42,247 | not comparable: includes $1,557M of software and services, which includes joint-venture services | — | — | +2.7% |

The automotive table below matches unit scope: vehicle revenue against vehicle deliveries. FY2024 figures are comparatives from the FY2025 release. Credits are assumed to sit inside automotive revenue.

| Period | Automotive revenue $M | Automotive gross profit $M | Credits $M | Auto revenue / unit | Auto gross profit / unit | Same, excluding credits |
|---|---|---|---|---|---|---|
| FY2024 | 4,486 | −1,207 | 325 | $87.0k | −$23.4k | −$29.7k |
| FY2025 | 3,830 | −432 | about 191 (325 − 134 stated decrease) | $90.7k | −$10.2k | −$14.7k |
| Q4 2024 | — | +110 | 299 | — | +$7.8k | −$13.3k |
| Q4 2025 | — | −59 | about 29 (299 − 270 stated decrease) | — | −$6.1k | −$9.0k |

- 2025 deliveries (42,247) and production (42,284) come from Rivian's 8-K EX-99.1 of 2026-01-02. The FY2025 figures come from the 8-K EX-99.1 of 2026-02-12 (S-new-r5-6). These replace the Business Wire and Seeking Alpha copies.
- **Q4 2025 shows why credits are kept separate.** Reported automotive gross profit per unit fell from +$7.8k to −$6.1k, but excluding credits it improved from −$13.3k to −$9.0k. The swing is the $270M fall in credit sales.
- The 2023→2024 consolidated gain of $17.2k per unit includes about $4.9k from a $252M rise in credit sales.
- **Engine reading (illustrative):**
  - Stage: introduction. Signs were (−,−,+) in every year 2020–25.
  - No young-firm margin flag: the automotive loss per unit narrowed from $23.4k to $10.2k (excluding credits, $29.7k to $14.7k).
  - Credit-dependence warnings: Q4 2024 (credits $299M against gross profit $170M) and FY2025 (credits about $191M against consolidated gross profit $144M).
  - The first positive consolidated gross profit (FY2025) rests on software and services (+$576M), while automotive stays at −$432M.
  - Production gap: flagged for 2023 (production 14% above deliveries), not for 2025 (0.1%).

**Tesla 2023: revenue up, margin down, cause = price** (S-new-50, S-new-r5-5)

| Year | Automotive sales $M | Cost $M | Deliveries | Production | Revenue / unit | Cost / unit | Gross profit / unit |
|---|---|---|---|---|---|---|---|
| 2022 | 67,210 | 49,599 | 1,313,851 | 1,369,611 | $51.2k | $37.8k | $13.4k |
| 2023 | 78,509 | 65,121 | 1,808,581 | 1,845,985 | $43.4k | $36.0k | $7.4k |
| 2024 | 72,480 | 61,870 | 1,789,226 | 1,773,443 | $40.5k | $34.6k | $5.9k |

- **Sources.** Deliveries and production come from the delivery 8-Ks (Item 2.02, EX-99.1), all stored under DS2:
  - 2023-01-03, accession 0001564590-23-000002;
  - 2024-01-02, accession 0000950170-24-000282;
  - 2025-01-02, accession 0001628280-25-000007.

  The 2024 sales and cost come from the FY2024 10-K (accession 0001628280-25-003063).
- **Bridge 2022→2023:** volume +$6.6B, price −$14.0B, cost +$3.2B = −$4.2B, which matches the reported change.
- **Bridge 2023→2024:** −$0.1B, −$5.2B, +$2.6B = −$2.8B.
- Automotive sales exclude credits ($1,790M in 2023, $2,763M in 2024) and leasing. Deliveries include leased cars. Production was 4.2%, 2.1% and −0.9% away from deliveries, so no gap flag.

**Target FY2022: mature company, Sales +2.8%, gross-margin rate 28.3% → 23.6%** (S-new-51, S-new-r5-3)
- Waterfall: merchandising −3.4 pp, fulfillment and supply chain −0.8, shrink −0.7, mix +0.2; sums to −4.7.
- The inventory gap came first.
- The rate reverted to 26.5% in FY2023 (10-K).
- **Data timing is a real failure.** From companyfacts alone, the Q1 and Q2 2022 cost of sales arrive a year late (research item 14). On as-of reads, 5.2a sees Q3 2022 (−3.4 pp) but then Q4 2022 (−2.9 pp), never two qualifying quarters in a row, so it does not fire while it matters; the Q1–Q2 2022 drop becomes visible only in hindsight, from August 2023. With each 10-Q's own statement, via an instance read (5.4a), it fires at Q2 2022 (table below).

**Intel 2021–24: revenue falling, so R12 does not fire; CvD's case** (S-new-1, S-new-61, S-new-r5-2)

| Year | Revenue $M | Gross margin % |
|---|---|---|
| 2021 | 79,024 | 55.4% |
| 2022 | 63,054 | 42.6% |
| 2023 | 54,228 | 40.0% |
| 2024 | 53,101 | 32.7% (about 40.6% excluding stated charges; illustrative arithmetic) |

**Question 5.2 options on real quarters** (S-new-r5-2, S-new-r5-3, S-new-r5-7; Q4 = fiscal year − 9 months)
- Gross margin (GM) is total company, except Target, which uses its rate on Sales. On Target's total-revenue base the Q1 and Q2 2022 changes are −4.3 and −8.7 pp, with the same result.
- "TTM rev" is the year-over-year change in trailing-twelve-month total revenue.
- Under 5.2a, an episode opens on the second straight qualifying quarter and closes after two straight quarters that do not qualify.

| Company, quarter (filed) | TTM rev | GM | GM YoY pp | 5.2a | 5.2b (≥ 5 pp, revenue up) | 5.2d (excluding stated items) |
|---|---|---|---|---|---|---|
| TSLA 2022Q4 (10-K 2023-01-31) | +51.4% | 23.8% | −3.6 | 1st quarter | — | as (a); no stated items checked |
| TSLA 2023Q1 (10-Q 2023-04-24) | +38.3% | 19.3% | −9.8 | **fires** | **fires** | as (a) |
| TSLA 2023Q2–Q4 | +40.0 / +28.1 / +18.8% | 18.2 / 17.9 / 17.6% | −6.8 / −7.2 / −6.1 | open | open | — |
| TSLA 2024Q1–Q2 | +10.1 / +1.4% | 17.4 / 17.9% | −2.0 / −0.2 | closes at Q2 | — | — |
| TGT 2022Q1 (10-Q 2022-05-27) | +9.0% | 25.7% | −4.4 | 1st quarter | — (below 5) | as (a) |
| TGT 2022Q2 (10-Q 2022-08-26) | +7.5% | 21.5% | −8.9 | **fires** | **fires** | as (a) |
| TGT 2022Q3 | +5.2% | 24.7% | −3.4 | open | — | — |
| TGT 2022Q4–2023Q1 | +2.9 / +2.1% | 22.7 / 26.3% | −2.9 / +0.7 | closes at 2023Q1 | — | — |
| INTC 2021Q4 (10-K 2022-01-27) | +1.5% | 53.6% | −3.2 | 1st quarter | — | — |
| INTC 2022Q1 (10-Q 2022-04-29) | **−0.01%** | 50.4% | −4.8 | no: revenue down by $8M | no | no |
| INTC 2022Q2–2023Q1 | −5.4% to −27.4% | 34.2–42.6% | −13.4 to −20.6 | no (revenue down; CvD) | no | no |
| INTC 2024Q3 (10-Q 2024-11-01) | +2.6% | 15.0% (≈ 38.4% excluding the $3.1B) | −27.5 (≈ −4.1) | 1st quarter | **fires** on a stated one-quarter charge | 1st quarter |
| INTC 2024Q4 (10-K 2025-01-31) | −2.1% | 39.2% | −6.6 | no (revenue) | no | no |
| NVTA 2020Q4 (10-K 2021-02-26) | +29.0% | 32.0% | −12.6 | 1st verified quarter | **fires** | annual stated amounts only; not computed |
| NVTA 2021Q1 (10-Q 2021-05-04) | +32.6% | 27.2% | −9.9 | **fires** | open | — |
| NVTA 2021Q2 | +66.8% | 23.2% | +16.2 (base: Q2 2020, the COVID quarter) | open (one quarter off) | — | — |
| NVTA 2021Q3–2022Q3 | +77% → +20% | 12.4–23.8% | −8.8, −8.2, −5.7, −4.0, −10.9 | open | open | — |
| NVTA 2022Q4–2023Q1 | +12.1 / +6.1% | 24.2 / 24.6% | +0.4 / +3.2 | closes at 2023Q1 | — | — |

Further notes on the table:
- Invitae's 2020Q2–Q3 also fell 41 and 11 pp, so it probably fired earlier. Checking that needs 2018 quarters, which were not read.
- Intel 2021Q1 (−5.4 pp) probably fires under (b), but its TTM base needs 2019 quarters, which were not checked.
- **Result.** (a) and (b) agree on Tesla and Target. (b) is one quarter earlier on Invitae, but it also fires on Intel's stated $3.1B one-quarter charge. (d) matches (a) on every case here.

**Stage from cash-flow signs on real filings** (S-new-r5-2; $M; question 5.1)

| Company | FY | Operating | Investing | Financing | Signs → stage | 5.1a (2 of 3 years) |
|---|---|---|---|---|---|---|
| Tesla | 2021 | 11,497 | −7,868 | −5,203 | mature | growth (2019–20 growth) |
| Tesla | 2022 | 14,724 | −11,973 | −3,527 | mature | mature → review |
| Tesla | 2023 | 13,256 | −15,584 | +2,589 | growth | mature |
| Tesla | 2024 | 14,923 | −18,787 | +3,853 | growth | growth → review |
| Intel | 2021 | 29,456 | −24,283 | −6,211 | mature | mature |
| Intel | 2022 | 15,433 | −10,231 | +1,115 | growth | mature |
| Intel | 2023 | 11,471 | −24,041 | +8,505 | growth | **growth → review** |
| Intel | 2024 | 8,288 | −18,256 | +11,138 | growth | growth |
| Invitae | 2018 | −92 | +36 | +157 | decline | — |
| Invitae | 2019–22 | −145 to −560 | −175 to −401 | +1.8 (2022) to +1,566 | introduction | introduction from FY2020 |
| Rivian | 2021–25 | −779 to −5,052 | −1,369 to −2,511 | +99 to +19,828 | introduction | introduction |

How each option reads these companies:
- **5.1a without owner confirmation** routes Intel as "growth" from FY2023, on debt and partner funding while revenue fell. Tesla flips twice in four years.
- **5.1c** ("young" if TTM revenue growth > 25% or 3-year cumulative operating cash flow < 0; illustrative cut-offs):
  - reads Tesla FY2022 as young (revenue +51.4%);
  - gets Invitae and Rivian right (young);
  - has no decline stage, so Intel cannot be held out of the reversion prior.
- **5.1b** is right by construction for the 15 operating watchlist names, but the Round 6 test companies have no stage until the owner labels them.

**NVIDIA: a design-in supplier, customers anonymous** (S-new-r5-8, S-new-r5-2; fiscal years end late January)

| FY | Revenue $M | Direct customers ≥ 10% (as stated) | Revenue at stake (computed) | RPO at year end |
|---|---|---|---|---|
| FY2024 | 60,922 | one at 13% | ≈ $7.9B | $1.1B |
| FY2025 | 130,497 | 12%, 11%, 11% | ≈ $15.7B, $14.4B, $14.4B (34%, ≈ $44.4B) | $1.7B |
| FY2026 | 215,938 | 22%, 14% | ≈ $47.5B, $30.2B (36%, ≈ $77.7B) | $2.3B |

- **A shorter list is not a loss.** The list went from three names to two while concentration rose. At least one FY2025 customer fell below 10%, yet "below 10%" of FY2026 revenue still allows up to $21.6B, above that customer's $14.4B in FY2025. This is the existing failure-mode row.
- Customers are unnamed, so matching FY2025's 12% customer to FY2026's 22% customer is inference. NVIDIA also estimates that some indirect customers exceed 10%; that is an estimate, stated in text only.
- RPO is about 1% of revenue, so it says little for this class.
- **Engine reading (illustrative):**
  - Proposed class: design-in (≥10% customers disclosed, SIC 3674); the owner confirms.
  - Revenue at stake: 36%.
  - No weakening, because there is no loss evidence and revenue rose 65%.
  - Signals: `customer_at_stake` 0.36, and `customer_signal` intact.

**Microsoft: a contracted name** (S-new-r5-2, S-new-r5-9)
- RPO ÷ FY2026 revenue = 2.06×. RPO rose $233B in one quarter.
- Press reports put about 45% of commercial RPO with one counterparty, OpenAI (grade B).
- Engine reading (illustrative): the RPO trend stays within or above its own range, so intact. The counterparty share is shown as a grade-B note.

### All cases
Margins and unit economics:
1. Revenue up, gross margin down, at **any** stage (R12). Causes: price (Tesla), markdowns or input cost (Target), price/mix and acquisition amortization (Invitae), mix, one-off, credits, FX, or an accounting or segment change.
2. Revenue down, margin down → CvD (Intel 2022–23).
3. Revenue flat at a turn: Intel 2022Q1 TTM −0.01% → no R12. The CvD grid takes the case.
4. A one-quarter stated charge while revenue edges up (Intel 2024Q3, $3.1B) → stated items shown; no R12 under 5.2a.
5. Inventory outgrowing sales before the hit (Target).
6. Revenue per unit falling while cost per unit is flat: volume bought with price (Invitae 2021).
7. Young, negative margin improving per unit with volume (Rivian 2022–25).
8. Young, margin not improving, or unit cost not falling, while units rise (Invitae 2019–22).
9. First positive gross profit dependent on credits or services (Rivian FY2025; Q4 2024).
10. Reported per-unit worsens while ex-credit per-unit improves (Rivian Q4 2025).
11. Credits share when gross profit ≤ 0 → `not_meaningful`; credits shown in dollars.
12. Production above deliveries, with overhead capitalised into inventory (Rivian 2023, 14%).
13. Units not disclosed → margins only (Intel). Units only in 10-K text (Invitae billable units).
14. Unit scope ≠ revenue scope: leases (Tesla), JV services (Rivian FY2025), or a narrower stated base (Invitae: $380 stated vs $394 computed).
15. KPI category break (Tesla "Model S/X" in the 2022 release → "Other Models" in the 2023–24 releases, now including Cybertruck).
16. Cause stated at two levels: total change from volume, per-unit change from named items (Invitae 2022).
17. Pre-revenue zeros; tiny revenue (`not_meaningful`).
18. Segment recast vs consolidated figures (the Rivian "recast" mistake).
19. Restated gross profit (Intel FY2016/17).
20. No `GrossProfit` tag → revenue − cost of revenue, method tagged (Invitae).
21. No gross-profit line, and cost of sales defined differently from peers (Amazon excludes fulfillment) → not like-for-like for peer gaps.
22. Company-stated rate on a different base (Target: Sales, not total revenue).
23. Quarterly cost of revenue missing from companyfacts at filing time (Target 10-Qs before Q3 2022) → instance read, or the trigger is late.
24. Company-stated contribution margin.
25. Waterfall components that do not sum.

Stage:

26. Stage change from financing signs alone: Intel FY2023 "growth" on debt and partner funding; Tesla FY2024 "growth" on positive financing flows.
27. Shake-out pattern, or no stage holding 2 of 3 years → ambiguous.
28. A near-zero flow decides a sign (Invitae 2022 financing +$1.8M).
29. Fewer than 2 years of periodic cash flows: a recent IPO (SPCX) or a de-SPAC with predecessor history under another CIK (INFQ) → ambiguous until the owner sets the stage.
30. Decline stage → reversion prior shown with its reason, not used.

Customer base (D-M04-1):

31. Named vs anonymous ≥10% customers (NVIDIA "one direct customer").
32. A customer drops below 10% while revenue grows (NVIDIA FY2025 → FY2026).
33. Concentration rising without any loss (NVIDIA 36% from two customers).
34. Indirect customers estimated above 10%, in text only (NVIDIA).
35. Contracted name with RPO many times revenue; one counterparty dominating RPO (Microsoft; grade B).
36. RPO tiny against revenue → no RPO test for that class (NVIDIA ≈ 1%).
37. 8-K 1.02 for a financing replacement (co-filed with 2.03) vs the end of a customer or supply agreement.
38. Customer named by an M02 link (L1–L3) vs only inferred.
39. Customer percentage in a sentence, in a table only, on a dimensional context only, or absent.
40. A customer's own results or capex guidance falling (M02 money flow) → context, not a signal.

**Complete / known omissions:**
- Segment-level margin collapse hidden inside a stable consolidated margin: needs 5.4a.
- Distributor channel inventory.
- Contract renewal and churn rates, which no XBRL tag carries.
- Backlog measures stated in text that differ from RPO (aerospace and defence; not checked for BA or SPCX).
- FX as a cause, which is tagged only from text.
- Market share: Round 6.

### Suggestions
- **S5.1 One `lifecycle_stage` per company** (question 5.1, presented with Round 1). Stored with history and used for routing in Rounds 2–4:
  - growth names get the M-score without SGI;
  - young firms get Z as a warning only.

  The owner model tag (3.4) stays separate.
  - **Ambiguous rule (R2).** Stage is `ambiguous` when any of these holds:
    - the latest year's signs are a shake-out pattern;
    - no stage holds in 2 of the last 3 years;
    - fewer than 2 years of periodic cash flows exist.

    An ambiguous stage opens an `m04_stage` review item.
  - **While unconfirmed.** The last confirmed stage keeps routing. With no confirmed stage, both the young and the mature flag sets are computed and shown, labelled "stage unconfirmed". Neither counts toward D13 confluence until the owner confirms (D8, D10).
  - **Confirmation.** The computed stage is a proposal. The owner confirms each name's first stage and every change, because Intel's and Tesla's real signs mislead.
- **S5.2 R12 trigger** (question 5.2). Stage-neutral. It opens one "identify the cause" review item (`m04_margin_cause`) per episode.
  - Episode opening and closing are as defined above the 5.2 table.
  - Thresholds are starting values without a source. The 3 pp matches the approved Q2 "intact" band (change ≥ −3 pp).
- **S5.3 Cause finder** (question 5.3).
  - Searches the same filing's MD&A plus EX-99.1 and EX-99.2 for sentences on gross margin, cost of revenue or cost per unit containing "primarily due to", "primarily attributable to", "driven by" or "offset by".
  - Handles two levels: total change and per-unit change (Invitae 2022).
  - Rules tag one or more classes: price, volume/scale, mix (product, payer, customer), input cost, one-off, credits/other, FX, accounting (acquisition amortization, standard change) or segment change.
  - Arithmetic check: stated components must sum to the stated total. Invitae 2022 sums to $68.6M; Target's waterfall to −4.7 pp. Qualitative-only sentences get "no check" (Tesla 2024).
  - The owner confirms, following the guidance-label pattern (D-M02-24).
- **S5.4 Stated items.** Gross margin is shown as reported and "excluding stated items". Each item carries its tag or quote and accession (Intel Q3 2024: about $3.1B, "substantially all" in cost of sales). Unstated amounts are never estimated.
- **S5.5 Unit metrics.**
  - A `unit_metric` table: company, period, metric, value, unit, label as stated, accession, quote.
  - Extractors start with Tesla DS2 by model line and Invitae-style 10-K unit sentences, then a watchlist survey for similar releases.
  - The bridge runs only when the line item and the unit scope match (Rivian automotive vs deliveries); otherwise "not comparable". Where the company states a per-unit figure, the stated figure is shown first, with the computed one beside it.
  - Credits are shown separately. `credit_share_of_gp` = credits ÷ gross profit when gross profit > 0; otherwise `not_meaningful`, with credits shown in dollars. The warning fires at ≥ 50% (starting value, unsourced).
  - A production/delivery gap above 10% (starting value, unsourced) is flagged beside any unit-cost improvement.
- **S5.6 Stage-aware red flags.**
  - **All stages:**
    - R12 (S5.2);
    - inventory growth − sales growth > 15 pp (an unsourced starting value, motivated by S-new-53, whose measure differs), as a warning.
  - **Young:**
    - per-unit gross profit not improving over 4 quarters while units rise (starting value, unsourced);
    - unit cost not falling with cumulative units;
    - revenue per unit falling while cost per unit is flat;
    - production gap;
    - credit share;
    - survival gate.

    Negative gross margin alone is not a flag.
  - **Mature:**
    - SG&A growth > revenue growth for 4 quarters (starting value, unsourced; motivated by the sticky-cost asymmetry, S-new-54, which sets no threshold);
    - CvD Q2 margin gap.
  - **Decline:** the reversion prior is shown with the reason "decline stage: not used" (S5.10).
- **S5.7 Dimensional facts** (question 5.4).
  - Read from filing instances (watchlist only):
    - business-segment and product/service axes;
    - `srt:MajorCustomersAxis` with the concentration-risk axes;
    - any 10-Q line missing from companyfacts that a mapped concept needs (Target's cost of sales).
  - Stored in a new `fact_dim` table (the fact columns plus axis/member pairs), not as columns on `fact`. The current unique key has no dimension, and no existing `series` reader can then pick up a segment value as a company total.
  - Recasts are detected by comparing first and latest values per member. Breaks are flagged and both series kept. Values are never compared across scopes.
  - A re-read path (`--rescan`) fetches already-read instances once more, because raw files are not kept.
  - Each build part updates M00_STORAGE.md (the new table) and M00_SEC_DATA.md (the instance reader's scope) in the same commit.
- **S5.8 Contribution margins.** Company-stated figures are shown, labelled non-GAAP and quoted; never computed.
- **S5.9 Signals out (Round 5 rows of the M04 "Signals out" table).**
  - `signal` has a numeric `value`, NOT NULL `timeframe` and `evidence_grade`, and the primary key (ticker, module_id, signal, timeframe, as_of). So each enum state gets its own signal name, with value 1.
  - Grade A for filing-derived values; grade B only for press inputs (shown as notes, never as triggers).
  - Timeframe parameters (D2, D12): MY reads annual and TTM values; PT reads quarterly year-over-year values with 2-quarter persistence; ST shows information only for now, because margin, stage and customer data are quarterly at best.

  | Signal | Encoding | Meaning | MY | PT | ST |
  |---|---|---|---|---|---|
  | `lifecycle_stage.<stage>` | value 1; sign pattern and confirmation in `method` | Routing for stage-aware flags | ✓ | ✓ | info |
  | `margin_cause.<class>` | value = stated $M where given, else NULL; quote passage in `source_ref` | Cause of an R12 episode | ✓ | ✓ | info |
  | `gm_delta_pp` | pp, reported; excluding-items value in `method` | Year-over-year gross-margin change | ✓ | ✓ | info |
  | `unit_gp`, `unit_gp_ex_credits` | $ per unit, matching scope only | Per-unit gross profit | ✓ | info | info |
  | `credit_share_of_gp` | ratio, or NULL when `not_meaningful` | Credits ÷ gross profit | ✓ | ✓ | info |
  | `inventory_sales_gap` | pp | Inventory growth − sales growth | ✓ | ✓ | info |
  | `customer_at_stake` | share of TTM revenue | Revenue from disclosed major customers | ✓ | ✓ | info |
  | `customer_signal.<state>` | value 1; state = intact / weakening / info | Q2 customer row (S5.13) | ✓ | ✓ | info |

- **S5.10 Mean-reversion prior.** Shown as context text for every stage (D10). For the decline stage it carries "not used: decline-stage profitability does not revert (S-new-56)" and gets no weight.
- **S5.11 Regression cases:**
  - Invitae 2020–22 (the R12 case in M04_FINANCIALS.md):
    - R12 fires by 2021Q1 under 5.2a, at stage introduction;
    - cause classes as stated, with a $68.6M sum check;
    - derived gross profit (no tag);
    - all three young-firm flags;
    - survival gate fails at the FY2022 10-K (Round 4).
  - Rivian 2022–25 (R11): no margin flag; credit warnings for Q4 2024 and FY2025; automotive-scope bridge for FY2025.
  - Tesla 2023: R12 fires at 2023Q1, cause price.
  - Target FY2022:
    - early inventory warning;
    - R12 fires at Q2 2022 only with the 10-Q instance read (a companyfacts-only fixture must show the late-data failure);
    - causes price and input cost;
    - reverted.
  - Intel 2022–24: no R12 under 5.2a (2022Q1 revenue −0.01%; 2024Q3 a single quarter); stated one-offs shown; stage proposal "growth" from FY2023 goes to review.
  - NVIDIA FY2024–26: design-in, 36% at stake, the shrinking ≥10% list not read as a loss.
- **S5.12 Gross-margin comparability.**
  - Without a `GrossProfit` tag, gross profit = revenue − cost of revenue, with method `derived` (Invitae).
  - The base is always stated (Target: company rate on Sales; engine on total revenue).
  - Names with no gross-profit line or a non-standard cost of sales (Amazon) get a "not like-for-like" marker and are excluded from Round 6's peer gross-margin gap unless the owner confirms a peer set with the same definition. R12 still runs on the company's own history.
- **S5.13 Customer signal** (question 5.5; the D-M04-1 Q2 row).
  - **Class proposal (engine), owner confirms**, per M04_FINANCIALS.md ("owner sets per company; engine proposes"). The cut-offs are starting values, unsourced:
    - contracted/recurring when RPO ÷ TTM revenue ≥ 0.5 (Microsoft 2.06);
    - design-in/qualified when a ≥10% customer is disclosed, or an M02 L1–L3 link names the company as a supplier, and the SIC code is 3570–3679 (NVIDIA, SIC 3674);
    - transactional otherwise.
  - **Inputs:**
    - customer percentages from instance axes, else from the revenue-share sentence finder;
    - the `rpo` series;
    - 8-K 1.01/1.02 matched to `aliases.toml` customer names or to supply/customer-agreement wording;
    - 1.02 co-filed with 2.03 is treated as financing unless the text names a customer;
    - M02 confirmed links;
    - customers' own results and capex guidance (M02) as context.
  - **Weakening, by class:**
    - **Design-in:** a loss signal is any of: a customer or supply agreement ended (8-K or text); a disclosed customer's share below its own 3-year minimum while total revenue is flat or down (starting value, unsourced); or the customer naming a replacement supplier (M02 L1). Each opens an `m04_customer` review item, and "weakening" is set only after the owner confirms.
    - **Contracted:** RPO ÷ TTM revenue below its own 3-year minimum for 2 quarters (starting value, unsourced).
    - **Transactional:** information only, low weight.
  - **Revenue at stake** = share × TTM revenue, shown on every customer row. The row's vote is weighted by it, as D-M04-1 approved. How the weight enters `cvd_confidence` is settled with Round 6's missing-indicator rule. With no customer data the row is "missing", never "intact".
- **S5.14 Review kinds for this round** (volumes estimated from the cases above, to be measured in Part 7's live check; to join the pack-wide M04 review table and cap, following D-M02-51):

  | Kind | Opens on | Expected volume (15 operating watchlist names) | Cap | Priority |
  |---|---|---|---|---|
  | `m04_stage` | First-run confirmation; computed change; ambiguous | 15 at first run (a baseline, LESSONS), then about 4–5 a year (Tesla 2 and Intel 1 change in 2021–24) | 5 a week during the first run | 1 (routing depends on it) |
  | `m04_margin_cause` | R12 episode opens | Under 1 a quarter (3 episodes across the four test names in 2020–24) | None needed at that rate | 2 |
  | `m04_customer` | Design-in loss signal; RPO below range; 1.01/1.02 naming a customer | Not measured; estimate 1–3 a quarter | 3 a week | 3 |
  | `m04_unit_kpi` | New unit-metric label or category break | About 1 a year (Tesla) | 2 a week | 4 |

- **S5.15 Calibration status.** Round 6 calibrates CvD only. Every Round 5 threshold (3 pp and 2 quarters; 50% credit share; 10% production gap; 15 pp inventory gap; 4-quarter SG&A rule; class cut-offs) stays **information-only**: shown, but not counted in D13 confluence. That holds until a labelled set of margin and unit-economics episodes exists. The five cases above start that set; the owner adds more.
- **S5.16 Build plumbing (Part 7).**
  - **Script:** `scripts/run_m04.py`, which takes `refresh.lock` like every SEC-calling script.
  - **Logon refresh:** one instance read per new watchlist 10-K or 10-Q, and one EX-99.2 per configured earnings 8-K. Both are a handful of requests a day, well inside the 3-hour limit (D-M02-12).
  - **One-off backfills:** 3 years of instances and the RIVN history.
  - **Mock-up first:** a mock-up with real data comes before the Financials-tab rows (D-UI-4).
  - **Docs:** M04_FINANCIALS.md, M00_STORAGE.md, M00_SEC_DATA.md, M00_UI.md and DATA_SOURCES.md (DS12, DS14) are updated in the same commit.
  - **Live check (one owner run, about 70–80 requests, a few minutes at 5/s; download time measured):**
    - the latest 10-K and 10-Q instance for each of the 15 operating names (about 30);
    - EX-99.2 for configured names (about 10);
    - fixtures, preferring companyconcept per tag over whole companyfacts files:
      - Rivian: about 6 concepts and 4 release documents;
      - Target: about 4 concepts and the Q1–Q3 2022 10-Q instances;
      - Invitae: about 5 concepts and the FY2021/FY2022 10-K texts.

### Failure modes (rows to add)
| Input | How it can mislead | Guard |
|---|---|---|
| R12 gated by stage | Invitae (introduction stage) would never be checked | R12 runs at every stage; stage changes only the follow-up flags |
| R12 single-quarter version | Fires on a stated one-quarter charge (Intel 2024Q3) | 2-quarter persistence; stated items shown beside |
| R12 revenue condition | Knife-edge at a turn (Intel 2022Q1, −0.01%) | Case passes to CvD; both readings shown |
| Quarterly cost of revenue | Missing from companyfacts for a year (Target 10-Qs before Q3 2022), so the trigger is late or never fires | Instance read for missing 10-Q lines (S5.7); "missing: dimensional" label |
| Gross-margin definition | No gross-profit tag or line; cost of sales excludes fulfillment (Amazon); rate on Sales vs total revenue (Target) | Method `derived`; base stated; "not like-for-like" in peer gaps |
| Per-unit gross profit | Revenue scope ≠ units (leases, credits, services, JV revenue) | Bridge only on matching scope; "not comparable"; credits separate |
| Stated vs computed per-unit | Different revenue bases (Invitae $380 vs $394) | Stated figure first, with quote; computed beside |
| Deliveries vs production | Production above deliveries flatters cost | Gap > 10% flagged beside cost gains |
| KPI definitions | Category changes; undefined metrics | Label as stated plus quote; breaks flagged, not merged |
| Gross-margin signal | One-off charges look like collapse or recovery | Reported and "excluding stated items", each quoted |
| Regulatory credits | Lift gross profit with no unit cost; can vanish with policy; reported per-unit swings are credit effects (Rivian Q4 2025) | `credit_share_of_gp`; ex-credit per-unit beside reported |
| Cause sentences | Management framing; buried offsets; mis-signed summaries; two-level statements | Arithmetic sum check; quote stored; owner confirms |
| Segment vs consolidated | Segment figures read as consolidated (the Rivian "recast" mistake) | Separate `fact_dim` table; axis and member stored with every value |
| Life-cycle stage | Financing signs mimic growth (Intel FY2023, Tesla FY2024); one-year flips; near-zero flows decide a sign; acquirers look like growth | 2-of-3-year persistence; owner confirms first stage and every change; ambiguous → both flag sets shown, not counted |
| Mean-reversion prior | Decline-stage firms do not revert | Shown for every stage; for decline "not used" with the reason (D10) |
| Inventory gap | Inverted U; retail evidence only | Starting value to calibrate; warning, not trigger |
| Zeros and tiny revenue | Pre-revenue 0; huge margins on small bases | Zeros kept; `not_meaningful` below a revenue floor |
| ≥10% customer list | Customers anonymous; matching across years is inference; a shorter list read as a loss (NVIDIA FY2026) | Revenue at stake and total revenue shown; loss only with text or 8-K evidence and owner confirmation |
| RPO | Tiny for design-in suppliers (NVIDIA ≈ 1%); one counterparty can dominate (Microsoft, grade B) | RPO test for the contracted class only; counterparty share as a grade-B note |
| 8-K 1.02 | Mostly financing replacements (co-filed with 2.03) | Customer event only when the text names a customer or supply agreement |
| Round 5 thresholds | Starting values, mostly unsourced, with 5 labelled cases | Information-only until a labelled set exists (S5.15) |

### Questions
**5.1 Stage source** (presented with Round 1)
- (a) *Recommended.* Dickinson cash-flow signs as an engine proposal, with 2-of-3-year persistence. The owner confirms each name's first stage and every change. The ambiguous rule in S5.1 applies, the owner can override, and R12 is stage-neutral. Why: computed free from stored data, and confirmation catches the real misreads (Intel "growth" from FY2023; Tesla flipping twice).
  - Gets wrong without confirmation: Intel FY2023–24 and Tesla FY2024 (financing signs).
- (b) The owner sets every stage by hand. Gets wrong: Round 6 test companies and newly tracked names have no stage until labelled, and stages go stale when not revisited.
- (c) Rules on growth and cash flow (e.g. TTM revenue growth > 25% or 3-year cumulative operating cash flow < 0 → young; illustrative cut-offs). Gets wrong: Tesla FY2022 reads young (+51.4%); there is no decline stage, so Intel's reversion prior cannot be held back.

**5.2 R12 trigger**
- (a) *Recommended.* All of:
  - TTM revenue up year over year;
  - gross margin down ≥ 3 pp year over year for 2 straight quarters, on the reported margin, with "excluding stated items" shown beside it;
  - an episode closes after 2 non-qualifying quarters;
  - every stage.

  Why: on real quarters it fires on Tesla 2023Q1, Target 2022Q2 and Invitae 2021Q1, and stays silent on Intel's one-quarter 2024Q3 charge.
  - Gets wrong: none of the four cases, given 5.4a's instance read for Target (on companyfacts alone Target is missed). It waits a quarter when one large drop is not preceded by a ≥ 3 pp drop.
- (b) Any single quarter ≥ 5 pp, with revenue up. Gets wrong: Intel 2024Q3 (fires on a stated $3.1B one-quarter charge) and probably Intel 2021Q1 (−5.4 pp; base unchecked). One quarter earlier on Invitae.
- (c) Only when the gross-margin gap to peers worsens (CvD Q2). Gets wrong: silent when a squeeze is shared, although the company's own cause still needs naming. No trigger for names with fewer than 5 peers (Invitae, Rivian).
- (d) As (a), but triggered on the excluding-items margin. Gets wrong: nothing in these four cases (Intel 2024Q3 ≈ −4.1 pp, no second quarter). Recurring "one-off" charges would be excluded every time, and it depends on stated amounts that are annual-only for Invitae.

**5.3 Who names the cause**
- (a) *Recommended.* Code extracts and tags the sentences; the owner confirms; a Gemini hint runs only on request, with verified quotes. Why: code first (D28). The "primarily due to / attributable to" sentences exist in every case here (Tesla 2023–24, Invitae 2021–22), and quotes are stored.
- (b) Arithmetic decomposition only, no text. Gets wrong: Invitae 2022, where the arithmetic shows cost per unit +8% but cannot split amortization ($50.6M) from write-downs ($18.2M). Target's merchandising, freight and shrink waterfall cannot be derived from XBRL.
- (c) Gemini labels by default, with verified quotes. Gets wrong: nothing in accuracy, but every episode costs a request where code already finds the sentence.

**5.4 Unit KPIs, Rivian, segments and customer axes**
- (a) *Recommended.*
  - Tesla DS2 extractor plus a watchlist survey;
  - EX-99.2 fetched for configured companies;
  - RIVN added as a tracked name;
  - segment, product and `srt:MajorCustomersAxis` facts read from filing instances (extend `instance.py`, watchlist only) into `fact_dim`, plus any 10-Q line missing from companyfacts;
  - a one-off re-read of instances already read.

  EdgarTools stays an open evaluation item. Why: about one request per filing on the D-M02-32 path. Live check about 30 instances; backfill about 180.
- (b) Tesla only; Rivian as fixtures; dimensional values from the Financial Statement & Notes data sets (S40). Gets wrong: Target's 10-Q cost of sales and NVIDIA's customer shares arrive only when the bulk file is published (size and lag not checked). Rivian is fixture-only.
- (c) Defer KPIs and dimensional facts; margins only. Gets wrong: NVIDIA's 36% concentration, Rivian's automotive scope and Target's on-time R12 all stay missing.
- (d) Evaluate EdgarTools first (MIT-licensed; reads dimensions from a filing's XBRL, S41). Gets wrong: nothing in coverage, but it needs `uv add` (owner approval) and fetches the same instance files `instance.py` already reads.

**5.5 Customer signal (D-M04-1 Q2 customer row)**
- (a) *Recommended.* As S5.13:
  - the engine proposes the stickiness class and the owner confirms;
  - customer shares from instance axes, else sentences;
  - RPO test for contracted names only;
  - 8-K 1.01/1.02 only when the text names a customer or supply agreement;
  - M02 links as evidence;
  - design-in "weakening" only after owner confirmation;
  - revenue at stake shown and used as the weight.

  Why: implements the approved row and reuses M02. NVIDIA shows that list changes are not losses, and Microsoft that RPO matters only for contracted names.
- (b) Customer shares from text only (no instance read). Gets wrong: table-only and dimensional-only disclosures, and wording the targeted phrases miss (the limit recorded in D-M02-35).
- (c) Defer the customer row to M05/M06. M05 already lists RPO and ≥10% customers as leading data (A1). Gets wrong: the Q2 row stays "missing" for every name until then, so NVIDIA's 36% concentration is invisible to CvD.

### New sources added in this section
- **S-new-r5-1** Prędkiewicz, K. & Machnik, J. (2025), "Interdisciplinary measuring the life cycle phases of ICT firms", Central European Management Journal 33(3):405–420, Table 2 (Dickinson 2011 sign patterns, reproduced; secondary, other) — https://www.emerald.com/cemj/article/33/3/405/1248895/Interdisciplinary-measuring-the-life-cycle-phases
- **S-new-r5-2** SEC XBRL companyconcept data checked 2026-10-12 for Round 5. Pattern: `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/<Tag>.json`.
  - Tesla (CIK0001318605): Revenues, GrossProfit, NetCashProvidedByUsedInOperatingActivities, NetCashProvidedByUsedInInvestingActivities, NetCashProvidedByUsedInFinancingActivities.
  - Intel (CIK0000050863): RevenueFromContractWithCustomerExcludingAssessedTax, GrossProfit, and the three cash-flow totals.
  - Target (CIK0000027419): CostOfGoodsAndServicesSold, RevenueFromContractWithCustomerExcludingAssessedTax; CostOfRevenue and CostOfGoodsSold 404.
  - Invitae (CIK0001501134): RevenueFromContractWithCustomerExcludingAssessedTax, CostOfRevenue, and the three cash-flow totals; GrossProfit 404.
  - Rivian (CIK0001874178): the three cash-flow totals.
  - NVIDIA (CIK0001045810): Revenues, RevenueRemainingPerformanceObligation; ConcentrationRiskPercentage1 404.
  - Microsoft (CIK0000789019): RevenueRemainingPerformanceObligation, RevenueFromContractWithCustomerExcludingAssessedTax.
  - Example: https://data.sec.gov/api/xbrl/companyconcept/CIK0001501134/us-gaap/CostOfRevenue.json
- **S-new-r5-3** Target statements of operations (XBRL R pages):
  - Q3 2021 — https://www.sec.gov/Archives/edgar/data/27419/000002741921000034/R2.htm
  - Q1 2022 — https://www.sec.gov/Archives/edgar/data/27419/000002741922000015/R2.htm
  - Q2 2022 — https://www.sec.gov/Archives/edgar/data/27419/000002741922000027/R2.htm
  - Q3 2022 — https://www.sec.gov/Archives/edgar/data/27419/000002741922000037/R2.htm
  - Q1 2023 — https://www.sec.gov/Archives/edgar/data/27419/000002741923000025/R2.htm
  - Q2 2023 — https://www.sec.gov/Archives/edgar/data/27419/000002741923000035/R2.htm
  - Q3 2023 — https://www.sec.gov/Archives/edgar/data/27419/000002741923000052/R2.htm
  - FY2019–21 (10-K filed 2022-03-09) — https://www.sec.gov/Archives/edgar/data/27419/000002741922000007/R3.htm
  - FY2021–23 (10-K filed 2024-03-13) — https://www.sec.gov/Archives/edgar/data/27419/000002741924000032/R3.htm
- **S-new-r5-4** Invitae 10-K MD&A (revenue and cost-of-revenue drivers, billable units, cost-of-revenue contents):
  - FY2021 (0001501134-22-000008) — https://www.sec.gov/Archives/edgar/data/1501134/000150113422000008/nvta-20211231.htm
  - FY2022 (0001501134-23-000024) — https://www.sec.gov/Archives/edgar/data/1501134/000150113423000024/nvta-20221231.htm
- **S-new-r5-5** Tesla (fills the "URL to add" entries in S-new-50):
  - FY2024 10-K (0001628280-25-003063) — https://www.sec.gov/Archives/edgar/data/1318605/000162828025003063/tsla-20241231.htm
  - Delivery 8-Ks, Item 2.02, EX-99.1:
    - 2023-01-03 (0001564590-23-000002) — https://www.sec.gov/Archives/edgar/data/1318605/000156459023000002/tsla-ex991_6.htm
    - 2024-01-02 (0000950170-24-000282) — https://www.sec.gov/Archives/edgar/data/1318605/000095017024000282/tsla-ex99_1.htm
    - 2025-01-02 (0001628280-25-000007) — https://www.sec.gov/Archives/edgar/data/1318605/000162828025000007/exhibit991.htm
  - 8-K list with item numbers — https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001318605&type=8-K&dateb=&owner=include&count=40
- **S-new-r5-6** Rivian (replaces the Business Wire and Seeking Alpha entries in S-new-47):
  - 2025 production and deliveries, 8-K EX-99.1, 2026-01-02 (0001874178-26-000002) — https://www.sec.gov/Archives/edgar/data/1874178/000187417826000002/ex-9914q25deliveryproducti.htm
  - Q4/FY2025 results, 8-K EX-99.1, 2026-02-12 (0001874178-26-000007) — https://www.sec.gov/Archives/edgar/data/1874178/000187417826000007/ex-991pressrelease4q25earn.htm
  - Q4 2025 shareholder letter, EX-99.2 — https://www.sec.gov/Archives/edgar/data/1874178/000187417826000007/ex-9924q25shareholderletter.htm
  - 8-K list with item numbers — https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001874178&type=8-K&dateb=20260401&owner=include&count=20
- **S-new-r5-7** Intel Q3 2024 10-Q (0000050863-24-000149; charges in cost of sales, Note 5) — https://www.sec.gov/Archives/edgar/data/50863/000005086324000149/intc-20240928.htm
- **S-new-r5-8** NVIDIA FY2026 10-K (0001045810-26-000021; MD&A "Concentration of Revenue": FY2026 22% and 14%, FY2025 12%, 11% and 11%, FY2024 13%) — https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021/nvda-20260125.htm
- **S-new-r5-9** Microsoft commercial RPO of $625B and about 45% tied to OpenAI, Silicon UK, 2026-01-29 (press, other; grade B; Microsoft's own wording to be read) — https://www.silicon.co.uk/cloud/datacenter/microsoft-ai-spending-2-628544
- **S-new-r5-10** Patatoukas, P. N. (2012), "Customer-Base Concentration: Implications for Firm Performance and Capital Markets", The Accounting Review 87(2):363–392. Read via a summary (other): Berkeley Haas newsroom — https://newsroom.haas.berkeley.edu/research/less-more-unexpected-value-suppliers-have-few-major-customers-2/
- **Clarification of S-new-56** (no new ID): the Brazilian paper is da Costa, Macedo, Yokoyama & de Almeida (2017), "The Determinants of the Life Cycle Stages of Brazilian Public Companies", BBR 14(3), doi:10.15728/bbr.2017.14.3.3. Its stage-transition figures (62% / 30%) come from its own sample of 313 Brazilian listed companies, 2005–12.
- **Clarification of S45** (no new ID): the AEA 2018 paper at S45's link is Asgharian, H. & Liu, L. (2017), "Stock Return Dependence and Product Market Linkages", Lund University / Stockholm University working paper — https://swlb1.aeaweb.org/conference/2018/preliminary/paper/dGQ3hGSZ . Its SOURCES.md entry should carry the title and authors.

---

## Round 6 — CvD calibration and health scores

This round has 8 questions, not the usual 2–4. The critique moved the unfinished parts of the CvD grid here: when CvD switches on, missing rows, the overreaction gauge and how M01 reads M04. The owner can take it in two sittings: 6.1–6.4, then 6.5–6.8.

**Read before presenting this round** (critique 31; status on 2026-10-12)
- **Croux–Rousseeuw small-sample MAD factors (6.2a).** Values read from the revss package source (S-new-r6-3). The 1992 Physica-Verlag chapter is not online, so the recommendation rests on the package's transcription.
- **Mohanram's variance windows (6.3a).** Mohanram's own later paper uses two years of quarterly data (Li & Mohanram 2019, S-new-r6-2). The CXO summary of the 2005 original says five years (S-new-66). The 2005 text was not read: the publisher's copy is paywalled and SSRN refused automated access.
- **Leys et al. outlier bands (S6.2).** Primary postprint read (S-new-63).
- **The Z″ 1.1 / 2.6 zones** belong to Round 4 and are not used here.

### What the research says
1. **The window is set by XBRL**, phased in for periods ending from 2009-06-15 (float above $5B), then 2010 and 2011 (S-new-4).
   - The usable backtest window is about FY2010 to now, roughly 16 years.
   - A 10-year lookback is first available around FY2019–20.
   - Micron's 2001 bust is invisible.
   - Its 2008–09 bust shows only through comparatives. FY2009 gross margin was −9.2% (revenue 4,803, cost 5,243), first filed in the FY2011 10-K on 2011-10-25. Intel's comparatives reach FY2007 (S-new-r6-1).
2. **Overfitting.** With about 20–40 labelled episodes, every extra threshold variant tried raises the false-discovery risk (S-new-62). So calibrate for label stability (does the label survive ±20% threshold moves?) and log every variant tried.
3. **The robust-z method decides small-n results** (figures from S-new-r6-1; worked example A).
   - **Intel 2022 against 4 peers** (AMD, NVDA, TXN, MU), with a −1.5 cut-off:
     - IQR with type-7 quantiles (as `frames.py` uses): −1.71;
     - IQR with type-6 quantiles: −0.82;
     - MAD × 1.4826: −1.92;
     - MAD × 1.4826 × the n = 4 small-sample factor (1.363): −1.41.

     The four methods land on both sides of the line.
   - **Adding Qualcomm** (a product-market peer named in 1.3a) makes n = 5, so z decides instead of the fixed gap. Three of the four methods then agree (−1.64 to −2.09); type 6 gives −1.12.
   - Nine quantile definitions exist, and they differ most at small n (S-new-63, Hyndman & Fan).
   - **Small-n alternatives** (S-new-63):
     - The 1.4826 MAD factor understates scale at small n. Croux & Rousseeuw's factors b_n are 1.196, 1.495, 1.363, 1.206, 1.200, 1.140, 1.129 and 1.107 for n = 2–9, and n ÷ (n − 0.8) above that (S-new-r6-3).
     - Qn and Sn estimators (Rousseeuw & Croux 1993).
     - MAD with a 2.5 cut-off (Leys et al.). The postprint recommends 2.5 by default and cites Miller (1991)'s three bands: 3 is the most conservative, 2.5 moderate, 2 the least.
     - A very-small-sample M-estimator (Rousseeuw & Verboven).
   - **One extreme peer** puts everyone "in the pack" until it is dropped. NVIDIA's FY2024 growth of +125.9% has z +8.97 at n = 5.
   - **Diverging peers can hide a large gap.**
     - In 2025 AMD grew 34.3%, NVIDIA 65.5%, TXN 13.0%, QCOM 10.3% and Micron 45.4% (median +34.3%, MAD 21.3 pp).
     - Intel's −0.5% is 34.8 pp below the median, yet its z is only −0.91.
4. **Look-ahead bias** (S-new-64).
   - Intel recast FY2016 operating income from 12,874 to 13,133 and FY2017 from 17,936 to 18,050 in its 10-K filed 2019-02-01.
   - WDC's FY2023 revenue went from 12,318 to 6,255 after the SanDisk separation (S-new-1).
   - Frames are last-filed (S39).
   - **A peer's comparable period can arrive after the company's own filing** (S-new-r6-1).
     - WDC's quarter ending 2023-09-29 was filed on 2023-11-07, 32 days after Micron's FY2023 10-K (2023-10-06).
     - Until then WDC's latest period was 62 days off, outside the ±45-day TTM tolerance (1.4a).
5. **Survivorship.**
   - Delisting returns are mostly missing and large-negative: about −30% for NYSE/AMEX performance delistings, −55% for Nasdaq (S-new-65).
   - EDGAR keeps dead filers.
   - Whether Tiingo covers delisted tickers is unverified. A dead company's ticker can later belong to a successor or another firm, so a price probe must match dates as well as symbols.
   - Emergence from bankruptcy can break a series. Peabody's 10-K revenue has no 12-month 2017 period (S-new-r6-7). Predecessor and successor stubs after its Chapter 11 are the likely cause; to confirm.
6. **Piotroski F** (S32).
   - Tested on 1976–96 high book-to-market firms, with the edge in small, thinly followed firms.
   - The signals reversed in the 12 years after 1996 (S-new-66, lower-tier journal).
   - Later work uses F to find mispricing, not distress (S-new-66, Piotroski & So).
   - **At a trough, 4 of the 9 signals fail mechanically.** Micron scores 4 in FY2012, 3 in FY2016, 4 in FY2019, 5 in FY2020 and 4 in FY2023 (worked example C).
   - **Piotroski's equity signal is binary:** any common-stock sale scores 0 (EQ_OFFER from Compustat `sstk`; S-new-r6-2, footnote 2).
     - Intel tags stock-plan proceeds every year ($977M, $1,042M, $987M and $771M in 2022–25), so the binary rule scores Intel 0 every year.
     - Intel's basic weighted shares grew 1.2%, 2.0%, 2.1% and 5.8% in those years. The 2025 rise includes the strategic stakes (S-new-68, S-new-r6-1).
7. **Mohanram G** (S33).
   - Low scores returned −17.9% size-adjusted in year 1, against +3.3% for high scores.
   - **The sample is the lowest book-to-market quintile of US firms, 1979–1999** (S-new-66, CXO summary). That is a valuation group, not a cash-flow stage.
   - It is "stronger among large, heavily followed firms" (S-new-66, Piotroski 2005 discussion): the best large-cap evidence of the three scores.
   - **Definitions from Mohanram's later paper** (S-new-r6-2):
     - ROA = income before extraordinary items ÷ assets;
     - cash flow ÷ assets, and accruals;
     - VARROA and VARSGR = standard deviation of quarterly ROA and of quarterly sales growth over the past two years;
     - R&D, capex and advertising, each ÷ assets.

     Each signal is scored against the contemporaneous industry median; the continuous version uses the Fama–French 48 industries. The CXO summary of the 2005 paper gives five-year windows instead.
   - **Advertising is rarely tagged.** AAII drops it and uses a 7-point maximum (S-new-66). Among the six chip companies only Intel and TXN tag `AdvertisingExpense`, and only annually; NVIDIA stopped after FY2020 (S-new-r6-1).
8. **Altman Z** (S34, S-new-36).
   - Adding the 3.25 constant while keeping the 1.1 / 2.6 zones turns distress into "safe". Any Z″ above −2.15 crosses 1.1 (Rivian: −5.37 → −2.12).
   - **Micron FY2023, priced at its 10-K filing date:** the 2023-10-06 close of $69.96 × 1,098.0M cover shares ≈ $76.8B (S-new-r6-5, S-new-r6-1). X4 contributes 2.29 of a Z of 3.43 (1.14 without X4).
   - **Micron FY2022, priced at its filing date** (2022-10-07, $52.91): Z 4.31, of which X4 is 2.11.
   - **The FY2023 balance sheet at the cycle-low close** ($48.88 on 2022-09-26; an illustrative pairing of dates) gives Z 2.74. That is inside the 1.81–2.99 grey zone, with no change in the balance sheet. A price crash lowers Z just as M01 triggers.
9. **Normalized earnings.**
   - Support: profitability reverts (S-new-55); naive extrapolation is priced (S35).
   - Weakness: accounting breaks distort 10-year averages (S-new-67).
   - Real-data problems (S-new-r6-1):
     - **Current revenue is itself cyclical.** Micron's normalized earnings power (10-year margin × current revenue) fell 56.5%, from 7,942 in FY2022 (25.8% × 30,758) to 3,458 in FY2023 (22.3% × 15,540). On the cycle-average revenue base it fell only 11.2% (5,372 → 4,773).
     - **Aggregation matters.** Micron's FY2014–23 margin is 22.3% as a ratio of sums but 18.0% as a mean of ratios.
     - **Decliners keep old margins.** Intel's 2016–25 margin is 16.7% (first-reported; 16.8% after recasts). Times 2025 revenue of 52,853 that gives about $8.8–8.9B, against actual operating income of −$2.2B.
     - **Impairments distort the average** (Invitae 2022: $2,313M).
10. **Regression readings on real data** (worked example B).
    - **MU FY2023:**
      - Q1 peers: WDC files with the SEC; SK hynix and Samsung do not and are missing. Against chip peers Micron is an outlier.
      - Against WDC, revenue fell 49.5% vs 35.2%. That is a −14.3 pp gap while peers fall, a zone the approved table does not assign.
      - Capex −36% trips "cut > 20%", while capex ÷ revenue rose from 39% to 49%.
      - **Trough rule:** the FY2023 low (−9.1%) is below the FY2020 low (30.6%), and the FY2022 high (45.2%) is below the FY2018 high (58.9%). That is one cycle of lower lows and highs, not two: the previous low (FY2016, 20.2%) and high (FY2014, 33.2%) were both lower.
      - ROIC agrees: lows of 1.0% (FY2016), 7.6% (FY2020) and −12.1% (FY2023); highs of 23.6% (FY2014), 54.4% (FY2018) and 19.7% (FY2022).
      - The Q2 FY2023 write-down was $1.43B, with GAAP gross margin of −32.7% (S-new-5). Inventory days were 153, or 235 excluding the write-down (call transcript, other).
    - **INTC:**
      - Company-specific in 2022 (gap −24.9 pp) but *shared* in 2023 (peer median −8.2%), the reverse of the expected drift.
      - Gross margin 55.4% → 42.6% → 40.0% → 32.7% → 34.8% (2021–25).
      - In Intel's XBRL record (from FY2007), 2022's 42.6% is the lowest annual margin and its −20.2% revenue fall the deepest (2009: −6.5%).
      - AMD's x86 server unit share rose from 25.7% to 28.8% (Q4 2024 → Q4 2025; S-new-69). Intel's share is not given; reading it as 100 − AMD assumes a two-vendor market.
      - R&D held. The row-by-row count in worked example B gives AMBIGUOUS for 2022, 2023 and 2025.
    - **Invitae:** fails on trailing burn, as in Round 4.
11. **Filing deadlines** (for the `overdue` state).
    - 10-K: 60, 75 or 90 days after year-end, for large accelerated, accelerated and other filers. 10-Q: 40 days for accelerated filers, otherwise 45 (S88, FRM 1330.1).
    - Rule 12b-25 extends a late 10-K by 15 calendar days and a 10-Q by 5, if the NT form is filed within one business day of the due date (S-new-r6-4).
    - So for any filer status, a compliant report arrives within 105 days of year-end (10-K) or 50 days of quarter-end (10-Q).
    - **Real cases** (S-new-r6-6):
      - Invitae filed no NT 10-K and never filed its FY2023 10-K. Its 8-K 3.01 (2024-02-06) and its 8-K with Items 1.03 and 2.04 (2024-02-14) came first.
      - RadioShack filed an 8-K 2.04 (2014-12-02), an 8-K 1.03 (2015-02-11) and an NT 10-K (2015-04-16), and no 10-K after that.
12. **Market-share data.**
    - No free structured source was found.
    - Mercury Research figures reach us only through the press (S36, S-new-69; grade B).
    - TrendForce memory data are excluded by its terms (S93).
    - Segment revenue against industry totals needs DS12 and DS13, and neither is built.

### Worked examples
**A. Intel revenue growth vs peers** (S-new-r6-1; TTM revenue at the period end nearest calendar year-end; first-reported values)

| Company (period ends used) | 2022 YoY | 2023 YoY |
|---|---|---|
| INTC (2022-12-31, 2023-12-30) | −20.2% (63,054 vs 79,024) | −14.0% (54,228) |
| AMD (calendar) | +43.6% (includes Xilinx) | −3.9% |
| NVDA (FY to 2023-01-29 / 2024-01-28) | +0.2% | +125.9% |
| TXN (calendar) | +9.2% | −12.5% |
| MU (TTM to 2022-12-01 / 2023-11-30) | −8.3% (27,156 vs 29,619) | −40.4% (16,181) |
| QCOM (TTM to 2022-12-25 / 2023-12-24) | +19.2% (42,958 vs 36,036) | −15.5% (36,292) |

Micron's 2021 TTM base (29,619, to 2021-12-02) is now verified.

| Peer set | Median | Intel gap | IQR type 7 | IQR type 6 | MAD × 1.4826 | MAD × 1.4826 × b_n | What decides |
|---|---|---|---|---|---|---|---|
| 2022, n = 4 | +4.7% | −24.9 pp | −1.71 | −0.82 | −1.92 | −1.41 | Fixed gap: company-specific |
| 2022, n = 5 (+QCOM) | +9.2% | −29.4 pp | −2.09 | −1.12 | −1.98 | −1.64 | z (6.2a): company-specific if it persists 2 quarters |
| 2023, n = 4 | −8.2% | −5.8 pp | −0.16 | −0.06 | −0.21 | −0.16 | Fixed gap: shared |
| 2023, n = 5 | −12.5% | −1.5 pp | −0.17 | −0.02 | −0.11 | −0.10 | NVDA (z +8.97) dropped → n = 4 → fixed gap 0.0 pp: shared |
| 2025, n = 5 | +34.3% | −34.8 pp | — | — | −1.10 | −0.91 | z above −1.5 while peers grow: a zone the approved table leaves open (6.5) |

The 2025 peers: AMD +34.3%, NVDA (FY to 2026-01-25) +65.5%, TXN +13.0%, QCOM +10.3%, MU (TTM to 2025-11-27) +45.4%.

**B. Missing rows and confidence: Micron FY2023 and Intel FY2023, row by row** (S-new-r6-1; first-reported values; rules as recommended in 6.4–6.6)

| Row | MU FY2023 (TTM to 2023-08-31; 10-K filed 2023-10-06) | INTC FY2023 (TTM to 2023-12-30) |
|---|---|---|
| **Q1** Revenue vs peers | WDC is the only SEC peer. Until WDC filed on 2023-11-07: "awaiting peer filing" (missing). Then the fixed gap is −49.5% vs −35.2% = −14.3 pp while peers fall → **shared**, flagged `deeper_than_peers` (6.5a) | n = 5; NVDA dropped (z +8.97); fixed gap 0.0 pp while peers fall → **shared** |
| Industry pricing / volume | Missing (DS13 not built) | Missing |
| Inventory days | MU 144 → 181; WDC 115 → 124; rising across peers → **shared** | INTC 133 → 125; peer median change +4 days (AMD +24, NVDA −46, TXN +64, QCOM +4, MU −28). Not rising here → **neutral** |
| Supply response | MU capex −36%, WDC −48% → **shared** | INTC +4%; AMD +21%, TXN +81%, QCOM −39%, MU −38% (NVDA excluded: fallback tag) → mixed → **neutral** |
| Cycle history | FY2009 gross margin −9.2% recovered to 32.0% in FY2010 → **shared** | Deepest XBRL-era decline (2009 revenue −6.5%), so a first deep decline → **company-specific** |
| Q1 result | 4 present, all shared → **shared** (1.00); coverage 4 of 5 | 4 present: shared 1, company-specific 1, neutral 2 → **split** |
| **Q2** Market share | Missing (TrendForce excluded, S93) | Missing (S-new-69 starts at Q4 2024) |
| Gross-margin gap to peers | Only one comparable peer (fewer than 3), so shown but not counted: MU −54.3 pp vs WDC −20.8 pp = −33.5 pp | Gap to peer median −14.3 → −15.5 pp: a change of −1.2 pp → **intact** |
| Trough vs prior trough (GM, ROIC) | Both show one cycle of lower lows and highs, with a higher cycle before it → **intact** | Only one confirmed prior trough (2009, with the 5 pp swing filter) → insufficient history (missing) |
| R&D and capex intensity | R&D 3,114 vs 3-year average 2,793 (+11%); capex ÷ revenue 49.4% vs 37.9% → **intact** | R&D 16,046 vs 15,425 (+4%); capex ÷ revenue 47.5% vs 27.1% → **intact** |
| Moat / challengers | Not applicable until M06 | Not applicable |
| Customer base | Missing (row not yet designed) | Missing |
| Guidance record | Missing (the ledger holds 2025–26 releases only) | Missing |
| Health (F-quality) | 3 of 4 → **intact** | 2 of 4 → **neutral** |
| Q2 result | 3 present, all intact → **intact** (1.00); coverage 3 of 7 | 3 present: intact 2, neutral 1 → **intact** (0.67); coverage 3 of 7 |
| State under 6.6a | **CYCLICAL_TROUGH**, confidence 1.00 (the regression expectation) | **AMBIGUOUS** → review; confidence 0.25 |
| Under 6.6b (missing rows count as not agreeing) | Q2 = 3 of 7 = 0.43 → AMBIGUOUS | AMBIGUOUS |
| Under 6.6c (50% coverage floor) | Q2 coverage 43% → AMBIGUOUS | AMBIGUOUS |
| Under 6.6d (confidence × lower coverage) | CYCLICAL_TROUGH at 0.43 | AMBIGUOUS at 0.11 |

- **INTC 2022.**
  - Q1 is company-specific, 3 of 4: revenue, supply response (peers expanding) and cycle history. Inventory days rose with peers' (shared).
  - Q2 is split: gross-margin gap −11.5 pp (weakening), R&D and capex held (intact), F-quality 2 (neutral).
  - Result: AMBIGUOUS.
- **INTC 2025.**
  - Q1: revenue −0.5% against a +34.3% median (z −0.91: neutral under 6.5a, company-specific under 6.5b). Capex −39% while peers expand (company-specific). Cycle history company-specific; inventory flat (neutral). Under 6.5a, Q1 is split.
  - Q2: capex ÷ revenue 27.7% vs its own 44.0% (weakening); gross-margin gap +3.0 pp (intact); F-quality 3 (intact). An owner-entered share figure from S-new-69 (about −3.1 pp, derived) would add a weakening vote, making it 2 vs 2: split.
  - Result: AMBIGUOUS.
- **What this means for Intel's expectation.** The approved expectation (CYCLE_PLUS_DAMAGE drifting to STRUCTURAL_DECLINE) is not reached from filed data. The rows that would carry it (market share, moat, customers) are the missing ones, so the honest output is AMBIGUOUS → owner review (D8).
- **Micron at its 2022-09-26 price low** read NO_SLOWDOWN: the latest filing (Q3 FY2022) still showed growth.

**C. Health scores at troughs and in decline** (S-new-r6-1)

Micron FY2023 Piotroski F = 4:

| Signal | Value | Point |
|---|---|---|
| ROA | −5,833 / 66,283 = −8.8% | 0 |
| CFO > 0 | 1,559 | 1 |
| ΔROA | 14.8% → −8.8% | 0 |
| Accruals (CFO > ROA) | yes | 1 |
| ΔLeverage | 10.9% → 20.0% of average assets | 0 |
| ΔCurrent ratio | 2.89 → 4.46 | 1 |
| No equity issued (net basic-share growth ≤ 2%) | basic shares 1,112M → 1,093M (−1.7%) | 1 |
| ΔGross margin | 45.2% → −9.1% | 0 |
| ΔAsset turnover | 0.523 → 0.234 | 0 |

All four failing signals are cycle-driven. F-quality (accruals + leverage + liquidity + equity) = 3 of 4.

| Case | F | F-quality | 6.3a (F-quality votes: ≥ 3 intact, 2 neutral, ≤ 1 weakening) | 6.3b (F ≤ 3 = weakening) |
|---|---|---|---|---|
| MU FY2012 (trough) | 4 | 3 | Intact | Intact |
| MU FY2016 (trough) | 3 | 2 | Neutral | **Weakening (wrong for a trough)** |
| MU FY2019 (trough begins) | 4 | 2 | Neutral | Intact |
| MU FY2020 (trough) | 5 | 3 | Intact | Intact |
| MU FY2023 (trough) | 4 | 3 | Intact | Intact |
| INTC 2022 | 4 (3 under the binary equity rule) | 2 | Neutral | Intact (weakening under binary) |
| INTC 2023 | 4 (3 binary); basic shares +2.00%, exactly on the line | 2 | Neutral | Intact (weakening under binary) |
| INTC 2024 | 3 | 2 | Neutral | Weakening |
| INTC 2025 | 6 (strategic stakes repaired leverage and liquidity) | 3 | Intact | Intact |

**NVIDIA Mohanram G** (definitions per S-new-r6-2, with net income for ROA and cash-flow accruals). Peers: INTC, AMD and TXN on calendar years; QCOM and MU on the TTM within 45 days.

| Signal (vs peer median, n = 5) | NVDA FY2023 | Median | Point | NVDA FY2024 | Median | Point |
|---|---|---|---|---|---|---|
| ROA | 10.6% | 4.4% | 1 | 45.3% | 1.3% | 1 |
| CFO ÷ assets | 13.7% | 13.4% | 1 | 42.7% | 6.0% | 1 |
| Accruals ÷ assets (lower scores) | −3.1% | −3.3% | 0 | +2.5% | −5.1% | 0 |
| VARROA, 8 quarters (lower scores) | 2.0% | 1.8% | 0 | 6.6% | 1.7% | 0 |
| VARSGR, 8 quarters (lower scores) | 11.4% | 9.8% | 0 | 31.1% | 10.4% | 0 |
| R&D ÷ assets | 17.8% | 7.4% | 1 | 13.2% | 8.4% | 1 |
| Capex ÷ assets (NVDA on the fallback tag) | 4.5% | 10.3% | 0 | 1.6% | 9.4% | 0 |
| Advertising ÷ assets | Missing | — | — | Missing | — | — |
| **G** | **3 of 7** | | | **3 of 7** | | |

- **NVDA is in Mohanram's population.**
  - Its book-to-market at the FY2023 year-end was about 0.04. Equity was $22.1B against a market value of about $503B (2,470M cover shares × the $203.6 pre-split close on 2023-01-27; S-new-r6-5).
  - Its Dickinson cash-flow signs were (+,+,−), shake-out, in FY2023 and (+,−,−), mature, in FY2024. A cash-flow-stage gate would never score it.
- **G does not separate strong years.** Revenue grew 125.9% in FY2024 and G stayed at 3: the two volatility signals penalise acceleration, and a fabless company never scores the capex point.
- **Under 6.3b** (G ≤ 2 = weakening), NVDA reads intact in both years.

**D. Micron normalized earnings and the overreaction gauge** (earnings from S-new-r6-1; unadjusted closes from S-new-r6-5, to re-check against stored Tiingo bars at build)

| Latest filed quarter (period end) | TTM revenue | 10-yr margin (years) | NEP × current revenue | NEP × 10-yr average revenue | Close | 4-quarter price change | 4-quarter NEP change | Gap | CvD |
|---|---|---|---|---|---|---|---|---|---|
| Q4 FY2021 (2021-09-02) | 27,705 | 23.4% (FY2012–21) | 6,481 | 4,340 | $73.99 | | | | |
| Q1 FY2022 (2021-12-02) | 29,619 | 23.4% | 6,928 | 4,340 | $82.88 | | | | |
| Q2 FY2022 (2022-03-03) | 31,169 | 23.4% | 7,291 | 4,340 | $89.18 | | | | |
| Q3 FY2022 (2022-06-02) | 32,389 | 23.4% | 7,576 | 4,340 | $75.37 | | | | |
| Q4 FY2022 (2022-09-01) | 30,758 | 25.8% (FY2013–22) | 7,942 | 5,372 | $57.31 | −22.5% | +22.5% | −45.1 pp | NO_SLOWDOWN (revenue +11.0%, gross margin +7.6 pp, operating income +54%) |
| Q1 FY2023 (2022-12-01) | 27,156 | 25.8% | 7,012 | 5,372 | $55.49 | −33.0% | +1.2% | −34.3 pp | Active (revenue −8.3%) |
| Q2 FY2023 (2023-03-02) | 23,063 | 25.8% | 5,955 | 5,372 | $56.43 | −36.7% | −18.3% | −18.4 pp | Active |
| Q3 FY2023 (2023-06-01) | 18,173 | 25.8% | 4,692 | 5,372 | $69.09 | −8.3% | −38.1% | +29.7 pp | Active |
| Q4 FY2023 (2023-08-31) | 15,540 | 22.3% (FY2014–23) | 3,458 | 4,773 | $69.94 | +22.0% | −56.5% | +78.5 pp | Active |

- **Price path.** The closing high was $97.36 (2022-01-14) and the closing low $48.88 (2022-09-26), a fall of 49.8%. The low came while the latest filing still showed growth: the quarterly-lag failure mode.
- **Under 6.7a** (gap ≤ −25 pp) the gauge flags Q4 FY2022, when CvD was not yet active, and Q1 FY2023, when CvD was active (that 10-Q was filed on 2022-12-22).
- **The fiscal-year-end comparison** (FY2022 → FY2023: +22.0% vs −56.5%) shows no overreaction at all.
- **Normalized earnings power rises at FY2022** because that year's 31.5% operating margin enters the 10-year average while revenue is still high.

### All cases
1. Peer count: ≥ 10 / 5–9 / < 5 / 0 (all non-SEC).
2. One extreme peer, including when dropping it leaves fewer than 5.
3. Diverging peers that hide a large gap (Intel 2025).
4. A peer's acquisition year.
5. Fiscal vs calendar offsets; 53-week years; a peer's comparable period not yet filed (WDC after Micron).
6. A single, unlike peer (Micron vs WDC).
7. Label stable vs flipping under ±20% threshold moves (Intel 2023 equity growth at +2.00%).
8. No slowdown; revenue up while margins fall (NVDA FY2023); recovery after 2 clear quarters.
9. Peers falling and the company much worse or better; peers growing and the company borderline.
10. Gross-margin gap change between −3 and −5 pp.
11. Indicators that disagree within a question, or fewer than 2 present rows → AMBIGUOUS.
12. Rows without data: market share, industry pricing (DS13), moat (M06), customer base, guidance before the ledger starts.
13. A trough where a write-down distorts gross margin and inventory days.
14. Fewer than 2 confirmed prior troughs → insufficient history; wiggles below the swing filter.
15. ROIC with invested capital ≤ 0 or a goodwill jump; gross margin and ROIC disagreeing.
16. No `GrossProfit` tag; peers' cost of sales defined differently (Amazon's excludes fulfilment).
17. A capex cut as supply response vs as franchise weakening; subject or peer on a fallback capex tag (NVDA, Amazon).
18. F-score at a trough vs in a decline; a recapitalised decliner (Intel 2025).
19. Equity issued through plans, a strategic stake or an acquisition.
20. G-score with advertising missing, fewer than 5 peers or fabless capex; high vs low book-to-market.
21. Z under bubble or crash prices; the Z″ variant.
22. Normalized earnings in a trough, a decline or a growth phase; impairments inside the window.
23. Overreaction gauge before CvD activates, and after the price has recovered.
24. Recast history, a spin-off, or a break across emergence from bankruptcy (Peabody).
25. Overdue filer, with or without an NT form (RadioShack, Invitae); delisting return.
26. Delisted or reused ticker in the price source.
27. Episode before XBRL → out of scope.

**Complete for the rows this round designs.** Known omissions:
- the customer-base row (critique 2, designed elsewhere);
- A2 maintenance capex (not used here);
- foreign and IFRS peers (Round 1, critique 20);
- how enums are encoded in the `signal` table (critique 16);
- PT and ST parameters (an open M01 item).

### Suggestions
- **S6.1 Backtests use `facts_as_of` only** (S1.1).
  - Historical peer values come from each peer's as-of series, never from frames.
  - A peer period counts only from its filing date. Until then the row reads "awaiting peer filing" (missing), and the state re-runs when the peer files.
- **S6.2 Peer statistics.**
  - Store the method, n and b_n with every z, and always show the gap in pp.
  - Below 5 peers the fixed-gap rule decides and z is information only.
  - With 5–9 peers, z = gap ÷ (MAD × 1.4826 × b_n), using the Croux–Rousseeuw factors (S-new-r6-3). From 10 peers, b_n = n ÷ (n − 0.8).
  - Drop any peer with |z| > 3 once and recompute. If fewer than 5 peers remain, the fixed gap decides. 3 is the most conservative of Miller's bands; Leys et al. default to 2.5 (S-new-63).
  - Fallback-tag capex values (NVDA, Amazon) stay out of peer capex statistics (1.2a).
  - 2-quarter persistence unchanged.
- **S6.3 Test set and data plan.**
  - The owner blind-labels before any engine run. Each episode is assigned to a window by its first labelled quarter.
  - Candidates (the owner picks; labels are judgment calls; revenue checks from S-new-r6-7):
    - **Calibration window (FY2017 or earlier), 15 episodes:**
      - Troughs (6): MU FY2012; MU FY2016; Halliburton 2015–16 (revenue −28.1%, −32.8%); Nucor 2015–16 (−22.1%, −1.4%); Caterpillar 2015–16 (−14.8%, −18.0%); Deere FY2015–16 (−20.0%, −7.7%).
      - Cycle plus damage (3): Peabody 2015–16 (−17.4%, −15.9%); Chesapeake 2015–16 (−39.1%, −38.3%); Freeport-McMoRan 2015–16 (−25.9%, −6.6%).
      - Stumbles (3): AMD 2012–15 (−17.4% in 2012, −27.5% in 2015; recovered from 2016); J.C. Penney FY2012 (−24.8%); GoPro 2016 (−26.9%).
      - Declines and failures (3): Sears Holdings 2012–17 (revenue down every year in its XBRL record, 46,770 → 16,702; last 10-K filed 2018-03-23); RadioShack 2012–14 (2013: −19.4%; no FY2014 10-K); Fitbit 2017 (−25.5%).
    - **Test window (2018 or later), 9 episodes:**
      - Troughs (3): MU FY2019–20, MU FY2023, WDC FY2023.
      - Declines and failures (5): INTC 2022–25; Invitae 2022–23; Bed Bath & Beyond 2019–23; Rite Aid 2021–23; J.C. Penney 2017–20 (revenue 12,506 → 10,716; last 10-K filed 2020-03-20).
      - Stumbles (1): Boeing 2019–20.
    - **No-slowdown controls (4), to test activation:** NVDA FY2024, MU FY2018, Caterpillar 2018, Nucor 2021.
  - Report a confusion matrix and label stability; walk forward (calibrate ≤ 2017, test 2018+); log every variant.
  - **Red-flag thresholds stay information-only** until a labelled red-flag set exists (critique 32). This covers Rounds 2–5: earnings quality, dilution, unit economics and the new survival-gate warn band. They are shown but never weighted, and never gate beyond the approved survival gate. Candidates already in this pack: GE 2016–17, Invitae 2021–23, RadioShack 2013–15, Sears 2012–17, Rivian 2022–26, MSTR 2025–26, Target FY2022 and Tesla 2023, with Lockheed and Alphabet as clean controls.
  - **Part 8 data** (critique 35; the Build parts row should carry these counts):
    - About 20 subject companies plus about 5 peers in each of about 12 industries: roughly 70 companies after overlaps.
    - **Fetch:** companyconcept per tag, about 25 tags each. That is about 1,750 requests including 404s, or about 4 minutes at 8 per second. Whole companyfacts would be about 70 requests but 0.2–6 MB each (about 250 MB in total).
    - **Storage:** GE's concept files ran 9–66 KB each, so the set is roughly 30–60 MB. It lives under data/ with a manifest, not in tests/fixtures.
    - **Fixtures:** only MU, INTC, WDC and the chip peers (about 8 companies × 25 tags ≈ 200 small files).
    - **Tiingo probe:** the same run probes Tiingo for the delisted or renamed names (about 10 symbols, within the free tier's 50 requests an hour, S68), matching dates as well as symbols. An episode without prices keeps its EDGAR-based label and gets no overreaction gauge.
- **S6.4 Q2 R&D and capex row.**
  - **Capex on intensity:** capex ÷ revenue against the company's own 3-year average and its peers. Weakening when it falls more than 20% below its own average while peers hold (Intel 2025: 27.7% vs 44.0%).
  - **R&D on level:** R&D dollars against the own 3-year average; weakening when cut more than 20% while peers hold. Intensity would hide a cut, because it rises mechanically in a revenue slump: Micron FY2023 held R&D dollars flat while intensity went from 10.1% to 20.0%.
  - The row is weakening if either part is, and intact if both hold.
  - **Basis:** total capex (the capex concept, with the 1.2 marker), not A2's maintenance estimate, which is not designed yet.
  - A company on the fallback tag (NVDA, Amazon) is compared with its own history on that same tag. Its peer comparison is "not like-for-like" and skipped.
  - The company's own absolute capex cut moves to Q1 "supply response", read together with peers' cuts.
- **S6.5 Trough vs prior trough.**
  - **Turning points** come from the annual series, with a minimum swing of 5 pp of gross margin (starting value, unsourced). Without it, Intel's 1–4 pp wiggles of 2013–17 count as cycles.
  - **Vote:**
    - weakening needs two consecutive cycles of lower lows and lower highs in both gross margin and ROIC;
    - intact when neither shows it;
    - neutral when they disagree.
  - **ROIC definition:**
    - ROIC = NOPAT ÷ average invested capital.
    - NOPAT = operating income × (1 − tax ÷ pretax income, bounded at 0–35%), or operating income alone when pretax income ≤ 0.
    - Invested capital = equity + long-term debt + current debt − cash − short-term investments.
    - `not_meaningful` when invested capital ≤ 0 (buyback-funded deficits).
  - **Concepts:** S1.3 already lists tax, pretax income and current debt. Add `StockholdersEquity` and the short-term investment tags if they are not yet mapped.
  - "Insufficient history" when fewer than 2 confirmed prior troughs are in XBRL (Intel today).
  - Write-down quarters are adjusted with stated amounts, found by FTS5 ("inventory write-down", "lower of cost or net realizable value").
- **S6.6 Normalized earnings.**
  - Two variants side by side: cycle-average margin × current revenue (the approved base, which the gauge uses), and × cycle-average revenue.
  - Ratio-of-sums margin, excluding impairment tags.
  - Always visible (D10). Outside CYCLICAL_TROUGH and AMBIGUOUS it is labelled "not used: <state>" and carries no weight.
  - Prices taken at the same fiscal period ends (S6.12).
- **S6.7 Health scores.**
  - **F-quality is the only health vote in Q2.** It is a 0–4 subscore of accruals, leverage, liquidity and equity: ≥ 3 intact, 2 neutral, ≤ 1 weakening. This is an untested engineering choice, and the bands are starting values, unsourced.
  - **F is shown as information.** Its equity signal is net basic-share growth > 2%, consistent with 3.1.
    - This deviates from Piotroski's binary rule, which scores stock-plan issuance as dilution every year (Intel).
    - 2% is a starting value, unsourced. Intel 2023, at +2.00%, is the label-stability test.
  - **G is shown as information for low book-to-market names** (Mohanram's population), with ≥ 6 of 8 inputs and ≥ 5 peers.
    - Starting rule: B/M in the bottom fifth of the stored peer universe.
    - Definitions per Li & Mohanram, with two-year quarterly windows, labelled as such; the 2005 window is unverified.
    - Show n of 8.
- **S6.8 Z display.** Shown with and without X4, priced at the filing-date close × cover shares, plus a second line at the latest close, labelled.
- **S6.9 CvD activation.**
  - CvD runs when the latest filed quarter shows any of these (the 25% is a starting value, unsourced):
    - TTM revenue down year over year;
    - TTM gross margin down ≥ 3 pp;
    - TTM operating income down ≥ 25%.
  - It switches off after 2 straight quarters with none of these. Otherwise `cvd_state` = NO_SLOWDOWN.
  - **MU:** NO_SLOWDOWN at FY2022 (revenue +11.0%); active from Q1 FY2023 (−8.3%).
  - **NVDA FY2023:** revenue +0.2%, but gross margin fell from 64.9% to 56.9% and operating income from 10,041 to 4,224 → active.
- **S6.10 Row results and confidence.**
  - **Each row returns one of:**
    - a side: shared or company-specific in Q1, intact or weakening in Q2;
    - neutral: present but borderline;
    - missing, with its reason: no data, too few peers, awaiting peer filing, or insufficient history;
    - not applicable: not built in any module yet.
  - **Zones the approved table leaves open** (6.5a):
    - peers falling and the company z ≤ −1 or ≥ 10 pp below → shared, flagged `deeper_than_peers`;
    - peers falling, z ≥ 1 → shared;
    - peers growing and −1.5 < z, or gap within 10 pp → neutral;
    - gross-margin gap change between −5 and −3 pp → neutral.
  - **Gross-margin gap votes only with ≥ 3 comparable peers** (starting value, unsourced).
  - **Majority rule.** A question needs ≥ 2 present rows, and one side must hold ≥ 2/3 of them (starting values, unsourced). Otherwise the question is split and the state is AMBIGUOUS. This reads the approved "indicators that disagree → AMBIGUOUS" as "no clear majority".
  - **Confidence and coverage.** `cvd_confidence` = the lower of the two questions' winning shares. `cvd_coverage` (present ÷ applicable rows, per question) is shown beside it.
- **S6.11 Rows without data.**
  - **Market share:** an owner-entered grade-B series (company, market, period, share, unit or revenue basis, source_ref, date).
    - It votes when two points 4 quarters apart exist: down ≥ 2 pp → weakening, otherwise intact (starting values, unsourced).
    - Market growth is shown when known. With no series, the row is missing.
  - **Industry pricing / volume:** missing until DS13 exists.
  - **Moat / challengers:** not applicable until M06.
  - **Customer base:** designed in its own round; missing until built.
  - **Guidance record:** from S1.7; missing before the ledger's first release.
- **S6.12 Overreaction gauge.**
  - **Window:** closes at the latest filed quarter-end and 4 quarters earlier, against normalized earnings power (approved base) at the same two period ends.
  - **Threshold:** a "large gap" means price change − NEP change ≤ −25 pp (starting value, unsourced; calibrated in 6.1).
  - **Live line:** the latest close against the same base, labelled "after period end".
- **S6.13 Filing status.**
  - `stale` keeps the approved meaning: the last known state, carried while the next report is pending.
  - S1.6's no-filing state is renamed `overdue`: no 10-K within 105 days of year-end, or no 10-Q within 50 days of quarter-end. Those are the deadline plus the Rule 12b-25 extension, for any filer status (S88, S-new-r6-4).
  - An NT 10-K or NT 10-Q shows at once as a note.
  - Bounds by filer status (75/90/105 and 45/45/50 days) become possible once the cover's filer category is read.
- **S6.14 M01 reading.** As in the table "How M01 reads M04 (D27)" below (question 6.8).

### How M01 reads M04 (D27)
| M04 output | Rule 3: tranches after the first | Rule 7: depth beyond 2σ adds strength | Rule 4: exit warning |
|---|---|---|---|
| CYCLICAL_TROUGH, gate pass | Allowed | Yes | — |
| NO_SLOWDOWN, gate pass | Allowed (rule 3's "or no slowdown") | No: depth shown, no added strength | — |
| AMBIGUOUS | Blocked until the owner resolves the review item; the resolution becomes the state | No | — |
| STUMBLE | Blocked (review) | No | — |
| CYCLE_PLUS_DAMAGE, STRUCTURAL_DECLINE | Blocked | No | Yes |
| `stale` (carried state) | The first tranche may use it; later tranches wait for the next filing (approved guard) | As the carried state | As the carried state |
| `overdue` | Blocked | No | Yes |
| Gate fail | Blocked | No | Warning |
| Gate `incomplete` | Blocked, with the missing inputs listed. Round 4 decides which inputs are required (critique 8) | No | — |
| `distress_score`, `financing_pressure` warnings | Shown in the entry plan; never block (D16) | No effect | Listed |

- **Micron at its 2022-09-26 low.** The state was NO_SLOWDOWN, from the Q3 FY2022 10-Q. Rule 3 allowed a tranche and rule 7 added no strength. CvD became active with the Q1 FY2023 10-Q (2022-12-22).
- **4.1a makes the gate more permissive for young firms.**
  - Rivian, at Z″ −5.37, fails the approved gate. Under 4.1a the gate turns on runway (Round 4): 5.5 quarters on cash only (fail), 6.1 with the ABL if tagged, and about 7.5–8.2 pro forma after the July 2026 follow-on.
  - Rivian's revenue and gross margin rose in FY2025 (Round 5), so CvD reads NO_SLOWDOWN. Once a 10-Q shows the raise, rule 3 would allow tranches, without rule-7 strength.
  - That changes a D27 outcome, so question 6.8 asks the owner to confirm it.

### Changes to D-M04-1 in one place
Question numbers are those of this draft; other rounds' revisions may renumber them.

| # | Approved text (M04_FINANCIALS.md) | Proposed change | Where | Evidence |
|---|---|---|---|---|
| 1 | Peer z = (value − median) ÷ (IQR ÷ 1.35) | MAD × 1.4826 × b_n; drop \|z\| > 3 once; store method, n and b_n | 6.2 | Intel 2022 ranges from −0.82 to −2.09 across methods |
| 2 | Fallback (< 5 peers): gap within 10 pp → shared | Shared only when peers fall. Peers growing with the gap within 10 pp → neutral. Peers falling and ≥ 10 pp below → shared + `deeper_than_peers` | 6.5 | MU vs WDC: −14.3 pp |
| 3 | Revenue z row: shared needs −1 < z < 1 with peers falling; company-specific needs z ≤ −1.5 with peers growing | Open zones assigned (S6.10) | 6.5 | Intel 2025: z −0.91 at −34.8 pp |
| 4 | Gross-margin gap: intact at ≥ −3 pp; weakening below −5 pp | −5 to −3 pp → neutral; votes only with ≥ 3 comparable peers | 6.5, 6.6 | MU with WDC as the only peer |
| 5 | Q1 supply response: peers cutting together | Also the company's own absolute capex cut | 6.4 | MU −36% |
| 6 | Q2 R&D and capex: cut > 20% while peers hold | Capex on capex ÷ revenue; R&D on dollar level | 6.4 | MU capex ÷ revenue 39% → 49% |
| 7 | Trough vs prior trough (GM, ROIC): lower lows and highs over 2 cycles | Coded with a 5 pp swing filter; GM and ROIC must agree; write-down adjustment; ROIC defined | 6.4 | MU: one cycle only; Intel: insufficient history |
| 8 | Health score: F ≤ 3 or G ≤ 2 = weakening | F-quality votes; F and G are information; G only for low-B/M names | 6.3 | MU FY2016: F = 3 at a trough |
| 9 | Normalized earnings = cycle-average operating margin × current revenue | Approved base kept for the gauge; second base shown; ratio of sums; impairments excluded; "not used" label outside trough/ambiguous | 6.4 | MU: −56.5% vs −11.2% |
| 10 | Overreaction gauge: window and "large gap" undefined | Same 4-quarter window; ≤ −25 pp | 6.7 | MU Q1 FY2023: −34.3 pp |
| 11 | No state for "no slowdown" (M01 rule 3 assumes one) | NO_SLOWDOWN plus an activation rule | 6.5 | NVDA FY2023; MU FY2022 |
| 12 | Disagreeing indicators → AMBIGUOUS; confidence = share agreeing | 2/3 majority over present rows; missing rows excluded; coverage shown | 6.6 | MU FY2023 vs Intel FY2023 |
| 13 | Market share, industry pricing and moat rows have a source column only | Owner-entered grade-B share or missing; pricing missing until DS13; moat not applicable until M06 | 6.6 | S-new-69; S93 |
| 14 | Survival gate: Altman Z in the distress zone | Removed; becomes the `distress_score` warning | 4.1 | Rivian Z″ −5.37 |
| 15 | Runway = (cash + undrawn credit) ÷ quarterly burn < 6 quarters | Burn = OCF − capex, the worse of TTM ÷ 4 and the last-2-quarter average; restricted cash excluded; warn below 8 | 4.2 | Rivian: 5.5 vs 6.1 |
| 16 | Next-12-month maturities > liquidity | Maturities + 4 × quarterly burn > liquidity | 4.3 | — |
| 17 | Gate triggers: score, runway, maturities | Adds going concern "exists", an unwaived breach, forbearance, 8-K 2.04, reclassification to current, and 8-K 1.03/3.01 | S4.1, 4.4 | Invitae 2024; RadioShack 2014–15 |
| 18 | `survival_gate`: pass/fail | pass/fail/incomplete | S4.1 | — |
| 19 | One gate for all companies | Liquidity-only gate for model-tagged names (issuance-funded, asset-holding) | 3.4 | MSTR |
| 20 | Failure mode "last known state marked stale" | Kept. S1.6's no-filing state renamed `overdue`, bounded by deadline + Rule 12b-25 | S6.13 (and S1.6) | Invitae; RadioShack |
| 21 | INTC 2022–25: expect CYCLE_PLUS_DAMAGE drifting to STRUCTURAL_DECLINE | AMBIGUOUS (review) until the market-share and moat rows exist | 6.6 | Worked example B |
| 22 | Signals out: `cvd_state`, `cvd_confidence`, `survival_gate`, `overreaction_gap`, scores | Additions in the table below | This round | — |

### Signals out (Round 6 additions)
The PT and ST columns mirror the approved table. How enums are encoded in the numeric `signal` table is critique 16, handled with the signal writer (Round 1).

| Signal | Type / range | Meaning | MY | PT | ST |
|---|---|---|---|---|---|
| cvd_state | enum; adds NO_SLOWDOWN | Cycle vs decline class | ✓ | ✓ | info |
| cvd_confidence | 0–1 | Lower of the two questions' winning shares | ✓ | ✓ | info |
| cvd_coverage | two fractions (Q1, Q2) | Present ÷ applicable rows | ✓ | ✓ | info |
| deeper_than_peers | flag | Shared slump, company ≥ 1 robust z or ≥ 10 pp below | ✓ | ✓ | info |
| f_quality | 0–4 | Cycle-neutral F subscore; the Q2 health vote | ✓ | ✓ | info |
| normalized_ep | $, two bases | × current revenue; × cycle-average revenue | ✓ | ✓ | info |
| overreaction_gap | pp | Price change − NEP change over the same 4 quarters | ✓ | ✓ | info |
| filing_status | current / stale / overdue | Age of the last periodic filing | ✓ | ✓ | ✓ |

### Failure modes (rows to add)
| Input | How it can mislead | Guard |
|---|---|---|
| Robust z, n < 10 | The method flips the label: Intel 2022 at n = 4 reads −0.82, −1.41, −1.71 or −1.92 | Fixed gap below 5; MAD × b_n; method, n and b_n shown |
| One extreme peer | Inflates the spread so everyone is "in the pack" (NVDA 2023: z +8.97) | Drop at \|z\| > 3 once; fixed gap if fewer than 5 remain |
| Diverging peers | High dispersion hides a large gap (Intel 2025: −34.8 pp at z −0.91) | Gap in pp always shown; neutral zone; optional floor (6.5b) |
| Peer filing lag | The comparable peer quarter arrives weeks later (WDC, 32 days after Micron's 10-K) | "Awaiting peer filing"; re-run when the peer files |
| One unlike peer | Micron vs WDC alone gives a gross-margin gap of −33.5 pp (DRAM vs hard drives and flash) | Gross-margin gap votes only with ≥ 3 comparable peers |
| 53-week year | Growth inflated by about 2% | Flag; scale by days |
| Recasts and spins | WDC FY2023 $12.3B → $6.3B on "latest" | First-reported as-of values in backtests |
| Bankruptcy emergence | No 12-month period across the break (Peabody 2017) | Stubs never summed; insufficient history across the break |
| Concept coverage start | Micron gross profit starts later than revenue | History depth per concept |
| Inventory write-down | Gross margin −32.7%; inventory days understated (153 vs 235) | Stated amount attached; adjusted reading when disclosed |
| Capex cut | One number drives both Q1 supply response and Q2 weakening | Q2 on intensity; Q1 on absolute cut |
| Capex fallback tag | NVDA and Amazon report a broader tag | Kept out of peer capex statistics; own history on the same tag |
| Gross-margin definitions | No `GrossProfit` tag; cost of sales defined differently (Amazon) | Revenue − cost of revenue where tagged; owner confirms comparable peers |
| Turning points | 1–4 pp wiggles count as cycles (Intel 2013–17) | ≥ 5 pp swing filter |
| ROIC | Invested capital ≤ 0 after buybacks; goodwill jumps after acquisitions | `not_meaningful`; votes only together with gross margin |
| F-score at trough | 4 of 9 signals are cycle-driven (MU FY2016: F = 3) | F-quality subscore votes; F is information |
| Equity signal | The binary rule scores plan issuance as dilution every year (Intel); +2.00% sits on the line | Net basic-share growth > 2%; label-stability check |
| G-score | Volatility signals penalise acceleration (NVDA FY2024: 3 of 7); fabless never scores capex; advertising untagged | Information only; n of 8 shown; low-B/M names only |
| Normalized earnings | Cyclical revenue base; decliners keep old margins; impairments | Two bases; "not used" label outside trough/ambiguous; impairments excluded |
| Price vs earnings power | Mismatched windows fake an overreaction; fiscal-year ends miss the setup (MU) | Same 4-quarter window; live line labelled |
| Missing rows | Unbuilt rows read as disagreement (everything AMBIGUOUS) or disappear unseen | Excluded from the vote; coverage shown |
| Overdue filer | A dead company keeps its last state (Invitae, RadioShack) | `overdue` at deadline + Rule 12b-25 extension; 8-K 1.03 and 3.01 fail the gate first |
| Delisted prices | Tiingo coverage unverified; tickers reused | Live probe with date match; EDGAR-only label without the gauge |

### Questions
**6.1 Test set**
- (a) *Recommended.* The owner blind-labels the 24 XBRL-era episodes in S6.3 before seeing engine output, as for the M02 precision set (D-M02-40): 15 calibration and 9 test episodes across about 12 industries, plus 4 no-slowdown controls. Calibrate on episodes starting FY2017 or earlier; test on 2018 onward. Red-flag thresholds from Rounds 2–5 stay information-only until a labelled red-flag set exists. Why: the calibration half now holds troughs, damage, stumbles and declines, so every state is seen before the test.
- (b) Semiconductors only, about 12 episodes. Gets wrong: the listed semiconductor episodes are 5 troughs, one stumble (AMD) and one decline (Intel, in the test window), so calibration would see almost no damage or decline.
- (c) The 3 current cases now; grow later. Gets wrong: thresholds would be tuned and tested on the same three names (MU, INTC, Invitae).

**6.2 Few-peer statistics**
- (a) *Recommended.* MAD × 1.4826 × the Croux–Rousseeuw factor for n, with method, n and factor shown. Below 5 peers the fixed gap decides and z is information. Any peer with |z| > 3 is dropped once. Why: at n = 4 the methods put Intel 2022 on both sides of −1.5 (−0.82 to −1.92); at n = 5 three of four agree, and the NVDA 2023 outlier is removed before it widens the pack.
- (b) Keep IQR type 7; z decides at every n, flagged low confidence. Gets wrong: at n = 4, Intel 2022 is company-specific under type 7 (−1.71) but not under type 6 (−0.82) or MAD with the factor (−1.41), so the label depends on a quantile convention.
- (c) Qn/Sn with small-sample factors. Gets wrong: no figure is computed here, so the owner would choose without seeing Intel's result; at n = 4–5, Qn rests on only 6–10 pairwise differences.

**6.3 Health scores**
- (a) *Recommended.* As in S6.7:
  - F-quality (0–4) is the only health vote: ≥ 3 intact, 2 neutral, ≤ 1 weakening (starting values, unsourced, untested).
  - F is information, with net basic-share growth > 2% as its equity signal (a deviation from Piotroski's binary rule).
  - G is information for low book-to-market names with ≥ 6 of 8 inputs and ≥ 5 peers, using Li & Mohanram's definitions.

  Why: F ≤ 3 calls Micron's FY2016 trough "weakening", and the binary equity rule scores Intel's stock-plan issuance as dilution every year.
- (b) F and G as approved (F ≤ 3 or G ≤ 2 = weakening). Gets wrong: MU FY2016 (F = 3) reads weakening at a trough. Intel 2022–23 read weakening only under the binary equity rule. NVDA's G of 3 of 7 in its strongest year shows G does not separate cases here.
- (c) Drop both from the grid; show only. Gets wrong: Q2 loses its only balance-sheet row, and MU FY2023's Q2 falls to 2 present rows.

**6.4 Corrections to the approved profile** (D-M04-1; the full list is in "Changes to D-M04-1 in one place")
- (a) *Recommended.* All four:
  - normalized earnings on both bases (the gauge keeps the approved base), shown with its reason outside CYCLICAL_TROUGH and AMBIGUOUS;
  - capex judged on capex ÷ revenue (total capex, not A2 maintenance), absolute cuts moved to Q1, R&D judged on dollar level;
  - the trough rule coded with 5 pp turning points over 2 cycles and a write-down adjustment;
  - ROIC kept and defined (NOPAT ÷ average invested capital), with gross margin and ROIC required to agree.

  Why: each fixes a misreading in Micron's or Intel's real data; Micron's gross margin and ROIC agree (one cycle of lower lows and highs).
- (b) As (a), but drop ROIC and use gross margin only (recorded as a D-M04-1 change). Gets wrong: no difference for MU or INTC, which agree or lack history, but overbuilding that shows in ROIC before margins would be missed.
- (c) The normalized-earnings change only. Gets wrong: Micron's FY2023 capex cut reads as franchise weakening while capex ÷ revenue rose from 39% to 49%; Intel's small 2013–17 wiggles count as cycles.
- (d) Keep the approved profile as written. Gets wrong: as (c), and normalized earnings shows only the −56.5% base, not the −11.2% one.

**6.5 CvD activation and open zones**
- (a) *Recommended.* Activation per S6.9 (revenue down, gross margin down ≥ 3 pp, or operating income down ≥ 25%); otherwise NO_SLOWDOWN. Open zones assigned per S6.10. Why: MU FY2023 (−14.3 pp against a falling WDC) stays a trough; NVDA FY2023 (revenue +0.2%, gross margin −8.0 pp) activates; borderline rows lower confidence instead of forcing a side.
- (b) As (a), plus a fixed-gap floor beside z: peers growing and a gap ≥ 10 pp below → company-specific even when z > −1.5. Gets wrong: it reads Intel 2025 (−34.8 pp, z −0.91) as company-specific, which may be right, but it partly undoes D-M04-1's dispersion scaling in high-dispersion years.
- (c) Activation on revenue only (TTM down year over year). Gets wrong: NVDA FY2023 never activates, although gross margin fell 8.0 pp and operating income 58%.
- (d) Peers falling and the company far below → company-specific. Gets wrong: MU FY2023 becomes STUMBLE.

**6.6 Missing rows and confidence**
- (a) *Recommended.* Per S6.10–S6.11:
  - missing and not-applicable rows leave the denominator;
  - a question needs ≥ 2 present rows and a 2/3 majority, otherwise AMBIGUOUS;
  - `cvd_confidence` is the lower winning share, with coverage shown beside it;
  - market share comes from an owner-entered grade-B series, otherwise missing;
  - industry pricing is missing until DS13; moat is not applicable until M06.

  Why: MU FY2023 → CYCLICAL_TROUGH at 1.00, with coverage 3 of 7 shown; Intel → AMBIGUOUS → review.
- (b) Missing rows count as not agreeing. Gets wrong: MU FY2023 (Q2 = 3 of 7 = 0.43) → AMBIGUOUS; nearly every name would sit in review while four Q2 rows are unbuilt.
- (c) As (a), plus a 50% coverage floor per question. Gets wrong: MU FY2023 (Q2 coverage 43%) → AMBIGUOUS.
- (d) As (a), with confidence multiplied by the lower coverage. Gets wrong: no state changes, but MU's trough reads 0.43, mixing agreement and data depth in one number.

**6.7 Overreaction gauge**
- (a) *Recommended.* As in S6.12: price change against normalized-earnings-power change over the same 4 quarters ending at the latest filed quarter; a large gap is ≤ −25 pp (starting value, unsourced; calibrated in 6.1); plus a labelled live line. Why: on Micron it flags Q4 FY2022 (−45.1 pp, CvD not yet active) and Q1 FY2023 (−34.3 pp, CvD active: the setup), then clears as the price recovers (+78.5 pp at FY2023).
- (b) Drawdown from the trailing 52-week closing high to the latest close, against the NEP change over the latest 4 filed quarters. Micron at the 2022-09-26 low: −49.8% vs +30.8% = −80.6 pp. Gets wrong: the windows differ (price runs to today, earnings to the last filing), the mismatch in the failure-mode table, so the gap is largest before any filing shows the slump.
- (c) Fiscal-year ends only. Micron FY2022 → FY2023: +22.0% vs −56.5% = +78.5 pp. Gets wrong: misses the Q1 FY2023 setup entirely.
- (d) Show the gap with no threshold. Gets wrong: "CYCLICAL_TROUGH + a large gap", the setup D27 refers to, stays undefined.

**6.8 How M01 reads M04 (D27)**
- (a) *Recommended.* As in the table "How M01 reads M04":
  - only a gate pass plus CYCLICAL_TROUGH adds strength beyond 2σ;
  - NO_SLOWDOWN allows tranches without that strength;
  - AMBIGUOUS, STUMBLE, CYCLE_PLUS_DAMAGE, STRUCTURAL_DECLINE, `overdue`, a gate fail and a gate `incomplete` all block tranches;
  - distress and financing warnings never gate.

  The owner also confirms the Rivian consequence of 4.1a. Why: D27 grants the stronger signal only when both gates pass, and any other reading weakens it.
- (b) As (a), but AMBIGUOUS allows tranches with a warning. Gets wrong: Intel 2022–23 (AMBIGUOUS) would get tranche adds during the decline that rule 3 guards against.
- (c) As (a), but a `distress_score` in the distress zone also withholds rule-7 strength. Gets wrong: no current case changes (Micron's Z is 3.43; Rivian is NO_SLOWDOWN), but it brings back, for rule 7, the score whose 15–20% Type II error 4.1a removed.

### New sources added in this section
- **S-new-r6-1** SEC XBRL companyfacts, checked 2026-10-12. Pattern: `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`.
  - Companies: AMD (CIK0000002488), NVIDIA (CIK0001045810), Texas Instruments (CIK0000097476), Qualcomm (CIK0000804328), Western Digital (CIK0000106040), Intel (CIK0000050863), Micron (CIK0000723125).
  - Concepts used: revenue tags, cost of goods sold, gross profit, operating income, net income, pretax income, income tax, operating cash flow, PP&E payments and `PaymentsToAcquireProductiveAssets`, R&D, advertising, basic and diluted weighted shares, total and current assets and liabilities, equity, retained earnings, long-term and current debt, cash, short-term investments, inventory, and dei cover shares.
  - Example: https://data.sec.gov/api/xbrl/companyfacts/CIK0000804328.json
- **S-new-r6-2** Li, K. & Mohanram, P. (2019), "Fundamental Analysis: Combining the Search for Quality with the Search for Value", Contemporary Accounting Research 36(3):1263–1298 — https://ideas.repec.org/a/wly/coacre/v36y2019i3p1263-1298.html ; working-paper PDF, whose footnotes 2–3 define the FSCORE and GSCORE variables — https://www.ivey.uwo.ca/media/3775546/mohanram.pdf
- **S-new-r6-3** revss R package source, small-sample constants including Croux & Rousseeuw's MAD factors ("CR") — https://github.com/cran/revss/blob/master/R/revConstants.R ; primary record (not read): Croux, C. & Rousseeuw, P.J. (1992), "Time-efficient algorithms for two highly robust estimators of scale", in Computational Statistics vol. 1, Physica-Verlag, 411–428 — https://repository.uantwerpen.be/link/irua/2722
- **S-new-r6-4** Rule 12b-25, Notification of inability to timely file (17 CFR 240.12b-25) — https://www.law.cornell.edu/cfr/text/17/240.12b-25
- **S-new-r6-5** Yahoo Finance daily price history, unadjusted and split-adjusted closes for MU and NVDA, read 2026-10-12 (other; re-check against stored Tiingo bars at build) — https://finance.yahoo.com/quote/MU/history/ ; data endpoint https://query1.finance.yahoo.com/v8/finance/chart/MU
- **S-new-r6-6** EDGAR submissions histories, read 2026-10-12: Invitae (CIK0001501134) — https://data.sec.gov/submissions/CIK0001501134.json ; RadioShack / RS Legacy Corp (CIK0000096289) — https://data.sec.gov/submissions/CIK0000096289.json
- **S-new-r6-7** SEC XBRL companyconcept revenue for test-set candidates, read 2026-10-12. Tags: `Revenues`, `SalesRevenueNet`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueGoodsNet`; 10-K, 12-month periods, first filed.
  - Companies: J.C. Penney / Old Copper Company (CIK0001166126), Sears Holdings (CIK0001310067), GoPro (CIK0001500435), Fitbit (CIK0001447599), Peabody Energy (CIK0001064728), RadioShack (CIK0000096289), Freeport-McMoRan (CIK0000831259), Caterpillar (CIK0000018230), Deere (CIK0000315189), Chesapeake / Expand Energy (CIK0000895126), Halliburton (CIK0000045012), Nucor (CIK0000073309).
  - Example: https://data.sec.gov/api/xbrl/companyconcept/CIK0001310067/us-gaap/Revenues.json

## Build parts (proposal)
Each part is one conversation at Medium effort. High is used only if a design question arises. Claude cannot call SEC during builds, so the owner runs every live check and sends back a short log.

### What the research says
1. **How M02 was built** (`docs/M02_BUILD_LOG.md`):
   - One conversation per part. Each part ended with one combined live check run by the owner; fixture tests covered the rest.
   - Each M02 area had its own script with a local re-run flag: `run_money.py`, `run_suppliers.py`, `run_financing.py`, `run_seasonal.py`. `run_live.py` only wraps `pytest -m live`.
   - Every live log found new wording, so parts needed two to four live rounds. Local re-runs kept those rounds cheap: part 6's fourth round took 140 requests in 47 s.
   - Each screen was mocked up on real stored data and approved before it was built (D-UI-4; parts 3, 5b, 6).
2. **The lock.**
   - `engine.store.lock.run_script` takes `data/refresh.lock`, with a heartbeat and a stale check (D-M02-51).
   - The rate limiter works per process. Two processes each pacing at 5/s would reach SEC's 10/s limit (S121).
   - `run_live.py` already takes the lock (`scripts/run_live.py`).
3. **Time budget.**
   - The logon task stops at 3 hours (D-M02-12, S120).
   - The last three refreshes took 6.7, 1.5 and 6.2 minutes. Source: start time in the header vs the time each report was written, in `logs/refresh_20261010-211831.txt`, `logs/refresh_20261011-203412.txt` and `logs/refresh_20261012-020611.txt`.
   - SEC pace is 5/s. The 16-company M00 backfill made about 4,000 requests in about 15 minutes, roughly 265 a minute (D-SEC-18).
   - EFTS: 48 queries took 43 s (S-new-bp-4).
   - Tiingo's free tier allows 50 requests an hour, 1,000 a day and 500 symbols a month. The scheduled run stops at 40 an hour and spaces requests 3 s apart (S68, D-UI-19).
4. **File sizes decide the fixture format.**
   - Companyfacts files for 14 watchlist companies run from 0.2 to 5.2 MB: 45 MB in total, median 3.7 MB. GE's is 6.1 MB (S-new-bp-3).
   - GE's 15 companyconcept files total 434 KB, about 29 KB per tag (S-new-1).
5. **Some data is already stored at no extra cost.**
   - **Filing-fee facts.** `xbrl_facts.store_facts` keeps every companyfacts taxonomy (`src/engine/sec/xbrl_facts.py`), including `ffd` filing-fee facts.
     - In the watchlist files they appear only for filings from 2026-04-08 on.
     - Example: Intel's 424B5 0001193125-26-345221 (filed 2026-08-12) shows a total offering of $22,999,999,890 and a fee of $3,176,299.98.
     - They cover 17 of the watchlist's 125 424Bs from the last 3 years. Strategy has none (S-new-bp-3).
   - **Active filers.** `themes/universe.py` stores EDGAR's quarterly form indexes, which list every 10-K/10-Q filer. That filters peer proposals to active filers with no new request.
   - **Instances are not kept.** M02's instance reader stores only non-dimensional extension facts and keeps no file (`moneyflow/instance.py`: "the large file is not cached"). Dimensional facts therefore need a fresh read. The cost is known: M02's money live check read 113 instances in a run of about one minute (`logs/money_20261009-181912.txt`).
6. **One cover-page (R1) request serves two parts** (S-new-bp-5).
   - It carries the per-class cover shares (Part 1) and the error-correction flag (Part 3).
   - It exists for old filings too.
7. **Data-layer surprises found while counting:**
   - **GFS** files 20-F and 6-K in `ifrs-full`.
     - Its companyfacts holds 5 20-F and 10 6-K accessions and no 10-K/10-Q.
     - Quarterly figures arrive on XBRL 6-Ks; for example, the 6-K of 2026-08-05 covers the quarter to 2026-06-30.
     - A 10-K/10-Q-only filter (S1.1) drops GFS.
     - `refresh.FACT_FORMS` lists neither 6-K nor 10-KT, so a 6-K never forces a facts sync; only the 7-day backstop does (`src/engine/refresh.py`).
   - **MSTR's SIC is 6199** (finance services). A SIC 6000–6799 exclusion would drop it from every score.
   - **History sits under other CIKs:**
     - Google Inc. (0001288776) filed 10-K/10-Q until 2016-02-11.
     - Marvell Technology Group (0001058057) filed until 2021-03-16.
     - INFQ's CIK belonged to the SPAC Churchill Capital Corp X until its de-SPAC 8-K of 2026-02-17 (S-new-bp-3).
   - **`signal` is keyed by ticker** (migration 0001 primary key: ticker, module_id, signal, timeframe, as_of). Tickers get recycled:
     - Beyond, Inc. renamed itself Bed Bath & Beyond, Inc. and was to trade as BBBY from 2025-08-29.
     - The SEC record now names that CIK Neighborhood Intelligence, Inc. (NXH) (S-new-bp-2).
   - **Delisted prices.** Tiingo's symbology page says, "Tiingo supports delisted data for tickers that have not yet been recycled." It also says delisted symbols may end in a digit (S-new-bp-1). The supported-tickers file lists current coverage (S69).

### Worked example — sizing the live checks from real counts
**Restatement-walk volume** (S-new-bp-3).
- Method: per tag; fiscal-year and discrete-quarter values of revenue, net income and CFO; periodic forms only.
- A step is a change larger than max(0.5% of the value, $1M).

| Company | Steps | Filings that introduced them | Revenue/CFO steps with NI unchanged |
|---|---|---|---|
| AMZN | 33 | 12 | 11 |
| MSFT | 13 | 6 | 2 |
| BA | 12 | 5 | 1 |
| MSTR | 11 | 7 | 8 |
| AAPL | 9 | 3 | 3 |
| META | 6 | 1 | 2 |
| INFQ | 5 | 2 | 0 |
| TSLA | 4 | 4 | 2 |
| INTC / NVDA | 3 / 3 | 2 / 1 | 3 / 0 |
| GOOG | 2 | 1 | 2 |
| MU, MRVL, SPCX | 0 | 0 | 0 |
| **Watchlist** | **101** | **44** | **34** |
| GE (fixture) | 142 | 45 | 87 |

Limits of this count:
- GFS (`ifrs-full`) was not walked.
- MU's 2018 tag switch is invisible to a per-tag count.
- The full concept list from S1.3 will add more steps.

**Full-text history** (Part 4; S-new-bp-4). Three phrases × 16 CIKs, 10-K and 10-Q forms, 2001-01-01 to 2026-10-12. 48 queries took 43 s.

| Phrase | Documents | Filings | Where |
|---|---|---|---|
| "substantial doubt" | 7 | 6 | TSLA 2, MU 2, NVDA 1, INFQ 1 |
| "forbearance" | 12 | 10 | TSLA 2, MU 2, MSTR 2, NVDA 2, MSFT 1, INTC 1 |
| "not in compliance" | 124 | 120 | NVDA 66, INTC 13, META 13, MU 11, MSFT 10, TSLA 3, AAPL 2, BA 1, SPCX 1 |

- No watchlist company is in going-concern trouble today, so these hits are other uses (inference). They are a baseline for the classifier, not alerts.
- Predecessor CIKs were not searched.

**Filing events, 2023-10-12 to 2026-10-12** (submissions, S-new-bp-3):
- **Items on the `events.py` red-flag list:** 6 events in 3 years.
  - MSFT 1.05 (2024-01-19, amended 2024-03-08).
  - INTC 2.05 three times, each filed with 2.02 results.
  - INFQ 3.01 (2026-02-03) and 4.01 (2026-03-26, amended 2026-03-31), around its de-SPAC.
  - Also one NT 10-Q: INFQ, 2026-08-17.
- **Item 3.03:** MSTR 6, each with 5.03; BA, GOOG, INFQ and SPCX 1 each.
- **Item 1.02:** MSTR 3, MU 2, AMZN 1, TSLA 1.
- **Item 3.02:** MSTR 6, INTC 5, MRVL 4, SPCX 3, INFQ 2.
- **424B filings:** 125 in all. MSTR 30, GOOG 28, AMZN 13, MRVL 9, INFQ 9, INTC 8, BA 6, META 6, MU 6, GFS 4, AAPL 2, NVDA 2, MSFT 1, SPCX 1, TSLA 0.

**R1 cover pages** (S-new-bp-5):
- **Meta FY2025 10-K:** Class A 2,187,177,748 + Class B 342,377,716 = 2,529,555,464 shares as of 2026-01-23. Error-correction flag: false.
- **MicroStrategy Q2 2011 10-Q:** Class A 8,217,394 + Class B 2,492,830 shares as of 2011-07-27. These counts predate the 2024 10-for-1 split, so the split guard must cover cover counts too.

**Live-check budget per part.** Rows marked "estimate" depend on the owner's peer and episode choices. Times use the D-SEC-18 rate and the measured EFTS and instance runs; downloads of large files dominate.

| Part | Owner command | SEC requests | Other | Time |
|---|---|---|---|---|
| 1 | `run_financials.py probe` | 162 R1 pages: the XBRL 10-K/10-Q accessions of GOOG 44, META 57, MSTR 61. Plus 2 WDC companyconcept files. Plus 17 companyfacts files (~50 MB) only if the facts parser changes. | — | about 1 min |
| 2 | `run_financials.py peers` | Up to 90 browse-by-SIC pages (9 watchlist SICs × at most 10; starting cap). Plus companyfacts for confirmed peers: about 40–50, ~150–185 MB at the median (estimate). | Active-filer filter from stored form indexes: 0 | 1–2 min |
| 3 | `run_financials.py flags` | Up to 36 R1 pages: 48 watchlist 10-Ks filed since 2023, less the 12 already read in Part 1. Plus 44 later-filing documents (B.3a). Plus about 8 GE companyconcept files. | — | about 1 min |
| 4 | `run_financials.py gate` | 48 EFTS queries. Up to 143 hit documents, less any already stored. About 24 companyconcept files (Rivian, Invitae). | — | 1–2 min |
| 5 | `run_financials.py issuance` | 4 frames, 2.8 MB measured: basic weighted shares CY2024 and CY2025, public float at Q2 2024 and Q2 2025. Plus up to 216 requests: index + fee exhibit for each of the 108 424Bs without `ffd` facts. | — | about 1 min |
| 6 | `run_financials.py quality` | 13 prior annual reports (12 10-Ks + GFS's prior 20-F). Plus 3 companyconcept files (GE contract tags, Lockheed). | FTS5 scan, local | under 1 min |
| 7 | `run_financials.py units` | About 160 instances (3 years × 4 filings; M02 read 113 in about a minute). Up to 60 EX-99.2 files (4 releases × configured companies). About 25 requests for the RIVN backfill. About 4 Target companyconcept files. | — | 1–2 min |
| 8 | `run_financials.py cvd --backtest` | About 50–80 companyfacts: 11 non-watchlist episode companies + 40–70 distinct peers, ~185–300 MB (estimate). | Tiingo: at most 22 requests for at most 11 symbols (≈ 66 s at 3 s spacing); about 18 of the 480-symbol month are used today | 2–4 min |

One-off total: about 1,130–1,190 SEC requests across the eight parts.

**Logon refresh after all parts** (B.2a; estimate):

| Fetch | Requests per year |
|---|---|
| R1 page per new 10-K/10-Q/20-F (17 XBRL filers × 4) | ~70 |
| Peer companyfacts when the daily index shows a peer 10-K/10-Q | 160–200 |
| Instances | ~70 |
| EX-99.2 | ≤ 60 |
| Fee exhibits, only where `ffd` facts are missing (MSTR-like) | ~20 |
| Frames | 2 |
| **Total** | **≈ 380–420** |

- The heaviest earnings-season day is about 40 requests, about 20 of them companyfacts (≈ 75 MB).
- That is under a minute, against runs of 1.5–6.7 minutes and a 3-hour limit.

### All cases
1. **Logon-only runs.** The PC is off overnight, so every scheduled job runs during the owner's session (D-M02-12).
2. **Task killed at the 3-hour limit or at shutdown.** The stale lock is cleared, and each M04 step is idempotent and resumable: pending items stay pending.
3. **Owner script and refresh both want SEC.** The lock goes to one. The other names the holder and exits; local-only steps wait instead.
4. **SEC 429 or block page mid-backfill.** A budget stop ends the batch, the rest stays pending, and the stop is reported (D-SEC-18, D-UI-8).
5. **Tiingo cap hit during Part 8's probe.** A budget stop ends the batch; 8 requests an hour stay reserved for the app.
6. **First run of a history scan** (walk: 101 steps; EFTS: 136 filing hits). It becomes a baseline and is not queued (D-M02-58).
7. **New wording in a live log.** Re-run locally with `--no-sec`; expect two to four rounds.
8. **Non-watchlist fixture companies** (GE, Rivian, Target, Invitae, WDC, Lockheed). Companyconcept files are captured by a named part's live check (SB.6).
9. **Delisted names and recycled tickers.** Delisted: Invitae, Bed Bath & Beyond, Rite Aid, J.C. Penney. Recycled: BBBY. Rows are keyed by CIK, and prices are matched by date range.
10. **Foreign filer with quarterly XBRL 6-Ks in `ifrs-full`** (GFS). Handled by the form list and the facts trigger (SB.11).
11. **Fund without XBRL** (ETV files N-CSR). Labelled "fund: not scored"; no fetches.
12. **SIC that misplaces a company** (MSTR, 6199). Part 2 sets the model tag before any score is computed.
13. **History under a predecessor CIK** (Google Inc., Marvell Technology Group) **or a SPAC shell** (INFQ). Linked to the predecessor, or labelled "history starts <date>".
14. **Fee facts missing from companyfacts** (before 2026-04, or MSTR). Fetch the exhibit.
15. **A design answer shrinks a part** (e.g. 5.4c defers segments). That part's live check drops those fetches.
16. **A new package** (EdgarTools, if Part 7 adopts it). `uv add` needs owner approval (D24).
17. **Owner merges or switches branch mid-session.** Check the branch before every commit.
18. **Engine DB growth from peers and episode companies** (about 3.7 MB of JSON each). Each log prints row counts.
19. **New filings during a live check.** As-of reads keep results reproducible, and the log names the new filings.
20. **Calibration results that suggest new thresholds.** They go to a High-effort review with sources (D6), not into a Part 8 edit.

These cases are complete for the plan as proposed. Known omissions:
- The owner's bandwidth is not measured.
- The size of engine.db is not measured (Claude may not read `data\`).
- Gemini spend is not budgeted here; an estimate is shown before every call (D-UI-11).

### Suggestions
- **SB.1 Before Part 1 (docs only, on the review branch):**
  - Record D-M04-2 onward in M04_FINANCIALS.md, with one table of every change to D-M04-1.
  - Assign S122 onward to the S-new IDs and fix the duplicate S101 (S1.9).
  - Open `docs/M04_BUILD_LOG.md` (parts table, notes per part, live-check lines), as M02 did.
- **SB.2 Workflow.** Branches `m04-part1` … `m04-part8` from main. Order per part: mock-up → build with fixture tests → owner live check → PR → merge commit (DESIGN workflow).
- **SB.3 Parts** (table below). Each part:
  - runs at Medium effort and has one combined live check, budgeted above;
  - ships fixture tests;
  - adds its rows to the Financials tab. A row that is not used shows the reason and is never hidden (D10);
  - adds its signals to M04's "Signals out" table (MY/PT/ST columns) and to the "Timeframe parameters" table.
- **SB.4 Script and lock** (B.1).
- **SB.5 Refresh step.** Add `financials_step` to `run_refresh.py` after `financing_step`. It does per-new-filing work only (B.2) and is timed in the run report.
- **SB.6 Fixtures as companyconcept files per tag**, mapped to parts (table). About 40 files, roughly 1.2 MB at GE's 29 KB average, instead of six companyfacts files (GE's alone is 6.1 MB).
- **SB.7 Mock-ups first (D-UI-4).**
  - Part 1: the Financials tab with every planned M04 row, on real stored data: MU FY2022–23, META cover shares by class, AMZN's capex fallback.
  - Parts 2–7: their own rows and review layouts.
  - Part 8: the M04 tab, with MU and INTC grids built from Round 6 values.
- **SB.8 Docs in the same commit as the code** (table).
- **SB.9 Review kinds and caps** (B.3; table).
- **SB.10 CIK keys.** Part 1's migration (engine 0027 onward) gives M04 signal rows a CIK and settles how enums are encoded (Round 1). That keeps recycled tickers apart, and fixture companies without a ticker work.
- **SB.11 Form list and facts trigger.** Part 1 aligns as-of reads with `refresh.FACT_FORMS`, plus 10-KT and XBRL 6-K. An XBRL 6-K then forces a facts sync (GFS).
- **SB.12 Additions from other rounds** land in named parts when adopted (table).

**Parts** (one live check each; budget and command above):

| Part | Contents | Depends on | Effort | Live check |
|---|---|---|---|---|
| 1 Data foundation | `facts_as_of` (tag-switch and form fixes, SB.11); predecessor CIKs; shares split with multi-class cover counts (1.1), read through one R1 cover reader that Part 3 reuses; M04 extra concepts with a probe report; capex fallback marker and peer exclusion (1.2), with company-stated definitions from `config/capex_definitions.toml` shown beside; `signal` writer (SB.10); overdue-filing state (S1.6, named per Round 1) | — | Medium | R1 history for GOOG, META, MSTR; local probe report of extra tags per company; WDC fixture |
| 2 Company profile and peers | `lifecycle_stage` (5.1) and owner model tag (3.4), both decided before Round 2, on a setup page; SIC peer proposals filtered to active filers, confirmed by the owner into `peer_group` (1.3); offset tolerance (1.4); small-n peer statistics (6.2); 53-week and acquisition flags | 1 | Medium | Browse-by-SIC pages; companyfacts for confirmed peers |
| 3 Event, filing and restatement flags | 4.02/4.01/2.04/3.01/1.03/2.06 digest items; NT filings; amendment counts; restatement walk with step labels (2.2, 2.3), a first-run baseline and cap (B.3), and text for steps above tolerance; dei error flag from R1 | 1 | Medium | 36 R1 pages; 44 later-filing documents; walk report; GE walk fixture |
| 4 Survival gate and distress language | Runway (4.2); maturity wall (4.3); Z/Z″, with O after the paper check (4.1); going-concern and covenant finders and classifier with a baseline (4.4); gate states including "incomplete" | 1, 2, 3 | Medium | EFTS history (48 queries) and hit documents; gate printout for the watchlist; Rivian and Invitae fixtures |
| 5 Dilution and financing pressure | Net issuance (3.1); frames cross-section bands and composite issuance (3.2); SBC block; shelf and 424B classification from `ffd` facts first, fee exhibits where missing (3.3); 8-K 3.03 (MSTR's preferred designations); overhang finder; `financing_pressure` (3.4) | 1, 2, 4 | Medium | 4 frames; fee exhibits for 108 424Bs |
| 6 Earnings quality | `eq_cash`; contract-asset and deferred-revenue gaps; M-score; `misstate_f` (2.1); estimate-change finder and bands (2.4); model-tag routing for non-operating swings | 1, 2, 3 | Medium | 13 prior annual reports; FTS5 estimate-change scan report; GE contract and Lockheed fixtures |
| 7 Unit economics and segments | R12 trigger (5.2); cause finder (5.3); stated items; `unit_metric` with Tesla DS2; EX-99.2; RIVN tracked; dimensional segment and product facts stored from the single instance read (5.4) | 1, 2, 4 | Medium | Instances for the last 3 years, EX-99.2, RIVN backfill; Target fixture |
| 8 CvD assembly, health scores and calibration | Q1/Q2 grid and classification; guidance hit rate and "removed" kind (S1.7); F/G (6.3); profile corrections (6.4); normalized earnings and overreaction gauge on stored Tiingo closes; M04 tab; backtest harness on the owner's labels (6.1); Tiingo probe with an EDGAR-only fallback (B.4); red-flag thresholds stay information-only unless a labelled red-flag set exists | 1–7 | Medium (results review: High) | Companyfacts for episode companies and peers; Tiingo probe; backtest report with confusion matrix and label stability |

- The owner's blind labelling for Part 8 can run alongside Parts 3–7.
- **Dependencies:** no new packages are expected. EdgarTools would be the exception, and only if Part 7 adopts it (`uv add` needs owner approval, D24).

**Fixtures** (SB.6):

| Fixture company | Captured by | Companyconcept files | Tests |
|---|---|---|---|
| WDC | Part 1 | 2 (revenue tags) | As-of read: FY2023 revenue 12,318 as of 2024 |
| GE | Part 3 | about 8 (net income, revenues, CFO and its continuing-operations variant, pretax) | Walk labels: 142 steps from 45 filings |
| GE | Part 6 | 2: `UnbilledContractsReceivable` (25,162 at 2016-12-31 → 28,861 at 2017-12-31) and `BillingsInExcessOfCost`. The standard `ContractWithCustomerAssetNetCurrent` starts only at 2019-12-31. | Contract-asset gap. The 2016-12-31 value first appears in the 10-Q of 2017-05-05, so no 2017 quarter has a year-earlier base; Round 2 sets the expectation |
| Lockheed | Part 6 | 1 | Catch-up revenue |
| Rivian | Part 4 | about 12 | Z″, runway |
| Invitae | Part 4 (Part 7 if Round 5 adds the R12 case) | about 12 | Runway, Z″ |
| Target | Part 7 | about 4 | R12, inventory gap |

**Docs updated in the same commit** (SB.8). Every part also updates M04_FINANCIALS.md, M04_BUILD_LOG.md, LESSONS.md when a lesson generalizes, and the "Resume here" section of DESIGN.md.

| Part | Also updated |
|---|---|
| 1 | M00_SEC_DATA: as-of reads, form list, R1 reader, predecessor CIKs. M00_STORAGE: migrations from 0027 (share concepts, signal CIK and enums, overdue state). M00_UI: Financials rows and marker legend (D-UI-n). DATA_SOURCES: DS12–DS15. SOURCES: S122 onward |
| 2 | M00_STORAGE: peer writes, stage and tag tables. M00_SEC_DATA: browse-by-SIC. M00_UI: setup page |
| 3 | M00_STORAGE: walk steps and baseline marker. M00_SEC_DATA: dei flag via R1, historical document fetch. M00_UI: event rows and review-guide rows |
| 4 | M01_TIMEFRAMES: gate values including "incomplete" and the D27 reading. M00_STORAGE. M00_UI |
| 5 | M00_SEC_DATA: `ffd` facts, fee exhibits, frames cross-section. M00_STORAGE. M00_UI |
| 6 | M00_STORAGE. M00_UI. DATA_SOURCES: DS7 partly closed by one prior 10-K |
| 7 | M00_SEC_DATA: instance dimensions, EX-99.2. M00_STORAGE: axis/member columns or a new table. M00_UI. DATA_SOURCES: DS2, DS12, DS14. Watchlist config: RIVN tracked |
| 8 | M01_TIMEFRAMES: CvD states read by rules 3 and 7. M00_UI: M04 tab. M00_STORAGE. DESIGN.md: phase |

**Review kinds** (SB.9). Names follow the D-M02-51 pattern, and a round's answer can rename them.

| Kind | Part | Expected volume (watchlist, steady state) | Basis |
|---|---|---|---|
| `m04_gate`: fail, incomplete, hypothetical going concern with runway below 8 quarters, waived breach | 4 | a few a year after the baseline | 136 EFTS filing hits over 25 years; estimate |
| `m04_event`: 4.02, 4.01, 2.04, 3.01, 1.03, 2.06, NT | 3 | about 2 a year | 6 events + 1 NT in 3 years |
| `m04_restate`: unexplained step | 3 | about 6 steps a year after the baseline | 101 steps over about 16 XBRL years |
| `m04_dilution`, `m04_overhang` | 5 | about 4–8 a year | MSTR each quarter; INFQ warrants (estimate) |
| `m04_margin_cause` | 7 | 1–3 a year | estimate |
| `m04_estimate`, `m04_mscore` | 6 | about 5 a year | estimate |
| `m04_stage`; `m04_cvd` (AMBIGUOUS) | 2; 8 | a few a year | estimate |
| Setup items: peer sets, model tags, stickiness (if adopted) | 2 | 15 companies, once | setup page, not the weekly queue |

**Additions from other rounds, if adopted** (SB.12):

| Addition | Part |
|---|---|
| Capex split A2: concepts; runway burn; Q2 capex row | 1; 4; 8 |
| Customer signal: RPO concept; major-customer axis; 8-K 1.02; M02 supplier/customer links | 1; 7; 3; 8 |
| Market share, industry pricing and moat rows (missing or deferred); `cvd_confidence` with missing rows; NO_SLOWDOWN and grid gaps | 8 |
| D27 reading of "incomplete", AMBIGUOUS and stale states; the separate distress and financing warnings | 4, 8 (M01_TIMEFRAMES.md) |
| Untagged undrawn credit (quote-verified finder or owner entry); covenant-driven reclassification vs scheduled current maturities; IFRS "material uncertainty" wording | 4 |
| IPO year (SPCX); de-SPAC recasts (INFQ); Up-C units; size-filtered issuance universe without blank checks | 5 |
| Non-operating swings: bitcoin fair value (MSTR), unrealized gains, valuation-allowance releases | 6 |
| Gross-margin comparability (no `GrossProfit` tag; cost-of-sales scope); buyback-driven negative equity | 7, 8; 4 |
| Credit-rating actions (old engine) | 3 |
| ROIC concepts; R&D intensity | 1; 8 |
| Float shares for M07 (R22) | 1 |
| EdgarTools evaluation (S41) for dimensional facts; Invitae as an R12 case | 7 |
| Guidance-record rules and owner (M04 or M11) | 8 |
| Pre-2018 decline episodes (e.g. Sears Holdings, Peabody, GoPro, Fitbit) | 8 |

### Failure modes (rows for M04_BUILD_LOG.md and the M00 docs)
| Input or step | How it can mislead | Guard |
|---|---|---|
| Live-check estimates | Peer and episode counts are estimates; downloads of 3.7 MB files dominate the time | Each log prints requests, MB and seconds per fetch type; runs are resumable |
| Lock | Two SEC processes reach 10/s (S121) | `run_script` in every script; the refresh step runs inside the refresh's lock |
| Logon refresh | M04 work makes the background run heavy during the owner's session | Per-new-filing work only; step timed in the run report; backfills run by the owner |
| First runs | Baselines flood the queue (101 walk steps, 136 EFTS hits) | Baseline recorded, not queued; cap and priority |
| Fixtures | Companyfacts files bloat `tests/fixtures/`; later filings change the files | Companyconcept per tag; fetch date in the file name; tests pin values |
| Tickers | A recycled ticker attaches another company's prices or signals (BBBY, 2025) | CIK keys; Tiingo symbol matched by date range; on mismatch, "missing: no prices" |
| Delisted prices | Tiingo keeps delisted data only for tickers not yet recycled | Probe before the backtest; EDGAR-only fallback |
| Form filter | GFS's quarterly facts arrive on 6-K in `ifrs-full` | Form list aligned with the refresh, plus XBRL 6-K |
| SIC exclusions | MSTR (6199) sits among financials | Model tag decided in Part 2, before any score |
| Fee facts | Companyfacts carries `ffd` facts only from 2026-04, and none for MSTR | Exhibit fetch where they are missing |
| Instance reads | M02's reader keeps no file | Part 7 stores the needed dimensional facts on the one read |
| EFTS company filter | Predecessor CIKs are not searched | Predecessor list in Part 1; queried with the same phrases |
| Engine DB growth | Peer and episode facts multiply `fact` rows and lengthen backups | Row counts in each log; the owner decides on any split |
| Calibration | Backtest results invite threshold edits inside a build | Changes proposed with sources in a High review (D6) |

### Questions
**B.1 Run script and lock**
- (a) *Recommended.* One `scripts/run_financials.py`.
  - A subcommand per part: `probe`, `peers`, `flags`, `gate`, `issuance`, `quality`, `units`, `cvd`.
  - `--no-sec` for local re-runs.
  - The lock through `run_script`.
  - A log, `logs/financials_<step>_<timestamp>.txt`, with requests, MB and seconds per fetch type.

  Why: every part reads `fact`, so one lock holder and one log format suffice, and local re-runs keep the two to four live rounds to seconds.
- (b) One script per part, the M02 pattern. Gets wrong: eight copies of the lock and log code, and the R1 reader that Parts 1 and 3 share would live in two scripts.
- (c) Pytest live tests through `run_live.py` only (the earlier draft). Gets wrong: pass/fail output gives the owner no walk report or gate printout to read, and fixture capture becomes a side effect of a test.

**B.2 What runs in the logon refresh**
- (a) *Recommended.* Per-new-filing work only, about 380–420 SEC requests a year and about 40 on a heavy day:
  - the R1 page;
  - a peer's companyfacts when the daily index shows its 10-K/10-Q;
  - the instance;
  - EX-99.2;
  - the fee exhibit where `ffd` facts are missing;
  - local finders.

  History backfills run once, from B.1's script. Why: recent logon runs took 1.5–6.7 minutes, and these additions cost seconds a day.
- (b) Backfill on first sight inside the refresh, the M00 pattern. Gets wrong: the first logon after each merge pulls its share of about 1,100–1,200 one-off requests (up to ~300 MB in Part 8) in the background of the owner's session, and a kill at 3 hours leaves half a baseline.
- (c) No M04 fetches in the refresh; the owner runs an update weekly. Gets wrong: a 4.02 8-K or a going-concern 10-Q waits up to a week while M01 triggers read the old gate.

**B.3 Review kinds, caps and first-run baselines**
- (a) *Recommended.* M04 gets its own weekly cap of 5 (starting value, unsourced), flushed in this priority order:
  1. survival items (gate fail or incomplete, going concern, covenant);
  2. filing events;
  3. restatement steps;
  4. dilution and overhang;
  5. margin cause;
  6. estimate changes and M-score;
  7. stage changes and CvD AMBIGUOUS.

  Setup items go to a one-time setup page. The first run of every history scan is a baseline: recorded and shown, never queued.

  Why: steady-state M04 volume is under one a week, while the baselines hold 101 walk steps and 136 EFTS hits.
- (b) Share M02's cap of 10. Gets wrong: M04 survival items compete with M02's overflow of 68 link, 27 financing and 9 spender items (refresh log, 2026-10-12).
- (c) Queue every first-run finding. Gets wrong: 101 + 136 = 237 items, about 47 weeks at 5 a week.

**B.4 Delisted and recycled names in the test set**
- (a) *Recommended.* Part 8's live check probes Tiingo for each non-watchlist episode company: at most 22 requests and 11 symbols.
  - The symbol is matched to the SEC company by date range, not by ticker.
  - A name without matching prices keeps EDGAR-only labels. Its overreaction gauge and Z's X4 term show "missing: no prices".
  - All M04 rows are keyed by CIK.

  Why: Tiingo keeps delisted data only for tickers not yet recycled, and BBBY was recycled on 2025-08-29.
- (b) Drop episodes without prices. Gets wrong: it removes the decline cases (Invitae, Bed Bath & Beyond, Rite Aid and J.C. Penney all went through Chapter 11 and delisting), leaving calibration with troughs only.
- (c) Buy a source with delisted coverage (EODHD is the fallback noted in DS8, S70). Gets wrong: it breaks the free-sources rule (S2) for one gauge, and it needs an owner decision first.

### New sources added in this section
- **S-new-bp-1** Tiingo documentation, Appendix: Symbology (delisted data only for tickers that have not been recycled; delisted symbols may end in a digit), checked 2026-10-12 — https://www.tiingo.com/documentation/appendix/symbology
- **S-new-bp-2** Recycled ticker BBBY:
  - Beyond, Inc. Form 8-K filed 2025-08-22, accession 0001140361-25-032363. Name changed to Bed Bath & Beyond, Inc. effective 2025-08-18; BYON to trade until the close on 2025-08-28 and BBBY from 2025-08-29 — https://www.sec.gov/Archives/edgar/data/1130713/000114036125032363/ef20054350_8k.htm
  - SEC submissions record for CIK 0001130713, now Neighborhood Intelligence, Inc. (tickers NXH, BBBYW), checked 2026-10-12 — https://data.sec.gov/submissions/CIK0001130713.json
- **S-new-bp-3** SEC companyfacts and submissions JSON for the watchlist, fetched 2026-10-12. Used for: accession counts by form, 424B and 8-K item counts, `ffd` fee facts, SIC codes, predecessor CIKs, and the restatement-walk count (script in the session scratchpad).
  - Intel companyfacts (`ffd` example) — https://data.sec.gov/api/xbrl/companyfacts/CIK0000050863.json
  - GFS submissions — https://data.sec.gov/submissions/CIK0001709048.json
  - Google Inc. — https://data.sec.gov/submissions/CIK0001288776.json
  - Marvell Technology Group — https://data.sec.gov/submissions/CIK0001058057.json
  - Pattern: https://data.sec.gov/submissions/CIK##########.json
- **S-new-bp-4** SEC EDGAR full-text search counts, run 2026-10-12: 3 phrases × 16 watchlist CIKs, forms 10-K and 10-Q, 2001-01-01 to 2026-10-12, 48 queries in 43 s. Example query — https://efts.sec.gov/LATEST/search-index?q=%22not%20in%20compliance%22&ciks=0001045810&forms=10-K,10-Q&dateRange=custom&startdt=2001-01-01&enddt=2026-10-12
- **S-new-bp-5** XBRL cover pages (R1):
  - Meta Platforms FY2025 10-K (0001628280-26-003942) — https://www.sec.gov/Archives/edgar/data/1326801/000162828026003942/R1.htm
  - MicroStrategy Q2 2011 10-Q (0001193125-11-208374) — https://www.sec.gov/Archives/edgar/data/1050446/000119312511208374/R1.htm
- **S-new-bp-6** EDGAR company browse by SIC 3674. The list is alphabetical and includes inactive filers (first page: 3DLABS, Acacia Communications, ACTEL …) — https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&SIC=3674&type=10-K&dateb=&owner=include&count=100

## Known gaps
Points the revision could not fix with verifiable information. Each is checked at the build part named, or asked in the round.

- **Round 1:** Greenwald's book was not read (S13 is a Wikipedia summary; the Old School Value pages return 404). Open: gross or net PP&E, and whether the 5-year window includes the current year. Recommendation 1.5a does not depend on this, but the Greenwald figures shown use one reading (net PP&E, five prior years, ratio of sums).
- **Round 1:** Dickinson (2011) Table 1 not read; the stage sign mapping is from the secondary paper in S-new-56.
- **Round 1:** The full EDGAR browse-by-SIC list for 3674 was not fetched: www.sec.gov refused the research client (HTTP 403) without the engine's declared user agent. The SIC sample uses submissions JSON for named companies only.
- **Round 1:** The 31 parsed guidance-ledger rows sit in data\engine.db, which Claude may not read. Question 1.9 uses public releases instead (Micron Q2 FY2023; Intel 2022-2023), and Intel's July 2022 release was not read.
- **Round 1:** Tiingo coverage of delisted tickers is unchecked: the key is in .env, so the owner must run the probe.
- **Round 1:** Invitae's filer status for FY2023 is unknown (submissions show only the last status), so its 10-K due date is given as a range. Historical filer status is not in companyfacts.
- **Round 1:** R1 cover-page history before about 2011 has an unverified format; the full-history count (about 165) is an estimate at 4 filings a year.
- **Round 1:** NVIDIA FY2013-FY2021 capex is presumed to be a company extension tag; not confirmed from an instance.
- **Round 1:** GE's line label for UnbilledContractsReceivable (whether it is the 'contract assets' line) not confirmed from the 10-K text.
- **Round 1:** SPCX's per-class cover count is inferred from the absence of dei facts; not confirmed from its R1 page.
- **Round 1:** Causes of INFQ's 8-K 3.01 (2026-02-03) and 4.01 (2026-03-26) not read.
- **Round 1:** Thresholds without a source, labelled as starting values: quarter/instant tolerance ±40 days, the stage conflict at a 25% revenue CAGR, '2 misses in 4 quarters', and the depreciation cap rule.
- **Round 1:** Critique items owned by other rounds were not handled here beyond data status: the customer-signal design (2), cvd_confidence for missing rows (4), CvD grid gaps (5), consolidated D-M04-1 change table (6, partly fed by a list at the end of this round), M01 interaction (7) and the rest of the review-kind caps (15).
- **Round 2:** Alphabet 2023: the +$3.0B net-income effect and the prior 4-year server life were not re-confirmed. Only the -$3.9B depreciation was confirmed, in Item 7; Note 1 was not reached.
- **Round 2:** GE net-income residuals (-149 for FY2016, -30 for FY2017) are uncertain. It was not checked whether the 8-K's ASC 606 amounts are on a continuing-operations basis or a net-income basis. The LIFO-to-FIFO effect on 2016-17 earnings was not quantified.
- **Round 2:** GE causes not read: the FY2016 CFO shift (+1,400) and the FY2017 step-2 shift (+523). The -152 FY2017 residual is not matched to the ASU 2016-18 restricted-cash amounts. The cause of the FY2017 revenue step 2 (likely discontinued operations) is not verified.
- **Round 2:** The tag GE used for 2015 contract assets in its 2016 10-K was not identified; it is not in companyfacts and is probably an extension.
- **Round 2:** It was not checked whether GE's own 10-Ks quantified the cost-estimate changes. The fixture uses the SEC order's lower-bound amounts.
- **Round 2:** The M-score and Dechow figures come from a scratch tag mapping, so they are approximations. Tesla was not scored (alias gaps), nor were GFS (IFRS) and SPCX. NVIDIA FY2026 and Marvell FY2026 F-scores could not be computed (tag switch; no proceeds tag).
- **Round 2:** Attributing the 2016-2018 CFO-increasing shifts to ASU 2016-09, 2016-15 and 2016-18 is an inference; causes were not read. The text-label yield of the historical fetch (how many of the 102 steps text will explain) is unknown until it runs.
- **Round 2:** The m04_estimate volume (about 1-2 a year) is an inference from the Audit Analytics base rate. The Part 3 download time ('a few minutes') is an estimate. 'SPCX has no prior 10-K' was not checked.
- **Round 2:** Several new thresholds have no published source: the $0.1M floor, the 25% non-operating share, the 21% tax approximation, the 24-month baseline and the 5-a-week cap. All are labelled starting values.
- **Round 2:** Pack-level parts of the critique stay outside this section: 15 (the consolidated M04 review table across rounds), 16 (signal-table enum encoding for restate_delta and cf_shift labels), 19 (moving 5.1 ahead of Round 2; the S2.1 CFO/NI warning still depends on stage) and 20 (aligning the S1.1 form list).
- **Round 3:** SPCX lock-up terms were not read: the 424B4 is over 10 MB, beyond the fetch limit. The lock-up case therefore uses INFQ's resale registration as its real example, and the SPCX lock-up end stays a build-time text read.
- **Round 3:** The SPCX preferred-to-common conversion share count was not verified. A summarizer reading of the 10-Q equity table (6,728M) conflicts with the XBRL temporary-equity counts, so only the XBRL counts (2,046M → 135M → 0) are used.
- **Round 3:** Intel: the cause of the 60M gap between the Q2 2026 basic weighted average and the 2026-07-17 cover count is not checked (escrowed shares are a candidate). Whose resale the 2025-09-05 424B7 covers is not checked either.
- **Round 3:** BA: the final count of mandatory convertible depositary shares (whether the over-allotment was sold) is not checked. The 29.1M–35.0M range uses the term sheet's 100M.
- **Round 3:** INFQ: the CY2025/CY2024 annual weighted-average pair in the Q2 2026 10-Q does not reconcile with the same filing's H1 2025 figure. The cause is not investigated; the pair is shown as a defect only.
- **Round 3:** Review-item volumes in S3.9 are estimates. MSTR's count of convertible-note series and ATM programs is not checked, and INTC's FY2025 10-K 'downgraded' sentence is not classified.
- **Round 3:** Up-C: no real Up-C example is given. None is known on the watchlist, and the noncontrolling-interest percentage tag is too sparse (2 filers) to find one.
- **Round 3:** Why so few blank checks appear in the non-dimensional weighted-average frame (9 name matches) is not checked. Excluding SIC 6770 across the whole universe has no request-cheap data path; the float filter removes the 9 matches anyway.
- **Round 3:** Whether AMZN's and GOOG's 424B5s are debt was not checked filing by filing. The inference rests on their falling or flat share counts.
- **Round 3:** S-new-68 is still cited in Round 6 (strategic stakes). Replacing it there with S-new-r3-6 is outside this section.
- **Round 3:** The pack-level parts of critique points 6, 15, 16, 17, 19 and 36 belong to other sections: the consolidated D-M04-1 change table, the full review-kind list, the full signals table, moving the tag question to Round 1, and doc-update and mock-up steps. This section supplies only its own slice.
- **Round 4:** 4.4 example sentences: SEC filings (www.sec.gov Archives) could not be fetched directly without a contact e-mail User-Agent, so the class examples rest on EFTS exact-phrase matches and a summarising fetch tool. The table gives matched key words and short paraphrases rather than full verbatim sentences, which must be captured as fixtures with offsets at build.
- **Round 4:** INFQ's single 'substantial doubt' EFTS hit (FY2025 10-K carrying the pre-merger SPAC's statements) could not be read in full, so its class is not stated.
- **Round 4:** Boeing's covenant-compliance sentence ('were in compliance', matched in its FY2023 10-K and 2024 10-Qs) could not be read in context; the compliant-class example uses UTI instead.
- **Round 4:** Manufacturer Z (SIC 2000-3999) for watchlist names needs Tiingo prices from data/, which this review cannot read. The first-run m04_score_gap volume therefore uses book Z'' as a screen only (GFS 1.87 grey; SPCX Z'' uses annualized H1 EBIT because its TTM is unavailable).
- **Round 4:** Pack-wide parts of points 6, 15, 16 and 17 (the consolidated D-M04-1 table, all review kinds, enum encoding for every signal, the full signals-out table) belong to other rounds. This section supplies only Round 4's rows.
- **Round 4:** Point 36's mock-up and per-part doc lists are given for Part 4 only. Point 19 (moving the stage question earlier) is not this section's fix; S4.1 relies on lifecycle_stage and the model tag being decided before this round.
- **Round 4:** The 8-quarter warn band, the capex-funded tier and the M04 weekly cap of 5 have no published source; they are labelled starting values for Part 8 calibration.
- **Round 5:** 31: Dickinson (2011) primary still unread: The Accounting Review is paywalled and SSRN returned 403. Dickinson's US stage-transition rates are therefore unknown. The constructions in Lev & Thiagarajan / Abarbanell & Bushee and Kesavan & Mani's benchmark are also still unread.
- **Round 5:** 19 (partial): Question 5.1 cannot be moved into the Round 1 text from this chunk; it is only marked 'presented with Round 1'. The owner model-tag vocabulary (issuance-funded, asset-holding, bitcoin treasury, REIT, ...) belongs to question 3.4 and Round 1 and is not enumerated here.
- **Round 5:** 27 (partial): The 5.2d column assumes no stated cost-of-revenue items for Tesla and Target (not checked). Invitae's stated amounts are annual only, so its quarterly ex-items margin is not computed. Invitae quarters before 2020Q4 and Intel 2021Q1 under option (b) need 2018 and 2019 quarters, which were not fetched.
- **Round 5:** Microsoft's ~45% OpenAI share of commercial RPO is from the press (grade B); Microsoft's own call or 10-Q wording was not read.
- **Round 5:** The examples of 8-K 1.02 co-filed with 2.03 (Tesla 2023-01-25 and 2026-09-29, Rivian 2025-06-12) rest on EDGAR item numbers only; the texts were not read.
- **Round 5:** Invitae's FY2022 stated revenue-per-unit and cost-per-unit amounts were not found in the excerpts read (only 'higher'). Rivian's FY2025 and Q4 2025 credits are derived from the stated decreases and assume credits sit inside automotive revenue.
- **Round 5:** Patatoukas (2012) was read through a university press summary only, and the Asgharian & Liu (S45) finding through the abstract only.
- **Round 5:** The m04_customer review volume is an unmeasured estimate. The live-check minutes depend on instance download sizes, which were not measured.
- **Round 5:** Pack-wide items (15, 16, 17 consolidation; 6 consolidated D-M04-1 change table) need the other rounds. Round 5 supplies only its own rows. For the consolidated table: Round 5 does not change the approved grid, but the stage-neutral reading of R12 and the customer-row implementing rules should be listed for owner confirmation.
- **Round 6:** The Croux & Rousseeuw (1992) primary chapter is not available online. The b_n values come from the revss package source, not the paper itself.
- **Round 6:** Mohanram (2005)'s original variance windows remain unverified: the publisher's copy is paywalled and SSRN blocked automated access. The section uses Li & Mohanram (2019), co-authored by Mohanram, which gives 2 years of quarterly data; the CXO summary of 2005 says 5 years.
- **Round 6:** Tiingo coverage of delisted tickers cannot be checked here, because .env and data/ are off-limits. It is left to Part 8's live probe.
- **Round 6:** Micron and NVIDIA closes come from Yahoo Finance (secondary), not stored Tiingo bars (data/ is off-limits). They must be re-checked at build.
- **Round 6:** Bed Bath & Beyond, Rite Aid, Boeing and Invitae test episodes were carried from the draft and not re-verified in XBRL in this pass.
- **Round 6:** Peabody's missing 12-month 2017 period is attributed to post-bankruptcy predecessor/successor stubs by inference, not read from the filing.
- **Round 6:** Intel's x86 server share is derived as 100 − AMD, which assumes a two-vendor market that S-new-69 does not state. Server-market growth is not given, so the 'flat or growing market' condition cannot be tested.
- **Round 6:** The Part 8 request and storage estimates (about 1,750 requests, 30–60 MB) are extrapolated from observed file sizes, not measured.
- **Round 6:** Thresholds introduced here have no source and are labelled starting values: operating income −25% for activation, 5 pp turning-point swing, 2 pp share loss, −25 pp gauge gap, F-quality bands, ≥ 3 peers for the gross-margin gap, 2/3 majority with ≥ 2 present rows, and the bottom-fifth B/M gate for G.
- **Round 6:** Cross-section consistency must be reconciled outside this section. Round 1's S1.6 must adopt the 'overdue' name and bounds. The Build parts Part 8 row must carry the new request counts and Tiingo probe. The changes table cites other rounds' question numbers as in the current draft, which their revisions may renumber.
- **Round 6:** Critique 16 (enum encoding in the numeric signal table) and the pack-wide signals-out and timeframe-parameters table (17) are only partly handled: Round 6 additions only.
- **Round 6:** Critique 2 (customer-base row) and critique 1 (A2 maintenance capex) are designed elsewhere. This round treats the customer row as missing and does not use A2.
- **Round 6:** Critique 8's list of required vs optional gate inputs belongs to Round 4. Here 'incomplete' is only defined as not-pass for M01.
- **Build parts (proposal):** Live-check minutes are estimates. The owner's bandwidth is not measured; times use the D-SEC-18 rate (about 265 requests a minute), the measured EFTS run and M02's 113-instance run.
- **Build parts (proposal):** Peer counts for Part 2 (about 40–50) and episode peers for Part 8 (about 40–70) are estimates until the owner confirms peer sets.
- **Build parts (proposal):** Tiingo coverage of each delisted episode (Invitae, Rite Aid, J.C. Penney, Sears Holdings, Fitbit) was not checked, because that needs the owner's key; only BBBY's recycling is verified. The Part 8 probe settles the rest.
- **Build parts (proposal):** It was not checked whether 10-Ks filed in early 2023 carry the dei error-correction flag, so Part 3's 36 R1 pages are an upper bound.
- **Build parts (proposal):** Review volumes for gate, dilution, margin cause, estimate, stage and CvD kinds are estimates; only events, walk steps and EFTS hits were counted.
- **Build parts (proposal):** The label of GE's UnbilledContractsReceivable line was not confirmed against the text of GE's 2017 10-K.
- **Build parts (proposal):** Sizes of instances, the 44 walk filings and the up to 143 EFTS hit documents were not measured (www.sec.gov returned 403 to a script without a contact user agent).
- **Build parts (proposal):** The size of engine.db and its growth from peer and episode facts were not measured (Claude may not read data\).
- **New sources:** Altman Z'' zones 1.1/2.6: no primary found online. Altman (2000) states the formula but not the zones; candidate primaries (Altman, Hartzell & Peck 1995; Altman & Hotchkiss 3rd ed.) are not freely available. Left on the checklist.
- **New sources:** Ohlson (1980), Dickinson (2011) stage table, Mohanram (2005) variance windows, Beneish (1999) ACCR definition, and Lev & Thiagarajan / Abarbanell & Bushee constructions: no free primary copies found. They remain on the pre-review checklist as not read.
- **New sources:** Croux & Rousseeuw (1992) primary is a paywalled Springer chapter. The factors come from the revss source code only and were not checked against the paper.
- **New sources:** Micron's 153/235 inventory days have no primary written source: the Q2 FY2023 release states no DIO and the 8-K has no EX-99.2. Only the primary-computed 151/213 alternative could be supplied.
- **New sources:** Citation fixes in other rounds (S98 replacements, the edgar.tools row, the HXZ alignment, the Intel tranche wording, removal of the Round 6 asterisk) are listed in this section but must be applied by those sections' revisers or at merge. This chunk cannot edit them.
- **New sources:** S-new-src IDs may collide with other sections' S-new-src-n numbering and need renumbering at merge.

## New sources
These IDs are provisional. They become S123 onward when they are added to SOURCES.md. S122 goes to the duplicate S101 (see the S101 fix below). "Other" marks a source that is not peer-reviewed, or is secondary.

- **S-new-1** SEC XBRL companyconcept and companyfacts data, checked 2026-10-12 and rechecked the same day for this list.
  - URL patterns: `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/<taxonomy>/<Tag>.json` and, for whole files, `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`.
  - Values are the first-filed 10-K values in $M unless a row says otherwise.
  - **Micron (CIK0000723125).**
    - Tags:
      - revenue: `SalesRevenueNet` (FY2013–17), then `Revenues` (FY2018, first filed 2018-10-15), then `RevenueFromContractWithCustomerExcludingAssessedTax` (from the 10-K filed 2019-10-17);
      - income statement: `CostOfGoodsAndServicesSold`, `GrossProfit`, `OperatingIncomeLoss`, `NetIncomeLoss`;
      - balance sheet: `Assets`, `AssetsCurrent`, `LiabilitiesCurrent`, `InventoryNet`, and `LongTermDebtAndCapitalLeaseObligations` (`LongTermDebtNoncurrent` appears in a 10-K last at 2012-08-30);
      - other: `WeightedAverageNumberOfDilutedSharesOutstanding`, `NetCashProvidedByUsedInOperatingActivities`, `PaymentsToAcquirePropertyPlantAndEquipment`.
    - Key 10-Ks: FY2021 0000723125-21-000065, FY2022 0000723125-22-000048, FY2023 0000723125-23-000054.
    - **Round 1 table.** `InventoryNet` is 6,663 at FY2022 and 8,387 at FY2023. This primary value replaces edgar.tools.
    - **Round 6 Piotroski table.**
      - Net income −5,833.
      - Assets 58,849 / 66,283 / 64,254 (FY2021–23). ROA uses beginning-of-year assets.
      - Current assets / current liabilities: 21,781 / 7,539 → 21,244 / 4,765.
      - Long-term debt: 6,803 → 13,052.
      - Diluted shares: 1,122M → 1,093M.
    - **Gross-margin lows and highs:**
      - FY2016: 2,505 ÷ 12,399 = 20.2%;
      - FY2018: 17,891 ÷ 30,391 = 58.9%;
      - FY2020: 6,552 ÷ 21,435 = 30.6%.
    - **10-year operating margins:**
      - FY2014–23: 47,734 ÷ 214,506 = 22.3% as a ratio of sums, 18.0% as a mean of yearly ratios;
      - FY2013–22: 53,715 ÷ 208,039 = 25.8%.
    - **Quarterly revenue for the Round 6 TTM rows.** All quarters are in companyfacts, so the Round 6 asterisk can be removed.
      - 2021 base: 6,236 + 7,422 + 8,274 + 7,687 = 29,619. Q4 FY2021 is derived: FY 27,705 − 9-month 19,431 = 8,274.
      - TTM to 2022-12-01: 27,156 (−8.3%).
      - TTM to 2023-11-30: 16,181 (−40.4%).
  - **Intel (CIK0000050863).**
    - `RevenueFromContractWithCustomerExcludingAssessedTax`, FY2021–25: 79,024 / 63,054 / 54,228 / 53,101 / 52,853. 10-Ks: 0000050863-22-000007, -23-000006, -24-000010, -25-000009, -26-000011.
    - `GrossProfit`.
    - `OperatingIncomeLoss`: FY2016 12,874 → 13,133 and FY2017 17,936 → 18,050, both recast in 10-K 0000050863-19-000007, filed 2019-02-01.
  - **AMD (CIK0000002488).** `RevenueFromContractWithCustomerExcludingAssessedTax`, FY2021–23: 16,434 / 23,601 / 22,680 (+43.6%, −3.9%). 10-Ks: 0000002488-22-000016, -23-000047, -24-000012. `Revenues` holds only 2017 10-Q comparatives.
  - **NVIDIA (CIK0001045810).** `Revenues` for the fiscal years ending 2022-01-30, 2023-01-29 and 2024-01-28: 26,914 / 26,974 / 60,922 (+0.2%, +125.9%). 10-Ks: 0001045810-22-000036, -23-000017, -24-000029. `RevenueFromContractWithCustomerExcludingAssessedTax` stops at FY2022.
  - **Texas Instruments (CIK0000097476).** `RevenueFromContractWithCustomerExcludingAssessedTax`, 2021–23: 18,344 / 20,028 / 17,519 (+9.2%, −12.5%). 10-Ks: 0000097476-22-000009, -23-000007, -24-000007. `Revenues` returns 404.
  - **Strategy (CIK0001050446).** Weighted-average basic and diluted shares, `ProceedsFromIssuanceOfCommonStock`, `ShareBasedCompensation`. dei and `CommonStockSharesOutstanding` return 404.
  - **Meta (CIK0001326801).** `ShareBasedCompensation`, `PaymentsForRepurchaseOfCommonStock`, `PaymentsRelatedToTaxWithholdingForShareBasedCompensation`, revenue, operating cash flow, weighted-average shares. Share tags return 404.
  - **Alphabet (CIK0001652044).**
    - Net income and CFO.
    - `Depreciation`: 13,475 (2022) → 11,946 (2023), filed in 10-K 0001652044-24-000022. This is the D&A input; Alphabet has no `DepreciationDepletionAndAmortization` or `DepreciationAndAmortization` tag.
    - dei returns 404.
  - **GE (CIK0000040545):** `NetIncomeLoss`, `Revenues`, `NetCashProvidedByUsedInOperatingActivities`.
  - **WDC (CIK0000106040):** `RevenueFromContractWithCustomerExcludingAssessedTax`.
  - **Rivian (CIK0001874178):** `GrossProfit`.
  - **Lockheed (CIK0000936468):** `ContractWithCustomerPerformanceObligationSatisfiedInPreviousPeriod`.
  - **Target (CIK0000027419):** `InventoryNet`.
  - **Infleqtion (CIK0002007825):** `ClassOfWarrantOrRightOutstanding`, dei `EntityCommonStockSharesOutstanding`.
  - Example: https://data.sec.gov/api/xbrl/companyconcept/CIK0000723125/us-gaap/GrossProfit.json
- **S-new-2** Bhojraj, Lee & Oler (2003), "What's My Line? A Comparison of Industry Classification Schemes for Capital Market Research", J. Accounting Research 41(5):745–774 — https://ideas.repec.org/a/bla/joares/v41y2003i5p745-774.html
- **S-new-3** Fiscal-year alignment conventions.
  - Compustat fiscal-year assignment — https://leiq.bus.umich.edu/docs/Fiscal%20Year-end%20Month%20of%20Data.pdf
  - Fama-French portfolio formation, from the Data Library page "25 Portfolios Formed on Size and Accruals" — https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/tw_5_ports_me_AC.html
    - Corrected title: earlier versions of this entry did not name the page.
    - Its construction note forms portfolios at the end of June of year t from fiscal-year-end t−1 data. The lag of at least 6 months is implied by that rule; the page does not state it.
- **S-new-4** SEC Release 33-9002 (2009), XBRL phase-in (summary, other) — https://www.willkie.com/publications/2009/02/sec-issues-final-rules-mandating-xbrl-filings
- **S-new-5** Micron:
  - FY2023 10-K — https://www.sec.gov/Archives/edgar/data/723125/000072312523000054/mu-20230831.htm
  - Q4 FY2023 release — https://www.sec.gov/Archives/edgar/data/723125/000072312523000051/a2023q4ex991-pressrelease.htm
  - Q2 FY2023 release — https://www.sec.gov/Archives/edgar/data/723125/000072312523000018/a2023q2ex991-pressrelease.htm
    - Read 2026-10-12: inventory write-downs of $1.43B; GAAP gross margin −$1,206M (−32.7%); inventories $8,129M at 2023-03-02; COGS $4,899M.
    - The release states no inventory days, and the 8-K has no EX-99.2.
    - Computed from these primary figures for the 91-day quarter: about 151 days, or about 213 days excluding the write-down.
  - StorageNewsletter (other) — https://www.storagenewsletter.com/2023/09/28/micron-fiscal-4q23-financial-results/
  - Q2 FY2023 call transcript (other) — https://www.marketbeat.com/earnings/transcripts/88099/
    - It is the only source for the company-stated 153 and 235 inventory days. These are oral figures on an unstated definition, so they are grade B. Round 6 should show them beside the primary-computed 151 and 213.
  - Removed: edgar.tools inventories. `InventoryNet` (S-new-1) gives the same 6,663 and 8,387.
- **S-new-6** Sloan (1996), "Do Stock Prices Fully Reflect Information in Accruals and Cash Flows about Future Earnings?", The Accounting Review 71(3):289–315 — https://www.cuhk.edu.hk/acy2/workshop/June2009Wasley/1996TAR).pdf
- **S-new-7** Richardson, Sloan, Soliman & Tuna (2005), J. Accounting & Economics 39:437–485 — https://academicnewsletter.sufe.edu.cn/info/412636 ; Fairfield, Whisenant & Yohn (2003), The Accounting Review 78(1):353–371 (summaries only) — https://maaw.info/TheAccountingReview-5.htm (the host refused connections on 2026-10-12; re-check)
- **S-new-8** Green, Hand & Soliman (2011), "Going, Going, Gone? The Apparent Demise of the Accruals Anomaly", Management Science 57(5):797–816 — https://ideas.repec.org/a/inm/ormnsc/v57y2011i5p797-816.html
- **S-new-9** McLean & Pontiff (2016), "Does Academic Research Destroy Stock Return Predictability?", J. Finance 71(1):5–32 — https://academicnewsletter.sufe.edu.cn/info/359722
- **S-new-10** Hou, Xue & Zhang, "Replicating Anomalies".
  - NBER w23394 (May 2017) — https://www.nber.org/papers/w23394.pdf
  - Review of Financial Studies 33(5):2019–2133 (2020) — https://ideas.repec.org/a/oup/rfinst/v33y2020i5p2019-2133..html
  - The two versions report different headline figures, both with NYSE breakpoints and value weights:
    - the working paper: 64% of 447 anomalies are insignificant;
    - the RFS abstract: 65% of 452 fail t = 1.96, and 82% fail the multiple-test hurdle of 2.78.
  - Round 2 quotes the RFS figure and Round 3 the working-paper figure. Each should name its version, or both should use the RFS figure.
- **S-new-11** Fama & French (2008), "Dissecting Anomalies", J. Finance 63(4):1653–1678 — https://www.johnhcochrane.com/s/fama_french_dissecting_anomalies_JF.pdf
- **S-new-12** Ball, Gerakos, Linnainmaa & Nikolaev (2016), "Accruals, Cash Flows, and Operating Profitability in the Cross Section of Stock Returns", J. Financial Economics 121(1):28–45 — https://ideas.repec.org/a/eee/jfinec/v121y2016i1p28-45.html
- **S-new-13** Hribar & Collins (2002), "Errors in Estimating Accruals: Implications for Empirical Research", J. Accounting Research 40(1):105–134 — https://iro.uiowa.edu/esploro/outputs/journalArticle/Errors-in-Estimating-Accruals-Implications-for/9984380479802771
- **S-new-14** Beneish M-score teaching note (OSU; formula and cut-offs, other) — https://bpb-us-w2.wpmucdn.com/u.osu.edu/dist/3/40936/files/2016/12/M-Score-pa6gdy.pdf ; Beneish, Lee & Nichols (2013), Financial Analysts Journal 69(2):57–82 — https://ideas.repec.org/a/taf/ufajxx/v69y2013i2p57-82.html
- **S-new-15** Beneish & Vorst (2022), "The Cost of Fraud Prediction Errors", The Accounting Review 97(6):91–121 — https://cris.maastrichtuniversity.nl/en/publications/the-cost-of-fraud-prediction-errors ; summary (other) — https://blog.kelley.iu.edu/?p=3280
- **S-new-16** Dechow, Ge, Larson & Sloan (2011), "Predicting Material Accounting Misstatements", Contemporary Accounting Research 28(1):17–82 — https://thecaq.wpenginepowered.com/wp-content/uploads/2018/03/Dechow-et-al-2011-Contemporary_Accounting_Research.pdf
- **S-new-17** Restatement rates and reactions:
  - Munter (2022), SEC statement on assessing materiality — https://www.sec.gov/newsroom/speeches-statements/munter-statement-assessing-materiality-030922
  - PCAOB Data Point DP04-2025, restatements and auditor turnover — https://pcaobus.org/economicandriskanalysis/data-points/dp04-2025-financial-restatements-auditor-turnover.pdf
  - sec-api.io 4.02 price reactions (vendor) — https://sec-api.io/resources/stock-price-reactions-to-item-4-02-disclosures-in-sec-form-8-k-filings
- **S-new-18** Choudhary, Merkley & Schipper (2021), "Immaterial Error Corrections and Financial Reporting Reliability", Contemporary Accounting Research 38(4):2423–2460 — https://experts.arizona.edu/en/publications/immaterial-error-corrections-and-financial-reporting-reliability/ ; Hennes, Leone & Miller (2008), The Accounting Review 83(6) — https://www.kellogg.northwestern.edu/faculty/research/detail/2008/the-importance-of-distinguishing-errors-from-irregularities-in-restatement
- **S-new-19** 10-K error-correction checkbox:
  - Filer XBRL viewer showing `dei:DocumentFinStmtErrorCorrectionFlag` — https://ir.ondas.com/annual-reports/xbrl_doc_only/2384
  - Gibson Dunn (other) — https://www.gibsondunn.com/sec-releases-final-clawback-rules/
  - White & Case (other) — https://www.whitecase.com/insight-alert/key-considerations-2024-annual-reporting-and-proxy-season-your-upcoming-form-10-k
  - The C&DI 104.20 text was read on 2026-10-12. It is listed as S-new-src-3, and its findings are in the checklist below.
- **S-new-20** SEC v. General Electric, primary documents (adds links to S03): Order 33-10899 — https://www.sec.gov/litigation/admin/2020/33-10899.pdf ; press release 2020-312 — https://www.sec.gov/news/press-release/2020-312 ; GE 8-K — https://www.sec.gov/Archives/edgar/data/40545/000004054520000062/ge-20201209.htm
- **S-new-21** Albrecht, Glendening, Kim & Lee (2024), Review of Accounting Studies 29(2):1320–1359 — https://academicnewsletter.sufe.edu.cn/info/413886 ; Audit Analytics, nineteen years of changes in estimates (other) — https://blog.auditanalytics.com/an-overview-of-nineteen-years-of-changes-in-accounting-estimates/
- **S-new-22** Alphabet FY2023 10-K — https://www.sec.gov/Archives/edgar/data/1652044/000165204424000022/goog-20231231.htm ; Amazon FY2025 10-K — https://www.sec.gov/Archives/edgar/data/1018724/000101872426000004/amzn-20251231.htm
  - Alphabet Note 1 was read on 2026-10-12 through the filing's rendered page R10 — https://www.sec.gov/Archives/edgar/data/1652044/000165204424000022/R10.htm
  - From January 2023, server lives went from 4 to 6 years and certain network equipment from 5 to 6 years.
  - The 2023 effect: depreciation −$3.9B, net income +$3.0B, or $0.24 per basic and per diluted share.
  - Round 2 can drop "re-confirm at build".
- **S-new-23** COSO (2010) fraudulent financial reporting study, via BDO (other) — https://www.bdo.com/insights/focus-on-fraud-coso-fraudulent-financial-reporting-study ; Stubben (2010), "Discretionary Revenues as a Measure of Earnings Management", The Accounting Review 85(2):695–717 — https://academicnewsletter.sufe.edu.cn/info/415968
- **S-new-24** ASC 606 tag coverage, SEC frames API, checked 2026-10-12:
  - prior-period performance-obligation tag: 126 filers CY2024;
  - contract assets: 579 and contract liabilities: 2,034 at CY2024Q4I;
  - `ChangeInAccountingEstimateFinancialEffect`: 404.
  - Links: https://data.sec.gov/api/xbrl/frames/us-gaap/ContractWithCustomerPerformanceObligationSatisfiedInPreviousPeriod/USD/CY2024.json ; filer R page — https://www.sec.gov/Archives/edgar/data/813828/000081382820000022/R53.htm
- **S-new-25** SEC Staff Accounting Bulletin No. 99, Materiality — https://www.sec.gov/interps/account/sab99.htm
- **S-new-26** Pontiff & Woodgate (2008), "Share Issuance and Cross-sectional Returns", J. Finance 63(2):921–945 — https://ideas.repec.org/a/bla/jfinan/v63y2008i2p921-945.html ; McLean, Pontiff & Watanabe (2009), J. Financial Economics 94(1):1–17 — https://ideas.repec.org/a/eee/jfinec/v94y2009i1p1-17.html
- **S-new-27** Kenneth R. French Data Library, portfolios formed on net share issues — https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_port_form_NI.html
  - The page body was confirmed on 2026-10-12. Its HTML title wrongly reads "Earnings/Price", a site error.
  - Portfolios are formed each June using NYSE breakpoints: NI < 0, NI = 0, quintiles and deciles.
  - NI is the change in the log of split-adjusted shares outstanding from fiscal year-end t−2 to t−1. This is a period-end count, the measure behind option 3.1b.
- **S-new-28** Daniel & Titman (2006), "Market Reactions to Tangible and Intangible Information", J. Finance 61(4):1605–1643; NBER w9743 — https://www.nber.org/papers/w9743.pdf
- **S-new-29** Issuer underperformance:
  - Loughran & Ritter (1995), J. Finance 50(1):23–51 — https://ideas.repec.org/a/bla/jfinan/v50y1995i1p23-51.html
  - Spiess & Affleck-Graves (1999), J. Financial Economics 54(1):45–73 — https://ideas.repec.org/a/eee/jfinec/v54y1999i1p45-73.html
  - Hillion & Vermaelen (2004), J. Financial Economics 71(2):381–415 — https://ideas.repec.org/a/eee/jfinec/v71y2004i2p381-415.html
- **S-new-30** SBC and buybacks:
  - Aboody, Barth & Kasznik (2004), The Accounting Review 79(2):251–275 — https://www.gsb.stanford.edu/faculty-research/publications/sfas-no-123-stock-based-compensation-expense-equity-market-values
  - Mohanram, White & Zhao (2020), Review of Accounting Studies 25(3):1040–1077 — https://academicnewsletter.sufe.edu.cn/info/414126
  - Kahle (2002), J. Financial Economics 63(2):235–261 — https://ideas.repec.org/a/eee/jfinec/v63y2002i2p235-261.html
- **S-new-31** Shelf and ATM rules:
  - Form S-3 instructions — https://www.sec.gov/files/forms-3.pdf
  - Rule 405 — https://www.law.cornell.edu/cfr/text/17/230.405
  - Rule 415 — https://www.law.cornell.edu/cfr/text/17/230.415
  - CFI 116.23 and 116.26 summary (McGuireWoods, other) — https://www.mcguirewoods.com/client-resources/alerts/2026/3/atm-offerings-and-baby-shelf-limitations-evaluating-impact-of-new-sec-guidance/
  - Pending baby-shelf proposal (Mondaq, other) — https://www.mondaq.com/unitedstates/listing-rules-flotation/1806154/
- **S-new-32** Billett, Floros & Garfinkel (2019), "At-the-Market Offerings", J. Financial and Quantitative Analysis 54(3):1263–1283 — https://www.biz.uiowa.edu/faculty/jgarfinkel/pubs/ATM.pdf ; Gustafson & Iliev (2017), J. Financial Economics 124(3):580–598 — https://academicnewsletter.sufe.edu.cn/info/356175
- **S-new-33** Filing-fee exhibits:
  - SEC fee pages — https://www.sec.gov/ffb ; https://www.sec.gov/edgar/filing-fee-modernization
  - Strategy 424B5 (0001193125-24-247536) — https://www.sec.gov/Archives/edgar/data/1050446/000119312524247536/d905160d424b5.htm
  - Fee exhibit — https://www.sec.gov/Archives/edgar/data/1050446/000119312524247536/d905160dexfilingfees.htm
  - Strategy 424B list — https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001050446&type=424B&dateb=&owner=include&count=40
- **S-new-34** ASU 2020-06 convertible instruments: Deloitte — https://dart.deloitte.com/USDART/home/publications/archive/deloitte-publications/news/2020/aug/fasb-issues-guidance-convertible-instruments-contracts ; PwC — https://viewpoint.pwc.com/dt/us/en/fasb_financial_accou/asus_fulltext/2020/asu2020-06/ASU-2020-06/asu-2020-06.html
- **S-new-35** Strategy 10-Q cover pages: Q2 2025 R1 — https://www.sec.gov/Archives/edgar/data/1050446/000095017025102209/R1.htm ; Q2 2026 R1 — https://www.sec.gov/Archives/edgar/data/1050446/000105044626000044/R1.htm
- **S-new-36** Altman (2000), "Predicting Financial Distress of Companies: Revisiting the Z-Score and ZETA Models", NYU Stern working paper.
  - URLs:
    - original — https://pages.stern.nyu.edu/~ealtman/Zscores.pdf (HTTP 500 on 2026-10-12);
    - university mirror, the copy read — https://moodle2.units.it/pluginfile.php/322514/mod_resource/content/0/Zscores.pdf
  - Read 2026-10-12:
    - Z″ = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4 (p. 27). The text says the cut-off scores changed but does not state them.
    - The +3.25 constant belongs to the emerging-market model, where it sets a score of 0 equal to a D-rated bond.
    - Table 7 gives US bond-rating equivalents of that EM score: D 0, CCC 2.50, B 4.15, BB 4.95, BBB 5.85, A 6.65, AAA 8.15.
    - The Z′ (private-firm) grey zone is 1.23–2.90.
- **S-new-37** Market-based distress measures:
  - Shumway (2001), "Forecasting Bankruptcy More Accurately: A Simple Hazard Model", J. Business 74(1):101–124 — https://ideas.repec.org/a/ucp/jnlbus/v74y2001i1p101-24.html
  - Hillegeist et al. (2004), Review of Accounting Studies 9(1) — https://ideas.repec.org/a/spr/reaccs/v9y2004i1d10.1023_brast.0000013627.90884.b7.html
  - Altman et al. (2017), J. International Financial Management & Accounting 28(2) (abstract) — https://doi.org/10.1111/jifm.12053
- **S-new-38** Ohlson (1980), J. Accounting Research 18(1); formula via Wikipedia (other; the original is still to be read) — https://en.wikipedia.org/wiki/Ohlson_O-score
- **S-new-39** Campbell, Hilscher & Szilagyi (2008), "In Search of Distress Risk", J. Finance 63(6); NBER w12362 — https://www.nber.org/papers/w12362.pdf ; Dichev (1998), J. Finance 53(3) — https://doi.org/10.1111/0022-1082.00046
- **S-new-40** DeAngelo, DeAngelo & Stulz (2006), J. Financial Economics 81(2) — https://ideas.repec.org/a/eee/jfinec/v81y2006i2p227-254.html
- **S-new-41** Going-concern evidence:
  - Blay, Moon & Paterson (2016), Auditing: A Journal of Practice & Theory 35(2) — https://www.scheller.gatech.edu/directory/faculty/moon/theres-no-place-like-home-the-influence-of-home-state.pdf
  - Bakarich & Baranek (2020), Accounting Research Journal 33(6) (abstract) — https://ideas.repec.org/a/eme/arjpps/arj-06-2020-0165.html
  - Kausar, Taffler & Tan (2009), J. Accounting Research 47(1) — https://www.research.ed.ac.uk/en/publications/the-going-concern-market-anomaly/
- **S-new-42** Audit Analytics FY2025 going-concern trends, via Ideagen (other) — https://www.ideagen.com/resources/whitepapers/going-concern-opinions-market-trends
- **S-new-43** Going-concern rules:
  - ASC 205-40 / ASU 2014-15 (Deloitte Heads Up via IAS Plus) — https://www.iasplus.com/en/publications/us/heads-up/2014/going-concern
  - PCAOB AS 2415 — https://pcaobus.org/oversight/standards/auditing-standards/details/AS2415
  - PwC FRM 4230.1 — https://viewpoint.pwc.com/dt/us/en/sec/financial_reporting_m/financial_reporting___4_US/topic_4_independent__US/4200_accountants_rep_US/4230_other_report_mo_US.html
- **S-new-44** Covenant evidence:
  - Nini, Smith & Sufi (2012), Review of Financial Studies 25(6) — https://ideas.repec.org/a/oup/rfinst/v25y2012i6p1713-1761.html
  - Becher, Griffin & Nini (2018 working paper) — https://www.lehigh.edu/~jms408/Nini_2018.pdf
  - Dichev & Skinner (2002), J. Accounting Research 40(4) — https://ideas.repec.org/a/bla/joares/v40y2002i4p1091-1123.html
  - Chava & Roberts (2008), "How Does Financing Impact Investment? The Role of Debt Covenants", J. Finance 63(5):2085–2121, doi:10.1111/j.1540-6261.2008.01391.x — https://ideas.repec.org/a/bla/jfinan/v63y2008i5p2085-2121.html
    - Replaces the Wharton author PDF, which redirected to a 404 page on 2026-10-12.
- **S-new-45** Reg S-X 4-08(c) — https://www.law.cornell.edu/cfr/text/17/210.4-08 ; ASC 470-10-45-11 (Deloitte Roadmap) — https://dart.deloitte.com/USDART/home/codification/liabilities/asc470-10/roadmap-debt/chapter-13-balance-sheet-classification/13-5-credit-related-covenant-violations
- **S-new-46** XBRL debt-maturity elements (KLA filing viewer) — https://ir.kla.com/sec-filings/annual-reports/xbrl_doc_only/3365 ; SEC Release 33-10890 MD&A amendments (Kirkland summary, other) — https://www.kirkland.com/-/media/publications/alert/2020/11/alert--sec-amends-mda-disclosure-rules.pdf
- **S-new-47** Rivian (all on EDGAR). The Seeking Alpha and Business Wire copies are replaced; DS4 excluded Business Wire on its terms.
  - Q2 2026 8-K Ex. 99.1 — https://www.sec.gov/Archives/edgar/data/0001874178/000187417826000053/ex-9912q26rivianearningspr.htm
  - FY2025 results: 8-K filed 2026-02-12 (0001874178-26-000007), Ex. 99.1 — https://www.sec.gov/Archives/edgar/data/1874178/000187417826000007/ex-991pressrelease4q25earn.htm
    - Read 2026-10-12. Revenue / cost / gross profit: FY2025 5,387 / 5,243 / 144; FY2024 4,970 / 6,170 / (1,200).
    - Regulatory credit sales fell $134M year over year. No FY2025 credit total is stated.
    - The Q4 2025 shareholder letter is Ex. 99.2 in the same filing (`ex-9924q25shareholderletter.htm`). The FY2025 10-K is 0001874178-26-000008.
  - 2025 production and deliveries: 8-K filed 2026-01-02 (0001874178-26-000002, Items 7.01 and 9.01), Ex. 99.1 — https://www.sec.gov/Archives/edgar/data/1874178/000187417826000002/ex-9914q25deliveryproducti.htm
    - FY2025: produced 42,284, delivered 42,247.
    - Q4 2025: produced 10,974, delivered 9,745.
  - Q4 2023 shareholder letter — https://www.sec.gov/Archives/edgar/data/1874178/000187417824000005/ex-9924q23shareholderletter.htm
  - Q4 2024 shareholder letter — https://www.sec.gov/Archives/edgar/data/1874178/000187417825000004/ex-9924q24shareholderletter.htm
  - FY2024 10-K — https://www.sec.gov/Archives/edgar/data/1874178/000187417825000007/rivn-20241231.htm
- **S-new-48** Invitae: Q4 2022 release — https://www.sec.gov/Archives/edgar/data/1501134/000150113423000022/a991pressreleaseforearning.htm ; Q3 2023 release — https://www.sec.gov/Archives/edgar/data/1501134/000150113423000102/a991pressreleaseforearning.htm
- **S-new-49** Regulation S-K Item 303 (MD&A) — https://www.law.cornell.edu/cfr/text/17/229.303
- **S-new-50** Tesla (all read 2026-10-12):
  - FY2022 10-K (0000950170-23-001409) — https://www.sec.gov/Archives/edgar/data/1318605/000095017023001409/tsla-20221231.htm
    - 2022: 1,369,611 consumer vehicles produced, 1,313,851 delivered.
  - FY2023 10-K (0001628280-24-002390) — https://www.sec.gov/Archives/edgar/data/1318605/000162828024002390/tsla-20231231.htm
    - 2023: 1,845,985 produced, 1,808,581 delivered.
    - Automotive sales 78,509 (2022: 67,210); cost of automotive sales 65,121 (49,599); total automotive gross margin 19.4% (28.5%).
  - FY2024 10-K (0001628280-25-003063) — https://www.sec.gov/Archives/edgar/data/1318605/000162828025003063/tsla-20241231.htm
    - Automotive sales 72,480; cost 61,870; regulatory credits 2,763.
  - Delivery 8-Ks (Item 2.02, Ex. 99.1; DS2 stores these):
    - Q4 2022: 0001564590-23-000002, filed 2023-01-03, `tsla-ex991_6.htm`. Annual total stated only as "1.31 million".
    - Q4 2023: 0000950170-24-000282, filed 2024-01-02, `tsla-ex99_1.htm`. Annual total stated as "1.81 million".
    - Q4 2024: 0001628280-25-000007, filed 2025-01-02, `exhibit991.htm`. Annual total 1,789,226.
  - So the exact 2022 and 2023 totals in Round 5 come from the 10-Ks, and the 2024 total from the delivery 8-K.
- **S-new-51** Target FY2022 10-K Item 7 — https://corporate.target.com/investors/annual/2022-annual-report/10-k-report/10-k-part-ii/item-7-management-s-discussion-and-analysis-of-financial-condition-and-results-of-operations ; FY2023 results (trade press, other) — https://drugstorenews.com/target-reports-q4-full-year-results
- **S-new-52** Gross-margin signal:
  - Lev & Thiagarajan (1993), "Fundamental Information Analysis", J. Accounting Research 31(2):190–215 — https://ideas.repec.org/a/bla/joares/v31y1993i2p190-215.html
  - Abarbanell & Bushee (1997), J. Accounting Research 35(1):1–24 — https://doi.org/10.2307/2491464
  - Al-Debie & Walker (1999), British Accounting Review 31(3):261–280 — https://research.manchester.ac.uk/en/publications/fundamental-information-analysis-an-extension-and-uk-evidence/
- **S-new-53** Kesavan & Mani (2013), "The Relationship Between Abnormal Inventory Growth and Future Earnings for U.S. Public Retailers", Manufacturing & Service Operations Management — https://pubsonline.informs.org/doi/10.1287/msom.1120.0389
- **S-new-54** Novy-Marx (2011), "Operating Leverage", Review of Finance 15(1):103–134 — https://ideas.repec.org/a/oup/revfin/v15y2011i1p103-134.html ; Anderson, Banker & Janakiraman (2003), J. Accounting Research 41(1):47–63 — https://ideas.repec.org/a/bla/joares/v41y2003i1p47-63.html
- **S-new-55** Fama & French (2000), "Forecasting Profitability and Earnings", J. Business 73(2):161–175 — https://ideas.repec.org/a/ucp/jnlbus/v73y2000i2p161-75.html
- **S-new-56** Life cycle:
  - Vorst & Yohn (2018), The Accounting Review 93(6):357–381 — https://www.kellogg.northwestern.edu/academics-research/research/detail/2018/life-cycle-models-and-forecasting-growth-and-profitability/
  - Dickinson (2011), "Cash Flow Patterns as a Proxy for Firm Life Cycle", The Accounting Review 86(6):1969–1994 — https://doi.org/10.2308/accr-10130
  - Secondary paper with the stage mapping (Brazilian Business Review, other) — https://scielo.br/j/bbr/a/TCZG85pSFrYcMMZrHJYQCGd/?lang=en
- **S-new-57** Amir & Lev (1996), J. Accounting & Economics 22(1–3):3–30 — https://ideas.repec.org/a/eee/jaecon/v22y1996i1-3p3-30.html ; Nagy, Farmer, Bui & Trancik (2013), PLOS ONE 8(2) — https://pmc.ncbi.nlm.nih.gov/articles/PMC3585312/
- **S-new-58** EV start-up failures (outcome-selected, other) — https://qz.com/nikola-bankrupt-failed-electric-ev-startup-fisker-canoo-1851765824 ; https://www.nbcnews.com/business/autos/electric-car-company-fisker-files-bankruptcy-protection-rcna157814
- **S-new-59** Non-GAAP measures and KPIs:
  - C&DI 100.01 (Deloitte Roadmap) — https://dart.deloitte.com/USDART/home/accounting/sec/sec-reporting-interpretations-manual/roadmap-non-gaap-financial-measures/chapter-4-non-gaap-measures-that/4-3-what-is-a-potentially
  - Aterian response letter (2021) — https://www.sec.gov/Archives/edgar/data/1757715/000156459021048879/filename1.htm
  - Release 33-10751 KPI guidance (KPMG summary, other) — https://kpmg.com/us/en/frv/reference-library/2020/sec-issues-mda-guidance-kpi-metrics.html
- **S-new-60** ASU 2023-07 segment expenses (Forvis Mazars summary, other) — https://www.forvismazars.us/getmedia/3b12d823-a9cc-48b3-b397-9805caed82dd/FASB-Mandates-New-Segment-Details-for-Public-Companies-in-2024.pdf
- **S-new-61** Intel FY2024 10-K — https://www.sec.gov/Archives/edgar/data/50863/000005086325000009/intc-20241228.htm
- **S-new-62** Bailey, Borwein, López de Prado & Zhu (2014), "Pseudo-Mathematics and Financial Charlatanism", Notices of the AMS 61(5) — https://doi.org/10.1090/noti1105 ; Harvey, Liu & Zhu (2016), "…and the Cross-Section of Expected Returns", Review of Financial Studies 29(1) — https://doi.org/10.1093/rfs/hhv059
- **S-new-63** Small-sample statistics:
  - Hyndman & Fan (1996), "Sample Quantiles in Statistical Packages", The American Statistician 50(4) — https://doi.org/10.1080/00031305.1996.10473566
  - Rousseeuw & Verboven (2002), Computational Statistics & Data Analysis 40(4):741–758 — https://doi.org/10.1016/S0167-9473(02)00078-6
  - Rousseeuw & Croux (1993), JASA 88:1273–1283 (summary, other) — https://en.wikipedia.org/wiki/Robust_measures_of_scale
  - Croux & Rousseeuw (1992), "Time-Efficient Algorithms for Two Highly Robust Estimators of Scale", Computational Statistics, Vol. 1 (Physica), 411–428, doi:10.1007/978-3-662-26811-7_58. The primary is paywalled and was not read.
    - Its small-n MAD factors were read on 2026-10-12 from the source of the R package revss 3.1.0 (`R/revConstants.R`, `bnMdADMdCR`) — https://raw.githubusercontent.com/cran/revss/master/R/revConstants.R ; package manual — https://cran.r-project.org/web/packages/revss/revss.pdf
    - Factors for n = 2 to 9: 1.196, 1.495, 1.363, 1.206, 1.200, 1.140, 1.129, 1.107. For n ≥ 10: n ÷ (n − 0.8).
    - `madn` returns MAD × 1.4826 × the factor.
  - Leys et al. (2013), J. Experimental Social Psychology 49(4):764–766 — https://orbilu.uni.lu/handle/10993/59204
- **S-new-64** Kothari, Shanken & Sloan (1995), J. Finance 50(1) — https://ideas.repec.org/a/bla/jfinan/v50y1995i1p185-224.html
- **S-new-65** Shumway (1997), "The Delisting Bias in CRSP Data", J. Finance 52(1):327–340 — https://ideas.repec.org/a/bla/jfinan/v52y1997i1p327-40.html ; Shumway & Warther (1999), J. Finance — https://ideas.repec.org/a/bla/jfinan/v54y1999i6p2361-2379.html
- **S-new-66** Piotroski and Mohanram follow-ups:
  - Woodley, Jones & Reburn (2011), J. Accounting & Finance 11(4) — https://researchworks.creighton.edu/esploro/outputs/journalArticle/Value-Stocks-and-Accounting-Screens-Has/991006117468602656
  - Piotroski & So (2012), Review of Financial Studies 25(9):2841–2875 — https://ideas.repec.org/a/oup/rfinst/v25y2012i9p2841-2875.html
  - Piotroski (2005), discussion of Mohanram, Review of Accounting Studies 10:171–184 — https://academicnewsletter.sufe.edu.cn/info/414562
  - CXO summary of Mohanram (other) — https://www.cxoadvisory.com/fundamental-valuation/classic-paper-mohanrams-efficient-growth-investing/
  - AAII G-score article (other) — https://www.aaii.com/journal/article/calculating-mohanram-g-score-using-si-pro-and-microsoft-excel
- **S-new-67** Siegel (2016), "The Shiller CAPE Ratio: A New Look", Financial Analysts Journal 72(3) — https://rpc.cfainstitute.org/research/financial-analysts-journal/2016/the-shiller-cape-ratio-a-new-look
- **S-new-68** Intel's 2025 strategic share sales, from Intel's own 8-Ks (read 2026-10-12). This replaces the Yahoo Finance copy.
  - **US Department of Commerce.** 8-K filed 2025-08-25 (0000050863-25-000129; Items 1.01, 3.02, 7.01, 8.01) — https://www.sec.gov/Archives/edgar/data/50863/000005086325000129/intc-20250822.htm
    - Agreement dated 2025-08-22: 433,323,000 shares for $8,869.8M.
    - Two tranches:
      - 274,583,000 shares at $20.74, paid with $5,695.0M of accelerated CHIPS direct funding;
      - 158,740,000 shares at $20.00, held in escrow and released as $3,174.8M of Secure Enclave funds arrive.
    - The average is $20.47 a share, the figure Round 3 uses.
    - Also a 5-year warrant for 240,516,150 shares at $20.00. It is exercisable only if Intel's ownership of its foundry business falls below 51%.
  - **SoftBank.** 86,956,522 shares at $23.00 ($2.0B), agreement dated 2025-08-18. 8-K 0000050863-25-000126 — https://www.sec.gov/Archives/edgar/data/50863/000005086325000126/intc-20250818.htm
  - **NVIDIA.** 214,776,632 shares at $23.28 ($5.0B), agreement dated 2025-09-15. 8-K 0000050863-25-000155 — https://www.sec.gov/Archives/edgar/data/50863/000005086325000155/intc-20250915.htm
- **S-new-69** Mercury Research Q4 2025 server share, via heise (other, grade B; extends S36) — https://heise.de/-11176017

**Fixing the duplicate S101.** SOURCES.md has two S101 entries.
- Keep S101 for the telecom vendor-financing entry (Lucent). M02_THEMES.md cites it by ID in D-M02-41 and D-M02-43.
- Move McConnell & Muscarella (1985) to S122. It is tagged D-M02-28, but no doc cites it by ID, so only SOURCES.md changes.
- The provisional IDs above then become S123 onward.

**Citation fixes needed in other sections** (from the critique, and from the checks behind this list):
1. **Round 1, item 7.** "(S98)" should read "(S39 for the submissions history; S-new-src-1 for the 8-K item list)". S98 is the safe-harbor / Reg FD entry.
2. **Round 2, item 4.** "(S98, Form 8-K)" should read "(S-new-src-1: General Instructions B.1 and B.3, Item 4.02)". The "no Item 4.02 before 2004-08-23" cutoff cites S-new-src-2.
3. **Round 1 worked example.** The inventory row's source becomes `InventoryNet` (S-new-1). Delete "Inventory comes from edgar.tools (secondary)".
4. **Round 2, Alphabet.** Net income +$3.0B is confirmed in Note 1 (S-new-22). Delete "re-confirm at build".
5. **Rounds 2 and 3, Hou, Xue & Zhang.** The anomaly counts differ by version (S-new-10). Align them.
6. **Round 3 case 7 and Round 6 item 6.** S-new-68 is now Intel's 8-K.
   - $20.47 is the average of two tranches, and a contingent warrant comes with it.
   - The SoftBank and NVIDIA placements are further strategic-stake examples.
7. **Round 5.** The "URL to add" notes for Rivian's 2025 deliveries and Tesla's FY2024 10-K are resolved (S-new-47, S-new-50). Tesla's exact 2022 and 2023 deliveries cite the 10-Ks, not the delivery 8-Ks, which round them.
8. **Round 6.**
   - The Micron TTM asterisk can go (S-new-1).
   - Inventory days of 153 and 235 are oral figures from the call. The primary-computed values are about 151 and about 213 (S-new-5).
9. **S1.6 stale state (critique 9).** Deadline sources are now available (S-new-src-4, S-new-src-5).
10. **S2.6 CFO steps (critique 11).** A source for cash-flow classification shifting is now available (S-new-src-6).

**Pre-review reading checklist (critique 31).** Each primary is read before its round is presented, not before build. Status on 2026-10-12:

| Primary | Round | Recommendations that depend on it | Status |
|---|---|---|---|
| C&DI 104.20 (S-new-src-3) | 2 | 2.2a; S2.6 labels | **Read.** Issued 2025-04-11. The box is ticked whenever prior statements are revised to correct an error, Big R or little r. An out-of-period adjustment does not tick it. The answer is silent on changes in accounting principle, reclassifications and recasts. So a false flag only says no error correction was reported; it is not evidence of an `accounting_change` (supports critique 11). |
| Altman Z″ zones 1.1 / 2.6 (S34, S-new-36) | 4 | S4.4; the Rivian reading; 4.1a | **Partly read.** Altman (2000) confirms the formula and the purpose of the constant, but gives no Z″ zones. Its EM-score rating table offers primary anchors instead: Rivian's −2.12 with the constant is below the D anchor of 0. Candidate primaries for the zones, Altman, Hartzell & Peck (1995, Salomon Brothers) and Altman & Hotchkiss (Corporate Financial Distress and Bankruptcy, 3rd ed.), are not online. |
| Croux & Rousseeuw (1992) small-n MAD factors (S-new-63) | 6 | 6.2a | **Factors read from revss; primary paywalled.** Not checked against the paper. |
| Dickinson (2011) stage table (S-new-56) | Round 1 if stage moves forward (critique 19), else Round 5 | 5.1a | **Not read.** Paywalled at TAR; the mapping comes from a secondary paper. |
| Ohlson (1980) (S-new-38) | 4 | 4.1a adds the O-score only after reading | **Not read.** No free copy found. The O-score stays out until it is read. |
| Mohanram (2005) variance windows (S33) | 6 | 6.3a | **Not read.** Secondary sources say 5 years (CXO; GuruFocus for ROA). G stays out until it is read. |
| Beneish (1999) ACCR definition (S105) | 2 | 2.1a; S2.3 | **Not read.** The teaching note may differ from the original. |
| Lev & Thiagarajan (1993); Abarbanell & Bushee (1997) gross-margin signal construction (S-new-52) | 5 | 5.2 | **Not read.** |

**Reused IDs:** S02, S03, S32–S37, S39–S41, S43, S47, S50, S56, S81, S97, S100, S103, S105, S109, S110, S112.
- S98 drops out of the pack once citation fixes 1 and 2 are applied.
- S44 (Cohen & Frazzini 2008) and S45 (major-customer dependence) appear in the M04 header but no round cites them yet. The customer-signal design (critique 2) must cite them, or they come out of the header.

**Replaced by primary sources:**
- edgar.tools inventories → `InventoryNet`;
- Seeking Alpha Rivian FY2025 release → EDGAR Ex. 99.1;
- Business Wire Rivian deliveries → 8-K Ex. 99.1;
- Yahoo Finance Intel stake → Intel 8-K;
- Chava & Roberts dead PDF → RePEc.

**Dropped as unverifiable:**
- Going-concern rates attributed to Carson et al. (2013): a secondary summary only.
- Begley, Ming & Watts (1996): no working link.
- Bernard & Noel (1991) and Banz & Breen (1986): no link.
- The 2020 inventory-gap replication: uncited.
- Meta's 2025 server-life figure: inconsistent secondary source.
- GE's ASC 606 split amounts: secondary only.
- Invitae Z″ values: to be recomputed from fixtures.

### New sources added in this section
- **S-new-src-1** SEC, Form 8-K General Instructions and Items (PDF; OMB 3235-0060, expires 2027-11-30) — https://www.sec.gov/files/form8-k.pdf
  - General Instruction B.1: a report is due within four business days of the event.
  - B.3: no new report is needed when substantially the same information was "previously reported", as defined in Rule 12b-2.
  - Items 1.02, 1.03, 2.04, 4.01 and 4.02. Item 4.02(a) covers a company conclusion of non-reliance; 4.02(b) covers notice from the auditor.
  - Read 2026-10-12.
- **S-new-src-2** SEC Release 33-8400, "Additional Form 8-K Disclosure Requirements and Acceleration of Filing Date", issued 2004-03-16, effective 2004-08-23 — https://www.sec.gov/files/rules/final/33-8400.htm ; index page — https://www.sec.gov/rule-release/33-8400
  - It added Item 4.02 and shortened most 8-K deadlines to four business days. That is the basis for "no Item 4.02 history before 2004-08-23".
- **S-new-src-3** SEC staff, Exchange Act Forms Compliance and Disclosure Interpretations, Question 104.20 (2025-04-11) and the related 104.21–104.25 on the 10-K cover checkboxes — https://www.sec.gov/rules-regulations/staff-guidance/compliance-disclosure-interpretations/exchange-act-forms
  - Read 2026-10-12. The findings are in the checklist above.
- **S-new-src-4** SEC, Form 10-K General Instruction A.(2) (OMB 3235-0063, expires 2029-09-30): due 60 days after fiscal year-end for large accelerated filers, 75 for accelerated filers and 90 for all others — https://www.sec.gov/files/form10-k.pdf
  - Form 10-Q General Instruction A.1 (OMB 3235-0070, expires 2028-09-30): due 40 days after quarter-end for large accelerated and accelerated filers, 45 for all others — https://www.sec.gov/files/form10-q.pdf
  - Read 2026-10-12.
- **S-new-src-5** Exchange Act Rule 12b-25, 17 CFR 240.12b-25 — https://www.law.cornell.edu/cfr/text/17/240.12b-25
  - The NT form is due no later than one business day after the report's due date.
  - Under paragraph (b), the report is then treated as timely if filed within 15 calendar days of the due date (annual reports) or 5 days (quarterly reports).
  - Latest timely dates (computed): 10-K 75 / 90 / 105 days and 10-Q 45 / 45 / 50 days after period end, for large accelerated / accelerated / other filers.
  - Read 2026-10-12.
- **S-new-src-6** Lee, Lian Fen (2012), "Incentives to Inflate Reported Cash from Operations Using Classification and Timing", The Accounting Review 87(1):1–33, doi:10.2308/accr-10156. Summary (abstract-level) — https://academicnewsletter.sufe.edu.cn/info/415854
  - Firms inflate reported CFO by shifting items between cash-flow categories, within and beyond GAAP, and by timing payments and collections.
  - The incentive is stronger under financial distress, near the investment-grade cut-off, and where analysts forecast cash flow.
  - This supports treating a CFO/CFI/CFF shift as its own concern (critique 11).

### Provisional IDs → SOURCES.md (build Part 0, 2026-10-12)
All 131 provisional IDs map to S123–S225 in order of first definition in this pack; 43 IDs that define the same URL or work merge into 15 S-numbers. S122 is McConnell & Muscarella (the duplicate S101). The text above keeps the provisional IDs.

| Provisional ID(s) | S-number |
|---|---|
| S-new-r1-1, S-new-r2-8, S-new-r3-4, S-new-r3-5, S-new-r4-4, S-new-r5-2, S-new-r6-1, S-new-r6-6, S-new-r6-7, S-new-bp-3, S-new-1 | S123 |
| S-new-r1-2, S-new-r2-1, S-new-r3-3, S-new-src-1 | S124 |
| S-new-r1-3, S-new-src-4 | S125 |
| S-new-r1-4, S-new-r6-4, S-new-src-5 | S126 |
| S-new-r1-5 | S127 |
| S-new-r1-6, S-new-r4-3 | S128 |
| S-new-r1-7 | S129 |
| S-new-r1-8, S-new-61 | S130 |
| S-new-r1-9 | S131 |
| S-new-r2-2, S-new-src-3 | S132 |
| S-new-r2-3, S-new-src-6 | S133 |
| S-new-r2-4 | S134 |
| S-new-r2-5, S-new-r5-5, S-new-50 | S135 |
| S-new-r2-6 | S136 |
| S-new-r2-7, S-new-r3-7 | S137 |
| S-new-r2-9 | S138 |
| S-new-r3-1 | S139 |
| S-new-r3-2 | S140 |
| S-new-r3-6, S-new-68 | S141 |
| S-new-r3-8 | S142 |
| S-new-r3-9 | S143 |
| S-new-r4-1 | S144 |
| S-new-r4-2, S-new-38 | S145 |
| S-new-r4-5, S-new-bp-4 | S146 |
| S-new-r4-6 | S147 |
| S-new-r5-1 | S148 |
| S-new-r5-3 | S149 |
| S-new-r5-4 | S150 |
| S-new-r5-6, S-new-47 | S151 |
| S-new-r5-7 | S152 |
| S-new-r5-8 | S153 |
| S-new-r5-9 | S154 |
| S-new-r5-10 | S155 |
| S-new-r6-2 | S156 |
| S-new-r6-3, S-new-63 | S157 |
| S-new-r6-5 | S158 |
| S-new-bp-1 | S159 |
| S-new-bp-2 | S160 |
| S-new-bp-5 | S161 |
| S-new-bp-6 | S162 |
| S-new-2 | S163 |
| S-new-3 | S164 |
| S-new-4 | S165 |
| S-new-5 | S166 |
| S-new-6 | S167 |
| S-new-7 | S168 |
| S-new-8 | S169 |
| S-new-9 | S170 |
| S-new-10 | S171 |
| S-new-11 | S172 |
| S-new-12 | S173 |
| S-new-13 | S174 |
| S-new-14 | S175 |
| S-new-15 | S176 |
| S-new-16 | S177 |
| S-new-17 | S178 |
| S-new-18 | S179 |
| S-new-19 | S180 |
| S-new-20 | S181 |
| S-new-21 | S182 |
| S-new-22 | S183 |
| S-new-23 | S184 |
| S-new-24 | S185 |
| S-new-25 | S186 |
| S-new-26 | S187 |
| S-new-27 | S188 |
| S-new-28 | S189 |
| S-new-29 | S190 |
| S-new-30 | S191 |
| S-new-31 | S192 |
| S-new-32 | S193 |
| S-new-33 | S194 |
| S-new-34 | S195 |
| S-new-35 | S196 |
| S-new-36 | S197 |
| S-new-37 | S198 |
| S-new-39 | S199 |
| S-new-40 | S200 |
| S-new-41 | S201 |
| S-new-42 | S202 |
| S-new-43 | S203 |
| S-new-44 | S204 |
| S-new-45 | S205 |
| S-new-46 | S206 |
| S-new-48 | S207 |
| S-new-49 | S208 |
| S-new-51 | S209 |
| S-new-52 | S210 |
| S-new-53 | S211 |
| S-new-54 | S212 |
| S-new-55 | S213 |
| S-new-56 | S214 |
| S-new-57 | S215 |
| S-new-58 | S216 |
| S-new-59 | S217 |
| S-new-60 | S218 |
| S-new-62 | S219 |
| S-new-64 | S220 |
| S-new-65 | S221 |
| S-new-66 | S222 |
| S-new-67 | S223 |
| S-new-69 | S224 |
| S-new-src-2 | S225 |
