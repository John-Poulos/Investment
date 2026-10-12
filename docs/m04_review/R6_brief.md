# M04 Round 6 — CvD calibration and health scores — brief

Updated for Round 1 answers (D-M04-2…13): change 19 superseded by D-M04-13; capex rows on total capex (D-M04-6), one consistent tag, peers PP&E only (D-M04-3); FCF growth is a D-M04-11 information row, so 6.9 asks only about a CFO point; the equity point (6.15) routes by tag, then stage, uncounted while the stage is unconfirmed (D-M04-7, -8); `filing_status` = current/overdue, "stale" stays D-M04-1's mark on a carried CvD state (6.11).

**Decides:** CvD calibration (6.1–6.2), scoring (6.3–6.6, 6.9, 6.13–6.17), M01's reading (6.7–6.8, 6.10–6.12). Numbers unchanged.
**Outline:** Analyze 1–4, 6; Red Flags 1, 3, 4; Capex 3–5; Micron (l. 47–95). Approved: D-M04-1, R2, R12, A2, D27, M01 rules 3, 4, 7.

## What the research says
- XBRL starts about FY2010 (Micron's 2001 bust invisible); 20–40 episodes support few thresholds (S-new-4, S-new-62).
- Small peer groups: Intel 2022 at n = 4 scores −0.82 to −1.92 by method (S-new-r6-3, S-new-63). Recasts (WDC FY2023 12,318 → 6,255) and delisting returns of −30% to −55% bias backtests (S-new-64, -65).
- F: 4 of 9 signals fail at a trough; the binary equity rule scores Intel's plan issuance yearly (S32, S-new-r6-2). G: low-B/M only; NVIDIA 3 of 7 in a +125.9% year (S33, S-new-66).
- NEP on current revenue is cyclical (Micron −56.5% vs −11.2% on cycle-average) (S-new-r6-1). Rule 12b-25: 10-K within 105 days, 10-Q within 50 (S88, S-new-r6-4).

## Worked example
**Micron 2022–23** (S-new-r6-1; Yahoo closes, S-new-r6-5, to re-check against Tiingo). Gap = 4-quarter price change − NEP change, pp; **bold** = ≤ −25.

| Latest quarter (filed) | TTM rev | Close | CvD 6.5a | + 6.17a | Gap 6.7a | Gap 6.7e (cycle-avg) |
|---|---|---|---|---|---|---|
| Q3 FY22; **low $48.88 on 2022-09-26**; Q4 unfiled | growth | — | NO_SLOWDOWN | same, marked stale (6.11a) | — | — |
| Q4 FY22 (10-K 2022-10-07) | +11.0%; quarter ≈ −19.7% (release, to verify) | $57.31 | NO_SLOWDOWN | **Active** | **−45.1** | **−46.3** |
| Q1 FY23 (2022-12-22) | −8.3% | $55.49 | Active | Active | **−34.3** | **−56.8** |
| Q2 FY23 | −26.0% | $56.43 | Active | Active | −18.4 | **−60.5** |
| Q3 FY23 | −43.9% | $69.09 | Active | Active | +29.7 | **−32.1** |
| Q4 FY23 (10-K 2023-10-06) | −49.5% | $69.94 | CYCLICAL_TROUGH 1.00 | same | +78.5 | +33.2 |

| Case | 6.6a | 6.6b/c | 6.3a F-quality | 6.3b F ≤ 3 | 6.14a total capex ÷ rev vs 3-yr avg | 6.15a equity point |
|---|---|---|---|---|---|---|
| MU FY2023 | TROUGH 1.00 (Q2 coverage 3 of 7) | AMBIGUOUS | 3 intact | F 4 intact | 49.4% vs 37.9% = 1.30×: intact | kept |
| INTC 2023 | AMBIGUOUS 0.25 | AMBIGUOUS | 2 neutral | F 4 intact | 47.5% vs 27.1% = 1.75×: **neutral** | kept (+2.00%) |
| MU FY2016 | — | — | 2 neutral | F 3 **weakening** | — | — |
| INTC 2024 | — | — | 2 neutral | F 3 weakening | — | +2.1% → **3 intact** |

- The low came while filed data showed growth: 6.17a activates 11 weeks earlier; the stale mark holds later tranches.
- The current base clears near the low; the cycle-average base stays on after recovery.
- D-M04-9: `cvd_state` in `value_text`, grade A; an owner-entered share vote would make it B.

## All cases
- Pack 1–27: peers (offsets now D-M04-5), stability, activation, missing rows, write-downs, definitions, capex tags (now D-M04-3), F/G/Z, NEP, gauge, recasts, bankruptcy, overdue, delisted, pre-XBRL.
- Added 28–35: fresh bust (MU Q4 FY22); capex surge (INTC 2023); serial impairer; young issuer's equity point (Rivian, SPCX); filer status unknown; margin-only activation → R12 (NVDA FY2023); trough FCF ≈ −6.1B (MU FY2023); "first deep decline" from XBRL alone (Intel).
- *New:* 36 tagged names (D-M04-8): ETV, untagged financials "not applicable"; INFQ not applicable before 2026-02-13; MSTR's accruals point and Z "not meaningful". 37 stage unconfirmed (D-M04-7; SPCX): stage-routed inputs shown both ways, uncounted.
- **Complete** with 28–37. Omitted: customer row (unbuilt), IFRS peers, PT/ST parameters. Encoding settled (D-M04-9); positive trends are D-M04-11 rows.

## Suggestions
As the pack (S6.4, S6.12–S6.14 follow their questions), except:
- **S6.1** Backtests read `facts_as_of` (S1.1); outside D-M04-5 → "no comparable period". **S6.2** Peers per D-M04-4; ±20% stability shown. **S6.3** Fetch ≈ 6–7 min at 5/s.
- **S6.7** "Same measure as 3.1"; "less cycle-driven". **S6.8** Z on `shares_cover`, class-summed (D-M04-2); "not meaningful" for `asset_treasury`.
- **S6.10** Missing = a D-M04-9 "missing: <reason>" row; cycle history "insufficient" when no prior XBRL downturn is as deep.
- **S6.11** Customer row "missing until built"; guidance row reads `guidance_hit_rate` (D-M04-10), release-silent "missing (DS1)"; RF1 → 3.9, RF6 → 3.8.

## Changes to D-M04-1 in one place
**Decided in Round 1**

| Approved text | Change | By |
|---|---|---|
| Q1 "SIC peers (R24)" | 4-digit SIC proposals, owner confirms | D-M04-4 |
| Peer periods (D-SEC-9) | TTM ±45 d, quarters/instants ±40 d; outside counts toward < 5 | D-M04-5 |
| Q2 R&D and capex | Total capex; one consistent own tag; peers PP&E only; A2 split information | D-M04-3, -6 |
| Health inputs | Equity point and Z read the D-M04-2 share series | D-M04-2 |
| Q2 guidance record | Miss, repeated 2 of 4, removed | D-M04-10 |
| Gate "not for financials" | Tags first: fund, financial excluded; spac_shell trust only; asset_treasury, reit liquidity-only | D-M04-8 |
| #19 one gate | Superseded: `issuance_funded` keeps the normal gate | D-M04-13 |
| Signals out | `value_text`, missing rows, one row per timeframe, weakest-input grade | D-M04-9 |
| (new) trends | Five information rows, no vote until Part 8 | D-M04-11 |
| R2 stage | Dickinson 2 of 3; gate at every stage; unconfirmed uncounted | D-M04-7, -12 |

**Open here** (pack numbers)

| # | Approved | Proposed | Q |
|---|---|---|---|
| 1 | z on IQR ÷ 1.35 | MAD × 1.4826 × b_n; drop \|z\| > 3 once | 6.2 |
| 2 | Fallback ≤ 10 pp → shared | Shared only if peers fall; else neutral; `deeper_than_peers` | 6.5 |
| 3 | Revenue z zones | Open zones assigned | 6.5 |
| 4 | GM gap −3/−5 pp | Between → neutral; ≥ 3 comparable peers | 6.5, 6.6 |
| 5 | Supply response | Plus own absolute capex cut | 6.4 |
| 6 | Cut > 20% | Capex intensity (total), R&D level; surge → neutral | 6.4, 6.14 |
| 7 | Trough vs prior trough | 5 pp swings; GM and ROIC agree | 6.4 |
| 8 | F ≤ 3 or G ≤ 2 | F-quality votes; CFO point; equity point by tag/stage | 6.3, 6.9, 6.15 |
| 9 | NEP × current revenue | Second base; one-time rule; "not used" label | 6.4, 6.16 |
| 10 | Gauge undefined | 4 quarters, ≤ −25 pp; pp, sign flipped | 6.7, 6.12 |
| 11 | No "no slowdown" | NO_SLOWDOWN; activation incl. latest quarter | 6.5, 6.17 |
| 12 | Disagree → AMBIGUOUS | 2/3 of present rows; coverage | 6.6 |
| 13 | Share, pricing, moat | Owner share (B); pricing missing; moat n/a | 6.6 |
| 14–18 | Gate tests, states | Open in Round 4 | — |
| 20 | "State marked stale" | Stale = mark on carried CvD state; `filing_status` = current/overdue | 6.11 |
| 21 | INTC → damage → decline | AMBIGUOUS until share, moat rows | 6.13 |
| 22 | Signals out | Adds NO_SLOWDOWN, coverage, `deeper_than_peers`, `f_quality`, `normalized_ep`, `filing_status` (one row per value) | 6.3–6.11 |

**Trend rows (D-M04-11):** Round 6 calibration reports how each would have voted but does not tune them (6.1a); a vote is a separate owner decision after Part 8.

## Check flags
Became questions: 6.7e, 6.9–6.17. Fixed in text: rule-4 additions → D-M01-5; F = 4 means five failing signals; Intel's −1.64 flips at −1.8; two-value signals split (D-M04-9); Rivian passes on its ABL; pack 3.4 tag names → D-M04-8's.

## Gaps
**Closed:** Peabody 2017 stubs; Croux–Rousseeuw factors (≤ 0.9%); Intel x86 share ≈ 71% (B, vote unchanged); Mohanram gate sourced; Part 8 fetch 6–7 min; Micron 153/235 days reproduce with write-downs added back (Round 1).
**Needs the owner:** Tiingo delisted coverage — grep `supported_tickers.zip` (0 calls; 18 symbols, R6_gaps row 3); it also serves Round 1's P2 without writing `price_bar` rows · MU/NVDA closes, one read-only query · BBBY and Rite Aid, about 8 SEC requests · optional: MU `InventoryNet` 2022-12-01, Mohanram (2005).

## Questions
**6.1 Test set**
- (a) (recommended) Owner blind-labels 24 episodes: 15 calibration (to FY2017), 9 test, 4 controls; tune only activation, z cut, majority, gauge; D-M04-11 rows reported, not tuned. Why: every state seen, few thresholds. Gets wrong: delisted episodes may lack prices.
- (b) Semiconductors only. Gets wrong: no damage or decline in calibration.
- (c) The 3 current cases. Gets wrong: tuned and tested on the same names.

**6.2 Few-peer statistics**
- (a) (recommended) MAD × 1.4826 × b_n for 5–9 peers; fixed gap below 5 (D-M04-5 misses count); drop |z| > 3 once. Why: at n = 4 methods put Intel 2022 both sides of −1.5. Gets wrong: −1.64 flips at −1.8.
- (b) IQR type 7 at every n. Gets wrong: the label rests on a quantile convention.
- (c) Qn/Sn. Gets wrong: 6–10 pairs at n = 4–5.

**6.3 Health scores**
- (a) (recommended) F-quality 0–4 the only vote (≥ 3 intact, 2 neutral, ≤ 1 weakening); F, G shown. Why: F ≤ 3 calls MU's FY2016 trough weakening. Gets wrong: Intel 2025 intact after its stakes.
- (b) As approved. Gets wrong: MU FY2016 weakening; NVDA G = 3 in its best year.
- (c) Show only. Gets wrong: MU FY2023's Q2 falls to 2 rows.

**6.4 Corrections to the profile**
- (a) (recommended) NEP on both bases; capex intensity (total, D-M04-6; tags D-M04-3), R&D level; 5 pp turning points, write-down adjusted; ROIC agreeing with GM. Why: each fixes a Micron or Intel misreading. Gets wrong: a surge reads intact (6.14).
- (b) Without ROIC. Gets wrong: overbuilding seen first in ROIC missed.
- (c) NEP only. Gets wrong: MU's capex cut reads weakening while intensity rose 39% → 49%.
- (d) As written. Gets wrong: as (c), and only the −56.5% base.

**6.5 Activation and open zones**
- (a) (recommended) Active when TTM revenue falls, GM ≥ 3 pp or operating income ≥ 25%; else NO_SLOWDOWN. Why: NVDA FY2023 activates. Gets wrong: MU NO_SLOWDOWN at its 2022-10-07 10-K (6.17).
- (b) Plus a 10 pp floor. Gets wrong: Intel 2025 → company-specific.
- (c) Revenue only. Gets wrong: NVDA FY2023 (GM −8.0 pp) never activates.
- (d) Far below falling peers → company-specific. Gets wrong: MU → STUMBLE.

**6.6 Missing rows and confidence**
- (a) (recommended) Missing rows leave the denominator; ≥ 2 present rows, 2/3 majority; confidence = lower winning share, coverage shown. Why: MU → trough, INTC → review. Gets wrong: MU's trough rests on 3 of 7 Q2 rows.
- (b) Missing = disagreeing. Gets wrong: even MU's clean trough goes to review.
- (c) Plus a 50% coverage floor. Gets wrong: MU → AMBIGUOUS.
- (d) Confidence × coverage. Gets wrong: MU's trough reads 0.43.

**6.7 Overreaction gauge**
- (a) (recommended) Current base, same 4 quarters, ≤ −25 pp; both lines shown. Why: approved; no window-roll jumps. Gets wrong: clears at Q2 FY23 near the low.
- (e) Either base ≤ −25 pp. Gets wrong: still flags Q3 FY23 after recovery.
- (b) 52-week drawdown. Gets wrong: −80.6 pp before any filing.
- (c) Fiscal-year ends. Gets wrong: misses Q1 FY23.
- (d) No threshold. Gets wrong: "large gap" undefined.

**6.8 How M01 reads M04**
- (a) (recommended) Only CYCLICAL_TROUGH + gate pass (tag-routed, D-M04-8, -13) adds rule-7 strength; NO_SLOWDOWN allows tranches, depth as a warning; AMBIGUOUS, STUMBLE, damage, decline, overdue, gate fail or incomplete block; warnings never gate; record D-M01-5. Rivian (normal gate) passes at 6.1 quarters: tranches, no strength. Why: D27. Gets wrong: Rivian adds at Z″ −5.37.
- (b) AMBIGUOUS allows tranches. Gets wrong: Intel 2022–23 gets adds.
- (c) Distress Z withholds strength. Gets wrong: restores the score 4.1a removed.

**6.9 CFO in the health vote** (narrowed; FCF information settled by D-M04-11)
- (a) (recommended) Add CFO > 0 to F-quality, 0–5 (≥ 4 intact, 3 neutral, ≤ 2 weakening). Why: a cash vote that survives a trough. Gets wrong: a decliner with CFO > 0 keeps it.
- (b) TTM FCF ≥ 0. Gets wrong: MU FY2023 (≈ −6.1B) loses it at a trough.
- (c) FCF margin vs prior trough. Gets wrong: Intel lacks history.
- (d) D-M04-11 information only. Gets wrong: no cash vote before Part 8.

**6.10 Red-flag weight before calibration**
- (a) (recommended) Round 2–5 flags are information, warnings and R2 review items; no D13 weight or gating beyond the gate until a labelled set exists. Why: unsourced thresholds; as D-M04-11. Gets wrong: a serial diluter can reach confluence.
- (b) Fixed weight (illustrative −1). Gets wrong: unsourced; hits young issuers.
- (c) Severe flags block tranches. Gets wrong: uncalibrated blocks.

**6.11 Filing status and the stale mark** (reworded)
- (a) (recommended) `filing_status` = current / overdue (S1.6 bounds; 105/50 if category unknown), days in a numeric row (D-M04-9); overdue → gate incomplete plus exit warning. Separately, **stale** (D-M04-1) marks the carried CvD state once a fiscal period has ended unfiled; later tranches wait. Why: Micron's low is in a stale window. Gets wrong: a pause of up to 40–50 days a quarter.
- (b) Overdue → gate incomplete only. Gets wrong: no exit warning for a silent non-filer.
- (c) Stale = "next report pending". Gets wrong: always true; tranches never pass.

**6.12 Does rule-7 strength need the gauge?**
- (a) (recommended) No; gap shown beside it. Why: the gauge "informs, never overrides". Gets wrong: a trough without overreaction still gets strength.
- (b) Yes, ≤ −25 pp. Gets wrong: MU loses strength mid-trough (Q2 FY23).

**6.13 Intel regression expectation**
- (a) (recommended) AMBIGUOUS → review until share and moat rows exist; the owner's answer becomes the state. Why: the damage rows are missing. Gets wrong: the engine never says "damage" alone.
- (b) Keep damage → decline as must-pass. Gets wrong: invites tuning to one label.

**6.14 Capex surge into falling revenue**
- (a) (recommended) Total capex ÷ revenue > 1.5× own 3-year average (one tag) while revenue falls → neutral, pointer to M05. Why: "capex without demand destroys value". Gets wrong: a planned counter-cyclical build reads neutral.
- (b) Cuts only. Gets wrong: Intel 2023 (1.75×) intact.

**6.15 Equity point by tag and stage** (reworded for D-M04-7, -8, -12, -13)
- (a) (recommended) Follows Round 3, routed by tag then stage; lost only on extreme or serial issuance; `issuance_funded` loses it only when `financing_pressure` warns; unconfirmed stage → "missing: stage unconfirmed", both readings shown. Why: one dilution reading, R2. Gets wrong: INTC 2024 (+2.1%) intact.
- (b) Vote only at mature, shake-out, decline. Gets wrong: a trough borrower can turn "growth" and drop the row until reviewed (D-M04-12).
- (c) > 2% for all. Gets wrong: Rivian, SPCX lose it by construction.

**6.16 One-time items in NEP**
- (a) (recommended) Reported and ex-items shown; exclude only if nothing similar recurs in 10 years; repeats feed Round 2. Why: RF3 (GE, Rivian). Gets wrong: two unrelated one-offs both stay in.
- (b) Exclude all impairments. Gets wrong: flatters a serial impairer.
- (c) Reported only. Gets wrong: Invitae's $2,313M impairment stays in.

**6.17 Activation on the latest quarter**
- (a) (recommended) Also active when the latest quarter's revenue is ≥ 10% below a year earlier (starting value). Why: MU activates 2022-10-07, not 12-22. Gets wrong: one lumpy quarter switches it on.
- (b) TTM only. Gets wrong: MU NO_SLOWDOWN at a −45.1 pp gap.
