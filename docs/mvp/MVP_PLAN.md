# MVP plan (cross-module)
Updated 2026-10-13 · Basis: DESIGN D31, the nine briefs in `docs/mvp/` (M03, M05–M12), M04_BUILD_LOG "MVP path" and "Parallel waves", the M00 decision lists, migrations 0001–0037 and `scripts/run_refresh.py` · Status: for owner decision (plan questions QP.1–QP.3 at the start of sitting 1). Research signals, not advice.

## Summary
One row per module. "Questions" counts the brief's questions; "+1" is a question this plan restores. Request costs are from the briefs; "SEC" requests are owner-run (Claude cannot call SEC).

| Module | MVP signals | Questions | Build parts | New data and request cost | Depends on |
|---|---|---|---|---|---|
| M04 core (decided) | 4b-lite: `gc_language`, `covenant_status`. 8a: `cvd_state` (+ confidence, coverage), `f_quality`, `market_share_chg_pp` (gauge `normalized_ep_*` / `overreaction_gap` and Red Flag 1 `burn_no_share_gain` deferred, owner 2026-10-13) | 0 | 2 | None (stored text and facts; owner share entries, DS16) | 4a (built) |
| M07 Ownership | `insider_buy`, `insider_sale`, `insider_net_flow`, `followed_manager_13f` | 7 +1 (Q07.8) | 2 (1 if Q07.6d; 3 if Q07.6c) | SEC: Form 4 4th year, a few hundred requests once (Q07.1a); 13F about 25–40 per manager once, about 4 per new 13F | M04 1a |
| M09 Technicals | `band_z`, `trend_state`, `mom_12_1`, `rev_1m` | 8 | 2 | Tiingo: SPY, 1 full-history request then 1 a day (Q09.6a) | M04 4a; 8a soft |
| M08 Valuation | `valuation_multiple`, `valuation_pctile`, `peg`, `est_revision` | 7 | 2 | Alpha Vantage `EARNINGS_ESTIMATES` about 16 a week (≤ 3 a day); optional Tiingo peer prices (Q08.2b) | M04 1a–4a, stage confirmations; 8a NEP soft |
| M05 Capex | `capex_demand`, `growth_capex_roic`, `bookings_cover`, `commitment_cover` | 8 | 2 | None (stored facts and text) | M04 1b; 8a CvD soft |
| M03 Leaders | `curve_type.*`, `curve_stage.*`, `leader_rank.*`, `growth_runs.*` | 8 | 2 | SEC: CY frames 2019–23, about 10–15 requests once | M04 1c, 7a; 8a share soft |
| M06 Moat | `moat_quant`, `moat_verdict`, `challenger_max_rung`, `moat_gate` | 8 | 2 | None (CXMT alias, one config line) | M04 1b, 1c, 2; Part 2 needs 8a |
| M10 Macro | `macro_regime` (own table), `macro_exposure_warning`, `policy_event_exposure`, `move_context` | 8 | 2 | FRED keyless ≤ 7 a day (+1 GNPDEF); Federal Register 2–4 a day (first run 6–10); SPY shared with M09 | M04 4a; M02 7b |
| M11 Thesis + core | `confluence` (M00), `thesis_state`, `exit_warning`, `size_cap` | 8 | 2 | None (owner-entered theses and lots) | 4b-lite, 8a, every other MVP module's votes |
| MVP dashboard (M00) | none (reads `signal`) | 0 | 1 | None | M11 Part 2 |
| M12 Options (after MVP) | `cc_window`, `next_earnings`, `iv_pct_252`, `cc_template` | 8 | 2 | FRED 5 a day; Massive about 26 a day (≈ 5.5 min); backfill ≈ 3,000 calls (≈ 10.5 h, owner-run); Alpha Vantage 1 a week | M09, M10 FRED client, M11 lots, 4b-lite, 8a |

