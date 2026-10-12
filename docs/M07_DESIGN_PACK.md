# M07 — Design review pack (draft for the owner)

**Status:** research only — nothing is decided until the owner answers (D7); 2026-10-12 · Effort: High for this review, Medium per build part. Outputs are research signals, not financial advice.

## Purpose and dependencies
**Purpose.** Turn insider filings (Form 4, 10b5-1 disclosures, Form 144) and holder filings (13D, 13G, 13F) into D13 signals with grade A (D14). Every signal is visible in every timeframe (D10). Sale and exit items are warnings only (D16).

**Must honour:**
- R7: weight opportunistic open-market buys. Routine and 10b5-1 sales are noise unless abnormal.
- R13: totals come from raw Form 4 rows (S05).
- R16: Form 4 and 13D/G show in all timeframes. 13F is lagged.
- R22: show sales as $, % of stake and % of float or volume. G/A/M/F rows stay out of $ totals.
- D-SEC-10: 10b5-1 status is judged per row. Holdings are not stored.
- M01: ownership has "medium" weight in MY. Rule 6 raises alerts for opportunistic Form 4s.

**Depends on:**
- **M00:** `sec/insiders.py` (parser form4-1); `insider_txn` and `form4_doc` (migrations 0001/0005); the P/S report in `refresh.py` (lines ~276–295); the D13 `signal` table; the review queue; Tiingo `price_bar` (0012).
- **M02 part 5b:** `financing/schedules.py` and `thirteenf.py`; `fin_schedule`, `fin_holding` and `fin_issuer_map` (0023); EntityPublicFloat in `themes/flags.py` (D-M02-50).
- **M04:** the shares-concepts split (M04 pack question 1.1).
- **Consumer:** M11 (thesis, killswitch).

**How to answer.**
- Reply in plain text, e.g. "1.1a 1.2a 1.3a".
- Strike a suggestion by number ("S2.4 no"), or reply "rest ok".
- Answers become D-M07-1 onward.
- Thresholds are starting values, calibrated in Round 6.
- Citations are SOURCES.md S-numbers or provisional S-new-M07-n IDs.

---

## Round 1 — Which insider trades carry information (R7)

### What the research says
1. **How CMP classifies (S09; full text read, NBER w16454).**
   - Only insiders who traded in each of the 3 prior calendar years are classified.
   - *Routine* means trading in the same calendar month in ≥ 3 consecutive years. Every other classified insider is *opportunistic*.
   - The class is set each 1 January. Back-windows of 1–5 years give similar results.
   - Classified trades are about a third of all trades, tilted to large stocks. Of these, 64% of buys and 52% of sales are routine.
2. **CMP returns (S09).**
   - Long opportunistic buys, short opportunistic sells: 82 bps a month value-weighted (t = 2.15) and 180 bps equal-weighted (t = 6.07).
   - The routine spread is negative value-weighted and 43 bps equal-weighted (t = 1.73, only marginal).
   - Opportunistic sales carry −78 bps a month (t = 5.67). Routine sales carry +4 bps (not significant).
   - The result holds in both large and small stocks. Senior insiders are not significantly different. Local insiders' trades predict more firm news (modest evidence).
   - The sample is 1986–2007, so the effect may have decayed.
3. **Pooled studies.**
   - The information is in purchases, not sales, mainly in smaller firms; sample 1975–1995 (S-new-M07-1).
   - Purchases earn more than 6% a year abnormal; sales earn nothing significant (S-new-M07-2).
   - Both studies pool all sales together.
4. **Clusters and role.**
   - Clustered purchases are followed by more than 2% abnormal return the next month (S-new-M07-3).
   - CFO buys beat CEO buys by about 5% over 12 months (1992–2002). This is a single study (S-new-M07-4).
5. **Alternative definition (S-new-M07-5, read from summaries only).**
   - Insiders whose past pre-earnings trades were profitable earn more than 1% a month value-weighted, on the short side too (1986–2014).
   - Their firms have more restatements, enforcement actions and litigation.
6. **Codes.** Only P (open-market or private purchase) and S are discretionary trades. A, D, F, M, G, J, K, C, X, W and U are not (S-new-M07-17).
7. **Contract buys hide under code A.** Intel's 8-K (Item 5.02) required Lip-Bu Tan to buy $25M of shares *from Intel* within 30 days. His Form 4 codes the buy A, with a footnote citing the offer letter (S-new-M07-18).
8. **What is stored.**
   - `insider_txn` stores code, shares, price, shares_after, direct/indirect, role, footnotes, is_10b5_1 and plan_basis.
   - Joint filings keep all owners, but rows carry only the first owner (D-SEC-10).
   - The backfill keeps 3 years (`config/watchlist.toml` `form4_years = 3`), so almost no 2026 trade has 3 *prior* years.
   - The Insider Transactions Data Sets cover 2006 Q1–2026 Q3 for Forms 3, 4 and 5. In July 2025 the 2023–2025 sets gained the form-level `AFF10B5ONE` element (S46, S-new-M07-17).
   - Whether the sets carry row footnotes is unverified. This is DS6, deferred today.
   - The owner's address (`reportingOwnerAddress`) is not stored.

### Worked example
| Case (S-new-M07-18) | Facts | Proposed result |
|---|---|---|
| Musk, TSLA, Form 4 filed 2025-09-15, 0001104659-25-089693 | 25 P rows on 2025-09-12 at $371.90–$396.36, through his revocable trust; 2,568,732 shares, about $999.96M, average $389.28. Afterwards the trust holds 413,362,808, plus 96,000,000 direct. `aff10b5One` = 0. Roles: Director, CEO, 10% Owner | Classing him needs P/S rows in 2022–2024; those were not read, and the engine computes it. Otherwise `unclassified`, and the alert still fires |
| Tan, INTC, Form 4 for 2025-03-21, 0001127602-25-010360 | Code A, 1,043,406 shares at $23.96 (the 2025-03-20 close), about $25.0M, held by a family trust | `purchase_from_issuer`: shown, not scored |

