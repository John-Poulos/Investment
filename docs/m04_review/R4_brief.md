# M04 Round 4 — Survival gate and distress language — brief

**Decides:** what the survival gate tests and what it ignores (4.1), how runway and the debt wall are measured (4.2–4.3), which going-concern, covenant and 8-K facts fail it (4.4, new 4.7), its states and input age (new 4.5–4.6), how M01 reads a capex-funded review (new 4.8), and whether massive negative FCF is its own flag (new 4.9).
**Outline items:** "preserve capital – do not lose" (l. 147) via the D-M04-1 gate; Red Flags 4 "massive negative FCF" (l. 81), 1 "cash burn with no share gains" (l. 78) and 6 "large debt against revenue" (l. 83); capex 1–3 (l. 86–92) for the capex-funded tier. Approved: D-M04-1, R2, R11 (Rivian), R12 (Invitae), A2, D8, D16, D27 / M01 rules 3 and 7.

## What the research says
- Altman Z: 82–94% accurate one year out, 29–48% at three to five; Type II error now 15–20%. Z″ 1.10 / 2.60 = Altman's 4.35 / 5.85 with the +3.25 constant; only mixing forms misleads (S-new-36, S-new-r4-1).
- Market-based models beat accounting scores (S-new-37). Ohlson's O (cut-off 0.038) is unit-sensitive: Rivian P 0.031 in dollars, 0.90 in $ millions (S-new-38, S-new-r4-2).
- Young firms read as distressed by construction: negative retained earnings rose from 11.8% to 50.2% of industrials, 1978–2002 (S-new-40).
- Going-concern opinions are weak both ways: about half of bankruptcies have none, about 10% of recipients file within a year, over 70% are repeats. In the fixtures the text led Chapter 11 by only 62–144 days (S-new-41, S-new-42, S-new-r4-6).
- Rules fix the searchable wording: ASC 205-40, AS 2415 ("substantial doubt", "going concern"), IFRS "material uncertainty" (S-new-43, S-new-r4-3).
- Covenant violations hit 10–20% of firms a year and are usually trip wires followed by recovery (S-new-44).
- Undrawn credit is almost never tagged: 0 of 15 watchlist names tag it for a current period, and only GFS tags the IFRS version. `DebtCurrent` already contains commercial paper (S-new-46, S-new-r4-4).
- Runway has no peer-reviewed threshold. Under constant burn, 6 / 8 quarters equals S&P's "strong" liquidity test (≥ 1.5× sources ÷ uses over 12 months, > 1.0× the next 12): an analogy, not a calibration (S&P criteria 2014/2016, read by the gap check).

## Worked example
Real figures, $M (S-new-47, S-new-r4-4, Boeing releases 2022-07-27 and 2024-07-31). "Runway" is in quarters at the 4.2a burn.

| Case | Facts | Recommended (4.1a, 4.2a, 4.3a as changed) | Pack 4.3a (debt + 4 × burn fails) | Approved profile today (score in gate) |
|---|---|---|---|---|
| Rivian Q2 2026 | Z″ −5.37; runway 5.5 cash-only, 6.1 with the ABL | fail until the ABL is confirmed (and runs past 12 months), then pass + warn | same | **fail for years** whatever the cash |
| Rivian Q3 2026 (est.) | July raise ~1,317, less one quarter of burn ~962 | ~5.9 cash-only (fail); ~6.4 with the ABL (warn) | same | fail |
| Invitae FY2021 10-K | runway 5.6 (last-2) / 6.8 (TTM ÷ 4); Z″ 1.31 grey | **fail, 715 days before its 8-K 1.03** | same | pass; first fail Q1 2022 (652 days) |
| Boeing Q2 2022 | 12-mo debt 5,406 + 4 × 1,874 = 12,900; cash 11,448; stated credit 14,700 | pass: 7.8–9.5 counting credit that runs past 12 months (6.1 warn cash-only) | **fail on cash only**, pass with credit; passed next quarter | not computed (Z needs prices) |
| Boeing FY2019 | `DebtCurrent` 7,340 with CP 6,109 inside; liquidity 10,030 | wall passes (7,340 < 10,030); runway 3.6 fails cash-only, 7.1 warn with ~9,600 credit (secondary) | fail cash-only; pass with credit | wall fails only if CP is double counted (13,449) |
| Intel FY2024 | runway 5.6; OCF +8,288; capex cut 39% next year | capex-funded: warn + review, no fail | pass (19,406 vs 22,062) | — |
| AMZN Q2 2026 | runway 9.1; burn ~13,500 a quarter | pass, no FCF flag (see 4.9) | pass | — |