Totals for the MVP (M12 excluded): 32 new signals (M03, M05–M11), 63 module questions plus 3 plan questions in 5 sittings, 19 build parts (2 M04 + 16 + dashboard) in 10 waves.

## Overlaps and conflicts between briefs
Resolution first, then the reason. The top three are marked ★.

1. ★ **Short interest is asked nowhere.** M07's brief removed Q07.8 and points to "Q08.8"; M08's brief removed Q08.8 and points to "Q07.8". **Resolution:** M07 owns it (D15 module map; the outline puts it under Ownership item 4). The plan restores it as Q07.8 in sitting 1, using M08 pack Round 4 as its research:
   - a) *Recommended.* Defer to tuning, record DS18 "short interest", show "missing: no short-interest source" on the Insiders tab, and add one Massive probe request to M07 Part 1's live check. Why: Massive Basic access is unverified (its docs and pricing page disagree, S-new-M08-29), and the FINRA API needs an owner account (S-new-M08-28).
   - b) An info row `short_interest` (% of cover count, days to cover, settlement date) from Massive with a FINRA fallback, as M07 Part 3: about 16 calls twice a month.
   - c) Skip it.
2. ★ **The confluence vote map (M11 Q11.4a) does not match the briefs.**
   - M07: the map votes `insider_net_flow`, which M07 makes info in every timeframe (Q07.5a); `insider_buy` is M07's only MY ✓ row.
   - M03: M11 puts M03 in the low tier (weight 1); M03 Q03.8a says "medium until calibrated". M01's weights row names neither.
   - Money flow (a lead tier in M01) has no D13 writer: M02 writes no rows. M11 case 17 says M05 shares M02's `capex_stated` input family, but M05's `capex_demand` reads `capex_split` (XBRL PP&E); M02's own-definition capex is only shown beside it.
   - **Resolution:** each sitting confirms one "vote line" for its module, as a default to strike (no extra question): M07 `insider_buy` (opportunistic +1, no qualifying buy = missing, never 0) with non-plan opportunistic sales listed as reasons; M03 at the tier the owner picks in Q03.8; M05 `capex_demand` as the capex vote. M11's `config/confluence.toml` takes the confirmed lines, and the M11 sitting records the tiers once as an M01 amendment (next free D-M01). Money flow: QP.2.
3. ★ **Shared helpers proposed two or three times.** Resolution: the first part to need a helper builds it, and the others reuse it.

   | Helper | Proposed by | Built by (wave) | Reused by |
   |---|---|---|---|
   | SPY symbol in `prices_step` (no cik, no D13 rows) | M09 Q09.6, M10 Q10.7a, M11 hurdle | M09 Part 1 (W2) | M10 move_context, M11 hurdle (tuning), M12 |
   | Completed-week reader `technicals/bars.py` | M09; M10 uses "the chart's Monday-keyed weeks", which include the partial week | M09 Part 1 (W2) | M10 `move_context` (one week definition), M12 |
   | Earnings-in-window rule (`accepted_at`, Tesla 2.02 deliveries) | M09 `news_move`, M10 catalysts, M12 calendar | M09 Part 1 (W2) | M10 extends it with news and policy catalysts |
   | M01 rule readers (rules 1, 3, 4, 7 from M04 rows) | M09 `qualify.py`, M11 `size_cap` no-add gate, M12 `blocked_thesis` | M09 Part 1 (W2) as `src/engine/m01_rules.py` | M11, M12; the rule-4 reason list stays in one place, so M05's Q05.4a amendment (AHEAD_OF_DEMAND) reaches M11's `exit_warning` without code in two places |
   | FRED client `macro/fred.py` | M10, M12 (5 series), M09 (VIX, deferred), M11 (CPI, deferred) | M10 Part 1 (W8) | M12 Part 1, tuning |
   | Realized volatility | M11 (σ60d, σ1y), M12 (rv20) | M11 Part 2 (W9) as `prices/vol.py` | M12 |
   | ROIC series over n fiscal years | M05 (now vs 3 FYs earlier), M06 (10 years, so 11 balance sheets) | M05 Part 1 (W4), in M04's `trends.py` | M06 Part 1 (M04 decision, next free) |