*Illustrative (invented):*
- Director X trades in Feb and Aug 2023, Feb 2024, and Feb and Nov 2025 → routine for 2026.
- CFO Y trades in May 2023 and Sep 2024, with none in 2025 → unclassified.
- CEO Z trades in Mar 2023, Jun 2024 and Dec 2025 → opportunistic.

### All cases
1. P/S in all 3 prior years with a common month → routine. Without a common month → opportunistic.
2. A prior year without P/S (new insider; new listing such as SPCX, or INFQ after its SPAC merger; a gap year) → unclassified.
3. History made only of A/M/F/G/J/K/D/W/C/X/U rows → never counted.
4. P from the issuer or a private placement, or A with a price and a contract footnote → `purchase_from_issuer`.
5. Several trusts or joint filers for one person → one owner CIK.
6. Insider of several issuers, or also a 10% owner → class per (owner, issuer).
7. ≥ 3 distinct opportunistic buyers in the window → cluster. Opportunistic sales in the window offset it.
8. Plan-flagged row → `plan`. NULL evidence → "plan n/a".
9. Form 4/A → replaces the original.
10. Bulk rows before 2023 → no checkbox; row footnotes only if the sets carry them.

### Suggestions
- **S1.1** Add `insider_class(owner_cik, issuer_cik, year)` = routine / opportunistic / unclassified. Use CMP's exact rule on P and S rows only. Store the months seen in each prior year and the years of history used.
- **S1.2** P/S rows carry the class plus the subtypes `purchase_from_issuer` and `plan`.
- **S1.3** Backfill from the Insider Transactions Data Sets: one ZIP per quarter from 2006, about 83 requests, once. Per-filing Form 4s stay the source of truth from 2023, because the sets carry the 10b5-1 flag per form only (LESSONS).
- **S1.4** `cluster_buy`: ≥ 3 distinct opportunistic owner CIKs buying within 30 days, with joint filings counted once and no offsetting opportunistic sales.
- **S1.5** Parser form4-2 stores the owner's address state and the holding lines (Round 3), re-parsed from cached XML.
- **S1.6** No role multiplier in v1; the role is shown.

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| Class | Short history makes everyone look opportunistic; new listings have no history | `unclassified`, never defaulted; years used are stored |
| Code P / A with a price | Issuer purchases and contract buys get mixed with market buys or grants | Footnote and 8-K check; `purchase_from_issuer`, not scored |
| Mega-caps | Predictability is mainly in small firms (S-new-M07-1) | CMP holds in large stocks; per-name calibration |
| Effect sizes | Samples end 1995–2014; effects tend to shrink after publication | Treated as upper bounds; Round 6 backtest |
| Cluster count | One family's trusts counted as several insiders | Distinct owner CIKs |
| Role | Mixed evidence (S09 vs S-new-M07-4) | No multiplier |

### Questions
**1.1 Insiders CMP cannot classify**
- (a) *Recommended.* `unclassified` with no score; P rows still raise a rule 6 alert. Why: a default would score noise, and the alert keeps buys visible.
- (b) Treat them as opportunistic.
- (c) Hide them until 3 years of history exist.

**1.2 History source**
- (a) *Recommended.* Bulk backfill from 2006 using the Data Sets (closes DS6). Why: about 83 requests, once, gives every name the 3 prior years CMP needs.
- (b) Fetch per-filing Form 4s for 6 years.
- (c) Keep 3 years and accept almost no classes until 2029.

**1.3 Definition of "opportunistic"**
- (a) *Recommended.* CMP now; Ali–Hirshleifer later as a second flag. Why: CMP was read in full and needs only P/S rows.
- (b) Both at launch.
- (c) CMP only.

---

## Round 2 — 10b5-1 plans, abnormal sales, Form 144, gifts, hedges (R7, D-SEC-10)

### What the research says
1. **2022 amendments (S10; S-new-M07-17).**
   - Cooling-off for directors and officers: the later of 90 days after adoption, or 2 business days after the periodic report for the quarter of adoption. Capped at 120 days. Other persons wait 30 days.
   - One single-trade plan per 12 months; overlapping plans are restricted.
   - Item 408 discloses directors' and officers' plan adoptions and terminations each quarter, in tagged form.
   - Forms 4 and 5 filed from 2023-04-01 carry a 10b5-1 checkbox, and all bona fide gifts go on Form 4.
