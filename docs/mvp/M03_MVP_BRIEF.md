# M03 Leaders & S-curve — MVP brief
Updated 2026-10-13 · Source: docs/M03_DESIGN_PACK.md (research) · Status: for owner decision (one sitting)

Outputs are research signals, not financial advice.

## Purpose in one paragraph
Where each revenue curve sits on its S-curve, and which curve leads its category. Outline: "Catch the S-curve early" (space → leader → financials → moat → entry; TSLA layers, AMD data center, MU "structural product inside a cyclical ticker") and "Identify the leaders" items 1 and 3. Binding: **R6** (type A young company on its first curve; type B new curve inside an established company, from segments); **R14** (dollar wealth over T-bills — the outline's "0.3% … half the return" matches 86 of ~26,000 stocks, 0.33%, creating about half the $35T, S01: wealth, not returns); D8, D9, D10, D13/D14, D16, D-M02-3 (no blended score); M04: `fact_dim` with recasts never merged (D-M04-42), peers (D-M04-4, -5), small n (D-M04-52), owner-confirmed stage (D-M04-7, -12), tags (D-M04-8). **Departs from the outline:** no TAM (paid, S93; new gap); product competitiveness, roadmaps and switching costs → M06; "share accelerating" is read only as the filing growth gap in `leader_rank` plus M04's `market_share_chg_pp` (8a owner entries, DS16) shown beside the rank, not rebuilt. **Owned elsewhere:** S-curve item 2 (latency before appreciation) → M11 R4 milestones; item 4 (position before the crowd) → M02 crowding flag (D-M02-10) and M08. **Outline examples not covered:** AMD and ALAB are neither core nor promoted, so their segment curves are not stored (see Q03.1).

## Data already stored that the MVP uses
| Need | Stored in (code) | Gap |
|---|---|---|
| Segment/product revenue, operating income; 10-K/10-Q instances of 3 years, core + promoted | `fact_dim` (0035); `sec/instance_dim.py` `rows()`, `recasts()`; `financials/units_view.py` `segment_table()`, `renames()` | DS12: tracked tier not read (D-M04-80); company axes skipped. Intersegment rows are stored only when tagged on `srt:ConsolidationItemsAxis`, and `segment_table()` filters them out: the external split is checked at build |
| Company revenue (from 2009) | `fact`, `series`, `sec/asof.py` | — |
| Firm stage | `company_stage` (0032) | 8 of 15 open (BA, INFQ, INTC, MU, NVDA, SPCX, TSLA, RIVN) |
| Tags, themes, peers | `company_models.toml`, `entity_link`; `theme`, `theme_company`, `tier_member`; `peer_member`, `financials/peer_facts.py` | Non-SEC peers missing |
| All-filer CY revenue | `frame_value`, `sec/frames.py`, `financials/peers.py` | Only CY2024–25 stored (CY2024 on 2 tags); CY2019–23 ≈ 10–15 requests; runs then start 2020, and longer company histories read `at_least` |
| Signal writer | `signals.py` `write_signal` | Key has no curve field (Q03.8) |
| Market size (K, TAM) | — | New gap, no free source (S93). The pack's DS16/DS17 clash with the register (DS16 = market share, M04 8a; DS17 = credit ratings): take the next free DS number at the build commit |

## MVP signals (4)
| Signal | value / value_text | Meaning | Inputs | MY | PT | ST | Grade |
|---|---|---|---|---|---|---|---|
| `curve_type.<label>` | value: % of company revenue. Text: A / B / n_a / unassigned | R6 type | `fact_dim`/`fact`, `company_stage`, tags, owner override | info | info | info | A (an owner confirmation keeps the filing inputs' A, as `lifecycle_stage` does in `financials/stage.py`); B when the owner sets a type with no stored filing input (D14) |
| `curve_stage.<label>` | value: latest fiscal-year growth %. Text: emerging / accelerating / steep / past_inflection / declining / not_identified | Position on the curve | Fiscal-year curve revenue and its dollar increment | ✓ | info | info | A, weakest deciding filing |
| `leader_rank.<label>` | value: rank. Text: "k of n with data" | Dollar rank in the category; growth gap to the category median in `method` | Latest fiscal-year curve revenue in the category | ✓ | info | info | A; "among SEC filers" when a peer does not file |
| `growth_runs.<label>` | value: years. Text: `at_least` when the run reaches the start of history | Consecutive years above the all-filer median growth; CKL baselines in `method` | Curve growth; median from the CY frames | ✓ | info | info | A |

**Rules for all four:**
- Keyed by `cik` (ticker for display, D-M04-74); one row per timeframe; numbers in `value`, states in `value_text`; `source_ref` = newest accession "+N", inputs in `method` (D-M04-9).
- `as_of` is the filing date of the newest deciding annual report.
- Missing data is written as "missing: <reason>", never as 0.
- A rank needs at least 2 curves with data.
- PT and ST stay info until M01 builds those profiles.

## Worked example (real figures from the pack's primary sources unless marked)
**AMZN AWS** (S-new-M03-19/20). Figures from the releases; the FY2023–25 10-Ks inside the 3-year window should hold 2021–25 (checked at build).

| Year | Revenue $M | Growth | Increment $M |
|---|---|---|---|
| 2021 | 62,202 | — | — |
| 2022 | 80,096 | +28.8% | 17,894 (peak) |
| 2023 | 90,757 | +13.3% | 10,661 |
| 2024 | 107,556 | +18.5% | 16,799 (still below 2022) |
| 2025 | 128,725 | +19.7% | 21,169 (new peak) |

- **Pack correction.** The pack says the increment stayed below the 2022 peak for "one year only". In fact 2024 was below it too, so the pack's rule (below the peak for at least 2 years) would read `past_inflection` in 2024.
- **MVP rule.** `past_inflection` also needs the latest increment not to be rising. Under that rule, 2024 and 2025 both read `accelerating`, with the note "new curve or cycle? Read with `cvd_state` (pending M04 8a)".
- **Type.** AWS is 18.0% of $716,924M, so it is type B.

**NVDA Data Center** (S-new-M03-21/22/23)
- **Figures.** $47.5B → $115.2B → $193.7B. The increment grew 32.5 → 67.7 → 78.5 while growth fell from +217% to +142% to +68%. Both readings say `steep`, and K is not identified.
- **Type.** Data Center is 89.7% of $215.9B, but the M04 stage is still open, so it reads unassigned.
- **Check at build.** If Data Center sits on a company axis that `fact_dim` skips, the Compute & Networking segment is used instead, labelled.

**Intel Foundry** (S-new-M03-24)
- **Figures** (2022 → 2023, as recast in the 2024-04-02 8-K, $M). Total revenue went from 27,491 to 18,910 (−31%), but external revenue from 474 to 953 (+101%), so 95% of the segment is captive. It is staged on external revenue, flagged "captive 95%", with the 2023 operating loss of (6,955) shown beside it — if the external split is tagged where `fact_dim` keeps it (else "external unknown", case 5).
- **Break.** The segment set changed between the FY2023 and FY2024 10-Ks, so the series starts with the FY2024 10-K's years, 2022–2025 (D-M04-42). The stage is computed at build on external revenue.

**INFQ**
- Periods before 2026-02-13 belong to the `spac_shell` (D-M04-8), so there are fewer than 2 fiscal years after that date. It reads `not_identified` and unassigned.

**Leader, category "cloud"**
- **Data.** AWS is $128.7B. Google Cloud is probably a stored segment (checked at build). MSFT's Azure has no dollar figure; Intelligent Cloud is broader, so the owner decides whether to map it.
- **Result.** On the pack's checked figures: "missing: 1 of 3 with data", never a rank on zeros. If Google Cloud is stored, 2 of 3 and a rank is written. ("cloud" is an illustrative owner category.)
- **Mixed layers.** Ranking NVDA's chips against AWS's cloud inside "AI infrastructure" would be meaningless (Q03.3). META is a spender there, with no curve.

**growth_runs for AWS** (illustrative: an all-filer median of +8% each year)
- **Run.** "≥ 4 (stored history from 2021)".
- **Baselines.** Chance 6.25% for 4 years; CKL observed 10.2% for 4 years; for 5 years, 6.3% observed against 3.1% chance (S-new-M03-4).

**R14 card** (on the tab, not a signal; paraphrase of S01, not a verbatim quote)
> "About 4% of US-listed companies created all net dollar wealth above T-bills in 1926–2016; 86 created about half; about 57% of stocks trailed T-bills over their lives (Bessembinder 2018, S01). Dollar wealth, not a return forecast."

## Cases the rules must handle
1. **Curve source:** company (pure play, `fact`), segment (AWS) or product axis (NVDA Data Center?), axis labelled.
2. **Untagged curve** (MU HBM, TSLA robotaxi), skipped axis or company member: "missing: not disclosed as a fact"; owner may map another member.
3. **Segment set changed** (MU Q4 FY2025, INTC 2024): break, series restarts, never merged. Renamed member with agreeing values (BA): continued (`renames()`).
4. **Recast value:** the latest filing wins inside its 3 years; first-filed value on hover.
5. **Intersegment disclosed:** stage on external revenue, "captive" flag below 50% external; not disclosed: total, "external unknown".
6. **Fewer than 3 fiscal years or new segment:** `not_identified`.
7. **emerging:** curve < 10% of company revenue or first disclosed < 3 years ago, and growth > 40%.
8. **steep:** increment rising, growth falling (NVDA).
9. **accelerating:** increment and growth rising; note "new curve or cycle?" with `cvd_state`.
10. **One year below the increment peak** (AWS 2023): no change (the prior stage holds; with none, `not_identified`). **past_inflection:** ≥ 2 years below the peak and the latest increment not rising.
11. **declining:** revenue below its prior peak ≥ 2 fiscal years; under CYCLICAL_TROUGH it reads "held: cycle".
12. **Several match:** declining > past_inflection > emerging > accelerating > steep.
13. **Price-driven swings** (memory) read beside `cvd_state`; **acquisition year** marked, not a stage.
14. **Fund, treasury-asset, shell periods** (ETV, MSTR, INFQ pre-merger): n_a, no stage.
15. **Mature firm, curve ≥ 50%** (NVDA): unassigned until the owner overrides; **new listing** (SPCX): never typed by listing age.
16. **Off-calendar year** (NVDA, January): ±45 days (D-M04-5).
17. **Peer outside core and promoted:** company revenue only, if mapped "company = curve"; **non-SEC peer** (SK hynix, Samsung, TSMC): "missing: not an SEC filer", rank "among SEC filers".
18. **Mixed value-chain layers:** the owner names the category; a segment in two categories = two entries, overlap shown.
19. **Run reaching history start:** `at_least`. **All-filer median:** revenue > 0 in both years, robust to scaling errors (TIGO), labelled.

**How the rules can mislead (D9), with the guard:**
- Deceleration read as maturity: stage needs an increment peak.
- A one-year pause read as the inflection: the not-rising clause.
- Captive revenue read as a market curve: the captive flag.
- A recast read as growth: breaks.
- A watchlist made only of winners: the R14 card.
- CKL baselines are US 1951–1998: labelled "indicative".
- An HBM rank among SEC filers only: flagged.

## Deferred to the tuning phase
- S1.2 curve proposals (an owner file instead).
- S1.5 FSN, plus tracked-tier and older instances (request budget).
- S1.4 basis detector (`entity_link` covers INFQ).
- S2.2 components c/d and S2.4 (reuse M04 `gm_trend_pp` and DS16 later).
- S2.3 pioneer tags (needs deeper history).
- S3.1 `maturing` and quarterly TTM (segment Q4 derivation).
- S3.3 K interval (S-new-M03-11/12).
- Unit curves and S3.5 adoption (low value now).
- Calibration including failed curves, S3.6/3.3/4.3 (needs labels).
- S4.1 `wealth_created` (needs FRED, shares, delisted coverage).
- S4.3/S4.4 tenure (history too short).
- Round 5 tier, caps and PT alerts (M11 sitting); `stage_break`, `increment_trend` and `curve_share` folded into `method` and `value`.
- S4.5 SOURCES fixes (S01 ≈ 57%; merge S-new-M03-16 into S-new-60) at the build commit.

## Questions for the owner
**Q03.1 Where curves come from**
- a) *Recommended.* `fact_dim` as stored (core and promoted; about 5 fiscal years). Tracked names and peers enter as whole-company curves only. No new requests. For the outline's AMD (and ALAB) curves, the owner may promote them in the UI as RIVN was (D-M02-11, D-M04-81): about 25 requests plus about 12 instance reads each, once. Why: the stored years already cover AWS, NVDA, INTC and MU (D-M04-42, -80).
- b) As (a), plus older 10-K instances: about 150 requests once (estimate), 2–3 minutes, for deeper runs.
- c) Extend the 7a instance reads to the whole tracked tier (about 12 reads per name; amends D-M04-80, which gives tracked names no instance reads).