4. **Next earnings date.** M08 case 18 ("walk-down window", ≤ 30 days before a report) needs a forward date; only M12, after the MVP, builds `next_earnings`. **Resolution:** M08 Part 2 adds a cadence estimate (grade C) in a shared `calls/calendar.py` from `company_releases`; M12 later adds the IR headline (A) and vendor (B) sources to the same helper.
5. **"Cyclical" means three things.** M08's R6 flag (EPS sign change or margin range ≥ 30 pp), M06's `moat_quant` class "cyclical" (ROIC median above the hurdle), and M04's CvD states and trough-to-trough cycle dates (D-M04-83). **Resolution:** M08 owns the company-level R6 flag (owner override in `config/valuation.toml`); M06 renames its class `through_cycle`; NEP windows stay M04's. Raise in sittings 2 and 3 as a default to strike.
6. **Alpha Vantage's 25-a-day budget** (D-M02-20): transcripts keep 20, M08 ≤ 3 a day, M12 1 a week, probes from the spare. **Resolution:** the M08 sitting confirms the split; M02 stays the budget owner.
7. **13F rows from followed managers leak into M02** (K1 edges, Money flow "other filers", `m02_13f_issuer` items). **Resolution:** M07 Part 2 adds the keep-filter before `thirteenf.store_rows` and records an M02 decision (next free D-M02) on whether M02 views skip followed-manager filers.
8. **Two big-move detectors.** M09 `rev_1m` (4-week return, z vs 26 weeks, reversal candidate) and M10 `move_context` (1-week excess return vs SPY, z vs 52 weeks, explanation). **Resolution:** keep both (different questions), but on one week reader and one catalyst rule (item 3).
9. **Consistent, no action:** market share is M04 8a's (`market_share`, D-M04-68); M03 and M06 only read it. M05's AHEAD_OF_DEMAND is the D-M04-64 test, not a second one. M06 `moat_gate` blocks a first MY entry in M11's `size_cap` (R1). M09 Q09.3a and Q09.2a are compatible with every Q12.5/Q12.6 option, so M12's sitting can wait; only Q09.2b (switch to `pullback_sigma`) would change M12's add zone.
10. **Numbers left "TBD" in every brief** (migrations, DS entries; M03, M06 and M10 note collisions with DS12–DS17). Pre-assigned below.

## Plan questions (answer at the start of sitting 1)
**QP.1 Order**
- a) *Recommended.* Sittings and waves as below: M04 4b-lite + 8a build first, during sitting 1. Why: 8a is a hard dependency of M06 Part 2 and M11 Part 2, and a soft one for M03, M05, M08, M09 and M12; with it merged, later live checks read real CvD states instead of "missing: CvD not built".
- b) DESIGN's sitting order with 8a built after the first module waves.

**QP.2 Money-flow vote** (M01 lists money flow as a lead input; nothing writes it)
- a) *Recommended.* Add an optional thin M02 writer in W10 (one D13 row per spender and linked supplier from built M02 data: capex-guide direction from `changes.py` and the confirmed `spender_link` level), designed in the M11 sitting. Why: otherwise a lead tier is empty in every confluence score ("k of n" shows it, D-M04-56).
- b) Leave it empty in the MVP; revisit at tuning.

**QP.3 Short interest:** add Q07.8 to sitting 1 (item 1 above). Yes / no.

## Owner sitting order (High effort, one module or pair per sitting)
**Before sitting 2:** clear the 8 open `m04_stage` items (BA, INFQ, INTC, MU, NVDA, SPCX, TSLA, RIVN) and, if possible, the 7 open peer sets. Until then M08 routes only 7 names (`stage_unconfirmed`), M03 leaves 8 types unassigned, and M06's peer GM z reads missing.