- Reading: the score fails Rivian whatever its cash and passes Invitae too late. Runway catches Invitae about two years ahead.
- Once Boeing's stated credit counts, the pack's 4.3a changes no Boeing verdict. On cash only, its one change is a false alarm. So the recommendation on 4.3 changes (below).
- The pack's "about 7.5 quarters" for Rivian after the raise counted the unconfirmed ABL and skipped Q3's own burn. Restated as ~5.9 / ~6.4 (check flag; Round 6 line 2989 too).

## All cases
| Outcome | Pack cases |
|---|---|
| Pass / self-funding | 1 healthy; 3 self-funding (never ∞) |
| Decided by runway | 2 young firm with a deficit (Rivian); 5 near the line; 6 guided burn ignored (Invitae 8.5 vs 4.1); 9 pro forma raise as a note; 20 capex-funded; 21 seasonal Q1 OCF; 22 short history (SPCX); 23 capex untagged (INFQ) |
| Burn and liquidity mechanics | 4 one-quarter spike; 7 revolver tagged / untagged / borrowing base / conditional; 8 restricted cash |
| Debt wall | 10 12-month wall, holder puts, CP inside `DebtCurrent`; 24 roll-down vs reclassification; 25 24-month wall (MSTR) |
| Text classes | 11 going-concern classes; 12 silence before bankruptcy; 13 covenant classes; 27 SPAC-era text and predecessor CIK; 28 exhibits and unrelated hits |
| Events | 14 8-K 1.03 / 3.01 |
| Scope and states | 15 bank, fund, crypto treasury; 16 negative equity from buybacks vs losses; 17 not on watchlist; 18 overdue; 19 missing inputs; 26 foreign filer |
| **Added** | 29 3.01 that is a listing transfer (INFQ 2026-02-03, per a secondary source); 30 SPAC statements in a 10-K filed after the close (INFQ); 31 stale annual-only inputs (GFS, 2025-12-31); 32 credit that expires inside the test horizon (Boeing Q2 2022: $6.3B in October 2022); 33 runway restored by issuance (Invitae 2021, Rivian 2026); 34 large long-dated debt with positive OCF (Red Flag 6, question 3.8); 35 massive negative FCF at a capex-funded name (AMZN, 4.9); 36 a foreign filer's default or delisting announced only in a 6-K |

**Completeness:** complete for the gate once 29–36 are added. Known omissions stay as in the pack: unfiled covenant terms, rarely disclosed headroom, purchase and lease commitments, guarantees, cash trapped abroad, and crypto as liquidity.

