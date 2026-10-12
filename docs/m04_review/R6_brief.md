# M04 Round 6 — CvD calibration and health scores — brief

Updated for Rounds 1–5 answers (D-M04-2…50) and the probe (2026-10-12): Micron figures verified (L9); Tiingo symbols per episode, none for J.C. Penney (S6.15); 6.8 gate side settled (D-M04-31, -35, -38); 6.10 narrowed (D-M04-44, -45); 6.6 adds customer weight and R12 vote (D-M04-50, -44); 6.11 narrowed (S1.6, D-M04-36); new 6.18 market share (D-M04-30); change table through D-M04-50.

**Decides:** calibration (6.1–6.2), scoring (6.3–6.6, 6.9, 6.13–6.18), M01's reading (6.7–6.8, 6.10–6.12).
**Outline:** Analyze 1–4, 6; Red Flags 1, 3, 4; Capex 3–5; Micron (l. 47–95). Binding: D-M04-1…50, R2, R12, A2, D27, M01 rules 3, 4, 7.

## What the research says
- XBRL starts about FY2010; 20–40 episodes support few thresholds (S-new-4, -62); at n = 4, Intel 2022 scores −0.82 to −1.92 by method (S-new-r6-3, -63). Recasts (Rite Aid FY2017 32,845 → 22,928, S17) and delisting returns bias backtests (S-new-64, -65).
- F: 4 of 9 signals fail at a trough (S32, S-new-r6-2); G: NVIDIA 3 of 7 in a +125.9% year (S33, S-new-66); NEP on current revenue: Micron −56.5% vs −11.2% cycle-average (S-new-r6-1).
- 12b-25 limits 105/50 days (S88, S-new-r6-4); 12b-2 exit thresholds apply only to an issuer already in the category (Invitae, S2).

## Worked example
**Micron 2022–23** (S-new-r6-1). Quarter-end closes are stored Tiingo closes, equal to the pack's on all 13 dates (L9). Gap = 4-quarter price change − NEP change, pp; **bold** = ≤ −25.

| Latest quarter (filed) | TTM rev | Close | CvD 6.5a | + 6.17a | Gap 6.7a | Gap 6.7e |
|---|---|---|---|---|---|---|
| Q3 FY22; **low $48.88 on 2022-09-26**; Q4 unfiled | growth | — | NO_SLOWDOWN | same, stale (6.11a) | — | — |
| Q4 FY22 (10-K 2022-10-07) | +11.0%; quarter ≈ −19.7% (release) | $57.31 | NO_SLOWDOWN | **Active** | **−45.1** | **−46.3** |
| Q1 FY23 (2022-12-22) | −8.3% | $55.49 | Active | Active | **−34.3** | **−56.8** |
| Q2 FY23 | −26.0% | $56.43 | Active | Active | −18.4 | **−60.5** |
| Q3 FY23 | −43.9% | $69.09 | Active | Active | +29.7 | **−32.1** |
| Q4 FY23 (10-K 2023-10-06) | −49.5% | $69.94 | CYCLICAL_TROUGH 1.00 | same | +78.5 | +33.2 |

| Case | 6.6a | 6.6b/c | 6.3a F-quality | 6.3b F ≤ 3 | 6.14a capex ÷ rev vs 3-yr | 6.15a equity point |
|---|---|---|---|---|---|---|
| MU FY2023 | TROUGH 1.00 (Q2 3 of 7) | AMBIGUOUS | 3 intact | F 4 intact | 1.30×: intact | kept |
| INTC 2023 | AMBIGUOUS 0.25 | AMBIGUOUS | 2 neutral | F 4 intact | 1.75×: **neutral** | kept (+2.00%) |
| MU FY2016 | — | — | 2 neutral | F 3 **weakening** | — | — |
| INTC 2024 | — | — | 2 neutral | F 3 weakening | — | +2.1%, not extreme → **3 intact** |

- 6.17a activates 11 weeks earlier; the current base clears near the low, the cycle-average base stays on after recovery.
- Inventory: Q2 FY23 153.1 days, 235.0 with the write-down added back (`InventoryNet` 8,359/8,129; L9), grade A. Customer classes await the owner (D-M04-43).

## All cases
- Pack 1–27 (peers to pre-XBRL); NVDA has no PP&E-only tag in any year, so it is out of peer statistics throughout (D-M04-3, S4).
- 28–35: fresh bust; capex surge; serial impairer; young issuer's equity point; filer status unknown; margin-only activation (NVDA FY2023); trough FCF ≈ −6.1B; "first deep decline" from XBRL. 36 tagged names (D-M04-8); 37 stage unconfirmed (D-M04-7).
- *New:* 38 Invitae: R12 from 2020Q1 (−8.9, −10.5 pp); FY2022 large accelerated ($569.8M > $560M exit line), on time; FY2023 accelerated, never filed → overdue. 39 Boeing: runway FY2019 5.9, Q2 2024 5.5 → fail (D-M04-32); Z 1.53 a warning (D-M04-31). 40 no prices (J.C. Penney): gauge "missing: no price". 41 recycled tickers (BBBY, RAD, SHLD).
- **Complete** with 28–41. Omitted: IFRS peers, PT/ST parameters; customer row "missing: not built" until its part ships.