2. **Plans can be strategic (S-new-M07-6; abstract only, pre-2022).** Plan sales come before weak performance. Adoptions cluster before bad news, and early terminations come before good news.
3. **Size relative to holdings (S-new-M07-7; abstract, 1987–2002).** Only large sales that are also a large % of holdings predict negative returns. Small sales of a small % are followed by positive returns.
4. **Gifts (S-new-M07-8).** CEO and chair gifts come before sharp price drops, more so when the gift goes to their own family foundation. There are signs of backdating.
5. **Hedges (S-new-M07-9; 1996–2006 working paper).** Prices reverse after zero-cost collars and prepaid variable forwards, but not after exchange-fund contributions. Hedged fractions are about 30% for some types and about 9% for swaps.
6. **Form 144 (S-new-M07-10).** It must be filed electronically from 2023-04-13. An affiliate who intends to sell more than 5,000 shares or more than $50,000 in 3 months files a notice, which can arrive before the Form 4.
7. **Late disclosure (S-new-M07-11).** Delayed-disclosure sales were followed by −6% to −8%, but these were pre-SOX Form 5 transactions with the firm. Form 4s are due within 2 business days.
8. **What is stored and missing.**
   - Stored: the row `plan_basis`, the form `aff_10b5_1`, footnotes and the filing date.
   - Item 408 sits in 10-Q Part II Item 5 and 10-K Item 9B. The backfill holds only the latest 10-Q and 10-K.
   - The ecd tag names, and whether companyfacts carries them, are unverified (LESSONS: some tags exist only in the filing instance).
   - Form 144 XML is not parsed. The owner can check whether `filing` lists them with: `SELECT form, count(*) FROM filing WHERE form LIKE '144%' GROUP BY form`.

### Worked example — Jensen Huang, NVDA (real; S-new-M07-18)
**Plan** (NVDA 10-Q for the quarter ended 2025-04-27, Item 5): adopted 2025-03-20, up to 6,000,000 shares by 2025-12-31. Form 4 footnote F3 confirms the adoption date. The share count and end date were read through a search excerpt only.

| Step | Date |
|---|---|
| Adoption + 90 days | 2025-06-18 |
| 10-Q for the adoption quarter filed 2025-05-28, + 2 business days | 2025-05-30 |
| Cooling-off ends (the later date; cap 2025-07-18) | 2025-06-18 |
| First plan sale (Form 4 0001045810-25-000143) | 2025-06-20 → passes |

**That Form 4:**
- 7 S rows on 06-20 and 06-23, totalling 100,000 shares. Footnote F3 says they were sold under the plan.
- One F row on 06-18: 40,163 shares at $144.12, withheld for RSU taxes.
- `aff10b5One` = 1, but the F row is not a plan trade (D-SEC-10).
- **Plan progress:** at least 100,000 / 6,000,000 = 1.7%.
- **Timeliness:** the F row's deadline crosses Juneteenth (a federal holiday), so it falls on 06-23. A plain weekday count would wrongly flag the filing as late.

### All cases
1. Plan sale after cooling-off → noise. Before it → warning (the plan or footnote may be misread).
2. Adoption less than 30 days before a negative 8-K → red flag. Early termination → info. A modification → new cooling-off.
3. Plan of someone who is not a director or officer → 30 days. Adoption in fiscal Q4 → disclosed in 10-K Item 9B. Off-calendar quarters (NVDA) → the issuer's own quarters.
4. Checkbox set but the row is not a plan trade → row evidence only. No evidence → "plan n/a".
5. Opportunistic non-plan sale ≥ X% of holdings, or ≥ 3 opportunistic sellers in 30 days → abnormal. A small-% sale → not negative.
6. Form 4 past its deadline on the SEC calendar → late (info). 4/A and Form 5 → excluded.
7. Form 144 later matched by Form 4s → reconciled. Unmatched after 90 days → "not executed (as far as filed)".
8. Gift (G) by the CEO or Chair to a family foundation or trust after a 52-week high → info marker.
9. J/K or derivative row that may be a collar, a forward or a plain exercise → review queue.

### Suggestions
- **S2.1 Plan registry** `insider_plan(owner, issuer, adopted, terminated, max_shares, expires, source_accession, quote)`, built by a finder over stored 10-Q Item 5 and 10-K Item 9B text. Each row is a review item until confirmed (M02 pattern). ecd tags later.
- **S2.2 Plan checks**, using the federal-holiday calendar and the issuer's quarters: cooling-off, early-sale warning, plan progress, termination event.
- **S2.3 Abnormal sale** (warning), on any of:
  - (a) an opportunistic non-plan sale ≥ X% of holdings, with X = 10% as a starting display threshold;
  - (b) ≥ 3 opportunistic sellers in 30 days;
  - (c) a late filing (info only);
  - (d) a collar- or forward-type J/K row.
- **S2.4 `sec/form144.py`:** "intended sale" events, reconciled with later Form 4s.
- **S2.5 Gift flag** as in case 8; never part of $ totals.

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| "Plan = noise" | Plan timing can be strategic (pre-2022 evidence) | Registry red flags |
| Plan flag | Form checkbox ≠ row | Row `plan_basis`; NULL = "plan n/a" |
| Cooling-off | SEC business days ≠ NYSE days (SEC open on Good Friday, closed on Columbus and Veterans Day) | Federal calendar and issuer quarters |
| Form 144 | A notice is not a sale | "Intended" label; 90-day reconciliation |
| Gifts | Price often 0 | Valued at the close, labelled; out of totals |
| Late flag | 4/A and Form 5 look late; the evidence is pre-SOX | Original dates; info only |
| Hedges | Free-text description | Review queue with the footnote |

### Questions
**2.1 10b5-1 sales**
- (a) *Recommended.* Noise by default; registry red flags can raise a warning. Why: keeps R7 while catching the timing patterns in S-new-M07-6.
- (b) Always noise.
- (c) Same weight as non-plan sales.

**2.2 Opportunistic non-plan sales**
- (a) *Recommended.* A warning with negative value. Why: CMP finds −78 bps a month after them.
- (b) Only when "abnormal" by % of holdings.
- (c) Ignore them.

**2.3 Form 144**
- (a) *Recommended.* Parse it and show "intended sale". Why: it can arrive before the Form 4, and it has been XML since 2023.
- (b) Show a filing count only.
- (c) Skip it.

---

## Round 3 — Sale and buy cards: totals, stake, float, volume (R13, R22)

