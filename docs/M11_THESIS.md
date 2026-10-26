# M11 — Thesis, sizing & killswitch (and the core confluence score)

Status: MVP design decided 2026-10-25 (sitting 5, D-M11-1…8, every recommended option and default; M01 tiers D-M01-10; M02 money-flow writer D-M02-64); Part 1 next (wave W8) · Updated: 2026-10-25 · Outline headings: Entry, Size, Exit and Killswitch (items 1–5); Technical Analysis (item 4, confluence); Understand why an asset is or is not moving (item 5, "edge, not moving = early") · Depends on: M00 (`signal`, positions, lots, decisions, prices), M01 (rules 1–7 via `m01_rules.py`), M04 (gates, CvD, F-quality, guidance ledger and scorer), every voting module (M02, M03, M05–M08), M10 (policy events, move sentence, CPI), M09 (SPY) · Sources: S80, S86, S-new-M11-n (pack; numbered into SOURCES.md at Part 1)

Research: `docs/M11_DESIGN_PACK.md`; MVP cut and sitting record: `docs/mvp/M11_MVP_BRIEF.md`; cross-module plan: `docs/mvp/MVP_PLAN.md`. Thresholds marked † are starting values, never tuned on the watchlist alone (D32). Missing data stays missing, never zero (D-M04-9). Warnings and ceilings only, not financial advice; the owner makes every final call (D8, D16).

## Purpose
For each held or watched name: a written, versioned thesis with dated milestones and exit criteria written at entry; whether it is early, on track or wrong (R4); killswitch warnings (M01 rule 4 plus thesis triggers and shared theme keys, R23); a size ceiling; and the core per-timeframe confluence score (D13 "core computes", module_id M00). Binding: R1, R4, R5, R19, R23, D11/D12, D13/D14, D16, D27, D-M01-5…10, M01 rules 1–7, M04's "How M01 reads M04" table. Departs from the outline: "optimise size" is only a ceiling (no Kelly); the score has no entry threshold in the MVP.

## Inputs
| Data | Source (stored in; code) | Grade | Refresh |
|---|---|---|---|
| Module votes | `signal` rows of M02 (Q11.9 writer, W10), M03, M04, M05, M06, M07, M08; map `config/confluence.toml` | per row | Logon local pass |
| M01 gates and exit reasons | `m01_rules.py` (rules 1, 3, 4, 7: gate, filing status, CvD, `guidance_removed`, AHEAD_OF_DEMAND, `moat_gate`) | A | Same |
| Guidance milestones | `guidance`, `guidance_outcome`, `guidance/record.py` (shared scorer, latest guide, D-M04-10), `changes.py` | A / B | Per release |
| Event and KPI milestones | owner entry with a stored-document quote (A) or a note (B); `unit_metric` (DS2) | A / B | On entry / per filing |
| Open milestone sentences | `guidance_unparsed` items held for M11 (D-UI-14/15) | A | — |
| 8-K events | `event` | A | Per refresh |
| Policy events, move sentence, CPI | M10 `policy_event_exposure` (W9), `move_note`, `macro_series` CPIAUCSL (W8) | A / B | Daily |
| Prices, volatility | `price_bar` (adj close, split factor), SPY; `prices/vol.py` (Part 2) | A | Daily |
| Themes and spenders | `theme`, `theme_company`, confirmed `spender_link`, `capex_stated` | A / B | Per refresh |
| Positions, lots, decisions | `position`, `lot`, `decision` (0001; M11 adds cik, thesis and criterion columns), hand-entered (broker import DS24 deferred) | B (owner) | On entry |
| Theses, milestones, criteria, caps | `thesis`, `milestone`, `kill_criterion` (Part 1, 0046), `exposure_cap` (Part 2, 0048) | owner | On entry |

## Signals out
Keyed by `cik`, one row per timeframe, numbers in `value`, states in `value_text`, missing = "missing: <reason>", grade = weakest deciding input, `source_ref` = newest accession "+N" (D-M04-9). M01 defines MY weights only; PT and ST reuse them, labelled. Several theses on one cik (D11): the row shows the worst state, `method` lists each. A shared theme killswitch is written on every linked cik's `exit_warning` row.

