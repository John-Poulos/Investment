# M04 Round 3 — Dilution and financing pressure — brief

**Decides:** how issuance is measured and banded (3.1–3.2), how shelves, 424Bs and ATMs are read (3.3), and when `financing_pressure` warns (3.4, new 3.5–3.7). New 3.8–3.9 cover two outline red flags no round handles yet.
**Outline items:** Red Flag 2 "serial stock dilution for the company to survive" (l. 79), the main item. Red Flag 6 "large debt against revenue" (l. 83) and Red Flag 1 "cash burn with no share gains" (l. 78), both missing from the pack. Red Flag 3 in part (SBC counted as a cost, l. 80). R2 (stage-aware red flags), D8 (review queue).

## What the research says
- Net issuance predicts lower returns, mainly in the top quintile (−0.27% a month; small option issues earn positive returns) (S-new-11). It survives NYSE breakpoints and value weights (−0.66% a month, t −4.45) (S-new-10) and is weaker after publication (S-new-9).
- Issuers underperform afterwards: seasoned offerings by about 7% a year for 5 years; debt issuers and total external financing too (S-new-29, S103).
- SBC is a real cost (S-new-30). META FY2025 spent 2.19× its SBC on buybacks to cut basic shares 0.5%.
- A shelf is capacity, not a raise (S-new-31). The 424B form type names the supplement; 424B3/424B7 resales add no shares (S-new-r3-2). ATMs are 43% used on average (S-new-32).
- Diluted counts move with the profit sign (S-new-34). Same-filing comparatives are split-safe, but not across an IPO or de-SPAC (S-new-1). An 8-K 3.02 names a cause, not an amount, and is absent below 1% (S-new-r3-3).
- Downgrades are followed by −10% to −14% in a year; upgrades by nothing (S-new-r3-1). The old engine's rating substrings hit about a third of 10-Ks, mostly hypotheticals (S-new-r3-4).

## Worked example
Log change in basic weighted-average shares, both values from one filing. Bands are CY2025 frame percentiles of positive issuers (S-new-r3-4). The top quintile starts at +60.1% (all filers), +19.0% (float ≥ $75M) and +12.1% (float ≥ $700M).