| Sitting | Modules | Questions | Why this pairing and place |
|---|---|---|---|
| 1 | M07 + M09 (+ QP.1–3) | 16 + 3 | No 8a dependency and no setup data; both are market-data modules (Form 4, prices). Q09.6 settles SPY for M10 and M11; Q07.8 closes the short-interest gap |
| 2 | M08 + M05 | 15 | Both are fundamentals on stored facts that read 8a (NEP, CvD); both touch `xbrl_facts` extra concepts; settles the cyclical flag (item 5), the Alpha Vantage split (item 6) and M05's M01 rule-4 amendment |
| 3 | M03 + M06 | 16 | The outline's chain "space → leader → financials → moat"; both read 8a market share, peers and confirmed stages; Q03.8's tier and M06's verdict feed the vote map |
| 4 | M10 | 8 | Distinct topic; feeds M11's policy trigger (Q11.6) and the hurdle inputs |
| 5 | M11 | 8 (+ QP.2 design) | Needs every vote line; decides confluence, sizing and killswitches last (D31) |
| 6 | M12 (after W9) | 8 | Brief only; built after the MVP; reads M09's and M10's answers; gates DESIGN Q5 |

M04 4b-lite + 8a need no sitting (decided: D-M04-34, D-M04-1…68); the owner approved the 4b-lite + 8a mock-up on 2026-10-13 (gauge and Red Flag 1 deferred). Consequence for sitting 2: M08's NEP-based reading (soft dependency on 8a) has no `normalized_ep_*` rows in the MVP — M08 either computes its own NEP in its Part 1 or reads it as missing; settle in Q08 at sitting 2.

## Build waves (Medium effort)
Two parts per wave: the first in the main checkout (merges first), the second in a git worktree (rebased on main after the first merges). Live checks one at a time. The main checkout stays on `main` (or the part in its live check) whenever the PC may refresh (2026-10-13 incident).

| Wave | Main checkout (merges first) | Worktree | Needs | Live checks (requests) |
|---|---|---|---|---|
| W1 | M04 4b-lite | M04 8a | — (now) | 4b-lite subcommand (0 SEC, stored text only); `run_financials.py cvd --no-sec` (0) |
| W2 | M07 Part 1 | M09 Part 1 | Sitting 1 | `run_ownership.py insiders` (re-parse 0, `--history` a few hundred SEC; +1 Massive probe if QP.3/Q07.8a); `run_technicals.py signals` (1 Tiingo) |
| W3 | M07 Part 2 | M09 Part 2 | W2 | `run_ownership.py managers` (25–40 SEC per manager); M09 tab on real DB (0) |
| W4 | M08 Part 1 | M05 Part 1 | Sitting 2, stages cleared, W1 | `run_valuation.py value --no-sec` (0); `run_m05.py demand --no-sec` (0) |
| W5 | M08 Part 2 | M05 Part 2 | W4 | `run_valuation.py estimates --probe …` (5 AV); `run_m05.py commitments --no-sec` (0) |
| W6 | M06 Part 1 | M03 Part 1 | Sitting 3, W4 (ROIC helper) | `run_moat.py quant` (0); `run_leaders.py curves --no-sec` (0) |
| W7 | M06 Part 2 | M03 Part 2 | W6, W1 (8a `cvd.py`) | `run_moat.py challengers` (0); `run_leaders.py leaders` (10–15 SEC) |
| W8 | M10 Part 1 | M11 Part 1 | Sittings 4, 5 | `run_macro.py regime` (7 FRED + SPY reuse); `run_m11.py thesis --no-sec` (0) |
| W9 | M10 Part 2 | M11 Part 2 (confluence, size_cap) | W8, all module parts | `run_macro.py policy` (6–10 Federal Register); `run_m11.py confluence --no-sec` (0) |
| W10 | MVP dashboard (M00) | M02 thin writer (if QP.2a) | W9 | App on the real DB (0); writer `--no-sec` (0) |
| After | M12 Part 1, then Part 2 | — | Sitting 6 | `run_options.py probe` (≈ 22 requests); `window --no-net` (0) |

