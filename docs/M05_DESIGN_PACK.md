# M05 — Design review pack (draft for the owner)

**Status:** research only — nothing is decided until the owner answers (D7); 2026-10-12 · **Effort:** High for this review, Medium for each build part.

Outputs are research signals, not financial advice. All figures were checked on 2026-10-12 against SEC primary pages and the XBRL companyconcept and frames APIs (S-new-M05-6…10). Rows marked *illustrative* are invented or computed only to show a method.

## Purpose and dependencies

**Purpose.** For each company, M05 shows two things:
- what the company has committed to spend: capex, purchase obligations, prepayments and leases not yet commenced;
- what customers have committed to it: RPO, backlog and deposits.

It reads both against the company's own history and its business model. It also reports capex cycles and the company's record of carrying out its capex plans. M05 gives signals and warnings only; the owner decides (D8, D16).

**Approved revisions it must honour:**
- **R9:** for fabless companies, purchase obligations and prepayments are the primary gauge. Capex is still monitored for new offerings.
- **A1:** the leading filing data are RPO, purchase obligations and ≥10% customers.
- **A2** (M04_FINANCIALS): the capex split ladder runs disclosed → project-level → Greenwald (default) → D&A. Every value is method-tagged.
- **D-M02-5:** capex guidance is positive for the spender and its suppliers, labelled "hypothesis, not backtested".
- **Core decisions:**
  - D8: ambiguous items go to the review queue.
  - D9: every indicator has failure-mode rows.
  - D10: every output is visible; profiles change weights only.
  - D13: signal record.
  - D14: evidence grades.
  - D16: warnings only.
  - D19: peer groups.
  - S2: free sources only.
  - R8: HBM is an oligopoly.
  - R19: guidance ledger (M11).
- **CLAUDE.md:** missing data stays missing, never zero.

**Depends on:**
- **M00:**
  - `fact` stores every companyfacts tag;
  - `sec/sections.py` stores 10-K Items 7 and 8 and 10-Q Part I Items 1–2 as searchable text;
  - `xbrl_facts.CONCEPTS`.
- **M02 part 3 (`moneyflow/`):**
  - capex guidance and its freshness (`guided.py`, D-M02-28, D-M02-30);
  - own-definition actual capex (`actuals.py`, `config/capex_definitions.toml`);
  - stated actuals;
  - the capital-allocation block (D-M02-31);
  - `views.rpo`;
  - L0–L3 supply links;
  - `instance.py` (D-M02-32, D-M02-33).
- **M04** (its pack is still in progress and not approved):
  - the owner model tag (pack question 3.4, built in pack part 2);
  - the A2 split;
  - the CvD rows "Supply response", "R&D and capex intensity" and "Customer base" (D-M04-1);
  - peer groups (pack 1.3);
  - the survival gate (pack round 4);
  - `facts_as_of` and the `signal` writer (pack part 1).
- **M06:** the oligopoly flag. **M11:** the R19 ledger.

**M05 feeds:**
- M02 rung L4 (question 2.1);
- M04's earnings-quality block (`commitment_risk`);
- M04's CvD intensity and supply rows;
- M11 (the capex guidance record).

**Boundaries.** M05 reads the following and does not redo them:
- **M02 owns:**
  - spender capex guidance (latest per period, freshness states);
  - own-definition actual capex;
  - stated actuals;
  - the capital-allocation block;
  - `views.rpo` (year-on-year growth against the company's own median, shown in `company_view` and in the theme view's supplier rows);
  - L0–L3 links.
- **M02 rung L4** (order-flow matching) is still a "later part" (D-M02-7). Question 2.1 asks whether its store moves into M05.
- **M04 owns:**
  - the model tag;
  - the A2 split ladder. The M04 pack has no capex-split item yet; `capex_maint` is a name proposed here;
  - the CvD "Customer base" row and the stickiness classes. The M04 pack plans no customer store and lists customer-concentration % as "missing: dimensional";
  - the CvD "R&D and capex intensity" and "Supply response" rows.

## How to answer
- Answer in plain text, e.g. "1.1a 1.2a 2.1a …".
- Strike any suggestion by number ("S2.4 no"), or reply "rest ok".
- Answers become decisions D-M05-1 onward.
- Every threshold below is a starting value until it is calibrated.

---

## Round 1 — Future-spend gauges by business model

### What the research says
1. **Where future spend shows up depends on the business model.**
   - **NVIDIA (fabless):**
     - Capex was $6.1B in FY2026 (MD&A; cash-flow line $6.042B) and $4.43B in the first half of FY2027.
     - Supply commitments were **$279B at 2026-07-26**, up from $119B a quarter earlier. The 10-Q says they are "primarily memory and manufacturing facilities" (S-new-M05-6, S-new-M05-7).
     - This is consistent with R9. It is one company, not a test.
   - **Meta (hyperscaler):**
     - Purchases of property and equipment were $49.11B in the first half of 2026.
     - Non-cancelable contractual commitments were **$349.31B**, which the 10-Q says "mostly relate to third-party cloud capacity arrangements".
     - Leases not yet commenced were **$278.99B**, plus about $68B of data-center leases signed in July 2026.
     - The 10-Q does not say whether the leases overlap the $349.31B (S-new-M05-8).
     - So capex alone understates Meta's committed spend several times over.
   - **Micron (fab owner):**
     - Capex was $30.71B gross in FY2026, offset by $3.32B of government-incentive proceeds.
     - Purchase obligations for property, plant and equipment were $4.18B, "substantially all" due within a year.
     - Customer cash deposits received were $12.75B, "nearly all" repayable 2029–2031 (S-new-M05-9).
     - For a fab owner, capex is still the main gauge; deposits are a demand signal on the receiving side.
2. **The legal floor for disclosure is weak.**
   - Release 33-10890 removed the tabular contractual-obligations table (former Item 303(a)(5)).
   - Item 303(b)(1) now asks the company to analyze material cash requirements from known contractual and other obligations. Item 303(b)(1)(ii)(A) includes "commitments for capital expenditures".
   - The disclosure must state the type of obligation and the time period, but no format is required.
   - Compliance has been mandatory since fiscal years ending in 2021 (S-new-M05-1). Format and completeness vary by company.
