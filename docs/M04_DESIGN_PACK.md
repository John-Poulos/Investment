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

### What the research says
1. **Most M04 numeric inputs are already stored.**
   - The `fact` table keeps every companyfacts value from us-gaap, ifrs-full, dei and srt, each with its accession, form and filed date.
   - `series` holds 26 concepts (Q, FY, TTM, instant). Each has a first and a latest value and a `method` that names the tag used.
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
   - Checked 2026-10-12 (S-new-1):
     - META and Strategy have neither non-dimensional tag (404).
     - Alphabet has no dei count (404).
     - Apple's dei count is dated at the cover date: 2025-10-17 for a 2025-09-27 year end.
   - Weighted-average basic and diluted shares exist for all four.
   - No concept maps weighted-average shares or stock-based compensation (SBC).
   - Your 2026-10-07 note recommends separate concepts (M00_SEC_DATA.md line 104).
4. **The capex fallback reaches the user only on hover.**
   - `capex` falls back to `PaymentsToAcquireProductiveAssets`, which is broader: it includes software and intangibles. Amazon has used it since 2017 (S100).
   - `tabs/financials.html` shows `method` only in a tooltip.
   - M02's money view labels the fallback in text (`moneyflow/actuals.py:153`).
   - `FrameValue.tag` carries the tag, but no peer statistic flags or excludes fallback values.
5. **The peer machinery exists, but no peers are stored.**
   - `frames.py` has `peer_stats`, `robust_z`, `MIN_PEERS = 5`, and a closest-period match within ±45 days.
   - Nothing writes the `peer_group` and `peer_member` tables.
   - SIC codes exist only in `entity`, for resolved companies, and in EFTS hits. Frames carry none (D-SEC-9).
   - GICS explains return co-movement and key ratios better than SIC, NAICS or Fama-French, most of all for large firms, but it is not free (S-new-2). Text-based industries: S109.
6. **One offset tolerance for all period types misleads.**
   - Overlap arithmetic: a 45-day offset leaves about 88% overlap for a TTM window but about 51% for a quarter.
   - Observed offsets:
     - D-SEC-9: Micron ended 2025-05-29 and AVGO 2025-08-03 against a 2025-06-30 target (−32 and +34 days).
     - Micron's TTM ending 2022-12-01 is 30 days before calendar year-end.
   - Effect on the Q1 test: comparing Micron's fiscal year ending 2022-09-01 (121 days off) with Intel's calendar 2022 gives Intel z −3.35. The offset-respecting Micron TTM gives −1.71 (Round 6).
   - 53-week years add about 2% to that year's growth. Intel's FY2022 ran 2021-12-26 to 2022-12-31 (S-new-1).
   - Research data align fiscal years by convention (S-new-3):
     - Compustat assigns year-ends from January to May to the prior year.
     - Fama-French lag fiscal year-ends by at least 6 months.
7. **Red-flag events are already typed.**
   - `events.py` maps 8-K items 1.03, 1.05, 2.04, 2.05, 2.06, 3.01, 4.01 and 4.02 to `red_flag` for M04, and 3.02 to `capital`. Pre-2004 items are mapped through `LEGACY_ITEMS`. The full submissions history is covered (S98).
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

**What is buildable now**

