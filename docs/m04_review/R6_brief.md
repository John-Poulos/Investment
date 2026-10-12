# M04 Round 6 — CvD calibration and health scores — brief

**Decides:** how the CvD grid is calibrated (6.1–6.2), scored (6.3–6.6, 6.9, 6.13–6.17) and read by M01 (6.7–6.8, 6.10–6.12). The pack has 8 questions; checker flags add 6.9–6.17.
**Outline items:**
- Analyze 1–4 and 6 (l. 65–75): growth, FCF as the "golden indicator", margins, operating leverage, revenue up with margins down.
- Red Flags 1, 3 and 4 (l. 78–81).
- Capex 3–5 (l. 92–95).
- The Micron cycle example (l. 47–53).
- Approved: D-M04-1 ("calibrate by backtest"), R2, R12, A2, D27, and M01 rules 3, 4 and 7.

## What the research says
- **The backtest window is set by XBRL:** about FY2010 to now. Micron's 2001 bust is invisible (S-new-4, S-new-r6-1).
- **Overfitting:** 20–40 labelled episodes support only a few thresholds. Test label stability under ±20% moves and log every variant (S-new-62).
- **Small peer groups:** the z method decides the label. Intel 2022 at n = 4 scores −0.82 to −1.92 around a −1.5 cut-off. Croux–Rousseeuw small-sample factors help (S-new-r6-3, S-new-63).
- **Look-ahead and survivorship:**
  - recasts (Intel FY2016–17; WDC FY2023 12,318 → 6,255);
  - a peer's quarter filed 32 days after the subject's 10-K;
  - delisting returns of −30% to −55% (S-new-64, S-new-65).
- **Piotroski F:** 4 of the 9 signals fail mechanically at a trough (Micron scores 3–5). The binary equity rule scores Intel's plan issuance every year (S32, S-new-r6-2).
- **Mohanram G** covers low-B/M firms only. NVIDIA scores 3 of 7 in a +125.9% year (S33, S-new-66).
- **Normalized earnings power (NEP):** the current-revenue base is cyclical (Micron −56.5% vs −11.2% on cycle-average revenue). Decliners keep their old margins: Intel ≈ $8.8B against −$2.2B actual (S-new-r6-1).
- **Filing deadlines:** with Rule 12b-25, a compliant filing arrives within 105 days of year-end (10-K) or 50 days of quarter-end (10-Q) (S88, S-new-r6-4).

## Worked example
**Micron 2022–23** (example D; S-new-r6-1; closes from Yahoo, S-new-r6-5, to re-check against Tiingo). Gap = 4-quarter price change − 4-quarter NEP change; **bold** = flagged at ≤ −25 pp.

| Latest quarter (filed) | TTM rev | Close | CvD 6.5a | + 6.17a | Gap 6.7a (current-rev base) | Gap 6.7e (cycle-avg base) |
|---|---|---|---|---|---|---|
| Q3 FY22; **low $48.88 on 2022-09-26**; Q4 ended 09-01, unfiled | growth | — | NO_SLOWDOWN | NO_SLOWDOWN; 6.11a: stale → later tranches wait | — | — |
| Q4 FY22 (10-K 2022-10-07) | +11.0%; quarter ≈ −19.7% (release, to verify) | $57.31 | NO_SLOWDOWN | **Active** | **−45.1** | **−46.3** |
| Q1 FY23 (2022-12-22) | −8.3% | $55.49 | Active | Active | **−34.3** | **−56.8** |
| Q2 FY23 | −26.0% | $56.43 | Active | Active | −18.4 | **−60.5** |
| Q3 FY23 | −43.9% | $69.09 | Active | Active | +29.7 | **−32.1** |
| Q4 FY23 (10-K 2023-10-06) | −49.5% | $69.94 | CYCLICAL_TROUGH 1.00 | same | +78.5 | +33.2 |

| Case | 6.6a state | 6.6b/c | Health 6.3a (F-quality) | 6.3b (F ≤ 3) | 6.14a capex ÷ revenue vs own 3-yr average | 6.15a equity point |
|---|---|---|---|---|---|---|
| MU FY2023 | CYCLICAL_TROUGH 1.00 (Q2 coverage 3 of 7) | AMBIGUOUS | 3 intact | F 4 intact | 49.4% vs 37.9% = 1.30×: intact | unchanged |
| INTC 2023 | AMBIGUOUS 0.25 (Q1 split) | AMBIGUOUS | 2 neutral | F 4 intact | 47.5% vs 27.1% = 1.75×: **neutral** | unchanged (+2.00%) |
| MU FY2016 trough | — | — | 2 neutral | F 3 **weakening** | — | — |
| INTC 2024 | — | — | 2 neutral | F 3 weakening | — | +2.1% → **3 intact** |

