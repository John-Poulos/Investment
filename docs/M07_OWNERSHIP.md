# M07 — Ownership & insiders

Status: MVP design decided 2026-10-13 (sitting 1, D-M07-1…8); build parts 1–2 below · Updated: 2026-10-13 · Outline headings: Ownership and Insiders (items 1–4) · Depends on: M00 (SEC data: Form 4 parser D-SEC-10, 13F reader D-M02-45/46), M04 Part 1a (cover count, implied float, close, splits), M01 (rule 6, "ownership medium" in MY) · Sources: S05, S09, S10, S15, S46, S-new-M07-1…19, S-new-M08-28, -29 (provisional IDs from `docs/M07_DESIGN_PACK.md` and `docs/M08_DESIGN_PACK.md` "New sources"; numbered into SOURCES.md at Part 1)

Research: `docs/M07_DESIGN_PACK.md`; MVP cut: `docs/mvp/M07_MVP_BRIEF.md`; cross-module plan: `docs/mvp/MVP_PLAN.md`. Thresholds marked † are starting values, calibrated at tuning. Missing data stays missing (`method` = "missing: <reason>"), never zero (D-M04-9). Outputs are research signals; sale items are warnings only and the owner decides (D8, D16).

## Purpose
Are insiders buying with their own money, are they selling outside their plans, and are the managers the owner follows adding? Binding: R7 (weight opportunistic buys; routine and 10b5-1 sales are noise unless abnormal), R13 (totals from raw Form 4s), R16 (Form 4 and 13D/G in all timeframes; 13F lagged), R22 ($, % of seller's stake, % of float and volume; G/A/M/F out of $ totals).

## Inputs
| Data | Source (stored in; code) | Grade | Refresh |
|---|---|---|---|
| Form 4 rows: code, shares, price, shares_after, D/I, role, footnotes, `is_10b5_1`, `plan_basis` | `insider_txn` (0001, 0005); `sec/insiders.py` `transactions()` | A | Logon refresh, per new Form 4 |
| Form header: 4 vs 4/A, `aff_10b5_1`, joint owners | `form4_doc` (0005) | A | Same |
| Holding lines without a transaction (all non-derivative lines; derivatives apart) | new `form4_holding` (Part 1, form4-2 re-parse from the HTTP cache) | A | Same |
| CMP class per (owner, issuer, year) | new `insider_class` (Part 1) | A (derived) | Each 1 January and on new rows |
| Cover count, implied float | M04 signals `shares_cover`, `implied_float_shares`; `financials/shares.py` `cover_counts`, `implied_float`, `close_on`, `splits_after` (reused, D-M04-2) | A | Per new filing |
| Close and 20-day volume | `price_bar` (0012) | A (D-M04-82) | Daily |
| Followed managers' 13F-HR rows | `fin_13f`, `fin_holding`, `fin_issuer_map` (0023); `financing/thirteenf.py`, `issuers.py`; `config/m07_managers.toml` | A | On a new 13F-HR from a followed manager |
| Short interest | none (DS18, gap; D-M07-8) | — | — |

## Signals out
Every row: `cik` key (ticker for display, D-M04-74), `module_id = "M07"`, numbers in `value`, classes in `value_text` (D-M04-9), grade A (D14), `source_ref` = newest accession "+N" with every form in `method`, one row per timeframe, `as_of` = filing date (alerts fire on the filing day, not the trade day). ✓ = may carry weight once D13 weights exist; info = weight 0. PT and ST stay info until M01 designs those columns.

| Signal | value / value_text | Meaning | MY | PT | ST |
|---|---|---|---|---|---|
| `insider_buy` | $ of open-market P rows / `opportunistic`, `routine`, `unclassified`, `purchase_from_issuer` | An insider bought with own money (R7); % of stake after, % of cover count, cluster count in `method` | ✓ vote (opportunistic +1, D-M07-2) + M01 rule 6 alert; unclassified: alert, no score | info | info + alert |
| `insider_sale` | $ of S rows only / `plan`, `plan_na`, `non_plan_routine`, `non_plan_opportunistic`, `non_plan_unclassified` | R22 sale card; F/M/A/G rows listed "not in total"; % of stake before, of cover count, of implied float, of 20-day ADV | warning for `non_plan_opportunistic`, and `non_plan_unclassified` ≥ 10%† of stake (D-M07-3); else info | info | info |
| `insider_net_flow` | net $ = open-market P − non-plan S / `net_buy`, `net_sell`, `plan_only`, `none` | Outline item 3; plan, `plan_na` and gross S shares and $ shown beside, not netted (D-M07-5) | info | info | info |
| `followed_manager_13f` | Δ shares / `new`, `add`, `cut`, `exit`, `hold`, `mixed` | Outline item 2: buys by managers the owner follows; soft and lagged (quarter end and filing date in `method`) | ✓ (soft) | info | info (weight 0) |

Windows for `insider_net_flow`: MY 12 months, PT 3 months, ST 30 days. A window with no P/S gives `none` with no value; a window that starts before the stored Form 4 history gives "missing: history starts <date>". Event signals leave scoring after the profile window and stay visible (D10).

## Timeframe parameters
| Parameter | MY | PT | ST |
|---|---|---|---|
| Net-flow window | 12 months | 3 months | 30 days |
| Cluster window (attribute on `insider_buy`) | 90 days, ≥ 3† distinct opportunistic buyers | — | — |
| Weight (M01) | ownership medium | info until M01 PT column | info until M01 ST column |

## Rules
1. **Discretionary codes only.** P and S are the only discretionary trades; A, D, F, M, G, J, K, C, X, W, U never enter $ totals or classes (R22, S-new-M07-17). P bought from the issuer, a private placement, or A with a price and a contract footnote → `purchase_from_issuer`: shown, not scored, not in net flow (Tan, S-new-M07-18).
2. **CMP class (S09)** per (owner CIK, issuer CIK), set each 1 January from P/S rows in the 3 prior calendar years: P/S in the same calendar month in each of those years → routine; P/S in all 3 years without a common month → opportunistic; any of the 3 years without P/S → `unclassified`, never defaulted. Years used are stored. One owner CIK per person (rows carry the first joint owner, D-SEC-10); clusters count distinct CIKs.
3. **Plan status** per row: footnote-identified plan → `plan`; checkbox set but row not identified → `plan_na` (shown apart, not in net); otherwise non-plan, with `plan_basis` on every card (D-SEC-10).
4. **Stake** = all non-derivative lines on the form (D-M07-4); derivatives shown apart; only a Form 3 on file → stake missing.
5. **Cover count and float** from M04 (D-M04-2): source and date in `method`; multi-class names use M04's class-summed count; 20-F filer (GFS) or new listing → "float unknown", never 0. ADV: raw volume with the `splits_after` guard; no bars → ADV share missing.
6. **One row per company and filing day.** `write_signal` upserts on (cik, module, signal, timeframe, as_of), so same-day forms aggregate: value = summed $ (or Δ shares), `value_text` = the strongest class present (buys: opportunistic, unclassified, routine, `purchase_from_issuer`; sales: non-plan opportunistic → plan; 13F: `mixed` when managers differ). Per-form cards are built by the Insiders tab view from stored rows, not from `signal`.
7. **Form 4/A** replaces the original, matched by (owner, date, shares); no repeat alert.
8. **13F (D-M07-6):** rows summed by CUSIP; put/call rows apart; values in thousands before 2023-01-03 (LESSONS); amendments replace; a followed manager with no 13F for a quarter → missing for that quarter, never "exit". Rows of companies that are not ours are not stored and not queued (keep-filter before `thirteenf.store_rows`); our CUSIP unresolved → held once with the CUSIP shown.
9. **Alerts** (M01 rule 6): opportunistic and unclassified buys alert on the filing day in the end-of-run box; sale warnings never block (D16).

## Failure modes
| Input or indicator | How it can mislead | Guard |
|---|---|---|
| CMP class on short history | Everyone looks opportunistic | `unclassified`, never defaulted; 4-year window (D-M07-1) |
| CMP evidence | Predictability sits mainly in small firms and 1986–2014 samples; the effect may have decayed (S09, S-new-M07-1, -2) | Starting weights; MY only; literature labelled as such |
| Direct-line stake | Overstates a sale's share of the stake (Huang 11×) | All non-derivative lines (form4-2, D-M07-4) |
| Mega-cap net flow | Nearly always selling (stock pay, plans) | Info only; plan sales shown apart (D-M07-5) |
| 10b5-1 plans | Strategically timed plans read as noise (S-new-M07-6) | Known MVP blind spot; plan registry deferred (R2 below) |
| Footnote parsing | A misread footnote flips plan status | `plan_basis` on every card |
| Code A contract buys | Read as an own-money buy | `purchase_from_issuer` (rule 1) |
| Joint filings, family entities | Separate CIKs inflate a cluster | Distinct owner CIKs; cluster is an attribute, not a vote |
| Same-day forms | Overwrite each other in `signal` | Rule 6 aggregation |
| 13F | Stale (45 days, S15), long-only, copying adds little after costs (S-new-M07-15) | "lagged" in `method`; soft weight in MY, 0 in ST |
| 13F units | Thousands before 2023-01-03 | Unit switch by filing date (LESSONS) |
| 13F rows in M02 | Followed-manager rows appear as M02 K1 edges, Money flow rows, `m02_13f_issuer` items | Keep-filter; M02 decision at Part 2 (MVP_PLAN item 7) |
| Short interest | Absent, so the tab could read as "none" | "missing: no short-interest source" (D-M07-8) |

## Decisions
- D-M07-1 (2026-10-13, sitting 1, Q07.1a): `form4_years = 4`; one owner-run fetch of the missing year (back to ~2022-10, the window the setting keeps) before the first logon refresh on the new setting; the dry run prints the exact count (est. a few hundred requests, 1–3 minutes). Why: CMP needs P/S rows in the 3 prior calendar years and the class stays complete each 1 January (S09); applies R7. The setting is recorded as D-SEC-27 at Part 1.
- D-M07-2 (2026-10-13, Q07.2a + vote line): buys CMP cannot classify alert in every timeframe and carry no score. **Vote line** (MVP_PLAN overlap 2, owner-confirmed): `insider_buy` is M07's confluence vote — opportunistic = +1 in MY; no qualifying buy = missing, never 0; routine, unclassified and `purchase_from_issuer` do not vote; non-plan opportunistic sales are listed as reasons. Why: a default class would score noise; the alert keeps every own-money buy visible (R7, R16, M01 rule 6; pack 1.1a; S09, S-new-M07-1, -2, -3).
- D-M07-3 (2026-10-13, Q07.3a): non-plan sales — MY warning for `non_plan_opportunistic`; `non_plan_unclassified` warns only at ≥ 10%† of stake; routine and plan sales are info. Why: opportunistic sales carried −78 bps a month (S09); only large sales that are a large % of holdings predict (S-new-M07-7); applies R7, R22, D16.
- D-M07-4 (2026-10-13, Q07.4a): stake denominator = all non-derivative lines on the form, via a form4-2 re-parse from the HTTP cache (0 requests expected; misses counted and fetched); derivative lines apart. Why: the direct line alone overstates Huang's sale 11× (pack 3.1a, S-new-M07-18); applies R13, R22.
- D-M07-5 (2026-10-13, Q07.5a): net flow = open-market P − non-plan S, info in every timeframe; plan and `plan_na` sales and gross S shares and $ shown beside (the outline's CoreWeave figure, S05). Why: outline item 3 asks for the balance "with context given to scheduled 10b5-1 sales"; R7 makes plan sales noise; R13 raw rows.
- D-M07-6 (2026-10-13, Q07.6a): the fourth signal is `followed_manager_13f` for owner-named managers (Part 2); 13D/13G about our companies deferred (R4 below), so R16's 13D/G half is not met in the MVP: schedules stay listed in `fin_schedule` headers and M02's Money flow tab. Why: outline items 1–2 name smart-money 13Fs; reuses `thirteenf.py` at about 25–40 requests per manager once, then about 4 per new 13F-HR (R16 lagged; S15, S-new-M07-14, -15).
- D-M07-7 (2026-10-13, Q07.7a): owner-edited `config/m07_managers.toml` starts with Duquesne Family Office (Druckenmiller) and Berkshire Hathaway; filer CIKs verified at Part 2. "CEO of equity" is **not identified** by the owner, so DESIGN Q3 stays open; the guess "CEO of Fidelity" (Abigail P. Johnson, FMR; she appears in Fidelity's GFS 13G/A, S-new-M07-18) is unconfirmed and not added.
- D-M07-8 (2026-10-13, Q07.8a; plan QP.3 yes): short interest (outline Ownership item 4) is owned by M07 and deferred to tuning; DS18 "short interest" registered as a gap; the Insiders tab shows "missing: no short-interest source" (display line, no D13 row); M07 Part 1's live check adds one Massive short-interest probe request. Why: Massive Basic access is unverified (its docs and pricing page disagree, S-new-M08-29) and the FINRA API needs an owner account (S-new-M08-28); research in M08 pack Round 4.

## Deferred to tuning
From the pack rounds, unless a decision above says otherwise:
- R1: Ali–Hirshleifer definition (S-new-M07-5), role multiplier (S-new-M07-4), Insider Transactions Data Sets from 2006 (DS6).
- R2: plan registry and cooling-off (Item 408 finder, review items), Form 144, gift, hedge and late-filing flags (S10, S-new-M07-8…11).
- R3: economic stake (options, RSUs), affiliate float (D-M04-2's implied float stands), totals by role and month.
- R4: 13D/13G about our companies, threshold crossings, lockups (SPCX, INFQ) (S-new-M07-12, -13).
- R5: all-holder 13F Data Sets (~96 MB a quarter), passive/active split (S-new-M07-17).
- R6: decay, backtest calibration, PT/ST weights (needs M01's PT/ST columns).
- Short interest as a signal (D-M07-8; options in the brief's Q07.8b: Massive with FINRA fallback, about 16 calls twice a month).

## Build parts
Pre-assigned in `docs/mvp/MVP_PLAN.md` (wave W2/W3); parts of one module never run in parallel. Part decisions continue at D-M07-9.

**Part 1: Insider signals (Form 4)** — branch `m07-part1`, wave W2 (main checkout, merges first), migration `0040_m07_insiders`, D-SEC-27 (form4-2, `form4_years`), D-STO-30, D-UI-32 (Insiders tab cards), DS18 (short interest).
- Code: `sec/insiders.py` form4-2 (holding lines; the `PARSER_VERSION` bump makes `sync_insiders` re-parse every Form 4 from the cache, so the owner script runs it before the first logon refresh on the new code); new package `ownership/`: `classes.py` (CMP), `cards.py` (stake, cover, implied float, ADV via `financials/shares.py`), `step.py` (local pass after `prices_step`, 0 SEC requests; slot per MVP_PLAN refresh order), `views.py`; owner script `scripts/run_ownership.py insiders [--history] [--no-sec]`.
- Tables: `form4_holding(accession, line, table_kind, title, shares, direct_indirect, nature, footnotes)`, `insider_class(owner_cik, issuer_cik, year, class, years_used, months_seen)`, a 4/A link column.
- UI: Insiders tab with buy and sale cards, a net-flow strip per window, class and plan columns, the short-interest missing line; one Overview row (latest buy, net flow MY). Review kinds: none.
- Fixtures: synthetic Form 4 XML in the layout of Huang (9 lines, F row, footnote F3), Musk (25 P rows, trust) and Tan (code A, offer-letter footnote); a 4/A pair; Director X / CFO Y / CEO Z histories.

**Part 2: Followed managers** — branch `m07-part2`, wave W3, no migration expected, D-SEC-28 (manager filing sync, 13F keep-filter), D-UI-34 (followed-managers panel), DS11 row update.
- Code: `config/m07_managers.toml`; `ownership/managers.py` runs `sync_filings` for each manager (so `thirteenf.due` finds its 13F-HRs) and `thirteenf.read_filing` with the keep-filter (rule 8), so `financing/step.issuer_items` never queues other companies; the refresh SEC part runs only when the daily index shows a new 13F-HR from a followed manager. Records the next free D-M02 on whether M02 views skip followed-manager filers.
- UI: "Followed managers (lagged)" panel on the Insiders tab.
- Fixtures: a Berkshire-style information table with split rows per CUSIP and a pre-2023 thousands filing.

## Live checks (owner runs, sends the log)
- Part 1: `uv run python scripts/run_ownership.py insiders --no-sec` (cache re-parse, 0 SEC; misses counted), then `--history` (the D-M07-1 year: a few hundred SEC requests, 1–3 minutes, count printed first), plus one Massive short-interest probe request (D-M07-8). Checked against Huang (0001045810-25-000143), Musk (0001104659-25-089693), Tan (0001127602-25-010360) and the AAPL 60 forms / 170 rows (D-SEC-10).
- Part 2: `uv run python scripts/run_ownership.py managers`: about 25–40 SEC requests per manager (Berkshire's long submissions history may need more pages; dry run prints the count); checked against Berkshire → AAPL 2024-06-30 (789,368,450 → 400,000,000 shares, `cut`).

## Open questions
- **DESIGN Q3:** who is "CEO of equity"? Added to `config/m07_managers.toml` once named (D-M07-7).
- PT and ST columns and weights: M01 open question.
- Whether M02 views skip followed-manager filers: decided at Part 2 (next free D-M02, MVP_PLAN item 7).
- Short-interest source: after the Part 1 probe, at tuning (DS18).
