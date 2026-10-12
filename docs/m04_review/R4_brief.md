# M04 Round 4 — Survival gate and distress language — brief

Updated for Round 1 answers (D-M04-2…13): gate scope follows the model tag (`issuance_funded` normal gate, `asset_treasury`/`reit` liquidity-only, `fund`/`financial` not applicable, `spac_shell` trust only; D-M04-8, -13), so 4.5 asks only how M01 reads "not applicable"; a 3.01 listing transfer is information (S1.11), so INFQ passes and 4.7 keeps deficiencies, 2.04 and clearing; gate rows use `value_text` (D-M04-9); burn on total capex, "runway without growth capex" information (D-M04-6); `distress_score` labelled by D-M04-7 stage.

**Outline:** "preserve capital" (l. 147); Red Flags 4, 1, 6 (l. 81, 78, 83); capex 1–3 (l. 86–92). Approved: D-M04-1, -6…-9, -13, R2, R11, R12, A2, D16, D27 / M01 rules 3, 7.

## What the research says
- Altman Z: 82–94% accurate one year out, 29–48% at three to five; Type II error 15–20%; Ohlson's O is unit-sensitive (S-new-36…38, S-new-r4-1, -2). Young firms look distressed by construction (negative retained earnings 11.8% → 50.2% of industrials, S-new-40).
- Going-concern opinions are weak both ways (half of bankruptcies have none; over 70% are repeats; fixture text led Chapter 11 by 62–144 days); covenant violations are mostly trip wires (S-new-41…44, S-new-r4-3, -6).
- Undrawn credit is almost never tagged (0 of 15); `DebtCurrent` already holds commercial paper (S-new-46, S-new-r4-4). Runway 6 / 8 quarters matches S&P's "strong" liquidity test: an analogy, not a calibration.

## Worked example
Real figures, $M (S-new-47, S-new-r4-4, Boeing releases). Runway in quarters, burn = OCF − total capex (D-M04-6).

| Case | Facts | Recommended (4.1a–4.3a) | Pack 4.3a | Approved profile today |
|---|---|---|---|---|
| Rivian Q2 2026 | Z″ −5.37; runway 5.5 cash-only, 6.1 with ABL | fail until the ABL is confirmed past 12 months, then pass + warn | same | fail for years |
| Rivian Q3 2026 (est.) | raise ~1,317 less a quarter's burn ~962 | ~5.9 cash-only fail; ~6.4 with ABL warn | same | fail |
| Invitae FY2021 10-K | runway 5.6 (last-2) / 6.8 (TTM); Z″ 1.31 grey | **fail, 715 days before its 8-K 1.03** | same | pass; first fail 652 days ahead |
| Boeing Q2 2022 | 12-mo debt 5,406 + 4 × 1,874 = 12,900; cash 11,448; credit 14,700 | pass, 7.8–9.5 with credit (6.1 warn cash-only) | fail cash-only | not computed |
| Boeing FY2019 | `DebtCurrent` 7,340 incl. CP 6,109; liquidity 10,030 | wall passes; runway 3.6 cash-only fail, 7.1 warn with ~9,600 credit (secondary) | fail cash-only | wall fails on CP double count (13,449) |
| Intel FY2024 | runway 5.6; OCF +8,288; capex −39% next year | capex-funded: warn + review | pass | — |
| AMZN Q2 2026 | runway 9.1; burn ~13,500/qtr on the fallback tag, "≈ broader tag" (D-M04-3) | pass; `fcf_burn` information | pass | — |

**By tag (D-M04-8, -13):** MSTR `asset_treasury` → liquidity-only gate (24-month wall 4,550 vs 2,448 shown; Z not meaningful). ETV `fund` → not applicable. INFQ `spac_shell` to 2026-02-13 → trust only; after, normal gate: OCF-only runway 93.6 (capex untagged), pass; its 2026-02-03 3.01 (NYSE transfer) is information (S1.11). No watchlist name is `issuance_funded`; a Rivian-like one would take the normal gate.

Reading: the score fails Rivian whatever its cash and passes Invitae late; runway catches Invitae two years ahead. With Boeing's stated credit, pack 4.3a changes no verdict; cash-only, its one change is a false alarm. The pack's "about 7.5 quarters" for Rivian counted the unconfirmed ABL; restated ~5.9 / ~6.4.