## Suggestions
- **S4.1** Facts-first gate. *Changed:* 3.01 classified per 4.7; states and scope per 4.5; input age per 4.6.
- **S4.2** Runway. *Changed:* undrawn credit counts only if it matures beyond the test horizon (12 months for the fail, 24 for the warn) and is not blocked by covenants (S&P analogy). The grade is the weakest input's (A filing, B press or owner entry). The 6 / 8 pair is labelled "S&P-strong analogue, not calibrated".
- **S4.3** Wall. *Changed:* the approved test fails every tier; the 4 × burn add-on only warns (4.3a).
- **S4.4** Score family (Z, Z″, O) as a warning. GFS (SIC 3674) gets manufacturer Z, not book Z″. *Changed:* CHS deferred (no RSIZE, weak at 12 months).
- **S4.5** Going-concern finder. *Changed:* `spac_pre_merger` keys on the statements' period end being on or before the 2.01 close date, not on the filing date; 6-K text added for foreign filers.
- **S4.6** Covenant finder. *Changed:* adds IFRS "event of default" and "delist" phrases for 6-Ks.
- **S4.7** One-off EFTS history pass (about 200 requests), baseline only.
- **S4.8** Review kinds and the M04 weekly cap of 5 (unsourced; with M02's 10 a week, up to 15 judgment items a week in total).
- **S4.9** Regression and survival set. *Changed:* Boeing cases get a with-credit column; Rivian post-raise ~5.9 / ~6.4.
- **S4.10** Part 4 build notes; script name to follow the Build-parts B.1 answer.
- **S4.11** Signals out. *Added:* `fcf_burn` per 4.9; `debt_to_revenue` per 3.8.
- **S4.12** Change table. *Changed:* lists 4.3a as changed, plus 4.5–4.8. It becomes the single source; Round 6 rows 14–17 point to it.
- **S4.13** *(new)* `runway_q` carries "share of liquidity raised in the last 4 quarters" (financing cash flows), for Round 3's `financing_pressure`.

## Check flags
- Outline Red Flags with no rule: 6 debt vs revenue (→ question 3.8), 1 burn with no share gains (→ 3.9; confirm "share gains" = market share), 4 massive negative FCF (→ 4.9; AMZN burns ~54B a year unflagged).
- Any 3.01 fails, so INFQ should read "fail" today, not "pass" → 4.7. No rule clears an 8-K fail → 4.7.
- Pack 4.3a let capex-funded firms escape the approved "12-month debt > liquidity" fail, unlisted in S4.12 → 4.3 changed.
- "Incomplete" and "not applicable" rested on a suggestion; M01's reading of N/A is undefined (ETV) → 4.5.
- GFS is annual-only and 9 months old, so it is not "self-funding on both measures" → 4.6.
- An open capex-funded review counts as pass for rule 7 (Intel FY2024) → 4.8.
- Cross-round: 6.8 re-asks 4.1 (cite the answer); Build parts say `m04_gate` and 136 hits vs six kinds and 153 (align at merge); Known-gaps lines 3559–3560 are stale (remove).

## Gaps
**Closed now**
- Z″ zones 4.35 / 5.85 with the constant = 1.10 / 2.60 without (Altman 2017, slide 27). Ohlson figures and GNPDEF 577 / 603 / 706 re-run (FRED).
- Boeing's releases state undrawn credit of 14.7B (Q2 2022) and 10.0B (Q2 2024); 9.6B at FY2019 is secondary. Changes 4.3.
- Item 3.01 also covers voluntary listing transfers (form heading; Dillard's, Oasis, Baker Hughes, secondary). Changes S4.1; adds 4.7.
- INFQ's de-SPAC closed (2026-02-17, secondary) before its FY2025 10-K with SPAC statements was filed. Changes the S4.5 SPAC rule, which holds whatever the date.
- Warn band: the S&P "strong" analogy above. The weekly cap of 5 stays unsourced. Albemarle: buybacks "limited", not "barred" (secondary); check at capture.

**Needs the owner's live probe**
- P1: 9 Archives documents (Fisker, Invitae Q2 and Q3 2023, Proterra, Microvast, Riot, UTI, the Albemarle EX-10.1, Boeing FY2023 10-K) as text fixtures with offsets. Needs `run_survival.py --fixtures` or a small probe.
- P2: a local FTS5 query on corpus.db for INFQ's "substantial doubt" (0 requests), plus INFQ's 2026-02-03 8-K 3.01 (1 request; the 10-K as a fallback).
- P3: local only: manufacturer Z inputs from stored Tiingo closes and dei shares (0 SEC requests).
- P4 (optional): Boeing FY2019 10-K and Q2 2024 10-Q for the revolver maturity split (2 requests).

## Questions
**4.1 Role of distress scores, and how M01 reads the gate**
- (a) (recommended) Z, Z″ and O become a stage-flagged `distress_score` warning. The gate uses liquidity and legal facts only. M01: only `pass` (the warn band included) opens rule-3 adds and rule-7 strength. Why: Type II error is 15–20%, and runway caught Invitae 2 months before Z″ and a year before O. Gets wrong: Rivian becomes add-eligible once a confirmed runway reaches 6 (~6.4 after the raise with the ABL; ~5.9 cash-only still fails).
- (b) Scores block only rule-7 strength. Gets wrong: Rivian never gets the stronger signal, whatever its cash.
- (c) Score stays in the gate unless retained earnings < 0 and runway ≥ 6. Gets wrong: Boeing 2024 (positive retained earnings) hinges on price-based Z.
- (d) As now. Gets wrong: Rivian fails for years; Invitae's FY2021 10-K passes.

**4.2 Runway rule**
- (a) (recommended; credit rule tightened) Burn = OCF − total capex, the worse of TTM ÷ 4 and last-2. Cash burners fail below 6 and warn below 8. Capex-funded firms warn below 8 and get a review below 6, never a fail. Only confirmed credit counts, and only if it matures beyond the horizon. Why: Invitae fails 715 days ahead, and capex is a lever (Intel −39%). Gets wrong: capex that cannot really be cut only warns.
- (b) Total-capex burn fails everyone below 6. Gets wrong: Intel FY2024 fails with OCF +8,288.
- (c) Worse of TTM ÷ 4 and the latest quarter. Gets wrong: Boeing Q1 2022 fails at 3.4 on one −3,216 quarter.
- (d) OCF only, 12 / 24 months. Gets wrong: Invitae reads "moderate" 50 weeks before Chapter 11.
- (e) Fail below 4. Gets wrong: Invitae passes at 4.0–4.1 through 2023.

**4.3 Maturity wall test** (recommendation changed after the Boeing credit closure and check flags 5 and 10; letters re-ordered)
- (a) (recommended) The approved test fails every tier: next-12-month debt > liquidity, with CP never added and the larger of current debt and the year-1 tag at a 10-K. Debt + 4 × burn > liquidity is a warning. The 24-month wall and roll-down screen are shown. Why: the add-on's only Boeing verdict change is a cash-only false alarm, it changes none once credit counts, and no failure case shows it earlier than runway. Gets wrong (illustrative): a burner at 7 quarters' runway with debt of 3.5 quarters' burn only warns until runway fails.
- (b) Pack's 4.3a: debt + 4 × burn fails; capex-funded firms only warn. Gets wrong: Boeing Q2 2022 fails and passes next quarter; a capex-funded firm with debt alone over liquidity escapes the approved fail.
- (c) Approved text on raw tags (CP added). Gets wrong: Boeing FY2019 fails on a double count (13,449 vs 10,030).

**4.4 Going-concern and covenant text, and history**
- (a) (recommended; SPAC rule and 6-K text added) Fail on an auditor paragraph (Fisker), a management "exists" conclusion in any section (Invitae Q3 2023), an unwaived breach (Proterra), forbearance (Fisker) or a covenant-driven reclassification. Alleviated (Microvast), critical-audit-matter-only, waived (UTI) and reset (Albemarle) cases get a warning plus review. Hypotheticals (Riot) go to review only when runway < 8. Plus a one-off EFTS history baseline. Why: matches AS 2415, and violations alone are common. Gets wrong: text leads by only 62–144 days; a reset at a weakening firm stays a warning.
- (b) Any going-concern sentence or breach fails. Gets wrong: Riot, Microvast, UTI and Invitae's Q2 2023 boilerplate all fail.
- (c) As (a), with no history pass. Gets wrong: no baseline to tell repeats (over 70%) from new language.

**4.5 Gate states and scope** (new)
- (a) (recommended) Three states: pass (warn is a label on pass), fail, incomplete. The required inputs are as in S4.1, and the integrity "withheld" state maps to incomplete with its reason. FF12 group 11 and funds get "not applicable", which M01 reads as not pass (no gated adds) until a sector gate exists. Why: preserve capital (l. 147); no gate without a test. Gets wrong: ETV and any bank never get M01 tranche adds.
- (b) N/A reads as pass. Gets wrong: a distressed bank gets gated adds with no test at all.
- (c) Keep the approved text (only Z skipped for financials). Gets wrong: banks get an OCF runway that deposits make meaningless.

**4.6 Input age** (new)
- (a) (recommended) Facts older than the latest periodic filing are labelled "as of <date>". Foreign annual filers may use annual-only burn, labelled, for up to 16 months (one 20-F cycle); beyond that, incomplete. Domestic filers rely on the S1.6 overdue state. GFS today: "pass, annual only, as of 2025-12-31". Why: GFS's 6-Ks carry no XBRL, so the format, not distress, causes the gap. Gets wrong: a foreign filer can deteriorate for over a year unseen.
- (b) A 6-month maximum age for all. Gets wrong: GFS is incomplete for about half of each year.
- (c) No age rule (pack). Gets wrong: inputs of any age pass silently.

**4.7 8-K event triggers and clearing** (new)
- (a) (recommended) 1.03 fails and never clears automatically. 2.04 fails until a later periodic filing shows no breach or forbearance text and the owner resolves the review. 3.01 is classified from its text: final delisting or a missed cure fails; a deficiency notice with a cure period warns plus review; a transfer of listing is a note. INFQ's 3.01 is read at build (P2). Why: Item 3.01 covers voluntary transfers. Gets wrong: a deficiency that ends in delisting only warns until the final notice.
- (b) Any 1.03, 2.04 or 3.01 fails until the owner clears it (pack, plus clearing). Gets wrong: INFQ, and transfers like Dillard's, fail.
- (c) Fail only for the quarter of the 8-K. Gets wrong: an acceleration with no bankruptcy clears while the debt is still due.

**4.8 Capex-funded review below 6 quarters, and M01** (new)
- (a) (recommended) While the review is open, rule-3 adds are allowed and rule-7 strength is blocked. Why: OCF-positive firms can cut capex, but a short runway should not add strength. Gets wrong: Intel FY2024 (5.6) gets adds without the owner's review.
- (b) Plain pass (pack). Gets wrong: Intel FY2024 gets full beyond-2σ strength with its review open.
- (c) Blocks both. Gets wrong: same as 4.2b in effect; Intel gets no adds at OCF +8,288.

**4.9 Massive negative FCF (Red Flag 4)** (new)
- (a) (recommended) An `fcf_burn` information row now: TTM FCF ÷ revenue and ÷ liquidity, labelled operating burn vs capex-funded, with the A2 split and M05 bookings as context. The warning threshold is set at Part 8 calibration, as in 3.8a. Why: no sourced cut-off, and capex into demand is bullish (capex 2). Gets wrong: AMZN's ~54B a year draws no warning until calibration.
- (b) Warn now on any negative TTM FCF at a capex-funded name. Gets wrong: AMZN, SPCX and Intel FY2024 warn every quarter of a build-out.
- (c) Runway only (pack). Gets wrong: Red Flag 4 never shows for a cash-rich burner.