## Suggestions
As the pack (S6.4, S6.12–S6.14 follow their questions), except:
- **S6.1** Backtests read first-filed values (`facts_as_of`). **S6.2** Peers per D-M04-4 from a ranked shortlist (SIC 3674: 505 listed, 82 active; 20-F/40-F count as active, S1). **S6.3** Fetch ≈ 6–7 min (4–4.6/s measured).
- **S6.7** "Same measure as 3.1". **S6.8** Z on `shares_cover`, class-summed, shown as `distress_score` (D-M04-2, -31). **S6.10** Missing = "missing: <reason>" (D-M04-9).
- **S6.11** Customer row per D-M04-43, -49, -50; guidance row reads `guidance_hit_rate` (D-M04-10); RF1 → D-M04-30 with 6.18; RF6 → D-M04-29.
- **S6.15** (new) A Tiingo symbol counts only when its name and dates match the SEC company; bars stored under it: BBBYQ, RADCQ, NVTAQ, SHLDQ, RSH/RSHCQ, FIT, GPRO, BA. Check BTU (2017), CHK (2021 splice) and RADCQ/NVTAQ last trades.

## Changes to D-M04-1 in one place
**Decided**

| Approved text | Change | By |
|---|---|---|
| Peers, periods | SIC proposals, owner confirms; ±45/±40 d | D-M04-4, -5 |
| Q2 R&D and capex | Total capex; one own tag; peers PP&E only | D-M04-3, -6 |
| Health inputs | D-M04-2 share series | D-M04-2 |
| Q2 customer base | Owner-confirmed class; named 8-Ks; RPO; weight | D-M04-43, -49, -50 |
| Q2 guidance record | Miss, 2 of 4, removed | D-M04-10 |
| Q2 (new vote) | Confirmed price, mix or competition R12 cause → weakening | D-M04-40, -44 |
| Survival gate | Z out (warning); runway, wall; text and 8-K triggers; M01 on pass incl. warn | D-M04-31…34, -37, -38 |
| Gate scope; #19 | By tag; "not applicable" = not-pass; input age | D-M04-8, -13, -35, -36 |
| Signals out | `value_text`, missing rows, per timeframe | D-M04-9 |
| (new) information rows | Trends, debt, FCF burn; no vote until Part 8 | D-M04-11, -29, -39 |
| R2 stage | Dickinson 2 of 3; owner confirms | D-M04-7, -12 |
| Red-flag weight | R12 and per-unit flags count; others wait for ≥ 20 labels | D-M04-45 |

**Open here** (pack numbers)

| # | Approved | Proposed | Q |
|---|---|---|---|
| 1 | z on IQR ÷ 1.35 | MAD × 1.4826 × b_n; drop \|z\| > 3 once | 6.2 |
| 2–4 | Fallback, z zones, GM gap | Shared only if peers fall; open zones; between → neutral | 6.5, 6.6 |
| 5–7 | Supply, capex cut, troughs | Own capex cut; intensity, R&D level; 5 pp swings, ROIC | 6.4, 6.14 |
| 8 | F ≤ 3 or G ≤ 2 | F-quality; CFO point; equity point (D-M04-22…27) | 6.3, 6.9, 6.15 |
| 9 | NEP × current revenue | Second base; one-time rule | 6.4, 6.16 |
| 10 | Gauge undefined | 4 quarters, ≤ −25 pp | 6.7, 6.12 |
| 11 | No "no slowdown" | NO_SLOWDOWN; latest quarter | 6.5, 6.17 |
| 12 | Disagree → AMBIGUOUS | 2/3 of present weight; coverage | 6.6 |
| 13 | Share, pricing, moat | Share test; pricing missing; moat n/a | 6.18 |
| 20 | "State marked stale" | Stale mark; overdue → exit warning | 6.11 |
| 21 | INTC → damage → decline | AMBIGUOUS until share, moat rows | 6.13 |
| 22 | Signals out | NO_SLOWDOWN, coverage, `f_quality`, `normalized_ep` | 6.3–6.11 |

## Check flags
Became questions: 6.7e, 6.9–6.18. Fixed: F = 4 means five failing signals; Rivian is pass + warn only once its ABL is confirmed (D-M04-32); closes verified (L9).