## All cases
| Outcome | Pack cases |
|---|---|
| Pass / runway | 1 healthy; 3 self-funding; 2 young firm; 5 near the line; 6 guided burn ignored; 9 pro forma raise; 20 capex-funded; 21 seasonal OCF; 22 short history (SPCX); 23 capex untagged (INFQ) |
| Liquidity and wall | 4 one-quarter spike; 7 revolver variants; 8 restricted cash; 10 12-month wall, CP; 24 roll-down; 25 24-month wall (MSTR) |
| Text and events | 11 going-concern classes; 12 silence; 13 covenants; 14 8-K 1.03 / 2.04 / 3.01; 27 SPAC-era text; 28 exhibits |
| Scope and states | 15 bank, fund, treasury (by tag); 16 negative equity; 17 off-watchlist; 18 overdue; 19 missing inputs; 26 foreign filer |
| **Added** | 29 3.01 transfer; 30 SPAC statements after close; 31 stale annual inputs (GFS); 32 credit expiring inside the horizon; 33 runway restored by issuance; 34 long-dated debt (→ 3.8); 35 capex-funded negative FCF (AMZN); 36 6-K-only default; 37 `issuance_funded` in the warn band (D-M04-13); 38 stage unconfirmed (D-M04-7) |

**Completeness:** complete for the gate with 29–38. Omitted as in the pack: unfiled covenants, headroom, commitments, guarantees, cash abroad, crypto as liquidity.

## Suggestions
- **S4.1** Facts-first gate at every stage (D-M04-7), scoped by tag. *Changed:* encoding per D-M04-9 (`value_text` pass / fail / incomplete / not applicable, `value` NULL, `method` = trigger or missing inputs), replacing the pack's 1 / 0 / NULL.
- **S4.2** Runway on total capex; "runway without growth capex" from `capex_split` as information (D-M04-6). *Changed:* credit counts only if confirmed and maturing beyond the horizon; grade = weakest input (D-M04-9).
- **S4.3** Wall per 4.3a.
- **S4.4** Z, Z″, O as warning; manufacturer Z for GFS; market value from `shares_cover` (D-M04-2); "stage unconfirmed" label, uncounted (D-M04-7); CHS deferred.
- **S4.5** Going-concern finder. *Changed:* `spac_shell` periods go to the trust-only gate (D-M04-8); untagged SPACs fall back to the 2.01 close date; 6-K text added.
- **S4.6** Covenant finder plus IFRS "event of default", "delist".
- **S4.7** One-off EFTS history pass (about 200 requests).
- **S4.8** Review kinds; M04 weekly cap 5 (unsourced), 15 a week with M02. Setup, outside the cap: `m04_stage` 15 (D-M04-12), `m04_peer` ~13, `m04_credit_line` ~2, `m04_gate_input` 1 (INFQ); `m04_score_gap` 0–1.
- **S4.9–S4.10** Survival set (Boeing with credit, Rivian ~5.9 / ~6.4); build notes, script per B.1.
- **S4.11** Signals out per D-M04-9; adds `fcf_burn`, `debt_to_revenue` (3.8).
- **S4.12** Single change table: 4.3a, 4.5–4.8, scope by tag (D-M04-8), `issuance_funded` normal gate (D-M04-13, supersedes 3.4a and Round 6 change 19).
- **S4.13** `runway_q` carries "share of liquidity raised in the last 4 quarters" for `financing_pressure` (D-M04-13).

## Check flags
- Red Flags 6 → 3.8, 1 → 3.9, 4 → 4.9. INFQ 3.01 "fail" settled by S1.11; no 8-K fail ever cleared → 4.7.
- INFQ closing: D-M04-8 says 2026-02-13, a secondary source 2026-02-17; D-M04-8 governs, P2 confirms.
- Pack 4.3a loosened the approved wall fail → 4.3. Scope settled by D-M04-8, -13 → 4.5 narrowed. GFS stale → 4.6. Open review counted as pass → 4.8.
- Cross-round: 6.8 cites 4.1; Build parts counts align at merge; Known-gaps 3559–3560 stale.

## Gaps
**Closed:** Z″ zones; Ohlson re-run; Boeing credit stated (9.6B FY2019 secondary); INFQ's 3.01 a transfer (IR copies).
**Owner's probe:** P1 9 text fixtures (Fisker, Invitae Q2/Q3 2023, Proterra, Microvast, Riot, UTI, Albemarle, Boeing FY2023) · P2 local FTS5 INFQ "substantial doubt" (0 requests), INFQ 3.01 and closing 8-Ks (2, optional) · P3 manufacturer Z from Tiingo closes and `shares_cover` (local) · P4 Boeing revolver maturities (2, optional).

## Questions
**4.1 Role of distress scores, and how M01 reads the gate**
- (a) (recommended) Z, Z″, O become a stage-labelled `distress_score` warning; the gate uses liquidity and legal facts; M01 opens rule-3 adds and rule-7 strength only on pass (warn included). Why: Type II error 15–20%; runway beat Z″ and O on Invitae. Gets wrong: Rivian is add-eligible once confirmed runway reaches 6.
- (b) Scores block only rule-7 strength. Gets wrong: Rivian never gets strength, whatever its cash.
- (c) Score in the gate except for introduction and growth stages (D-M04-7). Gets wrong: BA (no 2 of 3), SPCX and INFQ (under 3 years) wait on the owner's stage call.
- (d) As now. Gets wrong: Rivian fails for years; Invitae FY2021 passes.