- **Timing.** The low came while the filed data still showed growth. A latest-quarter test (6.17a) activates CvD 11 weeks earlier, and the stale rule (6.11a) holds off later tranches at the low.
- **Gauge base.** On the current-revenue base the flag clears while the price is still near its low. On the cycle-average base it stays on after the price recovers, because NEP there jumps +23.8% when FY2022 enters the window.
- **Missing rows.** Counting them as disagreement (6.6b/c) sends even Micron's clean trough to review.

## All cases
- The pack's 27 cases cover:
  - peer count, extreme and diverging peers, acquisitions, offsets and peer lag, an unlike peer;
  - label stability;
  - activation and open zones;
  - disagreement and missing rows;
  - write-downs, history depth, ROIC and gross-margin definitions, capex tags;
  - F, G and Z;
  - NEP and gauge timing;
  - recasts, spin-offs and emergence from bankruptcy;
  - overdue filers, delisted tickers, pre-XBRL episodes.
- **Added:**
  - 28 a fresh bust that TTM smooths (MU Q4 FY22);
  - 29 a capex surge into falling revenue (INTC 2023);
  - 30 a serial impairer;
  - 31 a young issuer's equity point (Rivian, SPCX);
  - 32 filer status unknown, and the stale window;
  - 33 margin-only activation linked to R12 (NVDA FY2023; state not yet shown);
  - 34 negative FCF from growth capex at a trough (MU FY2023: CFO 1,559 − capex ≈ 7,677 = ≈ −6.1B);
  - 35 a "first deep decline" read from the XBRL window alone (Intel; 2001 is pre-XBRL).
- **Complete** for this round's rows once 28–35 are added. Known omissions:
  - the customer row (unbuilt);
  - IFRS peers;
  - enum encoding;
  - PT and ST parameters;
  - the outline's *positive* signals (FCF growth, gross-margin expansion, operating leverage, 3-year CAGR), which no round designs. They go to the M04 doc (6.9).

## Suggestions
- **S6.1** Backtests use `facts_as_of`. A peer counts from its filing date; until then the row reads "awaiting peer filing".
- **S6.2** MAD × b_n for 5–9 peers; fixed gap below 5; drop \|z\| > 3 once. *Added:* show the ±20% stability result.
- **S6.3** Test set and Part 8 data. *Changed:* fetch ≈ 6–7 min at 5/s (D-SEC-18), not 4. Calibrate only activation, z cut, majority and gauge.
- **S6.4** Capex on intensity, R&D on level. *Changed:* "total capex; A2 split shown as information"; surge per 6.14.
- **S6.5** 5 pp turning points; GM and ROIC agree. *Added:* one labelled inventory-days definition; write-down added back to inventory and COGS.
- **S6.6** NEP on two bases, ratio of sums, "not used: <state>". *Changed:* one-time items per 6.16.
- **S6.7** F-quality votes; F and G shown. *Changed:* "same measure as 3.1"; "less cycle-driven"; G window in `method`.
- **S6.8** Z with and without X4, at filing-date and latest close.
- **S6.9** Activation. *Added:* latest-quarter test (6.17); margin-only activation opens R12's cause review.
- **S6.10** Rows, open zones, majority, confidence. *Added:* cycle-history row → "insufficient history" when no prior XBRL downturn is as deep.
- **S6.11** Rows without data. *Changed:* customer row "missing until built (Round 5 rules)". *Added:* RF1 pointer to 3.9; RF6 to 3.8.
- **S6.12** Gauge per 6.7. *Added:* unit % → pp and sign flip recorded in change #10.
- **S6.13** Filing status per 6.11.
- **S6.14** M01 reading per 6.8, recorded as D-M01-5.

## Check flags
Flags that became questions: FCF (6.9); red-flag weight (6.10); overdue name and stale definition (6.11); gauge vs rule 7 (6.12); Intel expectation (6.13); capex surge (6.14); equity point vs R2 (6.15); one-time items vs RF3 (6.16); TTM lag (6.17); gauge base (6.7e).

