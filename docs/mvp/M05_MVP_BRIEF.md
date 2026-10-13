# M05 Capex & future spend — MVP brief
Updated 2026-10-13 · Source: docs/M05_DESIGN_PACK.md (research) · Status: for owner decision (one sitting)

Research signals, not advice. † = starting value, uncalibrated. Every signal is labelled "hypothesis, not backtested".

## Purpose in one paragraph
M05 asks two things of each company: is its capex going into real demand, and what has it committed to spend (and customers committed to it)? It serves outline "CAPEX and Future Spend" 1–5 and "Follow the money" 1.

Binding revisions:
- **R9:** fabless companies are read on purchase obligations and prepayments; capex is still monitored for new offerings (that monitor is deferred, S5.4).
- **A1:** RPO, purchase obligations and ≥10% customers lead.
- **D-M04-6 (amends A2):** M04 owns the capex split, depreciation by default; **M05 owns growth capex × ROIC.**
- **D-M04-42, -43, -54, -64:** M04 owns the ≥10% customer store and the CvD capex rows; M05 supplies only the D-M04-64 pointer view (M04_BUILD_LOG notes for M05).
- **D-M02-5:** capex guidance is positive for the spender and its suppliers; weighting "revisited later" (Q05.7).

Also D8, D10, D13, D14, D16.

**Against the outline** (the pack predates it in the repo):
- The pack led with peak risk. Outline 2 calls capex "rising into a demand wave" bullish, and outline 5 says capex "without demand destroys value". So the MVP's lead signal tests capex against demand, and peak risk becomes Q05.4.
- The pack never paired growth capex with ROIC. Outline 3 and the binding revision require it, so the MVP adds it.
- Outline 1 (capex that builds a moat, with a track record) needs M06. The MVP shows M04's capex guidance outcomes as the track record.

## Data already stored that the MVP uses
| Need | Where | Gap |
|---|---|---|
| Total capex, depreciation (or D&A) rung, growth, marks | `capex_split` (0030; last 8 FYs only), `financials/capex.py` (longer window on request) | — |
| M02 own-definition capex (shown beside) | `moneyflow/actuals.py` `actual_for` | MU incentive netting not mapped (gross) |
| ROIC (M04 S6.5; display only, no M04 ROIC signal), `rev_yoy` | `financials/trends.py` (`roic`, 8-FY table) | — |
| RPO and its YoY change vs the company's own median | `rpo` concept, `moneyflow/views.py` `rpo()` | Not in the CY2026Q2I frame: AMZN, META, AAPL, INTC, MRVL, GFS |
| Contract liabilities (deposits) | `fact`; `contract_liabilities` (current only) in `EXTRA_CONCEPTS`, already read by M04 Part 6 `deferred_rev_gap` | Total and noncurrent tags are in `fact` but unmapped (mapping is code only, 0 requests) |
| Purchase obligations, XBRL | `fact` (all companyfacts tags; since M04 7a the instance read also keeps non-dimensional extension facts) | `PurchaseObligation`, `Unrecorded…` not mapped |
| Purchase obligations, text | corpus `passage` (latest 10-K and 10-Q, new filings, 2 prior annual reports per DS7); `financials/text.py` | About 3 years of text only (**new gap**: quarterly text history) |
| ≥10% customers | `fact_dim` (0035), `units_view.major_customers` | M04 owns the store (D-M04-42, -43) |
| Capex guidance, OCF ÷ capex | `moneyflow/guided.py`, `allocation.Window.ocf_cover` | — |
| CvD state | M04 8a | Not built → "missing: CvD not built" |

No new fetches.

Gaps the MVP leaves for later become **new gaps** in DATA_SOURCES (DS numbers assigned at build):
- NVDA prepaid supply balances (check `fact` first: extension tags may already be stored by the 7a instance read, 0 requests);
- MU incentive tag (same check);
- AWS backlog wording;
- Meta's lease/commitment overlap;
- SPCX and GFS commitment taxonomies;
- ASC 440 (login-gated, unverified).

