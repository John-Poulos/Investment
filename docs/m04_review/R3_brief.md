# M04 Round 3 — Dilution and financing pressure — brief

Updated for Round 1 answers (D-M04-2…13): tags and the `issuance_funded` gate settled (D-M04-8, -13), so 3.4 keeps only the base rule; 3.6 routes on the owner-confirmed stage (D-M04-7, -12); signals use `value_text` and "missing" rows (D-M04-9); share series per D-M04-2, total capex per D-M04-6.

**Decides:** issuance measure and bands (3.1–3.2), shelves and ATMs (3.3), when `financing_pressure` warns (3.4–3.7), and two unhandled red flags (3.8–3.9).
**Outline items:** Red Flag 2 "serial stock dilution for the company to survive" (l. 79); Red Flags 6 (l. 83), 1 (l. 78), 3 in part (SBC, l. 80); R2, D8.

## What the research says
- Net issuance predicts lower returns, mainly in the top quintile (S-new-11), surviving NYSE breakpoints and value weights (S-new-10); weaker after publication (S-new-9). Seasoned issuers lag about 7% a year for 5 years (S-new-29, S103).
- SBC is a real cost (S-new-30). A shelf is capacity, not a raise (S-new-31); 424B3/424B7 resales add no shares (S-new-r3-2); ATMs are 43% used (S-new-32).
- Diluted counts move with the profit sign (S-new-34); same-filing pairs are split-safe except across an IPO or de-SPAC (S-new-1); an 8-K 3.02 names a cause, not an amount (S-new-r3-3). Downgrades precede −10% to −14% a year (S-new-r3-1).

## Worked example
Log change in basic weighted-average shares, both values from one filing. Bands: CY2025 frame percentiles of positive issuers; the top quintile starts at +60.1% (all filers), +19.0% (float ≥ $75M), +12.1% (float ≥ $700M) (S-new-r3-4).

| Name | Issuance | Band: all / ≥$75M / ≥$700M | Cause | Tag, stage, gate | 3.4a as drafted | 3.4a + 3.5a–3.7a |
|---|---|---|---|---|---|---|
| MSTR | CY2025 +44.2%; Q2 2026 +28.1% (cover +35.5%) | Q4 / top / top | ATM programs (stated strategy) | `asset_treasury`: liquidity-only gate (D-M04-8, -13) | `m04_dilution` review | review |
| BA | CY2025 +17.5%; Q2 2026 +4.5% | Q4 / Q4 / top | Oct 2024 raise: 129.4M common + 115M mandatory units | stage no 2 of 3 → owner confirms (D-M04-7, -12); gate fails Q2 2024 (runway 3.1), passes 2025–26 | **no warning** | **warns** (any stage) |
| INTC | CY2025 +5.8%; Q2 2026 +16.8% (cover +15.2%) | CY2025 Q3 / Q4 / Q4; Q2 2026 top on ≥$700M | three 3.02 placements, 735.1M shares | gate warns FY2024 (runway 5.6); 2025–26 at build | warns if the gate still warns | same, cause shown |
| META | −0.5% | repurchaser | buybacks 2.19× SBC | passes | information | information |
| SPCX / INFQ | +100.2% / +1,310% | top everywhere | IPO / de-SPAC (INFQ `spac_shell` to 2026-02-13) | stage unconfirmed, < 3 years (D-M04-7) | `not_meaningful` | `not_meaningful` |

- As drafted, a raise refills cash before the weighted average shows the shares, so Boeing's 2024 survival raise, the outline's own case, never warns.
- BA mandatory convertible (about 2027-10-15): 115M × 0.2914–0.3497 = 33.5M–40.2M shares = **4.24–5.09%** of 790,370,020 cover shares (pack: 3.7–4.4%).

## All cases
| Outcome | Cases (pack numbers) |
|---|---|
| Information only | 1 routine employee issuance; 2 buybacks offsetting SBC (META); 3 net buyback; 9 profit-sign flip; 13 shelf or WKSI shelf; 14 baby-shelf headroom; 20 rule change |
| Not common dilution | 11 ATM capacity vs sales; 12 preferred or debt supplements (MSTR preferred, GOOG 28 424Bs); 22 resale and lock-up supply |
| `not_meaningful` until post-event pairs | 21 IPO year (SPCX); 23 de-SPAC (INFQ); 29 inconsistent frame pair; 6 common-control exchange |
| Cause label | 6 share-paid acquisition; 7 strategic placements (INTC); 8 split or 3.03 recap; 17 3.02 below threshold; 18 weighted-average lag |
| Warning or review | 4 extreme ATM issuer (MSTR, review via `asset_treasury`); 5 `issuance_funded` (D-M04-13); 19 short vs long runway |
| Overhang (`m04_overhang`) | 15 convertibles; 16 warrants (INFQ 4.63% gross / 0.78% net); 25 mandatory (BA); 26 contingent warrants (INTC 240.5M) |
| Data defects | 10 multi-class (cover count from R1, D-M04-2); 24 Up-C; 27 IFRS (GFS); 28 unit mis-tag; 30 rating text classes |
| **Added** | 31 survival raise the gate shows repaired before the shares show (BA 2024–25); 32 escrowed shares in basic EPS but not the cover count (INTC 71M) |