| Need | Status | Gap or new work |
|---|---|---|
| Piotroski F, Altman Z″, Beneish, accruals, inventory days | Buildable from `fact` and `series` | Shares split first (F's equity signal) |
| Altman Z (manufacturers) | Needs cover shares × Tiingo price | Watchlist and tracked names only (DS8) |
| Dechow misstatement score | Needs 6–7 extra concepts | S1.3 |
| Peer z (Q1/Q2) | Code ready (`frames.py`) | No stored peers; one companyfacts request per peer |
| Restatement deltas | Data in `fact` | Walk across tags (defect 2a) |
| 8-K red flags | Typed in `event`, full history | 4.02 text only for filings fetched since backfill |
| Late filings, amendments, shelves, 424B, S-8 | `filing` metadata | Documents not fetched |
| Going-concern and covenant text | FTS5 over latest 10-K/10-Q and new 8-Ks | Prior years (DS7): EFTS + fetch |
| Dilution | Buybacks and equity proceeds mapped (`moneyflow/allocation.py`) | Basic/diluted weighted-average and SBC concepts; 424B security class |
| Runway and maturities | Cash, short-term investments, OCF, capex mapped; maturity, revolver and current-debt tags in `fact` where non-dimensional | Revolver capacity often dimensional |
| Segment revenue, customer concentration %, multi-class cover shares | — | Dimensional: missing from companyfacts and from `instance.py` |
| Unit KPIs | Tesla EX-99.1 stored (DS2) | Not parsed; EX-99.2 not fetched |
| Industry pricing and volume | — | New register entry |
| Guidance record (R19) | Ledger built; guided-vs-actual for capex only | Revenue, EPS and gross-margin hit rate not built; a target dropped between releases is not detected (`guidance/changes.py` has no "removed" kind) |
| Cycle history | XBRL from 2009–2011 | Pre-2009 troughs missing |

### Worked example — Micron FY2022 → FY2023 (CvD case "expect CYCLICAL_TROUGH")
Sources: S-new-5. Figures were checked through excerpts of the 10-K and release. Inventory comes from edgar.tools (secondary). Re-check every row against stored `fact` rows at build.

| Concept (engine) | FY2022 | FY2023 | Change | Source |
|---|---|---|---|---|
| revenue | $30,758M | $15,540M | −49.5% | 10-K, release |
| cost_of_revenue | $16,860M | $16,956M | +0.6% | 10-K |
| gross_profit | $13,898M | $(1,416)M | GM 45.2% → −9.1% | 10-K |
| operating_income | $9,702M | $(5,745)M | margin 31.5% → −37.0% | 10-K |
| operating_cash_flow | $15,181M | $1,559M | −89.7% | release |
| capex (PP&E payments, first tag) | $12,067M | $7,676M | −36.4% | 10-K |
| Micron's own "net capex" | — | $7.01B | about $0.67B below the tag | release (company definition) |
| inventory | $6,663M | $8,387M | +25.9% | edgar.tools (secondary) |
| inventory days (inventory ÷ COGS × 365) | 144.2 | 180.5 | +36 days | computed |

Point-in-time rows (real, S-new-1):

| Case | What the filings hold | What `series` does today |
|---|---|---|
| Tag switch | MU FY2018 revenue first filed 2018-10-15 under `Revenues` | first_filed 2019-10-17 under the new tag; an as-of-2018-11 read finds nothing |
| Split | MSTR Q3 2023 diluted shares first 14,221,000 (filed 2023-11-01), re-reported 142,214,000 (filed 2024-10-31) | first vs latest reads as +900% dilution, or as a "restatement" |
| Multi-class | META and MSTR: no non-dimensional period-end or cover count (404); GOOG: no dei count | share metrics silently missing |
| Non-periodic source | Alphabet 2023 net income in a DEF 14A (2026-04-24) | can become "latest" |

How M04 reads Micron:
- **Q2 (franchise):** gross margin collapsed, but the 10-K attributes it to lower DRAM and NAND prices, inventory write-downs and $382M of underutilization cost (S-new-5). The peer gross-margin gap must confirm.
- **Q1 (shared?):** WDC files with the SEC. SK hynix and Samsung do not, so they are "missing peers" (R24).
- **Supply response:** capex was cut 36%, consistent with the coordinated supply cuts in S37.
- **Capex definition:** the company states $7.01B and the tag gives $7,676M. This is exactly the case where the user must see which definition a value uses.

### All cases (data layer)
1. Tag present and stable → use it.
2. Tag switch, same or different value → walk all of the concept's tags in filed order.
3. Fallback tag broader than the concept → visible marker. Cases:
   - capex productive assets;
   - Micron's long-term debt, reported only as `LongTermDebtAndCapitalLeaseObligations` after `LongTermDebtNoncurrent` stops at 2013-05-30.
4. Company extension tag only → instance read where a recipe needs it (D-M02-32).
5. Dimensional only → "missing: dimensional". Examples: multi-class cover shares, segments, customer-concentration %, many revolvers.
6. Tag absent → missing, never zero. A reported zero is kept (Rivian's pre-revenue gross profit of 0).
7. Period before XBRL, or before the tag's first use → "insufficient history".
8. Value revised:
   - Big R restatement or little r revision;
   - recast (discontinued operations, new standard, segment change);
   - split.
9. Value arriving in an 8-K or DEF 14A → not "latest" for periodic analysis.
10. Year-to-date-derived quarters, including filers with no discrete Q4 facts (Rivian).
11. Instants at the balance-sheet date vs the cover date.
12. 52/53-week years and off-calendar fiscal years.
13. Peers:
    - in tolerance;
    - out of tolerance;
    - non-SEC (SK hynix, Samsung);
    - an acquisition year (AMD 2022 includes Xilinx);
    - fallback-tag values;
    - fewer than 5 peers.
14. Financials (SIC 6000–6799) and funds (ETV files N-CSR) → excluded from scores.
15. Company not on the watchlist → no stored facts; owner-run fetch.
16. Bankrupt or delisted company → last state goes stale (Invitae never filed an FY2023 10-K).

### Suggestions
- **S1.1 As-of reads first.** Add `facts_as_of(cik, concept, as_of)` built from `fact`:
  - use facts filed on or before `as_of`, from 10-K, 10-Q, 10-K/A and 10-Q/A only;
  - apply tag priority *after* the time filter;
  - derive quarters and TTM from those facts.

  `series` stays for live views. The restatement walk (Round 2) and backtests (Round 6) use `fact`. Fixtures:
  - Micron FY2018 revenue known as of 2018-10-15;
  - WDC FY2023 revenue = $12,318M as of 2024 (S-new-1).
- **S1.2 Shares split** per question 1.1.
- **S1.3 One M04 extra-concept list.** It reuses `Concept`, needs no new fetch, and reports a missing tag as a probe, never as zero. Tags:
  - `IncomeTaxExpenseBenefit`, pretax income, `IncomeLossFromContinuingOperations`;
  - `DebtCurrent` / `LongTermDebtCurrent`, `ShortTermBorrowings`, `CommercialPaper`;
  - maturities year 1–5 and after year 5, `LineOfCreditFacilityRemainingBorrowingCapacity`, restricted cash;
  - `ContractWithCustomerLiabilityCurrent` (with `DeferredRevenueCurrent` before 2018), `ContractWithCustomerAssetNetCurrent`, `ContractWithCustomerPerformanceObligationSatisfiedInPreviousPeriod`;
  - `ShareBasedCompensation`, `ProceedsFromIssuanceOfCommonStock`, plan-issuance proceeds, `ProceedsFromIssuanceOfLongTermDebt`;
  - `LongTermInvestments`, `PreferredStockValue`, `AccruedIncomeTaxesCurrent`;
  - investing and financing cash-flow totals;
  - `InventoryWriteDown`, `AssetImpairmentCharges`, `GoodwillImpairmentLoss`, `RestructuringCharges`, `AdvertisingExpense`.
- **S1.4 Method visible.** Every M04 value carries its tag and accession, and fallback values are marked (question 1.2).
- **S1.5 Signal names fixed now.** M04 becomes the first writer of the D13 `signal` table. Dechow's score is named `misstate_f`; Piotroski keeps `f_score`.
- **S1.6 Stale state.** A company becomes `stale` when its expected filing date plus 45 days passes with no filing.
- **S1.7 Guidance record (Q2).** Add a revenue, EPS and gross-margin hit rate using `periods.span_of` and `value_for` against `series`. Add a "removed" change kind, for the profile's "quiet target removals".
- **S1.8 Register entries in DATA_SOURCES.md:**
  - DS12 dimensional facts (segments, customer concentration, multi-class cover shares);
  - DS13 industry price and volume series (free FRED producer prices; SIA/WSTS monthly at grade B; to check);
  - DS14 unit KPIs beyond Tesla (generalise DS2, including EX-99.2 letters);
  - DS15 historical 4.02 8-K texts.
- **S1.9 Housekeeping.** SOURCES.md uses S101 twice. Renumber one when the S-new IDs are assigned.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| `series` first vs latest | A tag switch makes "first" a later comparative; 8-K or DEF 14A facts become "latest" | As-of reads from `fact`, periodic forms only |
| Shares | Cover and period-end dates mixed; multi-class counts missing; splits | Separate concepts; "missing: multi-class" label; split guard |
| Capex fallback | Broader tag; peer z mixes definitions | Visible marker; excluded from peer statistics |
| Peer offset | The cycle turns inside a 1–2-month offset; 53-week years | Per-type tolerance; each peer's end date shown; 53-week flag |
| SIC peers | Coarse or stale codes; conglomerates; key peers abroad | Owner curation (R24); non-SEC peers stored by name and flagged missing |
| Peer acquisitions | AMD +43.6% in 2022 includes Xilinx | Flag acquisition years (8-K 2.01, `BusinessAcquisition*` tags) |
| History depth | XBRL starts 2009–2011 and later for some concepts | "Insufficient history", never "first deep decline" |
| Frames in backtests | Last-filed values | Live breadth only |

### Questions
**1.1 Shares concepts**
- (a) *Recommended.* Four series: `shares_period_end`, `shares_cover` (kept on its own cover date), `shares_basic_wavg` and `shares_diluted_wavg`, plus `sbc`. For multi-class filers with no non-dimensional count (META, GOOG, MSTR), read the class-summed cover count from the filing's R1 page or instance, at one request per 10-K/10-Q. Why: it matches your 2026-10-07 note and fixes three silent gaps.
- (b) The four series; multi-class names use the basic weighted average only, labelled "lagging".
- (c) Keep one series and add the diluted weighted average.

**1.2 Capex fallback tag**
- (a) *Recommended.* A visible "≈ broader tag" marker plus a legend wherever the value appears; tooltip kept. Fallback values are excluded from peer statistics and listed as "not like-for-like". Why: closes the open item and keeps peer z on one definition.
- (b) Marker shown; fallback values included in peer statistics, flagged.
- (c) A separate row per tag.
- (d) Tooltip only (today).

**1.3 Peer discovery**
- (a) *Recommended.* The engine proposes peers from 4-digit SIC: `entity.sic`, EFTS `sics`, and one live probe of EDGAR browse-by-SIC. The owner confirms or edits them in `peer_group`. Product-market peers beyond SIC are allowed (Intel: AMD, NVIDIA, Qualcomm). Non-SEC peers are stored by name as "missing". Why: follows R24 and avoids the 2 GB bulk file (S50).
- (b) Proposals from 3-digit SIC.
- (c) The owner lists peers by hand only.
- (d) Bulk submissions.zip.

**1.4 Peer period offset**
- (a) *Recommended.* TTM ±45 days; quarters and instants ±35 days. That covers the Micron offsets of −30 and −32 days already seen and leaves at least 61% overlap for a quarter. Peers outside the tolerance show as "no comparable period" and count toward the fewer-than-5 fallback. Each peer's end date is shown and 53-week years are flagged. Why: Micron stays comparable while two-month mismatches are stopped.
- (b) TTM ±45; quarters and instants ±31 (Micron drops out in some quarters).
- (c) Quarters and instants ±16, with a calendar-quarter fallback labelled "offset N days".
- (d) ±45 for everything (today).

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
   - SGI mechanically pushes fast growers toward "manipulator".
3. **Dechow et al. misstatement score** (S-new-16, primary read).
   - Built from SEC enforcement releases (AAERs) 1982–2005 covering 676 misstating firms.
   - Model 1: −7.893 + 0.790·rsst_acc + 2.518·ch_rec + 1.191·ch_inv + 1.979·soft_assets + 0.171·ch_cs − 0.932·ch_roa + 1.029·issue, logistic. Score = probability ÷ 0.0037.
   - Score > 1.00 catches 68.6% of misstaters and wrongly flags 36.3% of clean firm-years. Score > 2.45 catches 18.8% and wrongly flags 5%.
   - Out of sample (Model 3, 1999–2002): 73.8% caught, 38.3% false flags.
   - Marginal effects are largest for soft assets (0.595) and issuance (0.559), against 0.099 for ch_rec.
   - Large firms are over-represented among misstaters, partly because of scrutiny. 82.5% of sample firms issue in a given year, so for large caps `issue` = 1 discriminates little (inference).
4. **Restatements.**
   - **What triggers a 4.02:** Item 4.02(a) applies when the company concludes prior statements "should no longer be relied upon"; 4.02(b) when the auditor gives that notice. The 8-K is due within 4 business days (S98, Form 8-K).
   - **Gap:** General Instruction B.3 waives the 8-K when the same information was already reported in a 10-K or 10-Q.
   - **Little r** (immaterial corrections, no 4.02):
     - Little r rose from about 35% of restatements in 2005 to nearly 76% in 2020, and SEC staff see some materiality analyses biased toward "immaterial" (S-new-17, Munter).
     - Little r corrections predict later errors, material weaknesses and comment letters, with modestly negative returns (S-new-18).
     - Errors must be separated from irregularities (S-new-18, Hennes et al.).
   - **Big R base rates:**
     - About 3% of companies a year (2005–2024).
     - 29% followed an auditor change in the prior year, against an 11% base rate (S-new-17, PCAOB).
   - **Price reaction:** the 4.02 abnormal return vs SPY is about −1.1% at 1 day and −2.0% at 20 days (S-new-17, vendor).
   - **The 10-K cover checkbox** has been in force since 2023 and is tagged `dei:DocumentFinStmtErrorCorrectionFlag` (S-new-19).
     - The research notes report staff guidance (Exchange Act Forms C&DI 104.20, April 2025): the box is ticked for any error correction, including little r revisions, but not for retrospective changes in principle. Read the C&DI text before build.
     - The flag is not in companyfacts (numeric only), so it needs one instance fetch per 10-K from 2023.
5. **Most first-vs-latest deltas are not errors.**
   - Common causes: ASC 606 retrospective adoption, discontinued-operations recasts and 8-K recasts (worked example, S-new-1).
   - One mechanical test: a reclassification leaves net income unchanged while revenue moves. It must be applied step by step between consecutive versions.
6. **The GE pattern** (S03, primary S-new-20, ¶5–8, ¶13–14).
   - Cost-estimate reductions gave GE Power Services more than $1.4B of revenue and earnings in 2016, and more than $1.1B in the first three quarters of 2017. That was 29% and 45% of GE Power segment profit.
   - A $5B deferred balance within contract assets rose with them.
   - Factoring added more than $1.4B (2016) and more than $500M (first three quarters of 2017) to Industrial Cash Flow, about 12% and 33% of the total. It pulled forward $878M from 2018, $585M from 2019, $407M from 2020 and $400M from later years.
   - Penalty $200M; no restatement.
   - Estimate changes on average make earnings more useful, with limited support for widespread manipulation (S-new-21, Albrecht et al.).
   - About 500 material estimate changes occur a year (2000–2018). Income-increasing changes outnumber decreasing ones almost every year. Depreciation and amortization come first, percentage-of-completion second (S-new-21, Audit Analytics).
   - Watchlist cases (S-new-22):
     - Alphabet 2023 extended server lives from 4 to 6 years: depreciation −$3.9B; net income +$3.0B (Note 1; re-confirm at build).
     - Amazon 2025 shortened a subset from 6 to 5 years: D&A +$1.4B, net income −$1.0B.
   - No standard numeric tag exists for estimate changes (frames for `ChangeInAccountingEstimateFinancialEffect` CY2024 → 404, S-new-24), so they need text extraction.
7. **Revenue recognition.**
   - Improper revenue recognition was the most common technique, in 61% of 347 SEC fraud cases from 1998–2007 (S-new-23, COSO via BDO).
   - Revenue-based models detect manipulation better than accrual models (S-new-23, Stubben).
   - The ASC 606 catch-up footprint is `ContractWithCustomerPerformanceObligationSatisfiedInPreviousPeriod`, tagged by 126 filers in CY2024 (Lockheed $1.2B, Northrop $396M, RTX −$144M) (S-new-24).
   - Contract assets: 579 filers, none found on the watchlist.
   - Contract liabilities: 2,034 filers, including BA, MSFT, AAPL, AMZN, NVDA, MU and MSTR.
   - DSO is already built (`financing/credit.dso`, D-M02-47).
8. **Cash conversion** is the most robust large-cap measure (S-new-6, S-new-12). But CFO can be engineered (GE factoring) and distorted on a consolidated basis: GE's 2016 CFO was −$244M against net income of $8.83B, cause not decomposed (S-new-1).
9. **Staging.** For young growth firms, accrual size, SGI and Δreceivables partly measure growth (S-new-7), so use own-history, growth-adjusted comparisons. Event flags are stage-neutral.

### Worked example — GE restatement walk (S-new-1, companyconcept JSON fetched 2026-10-12; $M)

| Concept, period | First reported (filed) | Later versions (filed) | Δ first → latest | Expected step labels |
|---|---|---|---|---|
| Net income FY2016 | 8,831 (2017-02-24) | 8,831 (2018-02-23); 7,500 (2019-02-26) | −1,331 (−15.1%) | Step to 2019-02-26: `accounting_change` (ASC 606 adopted retrospectively; amount read from GE's 2018 filings at build); any unexplained residual → review |
| Net income FY2017 | −5,786 (2018-02-23) | −8,484 (2019-02-26); −8,484 (2020-02-24) | −2,698 | Step 1 as above; step 2 unchanged |
| Revenues FY2016 | 123,693 (2017-02-24) | 123,693; 119,469 (2019-02-26) | −3.4% | `accounting_change` |
| Revenues FY2017 | 122,092 (2018-02-23) | 118,243 (2019-02-26); 99,279 (2020-02-24) | −18.7% | Step 1 (−3.2%) `accounting_change`; step 2 (−16.0%) `reclass`, because net income stayed at −8,484 (likely discontinued operations; not verified) |
| CFO FY2016 | −244 (2017-02-24) | −244; 1,160 (2019-02-26) | +1,404 | `unexplained` → review |
| CFO FY2017 | 10,426 (2018-02-23) | 6,032; 6,554 (2020-02-24) | −37.1% | `unexplained` → review |
| CFO FY2015 | 19,891 (10-K, 2016-02-26) | same value in an 8-K filed 2016-06-03 | 0 | Shows that 8-K recasts carry XBRL |

**GE estimate share** (S-new-20): 29% and 45% of segment profit. Both would be "elevated" under S2.7's bands.

**Alphabet cash conversion** (S-new-1, S-new-22):

| Year | Net income | CFO | CFO / NI | Estimate change | Share of NI |
|---|---|---|---|---|---|
| 2022 | 59,972 | 91,495 | 1.53 | — | — |
| 2023 | 73,795 | 101,746 | 1.38 | Server lives to 6 years: NI +3.0B (re-confirm) | ≈ 4.1% → note |

**Lockheed Martin** catch-up revenue tag (S-new-1): $2.2B (2019), $2.0B, $2.2B, $2.0B, $1.6B, $1.2B (2024). These are revenue, not profit, so they are shown against own history only.

**Engine row (illustrative):** `{ticker:"GE", module_id:"M04", signal:"restate_delta", value:-0.160, method:"Revenues FY2017, step 10-K 2019-02-26 → 10-K 2020-02-24; cause=reclass (NI unchanged)", evidence_grade:"A", …}`

### All cases
1. 8-K 4.02(a), company-driven, or 4.02(b), auditor-driven and rarer.
2. Big R disclosed only in a 10-K or 10-Q (B.3, no 8-K).
3. Little r revision: dei flag true from 2023; text "revision", "immaterial error".
4. Out-of-period correction booked in the current period: no prior revision, box not ticked.
5. Retrospective accounting change (ASC 606) → not an error.
6. Discontinued-operations or spin recast: GE FY2017 revenue −16% with net income unchanged; WDC FY2023 revenue $12.3B → $6.3B.
7. Segment recast.
8. Stock split (MSTR 10×).
9. Tag switch with an unchanged value.
10. Rounding noise.
11. Value from an 8-K or DEF 14A.
12. Mixed step: a quantified accounting change plus a residual.
13. Estimate change, income-increasing or income-decreasing; company-level only, no segment.
14. Recurring estimate changes in the same direction.
15. Catch-up revenue tagged or untagged; pre-2018 periods have no ASC 606 tags.
16. Contract assets outgrowing revenue (GE); deferred revenue falling while revenue grows.
17. Net income near zero or negative (CFO/NI not meaningful); finance arm or discontinued operations inside CFO.
18. Factoring or supplier finance pulling cash forward.
19. Growth company: SGI and accruals inflated.
20. Missing input: no single SG&A line, or D&A instead of depreciation alone.
21. Auditor change (4.01) within 12 months of an error.
22. Period before 2004-08-23 → no Item 4.02 history.

### Suggestions
- **S2.1 `eq_cash`.**
  - TTM and 3-year CFO/NI, and cash-flow accruals ÷ average assets, against own 5-year range plus peer robust z.
  - `not_meaningful` when |NI| < 1% of revenue (D-SRCH-15 pattern).
  - Warning when 3-year CFO/NI < 0.8 for a mature company (working value).
- **S2.2 Reuse `credit.dso()`** and add:
  - `contract_asset_gap`: contract assets growing more than 10 pp faster than revenue for 2 quarters (the GE pattern);
  - `deferred_rev_gap`: deferred revenue falling year over year while revenue grows.

  Both compare the same quarter a year earlier (D-M02-47). Thresholds are working values.
- **S2.3 `mscore`.**
  - Annual, components shown, built from mapped concepts. "Incomplete" when any input is missing.
  - The method names the ACCR variant and any D&A or SG&A substitution.
  - −1.78 is shown beside the own-history and peer percentile.
  - Growth-stage names get the score without SGI and go to review.
- **S2.4 `misstate_f`.** Dechow Model 1, built after the S1.3 concepts.
  - Labelled "approximation", because the coefficients were estimated on Compustat items.
  - Shows the score, its own-history percentile, and bands > 1.00 and > 2.45.
- **S2.5 `restatement` event signal.**
  - Inputs: 4.02 (tagged a or b) as a grade-A warning; the dei flag; FTS5 phrases in stored 10-K/10-Q ("as restated", "revision of previously issued", "immaterial error", "out-of-period adjustment").
  - Little r → note.
  - A 4.01 in the prior 12 months escalates the signal.
- **S2.6 `restate_delta` from the S1.1 walk.**
  - Periodic forms only. One row per (concept, period), with each step between consecutive versions labelled:
    - `reclass`: net income unchanged within tolerance while revenue or CFO moved;
    - `accounting_change`: "retrospective" or "adopted ASU" in the later filing, or the dei flag false;
    - `error`: a 4.02, the dei flag true, or "restated"/"revision" text;
    - `split`: share or per-share concepts, checked against Tiingo `split_factor`;
    - otherwise `unexplained` → review (D8).
  - A step only partly explained keeps the residual as `unexplained`.
- **S2.7 `estimate_share`.**
  - Code finds ASC 250 and catch-up passages by FTS5 ("change in estimate", "estimated useful life", "cumulative catch-up", "profit booking rate"). Gemini runs only on request, with verified quotes (D21, D28).
  - Share = after-tax effect ÷ net income, or pre-tax effect ÷ operating income.
  - Bands: < 10% note, 10–25% watch, ≥ 25% elevated (below GE's 29% and 45%).
  - Three years of same-direction changes add a flag. Changes in both directions are shown.
- **S2.8 Information only** until D13 weights exist. No return claim is made for these ratios (the decay evidence above).
- **S2.9 Regression fixtures** (GE is not on the watchlist, so fixtures only):
  - GE 2016–17: contract-asset and estimate-share flags; FY2017 revenue labelled `accounting_change` then `reclass`, not `error`.
  - Alphabet 2023: note only.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Accruals | Growth inflates them; the return edge has decayed; balance-sheet versions are distorted by M&A | Cash-flow-statement version; own history; no return claim; stage-aware |
| CFO / NI | Meaningless near zero NI; finance arms and discontinued operations (GE 2016 −$244M); factoring pulls cash forward | `not_meaningful`; 3-year sums; shown beside DSO and receivables-sale text |
| M-score | SGI penalizes growers; cut-off from 1980s–90s data; more than 100 false positives per true one; ACCR variants | Components shown; screen only; method tag; "incomplete" on missing input; growth names → review |
| Misstatement score | Compustat coefficients; `issue` ≈ always 1 for large caps; name clash with Piotroski | "Approximation"; percentile; signal named `misstate_f` |
| 4.02 events | B.3 cases have no 8-K; no history before 2004-08-23 | dei flag plus text; "missing" before Aug 2004 |
| Error-correction checkbox | 10-Ks from 2023 only; out-of-period corrections do not tick it | Combine with text |
| Estimate changes | Disclosed only when material, often company-level only; income-decreasing changes exist | Sign and size vs profit; recurrence; both directions |
| Catch-up revenue tag | Revenue, not profit; only 126 filers | Own history only |
| Restatement delta | Recasts, standard adoptions, tag switches, 8-K/DEF 14A facts and rounding look like errors | Step labels; periodic forms only; tolerance (question 2.3) |

### Questions
**2.1 Score set and role**
- (a) *Recommended.* Cash conversion and accruals as earnings-persistence warnings, with no return weight. M-score now: components shown, own-history and peer percentile, the published cut-off displayed, growth names without SGI sent to review. Misstatement score after the extra concepts. Why: the decay evidence says these are screens, not signals; the M-score alone showed a net investor benefit (S-new-15).
- (b) Both scores now, same display.
- (c) Cash conversion only, no scores.

**2.2 Restatement sources and escalation**
- (a) *Recommended.* 4.02, plus the dei error flag (one extra request per 10-K from 2023), plus 10-K/10-Q text. An auditor change within the prior 12 months escalates. Why: catches the B.3 and little r cases an 8-K-only detector misses.
- (b) 4.02 events only.
- (c) As (a) without the escalation.

**2.3 Tolerance for unexplained deltas** (revenue, net income, CFO)
- (a) *Recommended.* Review a step larger than both 0.5% of the value and $1M. Recasts are shown as "recast, not an error", with no flag. Why: small enough to catch partly explained steps, and recasts are labelled before anything is queued.
- (b) Review above the smaller of 1% of the value or 5% of pretax income. The 5% figure is the rule of thumb SAB 99 discusses and warns against using alone (S-new-25).
- (c) Above 2% only.

**2.4 Estimate changes and prior filings**
- (a) *Recommended.* Bands < 10% / 10–25% / ≥ 25% of net income, both directions shown. Fetch one prior 10-K per watchlist company now (about 16 requests), which also closes DS7 for risk-factor diffs. Why: the 3-year recurrence test needs history, and DS7 is already an open gap.
- (b) Any quantified change is a note; the prior 10-K waits for M06/M11.
- (c) Flag income-increasing changes only.

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
10. **Data.**
    - Available now:
      - Every S-3, S-3ASR, S-1, S-8, F-3 and 424B2/3/5 is in `filing` (`sec/submissions.py`), with no new calls needed.
      - 8-K 3.02 is typed.
      - Annual CY frames of basic weighted-average shares give a universe cross-section in about 2 requests a year (annual, because Q4 is sparse in quarterly frames: D-SEC-9).
      - `dei:EntityPublicFloat` is already read (`themes/flags.py`).
    - Gaps and complications:
      - Documents for these forms are not stored.
      - Strategy's 21 424B5s in 2025 include preferred-stock offerings, so each supplement needs its security class before it counts.
      - ATM agreements usually come under 8-K 1.01 or 8.01 and need text phrases (old `bd_tools.py:446`).
      - Share bridges are mostly dimensional: META's `StockRepurchasedDuringPeriodShares` returns 404.
11. **Old-engine defects:**
    - S-1/A is counted as a shelf, but it is often an IPO or resale.
    - "covenant" and "waiver of" match almost every 10-K.
    - No amounts are read.

### Worked example
**Strategy (MSTR): extreme issuer funded by ATM programs** (S-new-1, S-new-33, S-new-35)

| Row | Value | Source |
|---|---|---|
| Cover shares 2025-07-31 | Class A 263,912,697 + Class B 19,640,250 = 283,552,947 | Q2 2025 10-Q R1 |
| Cover shares 2026-07-24 | Class A 364,585,501 + Class B 19,640,250 = 384,225,751 | Q2 2026 10-Q R1 |
| Cover-to-cover change | +35.5% (log 0.304) in 358 days | computed |
| Basic weighted average, Q2 2026 vs Q2 2025 (one accession) | 352,534,000 vs 275,244,000 → +28.1% (log 0.247) | companyconcept |
| Equity proceeds | FY2025 $16,271,959,000; H1 2026 $8,245,330,000 | companyconcept |
| SBC | FY2025 $53,369,000; H1 2026 $27,441,000 (not the driver) | companyconcept |
| ATM capacity (424B5, 2024-10-30) | $21.0B against 183,003,980 Class A shares at $255.34 → about 44.9% of Class A value | 424B5 + fee exhibit; computed |
| 424B5 count | 21 in 2025, 4 in 2026 to date; includes preferred offerings and program supplements | EDGAR list |
| Engine reading (illustrative) | "Extreme" band: +28% is near Fama-French's top-quintile average of 20–26% (approximate; measure and era differ). Issuance-funded model → `m04_dilution` review, not a warning | — |

**Meta (META) FY2025: buybacks more than offset SBC** (S-new-1)

| Row | Value |
|---|---|
| SBC | $20,427M (FY2024 $16,690M) = 10.2% of revenue ($200,966M), 17.6% of OCF ($115,800M) |
| Buybacks / RSU tax withholding | $26,248M / $18,400M |
| Basic weighted shares | 2,534M → 2,521M (−0.5%); diluted 2,614M → 2,574M (−1.5%) |
| Buyback offset (computed) | (26,248 + 18,400) ÷ 20,427 = 2.19×: about $44.6B of cash to cut basic shares 0.5% |

**Infleqtion (INFQ): post-SPAC warrants** (S-new-1)
- Warrants outstanding: 10,424,967, dated 2026-02-13 and repeated with that date in the 2026-08-18 10-Q, so possibly stale.
- Cover shares: 216,471,927 (2026-03-20) → 225,357,052 (2026-08-14), +4.1%.
- Overhang: about 4.6–4.8% of shares, but only if in the money. The exercise price was not checked.

### All cases
1. Routine employee issuance (small positive issuance, which Fama-French find earns positive returns).
2. Buybacks that only offset SBC (META).
3. Net buyback.
4. Extreme ATM issuer (MSTR).
5. Issuance-funded model: bitcoin treasury, REIT, early growth (R2).
6. Share-paid acquisition (8-K 2.01, S-4).
7. Strategic stake sale: Intel sold 433.3M shares at $20.47 to the US government in 2025 (S-new-68).
8. Split or reverse split.
9. Profit-sign flip moving the diluted count.
10. Multi-class filer with no non-dimensional count.
11. ATM set up (424B5) vs actual sales.
12. Preferred or debt supplements (not common dilution).
13. Shelf only; WKSI routine automatic shelf.
14. Baby-shelf company near the one-third cap.
15. Convertibles: dilutive or antidilutive; capped calls; net-share settlement.
16. Warrants in or out of the money; SPAC redemptions; stale XBRL dates (INFQ).
17. 8-K 3.02 unregistered sales and PIPEs.
18. Weighted-average lag after a late-quarter ATM.
19. Issuance with long runway vs with short runway.
20. Rule change (baby-shelf cap removed).

### Suggestions
- **S3.1 `net_issuance_yoy`.**
  - Log change in basic weighted-average shares: current quarter vs the same quarter a year earlier, both from the latest filing (split-safe).
  - The cover-to-cover change is shown beside it where both covers exist.
  - Method tag `wavg_basic_same_filing`.
- **S3.2 Issuance band** from yearly CY-frame breakpoints, with zero issuers kept apart.
  - Labels: repurchaser (above or below median) / flat / positive quintiles 1–4 / top quintile "extreme issuer (S-new-11, S-new-10)".
  - Informational until D13 weights exist.
- **S3.3 Composite issuance** (5 years) from `price_bar` and shares, shown beside net issuance.
- **S3.4 SBC block** (new `sbc` concept):
  - SBC ÷ revenue and ÷ OCF;
  - FCF after SBC (OCF − capex − SBC);
  - buyback offset = (buybacks + RSU withholding) ÷ SBC, shown beside the net share change.

  Compared with the company's own 3-year range. No universe threshold, because none with evidence was found.
- **S3.5 Financing capacity:**
  - active shelf (S-3, S-3ASR or F-3 within 3 years);
  - 424B supplements in the last 12 months, counted by security class (common, preferred, debt), never as sales;
  - ATM capacity from the fee-exhibit XML where present, as a percentage of market cap;
  - actual sales from `ProceedsFromIssuanceOfCommonStock` and the share-count change;
  - baby-shelf headroom (one-third of float).

  Regulatory caps live in config, sourced and dated.
- **S3.6 Convertible and warrant overhang.**
  - Note-text phrases: "conversion rate", "initial conversion price", "warrants to purchase … exercise price".
  - Numbers are verified against the stored passage and go to review.
  - Shown as in-the-money shares ÷ basic shares at the current price. `ClassOfWarrantOrRightOutstanding` is used where present, with its date.
- **S3.7 Old engine.**
  - **Keep:** the severity vocabulary with "unknown" reported, and the ATM 8-K phrases.
  - **Drop:** the bare "covenant" and "waiver of" substrings, and S-1/A counted as a shelf.
- **S3.8 Regression cases:**
  - MSTR 2025–26: extreme and model-tagged → review; preferred 424B5s are not common dilution.
  - META 2025: offset 2.19× → informational.
  - INFQ 2026: warrant overhang, strike to check.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Diluted weighted shares | Move with the profit sign | Issuance measured on basic shares; diluted–basic gap shown in profit periods only |
| Splits | 10× "growth" or "restatements" | Same-filing pairs; `split_factor` cross-check |
| Multi-class | Metric silently missing | "Missing: multi-class" label or class-summed cover count (1.1) |
| Weighted-average lag | Late-quarter ATM sales show only partly | Cover-count cross-check (MSTR: +35.5% cover vs +28.1% weighted) |
| Share-paid acquisitions; strategic stakes | Large issuance that may create value | Cause linked (8-K 2.01, S-4); label |
| Issuance-funded models | Issuance is the strategy | Owner model tag → review, not warning |
| Shelf, 424B counts | Capacity, not dilution; preferred and debt supplements | Classify by security class; sales from proceeds and share counts |
| ATM capacity | Firms use 43% on average, median 27% | Capacity and actual sales shown separately |
| SBC vs buybacks | Buybacks only offset SBC; withholding sits in financing cash flow | Offset ratio beside net share change |
| Paper thresholds | 1963–2005 equal-weighted; edge halves after publication | Own cross-section percentiles; informational |
| Convertibles and warrants | As-converted shares only when dilutive; capped calls; stale warrant counts | Text with quote → review; in the money only |
| Rule changes | Baby-shelf cap may go | Caps in config with source and date |

### Questions
**3.1 Issuance measure**
- (a) *Recommended.* Basic weighted average, same quarter year over year from one filing, with a cover-to-cover cross-check. Why: split-safe, present for every filer, and not moved by the profit sign.
- (b) Period-end count (the Fama-French definition; missing for multi-class filers).
- (c) Diluted weighted average.

**3.2 Bands and window**
- (a) *Recommended.* Yearly percentile bands from the SEC frames cross-section, with the top quintile labelled "extreme"; a 12-month window with the 5-year composite beside it. Why: calibrated to today's universe instead of paper-era cut-offs.
- (b) Fixed cut-offs such as 5%, 10% and 20% a year (illustrative; no evidence supports these exact numbers).
- (c) Number and percentile only, no bands.

**3.3 Shelves and ATM programs**
- (a) *Recommended.* Detect from stored metadata, with one fee-exhibit fetch per 424B for capacity where an exhibit exists. Sales are measured from proceeds and share counts. Why: real amounts at about one request per 424B, with no prospectus text.
- (b) Also fetch and read 424B text.
- (c) Shelf metadata only (old engine).

**3.4 When it warns** (company model tag)
- (a) *Recommended.* `financing_pressure` warns only when three conditions all hold:
  - the issuance band is "extreme";
  - the survival gate fails, or runway is below 6 quarters;
  - the company is not owner-tagged with an issuance-funded or asset-holding model.

  Any one of these alone is information. Model-tagged names become `m04_dilution` review items. The same tag gives MSTR-like names a liquidity-only survival gate (Round 4). Why: issuance or shelves alone would fire on every small cap and on MSTR's stated strategy.
- (b) Warn on "extreme" issuance alone.
- (c) No model tag; all companies treated alike.

---

## Round 4 — Survival gate and distress language

### What the research says
1. **Altman Z** (S-new-36, primary).
   - Built on 33 bankrupt and 33 paired manufacturers (1946–65).
   - One year before failure, at the 2.67 cut-off (1.81 in brackets), accuracy was 82% (75%) for 1969–75, 85% (78%) for 1976–95 and 94% (84%) for 1997–99. Two years out: 68–80%. Three to five years out on the original sample: 29–48%.
   - Type II error (healthy firms scored as distressed) has risen:
     - 15–20% of all firms and 10% of the largest scored below 1.81;
     - in 1999 more than 20% of Compustat industrials did.
   - Altman advocates 1.81.
   - The average Z rose to almost 10 in 1999, mostly through market value (X4).
   - Z″ = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4. The +3.25 constant belongs to the emerging-market version only.
   - The Z″ zones (1.1 / 2.6) come from Wikipedia (S34) and are not in Altman (2000), so confirm them in a primary source.
2. **Market-based measures beat accounting-only scores** (S-new-37):
   - about half of the accounting ratios in earlier models are not significant, while market size, past returns and idiosyncratic volatility predict (Shumway);
   - a Black-Scholes-Merton probability carries more information than Z or O (Hillegeist et al.);
   - about 0.75 accuracy across countries (Altman et al., abstract).
3. **Ohlson O-score** is a 9-variable logit (formula via Wikipedia, S-new-38).
   - Horizon, cut-off and the unit of total assets must be read from Ohlson (1980) before coding.
   - A unit error shifts O by about 5.6 (0.407 × ln 10⁶).
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
7. **The rules fix the wording we can search for** (S-new-43).
   - ASC 205-40: management evaluates every period. Substantial doubt exists when it is "probable" the entity cannot meet obligations within one year. Disclosure is required even when management's plans alleviate the doubt.
   - AS 2415: the auditor's paragraph must say "substantial doubt" and "going concern", without conditional language. Absence of the paragraph is not assurance.
   - 10-Qs carry management's evaluation only.
8. **Covenant violations are common and usually not distress** (S-new-44).
   - 10–20% of US non-financial firms report a violation in any year (1996–2008).
   - Violations are followed by cuts to acquisitions, capex, leverage and payouts and by more CEO turnover; performance then improves (Nini, Smith & Sufi).
   - Their method was text search followed by manual reading, with financials excluded (Becher, Griffin & Nini).
   - Covenants are set tight as "trip wires" (Dichev & Skinner), and investment drops sharply after a violation (Chava & Roberts).
9. **Breaches are disclosable** (S-new-45).
   - Reg S-X 4-08(c): the notes state uncured defaults and waiver periods.
   - ASC 470-10-45-11: callable debt is classified as current unless waived for more than a year or a cure is probable.
   - 8-K 2.04 is already typed as high-severity.
10. **Maturities** (S-new-46).
    - `LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths` plus the year-2 to after-year-5 tags sit on the annual schedule. Extension-tagged buckets are missing from companyfacts.
    - Release 33-10890 removed the contractual-obligations table, so cash requirements now sit in narrative text.
11. **Runway** has no standard definition or peer-reviewed threshold. ASC 205-40's one year is the legal anchor (S-new-43).
    - The old engine's ladder: < 12 months distressed, < 24 moderate, for small caps only.
    - Its integrity gate withheld a verdict when inputs disagreed (the false "Distressed" call on Viking Therapeutics; `financial_intelligence.py:78-86`).
12. **Financials are excluded.** Altman's samples are manufacturers; Nini et al. drop SIC 6000–6999; FF12 group 11 is already coded (`themes/industries.py`, S112).
13. **Data.**
    - All Z″ inputs are mapped.
    - Debt and revolver tags are in `fact` where non-dimensional.
    - Going-concern booleans are not in companyfacts, so text is needed.
    - The corpus holds the latest 10-K and 10-Q only (DS7).
    - Porter stemming widens matches (S47).
    - EFTS takes one phrase per query and no NEAR (D-M02-17, S97).

### Worked example — Rivian Q2 2026 (not on the watchlist; R11 case; S-new-47; $M)
| Row | Value |
|---|---|
| Current assets / current liabilities (2026-06-30) | 7,618 / 3,620 |
| Total assets / total liabilities | 15,140 / 10,013 |
| Accumulated deficit / equity | (28,200) / 5,127 |
| Cash + short-term investments / total liquidity including ABL | 5,310 / 5,846 (ABL 536, derived) |
| Pro forma after the July 2026 follow-on (about 1,317 net) | 7,163 |
| TTM loss from operations / OCF / capex / FCF | −3,533 / −1,845 / −1,644 / −3,489 |
| FCF Q1 2026 / Q2 2026 | −1,075 / −849 |

- **Z″** (operating income as the EBIT proxy):
  - X1 0.264, X2 −1.863, X3 −0.233, X4 0.512.
  - Z″ = 1.732 − 6.072 − 1.568 + 0.538 = **−5.37**: distress under the 1.1 cut-off.
  - Without the X2 term it is 0.70, still below 1.1.
  - With the +3.25 constant it would be −2.12.
- **Runway (quarters):**

| Burn definition | Burn per quarter | Cash only | + ABL | Pro forma |
|---|---|---|---|---|
| FCF TTM ÷ 4 | 872 | 6.1 | 6.7 | 8.2 |
| FCF, last-2-quarter average | 962 | **5.5** | 6.1 | 7.5 |
| OCF TTM ÷ 4 | 461 | 11.5 | 12.7 | 15.5 |

- **Reading.** The score says distress; the facts say borderline. The gate flips on the burn and liquidity definitions (question 4.2).
  - The DOE loan and the Volkswagen funds are conditional, so they are a note, not liquidity.
  - No going-concern or covenant language appears in the release; confirm in the 10-K/10-Q.
  - Maturities are unread, because RIVN is not in `fact`.

**Invitae** (S02, S-new-48; $M):

| As of (filed) | Liquidity | Trailing burn → runway | Company or guided burn → runway |
|---|---|---|---|
| 2021-12-31 (2022-03-01) | 1,060 | OCF + capex 614.5/yr → 6.9 | company burn 849.2 → 5.0 |
| 2022-12-31 (2023-02-28) | 557.1 | 546.3/yr → **4.1 (fail)** | company 509.6 → 4.4; guided 250–275 → 8.5 (would pass) |
| 2023-09-30 (2023-11-08) | 264.7 | Q3 64.1 → 4.1 | equity −1,083 |

- Chapter 11 followed in Feb 2024, about 50 weeks after the FY2022 10-K. No FY2023 10-K was filed.
- Only trailing burn catches it. Z″ will be computed from fixture facts at build, not copied.

### All cases
1. Healthy mature company → pass.
2. Young firm with a deficit, operating loss and years of cash (Rivian) → score distress; gate decided by runway.
3. Self-funding (burn ≤ 0) → "self-funding", never ∞.
4. One-quarter burn spike from a year-to-date-derived working-capital swing.
5. Runway near the threshold, flipping by definition (Rivian 5.5 vs 6.1).
6. Guided burn lower than trailing (Invitae 8.5 vs 4.1).
7. Revolver tagged / untagged / borrowing-base limited; conditional facilities (DOE).
8. Restricted cash.
9. Pro forma raise after period end.
10. Maturity wall within 12 months; convertible with a holder put; commercial paper; missing extension buckets; between 10-Ks.
11. Going-concern sentence: auditor paragraph / management "exists" / alleviated / hypothetical risk factor / negated / "going concern basis" boilerplate.
12. No going-concern language, then bankruptcy (about half of cases).
13. Covenant: compliant / breach waived / breach unwaived / forbearance / reset amendment / cross default / acceleration (2.04).
14. 8-K 1.03 bankruptcy; 3.01 delisting notice.
15. Bank, fund (ETV N-CSR), crypto treasury (MSTR assets swing with bitcoin).
16. Equity below zero.
17. Not on the watchlist (no facts).
18. Stale (no new filing).
19. Missing inputs → gate "incomplete", never pass.

### Suggestions
- **S4.1 Facts first.** The gate fails on any of:
  - going concern "exists";
  - unwaived breach, forbearance, 8-K 2.04 or reclassification to current;
  - 8-K 1.03 or 3.01;
  - runway below threshold;
  - the maturity test.

  Further rules:
  - The `survival_gate` signal gains a third value, "incomplete", for missing inputs.
  - The absence of an opinion is never a pass (AS 2415).
  - Scores become a `distress_score` warning with a stage flag (question 4.1).
- **S4.2 Runway.**
  - Liquidity = cash + short-term investments (restricted cash excluded) + tagged `LineOfCreditFacilityRemainingBorrowingCapacity`.
  - Burn = −(OCF − capex), per question 4.2. Trailing only, never guidance.
  - Also shown: OCF-only runway, and runway net of next-12-month maturities.
  - Conditional facilities appear as a note.
  - Old engine's integrity gate kept: the verdict is withheld when inputs are inconsistent, e.g. a derived quarter crossing a restatement.
- **S4.3 Maturity wall.**
  - Next 12 months = the year-1 tag at the 10-K; at each 10-Q, current debt + short-term borrowings + commercial paper.
  - A 24-month wall (years 1 + 2) is shown against liquidity + max(0, TTM OCF).
  - "Maturities partial" when buckets are missing.
  - Convertibles are counted at the earliest holder put, read from text where tags lack it.
- **S4.4 Score family.**
  - Z for SIC 2000–3999 (S110), cut-off 1.81 (S-new-36).
  - Z″ for other non-financials, without the constant; zones used only after primary confirmation.
  - Z shown with and without X4. Formula version stored on every value.
  - Skip FF12 group 11 and N-CSR filers.
  - O-score only after reading Ohlson (1980). CHS-12m as information only (no RSIZE; SPY as a labelled market proxy).
- **S4.5 Going-concern finder (local FTS5).**
  - Queries: `NEAR("substantial doubt" "going concern", 25)` and `"continue as a going concern"`.
  - Sections: 10-K Item 8, 10-K Item 7, 10-Q Part I Items 1–2.
  - A raw-text sentence classifier labels each hit: `auditor_gc` / `management_exists` / `alleviated` / `hypothetical` / `negated` / `boilerplate`.
  - The quote and offsets are stored (D-SRCH-19).
- **S4.6 Covenant finder.**
  - Phrases: `"not in compliance"`, `NEAR(waiv* covenant, 10)`, `forbearance`, "event of default" near occurred or continuing, `"cross default"`, `NEAR(amend* "financial covenant", 10)`.
  - The baseline `"in compliance with all"` is recorded, so silence is distinguishable from compliance.
  - Classes: breach_unwaived / breach_waived / forbearance / reset / compliant.
- **S4.7 History via EFTS** (question 4.4).
  - One phrase per query ("substantial doubt", "forbearance", "not in compliance"), on 10-K and 10-Q since 2001, filtered by CIK.
  - Hits are fetched and run through the same classifier.
  - A first-scan baseline is recorded before any alert (D-M02-58).
- **S4.8 Review items (D8):**
  - hypothetical-only going-concern hits where runway is below 8 quarters;
  - waived breaches;
  - score in distress while the gate passes;
  - missing maturity buckets.

  Equity below zero is a warning.
- **S4.9 Regression cases:**
  - Rivian Q2 2026 (fixture): score distress, gate borderline.
  - Invitae FY2022 10-K: gate fails on trailing burn.
  - A mature non-manufacturer: pass.
  - Each quarter, report the watchlist count of score-distress vs gate-fail.

### Failure modes (rows to add)
| Input | How it can mislead | Guard |
|---|---|---|
| Z / Z″ / O on young firms | Deficit and operating loss read "distress" while years of cash remain | Stage flag; warning only, never a gate fail on its own |
| Z cut-offs and variant | 1946–65 manufacturers; Type II error 15–20%; +3.25 constant mixed with 1.1/2.6 zones turns distress into "safe" | Variant, version and cut-off stored; 1.81; unit test on fixtures |
| Z X4 | Bubble prices inflate Z (1999 average near 10); crashes cut it just as M01 triggers | Show with and without X4 |
| O-score / CHS | Unverified horizon, cut-off and unit; CHS power at 12 months is about a third of next-month | Read originals first; CHS information only |
| Burn | One-quarter swings; YTD derivation | Two-period rule; trailing only; three definitions shown |
| Revolver | Borrowing base or springing covenant cuts availability; conditional loans | Tagged remaining capacity only; conditional loans as a note |
| Maturity tags | Annual schedule; missing extension buckets; holder puts vary; commercial paper outside buckets | Max of year-1 tag and current debt + short-term borrowings + commercial paper; "partial" flag |
| Going-concern text | Hypotheticals, negations, alleviated cases and boilerplate all match; stemming widens matches | Sentence classifier on raw text; only "exists" fails |
| Going-concern as predictor | About half of bankruptcies had no opinion; about 90% of recipients do not file within a year | Gate input, never a forecast or a pass |
| Covenant text | "In compliance" dominates; violations are common and often waived | Unwaived, forbearance, 2.04 or reclassification only |
| Financials, funds, crypto treasuries | Z is meaningless for banks and funds; MSTR's assets swing with bitcoin | FF12 group 11 excluded; model tag → liquidity facts only |

### Questions
**4.1 Role of distress scores**
- (a) *Recommended.* Z and Z″ become a warning only, and the gate uses liquidity and legal facts. The O-score is added after verification, with CHS-12m as information. Why: Type II error of 15–20%, and young firms read as distress by construction.
- (b) Score stays in the gate unless retained earnings < 0 and runway ≥ 6 quarters.
- (c) As now (score in the gate).

**4.2 Runway rule**
- (a) *Recommended.* Burn = OCF − capex, taking the worse of TTM ÷ 4 and the last-2-quarter average. Fail below 6 quarters, warn below 8. Why: smooths one-quarter swings yet reacts within two quarters. Rivian: 5.5 quarters cash-only (fail), or 6.1 with the ABL if tagged (warn).
- (b) Worse of TTM ÷ 4 and the latest quarter. Rivian: 6.1 cash-only (warn).
- (c) OCF only, with the old engine's 12/24 months.
- (d) Fail below 4 quarters (the ASC 205-40 horizon).

**4.3 Maturity wall test**
- (a) *Recommended.* Next-12-month maturities + 4 × quarterly burn > liquidity. Why: a cash-burning company facing a wall fails earlier.
- (b) Next-12-month maturities > liquidity (as now).

**4.4 Going-concern and covenant triggers, and history**
- (a) *Recommended.* The gate fails on an auditor paragraph or a management "exists" conclusion, an unwaived breach, forbearance, an 8-K 2.04, or reclassification to current. Alleviated, waived and reset cases become a warning plus a review item. History: one owner-run EFTS pass back to 2001 for the watchlist. Why: matches the AS 2415 wording, and violations alone are common (10–20% a year).
- (b) Any going-concern sentence or any breach fails the gate.
- (c) As (a), without the EFTS history (latest filings only).

---

## Round 5 — Unit economics and margin collapse (stage-aware, R2)

### What the research says
1. **Filings must state the cause** (S-new-49).
   - Reg S-K 303(b) requires the reasons behind material line-item changes, in quantitative and qualitative terms, including offsetting changes.
   - 303(b)(2)(iii) asks how far a revenue increase comes from price, volume or new products.
   - 303(b)(2)(ii) covers known events that change the relationship between costs and revenues.
   - Examples:
     - Tesla's FY2023 10-K says total automotive gross margin (28.5% → 19.4%) fell "primarily due to a lower average selling price" (S-new-50).
     - Target publishes a gross-margin waterfall in percentage points (S-new-51).
     - Rivian's Q4 2023 letter splits its "~$81k" per-vehicle gain into about 45% fixed cost, 40% variable cost and 15% revenue per unit (S-new-47).
2. **Per-unit bridge.** Gross-profit change = volume effect + price effect + cost effect. The arithmetic is standard; no peer-reviewed definition was found. Tesla 2022→2023 reconciles exactly to the reported change (worked example).
3. **Falling gross margin predicts lower earnings.**
   - A gross-margin signal (% change in sales − % change in gross margin) is used by Lev & Thiagarajan and by Abarbanell & Bushee. Full texts were not opened, so the construction needs checking (S-new-52).
   - A UK extension found margin and cost signals the most informative, with effects that depend on the macro state and industry (S-new-52).
4. **Inventory ahead of sales.**
   - Abnormal inventory growth, measured against an operations benchmark, has an inverted-U relation to next-year EPS for US retailers that analysts do not fully price (S-new-53).
   - Target: inventory rose 30.5% at January 2022 against +13.2% sales, and 43% year over year at April 2022. The FY2022 gross-margin rate then fell 4.7 pp (S-new-1, S-new-51).
5. **Operating leverage and sticky costs.**
   - SG&A rises 0.55% per 1% sales increase but falls only 0.35% per 1% decrease (S-new-54). Operating leverage: S-new-54.
   - So falling margins on falling revenue can be scale. Margins collapsing while revenue rises cannot be: the cause must be price, mix, input cost, a one-off, credits or under-absorption. That is R12's diagnostic logic.
6. **Reversion.**
   - Profitability reverts about 38% a year, faster below the mean (S-new-55).
   - Life-cycle grouping improves forecasts most in the introduction and decline stages (S-new-56, Vorst & Yohn).
   - Return on net operating assets does not revert across stages: a gap of about 7 pp between mature and decline firms remains after 5 years (S-new-56, Dickinson abstract).
   - Target's gross-margin rate went from 23.6% to 26.5% in FY2023 (S-new-51, trade press).
7. **Stage from cash-flow signs** (S-new-56), as (operating, investing, financing):

   | Stage | Signs |
   |---|---|
   | Introduction | (−, −, +) |
   | Growth | (+, −, +) |
   | Mature | (+, −, −) |
   | Shake-out | (−,−,−), (+,+,+) or (+,+,−) |
   | Decline | (−,+,+) or (−,+,−) |

   - The mapping was read from a secondary paper; check it against Dickinson's own table.
   - Stages are not sequential: of mature firms classified the next year, 62% stayed mature and 30% moved back to growth.
8. **Young firms.**
   - Non-financial growth metrics were value-relevant where earnings were not (S-new-57, Amir & Lev).
   - Unit cost falls as a power of cumulative production; Wright's law forecast best across 62 technologies (S-new-57, Nagy et al.).
   - So the red flag is per-unit cost that does not fall as cumulative units grow.
9. **Negative gross margin.**
   - No peer-reviewed base rate was found.
   - Lordstown, Proterra, Fisker, Canoo and Nikola failed, but that list is outcome-selected (S-new-58).
   - The survival gate is the primary guard.
10. **Contribution margin is non-GAAP.**
    - C&DI 100.01 warns that excluding normal recurring cash operating expenses can mislead. Aterian's 2021 letter moved its reconciliation to gross profit (S-new-59).
    - Design choice: show company-stated figures labelled, never computed.
11. **KPI definition risk** (S-new-59, Release 33-10751 summary).
    - KPIs need definitions and method-change disclosure, but Rivian's per-vehicle gross profit is undefined.
    - Revenue scope often differs from the unit count:
      - Tesla's deliveries include leased cars, but leasing revenue is a separate line.
      - Regulatory credits have no units: Tesla $2,763M in 2024; Rivian $299M in Q4 2024 and $325M for FY2024 (S-new-47).
12. **Segments.**
    - ASU 2023-07 adds significant segment expenses, retrospectively (S-new-60).
    - Segment values sit on XBRL axes and are not in companyfacts (S41).
    - Warning case: a search engine called Rivian's automotive-segment cost (6,150 / 5,693) a "recast" of consolidated cost (6,464 / 6,170). Consolidated FY2022 gross profit is −3,123, unchanged in three 10-Ks (S-new-1).
13. **One-offs and credits inside gross profit:**
    - Intel 2024: $3.3B of impairment and accelerated depreciation plus $922M of Gaudi inventory charges (S-new-61).
    - Rivian write-downs: $920M (2022) → $107M (2023).
    - Rivian Q4 2024: gross profit $170M against credits of $299M.
    - Rivian 2023: produced 57,232, delivered 50,122 (S-new-47).
14. **Data.**
    - Margin concepts are mapped, and Q4 is derived (Rivian has no discrete Q4 facts).
    - MD&A is split by section, with tables tab-separated (D-SRCH-12).
    - Unit counts are not in XBRL.
    - Tesla's delivery EX-99.1 is stored but not parsed (DS2).
    - EX-99.2 is not fetched (`documents.py` `DEFAULT_EXTRA_TYPES`).
    - RIVN is not on the watchlist.
    - `instance.py` keeps non-dimensional contexts only.

### Worked example
**Rivian: young firm, negative margin, improving per unit** (S-new-1, S-new-47; consolidated, so including software and services)

| Period | Revenue $M | Gross profit $M | Deliveries | Revenue / unit | Cost / unit | Gross profit / unit | Gross margin |
|---|---|---|---|---|---|---|---|
| FY2022 | 1,658 | −3,123 | 20,332 | $81.5k | $235.1k | −$153.6k | −188% |
| FY2023 | 4,434 | −2,030 | 50,122 | $88.5k | $129.0k | −$40.5k | −46% |
| FY2024 | 4,970 | −1,200 | 51,579 | $96.4k | $119.6k | −$23.3k | −24% |
| Q4 2024 | — | +170 (automotive +110) | 14,183 | — | — | automotive +$7.8k; **excluding $299M credits about −$13.3k** | — |
| FY2025 | 5,387 | +144 | 42,247 | not comparable (JV services revenue) | — | +$3.4k (mixed scope) | +2.7% |

- 2025 deliveries come from Rivian's 2026-01-02 release (Business Wire; URL to add).
- The ex-credits figure assumes credits are booked in automotive revenue.
- The 2023→2024 gain of $17.2k per unit includes about $4.9k from a $252M rise in credit sales.
- Engine reading (illustrative): stage introduction/growth; no margin red flag; credit-dependence warning for Q4 2024; 2023 production/delivery gap flagged.

**Tesla 2023: revenue up, margin down, cause = price** (S-new-50; deliveries from Tesla delivery 8-Ks under DS2; 2024 from the FY2024 10-K, URL to add)

| Year | Automotive sales $M | Cost $M | Deliveries | Revenue / unit | Cost / unit | Gross profit / unit |
|---|---|---|---|---|---|---|
| 2022 | 67,210 | 49,599 | 1,313,851 | $51.2k | $37.8k | $13.4k |
| 2023 | 78,509 | 65,121 | 1,808,581 | $43.4k | $36.0k | $7.4k |
| 2024 | 72,480 | 61,870 | 1,789,226 | $40.5k | $34.6k | $5.9k |

- Bridge 2022→2023: volume +$6.6B, price −$14.0B, cost +$3.2B = −$4.2B, which matches the reported change.
- Bridge 2023→2024: −$0.1B, −$5.2B, +$2.6B = −$2.8B.
- Caveat: leased cars are in deliveries but not in automotive sales.

**Target FY2022: mature company, revenue +2.8%, gross-margin rate 28.3% → 23.6%** (S-new-51)
- Waterfall: merchandising −3.4 pp, fulfillment and supply chain −0.8, shrink −0.7, mix +0.2; sums to −4.7.
- The inventory gap came first.
- Reverted to 26.5% in FY2023.

**Intel 2021–24: revenue falling, so R12 does not fire; CvD's case** (S-new-1, S-new-61)

| Year | Revenue $M | Gross margin % |
|---|---|---|
| 2021 | 79,024 | 55.4% |
| 2022 | 63,054 | 42.6% |
| 2023 | 54,228 | 40.0% |
| 2024 | 53,101 | 32.7% (about 40.6% excluding stated charges; illustrative arithmetic) |

### All cases
1. Mature, revenue up, gross margin down (R12). Cause: price (Tesla), markdowns or input cost (Target), mix, one-off, credits, FX, or an accounting or segment change.
2. Mature, revenue down, margin down → CvD (Intel).
3. Inventory outgrowing sales before the hit (Target).
4. Young, negative margin improving per unit with volume (Rivian 2022–24).
5. Young, negative margin not improving while units rise.
6. Young, revenue per unit falling while cost per unit is flat (volume bought with price).
7. First positive gross profit dependent on credits or services.
8. Production above deliveries (overhead capitalised into inventory).
9. Units not disclosed → margins only.
10. Unit scope ≠ revenue scope.
11. KPI category break (Tesla's "Other models" now includes Cybertruck).
12. Pre-revenue zeros; tiny revenue (`not_meaningful`).
13. Segment recast vs consolidated figures.
14. Restated gross profit (Intel FY2016/17).
15. Stage change: shake-out; an asset sale flips investing cash flow; acquirers look like growth.
16. Decline stage → no reversion context.
17. Company-stated contribution margin.
18. Waterfall components that do not sum.

### Suggestions
- **S5.1 One `lifecycle_stage` per company** (question 5.1), stored with history and used for routing in Rounds 2–4:
  - growth names get the M-score without SGI;
  - young firms get Z as a warning only.

  The owner's model tag (3.4) stays separate.
- **S5.2 R12 trigger** (question 5.2). Opens one "identify the cause" review item per episode.
- **S5.3 Cause finder** (question 5.3).
  - Searches the same filing's MD&A plus EX-99.1 and EX-99.2 for sentences on gross margin or cost of revenue with "primarily due to", "driven by" or "offset by".
  - Rules tag one or more classes: price, volume/scale, mix, input cost, one-off, credits/other, FX, accounting/segment change.
  - Arithmetic check: waterfall components must sum to the total.
  - The owner confirms, following the guidance-label pattern (D-M02-24).
- **S5.4 Stated items.** Gross margin as reported, and "excluding stated items", each item with its tag or quote and accession. Unstated amounts are never estimated.
- **S5.5 Unit metrics.**
  - A `unit_metric` table: company, period, metric, value, unit, label as stated, accession, quote.
  - Start with a Tesla DS2 extractor by model line, then survey the watchlist for similar releases.
  - The bridge runs only when line item and unit scope match; otherwise "not comparable".
  - Credits shown separately; a `credit_share_of_gp` warning when credits ≥ 50% of gross profit.
  - A production/delivery gap above 10% is flagged beside any unit-cost improvement.
- **S5.6 Stage-aware red flags.**
  - **Young:**
    - per-unit gross profit not improving over 4 quarters while units rise;
    - unit cost not falling with cumulative units;
    - revenue per unit falling while cost per unit is flat;
    - production gap;
    - credit share;
    - survival gate.

    Negative gross margin alone is not a flag.
  - **Mature:**
    - R12;
    - inventory growth − sales growth > 15 pp (an unsourced starting value, motivated by S-new-53, whose measure differs);
    - SG&A growth > revenue growth for 4 quarters;
    - CvD Q2 margin gap.
  - **Decline:** no reversion context.
- **S5.7 Segment facts** (question 5.4).
  - Business-segment and product/service axes, watchlist only, via a migration adding axis and member columns.
  - Recasts detected by first vs latest per member; breaks flagged, both series kept.
  - Values are never compared across scopes.
- **S5.8 Contribution margins.** Company-stated figures shown, labelled non-GAAP and quoted; never computed.
- **S5.9 Signals out:** `margin_cause` (enum + quote), `gm_delta_pp`, `unit_gp`, `unit_gp_ex_credits`, `lifecycle_stage`, `credit_share_of_gp`, `inventory_sales_gap`.
- **S5.10 Mean-reversion prior** shown as context text for mature firms, hidden for the decline stage.
- **S5.11 Regression cases:**
  - Rivian 2022–24: no margin flag; credit warning.
  - Tesla 2023: R12 fires, cause price.
  - Target FY2022: early inventory warning; R12; price + input cost; reverted.
  - Intel 2024: no R12; stated one-offs shown.

### Failure modes (rows to add)
| Input | How it can mislead | Guard |
|---|---|---|
| Per-unit gross profit | Revenue scope ≠ units (leases, credits, services, JV revenue) | Bridge only on matching scope; "not comparable"; credits separate |
| Deliveries vs production | Production above deliveries flatters cost | Gap > 10% flagged beside cost gains |
| KPI definitions | Category changes; undefined metrics | Label as stated plus quote; breaks flagged, not merged |
| Gross-margin signal | One-off charges look like collapse or recovery | Reported and "excluding stated items", each quoted |
| Regulatory credits | Lift gross profit with no unit cost; can vanish with policy | `credit_share_of_gp` warning |
| Cause sentences | Management framing; buried offsets; mis-signed summaries | Arithmetic sum check; quote stored; owner confirms |
| Segment vs consolidated | Segment figures read as consolidated (the Rivian "recast" mistake) | Axis and member stored with every value |
| Life-cycle stage | One-year sign flips; acquirers look like growth | 2-of-3-year persistence; change → review; owner override |
| Mean-reversion prior | Decline-stage firms do not revert | Context only; suppressed for decline |
| Inventory gap | Inverted U; retail evidence only | Starting value to calibrate; warning, not trigger |
| Zeros and tiny revenue | Pre-revenue 0; huge margins on small bases | Zeros kept; `not_meaningful` below a revenue floor |

### Questions
**5.1 Stage source**
- (a) *Recommended.* Dickinson cash-flow signs with 2-of-3-year persistence; changes go to review; owner override. Why: computed free from stored data, and stages are not sequential (30% of mature firms moved back to growth).
- (b) The owner sets every stage by hand.
- (c) Rules on growth and cash flow (e.g. TTM revenue growth > 25% or 3-year cumulative CFO < 0 → young).

**5.2 R12 trigger**
- (a) *Recommended.* Revenue TTM year over year > 0 and gross margin down ≥ 3 pp year over year for 2 straight quarters, on the reported margin, with "excluding stated items" shown beside it. Why: the persistence test filters out one-quarter charges.
- (b) Any single quarter ≥ 5 pp.
- (c) Only when the gross-margin gap to peers worsens (CvD Q2).
- (d) As (a), but triggered on the excluding-items margin.

**5.3 Who names the cause**
- (a) *Recommended.* Code extracts and tags sentences; the owner confirms; a Gemini hint runs only on request, with verified quotes. Why: code first (D28), and quotes are stored.
- (b) Arithmetic decomposition only, no text.
- (c) Gemini labels by default, with verified quotes.

**5.4 Unit KPIs, Rivian and segments**
- (a) *Recommended.* Tesla DS2 extractor plus a watchlist survey; EX-99.2 fetched for configured companies; RIVN added as a tracked name; segment and product axes read from filing instances (extend `instance.py`, watchlist only). Why: about one request per release or filing, reusing the D-M02-32 path.
- (b) Tesla only; Rivian as fixtures; segments from the Financial Statement & Notes data sets (S40).
- (c) Defer KPIs and segments; margins only.

---

## Round 6 — CvD calibration and health scores

### What the research says
1. **The window is set by XBRL**, phased in for periods ending from 2009-06-15 (float above $5B), then 2010 and 2011 (S-new-4).
   - The usable backtest window is about FY2010 to now, roughly 16 years.
   - A 10-year lookback is first available around FY2019–20.
   - Micron's 2001 bust is invisible; its 2008–09 bust shows only through FY2009 comparatives.
2. **Overfitting.** With about 20–40 labelled episodes, every extra threshold variant tried raises the false-discovery risk (S-new-62). So calibrate for label stability (does the label survive ±20% threshold moves?) and log every variant tried.
3. **The robust-z method decides small-n results.**
   - Intel 2022 against 4 peers, with a −1.5 cut-off:
     - IQR with type-7 quantiles (as `frames.py` uses): −1.71;
     - IQR with type-6 quantiles: −0.82;
     - MAD × 1.4826: −1.92.
   - Nine quantile definitions exist, and they differ most at small n (S-new-63, Hyndman & Fan).
   - Small-n alternatives (S-new-63):
     - The 1.4826 MAD factor is insufficient at small n. n-specific factors exist (Croux & Rousseeuw 1992, via the revss docs; primary not read).
     - Qn and Sn estimators (Rousseeuw & Croux 1993).
     - MAD with a 2.5 cut-off (Leys et al.).
     - A very-small-sample M-estimator (Rousseeuw & Verboven).
   - One extreme peer (NVIDIA's FY2024 growth of +125.9%) puts everyone "in the pack".
4. **Look-ahead bias** (S-new-64).
   - Intel recast FY2016 operating income from 12,874 to 13,133 and FY2017 from 17,936 to 18,050 in its 10-K filed 2019-02-01.
   - WDC's FY2023 revenue went from 12,318 to 6,255 after the SanDisk separation (S-new-1).
   - Frames are last-filed (S39).
5. **Survivorship.** Delisting returns are mostly missing and large-negative: about −30% for NYSE/AMEX performance delistings, −55% for Nasdaq (S-new-65). EDGAR keeps dead filers. Whether Tiingo covers delisted tickers is unverified.
6. **Piotroski F** (S32).
   - Tested on 1976–96 high book-to-market firms, with the edge in small, thinly followed firms.
   - The signals reversed in the 12 years after 1996 (S-new-66, lower-tier journal).
   - Later work uses F to find mispricing, not distress (S-new-66, Piotroski & So).
   - At a trough, 4 of the 9 signals fail mechanically: Micron FY2023 scores 4 with a sound balance sheet (worked example).
   - The equity signal is muddied by plans and strategic stakes (Intel 2025, S-new-68).
7. **Mohanram G** (S33).
   - Low scores returned −17.9% size-adjusted in year 1, against +3.3% for high scores.
   - It is "stronger among large, heavily followed firms" (S-new-66, Piotroski 2005 discussion): the best large-cap evidence of the three scores.
   - Advertising is rarely tagged; AAII drops it and uses a 7-point maximum (S-new-66).
   - The variance windows are unverified (5 years per CXO); check the paper.
8. **Altman Z.**
   - Adding the 3.25 constant while keeping the 1.1 / 2.6 zones turns distress into "safe". Any Z″ above −2.15 crosses 1.1 (Rivian: −5.37 → −2.12).
   - For Micron FY2023 at an illustrative ~$70 price, X4 is 2.29 of a Z of 3.43 (1.14 without X4). A price crash lowers Z just as M01 triggers.
9. **Normalized earnings.**
   - Support: profitability reverts (S-new-55); naive extrapolation is priced (S35).
   - Weakness: accounting breaks distort 10-year averages (S-new-67).
   - Real-data problems:
     - Current revenue is itself cyclical: Micron's normalized earnings power fell 56% from FY2022 to FY2023.
     - Aggregation matters: Micron's 10-year margin is 22.3% as a ratio of sums but 18.0% as a mean of ratios.
     - Decliners keep old margins: Intel's 2016–2025 margin of 16.8% × 2025 revenue ≈ $8.9B, against actual operating income of −$2.2B.
     - Impairments distort the average (Invitae 2022: $2,313M).
10. **Regression readings on real data.**
    - **MU:**
      - Q1: an outlier among SEC chip peers; memory peers are non-SEC.
      - Capex −36% trips "cut > 20%" while capex ÷ revenue rose from 39% to 49%.
      - Trough rule: the FY2023 low (−9.1%) is below the FY2020 low (30.6%), and the FY2022 high (45.2%) is below the FY2018 high (58.9%). That is one cycle of lower lows and highs, not two (FY2016 low 20.2%).
      - The Q2 FY2023 write-down was $1.43B, with GAAP gross margin of −32.7% (S-new-5). Inventory days were 153, or 235 excluding the write-down (call transcript, other).
    - **INTC:**
      - Company-specific in 2022 (gap −24.9 pp) but *shared* in 2023 (peer median −8.2%), the reverse of the expected drift.
      - Gross margin 55.4% → 42.6% → 40.0% → 32.7% → 34.8%.
      - AMD's server share rose from 25.7% to 28.8% (Q4 2024 → Q4 2025; S-new-69).
      - R&D held, so the result is AMBIGUOUS.
    - **Invitae:** fails on trailing burn, as in Round 4.

### Worked example
**Intel revenue growth vs peers** (S-new-1; each peer's fiscal year closest to calendar year-end)

| Company | 2022 YoY | 2023 YoY |
|---|---|---|
| INTC | −20.2% (63,054 vs 79,024) | −14.0% (54,228) |
| AMD | +43.6% (includes Xilinx) | −3.9% |
| NVDA (FY to late January) | +0.2% | +125.9% |
| TXN | +9.2% | −12.5% |
| MU (TTM to 2022-12-01 / 2023-11-30) | −8.3%* | −40.4% |
| Peer median; Intel z (IQR type 7) | +4.7%; −1.71 | −8.2%; −0.16 |

\*Micron's 2021 TTM base uses one quarter not yet verified; re-check at build. The 2022 median and the fixed-gap result do not depend on it while Micron's growth stays below +0.2%.

With n = 4 the fixed-gap rule decides: −24.9 pp in 2022 (company-specific) and −5.8 pp in 2023 (shared). The z method alone moves 2022 between −0.82 and −1.92.

**Micron FY2023 Piotroski F = 4** (S-new-1)

| Signal | Value | Point |
|---|---|---|
| ROA | −5,833 / 66,283 = −8.8% | 0 |
| CFO > 0 | 1,559 | 1 |
| ΔROA | 14.8% → −8.8% | 0 |
| Accruals (CFO > ROA) | yes | 1 |
| ΔLeverage | 10.9% → 20.0% of average assets | 0 |
| ΔCurrent ratio | 2.89 → 4.46 | 1 |
| No equity issued | diluted shares 1,122M → 1,093M | 1 |
| ΔGross margin | 45.2% → −9.1% | 0 |
| ΔAsset turnover | 0.523 → 0.234 | 0 |

All four failing signals are cycle-driven.

**Micron normalized earnings:** about 7,940 (FY2022: 25.8% × 30,758) → about 3,460 (FY2023: 22.3% × 15,540). An overreaction test must take prices at the same fiscal period ends (2022-09-01, 2023-08-31) from stored Tiingo bars.

### All cases
1. Peer count: ≥ 8 / 5–7 / < 5 / 0 (all non-SEC).
2. One extreme peer.
3. A peer's acquisition year.
4. Fiscal vs calendar offsets; 53-week years.
5. Label stable vs flipping under ±20% threshold moves.
6. Indicators that disagree within a question → AMBIGUOUS.
7. Trough where a write-down distorts gross margin and inventory days.
8. Fewer than 2 prior troughs in XBRL → insufficient history.
9. Capex cut as supply response vs as franchise weakening.
10. F-score at a trough vs in a decline.
11. Equity issued through plans, a strategic stake or an acquisition.
12. G-score with advertising missing or fewer than 5 peers.
13. Z under bubble or crash prices; Z″ variant.
14. Normalized earnings in a trough, a decline or a growth phase; impairments inside the window.
15. Recast history or a spin-off.
16. Delisted company (stale state; delisting return).
17. Episode before XBRL → out of scope.

### Suggestions
- **S6.1 Backtests use `facts_as_of` only** (S1.1). Historical peer values come from each peer's as-of series, never from frames.
- **S6.2 Peer statistics.**
  - Store the method and n with every z.
  - Below 5 peers the fixed-gap rule decides and z is information only.
  - With 5–8 peers, use MAD with n-specific factors (read the primary before build), and flag and recompute without any peer with |z| > 3.
  - 2-quarter persistence unchanged.
- **S6.3 Test set.**
  - The owner blind-labels before any engine run. Candidates (owner picks; labels are judgment calls):
    - Troughs: MU FY2012, FY2016, FY2019–20, FY2023; WDC FY2023; oil and gas 2015–16 (e.g. Halliburton); steel 2015–16 (e.g. Nucor).
    - Declines and failures: INTC 2022–25; Invitae 2022–23; Bed Bath & Beyond 2019–23; Rite Aid 2021–23; J.C. Penney 2017–20.
    - Stumbles: Boeing 2019–20.
  - Report a confusion matrix and label stability; walk forward (calibrate ≤ 2017, test 2018+); log every variant.
- **S6.4 Q2 capex row.** Score capex ÷ revenue against own 3-year average and peers. Absolute cuts move to Q1 "supply response".
- **S6.5 Trough vs prior trough.**
  - Two consecutive cycles of lower gross-margin lows and lower highs, with turning points taken from the series.
  - "Insufficient history" when fewer than 2 prior troughs are in XBRL.
  - Write-down quarters adjusted with stated amounts, found by FTS5 ("inventory write-down", "lower of cost or net realizable value").
- **S6.6 Normalized earnings.**
  - Two variants side by side: cycle-average margin × current revenue, and × cycle-average revenue.
  - Ratio-of-sums margin, excluding impairment tags.
  - Shown only when `cvd_state` is CYCLICAL_TROUGH or AMBIGUOUS; otherwise greyed out with the reason.
  - Prices taken at the same fiscal period ends.
- **S6.7 Health scores.**
  - F-score with the equity signal as net basic-share growth > 2%, consistent with question 3.1.
  - An F-quality subscore (0–4: accruals, leverage, liquidity, equity offering) for shared slumps. This is an untested engineering choice and labelled as such.
  - G-score only for growth names with ≥ 6 of 8 inputs and ≥ 5 peers, after the variance windows are verified; show n of 8.
- **S6.8 Z display.** Shown with and without X4, priced at the filing date.

### Failure modes (rows to add)
| Input | How it can mislead | Guard |
|---|---|---|
| Robust z, n < 8 | The quantile method flips the label (−0.82 / −1.71 / −1.92) | Fixed gap decides below 5; method and n shown; small-n factors |
| One extreme peer | Inflates the spread so everyone is "in the pack" | MAD; drop and recompute when \|z\| > 3 |
| 53-week year | Growth inflated by about 2% | Flag; scale by days |
| Recasts and spins | WDC FY2023 $12.3B → $6.3B on "latest" | First-reported as-of values in backtests |
| Concept coverage start | Micron gross profit starts later than revenue | History depth per concept |
| Inventory write-down | Gross margin −32.7%; inventory days understated (153 vs 235) | Stated amount attached; adjusted reading when disclosed |
| Capex cut | One number drives both Q1 supply response and Q2 weakening | Q2 on intensity; Q1 on absolute cut |
| F-score at trough | 4 of 9 signals are cycle-driven | Cycle-neutral subscore |
| Equity signal | Plans or strategic stakes score 0 | Net basic-share growth > 2% |
| G-score | Advertising missing counted as 0 | n of 8 shown; no score below 6 |
| Normalized earnings | Cyclical revenue base; decliners keep old margins; impairments | Two bases; shown only for trough/ambiguous; impairments excluded |
| Price vs earnings power | Mismatched windows fake an overreaction | Same fiscal window |
| Stale last filing | A dead company keeps its last state | `stale` after expected date + 45 days |

### Questions
**6.1 Test set**
- (a) *Recommended.* The owner blind-labels about 24 XBRL-era episodes across about 4 industries before seeing engine output, as for the M02 precision set (D-M02-40). FY2010 to now; calibrate ≤ 2017, test 2018+. Why: honest out-of-sample testing despite few cases.
- (b) Semiconductors only, about 12 episodes.
- (c) The 3 current cases now; grow later.

**6.2 Few-peer statistics**
- (a) *Recommended.* MAD with n-specific small-sample factors, method and n shown. Below 5 peers the fixed gap decides and z is information. Why: the IQR quantile method alone flips Intel 2022.
- (b) Keep IQR type 7; z decides, flagged low confidence.
- (c) Qn/Sn with small-sample factors.

**6.3 Health scores**
- (a) *Recommended.* F as health information, plus a cycle-neutral 0–4 subscore that votes in Q2 during shared slumps (untested engineering choice). Equity signal = net basic-share growth > 2%. G for growth names only, with ≥ 6 of 8 inputs and ≥ 5 peers, after the paper is verified. Why: F fails 4 signals mechanically at a trough (Micron FY2023 = 4).
- (b) F and G as approved (F ≤ 3 or G ≤ 2 = weakening).
- (c) Drop both from the grid; show only.

**6.4 Corrections to the approved profile** (D-M04-1)
- (a) *Recommended.* All three:
  - normalized earnings on both revenue bases, shown only for CYCLICAL_TROUGH or AMBIGUOUS;
  - Q2 capex row on capex ÷ revenue, with absolute cuts moved to Q1;
  - trough rule coded as two consecutive cycles with a write-down adjustment.

  Why: each fixes a misreading found in Micron's or Intel's real data.
- (b) The normalized-earnings change only.
- (c) Keep the approved profile as written.

---

## Build parts (proposal)
Each part is one conversation at Medium effort; High only if a design question arises.
- **Branches:** `m04-part1`, `m04-part2`, and so on.
- **Each part:**
  - updates M04_FINANCIALS.md (and DATA_SOURCES.md where relevant) in the same commit;
  - adds its rows to the company Financials tab;
  - ships fixture tests.
- **Live check:** one combined owner run of `uv run python scripts/run_live.py <label>` per part, a few minutes, with the log sent back. Claude cannot call SEC.
- **Fixtures:** non-watchlist cases (GE, Rivian, Target, Invitae, WDC, Lockheed) are captured as files by those owner runs.
- **Dependencies:** no new packages expected.

| Part | Contents | Depends on | Live check (one per part) |
|---|---|---|---|
| 1 Data foundation | `facts_as_of` (tag-switch and form fixes); shares split with multi-class cover counts (1.1); M04 extra concepts with a probe report; capex fallback marker and peer exclusion (1.2); `signal` writer; stale state | — | Companyfacts refresh for the watchlist; R1/instance cover counts for GOOG, META, MSTR; probe report of which extra tags each company uses |
| 2 Company profile and peers | `lifecycle_stage` (5.1) and owner model tag (3.4); SIC peer proposals and owner confirmation into `peer_group` (1.3); offset tolerance (1.4); small-n peer statistics (6.2); 53-week and acquisition flags | 1 | One EDGAR browse-by-SIC probe; companyfacts for confirmed peers (about 1 request each) |
| 3 Event, filing and restatement flags | 4.02/4.01/2.04/3.01/1.03/2.06 digest items; NT filings; amendment counts; restatement walk with step labels (2.2, 2.3); dei error flag | 1 | 10-K instances since 2023 for the dei flag (about 1 per watchlist 10-K); walk report over stored facts |
| 4 Survival gate and distress language | Runway (4.2); maturity wall (4.3); Z/Z″ (O after the paper check) (4.1); going-concern and covenant finders and classifier (4.4); gate states including "incomplete" | 1, 2, 3 | EFTS history pass (3 phrases × 16 companies) if 4.4a; gate printout for the watchlist |
| 5 Dilution and financing pressure | Net issuance (3.1); frames cross-section bands and composite issuance (3.2); SBC block; shelf and 424B classification with fee exhibits (3.3); overhang finder; `financing_pressure` (3.4) | 1, 2, 4 | Annual CY frames of basic weighted shares (about 2 per year); fee exhibits for watchlist 424Bs from the last 3 years |
| 6 Earnings quality | `eq_cash`; contract-asset and deferred-revenue gaps; M-score; `misstate_f` (2.1); estimate-change finder and bands (2.4) | 1, 2, 3 | One prior 10-K per watchlist company (if 2.4a); FTS5 estimate-change scan report |
| 7 Unit economics and segments | R12 trigger (5.2); cause finder (5.3); stated items; `unit_metric` with Tesla DS2; EX-99.2; RIVN tracked; dimensional segment and product facts (5.4) | 1, 2 | EX-99.2 for configured companies; instances for segment axes (watchlist); RIVN backfill |
| 8 CvD assembly, health scores and calibration | Q1/Q2 grid and classification; guidance hit rate and "removed" kind (S1.7); F/G (6.3); profile corrections (6.4); normalized earnings and overreaction gauge; M04 tab; backtest harness on the owner's labels (6.1) | 1–7 | Companyfacts for non-watchlist episode companies (about 10–15 requests); backtest report with confusion matrix and stability |

The owner's blind labelling for Part 8 can run alongside Parts 3–7.

## New sources
Provisional IDs. They become S122 onward when added to SOURCES.md, which also needs the duplicate S101 fixed. "Other" marks non-peer-reviewed or secondary sources.

- **S-new-1** SEC XBRL companyconcept data checked 2026-10-12. Pattern: `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/<taxonomy>/<Tag>.json`.
  - Micron (CIK0000723125): SalesRevenueNet, GrossProfit, revenue tags.
  - Strategy (CIK0001050446): weighted-average basic and diluted shares, ProceedsFromIssuanceOfCommonStock, ShareBasedCompensation; dei and CommonStockSharesOutstanding 404.
  - Meta (CIK0001326801): ShareBasedCompensation, PaymentsForRepurchaseOfCommonStock, PaymentsRelatedToTaxWithholdingForShareBasedCompensation, revenue, operating cash flow, weighted-average shares; share tags 404.
  - Alphabet (CIK0001652044): net income, CFO; dei 404.
  - GE (CIK0000040545): NetIncomeLoss, Revenues, NetCashProvidedByUsedInOperatingActivities.
  - Intel (CIK0000050863): OperatingIncomeLoss, GrossProfit.
  - WDC (CIK0000106040): RevenueFromContractWithCustomerExcludingAssessedTax.
  - Rivian (CIK0001874178): GrossProfit.
  - Lockheed (CIK0000936468): ContractWithCustomerPerformanceObligationSatisfiedInPreviousPeriod.
  - Target (CIK0000027419): InventoryNet.
  - Infleqtion (CIK0002007825): ClassOfWarrantOrRightOutstanding, dei EntityCommonStockSharesOutstanding.
  - Example: https://data.sec.gov/api/xbrl/companyconcept/CIK0000723125/us-gaap/GrossProfit.json
- **S-new-2** Bhojraj, Lee & Oler (2003), "What's My Line? A Comparison of Industry Classification Schemes for Capital Market Research", J. Accounting Research 41(5):745–774 — https://ideas.repec.org/a/bla/joares/v41y2003i5p745-774.html
- **S-new-3** Fiscal-year alignment conventions: Compustat fiscal-year assignment — https://leiq.bus.umich.edu/docs/Fiscal%20Year-end%20Month%20of%20Data.pdf ; Fama-French portfolio formation lag — https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/tw_5_ports_me_AC.html
- **S-new-4** SEC Release 33-9002 (2009), XBRL phase-in (summary, other) — https://www.willkie.com/publications/2009/02/sec-issues-final-rules-mandating-xbrl-filings
- **S-new-5** Micron:
  - FY2023 10-K — https://www.sec.gov/Archives/edgar/data/723125/000072312523000054/mu-20230831.htm
  - Q4 FY2023 release — https://www.sec.gov/Archives/edgar/data/723125/000072312523000051/a2023q4ex991-pressrelease.htm
  - Q2 FY2023 release — https://www.sec.gov/Archives/edgar/data/723125/000072312523000018/a2023q2ex991-pressrelease.htm
  - StorageNewsletter (other) — https://www.storagenewsletter.com/2023/09/28/micron-fiscal-4q23-financial-results/
  - edgar.tools inventories (other) — https://app.edgar.tools/companies/MU
  - Q2 FY2023 call transcript (other) — https://www.marketbeat.com/earnings/transcripts/88099/
- **S-new-6** Sloan (1996), "Do Stock Prices Fully Reflect Information in Accruals and Cash Flows about Future Earnings?", The Accounting Review 71(3):289–315 — https://www.cuhk.edu.hk/acy2/workshop/June2009Wasley/1996TAR).pdf
- **S-new-7** Richardson, Sloan, Soliman & Tuna (2005), J. Accounting & Economics 39:437–485 — https://academicnewsletter.sufe.edu.cn/info/412636 ; Fairfield, Whisenant & Yohn (2003), The Accounting Review 78(1):353–371 (summaries only) — https://maaw.info/TheAccountingReview-5.htm
- **S-new-8** Green, Hand & Soliman (2011), "Going, Going, Gone? The Apparent Demise of the Accruals Anomaly", Management Science 57(5):797–816 — https://ideas.repec.org/a/inm/ormnsc/v57y2011i5p797-816.html
- **S-new-9** McLean & Pontiff (2016), "Does Academic Research Destroy Stock Return Predictability?", J. Finance 71(1):5–32 — https://academicnewsletter.sufe.edu.cn/info/359722
- **S-new-10** Hou, Xue & Zhang, "Replicating Anomalies", NBER w23394 (2017) — https://www.nber.org/papers/w23394.pdf ; Review of Financial Studies 33(5):2019–2133 (2020) — https://ideas.repec.org/a/oup/rfinst/v33y2020i5p2019-2133..html
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
  - The C&DI 104.20 text is to be read before build.
- **S-new-20** SEC v. General Electric, primary documents (adds links to S03): Order 33-10899 — https://www.sec.gov/litigation/admin/2020/33-10899.pdf ; press release 2020-312 — https://www.sec.gov/news/press-release/2020-312 ; GE 8-K — https://www.sec.gov/Archives/edgar/data/40545/000004054520000062/ge-20201209.htm
- **S-new-21** Albrecht, Glendening, Kim & Lee (2024), Review of Accounting Studies 29(2):1320–1359 — https://academicnewsletter.sufe.edu.cn/info/413886 ; Audit Analytics, nineteen years of changes in estimates (other) — https://blog.auditanalytics.com/an-overview-of-nineteen-years-of-changes-in-accounting-estimates/
- **S-new-22** Alphabet FY2023 10-K — https://www.sec.gov/Archives/edgar/data/1652044/000165204424000022/goog-20231231.htm ; Amazon FY2025 10-K — https://www.sec.gov/Archives/edgar/data/1018724/000101872426000004/amzn-20251231.htm
- **S-new-23** COSO (2010) fraudulent financial reporting study, via BDO (other) — https://www.bdo.com/insights/focus-on-fraud-coso-fraudulent-financial-reporting-study ; Stubben (2010), "Discretionary Revenues as a Measure of Earnings Management", The Accounting Review 85(2):695–717 — https://academicnewsletter.sufe.edu.cn/info/415968
- **S-new-24** ASC 606 tag coverage, SEC frames API, checked 2026-10-12:
  - prior-period performance-obligation tag: 126 filers CY2024;
  - contract assets: 579 and contract liabilities: 2,034 at CY2024Q4I;
  - `ChangeInAccountingEstimateFinancialEffect`: 404.
  - Links: https://data.sec.gov/api/xbrl/frames/us-gaap/ContractWithCustomerPerformanceObligationSatisfiedInPreviousPeriod/USD/CY2024.json ; filer R page — https://www.sec.gov/Archives/edgar/data/813828/000081382820000022/R53.htm
- **S-new-25** SEC Staff Accounting Bulletin No. 99, Materiality — https://www.sec.gov/interps/account/sab99.htm
- **S-new-26** Pontiff & Woodgate (2008), "Share Issuance and Cross-sectional Returns", J. Finance 63(2):921–945 — https://ideas.repec.org/a/bla/jfinan/v63y2008i2p921-945.html ; McLean, Pontiff & Watanabe (2009), J. Financial Economics 94(1):1–17 — https://ideas.repec.org/a/eee/jfinec/v94y2009i1p1-17.html
- **S-new-27** Kenneth R. French Data Library, portfolios formed on net share issues — https://mba.tuck.dartmouth.edu/pages/faculty/ken.French/Data_Library/det_port_form_NI.html
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
- **S-new-36** Altman (2000), "Predicting Financial Distress of Companies: Revisiting the Z-Score and ZETA Models", NYU Stern — https://pages.stern.nyu.edu/~ealtman/Zscores.pdf
- **S-new-37** Market-based distress measures:
  - Shumway (2001), "Forecasting Bankruptcy More Accurately: A Simple Hazard Model", J. Business 74(1):101–124 — https://ideas.repec.org/a/ucp/jnlbus/v74y2001i1p101-24.html
  - Hillegeist et al. (2004), Review of Accounting Studies 9(1) — https://ideas.repec.org/a/spr/reaccs/v9y2004i1d10.1023_brast.0000013627.90884.b7.html
  - Altman et al. (2017), J. International Financial Management & Accounting 28(2) (abstract) — https://doi.org/10.1111/jifm.12053
- **S-new-38** Ohlson (1980), J. Accounting Research 18(1); formula via Wikipedia (other; original to be read) — https://en.wikipedia.org/wiki/Ohlson_O-score
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
  - Chava & Roberts (2008), J. Finance 63(5) — https://finance.wharton.upenn.edu/~mrrobert/resources/Publications/CovenantInvestmentJF2008.pdf
- **S-new-45** Reg S-X 4-08(c) — https://www.law.cornell.edu/cfr/text/17/210.4-08 ; ASC 470-10-45-11 (Deloitte Roadmap) — https://dart.deloitte.com/USDART/home/codification/liabilities/asc470-10/roadmap-debt/chapter-13-balance-sheet-classification/13-5-credit-related-covenant-violations
- **S-new-46** XBRL debt-maturity elements (KLA filing viewer) — https://ir.kla.com/sec-filings/annual-reports/xbrl_doc_only/3365 ; SEC Release 33-10890 MD&A amendments (Kirkland summary, other) — https://www.kirkland.com/-/media/publications/alert/2020/11/alert--sec-amends-mda-disclosure-rules.pdf
- **S-new-47** Rivian:
  - Q2 2026 8-K Ex. 99.1 — https://www.sec.gov/Archives/edgar/data/0001874178/000187417826000053/ex-9912q26rivianearningspr.htm
  - FY2025 release copy (other; replace with the EDGAR Ex. 99.1) — https://seekingalpha.com/pr/20398455
  - Q4 2023 shareholder letter — https://www.sec.gov/Archives/edgar/data/1874178/000187417824000005/ex-9924q23shareholderletter.htm
  - Q4 2024 shareholder letter — https://www.sec.gov/Archives/edgar/data/1874178/000187417825000004/ex-9924q24shareholderletter.htm
  - FY2024 10-K — https://www.sec.gov/Archives/edgar/data/1874178/000187417825000007/rivn-20241231.htm
  - 2025 deliveries release (Business Wire, 2026-01-02; URL to add)
- **S-new-48** Invitae: Q4 2022 release — https://www.sec.gov/Archives/edgar/data/1501134/000150113423000022/a991pressreleaseforearning.htm ; Q3 2023 release — https://www.sec.gov/Archives/edgar/data/1501134/000150113423000102/a991pressreleaseforearning.htm
- **S-new-49** Regulation S-K Item 303 (MD&A) — https://www.law.cornell.edu/cfr/text/17/229.303
- **S-new-50** Tesla FY2023 10-K — https://www.sec.gov/Archives/edgar/data/1318605/000162828024002390/tsla-20231231.htm ; delivery 8-Ks (EX-99.1, stored under DS2); FY2024 10-K (URL to add)
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
  - Croux & Rousseeuw (1992) small-sample factors as implemented in the R package revss — https://cran.r-project.org/web/packages/revss/revss.pdf
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
- **S-new-68** Intel–US government equity stake (Yahoo Finance, other) — https://finance.yahoo.com/news/intel-announces-89-billion-investment-from-us-government-which-will-own-99-of-chipmaker-180452175.html
- **S-new-69** Mercury Research Q4 2025 server share, via heise (other; extends S36) — https://heise.de/-11176017

**Reused IDs:** S02, S03, S32–S37, S39–S41, S43, S47, S50, S56, S81, S97, S98, S100, S103, S105, S109, S110, S112.

**Dropped as unverifiable:**
- Going-concern rates attributed to Carson et al. (2013): a secondary summary only.
- Begley, Ming & Watts (1996): no working link.
- Bernard & Noel (1991) and Banz & Breen (1986): no link.
- The 2020 inventory-gap replication: uncited.
- Meta's 2025 server-life figure: inconsistent secondary source.
- GE's ASC 606 split amounts: secondary only.
- Invitae Z″ values: to be recomputed from fixtures.