**Q03.2 Mapping and typing curves**
- a) *Recommended.* An owner-edited `config/m03_curves.toml` (ticker, member or "company", label, category, optional type). The app never writes to it, and the tab lists unmapped members. No review items: ambiguous readings (unassigned types, "new curve or cycle?") go to an "Open for the owner" list on the tab, answered in the file — D8's queue in MVP form. Why: same pattern as `company_models.toml` (D-M04-8), and no queue load. Choose (b) for real queue items.
- b) Engine proposals through `propose()` (pack S1.2).
- c) Every segment becomes a curve automatically.

**Q03.3 What a category is**
- a) *Recommended.* An owner-named category per curve inside an M02 theme (default: the theme). Why: AI infrastructure mixes chips and cloud (worked example; LESSONS value chains).
- b) The M02 theme as is (pack 2.1a).
- c) 4-digit SIC.

**Q03.4 Stage method**
- a) *Recommended.* Rules on fiscal-year increment and growth (cases 6–12), with no K fit. A change is written at once and labelled "first reading" until the next year agrees. `maturing` is deferred. Why: K is biased before the inflection (S-new-M03-11, -12), and fiscal years avoid lumpy quarters.
- b) Quarterly TTM with 2 consecutive readings (pack S3.1).
- c) Owner labels only.

