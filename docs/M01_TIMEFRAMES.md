# M01 — Timeframe profiles

Status: reviewed 2026-10-07 (D27) · Updated: 2026-10-13 · Outline headings: Type of investing by time frame · Depends on: M00, M04 (CvD), M11 · Sources: S12, S19, S26, S28–S31

## Purpose
Defines the parameter profile each timeframe applies across all modules. Profiles change weights and recommendations, never visibility (D10). Profiles and bar sizes can be switched on the fly (D12). MY first; PT and ST later.

## Position layers
A holding = core lots under one primary profile + optional overlays (M12 options, shorter-term trades), each judged under its own profile (D11).

## Inputs
| Data | Source | Grade (A/B/C) | Refresh |
|---|---|---|---|
| Daily prices (weekly derived) | Free market data; source TBD at M02 | A | Daily |
| 10-Q, 10-K, 8-K, Form 4 | SEC EDGAR | A | On filing |
| CvD state, survival gate (`survival_gate`, `runway_q`; built M04 Part 4a) | M04 | Per input (weakest deciding input; B when an owner-entered credit line counts) | On filing and on each refresh (due dates, D-M04-61) |
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
| Weights | Fundamentals, moat, capex, money flow lead; ownership medium; analysts low; technicals time entries | | |
| Hurdle | S&P 500 TR; stretch TR + CPI | | |
| Lot awareness | Warn before selling lots held < 1 yr | | |
| Sizing | User caps per position and per shared killswitch (R23) | | |

## Rules
1. Entry needs the fundamental screen (R3), the confluence threshold (D13), and price in the entry zone.
2. The entry plan offers lump sum or tranches, weighing available funds, conviction and regime; the owner decides.
3. Every tranche after the first needs all three: CvD = CYCLICAL_TROUGH (or no slowdown), survival gate pass (M04), and the 1–2σ add trigger on the position's profile of record.
4. Exit warnings fire on: CvD moving to CYCLE_PLUS_DAMAGE or STRUCTURAL_DECLINE; a survival-gate fail (S6.14) or an overdue filing (D-M04-61); missed milestones or quietly removed targets (R19; M04's `guidance_removed`, S1.7); killswitch hits (R23); valuation ceiling if the owner sets one. M04 red-flag warnings are listed among the `exit_warning` reasons and never block (D-M04-21, -60). Warnings only (D16).
5. Thesis review after each 10-Q/10-K; on-track milestones with a flat price → "early," hold (R4).
6. Event alerts (8-K, opportunistic Form 4, guidance change, killswitch) surface immediately (R16).
7. Band depth is reported as σ below the 20-week mean with no cap. Beyond 2σ grades as a stronger signal only when CvD = CYCLICAL_TROUGH and the survival gate passes (gauge shown, not required, D-M04-62; read per D-M01-5); in any other state the depth is shown as a warning with no added strength (D27).

**Reading M04's gate (built M04 Part 4a, D-M04-31, -35, -38, -61).** The `survival_gate` signal's `value_text` is one of pass, warn, fail, incomplete, not_applicable; `method` names the trigger or the missing inputs. Rules 1, 3 and 7 read pass and warn as a pass; fail, incomplete and not_applicable as not-pass (incomplete = a required input missing, an overdue filing, a foreign filer's inputs older than 16 months, or inputs withheld as inconsistent; not applicable = `fund`, `financial`, untagged FF12 group 11). Rule 4's exit warning fires on fail and on an overdue filing (the gate `method` lists "exit warning: …"). A capex-funded name below 6 quarters reads warn with an open `m04_runway` review: rule-3 adds allowed, rule-7 strength blocked while it is open (the `runway_q` method says "capex-funded review open" and, once answered, the owner's choice). `distress_score`, `fcf_burn`, the debt rows and `negative_equity` are warnings or information and never gate inputs (D-M04-31, -21, -60).

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

## Open questions
- PT and ST columns — later phase.