## Gaps
**Closed by the probe:** Micron (L9); Tiingo coverage (T1/T2); episode facts (S2, S17).
**Open:** J.C. Penney prices; RADCQ/NVTAQ last trade, BTU, CHK (4–6 Tiingo requests); Rite Aid "last 10-K 2024-07-25 (period 2023-03-04)" (1 request); BBBY revenue before FY2016; optional Mohanram (2005).

## Questions
**6.1 Test set**
- (a) (recommended) Owner blind-labels 24 episodes (15 to FY2017, 9 from 2018) plus 4 controls; tune only activation, z cut, majority, gauge; information rows reported only; prices per S6.15. Why: every state seen, few thresholds. Gets wrong: J.C. Penney's 2 episodes lack the gauge.
- (b) Semiconductors only. Gets wrong: no damage or decline in calibration.
- (c) The 3 current cases. Gets wrong: tuned and tested on the same names.

**6.2 Few-peer statistics**
- (a) (recommended) MAD × 1.4826 × b_n for 5–9 peers; fixed gap below 5; drop |z| > 3 once. Why: at n = 4, methods put Intel 2022 on both sides of −1.5. Gets wrong: −1.64 flips at −1.8.
- (b) IQR type 7 at every n. Gets wrong: rests on a quantile convention.
- (c) Qn/Sn. Gets wrong: 6–10 pairs at n = 4–5.

**6.3 Health scores**
- (a) (recommended) F-quality 0–4 is the only vote (≥ 3 intact, 2 neutral, ≤ 1 weakening); F, G shown. Why: F ≤ 3 calls MU's FY2016 trough weakening. Gets wrong: Intel 2025 intact.
- (b) As approved. Gets wrong: MU FY2016 weakening; NVDA G = 3 in its best year.
- (c) Show only. Gets wrong: MU FY2023's Q2 falls to 2 rows.

**6.4 Corrections to the profile**
- (a) (recommended) NEP on both bases; total capex intensity, R&D level; 5 pp turning points, write-down adjusted; ROIC agreeing with GM. Why: fixes Micron and Intel misreadings. Gets wrong: a surge reads intact (6.14).
- (b) Without ROIC. Gets wrong: misses overbuilding.
- (c) NEP only. Gets wrong: MU's capex cut reads weakening while intensity rose 39% → 49%.
- (d) As written. Gets wrong: as (c), on one base.

**6.5 Activation and open zones**
- (a) (recommended) Active when TTM revenue, GM (≥ 3 pp) or operating income (≥ 25%) falls; else NO_SLOWDOWN. Why: NVDA FY2023 activates. Gets wrong: MU NO_SLOWDOWN at its 2022-10-07 10-K (6.17).
- (b) Plus a 10 pp floor. Gets wrong: Intel 2025 → company-specific.
- (c) Revenue only. Gets wrong: NVDA FY2023 (GM −8.0 pp) never activates.
- (d) Far below falling peers → company-specific. Gets wrong: MU → STUMBLE.

**6.6 Missing rows and confidence**
- (a) (recommended) Missing rows leave the denominator; ≥ 2 present; 2/3 majority by weight (customer per D-M04-50); R12 counts only when it fires; confidence = lower winning share, coverage shown. Why: MU → trough, INTC → review. Gets wrong: MU's trough rests on 3 of 7 rows.
- (b) Missing = disagreeing. Gets wrong: MU goes to review.
- (c) Plus a 50% coverage floor. Gets wrong: MU → AMBIGUOUS.
- (d) Confidence × coverage. Gets wrong: MU reads 0.43.

**6.7 Overreaction gauge**
- (a) (recommended) Current base, same 4 quarters, ≤ −25 pp; both shown. Why: approved; no window jumps. Gets wrong: clears at Q2 FY23, near the low.
- (e) Either base. Gets wrong: still flags Q3 FY23 after recovery.
- (b) 52-week drawdown. Gets wrong: −80.6 pp before any filing.
- (c) Fiscal-year ends. Gets wrong: misses Q1 FY23.
- (d) No threshold. Gets wrong: "large gap" undefined.

**6.8 How M01 reads the CvD state** (gate side settled by D-M04-31, -35, -38)
- (a) (recommended) Only CYCLICAL_TROUGH with a gate pass adds rule-7 strength; NO_SLOWDOWN allows tranches; AMBIGUOUS, STUMBLE, damage, decline, overdue block; record D-M01-5. Why: D27. Gets wrong: a NO_SLOWDOWN name at a gate warn (Rivian) gets tranches.
- (b) AMBIGUOUS allows tranches. Gets wrong: Intel 2022–23 gets adds.
- (c) Settled by D-M04-31.