Flags fixed in the text, with no question:
- **M01 rule 4.** The pack's table adds exit warnings for overdue filings, a gate fail and listed warnings. That changes M01 rule 4, so it is recorded as D-M01-5 in 6.8a. The NO_SLOWDOWN cell should read "depth shown as a warning".
- **Example C.** F = 4 means five signals fail, not four. Leverage is the fifth, and it is an F-quality input.
- **6.2a stability.** Intel's −1.64 at n = 5 flips under a −1.8 cut-off. The brief shows this instead of "three of four agree".
- **D13 records.** `cvd_coverage` and `normalized_ep` each carry two values. Split them into `_q1`/`_q2` and `_current`/`_cycle_avg`.
- **Rivian.** Round 4 passes Rivian at 6.1 quarters on its confirmed ABL, so no new raise is needed. 6.8a is aligned to that.

## Gaps
**Closed now**
- **Peabody 2017.** Its release confirms fresh-start reporting from 2017-04-01, with Predecessor and Successor stubs ($1,326.2M + $4,252.6M). The guard stands.
- **Croux–Rousseeuw factors.** A second transcription (Akinshin, arXiv 2207.12005) matches. Monte-Carlo factors differ by at most 0.9%, and no label changes.
- **Intel x86 share.** The Register, citing Mercury, gives "just over 71 percent" for Q4 2025, which matches 100 − 28.8. Intel's loss is 3.1–3.7 pp, so the vote is unchanged (grade B).
- **Mohanram.** A replication citing the original's p. 8 uses 16 quarterly periods, ≥ 3 firms per 2-digit SIC, and the lowest B/M quintile first. That sources the bottom-fifth gate. The pack's "G stays out until read" conflicts with S6.7 (G is information).
- **Part 8 fetch time:** 6–7 minutes at 5/s.
- **Micron 153 / 235 days** (partly closed). They reconcile with S-new-5 figures when the Dec-1 inventory is about $8.4B, a figure taken from the call.

**Needs the owner's live probe or data**
- **Tiingo delisted coverage.** Grep `supported_tickers.zip` (0 calls), or run 11–18 meta requests via a new `probe_tiingo_meta.py` (no DB writes).
- **MU and NVDA closes.** One read-only `price_bar` query (R6_gaps.md row 4; 0 requests).
- **BBBY and Rite Aid.** Revenue concepts plus submissions, about 8 SEC requests. Boeing's figures come from the DB.
- **Optional:**
  - MU `InventoryNet` at 2022-12-01 (0 requests);
  - a library copy of Mohanram (2005).

## Questions
**6.1 Test set** (reworded)
- (a) (recommended) The owner blind-labels the 24 episodes in S6.3: 15 for calibration (to FY2017) and 9 for testing (2018 on), plus 4 controls. Walk forward, and calibrate only activation, the z cut, the majority rule and the gauge. Why: calibration sees every state, and few thresholds are tuned. Gets wrong: delisted episodes may lack prices, so they get no gauge.
- (b) Semiconductors only. Gets wrong: calibration sees no damage or decline.
- (c) Only the 3 current cases. Gets wrong: tuned and tested on the same names.

**6.2 Few-peer statistics**
- (a) (recommended) MAD × 1.4826 × b_n for 5–9 peers; a fixed gap below 5; drop \|z\| > 3 once; show method, n and b_n. Why: at n = 4 the methods put Intel 2022 on both sides of −1.5. Gets wrong: Intel's −1.64 flips under a −1.8 cut-off.
- (b) IQR type 7 at every n. Gets wrong: Intel 2022 is company-specific under this quantile convention only.
- (c) Qn/Sn. Gets wrong: nothing computed; only 6–10 pairs at n = 4–5.

**6.3 Health scores** (see 6.9, 6.15)
- (a) (recommended) F-quality 0–4 is the only vote: ≥ 3 intact, 2 neutral, ≤ 1 weakening. F is shown with a > 2% equity signal. G is shown for low-B/M names. Why: F ≤ 3 calls Micron's FY2016 trough "weakening". Gets wrong: Intel 2025 reads intact after its strategic stakes.
- (b) As approved (F ≤ 3 or G ≤ 2). Gets wrong: MU FY2016 reads weakening; NVDA's G is 3 in its best year.
- (c) Show only. Gets wrong: MU FY2023's Q2 falls to 2 rows.

