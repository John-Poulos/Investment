# M03 — Design review pack (draft for the owner)

**Status:** research only — nothing is decided until the owner answers (D7); 2026-10-12 · **Effort:** High for this review; Medium for each build part.

Outputs are research signals, not financial advice.

## Purpose and dependencies
**The question M03 answers.** Which company leads each category the owner follows? Where does each revenue curve sit on its S-curve? How often has a lead like this lasted in the past?

**Approved revisions it must honour**
- **R6:** two S-curve types. (A) A young company on its first curve. (B) An established company with a new curve, tracked through segment data.
- **R14:** Bessembinder is stated as dollar wealth creation above T-bills, never as a claim about returns.
- **D8:** ambiguous classifications go to the review queue.
- **D9:** every indicator has failure-mode rows.
- **D10:** every signal is visible in every profile.
- **D13:** the signal record shape. **D14:** evidence grades.
- **D16:** warnings only.
- **D19 / R24:** peers, including companies that do not file with the SEC.
- **D-M02-3:** components are shown side by side, with no blended score until it has been backtested.
- **Also touched:** R8 (HBM is a three-supplier oligopoly), R10 (AMD–Google stays grade C), A3 and R21 (M06), R4, R19 and R23 (M11), and M01 rules 2, 3 and 6.

**Depends on (not redesigned here)**
| Module | What M03 reads | State |
|---|---|---|
| M01 | MY/PT/ST profiles, the weights row, rules 2, 3 and 6 (D12, D10) | Doc only |
| M02 | `theme`, `theme_company`, `theme_breadth`, tracked tier `tier_member`, spenders' capex guidance (D-M02-5), review plumbing `propose()` (D-M02-18) | Built |
| M04 pack | `lifecycle_stage` (Dickinson, S-new-56; question 5.1); CvD and the survival gate; part 7 segment and product axes (question 5.4, watchlist only) and `unit_metric` (DS2); peer tolerance (1.4); small-sample peer statistics (6.2); first `signal` writer (S1.5) | Draft; owner has not answered |
| M06 | Moat duration (A3), challenger rung (R21) | No doc |
| M11 | Milestones (R4), guidance ledger (R19), caps (R23) | No doc |

Wherever an M04 output does not exist yet, M03 shows "pending M04" and never assumes the gate passed.

## How this review runs
- **Order.** One round per section. Round 1 (segment data) comes first because Rounds 2 and 3 read its output.
- **Each round contains:**
  - what the research says;
  - a worked example (real figures; invented rows are marked illustrative);
  - all the cases the rule must handle;
  - suggestions (S1.1, …);
  - failure-mode rows;
  - questions.
- **How to answer.** Plain text, e.g. "1.1a 1.2a 1.3a".
  - Strike a suggestion by number ("S2.4 no"), or reply "rest ok".
  - Answers become D-M03-1 onward.
  - Every threshold is a starting value until calibration (question 3.3).
- **Source IDs.** S-numbers come from SOURCES.md. Provisional IDs (S-new-M03-n) are listed under "New sources".

---

## Round 1 — Segment and product data (the type-B input)

### What the research says
1. **Companyfacts carries no dimensional facts (S41).** `moneyflow/instance.py` already reads the filing instance but drops dimensional contexts (lines 87–90).
2. **The SEC Financial Statement and Notes (FSN) data sets** (S-new-M03-15; readme S40):
   - They include the notes. The DIM table encodes each context as `"{axis}={member};"`.
   - Coverage starts with submissions from 2009-04-15. Values are as filed and are not corrected later.
   - Published monthly since November 2020 (quarterly before). Recent zips are about 53–298 MB (2026_05 to 2026_09).
3. **ASU 2023-07** (S-new-M03-16, other; same standard as M04's S-new-60):
   - Requires significant segment expenses, including for single-segment filers.
   - Applies to fiscal years beginning after 2023-12-15 (interim periods a year later), so segment cost detail is richer from FY2024.
4. **Segment detail is a management choice.**
   - SFAS 131 increased disaggregation and exposed information that had been hidden (Berger & Hann 2003, S-new-M03-14).
   - Aggregation choices are linked to proprietary and agency costs (Berger & Hann 2007; abstract not read).
5. **Recasts break series.**
   - Micron reorganized into CMBU, CDBU, MCBU and AEBU in Q4 FY2025 and retrospectively adjusted all prior-period segment amounts (S-new-M03-25).
   - Intel created the Intel Foundry segment in 2024 and recast 2021–2023 (S-new-M03-24).
6. **Feasibility.**
   - **Option 1.** M04 part 7 plans an instance reader for segment, product and geography axes, for the watchlist only, reusing the D-M02-32 path. Extending it to the tracked tier would be an M03 addition. My own estimate (not in the M04 pack): 16 companies × 4 filings × 3 years ≈ 190 instances, under a minute at 5 requests/s.
   - **Option 2.** FSN monthly zips for peers and history. One request per month, but 50–300 MB each; keep only tracked CIKs on load.
   - The first-reported vs latest store pattern (D-SEC-8) already handles recasts.
   - **Gaps:**
     - company extension members (custom axis members);
     - 20-F filers such as GFS (US GAAP or IFRS not checked);
     - INFQ's SPAC CIK mixes shell and operating facts. FY2025 operating cash flow is −$2.27M in the 10-K filed 2026-03-31 (the shell's) and −$24.1M in the 10-Q filed 2026-08-18 (S-new-M03-26).

### Worked example — Intel Foundry (S-new-M03-24, primary; $M)
| Intel Foundry | 2022 | 2023 | Change |
|---|---|---|---|
| Total segment revenue | 27,491 | 18,910 | −31% |
| External revenue | 474 | 953 | +101% |
| External share of total | 1.7% | 5.0% | |
| Operating loss | (5,169) | (6,955) | |