| Signal | value / value_text | Meaning | MY | PT | ST | Grade |
|---|---|---|---|---|---|---|
| `confluence` (module_id M00) | [−1, 1]; `split`; no votes = missing row "0 of n"; "k of n" and the vote vector in `method` | Σ w·g·s ÷ Σ w·g over reporting, non-stale votes, one per module | ✓ | ✓ | info | weakest counted vote |
| `thesis_state` | no_thesis / early / on_track / review / exit_warning | R4 early vs wrong; fill-or-kill review after each 10-Q / 10-K | ✓ | ✓ | ✓ | weakest deciding milestone (owner-only = B) |
| `exit_warning` | armed / warning / hit / acknowledged; reasons and sources in `method` | M01 rule 4 plus thesis triggers and shared keys (D16) | ✓ | ✓ | ✓ | weakest deciding input; a hit needs A, or B confirmed by a second source |
| `size_cap` | % of portfolio; binding cap, `blocked: <gate>` or `over_cap: <theme>` | A ceiling and the rule 1 / rule 3 no-add gate | ✓ | ✓ | ✓ | A when the vol cap binds; B when owner-entered lots bind |

Shown without D13 rows (D32): every company's confluence line incl. "0 of n" with each module's vote or missing reason; for every held position all three caps, σ60d, σ1y, 1-year maximum drawdown and portfolio weight; lot age with the "< 1 yr" note; the R5 hurdle (lot return − SPY total return; CPI stretch) once M10 Part 1's CPI lands (Part 2).

## Timeframe parameters
| Parameter | MY | PT | ST |
|---|---|---|---|
| Vote weights | tiers per D-M01-10 | MY reused, labelled | info |
| Vote staleness | 120 days† | 120 days† | 10 days† |
| Entry threshold | none in the MVP (until ≥ 3 lead modules report) | none | none |

## Rules
1. **Thesis.** One versioned thesis per position plus watch-only theses; saved only with ≥ 1 kill criterion; an edit makes a new version; held positions without one read `no_thesis`.
2. **Milestones.** Guidance milestones take `guidance_outcome` (hit → hit; miss → missed; pending → open; removed / expired → withdrawn; dropped → shown, never a trigger; unscored / missing → unscorable with the reason; non-GAAP without a stated actual or `definition changed` → unscorable, never a miss). Event / KPI milestones: target and due date, quote (A) or note (B); KPI from `unit_metric` where stored, else owner-set; restated target = `slipped`; due passed without a hit = `missed`; no measurable target = `narrative`, never scored. Owner milestones (B) stay out of company credibility.
3. **States.** On track with price flat or down and CvD not damage / decline → `early` (M01 rule 5); CvD missing → "on track, CvD missing", never early; a 10-Q / 10-K after the last review → `review` with `review_due`.
4. **Slips.** Second slip, or any slip with a charge (quoted) → `exit_warning`; one slip without a charge → `review`.
5. **Killswitch triggers.** M01 rule-4 reasons (gate fail, overdue filing, CvD damage / decline, `guidance_removed`, AHEAD_OF_DEMAND), plus: a thesis-metric guide `lowered` (a `definition changed` row blocks it); rule 4 here; 8-K items the owner picks; M10 `policy_event_exposure` stated or confirmed on an owner-picked topic (from W9). `owner_rule` shown only. Hit needs A, or B confirmed by a second source; C never fires. Price drawdown is context only. Acknowledgement writes a `decision`; repeats only if the trigger worsens, deduplicated per criterion and week; hits go to the refresh's end-of-run alert box and a Portfolio banner (M01 rule 6), no review kind.
6. **Shared capex key** (per theme, confirmed spenders): one spender lowers its current-year capex guide → `warning`; ≥ 2† in the same season → `hit`; a spender's own position counts its own cut (D-M02-5); a closed position deactivates its criteria, a shared key stays while any linked position remains.
7. **Confluence.** One headline vote per module from `config/confluence.toml` (D-M11-4): M04 `cvd_state` (CYCLICAL_TROUGH +1; NO_SLOWDOWN → `f_quality` ≥ 4 +1, 3 → 0, ≤ 2 −1; STUMBLE / AMBIGUOUS 0; damage / decline −1); M05 `capex_demand`'s vote line (positive +1, neutral 0), fabless / outsourced `commitment_cover` (RISING +1, FALLING −1, FLAT 0, short_history missing); M06 `moat_verdict` (WIDE +1, NARROW +0.5†, NONE −1, UNRATED / N_A missing); M07 `insider_buy` (opportunistic +1, none missing); M08 `est_revision` (up +1, flat 0, down −1, not_meaningful missing); M03 `curve_stage.*` of the largest mapped curve (emerging / accelerating +1, past_inflection 0, declining −1); M02 `money_flow` (D-M02-64); M09 and M10 none. Weights per D-M01-10; grades A 1, B 0.5, C 0 (shown); missing and stale votes leave the denominator. Lead modules of opposite sign → no score, `split`, vector shown.
8. **Size cap.** min(owner per-position cap, risk budget ÷ max(σ60d, σ1y), theme headroom with full weight in each active theme); a no-add gate from `m01_rules.py` (first entry: rule 1 incl. `moat_gate`; tranches: rule 3) → 0 with the gate named; fewer than 60 bars → vol cap missing, the others apply; above cap after a rise → `over_cap`, never a forced trim.

