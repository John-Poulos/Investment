# M01 — Timeframe profiles

Status: reviewed 2026-10-07 (D27) · Updated: 2026-10-25 · Outline headings: Type of investing by time frame · Depends on: M00, M03 (curve signals, D-M01-8), M04 (CvD), M05 (`capex_demand`), M06 (`moat_gate`, D-M01-9), M11 · Sources: S12, S19, S26, S28–S31

## Purpose
Defines the parameter profile each timeframe applies across all modules. Profiles change weights and recommendations, never visibility (D10). Profiles and bar sizes can be switched on the fly (D12). MY first; PT and ST later.

## Position layers
A holding = core lots under one primary profile + optional overlays (M12 options, shorter-term trades), each judged under its own profile (D11).

## Inputs
| Data | Source | Grade (A/B/C) | Refresh |
|---|---|---|---|
| Daily prices (weekly derived) | Free market data; source TBD at M02 | A | Daily |
| 10-Q, 10-K, 8-K, Form 4 | SEC EDGAR | A | On filing |
| CvD state, survival gate (`survival_gate`, `runway_q`; built M04 Part 4a; `cvd_state`, `cvd_confidence`, coverage; built M04 Part 8a) | M04 | Per input (weakest deciding input; B when an owner-entered credit line counts) | On filing and on each refresh (due dates, D-M04-61) |
| Tax lots (date, qty, cost) | User entry or broker export | A | On trade |
| Available funds, conviction (1–5) | User settings | — | On change |
| CPI, M2 | FRED | A | Monthly |
| S&P 500 total return | Free proxy TBD (dividend-adjusted index ETF) | A | Daily |

## Signals out
| Signal | Type / range | Meaning | MY | PT | ST |
|---|---|---|---|---|---|
| profile_weights | module_id → weight | How much each module drives recommendations | ✓ | – | – |
| entry_plan | lump / tranches + triggers | Proposed entry; owner decides | ✓ | – | – |
| exit_warning | reason list | Warnings only; owner decides (D16) | ✓ | – | – |
| review_due | date | Next scheduled thesis review | ✓ | – | – |
| lot_status | <1 yr / ≥1 yr | Holding-period state per lot | ✓ | – | – |

## Timeframe parameters (MY; PT/ST later)
| Parameter | MY | PT | ST |
|---|---|---|---|
| Horizon | Years; thesis-driven, no fixed maximum | | |
| Bars for signals | Weekly default; switchable (D12) | | |
| Trend filter | 40-week moving average | | |
| Entry zone / add trigger | 20-week mean − 1 to 2σ triggers; depth reported uncapped (rule 7); calibrate by backtest | | |
| Fundamental windows | TTM, YoY, 3-yr CAGR; 5-yr averages; full-cycle history for CvD | M04 windows fixed per D-M04-29, -49, -64; the 5-yr average applies to display | |
| Review cadence | After each 10-Q/10-K; event alerts in between | | |
| Weights | Fundamentals, moat, capex, money flow lead (3); ownership and M03 medium (2); analysts low (1); technicals time entries (D-M01-10) | | |
| Hurdle | S&P 500 TR; stretch TR + CPI | | |
| Lot awareness | Warn before selling lots held < 1 yr | | |
| Sizing | User caps per position and per shared killswitch (R23) | | |