- **On total revenue** the curve reads "large, declining".
- **On external revenue** it reads "emerging" (about 1.8% of Intel's revenue).
- **Under answer 1.3a**, M03 reports: emerging, a −$7.0B operating loss beside it, and the flag "95% captive".
- **Micron (illustrative rows):**
  - CMBU for FY2024 as first reported is missing, because the unit did not exist yet.
  - The recast FY2024 value in the FY2025 10-K is $Y.
  - The chart shows the recast line, a dotted marker at the Q4 FY2025 reorganization, and the note "pre-recast values not comparable".

### All cases
1. A reportable segment (ASC 280) that is the curve (AWS).
2. A revenue breakdown by market or product (ASC 606) that is not a reportable segment. NVDA's "Data Center" is likely one (check at build).
3. A single-segment filer: the company is the curve. ASU 2023-07 expense lines exist from FY2024 only.
4. A product line named only in the text (MD&A) and not tagged: "not disclosed as a fact", with text search as a fallback.
5. A company extension member: the owner maps it.
6. A segment created later with recast history (Intel Foundry): the recast series is kept; the first-reported values before the segment existed are missing.
7. A reorganization that recasts every prior segment (Micron Q4 FY2025).
8. A segment merged, renamed or discontinued: the series ends and the break is marked.
9. Intersegment revenue disclosed: use external revenue. Not disclosed: use the total, flagged "external unknown".
10. A geography-only axis: not a curve.
11. 10-Q three-month vs year-to-date contexts. Where only those exist, Q4 = FY minus the nine-month value (check at build).
12. A 20-F or IFRS filer (GFS).
13. A SPAC or reverse-merger CIK (INFQ): reporting-basis change.
14. Periods before XBRL (2009–2011): "insufficient history".
15. A peer outside the watchlist and tracked tier: FSN (later) or missing.
16. An FSN as-filed value later corrected: for the watchlist the instance value wins; FSN-only peers carry an "as filed" flag.
17. Funds and treasury-asset models (ETV, MSTR's bitcoin): no curve.

### Suggestions
- **S1.1 One shared table.** `segment_fact(cik, accession, axis, member, concept, period, value, first_filed, latest_filed, is_external)`, built in M04 part 7 and read by M03. M03 does not fetch instances separately.
- **S1.2 Curve map.** `curve_map(ticker, axis, member, theme_id, curve_label, owner_confirmed)`. The engine proposes mappings from member names through M02's `propose()`, and the owner confirms them (D8).
- **S1.3 Recast detector.** The same (axis, member, period) with a changed value in a later filing raises `series_break` and a review item. Growth is computed only within one definition.
- **S1.4 Reporting-basis detector** for SPAC and reverse-merger CIKs. The same period with very different values across filings goes to review, and the owner sets the series start.
- **S1.5 FSN loader, later and for peers only.** One monthly download (safe for the rate limit); keep only rows for tracked CIKs; cross-check against instances for the watchlist.
- **S1.6 Register.** Dimensional facts are one shared entry with the M04 pack's proposed DS12; M03 adds the tracked tier to it.

### Failure modes (rows to add)
| Input | How it can mislead | Guard |
|---|---|---|
| Segment recast | Growth across the break compares different scopes | Keep first-reported and recast series; mark the break; compute growth within one definition only |
| Intersegment revenue | Captive volume reads as an external curve | Stage on external revenue when disclosed; flag segments under 50% external |
| Revenue breakdown vs ASC 280 segment | A market platform is not a reportable segment | Store the axis name; owner maps the line to the curve |
| Aggregation choices | A curve or a loss is hidden (S-new-M03-14) | "No segment" means "not disclosed", never zero; text search fallback |
| SPAC or reverse-merger CIK | Shell history under the same CIK | Basis-change detector; owner sets the series start |
| FSN as-filed values | Errors are never corrected | Cross-check against instances for the watchlist; FSN for peers only |

### Questions
**1.1 Segment source**
- (a) *Recommended.* The M04 part-7 instance reader for the watchlist, extended to the tracked tier by M03; FSN later for peers. Why: one point-in-time fetch path, about 190 instances.
- (b) FSN only.
- (c) EdgarTools as the parser (still under evaluation, an M00 open item).

**1.2 Recasts**
- (a) *Recommended.* Keep both series, chart the recast and mark the break. Why: growth across a break compares different scopes.
- (b) Latest values only.

**1.3 Intersegment revenue**
- (a) *Recommended.* Stage on external revenue when disclosed and flag segments under 50% external. Why: Intel Foundry reads emerging on external revenue but declining on total.
- (b) Total segment revenue.

---

## Round 2 — Category leaders

### What the research says
1. **Pioneers are not usually the winners** (Golder & Tellis 1993, S-new-M03-5; about 500 brands in 50 categories; full text read).
   - 47% of pioneers failed (17 of the 36 categories with failure data).
   - Pioneers' mean share was 10%; 19% for the pioneers that survived.
   - Early leaders (the share leader in the early growth phase) failed only 8% of the time, held a 28% mean share and led in more than half the categories.
   - Early leaders entered on average 13 years after the pioneer (5 years for post-WWII categories).
   - Caveat: early leaders were identified with hindsight, so 8% is not an ex-ante probability.
2. **Shakeouts end in oligopoly** (Klepper 1996, S-new-M03-6; abstract and summaries only). In technology-driven industries, early entry and scale make R&D pay better. The number of firms rises, then falls, so leaders tend to be set by the end of the growth phase.
3. **Sales are concentrating in a few highly productive firms with high markups** (Autor et al. 2020, S-new-M03-17).
4. **Text-based industries track product markets better than SIC codes** (Hoberg & Phillips, S109). M02 themes already cross SIC codes (LESSONS: value chains span related industries).
5. **Key competitors often do not file with the SEC** (SK hynix, Samsung, TSMC). Share leadership then rests on grade-B data: Counterpoint HBM shares (S06) and Mercury x86 shares (S36).
6. **Stored today:**
   - company revenue, gross profit and operating income, as Q, FY and TTM (`series`, `sec/xbrl_facts.py`);
   - peer robust z and own-series YoY (`frames.py`, D-SEC-9);
   - `theme_company`, `theme_breadth`, `tier_member`.

   **Gaps:**
   - the revenue that belongs to a theme sits at segment level (Round 1);
   - market-size denominators are paid or excluded by their terms (Gartner, IDC, TrendForce; S93);
   - there is no store for third-party shares;
   - SIC peer discovery is still open (M04 question 1.3).

### Worked example — "cloud" leadership, 2025
| Company / unit | 2025 revenue | YoY | Source |
|---|---|---|---|
| AMZN – AWS segment | $128,725M | +19.7% (release: 20%) | S-new-M03-20 (primary, checked) |
| GOOG – Google Cloud | missing (not fetched this round) | missing | — |
| MSFT – Azure | no segment dollar figure; growth % only | missing | check at build |

- The display reads "1 of 1 with data; 2 missing". No ranking is built with zeros.
- *Illustrative:* if Google Cloud were $X, growing 1.5 robust-z above the peer median, the growth component would read "gaining" while the dollar component reads "AWS leads". These are two signals, not a blend.

### All cases
1. A pure-play SEC filer, where the company is the curve.
2. A conglomerate with an owner-mapped segment (AWS).
3. Growth % disclosed but no dollars (Azure): growth component only; rank missing.
4. A theme company with no mapped segment: "exposure unknown", not ranked.
5. One segment mapped to two themes: counted in both, overlap flagged (feeds R23).
6. The leader or a key peer does not file with the SEC: a grade-B observation, or the rank is labelled "among SEC filers".
7. Two vendors' shares disagree: both are shown with date and source.
8. Too few companies with data: "k of n with data" and no z (M04 small-sample rule, question 6.2).
9. Off-calendar fiscal years (NVDA's ends in January): M04 offset tolerance (question 1.4).
10. An acquisition year (AMD 2022 includes Xilinx): flagged.
11. A small segment against the theme total: dollars shown beside the share; `not_meaningful` below an owner-set floor.
12. A recast in a peer's segment: growth only within one definition.
13. The owner rejects a proposed mapping: it stays unmapped and is not proposed again (`propose()` suppresses repeats).
14. Pioneer vs early leader: the entry date is shown, never scored.
15. A grade-C claim (AMD–Google ASIC, R10): never feeds the rank.

### Suggestions
- **S2.1 Category** = an M02 theme plus owner-confirmed segment or product mappings (S1.2). Example: AWS → "AI infrastructure".
- **S2.2 Leadership as four components side by side** (D-M02-3), with no single score:
  - (a) dollar rank on mapped revenue (grade A);
  - (b) growth gap to the theme median, as a robust z (`frames.py`);
  - (c) gross or segment margin gap;
  - (d) third-party share (grade B).
- **S2.3 Pioneer and early-leader tags** come from first-disclosure dates (the first filing that shows the segment). They are context only.
- **S2.4 `market_share_obs`** with source URL, source date, grade B and who entered it, plus an owner entry form. Companies that do not file with the SEC are stored by name. Confirmations go through M02's review queue.

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| Company revenue rank within a theme | Most of MSFT/AMZN/GOOG revenue is not the theme | Rank on owner-mapped segment revenue; otherwise "exposure unknown" |
| "First mover" label | Pioneers fail 47% of the time (S-new-M03-5) | Leader = share leader in the growth phase; entry date shown, not scored |
| Third-party share | Vendor methods differ; revisions; paywalled excerpts | Grade B with URL and date; owner confirms; never mixed silently with the grade-A rank |
| Missing non-SEC peers | NVDA looks dominant against SEC peers only; MU's HBM rank is wrong without SK hynix and Samsung | Peer list flagged `incomplete` with the missing names; rank shown "among SEC filers" |
| Small segment ÷ theme total | Swings when the base is small | Dollars beside the share; `not_meaningful` below the floor (LESSONS) |

### Questions
**2.1 What is a category?**
- (a) *Recommended.* An M02 theme plus owner-mapped segments. Why: it matches how M02 already groups companies, and SIC codes split value chains.
- (b) 4-digit SIC.
- (c) Hoberg-Phillips text-based industries (data-library terms not checked).

**2.2 Minimum evidence for "leader"**
- (a) *Recommended.* Grade-A mapped-revenue rank plus the growth gap, with third-party share as a grade-B overlay. Why: it stays on filings but still shows competitors that do not file with the SEC.
- (b) Third-party share required.
- (c) Revenue rank only.

**2.3 Non-SEC competitors**
- (a) *Recommended.* The owner enters annual figures with a source, grade B. Why: without SK hynix and Samsung, MU's HBM rank is wrong.
- (b) Exclude them and mark the rank "SEC filers only".

---

## Round 3 — S-curve stage and type (R6)

### What the research says
1. **The logistic shape** (Fisher & Pry 1971, S-new-M03-13; abstract only).
   - On a logistic curve the growth rate falls from the start, and the yearly dollar increment peaks at the inflection (half of the ceiling K). This property is my derivation from the logistic form, not a cited result.
   - So deceleration alone does not mean maturity, but a peak in the increment marks the inflection.
   - A rising growth rate cannot occur on a single pure logistic. The `accelerating` stage therefore flags an early phase, a second curve stacked on the first, or noise.
2. **The ceiling cannot be estimated before the inflection.**
   - Van den Bulte & Lilien 1997 (S-new-M03-11; abstract): Bass-model estimates are biased (roughly 20–30% in their simulations) and drift as data are added. Across 12 innovations, a 10% rise in observed penetration goes with about +5% estimated market size, −10% imitation coefficient and +15% innovation coefficient. More flexible models drift more, not less.
   - Modis 1994 (S-new-M03-12; journal record to verify): you need at least half of the curve and better than 10% precision per point before the ceiling is within 20% at 90% confidence.
3. **Sales growth persists more than earnings growth** (Chan, Karceski & Lakonishok 2003, "CKL", S-new-M03-4; tables read; US data 1951–1998).
   - Five straight years of above-median sales growth: 6.3% of firms vs 3.1% by chance. Ten years: 0.9% vs 0.1%.
   - Operating income before depreciation, five years: 3.6% vs 3.1%. Income before extraordinary items: 3.0% vs 3.1%, i.e. chance.
   - About 10% of firms grow faster than 18% a year over 10 years.
   - Technology firms: sales and operating income persist strongly; income before extraordinary items barely does (4.1% vs 3.1%).
   - So stage runs on revenue or units, and profit is judged separately.
4. **Incumbents starve curves that first serve new markets** (Christensen & Bower 1996, S-new-M03-10; summaries only). Type-B evidence therefore needs dollars committed and external revenue, not announcements.
5. **The firm-level stage belongs to M04** (`lifecycle_stage`, S-new-56). M03's stage is per curve.
6. **Adoption across firms.** Bloom et al. (S108) track technology bigrams across earnings calls; the ≥10× rise to peak is their selection rule, not their adoption measure. M02's `theme_breadth` is the filing-based analogue. HBM 10-K filer counts for 2019–2025 were 4, 5, 6, 4, 6, 10 and 12 (engine data, D-SEC-14). HBM is a component oligopoly (R8), so filer counts are not adoption there.
7. **Data.**
   - Type A: company `series`, `rpo` where it is tagged, 8-K KPIs (DS2, stored but not parsed).
   - Type B: Round 1. Units: M04's `unit_metric`.
   - Gaps: the ceiling K (paid sources) and segment history before XBRL.

### Worked example (real figures)
**NVDA Data Center** (S-new-M03-21/22/23, primary 8-K releases)

| FY | Revenue | Growth | Dollar increment | Share of company |
|---|---|---|---|---|
| 2023 | ≈ $15.0B (derived: 47.5 ÷ 3.17) | — | — | — |
| 2024 | $47.5B | +217% | +32.5 | 78% of $60.9B |
| 2025 | $115.2B | +142% | +67.7 | 88% of $130.5B |
| 2026 | $193.7B | +68% | +78.5 | 90% of $215.9B |

- Growth falls, but the increment is still rising, so the stage reads **steep**, and K is not identified.
- Type: Data Center is about 90% of revenue, which passes the ≥50% share test for type A. But if M04 reads NVDA's cash-flow stage as mature, it fails the intro/growth condition, so it stays unassigned until the owner decides (question 3.2).

**AMZN AWS** (S-new-M03-19/20, primary)

| Year | Revenue ($M) | Growth | Increment |
|---|---|---|---|
| 2013 | 3,108 | — | — |
| 2014 | 4,644 | +49% | +1.5B (derived) |
| 2015 | 7,880 | +70% | +3.2B (derived) |
| 2021 | 62,202 | — | — |
| 2022 | 80,096 | +28.8% | +17.9B |
| 2023 | 90,757 | +13.3% | +10.7B |
| 2024 | 107,556 | +18.5% | +16.8B |
| 2025 | 128,725 | +19.7% | +21.2B |

- In 2023 the increment fell below its 2022 peak for one year only, so AWS is not `past_inflection`.
- In 2024–25 both the increment and the growth rate rise, so it reads `accelerating`. That goes to review: "new curve or cycle?"
- AWS was 18.0% of AMZN's 2025 revenue ($716,924M), so it is type B.

**INFQ Infleqtion**, type A candidate (S-new-M03-26; percentages from unrounded values)

| Period | Revenue | Change |
|---|---|---|
| FY2024 → FY2025 | $28.1M → $31.1M | +10.7% |
| H1 2025 → H1 2026 | $13.5M → $23.4M | +74% |
| Q2 2025 → Q2 2026 | $5.3M → $13.5M | +157% |
| Q1 2025 → Q1 2026 | $8.2M (derived) → $9.9M | +21% |

- The quarters are lumpy, and the latest full-year growth (+10.7%) is below the 40% `emerging` threshold.
- The TTM to Q2 2026 has no year-earlier comparison, because H1 2024 is not tagged.
- So the stage reads **not_identified** until two consecutive TTM readings exist and agree.

### All cases
1. Increment rising, growth falling: `steep` (NVDA Data Center).
2. Increment and growth both rising: `accelerating`, sent to review (AWS 2024–25).
3. Increment below its peak for ≥ 2 years: `past_inflection`; a K fit is allowed.
4. A single-year dip in the increment (AWS 2023): no stage change.
5. TTM below its prior peak for ≥ 4 quarters: `declining`. During CYCLICAL_TROUGH it is held for review.
6. Lumpy quarters (INFQ): TTM with the quarters shown; two consecutive readings required.
7. Too few readings, or a new segment: `not_identified`.
8. A recast inside the window: computed within one definition (Round 1).
9. A captive segment: staged on external revenue (question 1.3).
10. Units but no dollars (Tesla storage GWh): staged on units, labelled as units.
11. Price-driven revenue swings (the memory cycle): read beside M04 CvD; units where available.
12. A jump from an acquisition: flagged; not a stage change on its own.
13. The company is the curve but the firm is mature (NVDA): type unassigned until the owner decides.
14. Type A has no "other segments": the `maturing` test does not apply; only `past_inflection` and `declining` can end growth.
15. A new listing of an old company (SPCX, prices from 2026-06-12): not type A because of listing age.
16. Funds and treasury-asset models (ETV, MSTR): type n/a, no stage.
17. Theme adoption: filer counts only for themes the owner tags broad-application.
18. Several stages match at once: the precedence in S3.1 applies.

### Suggestions
- **S3.1 `curve_stage` per curve**, with starting thresholds:
  - **emerging:** (curve < 10% of company revenue, or first disclosed < 3 years ago) and TTM growth > 40%;
  - **accelerating:** increment rising and growth rising;
  - **steep:** increment rising, growth falling;
  - **past_inflection:** increment below its peak for ≥ 2 years;
  - **maturing:** growth below 2× the company's other segments for ≥ 4 quarters;
  - **declining:** TTM below its prior peak for ≥ 4 quarters;
  - **not_identified.**

  Proposed precedence (mine; to calibrate): declining, past_inflection, maturing, emerging, accelerating, steep. A stage change needs two consecutive TTM readings.
- **S3.2 `curve_type`:**
  - A when the curve is ≥ 50% of revenue and M04 reads intro or growth;
  - B when the curve is < 50% inside a mature core;
  - n/a for funds and treasury-asset models;
  - otherwise unassigned.

  The owner confirms every type.
- **S3.3 Fit K only once `past_inflection`.** Show the K interval and the number of points used, never a point estimate.
- **S3.4 Re-acceleration goes to review** ("new curve or cycle?", tied to M04 CvD).
- **S3.5 Filer adoption** (`theme_breadth`) is used only for themes the owner tags broad-application.
- **S3.6 Calibrate on blind owner labels** (LESSONS: calibrate cut-offs on known cases first). Episodes: AWS 2013–25, NVDA Data Center FY23–26, TSLA Energy, Intel Foundry, Micron data-center units, plus failed curves (question 4.3).

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| YoY deceleration read as "mature" | Logistic growth falls from the very start | Stage needs an increment peak at least 2 periods back |
| Logistic/Bass K fit | Biased; drifts with new data (S-new-M03-11) | "Not identified" before the peak; afterwards an interval only |
| Re-acceleration | A stacked second curve, or a cyclical pause | Review: "new curve or cycle?" (M04 CvD) |
| Lumpy young-company revenue | Contract timing (INFQ) | TTM with quarters shown; 2 consecutive readings |
| Theme filer counts | Count mentions, not demand; few filers in an oligopoly; boilerplate (S84) | Broad-application themes only; owner tags the theme type |
| Type A by listing age | SPCX is a new listing; SPAC CIKs start at the shell | Type from curve share plus M04 stage, owner confirms |

### Questions
**3.1 Stage method**
- (a) *Recommended.* Rules on TTM growth, the increment peak and revenue share, with no K fit before the peak. Why: K estimates are biased and drift before the inflection (S-new-M03-11, S-new-M03-12).
- (b) Always fit logistic or Bass and show intervals.
- (c) Owner labels only.

**3.2 Type A/B split**
- (a) *Recommended.* Curve share plus M04's life-cycle stage, owner confirms. Why: listing age misleads (SPCX, SPAC CIKs), and NVDA shows that some cases need the owner.
- (b) Years since the first 10-K.
- (c) The owner sets each one by hand.

**3.3 Calibration**
- (a) *Recommended.* Blind labels on 10–15 episodes, then set the thresholds. Why: cut-offs are calibrated on known cases before they are enforced (LESSONS).
- (b) Use the starting thresholds as they are.

---

## Round 4 — Leader persistence and base rates (R14)

### What the research says
1. **Bessembinder (2018)** (S01; link S-new-M03-1; abstract checked).
   - About four in seven CRSP common stocks since 1926 had lifetime buy-and-hold returns below one-month T-bills (≈ 57.4%; 42.6% beat them, per secondary summaries). S01's "58%" should read about 57%.
   - In dollar wealth creation, about 4% of companies (1,092 of about 26,000; ASU summary) account for all net wealth creation of about $35T over T-bills, 1926–2016.
   - 86 stocks account for about half ($16T), as S01 says.
   - The paper attributes this to positive skewness and says it helps explain why poorly diversified active strategies tend to underperform.
2. **Global follow-up** (S-new-M03-2; abstract checked), January 1990 to December 2020:
   - the top 2.4% of firms account for all $75.7T of net global wealth creation;
   - 55.2% of US stocks and 57.4% of non-US stocks trail one-month T-bills.
3. **1926–2023 update** (S-new-M03-3, other): 51.6% of 29,078 stocks had negative cumulative returns. NVDA had the highest annualized compound return (33.38%) among stocks with at least 20 years of data.
4. **Leadership does persist in some industries.**
   - Sutton 2007 (S-new-M03-7): Japanese data, 45 industries over 23 years. At least some industries show leadership lasting longer than a Markovian benchmark predicts.
   - Bessen et al. (S-new-M03-9, summary): since 2000, a top-4 firm by sales is increasingly unlikely to be displaced. Leaders' investment in proprietary software and IT is the main factor.
5. **But sustained superior performance is getting harder** (Wiggins & Ruefli 2005, S-new-M03-8), across a broad range of industries. It increasingly comes from a chain of advantages rather than a single one.
6. **Only sales growth persists** (CKL, S-new-M03-4). After 3 years of above-median sales growth, 22.8% achieve 3 more years, against 12.5% by chance. For income before extraordinary items the repeat rate equals chance. Investors extrapolate glamour growth too far (LSV, S35).
7. **Data.**
   - Tiingo adjusted daily bars (`price_bar`; internal use only, S68).
   - Shares (M04 question 1.1).
   - A FRED T-bill series (not yet chosen: TB3MS or DGS1MO).
   - Bessembinder's exact formula must be read from the paper at build.
   - Rank turnover needs Round 1 segment history.
   - Gaps: delisting returns (Tiingo coverage of delisted tickers is unverified); GOOG prices start in 2014.

### Worked example
- **AWS sales-growth runs.** Real growth: 2022 +28.8%, 2023 +13.3%, 2024 +18.5%, 2025 +19.7%.
  - With an *illustrative* peer median of +8%, AWS has run 4 years above it.
  - Baselines: chance 1/16 = 6.25%; the empirical all-firm rate for 4-year runs is 10.2% (CKL Table III).
  - CKL's medians are across all firms, not a theme peer group, so the baselines are indicative only.
- **Persistence card** (layout illustrative, margins real): "run 4 yrs (chance 6.3%, observed 10.2%) · segment operating margin 2025 35.4% (45,606 / 128,725) vs 37.0% in 2024 (39,834 / 107,556) · challenger rung: not assessed (M06) · CvD: n/a".
- **`wealth_created` for NVDA:** computed at build from stored bars; missing here.

### All cases
1. Full adjusted price history: measure from the listing date or the first stored bar, labelled.
2. History shorter than the company's listed life (GOOG from 2014): "partial since 2014".
3. A new listing (SPCX): too short; base-rate card only.
4. A SPAC or reverse merger (INFQ): starts at the owner-set series start (S1.4).
5. Splits and dividends: adjusted bars, with shares on the same basis.
6. Multi-class shares (GOOG, META): need class-summed shares (M04 question 1.1), otherwise missing.
7. Delisted or failed companies: Tiingo coverage unverified; calibration says "survivors only" where they are missing.
8. A run broken by one year: the current run resets; the longest run is also shown.
9. A run on company revenue vs on the mapped curve: labelled; the curve is used when mapped.
10. Too few peers for a median: M04 small-sample rule; no run is computed.
11. An acquisition-driven growth year: flagged inside the run.
12. Tenure without non-SEC peers: "among SEC filers".
13. A rank loss during CYCLICAL_TROUGH: held for review.
14. A rank change caused by a recast: not a rank loss; the break is marked.
15. A theme newer than the data: tenure counts from the first year with at least 2 companies with data.

### Suggestions
- **S4.1 `wealth_created` per company.** Bessembinder-style dollar measure since listing, with a base-rate card: "about 57% of US stocks trailed T-bills over their lives; about 4% of firms produced all net dollar wealth above T-bills (S01)". Context only, never scored.
- **S4.2 `growth_runs`** against the theme or peer median, printing both CKL baselines:
  - chance: 5-year 3.1%, 4-year 6.3%, conditional 3-year 12.5%;
  - empirical all-firm: 5-year 6.3%, 4-year 10.2%.
- **S4.3 `leader_tenure`:** years at the top of the theme on mapped revenue, plus rank changes. A rank loss goes to review.
- **S4.4 Persistence card** per leader: tenure, runs, margin gap, M06 challenger rung, M04 CvD. Components only; the owner judges.
- **S4.5 SOURCES.md:** correct S01 to "about 57%" and add its link.

### Failure modes (rows to add)
| Indicator | How it can mislead | Guard |
|---|---|---|
| "4% of stocks" read as a return claim | It is dollar wealth, dominated by large, long-lived firms | Word R14 exactly; base rate beside every leader claim |
| Past wealth creation | Survivorship; it measures the past | Context only, never a buy signal |
| Sales-growth runs | Growth bought with price cuts or credit (CKL) | Paired with margin trend and M04 earnings quality |
| Persistence evidence | Japan 1970s–90s; a working paper; hypercompetition points the other way | Shown beside the M06 rung (R21) and moat duration (A3) |
| Watchlist examples | All winners | At least 1 in 3 calibration episodes are failed curves |

### Questions
**4.1 How R14 appears**
- (a) *Recommended.* A base-rate card plus the company's own dollar wealth created. Why: it states R14 exactly, next to the company's own record.
- (b) A text statement in the doc only.

**4.2 Persistence metric**
- (a) *Recommended.* Sales-growth runs against the chance and empirical baselines, plus leader tenure. Why: sales is the only fundamental that persists above chance (CKL).
- (b) Rank turnover only.
- (c) Third-party share stability only.

**4.3 Failed curves in calibration**
- (a) *Recommended.* Required: at least 1 in 3 episodes. Why: the watchlist examples are survivors.
- (b) Watchlist episodes only.

---

## Round 5 — Outputs: signals, M01 weights, M11 sizing

### What the research says
1. **M01's MY weights row** reads "Fundamentals, moat, capex, money flow lead; ownership medium; analysts low; technicals time entries" (M01_TIMEFRAMES.md). M03 is not placed in it yet.
2. **Horizon logic.**
   - Sales persistence is real but modest, earnings persistence is about chance, and investors over-extrapolate past growth (S-new-M03-4, S35).
   - Price behaviour (S12): short-horizon reversal, intermediate momentum, and reversal over 3–5 years.
   - Price evidence alone does not justify weighting curve stage in MY. The long-horizon reversal and LSV argue for pairing MY stage readings with valuation (M08).
   - Design choice, not a sourced result: stage weighted most in MY; acceleration and inflection events in PT; information only in ST.
3. **Sizing.** Skewness cuts both ways (S01): poorly diversified portfolios usually trail, and the winners' gains come from long compounding. That argues against oversized type-A bets and against mechanically trimming intact leaders. R23 and D16 already set the frame.
4. **Plumbing** (`store/migrations/engine/0001_initial.sql`). The `signal` table's primary key is (ticker, module_id, signal, timeframe, as_of), and `value` is NUMERIC. My reading of that schema:
   - two curves of one company (AMZN retail and AWS) cannot both hold `curve_stage` on the same day unless the curve is part of the key;
   - enum values are stored as text (SQLite allows text in a NUMERIC column);
   - nothing writes `signal` yet; the M04 pack (S1.5) proposes M04 as the first writer;
   - M01 profiles and M11 caps are not built. Theme overlap for R23 can come from `theme_company` today.

### Worked example (illustrative records on real figures)
- `{ticker: "NVDA", module_id: "M03", signal: "curve_stage.data_center", value: "steep", timeframe: "MY", evidence_grade: "A", source_ref: "8-K q4fy26pr (0001045810-26-000019)", method: "increment rising 32.5→67.7→78.5; no K fit", as_of: "2026-02-25"}`
- `{ticker: "AMZN", …, signal: "curve_stage.aws", value: "accelerating", …, method: "increment 10.7→16.8→21.2; growth 13.3→18.5→19.7%; review open: new curve or cycle?"}`
- `{ticker: "INFQ", …, signal: "curve_type", value: "A", …, method: "company = curve; M04 lifecycle pending; SPAC-CIK review open"}`. Its stage: not_identified.
- M11, illustrative cap table: confirmed leader ≤ owner cap X%; unproven type A ≤ X/3 until 2 milestones are met.

### All cases
1. Full grade-A evidence: the signal is written with its accession.
2. Mixed evidence (rank grade A, share grade B): separate signals, each with its own grade, never blended.
3. A component is missing: no row is written (missing, never zero). `not_identified` is a stage that is written.
4. A stage change seen once: pending; written on the second reading.
5. A recast inside the window: `stage_break` is written and the stage is recomputed within one definition.
6. A rank loss: review item plus a PT alert, as a warning only (D16).
7. A downgrade during CYCLICAL_TROUGH: held for review.
8. Several leaders sharing one killswitch (hyperscaler capex): R23 exposure, with M02 spender capex shown as the demand driver.
9. A company with several curves: one row per curve (question 5.4).
10. The owner overrides a type or stage: written with method "owner" and kept until the owner clears it.
11. A profile switch: all signals stay visible (D10), only weights change, and the profile of record is logged (D12).
12. A type-A position with no milestone defined: later tranches show "milestone missing" (if 5.3a).
13. An M04 input not built yet: "pending M04", and no gate pass is assumed.

### Suggestions
- **S5.1** Signals as listed under "Signals out". Each carries the filing and its accession in `source_ref`.
- **S5.2 Weights.**
  - MY: stage and leader lead, beside fundamentals.
  - PT: `increment_trend` and stage transitions are event alerts, as M01 rule 6 / R16 already do for filings.
  - ST: information only.
- **S5.3 M11 evidence tier:** confirmed leader, contender, or unproven type A, mapped to an owner-defined cap table.
  - Type A defaults to tranches (M01 rule 2).
  - Rule 3 already gates each later tranche on CvD, the survival gate and the 1–2σ trigger. Adding an R4 milestone gate for type A is a new proposal for the owner, not an existing rule.
- **S5.4 No automatic trim warning from M03 alone for an intact leader.** Warnings fire only on a stage break, a rank loss or a killswitch.

### Failure modes (rows to add)
| Output | How it can mislead | Guard |
|---|---|---|
| Stage feeding sizing | A wrong stage (recast, lumpy quarter) moves size | Evidence tier only; owner caps (R23); 2 readings per change |
| Leader tier in a cyclical trough | Looks like a lost curve | Read with M04 CvD; downgrade held for review |
| Theme concentration | Several "leaders" share one killswitch | R23 exposure by theme and killswitch |
| Timeframe shopping | PT acceleration used to justify MY adds | Profile-of-record logging (D12) |

### Questions
**5.1 M03's weight in MY**
- (a) *Recommended.* Leading, beside fundamentals (added to M01's weights row). Why: R6 makes the curve part of the MY thesis; valuation (M08) sits beside it.
- (b) Medium.

**5.2 M11 coupling**
- (a) *Recommended.* M03 sets an evidence tier and the owner's cap table maps it to a maximum size. Why: sizing stays owner-set (R23, D16).
- (b) M03 suggests a % size.
- (c) No coupling.

**5.3 Type-A entries**
- (a) *Recommended.* Tranches only; each later tranche is gated by M01 rule 3 plus an R4 milestone. Why: most young curves fail, while the winners compound.
- (b) The same as other entries.

**5.4 Signals for companies with several curves**
- (a) *Recommended.* Put the curve label in the signal name (`curve_stage.aws`), with no schema change. Why: it fits the D13 key as built, and the detail lives in `curve_map`.
- (b) Add a `subject` column to `signal` (a migration that changes D13).
- (c) One row per company, for its main curve only.

---

## Signals out (proposed, D13)
"info" = visible, no weight (D10). "Alert" = a PT event alert.

| Signal | Value | Meaning | Grade | MY | PT | ST |
|---|---|---|---|---|---|---|
| curve_type | A / B / n-a / unassigned | Owner-confirmed curve type (R6) | A | context | context | info |
| curve_stage | enum (S3.1) | Stage per curve | A | lead | transition = alert | info |
| curve_share | % | The curve's share of company revenue | A | ✓ | – | info |
| increment_trend | rising / peaked / below_peak | Yearly dollar increment against its peak | A | ✓ | change = alert | info |
| leader_rank | k of n with data | Dollar rank on mapped revenue | A | lead | change = alert | info |
| growth_gap_z | robust z | Growth against the theme median | A | ✓ | ✓ | info |
| margin_gap | percentage points | Margin against the theme median (component c; added in this pack) | A | ✓ | – | info |
| share_obs | % | Third-party share (component d; added in this pack) | B | ✓ | – | info |
| growth_runs | years | Years above the median, with baselines | A | ✓ | – | info |
| leader_tenure | years | Years at the top of the theme | A | ✓ | – | info |
| wealth_created | USD | Dollar wealth since listing; never scored | A | context | – | – |
| stage_break | flag | Recast or reporting-basis break | A | alert | alert | info |
| evidence_tier | confirmed / contender / unproven A | Input to the M11 cap table | A/B | ✓ | – | – |

## Build parts (proposal)
- Each part is one conversation at Medium effort, on branches `m03-part1` and so on.
- Each part updates its module doc in the same commit and ships fixture tests.
- **Live check:** one combined owner run of `uv run python scripts/run_live.py <label>` per part, with the log sent back. Claude cannot call SEC.
- **No new packages expected.** The FSN loader later would use the standard-library zipfile module.
- **Order:** after M04 parts 1, 2 and 7. If M03 goes first, M03 part 1 builds the shared segment reader in the shape M04 plans.

| Part | Contents | Depends on | Live check |
|---|---|---|---|
| 1 Segment facts and curve map | `segment_fact` reader with the tracked tier (1.1); `curve_map` proposals and confirmation (S1.2); recast and basis-change detectors (S1.3, S1.4); external flag (1.3) | M04 part 1 (part 7 if built) | Instances for watchlist and tracked names (≈190, under a minute at 5/s); recast report for MU and INTC |
| 2 Curve stage and type | TTM and increments per curve; `curve_stage` and `curve_type` with the 2-reading rule; unit curves through `unit_metric`; K interval after the inflection; "new curve or cycle?" review | 1; M04 `lifecycle_stage` and `unit_metric`; CvD pending until M04 part 8 | Stage printout for every mapped curve (stored data, no new SEC requests) |
| 3 Leaders and categories | Leader components (S2.2); `market_share_obs` and owner form (S2.4); missing-peer flags; first-disclosure dates; theme leader table | 1, 2; M02; M04 peers (1.3, 1.4) | Companyfacts for confirmed peers outside the watchlist (≈1 request each) |
| 4 Persistence and base rates | `wealth_created` (formula read from the paper first) and base-rate card; `growth_runs`; `leader_tenure`; persistence card | 1–3; Tiingo bars; FRED | One FRED series download; Tiingo coverage probe on 2–3 delisted calibration names |
| 5 Signals, weights and calibration | M03 `signal` writer (5.4); M01 weights row (5.1); evidence tier and cap hook (5.2); digest items for stage changes and rank losses; company "Leaders & curve" tab; calibration harness on blind labels including failed curves (3.3, 4.3) | 1–4; M04 signal writer if built | Companyfacts or instances for the episodes outside the watchlist (≈10–15 requests); calibration report |

The owner's blind labelling can run alongside parts 2–4.

## Known gaps
- **Market size K:** paid or excluded by terms (Gartner, IDC, TrendForce; S93). Free industry totals (e.g. monthly SIA/WSTS) not checked; this overlaps the M04 pack's proposed DS13.
- **Third-party shares:** owner-entered, grade B only.
- **History:** segment history before XBRL (2009–2011); FSN starts 2009-04-15.
- **Figures not fetched yet:**
  - Google Cloud and Azure dollar figures; Azure dollars may not be disclosed at all.
  - NVDA's ASC 280 segments vs its market platforms, and whether platform revenue is XBRL-tagged.
  - Tesla Energy: the $2.69B (+27%) figure came from a search snippet, and 2025 storage deployments (46.7 vs 31.4 GWh) from other sources. Verify against the stored deliveries 8-Ks (DS2) before use.
- **Open checks:**
  - which FRED T-bill series to use (TB3MS or DGS1MO), and whether it needs a key (no FRED key in `.env`);
  - Bessembinder's formula;
  - whether Modis (1994) is the TFSC 46 article with Debecker;
  - Hoberg-Phillips data-library terms;
  - GFS: US GAAP or IFRS;
  - Tiingo coverage of delisted tickers;
  - S-new-M03-2 page range.
- **GOOG prices start in 2014.**
- **Read only as abstract or summary:** Klepper, Fisher & Pry, Christensen & Bower, Van den Bulte & Lilien, Bessen et al., Berger & Hann 2007, Bessembinder global (S-new-M03-2), Bessembinder 2024 (S-new-M03-3).
- **Register IDs clash with the M04 pack,** which proposes DS12 (dimensional facts), DS13 (industry price and volume), DS14 (unit KPIs) and DS15 (historical 4.02 texts). Proposal:
  - share DS12;
  - DS16 = market size and industry totals (K);
  - DS17 = third-party market shares (grade B, owner-entered).
- **Signal key:** the `signal` primary key has no curve field (question 5.4).
- **M04:** every M04 input is still at the design stage.
- **Source housekeeping:** S01 "58%" should read about 57%; S-new-M03-16 duplicates S-new-60 (merge them).

## New sources
These IDs are provisional and become S-numbers when added to SOURCES.md; S-new-M03-18 is unused. "Other" marks sources that are not peer-reviewed or are secondary.

- **S-new-M03-1** Bessembinder (2018), "Do Stocks Outperform Treasury Bills?", J. Financial Economics 129(3):440–457, doi 10.1016/j.jfineco.2018.06.004 — https://ideas.repec.org/a/eee/jfinec/v129y2018i3p440-457.html
  - ASU summaries (other): https://blogs.wpcarey.asu.edu/20181212-research-shows-most-stocks-haven%E2%80%99t-outperformed-treasury-bills ; https://news.wpcarey.asu.edu/20180917-do-stocks-outperform-treasury-bills (gives S01 its link).
- **S-new-M03-2** Bessembinder, Chen, Choi & Wei (2023), "Long-Term Shareholder Returns: Evidence from 64,000 Global Stocks", Financial Analysts Journal 79(3), doi 10.1080/0015198X.2023.2188870 — https://rpc.cfainstitute.org/research/financial-analysts-journal/2023/long-term-shareholder-returns-evidence-from-64000-global-stocks
- **S-new-M03-3** Bessembinder (2024 working paper), "Which U.S. Stocks Generated the Highest Long-Term Returns?" (summary, other) — https://marginalrevolution.com/marginalrevolution/2024/09/which-u-s-stocks-generated-the-highest-long-term-returns.html
- **S-new-M03-4** Chan, Karceski & Lakonishok (2003), "The Level and Persistence of Growth Rates", J. Finance 58(2):643–684 — https://ideas.repec.org/p/nbr/nberwo/8282.html ; full text — https://www.lsvasset.com/pdf/research-papers/Level+Persistence_of_Growth_Rates_FINAL.pdf
- **S-new-M03-5** Golder & Tellis (1993), "Pioneer Advantage: Marketing Logic or Marketing Legend?", J. Marketing Research 30(2):158–170 — https://people.duke.edu/~moorman/Marketing-Strategy-Seminar-2015/Session%205/Golder%20and%20Tellis.pdf
- **S-new-M03-6** Klepper (1996), "Entry, Exit, Growth, and Innovation over the Product Life Cycle", American Economic Review 86(3):562–583 — https://ideas.repec.org/a/aea/aecrev/v86y1996i3p562-83.html
- **S-new-M03-7** Sutton (2007), "Market Share Dynamics and the 'Persistence of Leadership' Debate", American Economic Review 97(1):222–241 — https://ideas.repec.org/a/aea/aecrev/v97y2007i1p222-241.html
- **S-new-M03-8** Wiggins & Ruefli (2005), "Schumpeter's Ghost: Is Hypercompetition Making the Best of Times Shorter?", Strategic Management Journal 26(10):887–911 — https://ideas.repec.org/a/bla/stratm/v26y2005i10p887-911.html
- **S-new-M03-9** Bessen, Denk, Kim & Righi, "Declining Industrial Disruption" (working paper; summary, other) — https://sites.bu.edu/tpri/2021/10/06/declining-industrial-disruption
- **S-new-M03-10** Christensen & Bower (1996), "Customer Power, Strategic Investment, and the Failure of Leading Firms", Strategic Management Journal 17(3):197–218 (summary, other) — https://acawiki.org/Customer_power,_strategic_investment,_and_the_failure_of_leading_firms
- **S-new-M03-11** Van den Bulte & Lilien (1997), "Bias and Systematic Change in the Parameter Estimates of Macro-Level Diffusion Models", Marketing Science 16(4):338–353 — https://ideas.repec.org/a/inm/ormksc/v16y1997i4p338-353.html
- **S-new-M03-12** Modis (1994), "Determination of the Uncertainties in S-Curve Logistic Fits" (OSF preprint n53pd). The journal version is commonly cited as Debecker & Modis, Technological Forecasting and Social Change 46 (1994) — verify. https://ideas.repec.org/p/osf/osfxxx/n53pd.html
- **S-new-M03-13** Fisher & Pry (1971), "A Simple Substitution Model of Technological Change", Technological Forecasting and Social Change 3:75–88 — https://swov.nl/en/publicatie/simple-substitution-model-technological-change
- **S-new-M03-14** Berger & Hann (2003), "The Impact of SFAS No. 131 on Information and Monitoring", J. Accounting Research 41(2):163–223 — https://cuhk.edu.hk/acy2/workshop/20111214Hann/Paper1.pdf ; Berger & Hann (2007), The Accounting Review 82(4):869–906 (citation only).
- **S-new-M03-15** SEC Financial Statement and Notes data sets (monthly since November 2020) — https://www.sec.gov/data-research/financial-statement-notes-data-sets ; readme and DIM format: S40.
- **S-new-M03-16** ASU 2023-07, segment reporting (KPMG summary, other; same standard as M04's S-new-60, merge) — https://kpmg.com/us/en/frv/reference-library/2023/fasb-issues-asu-requiring-new-segment-disclosures.html
- **S-new-M03-17** Autor, Dorn, Katz, Patterson & Van Reenen (2020), "The Fall of the Labor Share and the Rise of Superstar Firms", Quarterly Journal of Economics 135(2):645–709 — https://academicnewsletter.sufe.edu.cn/info/344929
- **S-new-M03-19** Amazon releases and filings:
  - FY2015 10-K (AWS 2013–15) — https://www.sec.gov/Archives/edgar/data/0001018724/000101872416000172/amzn-20151231x10k.htm
  - Q4 2022 release — https://ir.aboutamazon.com/news-release/news-release-details/2023/Amazon-com-Announces-Fourth-Quarter-Results/
  - Q4 2024 release — https://ir.aboutamazon.com/news-release/news-release-details/2025/Amazon-com-Announces-Fourth-Quarter-Results/
- **S-new-M03-20** Amazon Q4 2025 release — https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-Fourth-Quarter-Results/
- **S-new-M03-21/22/23** NVIDIA Q4 releases (8-K, SEC):
  - FY2024 — https://www.sec.gov/Archives/edgar/data/1045810/000104581024000028/q4fy24pr.htm
  - FY2025 — https://www.sec.gov/Archives/edgar/data/1045810/000104581025000021/q4fy25pr.htm
  - FY2026 (2026-02-25) — https://www.sec.gov/Archives/edgar/data/1045810/000104581026000019/q4fy26pr.htm
- **S-new-M03-24** Intel 8-K exhibit 99.1 of 2024-04-02 (segment recast) — https://www.sec.gov/Archives/edgar/data/50863/000005086324000068/a04022024form8-kexhibit991.htm
- **S-new-M03-25** Micron FY2025 10-K (reorganization and recast) — https://www.sec.gov/Archives/edgar/data/723125/000072312525000028/mu-20250828.htm
- **S-new-M03-26** Infleqtion companyconcept, checked 2026-10-12. The RPO tag returns 404.
  - Revenue — https://data.sec.gov/api/xbrl/companyconcept/CIK0002007825/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json
  - Operating cash flow — https://data.sec.gov/api/xbrl/companyconcept/CIK0002007825/us-gaap/NetCashProvidedByUsedInOperatingActivities.json

**Reused IDs:** S01 (correct to about 57%), S06, S12, S35, S36, S40, S41, S68, S84, S93, S108, S109; from the M04 pack, S-new-56 (Dickinson) and S-new-60.