Notes:
- 4b-lite's command name is set at its build (the M04 log's `gate-text` included the EFTS pass that the MVP drops).
- Parts of one module never run in parallel, so module decision IDs are simply "next free"; only shared numbers are pre-assigned.
- **Refresh local-step order** (each part adds its slot; all after `prices_step`, short write transactions): M04 local steps (financials, units, gate, quality, then gate text, CvD) → M05, M06, M03 → M07 → M08 → M09 → M10 → M11 thesis → confluence → M12. Network additions sit with their own fetchers (Form 4 in the SEC part; SPY in `prices_step`; FRED and Federal Register in the M10 step; Alpha Vantage after transcripts).
- **Shared files that conflict in a wave** (keep both sides at rebase): `scripts/run_refresh.py`, `ui/app.py` context, `tabs/overview.html`, `sec/xbrl_facts.py` (W4), the M00 decision lists, `config/aliases.toml`.
- **Dashboard (W10):** one page with a row per core and promoted company and a column per module's headline row (value_text, grade, as_of, missing reason), the confluence "k of n" per profile and open alerts. It reads `signal` only, with 0 requests.

## Pre-assigned IDs per build part
Rules: migration numbers are 1..n with no gaps (`store/db.py`). A part marked "none expected" that turns out to need a migration takes the next number at its merge, and every later number moves up by one (as M04 did on 2026-10-12); the same applies to D-STO. D-SEC-26 was reserved for M04 Part 6 and recorded as unused, so it stays retired and D-SEC continues at 27. Highest in use today: D-SEC-25, D-STO-27, D-UI-29, D-M04-94, D-M02-61, D-M01-6, DS17.

