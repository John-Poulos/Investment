# M11 — Design review pack (draft for the owner)

Status: research only — nothing is decided until the owner answers (D7); 2026-10-12

Source IDs: existing S-IDs where they exist. New sources carry provisional IDs **S-new-M11-n**. They become S122 onward when added to SOURCES.md, after this list is merged with the M04 pack's proposed list, which also starts at S122.

## Purpose and dependencies

**Purpose.** M11 answers four questions for each holding and watch-only name:
- What is the thesis, and is it on track, early or wrong?
- How large may the position be?
- What would make me get out?
- Is it beating the hurdle?

M11 also combines all module signals into one confluence score for each timeframe (D13).

**Approved revisions it must honour:**
- **R4:** dated, checkable milestones separate "early" from "wrong".
- **R19:** guidance ledger scored against actuals, weighted toward near-term verifiable items, with consecutive releases compared.
- **R5:** hurdle is S&P 500 TR; the stretch hurdle is TR + CPI.
- **R23:** theme and shared-killswitch exposure, with caps set by the user.
- **D11:** core lots plus overlays, each with its own profile.
- **D12:** profile of record; each decision logs the profile it was made under.
- **D13:** the signal record format.
- **D14:** evidence grades.
- **D16:** exit signals are warnings only.
- **D8:** ambiguous cases go to review.
- **D10:** everything is visible in every timeframe.
- **D21:** quotes are verified.
- **M01:** rules 1–7 and the sizing-caps row.
- **Data handling:** missing data stays missing, never zero.

**Depends on:**
- **M01:** hurdle, review cadence, sizing caps, the lead/medium/low module tiers, and the rule 3 tranche gates.
- **M04 (design pack in progress):** `cvd_state`, `survival_gate` and `overreaction_gap`. M04's S1.7 also proposes a guidance hit rate and a "removed" change kind; Round 2 overlaps it, so that piece must be built once, not twice.
- **M02:**
  - themes and `theme_company`
  - capex guidance and the capex guided-vs-actual view (`moneyflow/guided.py`, D-M02-29/32)
  - `capex_stated`
  - the crowding flag (D-M02-57)
  - spender, supplier and financing links
  - news (D-M02-58)
- **R19 ledger** (`src/engine/guidance/`): includes `changes.py`, which already classifies each change as reaffirmed, raised, lowered, narrowed, widened or definition changed.
- **M00:**
  - `price_bar` (Tiingo, internal use only, S68)
  - the review queue, including the open milestone items held for M11 (D-UI-14/15)
  - the UI
- **Later:** M03 and M05–M10 supply signals (missing until built); M12 handles options overlays (DS5).

**Already in the schema but unused:** `position`, `lot`, `decision` and `signal` (engine migration 0001). Nothing reads or writes them today.

**Not built:** general guidance-vs-actual scoring. Capex is the only exception, because M02 already shows guided vs actual once a guided period ends.

---

## Round 1 — Thesis record, profile of record and decision log (D11, D12, R4)

**What the research says**
- **Checkable statements carry more weight than talk.** Good-news management forecasts move prices only when they come with verifiable forward-looking statements; "soft talk" does not (S-new-M11-1). So a thesis should be written as verifiable items (metric or event, date and source), not as prose.
- **Management targets are biased by incentives.** Forecast credibility varies with litigation and insider-trading incentives (S21). Analyst forecasts are walked down to beatable levels most strongly when the firm or its insiders sell stock after the announcement (S-new-M11-2). Each target should therefore record who set it, as R19 already does with `origin` and `grade`.
- **Investors hold losers too long and sell winners too early (the disposition effect).** In Odean's sample of 10,000 discount-brokerage accounts, the losers people kept went on to do worse (S-new-M11-3). Writing exit criteria down at entry is the standard guard.
- **Pre-mortems are weakly supported.** Imagining an outcome as already certain produced longer, more episodic explanations; the time framing itself had little effect (S-new-M11-4). This supports an optional pre-mortem prompt. It does not show that people find the true causes better. The popular "30% more reasons" figure is unverified and is not cited.
- **Frequent trading costs returns.** The households that traded most earned 11.4% a year net, against 17.9% for the market, mainly because of trading costs (S-new-M11-5). This supports logging every decision with its rationale and showing turnover.

**Worked example: Boeing 777-9 first delivery, one milestone across versions (S-new-M11-18)**

| Stated on | Target for first 777-9 delivery | Charge | Source |
|---|---|---|---|
| 2022-04-27 (Q1 2022) | 2025 | not found | AirInsight (secondary; page returned 403 on re-check) |
| Q3 2024 | 2026 ("the anticipated first delivery of the 777-9 was delayed to 2026") | $2,608M reach-forward loss in Q3 2024, plus an additional $891M on 777X in Q4 2024 (reason for the Q4 charge not checked) | Boeing FY2024 10-K (primary, quotes checked) |
| 2025-10-29 (Q3 2025) | 2027 ("now anticipates first delivery in 2027") | $4.9B pre-tax | 8-K EX-99.1 (primary, quote checked) |

How it would be stored:
- One `milestone` row: kind `event`, metric `777-9 first delivery`, `set_by` company, grade A.
- Each restatement becomes a new version.
- Status: `slipped` twice, a cumulative slip of 2 years since 2022.
- Missing data: the release that would mark the milestone `hit` (or `missed` after 2027) does not exist yet, so the current target stays `open`.

**All cases**
1. **New position with a thesis:** thesis v1 is stamped at creation and the profile of record is set.
2. **Watch-only thesis** for a name not held: `position_id` is NULL.
3. **Thesis edited:** a new version is created and the old one gets `superseded_at`. Nothing is overwritten.
4. **Buy, add, trim, exit or warning dismissed:** a `decision` row is written with the profile, bar size, `signal_snapshot` and a note.
5. **The owner switches the viewing profile (D12):** decisions log the viewing profile. The position keeps its profile of record unless a logged decision changes it.
6. **Overlay on a core position (D11):** the overlay gets its own thesis row and profile and is never judged under the core profile.
7. **Milestone with a measurable target and a due date:** scored. Without both, it is stored as `narrative` and not scored.
8. **Company restates a milestone** (Boeing): a new version with status `slipped`.
9. **Company stops mentioning a milestone:** `withdrawn` (Round 2).
10. **Owner-set milestone:** labelled `owner` and never mixed into company credibility.
11. **Open review item held for M11** (`guidance_unparsed`, milestone sentences, D-UI-14/15): the owner can choose "Make milestone" or leave it open.
12. **Lots with no thesis** (e.g. entered before M11): a "no thesis" warning.
13. **Position closed and later reopened:** a new thesis version that references the old one.
14. **Split or ticker change:** quantities adjust via Tiingo `splitFactor`; the thesis is keyed to the position, not the ticker. To confirm at build.
15. **Pre-mortem left blank:** allowed if the field is optional (Question 1.4).