### What the research says
1. **Rows kept out of $ totals:** G/A/M/F (R22, D-SEC-10), and also D, J, K, U and W (S-new-M07-17).
2. **Holdings sit on separate lines and are not stored (S-new-M07-18; D-SEC-10).** Huang's Form 4 has:
   - a direct line of 75,773,225 after the F row (75,673,225 after the sales);
   - eight indirect lines totalling 783,375,400.
3. **Cover-page counts (S-new-M07-18).**
   - NVDA's dei count is rounded: 24,400,000,000 at 2025-05-23 and 24,300,000,000 at 2025-08-22.
   - TSLA's is exact: 3,225,448,889 at 2025-07-17.
   - Share concepts stay separate (M00_SEC_DATA; M04 pack 1.1).
4. **EntityPublicFloat** is a dollar figure dated to the end of fiscal Q2 (D-M02-50). 20-F and 40-F filers have none.
5. **Raw rows only:** press totals for CoreWeave mixed plan and non-plan sales (S05).
6. **Gaps:** holding lines, derivative holdings, Form 3 holdings, and a 4/A dedupe rule.

### Worked example — Huang Form 4 (real except ADV)
| Item | Value |
|---|---|
| $ sale total, 7 S rows, 100,000 shares | $14,403,585 (average $144.04) |
| Excluded F row | $5,788,292, shown as "not in total" (it would add 40%) |
| % of stake, direct line only | 100,000 / 75,773,225 = 0.13% |
| % of stake, all 9 lines | 100,000 / 859,148,625 = 0.012% |
| % of shares outstanding | 100,000 / 24,400,000,000 (rounded) ≈ 0.0004% |
| % of 20-day ADV | *Illustrative:* an ADV of 200M gives 0.05% (the real value comes from stored bars at build) |
| Plan | Yes (footnote F3) → noise unless a red flag fires (2.1a) |

Musk's buy, measured after the purchase: 2,568,732 / 509,362,808 = 0.50% of his stake, and 2,568,732 / 3,225,448,889 = 0.080% of shares outstanding.

### All cases
1. Many S rows across days → summed per form and per 30-day window. Mixed S + F → the F row is listed as "not in total".
2. Zero-price gift → valued at the close, separately. 4/A → replaces the original, matched by (owner, date, shares).
3. Weighted-average price → the footnote's price range on hover.
4. Direct and indirect lines, or joint filers → one stake per form, never summed across owners.
5. Options and RSUs → a separate "economic stake". Only a Form 3 on file → holdings missing.
6. Rounded or exact cover count → source and date shown. Foreign private issuer (GFS files 6-Ks) or new listing → 13G base or "float unknown", never 0.
7. Controlling holder → taken out of the float. A split inside the ADV window → unadjusted volume.

### Suggestions
- **S3.1 Sale card**, per form and per 30-day window:
  - $ (S rows only) and shares;
  - % of holdings before the sale (all non-derivative lines, line count shown);
  - % of shares outstanding and % of float, each with its date;
  - % of the 20-day ADV ending the day before;
  - plan status;
  - the excluded rows.
- **S3.2** `form4_holding(accession, line, table_kind, title, shares, direct_indirect, nature, footnotes)`, re-parsed from the cache.
- **S3.3 Totals** by insider, role and month, with a reconciliation line (R13).
- **S3.4 Buy card** mirrors the sale card and adds the cluster count.
- **S3.5 Float** = cover count − affiliates. Affiliates are controlling or insider 13D/G holders at or above 10%, plus officers' and directors' holdings. EntityPublicFloat ÷ close serves as a "derived" cross-check.

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| $ total | F/M/A/G or 4/A rows counted | S rows only; 4/A replaces the original |
| % of stake | Direct line only (11× too high for Huang) | All lines on the form; derivatives apart |
| % of float | Rounded or stale counts, FPIs, new listings | Dates shown; "unknown", never 0 |
| % of ADV | Split mismatch | Unadjusted volume; split check |

### Questions
**3.1 Stake denominator**
- (a) *Recommended.* All non-derivative shares on the form; derivatives shown apart. Why: the direct line alone overstates Huang's sale 11×.
- (b) Direct holdings only.
- (c) Including vested options and RSUs.

**3.2 Float**
- (a) *Recommended.* Cover count minus insiders and controlling holders, with EntityPublicFloat as a cross-check. Why: it works for foreign private issuers and controlled companies like GFS.
- (b) EntityPublicFloat ÷ price.
- (c) Shares outstanding.

**3.3 ADV window**
- (a) *Recommended.* 20 trading days before the trade. Why: closest to the liquidity the seller faced.
- (b) 50 days.
- (c) 3 months.

---

## Round 4 — Large holders: 13D and 13G (R16)

### What the research says
1. **Deadlines (S-new-M07-17).**
   - 13D: initial filing within 5 business days; amendments within 2.
   - 13G, qualified and exempt investors: 45 days after the quarter in which they cross 5%.
   - 13G, passive investors: 5 business days.
   - 13G amendments: 45 days after the quarter, but faster when a holder crosses 10% or moves 5%.
   - The new 13G deadlines apply from 2024-09-30, and structured data is required from 2024-12-18.
   - 13D Item 6 must disclose cash-settled derivatives.