**6.4 Corrections to the approved profile** (see 6.14, 6.16)
- (a) (recommended) All four: NEP on both bases; capex on intensity and R&D on level; 5 pp turning points with the write-down adjustment; ROIC defined and agreeing with gross margin. Why: each fixes a Micron or Intel misreading. Gets wrong: a capex surge reads intact.
- (b) As (a), without ROIC. Gets wrong: overbuilding that shows first in ROIC is missed.
- (c) The NEP change only. Gets wrong: MU's capex cut reads weakening while capex ÷ revenue rose from 39% to 49%.
- (d) As written. Gets wrong: as (c), and NEP shows only the −56.5% base.

**6.5 Activation and open zones** (see 6.17)
- (a) (recommended) Activate when TTM revenue is down, gross margin is down ≥ 3 pp, or operating income is down ≥ 25%; otherwise NO_SLOWDOWN. Open zones per S6.10. Why: MU FY2023 stays a trough and NVDA FY2023 activates. Gets wrong: MU stays NO_SLOWDOWN at its 2022-10-07 10-K.
- (b) Plus a 10 pp fixed-gap floor while peers grow. Gets wrong: it partly undoes the dispersion scaling (Intel 2025 → company-specific).
- (c) Revenue only. Gets wrong: NVDA FY2023 (gross margin −8.0 pp) never activates.
- (d) Peers falling and the company far below → company-specific. Gets wrong: MU FY2023 → STUMBLE.

**6.6 Missing rows and confidence** (see 6.13)
- (a) (recommended) Missing rows leave the denominator; ≥ 2 present rows and a 2/3 majority; confidence is the lower winning share, with coverage shown. Why: MU → trough; INTC → review. Gets wrong: Micron's trough rests on 3 of 7 Q2 rows.
- (b) Missing counts as disagreeing. Gets wrong: MU → AMBIGUOUS, and nearly every name goes to review.
- (c) As (a), plus a 50% coverage floor. Gets wrong: MU → AMBIGUOUS.
- (d) Confidence × coverage. Gets wrong: MU's trough reads 0.43.

**6.7 Overreaction gauge** (option (e) added)
- (a) (recommended) The approved current-revenue base, the same 4 quarters, ≤ −25 pp; the live line and the cycle-average line are shown. Why: this is the approved base and it has no window-roll jumps. Gets wrong: the flag clears at Q2 FY23 (−18.4 pp) with the price still near its low.
- (e) Both bases; flag when either is ≤ −25 pp. Gets wrong: still flags at Q3 FY23 (−32.1 pp) after the price recovered.
- (b) 52-week drawdown vs the last filing. Gets wrong: mismatched windows (−80.6 pp before any filing showed the slump).
- (c) Fiscal-year ends. Gets wrong: misses Q1 FY23.
- (d) No threshold. Gets wrong: "large gap" stays undefined.

**6.8 How M01 reads M04** (reworded)
- (a) (recommended) As the table:
  - only CYCLICAL_TROUGH + gate pass adds rule-7 strength;
  - NO_SLOWDOWN allows tranches, with depth shown as a warning;
  - AMBIGUOUS, STUMBLE, damage, decline, overdue, gate fail and gate incomplete all block tranches;
  - warnings never gate.

  Record D-M01-5 (rule 4 gains overdue, gate-fail and listed warnings). Confirm Rivian: it passes at 6.1 quarters, so it takes tranches without strength. Why: this is D27. Gets wrong: Rivian can add at Z″ −5.37.
- (b) AMBIGUOUS allows tranches with a warning. Gets wrong: Intel 2022–23 gets adds.
- (c) A distress-zone Z also withholds strength. Gets wrong: it brings back the score that 4.1a removed.

**6.9 FCF in the grid** (new)
- (a) (recommended) Add CFO > 0 to F-quality, making it 0–5 (≥ 4 intact, 3 neutral, ≤ 2 weakening). Show TTM FCF, margin, YoY and 3-year CAGR as information. FCF growth as a positive signal goes to the M04 doc. Why: it covers the golden indicator, and CFO survives a trough. Gets wrong: a decliner with CFO > 0 keeps the point.
- (b) TTM FCF ≥ 0 as the point. Gets wrong: MU FY2023 (≈ −6.1B) loses it at a trough.
- (c) A Q2 row "FCF margin vs prior trough". Gets wrong: Intel has insufficient history.
- (d) No FCF. Gets wrong: the outline's golden indicator and RF4 are absent.