| Name | Issuance | Band: all / ≥$75M / ≥$700M | Cause | Gate (Round 4) | 3.4a as drafted | 3.4a + 3.5a + 3.7a |
|---|---|---|---|---|---|---|
| MSTR | CY2025 +44.2%; Q2 2026 +28.1% (cover +35.5%) | Q4 / top / top | ATM programs (stated strategy) | tag `asset_treasury` | `m04_dilution` review | review |
| BA | CY2025 +17.5%; Q2 2026 +4.5% | Q4 / Q4 / top | Oct 2024 raise: 129.4M common + 115M mandatory convertible units | fails Q2 2024 (runway 3.1); wall passes 2025–26 | **no warning** | **warns** |
| INTC | CY2025 +5.8%; Q2 2026 +16.8% (cover +15.2%) | CY2025 Q3 / Q4 / Q4; Q2 2026 top on ≥$700M | three 8-K 3.02 placements, 735.1M shares | FY2024 warns (runway 5.6); 2025–26 not in the pack | warns if the gate still warns (the pack's reading said information) | same, with the cause label |
| META | −0.5% | repurchaser | buybacks 2.19× SBC | passes | information | information |
| SPCX / INFQ | +100.2% / +1,310% | top everywhere | IPO / de-SPAC | — | `not_meaningful` | `not_meaningful` |

- **Universe:** on all filers MSTR is not "extreme"; on float ≥ $75M, BA and INTC drop to Q4 despite adding about 17% to their share counts.
- **Warning rule:** as drafted, it needs extreme issuance and a failing gate at once. A raise refills cash before the weighted average shows the shares, so Boeing's 2024 survival raise, the outline's own case, never warns.
- **BA mandatory convertible (about 2027-10-15):** 115M units × 0.2914–0.3497 = 33.5M–40.2M shares = **4.24–5.09%** of 790,370,020 cover shares (pack said 3.7–4.4%; see Gaps).

## All cases
| Outcome | Cases (pack numbers) |
|---|---|
| Information only | 1 routine employee issuance; 2 buybacks only offsetting SBC (META); 3 net buyback; 9 profit-sign flip; 13 shelf or WKSI shelf; 14 baby-shelf headroom; 20 rule change (cap in config) |
| Not common dilution | 11 ATM capacity vs sales; 12 preferred or debt supplements (MSTR preferred, GOOG 28 424Bs); 22 resale and lock-up supply |
| `not_meaningful` until post-event pairs | 21 IPO year (SPCX); 23 de-SPAC under one CIK (INFQ); 29 inconsistent frame pair; 6 common-control exchange |
| Cause label | 6 share-paid acquisition; 7 strategic placements (INTC); 8 split or 3.03 recap; 17 3.02 below threshold; 18 weighted-average lag |
| Warning or review | 4 extreme ATM issuer (MSTR); 5 issuance-funded model; 19 short vs long runway |
| Overhang (`m04_overhang`) | 15 convertibles; 16 warrants (INFQ 4.63% gross / 0.78% net); 25 mandatory (BA); 26 contingent warrants (INTC 240.5M) |
| Data defects | 10 multi-class; 24 Up-C; 27 IFRS (GFS); 28 unit mis-tag; 30 rating text classes |
| **Added** | 31 survival raise that the gate shows as repaired before the shares show (BA 2024–25); 32 escrowed shares in basic EPS but not in the cover count (INTC 71M) |

**Completeness:** complete for the 15 operating watchlist names once 31–32 are added. Known omissions (none on the watchlist): rights offerings, tracking stocks, spin-offs, share lending, Up-C beyond a text finder.

## Suggestions
- **S3.1** `net_issuance_yoy` per 3.1a, tag `wavg_basic_same_filing`.
- **S3.2** Bands per 3.2a. *Changed:* blank checks out by SIC 6770 from stored EFTS hits (as M02 does); five float frames, about 7 requests a year.
- **S3.3** 5-year composite issuance beside net issuance.
- **S3.4** SBC block (÷ revenue, ÷ OCF, FCF after SBC, buyback offset). *Added:* capex per 1.5a, method-tagged (A2).
- **S3.5** Financing capacity from metadata and fee exhibits. *Changed:* 424B4 lock-up stored as a release schedule (trigger, % of holdings, holder group).
- **S3.6** Overhang, gross and net. *Changed:* ÷ cover count (1.1), INFQ fixture 4.63% / 0.78%; INTC's 71M escrow shares listed beside its contingent warrant.
- **S3.7** Old engine: keep severity words and ATM phrases; drop bare "covenant"/"waiver of"; rating-sentence classifier that needs no agency name.
- **S3.8** Regression cases. *Changed:* BA mandatory 4.24–5.09%. *Added:* BA 2024–25 must warn; INTC escrow cause.
- **S3.9** Review kinds. *Changed:* `m04_overhang` baseline about 10 instruments; `m04_rating` baseline 1 (INTC); per-round cap folded into the one M04 cap.
- **S3.10** Signals. *Changed:* missing → "missing: <reason>" row (1.8a); `not_meaningful` and band labels in `value_text`; grade = weakest input.

## Check flags
- Red Flags 2, 6, 1, R2 stage routing and linked causes → questions 3.5, 3.8, 3.9, 3.6, 3.7.
- 3.4a tag list differs from 1.7 (`asset_holding` vs `asset_treasury`; `fund`, `financial`, `spac_shell` missing). Fix: route per 1.7.
- Liquidity-only gate change asked in 1.7, 3.4a and Round 4. Fix: drop from 3.4; moot if 4.1a passes.
- "Runway 6–8 quarters" misses capex-funded firms warning below 6 (Intel FY2024, 5.6). Fix: gate state fail or warn.
- 3.2a "why" partly picks the universe by where the watchlist lands. Fix: lead with the research.
- No conflict with D16, D27, M01 rules 3 and 7: `financing_pressure` never feeds them (4.1a).

## Gaps
**Closed now**
- Intel 60M gap: 71M escrowed shares are in basic EPS, not in the cover count (Q2 2026 10-Q Note 4, intc.com).
- Intel 424B7: Department of Commerce resale of up to 673.8M shares; no new shares (Ex. 5.1, intc.com).
- BA sold 115M units and 129.4M common: FY2024 proceeds ($5,657M; $18,200M) exceed both base-deal grosses in Boeing's pricing release.
- INTC "downgraded": an actual cut, BBB+ → BBB, August 2025, agency not named (FY2025 10-K, intc.com).
- Blank-check SIC path exists in the repo (`sec/fulltext.py` `sics`; `themes/industries.py` `BLANK_CHECK`).
- S-new-68 and S-new-r3-6 are the same 8-Ks; one ID at merge.

**Partly closed (secondary only):** SPCX lock-up is staggered (field shape only); MSTR has about 7 instruments; GOOG/AMZN 424Bs match bond deals.

**Needs the owner's live probe** (new `scripts/probe_m04_r3.py`, about 75–95 requests; P2–P4 local): P1 SPCX 424B4 lock-up · P2 SPCX conversion count · P3 INFQ frame pair · P4 MSTR notes and ATM tables · P5 Up-C example (RYAN, BROS, FLNC) · P6 blank-check overlap · P7 GOOG/AMZN 424B security types.

## Questions
**3.1 Issuance measure**
- (a) (recommended) Basic weighted average, same quarter a year apart, one filing; cover-to-cover check; `not_meaningful` across IPO, de-SPAC or recast. Why: split-safe, universal, not moved by the profit sign. Gets wrong: lags late sales (MSTR +28.1% vs +35.5% cover); the check shows it.
- (b) Period-end count. Gets wrong: META, MSTR, GOOG go missing.
- (c) Diluted weighted average. Gets wrong: MSTR swings 11.5% with the profit sign.

**3.2 Bands, universe and window** (why reworded)
- (a) (recommended) Yearly percentiles, same-filing pairs, float ≥ $700M, blank checks out; top quintile "extreme" (+12.1% in CY2025); 12-month window, 5-year composite beside it. Why: approximates the NYSE-breakpoint result the evidence rests on (S-new-10); float proxy, equal-weighted. Gets wrong: about 40% of all positive issuers (about 1,400 firms) read "extreme" (intended).
- (b) Float ≥ $75M (cut +19.0%). Gets wrong: BA +17.5% and INTC +16.8% fall to Q4.
- (c) All filers (cut +60.1%). Gets wrong: MSTR +44.2% is only Q4.
- (d) Fixed 5/10/20% cut-offs (unsourced). Gets wrong: at 20%, BA and INTC are missed.
- (e) No bands. Gets wrong: 3.4 has no "extreme" condition to test.

**3.3 Shelves and ATM programs**
- (a) (recommended) Metadata plus the fee exhibit per 424B (about 250 requests one-off); text only for 424B4 lock-up schedules and resale counts; sales from proceeds and share counts. Why: real amounts without reading prospectuses. Gets wrong: "capacity unknown" where fees were paid with the shelf.
- (b) Read all 424B text. Gets wrong: a multi-MB document per 424B (SPCX over 10 MB) for no gain.
- (c) Metadata only. Gets wrong: MSTR preferred counts as common; GOOG debt and INFQ resale count as issuance.

**3.4 When it warns** (reworded; recommendation kept)
- (a) (recommended) Warn when all three hold:
  - the issuance is extreme, or serial (3.5);
  - the gate state is fail or warn under any Round 4 rule;
  - no 1.7 tag routes it. `issuance_funded`, `asset_treasury` and `reit` go to `m04_dilution` review; `fund`, `financial` and `spac_shell` are excluded.

  One condition alone is information. Why: issuance alone fires on every small cap and on MSTR's strategy. Gets wrong: an "incomplete" gate gives no warning (shown as a data gap).
- (b) Extreme issuance alone. Gets wrong: MSTR warns every quarter; INTC and BA warn whatever their gate.
- (c) No model tag. Gets wrong: MSTR's strategy warns whenever its gate warns.

**3.5 Serial dilution to survive** (new)
- (a) (recommended) The gate condition also holds if the gate failed or warned in any of the 4 quarterly filings before the share-count jump; the cover-to-cover change is tested too; label `serial` when extreme in ≥ 2 of the last 3 years or composite issuance is top quintile (4 quarters and 2-of-3 are starting values). Why: a raise repairs the gate before the weighted average shows the shares. Gets wrong: a firm that raised from strength just after a brief gate warning also warns (cause label shown).
- (b) Both conditions at once (as drafted). Gets wrong: BA fails Q2 2024, raises October 2024, turns extreme in CY2025 when the gate passes: no warning.
- (c) Serial label only. Gets wrong: BA's single raise is not serial: no warning.

**3.6 Stage routing (R2)** (new)
- (a) (recommended) A gate fail warns at every stage. A gate warn:
  - warns for mature, shake-out and decline;
  - goes to `m04_dilution` review for introduction, growth, and ambiguous or unassigned stages.

  The engine proposes `issuance_funded` from a confirmed introduction stage; the owner's tag overrides. Why: honours R2 without hiding a survival raise. Gets wrong: a growth firm with a sliding runway is only a review item until it fails.
- (b) Introduction or growth → review at any gate state. Gets wrong: BA reads "introduction" in 2024 (1.6), so its survival raise is only a review item.
- (c) Owner tag only (as drafted). Gets wrong: an untagged young firm is warned like a mature one; ambiguous stage never reaches review.

**3.7 Does a linked cause stop the warning?** (new)
- (a) (recommended) Only non-cash causes (share-paid acquisition, IPO or de-SPAC recast, split, 3.03 recap) make it information. Cash raises (424B5, ATM, 3.02 placement) keep the warning when the gate fails or warns, with the cause shown. Why: the gate, not the buyer, shows whether shares were sold to survive. Gets wrong: Intel 2025 may warn although strategic buyers chose to invest (its 2025–26 gate state is computed at build).
- (b) Any linked cause → information (the pack's readings). Gets wrong: BA's October 2024 raise does not warn.
- (c) Linked cash cause → review. Gets wrong: BA's survival raise waits in the queue instead of warning.

**3.8 Debt against revenue (Red Flag 6)** (new)
- (a) (recommended) `debt_to_revenue` (total debt ÷ TTM revenue) and net debt ÷ EBITDA as information rows in Round 4, against own 3-year range and peer z, method-tagged, missing kept missing; warning threshold set at Part 8 calibration. Why: no round measures it; no sourced cut-off exists. Gets wrong: no warning until calibration.
- (b) Warn now above a starting value (illustrative: debt > 1× revenue). Gets wrong: capital-heavy sectors warn by construction.
- (c) Maturity wall only (4.3). Gets wrong: long-dated debt at 5× revenue (illustrative) passes every test.

**3.9 Cash burn with no share gains (Red Flag 1)** (new; designed in Rounds 4 and 6)
- (a) (recommended) A joint warning row: burn (runway warn or fail, or FCF < 0) with market share flat or falling (Round 6 test); never a gate input. Why: the outline pairs the two. Gets wrong: often "missing" where no share data exists.
- (b) Both side by side, no joint rule. Gets wrong: the owner pairs them by eye.