2. **Activism:** announcements earn about 7% abnormal return, with no reversal within a year (S-new-M07-12).
3. **Lockup expiry:** −1.5% over 3 days and a permanent 40% rise in volume, larger for venture-backed firms (S-new-M07-13). Relevant to SPCX and INFQ.
4. **Stored (M02 part 5b).** 1,674 13D/G filings are listed under our companies, mostly by institutions filing about them. `schedules.py` reads every header but parses the XML only when the filer is ours or both sides are known (LESSONS).
5. **Gaps:**
   - a `subject_ours` parse path;
   - text-format schedules before Dec 2024 (DS11);
   - the Item 4 purpose text (to check at build);
   - S-1/424B lockup terms, which are not ingested (D-SEC-7).

### Worked example — GFS, event date 2026-06-30 (real; S-new-M07-18)
| Filing | Persons | Shares | % |
|---|---|---|---|
| Mubadala 13G/A No. 3, signed 2026-08-10, 0001140361-26-032099 | Mubadala Investment Company PJSC, Mamoura, Mubadala Technology (each) | 399,573,756 | 72.82 |
| Same filing | Two subsidiaries | 285,271,687 / 114,302,069 | 51.99 / 20.83 |
| FMR + Abigail P. Johnson 13G/A No. 6, 0000315066-26-002033 | Joint | 69,848,379.52 | 12.7 |

- **Base:** 548,700,833 shares at 2026-06-01, from GFS's 6-K. GFS is a foreign private issuer.
- **Naive sum** of the reporting persons: about 1.6B shares (291%).
- **Float:** 149,127,077 shares (27.2%). FMR holds 46.8% of it.

### All cases
1. New 13D → high-severity event. 13D/A → change in % and in the Item 4 text. Switch from 13G to 13D → event.
2. Initial 13G, qualified (quarterly lag) or passive (5 days) → lag shown.
3. Crossing 5%, 10% or 20%, or a 5% move → `holder_cross`. 13G/A below 5% → old and new % and the persons.
4. Joint filings → the maximum per filing, never the sum. Fractional shares are kept.
5. FPI base taken from a 6-K → base date shown. Holder at or above 50%, or with a control 13D → affiliate.
6. Text schedule before Dec 2024 → history gap. The filer-is-ours and subject-is-ours paths stay separate.
7. Lockup terms known, released early, staggered or unknown.

### Suggestions
- **S4.1** Add a `subject_ours` path to `schedules.run` that stores `fin_holding` rows with `role='holder_of_ours'` (estimate 5–15 per company per year).
- **S4.2** Signals: `holder_13d_new` (high), `holder_cross` (info), `holder_switch_13g_to_13d` (event).
- **S4.3** Major-holders panel: %, event date, filing lag and form; joint filers collapsed; affiliates highlighted.
- **S4.4** Lockup calendar: dates from the prospectus, confirmed by the owner; alert 10 trading days before expiry.

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| Summed persons | 291% at GFS | Maximum per filing |
| 13G "exit" | May be a reclassification or a group change | Old and new % and the persons |
| 13G lag | Up to 45 days after quarter end | "Filed N days later" |
| Lockups | Early or staggered releases | Prospectus; owner confirms; "unknown" otherwise |

### Questions
**4.1 Which 13D/13G filings to read**
- (a) *Recommended.* All XML schedules about our companies. Why: the headers are already stored, and the stakes feed the float.
- (b) 13D only.
- (c) Holders at or above 10% only.

**4.2 Lockups for SPCX and INFQ**
- (a) *Recommended.* Fetch the prospectus once; the owner confirms the dates. Why: the terms exist only there.
- (b) Enter the dates by hand.
- (c) Skip.

**4.3 New activist 13D**
- (a) *Recommended.* Alert in all timeframes, with no score until reviewed. Why: the average effect is positive, but the purpose varies.
- (b) Positive score.
- (c) Info only.

---

## Round 5 — Institutions: 13F (R16, lagged) and Q3

### What the research says
1. **13F:** due 45 days after quarter end; long positions only (S15).
2. **13F Data Sets (S-new-M07-17).**
   - Coverage July 2013 to August 2026.
   - Since March 2024, one ZIP per 3-month window, e.g. `01jun2026-31aug2026_form13f.zip` (96.05 MB).
   - The SEC does not guarantee their accuracy.
3. **Hidden positions:** positions disclosed later outperform for up to 12 months, mainly at hedge funds (S-new-M07-14).
4. **Copying is weak timing.** Copycat funds only matched high-expense active funds after costs (S-new-M07-15). Institutional trades have partly permanent price effects (S-new-M07-16).
5. **Mechanics (LESSONS, D-M02-45/46):** values are in thousands before 2023-01-03 and in dollars after. Rows are summed by CUSIP.
6. **Stored today:** only the 13Fs filed *by* AMZN, GOOG, INTC and NVDA (`thirteenf.py`), not who owns our companies.
7. **Latency:** June holdings are posted around 31 August, so they are 2–3 months stale.
8. **Q3 context (S-new-M07-18).** Fidelity's GFS 13G/A lists Abigail P. Johnson (Chairman and CEO of FMR) as a reporting person. Her family's Series B shares hold 49% of FMR's votes.

### Worked example — Berkshire's Apple position (real; S-new-M07-18)
| Period (filed) | Rows | Shares | Value | % of AAPL |
|---|---|---|---|---|
| 2024-03-31 (2024-05-15) | 12 | 789,368,450 | $135,360,901,805 | 5.15% of 15,334,082,000 (cover 2024-04-19) |
| 2024-06-30 (2024-08-14) | 12 | 400,000,000 | $84,248,000,000 | 2.63% of 15,204,137,000 (cover 2024-07-19) |

- **Change:** −389,368,450 shares (−49.3%), visible only 45 days after quarter end.
- Berkshire's own 10-Q gave the value almost two weeks earlier (S-new-M07-19, other).