## Rules
1. Entry needs the fundamental screen (R3), the confluence threshold (D13), and price in the entry zone; a first MY entry also needs the survival gate (D-M01-6) and `moat_gate` = met (D-M01-9).
2. The entry plan offers lump sum or tranches, weighing available funds, conviction and regime; the owner decides.
3. Every tranche after the first needs all three: CvD = CYCLICAL_TROUGH (or no slowdown), survival gate pass (M04), and the 1–2σ add trigger on the position's profile of record.
4. Exit warnings fire on: CvD moving to CYCLE_PLUS_DAMAGE or STRUCTURAL_DECLINE; a survival-gate fail (S6.14) or an overdue filing (D-M04-61); missed milestones or quietly removed targets (R19; M04's `guidance_removed`, S1.7); killswitch hits (R23); valuation ceiling if the owner sets one. M04 red-flag warnings and M05's `capex_demand` = AHEAD_OF_DEMAND (capex surging into falling revenue, D-M05-4) are listed among the `exit_warning` reasons and never block (D-M04-21, -60; D-M01-7). Warnings only (D16).
5. Thesis review after each 10-Q/10-K; on-track milestones with a flat price → "early," hold (R4).
6. Event alerts (8-K, opportunistic Form 4, guidance change, killswitch) surface immediately (R16).
7. Band depth is reported as σ below the 20-week mean with no cap. Beyond 2σ grades as a stronger signal only when CvD = CYCLICAL_TROUGH and the survival gate passes (gauge shown, not required, D-M04-62; read per D-M01-5); in any other state the depth is shown as a warning with no added strength (D27).

**Reading M04's gate (built M04 Part 4a, D-M04-31, -35, -38, -61).** The `survival_gate` signal's `value_text` is one of pass, warn, fail, incomplete, not_applicable; `method` names the trigger or the missing inputs. Rules 1, 3 and 7 read pass and warn as a pass; fail, incomplete and not_applicable as not-pass (incomplete = a required input missing, an overdue filing, a foreign filer's inputs older than 16 months, or inputs withheld as inconsistent; not applicable = `fund`, `financial`, untagged FF12 group 11). Rule 4's exit warning fires on fail and on an overdue filing (the gate `method` lists "exit warning: …"). A capex-funded name below 6 quarters reads warn with an open `m04_runway` review: rule-3 adds allowed, rule-7 strength blocked while it is open (the `runway_q` method says "capex-funded review open" and, once answered, the owner's choice). `distress_score`, `fcf_burn`, the debt rows and `negative_equity` are warnings or information and never gate inputs (D-M04-31, -21, -60).

**Reading M04's CvD state (built M04 Part 8a, D-M04-56, -58, -61, -103).** `cvd_state` (`value_text`) is the effective state: the computed one, or the owner's answer on an `m04_cvd` item, which replaces it while the computed state stays the same (the method says "owner answer …"). Its `method` ends with M04's own reading ("M01: rule 3 tranches: … · rule 7 strength: … · rule 4 exit warning: …"), which rules 3, 4 and 7 apply as built:
- **Rule 3 (tranches):** allowed on CYCLICAL_TROUGH and NO_SLOWDOWN with a gate pass or warn, and on STUMBLE once the owner has answered it; blocked on AMBIGUOUS and an unanswered STUMBLE ("until you answer the m04_cvd item"), on `insufficient_data` (an active CvD with fewer than 2 present rows in a question; no item, D-M04-102), on CYCLE_PLUS_DAMAGE and STRUCTURAL_DECLINE, on an overdue filing, and on a gate fail, incomplete or not applicable (the gate overrides the grid). Stale (a period ended unfiled): the first tranche may use the carried state, later tranches wait for the filing.
- **Rule 7 (strength beyond 2σ):** only CYCLICAL_TROUGH with a gate pass or warn and no open capex-funded runway review (D-M04-38); never needs the overreaction gauge (D-M04-62; the gauge is deferred in the MVP).
- **Rule 4 (exit warning):** CYCLE_PLUS_DAMAGE, STRUCTURAL_DECLINE (computed or answered), a gate fail, an overdue filing and a core `guidance_removed` in the last 12 months; red-flag warnings (`distress_score` distress, open non-reliance, restatement 4.02 / escalated, `special_items`, `eq_cash`, `negative_equity`) and M05's AHEAD_OF_DEMAND (D-M01-7) are listed and never block.
- `cvd_confidence` (lower of the two winning shares) and `cvd_coverage_q1` / `_q2` are shown beside the state; NO_SLOWDOWN writes them as missing ("not active").

## Failure modes
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| On-the-fly timeframes | Switching views until a signal appears ("timeframe shopping") | Decisions log the profile used; positions keep a profile of record |
| σ add trigger | Fires again and again in a true decline (falling knife) | CvD gate (rule 3); depth beyond 2σ adds strength only under the gates (rule 7) |
| σ bands | Fat tails break bands more often than a normal model implies | Backtest band-hit rates per stock |
| Weekly bars | Hide intra-week gaps (e.g. earnings) | Daily bars on chart; gap alerts |
| Quarterly cadence | Lags a fast-moving killswitch | Event alerts bypass cadence |
| Total-return proxy | ETF fees and tracking error differ from the index | Label as proxy |

## Decisions
- D-M01-1 (2026-10-06): Entries support lump sum and tranches; tranche adds gated by CvD + survival gate + band trigger — target good companies in down cycles, not decliners.
- D-M01-2 (2026-10-06): Exits are warnings; owner decides (D16).
- D-M01-3 (2026-10-06): Timeframes switchable on the fly with profile-of-record logging (D12).
- D-M01-4 (2026-10-07): σ bands not capped at 2σ; beyond 2σ is a stronger signal only when CvD and survival gates pass (owner, D27).
- D-M01-6 (2026-10-12, M04 closing C.1a = D-M04-76): Rule 1 first entry also needs a survival-gate pass (warn included), no overdue filing, and CvD not STRUCTURAL_DECLINE or CYCLE_PLUS_DAMAGE (R3 "fundamentally qualified", M04 side).
- D-M01-5 (2026-10-12, M04 review 6.8a = D-M04-58): Only CvD = CYCLICAL_TROUGH with a survival-gate pass (pass with warn included, D-M04-31) adds rule-7 strength; NO_SLOWDOWN allows tranches (rule 3); AMBIGUOUS, CYCLE_PLUS_DAMAGE, STRUCTURAL_DECLINE and an overdue filing block tranches; STUMBLE is blocked until the owner resolves the `m04_cvd` review. A gate of "not applicable" reads as not-pass (D-M04-35); a capex-funded name in review below 6 quarters allows rule-3 adds but not rule-7 strength (D-M04-38).
- D-M01-7 (2026-10-13, MVP sitting 2, Q05.4a = D-M05-4; amends rule 4): M05's `capex_demand` = AHEAD_OF_DEMAND (capex ÷ revenue > 1.5× its own 3-year average while revenue falls — the D-M04-64 test — or capex expanding while TTM revenue falls and no bookings line rises) is listed among the `exit_warning` reasons, as M04's red flags are, and never blocks an entry or a tranche. Why: outline CAPEX 5 (capex without demand destroys value); Intel 2021–24 (S-new-M05-10); warnings only (D16). The reason list lives in one place (`src/engine/m01_rules.py`, MVP_PLAN item 3), so M11's `exit_warning` reads it without a second copy. *Built 2026-10-20 (M05 Part 1, D-M05-15):* `m01_rules.rule4` lists "capex AHEAD_OF_DEMAND <as_of> (M05; warning only, never blocking; D-M01-7)" from M05's newest MY `capex_demand` row; rules 1, 3 and 7 do not read it.
- D-M01-8 (2026-10-21, MVP sitting 3, Q03.8a = D-M03-8; weights row): M03's `curve_stage`, `leader_rank` and `growth_runs` (signal names `<family>.<curve label>`, read by prefix) carry MY weight "medium until calibrated"; `curve_type` is info; PT and ST info. Why: the outline's "Catch the S-curve early" is a lead input, but every M03 threshold is an uncalibrated starting value.
- D-M01-9 (2026-10-21, MVP sitting 3, M06 rule 4 = D-M06-5, -6; amends rule 1): a first MY entry also needs M06's `moat_gate` = met (R1 "invest only with a moat", A3 band low ≥ the MY horizon, 5 years by default). `unrated` and `not_met` block the first entry (an owner override is logged, D-M06-5); `not_applicable` (fund, financial, treasury vehicle, shell period) is shown, never counted as a fail, and leaves the call with the owner (D16). PT and ST read the gate as info. Why: R1 is binding; the survival gate stays separate (D-M01-6).
- D-M01-10 (2026-10-25, MVP sitting 5, Q11.4a = D-M11-4; weights row; MVP_PLAN overlap 2): confluence tiers as numbers — lead 3: M04 (fundamentals), M06 (moat), M05 (capex), M02 (money flow); medium 2: M07 (ownership), M03 (D-M01-8); low 1: M08 (analysts); M09 technicals time entries and carry no vote; M10 carries no vote while its rows are info (D-M10-8). One headline vote per module, the map in `config/confluence.toml` (D-M11-4); PT reuses the MY weights, labelled; ST info. Why: equal weights within tiers match fitted weights on small samples (S-new-M11-8, -9); numbers make the confluence score reproducible.

## Open questions
- PT and ST columns — later phase.