3. **Evidence that commitments lead results.**
   - Lee (2010) finds that a yearly increase in purchase obligations goes with higher future sales, earnings, asset turnover and fixed-asset growth, and that prices and analysts under-react. This is a committee-reviewed dissertation, not a journal article, and its sample predates 2021 (S-new-M05-3).
   - Order backlog predicts future earnings (S79, Rajgopal, Shevlin & Venkatachalam 2003). That is evidence about backlog, not purchase obligations.
4. **Data.**
   - Every companyfacts tag is already stored in `fact`. Only the concept map (`CONCEPTS`) lacks the purchase-obligation tags.
   - XBRL coverage in the 2025-Q4 frames (S-new-M05-10) is thin:
     - `PurchaseObligation`: 365 filers (GOOG $7.7B, MSTR $156M).
     - `UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount`: 288 filers (META $103.77B, AAPL $33.18B, NVDA $22.7B, INTC $6.7B, BA $65M).
     - TSLA, MU, MSFT, AMZN, MRVL and GFS appear in neither, so for them text is the only source.
   - Unchecked: SPCX's pre-listing XBRL and GFS's taxonomy.
   - MSTR has no capex-type future spend: its spend is bitcoin purchases funded by issuance (M04 dilution, M07).
   - ETV files N-CSR, so the module has no data for it.

### Worked example
Figures are primary as cited above. The classification is illustrative; the owner confirms it.

| Ticker | Proposed model | Leading gauge, latest value |
|---|---|---|
| NVDA | fabless | supply commitments $279B (2026-07-26) |
| META | hyperscaler | non-cancelable commitments $349.31B; leases not yet commenced $278.99B, shown separately because the overlap is not stated (2026-06-30) |
| MU | fab owner | FY2026 capex $30.71B gross, $3.32B incentives; deposits $12.75B |
| MSTR | treasury vehicle | n/a (not 0) |