## MVP signals (4)
D13 rows per D-M04-9: `cik` key, one row per timeframe, `value` for the number and `value_text` for the state, `as_of` = newest input's filing date, `source_ref` = newest accession "+N", inputs in `method`, `evidence_grade` = weakest deciding input. Missing (RPO untagged, MSTR/ETV "not applicable (<tag>)", no depreciation or D&A) = both empty and `method` "missing: <reason>", never 0. ✓ = may carry weight once D13 weights exist; info = 0.

| Signal | value / value_text | Meaning | Inputs | MY | PT | ST | Grade |
|---|---|---|---|---|---|---|---|
| `capex_demand` | capex ÷ depreciation; BUILD_INTO_DEMAND / AHEAD_OF_DEMAND / CUTTING / MAINTENANCE / STEADY / INSUFFICIENT_HISTORY | Capex into demand? (outline 2, 5) | `capex_split` rows; prior-8-FY median (`capex.py` with a 9-year window: `capex_split` keeps only 8); `rev_yoy`; RPO and contract-liability YoY; capex ÷ revenue vs own 3-yr average | ✓ (info for fabless/outsourced, R9) | ✓ (same) | info | weakest input (A) |
| `growth_capex_roic` | ROIC; ACCRETIVE / DILUTING / MAINTENANCE_ONLY / not_meaningful / INSUFFICIENT_HISTORY | Growth capex earning its return? (outline 3–4) | growth ÷ total from `capex_split`; `trends.roic` now and 3 FYs earlier (8-FY table) | ✓ (info for fabless/outsourced) | info | info | A |
| `bookings_cover` | RPO ÷ TTM revenue (years); RISING / FLAT / FALLING / short_history | "Follow the bookings" (outline 5, A1) | `rpo`, TTM revenue; deposits and ≥10% customers shown beside, never added | ✓ | ✓ | info | A |
| `commitment_cover` | commitments ÷ TTM denominator (years); RISING / FLAT / FALLING / short_history | Committed future spend (R9, A1) | `future_commitment` (XBRL per tag + text quotes); numerator and denominator per Q05.3 | ✓ fabless/outsourced, else info | same | info | A (tag or verified quote) |