| Wave | Part (branch) | Engine migration | D-SEC | D-STO | D-UI | DS (new gap) | Module decisions |
|---|---|---|---|---|---|---|---|
| W1 | M04 4b-lite (`m04-part4b-lite`) | 0038_m04_gate_text | — | 28 | 30 (quote view on gate rows) | — | D-M04-95…99 (unused ones recorded as such) |
| W1 | M04 8a (`m04-part8a`) | 0039_m04_cvd | — | 29 | 31 (M04 tab, share form) | — (DS16 built) | D-M04-100 onward |
| W2 | M07 Part 1 (`m07-part1`) | 0040_m07_insiders | 27 (form4-2, `form4_years`) | 30 | 32 (Insiders tab cards) | 18 (short interest, if Q07.8a) | D-M07-1…8 from sitting 1, parts from 9 |
| W2 | M09 Part 1 (`m09-part1`) | none expected | — | — | 33 (SPY benchmark symbol) | — (DS8 row) | D-M09-1…8, parts from 9 |
| W3 | M07 Part 2 (`m07-part2`) | none expected | 28 (manager filing sync, 13F keep-filter) | — | 34 (followed-managers panel) | — (DS11 row) | next free |
| W3 | M09 Part 2 (`m09-part2`) | none | — | — | 35 (Technicals tab, overlays) | — | next free |
| W4 | M08 Part 1 (`m08-part1`) | none expected | 29 (`MinorityInterest`) | — | 36 (Valuation tab) | — | D-M08-1…7, parts from 8 |
| W4 | M05 Part 1 (`m05-part1`) | none expected | 30 (contract liabilities, total and noncurrent) | — | 37 (Future spend section) | — | D-M05-1…8, parts from 9 |
| W5 | M08 Part 2 (`m08-part2`) | 0041_m08_estimates | — | 31 | 38 (Estimates block) | 19 (analyst estimates) | next free |
| W5 | M05 Part 2 (`m05-part2`) | 0042_m05_commitments | 31 (purchase-obligation concepts per tag) | 32 | 39 (commitment lines) | 20 (commitments beyond XBRL, prior 10-Q text) | next free |
| W6 | M06 Part 1 (`m06-part1`) | 0043_m06_verdict | — | 33 | 40 (Moat section, verdict setup) | 21 (fluidity / TNIC) | D-M06-1…8, parts from 9 |
| W6 | M03 Part 1 (`m03-part1`) | none expected | — | — | 41 (Leaders & curve tab) | 22 (market size / TAM) | D-M03-1…8, parts from 9 |
| W7 | M06 Part 2 (`m06-part2`) | 0044_m06_challenger | — | 34 | 42 (challenger list and form) | — | next free (+ next free D-M04 for the `cvd.py` hook) |
| W7 | M03 Part 2 (`m03-part2`) | none expected | 32 (CY frames 2019–23) | — | 43 (theme leader table) | — | next free |
| W8 | M10 Part 1 (`m10-part1`) | 0045_m10_macro | — | 35 (incl. FRED in the refresh) | 44 (Macro page, Overview line) | 23 (FRED macro series) | D-M10-1…8, parts from 9 |
| W8 | M11 Part 1 (`m11-part1`) | 0046_m11_thesis | — | 36 | 45 (Thesis tab, Portfolio page) | 24 (broker import) | D-M11-1…8, parts from 9 |
| W9 | M10 Part 2 (`m10-part2`) | 0047_m10_policy | — | 37 | 46 (policy event list) | — | next free (+ next free D-M02 for the `fedreg.py` extension) |
| W9 | M11 Part 2 (`m11-part2`) | 0048_m11_caps | — | 38 | 47 (confluence line, theme exposure) | — | next free (+ next free D-M01 if tiers change) |
| W10 | MVP dashboard (`mvp-dashboard`) | none | — | — | 48 | — | — |
| W10 | M02 writer (`m02-flow`, optional) | none expected | — | — | — | — | next free D-M02 (from 62) |
| After | M12 Part 1 (`m12-part1`) | 0049_m12_iv | — | 39 | — | 25 (ex-dividend dates; IV is DS5) | D-M12-1…8, parts from 9 |
| After | M12 Part 2 (`m12-part2`) | 0050_m12_window | — | 40 | 49 (Options tab) | — | next free |

New module docs (MODULE_TEMPLATE, D9 failure modes), written in each module's first part: `M03_LEADERS.md`, `M05_CAPEX.md`, `M06_MOAT.md`, `M07_OWNERSHIP.md`, `M08_VALUATION.md`, `M09_TECHNICALS.md`, `M10_MACRO.md`, `M11_THESIS.md`, `M12_OPTIONS.md`. Cross-module amendments raised in sittings (M01 rule 4 for Q05.4a, M01 rule 1 for M06's gate, M01 weights for Q03.8 and Q11.4, M02 for Q05.7) take the next free D-M01 / D-M02 number at that sitting; sittings are sequential, so they cannot clash.

## Remaining work and completion
**Basis:** each MVP build part counts equally. The MVP has **28 parts**: M04's 11 (9 merged: 0, 1a, 1b, 1c, 2, 3, 4a, 6, 7a; 4b-lite and 8a to build), 2 each for M03 and M05–M11 (16) and the dashboard. Left out: the optional extras (M02 writer, M07 Part 3), M00–M02 (built before D31) and M12 (after the MVP). The last column counts the nine MVP signal modules (M04, M03, M05–M11) that write D13 rows.