### All cases
1. Adds, cuts, new positions and closed positions.
2. Several rows per CUSIP → summed. Put/call rows → kept separate.
3. Values before 2023 in thousands → scaled. A later amendment revealing hidden holdings → flagged.
4. Passive vs active holders. A followed manager → info event, with the lag shown.
5. Position sold before the filing → "lagged". Several CUSIPs for one issuer → mapped to the issuer.
6. Missing window → missing, never zero.

### Suggestions
- **S5.1** Quarterly `inst_step`:
  - download the newest ZIP once;
  - filter to our CUSIPs (from 13G XML and `fin_issuer_map`);
  - store `inst_holding`;
  - per company: holder count, % held, active vs passive, top adds and cuts.
- **S5.2** Followed managers named by the owner (e.g. Berkshire).
- **S5.3** `inst_ownership_change` (info; the method names the period and the filing date).

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| Change | Lag; the position may already be gone | Dates; "lagged"; weight 0 in ST |
| Coverage | Hidden positions, shorts, non-13F securities | "Long 13F only" label |
| Rows, units | Split rows; thousands vs dollars | Sum by CUSIP; scale by date |
| Index growth | Passive inflows look like accumulation | Passive list |

### Questions
**5.1 Q3 "CEO of equity": please paste the original sentence.**
- (a) *Recommended if unsure.* The company CEO's own stake and any pledged shares. Why: computable once form4-2 lands; pledging needs the proxy statement.
- (b) The CEO or CIO of a holder (follow managers you trust).
- (c) A 13F filer whose executive sits on our company's board.
- (d) Something else.

**5.2 13F scope**
- (a) *Recommended.* All holders, active and passive shown apart. Why: one download a quarter covers everyone.
- (b) Followed managers only.
- (c) Skip 13F in M07.

**5.3 13F weight**
- (a) *Recommended.* Info in all timeframes; medium weight in MY only. Why: the data are 2–3 months stale.
- (b) Medium in MY and PT.
- (c) Display only.

---

## Round 6 — Timeframe weights, alerts and calibration (D10, D13, M01 rule 6)

### What the research says
1. **M01:** ownership has "medium" weight in MY. Rule 6 alerts on opportunistic Form 4s. The PT and ST columns are not designed yet (M01_TIMEFRAMES.md).
2. **Horizons in the literature:**
   - next month (S09, S-new-M07-3);
   - 6–12 months (S-new-M07-2);
   - a year (S-new-M07-12);
   - 3 days (S-new-M07-13).
3. **Existing surfaces:**
   - chart markers are planned (M00_UI);
   - the Insiders tab shows raw rows (`ui/services.py`);
   - `refresh.py` prints P/S trades with plan status;
   - the `signal` table and the review queue exist.

### Worked example — Musk's buy as a D13 record (shape illustrative)
`{ticker: "TSLA", module_id: "M07", signal: "opportunistic_buy" (or "unclassified_buy" if 2022–24 history fails CMP), value: 999959042, timeframe: "MY", evidence_grade: "A", source_ref: "Form 4 0001104659-25-089693", method: "P rows, CMP class, form4-2; 0.50% of reported stake; 0.080% of shares outstanding (cover 2025-07-17)", as_of: "2025-09-15"}`

The ST alert fires on the filing day, Monday 2025-09-15. The trade was on Friday the 12th.

Proposed parameters (starting values):

| Parameter | MY | PT | ST |
|---|---|---|---|
| Insider window | 12 months | 3 months | 30 days |
| Cluster window | 90 days | 30 days | 10 days |
| 13F weight | medium | low | 0 |
| Alerts | opportunistic P, 13D, abnormal sale | + Form 144 | + lockup |

### All cases
1. One form producing several signals → one primary signal, the others as attributes.
2. Old signal → decays out of the score but stays visible.
3. Profile switch → same records, new weights (D10, D12).
4. Plan and routine sales → never alert. Unclassified buy → alert, no score.
5. "Wrong?" mark → review item and calibration input. An amendment → record updated, no repeat alert.

### Suggestions
- **S6.1** One primary signal per form. Cluster size, % of stake, plan red flag and lateness go in as attributes.
- **S6.2** Decay windows per profile (table above).
- **S6.3 UI:**
  - chart markers: buy green, sale red, plan sale hollow, gift grey;
  - Insiders tab with buy and sale cards;
  - "Major holders" and "Institutions (lagged)" panels;
  - review items for plan rows, J/K hedges and purchases from the issuer.
- **S6.4 Calibration:** backtest the stake %, cluster window and decay on watchlist history (data sets plus stored Tiingo prices). Published effect sizes are treated as upper bounds.

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| Double count | One event emitted as three signals | One primary signal |
| Timeframe shopping | ST view of a 13F signal | Weight 0 in ST |
| Stale signals | An old buy still scoring | Decay |
| Alert fatigue | Weekly plan sales (Huang 2024) | No alerts for plan or routine sales |

### Questions
**6.1 PT/ST weights**
- (a) *Recommended.* Use the proposed table, revisited at the PT/ST phase. Why: the literature horizons already span all three timeframes.
- (b) MY only; everything else display-only.

**6.2 Alerts**
- (a) *Recommended.* Opportunistic P, cluster buys, new 13D, abnormal sales and lockups. Why: avoids flooding the digest.
- (b) Every P/S.
- (c) Weekly digest only.

**6.3 Calibration**
- (a) *Recommended.* Backtest, then owner review. Why: the samples are old and the watchlist is mostly mega-caps.
- (b) Literature defaults, fixed.

---