**Completeness:** complete for the 15 operating watchlist names with 31–32. Omitted (none on the watchlist): rights offerings, tracking stocks, spin-offs, share lending, Up-C beyond a text finder.

## Suggestions
- **S3.1** `net_issuance_yoy` per 3.1a; cover check on `shares_cover` (D-M04-2). **S3.2** Bands per 3.2a; blank checks out by SIC 6770; about 7 requests a year. **S3.3** 5-year composite issuance beside it.
- **S3.4** SBC block on the D-M04-2 `sbc` series (÷ revenue, ÷ OCF, buyback offset); FCF after SBC on total capex; owner earnings as information (D-M04-6).
- **S3.5** Financing capacity from metadata and fee exhibits; 424B4 lock-up as a release schedule. **S3.6** Overhang gross and net ÷ `shares_cover`; INTC's 71M escrow beside its contingent warrant.
- **S3.7** Old engine: keep severity words and ATM phrases; drop bare "covenant"/"waiver of"; rating classifier needing no agency name. **S3.8** Regression: BA mandatory 4.24–5.09%; BA 2024–25 warns; INTC escrow cause.
- **S3.9** Review volume: `m04_dilution` 1 (MSTR; no `issuance_funded` entries yet); `m04_overhang` about 10; `m04_rating` 1 (INTC); one M04 cap.
- **S3.10** Signals per D-M04-9: states in `value_text` (`warn`, `review`, `info`, `not_meaningful`), `value` NULL; "missing: <reason>" rows; weakest-input grade. Replaces the pack's "1 on, 0 off, absent".

## Check flags
- Settled, removed: tag vocabulary (`asset_holding` → `asset_treasury`, D-M04-8); liquidity-only gate for issuance-funded names (D-M04-13); stage rule (D-M04-7); signal encoding (D-M04-9).
- "Runway 6–8 quarters" missed capex-funded firms warning below 6 (Intel FY2024, 5.6). Fixed: 3.4a reads gate state fail or warn.
- No conflict with D16, D27, M01 rules 3 and 7: `financing_pressure` never feeds them.

## Gaps
**Closed:** Intel's 60M gap = 71M escrowed shares (Q2 2026 10-Q Note 4); Intel 424B7 is a Commerce resale, no new shares; BA sold both the units and the common; INTC cut BBB+ → BBB (August 2025); blank-check SIC path exists; S-new-68 = S-new-r3-6. Partly: SPCX lock-up staggered; GOOG/AMZN 424Bs are bond deals.
**Needs the owner's probe** (`scripts/probe_m04_r3.py`, about 75–95 requests): P1 SPCX lock-up · P2 SPCX conversion count · P3 INFQ frame pair · P4 MSTR notes and ATM tables · P5 Up-C example · P6 blank-check overlap · P7 GOOG/AMZN 424B security types.

## Questions
**3.1 Issuance measure**
- (a) (recommended) Basic weighted average, same quarter a year apart, one filing; cover-to-cover check on `shares_cover` (D-M04-2); `not_meaningful` across IPO, de-SPAC or recast. Why: split-safe, universal, not moved by the profit sign. Gets wrong: lags late sales (MSTR +28.1% vs +35.5% cover); the check shows it.
- (b) Period-end count. Gets wrong: META, MSTR, GOOG have no non-dimensional count (D-M04-2 fills only the cover count).
- (c) Diluted weighted average. Gets wrong: MSTR swings 11.5% with the profit sign.

**3.2 Bands, universe and window**
- (a) (recommended) Yearly percentiles, same-filing pairs, float ≥ $700M, blank checks out; top quintile "extreme" (+12.1% in CY2025); 12-month window, 5-year composite beside it. Why: nearest to the NYSE-breakpoint evidence (S-new-10). Gets wrong: about 1,400 small firms read "extreme" (intended).
- (b) Float ≥ $75M (cut +19.0%). Gets wrong: BA +17.5% and INTC +16.8% fall to Q4.
- (c) All filers (cut +60.1%). Gets wrong: MSTR +44.2% is only Q4.
- (d) Fixed 5/10/20% (unsourced). Gets wrong: at 20%, BA and INTC are missed.
- (e) No bands. Gets wrong: 3.4 has no "extreme" condition.