**6.9 CFO in the health vote** (FCF settled by D-M04-11, -39)
- (a) (recommended) CFO > 0 joins F-quality, 0–5 (≥ 4 intact, 3 neutral, ≤ 2 weakening). Why: a cash vote that survives a trough. Gets wrong: a decliner with CFO > 0 keeps it.
- (b) TTM FCF ≥ 0. Gets wrong: MU FY2023 (≈ −6.1B) loses it at a trough.
- (c) FCF margin vs prior trough. Gets wrong: Intel lacks history.
- (d) Information only. Gets wrong: no cash vote before Part 8.

**6.10 Other red flags before calibration** (R12 and per-unit flags settled by D-M04-44, -45)
- (a) (recommended) Restatement, `special_items`, `financing_pressure`, `distress_score`, Red Flag 1: shown and reviewed, no D13 weight until ≥ 20 labelled episodes (the pack's 10 plus about 10 from 6.1). Why: one rule (D-M04-45); 10 fall short. Gets wrong: a serial diluter with a passing gate can reach confluence.
- (b) Fixed weight (illustrative −1). Gets wrong: unsourced; hits young issuers.
- (c) Severe flags block tranches. Gets wrong: uncalibrated blocks.

**6.11 Overdue and the stale mark** (`filing_status` settled by S1.6, D-M04-36)
- (a) (recommended) Overdue → gate incomplete (D-M04-36) plus an exit warning; stale (D-M04-1) marks the carried CvD state once a period ends unfiled; later tranches wait. Why: Micron's low is in a stale window. Gets wrong: pauses up to 40–50 days a quarter.
- (b) Gate incomplete only. Gets wrong: no exit warning for a silent non-filer.
- (c) Stale = "next report pending". Gets wrong: always true; tranches never pass.

**6.12 Does rule-7 strength need the gauge?**
- (a) (recommended) No; gap shown. Why: the gauge "informs, never overrides". Gets wrong: a trough without overreaction gets strength.
- (b) Yes, ≤ −25 pp. Gets wrong: MU loses strength mid-trough.

**6.13 Intel regression expectation**
- (a) (recommended) AMBIGUOUS → review until share and moat rows exist; the owner's answer is the state. Why: damage rows missing. Gets wrong: never says "damage" alone.
- (b) Damage → decline as must-pass. Gets wrong: invites tuning to one label.

**6.14 Capex surge into falling revenue**
- (a) (recommended) Total capex ÷ revenue > 1.5× own 3-year average while revenue falls → neutral, pointer to M05. Why: capex without demand destroys value. Gets wrong: a planned counter-cyclical build reads neutral.
- (b) Cuts only. Gets wrong: Intel 2023 (1.75×) intact.

**6.15 Equity point**
- (a) (recommended) Round 3 measure (D-M04-22, -23), routed by tag then stage (D-M04-27); lost only on extreme or serial issuance (D-M04-26), for `issuance_funded` only when `financing_pressure` warns (D-M04-25); unconfirmed stage → missing. Why: one dilution reading. Gets wrong: INTC 2024 (+2.1%) intact.
- (b) Vote only at mature, shake-out, decline. Gets wrong: a trough borrower turning "growth" drops the row (D-M04-12).
- (c) > 2% for all. Gets wrong: Rivian, SPCX lose it by construction.

**6.16 One-time items in NEP**
- (a) (recommended) Reported and ex-items shown (D-M04-48); exclude only if nothing similar in 10 years; repeats feed `special_items` (D-M04-19). Why: RF3 (GE, Rivian). Gets wrong: two unrelated one-offs both stay in.
- (b) Exclude all impairments. Gets wrong: flatters a serial impairer.
- (c) Reported only. Gets wrong: Invitae's $2,313M impairment stays in.

**6.17 Activation on the latest quarter**
- (a) (recommended) Also active when the latest quarter's revenue is ≥ 10% below a year earlier (starting value). Why: MU activates 2022-10-07, not 12-22. Gets wrong: one lumpy quarter switches it on.
- (b) TTM only. Gets wrong: MU NO_SLOWDOWN at a −45.1 pp gap.

**6.18 Market-share test** (new; Q2 row and Red Flag 1, D-M04-30)
- (a) (recommended) Owner-entered third-party share (B), or computed from a stated industry total (A); Q2 "falling" = down ≥ 1 pp in 4 quarters in a flat or growing market; Red Flag 1 "no gains" = up < 1 pp (illustrative, Part 8); else "missing: no share data". Why: one reading feeds both rows. Gets wrong: most names rest on owner entries.
- (b) Revenue vs peer median as a proxy. Gets wrong: repeats Q1's revenue row.
- (c) Missing until M06. Gets wrong: Red Flag 1 is missing for every name.