**Q03.5 Type A/B**
- a) *Recommended.* A: the curve is at least 50% of revenue and the confirmed M04 stage is introduction or growth. B: the curve is under 50% and the company's confirmed M04 stage is mature, shake_out or decline (R6 "established company"; AMZN is confirmed mature, so AWS is B). n_a: fund, treasury-asset or shell periods. Anything else is unassigned. The owner can override in the file. Why: listing age misleads (SPCX, SPAC CIKs; pack 3.2a).
- b) Years since the first 10-K.
- c) The owner sets every type.

**Q03.6 Persistence baseline**
- a) *Recommended.* `growth_runs` against the all-filer median from the CY frames (about 10–15 requests once, re-used for 30 days), showing the CKL baselines. Why: CKL's baselines are all-firm medians, so this is the closest match (S-new-M03-4); a segment is not a firm, so segment runs are labelled indicative.
- b) Against the category median (2–5 companies).
- c) Defer.

**Q03.7 R14**
- a) *Recommended.* A base-rate card worded as R14 requires (a paraphrase of S01, dollar wealth, not returns); `wealth_created` deferred. Why: it states R14 exactly, with no new source (S01).
- b) Compute `wealth_created` now.
- c) Doc text only.

**Q03.8 Signal key and weight**
- a) *Recommended.* The curve label goes in the signal name (`curve_stage.aws`), with no schema change. MY ✓ at "medium until calibrated" in M01's weights row; PT/ST info. Why: it fits the D13 key as built (pack 5.4a), and the thresholds are uncalibrated (LESSONS).
- b) Add a `subject` column (a migration that changes D13), with MY as "lead".
- c) One row per company, for the main curve only.