**Suggestions**
1. **`thesis` table, versioned.** Fields:
   - `thesis_id`, `position_id` (nullable), `ticker`, `version`
   - `profile` (MY/PT/ST), `summary`, `created_at`, `superseded_at`
   - `hurdle` (TR or TR + CPI)
   - `review_due`: set from the M01 cadence, after each 10-Q/10-K
   - optional `premortem` text
2. **`milestone` table.** Fields:
   - `thesis_id`, `kind`, `metric`, `target_low`, `target_high`, `unit`, `due_by`, `source_ref`, `grade`, `set_by` (company or owner)
   - `kind` is one of: `guidance` (links to `guidance_id`), `event`, `kpi`, or `narrative` (not scored)
   - status is one of: `open`, `hit`, `missed`, `slipped`, `withdrawn`, `unscorable`
3. **`kill_criterion` table:** `thesis_id`, `shared_key` (nullable), `rule`, `source_module`, `active` (Round 5).
4. **New "Make milestone" review action** turns a `guidance_unparsed` or milestone item into a milestone row. This closes the D-UI-14 open item.
5. **The UI writes `decision` rows** for buy, add, trim, exit and dismiss, each with its signal snapshot. This is the D12 audit trail. Turnover is shown per position.

**Failure modes**

| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Thesis text | Written after the price moved, it becomes a rationalisation (S-new-M11-3) | Stamped at creation; edits create versions and never overwrite |
| Vague milestones ("AI leadership") | Can't be scored, yet look like progress | A measurable target and a due date are required; otherwise `narrative`, not scored |
| Profile of record | Profile shopping, i.e. switching profile to justify a hold (M01) | Each decision carries `profile` and `signal_snapshot`; the position keeps `profile_of_record` |
| Overlay | Judged under the core profile | Own thesis row and profile (D11) |
| Company targets | Walked down or inflated by incentives (S21, S-new-M11-2) | `origin` and `grade` per milestone; owner milestones kept separate |
| Decision log | Frequent trades erode returns unnoticed (S-new-M11-5) | Turnover shown per position and per year |

**Questions**
- **1.1 Where do theses live?**
  - (a) One thesis per position, versioned, plus watch-only theses (**recommended**): names you are waiting to buy need kill criteria too.
  - (b) Held positions only.
- **1.2 Who may set milestones?**
  - (a) Both the company (grade A/B, with a quote) and the owner, with owner milestones labelled `owner` and kept out of company credibility (**recommended**): some theses rest on the owner's own checkpoints.
  - (b) The company only.
- **1.3 Entering lots:**
  - (a) Manual entry first, broker CSV import later (**recommended**): the import format depends on the broker.
  - (b) A broker import now. Which broker?
- **1.4 Pre-mortem field:**
  - (a) Optional prompt at thesis creation (**recommended**): cheap to fill, though the evidence for it is only suggestive (S-new-M11-4).
  - (b) Required at entry.
  - (c) None.

---

## Round 2 — Milestone and guidance scoring: early vs wrong (R4, R19)

**What the research says**
- **How often a target counts as met depends on the window.** 12-month analyst price targets were met at the horizon 38% of the time, but 64% at any time within the window (S11). A score must therefore state its window: by the due date, or later.
- **A forecaster's track record changes how its next forecast is received.** Analysts respond less to managers with poor prior accuracy (Williams 1996; Kala, Shailer & Wilson 2025; S-new-M11-6). In the 2025 study, the market tends to follow the analysts. This supports a per-company credibility score built from the ledger.
- **Multi-year management forecasts are biased upward** in a sample of private venture-backed firms (S22). Applying that to public-company guidance is an assumption, not a finding. Weighting near-term guidance more rests mainly on R19 and S-new-M11-6.
- **The Brier score** (the mean squared error between a forecast probability and the 0/1 outcome; 0 is perfect) can score probability forecasts (S-new-M11-7). It fits only if the owner attaches a probability to a milestone. Range guidance is scored directly.
- **Calls add information beyond the release** (S99), so call-only guidance counts. It carries grade B until a company document matches it (D-M02-22).

**Worked example: Micron FQ1 FY2026, quarter ended 2025-11-27 (S-new-M11-19)**

| Metric (basis) | Guided 2025-09-23 | Actual 2025-12-17 | In range | error_mid | error_hw |
|---|---|---|---|---|---|
| Revenue | $12.50B ± $0.30B | $13.64B | No (above) | +9.1% | +3.8 |
| Gross margin (GAAP) | 50.5% ± 1.0 | 56.0% | No (above) | +5.5 pp | +5.5 |
| Gross margin (non-GAAP) | 51.5% ± 1.0 | 56.8% | No (above) | +5.3 pp | +5.3 |
| Diluted EPS (GAAP) | $3.56 ± $0.15 | $4.60 | No (above) | +29.2% | +6.9 |
| Diluted EPS (non-GAAP) | $3.75 ± $0.15 | $4.78 | No (above) | +27.5% | +6.9 |

Sources:
- Guidance: FQ4 FY2025 8-K EX-99.1 (primary, checked).
- Actuals: FQ1 FY2026 release via Nasdaq (company text on another host; re-confirmed through search summaries).

Formulas: error_mid = (actual − mid) / |mid|, in pp for margins; error_hw = (actual − mid) / half-width.

Reading:
- GAAP revenue would be scored against the 10-Q XBRL revenue concept. The expected concept is `RevenueFromContractWithCustomerExcludingAssessedTax`, not yet checked against Micron's companyfacts.
- Non-GAAP rows are scored only against the release text.
- All five rows missed above the range, which is a positive surprise. Range width says little about accuracy in a fast memory upcycle, so the credibility card must show the direction of misses, not only the hit rate.

Boeing under the status rule (Suggestion 3):
- Under Question 2.3a, the Q3 2024 slip with a $2,608M charge gives `exit_warning`, and the Q3 2025 second slip ($4.9B) repeats it.
- Under 2.3b, each slip gives `review`.