**3.3 Shelves and ATM programs**
- (a) (recommended) Metadata plus the fee exhibit per 424B (about 250 requests one-off); text only for 424B4 lock-ups and resale counts. Why: real amounts, no prospectus reading. Gets wrong: "capacity unknown" where fees were paid with the shelf.
- (b) Read all 424B text. Gets wrong: multi-MB documents (SPCX over 10 MB) for no gain.
- (c) Metadata only. Gets wrong: MSTR preferred counts as common; GOOG debt and INFQ resale count as issuance.

**3.4 When it warns** (narrowed: tags and the `issuance_funded` gate settled by D-M04-8, D-M04-13)
- (a) (recommended) Untagged and `issuance_funded` names warn when the issuance is extreme or serial (3.5) and the gate state is fail or warn (D-M04-13 adds: `issuance_funded` with a passing gate outside the warn band → `m04_dilution` review). `asset_treasury` and `reit` (liquidity-only gate) → `m04_dilution` review; `fund`, `financial` excluded; `spac_shell` `not_meaningful`. One condition alone is information. Why: issuance alone fires on every small cap. Gets wrong: an "incomplete" gate gives no warning (shown as a data gap).
- (b) Extreme issuance alone. Gets wrong: MSTR warns every quarter; INTC and BA warn whatever their gate.
- (c) `asset_treasury` and `reit` also warn on a liquidity-gate warn. Gets wrong: MSTR's stated strategy warns on every bitcoin swing.

**3.5 Serial dilution to survive**
- (a) (recommended) The gate condition also holds if the gate failed or warned in any of the 4 quarterly filings before the share-count jump; the cover change is tested too; `serial` = extreme in ≥ 2 of 3 years or top-quintile composite (starting values). Why: a raise repairs the gate before the weighted average shows the shares. Gets wrong: a firm raising from strength just after a brief gate warning also warns (cause shown).
- (b) Both conditions at once (as drafted). Gets wrong: BA fails Q2 2024, raises October 2024, turns extreme in CY2025 with the gate passing: no warning.
- (c) Serial label only. Gets wrong: BA's single raise is not serial: no warning.

**3.6 Stage routing (R2)** (reworded for D-M04-7, D-M04-12)
- (a) (recommended) Route on the owner-confirmed stage (D-M04-12). A gate fail warns at every stage. A gate warn warns for mature, shake-out and decline, and goes to `m04_dilution` review for introduction and growth. Under 3 years: both readings, labelled, uncounted (D-M04-7). The engine may propose `issuance_funded` for a confirmed introduction stage; only the owner edits the file (D-M04-8). Why: honours R2 without hiding a survival raise. Gets wrong: a growth firm with a sliding runway is only a review item until it fails.
- (b) Introduction or growth → review at any gate state. Gets wrong: a young firm that fails the gate and sells shares to survive is only a review item.
- (c) Owner tag only (as drafted). Gets wrong: an untagged young firm is warned like a mature one.

**3.7 Does a linked cause stop the warning?**
- (a) (recommended) Only non-cash causes (share-paid acquisition, IPO or de-SPAC recast, split, 3.03 recap) make it information. Cash raises (424B5, ATM, 3.02 placement) keep the warning when the gate fails or warns, cause shown. Why: the gate, not the buyer, shows whether shares were sold to survive. Gets wrong: Intel 2025 may warn although strategic buyers chose to invest.
- (b) Any linked cause → information (pack). Gets wrong: BA's October 2024 raise does not warn.
- (c) Linked cash cause → review. Gets wrong: BA's survival raise waits in the queue.

**3.8 Debt against revenue (Red Flag 6)**
- (a) (recommended) `debt_to_revenue` (total debt ÷ TTM revenue) and net debt ÷ EBITDA as information rows in Round 4, against own 3-year range and peer robust z, missing kept missing; no vote until Part 8, as for D-M04-11. Why: no round measures it; no sourced cut-off exists. Gets wrong: no warning until calibration.
- (b) Warn now above a starting value (illustrative: debt > 1× revenue). Gets wrong: capital-heavy sectors warn by construction.
- (c) Maturity wall only (4.3). Gets wrong: long-dated debt at 5× revenue (illustrative) passes every test.

**3.9 Cash burn with no share gains (Red Flag 1)** (designed in Rounds 4 and 6)
- (a) (recommended) A joint warning row: burn (runway warn or fail, or FCF on total capex < 0, D-M04-6) with market share flat or falling (Round 6 test); never a gate input. Why: the outline pairs the two. Gets wrong: often "missing" where no share data exists.
- (b) Both side by side, no joint rule. Gets wrong: the owner pairs them by eye.