Defaults with no question of their own (strike them if you disagree):
- Case 5 (external revenue and the 50% captive flag).
- The not-rising clause for `past_inflection` (case 10).

## Build parts
**Part 1 — Curves**
- **Goal:** the curve map, curve series, `curve_type`, `curve_stage`, the M03 tab and the R14 card.
- **Code:** `src/engine/leaders/` with `curves.py` (map loader; series with breaks, recasts, captive flag, shell boundary), `stage.py`, `views.py` and `step.py` (local refresh pass, 0 requests); signals via `write_signal`. Company curves reuse M04's fiscal-year points (`financials/capex.py` `fy_points`), the shell boundary `entity_link` / tags, and `segment_table()`'s break and rename logic, not copies.
- **Tables:** none expected. A cache, if needed, takes the next free migration at build (after M04 4b-lite 0038, 8a 0039 and the earlier MVP waves M07+M09, M08+M05; merge order).
- **Review kinds:** none.
- **UI:** a new "Leaders & curve" tab (`tabs/m03.html`), mocked up on stored data first: the curve table, unmapped candidates and the R14 card.
- **Live check:** `uv run python scripts/run_leaders.py curves --no-sec`: 0 requests, under a minute.
- **Fixtures:** AWS 2021–25, NVDA Data Center FY2024–26, Intel Foundry (total and external), the MU segment-set break, the BA rename, the INFQ boundary. Only NVDA FY2025/26 trimmed instances exist (`tests/fixtures/m04/`, segments only); the others need an owner probe run that saves trimmed instances (Claude cannot call SEC), else synthetic `fact_dim` rows on the published figures, labelled.
- **Depends on:** M04 1c and 7a (built). `cvd_state` notes show "pending M04 8a" until 8a lands.