## Signals out
All grade A (D14), `module_id = "M07"`, `source_ref` = accession, visible in every timeframe (D10). The weights follow the answers to 1.1, 2.2, 4.3, 5.3 and 6.1.

| Signal | Value | MY | PT | ST |
|---|---|---|---|---|
| opportunistic_buy | $ and shares; cluster size | scored | scored | alert |
| cluster_buy | distinct insiders | scored | scored | alert |
| unclassified_buy | $ and shares | alert, no score | alert, no score | alert |
| purchase_from_issuer | $; contract source | display | display | – |
| opportunistic_sell / abnormal_sale | −1 + % of stake, plan red flag, late | warning | warning | alert |
| plan_adopted / plan_terminated / plan_progress | shares, dates | info | info | – |
| intended_sale (Form 144) | shares | info | info | alert |
| hedge_or_gift_flag | J/K/G with context | warning / info | info | – |
| holder_13d_new / holder_cross / holder_switch_13g_to_13d | %, direction | scored after review | scored after review | alert |
| inst_ownership_change | Δ% of shares outstanding, lagged | medium | low | 0 |
| lockup_expiry | date; shares locked if known | info | scored | alert |

## Build parts (proposal)
- **Effort:** one conversation per part at Medium effort; High only if a design question arises.
- **Branches:** `m07-partN`.
- **Each part:**
  - updates the M07 module doc (from MODULE_TEMPLATE.md) and DATA_SOURCES.md in the same commit;
  - ships fixture tests.
- **Live check:** one combined owner run of `uv run python scripts/run_live.py <label>` per part, a few minutes, with the log sent back. Claude cannot call SEC.
- **Dependencies:** no new packages expected; ZIP handling is in the standard library.

| Part | Contents | Depends on | Live check |
|---|---|---|---|
| 1 Holdings and history | form4-2 (S1.5, S3.2); Data Sets backfill (S1.3); 4/A dedupe | M00 | Two quarterly ZIPs (one pre-2023, one 2025) to check layout and row footnotes; the owner's Form 144 query. The full backfill then runs as an owner-run script |
| 2 Classes and cards | S1.1–S1.4; S3.1, S3.3–S3.5 | 1; M04 part 1 shares split (or dei cover facts read directly) | Class and card report over the real DB, no SEC (Musk 2022–24, Huang 2025) |
| 3 Plans and intended sales | S2.1–S2.5 | 1, 2 | NVDA Item 5 re-read; one ecd instance probe; Form 144 XML for the last 12 months |
| 4 Large holders and lockups | S4.1–S4.4 | 2 | XML for schedules about our companies (headers stored); SPCX and INFQ prospectuses |
| 5 Institutions | S5.1–S5.3 | 4 (CUSIP map) | Newest 13F Data Set ZIP (one request, about 96 MB) |
| 6 Signals, UI, calibration | Signal writer; S6.1–S6.4 | 1–5 | Backtest report on stored data and Tiingo bars; alert dry run |

## Known gaps
1. **NVDA plan size:** the share count and end date in Item 5 were read through a search excerpt; the Form 4 confirms the adoption date. Re-read at build.
2. **Item 408 tags:** the ecd element names, and whether companyfacts carries them, are unverified.
3. **Data Set footnotes:** whether the Insider Transactions Data Sets carry row footnotes (needed for plan evidence before 2023) is unverified.
4. **Form 144:** whether `filing` lists them needs the owner's query; the XML layout is unchecked.
5. **Form 3 and Form 5 deadlines** were not re-verified. Only the 2-business-day rule for Form 4 is confirmed.
6. **Musk's history:** his 2022–2024 Form 4s were not read, so his CMP class is open.
7. **ADV figures** are illustrative; Claude cannot read the Tiingo bars.
8. **Lockups:** SPCX and INFQ lockup terms were not read; the prospectuses are not stored.
9. **Abstract-only papers:** the effect sizes for S-new-M07-4, -5, -6, -7 and -12 come from abstracts or search summaries. S-new-M07-9 was read from the 2009 working paper; the reported Financial Management 2015 44(3):655–683 version is unverified.
10. **Age of the evidence:** the insider samples end between 1995 and 2014. S-new-M07-6 predates the 2022 amendments, and S-new-M07-11 predates SOX.
11. **Searches stopped early** (search limit). Kang, Kim & Wang (2018) on clusters was not checked and is not cited.
12. **Data register:**
    - DS6 changes from deferred to needed.
    - New entries are proposed for 13F holders of our names, Form 144, DEF 14A ownership and pledging, and S-1/424B lockups.
    - The research numbered these DS12–DS15, but the M04 pack proposes DS12–DS15 for other items. Assign the numbers at merge.
13. **Outdated URL:** SOURCES.md S46 still points to https://www.sec.gov/dera/data/form-345. The current page is listed under S-new-M07-17.
14. **How the research touched SEC:**
    - One curl download of the Musk Form 4 sent a User-Agent containing the owner's email.
    - One fetch of the NVDA 10-Q with a generic User-Agent returned what looks like SEC's block page. No direct SEC requests were made after that.
    - Nothing in the repository was changed.

## New sources
These IDs are provisional. They become S-numbers, after the M04 pack's, when added to SOURCES.md. "Other" marks non-peer-reviewed sources.