| After | Parts merged | MVP done | Modules writing rows (of 9) |
|---|---|---|---|
| Now | 9 of 28 | 32% | 1 (M04) |
| W1 | 11 | 39% | 1 |
| W2 | 13 | 46% | 3 (+ M07, M09) |
| W3 | 15 | 54% | 3 |
| W4 | 17 | 61% | 5 (+ M08, M05) |
| W5 | 19 | 68% | 5 |
| W6 | 21 | 75% | 7 (+ M06, M03) |
| W7 | 23 | 82% | 7 |
| W8 | 25 | 89% | 9 (+ M10, M11) |
| W9 | 27 | 96% | 9, confluence live |
| W10 | 28 | 100% | 9 (+ M02 if QP.2a) |

**Remaining:** 5 sittings for the MVP (+1 for M12), 19 build parts in 10 waves (+2 for M12, +1 or 2 optional). **Pace:** waves A and B each merged within about a day with 1–2 live-check re-runs (PRs #37–#41, 2026-10-12/13). At one wave per owner day, with sittings 1–5 overlapping waves W1–W5, the MVP is about 10–12 owner days, so roughly 3 weeks at 4 days a week. The percentage is by part count, so it overstates progress on heavy parts (8a, M11 Part 2) and understates it on UI-only parts (M09 Part 2, the dashboard).

## Risks for the MVP as a whole
- **Rework when deepened.** Thin signals change encoding at tuning: M03's K fit and quarterly TTM, M06's `m06_metrics`, M08's history cache and revenue revisions, M09's backtest and band choice, M11's credibility card and Kelly. Guard: stable signal names, parameters in config with a version in `method` (M09's `v1` pattern), † starting values labelled. The confluence score built on 1–3 votes per name (M04 alone today: "+1.00, 1 of 7") will move as modules land; it is shown with k of n and has no entry threshold in the MVP (Q11.4a).
- **Data gaps that shape readings.** 8 unconfirmed stages and 7 open peer sets (M08 routing, M03 types, M06 peer z); the 3-year filing window (about 5 fiscal years; Form 4s from about 2023-10 until Q07.1); news only since 2026-10; Alpha Vantage coverage of INFQ, SPCX and GFS unknown; market share only as owner entries (DS16); no IV source (M12, DS5); non-SEC peers (SK hynix, Samsung, TSMC) missing in M03 and M06; prior 10-Ks partial (DS7).
- **Owner load per week** (at 4 days and one wave a day):
  - 1–2 sittings in each of the first two weeks;
  - up to 8 mock-up approvals and 8 live checks a week, plus re-runs, which LESSONS expects for the text finders (4b-lite, M05 Part 2, M10 Part 2);
  - one-off setup: 8 stages and 7 peer sets (week 1), 15 M06 verdicts, 4 challenger markets and the M03 curve file (week 2), theses, lots, caps and the M10 topic file (week 3);
  - owner-run fetches: Form 4 history, 13F managers, CY frames, the Alpha Vantage probe and (after the MVP) the 10.5-hour IV backfill;
  - new review items: `m04_cvd`, `m04_gc_text`, `m04_covenant`, `m06_verdict` (15), alongside M02's 10 a week.
  Keep at most one live check in flight; if the week fills, pause the waves, not the sittings.
- **Logon refresh budget** (3 h, PC off overnight, D-M02-12). New daily network: SPY 1, FRED ≤ 7, Federal Register 2–4, Alpha Vantage ≤ 3, 13F only on new filings. The one-off form4-2 re-parse of every cached Form 4 must run owner-side before the first logon refresh on that code (M07 brief). M12's 5.5 minutes a day comes after the MVP.
- **Alert volume.** The end-of-run box gets M07 opportunistic buys, M11 kill hits and M10 `no_catalyst` moves; deduplicate per criterion and week (M11 case 14), and record first runs as baselines (LESSONS).
- **Merge friction.** Every wave touches `run_refresh.py`, `app.py`, `overview.html` and the M00 decision lists; the numbering rules above prevent number clashes, not text conflicts.
- **Licences.** Tiingo, Alpha Vantage and Massive data and BAA10Y (terms checked at build) stay internal (S68, D-UI-2); the dashboard is not shareable.