## Failure modes
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| Thin vote set | MU's +1.00 rests on 3 of 7 modules; one module early in the MVP looks unanimous | "k of n" always shown; no entry threshold until ≥ 3 lead modules report |
| M04 vote in a strong year (D32) | All 17 active names NO_SLOWDOWN (2026-10-13), so M04 = F-quality, an improvement score: decliner INTC votes +1 | CvD overrides in a slowdown; labelled; checked on non-tech names at tuning |
| Two modules on one input | Spender capex counted by M02 and M05 | Spender gets no M02 vote (D-M02-64); one vote per family declared in the map |
| Owner-entered theses and milestones | Written after the move (rationalisation) | Versioned with dates; owner-only = B, out of credibility |
| Non-GAAP guides, changed definitions | False misses | Unscorable, never a miss |
| Walk-downs | Beat a lowered bar | Latest-guide scorer (D-M04-10) with the walk shown; first-guide scoring at tuning |
| Price stops | Sell cyclicals at the trough (MU 2022–23) | Drawdown is context only (S-new-M11-15) |
| One grade-B report | A rumour kills a thesis | Hit needs A or a second source; C never fires |
| One spender's cut | A reallocation read as a slowdown | One cut = warning; ≥ 2 in a season = hit |
| Shared capex key seeded on tech (D32) | Only `ai_infrastructure`'s five hyperscalers | Keys exist only where M02 has confirmed spender links; other industries labelled "no shared key" |
| KPI milestones (D32) | Only Tesla deliveries are code-scored | Other KPIs owner-set (B), labelled |
| Volatility cap | Low vol before a shock | Vol only caps; tranches follow M01 rule 3 |
| Short history (SPCX) | No vol cap | Missing, other caps apply |
| PT / ST weights | Undefined in M01 | MY reused, labelled |