- **S09 (existing)**, full text read from NBER working paper w16454 — https://www.nber.org/papers/w16454.pdf
- **S-new-M07-1** Lakonishok & Lee (2001), Review of Financial Studies 14(1):79–111 — https://ideas.repec.org/a/oup/rfinst/v14y2001i1p79-111.html
- **S-new-M07-2** Jeng, Metrick & Zeckhauser (2003), Review of Economics and Statistics 85(2):453–471 — https://ideas.repec.org/a/tpr/restat/v85y2003i2p453-471.html
- **S-new-M07-3** Alldredge & Blank (2019), Journal of Financial Research 42(2):331–360 — https://ideas.repec.org/a/bla/jfnres/v42y2019i2p331-360.html
- **S-new-M07-4** Wang, Shin & Francis (2012), JFQA 47(4):743–762 — https://ideas.repec.org/a/cup/jfinqa/v47y2012i04p743-762_00.html
- **S-new-M07-5** Ali & Hirshleifer (2017), Journal of Financial Economics 126(3):490–515 — https://www.escholarship.org/uc/item/2sb6x1hj
- **S-new-M07-6** Jagolinzer (2009), Management Science 55(2):224–239 — https://pubsonline.informs.org/doi/references/10.1287/mnsc.1080.0928
- **S-new-M07-7** Scott & Xu (2004), "Some Insider Sales Are Positive Signals", Financial Analysts Journal 60(3) — https://rpc.cfainstitute.org/research/financial-analysts-journal/2004/some-insider-sales-are-positive-signals
- **S-new-M07-8** Yermack (2009), Journal of Financial Economics 92(1):107–123 (working-paper version) — https://archive.nyu.edu/handle/2451/27856
- **S-new-M07-9** Bettis, Bizjak & Kalpathy (2009 working paper), "Insiders' Use of Hedging Instruments: An Empirical Examination" — https://shareholderforum.com/SOP/Library/20090318_Bettis-Bizjak-Kalpathy.pdf
- **S-new-M07-10** Debevoise & Plimpton (2023), Form 144 electronic-filing memo (other) — https://www.debevoise.com/insights/publications/2023/04/sec-requires-form-144-to-be-filed-electronically
- **S-new-M07-11** Cheng, Nagar & Rajan (2007), Review of Financial Studies 20(6):1833–1864 — https://ideas.repec.org/a/oup/rfinst/v20y2007i6p1833-1864.html ; SEC, Form 4 two-business-day rule (primary) — https://www.sec.gov/resources-small-businesses/going-public/officers-directors-10-shareholders
- **S-new-M07-12** Brav, Jiang, Partnoy & Thomas (2008), Journal of Finance 63(4):1729–1775 — https://ideas.repec.org/a/bla/jfinan/v63y2008i4p1729-1775.html
- **S-new-M07-13** Field & Hanka (2001), Journal of Finance 56(2):471–500 — https://ideas.repec.org/a/bla/jfinan/v56y2001i2p471-500.html
- **S-new-M07-14** Agarwal, Jiang, Tang & Yang (2013), Journal of Finance 68(2):739–783 — https://ideas.repec.org/a/bla/jfinan/v68y2013i2p739-783.html
- **S-new-M07-15** Frank, Poterba, Shackelford & Shoven (2004), Journal of Law and Economics 47(2):515–541 — https://ideas.repec.org/a/ucp/jlawec/y2004v47i2p515-41.html
- **S-new-M07-16** Sias, Starks & Titman (2006), Journal of Business 79(6):2869–2910 (RePEc lists only Sias and Starks) — https://ideas.repec.org/a/ucp/jnlbus/v79y2006i6p2869-2910.html
- **S-new-M07-17** SEC primary pages:
  - Form 4 transaction codes — https://www.sec.gov/edgar/searchedgar/ownershipformcodes.html
  - Rule 10b5-1 fact sheet (URL for S10) — https://www.sec.gov/files/33-11138-fact-sheet.pdf
  - 13D/13G modernization fact sheet — https://www.sec.gov/files/33-11253-fact-sheet.pdf
  - Form 13F Data Sets — https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets
  - Insider Transactions Data Sets (current URL for S46) — https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets
- **S-new-M07-18** Filings used in the examples (primary):
  - Musk Form 4, 0001104659-25-089693 — https://www.sec.gov/Archives/edgar/data/1318605/000110465925089693/tm2526050-1_4seq1.xml
  - Intel 8-K, 0000050863-25-000036 — https://www.sec.gov/Archives/edgar/data/50863/000005086325000036/intc-20250310.htm
  - Tan Form 4, 0001127602-25-010360 — https://www.intc.com/filings-reports/all-sec-filings/content/0001127602-25-010360/form4.html
  - Huang Form 4, 0001045810-25-000143 — https://www.sec.gov/Archives/edgar/data/1045810/000104581025000143/wk-form4_1750718967.xml
  - NVDA 10-Q, 0001045810-25-000116 — https://www.sec.gov/Archives/edgar/data/1045810/000104581025000116/nvda-20250427.htm
  - GFS Mubadala 13G/A — https://www.sec.gov/Archives/edgar/data/1709048/000114036126032099/primary_doc.xml
  - GFS FMR 13G/A — https://www.sec.gov/Archives/edgar/data/1709048/000031506626002033/primary_doc.xml ; Fidelity exhibit — https://www.sec.gov/Archives/edgar/data/1709048/000031506626002033/exhibit99.txt
  - Berkshire 13F-HRs — https://www.sec.gov/Archives/edgar/data/1067983/000095012324005622/32398.xml ; https://www.sec.gov/Archives/edgar/data/1067983/000095012324008740/34725.xml
  - dei cover counts — https://data.sec.gov/api/xbrl/companyconcept/CIK0001318605/dei/EntityCommonStockSharesOutstanding.json (TSLA; the same path with CIK0001045810 for NVDA and CIK0000320193 for AAPL)
- **S-new-M07-19** CNBC on Berkshire's Apple stake (other) — https://link.cnbc.com/public/36440273