**All cases**
1. **Range guidance, same basis as the actual:** `in_range`, `error_mid` and `error_hw`.
2. **Point guidance:** `error_mid` only. With no range there is no half-width.
3. **Bound** ("more than $25B"): a floor is hit when actual ≥ floor (a ceiling when actual ≤ ceiling). No midpoint error.
4. **Direction-only** ("grow", "increase"): skipped and flagged.
5. **`flag='not_meaningful'`:** skipped.
6. **Growth-rate guidance:** `unscorable` until DS3.
7. **GAAP guidance:** the XBRL actual, found via `moneyflow/periods.py` `span_of()` and `value_for()`. This includes 52/53-week fiscal years.
8. **Non-GAAP guidance:** the stated actual parsed from the next release (2.2a), or `unscorable` (2.2b).
9. **Basis mismatch** (non-GAAP guide vs GAAP actual): `unscorable`.
10. **`definition changed`** (e.g. Microsoft finance leases): scoring blocked.
11. **Guidance raised or lowered within the period:** scored against the first guidance (2.1a), with the walk shown.
12. **Metric and basis guided in release N−1 but absent in N:** `withdrawn`.
13. **Period not yet reported:** `open`, not due.
14. **Call-only guidance:** grade B at weight 0.5 until matched (D-M02-22).
15. **Actual later restated** (10-K/A): keep the first-reported actual and note the restatement. Proposed; confirm at build.
16. **Capex:** reuse M02's guided-vs-actual (`moneyflow/guided.py`, `capex_stated`). Not rebuilt.
17. **Event milestone:**
    - `hit` when a company document says it happened
    - `slipped` when the date is restated later
    - `missed` when `due_by` passes with no hit and no restatement
    - `withdrawn` when the company stops mentioning it
18. **KPI milestones** (Tesla deliveries): `unscorable` until DS2.
19. **Owner milestone with a probability:** Brier score, shown apart from company credibility.
20. **On track, price flat or down, CvD not STRUCTURAL_DECLINE:** `early` (hold; M01 rule 5).
21. **On track, price down, CvD missing (M04 not built):** "on track, CvD missing". Never `early` by default.

**Suggestions**
1. **`guidance_score` per guidance row, computed by code.** Fields:
   - `actual`, `actual_source` (`xbrl`, or `stated` with a quote), `in_range`
   - `error_mid`, `error_hw`, `scored_on`
   - Skipped rows are flagged as unbound or direction-only.
2. **Credibility card per company and metric family:**
   - hit rate, mean signed error (bias), mean |error_hw|
   - number of withdrawals, number of first-guide-to-final walk-downs
   - Window: the last 8 quarters, ordered by `stated_on`.
3. **Status rule**, written as the M11 signals `milestone_state` and `thesis_state`:

| Milestone state | Price | M04 CvD | Result |
|---|---|---|---|
| On track (hit, or not yet due) | Flat or down | Not STRUCTURAL_DECLINE | `early` (hold; M01 rule 5) |
| Missed, or slipped once without a charge | Any | Any | `review` |
| Slipped twice, slipped with a charge, or withdrawn | Any | Any | `exit_warning` (D16) |

4. **Weights:**
   - by horizon: next quarter 1.0, this FY 0.75, beyond 0.4 (illustrative starting values)
   - by grade: A 1.0, B 0.5
5. **Brier score only for owner milestones that carry a probability.**
6. **Build the guidance hit rate once,** shared with M04 S1.7.

**Failure modes**

| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Non-GAAP guidance vs GAAP actual | A false miss | Like-for-like basis only, otherwise `unscorable` |
| Definition change | Reads as a cut (Microsoft finance-lease case) | `definition changed` blocks scoring |
| Bound guidance | Treated as a point, giving a bogus midpoint error | Floor or ceiling test only |
| Walked-down guidance | An easy "beat" (S-new-M11-2) | Score against the first guidance; show the walk |
| Quietly dropped targets | Silence reads as fine (M01 rule 4) | `withdrawn` detection, release N−1 vs N |
| Hit rate alone | Hides the direction of misses (Micron's five rows above range) | Card shows signed bias next to the hit rate |
| Window choice | Horizon-only and any-time counts differ widely (S11) | Score states its window: by due date, or late |
| Lumpy KPIs | Late looks the same as missed | "Early vs wrong" needs CvD (M04), not price alone |

**Questions**
- **2.1 What should a "beat" be measured against?**
  - (a) The first guidance for the period, with the walk shown (**recommended**): this defeats walk-downs.
  - (b) The latest guidance before the result.
- **2.2 Non-GAAP scoring:**
  - (a) Parse the stated non-GAAP actual from the next release (grade A, quoted) (**recommended**): most releases guide non-GAAP.
  - (b) Score GAAP only; non-GAAP is `unscorable`.
- **2.3 A slipped milestone with a charge (Boeing):**
  - (a) `exit_warning` at the second slip or at any charge (**recommended**): a charge is hard evidence that the delay is costly.
  - (b) Always `review` only.
- **2.4 Horizon weights:**
  - (a) Start at 1.0 / 0.75 / 0.4 and revisit once scored history exists (**recommended**): this follows R19's near-term emphasis.
  - (b) Equal weights.

---

## Round 3 — Confluence score across modules (D13)

**What the research says**
- **Simple weights work as well as optimised ones.** Equal-weighted linear models predict about as well as optimised ones, and better than intuition (S-new-M11-8, Dawes). Simple averages beat estimated weights because estimating the weights adds error (S-new-M11-8, Smith & Wallis).
- **Fitted weights need very long histories.** None of 14 optimised portfolio models consistently beat 1/N; beating it would need about 3,000 months of data for 25 assets (S-new-M11-9). With 16 names and a few years of data, fitted module weights would be noise.
- **Testing many signals produces false positives.** A new factor needs t > 3.0, not 2.0 (S-new-M11-10). Keep the confluence inputs few and named in advance.

**Worked example (MU, MY profile; illustrative rows and weights are marked)**

| Signal source | Signal | s | Grade | Tier weight (illustrative) | Counted |
|---|---|---|---|---|---|
| M04 | CvD "no slowdown" (illustrative: M04's states are CYCLICAL_TROUGH, CYCLE_PLUS_DAMAGE, STUMBLE, STRUCTURAL_DECLINE and AMBIGUOUS; the "no slowdown" value in M01 rule 3 is not yet defined) | +1 | A | 3 | yes |
| M02 | Capex money flow: Alphabet raised 2026 capex to $195–205B from $180–190B (real, S80; MU is in "HBM & advanced packaging") | +1 | B (call) | 3 | yes |
| R19 card | Revenue above range, 1 of 1 scored (real, Round 2) | +1 | A | 2 | yes |
| M09 | Entry band | missing | — | 1 | no (unbuilt) |
| M02 | Crowding flag on AI infrastructure (illustrative) | −1 | A | 1 | yes |

Confluence = (3·1·1 + 3·0.5·1 + 2·1·1 + 1·1·(−1)) / (3 + 1.5 + 2 + 1) = 5.5 / 7.5 = **+0.73**.

Display: "4 of 5 signals reporting (3 of 4 modules)".

**All cases**
1. **All lead modules report and agree:** a score is shown with its signal vector.
2. **Lead modules disagree in sign:** a review item and no single score (3.3a).
3. **Module not built:** excluded from the denominator, shown as "k of n reporting".
4. **Module built but no signal for this ticker** (e.g. no guidance): missing, never 0.
5. **Signal older than the profile's review cadence:** marked stale and excluded.
6. **Grade C:** shown at weight 0 (3.2a).
7. **Grade B:** weight 0.5.
8. **Two signals sharing one input** (M02 money flow and a future M05 capex signal, both reading `guidance`/`capex_stated`): collapsed into one vote.
9. **`survival_gate` fail:** `no_add`, whatever the score.
10. **`cvd_state = STRUCTURAL_DECLINE`:** exit warning, whatever the score (M01 rules 3–4).
11. **No signals reporting:** no score, shown as "0 of n".
12. **Timeframe switched:** recomputed with that profile's weights; any decision logs the profile.
13. **Continuous module value:** mapped to [−1, 1] by a documented `method`; the raw value is kept in `value`.

**Suggestions**
1. Each module writes a signal of −1, 0 or +1, or a value in [−1, 1] with a documented mapping. The raw value stays in `value`, and `method` names the mapping.
2. **Formula:** confluence = Σ wₘ·gₘ·sₘ / Σ wₘ·gₘ, over reporting, non-stale signals.
   - wₘ = M01 tier weight, equal within each tier. M01 makes fundamentals, moat, capex and money flow lead; ownership medium; analysts low; technicals entry timing. The tiers for R19, crowding and technicals are not yet set by M01.
   - gₘ = evidence weight: A 1.0, B 0.5, C 0.
3. **Gates sit outside the average:** `survival_gate` and `STRUCTURAL_DECLINE`.
4. **M11 writes its own signals** with `module_id = 'M11'` (see Signals out).
5. **No fitted weights until a backtest exists,** and then only with an out-of-sample check (S-new-M11-10).

**Failure modes**

| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Shared inputs | Double counting (M02 money flow and M05 capex on the same rows) | Declare each signal's input source; collapse into one vote |
| Unbuilt module | A 0 dilutes the score | Dropped from the denominator; "k of n" shown |
| Grade C rumours | Inflate the score | Weight 0, still shown |
| Stale signals | An old view counted as current | Excluded beyond the cadence, marked stale |
| One number | Hides disagreement | Vector always shown (D10); sign disagreement goes to review (D8) |
| Fitted weights | Overfit on 16 names (S-new-M11-9, S-new-M11-10) | Tier weights only until an out-of-sample backtest |

**Questions**
- **3.1 Weights:**
  - (a) Equal within M01's lead/medium/low tiers (e.g. 3/2/1), with the owner placing R19, crowding and technicals in a tier (**recommended**): simple weights are as good as fitted ones here.
  - (b) An owner-set number per module.
  - (c) Fitted later by backtest.
- **3.2 Grade C:**
  - (a) Shown at weight 0 (**recommended**): rumours stay visible without moving the score.
  - (b) Weight 0.25.
- **3.3 Lead modules that disagree:**
  - (a) Send to review and show no single score (**recommended**): averaging opposite signs hides the conflict.
  - (b) Always show the score.

---

## Round 4 — Position sizing: Kelly, volatility, conviction, caps (M01 sizing row)

**What the research says**
- **Kelly sizing.** Kelly maximises long-run growth: f* = (μ − r)/σ² in continuous time (S-new-M11-11, Kelly 1956).
- **Full Kelly is very risky in the short term; fractional Kelly keeps much of the growth at much less risk** (S-new-M11-11, MacLean, Thorp & Ziemba 2010).
  - From the growth formula (our derivation, not a quote from the paper): betting c × Kelly yields c(2 − c) of the maximum excess growth. Half-Kelly gives 75% of it at half the volatility.
  - An edge overestimated 2× (c = 2) gives zero excess growth, and more than that gives negative excess growth. With single-stock edge estimates, this error is normal.
- **Volatility targeting: the evidence is mixed.**
  - Inverse-variance scaling raised factor Sharpe ratios in sample (S-new-M11-12, Moreira & Muir).
  - Across 103 equity strategies it did not systematically help, and real-time versions generally earned lower Sharpe ratios (S-new-M11-12, Cederburg et al.).
  - Over 60+ assets it raised Sharpe ratios for equities and credit, and consistently thinned the left tails (S-new-M11-12, Harvey et al. 2018; practitioner journal; index and asset-class results, not single stocks).
  - Conclusion: the robust benefit is fewer extreme losses. Use volatility for a cap, not for timing.
- **Conviction concentration.**
  - Managers' highest-conviction stocks beat the market by about 2.8–4.5% a year (S-new-M11-13, Antón, Cohen & Polk; working paper).
  - Households with concentrated accounts outperformed, especially those with large portfolios and in local and non-S&P 500 stocks (S-new-M11-13, Ivković et al.). Risk-adjusted results are not reported in the abstract.
  - Overconfidence costs returns (S-new-M11-5).
- **The skew argument for caps.**
  - About 4% of stocks created all net wealth, and 58% trailed T-bills (S01).
  - Idiosyncratic risk rose from 1962 to 1997, so more names are needed for the same diversification (S-new-M11-14).
- **Regulatory reference caps** (these are rules, not evidence; S-new-M11-17):
  - US regulated investment companies (IRC §851(b)(3)): at least 50% of assets in positions each ≤ 5% of assets and ≤ 10% of the issuer's voting securities, and at most 25% in any one issuer.
  - UCITS Art. 52: 5% per issuer, which member states may raise to 10%; holdings above 5% may then total no more than 40%.

**Worked example (all numbers illustrative; the formulas are what the build uses)**

| Input | Value | Note |
|---|---|---|
| Portfolio | $200,000 | illustrative |
| Owner per-position cap | 10% | illustrative |
| Risk budget per position | 2% of portfolio a year | illustrative |
| σ, 1 year (MU) | 55% | illustrative; build reads `price_bar` |
| Vol-budget cap | 2% / 55% = **3.64%** | |
| Conviction 4 → 1.25 × base 5% | **6.25%** | illustrative base |
| Owner edge 8%/yr → f* = 0.08 / 0.55² = 0.26; ½-Kelly | **13%**, ceiling only | ≈ 75% of maximum excess growth |
| Theme / shared-key headroom (Round 6) | 4% | illustrative |
| **Size cap shown** | **3.64% (about $7,270), bound by volatility** | the owner decides |

**All cases**
1. **Normal case:** size = the minimum of the caps, each shown with its basis.
2. **Fewer bars than the minimum** (SPCX starts 2026-06-12; check other recent listings in `price_fetch.first_date`): "vol unknown" and the lowest conviction multiplier.
3. **Earnings inside the window:** a gap-risk note.
4. **No owner edge entered:** no Kelly line.
5. **Owner edge entered:** a ½-Kelly ceiling is shown. It never raises the size.
6. **`survival_gate` fail or `STRUCTURAL_DECLINE`:** no adds, whatever the size (M01 rule 3).
7. **Tranche add in a down cycle:** governed by the M01 rule 3 gates. The vol cap does not cut it automatically.
8. **Position already above its cap after a rise:** a warning, no forced trim (D16).
9. **Conviction raised after a ≥ 20% price rise** (illustrative threshold): a logged decision with a note prompt.
10. **Name in several themes or shared keys:** headroom = the minimum over all of them.
11. **Portfolio value not entered:** caps shown in % only.
12. **Options overlay:** sized under its own profile; waits for M12/DS5.

**Suggestions**
1. **Size = the minimum of four caps:**
   - (a) the owner's per-position cap (M01)
   - (b) the vol-budget cap = risk budget ÷ annualised σ
   - (c) the conviction-tier cap = base × multiplier (1: 0.5×, 2: 0.75×, 3: 1×, 4: 1.25×, 5: 1.5×; illustrative)
   - (d) the theme and shared-key headroom (Round 6)
2. **Optional ½-Kelly ceiling,** computed only from an owner-entered expected excess return and horizon, and labelled "needs owner edge".
3. **Gates:** a `survival_gate` fail or `STRUCTURAL_DECLINE` gives `no_add`.
4. **Store the result as a `size_cap` signal.** `method` names the cap that bound; `source_ref` lists the inputs.
5. **Overlays are sized separately.** Options overlays wait for M12.

**Failure modes**

| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Kelly on an estimated edge | Oversizes; a 2× overestimate gives zero excess growth (S-new-M11-11) | Ceiling only, ≤ ½, never the default |
| Realised volatility | Low before shocks and high after crashes, so it shrinks sizes at troughs | Vol sets the cap only; tranche adds follow M01 rule 3 |
| σ with fat tails and gaps | Understates earnings-gap risk | Gap-risk note; 60-day and 1-year windows |
| Conviction | Rises with price (overconfidence, S-new-M11-5) | Changes logged; prompt after a ≥ 20% rise (illustrative) |
| Short history | Unstable σ | Minimum bars, otherwise "vol unknown" and the lowest tier |

**Questions**
- **4.1 Main sizing method:**
  - (a) The minimum of the owner cap, vol budget, conviction tier and theme headroom, with Kelly as a ceiling only (**recommended**): each cap guards a different risk.
  - (b) Conviction tiers only.
  - (c) Fractional Kelly as the primary method.
- **4.2 Volatility window:**
  - (a) Show 60-day and 1-year volatility; the cap uses the larger (**recommended**): the conservative choice when recent calm hides risk.
  - (b) 1-year only.
- **4.3 Conviction multipliers:**
  - (a) 0.5×–1.5× as above (**recommended**): a simple, symmetric starting table.
  - (b) An owner-set table.

---

## Round 5 — Killswitch and exit warnings, per position and shared (D16, R23, M01 rule 4)

**What the research says**
- **Price stop-losses help only when returns trend.** Under a random walk, simple 0/1 stop-loss rules always lower expected return; with momentum they can add value (S-new-M11-15). So the killswitch rests on thesis evidence (milestones, CvD, guidance), and price drawdown is context only. This fits D16.
- **Stocks fall together.** Correlations are much higher on the downside, especially in extreme moves (S-new-M11-16). Positions that share a driver will trip at the same time, so a shared driver needs one switch with portfolio-level exposure, not N separate alerts.
- **Too many alerts get ignored** (S86). Alerts need a cap and deduplication, as in the M02 digest (cap 10 a week, D-M02-10).
- **Kill criteria must be written at entry, before any loss,** to pre-commit against the disposition effect (S-new-M11-3).

**Worked example: shared killswitch `hyperscaler_capex`**

| Input | Value | Source |
|---|---|---|
| Alphabet 2026 capex guidance | $195–205B, raised from $180–190B (Q2 2026 call) | S80 (transcript, grade B until matched) |
| Amazon 2026 capex | ~$220B (call) | S80 |
| Microsoft CY2026 capex | ~$175B (call) | S80 |
| Sum of the three (Alphabet at midpoint) | ≈ $595B | calc; Meta's figure is in S80 but not restated in this pack |
| Linked positions by theme | AI infrastructure: NVDA, MSFT, AMZN, GOOG, META; HBM & advanced packaging: MU, INTC, GFS; Custom silicon & optics: MRVL | `config/themes.toml` |
| Current state | `armed`: the latest change was a raise | code |
| Hit example | Peak sum falls ≥ 10% (owner-set X; illustrative), i.e. to ≤ $535.5B on the three above → one review item: "hyperscaler_capex hit: N positions, Y% of portfolio" | illustrative |

**All cases**
1. **Lowered guidance on a thesis metric:** `warning`, or `hit` if the rule is met.
2. **Guidance withdrawn:** `hit`.
3. **`definition changed`:** blocked, so no trigger.
4. **Milestone slipped twice or slipped with a charge:** `hit` (Question 2.3a).
5. **CvD CYCLE_PLUS_DAMAGE or STRUCTURAL_DECLINE:** `hit`. While M04 is unbuilt, the criterion shows "input missing" and is never armed-and-clear.
6. **`survival_gate` fail:** `hit`.
7. **An 8-K item the owner picked for this thesis** (e.g. 4.02 non-reliance): `hit`.
8. **`owner_rule` free text:** shown, never evaluated.
9. **Grade B from a single source:** `warning` until a second source confirms it (Question 5.3a).
10. **Grade C:** never fires.
11. **Shared key fires:** one review item listing every linked position and the combined exposure.
12. **A spender's own position** (MSFT, AMZN, GOOG, META on `hyperscaler_capex`): direction per D-M02-5 (capex guidance positive for the spender), so a cut counts against it too. The owner can unlink it.
13. **Price drawdown alone:** context only (Question 5.1a).
14. **Cyclical at its trough with a deep drawdown** (the MU 2022–23 case): no warning unless CvD ≠ CYCLICAL_TROUGH or a thesis trigger fires.
15. **Warning dismissed:** a `decision` row with a note. It repeats only if the trigger worsens.
16. **Several criteria fire in the same week:** deduplicated per (criterion, week).
17. **Volume:** kill hits are outside the M02 10-a-week cap.
18. **Event alerts:** bypass the quarterly cadence (M01 rule 6).
19. **Position closed:** its criteria are deactivated. Shared keys stay while any linked position remains.

**Suggestions**
1. **Criterion types**, each evaluated by code and firing `exit_warning` with its source:
   - `guidance_cut`
   - `milestone`
   - `cvd`
   - `survival`
   - `event`
   - `owner_rule` (shown, not evaluated)
2. **Shared killswitch** = a `kill_criterion` row with a `shared_key` that positions link to. Each key needs a measurable rule.
3. **States:** `armed`, `warning` (one input crossed), `hit` (rule met), `acknowledged` (owner decision logged). No automatic trades (D16).
4. **New review kind `m11_kill_hit`:** deduplicated per (criterion, week), outside the M02 cap.

**Failure modes**

| Input or indicator | How it can mislead | Guard |
|---|---|---|
| One noisy input (e.g. a misread call sentence) | Fires many warnings | Fires only on grade A, or on grade B confirmed by a second source; the quote is shown (D21) |
| Accounting change | Mistaken for a cut | `definition changed` blocks it |
| Broad shared key ("AI demand") | Can't be checked | Each key needs a measurable rule |
| Repeated warnings | Ignored (S86) | Dismissal is logged; a repeat fires only if the trigger worsens; dedupe |
| Price-only kill on a cyclical | Sells at the bottom (S-new-M11-15) | Drawdown is context; a warning needs CvD ≠ CYCLICAL_TROUGH or a thesis trigger |
| Correlated positions | N separate alerts understate the joint hit (S-new-M11-16) | One shared item with the combined exposure |

**Questions**
- **5.1 Price drawdown in killswitches:**
  - (a) Context only, shown beside the fundamental triggers (**recommended**): price stops hurt without momentum (S-new-M11-15).
  - (b) A price stop as its own trigger.
- **5.2 Shared-killswitch trigger:**
  - (a) The sum of named spenders' current-year capex guidance falls ≥ X% from its peak, with the owner setting X (**recommended**): one cut can be a reallocation.
  - (b) Any one spender cutting.
- **5.3 Evidence that may fire a hit:**
  - (a) Grade A, or grade B confirmed (**recommended**): this stops a single misread firing.
  - (b) Any grade, labelled.

---

## Round 6 — Theme and shared-killswitch exposure caps; hurdle tracking (R23, R5)

**What the research says**
- **Crowded themes have done badly after the crowd arrives.** Specialized, largely thematic, ETFs lost about 30% risk-adjusted over their first five years, which the authors attribute to overvaluation at launch (S90). M02 already raises a crowding flag (D-M02-57).
- **Concentration in one theme is concentration in one factor.** Downside correlations rise (S-new-M11-16), so a theme cap should be stricter than a single-name cap, and a name in several themes counts in each.
- **Hurdle data** (S-new-M11-20):
  - S&P 500 total return 2025: 17.88% (YCharts, secondary; 17.9% per RBC).
  - The primary S&P DJI page gives the price return, 16.39%.
  - December 2025 CPI-U year on year: 2.7% (HL, secondary; BLS not checked).
- **CPI series** (S-new-M11-20):
  - FRED `CPIAUCSL` is the BLS CPI-U, seasonally adjusted; the latest value is Aug 2026 = 334.131.
  - For year-on-year hurdles, the not-seasonally-adjusted `CPIAUCNS` is the usual choice.
  - The M2 → PCE lag (S19) is context only.
- **Total-return proxy:** Tiingo adjusted close for SPY, with dividends reinvested through `adjClose` (S69). It fits the 500-symbols-a-month limit (S68).

**Worked example**

| Item | Value | Source |
|---|---|---|
| S&P 500 TR 2025 | 17.88% | YCharts (secondary); S&P DJI primary gives the price return, 16.39% |
| CPI-U Dec 2025 YoY | 2.7% | HL (secondary); BLS to verify |
| Stretch hurdle, compounded | 1.1788 × 1.027 − 1 = 21.06% | calc |
| Stretch hurdle, added | 20.58% | calc |
| Position return 2025 | 25.0% | **illustrative** |
| hurdle_excess / stretch_excess | +7.1 pp / +3.9 pp | calc on the illustrative row |
| Theme "HBM & advanced packaging": MU 6%, INTC 3%, GFS 2% | 11% vs a 25% cap → headroom 14% | **illustrative** weights; membership real (`themes.toml`) |

**All cases**
1. **Name in several themes** (INTC and GFS are in both "HBM & advanced packaging" and "Foundry & onshoring"): full weight in each (Question 6.2a). Totals are not added across themes.
2. **Membership proposed, not active:** shown as "possible exposure", not counted.
3. **A new add would breach a cap:** headroom 0, so the size cap is 0, with the reason.
4. **Breach caused by price drift:** a warning and an `m11_cap_breach` item. No forced trade.
5. **Shared-key exposure above its cap:** same handling as a theme breach.
6. **Lot bought mid-year:** hurdle time-weighted from `acquired_on` to today, or to the sale date.
7. **Partial sale:** hurdle computed per lot.
8. **Dividends:** via `adjClose` / `div_cash`.
9. **Lot held < 1 year:** shown, with a noise warning.
10. **Latest CPI month not yet published:** use the last published month, labelled.
11. **SPY vs the S&P 500 TR index:** labelled "SPY proxy" (ETF fee and tracking error apply).
12. **No FRED key:** the stretch hurdle is missing, never zero.

**Suggestions**
1. **`exposure_cap` table:** kind `position` | `theme` | `shared_kill`, key, max %, `set_by` owner. Suggested defaults (the owner sets the real numbers):
   - theme 25%, by analogy with the §851 25% single-issuer ceiling. This is an analogy, not evidence for a theme cap.
   - shared killswitch 35% (illustrative).
2. **Exposure view:**
   - per theme and per shared key: market value %, number of names, crowding flag, killswitch state
   - a breach gives a warning and a review item, never a forced trade
3. **Headroom for new size:** Round 4 cap (d) = the minimum over the name's themes and shared keys of (cap − current exposure).
4. **Hurdle signals per position and per lot:**
   - `hurdle_excess` vs SPY TR, and `stretch_excess` vs TR + CPI, over the same dates
   - both grade A, with `source_ref` = Tiingo SPY + the FRED series id
5. **Scheduling:** SPY joins the existing Tiingo rotation and CPI is fetched monthly, both in the background logon refresh (D-M02-12).

**Failure modes**

| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Multi-theme names | Exposure understated if split across themes | Full weight in each theme; totals not additive |
| Stale or proposed membership | Phantom or missing exposure | Only `active` counts; proposed shown apart |
| Calendar-year hurdle vs a mid-year lot | Period mismatch | Computed over each lot's own dates |
| "TR + CPI" | Added and compounded differ (about 0.5 pp in 2025) | Method chosen (Question 6.1) and labelled |
| SPY proxy | Drifts from the index | Labelled "SPY proxy" |
| Short holding periods | Hurdle comparison is noise | Shown with a warning (M01 lot awareness) |

**Questions**
- **6.1 Stretch hurdle arithmetic:**
  - (a) Compounded, (1 + TR)(1 + CPI) − 1 (**recommended**): returns compound, so the real hurdle does too.
  - (b) Added, TR + CPI.
- **6.2 Theme cap counting:**
  - (a) Full weight in every active theme a name belongs to (**recommended**): theme drawdowns hit the whole name.
  - (b) Weight split across themes.
- **6.3 CPI source:**
  - (a) A free FRED API key (`FRED_API_KEY` in `.env`, added by the owner), series `CPIAUCNS` (**recommended**): the keyless CSV pattern is not confirmed.
  - (b) Try the keyless CSV first, falling back to (a).

---

## Signals out

All signals use `module_id = 'M11'` (D13).

| Signal | Type / range | Meaning | MY | PT | ST |
|---|---|---|---|---|---|
| `confluence` | [−1, 1] or none | Weighted mean of reporting module signals | ✓ | ✓ | ✓ (profile weights differ) |
| `modules_reporting` | k / n | Coverage behind the score | ✓ | ✓ | ✓ |
| `disagreement` | bool | Lead modules differ in sign; goes to review | ✓ | ✓ | ✓ |
| `guidance_credibility` | hit rate, signed bias, mean \|error_hw\| per metric family | Company track record (R19) | ✓ | ✓ | info |
| `milestone_state` | open / hit / missed / slipped / withdrawn / unscorable | R4 status per milestone | ✓ | ✓ | info |
| `thesis_state` | early / on_track / review / exit_warning | "Early vs wrong" | ✓ | ✓ | ✓ |
| `exit_warning` | criterion id, state (armed / warning / hit / acknowledged) | Killswitch, per position or shared (D16) | ✓ | ✓ | ✓ |
| `no_add` | bool | Survival fail or STRUCTURAL_DECLINE | ✓ | ✓ | ✓ |
| `size_cap` | % of portfolio, binding cap in `method` | Maximum size, not a recommendation | ✓ | ✓ | ✓ |
| `exposure_breach` | theme or shared key, % over cap | R23 cap breach | ✓ | ✓ | ✓ |
| `hurdle_excess` / `stretch_excess` | pp | Excess return vs SPY TR and TR + CPI | ✓ | ✓ | info (short periods are noise) |

Example: `{ticker: "BA", module_id: "M11", signal: "milestone_state", value: "slipped", timeframe: "MY", evidence_grade: "A", source_ref: "8-K EX-99.1 0001628280-25-046915", method: "event milestone v3, 2 slips", as_of: "2025-10-29"}`

## Build parts (proposal)

Each part is one conversation at Medium effort, with fixture tests and one live check run by the owner. All schema changes go in the next free engine migration (after 0026).

| Part | Scope | Depends on | Live check |
|---|---|---|---|
| 1 | `thesis`, `milestone`, `kill_criterion` tables; lot and position entry; `decision` logging from the UI; "Make milestone" review action (`m11_milestone`) | 0001 tables | Turn the open Boeing 777-9 review item into a milestone on the real DB; print the rows |
| 2 | `guidance_score`, credibility card, `withdrawn` detection, first-guide walk, non-GAAP stated actuals; reuse `periods.py` and `guided.py`; shared with M04 S1.7 | Part 1 (milestone links) | Score MU FQ1 FY2026; confirm Micron's XBRL revenue concept |
| 3 | SPY proxy, FRED CPI, realised volatility and drawdown, hurdle signals per lot | Part 1; owner adds `FRED_API_KEY` | Fetch SPY + CPIAUCNS; print the hurdles for one lot |
| 4 | `exposure_cap`, exposure view, headroom, `size_cap` (minimum of caps, ½-Kelly ceiling), `m11_cap_breach` | Parts 1, 3 | Size cap for MU on real prices and themes |
| 5 | Kill-criterion evaluation, shared key `hyperscaler_capex`, states, `m11_kill_hit` with dedupe outside the M02 cap | Parts 1, 2; M04 inputs show "missing" until M04 is built | Evaluate on the real ledger; expect `armed` |
| 6 | Signal writers (M02, R19, M11), normalisation, confluence, gates, `m11_disagreement`, vector display | Parts 2, 4, 5; M04 for CvD and the survival gate | Confluence for the 16 tickers with k-of-n |

## Known gaps
1. The Williams (1996) abstract is unread; the citation is confirmed only through a citing paper. The BLS primary page for December 2025 CPI is unchecked.
2. The Micron FQ1 FY2026 actuals come from Nasdaq and search summaries, not the SEC 8-K. Micron's XBRL revenue concept is unchecked.
3. Boeing's 2025 target (April 2022) comes from a secondary source. The reason for the Q4 2024 $891M 777X charge is unchecked.
4. Every volatility, weight and portfolio figure is illustrative, because Claude cannot read `data\`. Recent-listing histories other than SPCX are unchecked.
5. M04 does not yet define a "no slowdown" CvD value (M01 rule 3), which the Round 3 example uses. M04's S1.7 overlaps Round 2.
6. M01 has not placed R19, crowding or technicals in a weight tier.
7. Non-GAAP stated actuals, the SPY proxy, FRED CPI and the owner lots import need new rows in DATA_SOURCES.md. DS2 (Tesla KPIs), DS3 (growth-rate guidance) and DS7 (prior-year risk factors) limit milestone scoring. DS5 blocks sizing of options overlays.
8. The FRED key is not in `.env`, and the keyless CSV pattern is unconfirmed.
9. The broker CSV format is unknown until the owner names a broker.
10. Meta's 2026 capex figure (S80) is not restated here, so the `hyperscaler_capex` sum covers three of four spenders.

## New sources
- **S-new-M11-1** Hutton, A., Miller, G. & Skinner, D. (2003), "The Role of Supplementary Statements with Management Earnings Forecasts", Journal of Accounting Research 41(5):867–890. https://ideas.repec.org/a/bla/joares/v41y2003i5p867-890.html
- **S-new-M11-2** Richardson, S., Teoh, S. H. & Wysocki, P. (2004), "The Walk-down to Beatable Analyst Forecasts: The Role of Equity Issuance and Insider Trading Incentives", Contemporary Accounting Research 21(4):885–924. https://ideas.repec.org/a/wly/coacre/v21y2004i4p885-924.html
- **S-new-M11-3** Disposition effect:
  - Shefrin, H. & Statman, M. (1985), "The Disposition to Sell Winners Too Early and Ride Losers Too Long", Journal of Finance 40(3):777–790. DOI 10.1111/j.1540-6261.1985.tb05002.x
  - Odean, T. (1998), "Are Investors Reluctant to Realize Their Losses?", Journal of Finance 53(5):1775–1798. https://faculty.haas.berkeley.edu/odean/papers/disposition/disposition.html
- **S-new-M11-4** Mitchell, D., Russo, J. E. & Pennington, N. (1989), "Back to the future: Temporal perspective in the explanation of events", Journal of Behavioral Decision Making 2(1):25–38. https://colab.ws/articles/10.1002%2Fbdm.3960020103 (outcome certainty, not time framing, drives the effect; the "30%" figure is unverified)
- **S-new-M11-5** Barber, B. & Odean, T. (2000), "Trading Is Hazardous to Your Wealth", Journal of Finance 55(2):773–806. https://ideas.repec.org/a/bla/jfinan/v55y2000i2p773-806.html
- **S-new-M11-6** Forecaster track record:
  - Williams, P. (1996), "The relation between a prior earnings forecast by management and analyst response to a current management forecast", The Accounting Review 71(1):103–115 (citation confirmed via a citing paper; abstract not read)
  - Kala, Shailer & Wilson (2025, online 2024), "Are Individual Analysts' Responses to Management Forecasts Conditioned by Managers' Forecasting Track Records?", European Accounting Review 34(4):1621–1655, DOI 10.1080/09638180.2024.2413001. https://ideas.repec.org/a/taf/euract/v34y2025i4p1621-1655.html
- **S-new-M11-7** Brier, G. W. (1950), "Verification of forecasts expressed in terms of probability", Monthly Weather Review 78(1):1–3. https://repository.library.noaa.gov/view/noaa/33800/noaa_33800_DS1.pdf
- **S-new-M11-8** Simple weights:
  - Dawes, R. M. (1979), "The robust beauty of improper linear models in decision making", American Psychologist 34(7):571–582. https://www.cmu.edu/dietrich/sds/docs/dawes/the-robust-beauty-of-improper-linear-models-in-decision-making.pdf
  - Smith, J. & Wallis, K. F. (2009), "A Simple Explanation of the Forecast Combination Puzzle", Oxford Bulletin of Economics and Statistics 71(3):331–355. https://econpapers.repec.org/RePEc:bla:obuest:v:71:y:2009:i:3:p:331-355
- **S-new-M11-9** DeMiguel, V., Garlappi, L. & Uppal, R. (2009), "Optimal Versus Naive Diversification: How Inefficient is the 1/N Portfolio Strategy?", Review of Financial Studies 22(5):1915–1953. https://ideas.repec.org/a/oup/rfinst/v22y2009i5p1915-1953.html
- **S-new-M11-10** Harvey, C., Liu, Y. & Zhu, H. (2016), "…and the Cross-Section of Expected Returns", Review of Financial Studies 29(1):5–68. https://www.nber.org/papers/w20592
- **S-new-M11-11** Kelly sizing:
  - Kelly, J. L. (1956), "A New Interpretation of Information Rate", Bell System Technical Journal 35(4):917–926. https://archive.org/details/bstj35-4-917
  - MacLean, L., Thorp, E. & Ziemba, W. (2010), "Long-term capital growth: the good and bad properties of the Kelly and fractional Kelly capital growth criteria", Quantitative Finance 10(7):681–687. https://escholarship.org/content/qt5mr5k8qj/qt5mr5k8qj.pdf
- **S-new-M11-12** Volatility management:
  - Moreira, A. & Muir, T. (2017), "Volatility-Managed Portfolios", Journal of Finance 72(4):1611–1644. https://www.nber.org/papers/22208
  - Cederburg, S., O'Doherty, M., Wang, F. & Yan, X. (2020), "On the performance of volatility-managed portfolios", Journal of Financial Economics 138:95–117. https://www.lehigh.edu/~xuy219/research/COWY.pdf
  - Harvey, C. et al. (2018), "The Impact of Volatility Targeting", Journal of Portfolio Management 45(1):14–33. https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf
- **S-new-M11-13** Conviction concentration:
  - Antón, M., Cohen, R. & Polk, C., "Best Ideas" (working paper, April 2021). https://personal.lse.ac.uk/polk/research/BestIdeas.pdf
  - Ivković, Z., Sialm, C. & Weisbenner, S. (2008), "Portfolio Concentration and the Performance of Individual Investors", JFQA 43(3):613–655. https://ideas.repec.org/a/cup/jfinqa/v43y2008i03p613-655_00.html
- **S-new-M11-14** Campbell, J., Lettau, M., Malkiel, B. & Xu, Y. (2001), "Have Individual Stocks Become More Volatile?", Journal of Finance 56(1):1–43. https://www.nber.org/papers/w7590.pdf
- **S-new-M11-15** Kaminski, K. & Lo, A. (2014), "When do stop-loss rules stop losses?", Journal of Financial Markets 18:234–254. https://dspace.mit.edu/handle/1721.1/114876
- **S-new-M11-16** Ang, A. & Chen, J. (2002), "Asymmetric correlations of equity portfolios", Journal of Financial Economics 63(3):443–494. https://ideas.repec.org/a/eee/jfinec/v63y2002i3p443-494.html
- **S-new-M11-17** Diversification rules:
  - 26 U.S.C. §851(b)(3). https://www.law.cornell.edu/uscode/text/26/851
  - Directive 2009/65/EC (UCITS) Art. 52, UK retained copy. https://www.legislation.gov.uk/eudr/2009/65/article/52/data.htm
- **S-new-M11-18** Boeing 777-9 schedule:
  - Q3 2025 8-K EX-99.1. https://www.sec.gov/Archives/edgar/data/12927/000162828025046915/a202509sep308kprex991.htm
  - FY2024 10-K. https://www.sec.gov/Archives/edgar/data/12927/000001292725000015/ba-20241231.htm
  - AirInsight (secondary). https://airinsight.com/boeing-pauses-777x-production-and-delays-first-delivery-until-2025/
- **S-new-M11-19** Micron guidance vs actual:
  - FQ4 FY2025 8-K EX-99.1. https://www.sec.gov/Archives/edgar/data/723125/000072312525000024/a2025q4ex991-pressrelease.htm
  - FQ1 FY2026 release (Nasdaq). https://www.nasdaq.com/press-release/micron-technology-inc-reports-results-first-quarter-fiscal-2026-2025-12-17
- **S-new-M11-20** Hurdle data:
  - S&P DJI, Market Attributes, December 2025. https://www.spglobal.com/spdji/en/documents/commentary/market-attributes-us-equities-202512.pdf
  - YCharts, S&P 500 total return, annual (secondary). https://ycharts.com/indicators/sandp_500_total_return_annual
  - RBC (secondary). https://ca.rbcwealthmanagement.com/weatherill-wealth/blog/4722507-SP-500-Stats-A-Lot-of-Bull
  - FRED CPIAUCSL. https://fred.stlouisfed.org/series/CPIAUCSL
  - Hargreaves Lansdown (secondary). https://www.hl.co.uk/news/the-us-ended-2025-with-steady-but-elevated-inflation-in-december