### All cases
1. Fab owner: capex leads.
2. Fabless or outsourced: commitments lead.
3. Hyperscaler: own-definition capex plus leases plus commitments.
4. Long-cycle manufacturer: backlog or RPO leads.
5. Treasury vehicle, or a fund filing N-CSR: "n/a for model" or "no data", never 0.
6. Pre-revenue company: capex is read against runway (M04 survival gate).
7. A hybrid or changing model (Intel's foundry pivot, Tesla's AI compute).
8. M04's model tag not yet set: the engine proposes one, and it goes to review.
9. The lead gauge applies but no tag exists: text extraction; if nothing is found, "missing".
10. An unchecked taxonomy (SPCX, GFS): "unchecked" until probed.
11. Two lines with an unstated overlap (Meta's leases vs its commitments): shown separately, never summed.
12. Commitments signed after the period (Meta's July 2026 leases): a separate dated line.

### Suggestions
- **S1.1 Spend-channel profile.** Each company gets a spend-channel field on M04's model tag; M05 creates no new taxonomy. Primary gauges by model:

  | Model | Primary gauges |
  |---|---|
  | fab owner | capex, PP&E purchase obligations, incentives, customer deposits |
  | fabless or outsourced | purchase obligations, prepaid supply and capacity, inventory; capex as a new-offering monitor (R9) |
  | hyperscaler | own-definition capex (M02), leases not yet commenced, non-cancelable commitments, RPO |
  | long-cycle manufacturer | backlog or RPO, inventory, capex |
  | treasury vehicle | n/a; links to M04 and M07 |
  | pre-revenue | capex against runway (M04 survival gate) |

- **S1.2** The engine proposes the profile and the owner confirms it (D8). An ambiguous profile opens a `m05_model` review item.
- **S1.3** Every gauge always shows (D10). The profile only decides which gauge leads the summary line and its weight. A gauge the model makes meaningless reads "n/a for model".
- **S1.4** Commitments signed after the period are stored as their own dated line with a quote. They are never folded into the period figure.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| One gauge for every company | A capex-only reading calls NVIDIA "light" and misses Meta's lease pipeline | Spend-channel profile; all gauges visible |
| Model tag drift | A changed model (Intel, Tesla) leaves the lead gauge pointing at the wrong thing | Profile shows its confirmation date; re-proposed whenever M04's tag changes |
| Not applicable shown as 0 | MSTR and ETV read as "no spend" | "n/a for model" or "no data" label |
| Overlapping lines | Meta's leases added to its commitments double-counts them | Lines never summed while the overlap is unstated |

### Questions
**1.1 Who owns the business-model tag?**
- (a) *Recommended.* M04's owner model tag (pack 3.4), with a spend-channel field added by M05. Why: one taxonomy, confirmed once, shared by CvD and M05.
- (b) A separate M05 tag.
- (c) Owner-only, with no engine proposal.

**1.2 Leases not yet commenced**
- (a) *Recommended.* A separate future-spend line beside capex, never added to it. Why: Meta does not state whether the leases overlap its commitments, and leases are not capex.
- (b) Added to capex as committed future capex.
- (c) Left out.

---

## Round 2 — Purchase obligations and prepayments (R9)

### What the research says
1. **Tags switch, and their scope differs.**
   - NVIDIA's `us-gaap:PurchaseObligation` runs from 2020-01-26 ($0.19B) through 2023-10-29 ($21.54B) to 2025-07-27 ($45.77B), then stops.
   - The FY2026 figure, $95.2B, appears only in text: the auditor's critical audit matter and Note 12. It is "substantially all" payable through FY2027 (S-new-M05-6).
   - NVIDIA's `UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount` reads $7.6B (FY2025) → $22.7B (FY2026). It is a different subset (S-new-M05-10).
2. **The same tag can hold a different concept.**
   - Meta's `UnrecordedUnconditional…` series: $34.12B (2024-12) → $103.77B (2025-12) → $182.88B (2026-03) → $278.99B (2026-06).
   - The 2026-06 value equals the 10-Q's leases not yet commenced, not its $349.31B of commitments.
   - The FY2025 10-K also has an unexplained $12.31B point dated 2025-10-31, with no frame. The instance context still needs checking (S-new-M05-8, S-new-M05-10).
3. **Payment timing is disclosed.**
   - NVIDIA's $279B schedule: $92B in the rest of FY2027, $87B in FY2028, $88B in FY2029, $6B in FY2030, $5B in FY2031 and $1B later.
   - Cloud service agreements are a separate $29B.
   - Excess-inventory purchase obligations were $2.14B, down from $2.74B (S-new-M05-7).
4. **Commitments carry write-down risk.**
   - NVIDIA's provisions for inventory and excess-inventory purchase obligations were $7.2B in FY2026 (including the $4.5B H20 charge in the first quarter of FY2026) and $3.7B in FY2025.
   - Provision releases were $1.5B and $0.69B (S-new-M05-6).
5. **ASC 440 is not a general floor.**
   - It is reported to require disclosure only for unconditional purchase obligations that meet its scope: noncancelable, tied to financing the supplier's facilities, and a remaining term over one year. For those, the fixed and determinable portion is disclosed for each of the next five years.
   - **Unverified:** the paragraph text is login-gated, and the cited overview names only the topic (S-new-M05-2).
6. **Data.**
   - Item 7, Item 8 and 10-Q Part I text is already stored.
   - Still needed:
     - per-tag concepts (the CONCEPTS rule: "Tags within a concept must mean the same thing");
     - a text extractor in the style of `moneyflow/stated.py`.
   - Extension tags (e.g. NVIDIA's prepaid supply agreements) need the XBRL instance. `moneyflow/instance.py` today fetches only for companies with an override recipe or financing coverage below 80%.
   - NVIDIA's prepaid supply and capacity balances were not found in the parts of the filing that were read.

### Worked example
NVIDIA; primary figures. The Q4 FY2026 cost of revenue is derived as FY − 9M. Cost-of-revenue source: S-new-M05-10.

| As of | Supply and capacity commitments | TTM cost of revenue | Cover |
|---|---|---|---|
| 2026-01-25 | $95.2B (10-K CAM and Note 12) | $62.48B (FY2026) | 1.52 years |
| 2026-07-26 | $279B (10-Q) | $76.73B (15.16 + 17.03 + 20.46 + 24.08) | 3.64 years |

| Payment year | Rest of FY2027 | FY2028 | FY2029 | FY2030 | FY2031 | Later |
|---|---|---|---|---|---|---|
| $B | 92 | 87 | 88 | 6 | 5 | 1 |

- The 10-Q says the commitments are "primarily memory and manufacturing facilities". M02_BUILD_LOG records the CFO commentary as "mostly memory".
- That is the L4 hook to MU and the other memory makers.

### All cases
1. Tag present and matching the text.
2. Tag stops (NVIDIA after 2025-07-27): the value comes from text, and the gap is labelled.
3. Two tags covering different subsets (NVIDIA): kept as separate concepts.
4. One tag holding a different concept (Meta's leases): the label follows the instance context, and the tag is not trusted by name.
5. A point off the frame (Meta's $12.31B): held for review.
6. Extension tag only: instance read.
7. Text only (TSLA, MU, MSFT, AMZN, MRVL, GFS).
8. Schedule given, or not given.
9. Several categories in one note: inventory and supply, capacity, PP&E, cloud, lease not yet commenced, investment, other.
10. "Cancellable, rescheduled or adjustable" wording.
11. Excess-purchase-obligation provisions and releases.
12. The XBRL and text figures disagree.
13. A scope or definition change between periods.
14. Prepayments made to suppliers (M02 L4/K5) vs prepayments received from customers (Round 3).
15. No disclosure: missing, never 0.
16. History before 2021 (the tabular era) vs after: a series break is marked.

### Suggestions
- **S2.1** Add a `future_commitment` table:
  - `cik`, `as_of`;
  - `category` (inventory and supply, capacity, PP&E, cloud, lease not yet commenced, investment, other, unspecified);
  - `amount`, `schedule_json`;
  - `source` (XBRL tag or text quote), `grade` (A), `doc`, `offset`;
  - `scope_label` as stated;
  - `cancellable_flag`.
- **S2.2** Per-tag concepts. `PurchaseObligation` and `UnrecordedUnconditional…` are never merged. `instance.py` also fetches for companies whose lead gauge is commitments.
- **S2.3** XBRL first, text as a cross-check. A gap above the agreed threshold (question 2.4) opens `m05_commit_gap`, following the D-M02-32 pattern.
- **S2.4** `commitment_cover` = commitments ÷ TTM cost of revenue (fabless) or ÷ TTM capex (hyperscaler).
  - Shown quarter on quarter and year on year, against the company's **own** history only.
  - Labelled "hypothesis, not backtested".
- **S2.5** Paired warning `commitment_risk`: commitments ÷ cost of revenue above the company's own historical range **and** the excess-purchase-obligation provision rising quarter on quarter. It goes to M04's earnings-quality block, and M04 decides.
- **S2.6** Prepayments to suppliers stay at supply rung L4 / K5 (D-M02-41). Deposits received from customers go to Round 3.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Text commitment tables | Cancellable orders omitted, so low figures may be understated (NVIDIA: "cancelable, rescheduled, or adjustable") | Cancellable flag; amount labelled "as stated" |
| Mixed scopes | Inventory, cloud ($27B), investments ($11.4B) and other ($3.4B) in one note beside the $95.2B | Category per row; cover uses supply and capacity only |
| Same tag, other meaning | Meta's tag = leases not yet commenced | Instance context check; per-tag concepts |
| Cross-company comparison | Outsourcing levels differ (S-new-M05-3) | Own history only |
| Definition change | Growth reads as demand | Scope label diffed; change opens a review item |
| Rising commitments as demand turns | Write-down risk read as a buy signal | `commitment_risk` paired warning to M04 |

### Questions
**2.1 Order-flow matching (M02 rung L4)**
- (a) *Recommended.* M05 builds the commitment store and M02 L4 consumes it for links. Why: one store, and L4 only adds the matching.
- (b) M02 builds L4, including the store.
- (c) Defer both.

**2.2 Cover denominator**
- (a) *Recommended.* By model (cost of revenue for fabless, capex for hyperscalers), with both shown. Why: each is what the commitment substitutes for.
- (b) Revenue for everyone.
- (c) No ratio, raw amounts only.

**2.3 Cancellable commitments**
- (a) *Recommended.* Store the "cancellable / adjustable" wording as a flag beside the amount. Why: it keeps NVIDIA in, with a visible caveat.
- (b) Exclude companies that use this wording.

**2.4 XBRL vs text gap threshold**
- (a) *Recommended.* 5%. Why: text amounts are rounded ($279B, $95.2B) and grouped differently from the tags.
- (b) 1%, as in D-M02-32.

---

## Round 3 — Receiving side: RPO, backlog, deposits, ≥10% customers (A1)

### What the research says
1. **RPO in frame CY2026Q2I** (`RevenueRemainingPerformanceObligation`, 673 filers).
   - Values: MSFT $684B, BA $715.3B, GOOG $519.5B, ORCL $638B, AVGO $179.2B, CoreWeave $103.7B, TSLA $10.05B, MU $5.0B, NVDA $3.2B, MSTR $0.55B.
   - Non-calendar filers (ORCL, MU, AVGO, NVDA) report at their own quarter ends.
   - Not tagged in this frame: AMZN, META, AAPL, INTC, MRVL, GFS (S-new-M05-10).
2. **Microsoft's step change.**
   - RPO: $375B (2025-06) → $398B (2025-09) → **$631B (2025-12)** → $633B (2026-03) → $684B (2026-06).
   - That is +82% for the year against revenue +17.8%.
   - A one-quarter step of $233B suggests a concentrated contract, which only the note can confirm (S-new-M05-10).
3. **Customer deposits are not revenue.**
   - Micron received $12.75B of deposits under take-or-pay strategic customer agreements, "nearly all" repayable 2029–2031.
   - The balance sheet shows $12,895M of noncurrent customer contract liabilities.
   - Most agreements carry pricing "subject to minimum and maximum bands" (S-new-M05-9).
   - Companyconcept `ContractWithCustomerLiability` reads $13.0B at 2026-09-03, against $169M a year earlier. The difference from $12,895M is probably the current portion; check at build.
4. **Unrecognized backlog and unnamed customers.**
   - RPO can exclude contracts of one year or less (practical expedient; S79).
   - ≥10% customers are often unnamed (S77, S78).
   - NVIDIA FY2026: two direct customers were 22% and 14% of revenue, unnamed (S-new-M05-6).
   - At 2026-07-26, five direct customers held 22/14/13/11/10% of receivables (S-new-M05-7).
5. **Data.**
   - `rpo` is already a concept, and `views.rpo` shows year-on-year growth against the company's own median.
   - `ContractWithCustomerLiability` is stored in `fact` but not mapped.
   - ≥10% customers are dimensional, so they come from text or instances.
   - The M04 pack plans no customer store.
   - Amazon's AWS backlog is text-only.

### Worked example
Microsoft; primary (S-new-M05-10).

| FY end | RPO | Revenue | RPO ÷ revenue | Capex (PP&E tag) | Capex ÷ revenue |
|---|---|---|---|---|---|
| 2025-06-30 | $375B | $281.72B | 1.33 | $64.55B | 22.9% |
| 2026-06-30 | $684B | $331.84B | 2.06 | $115.95B | 34.9% |

- M02 shows Microsoft's capex on its own definition, which includes finance leases (approximate recipe), so that figure is higher.
- Micron FY2026 (primary): $12.75B of deposits received; $12,895M of noncurrent customer contract liabilities; companyconcept $13.0B vs $169M a year earlier. An RPO-only reader misses this, and a liability-only reader books it as revenue.

### All cases
1. RPO tagged.
2. RPO untagged: text, or missing.
3. Quarter ends off the calendar.
4. The share due in the next 12 months is stated, or not.
5. A step change of one quarter (Microsoft).
6. Deposits with repayment terms and price bands (Micron).
7. The contract-liability tag jumps with no deposit text found: review item.
8. Company-defined backlog vs RPO; backlog cancellations (Boeing's order book).
9. RPO excludes contracts of one year or less (expedient).
10. ≥10% customers named, unnamed, or shown only as receivables concentration.
11. Fewer than 8 quarters of RPO history.
12. A counterparty whose own financing is the real risk (D-M02-41 loops).

### Suggestions
- **S3.1** Extend M02's `views.rpo` with:
  - `rpo_cover` = RPO ÷ TTM revenue;
  - the stated 12-month share, when parsed.

  Carry both into M05's signals for every company.
- **S3.2** Add a concept `contract_liability` (its own tag) and a text finder for "customer deposits / prepayments / advance payments". It reads amount, repayment window and quote, and produces the signal `customer_deposit` (grade A). The first appearance per company opens an `m05_deposit` review item.
- **S3.3** Step-change alert: a quarter-on-quarter RPO change above the company's own threshold (question 3.3) adds a weekly-digest line with the note quote. ST: info only.
- **S3.4** Show "top customer share of revenue" beside `rpo_cover`, from the store agreed in question 3.4, computed once.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| RPO across companies | Expedients differ (S79) | Own history only |
| Multi-year RPO | Reads as near-term demand | Stated 12-month share where given |
| One counterparty | A single customer dominates; its financing is the real risk | Concentration beside cover; D-M02-41 link |
| Deposits | Read as orders despite repayment terms and price bands | Separate "repayable" line with the quote |
| Backlog | Cancellations (Boeing) | Backlog shown as stated, with any cancellation text quoted |

### Questions
**3.1 Owner of the RPO view**
- (a) *Recommended.* M05 extends M02's `rpo` view with cover and the 12-month share; the M02 theme page keeps its supplier subset. Why: one computation, with A1 placing RPO in M05.
- (b) M02 keeps the view and M05 links to it.

**3.2 Customer deposits**
- (a) *Recommended.* A separate positive-demand line labelled "repayable", never added to RPO. Why: the deposits are repayable and price-banded (Micron).
- (b) Added to RPO.
- (c) Ignored.

**3.3 RPO step-alert threshold**
- (a) *Recommended.* The company's own 90th percentile of quarter-on-quarter changes, with at least 8 quarters of history. Why: it fits every company's scale.
- (b) A fixed +25% quarter on quarter.

**3.4 Who builds the ≥10% customer store?**
- (a) *Recommended.* M05 builds a small text-parsed store (share of revenue and receivables, named or unnamed, quote), which M04 CvD reads. Why: A1 lists ≥10% customers as M05 data, and the M04 pack plans none.
- (b) M04 builds it.
- (c) No store; quotes only.

---

## Round 4 — Capex-to-revenue cycles

### What the research says
1. **Industry booms predict low returns, mainly in competitive industries.**
   - Hoberg & Phillips (2010, JF): high industry valuations, investment and financing are followed by lower cash flows and returns in competitive industries. The effect is weak and generally insignificant in concentrated ones (S-new-M05-4; this is not S109).
   - Greenwood & Hanson (2015, QJE) find the same in **dry-bulk shipping**: firms overinvest in booms because they neglect competitors' supply response. This is evidence from one industry (S-new-M05-5).
2. **A capex-only return signal is weak.**
   - Firm investment and asset growth have predicted lower returns (S71, S72).
   - Investment factors lose much of their pricing power when investment is measured with capex-type measures rather than total asset growth; most of the asset-growth signal comes from inventory and receivables growth (S73).
3. **Capex ÷ revenue alone misreads the cycle.**
   - Micron's intensity peaked at the trough (FY2023, 49.4%) and fell in a record-capex boom (FY2026, 23.1%).
   - In this example, capex ÷ D&A and capex growth track the cycle instead.
4. **Data.**
   - `capex`, `da`, `revenue` and `ppe_net` already exist in CONCEPTS.
   - Microsoft's D&A tag returned 404 under `DepreciationDepletionAndAmortization`, `DepreciationAmortizationAndOther` and `DepreciationAndAmortization`. Report the tags checked; never guess.
   - `ConstructionInProgressGross` is unchecked for the watchlist.
   - Industry aggregation can use frames, as `spenders.py` already does.

### Worked example
Micron; fiscal years end in early September; $B. Sources: companyconcept, primary (S-new-M05-10).

| FY | Capex | Revenue | D&A | Capex ÷ revenue | Capex ÷ D&A |
|---|---|---|---|---|---|
| 2018 | 8.88 | 30.39 | 4.76 | 29.2% | 1.87 |
| 2019 | 9.78 | 23.41 | 5.42 | 41.8% | 1.80 |
| 2020 | 8.22 | 21.44 | 5.65 | 38.4% | 1.46 |
| 2021 | 10.03 | 27.71 | 6.21 | 36.2% | 1.61 |
| 2022 | 12.07 | 30.76 | 7.12 | 39.2% | 1.70 |
| 2023 | 7.68 | 15.54 | 7.76 | 49.4% | 0.99 |
| 2024 | 8.39 | 25.11 | 7.78 | 33.4% | 1.08 |
| 2025 | 15.86 | 37.38 | 8.35 | 42.4% | 1.90 |
| 2026 | 30.71 | 133.19 | 9.50 | 23.1% | **3.23** |

- FY2026 capex ÷ D&A is the highest in nine years.
- The draft rule would read PEAK_RISK only if the peer wave agrees, and the "concentrated industry" note applies (R8) (*illustrative read*).

### All cases
1. At least 8 years of history, or fewer: INSUFFICIENT_HISTORY.
2. Revenue swings driven by price (memory).
3. Capex gross vs net of incentives.
4. D&A tag not found (Microsoft): tags checked are listed; missing.
5. D&A lags after a wave.
6. A capex fallback tag (M04 pack 1.2 marker).
7. An acquisition year inflates D&A through acquired intangibles (AMD 2022 includes Xilinx; M04 pack).
8. All peers file with the SEC, or key peers do not (SK hynix, Samsung).
9. A competitive vs a concentrated industry (M06 flag).
10. Off-calendar fiscal years in the industry sum.

### Suggestions
- **S4.1** Signal `capex_cycle` per company. It shows capex ÷ D&A, capex YoY, capex ÷ revenue and revenue YoY together. States:
  - **EXPANDING:** capex ÷ D&A above the company's own median and rising.
  - **PEAK_RISK:** capex ÷ D&A ≥ its own 90th percentile while industry capex is also ≥ its own 90th.
  - **CONTRACTING.**
  - **MAINTENANCE:** about 1×.
  - **INSUFFICIENT_HISTORY:** fewer than 8 years.
- **S4.2** Industry wave from M04's peer group (D19): the sum of peers' capex YoY.
  - Labelled "SEC filers only" when key peers are missing.
  - PEAK_RISK carries "concentrated industry: weaker evidence" when M06 marks an oligopoly.
- **S4.3** This block feeds M04's CvD rows ("Supply response", "R&D and capex intensity"). Nothing is computed twice.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Capex ÷ revenue | Price-driven revenue makes the trough look like a peak (Micron FY2023) | Capex ÷ D&A leads; intensity shown beside it |
| Gross vs net capex | Incentives (Micron $3.32B) or partner-funded fabs not netted in the PP&E tag | Round 6 base; gross shown beside net |
| D&A lag | Capex ÷ D&A stays high for years after a wave | Capex YoY shown beside it; states use own history |
| Concentrated industry | The Hoberg–Phillips warning is weak there | Oligopoly note on PEAK_RISK (R8, M06) |
| Missing peers | The industry wave is incomplete | "SEC filers only" label |

### Questions
**4.1 Leading cycle metric**
- (a) *Recommended.* Capex ÷ D&A against the company's own history, with intensity beside it. Why: in the Micron example it tracks the cycle, and intensity does not.
- (b) Capex ÷ revenue.
- (c) Capex YoY only.

**4.2 What PEAK_RISK does**
- (a) *Recommended.* A warning only (D16), shown in all timeframes and weighted in MY. Why: the evidence is industry-level and weak in oligopolies.
- (b) Blocks M01 tranche adds.
- (c) Info only.

**4.3 Gross or net of incentives in cycle ratios**
- (a) *Recommended.* Net where the company guides net (Micron), using the M02 recipe, with gross beside it. Why: it matches the company's own guidance.
- (b) Always gross.

---

## Round 5 — Capex as a leading signal for the company itself

### What the research says
1. **Capex plans predict actual investment, with errors** (S75: Lamont 2000; Ali, Fan & Li 2018 working paper).
   - Announcements of capex increases by industrial firms earned positive returns; utilities showed no such effect (S101, the McConnell & Muscarella entry; SOURCES.md has a duplicate S101 ID).
   - D-M02-5 counts capex as positive for the spender, "hypothesis, not backtested".
2. **The evidence on capex leading the company's own revenue is mixed** (two anecdotes, not a test; S-new-M05-10):
   - **Tesla:** capex $1.33B (2019) → $3.16B → $6.48B (2021); revenue $24.6B (2019) → $81.5B (2022).
   - **Intel:** capex ÷ revenue went 23.7% (2021) → 39.4% → 47.5% → 45.1% (2024) while revenue fell from $79.0B to $53.1B. Capex was then cut to $14.6B (2025).
   - So capex shows intent; whether it pays off needs M04's CvD and M06's moat.
3. **In-year execution can be checked before year end.**
   - Tesla guided 2026 capex at "more than $25B" (M02 store, D-M02-25) against $8.53B in 2025. First-half 2026 capex was $8.28B.
   - Micron guides "approximately $25 billion in the first six months of 2027", net of incentives, with higher spending in the second half (S-new-M05-9).
4. **Data.**
   - Guidance, freshness and the after-year-end comparison already exist (`guided.py`, `guided_vs_actual`), and quarterly own-definition actuals come from `actuals.py`.
   - Missing:
     - a year-to-date run-rate check;
     - half-year and quarter guidance periods;
     - a per-company capex guidance record over years (R19).
   - R9's new-offering monitor can reuse M02's `links.py` sentence finder with a product-word list.

### Worked example
Tesla; primary figures, guidance from the M02 store.

| 2025 capex | 2026 guide | H1 2026 actual | Needed in H2 | Read |
|---|---|---|---|---|
| $8.53B | > $25B (≥ +193%) | $8.28B (33% of the floor) | ≥ $16.72B | Needs Tesla's own first-half share history. *Illustrative read:* "behind floor pace, check freshness" |

### All cases
1. Guidance as a point, a range, a floor ("more than") or an approximation.
2. The guided period is a fiscal year, a half-year (Micron) or a quarter.
3. Guidance net vs gross.
4. At least 3 years of own seasonality history, or fewer: "insufficient history".
5. Freshness states (D-M02-30).
6. A definition change (Microsoft's 2026 lease reclassification).
7. No guidance: execution n/a.
8. Capex funded by operating cash flow vs by debt (D-M02-31).
9. CvD in STRUCTURAL_DECLINE (the Intel pattern).
10. Fabless: a capex rise with or without a quoted product sentence.
11. Year end passed: the existing guided-vs-actual comparison takes over.

### Suggestions
- **S5.1** `capex_execution` = year-to-date actual ÷ the guided period, compared with the company's own year-to-date share at the same quarter. With fewer than 3 years of history it reads "insufficient history"; no default seasonality is assumed.
- **S5.2** `guided.py` accepts half-year and quarter periods as their own labels (D-M02-28 period-label rule). This is an M02 change, logged in M02_BUILD_LOG.
- **S5.3** A capex guidance record per company (raised / held / cut, hit / miss), shared with M11's R19 ledger and not stored twice.
- **S5.4** `capex_new_offering` (R9): a capex rise ≥ the company's own 75th percentile YoY plus a quoted product sentence, as an `m05_offering` review item (grade C until confirmed).
- **S5.5** Every positive capex reading is shown with M04's CvD state and the D-M02-5 funding line. The engine never scores it alone.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Run-rate | Spenders that are heavy in the fourth quarter look behind plan at mid-year | Own seasonal share; "insufficient history" otherwise |
| Floors ("more than") | A "behind" call is one-sided | Floor shown; the read says "floor pace" |
| Definition change | Reads as a miss (Microsoft's leases) | Definition change flag from M02 |
| Debt-funded capex | Reads as conviction | D-M02-31 funding line beside it |
| Failed product | Intel-type capex still reads as positive | CvD state shown beside it; question 5.2 |

### Questions
**5.1 Run-rate check**
- (a) *Recommended.* A warning when the year-to-date share is below the company's own 10th percentile at that quarter. Why: it respects each company's seasonality.
- (b) A fixed threshold (e.g. below 40% at mid-year).
- (c) No in-year check.

**5.2 D-M02-5 weighting for the spender**
- (a) *Recommended.* Positive only when CvD is not STRUCTURAL_DECLINE and capex is funded by operating cash flow; otherwise neutral, with a warning. Why: Intel spent heavily into falling revenue.
- (b) Always positive (as today).
- (c) Revisit after a backtest.

**5.3 R9 new-offering monitor**
- (a) *Recommended.* Fabless and outsourced models only. Why: R9 scopes it that way.
- (b) All models.

---

## Round 6 — Capex base and split, coordinated with M04 (A2)

### What the research says
1. **The A2 ladder sits in M04_FINANCIALS:** disclosed → project-level → Greenwald (default) → D&A.
   - Disclosed splits appear mainly in MLP filings (S25). Greenwald's method: S13.
   - The M04 pack has no split item yet; `capex_maint` is proposed here.
2. **Greenwald fails in price-driven booms.** It treats revenue growth as capacity growth, so for Micron FY2026 growth capex comes out above total capex and maintenance turns negative.
3. **The capex base must be one number.**
   - M02's own-definition actuals (Meta includes finance-lease principal; Amazon uses cash capex net of incentives) differ from the raw PP&E tag.
   - Micron guides net of incentives, but `actuals.recipe_for` has no incentive rule, so Micron falls back to "clause not mapped" with gross PP&E.
   - Only AMZN has an override in `config/capex_definitions.toml`.
   - Micron's incentive-proceeds tag is not identified; it is probably an extension (instance read).

### Worked example
Micron FY2026. The method is illustrative; inputs are primary.
- PP&E plus finance-lease right-of-use assets, net, at each fiscal year end FY2022–26: 38.55 / 37.93 / 39.75 / 46.59 / 63.31 $B. The engine's `ppe_net` reads `PropertyPlantAndEquipmentNet` instead.

| Step | Value |
|---|---|
| Greenwald average PP&E ÷ sales, FY2022–25 | (1.253 + 2.441 + 1.583 + 1.246) ÷ 4 = 1.631 |
| Growth capex = 1.631 × ΔSales $95.81B | $156.3B, above total capex of $30.71B: method not meaningful |
| D&A proxy | maintenance $9.50B, growth $21.21B (69%) |
| Net of incentives | base $27.39B, growth $17.89B |

### All cases
1. Split disclosed (MLPs).
2. Project-level split.
3. Greenwald meaningful.
4. Greenwald gives growth above total or below zero: next rung, with the reason shown.
5. D&A proxy.
6. Incentives netted per the company's guidance, or no recipe rule.
7. Own-definition actual exact vs approximate (M02 labels).
8. Fallback capex tag.
9. Which PP&E tag feeds Greenwald (with or without finance-lease right-of-use assets).

### Suggestions
- **S6.1 One base.** M02's `actual_for` is the capex base for M04 and M05. M04's `capex_maint` reads it, and M05 reads `capex_maint`.
- **S6.2** `growth_capex` = base − maintenance, carrying both method tags. If Greenwald gives a result above the total or below zero, mark it "method not meaningful" (the D-SRCH-15 pattern) and fall to the next rung.
- **S6.3** Add an incentive rule to M02's recipe table: "net of … incentives" → PP&E − incentive-proceeds tag. Micron stays in the override file until the tag is confirmed. This is an M02 change, logged in M02_BUILD_LOG.
- **S6.4** M05 shows growth share (growth ÷ base) against the company's own history. It is used in Round 5 and in M04's CvD intensity row.

### Failure modes (rows to add)
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Two capex definitions | M02 actual − M04 maintenance mixes definitions | One base (S6.1) |
| Greenwald | Negative or above total, silently clamped | "Method not meaningful"; next rung shown |
| D&A proxy | Understates maintenance when asset lives shorten; overstates it after a wave | Method tag; growth share against own history |
| Incentives | Double-counted or ignored | Recipe rule plus override; gross shown beside net |

### Questions
**6.1 Capex base**
- (a) *Recommended.* M02's own-definition actual for both M04 and M05. Why: one number on the page.
- (b) The raw PP&E tag in M04, own-definition in M05.

**6.2 Default rung when Greenwald is not meaningful**
- (a) *Recommended.* The D&A proxy, labelled. Why: it always exists, and its bias is known.
- (b) Missing.
- (c) The owner enters a figure in review.

**6.3 Micron incentive netting**
- (a) *Recommended.* Add the recipe rule in M02 now and override Micron until the tag is confirmed. Why: Micron guides net.
- (b) Show gross with a note.

---

## Signals out
Each signal is a D13 record:
- `module_id` = M05; grade A unless noted;
- `source_ref` = accession plus quote offset;
- `method` names the tag or recipe;
- every signal is labelled "hypothesis, not backtested" until calibrated.

All signals are visible in MY, PT and ST; weights follow the profile (D10).

| Signal | Type | MY | PT | ST |
|---|---|---|---|---|
| `commitment_cover` | years or ratio, against own history | high | medium | info; event alert on a step change |
| `commitment_risk` | warning, sent to M04 | high | high | info |
| `rpo_cover` | ratio, against own history | high | medium | info |
| `customer_deposit` | event; amount and repayment window | high | medium | info |
| `rpo_step` | event (digest line) | medium | medium | info |
| `capex_cycle` | EXPANDING / PEAK_RISK / CONTRACTING / MAINTENANCE / INSUFFICIENT_HISTORY | high | medium | info |
| `capex_execution` | year-to-date share against own history | medium | high | info |
| `growth_capex` | $ and share, method-tagged | high | low | info |
| `capex_new_offering` | review item, grade C until confirmed | medium | low | info |

## Build parts (proposal)
- Each part is one conversation at Medium effort, on branch `m05-partN`.
- Each part updates the M05 module doc (and M02_BUILD_LOG or DATA_SOURCES where touched) in the same commit and ships fixture tests.
- One live check per part: the owner runs `uv run python scripts/run_live.py <label>`, a few minutes, and sends the log. Claude cannot call SEC.
- No new packages are expected.

| Part | Contents | Depends on | Live check |
|---|---|---|---|
| 1 Profile and commitment store | Spend-channel field and `m05_model` (1.1); per-tag concepts; `future_commitment`; text extractor; extended instance fetch list; `m05_commit_gap` (2.4); cancellable flag | M04 part 1; M04 part 2 for the model tag | Instances for NVDA, META, MU (extension tags, Meta's tag context); extraction report over stored text for the watchlist |
| 2 Commitment signals | `commitment_cover` (2.2); `commitment_risk` to M04; schedule view; L4 hand-off (2.1) | 1 | Cover and risk report; NVDA and META schedules compared with their 10-Qs |
| 3 Receiving side | `rpo_cover` and 12-month share (3.1); `contract_liability`; deposit finder (3.2); step alert (3.3); customer store (3.4) | 1 | Receiving-side report; Micron deposits; AWS backlog text check |
| 4 Capex cycle | `capex_cycle` (4.1, 4.2); industry wave; CvD feed; D&A and construction-in-progress probes | M04 part 2 (peers) | Companyconcept probe of D&A and construction-in-progress tags for the watchlist (≤ 8 requests/s); Micron FY2018–26 printout |
| 5 Base and split | Incentive rule in M02 plus Micron override (4.3, 6.3); `growth_capex` (6.1, 6.2) | M04 split item | Micron instance read for the incentive tag; base and split printout |
| 6 Execution and new offerings | Half-year and quarter periods in `guided.py`; `capex_execution` (5.1); guidance record shared with R19; D-M02-5 weighting (5.2); `capex_new_offering` (5.3) | 5 | Execution report over stored guidance (TSLA, MU) |
| 7 Assembly | M05 section on the company page; digest lines; signal writes; calibration notes | 1–6 | UI check on scratch data (port 8799) after one refresh run |

## Known gaps
- Meta:
  - its tag context (leases vs commitments);
  - the $12.31B point dated 2025-10-31;
  - whether the leases overlap the $349.31B of commitments.
- NVIDIA's prepaid supply balances, and its purchase-obligation tag after 2025-07.
- Micron:
  - its incentive-proceeds tag;
  - its contract liability: $13.0B in companyconcept vs $12,895M noncurrent on the balance sheet.
- Amazon's AWS backlog wording; Microsoft's D&A tag; construction-in-progress coverage.
- SPCX and GFS taxonomies are unchecked. MSTR is n/a; ETV has no data (N-CSR).
- Who builds the customer store (question 3.4).
- ASC 440 scope and disclosure text: unverified, login-gated.
- Sources not used:
  - Arif & Lee (2014) was not verified and is not cited;
  - no journal version of Lee (2010) was found.
- Every threshold is uncalibrated, and every signal is "hypothesis, not backtested".

## New sources
These are provisional IDs. They are numbered after the M04 pack's new sources (S122 onward) when added to SOURCES.md, which also needs its duplicate S101 fixed. "Other" marks sources that are not peer-reviewed or are secondary.

- **S-new-M05-1** 17 CFR 229.303 (Regulation S-K Item 303, MD&A) (primary): https://www.law.cornell.edu/cfr/text/17/229.303 · Cleary Gottlieb summary of SEC Release 33-10890 (other): https://www.clearygottlieb.com/news-and-insights/publication-listing/sec-adopts-major-changes-to-mda-and-related-requirements
- **S-new-M05-2** Deloitte DART, ASC 440 Commitments overview (other; it does not state the disclosure rules): https://dart.deloitte.com/USDART/home/codification/liabilities/asc440
- **S-new-M05-3** Kwang June Lee (2010), "Purchase Obligations, Earnings Persistence and Stock Returns", PhD dissertation, UC Berkeley (committee-reviewed; not a journal article): https://escholarship.org/uc/item/74w2x17f
- **S-new-M05-4** Hoberg, G. & Phillips, G. (2010), "Real and Financial Industry Booms and Busts", Journal of Finance 65(1), 45–86: https://ideas.repec.org/a/bla/jfinan/v65y2010i1p45-86.html
- **S-new-M05-5** Greenwood, R. & Hanson, S. G. (2015), "Waves in Ship Prices and Investment", Quarterly Journal of Economics 130(1), 55–109: https://ideas.repec.org/a/oup/qjecon/v130y2015i1p55-109.html
- **S-new-M05-6** NVIDIA FY2026 Form 10-K (primary): https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021/nvda-20260125.htm (Note 12 is also at R21.htm in the same folder)
- **S-new-M05-7** NVIDIA Q2 FY2027 Form 10-Q (primary): https://www.sec.gov/Archives/edgar/data/1045810/000104581026000075/nvda-20260726.htm
- **S-new-M05-8** Meta Platforms Q2 2026 Form 10-Q (primary): https://www.sec.gov/Archives/edgar/data/1326801/000162828026050705/meta-20260630.htm
- **S-new-M05-9** Micron Technology FY2026 Form 10-K (primary): https://www.sec.gov/Archives/edgar/data/723125/000072312526000023/mu-20260903.htm
- **S-new-M05-10** SEC XBRL companyconcept and frames checks of 2026-10-12 (primary). Pattern: `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/<Tag>.json`.
  - Frames:
    - https://data.sec.gov/api/xbrl/frames/us-gaap/PurchaseObligation/USD/CY2025Q4I.json
    - https://data.sec.gov/api/xbrl/frames/us-gaap/UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount/USD/CY2025Q4I.json
    - https://data.sec.gov/api/xbrl/frames/us-gaap/RevenueRemainingPerformanceObligation/USD/CY2026Q2I.json
  - NVIDIA:
    - https://data.sec.gov/api/xbrl/companyconcept/CIK0001045810/us-gaap/PurchaseObligation.json
    - https://data.sec.gov/api/xbrl/companyconcept/CIK0001045810/us-gaap/CostOfRevenue.json
  - Meta: https://data.sec.gov/api/xbrl/companyconcept/CIK0001326801/us-gaap/UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount.json
  - Microsoft: https://data.sec.gov/api/xbrl/companyconcept/CIK0000789019/us-gaap/RevenueRemainingPerformanceObligation.json
  - Micron:
    - https://data.sec.gov/api/xbrl/companyconcept/CIK0000723125/us-gaap/PaymentsToAcquirePropertyPlantAndEquipment.json
    - https://data.sec.gov/api/xbrl/companyconcept/CIK0000723125/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json
    - https://data.sec.gov/api/xbrl/companyconcept/CIK0000723125/us-gaap/DepreciationDepletionAndAmortization.json
    - https://data.sec.gov/api/xbrl/companyconcept/CIK0000723125/us-gaap/PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization.json
  - Tesla: https://data.sec.gov/api/xbrl/companyconcept/CIK0001318605/us-gaap/PaymentsToAcquirePropertyPlantAndEquipment.json
  - Intel: https://data.sec.gov/api/xbrl/companyconcept/CIK0000050863/us-gaap/PaymentsToAcquirePropertyPlantAndEquipment.json