**`capex_demand`**, first match wins:
1. **AHEAD_OF_DEMAND:** capex ÷ revenue > 1.5× its own 3-yr average while revenue falls (= D-M04-64, so M04's Q2 pointer lands here), or expanding while TTM revenue falls and no bookings line rises.
2. **BUILD_INTO_DEMAND:** expanding (capex ÷ depreciation above its own 8-FY median, capex YoY > 0) while revenue or a bookings line rises.
3. **CUTTING:** capex YoY ≤ −20%†.
4. **MAINTENANCE:** ratio 0.8–1.2†.
5. **STEADY:** otherwise.

Rule 1's first test needs only 3 prior FYs (as D-M04-64) and runs first; the other states need 8 prior FYs of capex ÷ depreciation on one rung, else INSUFFICIENT_HISTORY. A `definition_changed` year is not scored (D-M04-3). Current-year guidance (M02) goes in `method`, unscored.

**`growth_capex_roic`:**
- Growth share < 25%† → MAINTENANCE_ONLY.
- Else ACCRETIVE if ROIC ≥ its value 3 FYs earlier, DILUTING if more than 3 pp† lower, and ACCRETIVE with a "flat" mark between.

**Covers:** ±10%† YoY change sets RISING or FALLING; no point a year earlier → short_history.

## Worked example
**Micron** ($M, FY; trimmed companyfacts in `tests/fixtures/m04/`; depreciation rung):

| FY | Capex | Depr. | Capex ÷ depr. | Capex YoY | Rev. YoY | Growth share | `capex_demand` |
|---|---|---|---|---|---|---|---|
| 2022 | 12,067 | 7,030 | 1.72 | +20.3% | +11.0% | 41.7% | BUILD_INTO_DEMAND |
| 2023 | 7,676 | 7,670 | 1.00 | −36.4% | −49.5% | 0.1% | CUTTING (capex ÷ revenue 49.4% = 1.30× its 3-yr average, under D-M04-64's 1.5×, so no M04 pointer) |
| 2024 | 8,386 | 7,700 | 1.09 | +9.2% | +61.6% | 8.2% | MAINTENANCE |
| 2025 | 15,857 | 8,280 | 1.92 | +89.1% | +48.9% | 47.8% | BUILD_INTO_DEMAND |
| 2026 | 30,712 | 9,420 | **3.26** | +93.7% | +256.3% | 69.3% | BUILD_INTO_DEMAND |

- **FY2026:** the median of the prior 8 FYs (2018–25) is 1.68, so 3.26 is the window's high. Medians behind the other rows: 1.61 (FY2022), 1.68 (FY2024), 1.56 (FY2025), all from the fixture's FY2012–26 facts. Note the pack's D&A ratio is 3.23; the depreciation rung gives 3.26.
- **Deposits:** contract liabilities $13.0B vs $169M a year earlier. Of that, $12.75B is take-or-pay deposits, repayable 2029–31 and price-banded, shown as "repayable, not revenue".
- **ROIC:** FY2026 `growth_capex_roic` depends on ROIC vs FY2023. The engine computes it; no figure is in the docs (illus.).

**Intel** (pack, primary):
- Capex ÷ revenue went 23.7% → 39.4% → 47.5% → 45.1% (2021–24) while revenue fell from $79.0B to $53.1B.
- In 2023 capex ÷ revenue was 1.75× its 3-yr average (M04_BUILD_LOG Part 8a expected reading; R6 brief) → AHEAD_OF_DEMAND (warning). The trimmed INTC fixture holds capex only for FY2022–25, so it cannot reproduce this (see Part 1 fixtures).
- 2022 split: 24,844 / 11,128, a growth share of 55%.

**Microsoft FY2025 → FY2026:**
- RPO went $375B → $684B against revenue $281.72B → $331.84B, so `bookings_cover` went 1.33 → 2.06 (+55%) → RISING.
- Capex $115,948M ÷ depreciation $34,300M = 3.38 (FY2025 2.93), with revenue +17.8% → BUILD_INTO_DEMAND *(illustrative: needs 8 prior FYs of `Depreciation`; the fixture holds 2, and the pack found no MSFT D&A tag, so the live read may be INSUFFICIENT_HISTORY)*.
- Caveat: the $233B one-quarter RPO step is concentrated. Press reports put about 45% of Microsoft's *commercial* RPO with OpenAI (grade B, M04 pack S-new-r5-9; Microsoft's own wording not read). M04's customer row (7b) is deferred, so the MVP shows only `major_customers`; the OpenAI share is not stored.

**NVIDIA** (R9, fabless; text figures):

| As of | Commitments | TTM cost of revenue | `commitment_cover` |
|---|---|---|---|
| 2026-01-25 | $95.2B (10-K) | $62.48B | 1.52 yrs |
| 2026-07-26 | $279B (10-Q) | $76.73B | 3.64 yrs, short_history |

- **XBRL vs text:** the `PurchaseObligation` tag stops at $45.77B (2025-07-27). An XBRL-only read is stale and about 6× low. The year-earlier point is that tag, a different series, so the text cover reads short_history; the tag line is shown beside across a labelled break, not compared.
- **Schedule:** $92B is due in the rest of FY2027 and $87B in FY2028.
- **Cancellable:** NVIDIA's "cancelable, rescheduled, or adjustable" wording sets the cancellable flag.

## Cases the rules must handle
1. Price-driven revenue (memory) makes capex ÷ revenue call the trough a peak (MU FY2023 49.4%). Guard: capex ÷ depreciation leads, and MU's FY2023 cut reads CUTTING, not a flag.
2. Capex into falling revenue (INTC): AHEAD_OF_DEMAND, the same test as D-M04-64.
3. Boom peak (MU FY2026 3.26×) reads BUILD_INTO_DEMAND, but a competitive-industry peak can destroy value (S-new-M05-4; weaker in oligopolies, R8) → Q05.4.
4. Debt-funded capex reads as conviction, and a structural decliner keeps spending (Intel). Guard: OCF ÷ capex (D-M02-31) and the CvD state (Q05.7).
5. Capex tag switch in the window (NVDA FY2010–12, `capex_split.definition_changed`): that year is not scored (D-M04-3). Microsoft's 2026 lease reclassification changes M02's own-definition capex and guidance, not the PP&E-tag series: labelled beside (D-M02-29), still scored.
6. Depreciation untagged → D&A rung (marked); the rung never mixes inside the window, so a short series reads INSUFFICIENT_HISTORY (MSFT may be one). Both missing → "not split", and `growth_capex_roic` is missing.
7. Useful-life change (INTC 2023 −29.5%) and the proxy's bias (low after asset lives shorten, high after a wave): the capex_split marks are carried.
8. ROIC:
   - invested capital ≤ 0 → not_meaningful;
   - pretax ≤ 0 → NOPAT = operating income, labelled;
   - an acquisition year (AMD–Xilinx) inflates invested capital → M04's acquisition flag goes in `method`.
9. Fewer than 8 FYs (SPCX, INFQ after the de-SPAC, RIVN) → INSUFFICIENT_HISTORY.
10. Fabless (NVDA, MRVL): commitments lead and capex is info (R9). Channel unset: every gauge shown, `commitment_cover` info only.
11. Tag stops (NVDA): the text value is used, with the series break labelled. Text-only names (TSLA, MU, MSFT, AMZN, MRVL, GFS) with nothing found → missing.
12. Same tag, other meaning (Meta's `Unrecorded…` = leases not yet commenced): concepts kept per tag, labelled by the quote.
13. Overlap unstated (Meta's leases vs its $349.31B): never summed. Signed after the period (Meta's July 2026 leases, about $68B): a separate dated line.
14. "Cancelable / adjustable" wording: flag shown, amount "as stated". XBRL and text more than 5%† apart: both shown, with a mark.
15. RPO untagged → missing row "missing: RPO not tagged", never 0. Expedients differ across companies (S79), so the company's own history only.
16. One counterparty dominates RPO (MSFT/OpenAI): M04's ≥10% customers shown beside it; a counterparty share outside the filings waits for M04 7b (deferred).
17. Repayable, price-banded deposits (MU): a separate line, never revenue or RPO. A contract-liability jump with no deposit text: a mark only.
18. Backlog with cancellations (BA): RPO only in the MVP.
19. Off-calendar fiscal years (MU, NVDA, MSFT): own labels; TTM from the company's own series.
20. MSTR, ETV, INFQ shell years: not_applicable via the M04 tags. GFS 20-F: IFRS tags; commitment taxonomy unchecked.
21. Current-year guide (TSLA "more than $25B" vs $8.53B): shown, not scored.

## Deferred to the tuning phase
- **Outline CAPEX 1 (capex that builds a moat, proven track record):** the moat judgment waits for M06; the MVP's proxies are `growth_capex_roic` and M04's capex guidance outcomes.
- **Counterparty share of RPO (MSFT/OpenAI):** needs M04 7b's customer row (deferred) or an owner entry (grade B).
- **Engine-proposed channel, `m05_model` review (S1.2):** the owner file replaces them.
- **PEAK_RISK and the industry wave (S4.1–4.2):** need confirmed peer sets (7 open) and M06's oligopoly flag.
- **`commitment_risk` (S2.5):** an M04 addition (Q05.8).
- **Parsed schedules, `m05_commit_gap`, prepaid supply (S2.3, S2.6):** the MVP shows the quote instead.
- **M02 rung L4 order-flow matching (pack Q2.1):** `future_commitment` is built for it.
- **`rpo_step` alert, 12-month RPO share, BA/AWS backlog text (S3.1, S3.3):** need wording parsers.
- **Customer store (Q3.4), Greenwald/A2 (Round 6):** settled by M04 (D-M04-42, -43, -6).
- **`capex_execution` and half-year/quarter guide periods (S5.1–5.2):** need ≥ 3 years of seasonality and an M02 change.
- **Capex guidance record (S5.3):** `guidance/record.py` holds it; R19 weighting belongs to M11.
- **`capex_new_offering` (S5.4):** a grade-C review.
- **Micron incentive netting (S6.3):** an M02 recipe change.
- **Prior-10-Q fetch for text history (about 50 requests, estimate: 16 companies × 3):** decide after the first log.
- **Calibration of all † values.**

## Questions for the owner
**Q05.1 Spend channel (for R9 and the Q05.3 denominator)**
- (a) *Recommended.* An owner-edited `config/m05_channels.toml` that M04's loader ignores. Pre-filled:
  - NVDA, MRVL: fabless;
  - AAPL: outsourced;
  - MU, INTC, GFS: fab_owner;
  - META, MSFT, AMZN, GOOG: hyperscaler;
  - BA: long_cycle;
  - TSLA, RIVN, SPCX, INFQ: manufacturer;
  - MSTR, ETV: n/a.

  Why: a one-time edit with no review kind, and M04's file takes only its six tags (D-M04-8; M04_BUILD_LOG notes).
- (b) An engine rule (capex ÷ revenue < 5% → fabless) plus an `m05_model` review.
- (c) No channel.

**Q05.2 Source of commitment amounts**
- (a) *Recommended.* XBRL per tag, never merged, plus a narrow text finder on stored 10-K/10-Q MD&A and notes: stated total, category, cancellable wording and a verified quote, with 0 requests. Why: NVDA's current figures are text-only, and 6 names have no tag (S-new-M05-6, -7, -10).
- (b) XBRL only, plus a list of quotes for the owner.
- (c) Defer `commitment_cover`.

**Q05.3 Numerator, denominator, leases**
- (a) *Recommended.*
  - Numerator: the stated supply-and-capacity (fabless, outsourced) or PP&E (others) total; cloud, investment and other categories shown beside, never added (NVDA's FY2026 note lists cloud $27B, investments $11.4B, other $3.4B beside $95.2B).
  - Denominator: TTM cost of revenue for fabless and outsourced, TTM capex for the rest, both in `method`.
  - Leases not yet commenced: a separate line, never summed.

  Why: the commitment substitutes for those costs, mixed scopes inflate the cover, and Meta does not state the overlap (S-new-M05-6, -8).
- (b) Revenue for everyone.
- (c) Raw amounts only.

**Q05.4 `capex_demand` lead metric and peak risk**
- (a) *Recommended.* Capex ÷ depreciation vs the company's own 8-FY median, read with demand evidence. AHEAD_OF_DEMAND is a warning (D16), added to the M01 rule-4 `exit_warning` reasons (an M01 amendment this answer approves; rule 4 lists only M04 red flags today) and never blocking. PEAK_RISK waits for tuning. Why: the ratio tracks Micron's cycle where intensity does not (S-new-M05-10), and the boom evidence is weak in oligopolies (S-new-M05-4, R8).
- (b) As (a), plus PEAK_RISK now at the company's own 90th percentile, with no industry wave.
- (c) Capex ÷ revenue leads.

**Q05.5 Growth capex × ROIC**
- (a) *Recommended.* A state from the growth share and the 3-FY change in ROIC. Why: it uses only built rows, on the D-M04-6 default rung.
- (b) Incremental return: ΔNOPAT over 3 FYs ÷ cumulative growth capex.
- (c) Both, with (b) as info.

**Q05.6 Customer deposits (outline 4, "prepayments or LTAs")**
- (a) *Recommended.* Contract liabilities (total, else current + noncurrent, labelled) as a separate "repayable, not revenue" line. They count as bookings evidence in `capex_demand` and are never added to RPO. Why: Micron's deposits are repayable and price-banded (S-new-M05-9).
- (b) Added to RPO.
- (c) Ignored in the MVP.

**Q05.7 When a capex rise counts as positive (D-M02-5)**
- (a) *Recommended.* ✓ only when all three hold:
  - `capex_demand` = BUILD_INTO_DEMAND;
  - OCF ÷ capex ≥ 1 (D-M02-31);
  - CvD is not STRUCTURAL_DECLINE or CYCLE_PLUS_DAMAGE.

  Otherwise neutral, with the reason shown; M04's `runway_q` and `survival_gate` shown beside. M02's display is unchanged. This answers M02's open item "weighting of capex as a buy signal for the spender" (M02_THEMES open items; D-M02-5 left weighting "revisited later"). Why: Intel spent into falling revenue (S-new-M05-10), and D-M02-5 itself separates "able and willing" from stretching.
- (b) Any rise is positive.
- (c) Info only until a backtest exists.

**Q05.8 `commitment_risk` (no M04 decision adopts it)**
- (a) *Recommended.* Defer it, then propose it as an M04 earnings-quality addition. Why: it needs a provision series that is not stored (NVDA's $7.2B FY2026 provision is text-only, S-new-M05-6).
- (b) Build it now as an info row in Part 2.

## Build parts (1–2)
**Part 1: capex against demand (no new data)**
- **Signals:** `capex_demand`, `growth_capex_roic`, `bookings_cover`, plus the deposits line and the channel file.
- **Code:**
  - `src/engine/capex/` (name TBD): channels, demand, views, and a local step after `financials_local_step`;
  - two contract-liability concepts in `EXTRA_CONCEPTS`, total and noncurrent, each its own concept (the CONCEPTS rule: tags within a concept mean the same thing); the current-only `contract_liabilities` that M04 Part 6 reads stays unchanged;
  - `views.rpo` extended with the cover.
- **Tables and reviews:** none beyond `signal` (migration TBD only if needed). No review kinds.
- **UI:** a "Future spend (M05)" section on the Money flow tab:
  - the signal rows;
  - an 8-FY capex ÷ depreciation strip;
  - the deposits line;
  - M04's ≥10% customers;
  - M04's capex guidance outcomes (the track record).

  Mock-up first, on MU and INTC.
- **Live check:** `uv run python scripts/run_m05.py demand --no-sec` (name TBD; D-M04-69 pattern). 0 requests, under 1 minute. Compare MU, INTC and MSFT with this brief.
- **Fixtures:** the existing MU trimmed companyfacts (capex and `Depreciation` FY2012–26, enough for every rule). The INTC (capex FY2022–25) and MSFT (FY2025–26) fixtures are too short for the 8-FY median and INTC's 2023 test, and MU's has no `ContractWithCustomerLiability`. Fill by an owner-run export of those tags from stored `fact` (0 requests; Claude cannot read `data\`), else synthetic cases in the tests.
- **Depends on:** M04 1b (done). Until M04 8a lands, CvD reads missing and Q05.7 stays neutral. Independent of 4b-lite. Migration (if any) takes the next free number after M04's 0038/0039.

**Part 2: commitments**
- **Signal:** `commitment_cover`, plus the lease and post-period lines.
- **Code:** per-tag concepts; `capex/commitments.py`, a text finder over stored passages (`financials/text.py` helpers; quotes cut by offset and verified, D21); the XBRL/text mark.
- **Table:** `future_commitment` (cik, as_of, category, amount, tag or quote, accession, offsets, scope label, cancellable flag, after-period flag, grade). Migration TBD. No review kinds.
- **Live check:** `uv run python scripts/run_m05.py commitments --no-sec`. 0 requests, about 1 minute. The log lists the tags found and the sentences taken or set aside, with reasons.
- **Fixtures:** trimmed excerpts exported from stored text by an owner-run step (Claude cannot read `data\` or call SEC):
  - NVDA: FY2026 10-K Note 12 and the Q2 FY2027 10-Q;
  - Meta: Q2 2026 10-Q;
  - MU: FY2026 10-K deposits.
- **Depends on:** Part 1.

## Open risks
- **Text finder wording:** each live log will show new phrasings (LESSONS). Expect a re-run.
- **Thin history:** about 3 years of stored text, so most commitment rows start as short_history.
- **Proxies:** depreciation-proxy bias and the M04 S6.5 ROIC approximations (bounded tax, untagged debt taken as none) shape both capex signals.
- **Not yet verified:** Meta's tag context and its $12.31B off-frame point, the SPCX and GFS taxonomies, ASC 440.
- **No D13 weights:** none exist yet; ✓ only marks eligibility.

## Check notes (2026-10-13)
Adversarial check against the pack, DESIGN, the outline, M01/M02/M04 docs, the code and the fixtures. Worked-example figures were recomputed from `tests/fixtures/m04/*_companyfacts_trimmed_20261012.json`. MU's capex, depreciation, YoY, growth share and 1.68 median all match, and so do INTC's 55% split and MSFT's 3.38, 1.33 → 2.06 cover and +17.8% revenue.

1. **Outline fit.**
   - Outline CAPEX 1 (moat-building capex) was not listed under Deferred. Added, with the MVP's proxies.
   - R9's "capex still monitored for new offerings" was missing from the binding list. Added, and `capex_demand` and `growth_capex_roic` read info for fabless/outsourced to match case 10.
2. **Binding decisions.**
   - The M04 notes for M05 (customer store, CvD capex rows, D-M04-64 pointer only) were not cited. Added.
   - Q05.4 put AHEAD_OF_DEMAND into M01 rule 4, which today lists only M04 red flags. It is now worded as an M01 amendment the answer approves.
   - Q05.7 is not a re-ask: D-M02-5 left weighting "revisited later", and M02's open items ask for it. It now says so and shows M04's runway and gate beside it.
   - No question re-asks a decided point.
3. **Data reality.** Every named table, column, function and config exists (`capex_split`, `guidance_outcome`, `fact`, `fact_dim`, corpus `passage`, `EXTRA_CONCEPTS`, `views.rpo`, `actual_for`, `Window.ocf_cover`, `major_customers`, `trends.roic`, `financials/text.py`, `financials_local_step`). Corrections:
   - `capex_split` keeps only the last 8 FYs (`capex.WINDOW = 8`), so a prior-8-FY median needs `capex.py` with a longer window. Stated.
   - The total and noncurrent contract liabilities must be two separate concepts. M04 Part 6 already reads the current one, which stays unchanged.
   - The 7a instance read now keeps extension facts, so NVDA's prepaid supply and MU's incentive tag may already be stored. Check at 0 requests.
   - The RPO "untagged" list is only for the CY2026Q2I frame.
   - The MU contract-liability fixture and the short INTC and MSFT fixtures need an owner-run export from stored `fact` (0 requests), else synthetic tests. Previously this was unstated.
   - "Numbered after M07's" for the DS numbers was unverifiable. Changed to "assigned at build".
   - The migration number now follows M04's 0038/0039.
4. **Numbers and sources.**
   - The MSFT OpenAI "~45% per the call" was wrong. The source is press (M04 pack S-new-r5-9, commercial RPO, grade B), and the M04 7b customer row that would hold it is deferred. Fixed in the example, case 16 and Deferred.
   - Intel's 1.75× was attributed to an "M04 8a fixture". It is the Part 8a expected reading in M04_BUILD_LOG / R6 brief, recomputed as 47.5% ÷ 27.2%.
   - The MU FY2023 "M04 intact" claim is not supported by D-M04-54. Replaced with "under 1.5×, no pointer".
   - The NVDA "RISING" read compared text against a different tag series. It is now short_history, with the tag shown across a labelled break.
   - The MSFT BUILD_INTO_DEMAND read assumed 8 FYs of depreciation that the pack could not find. Marked illustrative.
   - The pack's D&A ratio (3.23) vs the depreciation rung (3.26) is now noted.
   - The ~50-request estimate is labelled.
5. **MVP discipline.** 4 signals, 8 questions, 2 parts and 0-request live checks are OK.
   - D13 was missing `source_ref` and the `value`/`value_text` split. Added.
   - `not_reported` and `not_applicable` were states, which breaks D-M04-9's missing-row rule. They are now missing rows.
   - The rule order let INSUFFICIENT_HISTORY pre-empt the 3-year D-M04-64 test. Fixed.
   - Case 5 conflated MSFT's lease reclassification (M02 own-definition) with a capex tag switch. Fixed.
   - Q05.3's "headline total" would mix NVDA's cloud, investment and other categories into the cover, against the pack's own guard. The numerator is now the supply/capacity or PP&E category.
6. **Overlap.**
   - M02 writes no capex signals.
   - M04's CvD capex rows, `deferred_rev_gap`, `major_customers` and `guidance_outcome` are read, not rebuilt.
   - `bookings_cover` extends `views.rpo`.
   - No other overlap was found.
7. **Length.** About 21k characters, above the 8–15k target. The case list was kept whole (owner preference), so it was not cut.