**Part 2 — Leaders and persistence**
- **Goal:** `leader_rank` and `growth_runs`.
- **Code:** `leaders/rank.py`; `leaders/runs.py` (frame median per calendar year, tag priority as in `peers.py`).
- **Tables:** none (uses `frame_value`).
- **UI:** a leader table per category on the theme page (`theme.html`), plus rows on the M03 tab; M04's `market_share_chg_pp` (grade B or A) shown beside the rank once 8a lands, else "missing: no share data".
- **Live check:** `uv run python scripts/run_leaders.py leaders`: about 10–15 frame requests the first time, about 1 minute; `--no-sec` after that.
- **Fixtures:** cloud with 1 of 3 curves having data; a two-curve category; a run that reaches the start of history; a synthetic median (illustrative).
- **Depends on:** Part 1, M02 themes, M04 Part 2 peers.

## Open risks
- **Unverified figures.** The NVDA Data Center axis, Google Cloud and Azure figures are not checked yet, so leader rows may read "missing" more often than expected.
- **Short history.** The 3-year filing window gives about 5 fiscal years, and only 3 after a break (MU). That caps runs and delays stage readings.
- **Unassigned types.** 8 names stay unassigned until their M04 stage confirmations are done.
- **INFQ comparatives.** D-M04-8 keys the shell boundary on period end, which excludes the operating company's own prior-year comparatives. Its stage waits about 2 years unless the owner sets a series start.
- **HBM is invisible in facts** (it sits inside CMBU), so the outline's MU example needs DS16 owner shares or text at tuning.
- **The all-filer median includes micro-caps and SPACs.** It may sit low and make runs easy to achieve. It is labelled, and calibrated later.
- **Signal names with labels** (`curve_stage.aws`): M01 and the confluence readers must read the prefix as the signal family.

## Check notes (2026-10-13)
Adversarial check against the outline, DESIGN (R6, R14, D8, D13/D14), M04 Signals out and build-log notes, migrations 0001–0037 and `src/engine/`.
1. **Outline fit.** AMD and ALAB (outline examples) are neither core nor promoted, so their segment curves are not stored; this was silent. Added to Purpose and to Q03.1a (UI promotion as RIVN, ~25 + ~12 requests each). "Share accelerating" (Leaders item 3) now names its MVP reading (growth gap plus M04 `market_share_chg_pp`). S-curve items 2 (latency) and 4 (before the crowd) were dropped silently; now listed as owned by M11 (R4) and M02 (D-M02-10) / M08.
2. **Binding decisions.** Q03.5a typed every curve under 50% as B, which drops R6's "established company" (AMZN International would read B); added the confirmed M04 stage condition. Q03.1c extends instance reads to the tracked tier, which amends D-M04-80; now stated. Q03.2a's "no review items" sat against D8; it now names the tab's "Open for the owner" list as D8's queue in MVP form, with (b) for real queue items. No question re-asks a decided point.
3. **Data reality.** All named tables, functions and files exist (`fact_dim`, `company_stage`, `frame_value`, `entity_link`, `peer_member`, `theme`/`theme_company`/`tier_member`, `rows()`, `recasts()`, `segment_table()`, `renames()`, `write_signal`, `peer_facts.py`, `theme.html`). Corrected: intersegment rows are stored only on `srt:ConsolidationItemsAxis` and are filtered out by `segment_table()` (Intel's external split is a build check); "all years are in the stored 10-Ks" softened to "should hold, checked at build"; frames need clarified (runs start 2020). Migration numbering: "TBD after 0038, 0039" now says next free number in merge order after the earlier MVP waves. Fixtures: only NVDA FY2025/26 trimmed instances exist; the others need an owner probe or labelled synthetic rows.
4. **Numbers and sources.** AWS increments and growth, NVDA increments, shares (18.0%, 89.7%) and Intel figures recomputed and correct; the pack correction on AWS 2024 is right. Intel figures now carry their years and source (2024-04-02 8-K recast). The R14 card was presented as Bessembinder's wording; it is a paraphrase of S01 and now says so (S01's "58%" fix stays deferred to S4.5). "cloud" marked as an illustrative category; its "1 of 3" result tied to the pack's checked figures. Market-size gap: register DS16/DS17 are taken (market share, credit ratings); next free DS number.
5. **MVP discipline.** 4 signals, 8 questions, 2 parts, 0-request and ~1-minute live checks: fine. Added the D13 rules (cik key, one row per timeframe, value vs value_text, source_ref, D-M04-9). `curve_type` grade: A matches `lifecycle_stage`'s code; added B when the owner sets a type with no filing input (D14).
6. **Overlap.** Company curves now reuse M04's `fy_points`, tags/`entity_link` and `segment_table()` logic; M04's `market_share_chg_pp` (8a) is shown, not rebuilt. No M02 signal duplicates the four.