**6.10 Red-flag weight before calibration** (new)
- (a) (recommended) Round 2–5 red flags are information plus entry-plan warnings and R2 review items. They get no D13 weight and gate nothing beyond the survival gate until a labelled red-flag set exists. Why: their thresholds are unsourced. Gets wrong: a serial diluter can reach the confluence threshold, with a warning beside it.
- (b) A fixed negative weight (illustrative −1). Gets wrong: the weight is unsourced and hits young issuers (R2).
- (c) Severe flags withhold tranches. Gets wrong: uncalibrated thresholds would block adds.

**6.11 Filing status** (new)
- (a) (recommended) One signal, `filing_status` (current / stale / overdue + days), replacing `filing_overdue`.
  - **Stale:** a period has ended and its report is not yet filed; later tranches wait.
  - **Overdue:** bounds as Round 1 (by `category`; 105/50 when unknown). Effect: gate incomplete plus an exit warning.

  Why: Micron's low falls in a stale window. Gets wrong: a pause of up to 40–50 days every quarter.
- (b) Round 1 as drafted. Gets wrong: a silent non-filer gets no exit warning.
- (c) Stale as drafted ("next report pending"). Gets wrong: that is always true, so later tranches never pass.

**6.12 Does rule-7 strength need the gauge?** (new)
- (a) (recommended) No; the gap is shown beside it. Why: the approved gauge "informs, never overrides", and rule 7 already requires price beyond 2σ. Gets wrong: a trough whose price fell no more than its NEP still gets strength.
- (b) Yes, gap ≤ −25 pp. Gets wrong: Micron at Q2 FY23 (−18.4 pp, mid-trough) loses strength.

**6.13 Intel regression expectation** (new)
- (a) (recommended) AMBIGUOUS → review until the share and moat rows exist; the owner's resolution becomes the state. Why: the rows that would show damage are the missing ones. Gets wrong: the engine never says "damage" by itself.
- (b) Keep CYCLE_PLUS_DAMAGE → STRUCTURAL_DECLINE as a must-pass. Gets wrong: it invites tuning toward one label.

**6.14 Capex surge into falling revenue** (new)
- (a) (recommended) Capex ÷ revenue above 1.5× its own 3-year average while revenue falls → neutral, with a pointer to M05 bookings. Why: "capex without demand destroys value". Gets wrong: a planned counter-cyclical build reads neutral.
- (b) Cuts only. Gets wrong: Intel's 2023 surge (1.75×) reads intact.

**6.15 F-quality equity point by stage** (new)
- (a) (recommended) The point follows Round 3: it is lost only when issuance is extreme or serial, routed by stage and tag. Why: one dilution reading, and R2. Gets wrong: INTC 2024 (+2.1%) health reads intact.
- (b) The vote counts for mature, shake-out and decline stages only. Gets wrong: a trough borrower can read as growth stage and lose the row.
- (c) > 2% for all. Gets wrong: Rivian and SPCX lose the point by construction.

**6.16 One-time items in NEP** (new)
- (a) (recommended) Reported and ex-items shown side by side. An item is excluded only if nothing similar recurs in 10 years; repeats feed Round 2's earnings-quality flag. Why: RF3 (GE, Rivian), and Round 5 uses reported margins. Gets wrong: two unrelated one-offs both stay in.
- (b) Exclude all impairments. Gets wrong: a serial impairer is flattered.
- (c) Reported only. Gets wrong: Invitae's $2,313M impairment of 2022 stays in.

**6.17 Activation on the latest quarter** (new)
- (a) (recommended) Also activate when the latest quarter's revenue is ≥ 10% below the same quarter a year earlier (a starting value; calibrated in 6.1). Why: TTM smooths a fresh bust, and Micron activates on 2022-10-07, not 2022-12-22. Gets wrong: one lumpy quarter switches the grid on.
- (b) TTM only. Gets wrong: Micron stays NO_SLOWDOWN, with no rule-7 strength, while the gauge reads −45.1 pp.