## Decisions
- D-M11-1 (2026-10-25, sitting 5, Q11.1a): one versioned thesis per position plus watch-only theses; lots entered by hand; a thesis is saved only with at least one kill criterion. Why: outline Entry 1 "know exit before entry"; pre-commitment (S-new-M11-3).
- D-M11-2 (2026-10-25, Q11.2a): guidance milestones linked to a ledger row take M04's outcome; event / KPI milestones with target and due date, quoted (A) or noted (B), KPI status from `unit_metric` where stored; a "Make milestone" action on open `guidance_unparsed` items. Why: closes D-UI-14 and reuses the shared scorer.
- D-M11-3 (2026-10-25, Q11.3a): `exit_warning` at the second slip or any slip with a charge; one slip without a charge → `review`. Why: a charge is hard evidence the delay costs money (Boeing 777-9: $4.9B with the 2027 slip, S-new-M11-18).
- D-M11-4 (2026-10-25, Q11.4a + defaults): core `src/engine/confluence.py` (module_id M00), one headline vote per module from `config/confluence.toml` with the map in rule 7 (the vote lines confirmed in sittings 1–4; `commitment_cover` as M05's vote for fabless / outsourced channels; NARROW = +0.5†); tiers per **D-M01-10**; technicals excluded; grades A 1 / B 0.5 / C 0; no entry threshold until ≥ 3 lead modules report. Why: simple weights match fitted ones on small samples (S-new-M11-8, -9); one vote per module avoids double counting.
- D-M11-5 (2026-10-25, Q11.5a): lead modules of opposite sign → no single score, text `split`, vector shown, no review item. Why: an average hides the conflict (D10); fewer queue items (S86).
- D-M11-6 (2026-10-25, Q11.6a): extra triggers per rule 5 (thesis-metric guide lowered, the slip rule, owner-picked 8-K items, M10 policy events on an owner-picked topic from W9); `owner_rule` shown only; hit needs A or B + a second source; price drawdown context only. Why: price stops lower returns without momentum (S-new-M11-15); D16.
- D-M11-7 (2026-10-25, Q11.7a): shared capex killswitch per theme on confirmed spenders: one lowered current-year guide → warning, ≥ 2† in a season → hit. Why: D-M02-5 has no cross-company totals in v1; one cut can be a reallocation.
- D-M11-8 (2026-10-25, Q11.8a + defaults): `size_cap` per rule 8, gates read from `m01_rules.py`; conviction tiers and Kelly later. Standard rows shown for every held position and the R5 hurdle as a Part 2 display line on M10's CPI and the stored SPY (D32). Why: each cap guards a different risk; volatility mainly trims tails (S-new-M11-12); R23 needs the theme cap; R5 is approved and its inputs exist by W8.
- **D-M01-10** (recorded in `docs/M01_TIMEFRAMES.md`): confluence tiers lead 3 / medium 2 / low 1.
- **D-M02-64** (recorded in `docs/M02_THEMES.md`, plan QP.2a, Q11.9a): the supplier-side `money_flow` writer (W10).

## Deferred to tuning
R19 credibility card and first-guide scoring (M04's `guidance_hit_rate` stands in); non-GAAP stated actuals; Brier scores; conviction tiers and ½-Kelly; M01 rule-1 entry threshold and `entry_plan`; `lot_status` as a D13 row; `m11_kill_hit`, `m11_cap_breach` and disagreement review kinds; caps on shared keys beyond themes; broker import (DS24); pre-mortem; turnover display; hurdle as a D13 row.

## Build parts
**Part 1 — Thesis, milestones, killswitch** (wave W8; branch `m11-part1`; migration `0046_m11_thesis`; D-STO-36; D-UI-45; DS24 row; decisions from D-M11-9). Code: `src/engine/thesis/` (record, milestones, kill, step, views); "Make milestone" in `review.py`. Tables `thesis` (versioned), `milestone` (versioned; set_by, grade, quote reference), `kill_criterion` (`shared_key` = theme key); cik on `position`, thesis / criterion on `decision`. Signals `thesis_state`, `exit_warning` in the logon local pass after M10 (0 requests). UI: company Thesis tab (versions, milestones, criteria, reasons, M10's move sentence and exposure line, acknowledge button writing a `decision`); Portfolio page (positions, lot entry, lot age). Live check: `uv run python scripts/run_m11.py thesis --no-sec` (0 requests, under a minute) after the owner enters a BA thesis (v3 from the open item, v1 / v2 as owner notes) and RIVN, MSTR and NVDA watch theses: expect BA hit on v3's charge, RIVN hit (gate fail), MSTR hit ("removed"), NVDA hit (`guidance_removed` 2026-05-20), `hyperscaler_capex` armed or "no confirmed spender link". Fixtures: Boeing v1–v3, MSTR removals, RIVN gate fail, NVDA GM miss and removal, the Alphabet raise; D32: a utility rate-case milestone (owner-set).

**Part 2 — Confluence (core) and size_cap** (wave W9; branch `m11-part2`; migration `0048_m11_caps`; D-STO-38; D-UI-47). Code: `src/engine/confluence.py`, `config/confluence.toml`, `src/engine/thesis/sizing.py`, `src/engine/prices/vol.py` (shared with M12). Table `exposure_cap`. UI: confluence line on Overview (k of n, vector, split); exposure by theme, standard risk rows and the hurdle line on Portfolio. Live check: `uv run python scripts/run_m11.py confluence --no-sec` (0 requests, under a minute). Fixtures: today's MU (+1.00, 3 of 7), RIVN (−0.50, 2 of 7), NVDA (0 of 7), a split case, SPCX short history, MU 2023 CYCLICAL_TROUGH; D32: a bank ("class not mapped" from M10, F-quality per its rows).

## Live checks (owner runs, sends the log)
- Part 1: `uv run python scripts/run_m11.py thesis --no-sec`.
- Part 2: `uv run python scripts/run_m11.py confluence --no-sec`.

## Open questions
- Staleness 120 / 10 days, the ≥ 2-spender hit, the 60-bar minimum, NARROW = +0.5 and the F-quality mapping are uncalibrated starting values.
- Confirmed `spender_link` rows for `ai_infrastructure` are unchecked from Claude's side (data\ not readable); the Part 1 log says.