**4.2 Runway rule**
- (a) (recommended) Burn = OCF − total capex, worse of TTM ÷ 4 and last-2. Cash burners, `issuance_funded` included, fail below 6, warn below 8; capex-funded warn below 8, review below 6, never fail; confirmed credit only. Why: Invitae fails 715 days ahead; capex is a lever (Intel −39%). Gets wrong: capex that cannot be cut only warns.
- (b) Fail all below 6. Gets wrong: Intel FY2024 fails at OCF +8,288.
- (c) Worse of TTM ÷ 4 and latest quarter. Gets wrong: Boeing Q1 2022 fails on one quarter.
- (d) OCF only, 12 / 24 months. Gets wrong: Invitae "moderate" 50 weeks before Chapter 11.
- (e) Fail below 4. Gets wrong: Invitae passes through 2023.

**4.3 Maturity wall**
- (a) (recommended) 12-month debt > liquidity fails every gated tier and tag (CP never added); debt + 4 × burn warns; 24-month wall shown. Why: the add-on's only Boeing change is a false alarm. Gets wrong (illustrative): 7 quarters' runway with 3.5 quarters' debt only warns.
- (b) Pack 4.3a. Gets wrong: Boeing Q2 2022 fails then passes; capex-funded firms escape the approved fail.
- (c) Raw tags. Gets wrong: Boeing FY2019 fails on a CP double count.

**4.4 Going-concern and covenant text, and history**
- (a) (recommended) Fail on an auditor paragraph, a management "exists" conclusion, an unwaived breach, forbearance or covenant reclassification; alleviated, audit-matter-only, waived and reset cases warn + review; hypotheticals review only when runway < 8; `spac_shell` periods excluded; EFTS baseline. Why: matches AS 2415. Gets wrong: text leads by only 62–144 days.
- (b) Any going-concern sentence or breach fails. Gets wrong: Riot, Microvast, UTI fail.
- (c) As (a), no history. Gets wrong: repeats look new.

**4.5 How M01 reads "not applicable"** (narrowed; scope and states settled by D-M04-8, -9, -13)
- (a) (recommended) "Not applicable" (untagged FF12 group 11, `fund`, `financial`) reads as not pass until a sector gate exists; "withheld" maps to incomplete. Why: no gate without a test. Gets wrong: ETV and banks never get tranche adds.
- (b) Reads as pass. Gets wrong: a distressed bank gets gated adds untested.
- Former (c) removed: Z-only exclusion conflicts with D-M04-8.

**4.6 Input age**
- (a) (recommended) Older facts labelled "as of <date>"; foreign annual filers use annual burn up to 16 months, then incomplete; domestic filers use S1.6 overdue. Why: GFS's 6-Ks carry no XBRL. Gets wrong: a foreign filer can slide for a year unseen.
- (b) 6-month maximum. Gets wrong: GFS incomplete half of each year.
- (c) No rule. Gets wrong: stale inputs pass silently.

**4.7 8-K triggers and clearing** (3.01 transfer settled by S1.11)
- (a) (recommended) 1.03 fails, never auto-clears; 2.04 fails until a later periodic filing is clean and the owner resolves; 3.01 delisting or missed cure fails, cure-period deficiency warns + review. Why: cure notices often end in compliance. Gets wrong: a deficiency ending in delisting only warns until the final notice.
- (b) 1.03, 2.04 and non-transfer 3.01 fail until cleared. Gets wrong: every cure notice fails.
- (c) Fail only for the 8-K's quarter. Gets wrong: an acceleration clears while debt is due.

**4.8 Capex-funded review below 6 quarters**
- (a) (recommended) While open: rule-3 adds allowed, rule-7 strength blocked. Why: capex can be cut, but short runway should not add strength. Gets wrong: Intel FY2024 gets adds before review.
- (b) Plain pass. Gets wrong: Intel gets beyond-2σ strength.
- (c) Blocks both. Gets wrong: Intel gets no adds at OCF +8,288.

**4.9 Massive negative FCF (Red Flag 4)**
- (a) (recommended) `fcf_burn` information row (TTM FCF ÷ revenue and ÷ liquidity, operating vs capex-funded, `capex_split` context) beside D-M04-11's `fcf_growth`; threshold at Part 8. Why: no sourced cut-off; capex into demand is bullish. Gets wrong: AMZN warns only after calibration.
- (b) Warn on any negative FCF at a capex-funded name. Gets wrong: AMZN, SPCX, Intel warn every build-out quarter.
- (c) Runway only. Gets wrong: Red Flag 4 never shows for a cash-rich burner.
